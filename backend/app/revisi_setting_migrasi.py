"""
revisi_setting_migrasi.py — Migrasi untuk REVISI Struktur Setting (Final):
Tab Komisi disederhanakan, Harga Modal per-service menggantikan Potongan
Modal Chemical, Target Uang Harian jadi bisa diatur bebas (tidak hardcode 3).
=============================================================================
File ini SENGAJA dipisah dari database.py (pola yang sama seperti
revisi_bonus_migrasi.py/bonus_service_migrasi.py di revisi-revisi
sebelumnya) — database.py hanya disentuh untuk rumus komisi/uang harian
itu sendiri (lihat perubahan hitung_komisi_service/hitung_uang_harian_*
di database.py), TIDAK untuk migrasi data.

Dua migrasi idempotent, aman dipanggil berulang kali, TIDAK PERNAH
menghapus/menimpa data yang sudah ada:

1. Setting baru `uang_harian_target_service_harian` (default "3", SAMA
   PERSIS dengan angka yang sebelumnya hardcode di
   hitung_uang_harian_per_hari/hitung_uang_harian_bulan) — supaya Owner
   bisa mengubahnya lewat Setting > Uang Harian tanpa nominal yang SEDANG
   berjalan berubah sedikit pun sampai Owner sengaja menggantinya.

2. Backfill `services.modal` dari `potongan_modal_chemical` (global,
   SEBELUM revisi ini) — KHUSUS untuk service yang SEBELUM revisi ini
   memang dikenai potongan chemical (menurut aturan lama:
   nama TIDAK termasuk SERVICE_TANPA_POTONGAN di database.py) DAN modal
   service itu masih 0 (belum pernah diisi Owner untuk keperluan lain).
   Setelah backfill ini, hitung_komisi_service() yang baru (Harga - Modal)
   x Persentase akan menghasilkan angka KOMISI YANG SAMA PERSIS seperti
   rumus lama untuk service-service tsb -- tidak ada perubahan nominal
   komisi yang sedang berjalan akibat migrasi ini.
   Service yang modal-nya SUDAH diisi Owner sebelumnya (untuk pencatatan,
   dulu tidak memengaruhi komisi sama sekali) TIDAK disentuh -- nilai itu
   mulai berlaku sebagai biaya modal komisi PERSIS sesuai instruksi revisi
   ini ("Jika diisi, digunakan sebagai biaya modal service").
   Dijaga idempotent lewat setting penanda `migrasi_modal_komisi_selesai`
   (BUKAN dicek ulang dari nilai modal==0, supaya kalau Owner nanti sengaja
   mengembalikan modal suatu service ke 0, migrasi ini tidak menimpanya
   lagi di restart berikutnya).
"""

from database import get_conn, DEFAULT_SETTINGS, SERVICE_TANPA_POTONGAN


def migrasi_revisi_setting():
    with get_conn() as conn:
        _migrasi_target_uang_harian(conn)
        _migrasi_modal_dari_chemical(conn)


def _migrasi_target_uang_harian(conn):
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('uang_harian_target_service_harian', '3')"
    )


def _migrasi_modal_dari_chemical(conn):
    sudah = conn.execute(
        "SELECT 1 FROM settings WHERE key = 'migrasi_modal_komisi_selesai'"
    ).fetchone()
    if sudah:
        return  # sudah pernah dimigrasikan, jangan sentuh lagi (modal boleh sudah diubah Owner)

    row = conn.execute("SELECT value FROM settings WHERE key = 'potongan_modal_chemical'").fetchone()
    nilai_potongan = row["value"] if row else DEFAULT_SETTINGS.get("potongan_modal_chemical", "0")
    try:
        potongan = int(float(nilai_potongan))
    except (TypeError, ValueError):
        potongan = 0

    services = conn.execute("SELECT id, nama, modal FROM services").fetchall()
    for s in services:
        pernah_kena_potongan = s["nama"] not in SERVICE_TANPA_POTONGAN
        belum_pernah_diisi = (s["modal"] or 0) == 0
        if pernah_kena_potongan and belum_pernah_diisi and potongan > 0:
            conn.execute("UPDATE services SET modal = ? WHERE id = ?", (potongan, s["id"]))

    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('migrasi_modal_komisi_selesai', '1')"
    )
