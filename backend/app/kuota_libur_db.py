"""
kuota_libur_db.py — Kuota Libur Bulanan (cascade Tandai Libur manual -> Cuti)
=============================================================================
PERMINTAAN OWNER: Barber Holiday/Libur (Input Data > Tandai Libur, MANUAL --
lihat database.py::tandai_libur(), routers/input_data.py) sekarang punya
jatah "Kuota Libur per Bulan" opsional (Owner-editable di Pengaturan Izin &
Cuti, izin_cuti_settings.kuota_libur_bulanan, 0 = tidak dibatasi/tidak
dipakai -- Tandai Libur berjalan seperti biasa tanpa cascade apa pun).

SELAMA kuota bulan itu (per barber, reset tiap bulan kalender) belum habis,
Tandai Libur berjalan seperti biasa (baris absensi_libur, sumber NULL,
TIDAK menyentuh Izin & Cuti sama sekali). Begitu kuota bulan itu SUDAH
HABIS, Tandai Libur BERIKUTNYA untuk barber yang sama di bulan yang sama
OTOMATIS dicatat sebagai CUTI (disetujui otomatis, mengurangi kuota
gabungan Izin & Cuti, izin_cuti_settings.kuota_gabungan_hari) -- BUKAN
Libur (lihat tandai_libur_dengan_kuota()). Kalau KEDUA kuota itu (Libur
DAN Izin & Cuti) SAMA-SAMA habis, tanggal TETAP dicatat sebagai Libur
(supaya rekap tetap lengkap, tidak hilang begitu saja) TAPI ditandai
sumber='kelebihan_kuota' -- dipakai Rekap Bulanan (routers/rekap.py) dan
ringkasan kuota (routers/izin_cuti.py) untuk menstabilo baris itu merah.

Modul ini MENGGANTIKAN auto_libur_db.py (fitur "Auto-Libur Tidak Absen" --
barber yang lupa Check In SEMBARANG HARI otomatis dicatat Libur/Cuti --
SUDAH DIHAPUS TOTAL atas permintaan Owner, lihat riwayat git). TIDAK ADA
cron/sweep/loop/proses latar belakang apa pun di modul ini.

REVISI (PERMINTAAN OWNER): jadwal Libur Mingguan (Barber Holiday,
barbers.hari_libur_mingguan) SEKARANG ikut masuk kolam kuota Libur yang
SAMA ini -- lihat pastikan_libur_mingguan_tercatat() di bawah. BEDA dari
auto_libur_db.py yang dihapus (yang memicu untuk SEMBARANG hari barber
lupa Check In): ini HANYA memicu di hari yang MEMANG jadwal mingguan tetap
barber itu sendiri, dan BUKAN proses latar belakang -- dipanggil OPORTUNISTIK
(baris dibuat SAAT dibutuhkan, lihat database.py::get_hari_libur_rentang())
oleh titik-titik baca yang sudah ada, bukan timer/cron terpisah. Barber yang
Check In di hari jadwal mingguannya sendiri (shift tukar dadakan) membuat
baris ini (kalau sempat terlanjur dibuat) DIHAPUS oleh attendance_db.
check_in() -- lihat SUMBER_LIBUR_MINGGUAN.
"""

from datetime import date, datetime, timedelta

import attendance_db
import booking_db
import database as db
import izin_cuti_db
from database import get_conn

SUMBER_KELEBIHAN_KUOTA = "kelebihan_kuota"
SUMBER_LIBUR_MINGGUAN = "libur_mingguan"
DIAJUKAN_OLEH_KUOTA_LIBUR = "Sistem (Kuota Libur Habis)"

# FITUR Pembersihan Data Bulanan Otomatis: kunci setting (per tenant) yang
# menyimpan cutoff TERAKHIR berhasil dibersihkan dari hapus_riwayat_libur_sebelum()
# di bawah -- lihat catatan lengkap di fungsi itu dan di
# pastikan_libur_mingguan_tercatat().
_SETTING_CUTOFF_LIBUR_TERCAPAI = "purge_libur_cutoff_tercapai"


def migrasi_absensi_libur_sumber():
    """JALUR SQLITE SAJA (dipanggil dari main.py::on_startup() bersama
    migrasi_*() lain) -- PRAGMA table_info() di bawah ini SQL SQLite murni.
    Menambah kolom `sumber` ke `absensi_libur` (idempotent). Jalur
    PostgreSQL: kolom yang sama sudah langsung dibuat lewat
    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` di postgres_schema.py."""
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(absensi_libur)").fetchall()]
        if "sumber" not in kolom:
            conn.execute("ALTER TABLE absensi_libur ADD COLUMN sumber TEXT")


def _libur_terpakai_bulan_ini(barber_id: int, tahun: int, bulan: int) -> int:
    """Jumlah SEMUA baris absensi_libur bulan itu (Libur manual biasa
    MAUPUN yang ditandai 'kelebihan_kuota') -- SATU jatah "Libur/bulan"
    untuk semuanya, bukan hitungan terpisah per sumber."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ? AND tanggal LIKE ?",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%"),
        ).fetchone()
    return row["jumlah"]


def get_sisa_kuota_libur_bulan_ini(barber_id: int, tenant_id: int) -> dict:
    """Kartu "Sisa Kuota Libur" (Absensi barber & Owner) -- BEDA dari kuota
    gabungan Izin&Cuti (izin_cuti_db.get_sisa_kuota(), yang anchor ke
    periode Owner-editable) -- Kuota Libur SELALU reset per BULAN KALENDER
    (WIB, attendance_db.tanggal_hari_ini()), TIDAK ikut periode Izin&Cuti
    sama sekali. Return
    {"aktif": bool, "kuota": int|None, "terpakai": int|None,
    "sisa": int|None} -- `aktif`=False (field lain None) kalau Owner belum
    mengisi kuota_libur_bulanan (0/default, fitur ini tidak dipakai)."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    kuota = settings.get("kuota_libur_bulanan", 0)
    if kuota <= 0:
        return {"aktif": False, "kuota": None, "terpakai": None, "sisa": None}
    hari_ini = attendance_db.tanggal_hari_ini()
    tahun, bulan = int(hari_ini[:4]), int(hari_ini[5:7])
    terpakai = _libur_terpakai_bulan_ini(barber_id, tahun, bulan)
    return {"aktif": True, "kuota": kuota, "terpakai": terpakai, "sisa": max(0, kuota - terpakai)}


def ada_kelebihan_kuota_bulan_ini(barber_id: int, tahun: int, bulan: int) -> bool:
    """Dipakai Rekap Bulanan (routers/rekap.py) dan ringkasan kuota
    (routers/izin_cuti.py) untuk stabilo merah -- True kalau ADA minimal
    satu tanggal bulan ini yang ditandai Libur PADAHAL Kuota Libur bulanan
    DAN kuota gabungan Izin&Cuti SAMA-SAMA sudah habis (lihat
    tandai_libur_dengan_kuota())."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ? AND tanggal LIKE ? AND sumber = ?",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%", SUMBER_KELEBIHAN_KUOTA),
        ).fetchone()
    return row["jumlah"] > 0


def ada_kelebihan_kuota_bulan_ini_sekarang(barber_id: int) -> bool:
    """Wrapper ada_kelebihan_kuota_bulan_ini() utk BULAN KALENDER BERJALAN
    -- dipakai routers/izin_cuti.py::ambil_sisa_kuota_semua_barber() (tabel
    ringkasan kuota Absensi > Owner)."""
    hari_ini = attendance_db.tanggal_hari_ini()
    return ada_kelebihan_kuota_bulan_ini(barber_id, int(hari_ini[:4]), int(hari_ini[5:7]))


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: tanda visual BEDA di kolom Keterangan Rekap Transaksi
# untuk DUA kasus Tandai Libur yang sebenarnya TIDAK murni dari kuota Libur
# sendiri -- supaya Owner bisa lihat langsung tanggal mana yang sebenarnya
# "nebeng" kuota lain, tanpa harus buka Absensi/Izin & Cuti satu-satu.
# ---------------------------------------------------------------------------

def _tanggal_filter(q: str, params: list, kolom_tanggal: str, tahun: int, bulan: int,
                     tanggal: str, tanggal_mulai: str, tanggal_selesai: str) -> str:
    # BUGFIX PERFORMA (dilaporkan Owner -- Rekap lambat untuk tenant dengan
    # banyak data): range bisa pakai index biasa, LIKE wildcard-di-awal
    # TIDAK BISA -- lihat catatan lengkap di database.py::get_transaksi_list().
    if tahun is not None and bulan is not None:
        q += f" AND {kolom_tanggal} >= ? AND {kolom_tanggal} <= ?"
        params.append(f"{tahun:04d}-{bulan:02d}-01"); params.append(f"{tahun:04d}-{bulan:02d}-31")
    elif tahun is not None:
        q += f" AND {kolom_tanggal} LIKE ?"; params.append(f"{tahun:04d}-%")
    elif bulan is not None:
        q += f" AND {kolom_tanggal} LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal is not None:
        q += f" AND {kolom_tanggal} = ?"; params.append(tanggal)
    if tanggal_mulai is not None:
        q += f" AND {kolom_tanggal} >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += f" AND {kolom_tanggal} <= ?"; params.append(tanggal_selesai)
    return q


def _tanggal_cuti_otomatis_kuota_habis(barber_id: int = None, tahun: int = None, bulan: int = None,
                                        tanggal: str = None, tanggal_mulai: str = None,
                                        tanggal_selesai: str = None, tenant_id: int = None) -> set:
    """Set (barber_id, tanggal) yang Cuti-nya BUKAN pengajuan asli barber/Owner
    -- OTOMATIS dicatat sistem karena kuota Libur bulanan sudah habis
    sementara kuota gabungan Izin&Cuti masih ada sisa (cabang `sisa is None
    or sisa > 0` di tandai_libur_dengan_kuota()). Baris ini TIDAK ADA di
    absensi_libur sama sekali (tersimpan di izin_cuti)."""
    q = "SELECT ic.barber_id AS barber_id, ic.tanggal_mulai AS tanggal FROM izin_cuti ic"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = ic.barber_id"
    q += " WHERE ic.diajukan_oleh = ? AND ic.status = 'disetujui'"
    params = [DIAJUKAN_OLEH_KUOTA_LIBUR]
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND ic.barber_id = ?"; params.append(barber_id)
    q = _tanggal_filter(q, params, "ic.tanggal_mulai", tahun, bulan, tanggal, tanggal_mulai, tanggal_selesai)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return {(r["barber_id"], r["tanggal"]) for r in rows}


def _tanggal_libur_kelebihan_kuota(barber_id: int = None, tahun: int = None, bulan: int = None,
                                    tanggal: str = None, tanggal_mulai: str = None,
                                    tanggal_selesai: str = None, tenant_id: int = None) -> set:
    """Set (barber_id, tanggal) yang dicatat Libur TAPI kuota Libur DAN kuota
    gabungan Izin&Cuti SAMA-SAMA sudah habis (sumber='kelebihan_kuota')."""
    q = "SELECT al.barber_id AS barber_id, al.tanggal AS tanggal FROM absensi_libur al"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = al.barber_id"
    q += " WHERE al.sumber = ?"
    params = [SUMBER_KELEBIHAN_KUOTA]
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND al.barber_id = ?"; params.append(barber_id)
    q = _tanggal_filter(q, params, "al.tanggal", tahun, bulan, tanggal, tanggal_mulai, tanggal_selesai)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return {(r["barber_id"], r["tanggal"]) for r in rows}


def tandai_rekap_transaksi_kuota(data: list, tahun: int = None, bulan: int = None, barber_id: int = None,
                                  tanggal: str = None, tanggal_mulai: str = None, tanggal_selesai: str = None,
                                  tenant_id: int = None) -> list:
    """PERMINTAAN OWNER: dipanggil routers/rekap.py SETELAH
    db.get_rekap_transaksi_list() (pola sama seperti reimburse_db/kasbon_db/
    data_non_barber_db.gabung_ke_rekap_transaksi()) -- menandai dua kasus
    Tandai Libur yang sebenarnya "nebeng" kuota lain, BUKAN kuota Libur asli:

    1. "Libur ⚠️" -- tanggal yang OTOMATIS tercatat Cuti oleh sistem karena
       kuota Libur bulan itu sudah habis. Baris ini belum pernah ada sama
       sekali di Rekap Transaksi sebelumnya (tersimpan di izin_cuti, bukan
       absensi_libur) -- ditambahkan sebagai baris baru tipe "libur" (pil
       Ket. yang sama), tapi diberi flag `dari_kuota_cuti_izin=True` supaya
       frontend TIDAK menampilkan tombol Hapus Keterangan Libur (tidak ada
       apa pun untuk dihapus di absensi_libur -- pembatalannya harus lewat
       Izin & Cuti, bukan endpoint Libur).
    2. "Libur 🔴" -- tanggal yang kuota Libur DAN kuota gabungan Izin&Cuti
       SAMA-SAMA sudah habis (sumber='kelebihan_kuota'). Baris ini SUDAH
       ada di `data` (dari get_libur_list()), tinggal keterangan-nya
       ditandai -- tombol Hapus Keterangan Libur TETAP ada seperti biasa
       (baris ini memang baris Libur asli di absensi_libur)."""
    cuti_otomatis = _tanggal_cuti_otomatis_kuota_habis(barber_id, tahun, bulan, tanggal, tanggal_mulai,
                                                        tanggal_selesai, tenant_id)
    kelebihan_kuota = _tanggal_libur_kelebihan_kuota(barber_id, tahun, bulan, tanggal, tanggal_mulai,
                                                      tanggal_selesai, tenant_id)
    if not cuti_otomatis and not kelebihan_kuota:
        return data

    for r in data:
        if r.get("tipe") == "libur" and (r["barber_id"], r["tanggal"]) in kelebihan_kuota:
            r["keterangan"] = "; ".join(
                "Libur 🔴" if bagian == "Libur" else bagian for bagian in r["keterangan"].split("; ")
            )

    for (bid, tgl) in cuti_otomatis:
        cocok = [r for r in data if r["barber_id"] == bid and r["tanggal"] == tgl]
        if cocok:
            for r in cocok:
                lama = (r.get("keterangan") or "").strip()
                r["keterangan"] = "; ".join(x for x in [lama, "Libur ⚠️"] if x and x != "-")
                r["dari_kuota_cuti_izin"] = True
            continue
        barber = db.get_barber(bid)
        if barber is None:
            continue
        data.append({
            "tipe": "libur",
            "tanggal": tgl,
            "barber_id": bid,
            "nama_barber": barber["nama"],
            "daftar_service": "",
            "jumlah_service": 0,
            "tips": 0,
            "uang_harian": 0,
            "pendapatan": 0,
            "keterangan": "Libur ⚠️",
            "dari_kuota_cuti_izin": True,
        })

    data.sort(key=lambda r: r["nama_barber"])
    data.sort(key=lambda r: r["tanggal"], reverse=True)
    return data


def tandai_libur_dengan_kuota(barber_id: int, tenant_id: int, tanggal: str) -> str:
    """Dipanggil routers/input_data.py SEBAGAI PENGGANTI database.tandai_libur()
    langsung -- menerapkan cascade Kuota Libur (lihat modul docstring) SAAT
    Admin/Owner menandai Libur manual untuk satu tanggal. Return
    'libur' | 'cuti' | 'kelebihan_kuota' supaya caller (router) bisa
    memberi tahu Admin/Owner persis apa yang terjadi.

    PERMINTAAN OWNER: Tandai Libur DITOLAK (ValueError) kalau tanggal ini
    sudah tercakup pengajuan Izin/Cuti yang DISETUJUI milik barber yang
    sama -- validasi arah SEBALIKNYA dari yang sudah ada di
    izin_cuti_db.buat_pengajuan() (yang menolak pengajuan baru di atas
    tanggal yang sudah Libur). Tanpa ini, satu tanggal bisa tercatat
    GANDA (Libur DAN Cuti/Izin sekaligus) -- bikin Rekap & Bonus Customer
    (hari_libur) salah hitung.

    PERMINTAAN OWNER: Tandai Libur JUGA DITOLAK kalau tanggal ini sudah
    otomatis Libur Mingguan (Barber Holiday, barbers.hari_libur_mingguan --
    lihat booking_db.is_jadwal_mingguan_libur()) DAN barber belum Check In
    hari itu -- sebelumnya tetap diproses seperti biasa (diam-diam
    memakai 1 jatah kuota Libur bulanan untuk hari yang sebenarnya SUDAH
    otomatis libur tanpa perlu dicatat manual sama sekali). Kalau barber
    SUDAH Check In hari itu (berarti dia memutuskan tetap masuk meski
    jadwal mingguannya libur), guard ini TIDAK berlaku -- Tandai Libur
    tetap berjalan normal (lihat override Check In di
    booking_db.is_jadwal_mingguan_libur())."""
    if booking_db.is_jadwal_mingguan_libur(barber_id, tanggal):
        raise ValueError(
            "Tidak bisa ditandai Libur -- tanggal ini sudah otomatis Libur Mingguan "
            "(jadwal rutin barber ini), tidak perlu dicatat manual lagi."
        )

    pengajuan_aktif = izin_cuti_db.get_pengajuan_aktif_pada_tanggal(barber_id, tanggal)
    if pengajuan_aktif is not None:
        jenis_label = "Izin" if pengajuan_aktif["jenis"] == "izin" else "Cuti"
        raise ValueError(
            f"Tidak bisa ditandai Libur -- barber ini tercatat sedang {jenis_label} pada tanggal ini "
            f"({pengajuan_aktif['tanggal_mulai']} s/d {pengajuan_aktif['tanggal_selesai']})."
        )

    # PERMINTAAN OWNER: pastikan baris Libur Mingguan bulan ini SUDAH
    # tercatat dulu (lihat pastikan_libur_mingguan_tercatat()) SEBELUM kuota
    # dihitung di bawah -- tanpa ini, permintaan manual bisa salah hitung
    # kalau tidak ada yang kebetulan sudah buka Rekap/Dashboard barber ini
    # bulan ini (satu-satunya titik lain yang memicu pencatatan otomatis).
    tahun, bulan = int(tanggal[:4]), int(tanggal[5:7])
    awal_bulan = f"{tahun:04d}-{bulan:02d}-01"
    pastikan_libur_mingguan_tercatat(barber_id, tenant_id, awal_bulan, tanggal)

    return _terapkan_kuota_libur(barber_id, tenant_id, tanggal)


def _terapkan_kuota_libur(barber_id: int, tenant_id: int, tanggal: str, sumber_libur: str = None) -> str:
    """Inti cascade kuota (TANPA guard jadwal mingguan/Cuti-Izin aktif, dan
    TANPA memanggil pastikan_libur_mingguan_tercatat() -- caller-nya
    masing-masing yang bertanggung jawab) -- diekstrak APA ADANYA (rumus
    tidak diubah) dari tandai_libur_dengan_kuota() supaya bisa dipakai ULANG
    oleh pastikan_libur_mingguan_tercatat() (lihat di bawah) tanpa duplikasi
    logika. `sumber_libur`: diteruskan ke database.tandai_libur() KHUSUS
    kalau hasilnya 'libur' murni (BUKAN kelebihan_kuota, yang sumbernya
    SELALU SUMBER_KELEBIHAN_KUOTA apa pun nilai parameter ini) -- None
    (default) sama persis perilaku lama (Libur manual biasa).

    PENTING (hindari rekursi tak berujung): fungsi ini TIDAK PERNAH memicu
    pastikan_libur_mingguan_tercatat() lagi -- _libur_terpakai_bulan_ini()
    di bawah murni MENGHITUNG baris yang SUDAH ada di database saat
    dipanggil (termasuk baris yang baru saja dibuat pemanggil SEBELUMNYA
    dalam loop pastikan_libur_mingguan_tercatat(), karena setiap baris
    langsung commit sebelum tanggal berikutnya diproses).

    PERBAIKAN Owner (audit "tidak boleh input dobel"): kalau tanggal ini
    SUDAH punya baris absensi_libur (sumber apa pun -- percobaan
    Tandai Libur sebelumnya, atau materialisasi Libur Mingguan), cascade
    SELALU dianggap sudah "libur" tanpa menghitung ulang kuota sama
    sekali -- TANPA ini, mengulang "Tandai Libur" untuk tanggal yang
    PERSIS sama saat kuota bulan itu PAS di batas (mis. 5/5, dan 1 dari
    5 itu adalah tanggal ini sendiri) akan salah membuat PENGAJUAN CUTI
    TAMBAHAN untuk tanggal yang sama (tanggal itu jadi tercatat Libur
    DAN Cuti sekaligus) -- bikin Rekap & kuota salah hitung, dan baris
    Cuti itu dibuat lewat INSERT langsung di bawah (BUKAN
    izin_cuti_db.buat_pengajuan()), jadi tidak lewat guard tumpang
    tindih yang ada di sana sama sekali."""
    with get_conn() as conn:
        sudah_ada = conn.execute(
            "SELECT 1 FROM absensi_libur WHERE barber_id = ? AND tanggal = ?",
            (barber_id, tanggal),
        ).fetchone()
    if sudah_ada is not None:
        return "libur"

    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    kuota = settings.get("kuota_libur_bulanan", 0)
    if kuota <= 0:
        db.tandai_libur(barber_id, tanggal, sumber=sumber_libur)
        return "libur"

    tahun, bulan = int(tanggal[:4]), int(tanggal[5:7])
    terpakai = _libur_terpakai_bulan_ini(barber_id, tahun, bulan)
    if terpakai < kuota:
        db.tandai_libur(barber_id, tanggal, sumber=sumber_libur)
        return "libur"

    sisa = izin_cuti_db.get_sisa_kuota_gabungan_pada_tanggal(barber_id, tenant_id, tanggal)
    if sisa is None or sisa > 0:
        now = datetime.now().isoformat(timespec="seconds")
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO izin_cuti (barber_id, jenis, tanggal_mulai, tanggal_selesai, alasan,
                                           status, diajukan_oleh, disetujui_oleh, tanggal_approval,
                                           created_at, updated_at)
                   VALUES (?, 'cuti', ?, ?, ?, 'disetujui', ?, ?, ?, ?, ?)""",
                (barber_id, tanggal, tanggal,
                 "Kuota Libur bulan ini sudah habis (dicatat otomatis sebagai Cuti).",
                 DIAJUKAN_OLEH_KUOTA_LIBUR, DIAJUKAN_OLEH_KUOTA_LIBUR, tanggal[:10], now, now),
            )
        return "cuti"

    db.tandai_libur(barber_id, tanggal, sumber=SUMBER_KELEBIHAN_KUOTA)
    return "kelebihan_kuota"


def pastikan_libur_mingguan_tercatat(barber_id: int, tenant_id: int, tanggal_mulai: str, tanggal_selesai: str) -> None:
    """PERMINTAAN OWNER (lihat docstring modul): jadwal Libur Mingguan
    (Barber Holiday) barber ini BENAR-BENAR tercatat (baris nyata di
    absensi_libur/izin_cuti, BUKAN cuma status terhitung di tempat) dan
    MENGURANGI kuota Libur gabungan yang SAMA dengan Tandai Libur manual --
    lewat cascade yang SAMA PERSIS (_terapkan_kuota_libur() di atas). TIDAK
    ADA cron/sweep: fungsi ini dipanggil OPORTUNISTIK setiap kali data Libur
    barber ini dibutuhkan (database.py::get_hari_libur_rentang()/
    get_libur_list(), MAUPUN tandai_libur_dengan_kuota() sendiri di atas) --
    idempotent, aman dipanggil berkali-kali untuk rentang yang sama.

    Begitu barber Check In di hari jadwal mingguannya, baris
    sumber=SUMBER_LIBUR_MINGGUAN yang SUDAH TERLANJUR dibuat (kalau ada)
    akan dihapus oleh attendance_db.check_in() -- fungsi ini sendiri TIDAK
    PERNAH membuat baris untuk tanggal yang SUDAH ada Check In, dicegah
    lewat booking_db.is_jadwal_mingguan_libur() (sudah mengandung override
    Check In itu).

    Dibatasi ke tanggal <= HARI INI (WIB) -- jadwal masa depan belum tentu
    barber benar-benar tidak Check In nanti, jadi tidak boleh dibuatkan
    baris Libur lebih awal dari waktunya."""
    hari_ini = attendance_db.tanggal_hari_ini()
    akhir_efektif = min(tanggal_selesai, hari_ini)
    if akhir_efektif < tanggal_mulai:
        return

    # FITUR Pembersihan Data Bulanan Otomatis: `tanggal_mulai` TIDAK boleh
    # mundur sampai sebelum cutoff TERAKHIR yang sudah berhasil dibersihkan
    # (lihat hapus_riwayat_libur_sebelum() di bawah) -- tanpa penjagaan ini,
    # melihat Rekap periode LAMA yang SUDAH dipurge akan membuat baris
    # absensi_libur baru lagi untuk tanggal yang sama (fungsi ini dipanggil
    # OPORTUNISTIK setiap kali periode itu dibaca, tidak tahu periode itu
    # sudah "sengaja dikosongkan" oleh Owner), sehingga baris yang sudah
    # dihapus permanen seperti "muncul lagi" di Rekap.
    cutoff_tercapai = db.get_setting(_SETTING_CUTOFF_LIBUR_TERCAPAI, None, tenant_id=tenant_id)
    if cutoff_tercapai and tanggal_mulai < cutoff_tercapai:
        tanggal_mulai = cutoff_tercapai
    if akhir_efektif < tanggal_mulai:
        return

    d = date.fromisoformat(tanggal_mulai)
    akhir = date.fromisoformat(akhir_efektif)
    while d <= akhir:
        iso = d.isoformat()
        if booking_db.is_jadwal_mingguan_libur(barber_id, iso):
            with get_conn() as conn:
                sudah_ada = conn.execute(
                    "SELECT 1 FROM absensi_libur WHERE barber_id = ? AND tanggal = ?",
                    (barber_id, iso),
                ).fetchone()
            if sudah_ada is None and izin_cuti_db.get_pengajuan_aktif_pada_tanggal(barber_id, iso) is None:
                _terapkan_kuota_libur(barber_id, tenant_id, iso, sumber_libur=SUMBER_LIBUR_MINGGUAN)
        d += timedelta(days=1)


def hapus_riwayat_libur_sebelum(tenant_id: int, sebelum_tanggal: str) -> int:
    """FITUR Pembersihan Data Bulanan Otomatis (lihat data_purge_db.py):
    hapus PERMANEN baris absensi_libur (Tandai Libur manual MAUPUN Libur
    Mingguan, lihat SUMBER_LIBUR_MINGGUAN) milik tenant ini bertanggal
    lebih lama dari `sebelum_tanggal` ("YYYY-MM-01") -- tabel ini SEBELUMNYA
    TIDAK PERNAH ikut dibersihkan sama sekali (celah ditemukan Owner lewat
    Rekap production: baris "Libur" tetap tampil untuk periode yang
    Transaksi-nya sudah dihapus, lihat riwayat git).

    TIDAK butuh arsip PDF (sama seperti Booking/Log Audit/Pengajuan Koreksi
    -- hanya barber_id/tanggal/sumber, tidak ada nilai uang apa pun, dan
    jumlah "Hari Libur" bulan-bulan lama itu SUDAH ikut tercetak di PDF
    Rekap Transaksi yang dibangun SEBELUM baris ini dihapus, lihat
    laporan_pdf.py). Kuota Libur bulanan (get_sisa_kuota_libur_bulan_ini())
    SELALU menghitung bulan KALENDER BERJALAN saja, jadi menghapus baris
    bulan-bulan lalu tidak mengubah kuota yang sedang aktif.

    WAJIB mencatat `sebelum_tanggal` sebagai cutoff tercapai (dibaca
    pastikan_libur_mingguan_tercatat() di atas) SETIAP kali dipanggil --
    bahkan kalau tidak ada baris yang terhapus -- supaya baris Libur
    Mingguan yang sudah dipurge TIDAK dibuat ulang saat periode itu dilihat
    lagi di Rekap. Mengembalikan jumlah baris yang terhapus."""
    with get_conn() as conn:
        jumlah = conn.execute(
            "DELETE FROM absensi_libur WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?) "
            "AND tanggal < ?",
            (tenant_id, sebelum_tanggal),
        ).rowcount
    db.set_setting(_SETTING_CUTOFF_LIBUR_TERCAPAI, sebelum_tanggal, tenant_id=tenant_id)
    return jumlah
