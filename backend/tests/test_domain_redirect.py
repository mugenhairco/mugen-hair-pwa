"""Regresi: redirect permanen (HTTP 308) dari domain onrender.com lama ke
domain produksi (rivoirsett.com) -- lihat main.py::_redirect_domain_lama().
Render TIDAK punya redirect otomatis berbasis Host header di level
platform untuk Web Service (hanya bisa "Disable" total = 404) -- middleware
ini SATU-SATUNYA yang menjamin siapa pun yang masih membuka
mugen-hair-api.onrender.com otomatis dialihkan ke api.rivoirsett.com,
tanpa tindakan apa pun dari pengguna."""


def test_redirect_domain_lama_ke_produksi(app_client):
    r = app_client.get(
        "/api/health",
        headers={"Host": "mugen-hair-api.onrender.com"},
        follow_redirects=False,
    )
    assert r.status_code == 308
    assert r.headers["location"] == "https://api.rivoirsett.com/api/health"


def test_redirect_mempertahankan_query_string(app_client):
    r = app_client.get(
        "/api/auth/login?debug=1",
        headers={"Host": "mugen-hair-api.onrender.com"},
        follow_redirects=False,
    )
    assert r.status_code == 308
    assert r.headers["location"] == "https://api.rivoirsett.com/api/auth/login?debug=1"


def test_redirect_308_mempertahankan_method_post(app_client):
    """308 (BUKAN 301/302) memastikan browser/klien mengulang request POST
    ini sebagai POST juga ke domain baru, bukan berubah jadi GET."""
    r = app_client.post(
        "/api/auth/login",
        json={"username": "siapa", "password": "saja"},
        headers={"Host": "mugen-hair-api.onrender.com"},
        follow_redirects=False,
    )
    assert r.status_code == 308
    assert r.headers["location"] == "https://api.rivoirsett.com/api/auth/login"


def test_redirect_tidak_terpicu_untuk_domain_produksi(app_client):
    r = app_client.get("/api/health", headers={"Host": "api.rivoirsett.com"})
    assert r.status_code == 200


def test_redirect_tidak_terpicu_untuk_host_default_testclient(app_client):
    r = app_client.get("/api/health")
    assert r.status_code == 200
