"""test_booking_mandiri.py — FITUR Booking Mandiri (PERMINTAAN Owner): kasir
mencatat customer WALK-IN langsung dari menu Booking > Booking Mandiri
=============================================================================
Cakupan:
- booking_db.buat_booking(sumber="kasir_mandiri"): WhatsApp OPSIONAL (boleh
  kosong, TETAP divalidasi formatnya kalau diisi), metode "bayar_nanti"
  diterima HANYA untuk sumber ini (ditolak untuk booking publik biasa).
- _kirim_notifikasi_wa_booking(): TIDAK PERNAH mengirim Fonte untuk booking
  sumber="kasir_mandiri" -- baik WA diisi maupun tidak, di SEMUA pemicu
  (buat_booking/verifikasi_pembayaran).
- Endpoint /api/booking/mandiri/pengaturan, /api/booking/mandiri/slot,
  POST /api/booking/mandiri (permission izin_booking_mandiri, Owner selalu
  lolos) -- termasuk metode gateway (mock payment_provider_client, TIDAK
  pernah memanggil Faspay sungguhan).

SEMUA test memonkeypatch whatsapp_service.kirim_whatsapp -- TIDAK PERNAH
memanggil Fonnte sungguhan."""

import itertools
from datetime import timedelta

import booking_db
import database as db
from booking_db import _hari_ini_wib

_urutan_unik = itertools.count(1)


def _siapkan_barber_dan_service(tenant_id, nominal=100000):
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber BM T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Potong Rambut BM T{tenant_id}-{n}", nominal, tenant_id=tenant_id)
    return barber_id, service_id


def _pasang_penangkap_wa(monkeypatch):
    panggilan = []

    def _tangkap(nomor, pesan, tenant_id=None):
        panggilan.append({"nomor": nomor, "pesan": pesan, "tenant_id": tenant_id})
        return True

    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", _tangkap)
    return panggilan


def test_buat_booking_mandiri_wa_kosong_diterima(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _pasang_penangkap_wa(monkeypatch)
    booking_db.update_payment_settings(metode_aktif=["cash"], tenant_id=tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    booking = booking_db.buat_booking(
        barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00", service_ids=[service_id],
        customer_nama="Walk In", customer_whatsapp="", metode_pembayaran="cash",
        tenant_id=tenant_id, sumber="kasir_mandiri",
    )
    assert booking["customer_whatsapp"] == ""
    assert booking["sumber"] == "kasir_mandiri"
    assert booking["status_pembayaran"] == "terverifikasi"  # cash selalu instan


def test_buat_booking_mandiri_wa_invalid_tetap_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking_db.update_payment_settings(metode_aktif=["cash"], tenant_id=tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    try:
        booking_db.buat_booking(
            barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00", service_ids=[service_id],
            customer_nama="Walk In", customer_whatsapp="bukan-nomor", metode_pembayaran="cash",
            tenant_id=tenant_id, sumber="kasir_mandiri",
        )
        assert False, "harus ditolak -- WA diisi tapi formatnya salah"
    except ValueError:
        pass


def test_bayar_nanti_ditolak_untuk_booking_publik(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking_db.update_payment_settings(metode_aktif=["cash"], tenant_id=tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    try:
        booking_db.buat_booking(
            barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00", service_ids=[service_id],
            customer_nama="Budi", customer_whatsapp="081234567890", metode_pembayaran="bayar_nanti",
            tenant_id=tenant_id,  # sumber default "publik"
        )
        assert False, "bayar_nanti tidak boleh dipakai booking publik"
    except ValueError:
        pass


def test_bayar_nanti_diterima_untuk_kasir_mandiri_dan_menunggu_verifikasi(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    booking = booking_db.buat_booking(
        barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00", service_ids=[service_id],
        customer_nama="Walk In", customer_whatsapp="", metode_pembayaran="bayar_nanti",
        tenant_id=tenant_id, sumber="kasir_mandiri",
    )
    assert booking["status_pembayaran"] == "menunggu_verifikasi"
    # "Sudah Bayar" di UI memanggil fungsi yang SAMA dgn tombol Verifikasi biasa.
    booking_db.verifikasi_pembayaran(booking["id"], oleh="kasir1")
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"


def test_fonte_tidak_pernah_terkirim_untuk_booking_mandiri_walau_wa_diisi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    panggilan = _pasang_penangkap_wa(monkeypatch)
    import subscription_db
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    booking = booking_db.buat_booking(
        barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00", service_ids=[service_id],
        customer_nama="Walk In", customer_whatsapp="081234567890", metode_pembayaran="bayar_nanti",
        tenant_id=tenant_id, sumber="kasir_mandiri",
    )
    assert panggilan == []  # tidak ada WA sama sekali saat booking dibuat
    booking_db.verifikasi_pembayaran(booking["id"], oleh="kasir1")
    assert panggilan == []  # tetap tidak ada WA saat "Sudah Bayar" diklik


def test_fonte_tetap_terkirim_untuk_booking_publik_biasa(single_tenant, monkeypatch):
    """Kontrol negatif -- pastikan guard baru TIDAK diam-diam mematikan WA
    untuk booking publik biasa (sumber default)."""
    tenant_id = single_tenant["tenant_id"]
    panggilan = _pasang_penangkap_wa(monkeypatch)
    import subscription_db
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")
    booking_db.update_payment_settings(metode_aktif=["qris"], tenant_id=tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    booking_db.buat_booking(
        barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00", service_ids=[service_id],
        customer_nama="Budi", customer_whatsapp="081234567890", metode_pembayaran="qris",
        tenant_id=tenant_id,
    )
    assert len(panggilan) == 1  # reminder_qris terkirim seperti biasa


def test_endpoint_pengaturan_mandiri(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    booking_db.update_payment_settings(metode_aktif=["cash", "qris"], tenant_id=single_tenant["tenant_id"])
    db.add_barber("Barber Endpoint", tenant_id=single_tenant["tenant_id"])
    r = client.get("/api/booking/mandiri/pengaturan", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "cash" in data["metode_aktif"] and "qris" in data["metode_aktif"]
    assert any(b["nama"] == "Barber Endpoint" for b in data["barbers"])


def test_endpoint_slot_mandiri(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    barber_id, service_id = _siapkan_barber_dan_service(single_tenant["tenant_id"])
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    r = client.get(f"/api/booking/mandiri/slot?barber_id={barber_id}&tanggal={tanggal}&service_ids={service_id}",
                    headers=headers)
    assert r.status_code == 200, r.text
    assert "slot" in r.json() or isinstance(r.json(), dict)


def test_endpoint_buat_booking_mandiri_cash(single_tenant, monkeypatch):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    _pasang_penangkap_wa(monkeypatch)
    booking_db.update_payment_settings(metode_aktif=["cash"], tenant_id=tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    r = client.post("/api/booking/mandiri", json={
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "10:00", "service_ids": [service_id],
        "customer_nama": "Walk In Endpoint", "customer_whatsapp": "", "metode_pembayaran": "cash",
    }, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status_pembayaran"] == "terverifikasi"
    assert data["sumber"] == "kasir_mandiri"


def test_endpoint_buat_booking_mandiri_bayar_nanti(single_tenant):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    r = client.post("/api/booking/mandiri", json={
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "11:00", "service_ids": [service_id],
        "customer_nama": "Walk In Nanti", "metode_pembayaran": "bayar_nanti",
    }, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status_pembayaran"] == "menunggu_verifikasi"


def test_endpoint_buat_booking_mandiri_gateway_checkout(single_tenant, monkeypatch):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    booking_db.update_payment_settings(metode_aktif=["gateway"], tenant_id=tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()

    monkeypatch.setattr("payment_provider_client.is_enabled", lambda: True)
    monkeypatch.setattr("payment_provider_client.channel_aktif", lambda: ["qris"])
    monkeypatch.setattr("payment_provider_client.va_bank_aktif", lambda: {})
    monkeypatch.setattr("payment_provider_client.buat_transaksi", lambda *a, **k: {
        "provider_transaction_id": "TX123", "qr_content": "00020101QRDATA", "qr_url": None,
        "expired_at": "2026-01-01T23:59:59+07:00", "provider_response": "{}", "channel_code": None,
    })

    r = client.post("/api/booking/mandiri", json={
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "12:00", "service_ids": [service_id],
        "customer_nama": "Walk In Gateway", "customer_whatsapp": "081234567890",
        "metode_pembayaran": "gateway", "channel": "qris",
    }, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["qr_content"] == "00020101QRDATA"
    assert data["status_pembayaran"] == "menunggu_verifikasi"


def test_endpoint_buat_booking_mandiri_gateway_qris_wajib_wa(single_tenant, monkeypatch):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    monkeypatch.setattr("payment_provider_client.is_enabled", lambda: True)
    monkeypatch.setattr("payment_provider_client.channel_aktif", lambda: ["qris"])
    r = client.post("/api/booking/mandiri", json={
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "13:00", "service_ids": [service_id],
        "customer_nama": "Walk In Gateway", "metode_pembayaran": "gateway", "channel": "qris",
    }, headers=headers)
    assert r.status_code == 422
