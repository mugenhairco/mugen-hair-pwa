"""
tenant_middleware.py — Resolusi tenant di lapisan middleware (SATU titik,
dipakai SEMUA endpoint publik/login)
=============================================================================
Sejak Phase 1, resolusi tenant endpoint publik utamanya lewat mekanisme
`?tenant=<slug>` (query string, lihat auth.py::resolve_tenant_publik()).
Middleware ini MENAMBAH dua sumber lain (header eksplisit, subdomain) yang
di-resolve SEKALI per request lalu ditaruh di
`request.state.requested_tenant_slug`, supaya:

1. Query string tetap berfungsi identik seperti Phase 1 (prioritas utama,
   endpoint yang sudah memanggil `resolve_tenant_publik(tenant=...)` tidak
   perlu berubah sama sekali).
2. Endpoint yang TIDAK punya slot query string alami untuk slug (mis.
   POST /api/auth/login, body JSON bukan query string) tetap bisa
   menerima slug lewat header `X-Tenant-Slug` TANPA setiap router harus
   menulis parsing header-nya sendiri berulang-ulang.
3. FITUR Subdomain Otomatis per Tenant: SETIAP request ke subdomain
   `<slug>.rivoirsett.com` otomatis dikenali tenant-nya TANPA konfigurasi
   DNS/kode tambahan apa pun per tenant baru -- wildcard DNS (*.rivoirsett.com,
   dikonfigurasi SEKALI di Cloudflare/registrar, di luar cakupan kode ini)
   membuat SETIAP subdomain sampai ke server yang sama, middleware inilah
   yang membaca header Host dan memetakannya ke slug tenant. AKTIF SECARA
   DEFAULT (base domain "rivoirsett.com") -- boleh dioverride/dimatikan
   lewat environment variable TENANT_SUBDOMAIN_SUFFIX kalau domain produksi
   berubah di masa depan (satu-satunya tempat yang perlu disentuh, kosongkan
   env var ini untuk MEMATIKAN resolusi subdomain sama sekali).
4. FITUR Custom Domain (persiapan): kalau Host request SAMA SEKALI TIDAK
   cocok pola subdomain `*.rivoirsett.com` (mis. tenant sudah pindah ke
   domain sendiri, `mugenhairco.com`), dicoba SEKALI lagi lewat
   tenant_db.get_tenant_by_custom_domain() -- kolom `custom_domain` SUDAH
   ADA di skema `tenants` tapi belum ada endpoint tulis untuk mengisinya
   (murni forward-compat, TIDAK ADA baris yang akan cocok sampai fitur
   pengisiannya sendiri dibuat) -- begitu ada, tenant tersebut otomatis
   ter-resolve lewat mekanisme SAMA PERSIS (request.state.requested_tenant_slug)
   TANPA perlu mengubah endpoint/frontend mana pun lagi.

Urutan prioritas (yang pertama ketemu & tidak kosong yang dipakai):
  query string `?tenant=` > header `X-Tenant-Slug` > subdomain Host >
  custom domain Host.

PENTING: middleware ini HANYA menaruh *kandidat* slug ke request.state --
TIDAK PERNAH memutuskan sendiri apakah slug itu valid/aktif (itu tetap
tanggung jawab tenant_db.py, dipanggil dari resolve_tenant_publik()/
routers/auth_router.py, sama seperti sebelumnya). Middleware murni lapisan
"cari input dari mana", bukan lapisan otorisasi.
"""

import os

from starlette.middleware.base import BaseHTTPMiddleware

# SAMA PERSIS dengan tenant_db.py::TENANT_SUBDOMAIN_SUFFIX (diduplikasi di
# sini murni supaya modul ini tidak perlu import tenant_db -- pola yang
# sama dengan SLUG_TENANT_DEFAULT yang diduplikasi lintas
# tenant_migrasi.py/postgres_schema.py/tenant_db.py). AKTIF secara default
# ("rivoirsett.com") -- kosongkan env var ini untuk mematikan resolusi
# subdomain sama sekali (mis. deployment yang sengaja belum memakai
# subdomain wildcard apa pun).
SUBDOMAIN_BASE_DOMAIN = os.environ.get("TENANT_SUBDOMAIN_SUFFIX", "rivoirsett.com").strip().lower()

# Label subdomain yang BUKAN slug tenant walau base domain cocok --
# "admin" WAJIB ada di sini (Super Admin login lewat admin.rivoirsett.com,
# TIDAK PERNAH lewat subdomain tenant mana pun, lihat routers/superadmin.py)
# -- juga ditegakkan di sisi PENDAFTARAN (tenant_registration.py TIDAK
# PERNAH menghasilkan slug otomatis yang bertabrakan dengan label-label ini,
# dan Super Admin manual (routers/superadmin.py::buat_tenant()) ditolak
# eksplisit kalau mencoba memakai slug yang sama).
LABEL_BUKAN_TENANT = {"www", "api", "app", "admin", "mail", "ftp"}


def _slug_dari_subdomain(host: str) -> str | None:
    if not SUBDOMAIN_BASE_DOMAIN or not host:
        return None
    host = host.split(":", 1)[0].strip().lower()  # buang port kalau ada
    if not host.endswith("." + SUBDOMAIN_BASE_DOMAIN):
        return None
    sisa = host[: -(len(SUBDOMAIN_BASE_DOMAIN) + 1)]
    if not sisa or "." in sisa or sisa in LABEL_BUKAN_TENANT:
        return None
    return sisa


def _slug_dari_custom_domain(host: str) -> str | None:
    """FITUR Custom Domain (persiapan, lihat docstring modul): HANYA dicoba
    kalau Host-nya SAMA SEKALI bukan bentuk subdomain rivoirsett.com --
    menghindari lookup database sia-sia untuk mayoritas mutlak request
    (subdomain tenant biasa/root domain) yang sudah pasti tertangkap oleh
    _slug_dari_subdomain() di atas."""
    if not host:
        return None
    host_polos = host.split(":", 1)[0].strip().lower()
    if SUBDOMAIN_BASE_DOMAIN and (
        host_polos == SUBDOMAIN_BASE_DOMAIN or host_polos.endswith("." + SUBDOMAIN_BASE_DOMAIN)
    ):
        return None  # domain platform sendiri -- bukan kandidat custom domain tenant
    import tenant_db  # import lokal: hindari import siklik (tenant_db.py -> database.py)
    t = tenant_db.get_tenant_by_custom_domain(host_polos)
    return t["slug"] if t else None


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        slug = (
            request.query_params.get("tenant")
            or request.headers.get("x-tenant-slug")
            or _slug_dari_subdomain(host)
            or _slug_dari_custom_domain(host)
        )
        request.state.requested_tenant_slug = (slug or "").strip() or None
        return await call_next(request)
