"""
test_billing_downgrade.py — FONDASI Multi-Tenant Phase 4: Downgrade Paket
=============================================================================
SESUAI KEPUTUSAN cakupan Phase 4 ("Blokir downgrade sampai pemakaian
dikurangi dulu"): downgrade langsung berhasil kalau pemakaian sekarang
masih di bawah limit paket tujuan, diblokir TOTAL (422, TIDAK ADA
penonaktifan otomatis apa pun) kalau melebihi, dan upgrade (paket lebih
mahal/urutan lebih tinggi) ditolak lewat endpoint ini -- harus lewat
checkout."""

import auth_db
import billing_db
import billing_limits
import database as db
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


# ============================= billing_limits.hitung_pemakaian / evaluasi_downgrade =============================

def test_hitung_pemakaian(app_client):
    # tenant default sudah punya akun admin bootstrap ("owner") sejak boot
    # (lihat main.py::_bootstrap_admin_pertama()) -- pakai baseline SEKARANG
    # + N, bukan angka tetap (pola sama seperti test_billing_limits.py).
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    jumlah_user_awal = billing_limits.hitung_pemakaian(tenant["id"])["max_user"]
    db.add_barber("Barber 1", tenant_id=tenant["id"])
    db.add_barber("Barber 2", tenant_id=tenant["id"])

    pemakaian = billing_limits.hitung_pemakaian(tenant["id"])
    assert pemakaian["max_barber"] == 2
    assert pemakaian["max_user"] == jumlah_user_awal
    assert pemakaian["max_booking"] == 0


def test_evaluasi_downgrade_kosong_kalau_limit_null(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    db.add_barber("Barber 1", tenant_id=tenant["id"])
    free = billing_db.get_package_by_kode("free")  # semua limit NULL secara default

    assert billing_limits.evaluasi_downgrade(tenant["id"], free) == []


def test_evaluasi_downgrade_melaporkan_pelanggaran(app_client):
    tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    db.add_barber("Barber 1", tenant_id=tenant["id"])
    db.add_barber("Barber 2", tenant_id=tenant["id"])
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], max_barber=1)
    free = billing_db.get_package(free["id"])

    pelanggaran = billing_limits.evaluasi_downgrade(tenant["id"], free)
    assert len(pelanggaran) == 1
    assert "barber aktif" in pelanggaran[0]


# ============================= Endpoint HTTP =============================

def test_downgrade_berhasil_saat_pemakaian_di_bawah_limit(app_client):
    tenant, headers = _owner_login(app_client)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], urutan=1, max_barber=10)
    subscription_db.update_package(tenant["id"], "enterprise")  # tenant default SUDAH punya baris subscription sejak boot
    enterprise = billing_db.get_package_by_kode("enterprise")
    billing_db.update_package(enterprise["id"], urutan=5)

    r = app_client.post("/api/billing/downgrade", headers=headers, json={"package_id": pro["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["package"] == "pro"

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["package"] == "pro"


def test_downgrade_diblokir_saat_pemakaian_melebihi_limit(app_client):
    tenant, headers = _owner_login(app_client)
    for i in range(3):
        db.add_barber(f"Barber {i}", tenant_id=tenant["id"])

    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], urutan=1, max_barber=2)
    subscription_db.update_package(tenant["id"], "enterprise")  # tenant default SUDAH punya baris subscription sejak boot
    enterprise = billing_db.get_package_by_kode("enterprise")
    billing_db.update_package(enterprise["id"], urutan=5)

    r = app_client.post("/api/billing/downgrade", headers=headers, json={"package_id": pro["id"]})
    assert r.status_code == 422
    assert "diblokir" in r.json()["detail"]
    assert "barber aktif" in r.json()["detail"]

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["package"] == "enterprise"  # TIDAK berubah


def test_downgrade_tidak_menonaktifkan_apa_pun_secara_otomatis(app_client):
    """Regresi langsung dari keputusan eksplisit: TIDAK ADA penonaktifan
    barber otomatis -- downgrade yang diblokir harus 100% tanpa efek
    samping, ketiga barber tetap aktif persis seperti sebelumnya."""
    tenant, headers = _owner_login(app_client)
    ids = [db.add_barber(f"Barber {i}", tenant_id=tenant["id"]) for i in range(3)]

    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], urutan=1, max_barber=1)
    subscription_db.update_package(tenant["id"], "enterprise")  # tenant default SUDAH punya baris subscription sejak boot
    enterprise = billing_db.get_package_by_kode("enterprise")
    billing_db.update_package(enterprise["id"], urutan=5)

    app_client.post("/api/billing/downgrade", headers=headers, json={"package_id": pro["id"]})

    for bid in ids:
        assert db.get_barber(bid)["aktif"] == 1


def test_downgrade_ke_urutan_lebih_tinggi_ditolak_sebagai_upgrade(app_client):
    tenant, headers = _owner_login(app_client)
    subscription_db.update_package(tenant["id"], "free")  # tenant default SUDAH punya baris subscription sejak boot
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], urutan=1)
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], urutan=3)

    r = app_client.post("/api/billing/downgrade", headers=headers, json={"package_id": pro["id"]})
    assert r.status_code == 422
    assert "upgrade" in r.json()["detail"].lower()

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["package"] == "free"


def test_downgrade_paket_tidak_ada_422(app_client):
    tenant, headers = _owner_login(app_client)
    r = app_client.post("/api/billing/downgrade", headers=headers, json={"package_id": 999999})
    assert r.status_code == 422


def test_downgrade_paket_nonaktif_422(app_client):
    tenant, headers = _owner_login(app_client)
    basic = billing_db.get_package_by_kode("basic")
    billing_db.update_package(basic["id"], aktif=False)

    r = app_client.post("/api/billing/downgrade", headers=headers, json={"package_id": basic["id"]})
    assert r.status_code == 422


def test_downgrade_tenant_lain_tidak_terpengaruh(two_tenants):
    import auth_db as _auth_db
    _auth_db.tambah_user("ownerA2", "passwordA123", role="admin", tenant_id=two_tenants["tenant_a"])
    headers_a = _login(two_tenants["client"], "ownerA2", "passwordA123")

    subscription_db.create_default_subscription(two_tenants["tenant_a"], package="enterprise", status="active")
    subscription_db.create_default_subscription(two_tenants["tenant_b"], package="enterprise", status="active")
    pro = billing_db.get_package_by_kode("pro")
    billing_db.update_package(pro["id"], urutan=1)
    enterprise = billing_db.get_package_by_kode("enterprise")
    billing_db.update_package(enterprise["id"], urutan=5)

    r = two_tenants["client"].post("/api/billing/downgrade", headers=headers_a, json={"package_id": pro["id"]})
    assert r.status_code == 200, r.text

    assert subscription_db.get_subscription(two_tenants["tenant_a"])["package"] == "pro"
    assert subscription_db.get_subscription(two_tenants["tenant_b"])["package"] == "enterprise"
