"""Regresi FITUR Subdomain Otomatis per Tenant: TenantResolutionMiddleware
(tenant_middleware.py).

Resolusi subdomain AKTIF SECARA DEFAULT (env var TENANT_SUBDOMAIN_SUFFIX,
default "rivoirsett.com") -- kosongkan env var itu untuk mematikan
resolusi subdomain sama sekali. Label reservasi platform (admin/www/api/
app/dst) TIDAK PERNAH dianggap slug tenant, dan Custom Domain (kolom
tenants.custom_domain) jadi fallback kalau Host tidak berbentuk subdomain
rivoirsett.com sama sekali."""

import tenant_db
import tenant_middleware


def test_subdomain_mati_total_kalau_base_domain_dikosongkan(monkeypatch):
    monkeypatch.setattr(tenant_middleware, "SUBDOMAIN_BASE_DOMAIN", "")
    assert tenant_middleware._slug_dari_subdomain("toko-a.mugenhair.app") is None
    assert tenant_middleware._slug_dari_subdomain("mugenhairco.rivoirsett.com") is None


def test_subdomain_resolusi_aktif_kalau_base_domain_diisi(monkeypatch):
    monkeypatch.setattr(tenant_middleware, "SUBDOMAIN_BASE_DOMAIN", "mugenhair.app")
    assert tenant_middleware._slug_dari_subdomain("toko-a.mugenhair.app") == "toko-a"
    assert tenant_middleware._slug_dari_subdomain("toko-a.mugenhair.app:8000") == "toko-a"
    # www/api/app/admin/mail/ftp bukan slug tenant walau base domain cocok.
    assert tenant_middleware._slug_dari_subdomain("www.mugenhair.app") is None
    assert tenant_middleware._slug_dari_subdomain("api.mugenhair.app") is None
    assert tenant_middleware._slug_dari_subdomain("app.mugenhair.app") is None
    assert tenant_middleware._slug_dari_subdomain("admin.mugenhair.app") is None
    # Bare base domain (tanpa subdomain sama sekali) -> tidak ada slug.
    assert tenant_middleware._slug_dari_subdomain("mugenhair.app") is None
    # Host domain lain sama sekali -> tidak ada slug.
    assert tenant_middleware._slug_dari_subdomain("evil.com") is None
    # Subdomain berlapis (bukan bentuk slug tunggal yang valid) -> None.
    assert tenant_middleware._slug_dari_subdomain("a.b.mugenhair.app") is None


def test_subdomain_aktif_default_tanpa_konfigurasi_apa_pun():
    """Modul dimuat dengan env var TENANT_SUBDOMAIN_SUFFIX TIDAK diisi
    sama sekali (kondisi test runner ini) -- harus tetap default ke
    "rivoirsett.com", BUKAN kosong/mati seperti sebelumnya."""
    assert tenant_middleware.SUBDOMAIN_BASE_DOMAIN == "rivoirsett.com"
    assert tenant_middleware._slug_dari_subdomain("mugenhairco.rivoirsett.com") == "mugenhairco"
    assert tenant_middleware._slug_dari_subdomain("admin.rivoirsett.com") is None


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


def test_branding_lewat_subdomain_default(two_tenants):
    """Default runtime (rivoirsett.com AKTIF tanpa monkeypatch apa pun) --
    GET /api/tenant/branding lewat Host subdomain harus mengembalikan
    branding TENANT tersebut (is_platform_default: False), BUKAN branding
    platform."""
    client = two_tenants["client"]
    r = client.get("/api/tenant/branding", headers={"Host": "test-toko-a.rivoirsett.com"})
    assert r.status_code == 200, r.text
    assert r.json()["is_platform_default"] is False


def test_branding_subdomain_tidak_dikenal_pakai_platform(app_client):
    """Subdomain BERBENTUK tenant tapi slug-nya tidak ada di database --
    branding PLATFORM (is_platform_default: True), sinyal yang dipakai
    frontend/app/js/tenant_guard.js untuk menampilkan halaman "Tenant
    Tidak Ditemukan"."""
    r = app_client.get("/api/tenant/branding", headers={"Host": "tidak-ada-begini.rivoirsett.com"})
    assert r.status_code == 200, r.text
    assert r.json()["is_platform_default"] is True


def test_admin_subdomain_tidak_pernah_dianggap_slug_tenant(app_client):
    """admin.rivoirsett.com HARUS selalu None (bukan slug "admin") --
    reservasi ini menjaga Super Admin tetap bisa memakai subdomain admin
    tanpa pernah tertukar/dicegat resolusi tenant mana pun."""
    r = app_client.get("/api/tenant/branding", headers={"Host": "admin.rivoirsett.com"})
    assert r.status_code == 200, r.text
    assert r.json()["is_platform_default"] is True


def test_resolusi_custom_domain(monkeypatch, single_tenant):
    """FITUR Custom Domain (persiapan): Host yang SAMA SEKALI bukan bentuk
    subdomain rivoirsett.com, tapi cocok dengan tenants.custom_domain --
    tetap ter-resolve ke tenant yang sama lewat mekanisme request.state
    yang SAMA PERSIS (TIDAK ADA endpoint/kode tambahan apa pun di luar
    tenant_db.get_tenant_by_custom_domain())."""
    with tenant_db.get_conn() as conn:
        conn.execute("UPDATE tenants SET custom_domain = ? WHERE id = ?",
                     ("mugenhairco.com", single_tenant["tenant_id"]))
    client = single_tenant["client"]
    r = client.get("/api/tenant/branding", headers={"Host": "mugenhairco.com"})
    assert r.status_code == 200, r.text
    assert r.json()["is_platform_default"] is False


def test_custom_domain_tidak_dicoba_untuk_subdomain_rivoirsett():
    """Optimisasi: Host yang SUDAH cocok pola *.rivoirsett.com TIDAK pernah
    memicu lookup custom_domain (murni untuk domain yang SAMA SEKALI di
    luar rivoirsett.com)."""
    assert tenant_middleware._slug_dari_custom_domain("mugenhairco.rivoirsett.com") is None
    assert tenant_middleware._slug_dari_custom_domain("rivoirsett.com") is None


# =============================================================================
# HOTFIX Migrasi Subdomain: Origin header (BUKAN Host) adalah sumber yang
# benar untuk resolusi subdomain/custom domain di topologi deployment
# produksi (frontend di {slug}.rivoirsett.com, backend API SELALU tetap di
# satu domain api.rivoirsett.com -- Host header yang SAMPAI ke backend
# TIDAK PERNAH membawa subdomain tenant, cuma domain API itu sendiri).
# Ditemukan karena test_branding_lewat_subdomain_default() di atas (dan
# semua test lain di file ini) memakai TestClient yang membiarkan Host
# diset LANGSUNG tanpa Origin sama sekali -- caranya tidak meniru
# perilaku browser sungguhan (yang SELALU mengirim Origin untuk request
# cross-origin, TIDAK PERNAH mengizinkan JS memalsukan Host), jadi celah
# ini tidak pernah tertangkap test yang sudah ada.
# =============================================================================

def test_resolusi_utamakan_origin_bukan_host(monkeypatch):
    """Skenario browser SUNGGUHAN: frontend tenant di subdomain sendiri
    memanggil API yang selalu satu domain tetap -- Host header di request
    yang SAMPAI ke backend adalah domain API (TIDAK berguna untuk
    resolusi), Origin header (dikirim otomatis browser, tidak bisa
    dipalsukan lewat JS halaman) yang membawa subdomain tenant
    sebenarnya."""
    monkeypatch.setattr(tenant_middleware, "SUBDOMAIN_BASE_DOMAIN", "rivoirsett.com")

    class _FakeRequest:
        headers = {"origin": "https://mugen.rivoirsett.com", "host": "api.rivoirsett.com"}

    hostname = tenant_middleware._hostname_dari_origin_atau_host(_FakeRequest())
    assert hostname == "mugen.rivoirsett.com"
    assert tenant_middleware._slug_dari_subdomain(hostname) == "mugen"


def test_resolusi_fallback_ke_host_kalau_tidak_ada_origin(monkeypatch):
    """Request tanpa Origin (curl/server-ke-server/webhook, bukan browser,
    atau test yang meniru Host langsung seperti seluruh test lain di file
    ini) -- fallback ke Host, perilaku LAMA tidak berubah sama sekali."""
    monkeypatch.setattr(tenant_middleware, "SUBDOMAIN_BASE_DOMAIN", "rivoirsett.com")

    class _FakeRequest:
        headers = {"host": "mugen.rivoirsett.com"}

    hostname = tenant_middleware._hostname_dari_origin_atau_host(_FakeRequest())
    assert hostname == "mugen.rivoirsett.com"


def test_branding_lewat_origin_bukan_host(two_tenants):
    """End-to-end lewat header Origin (bukan Host) -- meniru persis
    request cross-origin browser sungguhan dari subdomain tenant ke
    domain API yang terpisah."""
    client = two_tenants["client"]
    r = client.get(
        "/api/tenant/branding",
        headers={"Host": "api.rivoirsett.com", "Origin": "https://test-toko-a.rivoirsett.com"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_platform_default"] is False


# =============================================================================
# HOTFIX Migrasi Subdomain: root domain (tanpa slug tenant apa pun yang
# ter-resolve) TIDAK BOLEH LAGI diam-diam menyajikan data tenant default --
# tenant_db.cari_tenant_publik(None) sekarang return None, bukan fallback
# ke SLUG_TENANT_DEFAULT.
# =============================================================================

def test_cari_tenant_publik_slug_kosong_return_none():
    assert tenant_db.cari_tenant_publik(None) is None
    assert tenant_db.cari_tenant_publik("") is None


def test_endpoint_publik_tanpa_tenant_404_bukan_default_tenant(app_client):
    """Root domain (request publik TANPA ?tenant=, TANPA header X-Tenant-
    Slug, TANPA subdomain/Origin yang cocok) HARUS 404 -- bukan lagi
    diam-diam menyajikan data tenant default (mugen-hair-co) seperti
    sebelum migrasi subdomain ini."""
    r = app_client.get("/api/public/booking/barbers")
    assert r.status_code == 404, r.text
    assert "tidak ditemukan" in r.json()["detail"].lower()

    r2 = app_client.get("/api/public/booking/services")
    assert r2.status_code == 404

    r3 = app_client.get("/api/website/content")
    assert r3.status_code == 404


def test_endpoint_publik_dengan_tenant_eksplisit_tetap_berfungsi(app_client):
    """Regresi: subdomain/?tenant= eksplisit tetap berfungsi normal --
    HANYA fallback implisit yang dihapus, bukan resolusi tenant secara
    umum."""
    r = app_client.get("/api/public/booking/barbers?tenant=mugen-hair-co")
    assert r.status_code == 200, r.text
