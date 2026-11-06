"""
booking_dilihat_migrasi.py — Migrasi skema untuk FITUR Unread Row Highlight
(List Booking Owner/Admin)
=============================================================================
Satu kolom baru di `bookings` (ALTER TABLE, idempotent, TANPA menghapus/
menimpa data yang sudah ada -- pola SAMA PERSIS booking_sumber_migrasi.py):

- `dilihat` INTEGER NOT NULL DEFAULT 1 -- 0 berarti "baru/belum pernah
  dilihat staff" (baris di-highlight warna lembut di tab Booking List,
  lihat pages/booking.js::bookingTable()), 1 berarti "sudah dilihat"
  (tampilan normal). DEFAULT 1 di migrasi ini SENGAJA (BUKAN 0) -- supaya
  SELURUH booking LAMA yang sudah ada sebelum fitur ini ditambahkan
  langsung dianggap "sudah dilihat" (tidak tiba-tiba semuanya ter-highlight
  massal begitu fitur ini rilis). Status bersama SATU untuk SEMUA staff/
  Owner yang login (bukan per-akun) -- begitu satu orang membereskannya,
  baris itu normal untuk semua yang membuka Booking List.

  buat_booking() (booking_db.py) mengisi kolom ini EKSPLISIT untuk booking
  BARU (menimpa DEFAULT di atas, yang hanya berlaku untuk baris LAMA via
  ALTER TABLE): 0 untuk sumber="publik" (customer self-booking, belum
  pernah dilihat staff manapun), 1 untuk sumber="kasir_mandiri" (staff
  sendiri yang menginputnya saat itu juga -- PERMINTAAN Owner: booking
  Booking Mandiri TIDAK PERNAH perlu di-highlight). Ditandai 1 lagi lewat
  tandai_booking_dilihat() (dipanggil endpoint POST /{id}/tandai-dilihat)
  begitu staff mengklik salah satu tombol aksi (Verifikasi/Batalkan/
  Reschedule) ATAU klik barisnya langsung (KHUSUS booking metode "gateway"
  -- booking itu tidak punya tombol Verifikasi sama sekali, status hanya
  berubah otomatis lewat webhook provider).

Instalasi Postgres yang setara ada di postgres_schema.py (ALTER TABLE ADD
COLUMN IF NOT EXISTS, blok terpisah -- modul ini TIDAK diimpor dari sana,
duplikasi SENGAJA mengikuti pola yang sudah dipakai seluruh proyek)."""

from database import get_conn


def migrasi_booking_dilihat():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if "dilihat" not in kolom:
            conn.execute("ALTER TABLE bookings ADD COLUMN dilihat INTEGER NOT NULL DEFAULT 1")
