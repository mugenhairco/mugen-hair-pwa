"""
tenant_migrasi.py — FONDASI Multi-Tenant (SaaS) — Phase 1
=============================================================================
Migrasi skema untuk mengubah aplikasi single-barbershop menjadi platform
multi-tenant row-based, sesuai audit & rancangan yang sudah disetujui
Owner (lihat dokumen audit terpisah). Satu file migrasi terpusat (pola sama
seperti karyawan_migrasi.py/r2_storage_migrasi.py: satu file migrasi per
sesi pekerjaan) karena perubahan ini menyentuh tabel milik banyak modul
sekaligus (database.py, auth_db.py, booking_db.py, website_content.py).

PENTING -- TIDAK DESTRUKTIF, TIDAK MENGUBAH BUSINESS LOGIC:
- Kolom `tenant_id` ditambahkan sebagai NULLABLE di semua tabel yang butuh
  (ALTER TABLE ADD COLUMN, idempotent) -- TIDAK PERNAH menghapus/mengubah
  kolom yang sudah ada, TIDAK PERNAH menghapus baris.
- Data yang SUDAH ADA (satu barbershop yang sudah berjalan produksi) di-
  backfill OTOMATIS ke SATU tenant default ("MUGEN Hair Co.", dibuat sekali
  di sini) -- Owner existing TIDAK KEHILANGAN AKSES/DATA apa pun, dan tidak
  perlu melakukan apa pun secara manual.
- `database.py` (SALINAN VERBATIM aplikasi Desktop) TIDAK diubah strukturnya
  di sini -- migrasi ini HANYA menambah kolom lewat ALTER TABLE dari LUAR
  file itu, sama seperti pola SEMUA migrasi lain di proyek ini sejak awal
  (karyawan_migrasi.py, booking_form_migrasi.py, dst -- lihat masing-masing
  file itu, tidak ada satu pun yang menaruh ALTER TABLE di dalam
  database.py sendiri).

Tabel yang mendapat `tenant_id` LANGSUNG (root data milik satu toko, sesuai
hasil audit "Database Design Impact"):
  users, barbers, services, produk, pengeluaran, website_gallery,
  bookings, closed_slot, toko_libur

FONDASI Multi-Tenant Phase 1.1 -- tiga tabel tambahan juga mendapat
tenant_id LANGSUNG (bukan lewat _TABEL_TENANT_LANGSUNG generik di atas
karena masing-masing constraint-nya beda, lihat penjelasan tiap fungsi):
  pemasukan (barber_id NULLABLE -- beda dari pengeluaran yang barber_id-nya
  juga nullable tapi SUDAH dapat tenant_id sejak Phase 1, pemasukan
  ketinggalan saat itu), kas_saldo_awal & kas_penyesuaian (TIDAK PUNYA
  barber_id sama sekali -- saldo kas milik TOKO, bukan satu karyawan,
  jadi tidak bisa di-scope transitif lewat JOIN ke barbers seperti
  kasbon/reimburse/dst di bawah).

Tabel yang TIDAK mendapat kolom baru (tenant-scoped TRANSITIF lewat FK ke
tabel di atas, sesuai audit -- query-nya di-filter lewat JOIN, bukan lewat
kolom baru): transaksi, transaksi_detail, absensi_libur, produk_mutasi,
booking_items. FONDASI Multi-Tenant Phase 1.1 menambah pola yang sama untuk
modul Karyawan (semua barber_id NOT NULL, sehingga cukup di-scope lewat
JOIN ke barbers.tenant_id): kasbon, kasbon_pembayaran, slip_gaji,
komisi_penyesuaian, reimburse, izin_cuti, data_non_barber.

`settings` dan `file_asset` SENGAJA TIDAK mendapat kolom baru sama sekali
(dan TIDAK butuh migrasi apa pun di sini) -- keduanya sudah punya kolom
`key TEXT PRIMARY KEY` sejak awal; isolasi tenant dilakukan dengan
menyisipkan tenant_id ke DALAM string key itu sendiri (mis. "1:persentase_komisi"),
murni di lapisan Python (lihat database.py::_kunci_tenant() dan
file_asset_db.py) -- pendekatan ini SENGAJA dipilih untuk menghindari
migrasi ALTER PRIMARY KEY yang jauh lebih berisiko (SQLite tidak bisa
mengubah PRIMARY KEY tanpa membangun ulang tabel) padahal `settings`/
`file_asset` termasuk tabel yang paling sering dibaca-tulis di aplikasi
ini. Baris LAMA (key belum berawalan "<tenant_id>:") tetap terbaca sebagai
milik tenant default lewat fallback di get_setting()/file_asset_db.ambil()
-- lihat komentar di masing-masing fungsi itu.
"""

from database import get_conn, DEFAULT_SETTINGS

NAMA_TENANT_DEFAULT = "MUGEN Hair Co."
SLUG_TENANT_DEFAULT = "mugen-hair-co"

_TABEL_TENANT_LANGSUNG = [
    "users", "barbers", "services", "produk", "pengeluaran",
    "website_gallery", "bookings", "closed_slot", "toko_libur",
    # FONDASI Multi-Tenant Phase 1.1 -- lihat penjelasan di docstring modul.
    "pemasukan", "kas_saldo_awal", "kas_penyesuaian",
]


def migrasi_tenant():
    with get_conn() as conn:
        _buat_tabel_tenants(conn)
        _tambah_kolom_is_toko_utama(conn)
        tenant_id_default = _pastikan_tenant_default(conn)
        _backfill_toko_utama(conn)
        for tabel in _TABEL_TENANT_LANGSUNG:
            _tambah_kolom_tenant_id(conn, tabel)
            _backfill_tenant_id(conn, tabel, tenant_id_default)
        _migrasi_prefix_settings(conn, tenant_id_default)
        _backfill_default_settings_semua_tenant(conn)


def _buat_tabel_tenants(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            slug               TEXT NOT NULL UNIQUE,
            nama_barbershop    TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'aktif',
            masa_aktif_sampai  TEXT,
            custom_domain      TEXT,
            created_at         TEXT NOT NULL
        )
    """)


def _tambah_kolom_is_toko_utama(conn):
    """HOTFIX Migrasi Subdomain (insiden kehilangan data toko utama, lihat
    kronologi lengkap di docstring _pastikan_tenant_default() di bawah)."""
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(tenants)").fetchall()]
    if kolom and "is_toko_utama" not in kolom:
        conn.execute("ALTER TABLE tenants ADD COLUMN is_toko_utama INTEGER NOT NULL DEFAULT 0")


def _pastikan_tenant_default(conn) -> int:
    """Tenant pertama, merepresentasikan data yang SUDAH berjalan produksi
    sebelum Phase 1 ini -- dibuat SEKALI (idempotent), seluruh baris lama
    di-backfill ke tenant ini supaya Owner existing tidak kehilangan
    akses/data apa pun.

    INSIDEN kehilangan data toko utama (HOTFIX Migrasi Subdomain): SEBELUM
    perbaikan ini, fungsi ini HANYA mengecek `WHERE slug = SLUG_TENANT_DEFAULT`
    -- begitu Super Admin mengganti slug toko utama lewat fitur "Ubah Slug"
    (mis. "mugen-hair-co" -> "mugen"), pengecekan itu SELALU gagal
    menemukan tenant mana pun sejak saat itu, sehingga fungsi ini (dipanggil
    SETIAP kali proses ini boot/restart) mengira toko utama "hilang" dan
    diam-diam MEMBUAT TENANT BARU YANG KOSONG bernama sama pada RESTART
    BERIKUTNYA -- tenant asli (dengan slug baru, berikut SELURUH datanya)
    sebenarnya tetap ada, tapi dua tenant bernama sama ("MUGEN Hair Co.")
    tampil berdampingan di Dashboard Super Admin, membuka celah salah pilih
    saat menghapus tenant lain -- dikombinasikan dengan hapus_tenant() yang
    JUGA masih mengecek slug (lihat riwayat perbaikan di tenant_db.py),
    berujung toko utama produksi PRODUKSI SUNGGUHAN terhapus permanen tanpa
    backup. Diperbaiki dengan mengecek APAKAH ADA TENANT SAMA SEKALI (bukan
    lagi slug spesifik) -- tenant baru HANYA dibuat kalau tabel `tenants`
    benar-benar kosong total (instalasi pertama kali); kalau sudah ada
    tenant lain (apa pun slug-nya, mis. karena rename yang sah), tenant
    PALING LAMA (id terkecil) dipakai sebagai target backfill baris legacy
    tanpa tenant_id -- TIDAK PERNAH membuat baris baru lagi selama masih
    ada tenant yang tersisa."""
    row = conn.execute("SELECT id FROM tenants WHERE slug = ?", (SLUG_TENANT_DEFAULT,)).fetchone()
    if row:
        return row["id"]
    row = conn.execute("SELECT id FROM tenants ORDER BY id LIMIT 1").fetchone()
    if row:
        return row["id"]
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO tenants (slug, nama_barbershop, status, created_at) VALUES (?, ?, 'aktif', ?)",
        (SLUG_TENANT_DEFAULT, NAMA_TENANT_DEFAULT, now),
    )
    return cur.lastrowid


def _backfill_toko_utama(conn) -> None:
    """HOTFIX Migrasi Subdomain (insiden kehilangan data toko utama): set
    flag PERMANEN `tenants.is_toko_utama` -- SATU-SATUNYA yang dicek
    tenant_db.py::hapus_tenant() untuk melindungi toko utama dari
    penghapusan, menggantikan pengecekan slug yang TERBUKTI rapuh (lihat
    docstring _pastikan_tenant_default() di atas untuk kronologi lengkap
    insidennya). Idempotent & SEKALI SAJA seumur hidup database: no-op
    begitu ADA tenant mana pun yang sudah ter-flag. WAJIB dipanggil SETELAH
    _pastikan_tenant_default() (supaya tenant defaultnya sudah pasti ada)."""
    sudah_ada = conn.execute("SELECT 1 FROM tenants WHERE is_toko_utama = 1 LIMIT 1").fetchone()
    if sudah_ada:
        return
    conn.execute("UPDATE tenants SET is_toko_utama = 1 WHERE slug = ?", (SLUG_TENANT_DEFAULT,))


def _tambah_kolom_tenant_id(conn, tabel: str):
    kolom = [r["name"] for r in conn.execute(f"PRAGMA table_info({tabel})").fetchall()]
    if kolom and "tenant_id" not in kolom:
        conn.execute(f"ALTER TABLE {tabel} ADD COLUMN tenant_id INTEGER")


def _backfill_tenant_id(conn, tabel: str, tenant_id_default: int):
    """Idempotent -- hanya mengisi baris yang tenant_id-nya MASIH KOSONG,
    tidak pernah menimpa baris yang sudah pernah di-assign ke tenant lain
    (mis. tenant baru yang dibuat setelah Phase 1 ini aktif)."""
    conn.execute(f"UPDATE {tabel} SET tenant_id = ? WHERE tenant_id IS NULL", (tenant_id_default,))


def _key_sudah_diprefix(key: str) -> bool:
    depan = key.split(":", 1)[0]
    return depan.isdigit()


def _migrasi_prefix_settings(conn, tenant_id_default: int):
    """SAMA PERSIS logikanya dengan postgres_schema.py::_migrasi_prefix_settings()
    (diduplikasi murni karena jalur SQLite/Postgres memang dua file skema
    terpisah sejak awal proyek ini, lihat db_compat.py) -- generik, TIDAK
    perlu tahu daftar key satu-satu (default setting tersebar di banyak
    modul: database.py, pengaturan_identitas.py, website_content.py,
    booking_db.py, dst). Menyalin SETIAP baris `settings` yang key-nya masih
    polos (belum berbentuk "<tenant_id>:asli") ke bentuk baru diprefix
    tenant default, dengan NILAI SAAT INI (bukan nilai default pabrik) --
    baris lama TETAP dibiarkan ada. WAJIB jalan SEBELUM kode mana pun mulai
    membaca key ber-prefix (lihat database.py::get_setting()), supaya toko
    yang SUDAH mengustomisasi setting tidak diam-diam ter-reset."""
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    for r in rows:
        key = r["key"]
        if _key_sudah_diprefix(key):
            continue
        kunci_baru = f"{tenant_id_default}:{key}"
        existing = conn.execute("SELECT value FROM settings WHERE key = ?", (kunci_baru,)).fetchone()
        if existing is None:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (kunci_baru, r["value"]))


def _backfill_default_settings_semua_tenant(conn):
    """BUGFIX: tenant_db.buat_tenant() (dipakai routers/tenant_registration.py
    registrasi mandiri MAUPUN routers/superadmin.py provisioning manual)
    SEBELUM PERBAIKAN INI hanya membuat baris `tenants` itu sendiri, TIDAK
    PERNAH men-seed satu setting pun -- database.py::get_setting()/
    _setting_float() lalu diam-diam fallback ke "0" (BUKAN nilai default
    pabrik yang seharusnya, mis. persentase_komisi 40%) untuk SETIAP tenant
    yang dibuat lewat kedua jalur itu (satu-satunya tenant yang benar dari
    awal adalah tenant default hasil migrasi di atas), sampai Owner tenant
    itu KEBETULAN membuka & menyimpan ulang setiap halaman Setting terkait
    sendiri -- bug nyata yang ditemukan lewat laporan Komisi selalu Rp 0
    (lihat rekap.js/dashboard_barber.js REVISI Bugfix Komisi).

    Backfill ini jalan tiap kali proses ini boot (SAMA seperti seluruh
    migrasi lain di file ini, murah & aman diulang) untuk SEMUA tenant yang
    ADA SAAT INI -- AMAN & idempotent (INSERT ... ON CONFLICT DO NOTHING,
    dialek-netral persis pola database.py::init_db() men-seed DEFAULT_
    SETTINGS) -- HANYA mengisi baris yang BENAR-BENAR belum ada, TIDAK
    PERNAH menimpa setting yang sudah eksplisit diisi/diubah Owner tenant
    mana pun (termasuk kalau Owner itu sengaja mengubahnya jadi 0).
    tenant_db.buat_tenant() sendiri JUGA sudah diperbaiki (seed langsung
    saat tenant baru dibuat) -- backfill di sini KHUSUS untuk tenant yang
    SUDAH TERLANJUR ada sebelum perbaikan ini dipasang."""
    tenant_ids = [r["id"] for r in conn.execute("SELECT id FROM tenants").fetchall()]
    for tenant_id in tenant_ids:
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
                (f"{tenant_id}:{key}", value),
            )
