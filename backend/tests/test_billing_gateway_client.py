"""
test_billing_gateway_client.py — FONDASI Multi-Tenant Phase 4: Klien Payment Gateway Langganan SaaS
=============================================================================
File ini SEBELUMNYA bernama test_midtrans_client.py, mengikuti rename
midtrans_client.py -> billing_gateway_client.py (proyek tidak lagi
mengasumsikan Midtrans sebagai provider tetap -- lihat catatan lengkap di
billing_gateway_client.py). Kredensial datang dari
`billing_gateway_db.get_config()` (DB-backed, platform-wide Billing SaaS --
lihat billing_gateway_db.py), BUKAN konstanta module-level yang dibaca dari
environment variable saat modul diimpor. Seluruh pengujian di sini tetap
memakai mock/simulasi (monkeypatch billing_gateway_db.get_config() + fungsi
requests.post/requests.get) -- TIDAK PERNAH memanggil provider sungguhan
maupun database sungguhan, supaya suite ini tetap hijau tanpa kredensial
provider apa pun."""

import hashlib

import pytest

import billing_gateway_client
import billing_gateway_db
import gateway_client_base


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _cfg(server_key: str = "", client_key: str = "", environment: str = "sandbox") -> dict:
    return {
        "server_key": server_key, "client_key": client_key, "environment": environment,
        "enabled": bool(server_key and client_key),
    }


# ============================= is_enabled / fail-closed =============================

def test_is_enabled_false_tanpa_kredensial(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: _cfg())
    with pytest.raises(gateway_client_base.GatewayNotConfiguredError, match="belum dikonfigurasi"):
        billing_gateway_client.buat_transaksi("ORDER-1", 100000, [])
    with pytest.raises(gateway_client_base.GatewayNotConfiguredError, match="belum dikonfigurasi"):
        billing_gateway_client.cek_status_transaksi("ORDER-1")


def test_verifikasi_signature_selalu_false_tanpa_server_key(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: _cfg(server_key=""))
    assert billing_gateway_client.verifikasi_signature("ORDER-1", "200", "100000.00", "apapun") is False


# ============================= buat_transaksi =============================

def test_buat_transaksi_sukses(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="SB-Mid-server-test", client_key="SB-Mid-client-test"))

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["url"] = url
        dipanggil["json"] = json
        dipanggil["headers"] = headers
        return _FakeResponse(201, {"token": "checkout-token-abc", "redirect_url": "https://example.test/checkout/abc"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    hasil = billing_gateway_client.buat_transaksi(
        "ORDER-100", 150000,
        [{"id": "pkg-basic", "price": 150000, "quantity": 1, "name": "Paket Basic"}],
        customer_details={"first_name": "Budi"},
    )
    assert hasil == {"token": "checkout-token-abc", "redirect_url": "https://example.test/checkout/abc"}
    assert dipanggil["url"].endswith("/snap/v1/transactions")
    assert dipanggil["json"]["transaction_details"] == {"order_id": "ORDER-100", "gross_amount": 150000}
    assert dipanggil["headers"]["Authorization"].startswith("Basic ")


def test_buat_transaksi_gagal_melempar_gateway_request_error(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="SB-Mid-server-test", client_key="SB-Mid-client-test"))

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(401, {"error_messages": ["Access denied"]})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    with pytest.raises(gateway_client_base.GatewayRequestError, match="menolak"):
        billing_gateway_client.buat_transaksi("ORDER-100", 150000, [])


def test_buat_transaksi_timeout_melempar_gateway_timeout_error(monkeypatch):
    """REGRESI temuan audit: exception jaringan/timeout sebelumnya TIDAK
    ditangkap sama sekali, bisa lolos jadi HTTP 500 mentah -- sekarang
    gateway_client_base.post_json() menerjemahkannya jadi GatewayTimeoutError."""
    import requests as requests_lib

    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="SB-Mid-server-test", client_key="SB-Mid-client-test"))

    def fake_post(url, json, headers, timeout):
        raise requests_lib.exceptions.ConnectTimeout("connection timed out")

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    with pytest.raises(gateway_client_base.GatewayTimeoutError):
        billing_gateway_client.buat_transaksi("ORDER-100", 150000, [])


def test_client_script_url_sandbox_vs_production(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="x", client_key="y", environment="sandbox"))
    assert "sandbox" in billing_gateway_client.client_script_url()

    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="x", client_key="y", environment="production"))
    assert "sandbox" not in billing_gateway_client.client_script_url()


# ============================= cek_status_transaksi =============================

def test_cek_status_transaksi_sukses(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: _cfg(server_key="x", client_key="y"))

    def fake_get(url, headers, timeout):
        assert url.endswith("/ORDER-100/status")
        return _FakeResponse(200, {"transaction_status": "settlement", "order_id": "ORDER-100"})

    monkeypatch.setattr(gateway_client_base.requests, "get", fake_get)

    hasil = billing_gateway_client.cek_status_transaksi("ORDER-100")
    assert hasil["transaction_status"] == "settlement"


# ============================= verifikasi_signature =============================

def _hitung_signature(order_id, status_code, gross_amount, server_key):
    raw = f"{order_id}{status_code}{gross_amount}{server_key}"
    return hashlib.sha512(raw.encode()).hexdigest()


def test_verifikasi_signature_valid(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="SB-Mid-server-rahasia", client_key="x"))
    sig = _hitung_signature("ORDER-100", "200", "150000.00", "SB-Mid-server-rahasia")
    assert billing_gateway_client.verifikasi_signature("ORDER-100", "200", "150000.00", sig) is True


def test_verifikasi_signature_amount_diubah_ditolak(monkeypatch):
    """Regresi keamanan langsung dari spesifikasi Phase 4: "jangan pernah
    percaya transaction amount dari client" -- signature yang dihitung dari
    amount ASLI HARUS ditolak kalau amount yang dibandingkan diam-diam
    diubah (mis. payload notifikasi dipalsukan)."""
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="SB-Mid-server-rahasia", client_key="x"))
    sig_asli = _hitung_signature("ORDER-100", "200", "150000.00", "SB-Mid-server-rahasia")
    assert billing_gateway_client.verifikasi_signature("ORDER-100", "200", "1.00", sig_asli) is False


def test_verifikasi_signature_order_id_diubah_ditolak(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="SB-Mid-server-rahasia", client_key="x"))
    sig_asli = _hitung_signature("ORDER-100", "200", "150000.00", "SB-Mid-server-rahasia")
    assert billing_gateway_client.verifikasi_signature("ORDER-LAIN", "200", "150000.00", sig_asli) is False


def test_verifikasi_signature_server_key_salah_ditolak(monkeypatch):
    """Signature dihitung dari Server Key LAIN (mis. hasil kebocoran/salah
    tempel kredensial) HARUS ditolak begitu Server Key aktif di deployment
    ini berbeda."""
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(server_key="SB-Mid-server-benar", client_key="x"))
    sig_dari_key_lain = _hitung_signature("ORDER-100", "200", "150000.00", "SB-Mid-server-lain")
    assert billing_gateway_client.verifikasi_signature("ORDER-100", "200", "150000.00", sig_dari_key_lain) is False
