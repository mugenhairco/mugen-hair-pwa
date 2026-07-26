"""
pengaturan_backup.py — Backup Database (TAHAP 10; PostgreSQL: tahap lanjutan)
=============================================================================
SQLite (DATABASE_URL kosong) -- TIDAK berubah sama sekali dari TAHAP 10:
Export: kirim file .db apa adanya (dipakai lewat FileResponse di router,
tidak butuh fungsi di sini).
Import: mengganti file database yang sedang dipakai dengan file upload.
Ini operasi BERISIKO, jadi:
1. Validasi dulu file yang diupload benar-benar file SQLite (cek magic
   header), supaya tidak menimpa database yang jalan dengan file sampah.
2. SELALU backup database yang sedang aktif ke folder backups/ (dengan
   timestamp) SEBELUM menimpanya — supaya data lama tidak pernah hilang
   total walau admin salah upload file.

PostgreSQL (DATABASE_URL diisi) -- TIDAK ada satu file tunggal yang bisa
di-copy seperti SQLite, jadi Export/Import di sini memakai snapshot JSON
seluruh tabel (bukan pg_dump biner -- lebih portabel, tidak butuh binary
client Postgres terpasang di proses backend) lewat export_database_postgres()/
import_database_postgres() di bawah. Router (routers/pengaturan.py) memilih
fungsi mana yang dipanggil berdasarkan db_compat.IS_POSTGRES.
"""

import json
import os
import shutil
from datetime import datetime

import db_compat
from database import DB_PATH

SQLITE_MAGIC = b"SQLite format 3\x00"
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "backups")

# Urutan FK-safe (referensi lebih dulu) -- sama seperti migrate_to_postgres.py.
# 'sync_meta' SENGAJA tidak diikutkan (fitur Google Sheets sudah dihapus).
POSTGRES_BACKUP_TABLES = [
    "settings", "barbers", "services", "transaksi", "transaksi_detail",
    "absensi_libur", "pengeluaran", "produk", "produk_mutasi", "users",
    "bookings", "booking_items", "closed_slot", "toko_libur",
]
POSTGRES_BACKUP_FORMAT = "mugen-postgres-backup-v1"


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


def export_database_postgres() -> bytes:
    with db_compat.get_conn() as conn:
        tabel = {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}").fetchall()]
                 for t in POSTGRES_BACKUP_TABLES}
    return json.dumps({"format": POSTGRES_BACKUP_FORMAT, "dibuat_pada": datetime.now().isoformat(),
                        "tabel": tabel}, default=str, ensure_ascii=False).encode("utf-8")


def _backup_json_sebelum_import_postgres() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tujuan = os.path.join(BACKUP_DIR, f"mugen_hair_postgres_sebelum_import_{stamp}.json")
    with open(tujuan, "wb") as fh:
        fh.write(export_database_postgres())
    return tujuan


def import_database_postgres(konten: bytes) -> str:
    """Return path backup JSON yang dibuat sebelum penimpaan. Mengganti
    SELURUH isi tabel bisnis dengan isi file yang diupload (DELETE lalu
    INSERT ulang per tabel, urutan FK-safe / kebalikannya untuk hapus),
    dalam SATU transaksi -- kalau ada baris yang gagal, seluruhnya
    di-rollback (lihat db_compat.get_conn()), tidak pernah database
    setengah-terisi."""
    try:
        data = json.loads(konten)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("File yang diupload bukan file backup JSON PostgreSQL yang valid.")
    if data.get("format") != POSTGRES_BACKUP_FORMAT:
        raise ValueError("Format file backup tidak dikenali untuk PostgreSQL.")

    backup_path = _backup_json_sebelum_import_postgres()

    with db_compat.get_conn() as conn:
        for t in reversed(POSTGRES_BACKUP_TABLES):
            conn.execute(f"DELETE FROM {t}")
        for t in POSTGRES_BACKUP_TABLES:
            baris = data.get("tabel", {}).get(t) or []
            if not baris:
                continue
            kolom = list(baris[0].keys())
            placeholder = ", ".join("?" for _ in kolom)
            daftar_kolom = ", ".join(kolom)
            for r in baris:
                conn.execute(
                    f"INSERT INTO {t} ({daftar_kolom}) VALUES ({placeholder})",
                    tuple(r[k] for k in kolom),
                )
            if "id" in kolom:
                conn.execute(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t}), 1), true)"
                )
    return backup_path
