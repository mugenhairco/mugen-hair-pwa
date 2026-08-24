"""test_payment_provider_client.py — Seam Payment Gateway DINAMIS
=============================================================================
Cakupan: payment_provider_client.py MURNI sebagai dispatcher tipis ke
snap_advance_client.py -- buat_transaksi() memilih fungsi client yang benar
berdasarkan channel, channel "direct_debit" melempar pending_faspay (belum
bisa dipakai checkout sama sekali), channel tidak dikenal ditolak jelas.
TIDAK menguji ulang isi snap_advance_client.py sendiri (formula
signature/request Faspay dkk sudah diuji test_snap_advance.py) -- di sini
HANYA memastikan seam-nya memanggil fungsi yang tepat."""

import pytest

import payment_provider_client
import snap_advance_client


def test_dispatch_va_memanggil_snap_advance_client_buat_transaksi_va(monkeypatch):
    dipanggil = {}

    def _fake(payment_reference, amount, customer_details):
        dipanggil["args"] = (payment_reference, amount, customer_details)
        return {"va_number": "70212345678901"}
    monkeypatch.setattr(snap_advance_client, "buat_transaksi_va", _fake)

    hasil = payment_provider_client.buat_transaksi("va", "BOOKING-1-1-abc", 100000, {"nama": "Budi"})
    assert hasil == {"va_number": "70212345678901"}
    assert dipanggil["args"] == ("BOOKING-1-1-abc", 100000, {"nama": "Budi"})


def test_dispatch_qris_memanggil_snap_advance_client_buat_transaksi_qris(monkeypatch):
    dipanggil = {}

    def _fake(payment_reference, amount, customer_details):
        dipanggil["args"] = (payment_reference, amount, customer_details)
        return {"qr_url": "https://example.test/qr.png"}
    monkeypatch.setattr(snap_advance_client, "buat_transaksi_qris", _fake)

    hasil = payment_provider_client.buat_transaksi("qris", "BOOKING-1-1-abc", 100000, {"whatsapp": "081234567890"})
    assert hasil == {"qr_url": "https://example.test/qr.png"}
    assert dipanggil["args"] == ("BOOKING-1-1-abc", 100000, {"whatsapp": "081234567890"})


def test_dispatch_direct_debit_melempar_pending_faspay():
    """Registrasi/Account Binding Direct Debit belum dikonfirmasi Faspay --
    channel ini SENGAJA tidak boleh dipakai checkout sama sekali, seam
    menolaknya SEBELUM menyentuh snap_advance_client.py."""
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        payment_provider_client.buat_transaksi("direct_debit", "BOOKING-1-1-abc", 100000, {})


def test_dispatch_channel_tidak_dikenal_raise_valueerror():
    with pytest.raises(ValueError):
        payment_provider_client.buat_transaksi("ewallet", "BOOKING-1-1-abc", 100000, {})


def test_channel_label_va_dan_qris(app_client):
    import snap_advance_db
    snap_advance_db.update_config(va_channel_code="702", qris_channel_code="715")
    assert payment_provider_client.channel_label("va") == "BCA VA (Dynamic)"
    assert payment_provider_client.channel_label("qris") == "LinkAja QRIS"
    assert payment_provider_client.channel_label("direct_debit") is None
