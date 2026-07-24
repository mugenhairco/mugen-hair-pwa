"""
pengaturan_backup.py — Backup Database (TAHAP 10)
===================================================
Export: kirim file .db apa adanya (dipakai lewat FileResponse di router,
tidak butuh fungsi di sini).

Import: mengganti file database yang sedang dipakai dengan file upload.
Ini operasi BERISIKO, jadi:
1. Validasi dulu file yang diupload benar-benar file SQLite (cek magic
   header), supaya tidak menimpa database yang jalan dengan file sampah.
2. SELALU backup database yang sedang aktif ke folder backups/ (dengan
   timestamp) SEBELUM menimpanya — supaya data lama tidak pernah hilang
   total walau admin salah upload file.
"""

import os
import shutil
from datetime import datetime

from database import DB_PATH

SQLITE_MAGIC = b"SQLite format 3\x00"
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "backups")


def validasi_file_sqlite(konten: bytes):
    if len(konten) < len(SQLITE_MAGIC) or konten[: len(SQLITE_MAGIC)] != SQLITE_MAGIC:
        raise ValueError("File yang diupload bukan file database SQLite yang valid (.db).")


def buat_backup_sebelum_import() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tujuan = os.path.join(BACKUP_DIR, f"mugen_hair_sebelum_import_{stamp}.db")
    if os.path.isfile(DB_PATH):
        shutil.copy2(DB_PATH, tujuan)
    return tujuan


def import_database(konten: bytes) -> str:
    """Return path backup yang dibuat sebelum penimpaan (untuk ditampilkan ke admin)."""
    validasi_file_sqlite(konten)
    backup_path = buat_backup_sebelum_import()
    with open(DB_PATH, "wb") as fh:
        fh.write(konten)
    return backup_path
