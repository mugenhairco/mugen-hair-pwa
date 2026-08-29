"""
session_login_migrasi.py — Kontrol Sesi Login Satu-Device per Akun
=============================================================================
File ini SENGAJA dipisah dari auth_db.py (pola yang sama seperti
lokasi_user_migrasi.py/tampilan_migrasi.py di tahap-tahap sebelumnya).

Satu kolom baru pada tabel `users`: `current_session_hash` (TEXT, boleh
NULL) -- menyimpan hash SHA-256 dari token yang SEDANG aktif untuk akun
ini (lihat auth.py::hash_token()). Login manapun (device apa pun) menulis
ulang kolom ini dengan hash token BARU, otomatis mencabut sesi lama --
lihat auth.py::get_current_user() untuk pengecekannya di setiap request.

Idempotent (aman dipanggil berulang kali), TIDAK PERNAH menghapus/menimpa
data lain."""

from auth_db import get_conn


def migrasi_session_login():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "current_session_hash" not in kolom:
            conn.execute("ALTER TABLE users ADD COLUMN current_session_hash TEXT")
