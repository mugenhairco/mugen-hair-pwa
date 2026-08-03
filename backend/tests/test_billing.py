"""
test_billing.py — FONDASI Multi-Tenant Phase 4: Billing & Payment (Midtrans)
=============================================================================
Cakupan modul pertama Phase 4 (konfigurasi paket): seed 4 baris default saat
boot, CRUD Super Admin (nama/harga/durasi/status/urutan/deskripsi/limit),
`kode` tidak bisa diubah, validasi, isolasi endpoint dari akun tenant biasa,
dan audit log."""

import billing_db


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    import auth_db
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    return _login(client, username, password)


# ============================= Seed default =============================

def test_boot_seed_4_paket_default(app_client):
    paket = billing_db.list_packages()
    kode = {p["kode"] for p in paket}
    assert kode == {"free", "basic", "pro", "enterprise"}
    free = billing_db.get_package_by_kode("free")
    assert free["harga"] == 0
    assert free["aktif"] == 1
    assert free["durasi_hari"] == 30


def test_seed_idempotent_tidak_menimpa_perubahan(app_client):
    free = billing_db.get_package_by_kode("free")
    billing_db.update_package(free["id"], harga=123456)

    billing_db.seed_default_packages()

    free2 = billing_db.get_package_by_kode("free")
    assert free2["harga"] == 123456


# ============================= CRUD Super Admin =============================

def test_superadmin_list_packages(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/superadmin/billing/packages", headers=headers)
    assert r.status_code == 200, r.text
    kode = {p["kode"] for p in r.json()}
    assert kode == {"free", "basic", "pro", "enterprise"}


def test_akun_tenant_biasa_ditolak_endpoint_superadmin_billing(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/billing/packages", headers=two_tenants["headers_a"])
    assert r.status_code == 403


def test_superadmin_ubah_atribut_paket(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    basic = billing_db.get_package_by_kode("basic")

    r = app_client.put(f"/api/superadmin/billing/packages/{basic['id']}", headers=headers, json={
        "nama": "Basic Plus", "harga": 150000, "durasi_hari": 30, "aktif": True,
        "urutan": 2, "deskripsi": "Paket untuk toko kecil",
        "max_barber": 3, "max_user": 5, "max_layanan": 20, "max_booking": 500, "max_cabang": 1,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nama"] == "Basic Plus"
    assert data["harga"] == 150000
    assert data["max_barber"] == 3
    assert data["max_cabang"] == 1
    assert data["kode"] == "basic"  # kode TIDAK berubah


def test_superadmin_nonaktifkan_paket(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    pro = billing_db.get_package_by_kode("pro")

    r = app_client.put(f"/api/superadmin/billing/packages/{pro['id']}", headers=headers, json={"aktif": False})
    assert r.status_code == 200, r.text
    assert r.json()["aktif"] == 0

    aktif_saja = billing_db.list_packages(hanya_aktif=True)
    assert "pro" not in {p["kode"] for p in aktif_saja}


def test_superadmin_kode_tidak_bisa_diubah_lewat_endpoint(app_client):
    """PackageUpdateBody sengaja TIDAK punya field `kode` sama sekali --
    body ekstra seperti ini diabaikan FastAPI/Pydantic, bukan error."""
    headers = _buat_superadmin_dan_login(app_client)
    free = billing_db.get_package_by_kode("free")
    r = app_client.put(f"/api/superadmin/billing/packages/{free['id']}", headers=headers,
                        json={"nama": "Free Baru", "kode": "hacked"})
    assert r.status_code == 200, r.text
    assert r.json()["kode"] == "free"


def test_superadmin_ubah_paket_tidak_ada_404(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.put("/api/superadmin/billing/packages/999999", headers=headers, json={"nama": "X"})
    assert r.status_code == 422  # ValueError billing_db -> 422 (bukan 404, sesuai routers/billing.py)


def test_superadmin_harga_negatif_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    free = billing_db.get_package_by_kode("free")
    r = app_client.put(f"/api/superadmin/billing/packages/{free['id']}", headers=headers, json={"harga": -1000})
    assert r.status_code == 422


def test_superadmin_durasi_kurang_dari_1_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    free = billing_db.get_package_by_kode("free")
    r = app_client.put(f"/api/superadmin/billing/packages/{free['id']}", headers=headers, json={"durasi_hari": 0})
    assert r.status_code == 422


def test_superadmin_limit_negatif_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    free = billing_db.get_package_by_kode("free")
    r = app_client.put(f"/api/superadmin/billing/packages/{free['id']}", headers=headers, json={"max_barber": -1})
    assert r.status_code == 422


def test_superadmin_limit_null_berarti_tidak_dibatasi(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    enterprise = billing_db.get_package_by_kode("enterprise")
    r = app_client.put(f"/api/superadmin/billing/packages/{enterprise['id']}", headers=headers,
                        json={"max_barber": None})
    assert r.status_code == 200, r.text
    assert r.json()["max_barber"] is None


# ============================= Audit log =============================

def test_audit_log_mencatat_ubah_paket_billing(app_client):
    headers = _buat_superadmin_dan_login(app_client, username="auditor1")
    free = billing_db.get_package_by_kode("free")

    app_client.put(f"/api/superadmin/billing/packages/{free['id']}", headers=headers, json={"harga": 50000})

    r = app_client.get("/api/superadmin/audit-log", headers=headers)
    aksi = [e["aksi"] for e in r.json()]
    assert aksi[0] == "ubah_paket_billing"


# ============================= Validasi billing_db langsung =============================

def test_update_package_nama_kosong_ditolak():
    free = billing_db.get_package_by_kode("free")
    try:
        billing_db.update_package(free["id"], nama="   ")
        assert False, "harus melempar ValueError"
    except ValueError:
        pass


# ============================= Katalog Fitur =============================

def test_boot_seed_katalog_fitur_default(app_client):
    fitur = billing_db.list_features()
    kode = {f["kode"] for f in fitur}
    assert "booking_online" in kode
    assert "qris" in kode
    assert len(fitur) == 13


def test_seed_fitur_idempotent_tidak_menimpa_perubahan(app_client):
    qris = billing_db.get_feature_by_kode("qris")
    billing_db.update_feature(qris["id"], nama="QRIS Custom")

    billing_db.seed_default_features()

    qris2 = billing_db.get_feature_by_kode("qris")
    assert qris2["nama"] == "QRIS Custom"


def test_superadmin_list_features(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/superadmin/billing/features", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 13


def test_akun_tenant_biasa_ditolak_endpoint_features(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/billing/features", headers=two_tenants["headers_a"])
    assert r.status_code == 403


def test_superadmin_tambah_fitur_baru(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.post("/api/superadmin/billing/features", headers=headers, json={
        "kode": "sms_reminder", "nama": "SMS Reminder", "deskripsi": "Pengingat lewat SMS",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kode"] == "sms_reminder"
    assert data["aktif"] == 1

    r2 = app_client.get("/api/superadmin/billing/features", headers=headers)
    assert len(r2.json()) == 14


def test_superadmin_tambah_fitur_kode_duplikat_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.post("/api/superadmin/billing/features", headers=headers,
                         json={"kode": "qris", "nama": "QRIS Duplikat"})
    assert r.status_code == 422


def test_superadmin_tambah_fitur_kode_kosong_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.post("/api/superadmin/billing/features", headers=headers,
                         json={"kode": "   ", "nama": "Tanpa Kode"})
    assert r.status_code == 422


def test_superadmin_ubah_fitur(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    fitur = billing_db.get_feature_by_kode("api")

    r = app_client.put(f"/api/superadmin/billing/features/{fitur['id']}", headers=headers, json={
        "nama": "API Access", "deskripsi": "Akses REST API", "urutan": 99,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nama"] == "API Access"
    assert data["kode"] == "api"  # kode TIDAK berubah


def test_superadmin_nonaktifkan_fitur(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    fitur = billing_db.get_feature_by_kode("priority_support")

    r = app_client.put(f"/api/superadmin/billing/features/{fitur['id']}", headers=headers, json={"aktif": False})
    assert r.status_code == 200, r.text
    assert r.json()["aktif"] == 0

    aktif_saja = billing_db.list_features(hanya_aktif=True)
    assert "priority_support" not in {f["kode"] for f in aktif_saja}


def test_superadmin_hapus_fitur(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    fitur = billing_db.get_feature_by_kode("multi_cabang")

    r = app_client.delete(f"/api/superadmin/billing/features/{fitur['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert billing_db.get_feature(fitur["id"]) is None


def test_hapus_fitur_melepas_dari_semua_paket_cascade(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    fitur = billing_db.get_feature_by_kode("google_calendar")
    basic = billing_db.get_package_by_kode("basic")
    pro = billing_db.get_package_by_kode("pro")
    billing_db.set_package_features(basic["id"], [fitur["id"]])
    billing_db.set_package_features(pro["id"], [fitur["id"]])

    r = app_client.delete(f"/api/superadmin/billing/features/{fitur['id']}", headers=headers)
    assert r.status_code == 200, r.text

    assert billing_db.get_package_features(basic["id"]) == []
    assert billing_db.get_package_features(pro["id"]) == []


def test_hapus_fitur_tidak_ada_422(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.delete("/api/superadmin/billing/features/999999", headers=headers)
    assert r.status_code == 422


# ============================= Penugasan Fitur per Paket (checkbox) =============================

def test_superadmin_centang_fitur_untuk_paket(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    pro = billing_db.get_package_by_kode("pro")
    booking = billing_db.get_feature_by_kode("booking_online")
    qris = billing_db.get_feature_by_kode("qris")

    r = app_client.put(f"/api/superadmin/billing/packages/{pro['id']}/features", headers=headers,
                        json={"feature_ids": [booking["id"], qris["id"]]})
    assert r.status_code == 200, r.text
    kode = {f["kode"] for f in r.json()}
    assert kode == {"booking_online", "qris"}

    r2 = app_client.get(f"/api/superadmin/billing/packages/{pro['id']}/features", headers=headers)
    assert {f["kode"] for f in r2.json()} == {"booking_online", "qris"}


def test_ubah_penugasan_fitur_mengganti_seluruh_daftar_lama(app_client):
    pro = billing_db.get_package_by_kode("pro")
    booking = billing_db.get_feature_by_kode("booking_online")
    qris = billing_db.get_feature_by_kode("qris")
    api = billing_db.get_feature_by_kode("api")

    billing_db.set_package_features(pro["id"], [booking["id"], qris["id"]])
    hasil = billing_db.set_package_features(pro["id"], [api["id"]])

    assert {f["kode"] for f in hasil} == {"api"}


def test_centang_fitur_tidak_ada_di_katalog_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    pro = billing_db.get_package_by_kode("pro")
    r = app_client.put(f"/api/superadmin/billing/packages/{pro['id']}/features", headers=headers,
                        json={"feature_ids": [999999]})
    assert r.status_code == 422


def test_centang_fitur_paket_tidak_ada_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    booking = billing_db.get_feature_by_kode("booking_online")
    r = app_client.put("/api/superadmin/billing/packages/999999/features", headers=headers,
                        json={"feature_ids": [booking["id"]]})
    assert r.status_code == 422


def test_dua_paket_beda_bisa_punya_fitur_berbeda(app_client):
    free = billing_db.get_package_by_kode("free")
    enterprise = billing_db.get_package_by_kode("enterprise")
    booking = billing_db.get_feature_by_kode("booking_online")
    api = billing_db.get_feature_by_kode("api")

    billing_db.set_package_features(free["id"], [booking["id"]])
    billing_db.set_package_features(enterprise["id"], [booking["id"], api["id"]])

    assert {f["kode"] for f in billing_db.get_package_features(free["id"])} == {"booking_online"}
    assert {f["kode"] for f in billing_db.get_package_features(enterprise["id"])} == {"booking_online", "api"}


def test_audit_log_mencatat_perubahan_fitur(app_client):
    headers = _buat_superadmin_dan_login(app_client, username="auditor2")
    pro = billing_db.get_package_by_kode("pro")
    qris = billing_db.get_feature_by_kode("qris")

    app_client.post("/api/superadmin/billing/features", headers=headers,
                     json={"kode": "custom_fitur", "nama": "Fitur Kustom"})
    app_client.put(f"/api/superadmin/billing/packages/{pro['id']}/features", headers=headers,
                    json={"feature_ids": [qris["id"]]})

    r = app_client.get("/api/superadmin/audit-log", headers=headers)
    aksi = [e["aksi"] for e in r.json()]
    assert aksi[0] == "ubah_fitur_paket_billing"
    assert aksi[1] == "tambah_fitur_billing"
