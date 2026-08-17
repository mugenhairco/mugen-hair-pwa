"""
user_roles_migrasi.py — Migrasi skema untuk FITUR Role User Custom
=============================================================================
File ini SENGAJA dipisah dari auth_db.py (pola yang sama seperti
tampilan_migrasi.py) supaya init_auth_db() (CREATE TABLE IF NOT EXISTS,
dipanggil tiap startup) tidak perlu tahu soal ALTER TABLE.

Satu migrasi idempotent, aman dipanggil berulang kali, TIDAK PERNAH
menghapus/menimpa data yang sudah ada:

Kolom baru `users.custom_role_id` (INTEGER, nullable) -- referensi opsional
ke `user_roles.id` (lihat user_roles_db.py). NULL (default, TERMASUK
SEMUA akun staff yang sudah ada sebelum fitur ini) berarti "pakai set izin
default tenant" (perilaku LAMA, TIDAK BERUBAH sama sekali) -- diisi HANYA
kalau Owner sengaja menempelkan akun itu ke role custom tertentu. TIDAK
ada FK di sini (pola sama seperti tenant_id/barber_id lain di tabel
`users` -- tabel produksi lama, lihat catatan panjang soal FK di
postgres_schema.py)."""

from auth_db import get_conn


def migrasi_user_roles():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "custom_role_id" not in kolom:
            conn.execute("ALTER TABLE users ADD COLUMN custom_role_id INTEGER")
