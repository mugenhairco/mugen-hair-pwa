"""test_booking_hari_ini.py — FITUR Tampilan Operasional Harian Booking
(tab "Hari Ini"/"Akan Datang", pages/booking.js): GET /api/booking/mine
sekarang menerima dua parameter opsional baru:
- `tanggal`  : persis SATU tanggal (dipakai tab "Hari Ini").
- `dari_tanggal` : seluruh booking dengan tanggal >= nilai ini, TANPA
  batas atas (dipakai tab "Akan Datang").

Keduanya default None -- kalau tidak dikirim (tab "Semua Booking" lama),
perilaku endpoint TIDAK berubah sama sekali dari sebelumnya (tahun/bulan
saja). Barber_id TETAP hanya diambil dari akun login (bukan parameter
apa pun) -- Barber lain TIDAK BISA terlihat lewat kombinasi parameter
baru ini.

Bookings dibuat di tanggal MASA DEPAN (offset >= 1 hari) supaya tidak
menyentuh sama sekali validasi "jam sudah lewat hari ini" di
booking_db.py::_validasi_booking() -- test ini murni soal filter
tanggal/dari_tanggal, bukan soal validasi jam operasional."""

from datetime import timedelta

import auth_db
import database as db

import booking_db
from booking_db import _hari_ini_wib


def _siapkan_barber(client, tenant_id, username):
    booking_db.update_payment_settings(metode_aktif=["transfer"], tenant_id=tenant_id)
    barber_id = db.add_barber(f"Barber {username}", tenant_id=tenant_id)
    service_id = db.add_service(f"Service {username}", 50000, tenant_id=tenant_id)
    auth_db.tambah_user(username, "password123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return barber_id, service_id, {"Authorization": f"Bearer {token}"}


def _booking(tenant_id, barber_id, service_id, hari_offset, jam_mulai="10:00", nama="Budi"):
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    return booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai=jam_mulai,
                                    service_ids=[service_id], customer_nama=nama,
                                    customer_whatsapp="081234567890", metode_pembayaran="transfer",
                                    tenant_id=tenant_id)


def test_mine_tanggal_hanya_mengembalikan_satu_tanggal_persis(single_tenant):
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    barber_id, service_id, headers = _siapkan_barber(client, tenant_id, "barberhi1")
    _booking(tenant_id, barber_id, service_id, hari_offset=1)
    _booking(tenant_id, barber_id, service_id, hari_offset=2)
    besok = (_hari_ini_wib() + timedelta(days=1)).isoformat()

    r = client.get(f"/api/booking/mine?tanggal={besok}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    assert data[0]["tanggal"] == besok


def test_mine_dari_tanggal_mengembalikan_seluruh_masa_depan_tanpa_batas_atas(single_tenant):
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    barber_id, service_id, headers = _siapkan_barber(client, tenant_id, "barberhi2")
    _booking(tenant_id, barber_id, service_id, hari_offset=1)
    _booking(tenant_id, barber_id, service_id, hari_offset=2)
    _booking(tenant_id, barber_id, service_id, hari_offset=6)
    lusa = (_hari_ini_wib() + timedelta(days=2)).isoformat()

    r = client.get(f"/api/booking/mine?dari_tanggal={lusa}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    # offset=1 (besok) TIDAK ikut -- di bawah dari_tanggal.
    assert len(data) == 2
    assert all(row["tanggal"] >= lusa for row in data)


def test_mine_tanpa_parameter_baru_perilaku_lama_tidak_berubah(single_tenant):
    """Tab "Semua Booking" (bulan/tahun, TIDAK diubah) -- kalau `tanggal`/
    `dari_tanggal` tidak dikirim sama sekali, seluruh booking tetap
    dikembalikan seperti sebelum fitur ini ada."""
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    barber_id, service_id, headers = _siapkan_barber(client, tenant_id, "barberhi3")
    _booking(tenant_id, barber_id, service_id, hari_offset=1)
    _booking(tenant_id, barber_id, service_id, hari_offset=2)

    r = client.get("/api/booking/mine", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2


def test_mine_tanggal_tetap_terisolasi_per_barber(single_tenant):
    """Barber A TIDAK BISA melihat booking Barber B lewat parameter
    tanggal/dari_tanggal apa pun -- barber_id SELALU dari akun login,
    BUKAN dari parameter request manapun."""
    client, tenant_id = single_tenant["client"], single_tenant["tenant_id"]
    barber_a, service_a, headers_a = _siapkan_barber(client, tenant_id, "barberhi4a")
    barber_b, service_b, headers_b = _siapkan_barber(client, tenant_id, "barberhi4b")
    besok = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    _booking(tenant_id, barber_a, service_a, hari_offset=1, jam_mulai="10:00")
    _booking(tenant_id, barber_b, service_b, hari_offset=1, jam_mulai="11:00")

    r = client.get(f"/api/booking/mine?tanggal={besok}", headers=headers_a)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    assert data[0]["barber_id"] == barber_a
