"""
auto_libur_db.py — Migrasi skema `absensi_libur.sumber`
=============================================================================
PERMINTAAN OWNER: fitur "Auto-Libur" ("jika barber tidak absen sampai jam
tutup operasional maka otomatis dicatat libur") DIHAPUS TOTAL -- loop
background real-time, sapuan bulanan, cascade Libur->Cuti&Izin->Libur
kelebihan kuota, kartu "Sisa Kuota Libur", toggle "Aktifkan Auto-Libur
Tidak Absen" di Pengaturan Izin & Cuti, dan stabilo merah "kuota_habis" di
Rekap Bulanan SEMUA dihapus dari kode (lihat routers/attendance.py,
routers/izin_cuti.py, routers/rekap.py, dan frontend/app/js/pages/
pengaturan.js, absensi.js, rekap.js). Mulai sekarang, satu-satunya cara
mencatat Barber Holiday/libur adalah MANUAL lewat menu Input Data >
Tandai Libur (database.py::tandai_libur(), TIDAK disentuh sama sekali).

Fungsi `migrasi_absensi_libur_sumber()` di bawah ini DIPERTAHANKAN (bukan
ikut dihapus) karena kolom `sumber` pada `absensi_libur` adalah kolom
penanda ASAL baris yang generik (dipakai `database.py::tandai_libur()`,
parameter `sumber` opsional) -- tidak eksklusif milik Auto-Libur, dan baris
lama yang sudah terlanjur tercatat `sumber='auto_libur'`/
`'auto_libur_kelebihan'` dari SEBELUM penghapusan ini TETAP ada di database
produksi (sengaja TIDAK dihapus/dimigrasikan -- riwayat Absensi/Rekap lama
tidak boleh hilang), jadi kolomnya tetap harus ada di skema."""

from database import get_conn


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
