"""
booking_notif_dimatikan_migrasi.py — Migrasi skema untuk FITUR Matikan
Notifikasi Suara per-Booking (List Booking Owner/Admin)
=============================================================================
Satu kolom baru di `bookings` (ALTER TABLE, idempotent, TANPA menghapus/
menimpa data yang sudah ada -- pola SAMA PERSIS booking_dilihat_migrasi.py):

- `notif_suara_dimatikan` INTEGER NOT NULL DEFAULT 0 -- 1 berarti booking
  ini TIDAK ikut dihitung lagi oleh booking_db.hitung_booking_belum_
  dikonfirmasi() (dipakai booking_notif.js utk badge + chime berulang),
  walau status_pembayaran booking itu SENDIRI masih 'menunggu_verifikasi'.
  Diisi lewat klik "No. Transaksi" booking itu di tab Booking List (lihat
  pages/booking.js::bookingTable()) -> POST /api/booking/{id}/matikan-
  notifikasi-suara. Status BERSAMA untuk SEMUA staff/Owner (bukan per-akun,
  SAMA seperti `dilihat`) -- begitu satu kasir mematikan, booking itu tidak
  lagi ikut berbunyi di device manapun begitu badge/chime di-refresh lagi
  (lewat trigger yang SUDAH ada: navigasi menu, login, visibilitychange,
  aksi booking lain -- TIDAK ada push baru ditambahkan khusus utk ini,
  SENGAJA dijaga sesederhana mungkin). Tidak ada jalur "nyalakan lagi" --
  sekali dimatikan, permanen untuk booking itu.

Instalasi Postgres yang setara ada di postgres_schema.py (ALTER TABLE ADD
COLUMN IF NOT EXISTS, blok terpisah -- modul ini TIDAK diimpor dari sana,
duplikasi SENGAJA mengikuti pola yang sudah dipakai seluruh proyek)."""

from database import get_conn


def migrasi_booking_notif_dimatikan():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if "notif_suara_dimatikan" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN notif_suara_dimatikan INTEGER NOT NULL DEFAULT 0")
