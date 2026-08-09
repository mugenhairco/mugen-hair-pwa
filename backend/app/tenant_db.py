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
from db_compat import IntegrityError

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
        # HARDENING: lapis pertahanan TERAKHIR terhadap race TOCTOU yang
        # SAMA seperti buat_tenant() di atas -- SELALU UPDATE baris yang
        # SUDAH ADA (tenant_id sudah dipastikan ada lewat get_tenant() di
        # atas), TIDAK PERNAH membuat baris baru.
        try:
            conn.execute("UPDATE tenants SET booking_slug = ? WHERE id = ?", (booking_slug, tenant_id))
        except IntegrityError:
            raise ValueError(f"Booking slug '{booking_slug}' sudah dipakai, silakan pilih yang lain.")


_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def set_slug(tenant_id: int, slug_baru: str) -> None:
    """FITUR Migrasi Subdomain (arsitektur SaaS subdomain penuh): ganti
    `slug` tenant -- subdomain dashboard/login/booking UTAMA tenant
    ({slug}.rivoirsett.com), berbeda dari booking_slug yang murni untuk
    URL booking publik custom (lihat set_booking_slug()). `slug` immutable
    di luar jalur ini (satu-satunya cara mengubahnya setelah tenant
    dibuat, dipakai Super Admin lewat PUT /api/superadmin/tenants/{id}/
    slug -- routers/superadmin.py). Divalidasi FORMAT (label DNS valid --
    huruf kecil/angka/dash, tidak diawali/diakhiri dash, BEDA dari
    _BOOKING_SLUG_RE yang tidak mengizinkan dash sama sekali) dan
    KEUNIKAN (pool gabungan slug+booking_slug SELURUH tenant + label
    sistem reservasi, lewat _slug_dipakai() yang sama dipakai
    set_booking_slug()) SEBELUM disimpan.

    SENGAJA TIDAK memblokir mengganti slug tenant SLUG_TENANT_DEFAULT --
    justru itulah pemakaian UTAMANYA (migrasi tenant Mugen dari
    "mugen-hair-co" ke "mugen" saat arsitektur pindah ke subdomain penuh,
    root domain tidak lagi melayani data tenant apa pun). Larangan
    menghapus tenant default (lihat hapus_tenant()) TIDAK berlaku di sini
    -- mengganti nama beda dengan menghapus, tenant & seluruh datanya
    tetap utuh, hanya `slug`-nya yang berubah."""
    slug_baru = (slug_baru or "").strip().lower()
    if not slug_baru:
        raise ValueError("Slug tidak boleh kosong.")
    if not _SLUG_RE.match(slug_baru):
        raise ValueError(
            "Slug hanya boleh berisi huruf kecil, angka, dan tanda hubung (-), "
            "tidak boleh diawali/diakhiri tanda hubung."
        )
    if get_tenant(tenant_id) is None:
        raise ValueError("Tenant tidak ditemukan.")
    if _slug_dipakai(slug_baru, kecuali_tenant_id=tenant_id):
        raise ValueError(f"Slug '{slug_baru}' sudah dipakai, silakan pilih yang lain.")
    with get_conn() as conn:
        # HARDENING: lapis pertahanan TERAKHIR terhadap race TOCTOU,
        # pola SAMA seperti set_booking_slug()/buat_tenant() di atas.
        try:
            conn.execute("UPDATE tenants SET slug = ? WHERE id = ?", (slug_baru, tenant_id))
        except IntegrityError:
            raise ValueError(f"Slug '{slug_baru}' sudah dipakai, silakan pilih yang lain.")


def get_tenant(tenant_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        return dict(row) if row else None


def slug_untuk_url_media(tenant_id: int | None) -> str:
    """AUDIT 404 file media (Logo/Foto Karyawan/dst): endpoint GET yang
    menyajikan bytes gambar (mis. /api/pengaturan/logo, /api/pengaturan/
    favicon, /api/public/booking/barber-foto/{id}) diakses browser lewat
    tag <img src="...">, BUKAN fetch()/XHR -- tag <img> TIDAK PERNAH bisa
    menyertakan header Authorization (Bearer token) ATAUPUN header Origin
    (browser hanya mengirim Origin untuk permintaan cross-origin lewat
    fetch()/XHR, TIDAK untuk permintaan subresource sederhana seperti
    <img>/<script>/<link> -- lihat tenant_middleware.py::
    _hostname_dari_origin_atau_host()). Host request yang sampai ke backend
    SELALU "api.rivoirsett.com" (domain API tetap, beda dari subdomain
    tenant di browser -- lihat docstring tenant_middleware.py), dan "api"
    sendiri ada di LABEL_BUKAN_TENANT -- jadi middleware TIDAK PERNAH bisa
    menyimpulkan tenant dari permintaan <img> semacam ini lewat sinyal
    manapun KECUALI query string `?tenant=<slug>` di URL-nya sendiri (satu-
    satunya sinyal yang tag <img> BISA bawa, karena itu bagian dari `src`).

    Dipakai endpoint JSON yang SUDAH berhasil resolve tenant_id-nya sendiri
    (identitas/branding/daftar barber publik) untuk menyisipkan slug ke
    *_url yang mereka kembalikan, supaya permintaan <img> BERIKUTNYA yang
    memuat url itu ikut membawa sinyal yang sama. Return "" (bukan None)
    kalau tenant_id kosong/tenant tidak ditemukan/belum punya slug, supaya
    pemanggil bisa langsung menyisipkan hasilnya tanpa cek None terpisah."""
    if tenant_id is None:
        return ""
    t = get_tenant(tenant_id)
    return (t.get("slug") or "") if t else ""


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
    """Resolusi tenant untuk endpoint publik (tanpa sesi login, lihat
    routers/booking.py::resolve_tenant_publik()) -- `slug` ketemu lewat
    kolom `slug` ATAU `booking_slug` (get_tenant_by_slug_atau_booking_slug())
    dipakai SELURUH endpoint publik yang memanggil fungsi ini lewat
    resolve_tenant_publik() (routers/booking.py public_router,
    routers/website.py, routers/pengaturan.py identitas/logo publik).
    Return dict tenant (bukan cuma id) supaya caller bisa cek status
    aktif juga.

    HOTFIX Migrasi Subdomain (arsitektur SaaS subdomain penuh): `slug`
    kosong SEKARANG return None (BUKAN lagi diam-diam jatuh ke
    SLUG_TENANT_DEFAULT seperti sebelum migrasi ini) -- root domain
    (rivoirsett.com, tanpa subdomain tenant apa pun) TIDAK BOLEH LAGI
    diam-diam menyajikan data tenant mana pun (bahkan tenant default
    sekalipun); caller (resolve_tenant_publik(), auth.py) sudah menangani
    None dengan 404 "Tenant tidak ditemukan" -- konsisten dengan
    resolve_tenant_untuk_branding() yang SEJAK AWAL sudah begini (lihat
    docstringnya). TIDAK ADA lagi konsep "tenant default" untuk resolusi
    endpoint publik -- SETIAP tenant, termasuk yang pertama kali dibuat,
    HANYA bisa diakses lewat slug/booking_slug/subdomain miliknya sendiri
    yang eksplisit."""
    if not slug:
        return None
    return get_tenant_by_slug_atau_booking_slug(slug)


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
        # HARDENING (crash produksi "duplicate key value violates unique
        # constraint" saat startup, lihat booking_slug_migrasi.py/
        # postgres_schema.py::_backfill_booking_slug() untuk penjelasan akar
        # masalah race SEJENIS): _slug_dipakai() di atas adalah cek
        # "terlebih dahulu" (TOCTOU -- masih ada celah waktu SANGAT kecil
        # antara cek itu dan INSERT ini kalau dua request/proses berbarengan
        # membuat tenant dengan slug/booking_slug yang SAMA persis).
        # try/except di sini SATU-SATUNYA lapis pertahanan TERAKHIR --
        # mengubah IntegrityError mentah dari database (yang kalau lolos
        # akan jadi HTTP 500 tak jelas ke pemanggil) jadi ValueError yang
        # SAMA persis pesannya dengan hasil cek di atas, BUKAN membuat
        # baris tenant baru yang "menimpa" yang sudah ada -- INSERT yang
        # gagal TETAP gagal total (tidak ada baris yatim tersisa).
        try:
            cur = conn.execute(
                "INSERT INTO tenants (slug, nama_barbershop, status, booking_slug, created_at) "
                "VALUES (?, ?, 'aktif', ?, ?)",
                (slug, nama_barbershop, booking_slug, now),
            )
        except IntegrityError:
            raise ValueError(f"Slug '{slug}' sudah dipakai tenant lain.")
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


def hapus_tenant(tenant_id: int) -> dict:
    """FITUR Hapus Tenant (Super Admin Dashboard): penghapusan PERMANEN satu
    tenant beserta SELURUH data yang menjadi miliknya -- TIDAK bisa
    dibatalkan, TIDAK ada mekanisme undo. Dipakai untuk membersihkan tenant
    testing/development, lihat routers/superadmin.py::hapus_tenant() untuk
    lapis konfirmasi tambahan (harus mengetik ulang slug tenant) sebelum
    endpoint ini pernah dipanggil.

    DUA PENJAGA KESELAMATAN KERAS (tidak bisa dilewati parameter apa pun):
    1. Tenant dengan kolom `is_toko_utama = True` TIDAK PERNAH bisa dihapus
       lewat fungsi ini, apa pun alasannya -- konsisten dengan aturan yang
       berlaku SELAMA proyek ini ("jangan pernah menghapus/mengubah data
       toko utama produksi").
       INSIDEN (HOTFIX Migrasi Subdomain): SEBELUM perbaikan ini, penjaga
       ini mengecek `tenant["slug"] == SLUG_TENANT_DEFAULT` -- begitu slug
       toko utama diganti lewat fitur "Ubah Slug" (mis. "mugen-hair-co" ->
       "mugen"), pengecekan itu SELALU gagal cocok sejak saat itu, dan
       proteksinya diam-diam berhenti berlaku untuk tenant itu. Diperbaiki
       dengan flag PERMANEN `is_toko_utama` (lihat
       tenant_migrasi.py/postgres_schema.py::_backfill_toko_utama() --
       di-set SEKALI SAJA saat migrasi, TIDAK PERNAH berubah lagi apa pun
       yang terjadi pada slug tenant itu setelahnya) -- TIDAK terikat slug
       sama sekali lagi.
    2. Tidak bisa menghapus tenant TERAKHIR yang tersisa -- aplikasi ini
       butuh minimal SATU tenant untuk tetap berfungsi (auth.py/tenant_
       middleware.py mengasumsikan selalu ada tenant default).

    Urutan DELETE di bawah mengikuti PERSIS seluruh foreign key di skema
    (lihat postgres_schema.py::_TABLES / tenant_migrasi.py) -- anak
    (leaf) dihapus dulu, baru tabel induk/root, supaya tidak pernah
    melanggar constraint DAN tidak meninggalkan orphan record sama sekali.
    SATU transaksi (lewat get_conn() yang sama seperti seluruh modul ini,
    otomatis bekerja di SQLite maupun PostgreSQL lewat db_compat) --
    kalau ADA SATU SAJA langkah yang gagal, SEMUANYA otomatis rollback,
    tidak ada penghapusan sebagian.

    `settings`/`file_asset` TIDAK punya kolom tenant_id -- diisolasi lewat
    prefix "<tenant_id>:" di kolom key (lihat _kunci_tenant() di
    database.py/postgres_schema.py). Pola LIKE dihitung PENUH di Python
    lalu dikirim sebagai SATU parameter (BUKAN digabung pakai `||` di teks
    SQL) -- karakter '%' literal di TEKS query (bukan di dalam parameter)
    akan disalahartikan psycopg2 sebagai placeholder format-string
    (jebakan SAMA PERSIS yang sudah didokumentasikan di postgres_schema.py
    soal `_TABLES`, ditemukan lagi di sini lewat pengujian terhadap
    PostgreSQL sungguhan -- "IndexError: tuple index out of range").
    Portable di kedua dialek dan TIDAK PERNAH salah cocok dengan tenant
    lain (mis. tenant id=2 tidak pernah cocok dengan prefix "20:" atau
    "23:", karena karakter SETELAH digit id harus persis ':').

    Return dict tenant yang baru saja dihapus (snapshot SEBELUM
    dihapus -- dipakai pemanggil untuk audit log & pesan konfirmasi ke
    Super Admin, lihat superadmin_audit_db.catat())."""
    tenant = get_tenant(tenant_id)
    if tenant is None:
        raise ValueError("Tenant tidak ditemukan.")
    if tenant.get("is_toko_utama"):
        raise ValueError(f"Tenant '{tenant['slug']}' adalah toko utama, tidak bisa dihapus.")
    if len(list_tenants()) <= 1:
        raise ValueError("Tidak bisa menghapus satu-satunya tenant yang tersisa.")

    with get_conn() as conn:
        conn.execute(
            "DELETE FROM transaksi_detail WHERE transaksi_id IN ("
            "SELECT tr.id FROM transaksi tr JOIN barbers b ON b.id = tr.barber_id WHERE b.tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM kasbon_pembayaran WHERE kasbon_id IN ("
            "SELECT k.id FROM kasbon k JOIN barbers b ON b.id = k.barber_id WHERE b.tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM booking_items WHERE booking_id IN (SELECT id FROM bookings WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM produk_mutasi WHERE produk_id IN (SELECT id FROM produk WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM email_verification_tokens WHERE user_id IN (SELECT id FROM users WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM password_reset_tokens WHERE user_id IN (SELECT id FROM users WHERE tenant_id = ?)",
            (tenant_id,))
        # pengeluaran mereferensikan kas_penyesuaian_id & reimburse_id --
        # WAJIB dihapus sebelum keduanya.
        conn.execute("DELETE FROM pengeluaran WHERE tenant_id = ?", (tenant_id,))
        conn.execute(
            "DELETE FROM transaksi WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM slip_gaji WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM kasbon WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM komisi_penyesuaian WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM reimburse WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM izin_cuti WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM data_non_barber WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute(
            "DELETE FROM absensi_libur WHERE barber_id IN (SELECT id FROM barbers WHERE tenant_id = ?)",
            (tenant_id,))
        conn.execute("DELETE FROM closed_slot WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM bookings WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM pemasukan WHERE tenant_id = ?", (tenant_id,))
        # users.barber_id -> barbers, WAJIB dihapus sebelum barbers.
        conn.execute("DELETE FROM users WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM kas_penyesuaian WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM kas_saldo_awal WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM website_gallery WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM toko_libur WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM produk WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM services WHERE tenant_id = ?", (tenant_id,))
        # Root: barbers -- HANYA setelah SEMUA anak di atas bersih.
        conn.execute("DELETE FROM barbers WHERE tenant_id = ?", (tenant_id,))
        _pola_prefix = f"{tenant_id}:%"
        conn.execute("DELETE FROM settings WHERE key LIKE ?", (_pola_prefix,))
        conn.execute("DELETE FROM file_asset WHERE key LIKE ?", (_pola_prefix,))
        conn.execute("DELETE FROM tenant_subscriptions WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM tenant_subscription_payments WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM subscription_invoices WHERE tenant_id = ?", (tenant_id,))
        # Riwayat audit LAMA milik tenant ini ikut dihapus -- entri audit
        # BARU untuk aksi penghapusan ini sendiri dicatat TERPISAH oleh
        # pemanggil (routers/superadmin.py) SETELAH fungsi ini selesai,
        # lihat superadmin_audit_db.catat().
        conn.execute("DELETE FROM superadmin_audit_log WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))

    return tenant


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
