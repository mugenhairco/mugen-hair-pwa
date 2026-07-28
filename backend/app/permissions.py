"""
permissions.py — Hak Akses Admin (dinamis, disimpan di PostgreSQL)
=============================================================================
Role baru 'staff' (label UI: "Admin") duduk di antara 'admin' (label UI:
"Owner", akses penuh TANPA batasan apa pun) dan 'barber'. Apa yang boleh
dilakukan role 'staff' TIDAK di-hardcode di kode -- Owner mengatur lewat
menu Setting > Hak Akses Admin (lihat routers/pengaturan.py endpoint
/hak-akses-admin), disimpan sebagai baris di tabel `settings` yang sudah
ada (key-value generik, sudah dialek-netral SQLite/PostgreSQL lewat
db_compat.py -- TIDAK perlu tabel baru).

Owner ('admin') SELALU lolos setiap pengecekan izin di sini tanpa syarat
(lihat auth.require_permission) -- daftar & default di bawah ini HANYA
berlaku untuk role 'staff'.
"""

import json

import database as db

# (key, grup, label, default) -- default HANYA prasangka awal sebelum Owner
# pernah mengatur apa pun; begitu Owner menyimpan lewat menu Hak Akses
# Admin, nilai tersimpan menang selamanya (lihat get_all()).
PERMISSION_DEFS = [
    # ---- Dashboard: kartu apa saja yang boleh dilihat 'staff' ----
    ("izin_dashboard_nilai_service", "dashboard", "Nilai Service", True),
    ("izin_dashboard_jumlah_service", "dashboard", "Jumlah Service", True),
    ("izin_dashboard_pengeluaran_toko", "dashboard", "Pengeluaran Toko", True),
    ("izin_dashboard_penjualan_produk", "dashboard", "Penjualan Produk", True),
    ("izin_dashboard_total_komisi", "dashboard", "Total Komisi Barber", False),
    ("izin_dashboard_total_tips", "dashboard", "Total Tips", False),
    ("izin_dashboard_uang_harian", "dashboard", "Uang Harian", False),
    ("izin_dashboard_bonus_customer", "dashboard", "Bonus Customer", False),
    ("izin_dashboard_laba_kotor", "dashboard", "Laba Kotor Toko", False),
    # ---- User: HANYA berlaku untuk mengelola user ber-role Barber ----
    ("izin_user_tambah", "user", "Membuat User Barber", False),
    ("izin_user_hapus", "user", "Menghapus (menonaktifkan) User Barber", False),
    ("izin_user_ganti_password", "user", "Mengubah Password User Barber", False),
    # REVISI (kedua): grup "Pengeluaran" DIHAPUS dari sini -- menu
    # Pengeluaran tidak lagi memakai sistem izin sama sekali, 'staff' (Admin)
    # selalu punya akses PENUH sama persis seperti Owner (lihat
    # routers/pengeluaran.py).
    # ---- Backup ----
    ("izin_backup_export", "backup", "Export Database", False),
    ("izin_backup_import", "backup", "Import Database", False),
    # ---- Laporan ----
    ("izin_laporan_pdf", "laporan", "Download Laporan PDF", False),
    # ---- Karyawan (Modul Karyawan, Fase 1: Slip Gaji, Fase 2: Kasbon) ----
    ("izin_slip_gaji", "karyawan", "Kelola Slip Gaji", False),
    ("izin_kasbon", "karyawan", "Kelola Kasbon Karyawan", False),
    ("izin_komisi", "karyawan", "Kelola Penyesuaian Komisi", False),
    # ---- Setting: akses ke tab-nya sendiri ----
    ("izin_setting_identitas", "setting", "Tab Identitas Barbershop", False),
    ("izin_setting_tampilan", "setting", "Tab Tampilan", False),
    ("izin_setting_user", "setting", "Tab User", False),
    ("izin_setting_backup", "setting", "Tab Backup", False),
]

PERMISSION_KEYS = {key for key, *_ in PERMISSION_DEFS}


def get_all() -> dict:
    """{key: bool} untuk SELURUH permission, dengan default dari
    PERMISSION_DEFS kalau Owner belum pernah mengaturnya sama sekali.
    SATU query (get_all_settings(), sudah ada sejak Tahap 2) -- bukan satu
    query per key -- karena fungsi ini dipanggil di SETIAP pengecekan
    require_permission()/has(), termasuk untuk request yang datang beruntun."""
    semua = db.get_all_settings()
    hasil = {}
    for key, _grup, _label, default in PERMISSION_DEFS:
        nilai = semua.get(key)
        hasil[key] = (nilai == "1") if nilai is not None else default
    return hasil


def set_bulk(data: dict) -> dict:
    """Timpa permission yang DIKIRIM saja (key yang tidak dikirim tetap
    seperti sebelumnya) -- validasi key dulu supaya tidak ada key sembarang
    ikut tersimpan ke tabel settings."""
    tidak_dikenal = set(data.keys()) - PERMISSION_KEYS
    if tidak_dikenal:
        raise ValueError(f"Permission tidak dikenal: {', '.join(sorted(tidak_dikenal))}")
    bersih = {key: ("1" if bool(v) else "0") for key, v in data.items()}
    if bersih:
        db.set_settings_bulk(bersih)
    return get_all()


def has(key: str) -> bool:
    if key not in PERMISSION_KEYS:
        raise ValueError(f"Permission tidak dikenal: {key}")
    return get_all().get(key, False)


def has_any(keys) -> bool:
    izin = get_all()
    return any(izin.get(k, False) for k in keys)
