"""test_permission_tree.py — REVISI BESAR Hak Akses (hapus Role "Admin"
bawaan/default, satu checklist dropdown per menu/tab/sub-item -- lihat
permissions.py::PERMISSION_TREE)
=============================================================================
Cakupan:
- Struktur PERMISSION_TREE itu sendiri (setiap node punya parent valid,
  tidak ada siklus, cross_cutting adalah subset node root).
- get_all()/set_bulk() -- cascade "uncheck induk -> seluruh keturunan ikut
  mati" (permissions.py::set_bulk(), konsisten dengan model dropdown
  frontend yang menyembunyikan total anak kalau induk tidak dicentang).
- Endpoint GET /api/pengaturan/permission-tree (metadata pohon untuk UI).
- BUGFIX migrasi (user_roles_db.py::_baca_izin_lama_dengan_default()):
  key LAMA yang TIDAK PERNAH ditulis eksplisit ke `settings` (Owner tidak
  pernah mengubahnya dari default) harus tetap terbaca sebagai DEFAULT
  LAMA-nya (PERMISSION_DEFS versi sebelum revisi ini, BANYAK True by
  design) -- BUKAN False, walau permissions.get_all() yang SEKARANG
  (PERMISSION_TREE, tanpa default sama sekali) akan mengembalikan False
  untuk key yang sama kalau dipakai langsung tanpa lapis ini."""

import database as db
import permissions
import user_roles_db


def _buat_owner_dan_login(client, tenant_id, username="ownertree", password="passwordO123"):
    import auth_db
    auth_db.tambah_user(username, password, role="admin", tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ============================= Struktur PERMISSION_TREE =============================

def test_setiap_node_punya_parent_valid_atau_root():
    for key, (label, parent) in permissions.PERMISSION_TREE.items():
        assert isinstance(label, str) and label
        if parent is not None:
            assert parent in permissions.PERMISSION_TREE, f"{key} punya parent {parent!r} yang tidak ada di katalog"


def test_tidak_ada_siklus_di_pohon():
    for key in permissions.PERMISSION_TREE:
        dikunjungi = set()
        current = key
        while True:
            _label, parent = permissions.PERMISSION_TREE[current]
            if parent is None:
                break
            assert parent not in dikunjungi, f"Siklus terdeteksi melibatkan {key}"
            dikunjungi.add(parent)
            current = parent


def test_cross_cutting_keys_adalah_root_tanpa_anak():
    roots = set(permissions.tree_children(None))
    for key in permissions.CROSS_CUTTING_KEYS:
        assert key in roots, f"{key} harus berupa root (parent=None)"
        assert not permissions.tree_children(key), f"{key} (lintas-menu) tidak boleh punya anak"


def test_tree_roots_tidak_mengikutkan_cross_cutting():
    roots = permissions.tree_roots()
    assert not (set(roots) & permissions.CROSS_CUTTING_KEYS)


def test_hak_akses_user_dan_billing_tidak_ada_di_tree():
    """"Hak Akses User" (mengatur Role orang lain) dan "Billing" PERMANEN
    Owner-only -- TIDAK PERNAH masuk katalog yang bisa diberikan ke Role
    manapun (privilege-escalation risk untuk yang pertama, kredensial
    pihak ketiga billing SaaS untuk yang kedua)."""
    for key in permissions.PERMISSION_TREE:
        assert "hak_akses" not in key
        assert "billing" not in key


# ============================= get_all()/set_bulk() =============================

def test_role_baru_fail_closed_semua_false(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kosong"}, headers=headers).json()
    izin = permissions.get_all(role_id=role["id"])
    assert all(v is False for v in izin.values())


def test_set_bulk_cascade_uncheck_mematikan_keturunan(single_tenant):
    """Centang izin_setting_user + dua anaknya, lalu matikan izin_setting_
    user lagi -- KEDUA anaknya harus ikut mati, konsisten dengan model
    dropdown (anak tidak mungkin aktif kalau induknya tidak dicentang)."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    permissions.set_bulk({
        "izin_setting_lihat": True,
        "izin_setting_user": True,
        "izin_user_tambah": True,
        "izin_user_hapus": True,
    }, role_id=role["id"])
    izin = permissions.get_all(role_id=role["id"])
    assert izin["izin_user_tambah"] is True
    assert izin["izin_user_hapus"] is True

    permissions.set_bulk({"izin_setting_user": False}, role_id=role["id"])
    izin2 = permissions.get_all(role_id=role["id"])
    assert izin2["izin_setting_user"] is False
    assert izin2["izin_user_tambah"] is False  # ikut mati (cascade)
    assert izin2["izin_user_hapus"] is False   # ikut mati (cascade)
    assert izin2["izin_setting_lihat"] is True  # TIDAK ikut (bukan keturunan izin_setting_user)


def test_set_bulk_key_tidak_dikenal_ditolak(single_tenant):
    import pytest
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    with pytest.raises(ValueError):
        permissions.set_bulk({"izin_tidak_ada_di_katalog": True}, role_id=role["id"])


# ============================= Endpoint GET /permission-tree =============================

def test_endpoint_permission_tree_owner(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/pengaturan/permission-tree", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(n["key"] for n in data["nodes"]) == permissions.PERMISSION_KEYS
    assert set(data["cross_cutting"]) == permissions.CROSS_CUTTING_KEYS


def test_endpoint_permission_tree_staff_ditolak(single_tenant):
    import auth_db
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    auth_db.tambah_user("staffpt", "passwordS123", role="staff", tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "staffpt", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}
    r = client.get("/api/pengaturan/permission-tree", headers=headers_staff)
    assert r.status_code == 403


# ============================= BUGFIX migrasi: default lama =============================

def test_baca_izin_lama_dengan_default_key_belum_ditulis_pakai_default_lama(single_tenant):
    """Tenant baru (belum pernah menyentuh Hak Akses Admin sama sekali) --
    key yang DULU default True (mis. izin_booking_kelola, izin_dashboard_
    lihat) harus terbaca True, key yang DULU default False (mis.
    izin_kasbon) harus terbaca False -- MENCERMINKAN PERSIS perilaku lama,
    BUKAN fail-closed PERMISSION_TREE yang baru."""
    tenant_id = single_tenant["tenant_id"]
    lama = user_roles_db._baca_izin_lama_dengan_default(tenant_id)
    assert lama["izin_booking_kelola"] is True
    assert lama["izin_dashboard_lihat"] is True
    assert lama["izin_produk_kelola"] is True
    assert lama["izin_kasbon"] is False
    assert lama["izin_komisi"] is False


def test_baca_izin_lama_dengan_default_key_eksplisit_menang_atas_default(single_tenant):
    """Kalau Owner SUDAH eksplisit mengubah suatu key dari default lamanya
    (ditulis ke `settings`), nilai eksplisit itu yang menang, BUKAN
    default lama."""
    tenant_id = single_tenant["tenant_id"]
    db.set_settings_bulk({"izin_booking_kelola": "0", "izin_kasbon": "1"}, tenant_id=tenant_id)
    lama = user_roles_db._baca_izin_lama_dengan_default(tenant_id)
    assert lama["izin_booking_kelola"] is False  # eksplisit 0, walau default True
    assert lama["izin_kasbon"] is True  # eksplisit 1, walau default False


def test_migrasi_role_staff_default_mewarisi_default_lama_bukan_false(single_tenant):
    """Regresi BUGFIX: SEBELUM diperbaiki, migrasi membaca nilai lama
    lewat permissions.get_all(role_id=None) yang SEKARANG fail-closed
    tanpa default -- key yang tidak pernah ditulis eksplisit (mis.
    izin_booking_kelola, default lama True) akan KELIRU terbaca False,
    mengunci staff lama yang sebenarnya masih berhak. Test ini membuktikan
    Role "Staff" hasil migrasi TETAP mewarisi True untuk key semacam itu."""
    import auth_db
    tenant_id = single_tenant["tenant_id"]
    # Simulasikan staff LAMA (custom_role_id NULL, dari SEBELUM revisi ini)
    # -- tenant ini belum pernah menyentuh Hak Akses Admin sama sekali.
    auth_db.tambah_user("staffmigrasi", "passwordS123", role="staff", tenant_id=tenant_id)

    user_roles_db.migrasi_role_staff_default()

    roles = user_roles_db.list_roles(tenant_id)
    role_staff = next(r for r in roles if r["nama"] == "Staff")
    izin = permissions.get_all(role_id=role_staff["id"])
    # izin_booking_list mewarisi dari izin_booking_kelola lama (default True)
    assert izin["izin_booking_list"] is True
    assert izin["izin_dashboard_lihat"] is True
    assert izin["izin_kasbon"] is False  # default lama False, tetap False

    target = auth_db.get_user_by_username("staffmigrasi", tenant_id=tenant_id)
    assert target["custom_role_id"] == role_staff["id"]


def test_migrasi_role_staff_default_idempotent(single_tenant):
    """Dipanggil dua kali (SAMA seperti tiap restart server) -- TIDAK
    membuat Role "Staff" dobel, TIDAK mengubah apa pun yang kedua kalinya."""
    import auth_db
    tenant_id = single_tenant["tenant_id"]
    auth_db.tambah_user("staffmigrasi2", "passwordS123", role="staff", tenant_id=tenant_id)

    user_roles_db.migrasi_role_staff_default()
    user_roles_db.migrasi_role_staff_default()

    roles_staff = [r for r in user_roles_db.list_roles(tenant_id) if r["nama"] == "Staff"]
    assert len(roles_staff) == 1
