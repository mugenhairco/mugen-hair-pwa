"""Regresi: User Management tenant -- Owner tenant tidak boleh melihat atau
mengubah akun Super Admin, dan isolasi antar tenant tetap seperti sebelumnya
(lihat routers/pengaturan.py::_pastikan_bukan_akun_dilindungi() +
_pastikan_target_tenant_sama())."""

import auth_db


def _buat_superadmin(username="superadmin1", password="rahasia123"):
    return auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)


def test_list_user_tenant_tidak_pernah_menyertakan_superadmin(two_tenants):
    _buat_superadmin()
    r = two_tenants["client"].get("/api/pengaturan/user", headers=two_tenants["headers_a"])
    assert r.status_code == 200, r.text
    roles = {u["role"] for u in r.json()}
    assert "superadmin" not in roles


def test_ganti_password_superadmin_dari_tenant_ditolak_403(two_tenants):
    superadmin_id = _buat_superadmin()
    r = two_tenants["client"].put(
        f"/api/pengaturan/user/{superadmin_id}/password",
        json={"password": "dicoba123"},
        headers=two_tenants["headers_a"],
    )
    assert r.status_code == 403, r.text


def test_ganti_username_superadmin_dari_tenant_ditolak_403(two_tenants):
    superadmin_id = _buat_superadmin()
    r = two_tenants["client"].put(
        f"/api/pengaturan/user/{superadmin_id}/username",
        json={"username": "dicoba"},
        headers=two_tenants["headers_a"],
    )
    assert r.status_code == 403, r.text


def test_nonaktifkan_superadmin_dari_tenant_ditolak_403(two_tenants):
    superadmin_id = _buat_superadmin()
    r = two_tenants["client"].put(
        f"/api/pengaturan/user/{superadmin_id}/nonaktifkan",
        headers=two_tenants["headers_a"],
    )
    assert r.status_code == 403, r.text


def test_aktifkan_superadmin_dari_tenant_ditolak_403(two_tenants):
    superadmin_id = _buat_superadmin()
    r = two_tenants["client"].put(
        f"/api/pengaturan/user/{superadmin_id}/aktifkan",
        headers=two_tenants["headers_a"],
    )
    assert r.status_code == 403, r.text


def test_hapus_superadmin_dari_tenant_ditolak_403(two_tenants):
    superadmin_id = _buat_superadmin()
    r = two_tenants["client"].delete(
        f"/api/pengaturan/user/{superadmin_id}",
        headers=two_tenants["headers_a"],
    )
    assert r.status_code == 403, r.text


def test_akses_user_tenant_lain_tetap_404_bukan_403(two_tenants):
    """Regresi: percobaan mengubah user MILIK TENANT LAIN (bukan Super
    Admin) TIDAK berubah -- tetap 404 seperti sebelum perubahan ini (lihat
    _pastikan_target_tenant_sama()), supaya tidak membocorkan keberadaan
    user tenant lain. Protected-account 403 di atas HANYA untuk Super
    Admin, bukan mengganti perilaku isolasi antar tenant."""
    r = two_tenants["client"].get("/api/pengaturan/user", headers=two_tenants["headers_b"])
    assert r.status_code == 200, r.text
    owner_b_id = next(u["id"] for u in r.json() if u["username"] == "ownerB")

    r = two_tenants["client"].put(
        f"/api/pengaturan/user/{owner_b_id}/password",
        json={"password": "dicoba123"},
        headers=two_tenants["headers_a"],
    )
    assert r.status_code == 404, r.text
