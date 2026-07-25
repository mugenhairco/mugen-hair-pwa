"""
tampilan_migrasi.py — Migrasi skema untuk REVISI UI/UX: Dark Mode & Light
Mode per akun
=============================================================================
File ini SENGAJA dipisah dari auth_db.py (pola yang sama seperti migrasi
tahap-tahap sebelumnya) supaya init_auth_db() (CREATE TABLE IF NOT EXISTS,
dipanggil tiap startup) tidak perlu tahu soal ALTER TABLE.

Satu migrasi idempotent, aman dipanggil berulang kali, TIDAK PERNAH
menghapus/menimpa data yang sudah ada:

Kolom baru `users.tema` (TEXT, default 'terang') -- preferensi tema
Dark/Light Mode disimpan PER AKUN (bukan per perangkat/browser), supaya
tetap konsisten kalau akun yang sama login dari perangkat lain. User yang
SUDAH ADA otomatis dapat 'terang' (SAMA PERSIS dengan tampilan yang
sedang berjalan sebelum revisi ini) sampai account itu sendiri sengaja
mengganti lewat switch Dark Mode -- tidak ada perubahan tampilan mendadak
untuk siapa pun akibat migrasi ini.
"""

from auth_db import get_conn


def migrasi_tampilan():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "tema" not in kolom:
            conn.execute("ALTER TABLE users ADD COLUMN tema TEXT NOT NULL DEFAULT 'terang'")
