"""
permissions.py — Hak Akses User (dinamis, disimpan di PostgreSQL)
=============================================================================
STRUKTUR: USER -> ROLE -> HAK AKSES. Role 'staff' (label UI: "Admin") duduk
di antara 'admin' (label UI: "Owner", akses penuh TANPA batasan apa pun) dan
'barber'. Apa yang boleh dilakukan role 'staff' TIDAK di-hardcode di kode --
Owner mengatur lewat menu Setting > Hak Akses User (lihat
routers/pengaturan.py), yang SEKARANG menampilkan SATU tabel Role berisi
Role bawaan "Admin" + seluruh Role Custom (lihat user_roles_db.py) -- BUKAN
lagi dua konsep terpisah. Role "Admin" adalah Role BAWAAN/default (tidak
bisa diganti nama/dihapus), izinnya disimpan sebagai baris di tabel
`settings` yang sudah ada (key-value generik, sudah dialek-netral
SQLite/PostgreSQL lewat db_compat.py -- endpoint /hak-akses-admin, URL path
TIDAK diubah, murni label UI) -- dipakai SEMUA akun staff yang Role-nya
"Admin" (belum memilih Role Custom lain).

FITUR Role Custom (diminta Owner): Owner bisa membuat Role bernama sendiri
(mis. "Kasir", "Supervisor" -- lihat user_roles_db.py) dengan checklist
izin_* SENDIRI dari katalog yang SAMA persis di bawah ini (TIDAK ADA sistem
izin baru, murni Role tambahan di luar "Admin"/"Owner"/"Barber"), dipilih
LANGSUNG sebagai Role saat membuat/mengedit User (tab User) lewat
`users.custom_role_id` -- BUKAN "ditempelkan ke Admin", akun ber-Role Kasir
memakai HANYA izin Role Kasir, tidak pernah gabungan dengan Role "Admin".
Parameter `role_id` OPSIONAL di get_all()/has()/has_any()/set_bulk() di
bawah -- diisi = baca/tulis checklist Role Custom itu, None (default, JUGA
berlaku untuk staff ber-Role "Admin") = pakai set izin Role "Admin" di atas,
100% kompatibel mundur.

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
    # FITUR Koreksi Absensi: staff (Admin) SELALU boleh MELIHAT pengajuan
    # koreksi (sama seperti dashboard/riwayat Absensi lainnya), tapi
    # approve/reject wajib izin eksplisit ini -- pola sama persis
    # izin_cuti_karyawan (approval Izin & Cuti).
    ("izin_absensi_koreksi", "absensi", "Approve/Reject Koreksi Absensi", False),
    # ---- Perluasan Hak Akses Admin (diminta Owner): modul operasional
    # harian di bawah ini SEBELUMNYA staff selalu akses PENUH tanpa syarat
    # apa pun (require_owner_or_staff polos, tidak ada permission sama
    # sekali) -- SEKARANG bisa diatur granular Owner, dipecah "Kelola"
    # (tambah/edit, risiko rendah) vs "Hapus" (destruktif, risiko lebih
    # tinggi) per modul, pola SAMA seperti izin_user_tambah vs izin_user_
    # hapus. Default TRUE untuk SEMUA (bukan False seperti kebanyakan
    # permission granular lain di atas) -- SENGAJA, supaya staff yang
    # SUDAH memakai modul ini sehari-hari TIDAK tiba-tiba terkunci begitu
    # perubahan ini deploy; Owner tetap bebas mematikan kapan pun lewat
    # Setting > Hak Akses Admin. Endpoint GET (lihat data) TIDAK ikut
    # digerbang -- staff SELALU boleh melihat, sama seperti pola karyawan
    # (kasbon.py dkk) yang sudah ada.
    # ---- Booking ----
    ("izin_booking_kelola", "booking", "Kelola Booking (verifikasi pembayaran, closed slot, toko libur)", True),
    ("izin_booking_batalkan", "booking", "Batalkan Booking", True),
    # DIPISAH dari izin_booking_batalkan (permintaan eksplisit Owner):
    # Batalkan otomatis mengirim WhatsApp pembatalan ke customer, Hapus
    # Permanen TIDAK -- dua konsekuensi berbeda, jadi dua izin berbeda,
    # pola SAMA seperti izin_produk_kelola vs izin_produk_hapus di atas /
    # izin_input_data_kelola vs izin_input_data_hapus di bawah. Default
    # FALSE (BUKAN True seperti kebanyakan izin "Perluasan Hak Akses Admin"
    # lain di sini) -- ini kemampuan BARU yang belum pernah ada sama sekali
    # untuk staff manapun sebelumnya (beda dari izin_input_data_hapus yang
    # default True karena migrasi dari kemampuan yang SUDAH ADA), jadi tidak
    # ada alasan default-nya menyala tanpa Owner sengaja mengaktifkan.
    ("izin_booking_hapus", "booking", "Hapus Booking Permanen", False),
    ("izin_booking_pengaturan", "booking", "Pengaturan Booking (jadwal, Metode Pembayaran, QRIS, URL Booking)", True),
    # ---- Produk ----
    ("izin_produk_kelola", "produk", "Kelola Produk (tambah/edit, restock/jual/tester)", True),
    ("izin_produk_hapus", "produk", "Hapus Produk & Koreksi/Hapus Mutasi", True),
    # ---- Pengeluaran ----
    ("izin_pengeluaran_kelola", "pengeluaran", "Kelola Pengeluaran (catat/edit)", True),
    ("izin_pengeluaran_hapus", "pengeluaran", "Hapus Pengeluaran", True),
    # ---- Pemasukan ----
    ("izin_pemasukan_kelola", "pemasukan", "Kelola Pemasukan (catat/edit)", True),
    ("izin_pemasukan_hapus", "pemasukan", "Hapus Pemasukan", True),
    # ---- Uang Kas ----
    ("izin_uang_kas_kelola", "uang_kas", "Kelola Uang Kas (saldo awal, penyesuaian)", True),
    ("izin_uang_kas_hapus", "uang_kas", "Hapus Penyesuaian Uang Kas", True),
    # ---- Data Non-Barber ----
    ("izin_data_non_barber_kelola", "data_non_barber", "Kelola Data Non-Barber (tambah/edit)", True),
    ("izin_data_non_barber_hapus", "data_non_barber", "Hapus Data Non-Barber", True),
    # ---- Input Data / Transaksi (termasuk hapus dari tombol Aksi di Rekap Transaksi) ----
    ("izin_input_data_kelola", "input_data", "Kelola Transaksi Harian (tambah/edit, tandai/batalkan libur)", True),
    ("izin_input_data_hapus", "input_data", "Hapus Transaksi Harian", True),
    # ---- Riwayat Transaksi (menu Keuangan > Riwayat Transaksi -- SEBELUMNYA
    # aksi "Cek Ulang"-nya menumpang izin_booking_kelola walau ini menu
    # terpisah di sidebar; sekarang key sendiri supaya Hak Akses Menu bisa
    # mengatur Booking dan Riwayat Transaksi independen, lihat MENU_DEFS) ----
    ("izin_riwayat_transaksi", "riwayat_transaksi", "Cek Ulang Status Transaksi Payment Gateway", True),
    # ---- Settlement Faspay (closing harian transaksi SNAP Advance per
    # tenant/"terminal") -- pola SAMA PERSIS Riwayat Transaksi di atas ----
    ("izin_settlement_faspay", "settlement_faspay", "Submit Settlement Faspay", False),
    # ---- Katalog KHUSUS "Hak Akses Menu" (permintaan Owner: setiap menu di
    # sidebar punya SATU level -- Tidak Ada Akses/Baca/Baca & Edit -- bukan
    # checklist per-aksi). Key "_lihat" di bawah ini MURNI gerbang MELIHAT
    # (dulu sebagian besar modul operasional -- Booking/Input Data/Produk/
    # Pengeluaran/Pemasukan/Uang Kas/Dashboard/Rekap/Absensi/Riwayat
    # Transaksi -- GET-nya SAMA SEKALI TIDAK digerbang izin apa pun, staff
    # SELALU bisa lihat; modul Karyawan -- Kasbon/Komisi/Slip Gaji/
    # Reimburse/Izin Cuti -- justru SEBALIKNYA, satu key yang sama menggerbang
    # baca DAN tulis sekaligus). Level "Baca" = key "_lihat" ini True, key
    # tulis (existing di atas) False. Level "Baca & Edit" = key "_lihat" DAN
    # SEMUA key tulis True. Level "Tidak Ada Akses" = semuanya False. Lihat
    # MENU_DEFS/get_menu_level()/set_menu_level() di bawah untuk pemetaan
    # lengkap tiap menu -> (key baca, [key tulis]) dan cara level dihitung/
    # disimpan. Default True untuk modul yang SEBELUMNYA selalu terbuka
    # (supaya tidak ada staff yang tiba-tiba terkunci begitu revisi ini
    # deploy), default False untuk modul Karyawan (SAMA seperti default key
    # tulisnya, konsisten dengan perilaku lama).
    ("izin_dashboard_lihat", "menu", "Lihat menu Dashboard", True),
    ("izin_input_data_lihat", "menu", "Lihat menu Input Data", True),
    ("izin_rekap_lihat", "menu", "Lihat menu Rekap", True),
    ("izin_slip_gaji_lihat", "menu", "Lihat menu Slip Gaji", False),
    ("izin_kasbon_lihat", "menu", "Lihat menu Kasbon", False),
    ("izin_komisi_lihat", "menu", "Lihat menu Komisi", False),
    ("izin_reimburse_lihat", "menu", "Lihat menu Reimburse", False),
    ("izin_cuti_karyawan_lihat", "menu", "Lihat menu Izin & Cuti", False),
    ("izin_absensi_lihat", "menu", "Lihat menu Absensi", True),
    ("izin_booking_lihat", "menu", "Lihat menu Booking", True),
    ("izin_riwayat_transaksi_lihat", "menu", "Lihat menu Riwayat Transaksi", True),
    ("izin_pemasukan_lihat", "menu", "Lihat menu Pemasukan", True),
    ("izin_pengeluaran_lihat", "menu", "Lihat menu Pengeluaran", True),
    ("izin_uang_kas_lihat", "menu", "Lihat menu Uang Kas", True),
    ("izin_produk_lihat", "menu", "Lihat menu Produk", True),
    ("izin_settlement_faspay_lihat", "menu", "Lihat menu Settlement Faspay", False),
]

PERMISSION_KEYS = {key for key, *_ in PERMISSION_DEFS}

# ---------------------------------------------------------------------------
# Hak Akses Menu (permintaan Owner): SATU level per menu sidebar --
# "Tidak Ada Akses" / "Baca" / "Baca & Edit" -- dibangun DI ATAS katalog
# izin_* yang sudah ada di atas (TIDAK ADA sistem penyimpanan baru, tetap
# lewat get_all()/set_bulk() yang sama, jadi Role Custom & Role "Admin"
# bawaan otomatis ikut kompatibel tanpa kode terpisah). Setting & Billing
# SENGAJA TIDAK masuk sini -- Setting sudah punya delegasi tab sendiri
# (izin_setting_*, lebih granular dari 3 level ini) dan Billing selalu
# khusus Owner (require_admin) -- di luar cakupan permintaan ini.
MENU_DEFS = {
    "dashboard": {"label": "Dashboard", "read_key": "izin_dashboard_lihat", "write_keys": []},
    "input_data": {"label": "Input Data", "read_key": "izin_input_data_lihat",
                    "write_keys": ["izin_input_data_kelola", "izin_input_data_hapus",
                                    "izin_data_non_barber_kelola", "izin_data_non_barber_hapus"]},
    "rekap": {"label": "Rekap", "read_key": "izin_rekap_lihat", "write_keys": []},
    "slip_gaji": {"label": "Slip Gaji", "read_key": "izin_slip_gaji_lihat", "write_keys": ["izin_slip_gaji"]},
    "kasbon": {"label": "Kasbon", "read_key": "izin_kasbon_lihat", "write_keys": ["izin_kasbon"]},
    "komisi": {"label": "Komisi", "read_key": "izin_komisi_lihat", "write_keys": ["izin_komisi"]},
    "reimburse": {"label": "Reimburse", "read_key": "izin_reimburse_lihat", "write_keys": ["izin_reimburse"]},
    "izin_cuti": {"label": "Izin & Cuti", "read_key": "izin_cuti_karyawan_lihat", "write_keys": ["izin_cuti_karyawan"]},
    "absensi": {"label": "Absensi", "read_key": "izin_absensi_lihat",
                "write_keys": ["izin_absensi_pengaturan", "izin_absensi_koreksi"]},
    "booking": {"label": "Booking", "read_key": "izin_booking_lihat",
                "write_keys": ["izin_booking_kelola", "izin_booking_batalkan", "izin_booking_hapus", "izin_booking_pengaturan"]},
    "riwayat_transaksi": {"label": "Riwayat Transaksi", "read_key": "izin_riwayat_transaksi_lihat",
                           "write_keys": ["izin_riwayat_transaksi"]},
    "pemasukan": {"label": "Pemasukan", "read_key": "izin_pemasukan_lihat",
                  "write_keys": ["izin_pemasukan_kelola", "izin_pemasukan_hapus"]},
    "pengeluaran": {"label": "Pengeluaran", "read_key": "izin_pengeluaran_lihat",
                     "write_keys": ["izin_pengeluaran_kelola", "izin_pengeluaran_hapus"]},
    "uang_kas": {"label": "Uang Kas", "read_key": "izin_uang_kas_lihat",
                 "write_keys": ["izin_uang_kas_kelola", "izin_uang_kas_hapus"]},
    "produk": {"label": "Produk", "read_key": "izin_produk_lihat",
               "write_keys": ["izin_produk_kelola", "izin_produk_hapus"]},
    "settlement_faspay": {"label": "Settlement Faspay", "read_key": "izin_settlement_faspay_lihat",
                           "write_keys": ["izin_settlement_faspay"]},
}

LEVEL_NONE, LEVEL_BACA, LEVEL_EDIT = "none", "read", "write"


def get_menu_level(menu_key: str, tenant_id=None, role_id=None) -> str:
    """Level EFEKTIF ("none"/"read"/"write") satu menu, dihitung dari key
    baca+tulisnya (lihat MENU_DEFS). Kalau ANY key tulis sudah True (mis.
    data lama sebelum revisi ini, atau kombinasi tidak biasa) tapi key baca
    lupa ikut True, tetap dianggap minimal "read" -- tulis TANPA bisa baca
    tidak masuk akal buat pengguna."""
    if menu_key not in MENU_DEFS:
        raise ValueError(f"Menu tidak dikenal: {menu_key}")
    definisi = MENU_DEFS[menu_key]
    izin = get_all(tenant_id=tenant_id, role_id=role_id)
    baca = izin.get(definisi["read_key"], False)
    write_keys = definisi["write_keys"]
    semua_tulis = bool(write_keys) and all(izin.get(k, False) for k in write_keys)
    if semua_tulis:
        return LEVEL_EDIT
    if baca or any(izin.get(k, False) for k in write_keys):
        return LEVEL_BACA
    return LEVEL_NONE


def get_all_menu_levels(tenant_id=None, role_id=None) -> dict:
    """{menu_key: level} untuk SELURUH menu di MENU_DEFS -- satu query
    get_all() dipakai ulang untuk semua menu (bukan panggil get_menu_level()
    N kali, masing-masing query database sendiri)."""
    izin = get_all(tenant_id=tenant_id, role_id=role_id)
    hasil = {}
    for menu_key, definisi in MENU_DEFS.items():
        baca = izin.get(definisi["read_key"], False)
        write_keys = definisi["write_keys"]
        semua_tulis = bool(write_keys) and all(izin.get(k, False) for k in write_keys)
        if semua_tulis:
            hasil[menu_key] = LEVEL_EDIT
        elif baca or any(izin.get(k, False) for k in write_keys):
            hasil[menu_key] = LEVEL_BACA
        else:
            hasil[menu_key] = LEVEL_NONE
    return hasil


def set_menu_level(menu_key: str, level: str, tenant_id=None, role_id=None) -> dict:
    """Simpan satu level menu -- diterjemahkan ke key baca+tulis lama lewat
    set_bulk() yang sudah ada (lihat MENU_DEFS)."""
    if menu_key not in MENU_DEFS:
        raise ValueError(f"Menu tidak dikenal: {menu_key}")
    if level not in (LEVEL_NONE, LEVEL_BACA, LEVEL_EDIT):
        raise ValueError(f"Level tidak dikenal: {level}")
    definisi = MENU_DEFS[menu_key]
    data = {definisi["read_key"]: level in (LEVEL_BACA, LEVEL_EDIT)}
    for k in definisi["write_keys"]:
        data[k] = (level == LEVEL_EDIT)
    return set_bulk(data, tenant_id=tenant_id, role_id=role_id)


def set_all_menu_levels(levels: dict, tenant_id=None, role_id=None) -> dict:
    """Simpan BANYAK level menu sekaligus (dipakai form "Kelola Izin" yang
    baru -- satu PUT menyimpan seluruh dropdown menu untuk satu Role) --
    satu set_bulk() gabungan (bukan N kali panggil set_menu_level(), N kali
    query terpisah)."""
    tidak_dikenal = set(levels.keys()) - set(MENU_DEFS.keys())
    if tidak_dikenal:
        raise ValueError(f"Menu tidak dikenal: {', '.join(sorted(tidak_dikenal))}")
    data = {}
    for menu_key, level in levels.items():
        if level not in (LEVEL_NONE, LEVEL_BACA, LEVEL_EDIT):
            raise ValueError(f"Level tidak dikenal untuk menu {menu_key}: {level}")
        definisi = MENU_DEFS[menu_key]
        data[definisi["read_key"]] = level in (LEVEL_BACA, LEVEL_EDIT)
        for k in definisi["write_keys"]:
            data[k] = (level == LEVEL_EDIT)
    set_bulk(data, tenant_id=tenant_id, role_id=role_id)
    return get_all_menu_levels(tenant_id=tenant_id, role_id=role_id)


def get_all(tenant_id=None, role_id=None) -> dict:
    """{key: bool} untuk SELURUH permission.

    FITUR Role Custom (diminta Owner, lihat user_roles_db.py): `role_id`
    OPSIONAL -- diisi (akun 'staff' yang Role-nya salah satu Role Custom
    lewat users.custom_role_id) -> baca dari user_role_permissions (fail-
    CLOSED, kode yang tidak ada di sana = False, TIDAK PERNAH pakai default
    PERMISSION_DEFS -- role baru sengaja mulai kosong, lihat docstring
    modul user_roles_db.py). `role_id=None` (default, JUGA berlaku untuk
    SEMUA akun staff ber-Role "Admin", Role bawaan) -> PERSIS perilaku
    lama, dengan default dari PERMISSION_DEFS kalau Owner belum pernah
    mengaturnya sama sekali. SATU query (get_all_settings(),
    sudah ada sejak Tahap 2) -- bukan satu query per key -- karena fungsi
    ini dipanggil di SETIAP pengecekan require_permission()/has(), termasuk
    untuk request yang datang beruntun.

    FONDASI Multi-Tenant Phase 1: `tenant_id` opsional (lihat catatan
    db.get_setting()/_kunci_tenant()) -- Hak Akses User adalah pengaturan
    PER TOKO (Owner Tenant A tidak boleh mengatur Admin Tenant B), jadi
    endpoint ber-login WAJIB mengisi ini (lihat auth.require_permission)."""
    if role_id is not None:
        import user_roles_db  # import lokal: hindari import siklik (user_roles_db.py -> database.py)
        aktif = user_roles_db.get_role_permission_keys(role_id)
        return {key: (key in aktif) for key, *_ in PERMISSION_DEFS}
    semua = db.get_all_settings(tenant_id=tenant_id)
    hasil = {}
    for key, _grup, _label, default in PERMISSION_DEFS:
        nilai = semua.get(key)
        hasil[key] = (nilai == "1") if nilai is not None else default
    return hasil


def set_bulk(data: dict, tenant_id=None, role_id=None) -> dict:
    """Timpa permission yang DIKIRIM saja (key yang tidak dikirim tetap
    seperti sebelumnya) -- validasi key dulu supaya tidak ada key sembarang
    ikut tersimpan. `role_id` opsional -- lihat get_all()."""
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
