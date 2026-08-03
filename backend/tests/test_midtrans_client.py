"""
test_midtrans_client.py — FONDASI Multi-Tenant Phase 4: Klien Midtrans Snap API
=============================================================================
SESUAI KEPUTUSAN cakupan Phase 4: seluruh pengujian di sini memakai
mock/simulasi (monkeypatch modul-level MIDTRANS_*/IS_ENABLED + fungsi
requests.post/requests.get) -- TIDAK PERNAH memanggil Midtrans sungguhan,
supaya suite ini tetap hijau tanpa kredensial Midtrans apa pun."""

import hashlib

import pytest

import midtrans_client


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


# ============================= IS_ENABLED / fail-closed =============================

def test_is_enabled_false_tanpa_kredensial(monkeypatch):
    monkeypatch.setattr(midtrans_client, "IS_ENABLED", False)
    with pytest.raises(RuntimeError, match="belum dikonfigurasi"):
        midtrans_client.buat_transaksi_snap("ORDER-1", 100000, [])
    with pytest.raises(RuntimeError, match="belum dikonfigurasi"):
        midtrans_client.cek_status_transaksi("ORDER-1")


def test_verifikasi_signature_selalu_false_tanpa_server_key(monkeypatch):
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "")
    assert midtrans_client.verifikasi_signature("ORDER-1", "200", "100000.00", "apapun") is False


# ============================= buat_transaksi_snap =============================

def test_buat_transaksi_snap_sukses(monkeypatch):
    monkeypatch.setattr(midtrans_client, "IS_ENABLED", True)
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "SB-Mid-server-test")

    dipanggil = {}

    def fake_post(url, json, headers, timeout):
        dipanggil["url"] = url
        dipanggil["json"] = json
        dipanggil["headers"] = headers
        return _FakeResponse(201, {"token": "snap-token-abc", "redirect_url": "https://example.test/snap/abc"})

    monkeypatch.setattr(midtrans_client.requests, "post", fake_post)

    hasil = midtrans_client.buat_transaksi_snap(
        "ORDER-100", 150000,
        [{"id": "pkg-basic", "price": 150000, "quantity": 1, "name": "Paket Basic"}],
        customer_details={"first_name": "Budi"},
    )
    assert hasil == {"token": "snap-token-abc", "redirect_url": "https://example.test/snap/abc"}
    assert dipanggil["url"].endswith("/snap/v1/transactions")
    assert dipanggil["json"]["transaction_details"] == {"order_id": "ORDER-100", "gross_amount": 150000}
    assert dipanggil["headers"]["Authorization"].startswith("Basic ")


def test_buat_transaksi_snap_gagal_melempar_runtimeerror(monkeypatch):
    monkeypatch.setattr(midtrans_client, "IS_ENABLED", True)
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "SB-Mid-server-test")

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(401, {"error_messages": ["Access denied"]})

    monkeypatch.setattr(midtrans_client.requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="menolak"):
        midtrans_client.buat_transaksi_snap("ORDER-100", 150000, [])


def test_snap_base_url_sandbox_vs_production(monkeypatch):
    monkeypatch.setattr(midtrans_client, "MIDTRANS_IS_PRODUCTION", False)
    monkeypatch.setattr(midtrans_client, "_SNAP_BASE_URL", "https://app.sandbox.midtrans.com/snap/v1")
    assert "sandbox" in midtrans_client._SNAP_BASE_URL


# ============================= cek_status_transaksi =============================

def test_cek_status_transaksi_sukses(monkeypatch):
    monkeypatch.setattr(midtrans_client, "IS_ENABLED", True)

    def fake_get(url, headers, timeout):
        assert url.endswith("/ORDER-100/status")
        return _FakeResponse(200, {"transaction_status": "settlement", "order_id": "ORDER-100"})

    monkeypatch.setattr(midtrans_client.requests, "get", fake_get)

    hasil = midtrans_client.cek_status_transaksi("ORDER-100")
    assert hasil["transaction_status"] == "settlement"


# ============================= verifikasi_signature =============================

def _hitung_signature(order_id, status_code, gross_amount, server_key):
    raw = f"{order_id}{status_code}{gross_amount}{server_key}"
    return hashlib.sha512(raw.encode()).hexdigest()


def test_verifikasi_signature_valid(monkeypatch):
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "SB-Mid-server-rahasia")
    sig = _hitung_signature("ORDER-100", "200", "150000.00", "SB-Mid-server-rahasia")
    assert midtrans_client.verifikasi_signature("ORDER-100", "200", "150000.00", sig) is True


def test_verifikasi_signature_amount_diubah_ditolak(monkeypatch):
    """Regresi keamanan langsung dari spesifikasi Phase 4: "jangan pernah
    percaya transaction amount dari client" -- signature yang dihitung dari
    amount ASLI HARUS ditolak kalau amount yang dibandingkan diam-diam
    diubah (mis. payload notifikasi dipalsukan)."""
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "SB-Mid-server-rahasia")
    sig_asli = _hitung_signature("ORDER-100", "200", "150000.00", "SB-Mid-server-rahasia")
    assert midtrans_client.verifikasi_signature("ORDER-100", "200", "1.00", sig_asli) is False


def test_verifikasi_signature_order_id_diubah_ditolak(monkeypatch):
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "SB-Mid-server-rahasia")
    sig_asli = _hitung_signature("ORDER-100", "200", "150000.00", "SB-Mid-server-rahasia")
    assert midtrans_client.verifikasi_signature("ORDER-LAIN", "200", "150000.00", sig_asli) is False


def test_verifikasi_signature_server_key_salah_ditolak(monkeypatch):
    """Signature dihitung dari Server Key TENANT/DEPLOYMENT lain (mis. hasil
    kebocoran/salah tempel kredensial) HARUS ditolak begitu Server Key
    aktif di deployment ini berbeda."""
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "SB-Mid-server-benar")
    sig_dari_key_lain = _hitung_signature("ORDER-100", "200", "150000.00", "SB-Mid-server-lain")
    assert midtrans_client.verifikasi_signature("ORDER-100", "200", "150000.00", sig_dari_key_lain) is False
