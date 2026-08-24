"""
nomor_transaksi_booking_migrasi.py — Migrasi skema untuk Format Baru Nomor
Transaksi Booking
=============================================================================
File migrasi BARU terpisah (pola SAMA PERSIS booking_verifikasi_migrasi.py:
satu file migrasi per "sesi" pekerjaan) -- SATU kolom baru di `bookings`
(ALTER TABLE, nullable, TANPA backfill):

- `nomor_transaksi` -- format baru [JAM KONFIRMASI][MENIT KONFIRMASI]
  [TANGGAL BOOKING][BULAN BOOKING][JAM BOOKING][INISIAL TENANT], mis.
  "1705071313MH" (lihat booking_db.py::_buat_nomor_transaksi_booking()).
  Diisi SEKALI saat booking dibuat (booking_db.buat_booking()), TIDAK
  PERNAH diubah setelahnya. NULL berarti booking LAMA (dibuat SEBELUM
  migrasi ini) -- SENGAJA TIDAK di-backfill, frontend jatuh ke rumus lama
  (MugenUI.buatNomorTransaksi(), berbasis nama service) HANYA untuk baris
  yang kolom ini NULL, supaya nomor yang sudah pernah ditampilkan/dicatat
  ke transaksi lama TIDAK PERNAH berubah (persyaratan eksplisit Owner).

Instalasi Postgres yang setara ada di postgres_schema.py (ALTER TABLE ADD
COLUMN IF NOT EXISTS, blok terpisah -- modul ini TIDAK diimpor dari sana,
duplikasi SENGAJA mengikuti pola yang sudah dipakai seluruh proyek)."""

from database import get_conn


def migrasi_nomor_transaksi_booking():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if "nomor_transaksi" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN nomor_transaksi TEXT")
