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

from datetime import datetime

from database import get_conn

STATUS_VALID = {"aktif", "nonaktif"}

# SAMA PERSIS dengan tenant_migrasi.py::SLUG_TENANT_DEFAULT (jalur SQLite) /
# postgres_schema.py::TENANT_DEFAULT_SLUG (jalur Postgres) -- diduplikasi di
# sini murni supaya modul ini tidak perlu import salah satu dari keduanya
# (tenant_db.py dipakai auth.py & routers/booking.py, TIDAK terikat jalur
# SQLite/Postgres mana pun secara langsung).
SLUG_TENANT_DEFAULT = "mugen-hair-co"


def get_tenant(tenant_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        return dict(row) if row else None


def get_tenant_by_slug(slug: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE slug = ?", (slug,)).fetchone()
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
    dan fondasi provisioning Super Admin (lihat routers/superadmin.py)."""
    slug = (slug or "").strip().lower()
    nama_barbershop = (nama_barbershop or "").strip()
    if not slug:
        raise ValueError("Slug tenant tidak boleh kosong.")
    if not nama_barbershop:
        raise ValueError("Nama barbershop tidak boleh kosong.")
    if get_tenant_by_slug(slug) is not None:
        raise ValueError(f"Slug '{slug}' sudah dipakai tenant lain.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tenants (slug, nama_barbershop, status, created_at) VALUES (?, ?, 'aktif', ?)",
            (slug, nama_barbershop, now),
        )
        return cur.lastrowid


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
