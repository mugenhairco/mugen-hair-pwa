"""
test_payment_gateway_client.py — Implementasi Payment Gateway & Riwayat
Transaksi Multi-Tenant: Klien Payment Gateway Booking Customer
=============================================================================
Provider RESMI: Faspay Xpress v4 (lihat payment_gateway_client.py) --
kredensial datang dari `payment_gateway_db.get_config()` (DB-backed,
platform-wide Payment Gateway booking), BUKAN konstanta module-level.
Seluruh pengujian di sini memakai mock/simulasi (monkeypatch
payment_gateway_db.get_config() + fungsi requests.post) -- TIDAK PERNAH
memanggil provider sungguhan maupun database sungguhan.

Sebelum audit ini, payment_gateway_client.py (booking) TIDAK punya test
langsung sama sekali (hanya diuji tidak langsung lewat mock penuh di
test_booking_gateway.py) -- file ini menutup celah itu, pola SAMA PERSIS
dengan test_billing_gateway_client.py (langganan SaaS) yang sudah ada.

KEAMANAN: kredensial test di sini SENGAJA nilai fiktif yang jelas berbeda
dari kredensial development sungguhan (Merchant ID 37070/User ID bot37070/
Password p@ssw0rd yang dikirim tim Faspay) -- TIDAK PERNAH menaruh
kredensial sungguhan di source code."""

import datetime as dt_module

import pytest

import gateway_client_base
import payment_gateway_client
import payment_gateway_db


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _cfg(merchant_id: str = "", server_key: str = "", secret_key: str = "",
         client_key: str = "", environment: str = "sandbox", metode_aktif: list = None) -> dict:
    return {
        "pgw_merchant_id": merchant_id, "pgw_server_key": server_key, "pgw_secret_key": secret_key,
        "pgw_client_key": client_key, "pgw_environment": environment,
        "metode_aktif": metode_aktif or [],
    }


_MID = "37070-test"
_USER_ID = "bot-test-payment-client"
_PASSWORD = "p-test-payment-client"


# ============================= is_enabled / client_key / client_script_url =============================

def test_is_enabled_ikuti_config(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config", lambda: _cfg())
    assert payment_gateway_client.is_enabled() is False
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    assert payment_gateway_client.is_enabled() is True


def test_is_production_ikuti_config(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config", lambda: _cfg(environment="production"))
    assert payment_gateway_client.is_production() is True
    monkeypatch.setattr(payment_gateway_db, "get_config", lambda: _cfg(environment="sandbox"))
    assert payment_gateway_client.is_production() is False


def test_client_key_dan_script_url_selalu_none(monkeypatch):
    """Faspay Xpress v4 TIDAK punya JS SDK/client-side key -- checkout murni
    redirect ke halaman Faspay, terlepas dari status konfigurasi apa pun --
    frontend (book_public.js) mengenali None ini untuk jatuh ke jalur
    window.open(redirect_url)."""
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    assert payment_gateway_client.client_key() is None
    assert payment_gateway_client.client_script_url() is None


# ============================= buat_transaksi =============================

def test_buat_transaksi_gagal_kalau_belum_dikonfigurasi(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config", lambda: _cfg())
    with pytest.raises(gateway_client_base.GatewayNotConfiguredError, match="belum dikonfigurasi"):
        payment_gateway_client.buat_transaksi("BOOK-1", 100000, [])


def test_buat_transaksi_sukses(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
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

    hasil = payment_gateway_client.buat_transaksi(
        "BOOK-1-1-abc", 150000,
        [{"id": "1", "price": 150000, "quantity": 1, "name": "Dry Cut"}],
        customer_details={"first_name": "Budi", "phone": "081234567890"},
    )
    assert hasil == {"token": None, "redirect_url": "https://xpress-sandbox.faspay.co.id/checkout/abc"}
    assert dipanggil["url"] == "https://xpress-sandbox.faspay.co.id/v4/post"
    payload = dipanggil["json"]
    assert payload["merchant_id"] == _MID
    assert payload["bill_no"] == "BOOK-1-1-abc"
    assert payload["bill_total"] == "150000"
    assert payload["cust_name"] == "Budi"
    assert payload["msisdn"] == "081234567890"
    assert payload["email"] == "support@rivoirsett.com"  # fallback -- form booking publik tidak punya field email
    assert payload["item"] == [{"product": "Dry Cut", "qty": "1", "amount": "150000"}]
    assert payload["signature"] == gateway_client_base.sign_sha1_of_md5(
        [_USER_ID, _PASSWORD, "BOOK-1-1-abc", "150000"])


def test_buat_transaksi_fallback_msisdn_kalau_kosong(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["json"] = json
        return _FakeResponse(200, {"response_code": "00", "redirect_url": "https://example.test/x"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    payment_gateway_client.buat_transaksi("BOOK-1", 50000, [], customer_details={})
    assert dipanggil["json"]["msisdn"] == "628000000000"
    assert dipanggil["json"]["cust_name"] == "Customer"


def test_buat_transaksi_response_code_bukan_00_melempar_gateway_request_error(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(200, {"response_code": "01", "response_desc": "Signature tidak valid"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    with pytest.raises(gateway_client_base.GatewayRequestError, match="menolak"):
        payment_gateway_client.buat_transaksi("BOOK-1", 150000, [])


def test_buat_transaksi_timeout_melempar_gateway_timeout_error(monkeypatch):
    import requests as requests_lib

    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    def fake_post(url, json, headers, timeout):
        raise requests_lib.exceptions.ConnectTimeout("connection timed out")

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    with pytest.raises(gateway_client_base.GatewayTimeoutError):
        payment_gateway_client.buat_transaksi("BOOK-1", 150000, [])


def test_buat_transaksi_environment_production_pakai_base_url_production(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD,
                                      environment="production"))

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["url"] = url
        return _FakeResponse(200, {"response_code": "00", "redirect_url": "https://example.test/x"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    payment_gateway_client.buat_transaksi("BOOK-1", 150000, [])
    assert dipanggil["url"] == "https://xpress.faspay.co.id/v4/post"


def test_buat_transaksi_bill_expired_wib_setelah_bill_date(monkeypatch):
    """AUDIT (UAT Faspay -- "bill expired must be greater than today"):
    bill_date/bill_expired WAJIB dihitung dari gateway_client_base.now_wib()
    (Asia/Jakarta), BUKAN datetime.now() polos yang di server Render
    (default UTC, 7 jam di belakang WIB) membuat Faspay menganggap
    bill_expired sudah lewat."""
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    waktu_tetap = dt_module.datetime(2026, 8, 11, 14, 0, 0, tzinfo=gateway_client_base.WIB)
    monkeypatch.setattr(gateway_client_base, "now_wib", lambda: waktu_tetap)

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["json"] = json
        return _FakeResponse(200, {"response_code": "00", "redirect_url": "https://example.test/x"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    payment_gateway_client.buat_transaksi("BOOK-1", 150000, [])
    payload = dipanggil["json"]
    assert payload["bill_date"] == "2026-08-11 14:00:00"
    assert payload["bill_expired"] == "2026-08-11 14:30:00"


def test_buat_transaksi_item_product_disanitasi(monkeypatch):
    """AUDIT (UAT Faspay -- "item[product] must be alphanumeric"): nama
    layanan sungguhan lazim mengandung simbol (mis. "Cut & Wash", "Hair
    Coloring (Full)") -- Faspay menolaknya mentah-mentah, item[].product
    WAJIB sudah disanitasi jadi alphanumeric+spasi sebelum dikirim."""
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["json"] = json
        return _FakeResponse(200, {"response_code": "00", "redirect_url": "https://example.test/x"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    payment_gateway_client.buat_transaksi(
        "BOOK-1", 200000,
        [
            {"id": "1", "price": 100000, "quantity": 1, "name": "Cut & Wash"},
            {"id": "2", "price": 100000, "quantity": 1, "name": "Hair Coloring (Full)"},
        ],
    )
    assert dipanggil["json"]["item"] == [
        {"product": "Cut Wash", "qty": "1", "amount": "100000"},
        {"product": "Hair Coloring Full", "qty": "1", "amount": "100000"},
    ]


def test_buat_transaksi_item_product_kosong_pakai_fallback(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["json"] = json
        return _FakeResponse(200, {"response_code": "00", "redirect_url": "https://example.test/x"})

    monkeypatch.setattr(gateway_client_base.requests, "post", fake_post)

    payment_gateway_client.buat_transaksi(
        "BOOK-1", 100000, [{"id": "1", "price": 100000, "quantity": 1, "name": "###"}],
    )
    assert dipanggil["json"]["item"] == [{"product": "Layanan", "qty": "1", "amount": "100000"}]


# ============================= cek_status_transaksi (SENGAJA dinonaktifkan) =============================

def test_cek_status_transaksi_belum_tersedia_untuk_faspay(monkeypatch):
    """SESUAI KEPUTUSAN: dokumentasi resmi Faspay Xpress v4 belum mencakup
    endpoint Inquiry/Check Status -- fitur "Cek Ulang ke Provider" untuk
    booking SENGAJA dinonaktifkan (melempar error jelas), BUKAN
    diimplementasikan berdasarkan tebakan."""
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    with pytest.raises(gateway_client_base.GatewayError, match="Inquiry/Check Status belum tersedia"):
        payment_gateway_client.cek_status_transaksi("BOOK-1")


# ============================= verifikasi_signature =============================

def _hitung_signature(bill_no, payment_status_code, user_id=_USER_ID, password=_PASSWORD):
    return gateway_client_base.sign_sha1_of_md5([user_id, password, bill_no, payment_status_code])


def test_verifikasi_signature_selalu_false_tanpa_kredensial(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config", lambda: _cfg())
    assert payment_gateway_client.verifikasi_signature("BOOK-1", "2", "apapun") is False


def test_verifikasi_signature_valid(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    sig = _hitung_signature("BOOK-1", "2")
    assert payment_gateway_client.verifikasi_signature("BOOK-1", "2", sig) is True


def test_verifikasi_signature_status_code_diubah_ditolak(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    sig_asli = _hitung_signature("BOOK-1", "2")
    assert payment_gateway_client.verifikasi_signature("BOOK-1", "3", sig_asli) is False


def test_verifikasi_signature_bill_no_diubah_ditolak(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    sig_asli = _hitung_signature("BOOK-1", "2")
    assert payment_gateway_client.verifikasi_signature("BOOK-LAIN", "2", sig_asli) is False


def test_verifikasi_signature_kredensial_salah_ditolak(monkeypatch):
    monkeypatch.setattr(payment_gateway_db, "get_config",
                         lambda: _cfg(merchant_id=_MID, server_key=_USER_ID, secret_key=_PASSWORD))
    sig_dari_kredensial_lain = _hitung_signature("BOOK-1", "2", user_id="bot-lain", password="password-lain")
    assert payment_gateway_client.verifikasi_signature("BOOK-1", "2", sig_dari_kredensial_lain) is False
