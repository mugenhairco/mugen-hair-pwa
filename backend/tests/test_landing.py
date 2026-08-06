"""
test_landing.py — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
=============================================================================
Cakupan: FAQ/Testimonial publik vs Super Admin CRUD, kontak & statistik
platform, katalog paket publik, dan alur Register self-service (unik
email/whatsapp, password mismatch, tenant baru langsung terblokir status
'expired', dan #/billing tidak terpengaruh perubahan ini di sisi backend
-- akses_diblokir() TIDAK diubah sama sekali).

REVISI FITUR Verifikasi Email: register() TIDAK LAGI mengembalikan
token/auto-login (akun baru wajib verifikasi email dulu sebelum bisa
login) -- lihat tests/test_email_auth.py untuk cakupan lengkap fitur itu
sendiri, dua test di bawah (test_register_berhasil_membuat_tenant_
terblokir_sampai_bayar & test_register_login_valid_untuk_endpoint_
berlogin_setelah_verifikasi) sudah disesuaikan ke alur baru ini."""

import hashlib

import pytest

import auth_db
import billing_db
import billing_invoice_db
import billing_webhook
import database as db
import landing_db
import midtrans_client
import subscription_db
import tenant_db


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _aktifkan_midtrans_mock(monkeypatch, token="snap-token-abc", redirect="https://example.test/snap/abc"):
    monkeypatch.setattr(midtrans_client, "IS_ENABLED", True)
    monkeypatch.setattr(midtrans_client, "MIDTRANS_SERVER_KEY", "SB-Mid-server-test")
    monkeypatch.setattr(midtrans_client, "MIDTRANS_CLIENT_KEY", "SB-Mid-client-test")

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(201, {"token": token, "redirect_url": redirect})

    monkeypatch.setattr(midtrans_client.requests, "post", fake_post)


def _hitung_signature(order_id, status_code, gross_amount, server_key):
    raw = f"{order_id}{status_code}{gross_amount}{server_key}"
    return hashlib.sha512(raw.encode()).hexdigest()


def _webhook_payload(order_id, gross_amount, server_key):
    status_code = "200"
    gross_amount_str = f"{gross_amount}.00"
    return {
        "order_id": order_id,
        "status_code": status_code,
        "gross_amount": gross_amount_str,
        "transaction_status": "settlement",
        "payment_type": "bank_transfer",
        "signature_key": _hitung_signature(order_id, status_code, gross_amount_str, server_key),
    }


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _payload_register(**override):
    payload = {
        "nama_barbershop": "Barbershop Uji Coba",
        "owner_name": "Budi Santoso",
        "email": "budi@contoh.com",
        "whatsapp": "081234567890",
        "password": "rahasia123",
        "confirm_password": "rahasia123",
    }
    payload.update(override)
    return payload


# ============================= FAQ =============================

def test_faq_publik_hanya_yang_aktif(app_client):
    landing_db.create_faq("Apa itu Rivoir?", "Platform manajemen barbershop.")
    tidak_aktif = landing_db.create_faq("Pertanyaan nonaktif", "Jawaban")
    landing_db.update_faq(tidak_aktif["id"], aktif=False)

    r = app_client.get("/api/public/landing/faq")
    assert r.status_code == 200, r.text
    pertanyaan = {f["pertanyaan"] for f in r.json()}
    assert "Apa itu Rivoir?" in pertanyaan
    assert "Pertanyaan nonaktif" not in pertanyaan


def test_faq_superadmin_crud(app_client):
    headers = _buat_superadmin_dan_login(app_client)

    r = app_client.post("/api/superadmin/landing/faq", headers=headers,
                         json={"pertanyaan": "Bagaimana cara upgrade paket?", "jawaban": "Lewat halaman Billing."})
    assert r.status_code == 200, r.text
    faq_id = r.json()["id"]

    r = app_client.put(f"/api/superadmin/landing/faq/{faq_id}", headers=headers, json={"aktif": False})
    assert r.status_code == 200, r.text
    assert r.json()["aktif"] == 0

    r = app_client.delete(f"/api/superadmin/landing/faq/{faq_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert landing_db.get_faq(faq_id) is None


def test_faq_superadmin_endpoint_ditolak_akun_biasa(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/landing/faq", headers=two_tenants["headers_a"])
    assert r.status_code == 403


# ============================= Testimonial =============================

def test_testimonial_publik_hanya_yang_aktif(app_client):
    landing_db.create_testimonial("Pak Joko", "Sangat membantu operasional toko saya.")
    nonaktif = landing_db.create_testimonial("Pak Slamet", "Testimoni nonaktif")
    landing_db.update_testimonial(nonaktif["id"], aktif=False)

    r = app_client.get("/api/public/landing/testimonials")
    assert r.status_code == 200, r.text
    nama = {t["nama"] for t in r.json()}
    assert "Pak Joko" in nama
    assert "Pak Slamet" not in nama


def test_testimonial_rating_invalid_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.post("/api/superadmin/landing/testimonials", headers=headers,
                         json={"nama": "Pak Joko", "isi": "Bagus", "rating": 9})
    assert r.status_code == 422


# ============================= Kontak & Statistik =============================

def test_kontak_platform_default_kosong_lalu_bisa_diubah_superadmin(app_client):
    headers = _buat_superadmin_dan_login(app_client)

    r = app_client.get("/api/public/landing/contact")
    assert r.status_code == 200, r.text
    assert r.json()["platform_contact_whatsapp"] == ""

    r = app_client.put("/api/superadmin/landing/contact", headers=headers,
                        json={"platform_contact_whatsapp": "081200000000", "platform_contact_email": "cs@rivoir.id"})
    assert r.status_code == 200, r.text

    r = app_client.get("/api/public/landing/contact")
    assert r.json()["platform_contact_whatsapp"] == "081200000000"
    assert r.json()["platform_contact_email"] == "cs@rivoir.id"


def test_stats_publik_active_tenants_dihitung_live(two_tenants):
    # BOOT juga membuat tenant default (_bootstrap_admin_pertama()), jadi
    # jumlahnya BUKAN pas 2 -- bandingkan terhadap tenant_db langsung
    # supaya test tidak bergantung ke detail bootstrap.
    diharapkan = len(tenant_db.list_tenants())
    r = two_tenants["client"].get("/api/public/landing/stats")
    assert r.status_code == 200, r.text
    assert r.json()["active_tenants"] == diharapkan
    assert diharapkan >= 2


def test_stats_manual_diedit_superadmin(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.put("/api/superadmin/landing/stats", headers=headers,
                        json={"platform_stat_happy_customers": "500", "platform_stat_uptime": "99.9%"})
    assert r.status_code == 200, r.text

    r = app_client.get("/api/public/landing/stats")
    assert r.json()["platform_stat_happy_customers"] == "500"
    assert r.json()["platform_stat_uptime"] == "99.9%"


# ============================= Katalog paket publik =============================

def test_packages_publik_hanya_aktif_dan_bawa_fitur(app_client):
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], aktif=False)

    r = app_client.get("/api/public/landing/packages")
    assert r.status_code == 200, r.text
    kode = {p["kode"] for p in r.json()}
    assert "pro" not in kode
    assert "fitur" in r.json()[0]


# ============================= Register self-service =============================

def test_register_berhasil_membuat_tenant_terblokir_sampai_bayar(app_client):
    # REVISI FITUR Verifikasi Email: register() TIDAK LAGI mengembalikan
    # token/user/tenant langsung (akun baru wajib verifikasi email dulu
    # sebelum bisa login sama sekali -- lihat routers/tenant_registration.py
    # & tests/test_email_auth.py untuk cakupan lengkap fitur itu) -- test
    # ini tetap memverifikasi bagian yang TIDAK berubah: tenant + subscription
    # 'expired' langsung terbentuk saat register, diambil lewat tenant_db
    # (bukan dari body respons lagi).
    r = app_client.post("/api/public/registration/register", json=_payload_register())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["registered"] is True
    assert body["email"] == "budi@contoh.com"

    tenant = tenant_db.get_tenant_by_email("budi@contoh.com")
    assert tenant is not None
    tenant_id = tenant["id"]

    sub = subscription_db.get_subscription(tenant_id)
    assert sub["status"] == "expired"
    assert subscription_db.akses_diblokir(tenant_id) is True

    assert tenant["email"] == "budi@contoh.com"
    assert tenant["whatsapp"] == "081234567890"
    assert tenant["owner_name"] == "Budi Santoso"


def test_register_login_valid_untuk_endpoint_berlogin_setelah_verifikasi(app_client):
    """REVISI: login (dan token yang dihasilkannya) HANYA tersedia SETELAH
    email diverifikasi -- lihat tests/test_email_auth.py untuk cakupan
    lengkap gerbang verifikasi itu sendiri, test ini murni memastikan token
    HASIL login (setelah verifikasi) tetap valid dipakai endpoint lain
    (/api/subscription/me), SAMA seperti sebelum fitur verifikasi ada."""
    import email_auth_db

    app_client.post("/api/public/registration/register", json=_payload_register())
    user = email_auth_db.get_user_by_email("budi@contoh.com")
    with db.get_conn() as conn:
        token_verifikasi = conn.execute(
            "SELECT token FROM email_verification_tokens WHERE user_id = ?", (user["id"],)
        ).fetchone()["token"]
    app_client.post("/api/auth/verifikasi-email", json={"token": token_verifikasi})

    r = app_client.post("/api/auth/login", json={"username": "budi@contoh.com", "password": "rahasia123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    r2 = app_client.get("/api/subscription/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "expired"


def test_register_email_duplikat_ditolak(app_client):
    app_client.post("/api/public/registration/register", json=_payload_register())
    r = app_client.post("/api/public/registration/register",
                         json=_payload_register(whatsapp="089999999999", nama_barbershop="Toko Lain"))
    assert r.status_code == 422
    assert "email" in r.json()["detail"].lower()


def test_register_whatsapp_duplikat_ditolak(app_client):
    app_client.post("/api/public/registration/register", json=_payload_register())
    r = app_client.post("/api/public/registration/register",
                         json=_payload_register(email="lain@contoh.com", nama_barbershop="Toko Lain"))
    assert r.status_code == 422
    assert "whatsapp" in r.json()["detail"].lower()


def test_register_password_tidak_cocok_ditolak(app_client):
    r = app_client.post("/api/public/registration/register",
                         json=_payload_register(confirm_password="beda123"))
    assert r.status_code == 422
    # REGRESI: detail HARUS string polos yang bisa ditampilkan apa adanya di
    # register.js -- sebelumnya divalidasi lewat Pydantic model_validator,
    # yang membungkus ValueError jadi ARRAY objek error FastAPI (bukan
    # string), membuat frontend menampilkan "[object Object]".
    assert isinstance(r.json()["detail"], str)
    assert "cocok" in r.json()["detail"].lower()


def test_register_email_format_invalid_ditolak(app_client):
    r = app_client.post("/api/public/registration/register", json=_payload_register(email="bukan-email"))
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert "email" in r.json()["detail"].lower()


def test_register_password_terlalu_pendek_ditolak_tanpa_tenant_yatim(app_client):
    r = app_client.post("/api/public/registration/register",
                         json=_payload_register(password="abc", confirm_password="abc"))
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert "4 karakter" in r.json()["detail"]
    # Tenant TIDAK boleh terlanjur dibuat -- dicek SEBELUM tenant_db.buat_tenant().
    assert tenant_db.get_tenant_by_email("budi@contoh.com") is None


def test_register_field_kosong_ditolak_dengan_pesan_string(app_client):
    for field, pesan in [("nama_barbershop", "barbershop"), ("owner_name", "owner"), ("whatsapp", "whatsapp")]:
        r = app_client.post("/api/public/registration/register", json=_payload_register(**{field: ""}))
        assert r.status_code == 422, field
        assert isinstance(r.json()["detail"], str), field


def test_register_slug_otomatis_dan_unik_kalau_nama_sama(app_client):
    app_client.post("/api/public/registration/register", json=_payload_register())
    r2 = app_client.post("/api/public/registration/register",
                          json=_payload_register(email="lain2@contoh.com", whatsapp="081111111111"))
    assert r2.status_code == 200, r2.text
    tenant1 = tenant_db.get_tenant_by_email("budi@contoh.com")
    tenant2 = tenant_db.get_tenant_by_email("lain2@contoh.com")
    assert tenant1["slug"] != tenant2["slug"]


# ============================= FITUR Subdomain Otomatis per Tenant =============================
# Slug hasil registrasi mandiri LANGSUNG dipakai sebagai subdomain
# (<slug>.rivoirsett.com, lihat tenant_middleware.py) -- spesifikasi
# produk eksplisit minta TANPA pemisah apa pun (bukan lagi "mugen-hair-co"
# gaya lama), dengan angka collision menempel langsung.

def test_register_slug_sesuai_contoh_spesifikasi_tanpa_pemisah(app_client):
    r = app_client.post("/api/public/registration/register",
                         json=_payload_register(nama_barbershop="MUGEN Hair Co.", email="mugen@contoh.com"))
    assert r.status_code == 200, r.text
    tenant = tenant_db.get_tenant_by_email("mugen@contoh.com")
    assert tenant["slug"] == "mugenhairco"

    r2 = app_client.post("/api/public/registration/register",
                          json=_payload_register(nama_barbershop="Bubble Shot", email="bubble@contoh.com",
                                                  whatsapp="081199999999"))
    assert r2.status_code == 200, r2.text
    tenant2 = tenant_db.get_tenant_by_email("bubble@contoh.com")
    assert tenant2["slug"] == "bubbleshot"


def test_register_slug_collision_pakai_angka_tanpa_pemisah(app_client):
    r1 = app_client.post("/api/public/registration/register",
                          json=_payload_register(nama_barbershop="MUGEN Hair Co.", email="satu@contoh.com"))
    assert r1.status_code == 200, r1.text
    r2 = app_client.post("/api/public/registration/register",
                          json=_payload_register(nama_barbershop="MUGEN Hair Co.", email="dua@contoh.com",
                                                  whatsapp="081188888888"))
    assert r2.status_code == 200, r2.text
    r3 = app_client.post("/api/public/registration/register",
                          json=_payload_register(nama_barbershop="MUGEN Hair Co.", email="tiga@contoh.com",
                                                  whatsapp="081177777777"))
    assert r3.status_code == 200, r3.text

    slug1 = tenant_db.get_tenant_by_email("satu@contoh.com")["slug"]
    slug2 = tenant_db.get_tenant_by_email("dua@contoh.com")["slug"]
    slug3 = tenant_db.get_tenant_by_email("tiga@contoh.com")["slug"]
    assert slug1 == "mugenhairco"
    assert slug2 == "mugenhairco2"
    assert slug3 == "mugenhairco3"


def test_register_nama_toko_admin_tidak_kebagian_slug_reservasi(app_client):
    """Barbershop bernama persis "Admin" TIDAK PERNAH boleh kebagian slug
    "admin" -- subdomain itu HARUS selalu berarti Dashboard Super Admin
    (item 8 spesifikasi), tidak pernah tenant mana pun."""
    r = app_client.post("/api/public/registration/register",
                         json=_payload_register(nama_barbershop="Admin", email="admin-toko@contoh.com"))
    assert r.status_code == 200, r.text
    tenant = tenant_db.get_tenant_by_email("admin-toko@contoh.com")
    assert tenant["slug"] != "admin"
    assert tenant["slug"] == "admin2"


def test_buat_tenant_manual_menolak_slug_reservasi(app_client):
    """Provisioning manual Super Admin (routers/superadmin.py) memakai
    tenant_db.buat_tenant() yang SAMA -- reservasi ditegakkan di SATU
    titik ini, jadi berlaku untuk KEDUA jalur pembuatan tenant."""
    with pytest.raises(ValueError):
        tenant_db.buat_tenant("admin", "Toko Nakal")
    with pytest.raises(ValueError):
        tenant_db.buat_tenant("www", "Toko Nakal Lagi")


def test_register_tercatat_di_audit_log(app_client):
    import superadmin_audit_db
    app_client.post("/api/public/registration/register", json=_payload_register())
    log = superadmin_audit_db.list_log()
    assert any(l["aksi"] == "registrasi_publik" for l in log)


# ============================= Integrasi penuh: Register -> Checkout -> Webhook =============================
# Jalur PALING PENTING di Phase 5 -- membuktikan tenant self-service BENAR-
# BENAR bisa keluar dari status 'expired' (diblokir) lewat checkout Midtrans
# Phase 4 yang TIDAK diubah sama sekali, sampai ke webhook yang TIDAK diubah
# sama sekali juga.

def test_register_checkout_webhook_end_to_end_mengaktifkan_tenant(app_client, monkeypatch):
    import email_auth_db

    _aktifkan_midtrans_mock(monkeypatch)

    r = app_client.post("/api/public/registration/register", json=_payload_register())
    assert r.status_code == 200, r.text
    # REVISI FITUR Verifikasi Email: register() TIDAK LAGI auto-login --
    # verifikasi dulu (lihat tests/test_email_auth.py untuk cakupan lengkap
    # gerbang ini sendiri), baru login normal, SEBELUM lanjut ke Checkout/
    # Webhook (yang TIDAK diubah sama sekali, sesuai instruksi eksplisit).
    user = email_auth_db.get_user_by_email("budi@contoh.com")
    with db.get_conn() as conn:
        token_verifikasi = conn.execute(
            "SELECT token FROM email_verification_tokens WHERE user_id = ?", (user["id"],)
        ).fetchone()["token"]
    app_client.post("/api/auth/verifikasi-email", json={"token": token_verifikasi})

    r_login = app_client.post("/api/auth/login", json={"username": "budi@contoh.com", "password": "rahasia123"})
    assert r_login.status_code == 200, r_login.text
    login_body = r_login.json()
    token = login_body["token"]
    tenant_id = login_body["tenant"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Sebelum bayar: diblokir, sama seperti yang router.js baca lewat
    # /api/subscription/status.
    r = app_client.get("/api/subscription/status", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["akses_diblokir"] is True

    pro = billing_db.get_package_by_kode("pro")
    r = app_client.post("/api/billing/checkout", headers=headers, json={"package_id": pro["id"]})
    assert r.status_code == 200, r.text
    invoice = r.json()

    # Webhook Midtrans (TIDAK DIUBAH SAMA SEKALI) memproses notifikasi paid.
    payload = _webhook_payload(invoice["order_id"], invoice["jumlah"], midtrans_client.MIDTRANS_SERVER_KEY)
    hasil = billing_webhook.proses_notifikasi(payload)
    assert hasil["status"] == "paid"

    sub = subscription_db.get_subscription(tenant_id)
    assert sub["status"] == "active"
    assert sub["package"] == "pro"
    assert subscription_db.akses_diblokir(tenant_id) is False

    # Setelah bayar: #/billing (dan seluruh endpoint lain) tidak lagi
    # dianggap diblokir dari sisi backend.
    r = app_client.get("/api/subscription/status", headers=headers)
    assert r.json()["akses_diblokir"] is False
