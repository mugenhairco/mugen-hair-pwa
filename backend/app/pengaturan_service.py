"""
pengaturan_service.py — Manajemen Layanan tambahan (TAHAP 10)
================================================================
`database.py` (Tahap 2) SUDAH punya get_services/add_service/update_service/
hapus_service/service_sudah_dipakai — dipakai APA ADANYA (tidak diduplikasi).
File ini hanya menambah:
1. Field `modal` per layanan (kolom baru dari pengaturan_migrasi.py) — TIDAK
   dipakai di hitung_komisi_service manapun, jadi murni field tambahan untuk
   dicatat/ditampilkan, tidak mengubah hasil komisi yang sudah berjalan.
2. Validasi harga/modal tidak boleh negatif, dan pesan error ramah untuk
   nama layanan kosong/duplikat (database.py mengandalkan UNIQUE constraint
   SQLite untuk itu).

Catatan: `get_services()`/`get_service()` di database.py memakai `SELECT *`,
jadi kolom `modal` otomatis ikut ke luar begitu kolom ini ada — tidak perlu
fungsi baca terpisah.
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


def tambah_service_lengkap(nama: str, harga: int, modal: int = 0,
                            pakai_potongan_chemical: bool = None) -> int:
    if not (nama or "").strip():
        raise ValueError("Nama layanan tidak boleh kosong.")
    _validasi_angka("Harga", harga)
    _validasi_angka("Modal", modal)
    try:
        service_id = db.add_service(nama, harga, pakai_potongan_chemical)
    except sqlite3.IntegrityError:
        raise ValueError(f"Nama layanan '{nama.strip()}' sudah dipakai.")
    set_modal(service_id, modal)
    return service_id


def update_service_lengkap(service_id: int, nama: str = None, harga: int = None, modal: int = None,
                            pakai_potongan_chemical: bool = None, aktif: bool = None):
    if db.get_service(service_id) is None:
        raise ValueError("Layanan tidak ditemukan.")
    if nama is not None and not nama.strip():
        raise ValueError("Nama layanan tidak boleh kosong.")
    _validasi_angka("Harga", harga)
    _validasi_angka("Modal", modal)
    try:
        db.update_service(service_id, nama=nama, harga=harga,
                           pakai_potongan_chemical=pakai_potongan_chemical, aktif=aktif)
    except sqlite3.IntegrityError:
        raise ValueError(f"Nama layanan '{(nama or '').strip()}' sudah dipakai.")
    if modal is not None:
        set_modal(service_id, modal)
