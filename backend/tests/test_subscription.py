"""
test_subscription.py — FONDASI Multi-Tenant Phase 3: Subscription & Tenant Lifecycle
=============================================================================
Cakupan: backfill migrasi untuk tenant lama, tenant baru lewat Dashboard
Super Admin otomatis dapat subscription, CRUD Super Admin (package/status/
trial/grace/config/pembayaran VA) + audit log, akses read-only Owner
(terisolasi per tenant), penegakan akses di halaman publik /book per status,
dan regresi: tenants.status ('aktif'/'nonaktif') TIDAK terpengaruh sama
sekali oleh subscription.status (dua mekanisme independen, lihat
subscription_db.py)."""

import auth_db
import billing_db
import billing_invoice_db
import database as db
import subscription_db
import tenant_db


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    return _login(client, username, password)


# ============================= Backfill migrasi =============================

def test_tenant_default_dapat_subscription_saat_boot(app_client):
    """migrasi_subscription() (dipanggil setelah migrasi_tenant() di
    main.py::on_startup()) HARUS memberi tenant default ("mugen-hair-co",
    dibuat migrasi_tenant() sendiri) baris subscription -- status default
    HARUS 'active' (bukan 'expired'/'suspended'/dst) supaya tenant produksi
    lama TIDAK PERNAH tiba-tiba terkunci begitu Phase 3 di-deploy."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    assert tenant is not None
    sub = subscription_db.get_subscription(tenant["id"])
    assert sub is not None
    assert sub["status"] == "active"
    assert sub["package"] == "free"
    assert subscription_db.akses_diblokir(tenant["id"]) is False


def test_tenant_tanpa_baris_subscription_tidak_diblokir_fail_open(two_tenants):
    """Tenant dari fixture two_tenants dibuat lewat tenant_db.buat_tenant()
    LANGSUNG (bukan lewat routers/superadmin.py, jadi TIDAK melewati
    subscription_db.create_default_subscription()) -- sengaja TIDAK punya
    baris tenant_subscriptions. akses_diblokir() harus False (fail-open)."""
    assert subscription_db.get_subscription(two_tenants["tenant_a"]) is None
    assert subscription_db.akses_diblokir(two_tenants["tenant_a"]) is False

    r = two_tenants["client"].get("/api/subscription/me", headers=two_tenants["headers_a"])
    assert r.status_code == 404


def test_backfill_tidak_menimpa_subscription_yang_sudah_diatur(app_client):
    """migrasi_subscription() idempotent -- dipanggil ulang (simulasi
    restart proses) TIDAK boleh menimpa perubahan yang sudah dibuat Super
    Admin sebelumnya."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    subscription_db.update_package(tenant["id"], "enterprise")
    subscription_db.update_status(tenant["id"], "suspended")

    from subscription_migrasi import migrasi_subscription
    migrasi_subscription()

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["package"] == "enterprise"
    assert sub["status"] == "suspended"


# ============================= Tenant baru (Super Admin) =============================

def test_tenant_baru_lewat_superadmin_otomatis_dapat_subscription(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.post("/api/superadmin/tenants", headers=headers, json={
        "slug": "toko-baru", "nama_barbershop": "Toko Baru Sejahtera",
        "owner_username": "ownerbaru", "owner_password": "passwordbaru123",
    })
    assert r.status_code == 200, r.text
    tenant_id = r.json()["id"]

    sub = subscription_db.get_subscription(tenant_id)
    assert sub is not None
    assert sub["status"] == "active"
    assert sub["package"] == "free"


# ============================= Owner read-only =============================

def test_owner_melihat_subscription_sendiri(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    headers = _login(app_client, "owner1", "password123")

    r = app_client.get("/api/subscription/me", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tenant_id"] == tenant["id"]
    assert data["status"] == "active"
    assert data["akses_diblokir"] is False


def test_staff_dan_barber_ditolak_endpoint_subscription_me(app_client):
    """Sesuai cakupan Phase 3: "Owner hanya dapat melihat informasi
    subscription" -- akun 'staff' (Admin) dan 'barber' TIDAK ikut bisa
    mengakses endpoint ini sama sekali (require_admin, murni role 'admin')."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    auth_db.tambah_user("staff1", "password123", role="staff", tenant_id=tenant["id"])
    barber_id = db.add_barber("Andi Saputra", tenant_id=tenant["id"])
    auth_db.tambah_user("barber1", "password123", role="barber", barber_id=barber_id, tenant_id=tenant["id"])

    headers_staff = _login(app_client, "staff1", "password123")
    headers_barber = _login(app_client, "barber1", "password123")

    assert app_client.get("/api/subscription/me", headers=headers_staff).status_code == 403
    assert app_client.get("/api/subscription/me", headers=headers_barber).status_code == 403


def test_status_endpoint_terbuka_untuk_semua_role_tenant(app_client):
    """Beda dari /me (Owner-murni) -- /status boleh dipanggil staff & barber,
    hanya mengembalikan boolean (bukan detail package/trial/dst)."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    auth_db.tambah_user("staff1", "password123", role="staff", tenant_id=tenant["id"])
    barber_id = db.add_barber("Andi Saputra", tenant_id=tenant["id"])
    auth_db.tambah_user("barber1", "password123", role="barber", barber_id=barber_id, tenant_id=tenant["id"])

    headers_staff = _login(app_client, "staff1", "password123")
    headers_barber = _login(app_client, "barber1", "password123")

    r1 = app_client.get("/api/subscription/status", headers=headers_staff)
    assert r1.status_code == 200
    # Feature Gating (FONDASI Multi-Tenant Phase 4 lanjutan): endpoint ini
    # SEKARANG juga membawa `package`/`features` (lihat routers/subscription.py)
    # -- dicek per-field (bukan exact dict equality) supaya penambahan field
    # di masa depan tidak otomatis mematahkan test ini.
    assert r1.json()["akses_diblokir"] is False

    subscription_db.update_status(tenant["id"], "cancelled")
    r2 = app_client.get("/api/subscription/status", headers=headers_barber)
    assert r2.json()["akses_diblokir"] is True


def test_status_endpoint_superadmin_tidak_diblokir(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/subscription/status", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"akses_diblokir": False, "package": None, "features": []}


def test_owner_tidak_bisa_lihat_subscription_tenant_lain(two_tenants):
    """Isolasi tenant: endpoint Owner SELALU pakai tenant_id dari sesi login
    sendiri (user["tenant_id"]) -- tidak ada parameter tenant_id yang bisa
    dipakai untuk mengintip tenant lain."""
    client = two_tenants["client"]
    subscription_db.create_default_subscription(two_tenants["tenant_a"], package="pro", status="active")
    subscription_db.create_default_subscription(two_tenants["tenant_b"], package="free", status="suspended")

    r_a = client.get("/api/subscription/me", headers=two_tenants["headers_a"])
    r_b = client.get("/api/subscription/me", headers=two_tenants["headers_b"])
    assert r_a.json()["package"] == "pro"
    assert r_b.json()["package"] == "free"
    assert r_a.json()["tenant_id"] != r_b.json()["tenant_id"]


def test_akun_tenant_biasa_ditolak_endpoint_superadmin_subscriptions(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/subscriptions", headers=two_tenants["headers_a"])
    assert r.status_code == 403


# ============================= Super Admin CRUD =============================

def test_superadmin_ubah_package_dan_status(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")

    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/package",
                        headers=headers, json={"package": "enterprise"})
    assert r.status_code == 200, r.text
    assert r.json()["package"] == "enterprise"

    r2 = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/status",
                         headers=headers, json={"status": "grace_period"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "grace_period"


def test_superadmin_package_tidak_valid_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/package",
                        headers=headers, json={"package": "diamond"})
    assert r.status_code == 422


def test_superadmin_status_tidak_valid_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/status",
                        headers=headers, json={"status": "dibekukan"})
    assert r.status_code == 422


def test_superadmin_atur_trial_dan_grace(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")

    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/trial",
                        headers=headers, json={"hari": 30})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["trial_start"] is not None
    assert data["trial_end"] is not None
    from datetime import datetime
    delta = datetime.fromisoformat(data["trial_end"]) - datetime.fromisoformat(data["trial_start"])
    assert delta.days == 30

    r2 = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/grace",
                         headers=headers, json={"hari": 5})
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    delta2 = datetime.fromisoformat(data2["grace_end"]) - datetime.fromisoformat(data2["grace_start"])
    assert delta2.days == 5


def test_superadmin_ubah_subscription_tenant_tidak_ada_404(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.put("/api/superadmin/subscriptions/999999/package", headers=headers, json={"package": "pro"})
    assert r.status_code == 404


def test_superadmin_config_platform(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/superadmin/subscriptions/config", headers=headers)
    assert r.status_code == 200
    # FITUR Landing Page & Pricing (Free Trial 30 Hari): default trial_hari
    # dinaikkan 14 -> 30 (subscription_db.DEFAULT_TRIAL_HARI).
    assert r.json() == {"trial_hari": 30, "grace_hari": 7}

    r2 = app_client.put("/api/superadmin/subscriptions/config", headers=headers,
                         json={"trial_hari": 21, "grace_hari": 3})
    assert r2.status_code == 200, r2.text
    assert r2.json() == {"trial_hari": 21, "grace_hari": 3}

    r3 = app_client.get("/api/superadmin/subscriptions/config", headers=headers)
    assert r3.json() == {"trial_hari": 21, "grace_hari": 3}


def test_superadmin_config_durasi_kurang_dari_1_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.put("/api/superadmin/subscriptions/config", headers=headers, json={"trial_hari": 0})
    assert r.status_code == 422


def test_superadmin_list_subscriptions_berisi_slug_dan_nama(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/superadmin/subscriptions", headers=headers)
    assert r.status_code == 200, r.text
    baris = [b for b in r.json() if b["tenant_slug"] == "mugen-hair-co"]
    assert len(baris) == 1
    assert baris[0]["nama_barbershop"] == "MUGEN Hair Co."


# ============================= Pembayaran VA (struktur saja) =============================

def test_superadmin_catat_dan_tandai_lunas_pembayaran(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")

    r = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "1234567890", "amount": 150000,
    })
    assert r.status_code == 200, r.text
    payment = r.json()
    assert payment["payment_status"] == "pending"
    assert payment["paid_at"] is None

    r2 = app_client.put(f"/api/superadmin/subscriptions/payments/{payment['id']}/status",
                         headers=headers, json={"payment_status": "paid"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["payment_status"] == "paid"
    assert r2.json()["paid_at"] is not None

    r3 = app_client.get(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers)
    assert len(r3.json()) == 1


def test_pembayaran_amount_nol_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    r = app_client.post(f"/api/superadmin/subscriptions/{tenant['id']}/payments", headers=headers, json={
        "provider": "BCA", "virtual_account_number": "123", "amount": 0,
    })
    assert r.status_code == 422


def test_payment_status_tidak_valid_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    payment = subscription_db.create_payment(tenant["id"], "BCA", "123", 100000)
    r = app_client.put(f"/api/superadmin/subscriptions/payments/{payment['id']}/status",
                        headers=headers, json={"payment_status": "lunas_sebagian"})
    assert r.status_code == 422


# ============================= Audit log =============================

def test_audit_log_mencatat_perubahan_subscription(app_client):
    headers = _buat_superadmin_dan_login(app_client, username="auditor1")
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")

    app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/package", headers=headers, json={"package": "pro"})
    app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/status", headers=headers, json={"status": "expired"})

    r = app_client.get("/api/superadmin/audit-log", headers=headers)
    aksi = [e["aksi"] for e in r.json() if e["tenant_slug"] == "mugen-hair-co"]
    assert aksi[:2] == ["ubah_status_subscription", "ubah_package_subscription"]


# ============================= Penegakan akses: dashboard internal =============================

def test_login_owner_tetap_berhasil_walau_subscription_diblokir(app_client):
    """SESUAI KEPUTUSAN: dua mekanisme independen -- subscription
    Expired/Suspended/Cancelled TIDAK membuat login 401 (beda dari
    tenants.status='nonaktif'). Owner tetap bisa login & memanggil
    /api/subscription/me (read-only) untuk melihat kenapa diblokir.

    KOREKSI (audit lanjutan -- enforcement paket/subscription): SEBELUMNYA
    test ini mendokumentasikan bahwa "endpoint bisnis biasa tetap bisa
    diakses" saat diblokir (penegakan HANYA di frontend router.js) --
    itu justru CELAH yang diperbaiki (auth.py::get_current_user(), lihat
    _PREFIX_BEBAS_BLOKIR_SUBSCRIPTION). SEKARANG hanya /api/auth, /api/billing,
    /api/subscription yang tetap bisa diakses saat diblokir (supaya Owner
    tetap bisa login, lihat status, dan BAYAR untuk memulihkan akses) --
    endpoint bisnis LAIN (dicontohkan lewat /api/pengaturan/whatsapp di
    bawah) sekarang WAJIB 403."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    subscription_db.update_status(tenant["id"], "expired")

    r = app_client.post("/api/auth/login", json={"username": "owner1", "password": "password123"})
    assert r.status_code == 200, r.text

    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    r2 = app_client.get("/api/subscription/me", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["akses_diblokir"] is True

    # /api/auth TETAP bebas blokir SENGAJA (Owner harus tetap bisa login
    # kapan pun, termasuk saat diblokir -- supaya bisa lanjut ke /api/billing
    # untuk membayar).
    r3 = app_client.get("/api/auth/me", headers=headers)
    assert r3.status_code == 200

    # Endpoint bisnis di luar prefix bebas blokir SEKARANG 403 -- pola SAMA
    # untuk SELURUH endpoint ber-login lain, satu titik di get_current_user().
    r4 = app_client.get("/api/pengaturan/whatsapp", headers=headers)
    assert r4.status_code == 403


def test_tenants_status_nonaktif_tidak_terpengaruh_subscription_aktif(app_client):
    """Regresi kebalikannya -- kill-switch tenants.status ('aktif'/
    'nonaktif', SUDAH ADA sejak Phase 1) tetap 401 TOTAL walau
    subscription.status-nya 'active' (normal). Dua mekanisme SEPENUHNYA
    independen, auth.py TIDAK disentuh sama sekali oleh Phase 3 ini."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    headers = _login(app_client, "owner1", "password123")

    tenant_db.set_status(tenant["id"], "nonaktif")
    r = app_client.get("/api/auth/me", headers=headers)
    assert r.status_code == 401


# ============================= Penegakan akses: /book publik =============================

def test_book_publik_normal_saat_trial_active_grace(app_client):
    # HOTFIX Migrasi Subdomain: endpoint publik TIDAK LAGI diam-diam jatuh
    # ke tenant default kalau ?tenant= kosong -- WAJIB eksplisit.
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    for status in ("trial", "active", "grace_period"):
        subscription_db.update_status(tenant["id"], status)
        r = app_client.get(f"/api/public/booking/barbers?tenant={tenant['slug']}")
        assert r.status_code == 200, f"status={status}: {r.text}"
        r2 = app_client.get(f"/api/public/booking/subscription-status?tenant={tenant['slug']}")
        assert r2.json() == {"tersedia": True}


def test_book_publik_diblokir_saat_expired_suspended_cancelled(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    for status in ("expired", "suspended", "cancelled"):
        subscription_db.update_status(tenant["id"], status)
        r = app_client.get(f"/api/public/booking/barbers?tenant={tenant['slug']}")
        assert r.status_code == 403, f"status={status}: {r.text}"
        r2 = app_client.get(f"/api/public/booking/services?tenant={tenant['slug']}")
        assert r2.status_code == 403
        r3 = app_client.get(f"/api/public/booking/pengaturan?tenant={tenant['slug']}")
        assert r3.status_code == 403
        # subscription-status sendiri TETAP bisa diakses (justru untuk
        # melaporkan status ini ke frontend).
        r4 = app_client.get(f"/api/public/booking/subscription-status?tenant={tenant['slug']}")
        assert r4.status_code == 200
        assert r4.json() == {"tersedia": False}


def test_book_publik_buat_booking_diblokir_saat_suspended(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    subscription_db.update_status(tenant["id"], "suspended")
    r = app_client.post(f"/api/public/booking?tenant={tenant['slug']}", json={
        "barber_id": 1, "tanggal": "2026-01-01", "jam_mulai": "10:00",
        "service_ids": [1], "customer_nama": "Test", "customer_whatsapp": "0800",
        "metode_pembayaran": "transfer",
    })
    assert r.status_code == 403


def test_book_publik_tenant_tanpa_subscription_tidak_diblokir_status(two_tenants):
    """Fail-open juga berlaku untuk halaman publik -- tenant hasil fixture
    two_tenants (tanpa baris subscription) TIDAK diblokir OLEH STATUS
    (resolve_tenant_publik_aktif). Dites lewat /subscription-status (BUKAN
    /barbers seperti sebelumnya) -- endpoint itu SENGAJA satu-satunya yang
    TIDAK ikut digerbang fitur "booking_online" (lihat docstring
    public_subscription_status() di routers/booking.py), jadi proxy yang
    bersih untuk fail-open status TANPA tercampur gerbang fitur terpisah
    (AUDIT enforcement paket/subscription -- lihat test di bawah untuk
    gerbang fitur "booking_online" itu sendiri)."""
    client = two_tenants["client"]
    r = client.get(f"/api/public/booking/subscription-status?tenant=test-toko-a")
    assert r.status_code == 200
    assert r.json() == {"tersedia": True}


def test_book_publik_tenant_tanpa_subscription_diblokir_fitur_booking_online(two_tenants):
    """AUDIT (enforcement paket/subscription): BEDA dari fail-open status di
    atas -- tenant tanpa baris subscription juga TIDAK PUNYA fitur
    "booking_online" sama sekali (fail-CLOSED, lihat feature_access.py),
    jadi /barbers (dan /services/slot lainnya, pola sama) tetap 403 walau
    statusnya sendiri tidak diblokir. Dua gate independen, keduanya harus
    dilewati."""
    client = two_tenants["client"]
    r = client.get(f"/api/public/booking/barbers?tenant=test-toko-a")
    assert r.status_code == 403


def test_book_publik_tenant_lain_tidak_ikut_terblokir(two_tenants):
    """Isolasi tenant: memblokir subscription tenant A TIDAK memengaruhi
    halaman publik tenant B."""
    client = two_tenants["client"]
    subscription_db.create_default_subscription(two_tenants["tenant_a"], status="suspended")
    subscription_db.create_default_subscription(two_tenants["tenant_b"], status="active")

    r_a = client.get("/api/public/booking/barbers?tenant=test-toko-a")
    r_b = client.get("/api/public/booking/barbers?tenant=test-toko-b")
    assert r_a.status_code == 403
    assert r_b.status_code == 200


# ============================= Perbaikan Billing/Subscription: Auto-Suspend (requirement 8, 9, 12, 13) =============================

def _sub_aktif_dengan_periode(tenant_id, hari_lewat):
    """Tenant status 'active' dengan periode_selesai `hari_lewat` hari yang
    lalu dari sekarang (negatif = MASIH di masa depan)."""
    from datetime import datetime, timedelta
    subscription_db.update_status(tenant_id, "active")
    periode_selesai = (datetime.now() - timedelta(days=hari_lewat)).isoformat(timespec="seconds")
    subscription_db.set_periode(tenant_id, periode_selesai, periode_selesai)


def test_status_aktif_dengan_periode_selesai_masa_depan_tidak_diblokir(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _sub_aktif_dengan_periode(tenant["id"], hari_lewat=-10)
    assert subscription_db.akses_diblokir(tenant["id"]) is False
    assert subscription_db.get_subscription(tenant["id"])["status"] == "active"


def test_status_aktif_periode_lewat_dalam_7_hari_belum_disuspend(app_client):
    """requirement poin 8: periode sudah berakhir TAPI belum lewat 7 hari --
    akses TETAP terbuka, status TETAP 'active' (belum auto-suspend)."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _sub_aktif_dengan_periode(tenant["id"], hari_lewat=3)
    assert subscription_db.akses_diblokir(tenant["id"]) is False
    assert subscription_db.get_subscription(tenant["id"])["status"] == "active"


def test_status_aktif_periode_lewat_lebih_dari_7_hari_otomatis_suspended(app_client):
    """requirement poin 9: lewat lebih dari 7 hari tanpa pembayaran sukses
    -> status OTOMATIS jadi 'suspended', akses diblokir."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _sub_aktif_dengan_periode(tenant["id"], hari_lewat=8)
    assert subscription_db.akses_diblokir(tenant["id"]) is True
    assert subscription_db.get_subscription(tenant["id"])["status"] == "suspended"


def test_auto_suspend_tidak_menghapus_tenant_atau_invoice_atau_riwayat(app_client):
    """requirement poin 9: auto-suspend TIDAK PERNAH menghapus tenant/
    database/invoice/riwayat pembayaran -- murni mengubah kolom status."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    paket = billing_db.get_package_by_kode("pro")
    order_id = billing_invoice_db.buat_order_id(tenant["id"])
    invoice = billing_invoice_db.buat_invoice(order_id, tenant["id"], paket)

    _sub_aktif_dengan_periode(tenant["id"], hari_lewat=8)
    subscription_db.akses_diblokir(tenant["id"])  # memicu auto-suspend

    assert tenant_db.get_tenant(tenant["id"]) is not None
    assert billing_invoice_db.get_invoice(invoice["id"]) is not None


def test_status_trial_tidak_terpengaruh_auto_suspend(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    from datetime import datetime, timedelta
    periode_selesai = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    subscription_db.set_periode(tenant["id"], periode_selesai, periode_selesai)
    subscription_db.update_status(tenant["id"], "trial")

    assert subscription_db.akses_diblokir(tenant["id"]) is False
    assert subscription_db.get_subscription(tenant["id"])["status"] == "trial"


def test_status_grace_period_tidak_terpengaruh_auto_suspend(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    from datetime import datetime, timedelta
    periode_selesai = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    subscription_db.set_periode(tenant["id"], periode_selesai, periode_selesai)
    subscription_db.update_status(tenant["id"], "grace_period")

    assert subscription_db.akses_diblokir(tenant["id"]) is False
    assert subscription_db.get_subscription(tenant["id"])["status"] == "grace_period"


def test_status_cancelled_manual_tidak_diubah_oleh_auto_suspend(app_client):
    """Status 'cancelled' yang di-set manual Super Admin TETAP 'cancelled'
    (bukan diam-diam ditimpa 'suspended') -- _auto_suspend_jika_lewat()
    hanya beraksi untuk status == 'active'."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    from datetime import datetime, timedelta
    periode_selesai = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    subscription_db.set_periode(tenant["id"], periode_selesai, periode_selesai)
    subscription_db.update_status(tenant["id"], "cancelled")

    assert subscription_db.akses_diblokir(tenant["id"]) is True
    assert subscription_db.get_subscription(tenant["id"])["status"] == "cancelled"


def test_pembayaran_setelah_suspend_otomatis_kembali_aktif(app_client, monkeypatch):
    """requirement poin 12: Suspended -> pembayaran sukses -> status
    otomatis 'active' kembali, TANPA aksi Super Admin apa pun."""
    from test_billing_webhook import _buat_invoice, _dengan_server_key, _payload
    import billing_webhook

    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _sub_aktif_dengan_periode(tenant["id"], hari_lewat=8)
    assert subscription_db.akses_diblokir(tenant["id"]) is True
    assert subscription_db.get_subscription(tenant["id"])["status"] == "suspended"

    _dengan_server_key(monkeypatch)
    invoice = _buat_invoice(tenant["id"], package_kode="pro", durasi_hari=30)
    billing_webhook.proses_notifikasi(_payload(invoice["order_id"], "2", invoice["jumlah"]))

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["status"] == "active"
    assert subscription_db.akses_diblokir(tenant["id"]) is False


def test_pembayaran_setelah_suspend_anchor_tetap_dari_periode_lama(app_client, monkeypatch):
    """requirement poin 13: walau dibayar SETELAH suspend, tanggal bayar
    TETAP TIDAK jadi anchor baru -- mengikuti aturan requirement poin 1
    (menyambung dari periode_selesai lama)."""
    from test_billing_webhook import _buat_invoice, _dengan_server_key, _payload
    import billing_webhook

    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    _sub_aktif_dengan_periode(tenant["id"], hari_lewat=8)
    periode_selesai_lama = subscription_db.get_subscription(tenant["id"])["periode_selesai"]
    subscription_db.akses_diblokir(tenant["id"])  # picu auto-suspend

    _dengan_server_key(monkeypatch)
    invoice = _buat_invoice(tenant["id"], package_kode="pro", durasi_hari=30)
    hasil = billing_webhook.proses_notifikasi(_payload(invoice["order_id"], "2", invoice["jumlah"]))

    assert hasil["periode_mulai"] == periode_selesai_lama


def test_akses_diblokir_publik_booking_ikut_ter_suspend(two_tenants):
    """Regresi lintas titik panggil akses_diblokir(): auto-suspend yang
    terpicu lewat SATU titik panggil (mis. /api/subscription/status) harus
    otomatis terlihat di titik panggil LAIN (halaman publik booking) juga,
    karena status disimpan (bukan cache per-request)."""
    client = two_tenants["client"]
    subscription_db.create_default_subscription(two_tenants["tenant_a"], package="pro", status="active")
    _sub_aktif_dengan_periode(two_tenants["tenant_a"], hari_lewat=8)

    r_status = client.get("/api/subscription/status", headers=two_tenants["headers_a"])
    assert r_status.json()["akses_diblokir"] is True

    r_publik = client.get("/api/public/booking/barbers?tenant=test-toko-a")
    assert r_publik.status_code == 403
