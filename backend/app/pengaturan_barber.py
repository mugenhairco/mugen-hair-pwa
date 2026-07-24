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

import sqlite3

import database as db
from database import get_conn


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
    if db.get_barber(barber_id) is None:
        raise ValueError("Barber tidak ditemukan.")
    if barber_sudah_dipakai(barber_id):
        raise ValueError(
            "Barber ini sudah memiliki riwayat transaksi/absensi dan tidak dapat "
            "dihapus. Silakan gunakan fitur Nonaktifkan Barber."
        )
    with get_conn() as conn:
        conn.execute("DELETE FROM barbers WHERE id = ?", (barber_id,))


def tambah_barber_validated(nama: str, is_rafiq: bool = False) -> int:
    if not (nama or "").strip():
        raise ValueError("Nama barber tidak boleh kosong.")
    try:
        return db.add_barber(nama, is_rafiq)
    except sqlite3.IntegrityError:
        raise ValueError(f"Nama barber '{nama.strip()}' sudah dipakai.")


def update_barber_validated(barber_id: int, nama: str = None, is_rafiq: bool = None, aktif: bool = None):
    if db.get_barber(barber_id) is None:
        raise ValueError("Barber tidak ditemukan.")
    if nama is not None and not nama.strip():
        raise ValueError("Nama barber tidak boleh kosong.")
    try:
        db.update_barber(barber_id, nama=nama, is_rafiq=is_rafiq, aktif=aktif)
    except sqlite3.IntegrityError:
        raise ValueError(f"Nama barber '{(nama or '').strip()}' sudah dipakai.")
