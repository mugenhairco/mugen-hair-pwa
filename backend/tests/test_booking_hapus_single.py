"""test_booking_hapus_single.py — Requirement Owner: Hapus PERMANEN satu
booking (BEDA dari batalkan_booking() yang soft-cancel, dan BEDA dari
hapus_riwayat_booking() yang hapus banyak sekaligus). Cakupan: cascade
hapus (booking_items/booking_payment_transactions/booking_payment_status_log),
tetap bisa dihapus walau status_pembayaran='terverifikasi', slot langsung
terbuka lagi, izin_booking_hapus TERPISAH dari izin_booking_batalkan,
isolasi tenant."""

from datetime import timedelta

import auth_db
import booking_db
import booking_gateway_db
import database as db
import payment_gateway_db
import permissions
from booking_db import _hari_ini_wib


def _siapkan_barber(tenant_id, username="hapus1"):
    booking_db.update_payment_settings(metode_aktif=["transfer", "gateway"], tenant_id=tenant_id)
    barber_id = db.add_barber(f"Barber {username}", tenant_id=tenant_id)
    service_id = db.add_service(f"Service {username}", 50000, tenant_id=tenant_id)
    return barber_id, service_id


def _booking(tenant_id, barber_id, service_id, hari_offset, jam_mulai="10:00",
             nama="Budi", metode="transfer"):
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    return booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai=jam_mulai,
                                    service_ids=[service_id], customer_nama=nama,
                                    customer_whatsapp="081234567890", metode_pembayaran=metode,
                                    tenant_id=tenant_id)


def test_hapus_booking_membebaskan_slot(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber(tenant_id)
    booking = _booking(tenant_id, barber_id, service_id, hari_offset=1)
    tanggal = booking["tanggal"]

    slot_sebelum = booking_db.hitung_slot(barber_id, tanggal, [service_id], tenant_id=tenant_id)
    status_sebelum = next(s["status"] for s in slot_sebelum["slots"] if s["jam"] == "10:00")
    assert status_sebelum == "booked"

    booking_db.hapus_booking(booking["id"])

    slot_sesudah = booking_db.hitung_slot(barber_id, tanggal, [service_id], tenant_id=tenant_id)
    status_sesudah = next(s["status"] for s in slot_sesudah["slots"] if s["jam"] == "10:00")
    assert status_sesudah == "available"
    assert booking_db.get_booking(booking["id"]) is None


def test_hapus_booking_terverifikasi_tetap_bisa_dihapus(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber(tenant_id)
    booking = _booking(tenant_id, barber_id, service_id, hari_offset=1)
    booking_db.verifikasi_pembayaran(booking["id"])
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"

    hasil = booking_db.hapus_booking(booking["id"])
    assert hasil["id"] == booking["id"]
    assert booking_db.get_booking(booking["id"]) is None


def test_hapus_booking_cascade_hapus_items_dan_transaksi_gateway(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    payment_gateway_db.update_config(merchant_id="1", server_key="u", secret_key="p")
    barber_id, service_id = _siapkan_barber(tenant_id)
    booking = _booking(tenant_id, barber_id, service_id, hari_offset=1, metode="gateway")

    order_id = booking_gateway_db.buat_order_id(tenant_id, booking["id"])
    transaksi = booking_gateway_db.buat_transaksi(
        order_id=order_id, tenant_id=tenant_id, tenant_nama="Test Toko", booking_id=booking["id"],
        customer_nama="Budi", barber_nama="Barber Test", layanan="Haircut", nominal=50000,
    )
    booking_gateway_db.update_status(transaksi["id"], "diproses", sumber="webhook")

    # Booking lain (tidak dihapus) HARUS tetap utuh -- buktikan cascade
    # discope ke SATU booking_id, bukan ikut menghapus booking lain.
    booking_lain = _booking(tenant_id, barber_id, service_id, hari_offset=2, jam_mulai="14:00")

    booking_db.hapus_booking(booking["id"])

    with booking_db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_items WHERE booking_id = ?",
                             (booking["id"],)).fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_payment_transactions WHERE booking_id = ?",
                             (booking["id"],)).fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_payment_status_log WHERE transaction_id = ?",
                             (transaksi["id"],)).fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_items WHERE booking_id = ?",
                             (booking_lain["id"],)).fetchone()["n"] == 1
    assert booking_db.get_booking(booking_lain["id"]) is not None


def test_hapus_booking_tidak_ditemukan_raise_valueerror(single_tenant):
    import pytest
    with pytest.raises(ValueError):
        booking_db.hapus_booking(999999)


def test_router_hapus_booking_ditolak_tanpa_izin_booking_hapus(single_tenant):
    """izin_booking_hapus TERPISAH dari izin_booking_batalkan (permintaan
    eksplisit Owner) -- staff yang cuma punya izin Batalkan TIDAK otomatis
    boleh Hapus permanen."""
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber(tenant_id)
    booking = _booking(tenant_id, barber_id, service_id, hari_offset=1)

    auth_db.tambah_user("staffhapus1", "password123", role="staff", tenant_id=tenant_id)
    permissions.set_bulk({
        "izin_booking_lihat": True, "izin_booking_kelola": True, "izin_booking_batalkan": True,
        "izin_booking_hapus": False,
    }, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "staffhapus1", "password": "password123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.request("DELETE", f"/api/booking/{booking['id']}", headers=headers)
    assert r2.status_code == 403, r2.text
    assert booking_db.get_booking(booking["id"]) is not None


def test_router_hapus_booking_boleh_dengan_izin_booking_hapus(single_tenant):
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber(tenant_id)
    booking = _booking(tenant_id, barber_id, service_id, hari_offset=1)

    auth_db.tambah_user("staffhapus2", "password123", role="staff", tenant_id=tenant_id)
    permissions.set_bulk({
        "izin_booking_lihat": True, "izin_booking_hapus": True,
    }, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "staffhapus2", "password": "password123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.request("DELETE", f"/api/booking/{booking['id']}", headers=headers)
    assert r2.status_code == 200, r2.text
    assert booking_db.get_booking(booking["id"]) is None


def test_router_hapus_booking_ditolak_tenant_lain(two_tenants):
    tenant_b = two_tenants["tenant_b"]
    client = two_tenants["client"]
    barber_b, service_b = _siapkan_barber(tenant_b, "hapusB")
    booking_b = _booking(tenant_b, barber_b, service_b, hari_offset=1)

    r = client.request("DELETE", f"/api/booking/{booking_b['id']}", headers=two_tenants["headers_a"])
    assert r.status_code == 404, r.text
    assert booking_db.get_booking(booking_b["id"]) is not None
