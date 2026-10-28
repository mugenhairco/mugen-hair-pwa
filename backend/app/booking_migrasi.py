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
    "booking_metode_aktif": '["qris"]',
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
        _perbaiki_metode_aktif_kosong_setelah_hapus_transfer(conn)


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


# PERMINTAAN Owner (REVISI payment): "transfer" (Transfer Bank) dihapus
# total dari booking_db.METODE_VALID -- HOTFIX DEPLOY: nilai default lama
# `DEFAULT_BOOKING_SETTINGS["booking_metode_aktif"]` di atas SEMPAT berupa
# '["transfer"]' (sebelum fix ini), jadi SETIAP tenant yang pernah ter-seed
# dari nilai itu (tenant baru yang belum pernah mengatur metode pembayaran
# SAMA SEKALI, atau tenant lama yang belum pernah mengubah default) kini
# tersimpan dengan metode_aktif berisi HANYA entri yang sudah tidak valid
# -- booking_db.get_payment_settings() menyaringnya habis (defensive
# filter) sehingga tenant itu TIDAK PUNYA metode pembayaran aktif SAMA
# SEKALI sampai Superadmin mengatur ulang secara manual. Baris di bawah
# memperbaiki data LAMA yang SUDAH tersimpan seperti itu -- HANYA tenant
# yang metode_aktif-nya SETELAH disaring menjadi KOSONG TOTAL yang
# disentuh (tenant yang sudah punya minimal satu metode valid, apa pun
# isinya, TIDAK diubah).
_METODE_VALID_SAAT_INI = {"qris", "gateway", "cash"}


def _perbaiki_metode_aktif_kosong_setelah_hapus_transfer(conn):
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key = 'booking_metode_aktif' "
        "OR key LIKE '%:booking_metode_aktif'"
    ).fetchall()
    for row in rows:
        try:
            metode_aktif = json.loads(row["value"])
        except (TypeError, ValueError):
            continue  # data korup/tidak terduga -- jangan sentuh, bukan tanggung jawab migrasi ini
        if not isinstance(metode_aktif, list):
            continue
        if [m for m in metode_aktif if m in _METODE_VALID_SAAT_INI]:
            continue  # masih punya minimal satu metode valid -- jangan sentuh
        conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps(["qris"]), row["key"]))
