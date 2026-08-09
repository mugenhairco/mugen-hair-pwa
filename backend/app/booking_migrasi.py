"""
booking_migrasi.py — Migrasi skema untuk Modul BOOKING
=========================================================
File ini SENGAJA dipisah dari database.py (pola yang sama seperti
pengeluaran_migrasi.py/pengaturan_migrasi.py/sync_migrasi.py/
revisi_bonus_migrasi.py di tahap-tahap sebelumnya) — database.py TIDAK
disentuh sama sekali untuk modul Booking. Tabel baru modul ini (bookings,
booking_items, closed_slot) dibuat oleh booking_db.py sendiri (pola yang
sama seperti auth_db.py punya init_auth_db() terpisah dari database.py).

Dua migrasi idempotent di sini, aman dipanggil berulang kali:

1. Kolom baru `services.durasi_menit` (ALTER TABLE) — durasi standar
   (dalam menit) yang dipakai modul Booking untuk menghitung berapa slot
   jadwal yang perlu diblokir per service. Default 60 menit (sama dengan
   interval slot default) untuk semua layanan yang sudah ada, Owner bebas
   mengubahnya lewat Setting > Layanan.
2. Setting Booking (jam operasional, interval slot, maksimal hari
   booking ke depan, metode pembayaran aktif, info QRIS/transfer bank) --
   disimpan di tabel `settings` yang sudah ada (key-value generik),
   diseed HANYA kalau key-nya belum ada sama sekali (tidak pernah menimpa
   nilai yang sudah diatur Owner).
"""

import json

from database import get_conn

DEFAULT_BOOKING_SETTINGS = {
    "booking_jam_buka": "10:00",
    "booking_jam_tutup": "20:00",
    "booking_interval_menit": "60",
    "booking_maksimal_hari_kedepan": "30",
    "booking_metode_aktif": '["transfer"]',
    "booking_qris_merchant_nama": "",
    "booking_qris_filename": "",
    "booking_bank_nama": "",
    "booking_bank_nomor_rekening": "",
    "booking_bank_nama_pemilik": "",
}


def migrasi_booking():
    with get_conn() as conn:
        _migrasi_durasi_service(conn)
        _seed_booking_settings(conn)
        _hapus_metode_cash(conn)


def _migrasi_durasi_service(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(services)").fetchall()]
    if "durasi_menit" in kolom:
        return  # sudah pernah dimigrasikan, jangan sentuh nilai yang mungkin sudah diubah admin
    conn.execute("ALTER TABLE services ADD COLUMN durasi_menit INTEGER NOT NULL DEFAULT 60")


def _seed_booking_settings(conn):
    for key, default_value in DEFAULT_BOOKING_SETTINGS.items():
        existing = conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone()
        if existing is not None:
            continue  # sudah pernah diisi (migrasi sebelumnya atau admin), jangan menimpa
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, default_value))


def _hapus_metode_cash(conn):
    """HAPUS METODE CASH: strip "cash" dari `booking_metode_aktif` milik
    SEMUA tenant yang sudah pernah menyimpannya (key `settings` berpola
    `{tenant_id}:booking_metode_aktif` -- lihat `_kunci_tenant()` di
    database.py -- atau key polos `booking_metode_aktif` untuk instalasi
    single-tenant lama). Cash sudah dihapus total dari METODE_VALID
    (booking_db.py) -- baris ini murni membersihkan data LAMA yang
    mungkin masih menyebut "cash" supaya daftar metode aktif yang
    ditampilkan ke customer tidak pernah lagi berisi metode yang sudah
    tidak ada kode-nya sama sekali. Idempotent: hanya menulis ulang baris
    yang benar-benar berubah, aman dipanggil berkali-kali."""
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key = 'booking_metode_aktif' "
        "OR key LIKE '%:booking_metode_aktif'"
    ).fetchall()
    for row in rows:
        try:
            metode_aktif = json.loads(row["value"])
        except (TypeError, ValueError):
            continue  # data korup/tidak terduga -- jangan sentuh, bukan tanggung jawab migrasi ini
        if not isinstance(metode_aktif, list) or "cash" not in metode_aktif:
            continue
        baru = [m for m in metode_aktif if m != "cash"]
        conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps(baru), row["key"]))
