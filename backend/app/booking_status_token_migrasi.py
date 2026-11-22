"""
booking_status_token_migrasi.py — Migrasi skema untuk FITUR Link Cek Status
Booking Langsung (dikirim otomatis lewat pesan WhatsApp)
=============================================================================
Satu kolom baru di `bookings` (ALTER TABLE, nullable, TANPA backfill -- pola
SAMA PERSIS nomor_transaksi_booking_migrasi.py):

- `status_token` TEXT -- string acak unik (secrets.token_urlsafe, lihat
  booking_db.py::get_atau_buat_status_token()) dipakai sebagai identifier
  AMAN di URL publik (routers/booking.py::public_cek_status_token()) supaya
  customer bisa membuka status booking-nya LANGSUNG dari link di pesan
  WhatsApp, TANPA mengetik ulang nomor WA. SENGAJA token acak TERPISAH
  (BUKAN nomor_transaksi, yang predictable dari jam/tanggal booking --
  lihat booking_db.py::_buat_nomor_transaksi_booking() -- TIDAK aman dipakai
  sebagai identifier publik: bisa ditebak/diiterasi untuk melihat data
  booking customer lain).

  NULL untuk booking LAMA (dibuat SEBELUM migrasi ini) -- SENGAJA TIDAK
  di-backfill massal saat startup (konsisten dengan filosofi proyek ini:
  hindari migrasi retroaktif massal tanpa kebutuhan nyata, lihat juga
  rekap_gabungan_db.py). Diisi LAZY, satu per satu, HANYA saat benar-benar
  dibutuhkan untuk mengirim link (booking_db.py::get_atau_buat_status_token(),
  dipanggil dari _kirim_notifikasi_wa_booking() sebelum render() template).

Index UNIQUE (bukan PRIMARY KEY, kolom boleh NULL untuk baris lama -- SQLite
mengizinkan banyak NULL berdampingan di index UNIQUE, tidak dianggap
duplikat) supaya lookup token di endpoint publik cepat & dijamin satu
booking per token.

Instalasi Postgres yang setara ada di postgres_schema.py (ALTER TABLE ADD
COLUMN IF NOT EXISTS + CREATE UNIQUE INDEX IF NOT EXISTS, blok terpisah --
modul ini TIDAK diimpor dari sana, duplikasi SENGAJA mengikuti pola yang
sudah dipakai seluruh proyek)."""

from database import get_conn


def migrasi_booking_status_token():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if "status_token" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN status_token TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_status_token ON bookings(status_token)")
