"""Regresi Phase 2.0: Per-Tenant Login & Tenant Resolution.

Keterbatasan Phase 1 yang diselesaikan di sini (didokumentasikan sebagai
technical debt di routers/auth_router.py sebelum Phase 2.0): dua tenant
BERBEDA yang kebetulan memilih username yang SAMA PERSIS membuat login
ambigu -- sekarang terdeteksi & diselesaikan lewat slug tenant eksplisit
(body `tenant`, header `X-Tenant-Slug`, atau subdomain lewat
tenant_middleware.py) TANPA mengubah alur login untuk instalasi yang
cuma punya satu tenant (kasus paling umum, byte-identik seperti sebelumnya)."""

import auth_db


def test_login_satu_tenant_tidak_berubah(two_tenants):
    """Kasus paling umum: username unik (tidak ambigu) -- login TANPA
    field `tenant` harus tetap berfungsi identik seperti Phase 1."""
    client = two_tenants["client"]
    r = client.post("/api/auth/login", json={"username": "ownerA", "password": "passwordA123"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token"]
    assert data["user"]["tenant_id"] == two_tenants["tenant_a"]
    assert data["tenant"]["slug"] == "test-toko-a"


def test_login_password_salah_tetap_401_generik(two_tenants):
    client = two_tenants["client"]
    r = client.post("/api/auth/login", json={"username": "ownerA", "password": "salah"})
    assert r.status_code == 401
    assert "ditemukan" not in r.json()["detail"].lower()  # tidak membocorkan username ada/tidak


def test_login_dengan_slug_tenant_eksplisit(two_tenants):
    client = two_tenants["client"]
    r = client.post("/api/auth/login", json={
        "username": "ownerA", "password": "passwordA123", "tenant": "test-toko-a",
    })
    assert r.status_code == 200, r.text
    assert r.json()["tenant"]["slug"] == "test-toko-a"


def test_login_slug_salah_untuk_user_ini_ditolak(two_tenants):
    """Username 'ownerA' cuma ada di tenant A -- login dengan slug tenant B
    (toko lain, username tidak ada di sana) harus ditolak 401, BUKAN
    diam-diam login ke tenant B atau bocor error yang berbeda."""
    client = two_tenants["client"]
    r = client.post("/api/auth/login", json={
        "username": "ownerA", "password": "passwordA123", "tenant": "test-toko-b",
    })
    assert r.status_code == 401


def test_login_slug_tidak_dikenal_404(two_tenants):
    client = two_tenants["client"]
    r = client.post("/api/auth/login", json={
        "username": "ownerA", "password": "passwordA123", "tenant": "toko-tidak-ada",
    })
    assert r.status_code == 404


def test_username_sama_password_beda_tidak_ambigu(two_tenants):
    """Dua tenant BERBEDA kebetulan pakai username yang SAMA ('kembar'),
    TAPI password beda -- ini TIDAK dianggap ambigu, karena hanya SATU
    kandidat yang password-nya benar-benar cocok."""
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    auth_db.tambah_user("kembar", "passwordUnikA1", role="admin", tenant_id=tenant_a)
    auth_db.tambah_user("kembar", "passwordUnikB1", role="admin", tenant_id=tenant_b)

    client = two_tenants["client"]
    r = client.post("/api/auth/login", json={"username": "kembar", "password": "passwordUnikA1"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["tenant_id"] == tenant_a

    r = client.post("/api/auth/login", json={"username": "kembar", "password": "passwordUnikB1"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["tenant_id"] == tenant_b


def test_username_dan_password_sama_ambigu_lalu_diselesaikan_dengan_slug(two_tenants):
    """Dua tenant BERBEDA kebetulan pakai username DAN password yang SAMA
    PERSIS -- kasus paling langka, tapi HARUS terdeteksi (409 + daftar
    toko), bukan diam-diam masuk ke salah satu tenant secara acak/pertama-
    ketemu (bug Phase 1 yang diperbaiki di Phase 2.0)."""
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    auth_db.tambah_user("kembarpersis", "passwordSama123", role="admin", tenant_id=tenant_a)
    auth_db.tambah_user("kembarpersis", "passwordSama123", role="admin", tenant_id=tenant_b)

    client = two_tenants["client"]
    r = client.post("/api/auth/login", json={"username": "kembarpersis", "password": "passwordSama123"})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    slugs = {t["slug"] for t in detail["tenants"]}
    assert slugs == {"test-toko-a", "test-toko-b"}

    # Password SALAH untuk kandidat ambigu ini tidak boleh membocorkan
    # ambiguitas -- tetap 401 generik, bukan 409.
    r = client.post("/api/auth/login", json={"username": "kembarpersis", "password": "passwordSalah"})
    assert r.status_code == 401

    # Setelah memilih toko (slug) secara eksplisit, login berhasil normal.
    r = client.post("/api/auth/login", json={
        "username": "kembarpersis", "password": "passwordSama123", "tenant": "test-toko-b",
    })
    assert r.status_code == 200, r.text
    assert r.json()["user"]["tenant_id"] == tenant_b


def test_middleware_header_x_tenant_slug(two_tenants):
    """Slug tenant lewat header X-Tenant-Slug (di-resolve
    TenantResolutionMiddleware, lihat tenant_middleware.py) harus
    berfungsi SAMA seperti field `tenant` di body -- dipakai client yang
    tidak punya slot query-string/body alami untuk slug (mis. app native)."""
    client = two_tenants["client"]
    r = client.post(
        "/api/auth/login",
        json={"username": "ownerA", "password": "passwordA123"},
        headers={"X-Tenant-Slug": "test-toko-a"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tenant"]["slug"] == "test-toko-a"
