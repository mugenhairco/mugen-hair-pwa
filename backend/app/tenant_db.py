"""
tenant_db.py — FONDASI Multi-Tenant (SaaS) — akses tabel `tenants`
=============================================================================
Modul tipis, murni CRUD ke tabel `tenants` (dibuat oleh tenant_migrasi.py/
postgres_schema.py -- lihat file itu untuk penjelasan arsitektur lengkap).

TIDAK menyentuh `database.py` sama sekali (file itu tetap murni logika
bisnis barbershop, TIDAK PERNAH tahu apa itu "tenant") -- modul inilah yang
jadi satu-satunya sumber kebenaran "tenant mana yang aktif", dipakai oleh
auth.py (resolusi tenant dari sesi login) dan routers/booking.py
public_router (resolusi tenant dari slug publik).

Fitur pembuatan tenant BARU di sini SENGAJA minimal (bukan Super Admin
Dashboard lengkap -- itu di luar cakupan Phase 1) -- hanya cukup untuk
menjalankan pengujian isolasi dua tenant yang diminta, dan sebagai fondasi
yang akan diperluas Super Admin nanti (lihat roadmap audit, Tahap 7)."""

import os
import re
from datetime import datetime

from database import get_conn, DEFAULT_SETTINGS

STATUS_VALID = {"aktif", "nonaktif"}

# SAMA PERSIS dengan tenant_migrasi.py::SLUG_TENANT_DEFAULT (jalur SQLite) /
# postgres_schema.py::TENANT_DEFAULT_SLUG (jalur Postgres) -- diduplikasi di
# sini murni supaya modul ini tidak perlu import salah satu dari keduanya
# (tenant_db.py dipakai auth.py & routers/booking.py, TIDAK terikat jalur
# SQLite/Postgres mana pun secara langsung).
SLUG_TENANT_DEFAULT = "mugen-hair-co"

# FITUR Alamat Website Tenant (Dashboard Super Admin): domain root platform
# -- dipakai membentuk URL subdomain tenant (https://<slug>.<suffix>), SAMA
# PERSIS domain yang sudah diizinkan main.py::ALLOWED_ORIGIN_REGEX (CORS).
# Boleh dioverride lewat env var TENANT_SUBDOMAIN_SUFFIX kalau domain
# produksi berubah di masa depan -- satu-satunya tempat yang perlu disentuh.
TENANT_SUBDOMAIN_SUFFIX = os.environ.get("TENANT_SUBDOMAIN_SUFFIX", "rivoirsett.com")


def get_website_url(tenant: dict) -> str | None:
    """URL lengkap website satu tenant -- SEKADAR membentuk string dari data
    yang SUDAH ADA (custom_domain/slug), TIDAK PERNAH mengubah/menyimpan
    apa pun, dan TIDAK dipakai untuk resolusi tenant/otorisasi APAPUN (itu
    tetap murni lewat sesi login/slug eksplisit, lihat cari_tenant_publik())
    -- HANYA dipakai untuk tampilan kolom "Alamat Website" di Dashboard
    Super Admin.

    Prioritas: `custom_domain` (kolom SUDAH ADA di skema `tenants` sejak
    Phase 1, sebelumnya belum pernah dibaca/ditulis di mana pun) kalau
    tenant sudah pindah ke domain sendiri, else subdomain bawaan dari slug
    -- OTOMATIS mengikuti begitu custom_domain diisi/diubah kapan pun di
    masa depan, tanpa perlu logika tambahan di sini. None kalau tenant
    tidak punya keduanya (seharusnya tidak pernah terjadi untuk tenant yang
    dibuat lewat buat_tenant() -- slug WAJIB diisi -- dijaga defensif murni
    untuk data lama/tidak lengkap)."""
    custom_domain = (tenant.get("custom_domain") or "").strip()
    if custom_domain:
        if custom_domain.startswith("http://") or custom_domain.startswith("https://"):
            return custom_domain
        return f"https://{custom_domain}"
    slug = (tenant.get("slug") or "").strip()
    if slug:
        return f"https://{slug}.{TENANT_SUBDOMAIN_SUFFIX}"
    return None


def get_booking_url(tenant: dict) -> str | None:
    """FITUR URL Booking Publik per Tenant: URL lengkap halaman booking
    PUBLIK tenant -- SELALU subdomain berbasis `booking_slug` (BUKAN
    custom_domain, beda dari get_website_url() di atas -- booking_slug
    independen, bisa berbeda dari domain website tenant), diikuti path
    "/app/#/book" (SAMA PERSIS pola "Link Booking" yang sudah ada di
    Setting > Booking/booking.js -- lihat komentar BUGFIX di sana kenapa
    origin polos tanpa path salah) supaya link SELALU langsung berfungsi,
    tidak bergantung pada default routing subdomain kosong. None kalau
    tenant belum punya booking_slug sama sekali (seharusnya tidak pernah
    terjadi untuk tenant yang dibuat lewat buat_tenant() sejak fitur ini
    ada -- dijaga defensif untuk data lama sebelum migrasi backfill)."""
    booking_slug = (tenant.get("booking_slug") or "").strip()
    if not booking_slug:
        return None
    return f"https://{booking_slug}.{TENANT_SUBDOMAIN_SUFFIX}/app/#/book"


def _slugify_dasar(nama: str) -> str:
    """SAMA PERSIS algoritma yang dipakai routers/tenant_registration.py
    sebelumnya (dipusatkan di sini supaya `slug` DAN `booking_slug`
    memakai basis identik) -- SELURUH karakter selain huruf/angka dibuang
    TOTAL (BUKAN diganti "-"), sesuai spesifikasi produk eksplisit, mis.
    "MUGEN Hair Co." -> "mugenhairco"."""
    slug = re.sub(r"[^a-z0-9]+", "", (nama or "").strip().lower())
    return slug or "toko"


def _slug_dipakai(slug: str, kecuali_tenant_id: int | None = None) -> bool:
    """FITUR URL Booking Publik per Tenant: `slug` DAN `booking_slug`
    resolve lewat subdomain *.rivoirsett.com yang SAMA (lihat
    get_tenant_by_slug_atau_booking_slug()) -- jadi keduanya HARUS
    dianggap SATU pool keunikan (plus label sistem yang direservasi, lihat
    tenant_middleware.LABEL_BUKAN_TENANT) supaya tidak pernah ada dua
    tenant kebagian subdomain publik yang sama, apa pun kombinasi
    kolomnya. `kecuali_tenant_id` dipakai saat MENGEDIT booking_slug
    tenant yang sudah ada, supaya tenant itu tidak dianggap bertabrakan
    dengan slug/booking_slug MILIKNYA SENDIRI."""
    import tenant_middleware  # import lokal: hindari import siklik saat modul ini dimuat lebih dulu
    if slug in tenant_middleware.LABEL_BUKAN_TENANT:
        return True
    with get_conn() as conn:
        query = "SELECT id FROM tenants WHERE (slug = ? OR booking_slug = ?)"
        params = [slug, slug]
        if kecuali_tenant_id is not None:
            query += " AND id != ?"
            params.append(kecuali_tenant_id)
        row = conn.execute(query, params).fetchone()
        return row is not None


def buat_slug_unik(nama_barbershop: str, kecuali_tenant_id: int | None = None) -> str:
    """Angka collision LANGSUNG menempel tanpa pemisah (mis. "mugenhairco2",
    BUKAN "mugenhairco-2") -- SESUAI spesifikasi produk eksplisit. Dipakai
    baik untuk `slug` (saat tenant dibuat, lewat buat_tenant() di bawah)
    maupun `booking_slug` (saat diedit lewat Setting > Booking, lihat
    set_booking_slug())."""
    dasar = _slugify_dasar(nama_barbershop)
    slug = dasar
    percobaan = 1
    while _slug_dipakai(slug, kecuali_tenant_id):
        percobaan += 1
        slug = f"{dasar}{percobaan}"
    return slug


_BOOKING_SLUG_RE = re.compile(r"^[a-z0-9]+$")


def set_booking_slug(tenant_id: int, booking_slug: str) -> None:
    """FITUR URL Booking Publik per Tenant (item 7 spesifikasi): tenant
    mengubah booking_slug lewat Setting > Booking -- divalidasi FORMAT
    (huruf kecil + angka saja, sama seperti `slug`) dan KEUNIKAN (pool
    gabungan slug+booking_slug SELURUH tenant + label sistem, lihat
    _slug_dipakai()) SEBELUM disimpan. Link Booking & QR Code di frontend
    otomatis ikut berubah begitu ini disimpan (keduanya dibentuk dari
    booking_slug TERKINI setiap kali dibaca, TIDAK ADA state tersimpan
    terpisah, lihat get_booking_url())."""
    booking_slug = (booking_slug or "").strip().lower()
    if not booking_slug:
        raise ValueError("Booking slug tidak boleh kosong.")
    if not _BOOKING_SLUG_RE.match(booking_slug):
        raise ValueError("Booking slug hanya boleh berisi huruf kecil dan angka, tanpa spasi/karakter khusus.")
    if get_tenant(tenant_id) is None:
        raise ValueError("Tenant tidak ditemukan.")
    if _slug_dipakai(booking_slug, kecuali_tenant_id=tenant_id):
        raise ValueError(f"Booking slug '{booking_slug}' sudah dipakai, silakan pilih yang lain.")
    with get_conn() as conn:
        conn.execute("UPDATE tenants SET booking_slug = ? WHERE id = ?", (booking_slug, tenant_id))


def get_tenant(tenant_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        return dict(row) if row else None


def get_tenant_by_slug(slug: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None


def get_tenant_by_booking_slug(booking_slug: str):
    """FITUR URL Booking Publik per Tenant: kolom `booking_slug` TERPISAH
    dari `slug` (slug tetap dipakai subdomain dashboard/staff APA ADANYA,
    tidak pernah berubah otomatis) -- dipakai HANYA sebagai fallback lewat
    get_tenant_by_slug_atau_booking_slug() di bawah, TIDAK PERNAH dipanggil
    langsung untuk resolusi login/branding/Super Admin."""
    booking_slug = (booking_slug or "").strip().lower()
    if not booking_slug:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE booking_slug = ?", (booking_slug,)).fetchone()
        return dict(row) if row else None


def get_tenant_by_slug_atau_booking_slug(slug: str):
    """FITUR URL Booking Publik per Tenant: `slug` (subdomain dashboard/
    staff, PRIORITAS -- perilaku LAMA tidak berubah sama sekali) dulu, baru
    fallback ke `booking_slug` (URL booking publik customer, lihat
    set_booking_slug()) kalau tidak ketemu. Dipakai cari_tenant_publik()
    (endpoint publik booking/website/identitas) DAN
    auth.py::resolve_tenant_untuk_branding() (supaya Logo/Nama Bisnis/dst
    tetap tampil benar begitu customer membuka subdomain booking_slug) --
    TIDAK PERNAH dipakai resolusi sesi login (itu murni lewat token)."""
    return get_tenant_by_slug(slug) or get_tenant_by_booking_slug(slug)


def get_tenant_by_custom_domain(host: str):
    """FITUR Subdomain Otomatis per Tenant: fondasi resolusi Custom Domain
    (mis. `mugenhairco.com` milik tenant sendiri, BUKAN subdomain bawaan
    `mugenhairco.rivoirsett.com`) -- lihat tenant_middleware.py, dipanggil
    sebagai fallback KHUSUS kalau Host request TIDAK cocok pola subdomain
    `*.rivoirsett.com` sama sekali. Kolom `custom_domain` SUDAH ADA di
    skema `tenants` sejak Phase 1 tapi belum pernah dibaca untuk resolusi
    APAPUN sebelum ini (hanya dipakai get_website_url() untuk TAMPILAN) --
    TIDAK ADA endpoint tulis untuk kolom ini SAMA SEKALI sampai sekarang,
    jadi fallback ini murni "siap dipakai begitu fitur pengisian Custom
    Domain-nya sendiri dibuat" (tidak ada baris yang akan cocok sebelum
    itu, murni forward-compat sesuai permintaan -- TIDAK mengubah perilaku
    resolusi tenant manapun yang sudah berjalan). Pencocokan case-
    insensitive & mengabaikan skema/trailing slash (disimpan sebagai host
    polos, tapi dijaga defensif kalau suatu saat diisi dengan format URL
    penuh)."""
    host = (host or "").strip().lower()
    if not host:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tenants WHERE LOWER(REPLACE(REPLACE(custom_domain, 'https://', ''), 'http://', '')) = ?",
            (host,),
        ).fetchone()
        return dict(row) if row else None


def list_tenants():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tenants ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]


def tenant_aktif(tenant_id: int) -> bool:
    t = get_tenant(tenant_id)
    return bool(t and t["status"] == "aktif")


def cari_tenant_publik(slug: str | None):
    """FONDASI Multi-Tenant Phase 1: mekanisme SEMENTARA resolusi tenant
    untuk endpoint publik booking (tanpa sesi login, lihat
    routers/booking.py::resolve_tenant_publik()) -- resolusi PENUH lewat
    subdomain/custom domain per tenant ADA DI LUAR CAKUPAN Phase 1 (custom
    domain eksplisit di luar cakupan Phase 1, lihat roadmap audit Fase 2).
    `slug` kosong (None) = tenant default (SATU-SATUNYA tenant yang ada di
    deployment single-tenant SEKARANG) -- perilaku LAMA sebelum Phase 1
    TIDAK BERUBAH SAMA SEKALI selama frontend belum mengirim parameter ini.
    Return dict tenant (bukan cuma id) supaya caller bisa cek status
    aktif juga, atau None kalau slug diisi tapi tidak ditemukan.

    FITUR URL Booking Publik per Tenant: `slug` yang tidak ketemu lewat
    kolom `slug` di-fallback ke kolom `booking_slug` lewat
    get_tenant_by_slug_atau_booking_slug() -- SATU-SATUNYA perubahan di
    sini, transparan untuk SELURUH endpoint publik yang memanggil fungsi
    ini lewat resolve_tenant_publik() (routers/booking.py public_router,
    routers/website.py, routers/pengaturan.py identitas/logo publik),
    TIDAK ADA endpoint yang perlu diubah satu per satu."""
    if slug:
        return get_tenant_by_slug_atau_booking_slug(slug)
    return get_tenant_by_slug(SLUG_TENANT_DEFAULT)


def buat_tenant(slug: str, nama_barbershop: str, booking_slug: str | None = None) -> int:
    """Pembuatan tenant MINIMAL -- hanya baris `tenants` itu sendiri (belum
    membuat user Owner/data awal, itu tanggung jawab pemanggil, sama seperti
    _bootstrap_admin_pertama() di main.py membuat user pertama terpisah dari
    pembuatan tenant default). Dipakai untuk pengujian Phase 1 (Tenant B)
    dan fondasi provisioning Super Admin (lihat routers/superadmin.py).

    BUGFIX (ditemukan lewat laporan Komisi selalu Rp 0 untuk tenant hasil
    registrasi mandiri maupun provisioning Super Admin): SEBELUM perbaikan
    ini, fungsi "minimal" di atas benar-benar TIDAK menyeed satu setting
    pun -- get_setting()/_setting_float() di database.py diam-diam fallback
    ke "0" (BUKAN nilai default pabrik seperti persentase_komisi 40%) untuk
    SETIAP tenant yang dibuat lewat fungsi ini, sampai Owner-nya KEBETULAN
    membuka & menyimpan ulang setiap halaman Setting terkait sendiri. Kedua
    pemanggil (routers/tenant_registration.py registrasi mandiri &
    routers/superadmin.py provisioning manual) TIDAK PERNAH melakukan
    seeding tambahan apa pun setelah memanggil ini, jadi diperbaiki DI SINI
    -- satu-satunya titik pembuatan tenant baru. Dipilih DEFAULT_SETTINGS
    (bukan seluruh setting lain yang tersebar di banyak modul, mis. Bonus
    Service/Booking) karena itulah yang TERBUKTI menyebabkan bug yang
    dilaporkan; tenant yang SUDAH TERLANJUR ada sebelum perbaikan ini
    dibackfill terpisah lewat tenant_migrasi.py::
    _backfill_default_settings_semua_tenant() (jalan tiap boot)."""
    slug = (slug or "").strip().lower()
    nama_barbershop = (nama_barbershop or "").strip()
    if not slug:
        raise ValueError("Slug tenant tidak boleh kosong.")
    if not nama_barbershop:
        raise ValueError("Nama barbershop tidak boleh kosong.")
    # FITUR Subdomain Otomatis per Tenant: ditegakkan DI SINI (satu-satunya
    # titik pembuatan tenant, dipakai BAIK registrasi mandiri MAUPUN
    # provisioning manual Super Admin) supaya label subdomain yang
    # DIRESERVASI platform (admin/www/api/app/dst, lihat
    # tenant_middleware.py) TIDAK PERNAH bisa dipakai sebagai slug tenant
    # mana pun -- terutama "admin", yang HARUS selalu berarti Dashboard
    # Super Admin (admin.rivoirsett.com), tidak pernah tenant mana pun.
    import tenant_middleware  # import lokal: hindari import siklik saat modul ini dimuat lebih dulu
    if slug in tenant_middleware.LABEL_BUKAN_TENANT:
        raise ValueError(f"Slug '{slug}' adalah nama sistem yang direservasi, tidak bisa dipakai tenant.")
    # FITUR URL Booking Publik per Tenant: dicek terhadap pool GABUNGAN
    # slug+booking_slug SELURUH tenant (_slug_dipakai(), BUKAN lagi hanya
    # get_tenant_by_slug()) -- supaya slug baru TIDAK PERNAH bisa
    # bertabrakan dengan booking_slug tenant lain yang sudah diedit lewat
    # Setting > Booking (keduanya resolve lewat subdomain *.rivoirsett.com
    # yang SAMA, lihat get_tenant_by_slug_atau_booking_slug()).
    if _slug_dipakai(slug):
        raise ValueError(f"Slug '{slug}' sudah dipakai tenant lain.")
    # FITUR URL Booking Publik per Tenant: booking_slug OTOMATIS dibuat
    # saat tenant pertama kali dibuat (spesifikasi item 2). Kalau `slug`
    # yang diberikan pemanggil KEBETULAN sudah berformat valid (huruf kecil
    # + angka saja -- SELALU benar untuk slug hasil buat_slug_unik(), TIDAK
    # SELALU benar untuk slug yang diketik manual lewat form Super Admin,
    # yang boleh mengandung "-" dst) dipakai ulang APA ADANYA (paling
    # intuitif, booking_slug = slug). Kalau TIDAK (mis. mengandung "-"),
    # dihitung ulang dari nama_barbershop lewat buat_slug_unik() supaya
    # booking_slug SELALU valid sejak awal dibuat -- tidak pernah gagal
    # validasi format begitu Owner sekadar menyimpan ulang nilai yang sama
    # tanpa mengubah apa pun lewat Setting > Booking (lihat set_booking_slug()).
    # TIDAK PERNAH ikut berubah otomatis kalau nama_barbershop diedit
    # belakangan (kolom terpisah, hanya berubah lewat set_booking_slug()
    # eksplisit) -- caller boleh override lewat parameter `booking_slug`
    # kalau perlu nilai lain.
    booking_slug = (booking_slug or "").strip().lower()
    if not booking_slug:
        booking_slug = slug if _BOOKING_SLUG_RE.match(slug) else buat_slug_unik(nama_barbershop)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tenants (slug, nama_barbershop, status, booking_slug, created_at) VALUES (?, ?, 'aktif', ?, ?)",
            (slug, nama_barbershop, booking_slug, now),
        )
        tenant_id = cur.lastrowid
        # Tenant BARU, mustahil baris settings-nya sudah ada -- INSERT polos
        # (bukan ON CONFLICT DO NOTHING) cukup, konsisten dengan fungsi lain
        # di modul ini yang juga tidak defensif berlebihan untuk kasus yang
        # secara struktural tidak mungkin terjadi.
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (f"{tenant_id}:{key}", value))
        return tenant_id


def get_tenant_by_email(email: str):
    """FONDASI Multi-Tenant Phase 5 (Landing Page SaaS): dipakai Register
    publik untuk menolak email yang sudah dipakai tenant lain -- lihat
    landing_migrasi.py untuk kolom `email` (baru) + unique index-nya."""
    email = (email or "").strip().lower()
    if not email:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE LOWER(email) = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_tenant_by_whatsapp(whatsapp: str):
    """Sama seperti get_tenant_by_email() tapi untuk kolom `whatsapp`."""
    whatsapp = (whatsapp or "").strip()
    if not whatsapp:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE whatsapp = ?", (whatsapp,)).fetchone()
        return dict(row) if row else None


def set_registrant_info(tenant_id: int, owner_name: str, email: str, whatsapp: str) -> None:
    """FONDASI Multi-Tenant Phase 5: dipanggil SEKALI, tepat setelah
    buat_tenant() berhasil di alur Register publik -- buat_tenant() sendiri
    SENGAJA TIDAK diubah (dipakai juga oleh provisioning Super Admin yang
    tidak pernah mengisi field ini) supaya alur lama tetap identik."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenants SET owner_name = ?, email = ?, whatsapp = ? WHERE id = ?",
            (owner_name, email, whatsapp, tenant_id),
        )


def set_status(tenant_id: int, status: str) -> None:
    """FONDASI Multi-Tenant Phase 2.1 (Super Admin Dashboard): aktifkan/
    nonaktifkan satu tenant. Efeknya langsung terasa tanpa tunggu token
    expired -- get_current_user() (auth.py) sudah menolak SEMUA request user
    tenant yang di-nonaktifkan sejak Phase 1, jadi fungsi ini murni mengubah
    kolom `status`, tidak perlu menyentuh baris user/data lain sama sekali."""
    if status not in STATUS_VALID:
        raise ValueError(f"Status harus salah satu dari: {', '.join(sorted(STATUS_VALID))}.")
    if get_tenant(tenant_id) is None:
        raise ValueError("Tenant tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("UPDATE tenants SET status = ? WHERE id = ?", (status, tenant_id))
