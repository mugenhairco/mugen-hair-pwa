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
barber yang lupa Check In otomatis dicatat Libur/Cuti -- SUDAH DIHAPUS
TOTAL atas permintaan Owner, lihat riwayat git). Kuota Libur di sini HANYA
dipicu MANUAL oleh Admin/Owner lewat Input Data > Tandai Libur -- TIDAK
ADA loop/sweep/proses otomatis apa pun di modul ini.
"""

from datetime import datetime

import attendance_db
import database as db
import izin_cuti_db
from database import get_conn

SUMBER_KELEBIHAN_KUOTA = "kelebihan_kuota"
DIAJUKAN_OLEH_KUOTA_LIBUR = "Sistem (Kuota Libur Habis)"


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


def tandai_libur_dengan_kuota(barber_id: int, tenant_id: int, tanggal: str) -> str:
    """Dipanggil routers/input_data.py SEBAGAI PENGGANTI database.tandai_libur()
    langsung -- menerapkan cascade Kuota Libur (lihat modul docstring) SAAT
    Admin/Owner menandai Libur manual untuk satu tanggal. Return
    'libur' | 'cuti' | 'kelebihan_kuota' supaya caller (router) bisa
    memberi tahu Admin/Owner persis apa yang terjadi."""
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    kuota = settings.get("kuota_libur_bulanan", 0)
    if kuota <= 0:
        db.tandai_libur(barber_id, tanggal)
        return "libur"

    tahun, bulan = int(tanggal[:4]), int(tanggal[5:7])
    terpakai = _libur_terpakai_bulan_ini(barber_id, tahun, bulan)
    if terpakai < kuota:
        db.tandai_libur(barber_id, tanggal)
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
