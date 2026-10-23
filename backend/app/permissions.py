"""
permissions.py — Hak Akses User (dinamis, disimpan di PostgreSQL)
=============================================================================
REVISI BESAR (permintaan Owner, Oktober 2026): sistem "Hak Akses Menu" 3
level (Tidak Ada Akses/Baca/Baca & Edit) DIHAPUS TOTAL -- diganti SATU
saklar boolean per unit ("boleh akses atau tidak", tidak ada lagi
pembedaan baca vs tulis). Konsep Role "Admin" BAWAAN juga DIHAPUS -- tidak
ada lagi role 'staff' yang otomatis punya izin tanpa Role eksplisit. SETIAP
akun 'staff' WAJIB punya Role (lihat user_roles_db.py) -- nama bebas
("Staff", "Kasir", atau apa pun), dibuat Owner sendiri, checklist izinnya
100% ditentukan Owner lewat pohon PERMISSION_TREE di bawah. Role "Staff"
dibuat otomatis oleh migrasi (migrasi_role_staff_default(), dipanggil dari
main.py) untuk tiap tenant, membawa persis nilai izin yang SEBELUMNYA
tersimpan di tabel `settings` sebagai Role "Admin" lama -- supaya tidak
ada akun yang mendadak terkunci begitu revisi ini di-deploy. Setelah
migrasi, SETIAP akun 'staff' (termasuk yang dulu role_id NULL/"Admin")
WAJIB punya users.custom_role_id terisi -- lihat migrasi_assign_role_staff_
default_ke_user_lama() di user_roles_db.py.

STRUKTUR: USER -> ROLE -> HAK AKSES. Role 'staff' (TIDAK ADA LAGI label UI
"Admin" -- itu cuma nama SALAH SATU Role yang kebetulan dibuat migrasi,
bukan konsep istimewa) duduk di antara 'admin' ("Owner", akses penuh TANPA
batasan apa pun, TIDAK PERNAH disentuh revisi ini) dan 'barber' (TIDAK
PERNAH disentuh revisi ini -- tetap hardcoded seperti sebelumnya, lihat
nav.js/auth.py).

PERMISSION_TREE (katalog baru): {node_key: {"label", "parent", "roots": bool}}
-- setiap node punya SATU key izin_* (sama persis nama variabelnya),
`parent` = node_key induknya (None = menu paling atas) untuk kebutuhan UI
dropdown (anak-anak HANYA tampil kalau induknya sudah dicentang, lihat
pages/pengaturan.js & pages/superadmin.js yang me-render pohon ini).
Beberapa izin LINTAS-MENU (Download Laporan PDF, dst) SENGAJA tidak punya
`parent` (None) DAN tidak pernah jadi induk siapa pun -- ditampilkan
sejajar di luar pohon menu, bukan di dalam satu menu tertentu (lihat
CROSS_CUTTING_KEYS).

"Hak Akses User" (mengatur Role orang lain) dan "Billing" TETAP permanen
Owner-only, TIDAK PERNAH masuk PERMISSION_TREE -- tidak ada Role manapun
yang bisa diberi akses ke situ.

Owner ('admin') SELALU lolos setiap pengecekan izin di sini tanpa syarat
(lihat auth.require_permission) -- seluruh katalog di bawah HANYA berlaku
untuk role 'staff'.
"""

import json

import database as db

# ---------------------------------------------------------------------------
# PERMISSION_TREE -- katalog tunggal. Setiap entri: key -> (label, parent).
# `parent=None` DAN tidak jadi induk node lain = root menu ATAU izin
# lintas-menu (lihat CROSS_CUTTING_KEYS di bawah untuk daftar yang mana).
# Urutan di dict ini DIPAKAI APA ADANYA sebagai urutan tampil di UI.
# ---------------------------------------------------------------------------
PERMISSION_TREE = {
    # ---- Dashboard ----
    "izin_dashboard_lihat": ("Dashboard", None),
    "izin_dashboard_nilai_service": ("Nilai Service", "izin_dashboard_lihat"),
    "izin_dashboard_jumlah_service": ("Jumlah Service", "izin_dashboard_lihat"),
    "izin_dashboard_pengeluaran_toko": ("Pengeluaran Toko", "izin_dashboard_lihat"),
    "izin_dashboard_penjualan_produk": ("Penjualan Produk", "izin_dashboard_lihat"),
    "izin_dashboard_total_komisi": ("Total Komisi Barber", "izin_dashboard_lihat"),
    "izin_dashboard_total_tips": ("Total Tips", "izin_dashboard_lihat"),
    "izin_dashboard_uang_harian": ("Uang Harian", "izin_dashboard_lihat"),
    "izin_dashboard_bonus_customer": ("Bonus Customer", "izin_dashboard_lihat"),
    "izin_dashboard_laba_kotor": ("Laba Kotor Toko", "izin_dashboard_lihat"),

    # ---- Input Data ----
    "izin_input_data_lihat": ("Input Data", None),
    "izin_input_data_kelola": ("Input Barber (Transaksi & Tandai Libur, termasuk Koreksi)", "izin_input_data_lihat"),
    "izin_input_data_hapus": ("Hapus Transaksi", "izin_input_data_kelola"),
    "izin_manual_customer": ("Manual Customer (Waiting List / Booking Jalan)", "izin_input_data_lihat"),
    "izin_data_non_barber_kelola": ("Data Non-Barber (Kasir/OB/Kru -- input gaji harian)", "izin_input_data_lihat"),
    "izin_data_non_barber_hapus": ("Hapus Data Non-Barber", "izin_data_non_barber_kelola"),

    # ---- Rekap ----
    "izin_rekap_lihat": ("Rekap", None),
    "izin_rekap_transaksi": ("Transaksi", "izin_rekap_lihat"),
    "izin_rekap_bulanan": ("Bulanan", "izin_rekap_lihat"),
    "izin_rekap_pengeluaran": ("Pengeluaran (dari tab Rekap)", "izin_rekap_lihat"),

    # ---- Absensi ----
    "izin_absensi_lihat": ("Absensi", None),
    "izin_absensi_dashboard": ("Dashboard Ringkasan", "izin_absensi_lihat"),
    "izin_absensi_limit": ("Sisa Limit Bulan Ini", "izin_absensi_lihat"),
    "izin_absensi_pengaturan": ("Pengaturan Absensi (jam kerja, radius, lokasi toko)", "izin_absensi_lihat"),
    "izin_absensi_koreksi": ("Approve/Reject Koreksi Absensi", "izin_absensi_lihat"),
    "izin_absensi_export_excel": ("Export Excel Riwayat Absensi", "izin_absensi_lihat"),

    # ---- Produk ----
    "izin_produk_lihat": ("Produk", None),
    "izin_produk_kelola": ("Tambah & Kelola Daftar Produk", "izin_produk_lihat"),
    "izin_produk_mutasi": ("Restock / Jual / Tester", "izin_produk_lihat"),
    "izin_produk_riwayat_mutasi": ("Riwayat Mutasi", "izin_produk_lihat"),
    "izin_produk_hapus": ("Nonaktifkan Produk / Hapus Mutasi", "izin_produk_lihat"),

    # ---- Pengeluaran ----
    "izin_pengeluaran_lihat": ("Pengeluaran", None),
    "izin_pengeluaran_kelola": ("Tambah & Kelola Pengeluaran", "izin_pengeluaran_lihat"),
    "izin_pengeluaran_hapus": ("Hapus Pengeluaran", "izin_pengeluaran_kelola"),

    # ---- Pemasukan ----
    "izin_pemasukan_lihat": ("Pemasukan", None),
    "izin_pemasukan_kelola": ("Tambah & Kelola Pemasukan", "izin_pemasukan_lihat"),
    "izin_pemasukan_hapus": ("Hapus Pemasukan", "izin_pemasukan_kelola"),

    # ---- Uang Kas ----
    "izin_uang_kas_lihat": ("Uang Kas", None),
    "izin_uang_kas_kelola": ("Kelola Penyesuaian Kas (saldo awal, penyesuaian)", "izin_uang_kas_lihat"),
    "izin_uang_kas_hapus": ("Hapus Penyesuaian Kas", "izin_uang_kas_kelola"),

    # ---- Riwayat Transaksi (Payment Gateway) -- label diperjelas supaya
    # tidak tertukar dengan Rekap > Transaksi (permintaan Owner) ----
    "izin_riwayat_transaksi_lihat": ("Riwayat Transaksi (Payment Gateway)", None),
    "izin_riwayat_transaksi": ("Cek Ulang Status Pembayaran Gateway", "izin_riwayat_transaksi_lihat"),

    # ---- Settlement Faspay ----
    "izin_settlement_faspay_lihat": ("Settlement Faspay", None),
    "izin_settlement_faspay": ("Submit Closing Harian", "izin_settlement_faspay_lihat"),

    # ---- Kasbon (tampilan admin -- lihat semua karyawan) ----
    "izin_kasbon_lihat": ("Kasbon", None),
    "izin_kasbon": ("Tambah & Kelola Kasbon (buat kasbon baru, proses pembayaran)", "izin_kasbon_lihat"),
    "izin_kasbon_hapus": ("Hapus Kasbon", "izin_kasbon"),

    # ---- Komisi ----
    "izin_komisi_lihat": ("Komisi", None),
    "izin_komisi": ("Tambah & Kelola Penyesuaian Komisi", "izin_komisi_lihat"),
    "izin_komisi_hapus": ("Hapus Penyesuaian Komisi", "izin_komisi"),

    # ---- Slip Gaji ----
    "izin_slip_gaji_lihat": ("Slip Gaji", None),
    "izin_slip_gaji": ("Generate & Kelola Slip Gaji (termasuk Tandai/Batalkan Sudah Dibayar)", "izin_slip_gaji_lihat"),
    "izin_slip_gaji_hapus": ("Hapus Slip Gaji", "izin_slip_gaji"),

    # ---- Reimburse (tampilan admin) ----
    "izin_reimburse_lihat": ("Reimburse", None),
    "izin_reimburse": ("Setujui / Tolak Klaim Reimburse", "izin_reimburse_lihat"),
    "izin_reimburse_tambah": ("Tambah Klaim (atas nama barber)", "izin_reimburse_lihat"),
    "izin_reimburse_hapus": ("Hapus Klaim Reimburse", "izin_reimburse"),

    # ---- Izin & Cuti (tampilan admin) ----
    "izin_cuti_karyawan_lihat": ("Izin & Cuti", None),
    "izin_cuti_karyawan": ("Setujui / Tolak Pengajuan", "izin_cuti_karyawan_lihat"),
    "izin_cuti_karyawan_hapus": ("Hapus / Batalkan Pengajuan", "izin_cuti_karyawan"),

    # ---- Booking ----
    "izin_booking_lihat": ("Booking", None),
    "izin_booking_list": ("Booking List", "izin_booking_lihat"),
    "izin_booking_hapus": ("Hapus Booking Permanen", "izin_booking_list"),
    "izin_booking_calendar": ("Calendar", "izin_booking_lihat"),
    "izin_booking_operating_hours": ("Operating Hours", "izin_booking_lihat"),
    "izin_booking_barber_holiday": ("Barber Holiday", "izin_booking_lihat"),
    "izin_booking_closed_slot": ("Closed Slot", "izin_booking_lihat"),
    "izin_booking_payment_settings": ("Payment Settings", "izin_booking_lihat"),
    "izin_booking_settings": ("Booking Settings", "izin_booking_lihat"),
    "izin_booking_website_content": ("Website Content", "izin_booking_lihat"),

    # ---- WhatsApp (sebelumnya hardcoded Owner-only, SEKARANG dibuka) ----
    "izin_whatsapp_lihat": ("WhatsApp", None),
    "izin_whatsapp_notifikasi_booking": ("Notifikasi Booking", "izin_whatsapp_lihat"),
    "izin_whatsapp_reminder_absensi": ("Reminder Absensi", "izin_whatsapp_lihat"),

    # ---- Setting (sebelumnya 8 tab hardcoded Owner-only, SEKARANG dibuka
    # SEMUA kecuali "Hak Akses User" -- lihat catatan modul. "Profil" TIDAK
    # masuk di sini sama sekali -- bukan izin yang diberikan ke orang lain,
    # setiap akun otomatis punya akses ke Profil-nya sendiri.) ----
    "izin_setting_lihat": ("Setting", None),
    "izin_setting_branding": ("Branding", "izin_setting_lihat"),
    "izin_setting_tampilan": ("Tampilan", "izin_setting_lihat"),
    "izin_setting_komisi": ("Komisi", "izin_setting_lihat"),
    "izin_setting_bonus_service": ("Bonus Service", "izin_setting_lihat"),
    "izin_setting_uang_harian": ("Uang Harian", "izin_setting_lihat"),
    "izin_setting_karyawan": ("Karyawan (tambah/edit Barber & Non-Barber, gaji)", "izin_setting_lihat"),
    "izin_setting_layanan": ("Layanan (Service & harga)", "izin_setting_lihat"),
    "izin_setting_subscription": ("Subscription (lihat status paket -- read-only)", "izin_setting_lihat"),
    "izin_setting_user": ("User (tambah/edit akun Kasir/Staff/Barber)", "izin_setting_lihat"),
    "izin_user_tambah": ("Membuat User Barber", "izin_setting_user"),
    "izin_user_hapus": ("Menonaktifkan/Mengaktifkan/Menghapus Permanen User Barber", "izin_setting_user"),
    "izin_user_ganti_password": ("Mengubah Password User Barber", "izin_setting_user"),
    "izin_setting_backup": ("Backup", "izin_setting_lihat"),
    "izin_backup_export": ("Export Database", "izin_setting_backup"),
    "izin_backup_import": ("Import Database", "izin_setting_backup"),
    # "Hak Akses User" SENGAJA TIDAK ADA DI SINI -- permanen Owner-only.

    # ---- Lintas-menu (sejajar, TIDAK ada di dalam satu menu manapun --
    # lihat CROSS_CUTTING_KEYS) ----
    "izin_laporan_pdf": ("Download Laporan PDF (semua modul)", None),
}

# Key yang SENGAJA tidak masuk pohon menu manapun -- ditampilkan sejajar/
# terpisah di UI (lihat docstring modul).
CROSS_CUTTING_KEYS = {"izin_laporan_pdf"}

PERMISSION_KEYS = set(PERMISSION_TREE.keys())


def tree_children(parent_key) -> list:
    """Daftar key yang `parent`-nya persis `parent_key`, urutan sesuai
    PERMISSION_TREE. `parent_key=None` -> seluruh root (menu utama +
    izin lintas-menu)."""
    return [k for k, (_label, parent) in PERMISSION_TREE.items() if parent == parent_key]


def tree_roots() -> list:
    """Root menu SAJA (bukan izin lintas-menu) -- akar pohon dropdown di UI."""
    return [k for k in tree_children(None) if k not in CROSS_CUTTING_KEYS]


def _descendants(key) -> set:
    hasil = set()
    for anak in tree_children(key):
        hasil.add(anak)
        hasil |= _descendants(anak)
    return hasil


def get_all(tenant_id=None, role_id=None) -> dict:
    """{key: bool} untuk SELURUH permission di PERMISSION_TREE.

    FITUR Role (diminta Owner -- REVISI besar: TIDAK ADA LAGI Role "Admin"
    bawaan/default, lihat docstring modul): `role_id` WAJIB diisi untuk
    SEMUA akun 'staff' (lihat user_roles_db.py) -- dibaca dari
    user_role_permissions (fail-CLOSED, key yang tidak ada di sana =
    False, TIDAK PERNAH pakai default apa pun -- Role baru sengaja mulai
    kosong). `role_id=None` HANYA dipakai jalur internal/migrasi (mis.
    membaca nilai lama dari tabel `settings` saat memindahkan Role "Admin"
    lama ke Role "Staff" baru, lihat migrasi_role_staff_default()) --
    TIDAK PERNAH dipakai lagi oleh request login staff biasa begitu
    migrasi selesai (auth.require_permission SELALU mengisi role_id dari
    users.custom_role_id, yang SEKARANG wajib terisi untuk role 'staff').

    SATU query (get_all_settings() untuk jalur role_id=None, atau SATU
    query ke user_role_permissions untuk role_id terisi) -- bukan satu
    query per key -- karena fungsi ini dipanggil di SETIAP pengecekan
    require_permission()/has(), termasuk untuk request yang datang
    beruntun.

    FONDASI Multi-Tenant Phase 1: `tenant_id` opsional, HANYA relevan
    untuk jalur role_id=None (baca tabel `settings` lama, dipakai migrasi)."""
    if role_id is not None:
        import user_roles_db  # import lokal: hindari import siklik (user_roles_db.py -> database.py)
        aktif = user_roles_db.get_role_permission_keys(role_id)
        return {key: (key in aktif) for key in PERMISSION_TREE}
    semua = db.get_all_settings(tenant_id=tenant_id)
    return {key: (semua.get(key) == "1") for key in PERMISSION_TREE}


def set_bulk(data: dict, tenant_id=None, role_id=None) -> dict:
    """Timpa permission yang DIKIRIM saja (key yang tidak dikirim tetap
    seperti sebelumnya) -- validasi key dulu supaya tidak ada key sembarang
    ikut tersimpan. `role_id` WAJIB diisi untuk pemakaian normal (lihat
    get_all())."""
    tidak_dikenal = set(data.keys()) - PERMISSION_KEYS
    if tidak_dikenal:
        raise ValueError(f"Permission tidak dikenal: {', '.join(sorted(tidak_dikenal))}")
    if role_id is not None:
        import user_roles_db  # import lokal: hindari import siklik
        aktif = user_roles_db.get_role_permission_keys(role_id)
        for key, nilai in data.items():
            if nilai:
                aktif.add(key)
            else:
                aktif.discard(key)
                # PERBAIKAN (konsistensi pohon): kalau sebuah node induk
                # dimatikan, SELURUH keturunannya ikut dimatikan juga --
                # mencegah state "anak aktif tapi induknya tidak" yang
                # tidak mungkin direpresentasikan di UI dropdown (anak
                # hanya muncul kalau induk dicentang).
                aktif -= _descendants(key)
        user_roles_db.set_role_permission_keys(role_id, aktif)
        return get_all(role_id=role_id)
    bersih = {key: ("1" if bool(v) else "0") for key, v in data.items()}
    if bersih:
        db.set_settings_bulk(bersih, tenant_id=tenant_id)
    return get_all(tenant_id=tenant_id)


def has(key: str, tenant_id=None, role_id=None) -> bool:
    if key not in PERMISSION_KEYS:
        raise ValueError(f"Permission tidak dikenal: {key}")
    return get_all(tenant_id=tenant_id, role_id=role_id).get(key, False)


def has_any(keys, tenant_id=None, role_id=None) -> bool:
    izin = get_all(tenant_id=tenant_id, role_id=role_id)
    return any(izin.get(k, False) for k in keys)
