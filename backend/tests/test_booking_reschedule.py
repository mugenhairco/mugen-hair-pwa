"""test_booking_reschedule.py — AUDIT menu Booking (permintaan Owner):
Reschedule (item #3 spek) + highlight booking "advance" (item #4 spek)
=============================================================================
Cakupan: booking_db.reschedule_booking() -- admin bisa ubah tanggal/jam/
barber/service booking yang sudah terverifikasi, status_pembayaran TIDAK
PERNAH ikut berubah (tetap 'terverifikasi' walau harga berubah -- selisih
diselesaikan offline, SESUAI SPEK), pengecekan ketersediaan slot tetap
wajib (termasuk exclude booking itu sendiri dari pengecekan tumpang tindih
supaya reschedule ke jam yang SAMA tidak dianggap bentrok dengan dirinya
sendiri), booking metode "gateway" ditolak (payment gateway tidak boleh
disentuh). Juga cakupan _is_advance_booking() (booking_db.py) yang dipakai
frontend untuk highlight kuning No. Transaksi."""

import itertools
from datetime import timedelta

import booking_db
import database as db
from booking_db import _hari_ini_wib

_urutan_unik = itertools.count(1)


def _siapkan_barber_dan_service(tenant_id, nominal=100000, nama_prefix="Reschedule"):
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber {nama_prefix} T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Service {nama_prefix} T{tenant_id}-{n}", nominal, tenant_id=tenant_id)
    return barber_id, service_id


def _buat_booking(tenant_id, metode_pembayaran="transfer", nominal=100000, hari_offset=1, barber_id=None, service_id=None):
    booking_db.update_payment_settings(metode_aktif=["transfer", "qris", "gateway"], tenant_id=tenant_id)
    if barber_id is None or service_id is None:
        barber_id, service_id = _siapkan_barber_dan_service(tenant_id, nominal)
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    booking = booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                       service_ids=[service_id], customer_nama="Rina",
                                       customer_whatsapp="081234567891", metode_pembayaran=metode_pembayaran,
                                       tenant_id=tenant_id)
    return booking, barber_id, service_id


# ---------------------------------------------------------------------------
# reschedule_booking()
# ---------------------------------------------------------------------------

def test_reschedule_ubah_tanggal_jam_tetap_terverifikasi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    booking, barber_id, service_id = _buat_booking(tenant_id)
    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin1")

    tanggal_baru = (_hari_ini_wib() + timedelta(days=3)).isoformat()
    hasil = booking_db.reschedule_booking(booking["id"], tenant_id=tenant_id, tanggal=tanggal_baru, jam_mulai="14:00")

    assert hasil["tanggal"] == tanggal_baru
    assert hasil["jam_mulai"] == "14:00"
    assert hasil["barber_id"] == barber_id  # tidak diisi -- dipertahankan apa adanya
    assert hasil["status_pembayaran"] == "terverifikasi"  # SESUAI SPEK: tidak pernah ikut berubah


def test_reschedule_ganti_service_harga_berubah_status_tetap_terverifikasi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    booking, barber_id, _ = _buat_booking(tenant_id, nominal=100000)
    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin1")
    service_mahal_id = db.add_service(f"Service Mahal T{tenant_id}", 250000, tenant_id=tenant_id)

    hasil = booking_db.reschedule_booking(booking["id"], tenant_id=tenant_id, service_ids=[service_mahal_id])

    assert hasil["total_harga"] == 250000  # harga BERUBAH (selisih diselesaikan offline)
    assert hasil["status_pembayaran"] == "terverifikasi"  # tapi status TIDAK ikut berubah
    assert [it["service_id"] for it in hasil["items"]] == [service_mahal_id]


def test_reschedule_ganti_barber(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    booking, barber_lama_id, service_id = _buat_booking(tenant_id)
    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin1")
    barber_baru_id = db.add_barber(f"Barber Baru T{tenant_id}", tenant_id=tenant_id)

    hasil = booking_db.reschedule_booking(booking["id"], tenant_id=tenant_id, barber_id=barber_baru_id)

    assert hasil["barber_id"] == barber_baru_id
    assert hasil["barber_id"] != barber_lama_id


def test_reschedule_slot_bentrok_dengan_booking_lain_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    booking_a, _, _ = _buat_booking(tenant_id, barber_id=barber_id, service_id=service_id, hari_offset=5)
    booking_db.verifikasi_pembayaran(booking_a["id"], oleh="admin1")
    # booking_b: barber+tanggal SAMA, jam beda -- akan di-reschedule supaya BENTROK dengan booking_a.
    tanggal = booking_a["tanggal"]
    booking_b = booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="16:00",
                                         service_ids=[service_id], customer_nama="Andi",
                                         customer_whatsapp="081234567892", metode_pembayaran="transfer",
                                         tenant_id=tenant_id)
    booking_db.verifikasi_pembayaran(booking_b["id"], oleh="admin1")

    import pytest
    with pytest.raises(ValueError, match="sudah dibooking"):
        booking_db.reschedule_booking(booking_b["id"], tenant_id=tenant_id, tanggal=tanggal, jam_mulai="10:00")


def test_reschedule_ke_slot_sendiri_tidak_dianggap_bentrok(single_tenant, monkeypatch):
    """BUGFIX yang diperbaiki: exclude_booking_id pada _get_booking_aktif_tanggal()
    -- reschedule booking ke jam yang PERSIS SAMA (mis. cuma ganti service,
    tanggal/jam/barber tidak berubah) TIDAK BOLEH ditolak gara-gara booking
    itu "bentrok" dengan dirinya sendiri."""
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    booking, barber_id, service_id = _buat_booking(tenant_id)
    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin1")

    # Reschedule TANPA mengubah tanggal/jam/barber sama sekali -- harus tetap sukses.
    hasil = booking_db.reschedule_booking(booking["id"], tenant_id=tenant_id, tanggal=booking["tanggal"],
                                           jam_mulai=booking["jam_mulai"], barber_id=barber_id)
    assert hasil["tanggal"] == booking["tanggal"]
    assert hasil["jam_mulai"] == booking["jam_mulai"]


def test_reschedule_metode_gateway_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    import payment_gateway_db
    payment_gateway_db.update_config(merchant_id="37070", server_key="bot-test3", secret_key="pass-test3")
    booking, _, _ = _buat_booking(tenant_id, metode_pembayaran="gateway")

    import pytest
    with pytest.raises(ValueError, match="[Pp]ayment [Gg]ateway"):
        booking_db.reschedule_booking(booking["id"], tenant_id=tenant_id, jam_mulai="15:00")


def test_reschedule_booking_dibatalkan_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking, _, _ = _buat_booking(tenant_id)
    booking_db.batalkan_booking(booking["id"])

    import pytest
    with pytest.raises(ValueError):
        booking_db.reschedule_booking(booking["id"], tenant_id=tenant_id, jam_mulai="15:00")


def test_reschedule_service_kosong_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    booking, _, _ = _buat_booking(tenant_id)
    booking_db.verifikasi_pembayaran(booking["id"], oleh="admin1")

    import pytest
    with pytest.raises(ValueError, match="[Ss]ervice"):
        booking_db.reschedule_booking(booking["id"], tenant_id=tenant_id, service_ids=[])


# ---------------------------------------------------------------------------
# Endpoint HTTP -- routers/booking.py::reschedule_booking()
# ---------------------------------------------------------------------------

def test_endpoint_reschedule_sukses(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    booking, barber_id, service_id = _buat_booking(tenant_id)
    client.post(f"/api/booking/{booking['id']}/verifikasi", headers=headers)

    r = client.post(f"/api/booking/{booking['id']}/reschedule", json={"jam_mulai": "17:00"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["jam_mulai"] == "17:00"
    assert r.json()["status_pembayaran"] == "terverifikasi"


def test_endpoint_reschedule_metode_gateway_ditolak_422(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import payment_gateway_db
    payment_gateway_db.update_config(merchant_id="37070", server_key="bot-test4", secret_key="pass-test4")
    booking, _, _ = _buat_booking(tenant_id, metode_pembayaran="gateway")

    r = client.post(f"/api/booking/{booking['id']}/reschedule", json={"jam_mulai": "17:00"}, headers=headers)
    assert r.status_code == 422


def test_endpoint_reschedule_slot_bentrok_422(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    booking_a, _, _ = _buat_booking(tenant_id, barber_id=barber_id, service_id=service_id, hari_offset=6)
    client.post(f"/api/booking/{booking_a['id']}/verifikasi", headers=headers)
    tanggal = booking_a["tanggal"]
    booking_b = booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="18:00",
                                         service_ids=[service_id], customer_nama="Sari",
                                         customer_whatsapp="081234567893", metode_pembayaran="transfer",
                                         tenant_id=tenant_id)
    client.post(f"/api/booking/{booking_b['id']}/verifikasi", headers=headers)

    r = client.post(f"/api/booking/{booking_b['id']}/reschedule",
                     json={"tanggal": tanggal, "jam_mulai": "10:00"}, headers=headers)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# _is_advance_booking() -- highlight kuning No. Transaksi (item #4 spek)
# ---------------------------------------------------------------------------
# Unit test LANGSUNG ke _is_advance_booking() (bukan lewat buat_booking()
# sungguhan) supaya TIDAK bergantung jam berapa suite ini kebetulan
# dijalankan -- buat_booking() menolak jam yang "sudah lewat"/di luar jam
# operasional untuk booking di HARI INI, yang membuat skenario "dibuat &
# appointment di hari yang sama" gampang flaky kalau dites lewat jalur itu.
# created_at disimpan naive UTC (lihat docstring _is_advance_booking()).

def test_is_advance_booking_dibuat_lebih_awal_dari_appointment():
    assert booking_db._is_advance_booking("2026-08-23T09:00:00", "2026-08-27") is True


def test_is_advance_booking_dibuat_dan_appointment_hari_sama_tidak_advance():
    assert booking_db._is_advance_booking("2026-08-23T09:00:00", "2026-08-23") is False


def test_is_advance_booking_konversi_wib_dini_hari_utc_masih_hari_sebelumnya_wib():
    """created_at UTC 23:30 (17-08) == WIB 06:30 (18-08) -- kalau tanggal
    appointment-nya 18-08 (WIB), ini TIDAK advance (dibuat & appointment
    hari yang sama di WIB), meski tanggal UTC mentahnya beda hari."""
    assert booking_db._is_advance_booking("2026-08-17T23:30:00", "2026-08-18") is False


def test_is_advance_booking_created_at_kosong_tidak_meledak():
    assert booking_db._is_advance_booking("", "2026-08-27") is False
    assert booking_db._is_advance_booking(None, "2026-08-27") is False


def test_booking_advance_dibuat_lebih_awal_dari_appointment_lewat_get_booking(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking, _, _ = _buat_booking(tenant_id, hari_offset=4)  # dibuat "sekarang", appointment 4 hari lagi
    hasil = booking_db.get_booking(booking["id"])
    assert hasil["is_advance_booking"] is True


def test_booking_list_ikut_membawa_flag_advance(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking, _, _ = _buat_booking(tenant_id, hari_offset=2)
    daftar = booking_db.get_booking_list(tenant_id=tenant_id)
    baris = next(b for b in daftar if b["id"] == booking["id"])
    assert baris["is_advance_booking"] is True
