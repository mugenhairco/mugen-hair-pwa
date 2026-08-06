"""
test_cors.py — BUGFIX CORS: login gagal dari subdomain tenant SaaS
(rivoirsett.com/www/mugen/tenant1, dst) karena origin tidak dikenali.
=============================================================================
Akar masalah: ALLOWED_ORIGINS (exact-match list) tidak bisa mengikuti
subdomain tenant baru yang terus bertambah lewat registrasi mandiri/Super
Admin tanpa entry manual satu-satu. Diperbaiki lewat allow_origin_regex
(CORSMiddleware Starlette) yang mengizinkan SELURUH *.rivoirsett.com
(termasuk root & www) sekaligus, TANPA membuka akses domain lain -- lihat
catatan lengkap di main.py."""

import pytest

_ORIGIN_RIVOIR = [
    "https://rivoirsett.com",
    "https://www.rivoirsett.com",
    "https://mugen.rivoirsett.com",
    "https://tenant1.rivoirsett.com",
    "https://tenant2.rivoirsett.com",
]

_ORIGIN_ASING = [
    "https://evil.com",
    "https://notrivoirsett.com",
    "https://rivoirsett.com.evil.com",
]


@pytest.mark.parametrize("origin", _ORIGIN_RIVOIR)
def test_preflight_login_diizinkan_untuk_subdomain_rivoirsett(app_client, origin):
    r = app_client.options("/api/auth/login", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    })
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin
    assert r.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.parametrize("origin", _ORIGIN_RIVOIR)
def test_post_login_membawa_header_cors_walau_gagal_auth(app_client, origin):
    """CORS header HARUS ada di response APA PUN status HTTP-nya -- baik
    401 (kredensial salah, origin root domain yang tidak ter-resolve ke
    tenant mana pun sehingga lintas-tenant) maupun 404 (HOTFIX Migrasi
    Subdomain: Origin sekarang jadi sumber resolusi tenant di
    tenant_middleware.py, jadi origin berbentuk subdomain tenant yang
    TIDAK terdaftar di database -- mis. mugen/tenant1/tenant2 di
    app_client yang cuma punya tenant default -- ikut gagal ditemukan)
    -- kalau tidak, browser tetap memblokir walau backend sebenarnya
    sudah merespons dengan benar."""
    r = app_client.post("/api/auth/login", json={"username": "x", "password": "y"},
                         headers={"Origin": origin})
    assert r.status_code in (401, 404)
    assert r.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", _ORIGIN_RIVOIR)
def test_get_auth_me_membawa_header_cors(app_client, origin):
    r = app_client.get("/api/auth/me", headers={"Origin": origin})
    assert r.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", _ORIGIN_ASING)
def test_domain_asing_tetap_ditolak(app_client, origin):
    """Mekanisme wildcard subdomain TIDAK BOLEH membuka akses ke domain
    lain di luar rivoirsett.com."""
    r = app_client.get("/api/auth/me", headers={"Origin": origin})
    assert r.headers.get("access-control-allow-origin") is None


def test_swagger_branding_rivoir(app_client):
    r = app_client.get("/openapi.json")
    data = r.json()
    assert data["info"]["title"] == "Rivoir API"
    assert data["info"]["version"] == "1.0.0"
