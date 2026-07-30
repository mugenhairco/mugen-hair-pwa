#!/usr/bin/env python3
"""
migrate_blobs_to_r2.py — Backfill SATU KALI: pindahkan file BLOB lama ke Cloudflare R2
=========================================================================================
Script MANUAL (dijalankan langsung lewat command line, TIDAK PERNAH dipanggil
otomatis dari main.py/on_startup ataupun proses lain mana pun) untuk mengupload
file yang SUDAH ADA di kolom BLOB (`file_asset.data`, `website_gallery.data`,
`barbers.foto_data`, `reimburse.bukti_data` -- baris yang dibuat SEBELUM R2
dikonfigurasi, `*_r2_key IS NULL`) ke Cloudflare R2, lalu mengisi kolom
`*_r2_key` masing-masing supaya baris itu ikut terlayani lewat R2 mulai
sekarang (lihat r2_storage.py untuk arsitektur lengkap).

TIDAK PERLU dijalankan untuk file yang diupload SETELAH R2 dikonfigurasi --
file_asset_db.py/website_content.py/booking_db.py/reimburse_db.py otomatis
upload langsung ke R2 untuk upload baru, script ini KHUSUS backfill data lama.

ATURAN KESELAMATAN (instruksi eksplisit: jangan hapus/ubah data production):
- HANYA MENAMBAH nilai ke kolom `*_r2_key` yang sebelumnya NULL -- TIDAK
  PERNAH mengubah/menghapus satu byte pun dari kolom BLOB lama (`data`/
  `foto_data`/`bukti_data`) maupun kolom lain apa pun. Baris yang sudah
  berhasil di-backfill TETAP punya bytes lengkap di kolom BLOB-nya --
  murni redundan (bisa dibersihkan manual belakangan kalau Owner mau
  menghemat ruang, TAPI itu keputusan TERPISAH, bukan bagian script ini).
- Idempotent & aman dijalankan berulang -- baris yang `r2_key`-nya SUDAH
  terisi otomatis dilewati (di-skip, bukan diupload ulang/ditimpa).
- --dry-run: hitung & tampilkan berapa baris yang AKAN diupload di tiap
  tabel, TANPA mengupload atau menulis apa pun ke database.
- Menolak berjalan sama sekali kalau R2_* belum lengkap dikonfigurasi, atau
  kalau DATABASE_URL tidak diisi (mencegah backfill tidak sengaja jalan ke
  SQLite lokal alih-alih Neon production).

Cara pakai (manual, dari folder backend/app, DENGAN DATABASE_URL Neon DAN
env var R2_* lengkap sama-sama diisi di environment yang menjalankan ini):
    DATABASE_URL="postgresql://..." R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... \\
      R2_SECRET_ACCESS_KEY=... R2_BUCKET_NAME=... \\
      python migrate_blobs_to_r2.py --dry-run   # lihat jumlah baris dulu, tidak menulis apa pun
    DATABASE_URL="postgresql://..." R2_ACCOUNT_ID=... ... python migrate_blobs_to_r2.py  # backfill sungguhan
"""

import argparse
import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import db_compat  # noqa: E402

if not db_compat.IS_POSTGRES:
    print("DATABASE_URL belum diisi -- tidak ada database production untuk dibackfill. Batal.", file=sys.stderr)
    sys.exit(1)

import r2_storage  # noqa: E402

if not r2_storage.IS_ENABLED:
    print("Environment variable R2_* belum lengkap -- tidak ada tujuan upload. Batal.", file=sys.stderr)
    sys.exit(1)

import booking_db  # noqa: E402
import file_asset_db  # noqa: E402
import reimburse_db  # noqa: E402
import website_content  # noqa: E402
from database import get_conn  # noqa: E402

_EXT_GALLERY = {**website_content.EXT_KE_CONTENT_TYPE_GAMBAR, **website_content.EXT_KE_CONTENT_TYPE_VIDEO}


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""


def _backfill_file_asset(dry_run: bool) -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT key, filename, content_type, data FROM file_asset WHERE r2_key IS NULL AND data IS NOT NULL AND length(data) > 0"
        ).fetchall()
    print(f"file_asset: {len(rows)} baris perlu dibackfill.")
    if dry_run:
        return len(rows)
    n = 0
    for row in rows:
        prefix = file_asset_db.KEY_TO_PREFIX.get(row["key"], "assets")
        r2_key = r2_storage.upload(prefix, row["filename"], bytes(row["data"]), row["content_type"])
        with get_conn() as conn:
            conn.execute("UPDATE file_asset SET r2_key = ? WHERE key = ?", (r2_key, row["key"]))
        print(f"  [OK] key={row['key']} -> {r2_key}")
        n += 1
    return n


def _backfill_gallery(dry_run: bool) -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, data FROM website_gallery WHERE r2_key IS NULL AND data IS NOT NULL AND length(data) > 0"
        ).fetchall()
    print(f"website_gallery: {len(rows)} baris perlu dibackfill.")
    if dry_run:
        return len(rows)
    n = 0
    for row in rows:
        content_type = _EXT_GALLERY.get(_ext(row["filename"]), "application/octet-stream")
        r2_key = r2_storage.upload("gallery", row["filename"], bytes(row["data"]), content_type)
        with get_conn() as conn:
            conn.execute("UPDATE website_gallery SET r2_key = ? WHERE id = ?", (r2_key, row["id"]))
        print(f"  [OK] gallery id={row['id']} -> {r2_key}")
        n += 1
    return n


def _backfill_barber_foto(dry_run: bool) -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, foto_filename, foto_data FROM barbers WHERE foto_r2_key IS NULL AND foto_data IS NOT NULL AND length(foto_data) > 0"
        ).fetchall()
    print(f"barbers (foto): {len(rows)} baris perlu dibackfill.")
    if dry_run:
        return len(rows)
    n = 0
    for row in rows:
        content_type = booking_db.FOTO_EXT_KE_CONTENT_TYPE.get(_ext(row["foto_filename"]), "application/octet-stream")
        r2_key = r2_storage.upload("barbers", row["foto_filename"], bytes(row["foto_data"]), content_type)
        with get_conn() as conn:
            conn.execute("UPDATE barbers SET foto_r2_key = ? WHERE id = ?", (r2_key, row["id"]))
        print(f"  [OK] barber id={row['id']} -> {r2_key}")
        n += 1
    return n


def _backfill_reimburse_bukti(dry_run: bool) -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, bukti_filename, bukti_data FROM reimburse WHERE bukti_r2_key IS NULL AND bukti_data IS NOT NULL AND length(bukti_data) > 0"
        ).fetchall()
    print(f"reimburse (bukti): {len(rows)} baris perlu dibackfill.")
    if dry_run:
        return len(rows)
    n = 0
    for row in rows:
        content_type = reimburse_db.BUKTI_EXT_KE_CONTENT_TYPE.get(_ext(row["bukti_filename"]), "application/octet-stream")
        r2_key = r2_storage.upload("payments", row["bukti_filename"], bytes(row["bukti_data"]), content_type)
        with get_conn() as conn:
            conn.execute("UPDATE reimburse SET bukti_r2_key = ? WHERE id = ?", (r2_key, row["id"]))
        print(f"  [OK] reimburse id={row['id']} -> {r2_key}")
        n += 1
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Hitung & tampilkan jumlah baris saja, tidak upload/menulis apa pun.")
    args = parser.parse_args()

    print(f"Bucket tujuan: {r2_storage.R2_BUCKET_NAME}  ({'DRY RUN -- tidak ada perubahan' if args.dry_run else 'BACKFILL SUNGGUHAN'})")
    print()
    total = 0
    total += _backfill_file_asset(args.dry_run)
    total += _backfill_gallery(args.dry_run)
    total += _backfill_barber_foto(args.dry_run)
    total += _backfill_reimburse_bukti(args.dry_run)
    print()
    if args.dry_run:
        print(f"Total {total} baris AKAN diupload ke R2 kalau dijalankan tanpa --dry-run.")
    else:
        print(f"Selesai -- {total} baris berhasil dibackfill ke R2. Kolom BLOB lama TIDAK dihapus/diubah.")


if __name__ == "__main__":
    main()
