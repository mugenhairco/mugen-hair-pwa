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

Menjembatani EMPAT modul yang SENGAJA berdiri sendiri satu sama lain
(attendance_db.py, izin_cuti_db.py, dan konsep Barber Holiday di
database.py, plus tenant_db.py untuk sapuan lintas-tenant di bawah,
lihat docstring masing-masing) -- sengaja ditulis di file TERPISAH
(bukan menambah logika ini ke salah satu modul itu) supaya independensi
mereka untuk pemakaian lain tetap utuh.

PERBAIKAN Owner (revisi berikutnya): SEBELUMNYA modul ini murni PEMICU
MANUAL (tombol "Proses Auto-Libur" di Pengaturan Izin & Cuti, TIDAK ADA
scheduler/cron eksternal, lihat catatan panjang di faspay_settlement_db.py)
-- Owner EKSPLISIT meminta ini jadi OTOMATIS real-time: begitu jam
operasional (jam_pulang, attendance_settings) suatu tenant lewat DAN
seorang barber belum check-in, Auto-Libur langsung diproses TANPA
Owner perlu klik apa pun. Tombol manual DIHAPUS TOTAL (permintaan Owner).
Karena proyek ini tetap TIDAK PUNYA infrastruktur scheduler/cron
eksternal, "otomatis" di sini diwujudkan lewat SATU loop asyncio yang
hidup SELAMA proses aplikasi ini berjalan (lihat loop_realtime_semua_tenant()
di bagian bawah file ini, dipicu SEKALI dari main.py::on_startup()) --
bukan job terjadwal eksternal, murni loop di dalam proses yang sama.
Idempotent di setiap langkahnya (ON CONFLICT DO NOTHING + syarat
kelayakan yang SELALU dicek ulang), jadi aman dipanggil berkali-kali
ATAU dari beberapa worker/instance sekaligus tanpa risiko duplikat.

Definisi "hari kerja yang diharapkan" untuk seorang barber pada satu
tanggal (SEMUA syarat harus terpenuhi baru dianggap "seharusnya masuk"),
lihat _syarat_hari_kerja_diharapkan() di bawah:
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
Syarat KELIMA ("tanggal itu sudah lewat WAKTUNYA untuk check-in") TIDAK
lagi bagian dari _syarat_hari_kerja_diharapkan() -- ditentukan PEMANGGIL:
sapuan bulan berjalan (proses_auto_libur(), tanggal < hari ini) untuk
tanggal LAMPAU, ATAU proses real-time (_proses_satu_tanggal_semua_barber())
untuk HARI INI SENDIRI, HANYA setelah jam_pulang tenant itu lewat.

Kalau KEEMPAT syarat di atas terpenuhi DAN barber itu SAMA SEKALI tidak
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

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from starlette.concurrency import run_in_threadpool

import attendance_db
import booking_db
import database as db
import izin_cuti_db
import tenant_db
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


def _libur_terpakai_bulan_ini(barber_id: int, tahun: int, bulan: int) -> int:
    """PERMINTAAN OWNER (revisi): Kuota Libur/bulan SEKARANG dikurangi
    SEMUA baris absensi_libur bulan itu -- Barber Holiday MANUAL (sumber
    NULL) MAUPUN yang dibuat Auto-Libur (SUMBER_AUTO_LIBUR/
    SUMBER_AUTO_LIBUR_KELEBIHAN) -- BUKAN LAGI hanya yang dibuat Auto-
    Libur sendiri (perilaku SEBELUMNYA). Owner menandai Libur manual untuk
    tanggal apa pun (mis. menyusulkan tanggal lama sebelum Auto-Libur
    real-time ada) TETAP dianggap memakai jatah Libur bulan itu, sama
    seperti kalau Auto-Libur sendiri yang mencatatnya -- SATU jatah
    "Libur/bulan" untuk KEDUA sumber, bukan dua hitungan terpisah."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ? AND tanggal LIKE ?",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%"),
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


def batalkan_auto_libur_untuk_tanggal(barber_id: int, tanggal: str) -> dict:
    """PERMINTAAN OWNER: dipanggil routers/attendance.py SETELAH Koreksi
    Absensi disetujui (barber lupa check-in, lalu diajukan susulan) --
    attendance_logs untuk barber+tanggal ini SEKARANG sudah terisi, jadi
    kalau Auto-Libur SEBELUMNYA sudah terlanjur memproses tanggal itu
    (mencatat Libur di absensi_libur ATAU Cuti di izin_cuti, keduanya
    ditandai "Sistem (Auto-Libur)"), catatan itu BASI dan harus dibatalkan
    di sini -- kalau tidak, akan ada dua catatan bertabrakan untuk tanggal
    yang sama (sudah masuk kerja TAPI juga tercatat Libur/Cuti).

    Kuota yang sempat terpakai OTOMATIS kembali begitu baris ini dihapus --
    baik Kuota Libur (auto_libur_db._libur_terpakai_bulan_ini()) maupun
    kuota gabungan Izin&Cuti (izin_cuti_db._kuota_terpakai_hari()) SELALU
    dihitung LIVE dari baris yang ADA, tidak pernah dari counter tersimpan
    -- TIDAK PERLU logika "refund" terpisah sama sekali.

    HANYA menyentuh baris yang jelas-jelas dibuat Auto-Libur sendiri
    (sumber/diajukan_oleh "Sistem (Auto-Libur)") -- Barber Holiday manual
    atau pengajuan Izin/Cuti asli milik barber TIDAK PERNAH ikut terhapus
    oleh fungsi ini, apa pun isinya.

    Return {"dibatalkan_libur": bool, "dibatalkan_cuti": bool} -- keduanya
    False di kasus normal (mayoritas -- tanggal itu memang belum pernah
    diproses Auto-Libur sama sekali)."""
    dibatalkan_libur = False
    dibatalkan_cuti = False
    with get_conn() as conn:
        row_libur = conn.execute(
            "SELECT id FROM absensi_libur WHERE barber_id = ? AND tanggal = ? AND sumber IN (?, ?)",
            (barber_id, tanggal, SUMBER_AUTO_LIBUR, SUMBER_AUTO_LIBUR_KELEBIHAN),
        ).fetchone()
        if row_libur:
            conn.execute("DELETE FROM absensi_libur WHERE id = ?", (row_libur["id"],))
            dibatalkan_libur = True
        row_cuti = conn.execute(
            "SELECT id FROM izin_cuti WHERE barber_id = ? AND tanggal_mulai = ? AND tanggal_selesai = ? "
            "AND diajukan_oleh = ? AND status = 'disetujui'",
            (barber_id, tanggal, tanggal, DIAJUKAN_OLEH_AUTO_LIBUR),
        ).fetchone()
        if row_cuti:
            conn.execute("DELETE FROM izin_cuti WHERE id = ?", (row_cuti["id"],))
            dibatalkan_cuti = True
    if dibatalkan_libur or dibatalkan_cuti:
        logger.info(
            "Auto-Libur dibatalkan (Koreksi Absensi disetujui): barber_id=%s tanggal=%s libur=%s cuti=%s",
            barber_id, tanggal, dibatalkan_libur, dibatalkan_cuti,
        )
    return {"dibatalkan_libur": dibatalkan_libur, "dibatalkan_cuti": dibatalkan_cuti}


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
    BULAN KALENDER (WIB), TIDAK ikut periode Izin&Cuti sama sekali.
    `terpakai` menghitung SEMUA baris Libur bulan itu (manual MAUPUN
    Auto-Libur, lihat _libur_terpakai_bulan_ini()). Return {"aktif": bool,
    "kuota": int|None, "terpakai": int|None, "sisa": int|None} --
    `aktif`=False (semua field lain None) kalau Owner belum mengisi
    kuota_libur_bulanan (0/default)."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    kuota = settings.get("kuota_libur_bulanan", 0)
    if kuota <= 0:
        return {"aktif": False, "kuota": None, "terpakai": None, "sisa": None}
    hari_ini = _hari_ini_wib()
    tahun, bulan = int(hari_ini[:4]), int(hari_ini[5:7])
    terpakai = _libur_terpakai_bulan_ini(barber_id, tahun, bulan)
    return {"aktif": True, "kuota": kuota, "terpakai": terpakai, "sisa": max(0, kuota - terpakai)}


def _syarat_hari_kerja_diharapkan(barber_id: int, tenant_id: int, tanggal: str) -> bool:
    """Syarat 1-4 dari modul docstring (SEMUA harus True) -- syarat #5
    ("waktunya sudah lewat") SENGAJA tidak di sini, ditentukan pemanggil
    (lihat modul docstring)."""
    if booking_db.is_toko_libur(tanggal, tenant_id=tenant_id):
        return False
    if not booking_db.is_hari_operasional(tanggal, tenant_id=tenant_id):
        return False
    if booking_db.is_barber_libur(barber_id, tanggal):
        return False
    if _sudah_ada_izin_cuti(barber_id, tanggal):
        return False
    if _sudah_ada_attendance_log(barber_id, tanggal):
        return False
    return True


def _terapkan_cascade(barber_id: int, tenant_id: int, tanggal: str, kuota_libur_bulanan: int,
                       libur_terpakai: int) -> str:
    """MENULIS baris cascade (Libur -> Cuti&Izin -> Libur kelebihan) untuk
    SATU barber+tanggal -- TIDAK mengecek syarat kelayakan (pemanggil
    WAJIB sudah memverifikasi lewat _syarat_hari_kerja_diharapkan()).
    Return 'libur' | 'cuti' | 'kelebihan_kuota'.

    KOREKSI Owner (bugfix lama): SETIAP operasi tulis di bawah SENGAJA
    pakai koneksi PENDEK sendiri (bukan satu transaksi besar yang menahan
    lock) -- get_sisa_kuota_gabungan_pada_tanggal() sendiri membuka+
    menulis lewat izin_cuti_db.get_cuti_settings(), jadi transaksi besar
    akan DEADLOCK ("database is locked", writer-vs-writer, lihat catatan
    panjang di database.py::get_conn())."""
    now = datetime.now().isoformat(timespec="seconds")
    if kuota_libur_bulanan > 0 and libur_terpakai < kuota_libur_bulanan:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO absensi_libur (barber_id, tanggal, sumber) VALUES (?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (barber_id, tanggal, SUMBER_AUTO_LIBUR),
            )
        return "libur"

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
        return "cuti"

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO absensi_libur (barber_id, tanggal, sumber) VALUES (?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            (barber_id, tanggal, SUMBER_AUTO_LIBUR_KELEBIHAN),
        )
    return "kelebihan_kuota"


def proses_auto_libur(tenant_id: int, tahun: int, bulan: int) -> dict:
    """Sapuan SATU bulan tertentu, HANYA tanggal LAMPAU (< hari ini, lihat
    _tanggal_list_bulan()) -- dipakai sweep_otomatis_tenant() di bawah
    sebagai jaring pengaman (catch-up kalau proses ini sempat tidak
    berjalan, mis. restart/deploy pas jam_pulang lewat). TIDAK LAGI
    dipicu tombol manual (dihapus, permintaan Owner) -- lihat modul
    docstring. Return {"jumlah_dibuat": int, "detail": [{"barber_id",
    "nama_barber","tanggal_libur":[...],"tanggal_cuti":[...],
    "tanggal_kelebihan_kuota":[...]}]}. Raise ValueError kalau Owner belum
    mengaktifkan auto_libur_tidak_absen_aktif."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    if not settings.get("auto_libur_tidak_absen_aktif"):
        raise ValueError("Auto-Libur belum diaktifkan. Aktifkan dulu lewat Pengaturan Izin & Cuti.")
    kuota_libur_bulanan = settings.get("kuota_libur_bulanan", 0)

    tanggal_list = _tanggal_list_bulan(tahun, bulan)
    barbers = db.get_barbers(hanya_aktif=True, tenant_id=tenant_id)

    jumlah_dibuat = 0
    detail_per_barber = {}
    for barber in barbers:
        barber_id = barber["id"]
        libur_terpakai = _libur_terpakai_bulan_ini(barber_id, tahun, bulan)
        for tanggal in tanggal_list:
            if not _syarat_hari_kerja_diharapkan(barber_id, tenant_id, tanggal):
                continue

            detail = detail_per_barber.setdefault(barber_id, {
                "barber_id": barber_id, "nama_barber": barber["nama"],
                "tanggal_libur": [], "tanggal_cuti": [], "tanggal_kelebihan_kuota": [],
            })
            jenis = _terapkan_cascade(barber_id, tenant_id, tanggal, kuota_libur_bulanan, libur_terpakai)
            jumlah_dibuat += 1
            if jenis == "libur":
                libur_terpakai += 1
                detail["tanggal_libur"].append(tanggal)
            elif jenis == "cuti":
                detail["tanggal_cuti"].append(tanggal)
            else:
                libur_terpakai += 1
                detail["tanggal_kelebihan_kuota"].append(tanggal)

    logger.info("Auto-Libur diproses: tenant_id=%s periode=%s-%s, %d baris dibuat.",
                tenant_id, tahun, bulan, jumlah_dibuat)
    return {"jumlah_dibuat": jumlah_dibuat, "detail": list(detail_per_barber.values())}


def _jam_pulang_sudah_lewat(tenant_id: int) -> bool:
    """PERMINTAAN OWNER: True kalau waktu SEKARANG (WIB) sudah melewati
    jam_pulang (jam operasional tutup, attendance_settings) tenant ini --
    penentu proses Auto-Libur real-time HARI INI (lihat
    _proses_satu_tanggal_semua_barber()/sweep_otomatis_tenant()).
    False kalau Owner belum mengisi Lokasi/Pengaturan Absensi sama sekali
    (jam_pulang kosong) -- tidak ada acuan, jangan diproses."""
    settings = attendance_db.get_settings(tenant_id)
    jam_pulang = settings.get("jam_pulang")
    if not jam_pulang:
        return False
    return attendance_db.sekarang_wib().strftime("%H:%M") >= jam_pulang


def _proses_satu_tanggal_semua_barber(tenant_id: int, tanggal: str, settings: dict) -> int:
    """Terapkan cascade untuk SATU tanggal (HARI INI, dipanggil HANYA
    setelah _jam_pulang_sudah_lewat()) -- SEMUA barber aktif tenant ini
    sekaligus. Return jumlah baris baru dibuat."""
    kuota_libur_bulanan = settings.get("kuota_libur_bulanan", 0)
    tahun, bulan = int(tanggal[:4]), int(tanggal[5:7])
    barbers = db.get_barbers(hanya_aktif=True, tenant_id=tenant_id)
    jumlah = 0
    for barber in barbers:
        barber_id = barber["id"]
        if not _syarat_hari_kerja_diharapkan(barber_id, tenant_id, tanggal):
            continue
        libur_terpakai = _libur_terpakai_bulan_ini(barber_id, tahun, bulan)
        _terapkan_cascade(barber_id, tenant_id, tanggal, kuota_libur_bulanan, libur_terpakai)
        jumlah += 1
    return jumlah


def sweep_otomatis_tenant(tenant_id: int) -> dict:
    """PERMINTAAN OWNER: gantikan SEPENUHNYA tombol manual "Proses Auto-
    Libur" -- dipanggil loop_realtime_semua_tenant() di bawah TIAP TICK,
    PER tenant aktif. Idempotent, aman dipanggil berkali-kali. Dua
    bagian: (1) sapuan bulan berjalan UNTUK TANGGAL LAMPAU (proses_auto_libur,
    jaring pengaman restart/deploy), (2) HARI INI SAJA, HANYA kalau
    jam_pulang tenant ini sudah lewat (real-time)."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    if not settings.get("auto_libur_tidak_absen_aktif"):
        return {"jumlah_dibuat": 0}
    hari_ini = _hari_ini_wib()
    tahun, bulan = int(hari_ini[:4]), int(hari_ini[5:7])
    jumlah = proses_auto_libur(tenant_id, tahun, bulan)["jumlah_dibuat"]
    if _jam_pulang_sudah_lewat(tenant_id):
        jumlah += _proses_satu_tanggal_semua_barber(tenant_id, hari_ini, settings)
    return {"jumlah_dibuat": jumlah}


def _sweep_semua_tenant_sync():
    """SATU putaran penuh SEMUA tenant berstatus aktif -- dipanggil lewat
    run_in_threadpool() di bawah (SQLite/Postgres driver di proyek ini
    SINKRON/blocking, jalankan langsung di event loop asyncio akan
    membekukan SELURUH request HTTP yang sedang berjalan selama putaran
    ini). SATU tenant gagal (exception apa pun) TIDAK PERNAH menghentikan
    tenant lain -- dicatat ke log lalu lanjut."""
    for tenant in tenant_db.list_tenants():
        if tenant.get("status") != "aktif":
            continue
        try:
            sweep_otomatis_tenant(tenant["id"])
        except Exception:
            logger.exception("Auto-Libur real-time GAGAL untuk tenant_id=%s.", tenant["id"])


async def loop_realtime_semua_tenant(interval_detik: int = 900):
    """PERMINTAAN OWNER: loop background yang hidup SELAMA proses aplikasi
    ini berjalan -- dipicu SEKALI dari main.py::on_startup() lewat
    asyncio.create_task(). Proyek ini TETAP tidak punya scheduler/cron
    EKSTERNAL (lihat modul docstring) -- ini murni loop internal proses
    yang sama, TIDAK PERNAH berhenti sendiri (kecuali proses ini mati).
    interval_detik default 15 menit -- cukup responsif untuk kebutuhan
    Absensi/HR (bukan sistem real-time detik-ke-detik), sekaligus murah
    (satu putaran hanya menulis untuk tenant/tanggal yang BENAR-BENAR
    belum diproses, sisanya murni baca+skip lewat syarat kelayakan)."""
    while True:
        await run_in_threadpool(_sweep_semua_tenant_sync)
        await asyncio.sleep(interval_detik)
