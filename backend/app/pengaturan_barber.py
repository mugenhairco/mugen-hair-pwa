"""
pengaturan_barber.py — Manajemen Barber tambahan (TAHAP 10)
=============================================================
`database.py` (Tahap 2) SUDAH punya get_barbers/add_barber/update_barber —
dipakai APA ADANYA di sini (tidak diduplikasi/diubah). File ini HANYA
menambah dua hal yang belum ada di database.py:
1. Hapus Barber PERMANEN — tapi hanya boleh kalau barber itu belum pernah
   punya transaksi ATAU hari libur (supaya histori/perhitungan lama tidak
   pernah kehilangan data). Kalau sudah pernah dipakai, ditolak dengan
   pesan yang mengarahkan ke fitur Nonaktifkan (sudah ada di update_barber).
2. Pesan error yang ramah untuk nama kosong / nama duplikat (database.py
   hanya mengandalkan UNIQUE constraint di level SQLite untuk itu).
"""

import r2_storage
from db_compat import IntegrityError
import database as db
from database import get_conn

# Karyawan Non-Barber (Kasir/OB/Kru): jabatan valid untuk baris tabel
# `barbers` -- 'barber' tetap eksklusif jasa potong rambut (Komisi/Booking/
# Rekap Bulanan), jabatan lain HANYA login-less (tidak pernah dapat akun
# user, lihat auth_db.py -- dikelola Owner/Admin lewat Slip Gaji/Kasbon/
# Reimburse/Izin Cuti "atas nama" karyawan itu).
# REVISI (Non-Barber custom role): jabatan tetap 'barber' untuk Barber
# (SATU-SATUNYA nilai yang boleh, kode di seluruh aplikasi mencocokkan
# string ini persis -- lihat mis. database.py get_barbers()), TAPI Owner
# sekarang boleh membuat role Non-Barber APA SAJA (bukan cuma Kasir/OB/Kru
# yang dulu dikunci ke 3 pilihan tetap) lewat _jabatan_valid() di bawah --
# JABATAN_DEFAULT tetap dipertahankan HANYA untuk daftar pilihan cepat di
# form Setting > Karyawan (dropdown), BUKAN lagi validasi yang mengunci.
JABATAN_DEFAULT = {"barber", "kasir", "ob", "kru"}


def _jabatan_valid(jabatan: str) -> bool:
    """'barber' HARUS persis string itu (reserved). Selain itu, APA SAJA
    boleh selama teks non-kosong dan bukan kebetulan menulis 'barber' dengan
    kapitalisasi/spasi berbeda (supaya tidak ada dua jabatan yang keduanya
    "dianggap" barber oleh Owner tapi berbeda string secara teknis)."""
    j = (jabatan or "").strip()
    if not j:
        return False
    if j == "barber":
        return True
    return j.lower() != "barber"


def barber_sudah_dipakai(barber_id: int) -> bool:
    with get_conn() as conn:
        jml_transaksi = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM transaksi WHERE barber_id = ?", (barber_id,)
        ).fetchone()["jumlah"]
        jml_libur = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ?", (barber_id,)
        ).fetchone()["jumlah"]
        return (jml_transaksi + jml_libur) > 0


def hapus_barber(barber_id: int):
    barber = db.get_barber(barber_id)
    if barber is None:
        raise ValueError("Barber tidak ditemukan.")
    if barber_sudah_dipakai(barber_id):
        raise ValueError(
            "Barber ini sudah memiliki riwayat transaksi/absensi dan tidak dapat "
            "dihapus. Silakan gunakan fitur Nonaktifkan Barber."
        )
    r2_key = barber.get("foto_r2_key")
    with get_conn() as conn:
        conn.execute("DELETE FROM barbers WHERE id = ?", (barber_id,))
    if r2_key:
        r2_storage.delete(r2_key)


def tambah_barber_validated(nama: str, is_rafiq: bool = False, uang_harian: int = 0,
                             jabatan: str = "barber", gaji_per_hari: int = 0) -> int:
    if not (nama or "").strip():
        raise ValueError("Nama karyawan tidak boleh kosong.")
    jabatan = (jabatan or "").strip()
    if not _jabatan_valid(jabatan):
        raise ValueError(f"Jabatan tidak valid: {jabatan}")
    if uang_harian < 0:
        raise ValueError("Uang harian tidak boleh negatif.")
    if gaji_per_hari < 0:
        raise ValueError("Gaji per hari tidak boleh negatif.")
    try:
        return db.add_barber(nama, is_rafiq, uang_harian, jabatan=jabatan, gaji_per_hari=gaji_per_hari)
    except IntegrityError:
        raise ValueError(f"Nama karyawan '{nama.strip()}' sudah dipakai.")


def update_barber_validated(barber_id: int, nama: str = None, is_rafiq: bool = None, aktif: bool = None,
                             uang_harian: int = None, jabatan: str = None, gaji_per_hari: int = None):
    if db.get_barber(barber_id) is None:
        raise ValueError("Karyawan tidak ditemukan.")
    if nama is not None and not nama.strip():
        raise ValueError("Nama karyawan tidak boleh kosong.")
    if jabatan is not None:
        jabatan = jabatan.strip()
        if not _jabatan_valid(jabatan):
            raise ValueError(f"Jabatan tidak valid: {jabatan}")
    if uang_harian is not None and uang_harian < 0:
        raise ValueError("Uang harian tidak boleh negatif.")
    if gaji_per_hari is not None and gaji_per_hari < 0:
        raise ValueError("Gaji per hari tidak boleh negatif.")
    try:
        db.update_barber(barber_id, nama=nama, is_rafiq=is_rafiq, aktif=aktif, uang_harian=uang_harian,
                          jabatan=jabatan, gaji_per_hari=gaji_per_hari)
    except IntegrityError:
        raise ValueError(f"Nama karyawan '{(nama or '').strip()}' sudah dipakai.")
