"""
billing_db.py — FONDASI Multi-Tenant Phase 4: Billing & Payment (Payment Gateway)
=============================================================================
Konfigurasi paket langganan (nama/harga/durasi/status/urutan/deskripsi/
batas pemakaian) yang bisa diatur Super Admin -- TIDAK ADA satu pun nilai
di sini yang di-hardcode di kode aplikasi, semuanya baris di tabel
`subscription_packages`.

PENTING -- hubungan dengan subscription_db.py (Phase 3), SESUAI RULE Phase
4 "gunakan sistem paket yang sudah tersedia, jangan membuat tabel paket
baru kalau sudah ada, jangan mengubah fitur Phase 3": kode paket
(free/basic/pro/enterprise) TETAP PERSIS subscription_db.PACKAGE_VALID
(diimpor, BUKAN diduplikasi) -- SATU-SATUNYA "sistem paket" yang sudah ada
sebelum Phase 4 hanyalah EMPAT nilai teks itu sendiri di kolom
tenant_subscriptions.package, TANPA data harga/durasi/limit/fitur apa pun
melekat padanya. Tabel `subscription_packages` di sini BUKAN sistem paket
baru/tier baru -- murni wadah atribut yang bisa diatur Super Admin untuk
EMPAT kode yang sama itu (satu baris per kode, terhubung lewat
`subscription_packages.kode = tenant_subscriptions.package`, TANPA foreign
key -- lihat catatan panjang di postgres_schema.py soal kenapa tenant_id
dan kolom serupa di proyek ini sengaja tidak pernah pakai FK ke tabel
lain). tenant_subscriptions ITU SENDIRI (status/trial/grace/dst) SAMA
SEKALI TIDAK disentuh di sini.

Tabel baru murni milik modul ini (pola sama seperti subscription_db.py) --
init_billing_db() dipanggil dari main.py on_startup() jalur SQLite. Jalur
PostgreSQL: tabel yang SAMA dibuat di postgres_schema.py.

Modul ini JUGA berisi katalog fitur (`subscription_features` +
`subscription_package_features`, penugasan checkbox per paket).

REVISI (audit "fitur hardcode di Superadmin" -- diminta Owner): katalog ini
SEBELUMNYA berisi 14 kode, HANYA 4 yang sungguhan menggerbang sesuatu di
kode (booking_online/export_pdf/qris/log_error, log_error BELAKANGAN
dihapus juga, lihat hapus_gerbang_log_error() di bawah) -- 10 sisanya (Dashboard
Owner/Barber, Multi Barber, Multi Cabang, Google Calendar, Export Excel,
Virtual Account, API, Priority Support) murni LABEL yang bisa dicentang
Superadmin tanpa efek teknis apa pun, berpotensi menjanjikan sesuatu yang
tidak sungguhan ada ke paket berbayar. `_FITUR_DEFAULT` di bawah SEKARANG
HANYA berisi kode yang benar-benar ditegakkan (lihat feature_access.py) --
`hapus_fitur_tanpa_fungsi_nyata()` membersihkan baris lama yang sudah
sempat ter-seed di database production, dan endpoint `POST /features`
(bikin kode fitur baru bebas) DIHAPUS TOTAL dari routers/billing.py --
Super Admin sekarang HANYA bisa mencentang/hapus-centang dari daftar tetap
ini per paket, TIDAK BISA lagi mengarang nama fitur sendiri (lihat
docstring `_FITUR_DEFAULT`/`hapus_fitur_tanpa_fungsi_nyata()` di bawah
untuk audit lengkap per kode).

Dua kode (`export_excel`, `whatsapp_reminder`) yang audit ini temukan
SUNGGUHAN nyata (masing-masing laporan Excel Absensi & notifikasi WhatsApp
Fonnte) TAPI belum pernah digerbang sebelumnya (selalu menyala gratis
untuk SEMUA tenant) baru DIBERI gate SEKARANG (lihat routers/attendance.py
& booking_db.py::_kirim_notifikasi_wa_booking()) --
`seed_grandfather_fitur_baru_digerbang()` di bawah SEKALI memberikan
keduanya ke SELURUH paket yang sudah ada supaya tenant yang sudah
memakainya tidak tiba-tiba kehilangan akses begitu perubahan ini deploy,
pola SAMA PERSIS `seed_default_package_features()`/`_FITUR_NYATA_DEFAULT`
di bawah.

Beda dengan LIMIT_FIELDS di bawah (barber/user/layanan/booking) yang
BENAR-BENAR ditegakkan di kode karena entitasnya nyata ada."""

from datetime import datetime

from database import get_conn, get_setting, set_setting
from subscription_db import PACKAGE_VALID

# Kode fitur yang SUNGGUHAN ditegakkan sistem (lihat feature_access.py) --
# dipakai HANYA oleh seed_default_package_features() di bawah, supaya
# instalasi/tenant yang SUDAH ADA sebelum Feature Gating ini dibangun tidak
# tiba-tiba kehilangan Booking Online/Export PDF begitu deploy ini jalan
# (SEBELUM Feature Gating, keduanya selalu menyala untuk SEMUA tenant
# tanpa syarat apa pun -- default paket HARUS mencerminkan itu).
# "qris" SEBELUMNYA ada di sini juga -- DIHAPUS (diminta Owner, lihat
# hapus_gerbang_qris() di bawah): QRIS adalah metode pembayaran INTI yang
# HARUS tersedia untuk SEMUA paket tanpa kecuali, jadi tidak masuk akal
# jadi checkbox opsional per paket -- routers/booking.py TIDAK LAGI
# memanggil require_feature("qris")/tenant_has_feature(..., "qris") sama
# sekali di mana pun.
_FITUR_NYATA_DEFAULT = ("booking_online", "export_pdf")

# HANYA kode yang sungguhan menggerbang sesuatu di kode (lihat
# feature_access.py) -- lihat docstring modul di atas untuk audit lengkap
# 10 kode yang DIHAPUS dari sini (Dashboard Owner/Barber, Multi Barber,
# Multi Cabang, Google Calendar, Virtual Account, API, Priority Support --
# TIDAK PERNAH ada implementasinya sama sekali) dan 2 kode yang baru
# ditambah gate-nya di audit yang sama (Export Excel, WhatsApp Reminder --
# lihat seed_grandfather_fitur_baru_digerbang() supaya tenant yang sudah
# pakai tidak kehilangan akses).
_FITUR_DEFAULT = (
    ("booking_online", "Booking Online"),
    ("export_pdf", "Export PDF"),
    ("export_excel", "Export Excel"),
    # FITUR Feature Gating lanjutan (diminta Owner): "barber_app" (login
    # akun ber-role 'barber', lihat routers/auth_router.py::login()) --
    # SENGAJA (keputusan eksplisit Owner) fail-CLOSED langsung untuk paket
    # mana pun yang belum dicentang Super Admin.
    ("barber_app", "Aplikasi Barber (Login Barber)"),
)

# Batas pemakaian (kolom nullable di subscription_packages, NULL = tidak
# dibatasi) -- SESUAI KEPUTUSAN cakupan Phase 4: HANYA limit yang punya
# entitas nyata di aplikasi ini (barber/user/layanan/booking) yang benar-
# benar ditegakkan di kode (lihat billing_limits.py). max_cabang TETAP ada
# sebagai kolom yang bisa diisi Super Admin (aplikasi ini memang belum
# punya konsep "cabang" sama sekali -- kolom ini murni data konfigurasi/
# ditampilkan di halaman Billing, TIDAK menggerbang fungsi apa pun karena
# tidak ada jalur kode yang membuat entitas "cabang").
LIMIT_FIELDS = ("max_barber", "max_user", "max_layanan", "max_booking", "max_cabang")

_URUTAN_DEFAULT = {"free": 1, "basic": 2, "pro": 3, "enterprise": 4}
_NAMA_DEFAULT = {"free": "Free", "basic": "Basic", "pro": "Pro", "enterprise": "Enterprise"}
_HARGA_DEFAULT = {"free": 0, "basic": 188000, "pro": 250000, "enterprise": 350000}

# FITUR Landing Page & Pricing (paket 6 bulan): harga OPSIONAL untuk siklus
# langganan 6 bulan -- NULL (default) berarti paket ini HANYA menawarkan
# siklus bulanan (frontend tidak menampilkan opsi 6 Bulan untuk paket itu,
# lihat routers/billing.py::checkout()). SENGAJA kolom terpisah dari
# `harga` (bulanan) yang SUDAH ADA, BUKAN kolom "durasi_hari_6bulan" baru --
# durasi 6-bulan SELALU dihitung `durasi_hari * 6` (lihat checkout()),
# konsisten dengan makna "6 Bulan" itu sendiri, tanpa perlu Super Admin
# mengisi durasi terpisah yang gampang tidak sinkron.
_HARGA_6BULAN_DEFAULT = {"free": None, "basic": 950000, "pro": 1200000, "enterprise": 1800000}

# FITUR Landing Page & Pricing (paket Tahunan, diminta Owner): pola SAMA
# PERSIS dengan harga_6bulan di atas -- kolom OPSIONAL terpisah (bukan
# "durasi_hari_tahunan" baru, durasi tahunan SELALU durasi_hari*12, lihat
# checkout()), NULL berarti paket ini tidak menawarkan siklus tahunan.
# Nilai default = harga resmi yang diminta Owner (harga_tahunan/12 pas
# menghasilkan "harga efektif per bulan" yang diminta: Basic Rp130rb,
# Pro Rp180rb, Enterprise Rp280rb -- tidak perlu kolom terpisah untuk itu,
# dihitung langsung di frontend, lihat landing.js/billing.js).
_HARGA_TAHUNAN_DEFAULT = {"free": None, "basic": 1560000, "pro": 2160000, "enterprise": 3360000}


def init_billing_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_packages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                kode         TEXT NOT NULL UNIQUE,
                nama         TEXT NOT NULL,
                harga        INTEGER NOT NULL DEFAULT 0,
                harga_6bulan INTEGER,
                harga_tahunan INTEGER,
                durasi_hari  INTEGER NOT NULL DEFAULT 30,
                aktif        INTEGER NOT NULL DEFAULT 1,
                urutan       INTEGER NOT NULL DEFAULT 0,
                deskripsi    TEXT,
                max_barber   INTEGER,
                max_user     INTEGER,
                max_layanan  INTEGER,
                max_booking  INTEGER,
                max_cabang   INTEGER,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        # Instalasi SQLite yang SUDAH ADA sebelum kolom ini ditambahkan ke
        # CREATE TABLE di atas (instalasi baru sudah dapat kolomnya
        # langsung) -- pola sama seperti website_content.py::init_website_db().
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(subscription_packages)").fetchall()]
        if kolom and "harga_6bulan" not in kolom:
            conn.execute("ALTER TABLE subscription_packages ADD COLUMN harga_6bulan INTEGER")
        if kolom and "harga_tahunan" not in kolom:
            conn.execute("ALTER TABLE subscription_packages ADD COLUMN harga_tahunan INTEGER")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_features (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                kode         TEXT NOT NULL UNIQUE,
                nama         TEXT NOT NULL,
                deskripsi    TEXT,
                aktif        INTEGER NOT NULL DEFAULT 1,
                urutan       INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        # package_id/feature_id PAKAI foreign key (beda dengan tenant_id di
        # tabel lain) -- kedua tabel ini BARU dibuat di sini sendiri dengan
        # PRIMARY KEY yang benar sejak awal, TIDAK seperti tabel `tenants`
        # produksi lama yang jadi sumber insiden FK di catatan panjang
        # postgres_schema.py. Pola sama seperti kasbon_id/slip_gaji_id di
        # kasbon_db.py.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_package_features (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                package_id   INTEGER NOT NULL,
                feature_id   INTEGER NOT NULL,
                created_at   TEXT NOT NULL,
                UNIQUE(package_id, feature_id),
                FOREIGN KEY (package_id) REFERENCES subscription_packages(id),
                FOREIGN KEY (feature_id) REFERENCES subscription_features(id) ON DELETE CASCADE
            )
        """)
        # FITUR Package Permission Tree (Work #2, diminta Owner): batas
        # LUAR per-paket -- menu/tab/sub-item APA SAJA (katalog SAMA PERSIS
        # permissions.PERMISSION_TREE, lihat docstring modul di atas) yang
        # TERSEDIA SAMA SEKALI untuk tenant paket ini, TERLEPAS dari Role
        # staff-nya (yang mengatur batas DALAM, lihat permissions.py/
        # user_role_permissions). Pola tabel SAMA PERSIS user_role_permissions
        # (package_id/izin_key, bukan role_id/izin_key) -- package_id PAKAI
        # FK (tabel ini BARU, PRIMARY KEY benar sejak awal, BUKAN tabel
        # produksi lama).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_package_permissions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                package_id   INTEGER NOT NULL,
                izin_key     TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                UNIQUE(package_id, izin_key),
                FOREIGN KEY (package_id) REFERENCES subscription_packages(id) ON DELETE CASCADE
            )
        """)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def seed_default_packages():
    """Idempotent -- SEKALI membuat baris untuk keempat kode paket yang
    belum punya baris sama sekali, dengan nilai AWAL yang masuk akal
    (bukan nilai "benar" yang dipaksakan -- Super Admin bebas mengubah
    semuanya kapan pun lewat Dashboard-nya, ini murni titik awal supaya
    sistem tidak boot dengan paket kosong tanpa harga/nama)."""
    with get_conn() as conn:
        existing = {r["kode"] for r in conn.execute("SELECT kode FROM subscription_packages").fetchall()}
        now = _now()
        for kode in sorted(PACKAGE_VALID, key=lambda k: _URUTAN_DEFAULT.get(k, 99)):
            if kode in existing:
                continue
            conn.execute(
                "INSERT INTO subscription_packages "
                "(kode, nama, harga, harga_6bulan, harga_tahunan, durasi_hari, aktif, urutan, deskripsi, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 30, 1, ?, '', ?, ?)",
                (kode, _NAMA_DEFAULT.get(kode, kode.title()), _HARGA_DEFAULT.get(kode, 0),
                 _HARGA_6BULAN_DEFAULT.get(kode), _HARGA_TAHUNAN_DEFAULT.get(kode),
                 _URUTAN_DEFAULT.get(kode, 0), now, now),
            )


_KUNCI_MIGRASI_HARGA_PRICING_2 = "billing_migrasi_harga_pricing_2_selesai"


def migrasi_harga_pricing_v2():
    """FITUR Landing Page & Pricing (revisi paket 6 bulan): SEKALI SAJA
    sepanjang umur database (flag `settings`, pola SAMA PERSIS seperti
    seed_default_package_features() -- BUKAN dicek ulang dari nilai harga
    yang ada, supaya kalau Super Admin SUDAH mengubah harga basic/pro/
    enterprise secara manual sebelum migrasi ini pernah jalan, perubahan
    itu TIDAK diam-diam ditimpa lagi setiap kali server restart) menetapkan
    harga bulanan + harga 6 bulan BARU untuk basic/pro/enterprise sesuai
    daftar harga resmi terbaru (`_HARGA_DEFAULT`/`_HARGA_6BULAN_DEFAULT` di
    atas) -- SEKALI dijalankan, Super Admin 100% memegang kendali penuh
    lewat Dashboard tanpa gangguan apa pun dari migrasi ini lagi, PERSIS
    seperti paket free (harga tetap 0, tidak disentuh migrasi ini)."""
    if get_setting(_KUNCI_MIGRASI_HARGA_PRICING_2, default=None) == "1":
        return
    for kode in ("basic", "pro", "enterprise"):
        paket = get_package_by_kode(kode)
        if paket is not None:
            update_package(paket["id"], harga=_HARGA_DEFAULT[kode], harga_6bulan=_HARGA_6BULAN_DEFAULT[kode])
    set_setting(_KUNCI_MIGRASI_HARGA_PRICING_2, "1")


_KUNCI_MIGRASI_HARGA_TAHUNAN_1 = "billing_migrasi_harga_tahunan_1_selesai"


def migrasi_harga_tahunan_v1():
    """FITUR Landing Page & Pricing (paket Tahunan, diminta Owner): SEKALI
    SAJA sepanjang umur database (pola SAMA PERSIS migrasi_harga_pricing_v2()
    di atas) menetapkan harga_tahunan basic/pro/enterprise sesuai
    `_HARGA_TAHUNAN_DEFAULT` -- flag TERPISAH dari migrasi harga_6bulan
    supaya tidak menimpa ulang harga/harga_6bulan yang mungkin sudah diubah
    Super Admin secara manual sejak migrasi itu selesai. `harga`/
    `harga_6bulan` SAMA SEKALI TIDAK disentuh di sini."""
    if get_setting(_KUNCI_MIGRASI_HARGA_TAHUNAN_1, default=None) == "1":
        return
    for kode in ("basic", "pro", "enterprise"):
        paket = get_package_by_kode(kode)
        if paket is not None:
            update_package(paket["id"], harga_tahunan=_HARGA_TAHUNAN_DEFAULT[kode])
    set_setting(_KUNCI_MIGRASI_HARGA_TAHUNAN_1, "1")


_KUNCI_SEED_FITUR_PAKET = "billing_seed_fitur_nyata_paket_selesai"


def seed_default_package_features():
    """SEKALI SAJA sepanjang umur database (ditandai lewat `settings`, BUKAN
    dicek ulang dari isi subscription_package_features seperti
    seed_default_packages/seed_default_features) -- assign
    `_FITUR_NYATA_DEFAULT` (booking_online/export_pdf -- KOREKSI audit
    lanjutan: "qris" DIHAPUS TOTAL dari katalog, lihat hapus_gerbang_qris()
    di bawah, bukan lagi bagian tuple ini) ke KEEMPAT
    paket sekaligus, HANYA kalau migrasi ini belum pernah jalan sebelumnya.

    KENAPA bukan cek "paket ini sudah punya baris fitur atau belum" (pola
    idempotent yang dipakai fungsi seed_* lain di file ini): itu akan
    keliru menganggap "Super Admin sengaja mencentang nol fitur untuk paket
    ini" sama dengan "belum pernah disentuh sama sekali", lalu diam-diam
    MENGEMBALIKAN fitur yang justru sengaja dicabut Super Admin setiap kali
    server restart. Flag `settings` sekali-jalan ini memastikan seed HANYA
    terjadi tepat satu kali (transisi dari "belum ada Feature Gating sama
    sekali" ke "ada"), setelah itu Super Admin 100% memegang kendali penuh
    lewat Dashboard tanpa gangguan apa pun dari migrasi ini lagi."""
    if get_setting(_KUNCI_SEED_FITUR_PAKET, default=None) == "1":
        return
    fitur_ids = [f["id"] for f in list_features() if f["kode"] in _FITUR_NYATA_DEFAULT]
    if fitur_ids:
        for paket in list_packages():
            sudah_ada = {f["id"] for f in get_package_features(paket["id"])}
            gabungan = list(dict.fromkeys(list(sudah_ada) + fitur_ids))
            if set(gabungan) != sudah_ada:
                set_package_features(paket["id"], gabungan)
    set_setting(_KUNCI_SEED_FITUR_PAKET, "1")


# Kode fitur yang DIHAPUS permanen dari katalog (audit "fitur hardcode di
# Superadmin" -- lihat docstring modul di atas): diaudit langsung ke seluruh
# kode aplikasi, TIDAK PERNAH ada satu pun require_feature()/pemanggilan
# fungsi nyata yang menggerbang kode ini -- murni label yang bisa dicentang
# Superadmin tanpa efek teknis apa pun.
_KODE_FITUR_TANPA_FUNGSI_NYATA = (
    "dashboard_owner", "dashboard_barber", "multi_barber", "multi_cabang",
    "google_calendar", "virtual_account", "api", "priority_support",
)
_KUNCI_HAPUS_FITUR_DEKORATIF = "billing_hapus_fitur_tanpa_fungsi_nyata_selesai"


def hapus_fitur_tanpa_fungsi_nyata():
    """SEKALI SAJA sepanjang umur database -- DELETE permanen (bukan
    sekadar berhenti di-seed) `_KODE_FITUR_TANPA_FUNGSI_NYATA` dari
    `subscription_features`, supaya baris yang SUDAH sempat ter-seed di
    database production (dari _FITUR_DEFAULT versi lama, sebelum audit ini)
    ikut terhapus, bukan cuma tidak ditambah lagi. `ON DELETE CASCADE` di
    `subscription_package_features.feature_id` otomatis melepas kode ini
    dari SEMUA paket yang sudah mencentangnya -- efeknya kartu harga/
    Katalog Fitur Superadmin langsung berhenti menampilkan label yang
    memang tidak ada fungsinya. Flag `settings` sekali-jalan (pola sama
    seperti seed_default_package_features() di atas) supaya Super Admin
    yang menambah kode LAIN dengan nama kebetulan sama persis di masa
    depan (kalaupun endpoint pembuatannya belum dihapus) tidak ikut
    kehapus diam-diam tiap boot."""
    if get_setting(_KUNCI_HAPUS_FITUR_DEKORATIF, default=None) == "1":
        return
    placeholder = ", ".join("?" for _ in _KODE_FITUR_TANPA_FUNGSI_NYATA)
    with get_conn() as conn:
        conn.execute(
            f"DELETE FROM subscription_features WHERE kode IN ({placeholder})",
            _KODE_FITUR_TANPA_FUNGSI_NYATA,
        )
    set_setting(_KUNCI_HAPUS_FITUR_DEKORATIF, "1")


_KODE_FITUR_BARU_DIGERBANG = ("export_excel", "whatsapp_reminder")
_KUNCI_SEED_FITUR_BARU_DIGERBANG = "billing_seed_fitur_baru_digerbang_selesai"


def seed_grandfather_fitur_baru_digerbang():
    """SEKALI SAJA sepanjang umur database -- audit "fitur hardcode di
    Superadmin" yang sama menemukan `export_excel` (laporan Excel Absensi,
    routers/attendance.py) dan `whatsapp_reminder` (notifikasi Fonnte,
    booking_db.py::_kirim_notifikasi_wa_booking()) SUNGGUHAN nyata TAPI
    belum pernah digerbang paket sama sekali -- SELALU menyala gratis untuk
    SEMUA tenant sebelum gate ditambahkan di audit ini. Pola SAMA PERSIS
    seed_default_package_features()/_FITUR_NYATA_DEFAULT di atas: assign
    KEDUANYA ke SELURUH paket yang sudah ada SEKALI saat migrasi ini
    pertama jalan, supaya tenant yang sudah pakai tidak tiba-tiba
    kehilangan akses begitu deploy ini jalan -- Super Admin bebas
    mencabutnya lagi per paket kapan pun setelahnya lewat Dashboard."""
    if get_setting(_KUNCI_SEED_FITUR_BARU_DIGERBANG, default=None) == "1":
        return
    fitur_ids = [f["id"] for f in list_features() if f["kode"] in _KODE_FITUR_BARU_DIGERBANG]
    if fitur_ids:
        for paket in list_packages():
            sudah_ada = {f["id"] for f in get_package_features(paket["id"])}
            gabungan = list(dict.fromkeys(list(sudah_ada) + fitur_ids))
            if set(gabungan) != sudah_ada:
                set_package_features(paket["id"], gabungan)
    set_setting(_KUNCI_SEED_FITUR_BARU_DIGERBANG, "1")


_KUNCI_HAPUS_GERBANG_QRIS = "billing_hapus_gerbang_qris_selesai"


def hapus_gerbang_qris():
    """SEKALI SAJA sepanjang umur database (diminta Owner) -- "qris" DULU
    ada di _FITUR_NYATA_DEFAULT/_FITUR_DEFAULT (fitur SUNGGUHAN digerbang,
    lihat feature_access.py), TAPI Owner memutuskan QRIS adalah metode
    pembayaran INTI yang HARUS tersedia untuk SEMUA paket tanpa kecuali --
    tidak masuk akal ditawarkan sebagai checkbox opsional per paket.
    routers/booking.py SUDAH TIDAK memanggil require_feature("qris")/
    tenant_has_feature(..., "qris") di mana pun lagi (QRIS sekarang selalu
    aktif untuk siapa saja yang mengunggahnya) -- fungsi ini menghapus
    PERMANEN baris "qris" dari `subscription_features` supaya baris yang
    SUDAH sempat ter-seed di database production (dari versi _FITUR_DEFAULT
    lama) ikut terhapus, bukan cuma tidak ditambah lagi -- `ON DELETE
    CASCADE` di subscription_package_features otomatis melepasnya dari
    paket mana pun yang sudah mencentangnya, supaya Katalog Fitur Superadmin
    berhenti menampilkan checkbox "QRIS" yang sudah tidak berarti apa-apa
    lagi. Flag `settings` sekali-jalan (pola sama seperti hapus_fitur_
    tanpa_fungsi_nyata() di atas) supaya kalau Super Admin menambah kode
    LAIN dengan nama kebetulan sama persis "qris" di masa depan, itu TIDAK
    ikut terhapus diam-diam tiap boot."""
    if get_setting(_KUNCI_HAPUS_GERBANG_QRIS, default=None) == "1":
        return
    with get_conn() as conn:
        conn.execute("DELETE FROM subscription_features WHERE kode = 'qris'")
    set_setting(_KUNCI_HAPUS_GERBANG_QRIS, "1")


_KODE_FITUR_DIHAPUS_WORK_2 = (
    # 5 kode dekoratif-marketing (lihat _KODE_FITUR_DEKORATIF_MARKETING di
    # bawah) -- diganti SELURUHNYA oleh checklist menu nyata lewat Package
    # Permission Tree (Work #2, lihat migrasi_grandfather_package_permissions()
    # di atas), bukan lagi label tanpa penegakan.
    "manajemen_bisnis", "manajemen_barber", "hak_akses_role",
    "manajemen_layanan", "pengaturan_komisi_gaji",
    # 2 kode yang DULU sungguhan ditegakkan (absensi/whatsapp_reminder) --
    # SEKARANG diwakili root key pohon yang sama (izin_absensi_lihat/
    # izin_whatsapp_lihat) lewat Package Permission Tree, bukan kode
    # fitur terpisah lagi (lihat auth.py::require_menu_feature()).
    "absensi", "whatsapp_reminder",
)
_KUNCI_HAPUS_FITUR_WORK_2 = "billing_hapus_fitur_absorbed_tree_work2_selesai"


def hapus_fitur_absorbed_ke_tree():
    """SEKALI SAJA sepanjang umur database (Work #2, diminta Owner) -- DELETE
    permanen `_KODE_FITUR_DIHAPUS_WORK_2` dari `subscription_features`
    (pola SAMA PERSIS hapus_fitur_tanpa_fungsi_nyata()/hapus_gerbang_qris()
    di atas) -- `ON DELETE CASCADE` otomatis melepasnya dari paket mana pun
    yang masih mencentangnya. Akses tenant TIDAK terpengaruh (migrasi
    grandfather Package Permission Tree di atas sudah memberi akses penuh
    lebih dulu untuk key pengganti keduanya)."""
    if get_setting(_KUNCI_HAPUS_FITUR_WORK_2, default=None) == "1":
        return
    placeholder = ", ".join("?" for _ in _KODE_FITUR_DIHAPUS_WORK_2)
    with get_conn() as conn:
        conn.execute(
            f"DELETE FROM subscription_features WHERE kode IN ({placeholder})",
            _KODE_FITUR_DIHAPUS_WORK_2,
        )
    set_setting(_KUNCI_HAPUS_FITUR_WORK_2, "1")


_KUNCI_HAPUS_GERBANG_LOG_ERROR = "billing_hapus_gerbang_log_error_selesai"


def hapus_gerbang_log_error():
    """SEKALI SAJA sepanjang umur database (diminta Owner) -- fitur Log Error
    (DIY error monitoring, lihat main.py::_tangani_exception_global() versi
    lama & error_report.js yang SUDAH dihapus total dari kode) dicabut
    seluruhnya, bukan cuma disembunyikan. Menghapus PERMANEN baris
    "log_error" dari `subscription_features` supaya baris yang SUDAH sempat
    ter-seed di database production ikut terhapus, bukan cuma tidak
    ditambah lagi -- `ON DELETE CASCADE` di subscription_package_features
    otomatis melepasnya dari paket mana pun yang sudah mencentangnya,
    supaya Katalog Fitur Superadmin berhenti menampilkan checkbox "Log
    Error" yang sudah tidak berarti apa-apa lagi. Pola SAMA PERSIS
    hapus_gerbang_qris() di atas -- lihat docstring itu untuk penjelasan
    flag `settings` sekali-jalan."""
    if get_setting(_KUNCI_HAPUS_GERBANG_LOG_ERROR, default=None) == "1":
        return
    with get_conn() as conn:
        conn.execute("DELETE FROM subscription_features WHERE kode = 'log_error'")
    set_setting(_KUNCI_HAPUS_GERBANG_LOG_ERROR, "1")


_KODE_FITUR_DEKORATIF_MARKETING = (
    "manajemen_bisnis", "manajemen_barber", "hak_akses_role",
    "manajemen_layanan", "pengaturan_komisi_gaji",
)
_KUNCI_SEED_FITUR_DEKORATIF_MARKETING = "billing_seed_fitur_dekoratif_marketing_selesai"

# Sebaran BERTAHAP (diminta Owner: "agar terlihat ramai") -- paket lebih
# mahal menampilkan lebih banyak centang di kartu harga Landing Page,
# walau SEMUA kode ini SUNGGUHAN tersedia untuk SEMUA tenant apa pun
# paketnya (murni tampilan, lihat catatan _FITUR_DEFAULT di atas). "free"
# & "basic" SENGAJA TIDAK dapat "hak_akses_role" (Role Custom, fitur yang
# SUNGGUHAN baru/lanjutan, cocok jadi pembeda visual paket atas) maupun
# "manajemen_bisnis" (dashboard) di "free" -- kombinasi ini murni pilihan
# presentasi, BUKAN batasan teknis apa pun.
_SEBARAN_FITUR_DEKORATIF_PER_PAKET = {
    "free": ("manajemen_barber", "manajemen_layanan"),
    "basic": ("manajemen_barber", "manajemen_layanan", "manajemen_bisnis", "pengaturan_komisi_gaji"),
    "pro": _KODE_FITUR_DEKORATIF_MARKETING,
    "enterprise": _KODE_FITUR_DEKORATIF_MARKETING,
}


def seed_fitur_dekoratif_marketing():
    """SEKALI SAJA sepanjang umur database (diminta Owner) -- assign kelima
    kode `_KODE_FITUR_DEKORATIF_MARKETING` (lihat catatan _FITUR_DEFAULT)
    ke paket sesuai `_SEBARAN_FITUR_DEKORATIF_PER_PAKET`, SEKALI saat
    migrasi ini pertama jalan. Pola flag `settings` SAMA PERSIS seed_*
    lain di atas -- Super Admin bebas mengubah centang per paket kapan pun
    setelahnya lewat Dashboard, migrasi ini TIDAK PERNAH menimpanya lagi."""
    if get_setting(_KUNCI_SEED_FITUR_DEKORATIF_MARKETING, default=None) == "1":
        return
    fitur_by_kode = {f["kode"]: f["id"] for f in list_features() if f["kode"] in _KODE_FITUR_DEKORATIF_MARKETING}
    for paket in list_packages():
        kode_untuk_paket = _SEBARAN_FITUR_DEKORATIF_PER_PAKET.get(paket["kode"], ())
        fitur_ids = [fitur_by_kode[k] for k in kode_untuk_paket if k in fitur_by_kode]
        if not fitur_ids:
            continue
        sudah_ada = {f["id"] for f in get_package_features(paket["id"])}
        gabungan = list(dict.fromkeys(list(sudah_ada) + fitur_ids))
        if set(gabungan) != sudah_ada:
            set_package_features(paket["id"], gabungan)
    set_setting(_KUNCI_SEED_FITUR_DEKORATIF_MARKETING, "1")


def list_packages(hanya_aktif: bool = False) -> list:
    with get_conn() as conn:
        q = "SELECT * FROM subscription_packages"
        if hanya_aktif:
            q += " WHERE aktif = 1"
        q += " ORDER BY urutan, id"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_package(package_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_packages WHERE id = ?", (package_id,)).fetchone()
        return dict(row) if row else None


def get_package_by_kode(kode: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_packages WHERE kode = ?", (kode,)).fetchone()
        return dict(row) if row else None


def update_package(package_id: int, **fields) -> dict:
    """Dipanggil Super Admin (routers/billing.py) -- fields yang diterima:
    nama, harga, harga_6bulan, durasi_hari, aktif, urutan, deskripsi, +
    LIMIT_FIELDS. `kode` SENGAJA TIDAK BISA diubah lewat sini (identitas
    baris, dipakai tenant_subscriptions.package -- mengubahnya akan memutus
    keterkaitan seluruh tenant yang sudah memakai kode itu)."""
    if get_package(package_id) is None:
        raise ValueError("Paket tidak ditemukan.")
    kolom_diizinkan = {"nama", "harga", "harga_6bulan", "harga_tahunan", "durasi_hari", "aktif", "urutan", "deskripsi", *LIMIT_FIELDS}
    aman = {k: v for k, v in fields.items() if k in kolom_diizinkan}
    if not aman:
        return get_package(package_id)
    if "aktif" in aman:
        # bool -> 1/0 eksplisit (sama pola seperti database.py::update_barber()) --
        # kolom `aktif` INTEGER di kedua jalur SQLite & PostgreSQL, sebagian
        # driver PostgreSQL menolak binding bool langsung ke kolom INTEGER.
        aman["aktif"] = 1 if aman["aktif"] else 0
    if "nama" in aman and not (aman["nama"] or "").strip():
        raise ValueError("Nama paket tidak boleh kosong.")
    if "harga" in aman and (aman["harga"] is None or aman["harga"] < 0):
        raise ValueError("Harga tidak boleh negatif.")
    # harga_6bulan/harga_tahunan BOLEH None (paket ini tidak menawarkan
    # siklus itu) -- HANYA divalidasi tidak negatif kalau memang diisi.
    if "harga_6bulan" in aman and aman["harga_6bulan"] is not None and aman["harga_6bulan"] < 0:
        raise ValueError("Harga 6 bulan tidak boleh negatif.")
    if "harga_tahunan" in aman and aman["harga_tahunan"] is not None and aman["harga_tahunan"] < 0:
        raise ValueError("Harga tahunan tidak boleh negatif.")
    if "durasi_hari" in aman and (not aman["durasi_hari"] or aman["durasi_hari"] < 1):
        raise ValueError("Durasi langganan minimal 1 hari.")
    for limit_key in LIMIT_FIELDS:
        if limit_key in aman and aman[limit_key] is not None and aman[limit_key] < 0:
            raise ValueError(f"{limit_key} tidak boleh negatif.")
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    params = list(aman.values()) + [_now(), package_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE subscription_packages SET {set_clause}, updated_at = ? WHERE id = ?", params)
    return get_package(package_id)


# ============================= Katalog Fitur =============================

def seed_default_features():
    """Idempotent -- sama pola seperti seed_default_packages(), murni titik
    awal supaya katalog tidak kosong saat boot pertama. Super Admin bebas
    menambah/menghapus/mengubah SEMUANYA kapan pun."""
    with get_conn() as conn:
        existing = {r["kode"] for r in conn.execute("SELECT kode FROM subscription_features").fetchall()}
        now = _now()
        for urutan, (kode, nama) in enumerate(_FITUR_DEFAULT):
            if kode in existing:
                continue
            conn.execute(
                "INSERT INTO subscription_features (kode, nama, deskripsi, aktif, urutan, created_at, updated_at) "
                "VALUES (?, ?, '', 1, ?, ?, ?)",
                (kode, nama, urutan, now, now),
            )


def list_features(hanya_aktif: bool = False) -> list:
    with get_conn() as conn:
        q = "SELECT * FROM subscription_features"
        if hanya_aktif:
            q += " WHERE aktif = 1"
        q += " ORDER BY urutan, id"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_feature(feature_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_features WHERE id = ?", (feature_id,)).fetchone()
        return dict(row) if row else None


def get_feature_by_kode(kode: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_features WHERE kode = ?", (kode,)).fetchone()
        return dict(row) if row else None


def update_feature(feature_id: int, **fields) -> dict:
    """`kode` SENGAJA TIDAK BISA diubah lewat sini -- alasan sama persis
    seperti update_package() (identitas baris, dipakai
    subscription_package_features.feature_id)."""
    if get_feature(feature_id) is None:
        raise ValueError("Fitur tidak ditemukan.")
    kolom_diizinkan = {"nama", "deskripsi", "aktif", "urutan"}
    aman = {k: v for k, v in fields.items() if k in kolom_diizinkan}
    if not aman:
        return get_feature(feature_id)
    if "aktif" in aman:
        aman["aktif"] = 1 if aman["aktif"] else 0
    if "nama" in aman and not (aman["nama"] or "").strip():
        raise ValueError("Nama fitur tidak boleh kosong.")
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    params = list(aman.values()) + [_now(), feature_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE subscription_features SET {set_clause}, updated_at = ? WHERE id = ?", params)
    return get_feature(feature_id)


def delete_feature(feature_id: int):
    """Hapus PERMANEN dari katalog (beda dengan `aktif=0` lewat
    update_feature() -- itu murni menyembunyikan dari daftar tanpa
    menghapus). ON DELETE CASCADE di subscription_package_features.feature_id
    otomatis melepas fitur ini dari SEMUA paket yang sudah mencentangnya."""
    if get_feature(feature_id) is None:
        raise ValueError("Fitur tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("DELETE FROM subscription_features WHERE id = ?", (feature_id,))


def get_package_features(package_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT f.* FROM subscription_package_features pf "
            "JOIN subscription_features f ON f.id = pf.feature_id "
            "WHERE pf.package_id = ? ORDER BY f.urutan, f.id",
            (package_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def set_package_features(package_id: int, feature_ids: list) -> list:
    """Checkbox-style: MENGGANTI SELURUH penugasan fitur paket ini dengan
    daftar `feature_ids` yang dikirim (bukan menambah satu per satu) --
    cara paling gampang dikirim langsung dari form checkbox frontend tanpa
    perlu menghitung diff sendiri."""
    if get_package(package_id) is None:
        raise ValueError("Paket tidak ditemukan.")
    feature_ids = list(dict.fromkeys(feature_ids or []))
    katalog_ids = {f["id"] for f in list_features()}
    for fid in feature_ids:
        if fid not in katalog_ids:
            raise ValueError(f"Fitur id={fid} tidak ditemukan di katalog.")
    now = _now()
    with get_conn() as conn:
        conn.execute("DELETE FROM subscription_package_features WHERE package_id = ?", (package_id,))
        for fid in feature_ids:
            conn.execute(
                "INSERT INTO subscription_package_features (package_id, feature_id, created_at) VALUES (?, ?, ?)",
                (package_id, fid, now),
            )
    return get_package_features(package_id)


# ============================= Package Permission Tree (Work #2) =============================
# Batas LUAR per-paket -- lihat catatan tabel subscription_package_permissions
# di init_billing_db() di atas. Pola fungsi SAMA PERSIS user_roles_db.py::
# get_role_permission_keys()/set_role_permission_keys() -- fail-CLOSED
# (package BARU yang belum pernah disentuh Super Admin = kosong, TIDAK ADA
# menu/fitur apa pun yang tersedia untuk tenant paket itu) KECUALI untuk
# paket yang SUDAH ADA sebelum Work #2 (lihat migrasi_grandfather_package_
# permissions() di bawah -- full akses, mencerminkan kondisi nyata SEBELUM
# gate ini ada).

def get_package_permission_keys(package_id: int) -> set:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT izin_key FROM subscription_package_permissions WHERE package_id = ?", (package_id,)
        ).fetchall()
        return {r["izin_key"] for r in rows}


def set_package_permission_keys(package_id: int, keys: set):
    if get_package(package_id) is None:
        raise ValueError("Paket tidak ditemukan.")
    now = _now()
    with get_conn() as conn:
        conn.execute("DELETE FROM subscription_package_permissions WHERE package_id = ?", (package_id,))
        for key in keys:
            conn.execute(
                "INSERT INTO subscription_package_permissions (package_id, izin_key, created_at) VALUES (?, ?, ?)",
                (package_id, key, now),
            )


_KUNCI_GRANDFATHER_PACKAGE_PERMISSIONS = "billing_grandfather_package_permissions_selesai"


def migrasi_grandfather_package_permissions():
    """SEKALI SAJA sepanjang umur database (idempotent lewat flag `settings`,
    pola SAMA PERSIS seed_default_package_features() di atas) -- Work #2
    (Superadmin Package Permission Tree) baru menambahkan GATE SUNGGUHAN
    untuk SELURUH menu/tab/sub-item (lihat auth.py::require_permission()/
    require_menu_read(), sekarang JUGA memeriksa tenant_has_menu_access())
    yang SEBELUM ini TIDAK PERNAH digerbang per-paket sama sekali (SEMUA
    tenant, apa pun paketnya, selalu bisa memakai SEMUA menu). Supaya TIDAK
    ADA satu pun tenant yang tiba-tiba kehilangan akses begitu revisi ini
    deploy (PERMINTAAN OWNER EKSPLISIT: "paket yang sudah ada otomatis
    semua menunya tercentang, sama seperti kondisi sekarang, akses penuh"),
    SETIAP paket yang SUDAH ADA sebelum migrasi ini pertama jalan diberi
    SELURUH key permissions.PERMISSION_TREE (akses penuh) -- paket BARU
    yang dibuat Super Admin SETELAH migrasi ini pertama jalan TIDAK ikut
    (mulai kosong/fail-closed, Super Admin mengisi sendiri, SAMA seperti
    Role baru di user_roles_db.py)."""
    if get_setting(_KUNCI_GRANDFATHER_PACKAGE_PERMISSIONS, default=None) == "1":
        return
    import permissions  # import lokal: hindari import siklik (permissions.py -> database.py)
    semua_key = set(permissions.PERMISSION_KEYS)
    # PENGECUALIAN PENTING: root "izin_absensi_lihat" (+ seluruh
    # keturunannya) TIDAK ikut blanket True di atas -- "absensi" adalah
    # SATU-SATUNYA fitur yang SEBELUM diabsorb ke tree ini (lihat
    # hapus_fitur_absorbed_ke_tree() di bawah) sengaja fail-CLOSED TANPA
    # grandfather sama sekali (keputusan eksplisit Owner, lihat catatan
    # conftest.py::_default_barber_app_dan_absensi_aktif/_FITUR_DEFAULT di
    # atas -- beda dari whatsapp_reminder yang MEMANG sudah digrandfather
    # lewat seed_grandfather_fitur_baru_digerbang()). Menyamakannya dengan
    # menu lain (yang memang selalu terbuka tanpa gate apa pun sebelum Work
    # #2) akan DIAM-DIAM membuka Absensi untuk paket yang Owner sengaja
    # belum mengaktifkannya -- state per-paket yang SUDAH ADA (fitur
    # "absensi" tercentang/tidak di subscription_package_features, DIBACA
    # SEBELUM hapus_fitur_absorbed_ke_tree() menghapus barisnya) dibawa apa
    # adanya ke izin_absensi_lihat, BUKAN ditimpa True untuk semua paket.
    kunci_absensi = {"izin_absensi_lihat"} | permissions._descendants("izin_absensi_lihat")
    kunci_tanpa_absensi = semua_key - kunci_absensi
    fitur_absensi = get_feature_by_kode("absensi")
    for paket in list_packages():
        kunci_paket = set(kunci_tanpa_absensi)
        if fitur_absensi and fitur_absensi["id"] in {f["id"] for f in get_package_features(paket["id"])}:
            kunci_paket |= kunci_absensi
        set_package_permission_keys(paket["id"], kunci_paket)
    set_setting(_KUNCI_GRANDFATHER_PACKAGE_PERMISSIONS, "1")
