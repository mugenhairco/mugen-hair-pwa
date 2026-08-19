"""
booking_verifikasi_migrasi.py — Migrasi skema untuk Pembayaran Manual QRIS
Tenant + Notifikasi WhatsApp ("Verifikasi Booking"/"Payment Diterima")
=============================================================================
File migrasi BARU terpisah (pola SAMA PERSIS booking_form_migrasi.py/
booking_migrasi.py: satu file migrasi per "sesi" pekerjaan) -- SATU migrasi
idempotent di sini, aman dipanggil berulang kali, TIDAK PERNAH menghapus/
menimpa data yang sudah ada:

Empat kolom baru di `bookings` (ALTER TABLE, SEMUA nullable, TANPA
backfill -- NULL memang berarti "belum pernah", bukan nilai yang harus
diisi untuk booking lama):
- `verifikasi_booking_at`/`verifikasi_booking_oleh` -- kapan & siapa (admin,
  username TEXT, pola sama seperti attendance_db.py::disetujui_oleh) yang
  menekan tombol "Verifikasi Booking" (booking_db.terima_booking()).
- `pembayaran_diterima_at`/`pembayaran_diterima_oleh` -- kapan & siapa yang
  menekan "Payment Diterima" (booking_db.verifikasi_pembayaran(), TETAP
  NULL kalau dipicu webhook Faspay otomatis -- tidak ada admin manusia di
  jalur itu).

Instalasi Postgres yang setara ada di postgres_schema.py (ALTER TABLE ADD
COLUMN IF NOT EXISTS, blok terpisah -- modul ini TIDAK diimpor dari sana,
duplikasi SENGAJA mengikuti pola yang sudah dipakai seluruh proyek)."""

from database import get_conn


def migrasi_booking_verifikasi():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if "verifikasi_booking_at" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN verifikasi_booking_at TEXT")
        if "verifikasi_booking_oleh" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN verifikasi_booking_oleh TEXT")
        if "pembayaran_diterima_at" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN pembayaran_diterima_at TEXT")
        if "pembayaran_diterima_oleh" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN pembayaran_diterima_oleh TEXT")
