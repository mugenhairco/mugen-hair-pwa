"""
test_billing_checkout.py — FONDASI Multi-Tenant Phase 4: Invoice & Checkout
=============================================================================
Cakupan: GET katalog paket aktif + fitur, GET config Payment Gateway
langganan SaaS (client key publik, TIDAK PERNAH server key), POST checkout
(mock provider lewat monkeypatch gateway_client_base.requests.post --
TIDAK PERNAH memanggil provider sungguhan), riwayat invoice Owner
(terisolasi per tenant), dan monitoring invoice Super Admin lintas tenant."""

import billing_db
import billing_gateway_db
import billing_invoice_db
import gateway_client_base
import payment_provider_client
import snap_advance_db
import snap_payment_db
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


# PROVIDER RESMI: Faspay Xpress v4 -- buat_transaksi() SELALU return
# token=None (Faspay tidak punya konsep token checkout seperti Snap, murni
# redirect_url), respons sukses provider ditandai response_code "00".
# TETAP DIPERTAHANKAN (walau tidak lagi dipakai checkout POST /api/billing/checkout
# yang sudah migrasi ke SNAP) -- payment_gateway_client.py sendiri tetap ada.
def _aktifkan_billing_gateway_mock(monkeypatch, redirect="https://example.test/checkout/abc", status_code=200):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: {
        "merchant_id": "37070-test", "server_key": "bot-test-checkout", "secret_key": "p-test-checkout",
        "client_key": "", "environment": "sandbox", "enabled": True,
    })

    def fake_post(url, json, headers, timeout):
        if status_code >= 400:
            return _FakeResponse(status_code, {"response_code": "99", "response_desc": "Ditolak"})
        return _FakeResponse(status_code, {"response_code": "00", "response_desc": "Success", "redirect_url": redirect})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)


# Migrasi Faspay SNAP Advance: POST /api/billing/checkout SEKARANG lewat
# payment_provider_client.py (SNAP VA/QRIS), BUKAN lagi Xpress v4 -- lihat
# routers/billing.py::checkout(). `va_number` bisa dioverride per test buat
# assert nilai spesifik; `gagal` bikin payment_provider_client.buat_transaksi()
# melempar GatewayError (padanan status_code>=400 di atas).
def _aktifkan_snap_billing(monkeypatch, va_number="70212345678901", gagal=False):
    snap_advance_db.update_config(
        merchant_id="37070", partner_id="37070", channel_id="77001", va_bank_aktif=["702"],
        private_key="-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----",
        channel_aktif=["va", "qris"],
    )

    def _hasil(*a, **kw):
        if gagal:
            raise gateway_client_base.GatewayTimeoutError("Provider timeout.")
        return {"va_number": va_number, "provider_transaction_id": "trx-1",
                "expired_at": "2026-01-01T23:59:59+07:00", "provider_response": "{}"}
    monkeypatch.setattr(payment_provider_client, "buat_transaksi", _hasil)


def _owner_login(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    import auth_db
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    return tenant, _login(app_client, "owner1", "password123")


# ============================= GET /packages, /config =============================

def test_daftar_paket_aktif_membawa_fitur(app_client):
    tenant, headers = _owner_login(app_client)
    pro = billing_db.get_package_by_kode("pro")
    export_pdf = billing_db.get_feature_by_kode("export_pdf")
    billing_db.set_package_features(pro["id"], [export_pdf["id"]])

    r = app_client.get("/api/billing/packages", headers=headers)
    assert r.status_code == 200, r.text
    paket_pro = next(p for p in r.json() if p["kode"] == "pro")
    assert {f["kode"] for f in paket_pro["fitur"]} == {"export_pdf"}


def test_daftar_paket_aktif_tidak_membawa_paket_nonaktif(app_client):
    tenant, headers = _owner_login(app_client)
    enterprise = billing_db.get_package_by_kode("enterprise")
    billing_db.update_package(enterprise["id"], aktif=False)

    r = app_client.get("/api/billing/packages", headers=headers)
    assert "enterprise" not in {p["kode"] for p in r.json()}


def test_config_billing_gateway_tidak_membocorkan_server_key(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)

    r = app_client.get("/api/billing/config", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is True
    assert data["channel_aktif"] == ["va", "qris"]
    # SNAP (seperti Xpress v4 sebelumnya) TIDAK punya JS SDK/client-side
    # key -- client_key()/checkout_script_url() SELALU None.
    assert data["client_key"] is None
    assert data["checkout_script_url"] is None
    assert "private_key" not in data
    assert "-----BEGIN PRIVATE KEY-----" not in str(data)


def test_config_billing_gateway_disabled_saat_belum_dikonfigurasi(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    # Config fresh test DB SUDAH default disabled (belum pernah diisi Super
    # Admin) -- tidak perlu monkeypatch apa pun untuk memastikan itu.

    r = app_client.get("/api/billing/config", headers=headers)
    assert r.json()["enabled"] is False


# ============================= POST /checkout =============================

def test_checkout_sukses_membuat_invoice(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], harga=249000)

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"], "channel": "va", "bank_code": "702"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "pending"
    assert data["package_kode"] == "pro"
    assert data["jumlah"] == 249000
    # Migrasi Faspay SNAP Advance: kolom snap_token/snap_redirect_url lawas
    # (Xpress v4) SEKARANG SELALU None -- detail VA/QR ada di field baru.
    assert data["snap_token"] is None
    assert data["snap_redirect_url"] is None
    assert data["channel"] == "va"
    assert data["va_number"] == "70212345678901"
    assert data["payment_reference"]
    assert data["tenant_id"] == tenant["id"]
    assert data["order_id"].startswith(f"SUB-{tenant['id']}-")
    assert data["nomor_invoice"].startswith("INV-")

    transaksi = snap_payment_db.get_transaksi_by_reference(data["payment_reference"])
    assert transaksi is not None
    assert transaksi["status"] == "PENDING"
    assert transaksi["subscription_invoice_id"] == data["id"]


# FITUR Landing Page & Pricing (paket 6 bulan): checkout dengan siklus
# "6bulan" HARUS memakai harga_6bulan (bukan harga bulanan) + durasi
# efektif durasi_hari*6 -- lihat routers/billing.py::checkout().
def test_checkout_6bulan_sukses_pakai_harga_dan_durasi_6bulan(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], harga=250000, harga_6bulan=1200000, durasi_hari=30)

    r = app_client.post("/api/billing/checkout", headers=headers,
                         json={"package_id": pro["id"], "siklus": "6bulan", "channel": "va", "bank_code": "702"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["jumlah"] == 1200000
    assert data["durasi_hari"] == 180
    assert data["package_kode"] == "pro"


def test_checkout_6bulan_ditolak_kalau_paket_tidak_menawarkan(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], harga_6bulan=None)

    r = app_client.post("/api/billing/checkout", headers=headers,
                         json={"package_id": pro["id"], "siklus": "6bulan", "channel": "va", "bank_code": "702"})
    assert r.status_code == 422
    assert "tidak menawarkan siklus 6 bulan" in r.json()["detail"]


# FITUR Landing Page & Pricing (paket Tahunan): checkout dengan siklus
# "tahunan" HARUS memakai harga_tahunan (bukan harga bulanan) + durasi
# efektif durasi_hari*12 -- lihat routers/billing.py::checkout(). Pola SAMA
# PERSIS test_checkout_6bulan_sukses_pakai_harga_dan_durasi_6bulan() di
# atas -- angka jumlah HARUS PERSIS Rp2.160.000 (spesifikasi Owner untuk
# Pro + Tahunan), membuktikan harga yang ditampilkan frontend TIDAK
# berbeda dengan yang dikirim ke checkout/invoice sungguhan.
def test_checkout_tahunan_sukses_pakai_harga_dan_durasi_tahunan(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], harga=250000, harga_tahunan=2160000, durasi_hari=30)

    r = app_client.post("/api/billing/checkout", headers=headers,
                         json={"package_id": pro["id"], "siklus": "tahunan", "channel": "va", "bank_code": "702"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["jumlah"] == 2160000
    assert data["durasi_hari"] == 360
    assert data["package_kode"] == "pro"


def test_checkout_tahunan_basic_dan_enterprise_sesuai_spesifikasi(app_client, monkeypatch):
    """Basic + Tahunan -> Rp1.560.000, Enterprise + Tahunan -> Rp3.360.000
    (langsung dari nilai default migrasi_harga_tahunan_v1(), TANPA
    override manual) -- bukti checkout menerima angka PERSIS sama dengan
    yang ditampilkan di kartu Pricing, tidak ada penyimpangan."""
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    basic = billing_db.get_package_by_kode("basic")
    enterprise = billing_db.get_package_by_kode("enterprise")

    r_basic = app_client.post("/api/billing/checkout", headers=headers,
                               json={"package_id": basic["id"], "siklus": "tahunan", "channel": "va", "bank_code": "702"})
    assert r_basic.status_code == 200, r_basic.text
    assert r_basic.json()["jumlah"] == 1560000

    r_enterprise = app_client.post("/api/billing/checkout", headers=headers,
                                    json={"package_id": enterprise["id"], "siklus": "tahunan", "channel": "va", "bank_code": "702"})
    assert r_enterprise.status_code == 200, r_enterprise.text
    assert r_enterprise.json()["jumlah"] == 3360000


def test_checkout_tahunan_ditolak_kalau_paket_tidak_menawarkan(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], harga_tahunan=None)

    r = app_client.post("/api/billing/checkout", headers=headers,
                         json={"package_id": pro["id"], "siklus": "tahunan", "channel": "va", "bank_code": "702"})
    assert r.status_code == 422
    assert "tidak menawarkan siklus tahunan" in r.json()["detail"]


def test_checkout_siklus_tidak_dikenal_422(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")

    # "mingguan" (BUKAN "tahunan" -- FITUR Landing Page & Pricing paket
    # Tahunan sekarang menjadikan "tahunan" siklus VALID, lihat test khusus
    # di bawah, jadi tidak lagi contoh yang tepat untuk "siklus tidak dikenal").
    r = app_client.post("/api/billing/checkout", headers=headers,
                         json={"package_id": pro["id"], "siklus": "mingguan", "channel": "va", "bank_code": "702"})
    assert r.status_code == 422


def test_checkout_tanpa_gateway_dikonfigurasi_503(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    # Config fresh test DB SUDAH default disabled (belum pernah diisi Super
    # Admin) -- tidak perlu monkeypatch apa pun untuk memastikan itu.
    pro = billing_db.get_package_by_kode("pro")

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"], "channel": "va", "bank_code": "702"})
    assert r.status_code == 503


def test_checkout_paket_tidak_ada_422(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": 999999, "channel": "va", "bank_code": "702"})
    assert r.status_code == 422


def test_checkout_paket_nonaktif_422(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], aktif=False)

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"], "channel": "va", "bank_code": "702"})
    assert r.status_code == 422


def test_checkout_paket_gratis_ditolak(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    free = billing_db.get_package_by_kode("free")

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": free["id"], "channel": "va", "bank_code": "702"})
    assert r.status_code == 422
    assert "tidak memerlukan pembayaran" in r.json()["detail"]


def test_checkout_gateway_gagal_502_invoice_ditandai_denied(app_client, monkeypatch):
    """Migrasi Faspay SNAP Advance: urutan checkout BERBALIK dari Xpress
    v4 (invoice dibuat LEBIH DULU, lihat routers/billing.py::checkout()) --
    provider gagal TIDAK LAGI berarti "tidak ada invoice sama sekali",
    melainkan invoice tetap tercatat dengan status "denied" (mencegah baris
    hantu tersembunyi, sekaligus konsisten dengan pola snap_payment_db
    yang juga tetap mencatat baris FAILED, bukan menghapusnya)."""
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch, gagal=True)
    pro = billing_db.get_package_by_kode("pro")

    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"], "channel": "va", "bank_code": "702"})
    assert r.status_code == 502
    invoices = billing_invoice_db.list_invoices(tenant_id=tenant["id"])
    assert len(invoices) == 1
    assert invoices[0]["status"] == "denied"


# ============================= Riwayat invoice Owner =============================

def test_daftar_invoice_saya(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")

    app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"], "channel": "va", "bank_code": "702"})

    r = app_client.get("/api/billing/invoices", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.json()[0]["package_kode"] == "pro"


def test_detail_invoice_saya(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    invoice = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"], "channel": "va", "bank_code": "702"}).json()

    r = app_client.get(f"/api/billing/invoices/{invoice['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == invoice["id"]


def test_invoice_tenant_lain_404(two_tenants, monkeypatch):
    _aktifkan_snap_billing(monkeypatch)
    import auth_db
    auth_db.tambah_user("ownerA2", "passwordA123", role="admin", tenant_id=two_tenants["tenant_a"])
    headers_a = _login(two_tenants["client"], "ownerA2", "passwordA123")
    pro = billing_db.get_package_by_kode("pro")

    invoice = two_tenants["client"].post("/api/billing/checkout", headers=headers_a,
                                          json={"package_id": pro["id"], "channel": "va", "bank_code": "702"}).json()

    r = two_tenants["client"].get(f"/api/billing/invoices/{invoice['id']}", headers=two_tenants["headers_b"])
    assert r.status_code == 404


# ============================= Monitoring Super Admin =============================

def test_superadmin_list_invoices_semua_tenant(app_client, monkeypatch):
    tenant, headers = _owner_login(app_client)
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"], "channel": "va", "bank_code": "702"})

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
    _aktifkan_snap_billing(monkeypatch)
    pro = billing_db.get_package_by_kode("pro")
    invoice = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"], "channel": "va", "bank_code": "702"}).json()

    headers_sa = _buat_superadmin_dan_login(app_client)
    r = app_client.get(f"/api/superadmin/billing/invoices/{invoice['id']}", headers=headers_sa)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == invoice["id"]


def test_superadmin_detail_invoice_tidak_ada_404(app_client):
    headers_sa = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/superadmin/billing/invoices/999999", headers=headers_sa)
    assert r.status_code == 404
