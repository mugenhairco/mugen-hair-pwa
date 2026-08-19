"""test_booking_verifikasi_manual.py — FITUR Pembayaran Manual QRIS Tenant +
Notifikasi WhatsApp ("Verifikasi Booking" / "Payment Diterima")
=============================================================================
Cakupan: booking_db.terima_booking() ("Verifikasi Booking") DAN
verifikasi_pembayaran() ("Payment Diterima") diperluas -- dua aksi
INDEPENDEN (booking boleh langsung dibayar tanpa pernah "diterima" admin
dulu, dan sebaliknya), masing-masing idempoten (klik dobel TIDAK menimpa
catatan waktu/oleh yang sudah ada & TIDAK kirim WA dua kali), WA
"reminder_qris" dari terima_booking() HANYA untuk metode "qris" yang belum
dibayar, endpoint /terima menolak metode "gateway" (SAMA seperti /verifikasi
yang sudah ada), dan Faspay/gateway webhook (booking_gateway_webhook.py)
SAMA SEKALI TIDAK disentuh -- tetap memanggil verifikasi_pembayaran() tanpa
`oleh` seperti sebelumnya.

SEMUA test memonkeypatch whatsapp_service.kirim_whatsapp -- TIDAK PERNAH
memanggil Fonnte sungguhan."""

import hashlib
import itertools
from datetime import timedelta

import booking_db
import booking_gateway_db
import booking_gateway_webhook
import database as db
import payment_gateway_db
import subscription_db
import tenant_db
from booking_db import _hari_ini_wib

_urutan_unik = itertools.count(1)


def _beri_fitur_whatsapp_reminder(tenant_id):
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")


def _siapkan_barber_dan_service(tenant_id, nominal=100000):
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber BVM T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Potong Rambut BVM T{tenant_id}-{n}", nominal, tenant_id=tenant_id)
    return barber_id, service_id


def _buat_booking(tenant_id, metode_pembayaran, nominal=100000, hari_offset=1):
    booking_db.update_payment_settings(metode_aktif=["transfer", "qris", "gateway"], tenant_id=tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id, nominal)
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    return booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                    service_ids=[service_id], customer_nama="Budi",
                                    customer_whatsapp="081234567890", metode_pembayaran=metode_pembayaran,
                                    tenant_id=tenant_id)


def _pasang_penangkap_wa(monkeypatch):
    panggilan = []
    def _tangkap(nomor, pesan, tenant_id=None):
        panggilan.append({"nomor": nomor, "pesan": pesan, "tenant_id": tenant_id})
        return True
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", _tangkap)
    return panggilan


# ---------------------------------------------------------------------------
# terima_booking() -- "Verifikasi Booking"
# ---------------------------------------------------------------------------

def test_terima_booking_qris_belum_bayar_mengirim_reminder_dan_mencatat_oleh_waktu(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    booking = _buat_booking(tenant_id, "qris")
    panggilan = _pasang_penangkap_wa(monkeypatch)  # dipasang SETELAH buat_booking -- reminder saat create tidak ikut terhitung

    booking_db.terima_booking(booking["id"], oleh="admin1")

    assert len(panggilan) == 1
    assert "silakan selesaikan pembayaran" in panggilan[0]["pesan"].lower()

    hasil = booking_db.get_booking(booking["id"])
    assert hasil["verifikasi_booking_oleh"] == "admin1"
    assert hasil["verifikasi_booking_at"] is not None
    # Payment Diterima BELUM ditekan -- kolomnya tetap kosong.
    assert hasil["pembayaran_diterima_at"] is None
    assert hasil["pembayaran_diterima_oleh"] is None


def test_terima_booking_qris_idempoten_klik_dobel_tidak_kirim_wa_lagi_dan_tidak_timpa_catatan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    booking = _buat_booking(tenant_id, "qris")
    panggilan = _pasang_penangkap_wa(monkeypatch)

    booking_db.terima_booking(booking["id"], oleh="admin1")
    tercatat_pertama = booking_db.get_booking(booking["id"])["verifikasi_booking_at"]

    booking_db.terima_booking(booking["id"], oleh="admin2")  # klik dobel, admin lain
    hasil = booking_db.get_booking(booking["id"])

    assert len(panggilan) == 1  # TIDAK kirim WA kedua kalinya
    assert hasil["verifikasi_booking_oleh"] == "admin1"  # TIDAK ditimpa admin2
    assert hasil["verifikasi_booking_at"] == tercatat_pertama


def test_terima_booking_transfer_tidak_mengirim_wa_tapi_tetap_mencatat(single_tenant, monkeypatch):
    """Metode "transfer" TIDAK punya template "cara bayar" yang relevan
    (reminder_qris eksplisit menyebut QRIS) -- terima_booking() tetap
    mencatat verifikasi_booking_at/oleh, TAPI tidak mencoba kirim WA sama
    sekali."""
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    booking = _buat_booking(tenant_id, "transfer")
    panggilan = _pasang_penangkap_wa(monkeypatch)

    booking_db.terima_booking(booking["id"], oleh="admin1")

    assert len(panggilan) == 0
    hasil = booking_db.get_booking(booking["id"])
    assert hasil["verifikasi_booking_oleh"] == "admin1"
    assert hasil["verifikasi_booking_at"] is not None


def test_terima_booking_qris_customer_sudah_bayar_duluan_tidak_kirim_reminder(single_tenant, monkeypatch):
    """SESUAI SPEK: kalau customer ternyata sudah membayar sebelum
    "Verifikasi Booking" ditekan, pesan "silakan bayar" TIDAK relevan lagi
    -- tidak boleh dikirim, walau booking-nya tetap tercatat "diverifikasi"."""
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    booking = _buat_booking(tenant_id, "qris")
    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin1")  # Payment Diterima DULUAN
    panggilan = _pasang_penangkap_wa(monkeypatch)

    booking_db.terima_booking(booking["id"], oleh="admin1")

    assert len(panggilan) == 0
    hasil = booking_db.get_booking(booking["id"])
    assert hasil["verifikasi_booking_at"] is not None  # tetap tercatat diverifikasi


def test_terima_booking_dibatalkan_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _buat_booking(tenant_id, "qris")
    booking_db.batalkan_booking(booking["id"])
    import pytest
    with pytest.raises(ValueError):
        booking_db.terima_booking(booking["id"])


# ---------------------------------------------------------------------------
# verifikasi_pembayaran() -- "Payment Diterima" (independen dari terima_booking())
# ---------------------------------------------------------------------------

def test_payment_diterima_tanpa_verifikasi_booking_dulu(single_tenant, monkeypatch):
    """SKENARIO WAJIB #2 -- customer langsung membayar TANPA "Verifikasi
    Booking" pernah ditekan sama sekali: "Payment Diterima" tetap harus
    bisa langsung dipakai."""
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    booking = _buat_booking(tenant_id, "qris")
    panggilan = _pasang_penangkap_wa(monkeypatch)
    assert booking_db.get_booking(booking["id"])["verifikasi_booking_at"] is None  # belum pernah "diterima"

    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin1")

    hasil = booking_db.get_booking(booking["id"])
    assert hasil["status_pembayaran"] == "terverifikasi"
    assert hasil["pembayaran_diterima_oleh"] == "admin1"
    assert hasil["pembayaran_diterima_at"] is not None
    assert hasil["verifikasi_booking_at"] is None  # TETAP tidak pernah "diterima" -- tidak disyaratkan
    assert len(panggilan) == 1
    assert "terima & verifikasi" in panggilan[0]["pesan"]


def test_payment_diterima_idempoten_tidak_timpa_catatan_pertama(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    booking = _buat_booking(tenant_id, "transfer")
    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin1")
    tercatat_pertama = booking_db.get_booking(booking["id"])["pembayaran_diterima_at"]
    panggilan = _pasang_penangkap_wa(monkeypatch)

    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin2")  # klik dobel

    hasil = booking_db.get_booking(booking["id"])
    assert len(panggilan) == 0  # TIDAK kirim WA kedua kalinya
    assert hasil["pembayaran_diterima_oleh"] == "admin1"  # TIDAK ditimpa
    assert hasil["pembayaran_diterima_at"] == tercatat_pertama


def test_webhook_faspay_tidak_mencatat_oleh_manusia(single_tenant, monkeypatch):
    """Faspay/gateway webhook TIDAK boleh berubah sama sekali -- tetap
    memanggil verifikasi_pembayaran() TANPA `oleh` (tidak ada admin manusia
    di jalur otomatis ini), kolom pembayaran_diterima_oleh tetap NULL
    walau pembayaran_diterima_at tetap tercatat (pembayaran memang benar-
    benar terjadi saat itu)."""
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    payment_gateway_db.update_config(merchant_id="37070", server_key="bot-test", secret_key="pass-test")
    booking = _buat_booking(tenant_id, "gateway", nominal=100000)
    tenant = tenant_db.get_tenant(tenant_id)
    order_id = booking_gateway_db.buat_order_id(tenant_id, booking["id"])
    booking_gateway_db.buat_transaksi(
        order_id, tenant_id, tenant["nama_barbershop"] if tenant else "-", booking["id"],
        booking["customer_nama"], booking["nama_barber"], booking["daftar_service"], booking["total_harga"],
        checkout_token="tok-test", checkout_redirect_url="https://example.test/pay",
    )
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)

    tahap1 = hashlib.md5(f"bot-testpass-test{order_id}2".encode()).hexdigest()
    signature = hashlib.sha1(tahap1.encode()).hexdigest()
    payload = {
        "bill_no": order_id, "payment_status_code": "2", "bill_total": str(booking["total_harga"]),
        "signature": signature, "payment_channel": "QRIS", "trx_id": "899999999999", "payment_reff": "null",
    }
    booking_gateway_webhook.proses_notifikasi(payload)

    hasil = booking_db.get_booking(booking["id"])
    assert hasil["status_pembayaran"] == "terverifikasi"
    assert hasil["pembayaran_diterima_at"] is not None
    assert hasil["pembayaran_diterima_oleh"] is None


# ---------------------------------------------------------------------------
# Endpoint HTTP -- routers/booking.py::terima_booking()/verifikasi_booking()
# ---------------------------------------------------------------------------

def test_endpoint_terima_booking_owner_sukses_dan_mencatat_username(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    booking = _buat_booking(tenant_id, "qris")

    r = client.post(f"/api/booking/{booking['id']}/terima", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["verifikasi_booking_at"] is not None
    assert r.json()["verifikasi_booking_oleh"]  # username owner tercatat


def test_endpoint_terima_booking_metode_gateway_ditolak_422(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    payment_gateway_db.update_config(merchant_id="37070", server_key="bot-test2", secret_key="pass-test2")
    booking = _buat_booking(tenant_id, "gateway")

    r = client.post(f"/api/booking/{booking['id']}/terima", headers=headers)
    assert r.status_code == 422


def test_endpoint_verifikasi_pembayaran_mencatat_username(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    booking = _buat_booking(tenant_id, "transfer")

    r = client.post(f"/api/booking/{booking['id']}/verifikasi", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["pembayaran_diterima_at"] is not None
    assert r.json()["pembayaran_diterima_oleh"]  # username owner tercatat
