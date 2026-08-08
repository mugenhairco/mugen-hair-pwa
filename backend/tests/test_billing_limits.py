"""
test_billing_limits.py — FONDASI Multi-Tenant Phase 4: Penegakan Limit Pemakaian
=============================================================================
Cakupan billing_limits.py: limit NULL = tidak dibatasi, blokir tepat saat
mencapai batas (barber/user/layanan/booking bulan berjalan), booking yang
dibatalkan tidak memakan kuota, fail-open kalau tenant belum punya baris
subscription sama sekali, dan enforcement di lapisan router (HTTP 422)."""

import auth_db
import billing_db
import billing_limits
import booking_db
import database as db
import subscription_db
import tenant_db


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _tenant_default():
    return tenant_db.get_tenant_by_slug("mugen-hair-co")


# ============================= Unlimited (NULL) =============================

def test_unlimited_saat_limit_null(app_client):
    tenant = _tenant_default()
    for i in range(5):
        db.add_barber(f"Barber {i}", tenant_id=tenant["id"])
    billing_limits.pastikan_boleh_tambah_barber(tenant["id"])  # tidak melempar


def test_fail_open_tenant_tanpa_subscription(two_tenants):
    billing_limits.pastikan_boleh_tambah_barber(two_tenants["tenant_a"])
    billing_limits.pastikan_boleh_tambah_user(two_tenants["tenant_a"])
    billing_limits.pastikan_boleh_tambah_layanan(two_tenants["tenant_a"])
    billing_limits.pastikan_boleh_tambah_booking(two_tenants["tenant_a"])


# ============================= max_barber =============================

def test_barber_diblokir_saat_mencapai_limit(app_client):
    tenant = _tenant_default()
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], max_barber=2)

    db.add_barber("Barber 1", tenant_id=tenant["id"])
    billing_limits.pastikan_boleh_tambah_barber(tenant["id"])  # masih 1/2, boleh
    db.add_barber("Barber 2", tenant_id=tenant["id"])

    try:
        billing_limits.pastikan_boleh_tambah_barber(tenant["id"])
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "maksimal 2 barber" in str(e)


def test_barber_nonaktif_tidak_dihitung(app_client):
    tenant = _tenant_default()
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], max_barber=1)

    bid = db.add_barber("Barber Nonaktif", tenant_id=tenant["id"])
    db.update_barber(bid, aktif=False)
    billing_limits.pastikan_boleh_tambah_barber(tenant["id"])  # tidak melempar, barber nonaktif tidak dihitung


def test_http_tambah_barber_ditolak_saat_limit_tercapai(app_client):
    tenant = _tenant_default()
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], max_barber=1)
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    headers = _login(app_client, "owner1", "password123")

    r1 = app_client.post("/api/pengaturan/barber", headers=headers, json={"nama": "Barber A"})
    assert r1.status_code == 200, r1.text

    r2 = app_client.post("/api/pengaturan/barber", headers=headers, json={"nama": "Barber B"})
    assert r2.status_code == 422
    assert "maksimal 1 barber" in r2.json()["detail"]


# ============================= max_user =============================

def test_user_diblokir_saat_mencapai_limit(app_client):
    tenant = _tenant_default()
    free = billing_db.get_package_by_kode("free")
    jumlah_awal = len(auth_db.get_user_list(tenant_id=tenant["id"]))
    billing_db.update_package(free["id"], max_user=jumlah_awal + 1)

    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    try:
        billing_limits.pastikan_boleh_tambah_user(tenant["id"])
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "maksimal" in str(e)


def test_http_tambah_user_ditolak_saat_limit_tercapai(app_client):
    tenant = _tenant_default()
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    headers = _login(app_client, "owner1", "password123")

    free = billing_db.get_package_by_kode("free")
    jumlah_sekarang = len(auth_db.get_user_list(tenant_id=tenant["id"]))
    billing_db.update_package(free["id"], max_user=jumlah_sekarang)

    r = app_client.post("/api/pengaturan/user", headers=headers,
                         json={"username": "staffbaru", "password": "password123", "role": "staff"})
    assert r.status_code == 422
    assert "maksimal" in r.json()["detail"]


# ============================= max_layanan =============================

def test_layanan_diblokir_saat_mencapai_limit(app_client):
    # tenant default dapat 8 layanan bawaan (Dry Cut, dst) dari
    # database.py::init_db() -- SELALU pakai baseline jumlah SEKARANG + 1
    # (pola sama seperti test_user_diblokir_saat_mencapai_limit), bukan
    # angka tetap, supaya test ini tidak diam-diam salah asumsi jumlah awal.
    tenant = _tenant_default()
    free = billing_db.get_package_by_kode("free")
    jumlah_awal = len(db.get_services(hanya_aktif=True, tenant_id=tenant["id"]))
    billing_db.update_package(free["id"], max_layanan=jumlah_awal + 1)

    db.add_service("Potong Rambut", 50000, tenant_id=tenant["id"])
    try:
        billing_limits.pastikan_boleh_tambah_layanan(tenant["id"])
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "maksimal" in str(e)


def test_http_tambah_service_ditolak_saat_limit_tercapai(app_client):
    tenant = _tenant_default()
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant["id"])
    headers = _login(app_client, "owner1", "password123")

    free = billing_db.get_package_by_kode("free")
    jumlah_sekarang = len(db.get_services(hanya_aktif=True, tenant_id=tenant["id"]))
    billing_db.update_package(free["id"], max_layanan=jumlah_sekarang)

    r = app_client.post("/api/pengaturan/service", headers=headers,
                         json={"nama": "Cukur Jenggot", "harga": 30000})
    assert r.status_code == 422
    assert "maksimal" in r.json()["detail"]


# ============================= max_booking (per bulan berjalan) =============================

def _siapkan_barber_dan_service(tenant_id):
    barber_id = db.add_barber("Barber Booking", tenant_id=tenant_id)
    service_id = db.add_service("Potong Rambut", 50000, tenant_id=tenant_id)
    return barber_id, service_id


def test_booking_diblokir_saat_mencapai_limit_bulan_ini(app_client):
    tenant = _tenant_default()
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], max_booking=1)
    barber_id, service_id = _siapkan_barber_dan_service(tenant["id"])

    from datetime import timedelta
    from booking_db import _hari_ini_wib
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()

    booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                             service_ids=[service_id], customer_nama="Budi",
                             customer_whatsapp="081234567890", metode_pembayaran="transfer",
                             tenant_id=tenant["id"])

    try:
        billing_limits.pastikan_boleh_tambah_booking(tenant["id"])
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "maksimal 1 booking" in str(e)


def test_booking_dibatalkan_tidak_memakan_kuota(app_client):
    tenant = _tenant_default()
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], max_booking=1)
    barber_id, service_id = _siapkan_barber_dan_service(tenant["id"])

    from datetime import timedelta
    from booking_db import _hari_ini_wib
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()

    booking = booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                       service_ids=[service_id], customer_nama="Budi",
                                       customer_whatsapp="081234567890", metode_pembayaran="transfer",
                                       tenant_id=tenant["id"])
    booking_db.batalkan_booking(booking["id"])

    billing_limits.pastikan_boleh_tambah_booking(tenant["id"])  # tidak melempar


def test_http_public_booking_ditolak_saat_limit_tercapai(app_client):
    tenant = _tenant_default()
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], max_booking=1)
    barber_id, service_id = _siapkan_barber_dan_service(tenant["id"])

    from datetime import timedelta
    from booking_db import _hari_ini_wib
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()

    body = {
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "10:00",
        "service_ids": [service_id], "customer_nama": "Budi",
        "customer_whatsapp": "081234567890", "metode_pembayaran": "transfer",
    }
    # HOTFIX Migrasi Subdomain: endpoint publik TIDAK LAGI diam-diam
    # jatuh ke tenant default kalau ?tenant= kosong -- WAJIB eksplisit.
    r1 = app_client.post(f"/api/public/booking?tenant={tenant['slug']}", json=body)
    assert r1.status_code == 200, r1.text

    body["jam_mulai"] = "13:00"
    r2 = app_client.post(f"/api/public/booking?tenant={tenant['slug']}", json=body)
    assert r2.status_code == 422
    assert "maksimal 1 booking" in r2.json()["detail"]


def test_dua_tenant_kuota_booking_terpisah(two_tenants):
    subscription_db.create_default_subscription(two_tenants["tenant_a"], package="free", status="active")
    subscription_db.create_default_subscription(two_tenants["tenant_b"], package="free", status="active")
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], max_booking=1)

    # tenant_db.buat_tenant() (fixture two_tenants) TIDAK ikut men-seed
    # booking settings (beda dari tenant default yang dapat migrasi_booking()
    # saat boot) -- metode pembayaran "transfer" harus diaktifkan manual dulu
    # supaya buat_booking() di bawah tidak ditolak karena alasan LAIN.
    booking_db.update_payment_settings(metode_aktif=["transfer"], tenant_id=two_tenants["tenant_a"])

    barber_a, service_a = _siapkan_barber_dan_service(two_tenants["tenant_a"])

    from datetime import timedelta
    from booking_db import _hari_ini_wib
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()

    booking_db.buat_booking(barber_id=barber_a, tanggal=tanggal, jam_mulai="10:00",
                             service_ids=[service_a], customer_nama="Budi",
                             customer_whatsapp="081234567890", metode_pembayaran="transfer",
                             tenant_id=two_tenants["tenant_a"])

    try:
        billing_limits.pastikan_boleh_tambah_booking(two_tenants["tenant_a"])
        assert False, "harus melempar ValueError"
    except ValueError:
        pass

    billing_limits.pastikan_boleh_tambah_booking(two_tenants["tenant_b"])  # tenant lain, kuota terpisah
