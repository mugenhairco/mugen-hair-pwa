"""Regresi Phase 2.0: TenantResolutionMiddleware (tenant_middleware.py).

Resolusi subdomain HANYA aktif kalau environment variable
TENANT_SUBDOMAIN_BASE_DOMAIN diisi -- kosong (default, termasuk
deployment produksi saat ini) berarti fitur ini MATI TOTAL, byte-identik
dengan sebelum middleware ini ada."""

import tenant_middleware


def test_subdomain_mati_total_tanpa_base_domain(monkeypatch):
    monkeypatch.setattr(tenant_middleware, "SUBDOMAIN_BASE_DOMAIN", "")
    assert tenant_middleware._slug_dari_subdomain("toko-a.mugenhair.app") is None
    assert tenant_middleware._slug_dari_subdomain("mugen-hair-co.onrender.com") is None


def test_subdomain_resolusi_aktif_kalau_base_domain_diisi(monkeypatch):
    monkeypatch.setattr(tenant_middleware, "SUBDOMAIN_BASE_DOMAIN", "mugenhair.app")
    assert tenant_middleware._slug_dari_subdomain("toko-a.mugenhair.app") == "toko-a"
    assert tenant_middleware._slug_dari_subdomain("toko-a.mugenhair.app:8000") == "toko-a"
    # www/api bukan slug tenant walau base domain cocok.
    assert tenant_middleware._slug_dari_subdomain("www.mugenhair.app") is None
    assert tenant_middleware._slug_dari_subdomain("api.mugenhair.app") is None
    # Bare base domain (tanpa subdomain sama sekali) -> tidak ada slug.
    assert tenant_middleware._slug_dari_subdomain("mugenhair.app") is None
    # Host domain lain sama sekali -> tidak ada slug.
    assert tenant_middleware._slug_dari_subdomain("evil.com") is None
    # Subdomain berlapis (bukan bentuk slug tunggal yang valid) -> None.
    assert tenant_middleware._slug_dari_subdomain("a.b.mugenhair.app") is None


def test_login_lewat_subdomain(monkeypatch, two_tenants):
    """End-to-end: subdomain di header Host -> slug tenant ter-resolve
    middleware -> login scoped ke tenant yang benar, TANPA field `tenant`
    di body maupun header X-Tenant-Slug sama sekali."""
    monkeypatch.setattr(tenant_middleware, "SUBDOMAIN_BASE_DOMAIN", "mugenhair.app")
    client = two_tenants["client"]
    r = client.post(
        "/api/auth/login",
        json={"username": "ownerA", "password": "passwordA123"},
        headers={"Host": "test-toko-a.mugenhair.app"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tenant"]["slug"] == "test-toko-a"
