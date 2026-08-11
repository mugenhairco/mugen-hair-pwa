"""
test_billing_gateway_client.py — FONDASI Multi-Tenant Phase 4: Klien Payment Gateway Langganan SaaS
=============================================================================
Provider RESMI: Faspay Xpress v4 (lihat billing_gateway_client.py) --
kredensial datang dari `billing_gateway_db.get_config()` (DB-backed,
platform-wide Billing SaaS), BUKAN konstanta module-level yang dibaca dari
environment variable saat modul diimpor. Seluruh pengujian di sini tetap
memakai mock/simulasi (monkeypatch billing_gateway_db.get_config() + fungsi
requests.post) -- TIDAK PERNAH memanggil provider sungguhan maupun database
sungguhan, supaya suite ini tetap hijau tanpa kredensial provider apa pun.

KEAMANAN: kredensial test di sini SENGAJA nilai fiktif yang jelas berbeda
dari kredensial development sungguhan (Merchant ID 37070/User ID bot37070/
Password p@ssw0rd yang dikirim tim Faspay) -- TIDAK PERNAH menaruh
kredensial sungguhan di source code."""

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


def _cfg(merchant_id: str = "", server_key: str = "", secret_key: str = "",
         client_key: str = "", environment: str = "sandbox") -> dict:
    return {
        "merchant_id": merchant_id, "server_key": server_key, "secret_key": secret_key,
        "client_key": client_key, "environment": environment,
        "enabled": bool(merchant_id and server_key and secret_key),
    }


_MID = "37070-test"
_USER_ID = "bot-test-billing-client"
_PASSWORD = "p-test-billing-client"


# ============================= is_enabled / client_key / client_script_url =============================

def test_is_enabled_ikuti_config(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: _cfg())
    assert billing_gateway_client.is_enabled() is False
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    assert billing_gateway_client.is_enabled() is True


def test_is_production_ikuti_config(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: _cfg(environment="production"))
    assert billing_gateway_client.is_production() is True
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: _cfg(environment="sandbox"))
    assert billing_gateway_client.is_production() is False


def test_client_key_dan_script_url_selalu_none(monkeypatch):
    """Faspay Xpress v4 TIDAK punya JS SDK/client-side key -- checkout murni
    redirect ke halaman Faspay, terlepas dari status konfigurasi apa pun --
    frontend (billing.js) mengenali None ini untuk jatuh ke jalur
    window.open(redirect_url)."""
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    assert billing_gateway_client.client_key() is None
    assert billing_gateway_client.client_script_url() is None


# ============================= buat_transaksi =============================

def test_buat_transaksi_gagal_kalau_belum_dikonfigurasi(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: _cfg())
    with pytest.raises(gateway_client_base.GatewayNotConfiguredError, match="belum dikonfigurasi"):
        billing_gateway_client.buat_transaksi("ORDER-1", 100000, [])


def test_buat_transaksi_sukses(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["url"] = url
        dipanggil["json"] = json
        return _FakeResponse(200, {
            "response_code": "00", "response_desc": "Success",
            "redirect_url": "https://xpress-sandbox.faspay.co.id/checkout/abc",
        })

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    hasil = billing_gateway_client.buat_transaksi(
        "ORDER-100", 150000,
        [{"id": "pkg-basic", "price": 150000, "quantity": 1, "name": "Paket Basic"}],
        customer_details={"first_name": "Budi", "phone": "081234567890", "email": "budi@example.test"},
    )
    assert hasil == {"token": None, "redirect_url": "https://xpress-sandbox.faspay.co.id/checkout/abc"}
    assert dipanggil["url"] == "https://xpress-sandbox.faspay.co.id/v4/post"
    payload = dipanggil["json"]
    assert payload["merchant_id"] == _MID
    assert payload["bill_no"] == "ORDER-100"
    assert payload["bill_total"] == "150000"
    assert payload["cust_name"] == "Budi"
    assert payload["msisdn"] == "081234567890"
    assert payload["email"] == "budi@example.test"
    assert payload["item"] == [{"product": "Paket Basic", "qty": "1", "amount": "150000"}]
    assert payload["signature"] == gateway_client_base.sign_sha1_of_md5(
        [_USER_ID, _PASSWORD, "ORDER-100", "150000"])


def test_buat_transaksi_fallback_email_msisdn_kalau_kosong(monkeypatch):
    """customer_details boleh tidak lengkap (mis. Owner tenant lama belum
    isi whatsapp/email saat registrasi) -- WAJIB tetap terkirim ke Faspay
    pakai nilai fallback, bukan meledak/mengirim string kosong."""
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["json"] = json
        return _FakeResponse(200, {"response_code": "00", "redirect_url": "https://example.test/x"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    billing_gateway_client.buat_transaksi("ORDER-101", 50000, [], customer_details={})
    assert dipanggil["json"]["email"] == "support@rivoirsett.com"
    assert dipanggil["json"]["msisdn"] == "628000000000"
    assert dipanggil["json"]["cust_name"] == "Owner"


def test_buat_transaksi_response_code_bukan_00_melempar_gateway_request_error(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(200, {"response_code": "01", "response_desc": "Signature tidak valid"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    with pytest.raises(gateway_client_base.GatewayRequestError, match="menolak"):
        billing_gateway_client.buat_transaksi("ORDER-100", 150000, [])


def test_buat_transaksi_timeout_melempar_gateway_timeout_error(monkeypatch):
    """REGRESI temuan audit: exception jaringan/timeout sebelumnya TIDAK
    ditangkap sama sekali, bisa lolos jadi HTTP 500 mentah -- sekarang
    gateway_client_base.post_json() menerjemahkannya jadi GatewayTimeoutError."""
    import requests as requests_lib

    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    def fake_post(url, json, headers, timeout):
        raise requests_lib.exceptions.ConnectTimeout("connection timed out")

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    with pytest.raises(gateway_client_base.GatewayTimeoutError):
        billing_gateway_client.buat_transaksi("ORDER-100", 150000, [])


def test_buat_transaksi_environment_production_pakai_base_url_production(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD,
                                      environment="production"))

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["url"] = url
        return _FakeResponse(200, {"response_code": "00", "redirect_url": "https://example.test/x"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    billing_gateway_client.buat_transaksi("ORDER-100", 150000, [])
    assert dipanggil["url"] == "https://xpress.faspay.co.id/v4/post"


# ============================= cek_status_transaksi (SENGAJA dinonaktifkan) =============================

def test_cek_status_transaksi_belum_tersedia_untuk_faspay(monkeypatch):
    """SESUAI KEPUTUSAN: dokumentasi resmi Faspay Xpress v4 belum mencakup
    endpoint Inquiry/Check Status -- fitur "Cek Ulang ke Provider" untuk
    langganan SaaS SENGAJA dinonaktifkan (melempar error jelas), BUKAN
    diimplementasikan berdasarkan tebakan endpoint."""
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    with pytest.raises(gateway_client_base.GatewayError, match="Inquiry/Check Status belum tersedia"):
        billing_gateway_client.cek_status_transaksi("ORDER-1")


# ============================= verifikasi_signature =============================

def _hitung_signature(bill_no, payment_status_code, user_id=_USER_ID, password=_PASSWORD):
    return gateway_client_base.sign_sha1_of_md5([user_id, password, bill_no, payment_status_code])


def test_verifikasi_signature_selalu_false_tanpa_kredensial(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: _cfg())
    assert billing_gateway_client.verifikasi_signature("ORDER-1", "2", "apapun") is False


def test_verifikasi_signature_valid(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    sig = _hitung_signature("ORDER-100", "2")
    assert billing_gateway_client.verifikasi_signature("ORDER-100", "2", sig) is True


def test_verifikasi_signature_status_code_diubah_ditolak(monkeypatch):
    """Regresi keamanan langsung dari spesifikasi Phase 4: "jangan pernah
    percaya data dari client begitu saja" -- signature yang dihitung dari
    payment_status_code ASLI HARUS ditolak kalau status yang dibandingkan
    diam-diam diubah (mis. payload notifikasi dipalsukan)."""
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    sig_asli = _hitung_signature("ORDER-100", "2")
    assert billing_gateway_client.verifikasi_signature("ORDER-100", "3", sig_asli) is False


def test_verifikasi_signature_bill_no_diubah_ditolak(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    sig_asli = _hitung_signature("ORDER-100", "2")
    assert billing_gateway_client.verifikasi_signature("ORDER-LAIN", "2", sig_asli) is False


def test_verifikasi_signature_kredensial_salah_ditolak(monkeypatch):
    """Signature dihitung dari User ID/Password LAIN (mis. hasil kebocoran/
    salah tempel kredensial) HARUS ditolak begitu kredensial aktif di
    deployment ini berbeda."""
    monkeypatch.setattr(billing_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    sig_dari_kredensial_lain = _hitung_signature("ORDER-100", "2", user_id="bot-lain", password="password-lain")
    assert billing_gateway_client.verifikasi_signature("ORDER-100", "2", sig_dari_kredensial_lain) is False
