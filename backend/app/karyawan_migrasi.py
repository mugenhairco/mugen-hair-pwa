"""
karyawan_migrasi.py — Migrasi skema untuk Karyawan Non-Barber (Kasir/OB/Kru)
=============================================================================
File ini SENGAJA dipisah dari database.py (pola yang sama seperti
revisi_bonus_migrasi.py/pengeluaran_migrasi.py di tahap-tahap sebelumnya).

Dua kolom baru pada tabel `barbers` (tabel TIDAK di-rename -- FK-nya
dipakai ~10 tabel lain, generalisasi cukup lewat kolom `jabatan` baru,
lihat database.py::get_barbers()/get_karyawan()):

1. `jabatan` (TEXT, default 'barber') -- menandai apakah baris ini Barber
   (jasa potong rambut, komisi/booking/rekap bulanan tetap eksklusif
   jabatan ini) atau karyawan lain non-login (Kasir/OB/Kru, nilai valid
   lihat pengaturan_barber.JABATAN_VALID). Baris LAMA otomatis
   'barber' lewat DEFAULT, tidak perlu backfill manual.
2. `gaji_per_hari` (INTEGER, default 0) -- HANYA relevan untuk jabatan
   non-barber (Gaji = gaji_per_hari x jumlah hari masuk, diinput manual
   saat Generate Slip Gaji, lihat slip_gaji_db.py). Untuk Barber, kolom
   ini tidak dipakai sama sekali (Barber tetap gaji_pokok bulanan flat).

Idempotent (aman dipanggil berulang kali), TIDAK PERNAH menghapus/
menimpa data yang sudah ada.
"""

from database import get_conn


def migrasi_karyawan():
    with get_conn() as conn:
        _migrasi_kolom_jabatan(conn)
        _migrasi_kolom_gaji_per_hari(conn)


def _migrasi_kolom_jabatan(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
    if "jabatan" in kolom:
        return
    conn.execute("ALTER TABLE barbers ADD COLUMN jabatan TEXT NOT NULL DEFAULT 'barber'")


def _migrasi_kolom_gaji_per_hari(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
    if "gaji_per_hari" in kolom:
        return
    conn.execute("ALTER TABLE barbers ADD COLUMN gaji_per_hari INTEGER NOT NULL DEFAULT 0")
