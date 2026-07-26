#!/usr/bin/env python3
"""
migrate_to_postgres.py — Migrasi SATU KALI data dari SQLite ke PostgreSQL
=============================================================================
Script MANUAL (dijalankan langsung lewat command line, TIDAK PERNAH dipanggil
otomatis dari main.py/on_startup ataupun proses lain mana pun) untuk menyalin
seluruh data yang sudah ada di SQLite (backend/app/mugen_hair.db) ke database
PostgreSQL yang ditunjuk oleh environment variable DATABASE_URL.

ATURAN KESELAMATAN:
- SQLite di-backup OTOMATIS (salinan file .db, dengan stempel waktu, ke
  folder backend/backups/) SEBELUM satu baris pun dibaca -- lihat
  _backup_sqlite() di bawah. SQLite sumber dibuka READ-ONLY sepanjang
  proses ini, TIDAK PERNAH ditulis/diubah.
- Skema PostgreSQL dipastikan lengkap lebih dulu lewat
  postgres_schema.create_all() (idempotent, tidak menghapus apa pun).
- Menolak berjalan kalau tabel target di PostgreSQL SUDAH ADA ISINYA --
  mencegah data dobel kalau script ini tidak sengaja dijalankan dua kali --
  kecuali dijalankan dengan --force.
- HANYA menyalin data. TIDAK membuat aplikasi mulai memakai PostgreSQL
  (cutover) -- itu tetap ditentukan sepenuhnya oleh ada/tidaknya
  DATABASE_URL di environment proses backend (lihat db_compat.py), langkah
  TERPISAH yang baru dilakukan setelah migrasi ini diverifikasi lengkap
  dan Owner memberi persetujuan eksplisit.

Cara pakai (manual, dari folder backend/app):
    DATABASE_URL="postgresql://..." python migrate_to_postgres.py --dry-run
    DATABASE_URL="postgresql://..." python migrate_to_postgres.py
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import db_compat  # noqa: E402

if not db_compat.IS_POSTGRES:
    print("DATABASE_URL belum diisi -- tidak ada target PostgreSQL untuk migrasi. Batal.", file=sys.stderr)
    sys.exit(1)

import database as db  # noqa: E402
import postgres_schema  # noqa: E402

# Urutan menyalin WAJIB mengikuti dependensi foreign key (tabel yang
# direferensikan disalin lebih dulu). Kolom kedua = nama kolom primary key
# ('id' ber-SERIAL untuk sebagian besar tabel, 'key' untuk tabel key-value
# 'settings' yang primary key-nya bukan SERIAL).
TABEL_URUTAN = [
    ("settings", "key"),
    ("barbers", "id"),
    ("services", "id"),
    ("transaksi", "id"),
    ("transaksi_detail", "id"),
    ("absensi_libur", "id"),
    ("pengeluaran", "id"),
    ("produk", "id"),
    ("produk_mutasi", "id"),
    ("users", "id"),
    ("bookings", "id"),
    ("booking_items", "id"),
    ("closed_slot", "id"),
    ("toko_libur", "id"),
]

# Tabel yang diperiksa oleh _cek_target_kosong() -- SENGAJA TIDAK termasuk
# 'settings' dan 'services': postgres_schema.create_all() (dipanggil sebelum
# penyalinan) SELALU mengisi keduanya dengan nilai default/service bawaan,
# jadi keduanya PASTI tidak kosong pada instalasi PostgreSQL baru sekalipun
# -- memeriksa keduanya di sini akan salah mendeteksi instalasi baru sebagai
# "sudah ada data". Data sebenarnya dari SQLite tetap menang lewat UPSERT di
# _salin_tabel() (ON CONFLICT DO UPDATE), jadi nilai default itu otomatis
# tertimpa nilai asli tanpa perlu tabel ini dianggap "kotor".
TABEL_DIPERIKSA_KOSONG = {t for t, _ in TABEL_URUTAN if t not in ("settings", "services")}


def _backup_sqlite():
    if not os.path.isfile(db.DB_PATH):
        print(f"Peringatan: file SQLite tidak ditemukan di {db.DB_PATH} -- tidak ada yang dibackup/dimigrasikan.")
        return None
    backup_dir = os.path.join(os.path.dirname(_APP_DIR), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"mugen_hair_pre_postgres_migrate_{stamp}.db")
    shutil.copy2(db.DB_PATH, dest)
    print(f"Backup SQLite dibuat: {dest}")
    return dest


def _sqlite_conn():
    conn = sqlite3.connect(f"file:{db.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _cek_target_kosong(pg_conn, force: bool):
    tidak_kosong = []
    for tabel in TABEL_DIPERIKSA_KOSONG:
        n = pg_conn.execute(f"SELECT COUNT(*) AS n FROM {tabel}").fetchone()["n"]
        if n > 0:
            tidak_kosong.append((tabel, n))
    if tidak_kosong and not force:
        print("PostgreSQL sudah punya data di tabel berikut -- migrasi dibatalkan "
              "(pakai --force untuk tetap lanjut, mis. untuk melanjutkan migrasi yang terputus "
              "atau menjalankan ulang migrasi dengan aman -- baris disalin lewat UPSERT, data "
              "SQLite akan menang/menimpa baris PostgreSQL dengan id yang sama):")
        for tabel, n in tidak_kosong:
            print(f"  - {tabel}: {n} baris")
        sys.exit(1)


def _salin_tabel(sqlite_conn, pg_conn, tabel: str, pk: str) -> int:
    rows = sqlite_conn.execute(f"SELECT * FROM {tabel}").fetchall()
    if not rows:
        print(f"  {tabel}: 0 baris (dilewati)")
        return 0
    kolom = rows[0].keys()
    placeholder = ", ".join("?" for _ in kolom)
    daftar_kolom = ", ".join(kolom)
    # UPSERT (bukan sekadar INSERT ... ON CONFLICT DO NOTHING): SQLite adalah
    # sumber kebenaran yang sedang dimigrasikan, jadi datanya SELALU menang
    # menimpa baris yang kebetulan sudah ada di PostgreSQL dengan primary key
    # yang sama (mis. default 'settings'/'services' yang otomatis diisi
    # postgres_schema.create_all() di atas) -- ini juga membuat script ini
    # aman dijalankan ulang berkali-kali (idempotent per baris).
    kolom_update = [k for k in kolom if k != pk]
    conflict = (
        f"ON CONFLICT ({pk}) DO UPDATE SET " + ", ".join(f"{k} = EXCLUDED.{k}" for k in kolom_update)
        if kolom_update else f"ON CONFLICT ({pk}) DO NOTHING"
    )
    for r in rows:
        nilai = tuple(r[k] for k in kolom)
        pg_conn.execute(f"INSERT INTO {tabel} ({daftar_kolom}) VALUES ({placeholder}) {conflict}", nilai)
    if pk == "id":
        # Baris disalin dengan id EKSPLISIT (mempertahankan id asli dari
        # SQLite, supaya foreign key antar tabel yang ikut disalin tetap
        # valid) -- sequence SERIAL kolom itu perlu disamakan ke MAX(id)
        # setelahnya, supaya INSERT berikutnya lewat aplikasi (tanpa id
        # eksplisit) melanjutkan dari situ, bukan mulai dari 1 lagi.
        pg_conn.execute(
            f"SELECT setval(pg_get_serial_sequence('{tabel}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {tabel}), 1), true)"
        )
    print(f"  {tabel}: {len(rows)} baris disalin")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true",
                         help="Tetap lanjut walau tabel target PostgreSQL sudah berisi data.")
    parser.add_argument("--dry-run", action="store_true",
                         help="Hanya tampilkan jumlah baris di SQLite yang AKAN disalin, tidak menulis apa pun ke PostgreSQL.")
    args = parser.parse_args()

    _backup_sqlite()
    sqlite_conn = _sqlite_conn()

    if args.dry_run:
        print("--dry-run: jumlah baris di SQLite (tidak ada yang ditulis ke PostgreSQL):")
        for tabel, _ in TABEL_URUTAN:
            n = sqlite_conn.execute(f"SELECT COUNT(*) AS n FROM {tabel}").fetchone()[0]
            print(f"  {tabel}: {n} baris")
        return

    print("Memastikan skema PostgreSQL sudah lengkap...")
    postgres_schema.create_all()

    with db_compat.get_conn() as pg_conn:
        _cek_target_kosong(pg_conn, args.force)
        print("Menyalin data...")
        total = sum(_salin_tabel(sqlite_conn, pg_conn, tabel, kolom_id) for tabel, kolom_id in TABEL_URUTAN)
        print(f"Selesai: {total} baris disalin ke PostgreSQL.")
        print("PENTING: ini BELUM cutover -- aplikasi baru benar-benar memakai PostgreSQL kalau "
              "DATABASE_URL diisi di environment proses backend (mis. di Render) DAN proses backend "
              "di-restart. Jangan lakukan itu sebelum data di atas diverifikasi lengkap dan Owner setuju.")


if __name__ == "__main__":
    main()
