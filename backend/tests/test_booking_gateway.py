"""
test_booking_gateway.py — Implementasi Payment Gateway & Riwayat Transaksi
Multi-Tenant: Payment Gateway Booking Customer (Sistem B)
=============================================================================
Cakupan: booking metode "gateway" SELALU mulai "menunggu_verifikasi" (bukan
langsung terverifikasi saat dibuat -- regresi keamanan langsung dari audit),
checkout sukses membuat baris transaksi + booking diperkaya checkout_token/
redirect_url, checkout gagal (provider bermasalah) membatalkan booking
otomatis (slot bebas lagi), signature/order_id/gross_amount WAJIB lolos
sebelum efek samping apa pun (webhook), idempoten terhadap notifikasi
duplikat, status "berhasil" -> booking terverifikasi, status
"gagal"/"kedaluwarsa"/"dibatalkan" -> booking dibatalkan, "refund" TIDAK
mengubah status booking, verifikasi manual staff DITOLAK untuk booking
gateway (hanya webhook resmi yang boleh), isolasi tenant di
GET /api/booking/transactions[/{id}]. SEMUA test memakai payload buatan
sendiri dengan signature dihitung manual, panggilan provider di-monkeypatch
-- TIDAK PERNAH memanggil provider sungguhan."""

import hashlib
import itertools
from datetime import timedelta

import booking_db
import booking_gateway_db
import booking_gateway_webhook
import database as db
import gateway_client_base
import payment_gateway_client
import payment_gateway_db
import payment_provider_client
import snap_advance_db
import snap_payment_db
import tenant_db
from booking_db import _hari_ini_wib

USER_ID = "bot37070-test"
PASSWORD = "p-test-booking-gateway"
_urutan_unik = itertools.count(1)


def _hitung_signature(bill_no, payment_status_code, user_id=USER_ID, password=PASSWORD):
    """SHA1(MD5(user_id + password + bill_no + payment_status_code)) --
    formula RESMI Faspay Xpress v4 Payment Notification."""
    tahap1 = hashlib.md5(f"{user_id}{password}{bill_no}{payment_status_code}".encode()).hexdigest()
    return hashlib.sha1(tahap1.encode()).hexdigest()


def _payload(order_id, payment_status_code, nominal, payment_channel="QRIS",
             user_id=USER_ID, password=PASSWORD):
    """Payload notifikasi berformat Faspay Xpress v4 Payment Notification --
    lihat booking_gateway_webhook.py::proses_notifikasi() untuk field yang
    dibaca."""
    return {
        "request": "Payment Notification",
        "trx_id": "89850370" + order_id[-8:] if len(order_id) >= 8 else "8985037012345678",
        "merchant_id": "37070",
        "merchant": "RivoiR",
        "bill_no": order_id,
        "payment_reff": "null",
        "payment_date": "2026-01-01 10:00:00",
        "payment_status_code": payment_status_code,
        "payment_status_desc": "Payment Status",
        "bill_total": str(int(nominal)),
        "payment_total": str(int(nominal)),
        "payment_channel_uid": "402",
        "payment_channel": payment_channel,
        "signature": _hitung_signature(order_id, payment_status_code, user_id, password),
    }


def _aktifkan_pgw():
    payment_gateway_db.update_config(merchant_id="37070", server_key=USER_ID, secret_key=PASSWORD)


def _aktifkan_snap():
    """Migrasi Faspay SNAP Advance: checkout "gateway" sekarang lewat SNAP
    (bukan lagi Xpress v4, lihat routers/booking.py) -- helper setara
    _aktifkan_pgw() di atas TAPI mengisi kredensial minimal yang membuat
    payment_provider_client.is_enabled() True dan channel "va" aktif."""
    snap_advance_db.update_config(
        merchant_id="37070", partner_id="37070", channel_id="77001", va_bank_aktif=["702"],
        private_key="-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----",
        channel_aktif=["va", "qris"],
    )


def _tenant_default():
    return tenant_db.get_tenant_by_slug("mugen-hair-co")


def _siapkan_barber_dan_service(tenant_id, nominal=100000):
    """`barbers.nama`/`services.nama` UNIQUE GLOBAL (technical debt pra-multi-
    tenant, tidak diubah di sini) -- sertakan tenant_id + counter unik di
    nama supaya test yang memanggil helper ini berkali-kali (dua tenant,
    atau berkali-kali dalam satu tenant) tidak bentrok UNIQUE constraint."""
    booking_db.update_payment_settings(metode_aktif=["transfer", "gateway"], tenant_id=tenant_id)
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber Gateway T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Potong Rambut T{tenant_id}-{n}", nominal, tenant_id=tenant_id)
    return barber_id, service_id


def _buat_booking_gateway(tenant_id, nominal=100000, hari_offset=1):
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id, nominal)
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    return booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                    service_ids=[service_id], customer_nama="Budi",
                                    customer_whatsapp="081234567890", metode_pembayaran="gateway",
                                    tenant_id=tenant_id)


def _buat_transaksi_untuk_booking(tenant_id, booking, nominal=None):
    tenant = tenant_db.get_tenant(tenant_id)
    order_id = booking_gateway_db.buat_order_id(tenant_id, booking["id"])
    return booking_gateway_db.buat_transaksi(
        order_id, tenant_id, tenant["nama_barbershop"] if tenant else "-", booking["id"],
        booking["customer_nama"], booking["nama_barber"], booking["daftar_service"],
        nominal if nominal is not None else booking["total_harga"],
        checkout_token="tok-test", checkout_redirect_url="https://example.test/pay",
    )


# ============================= buat_booking(): status awal SELALU menunggu =============================

def test_booking_gateway_selalu_mulai_menunggu_verifikasi(app_client):
    """Regresi keamanan (audit): booking metode 'gateway' TIDAK PERNAH
    langsung 'terverifikasi' saat dibuat -- HANYA webhook resmi provider
    yang boleh mengubahnya jadi 'terverifikasi'."""
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    assert booking["status_pembayaran"] == "menunggu_verifikasi"


# ============================= Checkout endpoint (HTTP) =============================

def test_checkout_gateway_503_belum_dikonfigurasi(app_client):
    tenant = _tenant_default()
    barber_id, service_id = _siapkan_barber_dan_service(tenant["id"])
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    body = {
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "10:00",
        "service_ids": [service_id], "customer_nama": "Budi", "customer_whatsapp": "081234567890",
        "metode_pembayaran": "gateway",
    }
    r = app_client.post("/api/public/booking", params={"tenant": "mugen-hair-co"}, json=body)
    assert r.status_code == 503


def test_checkout_gateway_sukses(app_client, monkeypatch):
    """Migrasi Faspay SNAP Advance: checkout "gateway" sekarang lewat
    payment_provider_client.py (SNAP VA/QRIS), lihat _aktifkan_snap()."""
    _aktifkan_snap()
    tenant = _tenant_default()
    barber_id, service_id = _siapkan_barber_dan_service(tenant["id"])
    monkeypatch.setattr(payment_provider_client, "buat_transaksi",
                         lambda *a, **kw: {"va_number": "70212345678901", "provider_transaction_id": "trx-1",
                                            "expired_at": "2026-01-01T23:59:59+07:00", "provider_response": "{}"})

    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    body = {
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "10:00",
        "service_ids": [service_id], "customer_nama": "Budi", "customer_whatsapp": "081234567890",
        "metode_pembayaran": "gateway", "channel": "va", "bank_code": "702",
    }
    r = app_client.post("/api/public/booking", params={"tenant": "mugen-hair-co"}, json=body)
    assert r.status_code == 200, r.text
    hasil = r.json()
    assert hasil["status_pembayaran"] == "menunggu_verifikasi"
    assert hasil["va_number"] == "70212345678901"
    assert hasil["payment_reference"]

    transaksi = snap_payment_db.get_transaksi_by_reference(hasil["payment_reference"])
    assert transaksi is not None
    assert transaksi["tenant_id"] == tenant["id"]
    assert transaksi["status"] == "PENDING"
    assert transaksi["amount"] == hasil["total_harga"]


def test_checkout_gateway_gagal_membatalkan_booking_otomatis(app_client, monkeypatch):
    """Provider gagal dihubungi/menolak -> booking yang SUDAH tersimpan
    (mengisi slot) dibatalkan otomatis, TIDAK menggantung tanpa jalan bayar.
    Migrasi Faspay SNAP Advance: lihat _aktifkan_snap()."""
    _aktifkan_snap()
    tenant = _tenant_default()
    barber_id, service_id = _siapkan_barber_dan_service(tenant["id"])

    def _gagal(*a, **kw):
        raise gateway_client_base.GatewayTimeoutError("Provider timeout.")
    monkeypatch.setattr(payment_provider_client, "buat_transaksi", _gagal)

    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    body = {
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "10:00",
        "service_ids": [service_id], "customer_nama": "Budi", "customer_whatsapp": "081234567890",
        "metode_pembayaran": "gateway", "channel": "va", "bank_code": "702",
    }
    r = app_client.post("/api/public/booking", params={"tenant": "mugen-hair-co"}, json=body)
    assert r.status_code == 502

    # Slot bebas lagi -- booking baru di jam/tanggal yang sama (metode lain) harus berhasil.
    body2 = dict(body, metode_pembayaran="transfer")
    r2 = app_client.post("/api/public/booking", params={"tenant": "mugen-hair-co"}, json=body2)
    assert r2.status_code == 200, r2.text


# ============================= Webhook: validasi keamanan =============================

def test_signature_tidak_valid_ditolak(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "2", transaksi["nominal"])
    payload["signature"] = "signature-palsu"

    try:
        booking_gateway_webhook.proses_notifikasi(payload)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "Signature" in str(e)
    assert booking_gateway_db.get_transaksi(transaksi["id"])["status_pembayaran"] == "menunggu_pembayaran"


def test_order_id_tidak_dikenal_ditolak(app_client):
    _aktifkan_pgw()
    payload = _payload("BOOK-TIDAK-ADA", "2", 100000)
    try:
        booking_gateway_webhook.proses_notifikasi(payload)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak dikenal" in str(e)


def test_gross_amount_dimanipulasi_ditolak(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"], nominal=100000)
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "2", 1000)  # dipalsukan jadi kecil

    try:
        booking_gateway_webhook.proses_notifikasi(payload)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak cocok" in str(e)
    assert booking_gateway_db.get_transaksi(transaksi["id"])["status_pembayaran"] == "menunggu_pembayaran"


def test_transaction_status_tidak_dikenal_ditolak(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "99", transaksi["nominal"])  # kode tidak dikenal
    try:
        booking_gateway_webhook.proses_notifikasi(payload)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak dikenal" in str(e)


# ============================= Cascade ke booking =============================

def test_settlement_berhasil_booking_terverifikasi(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "2", transaksi["nominal"], payment_channel="QRIS")

    hasil = booking_gateway_webhook.proses_notifikasi(payload)
    assert hasil["status_pembayaran"] == "berhasil"
    assert hasil["channel_pembayaran"] == "QRIS"
    assert hasil["paid_at"] is not None

    updated_booking = booking_db.get_booking(booking["id"])
    assert updated_booking["status_pembayaran"] == "terverifikasi"
    assert updated_booking["status_booking"] == "aktif"


def test_in_process_menjadi_diproses_tanpa_cascade(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "1", transaksi["nominal"], payment_channel="Kartu Kredit")

    hasil = booking_gateway_webhook.proses_notifikasi(payload)
    assert hasil["status_pembayaran"] == "diproses"
    updated_booking = booking_db.get_booking(booking["id"])
    assert updated_booking["status_pembayaran"] == "menunggu_verifikasi"
    assert updated_booking["status_booking"] == "aktif"


def test_deny_cancel_expire_membatalkan_booking(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    for i, (payment_status_code, expected_status) in enumerate([
        ("3", "gagal"), ("8", "dibatalkan"), ("7", "kedaluwarsa"),
    ]):
        booking = _buat_booking_gateway(tenant["id"], hari_offset=2 + i)
        transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
        payload = _payload(transaksi["order_id"], payment_status_code, transaksi["nominal"])

        hasil = booking_gateway_webhook.proses_notifikasi(payload)
        assert hasil["status_pembayaran"] == expected_status
        assert booking_db.get_booking(booking["id"])["status_booking"] == "dibatalkan"


def test_refund_tidak_mengubah_status_booking(app_client):
    """Refund adalah peristiwa PASCA booking selesai -- TIDAK PERNAH
    membatalkan/mengaktifkan ulang booking secara otomatis."""
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    booking_gateway_webhook.proses_notifikasi(_payload(transaksi["order_id"], "2", transaksi["nominal"]))

    hasil = booking_gateway_webhook.proses_notifikasi(_payload(transaksi["order_id"], "4", transaksi["nominal"]))
    assert hasil["status_pembayaran"] == "refund"
    assert booking_db.get_booking(booking["id"])["status_booking"] == "aktif"
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"


# ============================= Idempoten =============================

def test_notifikasi_duplikat_tidak_double_cascade(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "2", transaksi["nominal"])

    hasil1 = booking_gateway_webhook.proses_notifikasi(payload)
    hasil2 = booking_gateway_webhook.proses_notifikasi(payload)  # provider kirim ulang notifikasi yang sama
    assert hasil1["paid_at"] == hasil2["paid_at"]

    log = booking_gateway_db.list_status_log(transaksi["id"])
    assert len(log) == 1


# ============================= Endpoint HTTP webhook =============================

def test_endpoint_webhook_sukses(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "2", transaksi["nominal"])

    r = app_client.post("/api/public/booking/gateway-webhook", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "berhasil"


def test_endpoint_webhook_signature_salah_400(app_client):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "2", transaksi["nominal"])
    payload["signature"] = "salah"

    r = app_client.post("/api/public/booking/gateway-webhook", json=payload)
    assert r.status_code == 400


def test_endpoint_webhook_tanpa_login_bisa_diakses(app_client):
    """Endpoint ini PUBLIK -- provider TIDAK PERNAH mengirim Authorization
    header apa pun, jadi TIDAK BOLEH ada dependency auth apa pun di sini."""
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    payload = _payload(transaksi["order_id"], "0", transaksi["nominal"])

    r = app_client.post("/api/public/booking/gateway-webhook", json=payload)
    assert r.status_code == 200, r.text


def test_endpoint_gateway_status_publik_read_only(app_client):
    """GET /api/public/booking/gateway-status/{order_id} -- dipakai polling
    wizard booking publik, payload minim TANPA data sensitif toko."""
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)

    r = app_client.get(f"/api/public/booking/gateway-status/{transaksi['order_id']}",
                        params={"tenant": "mugen-hair-co"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status_pembayaran"] == "menunggu_pembayaran"
    assert set(data.keys()) == {"status_pembayaran", "channel_pembayaran", "nominal"}


# ============================= Verifikasi manual staff DITOLAK =============================

def test_verifikasi_manual_ditolak_untuk_booking_gateway(two_tenants):
    client, headers_a, tenant_a = two_tenants["client"], two_tenants["headers_a"], two_tenants["tenant_a"]
    booking = _buat_booking_gateway(tenant_a)

    r = client.post(f"/api/booking/{booking['id']}/verifikasi", headers=headers_a)
    assert r.status_code == 422
    assert "gateway" in r.json()["detail"].lower() or "Payment Gateway" in r.json()["detail"]

    # Booking TETAP menunggu_verifikasi -- tidak ada celah tandai lunas manual.
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "menunggu_verifikasi"


# ============================= Isolasi Multi-Tenant =============================

def test_list_transaksi_terisolasi_per_tenant(two_tenants):
    client = two_tenants["client"]
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    headers_a, headers_b = two_tenants["headers_a"], two_tenants["headers_b"]

    booking_a = _buat_booking_gateway(tenant_a)
    _buat_transaksi_untuk_booking(tenant_a, booking_a)
    booking_b = _buat_booking_gateway(tenant_b)
    _buat_transaksi_untuk_booking(tenant_b, booking_b)

    ra = client.get("/api/booking/transactions", headers=headers_a)
    assert ra.status_code == 200, ra.text
    assert len(ra.json()) == 1
    assert ra.json()[0]["tenant_id"] == tenant_a

    rb = client.get("/api/booking/transactions", headers=headers_b)
    assert rb.status_code == 200, rb.text
    assert len(rb.json()) == 1
    assert rb.json()[0]["tenant_id"] == tenant_b


def test_detail_transaksi_tenant_lain_404(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_b = two_tenants["headers_b"]

    booking_a = _buat_booking_gateway(tenant_a)
    transaksi_a = _buat_transaksi_untuk_booking(tenant_a, booking_a)

    r = client.get(f"/api/booking/transactions/{transaksi_a['id']}", headers=headers_b)
    assert r.status_code == 404


def test_detail_transaksi_menyertakan_status_log(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_a = two_tenants["headers_a"]
    _aktifkan_pgw()

    booking_a = _buat_booking_gateway(tenant_a)
    transaksi_a = _buat_transaksi_untuk_booking(tenant_a, booking_a)
    booking_gateway_webhook.proses_notifikasi(
        _payload(transaksi_a["order_id"], "2", transaksi_a["nominal"]))

    r = client.get(f"/api/booking/transactions/{transaksi_a['id']}", headers=headers_a)
    assert r.status_code == 200, r.text
    assert r.json()["status_pembayaran"] == "berhasil"
    assert len(r.json()["status_log"]) == 1


# ============================= AUDIT: guard urutan status (perbaikan pasca-audit kesiapan) =============================

def test_notifikasi_basi_setelah_berhasil_tidak_membatalkan_booking_yang_sudah_dibayar(app_client):
    """Regresi langsung dari temuan audit kesiapan: webhook TIDAK MENJAMIN
    urutan pengiriman -- notifikasi "cancel"/"deny"/"expire" yang tertunda
    di jaringan provider bisa datang SETELAH "settlement" yang sudah lebih
    dulu diproses. TANPA guard, ini akan membatalkan booking yang SUDAH
    DIBAYAR (batalkan_booking() dipanggil berdasarkan status_baru yang
    DIMINTA notifikasi, bukan status yang BENAR-BENAR tersimpan)."""
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)

    # settlement diproses lebih dulu -- booking terverifikasi, slot terisi.
    booking_gateway_webhook.proses_notifikasi(_payload(transaksi["order_id"], "2", transaksi["nominal"]))
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"

    # notifikasi "cancel" BASI (tertunda di jaringan, datang belakangan) --
    # HARUS ditolak, TIDAK boleh membatalkan booking yang sudah dibayar.
    hasil = booking_gateway_webhook.proses_notifikasi(_payload(transaksi["order_id"], "8", transaksi["nominal"]))
    assert hasil["status_pembayaran"] == "berhasil"  # TETAP berhasil, TIDAK turun jadi "dibatalkan"

    booking_setelah = booking_db.get_booking(booking["id"])
    assert booking_setelah["status_pembayaran"] == "terverifikasi"
    assert booking_setelah["status_booking"] == "aktif"  # slot TIDAK dibebaskan

    log = booking_gateway_db.list_status_log(transaksi["id"])
    assert len(log) == 2
    assert log[0]["status_baru"] == "berhasil"
    assert log[0]["sumber"] == "webhook"
    assert log[1]["status_lama"] == "berhasil"
    assert log[1]["status_baru"] == "dibatalkan"
    assert log[1]["sumber"] == "webhook_diabaikan"  # dicatat untuk audit, TAPI TIDAK diterapkan


def test_notifikasi_basi_setelah_gagal_tidak_diterapkan(app_client):
    """Sisi lain guard yang sama: begitu transaksi final ("gagal"), booking
    SUDAH dibatalkan (slot bebas) -- notifikasi "settlement" yang datang
    belakangan TIDAK BOLEH memverifikasi ulang booking yang sudah tidak
    aktif (mencegah transaksi tercatat "berhasil" padahal booking-nya sudah
    hilang/dibatalkan orang lain sudah bisa mengisi slot itu)."""
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)

    booking_gateway_webhook.proses_notifikasi(_payload(transaksi["order_id"], "3", transaksi["nominal"]))
    assert booking_db.get_booking(booking["id"])["status_booking"] == "dibatalkan"

    hasil = booking_gateway_webhook.proses_notifikasi(_payload(transaksi["order_id"], "2", transaksi["nominal"]))
    assert hasil["status_pembayaran"] == "gagal"  # TETAP gagal, TIDAK "diperbaiki" jadi berhasil


def test_berhasil_ke_refund_tetap_diizinkan_meski_status_sudah_final(app_client):
    """Satu-satunya pengecualian guard urutan status: "berhasil" -> "refund"
    tetap sah (peristiwa PASCA pembayaran selesai)."""
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)

    booking_gateway_webhook.proses_notifikasi(_payload(transaksi["order_id"], "2", transaksi["nominal"]))
    hasil = booking_gateway_webhook.proses_notifikasi(_payload(transaksi["order_id"], "4", transaksi["nominal"]))
    assert hasil["status_pembayaran"] == "refund"

    log = booking_gateway_db.list_status_log(transaksi["id"])
    assert log[-1]["status_baru"] == "refund"
    assert log[-1]["sumber"] == "webhook"  # diterapkan sungguhan, BUKAN diabaikan


# ============================= AUDIT: rekonsiliasi manual (perbaikan pasca-audit kesiapan) =============================

def test_rekonsiliasi_manual_menerapkan_status_dari_provider(app_client, monkeypatch):
    """Regresi langsung dari temuan audit kesiapan: webhook yang TIDAK
    PERNAH sampai sama sekali (bukan telat -- hilang total) sebelumnya
    membuat transaksi macet selamanya tanpa jalan pemulihan (cek_status_
    transaksi() sudah ada tapi tidak pernah dipanggil). rekonsiliasi_manual()
    memanggil ULANG provider langsung (di sini di-monkeypatch, TIDAK PERNAH
    memanggil provider sungguhan) lalu menerapkan hasilnya lewat jalur SAMA
    PERSIS dengan webhook resmi."""
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"])
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)
    assert transaksi["status_pembayaran"] == "menunggu_pembayaran"

    monkeypatch.setattr(payment_gateway_client, "cek_status_transaksi", lambda order_id: {
        "payment_status_code": "2", "bill_total": str(transaksi["nominal"]),
        "payment_channel": "QRIS", "trx_id": "prov-txn-123",
    })

    hasil = booking_gateway_webhook.rekonsiliasi_manual(transaksi["id"], tenant_id=tenant["id"])
    assert hasil["status_pembayaran"] == "berhasil"
    assert hasil["transaction_id_provider"] == "prov-txn-123"
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"

    log = booking_gateway_db.list_status_log(transaksi["id"])
    assert len(log) == 1
    assert log[0]["sumber"] == "rekonsiliasi_manual"


def test_rekonsiliasi_manual_gross_amount_tidak_cocok_ditolak(app_client, monkeypatch):
    _aktifkan_pgw()
    tenant = _tenant_default()
    booking = _buat_booking_gateway(tenant["id"], nominal=100000)
    transaksi = _buat_transaksi_untuk_booking(tenant["id"], booking)

    monkeypatch.setattr(payment_gateway_client, "cek_status_transaksi", lambda order_id: {
        "payment_status_code": "2", "bill_total": "1000", "payment_channel": "QRIS",
    })

    try:
        booking_gateway_webhook.rekonsiliasi_manual(transaksi["id"], tenant_id=tenant["id"])
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak cocok" in str(e)
    assert booking_gateway_db.get_transaksi(transaksi["id"])["status_pembayaran"] == "menunggu_pembayaran"


def test_cek_status_transaksi_belum_tersedia_untuk_faspay(app_client):
    """Keputusan eksplisit: dokumentasi resmi Faspay Xpress v4 yang dipakai
    TIDAK mencakup endpoint Inquiry/Check Status -- cek_status_transaksi()
    SENGAJA melempar error jelas (TANPA memanggil HTTP apa pun/menebak
    endpoint), bukan diimplementasikan berdasarkan asumsi."""
    try:
        payment_gateway_client.cek_status_transaksi("BOOK-1-1-dummy")
        assert False, "harus melempar GatewayError"
    except gateway_client_base.GatewayError as e:
        assert "Inquiry" in str(e) or "Check Status" in str(e)


def test_rekonsiliasi_manual_transaksi_tenant_lain_ditolak(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    _aktifkan_pgw()
    booking_a = _buat_booking_gateway(tenant_a)
    transaksi_a = _buat_transaksi_untuk_booking(tenant_a, booking_a)

    try:
        booking_gateway_webhook.rekonsiliasi_manual(transaksi_a["id"], tenant_id=tenant_b)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak ditemukan" in str(e)


def test_endpoint_cek_ulang_transaksi_sukses(two_tenants, monkeypatch):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_a = two_tenants["headers_a"]
    _aktifkan_pgw()

    booking_a = _buat_booking_gateway(tenant_a)
    transaksi_a = _buat_transaksi_untuk_booking(tenant_a, booking_a)
    monkeypatch.setattr(payment_gateway_client, "cek_status_transaksi", lambda order_id: {
        "payment_status_code": "2", "bill_total": str(transaksi_a["nominal"]), "payment_channel": "GoPay",
    })

    r = client.post(f"/api/booking/transactions/{transaksi_a['id']}/cek-ulang", headers=headers_a)
    assert r.status_code == 200, r.text
    assert r.json()["status_pembayaran"] == "berhasil"


def test_endpoint_cek_ulang_transaksi_tenant_lain_ditolak(two_tenants, monkeypatch):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_b = two_tenants["headers_b"]
    _aktifkan_pgw()

    booking_a = _buat_booking_gateway(tenant_a)
    transaksi_a = _buat_transaksi_untuk_booking(tenant_a, booking_a)

    r = client.post(f"/api/booking/transactions/{transaksi_a['id']}/cek-ulang", headers=headers_b)
    assert r.status_code == 422
