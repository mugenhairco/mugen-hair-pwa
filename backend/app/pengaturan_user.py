"""
pengaturan_user.py — Manajemen User tambahan (TAHAP 10)
=========================================================
`auth_db.py` (Tahap 3) SUDAH punya tambah_user/ganti_password/nonaktifkan_user/
get_user_list — dipakai APA ADANYA. File ini hanya menambah dua hal yang
belum ada di sana:
1. Ganti Username (dengan pesan error ramah kalau sudah dipakai user lain).
2. Aktifkan kembali user yang sebelumnya dinonaktifkan (kebalikan dari
   nonaktifkan_user yang sudah ada).

Password TETAP di-hash lewat auth_db.hash_password/ganti_password — file
ini tidak pernah menyentuh atau menyimpan password dalam bentuk plain text.
"""

from db_compat import IntegrityError
import auth_db
from auth_db import get_conn


def ganti_username(user_id: int, username_baru: str):
    username_baru = (username_baru or "").strip()
    if not username_baru:
        raise ValueError("Username tidak boleh kosong.")
    if auth_db.get_user(user_id) is None:
        raise ValueError("User tidak ditemukan.")
    try:
        with get_conn() as conn:
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (username_baru, user_id))
    except IntegrityError:
        raise ValueError(f"Username '{username_baru}' sudah dipakai.")


def aktifkan_user(user_id: int):
    if auth_db.get_user(user_id) is None:
        raise ValueError("User tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("UPDATE users SET aktif = 1 WHERE id = ?", (user_id,))
