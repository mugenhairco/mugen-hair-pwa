"""test_nomor_transaksi_dan_jam_operasional.py — Format Baru Nomor Transaksi
Booking + Pesan Otomatis Berdasarkan Jam Operasional Tenant
=============================================================================
Cakupan 1 (nomor transaksi): format [JAM KONFIRMASI][MENIT KONFIRMASI]
[TANGGAL BOOKING][BULAN BOOKING][JAM BOOKING][INISIAL TENANT] dihitung dari
waktu AKTUAL booking dibuat (BUKAN jam appointment), menit booking dibuang,
TIDAK PERNAH memakai nama service, dipersist ke bookings.nomor_transaksi,
dan di-reuse APA ADANYA oleh booking_gateway_db (Riwayat Transaksi/Super
Admin/checkout menampilkan SATU nomor yang sama, bukan dua nomor berbeda).

Cakupan 2 (jam operasional): booking_db._di_luar_jam_operasional() dan
integrasinya di buat_booking() (field transien `dibuat_di_luar_jam_operasional`)
-- ditentukan dari waktu booking DIBUAT (WIB, _sekarang_wib() di-monkeypatch
untuk determinisme), BUKAN jam appointment yang dipilih, per-tenant, dengan
batas jam_buka INKLUSIF/jam_tutup EKSKLUSIF."""

import itertools
from datetime import datetime, timedelta

import booking_db
import booking_gateway_db
import database as db
import payment_gateway_client
import payment_gateway_db
import tenant_db
from booking_db import WIB, _hari_ini_wib

_urutan_unik = itertools.count(1)


def _siapkan_barber_dan_service(tenant_id, nominal=100000, nama_prefix="NoTrx"):
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber {nama_prefix} T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Service {nama_prefix} T{tenant_id}-{n} SUPERLENGKAP", nominal, tenant_id=tenant_id)
    return barber_id, service_id


def _buat_booking(tenant_id, metode_pembayaran="transfer", nominal=100000, hari_offset=1,
                   jam_mulai="13:00", barber_id=None, service_id=None):
    booking_db.update_payment_settings(metode_aktif=["transfer", "qris", "gateway"], tenant_id=tenant_id)
    if barber_id is None or service_id is None:
        barber_id, service_id = _siapkan_barber_dan_service(tenant_id, nominal)
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    return booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai=jam_mulai,
                                    service_ids=[service_id], customer_nama="Rina",
                                    customer_whatsapp="081234567891", metode_pembayaran=metode_pembayaran,
                                    tenant_id=tenant_id)


def _patch_sekarang(monkeypatch, jam, menit):
    monkeypatch.setattr(booking_db, "_sekarang_wib",
                         lambda: datetime.now(WIB).replace(hour=jam, minute=menit, second=0, microsecond=0))


# ============================= Format nomor transaksi =============================

def test_nomor_transaksi_sesuai_contoh_spek(single_tenant, monkeypatch):
    """Konfirmasi 17:05, booking tanggal +N hari jam 13:00, tenant "Test
    Toko" (fixture single_tenant, 2 kata) -> inisial "TT". Contoh resmi
    spek pakai tenant 2 kata lain ("Mugen Hair Co Barber Shop" -> "MH") --
    di sini yang diverifikasi adalah STRUKTURNYA, bukan inisial spesifik
    (dites terpisah di bawah)."""
    tenant_id = single_tenant["tenant_id"]
    _patch_sekarang(monkeypatch, 17, 5)
    booking = _buat_booking(tenant_id, jam_mulai="13:00", hari_offset=3)
    dd = booking["tanggal"][8:10]
    mm = booking["tanggal"][5:7]
    assert booking["nomor_transaksi"] == f"1705{dd}{mm}13TT"


def test_nomor_transaksi_inisial_dua_kata_pertama(app_client, monkeypatch):
    tenant_id = tenant_db.buat_tenant("mugen-hair-co-barber-shop-test", "Mugen Hair Co Barber Shop")
    _patch_sekarang(monkeypatch, 17, 5)
    booking = _buat_booking(tenant_id, jam_mulai="13:00")
    assert booking["nomor_transaksi"].endswith("MH")


def test_nomor_transaksi_inisial_king_barber_shop(app_client, monkeypatch):
    tenant_id = tenant_db.buat_tenant("king-barber-shop-test", "King Barber Shop")
    _patch_sekarang(monkeypatch, 9, 30)
    booking = _buat_booking(tenant_id, jam_mulai="11:00")  # default jam operasional tenant baru: 10:00-20:00
    assert booking["nomor_transaksi"].endswith("KB")


def test_nomor_transaksi_menit_booking_dibuang(single_tenant, monkeypatch):
    """13:45 -> hanya "13", BUKAN "1345" (beda dari rumus lama)."""
    _patch_sekarang(monkeypatch, 8, 0)
    booking = _buat_booking(single_tenant["tenant_id"], jam_mulai="13:45")
    # format: JJMM(konfirmasi 4) + DDMM(booking 4) + JJ(booking 2) + inisial(2) = 12 char
    assert len(booking["nomor_transaksi"]) == 12
    assert booking["nomor_transaksi"][8:10] == "13"


def test_nomor_transaksi_tidak_mengandung_nama_service(single_tenant, monkeypatch):
    """Service sengaja diberi nama "SUPERLENGKAP" (huruf mencolok) -- nomor
    transaksi TIDAK BOLEH memuatnya sama sekali (bug lama: rumus berbasis
    inisial service)."""
    _patch_sekarang(monkeypatch, 10, 10)
    booking = _buat_booking(single_tenant["tenant_id"], jam_mulai="10:00")
    assert "SUPERLENGKAP" not in booking["nomor_transaksi"]
    assert "S" not in booking["nomor_transaksi"][:8]  # bagian jam/tanggal murni digit


def test_nomor_transaksi_pakai_jam_konfirmasi_bukan_jam_booking(single_tenant, monkeypatch):
    """Booking dikonfirmasi jam 08:00 untuk appointment jam 17:00 -- 4
    digit PERTAMA harus "0800" (konfirmasi), BUKAN "1700"."""
    _patch_sekarang(monkeypatch, 8, 0)
    booking = _buat_booking(single_tenant["tenant_id"], jam_mulai="17:00")
    assert booking["nomor_transaksi"].startswith("0800")
    assert booking["nomor_transaksi"][8:10] == "17"


def test_nomor_transaksi_persisten_tidak_dihitung_ulang(single_tenant, monkeypatch):
    _patch_sekarang(monkeypatch, 11, 11)
    booking = _buat_booking(single_tenant["tenant_id"], jam_mulai="14:00")
    dibaca_ulang = booking_db.get_booking(booking["id"])
    assert dibaca_ulang["nomor_transaksi"] == booking["nomor_transaksi"]


def test_nomor_transaksi_dua_booking_berbeda_menit_beda_nomor(single_tenant, monkeypatch):
    _patch_sekarang(monkeypatch, 10, 0)
    b1 = _buat_booking(single_tenant["tenant_id"], jam_mulai="10:00", hari_offset=1)
    _patch_sekarang(monkeypatch, 10, 1)
    b2 = _buat_booking(single_tenant["tenant_id"], jam_mulai="10:00", hari_offset=2)
    assert b1["nomor_transaksi"] != b2["nomor_transaksi"]


# ============================= Reuse di booking_gateway_db (Riwayat Transaksi) =============================

def test_gateway_transaksi_reuse_nomor_booking(app_client, monkeypatch):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    payment_gateway_db.update_config(merchant_id="37070", server_key="u", secret_key="p")
    booking_db.update_payment_settings(metode_aktif=["transfer", "qris", "gateway"], tenant_id=tenant["id"])
    barber_id, service_id = _siapkan_barber_dan_service(tenant["id"])
    monkeypatch.setattr(payment_gateway_client, "buat_transaksi",
                         lambda *a, **kw: {"token": "tok-x", "redirect_url": "https://example.test/pay"})
    _patch_sekarang(monkeypatch, 14, 22)

    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    body = {
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "16:00",
        "service_ids": [service_id], "customer_nama": "Budi", "customer_whatsapp": "081234567890",
        "metode_pembayaran": "gateway",
    }
    r = app_client.post("/api/public/booking", params={"tenant": "mugen-hair-co"}, json=body)
    assert r.status_code == 200, r.text
    booking = r.json()
    assert booking["nomor_transaksi"] is not None

    transaksi = booking_gateway_db.get_transaksi_by_order_id(booking["gateway_order_id"])
    # SATU nomor yang SAMA persis -- Riwayat Transaksi/Super Admin dan layar
    # checkout customer TIDAK PERNAH menampilkan dua angka berbeda untuk
    # booking yang sama.
    assert transaksi["nomor_transaksi"] == booking["nomor_transaksi"]


def test_gateway_transaksi_tabrakan_nomor_dapat_sufiks_bukan_gagal(single_tenant):
    """Dua transaksi gateway dengan nomor_transaksi booking yang SAMA
    (kondisi buatan -- kolisi asli sangat jarang) TIDAK boleh membuat
    checkout kedua gagal, HANYA nomor tampilannya yang dapat sufiks."""
    tenant_id = single_tenant["tenant_id"]
    tenant = tenant_db.get_tenant(tenant_id)
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id)
    b1 = _buat_booking(tenant_id, metode_pembayaran="transfer", barber_id=barber_id, service_id=service_id, hari_offset=1)
    barber_id2, service_id2 = _siapkan_barber_dan_service(tenant_id)
    b2 = _buat_booking(tenant_id, metode_pembayaran="transfer", barber_id=barber_id2, service_id=service_id2, hari_offset=2)

    nomor_sama = "1705071313XX"
    order_id_1 = booking_gateway_db.buat_order_id(tenant_id, b1["id"])
    t1 = booking_gateway_db.buat_transaksi(
        order_id_1, tenant_id, tenant["nama_barbershop"], b1["id"], b1["customer_nama"], b1["nama_barber"],
        b1["daftar_service"], b1["total_harga"], nomor_transaksi=nomor_sama,
    )
    order_id_2 = booking_gateway_db.buat_order_id(tenant_id, b2["id"])
    t2 = booking_gateway_db.buat_transaksi(
        order_id_2, tenant_id, tenant["nama_barbershop"], b2["id"], b2["customer_nama"], b2["nama_barber"],
        b2["daftar_service"], b2["total_harga"], nomor_transaksi=nomor_sama,
    )
    assert t1["nomor_transaksi"] == nomor_sama
    assert t2["nomor_transaksi"] == f"{nomor_sama}-2"


# ============================= Jam operasional: unit _di_luar_jam_operasional() =============================

def _wib(jam, menit=0):
    return datetime(2026, 8, 7, jam, menit, tzinfo=WIB)


def test_tepat_jam_buka_dianggap_buka():
    assert booking_db._di_luar_jam_operasional(_wib(10, 0), "10:00", "20:00") is False


def test_tepat_jam_tutup_dianggap_tutup():
    assert booking_db._di_luar_jam_operasional(_wib(20, 0), "10:00", "20:00") is True


def test_sebelum_jam_buka_dianggap_tutup():
    assert booking_db._di_luar_jam_operasional(_wib(7, 0), "10:00", "20:00") is True


def test_setelah_jam_tutup_dianggap_tutup():
    assert booking_db._di_luar_jam_operasional(_wib(21, 0), "10:00", "20:00") is True


def test_tengah_jam_operasional_dianggap_buka():
    assert booking_db._di_luar_jam_operasional(_wib(15, 0), "10:00", "20:00") is False


# ============================= Jam operasional: integrasi buat_booking() =============================

def test_booking_dalam_jam_operasional_flag_false(single_tenant, monkeypatch):
    booking_db.update_booking_settings(jam_buka="10:00", jam_tutup="20:00", tenant_id=single_tenant["tenant_id"])
    _patch_sekarang(monkeypatch, 15, 0)
    booking = _buat_booking(single_tenant["tenant_id"], jam_mulai="10:00")
    assert booking["dibuat_di_luar_jam_operasional"] is False


def test_booking_luar_jam_operasional_setelah_tutup_flag_true(single_tenant, monkeypatch):
    booking_db.update_booking_settings(jam_buka="10:00", jam_tutup="20:00", tenant_id=single_tenant["tenant_id"])
    _patch_sekarang(monkeypatch, 21, 0)
    booking = _buat_booking(single_tenant["tenant_id"], jam_mulai="10:00")
    assert booking["dibuat_di_luar_jam_operasional"] is True


def test_booking_luar_jam_pakai_waktu_dibuat_bukan_jam_appointment(single_tenant, monkeypatch):
    """Booking pukul 21:00 (tutup) untuk appointment BESOK jam 10:00 (persis
    jam buka) -- TETAP dianggap dibuat di luar jam operasional, SESUAI
    spek eksplisit: yang menentukan adalah waktu booking dibuat, bukan
    jam appointment."""
    booking_db.update_booking_settings(jam_buka="10:00", jam_tutup="20:00", tenant_id=single_tenant["tenant_id"])
    _patch_sekarang(monkeypatch, 21, 0)
    booking = _buat_booking(single_tenant["tenant_id"], jam_mulai="10:00", hari_offset=1)
    assert booking["dibuat_di_luar_jam_operasional"] is True


def test_booking_jam_operasional_beda_per_tenant(two_tenants, monkeypatch):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    booking_db.update_booking_settings(jam_buka="08:00", jam_tutup="12:00", tenant_id=tenant_a)
    booking_db.update_booking_settings(jam_buka="14:00", jam_tutup="22:00", tenant_id=tenant_b)
    _patch_sekarang(monkeypatch, 10, 0)  # buka untuk tenant A, tutup untuk tenant B

    barber_a, service_a = _siapkan_barber_dan_service(tenant_a)
    barber_b, service_b = _siapkan_barber_dan_service(tenant_b)
    # jam_mulai HARUS di dalam jam_buka/jam_tutup masing-masing tenant
    # (validasi slot booking yang SUDAH ADA, tidak berhubungan dengan
    # logika baru yang diuji di sini -- itu soal jam booking DIBUAT, bukan
    # jam appointment).
    booking_a = _buat_booking(tenant_a, jam_mulai="09:00", barber_id=barber_a, service_id=service_a)
    booking_b = _buat_booking(tenant_b, jam_mulai="15:00", barber_id=barber_b, service_id=service_b)

    assert booking_a["dibuat_di_luar_jam_operasional"] is False
    assert booking_b["dibuat_di_luar_jam_operasional"] is True
