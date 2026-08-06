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


def get_tenant(tenant_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        return dict(row) if row else None


def get_tenant_by_slug(slug: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None


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
    aktif juga, atau None kalau slug diisi tapi tidak ditemukan."""
    if slug:
        return get_tenant_by_slug(slug)
    return get_tenant_by_slug(SLUG_TENANT_DEFAULT)


def buat_tenant(slug: str, nama_barbershop: str) -> int:
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
    if get_tenant_by_slug(slug) is not None:
        raise ValueError(f"Slug '{slug}' sudah dipakai tenant lain.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tenants (slug, nama_barbershop, status, created_at) VALUES (?, ?, 'aktif', ?)",
            (slug, nama_barbershop, now),
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
