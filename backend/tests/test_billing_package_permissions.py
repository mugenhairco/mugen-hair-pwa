"""test_billing_package_permissions.py — Work #2 (Superadmin Package
Permission Tree, diminta Owner): batas LUAR per-paket, memakai POHON MENU
YANG SAMA PERSIS dipakai Role Owner tenant (permissions.PERMISSION_TREE)
untuk menentukan menu/tab/sub-item APA SAJA yang tersedia SAMA SEKALI
untuk tenant paket ini -- lihat billing_db.py::subscription_package_
permissions, feature_access.tenant_has_menu_access(), auth.py::
require_permission()/require_menu_read() (SEKARANG dua gerbang berurutan:
package lebih dulu, lalu Role).

File ini SENGAJA OVERRIDE fixture autouse `_default_barber_app_dan_
absensi_aktif` (conftest.py) jadi no-op (TIDAK memonkeypatch feature_
access.tenant_has_menu_access() ke selalu True) -- di sinilah perilaku
ASLI (fail-closed tanpa grandfather untuk paket BARU, full-access untuk
paket yang SUDAH ADA sebelum Work #2) justru diuji, pola SAMA PERSIS
test_feature_access.py untuk tenant_has_feature()."""

import pytest

import auth_db
import billing_db
import feature_access
import permissions
import subscription_db
import user_roles_db


@pytest.fixture(autouse=True)
def _default_barber_app_dan_absensi_aktif():
    """OVERRIDE no-op -- lihat docstring modul."""
    yield


def _buat_superadmin_dan_login(client, username="superadminppt", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ============================= Grandfather (paket yang sudah ada) =============================

def test_paket_lama_otomatis_akses_penuh_setelah_grandfather(app_client):
    """migrasi_grandfather_package_permissions() (dipanggil main.py saat
    startup, SUDAH jalan otomatis lewat fixture app_client) -- SETIAP
    paket default (free/basic/pro/enterprise) harus punya SELURUH
    permissions.PERMISSION_KEYS tercentang, KECUALI izin_absensi_lihat +
    keturunannya -- "absensi" SENGAJA fail-closed TANPA grandfather sejak
    awal (keputusan eksplisit Owner, beda dari seluruh menu LAIN yang
    sebelum Work #2 memang selalu terbuka tanpa gate apa pun sama sekali),
    jadi blanket True untuk key ini justru akan DIAM-DIAM membuka Absensi
    untuk paket yang Owner sengaja belum mengaktifkannya -- lihat
    billing_db.py::migrasi_grandfather_package_permissions()."""
    kunci_absensi = {"izin_absensi_lihat"} | permissions._descendants("izin_absensi_lihat")
    kunci_diharapkan = permissions.PERMISSION_KEYS - kunci_absensi
    for kode in ("free", "basic", "pro", "enterprise"):
        paket = billing_db.get_package_by_kode(kode)
        aktif = billing_db.get_package_permission_keys(paket["id"])
        assert aktif == kunci_diharapkan, f"paket {kode} tidak akses penuh (minus Absensi)"
        assert not (aktif & kunci_absensi), f"paket {kode} seharusnya TIDAK punya akses Absensi"


def test_tenant_di_paket_lama_bisa_akses_menu_apa_pun(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")
    r = client.get("/api/booking", headers=headers)
    assert r.status_code == 200, r.text


# ============================= Paket BARU (fail-closed) =============================

def test_tenant_tanpa_baris_subscription_tidak_punya_akses_apa_pun(single_tenant):
    assert feature_access.tenant_has_menu_access(single_tenant["tenant_id"], "izin_booking_lihat") is False


def test_package_permission_keys_kosong_untuk_paket_belum_pernah_diisi(app_client):
    """Simulasikan paket yang baru ADA setelah migrasi grandfather pertama
    jalan (katalog paket tetap 4 kode baku -- billing_db.PACKAGE_VALID --
    jadi disimulasikan di sini lewat set_package_permission_keys ke set
    kosong langsung, pola sama seperti Role baru di user_roles_db.py)
    -- TIDAK ADA akses apa pun sampai Super Admin mencentang manual."""
    free = billing_db.get_package_by_kode("free")
    billing_db.set_package_permission_keys(free["id"], set())
    assert billing_db.get_package_permission_keys(free["id"]) == set()


def test_tenant_diblokir_kalau_paket_tidak_punya_menu_ini(single_tenant):
    """Super Admin mencabut izin_booking_lihat dari paket "free" -- tenant
    di paket itu SEKARANG ditolak 403 walau Owner (bukan staff) yang
    memanggil -- BATAS LUAR berlaku untuk SEMUA role termasuk Owner."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")

    free = billing_db.get_package_by_kode("free")
    semua = billing_db.get_package_permission_keys(free["id"])
    billing_db.set_package_permission_keys(free["id"], semua - {"izin_booking_lihat"})

    r = client.get("/api/booking", headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"]["upgrade_required"] is True


def test_cabut_izin_booking_lihat_tidak_memengaruhi_menu_lain(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")

    free = billing_db.get_package_by_kode("free")
    semua = billing_db.get_package_permission_keys(free["id"])
    billing_db.set_package_permission_keys(free["id"], semua - {"izin_booking_lihat"})

    r = client.get("/api/produk", headers=headers)
    assert r.status_code == 200, r.text


# ============================= Dua gerbang berurutan: package lalu Role =============================

def test_package_lolos_role_tidak_staff_tetap_ditolak(single_tenant):
    """Paket punya akses penuh (grandfather), TAPI Role staff belum
    dicentang -- tetap 403 (gerbang KEDUA, Role, yang menolak)."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")

    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    auth_db.tambah_user("staffppt1", "passwordS123", role="staff", tenant_id=tenant_id, custom_role_id=role["id"])
    r_login = client.post("/api/auth/login", json={"username": "staffppt1", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r = client.get("/api/booking", headers=headers_staff)
    assert r.status_code == 403


def test_package_ditolak_role_boleh_tetap_ditolak(single_tenant):
    """Role staff SUDAH dicentang penuh, TAPI paket tenant TIDAK punya
    menu ini -- tetap 403 (gerbang PERTAMA, package, yang menolak duluan)."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")

    free = billing_db.get_package_by_kode("free")
    semua = billing_db.get_package_permission_keys(free["id"])
    billing_db.set_package_permission_keys(free["id"], semua - {"izin_booking_lihat"})

    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    client.put(f"/api/pengaturan/user-roles/{role['id']}/permissions",
               json={"izin": {"izin_booking_lihat": True}}, headers=headers)
    auth_db.tambah_user("staffppt2", "passwordS123", role="staff", tenant_id=tenant_id, custom_role_id=role["id"])
    r_login = client.post("/api/auth/login", json={"username": "staffppt2", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r = client.get("/api/booking", headers=headers_staff)
    assert r.status_code == 403


def test_package_dan_role_keduanya_boleh_berhasil(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")

    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    client.put(f"/api/pengaturan/user-roles/{role['id']}/permissions",
               json={"izin": {"izin_booking_lihat": True}}, headers=headers)
    auth_db.tambah_user("staffppt3", "passwordS123", role="staff", tenant_id=tenant_id, custom_role_id=role["id"])
    r_login = client.post("/api/auth/login", json={"username": "staffppt3", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r = client.get("/api/booking", headers=headers_staff)
    assert r.status_code == 200, r.text


# ============================= Endpoint Superadmin CRUD =============================

def test_superadmin_get_permission_tree(two_tenants):
    client = two_tenants["client"]
    headers_super = _buat_superadmin_dan_login(client)
    r = client.get("/api/superadmin/billing/permission-tree", headers=headers_super)
    assert r.status_code == 200, r.text
    assert set(n["key"] for n in r.json()["nodes"]) == permissions.PERMISSION_KEYS


def test_superadmin_get_dan_put_package_permissions(two_tenants):
    client = two_tenants["client"]
    headers_super = _buat_superadmin_dan_login(client)
    free = billing_db.get_package_by_kode("free")

    r = client.get(f"/api/superadmin/billing/packages/{free['id']}/permissions", headers=headers_super)
    assert r.status_code == 200, r.text
    assert r.json()["izin_kasbon"] is True  # grandfather -- akses penuh

    r2 = client.put(f"/api/superadmin/billing/packages/{free['id']}/permissions", headers=headers_super,
                     json={"izin": {"izin_kasbon": False}})
    assert r2.status_code == 200, r2.text
    assert r2.json()["izin_kasbon"] is False
    assert r2.json()["izin_produk_lihat"] is True  # tidak ikut terpengaruh


def test_superadmin_put_package_permissions_cascade_uncheck(two_tenants):
    """Sama seperti permissions.set_bulk() Role -- mematikan node induk di
    PUT /packages/{id}/permissions ikut mematikan keturunannya."""
    client = two_tenants["client"]
    headers_super = _buat_superadmin_dan_login(client)
    free = billing_db.get_package_by_kode("free")

    r = client.put(f"/api/superadmin/billing/packages/{free['id']}/permissions", headers=headers_super,
                    json={"izin": {"izin_booking_lihat": False}})
    assert r.status_code == 200, r.text
    assert r.json()["izin_booking_lihat"] is False
    assert r.json()["izin_booking_list"] is False  # keturunan ikut mati
    assert r.json()["izin_booking_hapus"] is False  # cucu ikut mati


def test_superadmin_put_package_permissions_key_tidak_dikenal_ditolak(two_tenants):
    client = two_tenants["client"]
    headers_super = _buat_superadmin_dan_login(client)
    free = billing_db.get_package_by_kode("free")
    r = client.put(f"/api/superadmin/billing/packages/{free['id']}/permissions", headers=headers_super,
                    json={"izin": {"izin_tidak_ada": True}})
    assert r.status_code == 422


def test_owner_tidak_bisa_akses_endpoint_superadmin_permission_tree(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/superadmin/billing/permission-tree", headers=headers)
    assert r.status_code == 403


# ============================= Kode fitur dekoratif/absorbed terhapus =============================

def test_lima_kode_dekoratif_dan_dua_kode_absorbed_tidak_ada_di_katalog():
    kode_semua = {f["kode"] for f in billing_db.list_features()}
    dihapus = {"manajemen_bisnis", "manajemen_barber", "hak_akses_role",
               "manajemen_layanan", "pengaturan_komisi_gaji", "absensi", "whatsapp_reminder"}
    assert not (kode_semua & dihapus)


def test_empat_kode_sejajar_tetap_ada():
    kode_semua = {f["kode"] for f in billing_db.list_features()}
    assert kode_semua == {"booking_online", "export_pdf", "export_excel", "barber_app"}
