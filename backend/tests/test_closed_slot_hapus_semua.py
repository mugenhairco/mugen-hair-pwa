"""test_closed_slot_hapus_semua.py — FITUR Owner: tombol "Hapus Semua" di
tab Closed Slot (pages/booking.js::renderClosedSlot()). Cakupan:
booking_db.py::hapus_semua_closed_slot() (lingkup tenant_id + filter
tahun/bulan opsional) dan endpoint DELETE /api/booking/closed-slot
(HTTP, lingkup SAMA PERSIS dengan GET yang sedang ditampilkan)."""

from datetime import timedelta

import booking_db
import database as db
from booking_db import _hari_ini_wib


def _barber(tenant_id, nama="Barber Closed Slot"):
    return db.add_barber(nama, tenant_id=tenant_id)


def test_hapus_semua_closed_slot_hanya_tenant_sendiri(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = _barber(tenant_a, "Barber Closed Slot A")
    barber_b = _barber(tenant_b, "Barber Closed Slot B")
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()

    booking_db.tambah_closed_slot(barber_a, tanggal, "09:00", "10:00", tenant_id=tenant_a)
    booking_db.tambah_closed_slot(barber_b, tanggal, "09:00", "10:00", tenant_id=tenant_b)

    jumlah = booking_db.hapus_semua_closed_slot(tenant_a)

    assert jumlah == 1
    assert booking_db.get_closed_slot_list(tenant_id=tenant_a) == []
    assert len(booking_db.get_closed_slot_list(tenant_id=tenant_b)) == 1


def test_hapus_semua_closed_slot_filter_bulan_tidak_menyentuh_bulan_lain(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    hari_ini = _hari_ini_wib()
    bulan_ini = hari_ini.isoformat()
    booking_db.tambah_closed_slot(barber_id, bulan_ini, "09:00", "10:00", tenant_id=tenant_id)
    # Baris dari tahun lalu, bulan yang sama -- SENGAJA dipakai sebagai
    # pengganti "bulan lain" supaya test tidak bergantung pada tanggal
    # hari ini jatuh di bulan apa (hindari flaky di sekitar pergantian
    # tahun/bulan).
    tahun_lalu = f"{hari_ini.year - 1}-{hari_ini.month:02d}-01"
    booking_db.tambah_closed_slot(barber_id, tahun_lalu, "09:00", "10:00", tenant_id=tenant_id)

    jumlah = booking_db.hapus_semua_closed_slot(tenant_id, tahun=hari_ini.year, bulan=hari_ini.month)

    assert jumlah == 1
    sisa = booking_db.get_closed_slot_list(tenant_id=tenant_id)
    assert len(sisa) == 1
    assert sisa[0]["tanggal"] == tahun_lalu


def test_delete_closed_slot_bulk_endpoint(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    hari_ini = _hari_ini_wib()
    booking_db.tambah_closed_slot(barber_id, hari_ini.isoformat(), "09:00", "10:00", tenant_id=tenant_id)
    booking_db.tambah_closed_slot(barber_id, hari_ini.isoformat(), "11:00", "12:00", tenant_id=tenant_id)

    r = client.delete(f"/api/booking/closed-slot?tahun={hari_ini.year}&bulan={hari_ini.month}", headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["jumlah_terhapus"] == 2
    assert client.get("/api/booking/closed-slot", headers=headers).json() == []


def test_delete_closed_slot_bulk_endpoint_ditolak_tanpa_izin_kelola(single_tenant):
    """Pola SAMA PERSIS test_perluasan_hak_akses_admin.py -- izin_booking_
    kelola default TRUE (grandfather), jadi harus dimatikan eksplisit dulu
    oleh Owner lewat PUT /hak-akses-admin sebelum staff kena 403."""
    import auth_db

    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    auth_db.tambah_user("staffcs", "password123", role="staff", tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "staffcs", "password": "password123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r = client.put("/api/pengaturan/hak-akses-admin", json={"izin": {"izin_booking_kelola": False}}, headers=headers)
    assert r.status_code == 200, r.text

    r = client.delete("/api/booking/closed-slot", headers=headers_staff)
    assert r.status_code == 403
