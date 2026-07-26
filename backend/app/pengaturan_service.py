"""
pengaturan_service.py — Manajemen Layanan tambahan (TAHAP 10)
================================================================
`database.py` (Tahap 2) SUDAH punya get_services/add_service/update_service/
hapus_service/service_sudah_dipakai — dipakai APA ADANYA (tidak diduplikasi).
File ini hanya menambah:
1. Field `modal` per layanan (kolom baru dari pengaturan_migrasi.py) — sejak
   REVISI Struktur Setting (lihat revisi_setting_migrasi.py), field ini
   DIPAKAI oleh hitung_komisi_service() di database.py sebagai "Harga Modal"
   yang dikurangkan dari harga sebelum dikali Persentase Komisi (mengganti
   skema lama Potongan Modal Chemical berbasis nama service) — jadi bukan
   lagi field murni tampilan seperti sebelumnya.
2. Field `durasi_menit` per layanan (kolom baru dari booking_migrasi.py,
   modul BOOKING) — dipakai untuk menghitung berapa slot jadwal yang perlu
   diblokir saat customer booking online, TIDAK dipakai di hitung_komisi_service
   ataupun perhitungan bisnis lain yang sudah ada.
3. Validasi harga/modal/durasi tidak boleh negatif, dan pesan error ramah
   untuk nama layanan kosong/duplikat (database.py mengandalkan UNIQUE
   constraint SQLite untuk itu).

Catatan: `get_services()`/`get_service()` di database.py memakai `SELECT *`,
jadi kolom `modal`/`durasi_menit` otomatis ikut ke luar begitu kolom itu
ada — tidak perlu fungsi baca terpisah.
"""

import sqlite3

import database as db
from database import get_conn


def _validasi_angka(nama_field: str, nilai):
    if nilai is not None and nilai < 0:
        raise ValueError(f"{nama_field} tidak boleh negatif.")


def set_modal(service_id: int, modal: int):
    with get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (int(modal), service_id))


def set_durasi(service_id: int, durasi_menit: int):
    with get_conn() as conn:
        conn.execute("UPDATE services SET durasi_menit = ? WHERE id = ?", (int(durasi_menit), service_id))


def tambah_service_lengkap(nama: str, harga: int, modal: int = 0,
                            pakai_potongan_chemical: bool = None, durasi_menit: int = 60) -> int:
    if not (nama or "").strip():
        raise ValueError("Nama layanan tidak boleh kosong.")
    _validasi_angka("Harga", harga)
    _validasi_angka("Modal", modal)
    if not durasi_menit or durasi_menit <= 0:
        raise ValueError("Durasi harus lebih dari 0 menit.")
    try:
        service_id = db.add_service(nama, harga, pakai_potongan_chemical)
    except sqlite3.IntegrityError:
        raise ValueError(f"Nama layanan '{nama.strip()}' sudah dipakai.")
    set_modal(service_id, modal)
    set_durasi(service_id, durasi_menit)
    return service_id


def update_service_lengkap(service_id: int, nama: str = None, harga: int = None, modal: int = None,
                            pakai_potongan_chemical: bool = None, aktif: bool = None,
                            durasi_menit: int = None):
    if db.get_service(service_id) is None:
        raise ValueError("Layanan tidak ditemukan.")
    if nama is not None and not nama.strip():
        raise ValueError("Nama layanan tidak boleh kosong.")
    _validasi_angka("Harga", harga)
    _validasi_angka("Modal", modal)
    if durasi_menit is not None and durasi_menit <= 0:
        raise ValueError("Durasi harus lebih dari 0 menit.")
    try:
        db.update_service(service_id, nama=nama, harga=harga,
                           pakai_potongan_chemical=pakai_potongan_chemical, aktif=aktif)
    except sqlite3.IntegrityError:
        raise ValueError(f"Nama layanan '{(nama or '').strip()}' sudah dipakai.")
    if modal is not None:
        set_modal(service_id, modal)
    if durasi_menit is not None:
        set_durasi(service_id, durasi_menit)
