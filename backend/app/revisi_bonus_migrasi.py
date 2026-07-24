"""
revisi_bonus_migrasi.py — Migrasi skema untuk REVISI (Target Bonus Service
bertingkat + Uang Harian per-barber)
=============================================================================
File ini SENGAJA dipisah dari database.py (pola yang sama seperti
pengeluaran_migrasi.py/pengaturan_migrasi.py/sync_migrasi.py di
tahap-tahap sebelumnya) — database.py TIDAK disentuh untuk migrasi ini.

Dua migrasi idempotent, aman dipanggil berulang kali, TIDAK PERNAH
menghapus/menimpa data yang sudah ada:

1. Kolom baru `barbers.uang_harian` (ALTER TABLE) — sebelumnya nominal
   Uang Harian ditentukan dari DUA setting global (`uang_harian_barber` /
   `uang_harian_rafiq`) dipilih berdasarkan flag `is_rafiq`. Revisi ini
   mengganti jadi SATU nominal per-barber yang bisa diatur bebas oleh
   admin lewat menu Setting > Barber. Supaya nominal yang SEDANG berjalan
   untuk barber yang sudah ada TIDAK BERUBAH sedikit pun akibat migrasi
   ini, kolom baru itu di-backfill dari nilai efektif barber itu SAAT INI
   (persis rumus lama: is_rafiq ? uang_harian_rafiq : uang_harian_barber),
   hanya SEKALI saat kolom itu pertama kali dibuat.

2. Setting baru `bonus_customer_tiers` (tabel `settings`, key-value
   generik yang sudah ada sejak Tahap 2 — tidak perlu tabel baru) — daftar
   JSON target bertingkat untuk Bonus Customer/Target Bonus Service (mis.
   [{"target":60,"bonus":150000}, {"target":100,"bonus":250000}, ...]),
   menggantikan sistem lama yang cuma satu target
   (`target_bonus_customer`/`nominal_bonus_customer`). Supaya bonus yang
   SEDANG berjalan untuk siapa pun TIDAK BERUBAH sampai admin sengaja
   menambah/mengubah tier lewat menu Setting, nilai awalnya di-seed dari
   SATU tier yang setara dengan setting lama itu (kalau setting lama
   sudah ada) atau default `DEFAULT_SETTINGS` (kalau instalasi baru).
"""

import json

from database import DEFAULT_SETTINGS, get_conn


def migrasi_revisi_bonus():
    with get_conn() as conn:
        _migrasi_uang_harian_per_barber(conn)
        _migrasi_bonus_tiers(conn)


def _migrasi_uang_harian_per_barber(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
    if "uang_harian" in kolom:
        return  # sudah pernah dimigrasikan, jangan sentuh nilai yang mungkin sudah diubah admin

    conn.execute("ALTER TABLE barbers ADD COLUMN uang_harian INTEGER NOT NULL DEFAULT 0")

    def _ambil_setting(key):
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        nilai = row["value"] if row else DEFAULT_SETTINGS.get(key, "0")
        try:
            return int(float(nilai))
        except (TypeError, ValueError):
            return 0

    uang_harian_barber = _ambil_setting("uang_harian_barber")
    uang_harian_rafiq = _ambil_setting("uang_harian_rafiq")

    for barber in conn.execute("SELECT id, is_rafiq FROM barbers").fetchall():
        nominal = uang_harian_rafiq if barber["is_rafiq"] else uang_harian_barber
        conn.execute("UPDATE barbers SET uang_harian = ? WHERE id = ?", (nominal, barber["id"]))


def _migrasi_bonus_tiers(conn):
    existing = conn.execute("SELECT value FROM settings WHERE key = 'bonus_customer_tiers'").fetchone()
    if existing is not None:
        return  # sudah pernah dimigrasikan / sudah pernah diisi admin, jangan menimpa

    def _ambil_setting(key):
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        nilai = row["value"] if row else DEFAULT_SETTINGS.get(key)
        try:
            return int(float(nilai))
        except (TypeError, ValueError):
            return None

    target = _ambil_setting("target_bonus_customer") or int(DEFAULT_SETTINGS["target_bonus_customer"])
    bonus = _ambil_setting("nominal_bonus_customer") or int(DEFAULT_SETTINGS["nominal_bonus_customer"])
    tiers = json.dumps([{"target": target, "bonus": bonus}])
    conn.execute("INSERT INTO settings (key, value) VALUES ('bonus_customer_tiers', ?)", (tiers,))
