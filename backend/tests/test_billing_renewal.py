"""
test_billing_renewal.py — FITUR Notifikasi H-7 & Perpanjangan Cepat (diminta Owner)
=============================================================================
Cakupan: hapus total mekanisme grace (SUSPEND_GRACE_HARI otomatis + status
'grace_period' manual Super Admin) diganti peringatan H-7 di
GET /api/subscription/status (SEMUA role), dua endpoint baru
/api/billing/renewal-options & /api/billing/renewal-checkout (Owner ATAU
Staff/role custom, TIDAK TERMASUK Barber -- require_owner_or_staff) yang
HANYA menampilkan/mengizinkan paket sekarang + paket DI ATASNYA (tidak
pernah downgrade), dan peringatan fitur yang hilang saat downgrade
(GET /api/billing/downgrade-preview/{package_id}, Owner-only)."""

import auth_db
import billing_db
import database as db
import gateway_client_base
import payment_provider_client
import snap_advance_db
import subscription_db
import tenant_db


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _owner_login(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    return tenant, _login(app_client, "owner1", "password123")


def _staff_login(app_client, tenant):
    auth_db.tambah_user("kasir1", "password123", role="staff", tenant_id=tenant["id"])
    return _login(app_client, "kasir1", "password123")


def _barber_login(app_client, tenant):
    barber_id = db.add_barber("Andi Saputra", tenant_id=tenant["id"])
    auth_db.tambah_user("barber1", "password123", role="barber", barber_id=barber_id, tenant_id=tenant["id"])
    return _login(app_client, "barber1", "password123")


def _aktifkan_snap_billing(monkeypatch, va_number="70212345678901", gagal=False):
    snap_advance_db.update_config(
        merchant_id="37070", partner_id="37070", channel_id="77001", va_bank_aktif=["702"],
        sandbox_private_key="-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----",
        channel_aktif=["va", "qris"],
    )

    def _hasil(*a, **kw):
        if gagal:
            raise gateway_client_base.GatewayTimeoutError("Provider timeout.")
        return {"va_number": va_number, "provider_transaction_id": "trx-1",
                "expired_at": "2026-01-01T23:59:59+07:00", "provider_response": "{}"}
    monkeypatch.setattr(payment_provider_client, "buat_transaksi", _hasil)


# ============================= Hapus grace: status & migrasi =============================

def test_grace_period_bukan_lagi_status_valid():
    assert "grace_period" not in subscription_db.STATUS_VALID


def test_set_platform_config_tidak_lagi_punya_grace_hari(app_client):
    cfg = subscription_db.get_platform_config()
    assert "grace_hari" not in cfg
    assert cfg == {"trial_hari": subscription_db.DEFAULT_TRIAL_HARI}


def test_periode_lewat_langsung_suspended_tanpa_toleransi(app_client):
    from datetime import datetime, timedelta
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    subscription_db.update_status(tenant["id"], "active")
    periode_selesai = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    subscription_db.set_periode(tenant["id"], periode_selesai, periode_selesai)
    assert subscription_db.akses_diblokir(tenant["id"]) is True
    assert subscription_db.get_subscription(tenant["id"])["status"] == "suspended"


def test_migrasi_hapus_grace_period_konversi_status_lama_ke_active(app_client):
    """Simulasi baris tenant_subscriptions yang KEBETULAN masih berstatus
    'grace_period' (dibuat sebelum revisi ini, lewat SQL langsung karena
    update_status() SEKARANG menolak nilai itu) -- migrasi (dipanggil ulang
    di sini, simulasi redeploy) harus mengonversinya ke 'active'."""
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    with db.get_conn() as conn:
        conn.execute("UPDATE tenant_subscriptions SET status = 'grace_period' WHERE tenant_id = ?",
                     (tenant["id"],))
    assert subscription_db.get_subscription(tenant["id"])["status"] == "grace_period"

    # Migrasi ini SUDAH jalan sekali waktu app_client boot (main.py::
    # on_startup()) -- flag settings-nya dipaksa "belum jalan" lagi di sini
    # supaya simulasi "baris lama yang baru ketemu saat redeploy" berlaku.
    db.set_setting(subscription_db._KUNCI_HAPUS_GRACE_PERIOD, "0", tenant_id=None)
    subscription_db.migrasi_hapus_grace_period()

    assert subscription_db.get_subscription(tenant["id"])["status"] == "active"


def test_endpoint_grace_period_dihapus_total(app_client):
    import auth_db as _auth_db
    _auth_db.tambah_user("superadmin1", "rahasia123", role="superadmin", tenant_id=None)
    headers = _login(app_client, "superadmin1", "rahasia123")
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/grace",
                        headers=headers, json={"hari": 5})
    assert r.status_code == 404


# ============================= Peringatan H-7 (GET /api/subscription/status) =============================

def test_peringatan_kadaluarsa_true_saat_h_minus_7(app_client):
    from datetime import datetime, timedelta
    tenant, headers = _owner_login(app_client)
    subscription_db.update_status(tenant["id"], "active")
    periode_selesai = (datetime.now() + timedelta(days=5)).isoformat(timespec="seconds")
    subscription_db.set_periode(tenant["id"], periode_selesai, periode_selesai)

    r = app_client.get("/api/subscription/status", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["peringatan_kadaluarsa"] is True
    assert data["hari_tersisa"] == 5
    assert data["periode_selesai"] == periode_selesai


def test_peringatan_kadaluarsa_false_saat_masih_jauh(app_client):
    from datetime import datetime, timedelta
    tenant, headers = _owner_login(app_client)
    subscription_db.update_status(tenant["id"], "active")
    periode_selesai = (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds")
    subscription_db.set_periode(tenant["id"], periode_selesai, periode_selesai)

    r = app_client.get("/api/subscription/status", headers=headers)
    assert r.json()["peringatan_kadaluarsa"] is False


def test_peringatan_kadaluarsa_false_untuk_status_lifetime(app_client):
    tenant, headers = _owner_login(app_client)
    subscription_db.update_status(tenant["id"], "lifetime")

    r = app_client.get("/api/subscription/status", headers=headers)
    data = r.json()
    assert data["peringatan_kadaluarsa"] is False
    assert data["hari_tersisa"] is None


# ============================= Peringatan H-7 untuk masa TRIAL (diminta Owner: "perluas juga ke masa trial") =============================

def test_peringatan_kadaluarsa_true_saat_trial_h_minus_7(app_client):
    """Tenant BARU mendaftar (status 'trial') yang trial_end-nya tinggal
    5 hari lagi JUGA harus dapat peringatan H-7 -- SEBELUMNYA hanya status
    'active' (periode berbayar) yang dicek."""
    tenant, headers = _owner_login(app_client)
    subscription_db.set_trial(tenant["id"], hari=5)
    subscription_db.update_status(tenant["id"], "trial")

    r = app_client.get("/api/subscription/status", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "trial"
    assert data["peringatan_kadaluarsa"] is True
    assert data["hari_tersisa"] == 5


def test_peringatan_kadaluarsa_false_saat_trial_masih_jauh(app_client):
    tenant, headers = _owner_login(app_client)
    subscription_db.set_trial(tenant["id"], hari=30)
    subscription_db.update_status(tenant["id"], "trial")

    r = app_client.get("/api/subscription/status", headers=headers)
    assert r.json()["peringatan_kadaluarsa"] is False


def test_tenant_baru_mendaftar_dapat_peringatan_h7_saat_trial_hampir_habis(app_client):
    """End-to-end pola create_default_subscription() (dipanggil
    routers/tenant_registration.py::register() saat tenant SUNGGUHAN
    mendaftar) -- trial_end dihitung otomatis dari DEFAULT_TRIAL_HARI, lalu
    trial DIPERPENDEK manual di sini (simulasi "5 hari lagi") untuk
    membuktikan peringatannya benar-benar menyala tanpa perlu menunggu
    30 hari sungguhan."""
    tenant = tenant_db.buat_tenant("toko-trial-baru", "Toko Trial Baru")
    subscription_db.create_default_subscription(tenant, status="trial")
    subscription_db.set_trial(tenant, hari=5)
    auth_db.tambah_user("ownertrialbaru", "password123", role="admin", tenant_id=tenant)
    headers = _login(app_client, "ownertrialbaru", "password123")

    r = app_client.get("/api/subscription/status", headers=headers)
    data = r.json()
    assert data["status"] == "trial"
    assert data["peringatan_kadaluarsa"] is True
    assert data["akses_diblokir"] is False


def test_peringatan_kadaluarsa_terlihat_juga_untuk_staff(app_client):
    """Dikonfirmasi Owner: tulisan H-7 tampil untuk Owner DAN Staff/role
    custom apa pun -- endpoint /status TIDAK digerbang require_admin."""
    from datetime import datetime, timedelta
    tenant, _ = _owner_login(app_client)
    subscription_db.update_status(tenant["id"], "active")
    periode_selesai = (datetime.now() + timedelta(days=2)).isoformat(timespec="seconds")
    subscription_db.set_periode(tenant["id"], periode_selesai, periode_selesai)
    headers_staff = _staff_login(app_client, tenant)

    r = app_client.get("/api/subscription/status", headers=headers_staff)
    assert r.json()["peringatan_kadaluarsa"] is True


# ============================= GET /api/billing/renewal-options =============================

def test_renewal_options_hanya_sekarang_dan_di_atasnya(app_client):
    tenant, headers = _owner_login(app_client)
    subscription_db.update_package(tenant["id"], "basic")
    basic = billing_db.get_package_by_kode("basic")
    free = billing_db.get_package_by_kode("free")

    r = app_client.get("/api/billing/renewal-options", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["package_sekarang"]["kode"] == "basic"
    kode_pilihan = {p["kode"] for p in data["pilihan"]}
    assert "basic" in kode_pilihan
    assert all(p["urutan"] >= basic["urutan"] for p in data["pilihan"])
    if free["urutan"] < basic["urutan"]:
        assert "free" not in kode_pilihan


def test_billing_config_staff_bisa_akses(app_client):
    """GET /api/billing/config digerbang ulang ke require_owner_or_staff
    (dari require_admin) -- dibutuhkan pages/perpanjangan.js untuk tahu
    channel/bank pembayaran aktif sebelum checkout."""
    tenant, _ = _owner_login(app_client)
    headers_staff = _staff_login(app_client, tenant)
    r = app_client.get("/api/billing/config", headers=headers_staff)
    assert r.status_code == 200, r.text


def test_renewal_options_staff_bisa_akses(app_client):
    tenant, _ = _owner_login(app_client)
    headers_staff = _staff_login(app_client, tenant)
    r = app_client.get("/api/billing/renewal-options", headers=headers_staff)
    assert r.status_code == 200, r.text


def test_renewal_options_barber_ditolak(app_client):
    tenant, _ = _owner_login(app_client)
    headers_barber = _barber_login(app_client, tenant)
    r = app_client.get("/api/billing/renewal-options", headers=headers_barber)
    assert r.status_code == 403


# ============================= POST /api/billing/renewal-checkout =============================

def test_renewal_checkout_downgrade_ditolak_meski_oleh_staff(app_client):
    tenant, _ = _owner_login(app_client)
    subscription_db.update_package(tenant["id"], "pro")
    free = billing_db.get_package_by_kode("free")
    headers_staff = _staff_login(app_client, tenant)

    r = app_client.post("/api/billing/renewal-checkout", headers=headers_staff,
                         json={"package_id": free["id"], "siklus": "bulanan", "channel": "va", "bank_code": "702"})
    assert r.status_code == 422
    assert "Owner" in r.json()["detail"]


def test_renewal_checkout_staff_bisa_perpanjang_paket_sama(app_client, monkeypatch):
    tenant, _ = _owner_login(app_client)
    subscription_db.update_package(tenant["id"], "basic")
    basic = billing_db.get_package_by_kode("basic")
    headers_staff = _staff_login(app_client, tenant)
    _aktifkan_snap_billing(monkeypatch)

    r = app_client.post("/api/billing/renewal-checkout", headers=headers_staff,
                         json={"package_id": basic["id"], "siklus": "bulanan", "channel": "va", "bank_code": "702"})
    assert r.status_code == 200, r.text
    assert r.json()["va_number"] == "70212345678901"


def test_renewal_checkout_barber_ditolak(app_client):
    tenant, _ = _owner_login(app_client)
    subscription_db.update_package(tenant["id"], "basic")
    basic = billing_db.get_package_by_kode("basic")
    headers_barber = _barber_login(app_client, tenant)

    r = app_client.post("/api/billing/renewal-checkout", headers=headers_barber,
                         json={"package_id": basic["id"], "siklus": "bulanan", "channel": "va", "bank_code": "702"})
    assert r.status_code == 403


# ============================= GET /api/billing/downgrade-preview/{package_id} =============================

def test_downgrade_preview_daftar_fitur_hilang(app_client):
    tenant, headers = _owner_login(app_client)
    pro = billing_db.get_package_by_kode("pro")
    free = billing_db.get_package_by_kode("free")
    subscription_db.update_package(tenant["id"], "pro")

    # Pastikan "pro" punya fitur yang TIDAK dipunyai "free".
    fitur = billing_db.list_features()
    kode_fitur = next(f for f in fitur if f["kode"] == "export_excel")
    billing_db.set_package_features(pro["id"], [kode_fitur["id"]])
    billing_db.set_package_features(free["id"], [])

    r = app_client.get(f"/api/billing/downgrade-preview/{free['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert "Export Excel" in r.json()["fitur_hilang"]


def test_downgrade_preview_daftar_izin_menu_hilang(app_client):
    tenant, headers = _owner_login(app_client)
    pro = billing_db.get_package_by_kode("pro")
    free = billing_db.get_package_by_kode("free")
    subscription_db.update_package(tenant["id"], "pro")

    billing_db.set_package_permission_keys(pro["id"], {"izin_whatsapp_lihat"})
    billing_db.set_package_permission_keys(free["id"], set())

    r = app_client.get(f"/api/billing/downgrade-preview/{free['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert "WhatsApp" in r.json()["fitur_hilang"]


def test_downgrade_preview_kosong_kalau_tidak_ada_yang_hilang(app_client):
    tenant, headers = _owner_login(app_client)
    pro = billing_db.get_package_by_kode("pro")
    enterprise = billing_db.get_package_by_kode("enterprise")
    subscription_db.update_package(tenant["id"], "pro")

    billing_db.set_package_features(pro["id"], [])
    billing_db.set_package_permission_keys(pro["id"], set())

    r = app_client.get(f"/api/billing/downgrade-preview/{enterprise['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["fitur_hilang"] == []


def test_downgrade_preview_staff_ditolak(app_client):
    """Peringatan downgrade ini bagian dari alur downgrade -- TETAP
    Owner-only, BEDA dari renewal-options/renewal-checkout di atas."""
    tenant, _ = _owner_login(app_client)
    free = billing_db.get_package_by_kode("free")
    headers_staff = _staff_login(app_client, tenant)

    r = app_client.get(f"/api/billing/downgrade-preview/{free['id']}", headers=headers_staff)
    assert r.status_code == 403
