"""
pengaturan_migrasi.py — Migrasi skema TAHAP 10 (Setting)
==========================================================
Terpisah dari database.py (sesuai instruksi: jangan mengubah database.py
kecuali benar-benar diperlukan). Dua hal yang dilakukan, keduanya idempotent
dan TIDAK PERNAH menghapus data lama:

1. Tabel `settings` SUDAH ADA sejak Tahap 2 (key-value generik) — jadi
   Identitas Barbershop (nama, alamat, whatsapp, email, instagram, jam
   operasional, nama file logo) CUKUP disimpan sebagai key baru di situ,
   TANPA perlu tabel baru. Fungsi ini hanya mengisi key-key itu dengan nilai
   default kalau belum ada (INSERT OR IGNORE, tidak pernah menimpa nilai
   yang sudah diubah admin).
2. Tabel `services` mendapat kolom baru `modal` (dibutuhkan field "Modal"
   di CRUD Layanan Tahap 10) lewat ALTER TABLE. Kolom ini TIDAK dipakai di
   `hitung_komisi_service` / logika komisi manapun di database.py — jadi
   menambahkannya tidak mengubah satu pun hasil perhitungan yang sudah ada.
"""

from database import get_conn

IDENTITAS_DEFAULT = {
    "nama_barbershop": "MUGEN Hair Co.",
    "alamat": "",
    "whatsapp": "",
    "email": "",
    "instagram": "",
    "jam_operasional": "",
    "logo_filename": "",
}


def migrasi_pengaturan():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(services)").fetchall()]
        if "modal" not in kolom:
            conn.execute("ALTER TABLE services ADD COLUMN modal INTEGER NOT NULL DEFAULT 0")

        for key, value in IDENTITAS_DEFAULT.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
