"""test_whatsapp_notifikasi.py — FITUR Notifikasi WhatsApp Otomatis Booking
=============================================================================
Cakupan: whatsapp_service.kirim_whatsapp() tidak pernah memanggil jaringan
kalau token belum diisi, token per-tenant (isolasi), template pesan berisi
nominal/nama/tanggal yang benar, TIGA titik pemicu di booking_db.py
(buat_booking metode qris, verifikasi_pembayaran, batalkan_booking) memanggil
notifikasi TEPAT SATU KALI (idempoten -- guard status SEBELUM update),
verifikasi_pembayaran() dipicu dari DUA jalur (manual staff & webhook Faspay
otomatis) sama-sama mengirim notifikasi (SATU fungsi, DUA pemicu), dan
endpoint Setting > WhatsApp (require_admin, staff ditolak).

SEMUA test memonkeypatch whatsapp_service.kirim_whatsapp/requests.post --
TIDAK PERNAH memanggil Fonnte sungguhan."""

import hashlib
import itertools
from datetime import timedelta

import billing_db
import booking_db
import booking_gateway_db
import booking_gateway_webhook
import database as db
import payment_gateway_db
import subscription_db
import tenant_db
import whatsapp_service
import whatsapp_templates
from booking_db import _hari_ini_wib


def _beri_fitur_whatsapp_reminder(tenant_id):
    """Feature Gating "whatsapp_reminder" (AUDIT "fitur hardcode di
    Superadmin", lihat billing_db.py::seed_grandfather_fitur_baru_
    digerbang()): fitur ini SUDAH otomatis ter-grandfather ke SEMUA paket
    default sejak boot (fitur ini sebelumnya selalu gratis untuk semua
    tenant) -- baris ini HANYA perlu membuat baris tenant_subscriptions itu
    sendiri (fail-CLOSED tanpa baris subscription sama sekali, lihat
    feature_access.py), TIDAK perlu assign manual apa pun."""
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")

_urutan_unik = itertools.count(1)


def _siapkan_barber_dan_service(tenant_id, nominal=100000, metode_aktif=None):
    booking_db.update_payment_settings(metode_aktif=metode_aktif or ["transfer", "qris", "gateway"],
                                        tenant_id=tenant_id)
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber WA T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Potong Rambut WA T{tenant_id}-{n}", nominal, tenant_id=tenant_id)
    return barber_id, service_id


def _buat_booking(tenant_id, metode_pembayaran, nominal=100000, hari_offset=1):
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id, nominal)
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    return booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                    service_ids=[service_id], customer_nama="Budi",
                                    customer_whatsapp="081234567890", metode_pembayaran=metode_pembayaran,
                                    tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# whatsapp_service.py -- token gating, isolasi per-tenant
# ---------------------------------------------------------------------------

def test_kirim_whatsapp_tanpa_token_tidak_memanggil_jaringan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]

    def _gagal_kalau_dipanggil(*a, **kw):
        raise AssertionError("requests.post TIDAK BOLEH dipanggil kalau token belum diisi.")
    monkeypatch.setattr("whatsapp_service.requests.post", _gagal_kalau_dipanggil)

    assert whatsapp_service.is_enabled(tenant_id=tenant_id) is False
    assert whatsapp_service.kirim_whatsapp("081234567890", "tes", tenant_id=tenant_id) is False


def test_token_tersimpan_per_tenant_terisolasi(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    whatsapp_service.set_token("token-punya-a", tenant_id=tenant_a)
    assert whatsapp_service.get_token(tenant_id=tenant_a) == "token-punya-a"
    assert whatsapp_service.get_token(tenant_id=tenant_b) == ""
    assert whatsapp_service.is_enabled(tenant_id=tenant_a) is True
    assert whatsapp_service.is_enabled(tenant_id=tenant_b) is False


def test_kirim_whatsapp_sukses(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    whatsapp_service.set_token("token-valid", tenant_id=tenant_id)

    class _Resp:
        status_code = 200
        def json(self): return {"status": True}
    dipanggil = {}
    def _post(url, data=None, headers=None, timeout=None):
        dipanggil["url"] = url; dipanggil["data"] = data; dipanggil["headers"] = headers
        return _Resp()
    monkeypatch.setattr("whatsapp_service.requests.post", _post)

    assert whatsapp_service.kirim_whatsapp("081234567890", "halo", tenant_id=tenant_id) is True
    assert dipanggil["headers"]["Authorization"] == "token-valid"
    assert dipanggil["data"]["target"] == "6281234567890"
    assert dipanggil["data"]["message"] == "halo"


def test_kirim_whatsapp_ditolak_fonnte(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    whatsapp_service.set_token("token-invalid", tenant_id=tenant_id)

    class _Resp:
        status_code = 200
        def json(self): return {"status": False, "reason": "token salah"}
    monkeypatch.setattr("whatsapp_service.requests.post", lambda *a, **kw: _Resp())
    assert whatsapp_service.kirim_whatsapp("081234567890", "halo", tenant_id=tenant_id) is False


# ---------------------------------------------------------------------------
# whatsapp_templates.py -- isi pesan
# ---------------------------------------------------------------------------

def test_render_default_berisi_nominal_dan_layanan():
    booking = {"customer_nama": "Budi", "total_harga": 150000, "daftar_service": "Dry Cut",
               "tanggal": "2026-08-20", "jam_mulai": "10:00"}
    pesan = whatsapp_templates.render("reminder_qris", booking, "Rivoir Barbershop")
    assert "Budi" in pesan
    assert "Rp 150.000" in pesan
    assert "Dry Cut" in pesan
    assert "Rivoir Barbershop" in pesan
    assert "20 Agustus 2026" in pesan


def test_render_konfirmasi_dan_pembatalan_default():
    booking = {"customer_nama": "Sari", "total_harga": 75000, "daftar_service": "Cut & Wash",
               "tanggal": "2026-09-01", "jam_mulai": "14:30"}
    konfirmasi = whatsapp_templates.render("konfirmasi_pembayaran", booking, "Toko A")
    assert "Rp 75.000" in konfirmasi and "terima & verifikasi" in konfirmasi
    batal = whatsapp_templates.render("pembatalan", booking, "Toko A")
    assert "dibatalkan" in batal or "kami batalkan" in batal


def test_render_template_custom_menimpa_default():
    booking = {"customer_nama": "Budi", "total_harga": 150000, "daftar_service": "Dry Cut",
               "tanggal": "2026-08-20", "jam_mulai": "10:00"}
    custom = "Hai {nama}! Segera bayar {nominal} ya untuk {layanan}."
    pesan = whatsapp_templates.render("reminder_qris", booking, "Toko A", custom)
    assert pesan == "Hai Budi! Segera bayar Rp 150.000 ya untuk Dry Cut."


def test_render_template_custom_kosong_fallback_ke_default():
    booking = {"customer_nama": "Budi", "total_harga": 150000, "daftar_service": "Dry Cut",
               "tanggal": "2026-08-20", "jam_mulai": "10:00"}
    pesan = whatsapp_templates.render("reminder_qris", booking, "Toko A", "   ")
    assert pesan == whatsapp_templates.render("reminder_qris", booking, "Toko A", None)


def test_render_template_custom_placeholder_liar_tidak_crash():
    booking = {"customer_nama": "Budi", "total_harga": 150000, "daftar_service": "Dry Cut",
               "tanggal": "2026-08-20", "jam_mulai": "10:00"}
    custom = "Halo {nama}, ada { kurung tidak lengkap dan {placeholder_ngawur}."
    pesan = whatsapp_templates.render("reminder_qris", booking, "Toko A", custom)
    assert "Halo Budi" in pesan  # tidak melempar exception


def test_get_set_templates_per_tenant(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    kosong = whatsapp_service.get_templates(tenant_id=tenant_id)
    assert kosong["reminder_qris"] == ""

    whatsapp_service.set_templates({"reminder_qris": "Custom reminder {nama}"}, tenant_id=tenant_id)
    isi = whatsapp_service.get_templates(tenant_id=tenant_id)
    assert isi["reminder_qris"] == "Custom reminder {nama}"
    assert isi["konfirmasi_pembayaran"] == ""  # tidak ikut berubah


def test_set_templates_jenis_tidak_dikenal_ditolak(single_tenant):
    import pytest
    tenant_id = single_tenant["tenant_id"]
    with pytest.raises(ValueError):
        whatsapp_service.set_templates({"jenis_ngawur": "x"}, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Titik pemicu di booking_db.py
# ---------------------------------------------------------------------------

def _pasang_penangkap_wa(monkeypatch):
    panggilan = []
    def _tangkap(nomor, pesan, tenant_id=None):
        panggilan.append({"nomor": nomor, "pesan": pesan, "tenant_id": tenant_id})
        return True
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", _tangkap)
    return panggilan


def test_buat_booking_qris_mengirim_reminder(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    panggilan = _pasang_penangkap_wa(monkeypatch)
    booking = _buat_booking(tenant_id, "qris")
    assert len(panggilan) == 1
    assert panggilan[0]["nomor"] == booking["customer_whatsapp"]
    assert panggilan[0]["tenant_id"] == tenant_id
    assert "segera" in panggilan[0]["pesan"].lower() or "silakan selesaikan pembayaran" in panggilan[0]["pesan"].lower()


def test_buat_booking_transfer_tidak_mengirim_reminder(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    panggilan = _pasang_penangkap_wa(monkeypatch)
    _buat_booking(tenant_id, "transfer")
    assert len(panggilan) == 0


def test_buat_booking_qris_tidak_mengirim_reminder_tanpa_fitur_whatsapp_reminder(single_tenant, monkeypatch):
    """Feature Gating "whatsapp_reminder" (AUDIT "fitur hardcode di
    Superadmin"): paket TANPA fitur ini (dicabut manual Super Admin, walau
    di-grandfather otomatis sejak boot) -- notifikasi TIDAK PERNAH dicoba
    dikirim sama sekali (bukan dicoba lalu gagal)."""
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    free = billing_db.get_package_by_kode("free")
    billing_db.set_package_features(free["id"], [])  # cabut semua fitur, termasuk whatsapp_reminder
    panggilan = _pasang_penangkap_wa(monkeypatch)

    _buat_booking(tenant_id, "qris")

    assert len(panggilan) == 0


def test_kirim_notifikasi_wa_booking_tenant_id_none_tidak_mengirim(monkeypatch):
    """tenant_id None (exception handler global/kasus tidak diketahui) --
    diperlakukan sama seperti "tidak punya fitur" (fail-CLOSED), bukan
    exception."""
    panggilan = _pasang_penangkap_wa(monkeypatch)
    booking_db._kirim_notifikasi_wa_booking(
        {"tenant_id": None, "customer_whatsapp": "081234567890"}, "reminder_qris")
    assert len(panggilan) == 0


def test_verifikasi_pembayaran_mengirim_konfirmasi_dan_idempoten(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    booking = _buat_booking(tenant_id, "transfer")  # metode selain qris -- tidak ada pesan reminder duluan
    panggilan = _pasang_penangkap_wa(monkeypatch)

    booking_db.verifikasi_pembayaran(booking["id"])
    assert len(panggilan) == 1
    assert "terima & verifikasi" in panggilan[0]["pesan"]

    # Panggilan KEDUA (mis. klik dobel Admin) -- TIDAK boleh kirim pesan lagi.
    booking_db.verifikasi_pembayaran(booking["id"])
    assert len(panggilan) == 1


def test_batalkan_booking_mengirim_pembatalan_dan_idempoten(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    booking = _buat_booking(tenant_id, "transfer")
    panggilan = _pasang_penangkap_wa(monkeypatch)

    booking_db.batalkan_booking(booking["id"])
    assert len(panggilan) == 1
    assert "batalkan" in panggilan[0]["pesan"].lower()

    booking_db.batalkan_booking(booking["id"])
    assert len(panggilan) == 1


def test_webhook_faspay_sukses_memicu_notifikasi_yang_sama(single_tenant, monkeypatch):
    """Payment gateway (Faspay) sukses -> booking_gateway_webhook.py memanggil
    booking_db.verifikasi_pembayaran() -- SATU fungsi yang sama dipakai
    verifikasi manual staff, jadi notifikasi WA otomatis ikut terpicu TANPA
    kode tambahan apa pun di jalur webhook."""
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
    panggilan = _pasang_penangkap_wa(monkeypatch)

    tahap1 = hashlib.md5(f"bot-testpass-test{order_id}2".encode()).hexdigest()
    signature = hashlib.sha1(tahap1.encode()).hexdigest()
    payload = {
        "bill_no": order_id, "payment_status_code": "2", "bill_total": str(booking["total_harga"]),
        "signature": signature, "payment_channel": "QRIS", "trx_id": "899999999999", "payment_reff": "null",
    }
    booking_gateway_webhook.proses_notifikasi(payload)

    assert len(panggilan) == 1
    assert "terima & verifikasi" in panggilan[0]["pesan"]


# ---------------------------------------------------------------------------
# Endpoint Setting > WhatsApp (require_admin, KHUSUS Owner)
# ---------------------------------------------------------------------------

def test_api_whatsapp_settings_owner_bisa_simpan_dan_lihat(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.put("/api/pengaturan/whatsapp", json={"fonnte_token": "token-abc"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["fonnte_token"] == "token-abc"
    assert r.json()["aktif"] is True

    r2 = client.get("/api/pengaturan/whatsapp", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["fonnte_token"] == "token-abc"
    assert r2.json()["templates"]["reminder_qris"] == ""
    assert "reminder_qris" in r2.json()["defaults"]
    assert len(r2.json()["jenis_pesan"]) == 3


def test_api_whatsapp_templates_simpan_tidak_menimpa_token(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    client.put("/api/pengaturan/whatsapp", json={"fonnte_token": "token-tetap"}, headers=headers)
    r = client.put("/api/pengaturan/whatsapp", json={"templates": {"pembatalan": "Maaf {nama}, batal ya."}},
                    headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["fonnte_token"] == "token-tetap"  # tidak ikut ter-reset
    assert r.json()["templates"]["pembatalan"] == "Maaf {nama}, batal ya."


def test_booking_pakai_template_custom_kalau_sudah_diatur(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _beri_fitur_whatsapp_reminder(tenant_id)
    whatsapp_service.set_templates({"pembatalan": "Maaf {nama}, booking {layanan} dibatalkan ya."},
                                    tenant_id=tenant_id)
    booking = _buat_booking(tenant_id, "transfer")
    panggilan = _pasang_penangkap_wa(monkeypatch)
    booking_db.batalkan_booking(booking["id"])
    assert panggilan[0]["pesan"] == f"Maaf Budi, booking {booking['daftar_service']} dibatalkan ya."


def test_api_whatsapp_settings_staff_ditolak(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import auth_db
    auth_db.tambah_user("staffwa", "passwordS123", role="staff", tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "staffwa", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}

    assert client.get("/api/pengaturan/whatsapp", headers=headers_staff).status_code == 403
    assert client.put("/api/pengaturan/whatsapp", json={"fonnte_token": "x"}, headers=headers_staff).status_code == 403


def test_api_whatsapp_tes_tanpa_token_ditolak(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.post("/api/pengaturan/whatsapp/tes", json={"nomor_tujuan": "081234567890"}, headers=headers)
    assert r.status_code == 422


def test_api_whatsapp_tes_dengan_token(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    client.put("/api/pengaturan/whatsapp", json={"fonnte_token": "token-ok"}, headers=headers)
    monkeypatch.setattr("routers.pengaturan.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    r = client.post("/api/pengaturan/whatsapp/tes", json={"nomor_tujuan": "081234567890"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_tenant_isolation_token_tidak_bocor_via_api(two_tenants):
    client = two_tenants["client"]
    headers_a, headers_b = two_tenants["headers_a"], two_tenants["headers_b"]
    client.put("/api/pengaturan/whatsapp", json={"fonnte_token": "rahasia-a"}, headers=headers_a)
    r_b = client.get("/api/pengaturan/whatsapp", headers=headers_b)
    assert r_b.json()["fonnte_token"] == ""
