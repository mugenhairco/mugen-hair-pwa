"""test_booking_dilihat.py — FITUR Unread Row Highlight (List Booking
Owner/Admin)
=============================================================================
Cakupan: kolom bookings.dilihat (lihat booking_dilihat_migrasi.py) --
0 (belum dilihat) untuk booking sumber="publik" (TERMASUK metode gateway)
begitu dibuat, 1 (sudah dilihat) untuk sumber="kasir_mandiri" sejak dibuat
(staff sendiri yang menginputnya, PERMINTAAN Owner: tidak perlu di-highlight)
-- dan endpoint POST /api/booking/{id}/tandai-dilihat (booking_db.
tandai_booking_dilihat()) yang dipanggil frontend begitu staff klik tombol
aksi atau baris booking metode gateway."""

import itertools
from datetime import timedelta

import booking_db
import database as db
from booking_db import _hari_ini_wib

_urutan_unik = itertools.count(1)


def _siapkan_barber_dan_service(tenant_id, nominal=100000):
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber BD T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Potong Rambut BD T{tenant_id}-{n}", nominal, tenant_id=tenant_id)
    return barber_id, service_id


def _buat_booking(tenant_id, sumber="publik", metode_pembayaran="cash", nominal=100000, hari_offset=1):
    booking_db.update_payment_settings(metode_aktif=["cash", "qris", "gateway"], tenant_id=tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id, nominal)
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    return booking_db.buat_booking(
        barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00", service_ids=[service_id],
        customer_nama="Budi", customer_whatsapp="081234567890", metode_pembayaran=metode_pembayaran,
        tenant_id=tenant_id, sumber=sumber,
    )


def test_booking_publik_dilihat_0_saat_dibuat(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _buat_booking(tenant_id, sumber="publik", metode_pembayaran="qris")
    assert booking["dilihat"] == 0


def test_booking_publik_metode_gateway_juga_dilihat_0_saat_dibuat(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _buat_booking(tenant_id, sumber="publik", metode_pembayaran="gateway")
    assert booking["dilihat"] == 0


def test_booking_kasir_mandiri_dilihat_1_sejak_dibuat(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _buat_booking(tenant_id, sumber="kasir_mandiri", metode_pembayaran="cash")
    assert booking["dilihat"] == 1


def test_tandai_booking_dilihat_mengubah_0_jadi_1(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _buat_booking(tenant_id, sumber="publik", metode_pembayaran="qris")
    assert booking["dilihat"] == 0
    hasil = booking_db.tandai_booking_dilihat(booking["id"])
    assert hasil["dilihat"] == 1
    assert booking_db.get_booking(booking["id"])["dilihat"] == 1


def test_tandai_booking_dilihat_idempotent(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _buat_booking(tenant_id, sumber="publik", metode_pembayaran="qris")
    booking_db.tandai_booking_dilihat(booking["id"])
    hasil = booking_db.tandai_booking_dilihat(booking["id"])  # panggil kedua -- tidak boleh error
    assert hasil["dilihat"] == 1


def test_endpoint_tandai_dilihat(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    booking = _buat_booking(tenant_id, sumber="publik", metode_pembayaran="qris")
    assert booking["dilihat"] == 0

    r = client.post(f"/api/booking/{booking['id']}/tandai-dilihat", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["dilihat"] == 1


def test_endpoint_tandai_dilihat_booking_tenant_lain_404(two_tenants):
    client = two_tenants["client"]
    booking_lain = _buat_booking(two_tenants["tenant_b"], sumber="publik", metode_pembayaran="qris")

    r = client.post(f"/api/booking/{booking_lain['id']}/tandai-dilihat", headers=two_tenants["headers_a"])
    assert r.status_code == 404
