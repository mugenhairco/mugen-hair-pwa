"""
test_landing.py — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
=============================================================================
Cakupan: FAQ/Testimonial publik vs Super Admin CRUD, kontak & statistik
platform, katalog paket publik, dan alur Register self-service (unik
email/whatsapp, password mismatch, tenant baru langsung terblokir status
'expired', token langsung bisa dipakai login, dan #/billing tidak
terpengaruh perubahan ini di sisi backend -- akses_diblokir() TIDAK
diubah sama sekali)."""

import auth_db
import billing_db
import landing_db
import subscription_db
import tenant_db


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
    r = app_client.post("/api/public/registration/register", json=_payload_register())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["role"] == "admin"
    assert "password_hash" not in body["user"]
    tenant_id = body["tenant"]["id"]

    sub = subscription_db.get_subscription(tenant_id)
    assert sub["status"] == "expired"
    assert subscription_db.akses_diblokir(tenant_id) is True

    tenant = tenant_db.get_tenant(tenant_id)
    assert tenant["email"] == "budi@contoh.com"
    assert tenant["whatsapp"] == "081234567890"
    assert tenant["owner_name"] == "Budi Santoso"


def test_register_token_langsung_valid_untuk_endpoint_berlogin(app_client):
    r = app_client.post("/api/public/registration/register", json=_payload_register())
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


def test_register_email_format_invalid_ditolak(app_client):
    r = app_client.post("/api/public/registration/register", json=_payload_register(email="bukan-email"))
    assert r.status_code == 422


def test_register_slug_otomatis_dan_unik_kalau_nama_sama(app_client):
    app_client.post("/api/public/registration/register", json=_payload_register())
    r2 = app_client.post("/api/public/registration/register",
                          json=_payload_register(email="lain2@contoh.com", whatsapp="081111111111"))
    assert r2.status_code == 200, r2.text
    tenant1 = tenant_db.get_tenant_by_email("budi@contoh.com")
    tenant2 = tenant_db.get_tenant_by_email("lain2@contoh.com")
    assert tenant1["slug"] != tenant2["slug"]


def test_register_tercatat_di_audit_log(app_client):
    import superadmin_audit_db
    app_client.post("/api/public/registration/register", json=_payload_register())
    log = superadmin_audit_db.list_log()
    assert any(l["aksi"] == "registrasi_publik" for l in log)
