"""
test_billing_checkout.py — FONDASI Multi-Tenant Phase 4: Invoice & Checkout
=============================================================================
Cakupan: GET katalog paket aktif + fitur, GET config Midtrans (client key
publik, TIDAK PERNAH server key), POST checkout (mock Midtrans lewat
monkeypatch midtrans_client.requests.post -- TIDAK PERNAH memanggil
Midtrans sungguhan), riwayat invoice Owner (terisolasi per tenant), dan
monitoring invoice Super Admin lintas tenant."""

import billing_db
import billing_invoice_db
import midtrans_client
import tenant_db


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    import auth_db
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    return _login(client, username, password)


def _aktifkan_midtrans_mock(monkeypatch, token="snap-token-abc", redirect="https://example.test/snap/abc",
                             status_code=201):
    monkeypatch.setattr(midtrans_client, "IS_ENABLED", True)
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "SB-Mid-server-test")
    monkeypatch.setattr(midtrans_client, "MIDTRANS_CLIENT_KEY", "SB-Mid-client-test")

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(status_code, {"token": token, "redirect_url": redirect})

    monkeypatch.setattr(midtrans_client.requests, "post", fake_post)


def _owner_login(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    import auth_db
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    return tenant, _login(app_client, "owner1", "password123")


# ============================= GET /packages, /config =============================

def test_daftar_paket_aktif_membawa_fitur(app_client):
    tenant, headers = _owner_login(app_client)
    pro = billing_db.get_package_by_kode("pro")
    qris = billing_db.get_feature_by_kode("qris")
    billing_db.set_package_features(pro["id"], [qris["id"]])

    r = app_client.get("/api/billing/packages", headers=headers)
    assert r.status_code == 200, r.text
    paket_pro = next(p for p in r.json() if p["kode"] == "pro")
    assert {f["kode"] for f in paket_pro["fitur"]} == {"qris"}


def test_daftar_paket_aktif_tidak_membawa_paket_nonaktif(app_client):
    tenant, headers = _owner_login(app_client)
    enterprise = billing_db.get_package_by_kode("enterprise")
    billing_db.update_package(enterprise["id"], aktif=False)

    r = app_client.get("/api/billing/packages", headers=headers)
    assert "enterprise" not in {p["kode"] for p in r.json()}


def test_config_midtrans_tidak_membocorkan_server_key(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)

    r = app_client.get("/api/billing/config", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is True
    assert data["client_key"] == "SB-Mid-client-test"
    assert "server_key" not in data
    assert "SB-Mid-server-test" not in str(data)


def test_config_midtrans_disabled_saat_belum_dikonfigurasi(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    monkeypatch.setattr(midtrans_client, "IS_ENABLED", False)

    r = app_client.get("/api/billing/config", headers=headers)
    assert r.json()["enabled"] is False


# ============================= POST /checkout =============================

def test_checkout_sukses_membuat_invoice(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], harga=249000)

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "pending"
    assert data["package_kode"] == "pro"
    assert data["jumlah"] == 249000
    assert data["snap_token"] == "snap-token-abc"
    assert data["tenant_id"] == tenant["id"]
    assert data["order_id"].startswith(f"SUB-{tenant['id']}-")
    assert data["nomor_invoice"].startswith("INV-")


def test_checkout_tanpa_midtrans_dikonfigurasi_503(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    monkeypatch.setattr(midtrans_client, "IS_ENABLED", False)
    pro = billing_db.get_package_by_kode("pro")

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]})
    assert r.status_code == 503


def test_checkout_paket_tidak_ada_422(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": 999999})
    assert r.status_code == 422


def test_checkout_paket_nonaktif_422(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], aktif=False)

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]})
    assert r.status_code == 422


def test_checkout_paket_gratis_ditolak(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)
    free = billing_db.get_package_by_kode("free")

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": free["id"]})
    assert r.status_code == 422
    assert "tidak memerlukan pembayaran" in r.json()["detail"]


def test_checkout_midtrans_gagal_502_dan_tidak_membuat_invoice(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch, status_code=401)
    pro = billing_db.get_package_by_kode("pro")

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]})
    assert r.status_code == 502
    assert billing_invoice_db.list_invoices(tenant_id=tenant["id"]) == []


# ============================= Riwayat invoice Owner =============================

def test_daftar_invoice_saya(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")

    app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]})

    r = app_client.get("/api/billing/invoices", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.json()[0]["package_kode"] == "pro"


def test_detail_invoice_saya(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    invoice = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]}).json()

    r = app_client.get(f"/api/billing/invoices/{invoice['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == invoice["id"]


def test_invoice_tenant_lain_404(two_tenants, monkeypatch):
    _aktifkan_midtrans_mock(monkeypatch)
    import auth_db
    auth_db.tambah_user("ownerA2", "passwordA123", role="admin", tenant_id=two_tenants["tenant_a"])
    headers_a = _login(two_tenants["client"], "ownerA2", "passwordA123")
    pro = billing_db.get_package_by_kode("pro")

    invoice = two_tenants["client"].post("/api/billing/checkout", headers=headers_a,
                                          json={"package_id": pro["id"]}).json()

    r = two_tenants["client"].get(f"/api/billing/invoices/{invoice['id']}", headers=two_tenants["headers_b"])
    assert r.status_code == 404


# ============================= Monitoring Super Admin =============================

def test_superadmin_list_invoices_semua_tenant(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]})

    headers_sa = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/superadmin/billing/invoices", headers=headers_sa)
    assert r.status_code == 200, r.text
    baris = [b for b in r.json() if b["tenant_slug"] == "mugen-hair-co"]
    assert len(baris) == 1
    assert baris[0]["nama_barbershop"] == "MUGEN Hair Co."


def test_akun_tenant_biasa_ditolak_endpoint_superadmin_invoices(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/billing/invoices", headers=two_tenants["headers_a"])
    assert r.status_code == 403


def test_superadmin_detail_invoice_tenant_manapun(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_midtrans_mock(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    invoice = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]}).json()

    headers_sa = _buat_superadmin_dan_login(app_client)
    r = app_client.get(f"/api/superadmin/billing/invoices/{invoice['id']}", headers=headers_sa)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == invoice["id"]


def test_superadmin_detail_invoice_tidak_ada_404(app_client):
    headers_sa = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/superadmin/billing/invoices/999999", headers=headers_sa)
    assert r.status_code == 404
