"""
produk_migrasi.py — Migrasi skema untuk REVISI Modul Produk (Harga Modal/
Harga Jual + tipe transaksi Tester)
=============================================================================
File ini SENGAJA dipisah dari database.py (pola yang sama seperti
booking_form_migrasi.py/revisi_bonus_migrasi.py di tahap-tahap sebelumnya).

Dua migrasi idempotent, aman dipanggil berulang kali, TIDAK PERNAH
menghapus/menimpa data yang sudah ada:

1. Kolom baru `produk.harga_modal` / `produk.harga_jual` (ALTER TABLE,
   default 0) — produk yang SUDAH ADA otomatis dapat 0 sampai Owner mengisi
   sendiri lewat menu Produk, tidak ada data yang hilang/berubah.

2. Kolom baru `produk_mutasi.harga_modal_saat_itu` /
   `produk_mutasi.harga_jual_saat_itu` (ALTER TABLE, nullable) — SNAPSHOT
   harga produk pada saat transaksi Jual/Tester dicatat (lihat
   database._catat_keluar_produk), supaya laporan omzet bulan lalu TIDAK
   ikut berubah kalau Owner mengedit harga produk di kemudian hari. Baris
   mutasi LAMA (sebelum migrasi ini) otomatis NULL di kedua kolom baru ini
   -- omzet historisnya dihitung sebagai 0 (bukan salah, karena memang belum
   pernah ada data harga sebelumnya untuk transaksi itu; tidak ada cara
   menebak harga yang berlaku saat itu tanpa merusak keakuratan data).
"""

from database import get_conn


def migrasi_produk():
    with get_conn() as conn:
        _migrasi_harga_produk(conn)
        _migrasi_snapshot_harga_mutasi(conn)


def _migrasi_harga_produk(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(produk)").fetchall()]
    if "harga_modal" not in kolom:
        conn.execute("ALTER TABLE produk ADD COLUMN harga_modal INTEGER NOT NULL DEFAULT 0")
    if "harga_jual" not in kolom:
        conn.execute("ALTER TABLE produk ADD COLUMN harga_jual INTEGER NOT NULL DEFAULT 0")


def _migrasi_snapshot_harga_mutasi(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(produk_mutasi)").fetchall()]
    if "harga_modal_saat_itu" not in kolom:
        conn.execute("ALTER TABLE produk_mutasi ADD COLUMN harga_modal_saat_itu INTEGER")
    if "harga_jual_saat_itu" not in kolom:
        conn.execute("ALTER TABLE produk_mutasi ADD COLUMN harga_jual_saat_itu INTEGER")
