"""
booking_sumber_migrasi.py — Migrasi skema untuk FITUR Booking Mandiri (kasir
mencatat customer walk-in langsung dari menu Booking, bukan lewat wizard
publik)
=============================================================================
Satu kolom baru di `bookings` (ALTER TABLE, idempotent, TANPA menghapus/
menimpa data yang sudah ada -- pola SAMA PERSIS booking_verifikasi_migrasi.py):

- `sumber` TEXT NOT NULL DEFAULT 'publik' -- 'publik' untuk booking lewat
  wizard publik customer (TERMASUK seluruh booking lama sebelum migrasi ini,
  via DEFAULT), 'kasir_mandiri' untuk booking yang diinput staff lewat tab
  Booking > Booking Mandiri. Dipakai booking_db.py untuk: (1) nomor WhatsApp
  customer BOLEH kosong khusus 'kasir_mandiri' (lihat buat_booking_mandiri()),
  (2) blokir SEMUA notifikasi WhatsApp Fonte untuk booking 'kasir_mandiri'
  (lihat _kirim_notifikasi_wa_booking()) -- kasir yang menangani customer ini
  langsung/lewat telepon, WhatsApp otomatis tidak relevan di jalur ini.

Instalasi Postgres yang setara ada di postgres_schema.py (ALTER TABLE ADD
COLUMN IF NOT EXISTS, blok terpisah -- modul ini TIDAK diimpor dari sana,
duplikasi SENGAJA mengikuti pola yang sudah dipakai seluruh proyek)."""

from database import get_conn


def migrasi_booking_sumber():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if "sumber" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN sumber TEXT NOT NULL DEFAULT 'publik'")
