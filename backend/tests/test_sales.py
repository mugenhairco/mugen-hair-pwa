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
import billing_db
import gateway_client_base
import payment_provider_client
import sales_db
import snap_advance_db
import snap_payment_db
import snap_webhook
import subscription_db
import tenant_db
from database import get_conn


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    return _login(client, username, password)


# Migrasi Faspay SNAP Advance: transaksi Lisensi Lifetime SEKARANG lewat
# gateway NYATA yang SAMA dipakai checkout langganan biasa -- pola mock
# SAMA PERSIS test_billing_checkout.py::_aktifkan_snap_billing() (TIDAK
# PERNAH memanggil provider sungguhan).
def _aktifkan_snap_lifetime(monkeypatch, va_number="70299999999999", gagal=False):
    snap_advance_db.update_config(
        merchant_id="37070", partner_id="37070", channel_id="77001", va_bank_aktif=["702"],
        sandbox_private_key="-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----",
        channel_aktif=["va", "qris"],
    )

    def _hasil(*a, **kw):
        if gagal:
            raise gateway_client_base.GatewayTimeoutError("Provider timeout.")
        return {"va_number": va_number, "provider_transaction_id": "trx-lifetime-1",
                "expired_at": "2026-01-01T23:59:59+07:00", "provider_response": "{}"}
    monkeypatch.setattr(payment_provider_client, "buat_transaksi", _hasil)


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
# REVISI (desain awal keliru -- Faspay tidak punya dashboard manusia untuk
# membuat VA, VA hanya bisa dibuat lewat API): transaksi Lifetime SEKARANG
# lewat gateway SNAP Advance NYATA yang SAMA dipakai checkout langganan
# biasa (mock payment_provider_client.buat_transaksi(), lihat
# _aktifkan_snap_lifetime() di atas) -- status lunas ditentukan webhook
# (snap_webhook.terapkan_status_transaksi(), SAMA fungsi dipakai
# routers/snap_advance.py), BUKAN lagi PUT /lifetime/{id}/status manual.

def test_lifetime_purchase_bayar_lewat_snap_lalu_webhook_upgrade_tenant_dan_catat_komisi(app_client, monkeypatch):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _aktifkan_snap_lifetime(monkeypatch, va_number="70211112222")

    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "enterprise", "amount": 20000000,
        "channel": "va", "bank_code": "702", "referral_code_id": kode["id"],
    })
    assert r.status_code == 200, r.text
    purchase = r.json()
    assert purchase["payment_status"] == "pending"
    assert purchase["channel"] == "va"
    assert purchase["va_number"] == "70211112222"

    transaksi = snap_payment_db.get_transaksi_terkini_untuk_lifetime_purchase(purchase["id"])
    assert transaksi["transaction_type"] == snap_payment_db.TRANSACTION_TYPE_LIFETIME_LICENSE
    hasil = snap_webhook.terapkan_status_transaksi(transaksi, "PAID", sumber="webhook")
    assert hasil["status"] == "PAID"

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["status"] == "lifetime"
    assert sub["package"] == "enterprise"
    assert subscription_db.akses_diblokir(tenant["id"]) is False

    komisi = sales_db.list_komisi_by_referral_code(kode["id"])
    assert len(komisi) == 1
    assert komisi[0]["jenis"] == "lifetime"
    assert komisi[0]["nominal_komisi"] == 6000000  # 30% dari 20jt


def test_lifetime_purchase_tanpa_referral_tidak_catat_komisi(app_client, monkeypatch):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _aktifkan_snap_lifetime(monkeypatch)
    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "basic", "amount": 15000000,
        "channel": "va", "bank_code": "702",
    })
    purchase = r.json()
    transaksi = snap_payment_db.get_transaksi_terkini_untuk_lifetime_purchase(purchase["id"])
    snap_webhook.terapkan_status_transaksi(transaksi, "PAID", sumber="webhook")
    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["status"] == "lifetime"
    assert sales_db.list_komisi_semua() == []


def test_lifetime_amount_otomatis_dari_katalog_harga_lifetime(app_client, monkeypatch):
    """Nominal boleh dikosongkan -- diisi otomatis dari
    subscription_packages.harga_lifetime (lihat billing_db.py)."""
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], harga_lifetime=17000000)
    _aktifkan_snap_lifetime(monkeypatch)

    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "pro", "channel": "va", "bank_code": "702",
    })
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 17000000


def test_lifetime_amount_kosong_tanpa_katalog_harga_lifetime_ditolak(app_client, monkeypatch):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _aktifkan_snap_lifetime(monkeypatch)
    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "basic", "channel": "va", "bank_code": "702",
    })
    assert r.status_code == 422


def test_lifetime_package_kode_tidak_valid_ditolak(app_client, monkeypatch):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _aktifkan_snap_lifetime(monkeypatch)
    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "free", "amount": 1000000,
        "channel": "va", "bank_code": "702",
    })
    assert r.status_code == 422


def test_lifetime_gateway_gagal_menandai_transaksi_failed(app_client, monkeypatch):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _aktifkan_snap_lifetime(monkeypatch, gagal=True)
    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "basic", "amount": 15000000,
        "channel": "va", "bank_code": "702",
    })
    assert r.status_code == 502, r.text
    purchase = sales_db.list_lifetime_purchases(tenant_id=tenant["id"])[0]
    assert purchase["payment_status"] == "failed"
    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["status"] != "lifetime"


def test_lifetime_status_manual_override_tetap_tersedia(app_client, monkeypatch):
    """Endpoint PUT /lifetime/{id}/status DIPERTAHANKAN untuk koreksi
    manual (mis. tenant membayar lewat jalur lain di luar gateway) --
    TIDAK dihapus walau status lunas sekarang normalnya otomatis lewat
    webhook."""
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _aktifkan_snap_lifetime(monkeypatch)
    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers, json={
        "tenant_id": tenant["id"], "package_kode": "basic", "amount": 15000000,
        "channel": "va", "bank_code": "702",
    })
    purchase = r.json()
    r2 = app_client.put(f"/api/superadmin/sales/lifetime/{purchase['id']}/status", headers=headers,
                         json={"payment_status": "paid"})
    assert r2.status_code == 200, r2.text
    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["status"] == "lifetime"


def test_lifetime_batalkan_hilang_dari_billing_tenant_dan_snap_ikut_dibatalkan(app_client, monkeypatch):
    headers_sa = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    auth_db.tambah_user("owner_batal_lifetime", "passwordowner123", "admin", tenant_id=tenant["id"])
    headers_owner = _login(app_client, "owner_batal_lifetime", "passwordowner123")
    _aktifkan_snap_lifetime(monkeypatch)

    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers_sa, json={
        "tenant_id": tenant["id"], "package_kode": "basic", "amount": 15000000,
        "channel": "va", "bank_code": "702",
    })
    purchase = r.json()
    assert app_client.get("/api/billing/lifetime-pending", headers=headers_owner).json()["id"] == purchase["id"]

    r2 = app_client.put(f"/api/superadmin/sales/lifetime/{purchase['id']}/status", headers=headers_sa,
                         json={"payment_status": "cancelled"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["payment_status"] == "cancelled"

    # Hilang dari halaman Billing tenant.
    assert app_client.get("/api/billing/lifetime-pending", headers=headers_owner).json() is None

    # Transaksi SNAP terkait ikut dibatalkan (BUKAN masih menggantung di CREATED/PENDING).
    transaksi = snap_payment_db.get_transaksi_terkini_untuk_lifetime_purchase(purchase["id"])
    assert transaksi["status"] == "CANCELLED"


def test_lifetime_dibatalkan_tidak_bisa_diaktifkan_ulang_webhook_telat(app_client, monkeypatch):
    """Guard idempotency sales_db.PAYMENT_STATUS_FINAL -- status final TIDAK
    bisa ditimpa lagi, termasuk oleh webhook SNAP yang telat datang SETELAH
    Super Admin membatalkan transaksinya."""
    headers_sa = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _aktifkan_snap_lifetime(monkeypatch)
    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers_sa, json={
        "tenant_id": tenant["id"], "package_kode": "basic", "amount": 15000000,
        "channel": "va", "bank_code": "702",
    })
    purchase = r.json()
    app_client.put(f"/api/superadmin/sales/lifetime/{purchase['id']}/status", headers=headers_sa,
                    json={"payment_status": "cancelled"})

    # Webhook telat yang MASIH mencoba menandai PAID, dipanggil LANGSUNG di
    # layer sales_db supaya menguji guard PAYMENT_STATUS_FINAL-nya sendiri,
    # terpisah dari guard STATUS_FINAL milik snap_payment_db yang sudah
    # menghalangi di layer gateway.
    hasil = sales_db.tandai_status_lifetime(purchase["id"], "paid")
    assert hasil["payment_status"] == "cancelled"
    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["status"] != "lifetime"


# ============================= Billing tenant: tampilkan Lifetime pending =============================

def test_billing_lifetime_pending_tampil_lalu_hilang_setelah_lunas(app_client, monkeypatch):
    headers_sa = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    auth_db.tambah_user("owner_lifetime", "passwordowner123", "admin", tenant_id=tenant["id"])
    headers_owner = _login(app_client, "owner_lifetime", "passwordowner123")
    _aktifkan_snap_lifetime(monkeypatch, va_number="70233334444")

    r_belum = app_client.get("/api/billing/lifetime-pending", headers=headers_owner)
    assert r_belum.status_code == 200
    assert r_belum.json() is None

    r = app_client.post("/api/superadmin/sales/lifetime", headers=headers_sa, json={
        "tenant_id": tenant["id"], "package_kode": "basic", "amount": 15000000,
        "channel": "va", "bank_code": "702",
    })
    purchase = r.json()

    r_pending = app_client.get("/api/billing/lifetime-pending", headers=headers_owner)
    assert r_pending.status_code == 200
    data = r_pending.json()
    assert data["id"] == purchase["id"]
    assert data["va_number"] == "70233334444"
    assert data["amount"] == 15000000

    transaksi = snap_payment_db.get_transaksi_terkini_untuk_lifetime_purchase(purchase["id"])
    snap_webhook.terapkan_status_transaksi(transaksi, "PAID", sumber="webhook")

    r_sesudah = app_client.get("/api/billing/lifetime-pending", headers=headers_owner)
    assert r_sesudah.status_code == 200
    assert r_sesudah.json() is None


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


def test_kode_referral_list_menyertakan_username(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    _buat_sales_via_api(app_client, headers)
    r = app_client.get("/api/superadmin/sales/kode-referral", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()[0]["username"] == "sales1"


def test_superadmin_ganti_password_akun_sales(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    kode = _buat_sales_via_api(app_client, headers)
    user = auth_db.get_user_by_username("sales1")

    r = app_client.put(f"/api/superadmin/sales/akun/{user['id']}/password", headers=headers,
                        json={"password": "passwordbaru999"})
    assert r.status_code == 200, r.text

    # Password lama sudah tidak berlaku, password baru bisa dipakai login.
    r_lama = app_client.post("/api/auth/login", json={"username": "sales1", "password": "passwordsales1"})
    assert r_lama.status_code == 401
    r_baru = app_client.post("/api/auth/login", json={"username": "sales1", "password": "passwordbaru999"})
    assert r_baru.status_code == 200, r_baru.text


def test_ganti_password_sales_password_terlalu_pendek_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    _buat_sales_via_api(app_client, headers)
    user = auth_db.get_user_by_username("sales1")
    r = app_client.put(f"/api/superadmin/sales/akun/{user['id']}/password", headers=headers, json={"password": "ab"})
    assert r.status_code == 422


def test_ganti_password_sales_tidak_bisa_sasar_akun_bukan_sales(app_client):
    """Endpoint ini KHUSUS akun role 'sales' -- tidak boleh jadi jalan
    pintas reset password akun Owner tenant mana pun walau Superadmin tahu
    user_id-nya."""
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    pemilik_id = auth_db.tambah_user("ownerpercobaan", "passwordowner123", "admin", tenant_id=tenant["id"])
    r = app_client.put(f"/api/superadmin/sales/akun/{pemilik_id}/password", headers=headers,
                        json={"password": "passwordbaru999"})
    assert r.status_code == 404


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


# ============================= Defense-in-depth: data korup (tenant_id ter-isi untuk akun sales) =============================
# INSIDEN NYATA produksi: satu baris akun 'sales' kedapatan tenant_id-nya
# ter-isi (seharusnya NULL, ditegakkan auth_db.tambah_user() -- cara
# persisnya terjadi tidak diketahui, tapi EFEKNYA dikonfirmasi langsung
# dari database produksi). Tes di bawah ini SENGAJA mensimulasikan baris
# yang sama (lewat SQL langsung, BUKAN tambah_user(), supaya validasi
# invariannya tidak ikut mencegat) untuk membuktikan role 'sales' TETAP
# diperlakukan sebagai akun platform (branding, akses tenant-scope, login)
# WALAU datanya korup -- lihat BUGFIX di auth.py::get_current_user()/
# resolve_tenant_untuk_branding() dan routers/auth_router.py::login().

def _rusak_tenant_id_akun(username: str, tenant_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET tenant_id = ? WHERE username = ?", (tenant_id, username))


def test_sales_tenant_id_korup_tetap_dapat_branding_platform(app_client):
    headers_sa = _buat_superadmin_dan_login(app_client)
    _buat_sales_via_api(app_client, headers_sa)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _rusak_tenant_id_akun("sales1", tenant["id"])

    headers_sales = _login(app_client, "sales1", "passwordsales1")
    r = app_client.get("/api/tenant/branding", headers=headers_sales)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nama_barbershop"] == "Rivoir"
    assert data["is_platform_default"] is True


def test_sales_tenant_id_korup_tetap_bisa_login_dan_akses_portal_sales(app_client):
    headers_sa = _buat_superadmin_dan_login(app_client)
    _buat_sales_via_api(app_client, headers_sa)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _rusak_tenant_id_akun("sales1", tenant["id"])

    r_login = app_client.post("/api/auth/login", json={"username": "sales1", "password": "passwordsales1"})
    assert r_login.status_code == 200, r_login.text
    # tenant_info login TIDAK ikut mengarah ke tenant tempat tenant_id-nya
    # korup -- akun ini TETAP akun platform, bukan "milik" tenant manapun.
    assert r_login.json()["tenant"] is None

    headers_sales = {"Authorization": f"Bearer {r_login.json()['token']}"}
    r_me = app_client.get("/api/sales/me", headers=headers_sales)
    assert r_me.status_code == 200, r_me.text
    assert r_me.json()["kode"] == "PROMO10"
