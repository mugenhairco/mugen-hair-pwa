"""
tenant_middleware.py — FONDASI Multi-Tenant Phase 2.0: resolusi tenant di
lapisan middleware (SATU titik, dipakai SEMUA endpoint publik/login)
=============================================================================
Phase 1 memilih mekanisme `?tenant=<slug>` (query string) untuk resolusi
tenant endpoint publik (lihat auth.py::resolve_tenant_publik(), yang
secara eksplisit menyebut subdomain/custom domain "di luar cakupan Phase
1"). Middleware ini TIDAK mengganti mekanisme itu -- ia MENAMBAH dua
sumber tambahan (header eksplisit, subdomain OPSIONAL) yang di-resolve
SEKALI per request lalu ditaruh di `request.state.requested_tenant_slug`,
supaya:

1. Query string tetap berfungsi identik seperti Phase 1 (prioritas utama,
   endpoint yang sudah memanggil `resolve_tenant_publik(tenant=...)` tidak
   perlu berubah sama sekali).
2. Endpoint yang TIDAK punya slot query string alami untuk slug (mis.
   POST /api/auth/login, body JSON bukan query string) tetap bisa
   menerima slug lewat header `X-Tenant-Slug` TANPA setiap router harus
   menulis parsing header-nya sendiri berulang-ulang.
3. Deployment MASA DEPAN yang memakai subdomain per tenant (mis.
   toko-a.mugenhair.app) otomatis ke-resolve TANPA perubahan kode
   endpoint apa pun -- HANYA aktif kalau Owner mengisi environment
   variable `TENANT_SUBDOMAIN_BASE_DOMAIN` (kosong = fitur ini mati
   total -- deployment produksi saat ini (rivoirsett.com/api.rivoirsett.com)
   TIDAK mengisinya, jadi TIDAK terpengaruh sama sekali, byte-identik
   dengan sebelum middleware ini ada).

Urutan prioritas (yang pertama ketemu & tidak kosong yang dipakai):
  query string `?tenant=` > header `X-Tenant-Slug` > subdomain Host.

PENTING: middleware ini HANYA menaruh *kandidat* slug ke request.state --
TIDAK PERNAH memutuskan sendiri apakah slug itu valid/aktif (itu tetap
tanggung jawab tenant_db.py, dipanggil dari resolve_tenant_publik()/
routers/auth_router.py, sama seperti sebelumnya). Middleware murni lapisan
"cari input dari mana", bukan lapisan otorisasi.
"""

import os

from starlette.middleware.base import BaseHTTPMiddleware

# Kosong (default) = subdomain-based tenant resolution MATI TOTAL -- diisi
# Owner hanya kalau/ketika deployment production benar-benar pindah ke
# subdomain wildcard per tenant (di luar cakupan Phase 2.0 ini, murni
# disiapkan supaya tidak perlu ubah kode lagi nanti).
SUBDOMAIN_BASE_DOMAIN = os.environ.get("TENANT_SUBDOMAIN_BASE_DOMAIN", "").strip().lower()

# Label subdomain yang BUKAN slug tenant walau base domain sudah dikonfigurasi
# (mis. "www.mugenhair.app" bukan tenant bernama "www").
_LABEL_BUKAN_TENANT = {"www", "api", "app"}


def _slug_dari_subdomain(host: str) -> str | None:
    if not SUBDOMAIN_BASE_DOMAIN or not host:
        return None
    host = host.split(":", 1)[0].strip().lower()  # buang port kalau ada
    if not host.endswith("." + SUBDOMAIN_BASE_DOMAIN):
        return None
    sisa = host[: -(len(SUBDOMAIN_BASE_DOMAIN) + 1)]
    if not sisa or "." in sisa or sisa in _LABEL_BUKAN_TENANT:
        return None
    return sisa


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        slug = (
            request.query_params.get("tenant")
            or request.headers.get("x-tenant-slug")
            or _slug_dari_subdomain(request.headers.get("host", ""))
        )
        request.state.requested_tenant_slug = (slug or "").strip() or None
        return await call_next(request)
