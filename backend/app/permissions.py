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
    ("izin_user_hapus", "user", "Menonaktifkan/Mengaktifkan/Menghapus Permanen User Barber", False),
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
    ("izin_reimburse", "karyawan", "Kelola Reimburse", False),
    ("izin_cuti_karyawan", "karyawan", "Kelola Izin & Cuti", False),
    # ---- Setting: akses ke tab-nya sendiri ----
    ("izin_setting_identitas", "setting", "Tab Identitas Barbershop", False),
    ("izin_setting_tampilan", "setting", "Tab Tampilan", False),
    ("izin_setting_user", "setting", "Tab User", False),
    ("izin_setting_backup", "setting", "Tab Backup", False),
    # FONDASI Multi-Tenant Phase 2.2: Tab Branding (nama, logo, favicon,
    # warna, tagline, alamat, whatsapp, email, website) -- permission
    # TERPISAH dari izin_setting_identitas supaya Owner bisa memberi izin
    # granular (mis. staff boleh atur Branding tapi tidak boleh ke tab
    # Identitas lama, atau sebaliknya) sesuai instruksi "Admin dapat
    # mengubah Branding jika memiliki izin".
    ("izin_setting_branding", "setting", "Tab Branding", False),
    # ---- Absensi (modul GPS Check In/Out) ----
    # Lihat spesifikasi (chat) untuk pembagian peran: Owner ('admin') akses
    # penuh TANPA syarat (seperti biasa). 'staff' (Admin) SELALU boleh
    # MELIHAT (dashboard/riwayat/laporan Absensi -- tidak digerbang
    # permission apa pun, sama seperti pengeluaran.py), tapi MENGUBAH
    # Pengaturan Absensi (jam kerja/radius/lokasi toko) wajib izin eksplisit
    # ini dari Owner (lihat require_permission("izin_absensi_pengaturan")
    # di routers/attendance.py).
    ("izin_absensi_pengaturan", "absensi", "Kelola Pengaturan Absensi", False),
]

PERMISSION_KEYS = {key for key, *_ in PERMISSION_DEFS}


def get_all(tenant_id=None) -> dict:
    """{key: bool} untuk SELURUH permission, dengan default dari
    PERMISSION_DEFS kalau Owner belum pernah mengaturnya sama sekali.
    SATU query (get_all_settings(), sudah ada sejak Tahap 2) -- bukan satu
    query per key -- karena fungsi ini dipanggil di SETIAP pengecekan
    require_permission()/has(), termasuk untuk request yang datang beruntun.

    FONDASI Multi-Tenant Phase 1: `tenant_id` opsional (lihat catatan
    db.get_setting()/_kunci_tenant()) -- Hak Akses Admin adalah pengaturan
    PER TOKO (Owner Tenant A tidak boleh mengatur Admin Tenant B), jadi
    endpoint ber-login WAJIB mengisi ini (lihat auth.require_permission)."""
    semua = db.get_all_settings(tenant_id=tenant_id)
    hasil = {}
    for key, _grup, _label, default in PERMISSION_DEFS:
        nilai = semua.get(key)
        hasil[key] = (nilai == "1") if nilai is not None else default
    return hasil


def set_bulk(data: dict, tenant_id=None) -> dict:
    """Timpa permission yang DIKIRIM saja (key yang tidak dikirim tetap
    seperti sebelumnya) -- validasi key dulu supaya tidak ada key sembarang
    ikut tersimpan ke tabel settings."""
    tidak_dikenal = set(data.keys()) - PERMISSION_KEYS
    if tidak_dikenal:
        raise ValueError(f"Permission tidak dikenal: {', '.join(sorted(tidak_dikenal))}")
    bersih = {key: ("1" if bool(v) else "0") for key, v in data.items()}
    if bersih:
        db.set_settings_bulk(bersih, tenant_id=tenant_id)
    return get_all(tenant_id=tenant_id)


def has(key: str, tenant_id=None) -> bool:
    if key not in PERMISSION_KEYS:
        raise ValueError(f"Permission tidak dikenal: {key}")
    return get_all(tenant_id=tenant_id).get(key, False)


def has_any(keys, tenant_id=None) -> bool:
    izin = get_all(tenant_id=tenant_id)
    return any(izin.get(k, False) for k in keys)
