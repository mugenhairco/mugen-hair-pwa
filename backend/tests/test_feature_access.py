"""
test_feature_access.py — FONDASI Multi-Tenant Phase 4 lanjutan: Feature Gating per Paket
=============================================================================
Cakupan: tenant_has_feature() (unit), require_feature() melewatkan superadmin
tanpa syarat (unit langsung memanggil dependency-nya, tidak lewat HTTP --
tidak ada endpoint yang mengizinkan role superadmin DAN digerbang
require_feature sekaligus untuk diuji end-to-end), penegakan endpoint
(export_pdf lewat /api/uang-kas/pdf, salah satu dari 14 endpoint PDF yang
digerbang -- polanya identik untuk 13 lainnya; booking_online + qris lewat
routers/booking.py), dan yang PALING PENTING: propagasi langsung (live
propagation) -- mengubah penugasan fitur lewat endpoint superadmin yang
SUDAH ADA (PUT /api/superadmin/billing/packages/{id}/features, pola sama
seperti test_billing.py) langsung berlaku di panggilan BERIKUTNYA, TANPA
restart/deploy ulang -- membuktikan feature_access.py tidak menyimpan cache
apa pun di lapisan server.

CATATAN PENTING soal fixture app_client di sini: billing_db.seed_default_
package_features() (dipanggil main.py on_startup(), lihat docstring
lengkapnya di billing_db.py) SUDAH otomatis meng-assign booking_online/
qris/export_pdf ke KEEMPAT paket default sejak boot pertama -- supaya
instalasi lama (sebelum Feature Gating ini ada) tidak tiba-tiba kehilangan
fitur yang sebelumnya selalu menyala. Konsekuensinya: setiap test di bawah
yang ingin membuktikan skenario "paket TIDAK punya fitur ini" harus
EKSPLISIT mencabutnya dulu lewat _set_fitur_paket_persis() (BUKAN
mengasumsikan paket baru mulai kosong)."""

import billing_db
import feature_access
import subscription_db


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    import auth_db
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _set_fitur_paket_persis(client, headers, package_kode: str, *fitur_kodes):
    """Pola sama persis seperti test_billing.py::test_superadmin_centang_fitur_untuk_paket
    -- lewat endpoint HTTP superadmin sungguhan (bukan panggil billing_db
    langsung), supaya test ini juga membuktikan jalur propagasinya nyata.
    MENGGANTI SELURUH daftar fitur paket ini persis jadi `fitur_kodes` yang
    dikirim (termasuk mengosongkan total kalau dipanggil tanpa argumen) --
    dipakai untuk MENCABUT fitur real-default (lihat catatan modul di atas)
    supaya skenario "paket ini tidak punya fitur X" bisa diuji secara
    eksplisit, dan untuk MEMBERI fitur guna membuktikan propagasi langsung."""
    paket = billing_db.get_package_by_kode(package_kode)
    ids = [billing_db.get_feature_by_kode(k)["id"] for k in fitur_kodes]
    r = client.put(f"/api/superadmin/billing/packages/{paket['id']}/features", headers=headers,
                    json={"feature_ids": ids})
    assert r.status_code == 200, r.text


# ============================= tenant_has_feature() (unit) =============================

def test_tenant_tanpa_baris_subscription_tidak_punya_fitur_apa_pun(single_tenant):
    """tenant_db.buat_tenant() (dipakai fixture ini) TIDAK membuat baris
    tenant_subscriptions -- fail-CLOSED (beda dari billing_limits.py yang
    fail-open untuk limit angka), lihat docstring feature_access.py."""
    assert feature_access.tenant_has_feature(single_tenant["tenant_id"], "export_pdf") is False


def test_tenant_dengan_paket_setelah_fitur_dicabut(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    free = billing_db.get_package_by_kode("free")
    billing_db.set_package_features(free["id"], [])  # cabut fitur real-default (lihat catatan modul)
    assert feature_access.tenant_has_feature(single_tenant["tenant_id"], "export_pdf") is False


def test_tenant_dengan_paket_yang_punya_fitur(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    free = billing_db.get_package_by_kode("free")
    export_pdf = billing_db.get_feature_by_kode("export_pdf")
    billing_db.set_package_features(free["id"], [export_pdf["id"]])
    assert feature_access.tenant_has_feature(single_tenant["tenant_id"], "export_pdf") is True


# ============================= require_feature() superadmin bypass (unit) =============================

def test_require_feature_selalu_meloloskan_superadmin_walau_tanpa_tenant():
    from auth import require_feature
    dep = require_feature("export_pdf")
    user = {"role": "superadmin", "tenant_id": None, "username": "superadmin1"}
    assert dep(user=user) is user


# ============================= Endpoint PDF (export_pdf) =============================

def test_pdf_endpoint_403_upgrade_required_tanpa_fitur_export_pdf(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free")  # cabut semua fitur real-default

    r = single_tenant["client"].get("/api/uang-kas/pdf", headers=single_tenant["headers"])
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["upgrade_required"] is True
    assert detail["feature"] == "export_pdf"


def test_pdf_endpoint_sukses_setelah_fitur_diassign_lewat_superadmin_tanpa_restart(app_client):
    """Ini test propagasi langsung yang diminta plan: cabut fitur -> 403,
    assign lagi lewat endpoint superadmin yang SUDAH ADA (bukan restart/
    deploy ulang apa pun) -> panggilan BERIKUTNYA langsung 200."""
    import tenant_db
    import auth_db

    tenant_id = tenant_db.buat_tenant("test-toko-live", "Test Toko Live")
    auth_db.tambah_user("ownerlive", "passwordLive123", role="admin", tenant_id=tenant_id)
    r = app_client.post("/api/auth/login", json={"username": "ownerlive", "password": "passwordLive123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    subscription_db.create_default_subscription(tenant_id, package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(app_client)
    _set_fitur_paket_persis(app_client, superadmin_headers, "free")  # cabut semua dulu

    r1 = app_client.get("/api/uang-kas/pdf", headers=headers)
    assert r1.status_code == 403

    _set_fitur_paket_persis(app_client, superadmin_headers, "free", "export_pdf")

    r2 = app_client.get("/api/uang-kas/pdf", headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.headers["content-type"] == "application/pdf"


def test_pdf_endpoint_akun_lain_paket_lain_tidak_ikut_terpengaruh(two_tenants):
    """Cabut export_pdf dari paket tenant B saja -- tenant A (paket
    berbeda, masih punya fitur real-default bawaan) tidak ikut terpengaruh."""
    subscription_db.create_default_subscription(two_tenants["tenant_a"], package="free", status="active")
    subscription_db.create_default_subscription(two_tenants["tenant_b"], package="basic", status="active")
    superadmin_headers = _buat_superadmin_dan_login(two_tenants["client"])
    _set_fitur_paket_persis(two_tenants["client"], superadmin_headers, "basic")  # cabut semua dari basic

    ra = two_tenants["client"].get("/api/uang-kas/pdf", headers=two_tenants["headers_a"])
    assert ra.status_code == 200, ra.text  # free masih punya fitur real-default bawaan

    rb = two_tenants["client"].get("/api/uang-kas/pdf", headers=two_tenants["headers_b"])
    assert rb.status_code == 403


# ============================= Booking Online + QRIS (routers/booking.py) =============================

def test_public_pengaturan_booking_online_false_tanpa_fitur(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free")  # cabut semua

    r = single_tenant["client"].get("/api/public/booking/pengaturan", params={"tenant": "test-toko"})
    assert r.status_code == 200, r.text
    assert r.json() == {"booking_online": False}


def test_public_pengaturan_booking_online_true_dengan_fitur_real_default(single_tenant):
    """Fitur real-default sudah otomatis menyala sejak boot (lihat catatan
    modul) -- TIDAK perlu assign manual apa pun untuk skenario "menyala"."""
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")

    r = single_tenant["client"].get("/api/public/booking/pengaturan", params={"tenant": "test-toko"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["booking_online"] is True
    assert "jam_mulai" in data or "maksimal_hari_kedepan" in data  # payload penuh, bukan short-circuit


def test_public_buat_booking_403_tanpa_fitur_booking_online(single_tenant):
    """Lapisan pertahanan kedua -- panggilan langsung ke endpoint POST tanpa
    lewat wizard /book sekalipun (public_pengaturan sudah menyembunyikannya
    dari frontend, tapi endpoint publik ini masih bisa dipanggil langsung)."""
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free")  # cabut semua

    body = {
        "barber_id": 1, "tanggal": "2026-08-10", "jam_mulai": "10:00",
        "service_ids": [1], "customer_nama": "Budi", "customer_whatsapp": "081234567890",
        "metode_pembayaran": "tunai",
    }
    r = single_tenant["client"].post("/api/public/booking", params={"tenant": "test-toko"}, json=body)
    assert r.status_code == 403


def test_public_qris_404_tanpa_fitur_qris(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free")  # cabut semua

    r = single_tenant["client"].get("/api/public/booking/qris", params={"tenant": "test-toko"})
    assert r.status_code == 404


def test_owner_upload_qris_403_tanpa_fitur_qris(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free")  # cabut semua

    r = single_tenant["client"].delete("/api/booking/qris", headers=single_tenant["headers"])
    assert r.status_code == 403
    assert r.json()["detail"]["feature"] == "qris"


def test_owner_hapus_qris_sukses_dengan_fitur_qris_real_default(single_tenant):
    """Fitur real-default sudah otomatis menyala sejak boot -- TIDAK perlu
    assign manual apa pun untuk skenario "menyala"."""
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")

    r = single_tenant["client"].delete("/api/booking/qris", headers=single_tenant["headers"])
    assert r.status_code == 200, r.text
