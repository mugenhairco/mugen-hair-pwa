"""test_auth_single_session.py -- Kontrol Sesi Login Satu-Device per Akun.

Cakupan: login kedua (device lain) mencabut token pertama untuk SEMUA role
(Owner/Admin/Barber/Superadmin), akun Barber yang BERBEDA tetap bisa login
bersamaan tanpa saling memengaruhi, logout mencabut sesi di backend (bukan
cuma frontend), token "pre-deploy" (belum pernah tercatat hash sesi) dipaksa
login ulang, public booking & fallback resolve_tenant_hibrid tidak
terpengaruh, dan current_session_hash tidak pernah bocor ke response."""

import time

import auth
import auth_db
import database as db
import tenant_db


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _login_beda_device(client, username, password):
    """itsdangerous.TimestampSigner menyisipkan timestamp beresolusi 1
    DETIK (int(time.time())) -- dua login untuk akun yang SAMA dalam detik
    wall-clock yang SAMA PERSIS bisa menghasilkan string token yang
    IDENTIK (jadi hash-nya juga identik), yang membuat pengujian revoke
    jadi tidak deterministik (bukan bug fitur, murni presisi timestamp).
    Jeda sedikit di atas 1 detik SEBELUM login "device lain" supaya token
    baru DIJAMIN beda dari yang pertama."""
    time.sleep(1.05)
    return _login(client, username, password)


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_kedua_mencabut_token_pertama_owner(app_client):
    tenant_id = tenant_db.buat_tenant("toko-sesi-owner", "Toko Sesi Owner")
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant_id)

    token1 = _login(app_client, "owner1", "password123")
    assert app_client.get("/api/auth/me", headers=_headers(token1)).status_code == 200

    token2 = _login_beda_device(app_client, "owner1", "password123")
    r1 = app_client.get("/api/auth/me", headers=_headers(token1))
    assert r1.status_code == 401
    r2 = app_client.get("/api/auth/me", headers=_headers(token2))
    assert r2.status_code == 200


def test_login_kedua_mencabut_token_pertama_staff(app_client):
    tenant_id = tenant_db.buat_tenant("toko-sesi-staff", "Toko Sesi Staff")
    auth_db.tambah_user("staff1", "password123", role="staff", tenant_id=tenant_id)

    token1 = _login(app_client, "staff1", "password123")
    token2 = _login_beda_device(app_client, "staff1", "password123")
    assert app_client.get("/api/auth/me", headers=_headers(token1)).status_code == 401
    assert app_client.get("/api/auth/me", headers=_headers(token2)).status_code == 200


def test_login_kedua_mencabut_token_pertama_barber(app_client):
    tenant_id = tenant_db.buat_tenant("toko-sesi-barber", "Toko Sesi Barber")
    barber_id = db.add_barber("Andi Saputra", tenant_id=tenant_id)
    auth_db.tambah_user("barber1", "password123", role="barber", barber_id=barber_id, tenant_id=tenant_id)

    token1 = _login(app_client, "barber1", "password123")
    token2 = _login_beda_device(app_client, "barber1", "password123")
    assert app_client.get("/api/auth/me", headers=_headers(token1)).status_code == 401
    assert app_client.get("/api/auth/me", headers=_headers(token2)).status_code == 200


def test_login_kedua_mencabut_token_pertama_superadmin(app_client):
    auth_db.tambah_user("sa1", "password123", role="superadmin", tenant_id=None)

    token1 = _login(app_client, "sa1", "password123")
    token2 = _login_beda_device(app_client, "sa1", "password123")
    assert app_client.get("/api/auth/me", headers=_headers(token1)).status_code == 401
    assert app_client.get("/api/auth/me", headers=_headers(token2)).status_code == 200


def test_dua_akun_barber_berbeda_tetap_bisa_login_bersamaan(app_client):
    """requirement 3: pembatasan HANYA per-akun -- 5 (di sini 2, cukup
    membuktikan) akun Barber BERBEDA dalam satu tenant tetap boleh aktif
    bersamaan, tidak saling mencabut."""
    tenant_id = tenant_db.buat_tenant("toko-sesi-multi-barber", "Toko Sesi Multi Barber")
    barber1_id = db.add_barber("Andi Saputra", tenant_id=tenant_id)
    barber2_id = db.add_barber("Budi Santoso", tenant_id=tenant_id)
    auth_db.tambah_user("barberA", "password123", role="barber", barber_id=barber1_id, tenant_id=tenant_id)
    auth_db.tambah_user("barberB", "password123", role="barber", barber_id=barber2_id, tenant_id=tenant_id)

    token_a = _login(app_client, "barberA", "password123")
    token_b = _login(app_client, "barberB", "password123")

    assert app_client.get("/api/auth/me", headers=_headers(token_a)).status_code == 200
    assert app_client.get("/api/auth/me", headers=_headers(token_b)).status_code == 200


def test_logout_mencabut_sesi_di_backend(app_client):
    tenant_id = tenant_db.buat_tenant("toko-sesi-logout", "Toko Sesi Logout")
    auth_db.tambah_user("ownerlogout", "password123", role="admin", tenant_id=tenant_id)

    token = _login(app_client, "ownerlogout", "password123")
    assert app_client.get("/api/auth/me", headers=_headers(token)).status_code == 200

    r = app_client.post("/api/auth/logout", headers=_headers(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    assert app_client.get("/api/auth/me", headers=_headers(token)).status_code == 401


def test_token_lama_sebelum_migrasi_dipaksa_login_ulang(app_client):
    """requirement Owner (keputusan rollout): token yang diterbitkan SEBELUM
    fitur ini ada (current_session_hash tidak pernah tercatat untuk akun
    ini) HARUS dipaksa login ulang begitu deploy -- dibuktikan dengan
    menghasilkan token langsung lewat auth.buat_token() (BUKAN lewat
    endpoint login, supaya set_session_hash() tidak pernah dipanggil),
    meniru token yang sudah beredar sebelum migrasi kolom ini berjalan."""
    tenant_id = tenant_db.buat_tenant("toko-sesi-lama", "Toko Sesi Lama")
    user_id = auth_db.tambah_user("ownerlama", "password123", role="admin", tenant_id=tenant_id)

    token_pre_deploy = auth.buat_token(user_id)
    r = app_client.get("/api/auth/me", headers=_headers(token_pre_deploy))
    assert r.status_code == 401


def test_publik_booking_tidak_terpengaruh_sesi_dicabut(app_client):
    """Dipakai /subscription-status (BUKAN /barbers) -- endpoint itu SATU-
    SATUNYA endpoint publik yang TIDAK ikut digerbang fitur "booking_online"
    (lihat catatan di test_subscription.py), jadi proxy paling bersih untuk
    membuktikan endpoint publik tidak peduli header Authorization sama
    sekali, tanpa tercampur gerbang fitur terpisah yang butuh subscription
    aktif (di luar cakupan test session ini)."""
    tenant_id = tenant_db.buat_tenant("test-toko-a", "Test Toko A")
    auth_db.tambah_user("ownerpublik", "password123", role="admin", tenant_id=tenant_id)

    token1 = _login(app_client, "ownerpublik", "password123")
    _login(app_client, "ownerpublik", "password123")  # cabut token1

    r = app_client.get("/api/public/booking/subscription-status?tenant=test-toko-a", headers=_headers(token1))
    assert r.status_code == 200, r.text
    assert r.json() == {"tersedia": True}


def test_resolve_tenant_hibrid_sesi_dicabut_jatuh_ke_publik(app_client):
    tenant_id = tenant_db.buat_tenant("test-toko-hibrid", "Test Toko Hibrid")
    auth_db.tambah_user("ownerhibrid", "password123", role="admin", tenant_id=tenant_id)

    token1 = _login(app_client, "ownerhibrid", "password123")
    _login(app_client, "ownerhibrid", "password123")  # cabut token1

    r = app_client.get("/api/pengaturan/identitas?tenant=test-toko-hibrid", headers=_headers(token1))
    assert r.status_code == 200, r.text


def test_login_tidak_membocorkan_current_session_hash(app_client):
    tenant_id = tenant_db.buat_tenant("toko-sesi-bocor", "Toko Sesi Bocor")
    auth_db.tambah_user("ownerbocor", "password123", role="admin", tenant_id=tenant_id)

    r_login = app_client.post("/api/auth/login", json={"username": "ownerbocor", "password": "password123"})
    assert r_login.status_code == 200, r_login.text
    assert "current_session_hash" not in r_login.json()["user"]

    token = r_login.json()["token"]
    r_me = app_client.get("/api/auth/me", headers=_headers(token))
    assert r_me.status_code == 200
    assert "current_session_hash" not in r_me.json()
