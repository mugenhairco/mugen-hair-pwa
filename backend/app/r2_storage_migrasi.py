"""
r2_storage_migrasi.py — Migrasi skema untuk penyimpanan Cloudflare R2
=============================================================================
Empat kolom baru (`*_r2_key`, semua TEXT nullable) di empat tabel yang
sebelumnya menyimpan file lewat BLOB langsung (lihat r2_storage.py untuk
arsitektur lengkap) -- dikumpulkan di SATU file migrasi terpisah (pola sama
seperti booking_form_migrasi.py/karyawan_migrasi.py: satu file migrasi per
sesi pekerjaan) karena keempatnya menyentuh tabel milik modul yang berbeda
(file_asset_db.py, website_content.py, booking_db.py/database.py, reimburse_db.py).

PENTING -- TIDAK DESTRUKTIF: hanya menambah kolom baru (nullable, tanpa
default yang mengubah baris lama), TIDAK PERNAH menghapus/menimpa kolom
`data`/`foto_data`/`bukti_data` (BLOB) yang sudah ada -- baris lama yang
belum pernah di-backfill ke R2 (`*_r2_key IS NULL`) TETAP bisa dibaca lewat
jalur BLOB lama sampai `migrate_blobs_to_r2.py` dijalankan manual. Jalur
PostgreSQL: kolom yang SAMA ditambahkan di postgres_schema.py (ALTER TABLE
... ADD COLUMN IF NOT EXISTS, native idempotent di Postgres -- fungsi di
file ini HANYA dipanggil di jalur SQLite, sama seperti migrasi lain di
proyek ini)."""

from database import get_conn


def migrasi_r2_storage():
    with get_conn() as conn:
        _tambah_kolom(conn, "file_asset", "r2_key", "TEXT")
        _tambah_kolom(conn, "website_gallery", "r2_key", "TEXT")
        _tambah_kolom(conn, "barbers", "foto_r2_key", "TEXT")
        _tambah_kolom(conn, "reimburse", "bukti_r2_key", "TEXT")


def _tambah_kolom(conn, tabel: str, kolom: str, tipe: str):
    kolom_ada = [r["name"] for r in conn.execute(f"PRAGMA table_info({tabel})").fetchall()]
    if kolom_ada and kolom not in kolom_ada:
        conn.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {tipe}")
