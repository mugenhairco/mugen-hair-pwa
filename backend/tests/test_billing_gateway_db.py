"""
test_billing_gateway_db.py — Payment Gateway Billing SaaS (platform-wide, provider-agnostic)
=============================================================================
Cakupan: kredensial DB-backed (get_config/update_config, tabel `settings`
generik, tenant_id=None -- TIDAK ADA tabel baru), form generik tujuh field
(environment/api_key/server_key/client_key/merchant_id/secret_key/
webhook_url) yang TIDAK semua wajib diisi, migrasi bootstrap SEKALI dari env
var MIDTRANS_* lama (idempotent, tidak pernah menimpa perubahan Super
Admin), endpoint Super Admin (gating + audit log), dan bukti bahwa modul ini
TERPISAH TOTAL dari payment_gateway_db.py (Payment Gateway booking
customer) -- mengubah satu tidak pernah memengaruhi yang lain."""

import billing_gateway_db
import payment_gateway_db

_CONFIG_KOSONG = {
    "api_key": "", "server_key": "", "client_key": "", "merchant_id": "",
    "secret_key": "", "webhook_url": "", "environment": "sandbox", "enabled": False,
}


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    import auth_db
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    return _login(client, username, password)


# ============================= get_config / update_config =============================

def test_get_config_default_kosong_dan_disabled(app_client):
    assert billing_gateway_db.get_config() == _CONFIG_KOSONG


def test_update_config_menyimpan_dan_enabled_true(app_client):
    hasil = billing_gateway_db.update_config(
        server_key="SB-server-abc", client_key="SB-client-abc", environment="production",
    )
    assert hasil == {
        **_CONFIG_KOSONG,
        "server_key": "SB-server-abc", "client_key": "SB-client-abc",
        "environment": "production", "enabled": True,
    }
    assert billing_gateway_db.get_config() == hasil


def test_update_config_semua_field_generik_tersimpan(app_client):
    """Form TIDAK spesifik satu provider -- ketujuh field (di luar
    environment) harus bisa diisi & tersimpan independen satu sama lain,
    provider apa pun yang kelak memakainya."""
    hasil = billing_gateway_db.update_config(
        api_key="api-1", server_key="server-1", client_key="client-1",
        merchant_id="merchant-1", secret_key="secret-1", webhook_url="https://example.test/webhook",
        environment="production",
    )
    assert hasil == {
        "api_key": "api-1", "server_key": "server-1", "client_key": "client-1",
        "merchant_id": "merchant-1", "secret_key": "secret-1",
        "webhook_url": "https://example.test/webhook", "environment": "production", "enabled": True,
    }


def test_update_config_field_boleh_kosong_sebagian(app_client):
    """SESUAI KEPUTUSAN: tidak semua field wajib diisi -- provider yang
    hanya butuh server_key+client_key (mis. Midtrans) boleh membiarkan
    api_key/merchant_id/secret_key/webhook_url tetap kosong selamanya."""
    hasil = billing_gateway_db.update_config(server_key="only-server", client_key="only-client")
    assert hasil["api_key"] == ""
    assert hasil["merchant_id"] == ""
    assert hasil["secret_key"] == ""
    assert hasil["webhook_url"] == ""
    assert hasil["enabled"] is True


def test_update_config_partial_tidak_menimpa_field_lain(app_client):
    billing_gateway_db.update_config(server_key="key-1", client_key="key-2", environment="sandbox")
    billing_gateway_db.update_config(environment="production")
    cfg = billing_gateway_db.get_config()
    assert cfg["server_key"] == "key-1"
    assert cfg["client_key"] == "key-2"
    assert cfg["environment"] == "production"


def test_update_config_environment_invalid_ditolak(app_client):
    try:
        billing_gateway_db.update_config(environment="staging")
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "sandbox" in str(e) or "production" in str(e)


# ============================= Migrasi bootstrap dari env var =============================

def test_migrasi_bootstrap_dari_env_var_sekali_saja(app_client, monkeypatch):
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "ENV-server-lama")
    monkeypatch.setenv("MIDTRANS_CLIENT_KEY", "ENV-client-lama")
    monkeypatch.setenv("MIDTRANS_IS_PRODUCTION", "true")

    billing_gateway_db.migrasi_billing_gateway()

    cfg = billing_gateway_db.get_config()
    assert cfg == {
        **_CONFIG_KOSONG,
        "server_key": "ENV-server-lama", "client_key": "ENV-client-lama",
        "environment": "production", "enabled": True,
    }


def test_migrasi_tidak_menimpa_config_yang_sudah_diatur_super_admin(app_client, monkeypatch):
    billing_gateway_db.update_config(server_key="key-super-admin", client_key="key-super-admin-2", environment="sandbox")

    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "ENV-seharusnya-tidak-dipakai")
    monkeypatch.setenv("MIDTRANS_CLIENT_KEY", "ENV-seharusnya-tidak-dipakai-2")

    billing_gateway_db.migrasi_billing_gateway()

    cfg = billing_gateway_db.get_config()
    assert cfg["server_key"] == "key-super-admin"
    assert cfg["client_key"] == "key-super-admin-2"


def test_migrasi_tanpa_env_var_tidak_mengisi_apa_pun(app_client, monkeypatch):
    monkeypatch.delenv("MIDTRANS_SERVER_KEY", raising=False)
    monkeypatch.delenv("MIDTRANS_CLIENT_KEY", raising=False)

    billing_gateway_db.migrasi_billing_gateway()

    assert billing_gateway_db.get_config()["enabled"] is False


# ============================= Endpoint Super Admin =============================

def test_superadmin_get_dan_put_gateway_config(app_client):
    headers = _buat_superadmin_dan_login(app_client)

    r = app_client.get("/api/superadmin/billing/gateway-config", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False

    r2 = app_client.put("/api/superadmin/billing/gateway-config", headers=headers, json={
        "server_key": "SB-server-xyz", "client_key": "SB-client-xyz", "environment": "production",
        "merchant_id": "MID-1", "webhook_url": "https://example.test/webhook",
    })
    assert r2.status_code == 200, r2.text
    assert r2.json() == {
        **_CONFIG_KOSONG,
        "server_key": "SB-server-xyz", "client_key": "SB-client-xyz", "environment": "production",
        "merchant_id": "MID-1", "webhook_url": "https://example.test/webhook", "enabled": True,
    }

    log = app_client.get("/api/superadmin/audit-log", headers=headers).json()
    assert log[0]["aksi"] == "ubah_config_billing_gateway"


def test_superadmin_endpoint_ditolak_environment_invalid(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.put("/api/superadmin/billing/gateway-config", headers=headers, json={"environment": "staging"})
    assert r.status_code == 422


def test_akun_tenant_biasa_ditolak_endpoint_billing_gateway(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/billing/gateway-config", headers=two_tenants["headers_a"])
    assert r.status_code == 403


def test_tanpa_login_ditolak_endpoint_billing_gateway(app_client):
    r = app_client.get("/api/superadmin/billing/gateway-config")
    assert r.status_code == 401


# ============================= Terpisah total dari Payment Gateway booking =============================

def test_billing_gateway_terpisah_dari_payment_gateway_booking(app_client):
    """Mengubah kredensial Billing SaaS TIDAK PERNAH memengaruhi konfigurasi
    Payment Gateway booking customer (payment_gateway_db.py), dan
    sebaliknya -- dua sumber data yang sepenuhnya independen."""
    billing_gateway_db.update_config(server_key="billing-key", client_key="billing-client", environment="production")
    payment_gateway_db.update_config(provider="Midtrans", environment="sandbox", server_key="booking-key")

    billing_cfg = billing_gateway_db.get_config()
    booking_cfg = payment_gateway_db.get_config()

    assert billing_cfg["server_key"] == "billing-key"
    assert billing_cfg["environment"] == "production"
    assert booking_cfg["pgw_server_key"] == "booking-key"
    assert booking_cfg["pgw_environment"] == "sandbox"
