"""
test_sales.py — Program Afiliasi Sales/Marketing (sales_db.py, routers/sales.py)
=============================================================================
Cakupan: Super Admin merekrut akun sales + kode referral (persentase komisi
fleksibel), tenant mendaftar sendiri lewat kode referral (opsional, kode
tidak dikenal diabaikan diam-diam), komisi otomatis saat pembayaran
langganan ditandai lunas (baru 1x vs repeat berkelanjutan), transaksi
Lisensi Lifetime manual oleh Super Admin (upgrade subscription + komisi
otomatis), Portal Sales read-only (terisolasi -- hanya melihat kode/
tenant/komisi miliknya sendiri), dan batas akses role 'sales' (tidak bisa
masuk endpoint tenant-scope maupun endpoint khusus Super Admin)."""

import pytest

import auth_db
import sales_db
import subscription_db
import tenant_db


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    return _login(client, username, password)


def _buat_sales_via_api(client, headers_superadmin, username="sales1", password="passwordsales1",
                         nama_sales="Budi Sales", kode="PROMO10", **persen):
    body = {"username": username, "password": password, "nama_sales": nama_sales, "kode": kode}
    body.update(persen)
    r = client.post("/api/superadmin/sales/akun", headers=headers_superadmin, json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ============================= Role 'sales': validasi dasar =============================

def test_role_sales_wajib_tenant_id_none(app_client):
    with pytest.raises(ValueError):
        auth_db.tambah_user("sales_salah", "password1234", "sales", tenant_id=1)


def test_buat_akun_sales_sekaligus_kode_referral(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    assert kode["kode"] == "PROMO10"
    assert kode["komisi_persen_baru"] == 50
    assert kode["komisi_persen_repeat"] == 20
    assert kode["komisi_persen_lifetime"] == 30
    assert kode["aktif"] == 1

    # akun login sungguhan terbentuk, role='sales', tenant_id None
    user = auth_db.get_user_by_username("sales1")
    assert user["role"] == "sales"
    assert user["tenant_id"] is None


def test_kode_referral_duplikat_ditolak_dan_akun_tidak_menggantung(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    _buat_sales_via_api(app_client, headers, username="sales1", kode="SAMA")
    r = app_client.post("/api/superadmin/sales/akun", headers=headers, json={
        "username": "sales2", "password": "password1234", "nama_sales": "Sales Lain", "kode": "SAMA",
    })
    assert r.status_code == 422
    # akun login 'sales2' TIDAK boleh menggantung tanpa kode referral
    assert auth_db.get_user_by_username("sales2") is None


def test_ubah_persentase_komisi_fleksibel(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    r = app_client.put(f"/api/superadmin/sales/kode-referral/{kode['id']}", headers=headers, json={
        "komisi_persen_baru": 70, "komisi_persen_repeat": 25, "komisi_persen_lifetime": 35,
    })
    assert r.status_code == 200, r.text
    hasil = r.json()
    assert hasil["komisi_persen_baru"] == 70
    assert hasil["komisi_persen_repeat"] == 25
    assert hasil["komisi_persen_lifetime"] == 35


def test_persentase_komisi_di_luar_0_100_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    r = app_client.put(f"/api/superadmin/sales/kode-referral/{kode['id']}", headers=headers,
                        json={"komisi_persen_baru": 150})
    assert r.status_code == 422


# ============================= Atribusi tenant: pendaftaran mandiri =============================

def test_registrasi_tenant_dengan_kode_referral_valid(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)

    r = app_client.post("/api/public/registration/register", json={
        "nama_barbershop": "Barbershop Referral", "owner_name": "Owner Baru",
        "username": "ownerreferral", "email": "owner.referral@example.com",
        "whatsapp": "081234567890", "password": "passwordowner123",
        "confirm_password": "passwordowner123", "referral_code": "promo10",  # lowercase, harus dinormalisasi
    })
    assert r.status_code == 200, r.text
    # Cari tenant yang baru dibuat lewat username Owner-nya
    user = auth_db.get_user_by_username("ownerreferral")
    assert user is not None
    assert sales_db.get_tenant_referral_code_id(user["tenant_id"]) == kode["id"]


def test_registrasi_tenant_kode_referral_tidak_dikenal_diabaikan(app_client):
    r = app_client.post("/api/public/registration/register", json={
        "nama_barbershop": "Barbershop Tanpa Referral", "owner_name": "Owner Lain",
        "username": "ownertanparef", "email": "owner.tanpa@example.com",
        "whatsapp": "081234567891", "password": "passwordowner123",
        "confirm_password": "passwordowner123", "referral_code": "KODE-TIDAK-ADA",
    })
    assert r.status_code == 200, r.text
    user = auth_db.get_user_by_username("ownertanparef")
    assert sales_db.get_tenant_referral_code_id(user["tenant_id"]) is None


def test_superadmin_tempel_referral_manual_ke_tenant(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")

    r = app_client.put(f"/api/superadmin/sales/tenant/{tenant['id']}/referral", headers=headers,
                        json={"referral_code_id": kode["id"]})
    assert r.status_code == 200, r.text
    assert sales_db.get_tenant_referral_code_id(tenant["id"]) == kode["id"]

    # lepas lagi (null)
    r2 = app_client.put(f"/api/superadmin/sales/tenant/{tenant['id']}/referral", headers=headers,
                         json={"referral_code_id": None})
    assert r2.status_code == 200
    assert sales_db.get_tenant_referral_code_id(tenant["id"]) is None


# ============================= Komisi otomatis: Langganan =============================

def test_komisi_otomatis_baru_lalu_repeat_selamanya(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    sales_db.set_tenant_referral(tenant["id"], kode["id"])

    # Pembayaran pertama -> jenis 'baru', 50%
    r1 = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "VA001", "amount": 188000,
    })
    payment1 = r1.json()
    app_client.put(f"/api/superadmin/subscriptions/payments/{payment1['id']}/status",
                    headers=headers, json={"payment_status": "paid"})

    komisi = sales_db.list_komisi_by_referral_code(kode["id"])
    assert len(komisi) == 1
    assert komisi[0]["jenis"] == "baru"
    assert komisi[0]["nominal_komisi"] == 94000  # 50% dari 188000

    # Pembayaran kedua (perpanjangan) -> jenis 'repeat', 20%
    r2 = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "VA002", "amount": 188000,
    })
    payment2 = r2.json()
    app_client.put(f"/api/superadmin/subscriptions/payments/{payment2['id']}/status",
                    headers=headers, json={"payment_status": "paid"})

    komisi = sales_db.list_komisi_by_referral_code(kode["id"])
    assert len(komisi) == 2
    assert komisi[0]["jenis"] == "repeat"  # terbaru di depan (ORDER BY id DESC)
    assert komisi[0]["nominal_komisi"] == 37600  # 20% dari 188000

    # Perpanjangan KETIGA -> tetap 'repeat' (komisi residual SELAMANYA, bukan hanya sekali)
    r3 = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "VA003", "amount": 188000,
    })
    payment3 = r3.json()
    app_client.put(f"/api/superadmin/subscriptions/payments/{payment3['id']}/status",
                    headers=headers, json={"payment_status": "paid"})
    komisi = sales_db.list_komisi_by_referral_code(kode["id"])
    assert len(komisi) == 3
    assert komisi[0]["jenis"] == "repeat"


def test_tanpa_referral_tidak_ada_komisi_dicatat(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    assert sales_db.get_tenant_referral_code_id(tenant["id"]) is None

    r1 = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "VA001", "amount": 188000,
    })
    payment1 = r1.json()
    app_client.put(f"/api/superadmin/subscriptions/payments/{payment1['id']}/status",
                    headers=headers, json={"payment_status": "paid"})
    assert sales_db.list_komisi_semua() == []


def test_komisi_tidak_duplikat_kalau_status_paid_ditandai_dua_kali(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    sales_db.set_tenant_referral(tenant["id"], kode["id"])

    r1 = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "VA001", "amount": 188000,
    })
    payment1 = r1.json()
    for _ in range(2):
        r = app_client.put(f"/api/superadmin/subscriptions/payments/{payment1['id']}/status",
                            headers=headers, json={"payment_status": "paid"})
        assert r.status_code == 200
    assert len(sales_db.list_komisi_semua()) == 1


# ============================= Lisensi Lifetime (Beli Putus) =============================

def test_lifetime_purchase_upgrade_tenant_dan_catat_komisi(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")

    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "enterprise", "amount": 20000000,
        "provider": "faspay", "virtual_account_number": "VA-LIFETIME-1",
        "referral_code_id": kode["id"],
    })
    assert r.status_code == 200, r.text
    purchase = r.json()
    assert purchase["payment_status"] == "pending"

    r2 = app_client.put(f"/api/superadmin/sales/lifetime/{purchase['id']}/status", headers=headers,
                         json={"payment_status": "paid"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["payment_status"] == "paid"

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["status"] == "lifetime"
    assert sub["package"] == "enterprise"
    assert subscription_db.akses_diblokir(tenant["id"]) is False

    komisi = sales_db.list_komisi_by_referral_code(kode["id"])
    assert len(komisi) == 1
    assert komisi[0]["jenis"] == "lifetime"
    assert komisi[0]["nominal_komisi"] == 6000000  # 30% dari 20jt


def test_lifetime_purchase_tanpa_referral_tidak_catat_komisi(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "basic", "amount": 15000000,
        "provider": "faspay", "virtual_account_number": "VA-LIFETIME-2",
    })
    purchase = r.json()
    app_client.put(f"/api/superadmin/sales/lifetime/{purchase['id']}/status", headers=headers,
                    json={"payment_status": "paid"})
    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["status"] == "lifetime"
    assert sales_db.list_komisi_semua() == []


def test_lifetime_package_kode_tidak_valid_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "free", "amount": 1000000,
        "provider": "faspay", "virtual_account_number": "VA-X",
    })
    assert r.status_code == 422


# ============================= Komisi: toggle status bayar =============================

def test_superadmin_tandai_komisi_sudah_dibayar(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    sales_db.set_tenant_referral(tenant["id"], kode["id"])
    r1 = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "VA001", "amount": 188000,
    })
    payment1 = r1.json()
    app_client.put(f"/api/superadmin/subscriptions/payments/{payment1['id']}/status",
                    headers=headers, json={"payment_status": "paid"})
    komisi = sales_db.list_komisi_by_referral_code(kode["id"])[0]

    r = app_client.put(f"/api/superadmin/sales/komisi/{komisi['id']}/status", headers=headers,
                        json={"status": "sudah_dibayar"})
    assert r.status_code == 200, r.text
    hasil = r.json()
    assert hasil["status"] == "sudah_dibayar"
    assert hasil["dibayar_at"] is not None
    assert hasil["kode_referral"] == kode["kode"]
    assert hasil["nama_tenant"] == tenant["nama_barbershop"]


def test_komisi_status_tidak_valid_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    sales_db.set_tenant_referral(tenant["id"], kode["id"])
    r1 = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "VA001", "amount": 188000,
    })
    payment1 = r1.json()
    app_client.put(f"/api/superadmin/subscriptions/payments/{payment1['id']}/status",
                    headers=headers, json={"payment_status": "paid"})
    komisi = sales_db.list_komisi_by_referral_code(kode["id"])[0]
    r = app_client.put(f"/api/superadmin/sales/komisi/{komisi['id']}/status", headers=headers,
                        json={"status": "lunas_sebagian"})
    assert r.status_code == 422


# ============================= Portal Sales (read-only, milik sendiri) =============================

def test_sales_lihat_kode_dan_tenant_dan_komisi_miliknya(app_client):
    headers_sa = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers_sa)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    sales_db.set_tenant_referral(tenant["id"], kode["id"])

    r1 = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers_sa, json={
        "provider": "BCA", "virtual_account_number": "VA001", "amount": 188000,
    })
    payment1 = r1.json()
    app_client.put(f"/api/superadmin/subscriptions/payments/{payment1['id']}/status",
                    headers=headers_sa, json={"payment_status": "paid"})

    headers_sales = _login(app_client, "sales1", "passwordsales1")

    r_me = app_client.get("/api/sales/me", headers=headers_sales)
    assert r_me.status_code == 200, r_me.text
    assert r_me.json()["kode"] == "PROMO10"

    r_tenants = app_client.get("/api/sales/me/tenants", headers=headers_sales)
    assert r_tenants.status_code == 200
    daftar = r_tenants.json()
    assert len(daftar) == 1
    assert daftar[0]["tenant_id"] == tenant["id"]
    assert daftar[0]["status"] == "active"

    r_komisi = app_client.get("/api/sales/me/komisi", headers=headers_sales)
    assert r_komisi.status_code == 200
    hasil = r_komisi.json()
    assert len(hasil["komisi"]) == 1
    assert hasil["total_belum_dibayar"] == 94000
    assert hasil["total_sudah_dibayar"] == 0


def test_sales_tanpa_kode_referral_dapat_404(app_client):
    auth_db.tambah_user("sales_yatim", "password1234", "sales", tenant_id=None)
    headers = _login(app_client, "sales_yatim", "password1234")
    r = app_client.get("/api/sales/me", headers=headers)
    assert r.status_code == 404


# ============================= Batas akses role 'sales' =============================

def test_sales_tidak_bisa_akses_endpoint_tenant_scope(app_client):
    headers_sa = _buat_superadmin_dan_login(app_client)
    _buat_sales_via_api(app_client, headers_sa)
    headers_sales = _login(app_client, "sales1", "passwordsales1")

    r = app_client.get("/api/dashboard/owner", headers=headers_sales)
    assert r.status_code == 403


def test_sales_tidak_bisa_akses_endpoint_superadmin(app_client):
    headers_sa = _buat_superadmin_dan_login(app_client)
    _buat_sales_via_api(app_client, headers_sa)
    headers_sales = _login(app_client, "sales1", "passwordsales1")

    r = app_client.get("/api/superadmin/sales/kode-referral", headers=headers_sales)
    assert r.status_code == 403
    r2 = app_client.get("/api/superadmin/tenants", headers=headers_sales)
    assert r2.status_code == 403


def test_superadmin_tidak_bisa_akses_portal_sales(app_client):
    headers_sa = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/sales/me", headers=headers_sa)
    assert r.status_code == 403


def test_owner_tenant_tidak_bisa_akses_portal_sales_maupun_superadmin_sales(two_tenants):
    r = two_tenants["client"].get("/api/sales/me", headers=two_tenants["headers_a"])
    assert r.status_code == 403
    r2 = two_tenants["client"].get("/api/superadmin/sales/kode-referral", headers=two_tenants["headers_a"])
    assert r2.status_code == 403
