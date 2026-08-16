"""test_booking_hapus_riwayat.py — FITUR Reset Riwayat Booking (mengantisipasi
data menumpuk, pola SAMA PERSIS seperti attendance_db.py::
hapus_riwayat_absensi()): DELETE /api/booking/riwayat -- Owner ATAU Admin
(staff) SAMA-SAMA boleh (require_owner_or_staff), `sebelum_tanggal`
opsional (kosong = hapus SEMUA booking tenant ini).

Cakupan: cascade hapus booking_items + booking_payment_transactions +
booking_payment_status_log (tidak ada baris yatim tersisa), filter
sebelum_tanggal (booking di tanggal itu sendiri TIDAK ikut terhapus --
exclusive), isolasi tenant (booking tenant lain TIDAK PERNAH ikut
terhapus), akses ditolak untuk role barber."""

from datetime import timedelta

import auth_db
import booking_db
import booking_gateway_db
import database as db
import payment_gateway_db
from booking_db import _hari_ini_wib


def _siapkan_barber(tenant_id, username="reset1"):
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


def _jumlah_baris(conn, tabel, tenant_id=None, booking_ids=None):
    if tenant_id is not None:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {tabel} WHERE tenant_id = ?", (tenant_id,)).fetchone()["n"]
    placeholder = ", ".join("?" for _ in booking_ids)
    return conn.execute(f"SELECT COUNT(*) AS n FROM {tabel} WHERE booking_id IN ({placeholder})", booking_ids).fetchone()["n"]


def test_hapus_semua_riwayat_booking_kosongkan_sebelum_tanggal(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber(tenant_id)
    _booking(tenant_id, barber_id, service_id, hari_offset=1)
    _booking(tenant_id, barber_id, service_id, hari_offset=2)

    jumlah = booking_db.hapus_riwayat_booking(tenant_id)
    assert jumlah == 2
    with booking_db.get_conn() as conn:
        assert _jumlah_baris(conn, "bookings", tenant_id=tenant_id) == 0
        # single_tenant = satu-satunya tenant di database test terisolasi ini
        # (fresh per test function, lihat conftest.py) -- hitung global aman.
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_items").fetchone()["n"] == 0


def test_hapus_riwayat_dengan_sebelum_tanggal_exclusive(single_tenant):
    """Booking TEPAT di tanggal `sebelum_tanggal` TIDAK ikut terhapus --
    filter SQL "tanggal < sebelum_tanggal" (exclusive), bukan "<="."""
    tenant_id = single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber(tenant_id)
    _booking(tenant_id, barber_id, service_id, hari_offset=1)  # akan terhapus
    b2 = _booking(tenant_id, barber_id, service_id, hari_offset=2, jam_mulai="11:00")  # batas -- TIDAK terhapus
    b3 = _booking(tenant_id, barber_id, service_id, hari_offset=3, jam_mulai="12:00")  # setelah batas -- TIDAK terhapus
    batas = b2["tanggal"]

    jumlah = booking_db.hapus_riwayat_booking(tenant_id, sebelum_tanggal=batas)
    assert jumlah == 1
    sisa = booking_db.get_booking_list(tenant_id=tenant_id)
    sisa_ids = {r["id"] for r in sisa}
    assert sisa_ids == {b2["id"], b3["id"]}


def test_hapus_riwayat_cascade_hapus_transaksi_gateway_dan_log_status(single_tenant):
    """Booking metode "gateway" punya baris booking_payment_transactions +
    booking_payment_status_log -- keduanya WAJIB ikut terhapus (tidak ada
    baris yatim), sesuai urutan anak->induk di hapus_riwayat_booking()."""
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

    with booking_db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_payment_transactions WHERE booking_id = ?",
                             (booking["id"],)).fetchone()["n"] == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_payment_status_log WHERE transaction_id = ?",
                             (transaksi["id"],)).fetchone()["n"] == 1

    jumlah = booking_db.hapus_riwayat_booking(tenant_id)
    assert jumlah == 1
    with booking_db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_payment_transactions WHERE booking_id = ?",
                             (booking["id"],)).fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM booking_payment_status_log WHERE transaction_id = ?",
                             (transaksi["id"],)).fetchone()["n"] == 0


def test_hapus_riwayat_tidak_menyentuh_tenant_lain(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a, service_a = _siapkan_barber(tenant_a, "resetA")
    barber_b, service_b = _siapkan_barber(tenant_b, "resetB")
    _booking(tenant_a, barber_a, service_a, hari_offset=1)
    booking_b = _booking(tenant_b, barber_b, service_b, hari_offset=1)

    jumlah = booking_db.hapus_riwayat_booking(tenant_a)
    assert jumlah == 1
    sisa_b = booking_db.get_booking_list(tenant_id=tenant_b)
    assert len(sisa_b) == 1
    assert sisa_b[0]["id"] == booking_b["id"]


def test_router_hapus_riwayat_ditolak_untuk_barber(single_tenant):
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber(tenant_id)
    auth_db.tambah_user("barberreset", "password123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "barberreset", "password": "password123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.request("DELETE", "/api/booking/riwayat", headers=headers)
    assert r2.status_code == 403, r2.text


def test_router_hapus_riwayat_boleh_untuk_staff(single_tenant):
    """require_owner_or_staff -- staff (role "Admin" di UI) SAMA seperti
    Owner, TANPA delegasi permission terpisah."""
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    barber_id, service_id = _siapkan_barber(tenant_id)
    _booking(tenant_id, barber_id, service_id, hari_offset=1)
    auth_db.tambah_user("staffreset", "password123", role="staff", tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "staffreset", "password": "password123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.request("DELETE", "/api/booking/riwayat", headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["jumlah_dihapus"] == 1
