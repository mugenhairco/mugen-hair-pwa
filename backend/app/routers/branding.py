"""routers/branding.py — FONDASI Multi-Tenant Phase 2.2: Tenant & Platform Branding
=============================================================================
Endpoint PUBLIK TUNGGAL (GET /api/tenant/branding) -- satu-satunya sumber
branding yang dipakai frontend (brand.js) di SEMUA konteks: halaman Login
sebelum tenant diketahui, sudah login sebagai Owner/Admin/Barber tenant
tertentu, atau sebagai Super Admin (tidak terikat tenant mana pun).
Resolusi tenant lewat resolve_tenant_untuk_branding() di auth.py -- lihat
docstring-nya untuk perbedaan dengan resolve_tenant_publik()/
resolve_tenant_hibrid() yang dipakai endpoint lain (TIDAK diubah).

Endpoint TULIS (PUT branding, upload/hapus favicon) ada di
routers/pengaturan.py, sekelompok dengan endpoint Identitas & Logo yang
sudah ada (pola yang sama, ber-otentikasi + require_permission)."""

from fastapi import APIRouter, Depends

import branding_db
from auth import resolve_tenant_untuk_branding

router = APIRouter(prefix="/api/tenant", tags=["branding"])

# FONDASI Multi-Tenant Phase 2.2: Platform Branding -- identitas SISTEM
# (bukan milik tenant mana pun), TIDAK ADA endpoint tulis untuk ini sama
# sekali (tenant tidak bisa mengubahnya) -- fallback SATU-SATUNYA saat
# tenant belum/tidak bisa dikenali (lihat resolve_tenant_untuk_branding()).
# "Rivoir" BUKAN nama tenant sungguhan -- identitas developer platform ini.
PLATFORM_BRANDING = {
    "nama_barbershop": "Rivoir",
    "email": "",
    "logo_url": None,
    "favicon_url": None,
    "tagline": "",
    "alamat": "",
    "whatsapp": "",
    "primary_color": "",
    "secondary_color": "",
    "website_url": "",
    "is_platform_default": True,
}


@router.get("/branding")
def branding(tenant_id: int | None = Depends(resolve_tenant_untuk_branding)):
    """`logo_url`/`favicon_url` bernilai None kalau tenant BELUM upload
    sendiri (baik karena memang belum sempat, atau karena ini branding
    platform) -- frontend (brand.js) menafsirkan None SAMA di kedua kasus:
    pakai logo/favicon platform (statis, sudah ada di index.html/manifest.json)
    sebagai fallback, tidak perlu endpoint terpisah untuk itu."""
    if tenant_id is None:
        return PLATFORM_BRANDING
    hasil = branding_db.get_branding(tenant_id=tenant_id)
    hasil["is_platform_default"] = False
    return hasil
