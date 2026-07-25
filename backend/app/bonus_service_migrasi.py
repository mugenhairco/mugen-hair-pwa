"""
bonus_service_migrasi.py — Migrasi skema untuk REVISI Setting Bonus Service
+ Setting Uang Harian (menghilangkan hardcode Dry Cut/Cut & Wash)
=============================================================================
File ini SENGAJA dipisah dari database.py (pola yang sama seperti
revisi_bonus_migrasi.py/booking_form_migrasi.py di tahap-tahap sebelumnya).

SEBELUM revisi ini, Target Bonus Service (bonus bulanan bertingkat) DAN
syarat cair Uang Harian (>= 3 service/hari) SAMA-SAMA hardcode ke konstanta
`SERVICE_UANG_HARIAN = {"Dry Cut", "Cut & Wash"}` di database.py -- satu
konstanta dipakai untuk DUA keperluan berbeda. Revisi ini memisahkan
keduanya jadi DUA pengaturan independen (Setting > Bonus Service dan
Setting > Uang Harian, masing-masing daftar service pilihan Owner sendiri),
supaya mengubah salah satu TIDAK memengaruhi yang lain.

Satu migrasi idempotent, aman dipanggil berulang kali, TIDAK PERNAH
menimpa pengaturan yang sudah pernah diisi Owner:

Setting baru `bonus_service_acuan_service_ids` dan
`uang_harian_acuan_service_ids` (tabel `settings`, key-value generik yang
sudah ada sejak Tahap 2 -- tidak perlu tabel baru), masing-masing JSON list
of service id. Supaya bonus & uang harian yang SEDANG berjalan TIDAK
BERUBAH SEDIKIT PUN sampai Owner sengaja mengubahnya lewat menu Setting,
nilai awal KEDUA setting ini di-seed dari id service "Dry Cut" dan
"Cut & Wash" yang SEDANG ADA di database (persis service yang dipakai
konstanta lama) -- kalau salah satu/keduanya sudah pernah dihapus/diganti
nama, service itu otomatis dilewati (bukan error) dan seed-nya jadi
sebagian atau kosong; ini SAMA PERSIS efeknya dengan perilaku lama
(service yang tidak ada tidak pernah cocok dengan nama hardcode itu juga).
"""

import json

from database import get_conn

_SEED_NAMA = ("Dry Cut", "Cut & Wash")


def migrasi_bonus_service():
    with get_conn() as conn:
        _migrasi_acuan(conn, "bonus_service_acuan_service_ids")
        _migrasi_acuan(conn, "uang_harian_acuan_service_ids")


def _migrasi_acuan(conn, key):
    existing = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if existing is not None:
        return  # sudah pernah dimigrasikan / sudah pernah diisi Owner, jangan menimpa

    placeholder = ", ".join("?" for _ in _SEED_NAMA)
    rows = conn.execute(
        f"SELECT id FROM services WHERE nama IN ({placeholder})", _SEED_NAMA,
    ).fetchall()
    service_ids = [r["id"] for r in rows]
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(service_ids)))
