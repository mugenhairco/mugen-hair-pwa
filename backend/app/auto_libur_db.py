"""
auto_libur_db.py — Auto-Libur untuk Barber yang Tidak Absen
=============================================================================
PERMINTAAN OWNER: "jika role barber tidak absen maka otomatis direkap
dibuat libur (dan mengurangi kuota libur) dalam sebulan" -- HANYA aktif
kalau Owner mengaktifkan `auto_libur_tidak_absen_aktif` di Pengaturan
Izin & Cuti (izin_cuti_settings, default OFF -- tenant yang belum
mengaktifkannya TIDAK terpengaruh sama sekali).

KOREKSI Owner (revisi berikutnya dari permintaan di atas): barang yang
tidak check-in TIDAK LANGSUNG dianggap Cuti -- dianggap LIBUR lebih dulu,
mengurangi jatah "Kuota Libur per bulan" (Owner-editable,
`kuota_libur_bulanan`, 0 = tidak dipakai). Baru kalau Kuota Libur bulan
itu SUDAH HABIS, tanggal berikutnya diambilkan dari kuota gabungan
Izin&Cuti (izin_cuti_settings.kuota_gabungan_hari, lihat izin_cuti_db.py).
Kalau KEDUA kuota itu SAMA-SAMA habis, tanggal tetap dicatat sebagai Libur
(supaya rekapan tetap lengkap, bukan hilang begitu saja) TAPI ditandai
`sumber='auto_libur_kelebihan'` di `absensi_libur` -- inilah yang dipakai
Rekap Bulanan (routers/rekap.py, lihat ada_kelebihan_kuota_bulan_ini() di
bawah) untuk menstabilo baris "Hari Libur" barber itu warna merah.

Menjembatani TIGA modul yang SENGAJA berdiri sendiri satu sama lain
(attendance_db.py, izin_cuti_db.py, dan konsep Barber Holiday di
database.py, lihat docstring masing-masing) -- sengaja ditulis di file
TERPISAH (bukan menambah logika ini ke salah satu modul itu) supaya
independensi ketiganya untuk pemakaian lain tetap utuh.

TIDAK ADA infrastruktur scheduler/cron di proyek ini sama sekali (lihat
catatan panjang di faspay_settlement_db.py) -- mengikuti pola yang sama
persis: diproses lewat PEMICU MANUAL Owner/Admin (tombol "Proses Auto-
Libur" di Pengaturan Izin & Cuti), bukan job otomatis di background.

Definisi "hari kerja yang diharapkan" untuk seorang barber pada satu
tanggal (SEMUA syarat harus terpenuhi baru dianggap "seharusnya masuk"):
  1. Toko TIDAK toko_libur pada tanggal itu (booking_db.is_toko_libur).
  2. Tanggal itu termasuk hari_operasional toko (booking_db.is_hari_operasional).
  3. Barber itu TIDAK absensi_libur pada tanggal itu (Barber Holiday,
     booking_db.is_barber_libur) -- ini SEKALIGUS mekanisme idempotensi
     untuk tanggal yang SUDAH ditandai Libur (manual ATAU oleh Auto-Libur
     sendiri di proses sebelumnya), tidak perlu cek terpisah.
  4. Barber itu TIDAK punya pengajuan izin_cuti (status pending/disetujui,
     jenis izin ATAU cuti) yang mencakup tanggal itu -- sudah ada alasan
     resmi (atau sudah pernah diproses jadi Cuti oleh Auto-Libur), tidak
     perlu direkap ulang.
  5. Tanggal itu SUDAH LEWAT (< hari ini, WIB) -- TIDAK PERNAH memproses
     hari ini/masa depan, barber masih punya kesempatan check-in.

Kalau KELIMA syarat di atas terpenuhi DAN barber itu SAMA SEKALI tidak
punya baris attendance_logs untuk tanggal itu (benar-benar tidak pernah
check-in -- BUKAN sekadar lupa check-out/terlambat, itu urusan Absensi
sendiri, tidak disentuh di sini) -> tanggal itu dicatat lewat cascade
2 tingkat di atas (Libur dulu, baru Cuti&Izin, baru Libur lagi kalau
kedua kuota habis).

Baris Cuti ditulis LANGSUNG lewat SQL (bukan izin_cuti_db.buat_pengajuan())
supaya TIDAK memicu notifikasi push per-hari (satu bulan penuh tidak
masuk bisa sampai ~20+ notifikasi berturut-turut ke barber & Owner/Admin
-- spam, bukan informasi berguna) -- ringkasan hasil proses dikembalikan
sebagai response API biasa, cukup dilihat sekali di UI Owner. Baris Libur
ditulis lewat database.tandai_libur() (fungsi yang sudah ada, dipakai
bersama UI Barber Holiday manual) dengan parameter `sumber` baru.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import booking_db
import database as db
import izin_cuti_db
from database import get_conn

logger = logging.getLogger("mugen.auto_libur")

WIB = ZoneInfo("Asia/Jakarta")

DIAJUKAN_OLEH_AUTO_LIBUR = "Sistem (Auto-Libur)"
SUMBER_AUTO_LIBUR = "auto_libur"
SUMBER_AUTO_LIBUR_KELEBIHAN = "auto_libur_kelebihan"


def migrasi_absensi_libur_sumber():
    """JALUR SQLITE SAJA (dipanggil dari main.py::on_startup() bersama
    migrasi_*() lain) -- PRAGMA table_info() di bawah ini SQL SQLite murni.
    Menambah kolom `sumber` ke `absensi_libur` (idempotent) supaya baris
    yang dibuat Auto-Libur bisa dibedakan dari Barber Holiday manual --
    lihat SUMBER_AUTO_LIBUR/SUMBER_AUTO_LIBUR_KELEBIHAN di atas. Jalur
    PostgreSQL: kolom yang sama sudah langsung dibuat lewat
    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` di postgres_schema.py."""
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(absensi_libur)").fetchall()]
        if "sumber" not in kolom:
            conn.execute("ALTER TABLE absensi_libur ADD COLUMN sumber TEXT")


def _hari_ini_wib() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d")


def _tanggal_list_bulan(tahun: int, bulan: int) -> list:
    """Seluruh tanggal (YYYY-MM-DD) di bulan itu yang SUDAH LEWAT (< hari
    ini) -- bulan berjalan otomatis berhenti di kemarin, bulan yang sudah
    lewat penuh mencakup semua tanggal, bulan yang belum mulai/masih
    depan menghasilkan list kosong."""
    hari_ini = _hari_ini_wib()
    awal = datetime(tahun, bulan, 1)
    bulan_berikutnya = datetime(tahun + 1, 1, 1) if bulan == 12 else datetime(tahun, bulan + 1, 1)
    akhir_eksklusif = bulan_berikutnya
    hasil = []
    d = awal
    while d < akhir_eksklusif:
        tgl = d.strftime("%Y-%m-%d")
        if tgl < hari_ini:
            hasil.append(tgl)
        d += timedelta(days=1)
    return hasil


def _sudah_ada_izin_cuti(barber_id: int, tanggal: str) -> bool:
    """Barber sudah punya pengajuan izin_cuti (jenis apa pun, status
    pending/disetujui) yang mencakup tanggal ini -- sudah ada alasan
    resmi, JANGAN direkap ulang jadi auto-libur."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM izin_cuti WHERE barber_id = ? AND status IN ('pending', 'disetujui') "
            "AND tanggal_mulai <= ? AND tanggal_selesai >= ? LIMIT 1",
            (barber_id, tanggal, tanggal),
        ).fetchone()
    return row is not None


def _sudah_ada_attendance_log(barber_id: int, tanggal: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM attendance_logs WHERE barber_id = ? AND tanggal = ? LIMIT 1",
            (barber_id, tanggal),
        ).fetchone()
    return row is not None


def _libur_auto_terpakai_bulan_ini(barber_id: int, tahun: int, bulan: int) -> int:
    """Jumlah baris absensi_libur bulan ini yang SUMBER-nya Auto-Libur
    (SUMBER_AUTO_LIBUR/SUMBER_AUTO_LIBUR_KELEBIHAN) -- SENGAJA TIDAK ikut
    menghitung Barber Holiday manual (sumber NULL, di luar kendali Auto-
    Libur ini), supaya "Kuota Libur/bulan" murni jatah untuk hari tidak
    check-in, bukan tercampur jatah cuti manual yang Owner sendiri
    berikan."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ? AND tanggal LIKE ? "
            "AND sumber IN (?, ?)",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%", SUMBER_AUTO_LIBUR, SUMBER_AUTO_LIBUR_KELEBIHAN),
        ).fetchone()
    return row["jumlah"]


def ada_kelebihan_kuota_bulan_ini(barber_id: int, tahun: int, bulan: int) -> bool:
    """Dipakai Rekap Bulanan (routers/rekap.py) untuk stabilo merah -- True
    kalau ADA minimal satu tanggal bulan ini yang Auto-Libur terpaksa
    mencatat sebagai Libur PADAHAL Kuota Libur bulanan DAN kuota gabungan
    Izin&Cuti SAMA-SAMA sudah habis (permintaan Owner)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ? AND tanggal LIKE ? AND sumber = ?",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%", SUMBER_AUTO_LIBUR_KELEBIHAN),
        ).fetchone()
    return row["jumlah"] > 0


def ada_kelebihan_kuota_bulan_ini_sekarang(barber_id: int) -> bool:
    """Wrapper ada_kelebihan_kuota_bulan_ini() utk BULAN KALENDER BERJALAN
    (WIB) -- dipakai routers/izin_cuti.py::ambil_sisa_kuota_semua_barber()
    (tabel ringkasan kuota Absensi > Owner) supaya router tidak perlu tahu
    detail resolusi tanggal WIB (fungsi _hari_ini_wib() di atas privat)."""
    hari_ini = _hari_ini_wib()
    return ada_kelebihan_kuota_bulan_ini(barber_id, int(hari_ini[:4]), int(hari_ini[5:7]))


def get_sisa_kuota_libur_bulan_ini(barber_id: int, tenant_id: int) -> dict:
    """PERMINTAAN OWNER: kartu "Sisa Kuota Libur" (Absensi barber & Owner)
    -- BEDA dari kuota gabungan Izin&Cuti (izin_cuti_db.get_sisa_kuota(),
    yang anchor ke periode Owner-editable) -- Kuota Libur SELALU reset per
    BULAN KALENDER (WIB), TIDAK ikut periode Izin&Cuti sama sekali. Return
    {"aktif": bool, "kuota": int|None, "terpakai": int|None, "sisa": int|None}
    -- `aktif`=False (semua field lain None) kalau Owner belum mengisi
    kuota_libur_bulanan (0/default)."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    kuota = settings.get("kuota_libur_bulanan", 0)
    if kuota <= 0:
        return {"aktif": False, "kuota": None, "terpakai": None, "sisa": None}
    hari_ini = _hari_ini_wib()
    tahun, bulan = int(hari_ini[:4]), int(hari_ini[5:7])
    terpakai = _libur_auto_terpakai_bulan_ini(barber_id, tahun, bulan)
    return {"aktif": True, "kuota": kuota, "terpakai": terpakai, "sisa": max(0, kuota - terpakai)}


def proses_auto_libur(tenant_id: int, tahun: int, bulan: int) -> dict:
    """Return {"jumlah_dibuat": int, "detail": [{"barber_id","nama_barber",
    "tanggal_libur":[...],"tanggal_cuti":[...],"tanggal_kelebihan_kuota":[...]}]}.
    Raise ValueError kalau Owner belum mengaktifkan auto_libur_tidak_absen_aktif.

    Cascade per tanggal (SETELAH kelima syarat "hari kerja yang
    diharapkan" di modul docstring terpenuhi):
      1. Kuota Libur bulan ini (kuota_libur_bulanan) BELUM habis -> catat
         Libur (absensi_libur, sumber=SUMBER_AUTO_LIBUR).
      2. Kuota Libur SUDAH habis (atau tidak dipakai, kuota_libur_bulanan=0)
         -> cek sisa kuota gabungan Izin&Cuti UNTUK PERIODE tanggal itu
         (izin_cuti_db.get_sisa_kuota_gabungan_pada_tanggal()) -- kalau masih
         ada sisa (atau kuota itu juga tidak dipakai), catat Cuti
         (izin_cuti, seperti versi sebelumnya).
      3. KEDUA kuota sama-sama habis -> tetap catat Libur (absensi_libur,
         sumber=SUMBER_AUTO_LIBUR_KELEBIHAN) supaya rekapan tetap lengkap,
         Rekap Bulanan yang menstabilo merah baris ini."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    if not settings.get("auto_libur_tidak_absen_aktif"):
        raise ValueError("Auto-Libur belum diaktifkan. Aktifkan dulu lewat Pengaturan Izin & Cuti.")
    kuota_libur_bulanan = settings.get("kuota_libur_bulanan", 0)

    tanggal_list = _tanggal_list_bulan(tahun, bulan)
    barbers = db.get_barbers(hanya_aktif=True, tenant_id=tenant_id)
    now = datetime.now().isoformat(timespec="seconds")

    jumlah_dibuat = 0
    detail_per_barber = {}
    # KOREKSI Owner (bugfix): SETIAP operasi baca/tulis di bawah SENGAJA
    # pakai koneksi PENDEK milik sendiri (bukan satu transaksi besar yang
    # menahan lock sepanjang loop) -- get_sisa_kuota_gabungan_pada_tanggal()
    # sendiri membuka+menulis lewat izin_cuti_db.get_cuti_settings(), jadi
    # satu transaksi besar di sini akan DEADLOCK ("database is locked",
    # writer-vs-writer, lihat catatan panjang di database.py::get_conn()).
    # Efek samping yang JUSTRU BENAR: setiap iterasi jadi melihat baris
    # yang baru saja di-commit iterasi sebelumnya (bukan snapshot basi),
    # jadi kuota gabungan yang dicek tanggal berikutnya benar-benar live.
    for barber in barbers:
        barber_id = barber["id"]
        libur_terpakai = _libur_auto_terpakai_bulan_ini(barber_id, tahun, bulan)
        for tanggal in tanggal_list:
            if booking_db.is_toko_libur(tanggal, tenant_id=tenant_id):
                continue
            if not booking_db.is_hari_operasional(tanggal, tenant_id=tenant_id):
                continue
            if booking_db.is_barber_libur(barber_id, tanggal):
                continue
            if _sudah_ada_izin_cuti(barber_id, tanggal):
                continue
            if _sudah_ada_attendance_log(barber_id, tanggal):
                continue

            detail = detail_per_barber.setdefault(barber_id, {
                "barber_id": barber_id, "nama_barber": barber["nama"],
                "tanggal_libur": [], "tanggal_cuti": [], "tanggal_kelebihan_kuota": [],
            })

            if kuota_libur_bulanan > 0 and libur_terpakai < kuota_libur_bulanan:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO absensi_libur (barber_id, tanggal, sumber) VALUES (?, ?, ?) "
                        "ON CONFLICT DO NOTHING",
                        (barber_id, tanggal, SUMBER_AUTO_LIBUR),
                    )
                libur_terpakai += 1
                jumlah_dibuat += 1
                detail["tanggal_libur"].append(tanggal)
                continue

            sisa = izin_cuti_db.get_sisa_kuota_gabungan_pada_tanggal(barber_id, tenant_id, tanggal)
            if sisa is None or sisa > 0:
                with get_conn() as conn:
                    conn.execute(
                        """INSERT INTO izin_cuti (barber_id, jenis, tanggal_mulai, tanggal_selesai, alasan,
                                                   status, diajukan_oleh, disetujui_oleh, tanggal_approval,
                                                   created_at, updated_at)
                           VALUES (?, 'cuti', ?, ?, ?, 'disetujui', ?, ?, ?, ?, ?)""",
                        (barber_id, tanggal, tanggal,
                         "Tidak melakukan absen check-in pada tanggal ini (dicatat otomatis oleh sistem).",
                         DIAJUKAN_OLEH_AUTO_LIBUR, DIAJUKAN_OLEH_AUTO_LIBUR, tanggal[:10], now, now),
                    )
                jumlah_dibuat += 1
                detail["tanggal_cuti"].append(tanggal)
            else:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO absensi_libur (barber_id, tanggal, sumber) VALUES (?, ?, ?) "
                        "ON CONFLICT DO NOTHING",
                        (barber_id, tanggal, SUMBER_AUTO_LIBUR_KELEBIHAN),
                    )
                libur_terpakai += 1
                jumlah_dibuat += 1
                detail["tanggal_kelebihan_kuota"].append(tanggal)

    logger.info("Auto-Libur diproses: tenant_id=%s periode=%s-%s, %d baris dibuat.",
                tenant_id, tahun, bulan, jumlah_dibuat)
    return {"jumlah_dibuat": jumlah_dibuat, "detail": list(detail_per_barber.values())}
