"""test_role_custom.py — FITUR Role User Custom (diminta Owner)
=============================================================================
Cakupan: CRUD role (Owner-murni), checklist izin per role (fail-CLOSED,
BEDA dari default tenant yang banyak True by design -- lihat
user_roles_db.py), menempelkan akun staff ke role custom (saat dibuat
MAUPUN belakangan lewat PUT /user/{id}/role), propagasi ke pengecekan
izin sungguhan (endpoint yang sudah digerbang require_permission), staff
TANPA role custom tetap 100% memakai perilaku lama (kompatibel mundur),
dan penghapusan role yang masih terpakai TIDAK PERNAH memblokir/mengunci
staff (otomatis balik ke default, keputusan eksplisit Owner)."""

import auth_db
import permissions
import user_roles_db


def _buat_owner_dan_login(client, tenant_id, username="ownerrole", password="passwordO123"):
    auth_db.tambah_user(username, password, role="admin", tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_staff_dan_login(client, tenant_id, username="staffrole", password="passwordS123", custom_role_id=None):
    auth_db.tambah_user(username, password, role="staff", tenant_id=tenant_id, custom_role_id=custom_role_id)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ============================= CRUD Role (Owner-murni) =============================

def test_owner_buat_role(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["nama"] == "Kasir"
    assert r.json()["tenant_id"] == single_tenant["tenant_id"]


def test_staff_tidak_bisa_buat_role(single_tenant):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff_dan_login(client, tenant_id)
    r = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers_staff)
    assert r.status_code == 403


def test_barber_tidak_bisa_buat_role(single_tenant):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import database as db
    barber_id = db.add_barber("Barber Role", tenant_id=tenant_id)
    auth_db.tambah_user("barberrole", "passwordB123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "barberrole", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r.json()['token']}"}
    r2 = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers_barber)
    assert r2.status_code == 403


def test_owner_ganti_nama_role(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    r = client.put(f"/api/pengaturan/user-roles/{role['id']}", json={"nama": "Kasir Senior"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["nama"] == "Kasir Senior"


def test_owner_hapus_role(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    r = client.delete(f"/api/pengaturan/user-roles/{role['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert user_roles_db.get_role(role["id"]) is None


def test_role_tenant_lain_404(two_tenants):
    client = two_tenants["client"]
    role_a = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir A"}, headers=two_tenants["headers_a"]).json()
    r = client.get(f"/api/pengaturan/user-roles/{role_a['id']}/permissions", headers=two_tenants["headers_b"])
    assert r.status_code == 404
    r2 = client.delete(f"/api/pengaturan/user-roles/{role_a['id']}", headers=two_tenants["headers_b"])
    assert r2.status_code == 404


# ============================= Checklist izin per role =============================

def test_role_baru_mulai_kosong_fail_closed(single_tenant):
    """BEDA dari default tenant (banyak True by design) -- role custom baru
    TIDAK punya izin apa pun sampai Owner mencentang manual."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    r = client.get(f"/api/pengaturan/user-roles/{role['id']}/permissions", headers=headers)
    assert r.status_code == 200, r.text
    izin = r.json()
    assert izin["izin_kasbon"] is False
    assert izin["izin_booking_kelola"] is False  # walau default tenant utk ini True


def test_owner_centang_izin_role(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    r = client.put(f"/api/pengaturan/user-roles/{role['id']}/permissions", json={"izin": {"izin_kasbon": True}}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["izin_kasbon"] is True
    assert r.json()["izin_reimburse"] is False  # tidak ikut ter-set


# ============================= Penempelan role ke user =============================

def test_tambah_user_staff_dengan_custom_role_id(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    r = client.post("/api/pengaturan/user", json={
        "username": "kasir1", "password": "passwordK123", "role": "staff", "custom_role_id": role["id"],
    }, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["custom_role_id"] == role["id"]


def test_tambah_user_custom_role_id_untuk_barber_ditolak(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import database as db
    barber_id = db.add_barber("Barber X", tenant_id=tenant_id)
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    r = client.post("/api/pengaturan/user", json={
        "username": "barberx", "password": "passwordB123", "role": "barber",
        "barber_id": barber_id, "custom_role_id": role["id"],
    }, headers=headers)
    assert r.status_code == 422


def test_tambah_user_custom_role_id_tenant_lain_ditolak(two_tenants):
    client = two_tenants["client"]
    role_b = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir B"}, headers=two_tenants["headers_b"]).json()
    r = client.post("/api/pengaturan/user", json={
        "username": "kasirlintas", "password": "passwordK123", "role": "staff", "custom_role_id": role_b["id"],
    }, headers=two_tenants["headers_a"])
    assert r.status_code == 422


def test_owner_ubah_role_user_yang_sudah_ada(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    user_id = auth_db.tambah_user("staffbiasa", "passwordS123", role="staff", tenant_id=tenant_id)

    r = client.put(f"/api/pengaturan/user/{user_id}/role", json={"custom_role_id": role["id"]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["custom_role_id"] == role["id"]

    r2 = client.put(f"/api/pengaturan/user/{user_id}/role", json={"custom_role_id": None}, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["custom_role_id"] is None


def test_staff_tidak_bisa_ubah_role_user(single_tenant):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff_dan_login(client, tenant_id)
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers_owner).json()
    user_id = auth_db.tambah_user("staffbiasa2", "passwordS123", role="staff", tenant_id=tenant_id)
    r = client.put(f"/api/pengaturan/user/{user_id}/role", json={"custom_role_id": role["id"]}, headers=headers_staff)
    assert r.status_code == 403


# ============================= Propagasi ke pengecekan izin sungguhan =============================

def test_staff_dengan_role_custom_memakai_izin_role_bukan_default(single_tenant):
    """Endpoint POST /api/kasbon digerbang require_permission("izin_kasbon")
    -- default tenant untuk izin_kasbon adalah False (lihat permissions.py),
    role custom di sini SENGAJA dicentang True supaya perbedaannya nyata."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import database as db
    barber_id = db.add_barber("Barber Kasbon", tenant_id=tenant_id)

    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    client.put(f"/api/pengaturan/user-roles/{role['id']}/permissions", json={"izin": {"izin_kasbon": True}}, headers=headers)
    headers_staff = _buat_staff_dan_login(client, tenant_id, custom_role_id=role["id"])

    body = {"barber_id": barber_id, "jumlah": 100000, "tanggal": "2026-09-01", "keterangan": "Tes"}
    r = client.post("/api/kasbon", json=body, headers=headers_staff)
    assert r.status_code == 200, r.text


def test_staff_dengan_role_custom_tanpa_centang_ditolak(single_tenant):
    """Role custom yang tidak pernah dicentang izin_kasbon -- staff yang
    ditempelkan ke role ini DITOLAK, walau kebetulan tenant defaultnya juga
    False (membuktikan jalur role-lah yang dipakai, bukan tenant default)."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir Kosong"}, headers=headers).json()
    headers_staff = _buat_staff_dan_login(client, tenant_id, custom_role_id=role["id"])

    body = {"barber_id": 1, "jumlah": 100000, "tanggal": "2026-09-01", "keterangan": "Tes"}
    r = client.post("/api/kasbon", json=body, headers=headers_staff)
    assert r.status_code == 403


def test_staff_tanpa_custom_role_id_tetap_pakai_default_tenant(single_tenant):
    """Kompatibel mundur: staff TANPA custom_role_id (perilaku LAMA) --
    menyalakan izin_kasbon di default tenant tetap berlaku untuknya PERSIS
    seperti sebelum fitur role custom ada."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import database as db
    barber_id = db.add_barber("Barber Default", tenant_id=tenant_id)

    client.put("/api/pengaturan/hak-akses-admin", json={"izin": {"izin_kasbon": True}}, headers=headers)
    headers_staff = _buat_staff_dan_login(client, tenant_id, custom_role_id=None)

    body = {"barber_id": barber_id, "jumlah": 100000, "tanggal": "2026-09-01", "keterangan": "Tes"}
    r = client.post("/api/kasbon", json=body, headers=headers_staff)
    assert r.status_code == 200, r.text


# ============================= Hapus role yang masih terpakai =============================

def test_hapus_role_terpakai_staff_balik_ke_default_tidak_diblokir(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir Sementara"}, headers=headers).json()
    client.put(f"/api/pengaturan/user-roles/{role['id']}/permissions", json={"izin": {"izin_kasbon": True}}, headers=headers)
    user_id = auth_db.tambah_user("staffsementara", "passwordS123", role="staff", tenant_id=tenant_id,
                                   custom_role_id=role["id"])

    r = client.delete(f"/api/pengaturan/user-roles/{role['id']}", headers=headers)
    assert r.status_code == 200, r.text  # TIDAK diblokir walau masih ada staff yang memakainya

    target = auth_db.get_user(user_id)
    assert target["custom_role_id"] is None  # otomatis balik ke default

    r_login = client.post("/api/auth/login", json={"username": "staffsementara", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}
    # izin_kasbon default tenant (belum diatur eksplisit) -- False, jadi
    # setelah balik ke default staff ini TIDAK lagi bisa (bukan error 500,
    # bukan macet -- murni 403 biasa, membuktikan tidak ada state rusak).
    body = {"barber_id": 1, "jumlah": 100000, "tanggal": "2026-09-01", "keterangan": "Tes"}
    r2 = client.post("/api/kasbon", json=body, headers=headers_staff)
    assert r2.status_code == 403
