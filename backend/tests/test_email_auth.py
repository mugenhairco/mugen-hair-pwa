"""
test_email_auth.py — FITUR Email, Verifikasi Email, Lupa Kata Sandi
=============================================================================
Cakupan:
1. Registrasi mandiri: TIDAK LAGI auto-login (tidak ada token di respons),
   akun langsung blokir_sampai_verifikasi=True, email verifikasi terkirim
   (best-effort, IS_ENABLED=False di sandbox test -- dicek lewat DB
   langsung, bukan lewat mocking HTTP Resend).
2. Login diblokir SEBELUM verifikasi (403 terstruktur), berhasil SETELAH
   verifikasi.
3. Verifikasi email: token salah/kedaluwarsa ditolak, token benar
   diterima (idempotent -- klik ulang link yang sama aman).
4. Kirim Ulang Email Verifikasi (endpoint publik) -- generik untuk
   email tidak ditemukan MAUPUN sudah terverifikasi.
5. Lupa Kata Sandi: TIGA pesan berbeda (Owner & tidak-ditemukan IDENTIK
   demi anti-enumerasi, karyawan beda & eksplisit).
6. Reset Password: token valid berhasil, token salah/kedaluwarsa/sudah
   dipakai ditolak, password lama langsung tidak berlaku.
7. Tenant LAMA (dibuat lewat tenant_db.buat_tenant(), BUKAN registrasi
   mandiri) TIDAK PERNAH diblokir login walau belum/baru punya email
   yang belum diverifikasi.
8. Pengaturan > Profil > Email -- KHUSUS Owner (require_admin), staff/
   barber ditolak.
9. Email wajib unik saat registrasi (users.email, BUKAN cuma
   tenants.email registrant)."""

import database as db
import auth_db
import email_auth_db
import tenant_db


def _daftar_tenant_baru(client, email="owner@example.com", nama="Toko Uji", username="budi_owner"):
    """FITUR Username Registrasi Mandiri: `username` sekarang field
    TERPISAH dari email (SEBELUMNYA diam-diam sama dengan email -- lihat
    riwayat perbaikan di routers/tenant_registration.py::register()),
    default "budi_owner" dipakai LOGIN di seluruh test file ini yang
    sebelumnya memakai email sebagai username."""
    return client.post("/api/public/registration/register", json={
        "nama_barbershop": nama, "owner_name": "Budi Owner", "username": username,
        "email": email, "whatsapp": "081234567890" + email[:3],
        "password": "password123", "confirm_password": "password123",
    })


def _ambil_token_verifikasi(user_id):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT token FROM email_verification_tokens WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
        ).fetchone()
        return row["token"]


def _ambil_token_reset(user_id):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT token FROM password_reset_tokens WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
        ).fetchone()
        return row["token"]


# ---------------------------------------------------------------------------
# 1 & 2: Registrasi tidak auto-login, login diblokir sampai verifikasi
# ---------------------------------------------------------------------------

def test_register_tidak_lagi_auto_login(app_client):
    r = _daftar_tenant_baru(app_client)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" not in data
    assert data["registered"] is True
    assert data["email"] == "owner@example.com"


def test_register_akun_blokir_sampai_verifikasi(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    assert user["blokir_sampai_verifikasi"] == 1
    assert user["email_verified"] == 0
    assert user["email"] == "owner@example.com"


def test_login_ditolak_sebelum_verifikasi_dengan_kode_terstruktur(app_client):
    _daftar_tenant_baru(app_client)
    r = app_client.post("/api/auth/login", json={"username": "budi_owner", "password": "password123"})
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["code"] == "email_belum_terverifikasi"
    assert detail["email"] == "owner@example.com"


def test_login_berhasil_setelah_verifikasi(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    token = _ambil_token_verifikasi(user["id"])
    r = app_client.post("/api/auth/verifikasi-email", json={"token": token})
    assert r.status_code == 200

    r2 = app_client.post("/api/auth/login", json={"username": "budi_owner", "password": "password123"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["token"]


# ---------------------------------------------------------------------------
# 3: Verifikasi email
# ---------------------------------------------------------------------------

def test_verifikasi_token_salah_ditolak(app_client):
    r = app_client.post("/api/auth/verifikasi-email", json={"token": "token-tidak-ada"})
    assert r.status_code == 422


def test_verifikasi_token_kedaluwarsa_ditolak(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE email_verification_tokens SET expires_at = '2000-01-01T00:00:00' WHERE user_id = ?",
            (user["id"],),
        )
    token = _ambil_token_verifikasi(user["id"])
    r = app_client.post("/api/auth/verifikasi-email", json={"token": token})
    assert r.status_code == 422


def test_klik_link_verifikasi_dua_kali_aman(app_client):
    """Idempotent -- klik ulang link yang SAMA (mis. dari email client yang
    prefetch link) TIDAK error, hanya tidak melakukan apa-apa lagi."""
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    token = _ambil_token_verifikasi(user["id"])
    r1 = app_client.post("/api/auth/verifikasi-email", json={"token": token})
    r2 = app_client.post("/api/auth/verifikasi-email", json={"token": token})
    assert r1.status_code == 200
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# 4: Kirim Ulang Email Verifikasi
# ---------------------------------------------------------------------------

def test_resend_verifikasi_email_tidak_ditemukan_tetap_generik(app_client):
    r = app_client.post("/api/public/registration/resend-verification", json={"email": "tidakada@example.com"})
    assert r.status_code == 200
    assert "message" in r.json()


def test_resend_verifikasi_membuat_token_baru(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    token_lama = _ambil_token_verifikasi(user["id"])
    r = app_client.post("/api/public/registration/resend-verification", json={"email": "owner@example.com"})
    assert r.status_code == 200
    token_baru = _ambil_token_verifikasi(user["id"])
    assert token_baru != token_lama
    # Token LAMA tetap valid juga (tidak dihapus, lihat email_auth_db.py) --
    # kirim ulang TIDAK mencabut link sebelumnya yang mungkin masih dipegang user.
    r2 = app_client.post("/api/auth/verifikasi-email", json={"token": token_lama})
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# 5: Lupa Kata Sandi -- tiga jenis pesan
# ---------------------------------------------------------------------------

def test_lupa_password_owner_dan_tidak_ditemukan_pesan_identik(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    token = _ambil_token_verifikasi(user["id"])
    app_client.post("/api/auth/verifikasi-email", json={"token": token})

    r_owner = app_client.post("/api/auth/lupa-password", json={"email": "owner@example.com"})
    r_notfound = app_client.post("/api/auth/lupa-password", json={"email": "sama-sekali-tidak-ada@example.com"})
    assert r_owner.status_code == 200
    assert r_notfound.status_code == 200
    assert r_owner.json()["message"] == r_notfound.json()["message"]


def test_lupa_password_owner_membuat_reset_token(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    app_client.post("/api/auth/lupa-password", json={"email": "owner@example.com"})
    with db.get_conn() as conn:
        jumlah = conn.execute(
            "SELECT COUNT(*) AS n FROM password_reset_tokens WHERE user_id = ?", (user["id"],)
        ).fetchone()["n"]
    assert jumlah == 1


def test_lupa_password_karyawan_pesan_berbeda_dan_tidak_kirim_token(single_tenant):
    client = single_tenant["client"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Joni", uang_harian=50000, tenant_id=tenant_id)
    uid = auth_db.tambah_user("joni_barber", "password123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    email_auth_db.set_email_user(uid, "joni@example.com")

    r_owner = client.post("/api/auth/lupa-password", json={"email": "owner1@x.com"})  # tidak terdaftar (fixture beda)
    r_karyawan = client.post("/api/auth/lupa-password", json={"email": "joni@example.com"})
    assert r_karyawan.status_code == 200
    assert "Owner Tenant" in r_karyawan.json()["message"]
    assert r_karyawan.json()["message"] != r_owner.json()["message"]

    with db.get_conn() as conn:
        jumlah = conn.execute(
            "SELECT COUNT(*) AS n FROM password_reset_tokens WHERE user_id = ?", (uid,)
        ).fetchone()["n"]
    assert jumlah == 0, "Karyawan TIDAK BOLEH dapat token reset password"


# ---------------------------------------------------------------------------
# 6: Reset Password
# ---------------------------------------------------------------------------

def test_reset_password_berhasil_dan_password_lama_tidak_berlaku(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    v_token = _ambil_token_verifikasi(user["id"])
    app_client.post("/api/auth/verifikasi-email", json={"token": v_token})

    app_client.post("/api/auth/lupa-password", json={"email": "owner@example.com"})
    reset_token = _ambil_token_reset(user["id"])

    r = app_client.post("/api/auth/reset-password", json={
        "token": reset_token, "password": "passwordbaru456", "confirm_password": "passwordbaru456",
    })
    assert r.status_code == 200

    assert app_client.post("/api/auth/login", json={"username": "budi_owner", "password": "password123"}).status_code == 401
    assert app_client.post("/api/auth/login", json={"username": "budi_owner", "password": "passwordbaru456"}).status_code == 200


def test_reset_password_konfirmasi_tidak_cocok_ditolak(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    app_client.post("/api/auth/lupa-password", json={"email": "owner@example.com"})
    reset_token = _ambil_token_reset(user["id"])
    r = app_client.post("/api/auth/reset-password", json={
        "token": reset_token, "password": "abcd1234", "confirm_password": "beda5678",
    })
    assert r.status_code == 422


def test_reset_password_token_dipakai_dua_kali_ditolak(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    app_client.post("/api/auth/lupa-password", json={"email": "owner@example.com"})
    reset_token = _ambil_token_reset(user["id"])
    r1 = app_client.post("/api/auth/reset-password", json={
        "token": reset_token, "password": "passwordbaru456", "confirm_password": "passwordbaru456",
    })
    r2 = app_client.post("/api/auth/reset-password", json={
        "token": reset_token, "password": "passwordlagi789", "confirm_password": "passwordlagi789",
    })
    assert r1.status_code == 200
    assert r2.status_code == 422


def test_reset_password_token_salah_ditolak(app_client):
    r = app_client.post("/api/auth/reset-password", json={
        "token": "token-ngawur", "password": "abcd1234", "confirm_password": "abcd1234",
    })
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 7: Tenant LAMA tidak pernah diblokir
# ---------------------------------------------------------------------------

def test_tenant_lama_tidak_diblokir_walau_belum_verifikasi_email(app_client):
    tenant_id = tenant_db.buat_tenant("toko-lama", "Toko Lama")
    auth_db.tambah_user("owner_lama", "password123", role="admin", tenant_id=tenant_id)

    # Login tanpa email sama sekali -- normal.
    r1 = app_client.post("/api/auth/login", json={"username": "owner_lama", "password": "password123"})
    assert r1.status_code == 200
    headers = {"Authorization": f"Bearer {r1.json()['token']}"}

    # Tambah email lewat Profil -- BELUM diverifikasi.
    r2 = app_client.put("/api/pengaturan/profil/email", json={"email": "ownerlama@example.com"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["email_verified"] == 0

    # Login LAGI -- HARUS TETAP BOLEH (item 5: jangan blokir tenant lama).
    r3 = app_client.post("/api/auth/login", json={"username": "owner_lama", "password": "password123"})
    assert r3.status_code == 200


def test_tenant_lama_lupa_password_aktif_setelah_tambah_email(app_client):
    tenant_id = tenant_db.buat_tenant("toko-lama-2", "Toko Lama 2")
    uid = auth_db.tambah_user("owner_lama2", "password123", role="admin", tenant_id=tenant_id)
    email_auth_db.set_email_user(uid, "ownerlama2@example.com")

    r = app_client.post("/api/auth/lupa-password", json={"email": "ownerlama2@example.com"})
    assert r.status_code == 200
    with db.get_conn() as conn:
        jumlah = conn.execute(
            "SELECT COUNT(*) AS n FROM password_reset_tokens WHERE user_id = ?", (uid,)
        ).fetchone()["n"]
    assert jumlah == 1


# ---------------------------------------------------------------------------
# 8: Pengaturan > Profil > Email -- khusus Owner
# ---------------------------------------------------------------------------

def test_profil_email_ditolak_untuk_barber(single_tenant):
    client = single_tenant["client"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Andi", uang_harian=50000, tenant_id=tenant_id)
    auth_db.tambah_user("andi_barber", "password123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "andi_barber", "password": "password123"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    r2 = client.put("/api/pengaturan/profil/email", json={"email": "andi@example.com"}, headers=headers)
    assert r2.status_code == 403


def test_profil_email_berhasil_untuk_owner(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    r = client.put("/api/pengaturan/profil/email", json={"email": "ownerbaru@example.com"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "ownerbaru@example.com"
    assert r.json()["email_verified"] == 0
    assert r.json()["blokir_sampai_verifikasi"] == 0  # TIDAK PERNAH diset oleh jalur ini


def test_profil_email_sudah_dipakai_akun_lain_ditolak(two_tenants):
    client = two_tenants["client"]
    email_auth_db.set_email_user(
        auth_db.get_user_by_username("ownerB", tenant_id=two_tenants["tenant_b"])["id"], "dipakai@example.com"
    )
    r = client.put("/api/pengaturan/profil/email", json={"email": "dipakai@example.com"},
                    headers=two_tenants["headers_a"])
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 9: Email wajib unik saat registrasi
# ---------------------------------------------------------------------------

def test_registrasi_email_duplikat_ditolak(app_client):
    _daftar_tenant_baru(app_client, email="duplikat@example.com", nama="Toko Pertama")
    r = _daftar_tenant_baru(app_client, email="duplikat@example.com", nama="Toko Kedua")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 10 (FITUR Username Registrasi Mandiri): username wajib diisi, unik di
# SELURUH sistem (lintas tenant), langsung tersimpan & langsung dipakai
# login -- lihat riwayat perbaikan di routers/tenant_registration.py.
# ---------------------------------------------------------------------------

def test_registrasi_username_kosong_ditolak(app_client):
    r = _daftar_tenant_baru(app_client, username="")
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], str)
    assert "username" in r.json()["detail"].lower()
    # Tenant TIDAK boleh terlanjur dibuat -- konsisten dengan pengecekan
    # field wajib lain (nama_barbershop/owner_name/whatsapp) yang SUDAH
    # ADA, dicek SEBELUM tenant_db.buat_tenant() dipanggil sama sekali.
    assert tenant_db.get_tenant_by_email("owner@example.com") is None


def test_registrasi_username_hanya_spasi_ditolak(app_client):
    r = _daftar_tenant_baru(app_client, username="   ")
    assert r.status_code == 422, r.text
    assert "username" in r.json()["detail"].lower()


def test_registrasi_username_dipakai_tenant_lain_ditolak(app_client):
    """Bentrok LINTAS TENANT -- email & whatsapp SENGAJA dibuat beda supaya
    murni menguji pengecekan username, bukan ikut kena penolakan email/
    whatsapp duplikat yang sudah diuji terpisah di atas."""
    r1 = _daftar_tenant_baru(app_client, email="pertama@example.com", nama="Toko Pertama", username="tokosama")
    assert r1.status_code == 200, r1.text
    r2 = _daftar_tenant_baru(app_client, email="kedua@example.com", nama="Toko Kedua", username="tokosama")
    assert r2.status_code == 422, r2.text
    assert "username" in r2.json()["detail"].lower()
    # Toko kedua TIDAK terlanjur dibuat -- pengecekan username terjadi
    # SEBELUM tenant_db.buat_tenant() (pola sama dengan email/whatsapp).
    assert tenant_db.get_tenant_by_email("kedua@example.com") is None


def test_registrasi_username_dipakai_akun_non_registrasi_ditolak(app_client):
    """Keunikan berlaku GLOBAL -- termasuk terhadap akun yang dibuat lewat
    jalur LAIN (mis. tenant_db.buat_tenant() + auth_db.tambah_user()
    langsung, pola provisioning manual Super Admin), BUKAN cuma sesama
    hasil registrasi mandiri."""
    tenant_id = tenant_db.buat_tenant("toko-manual", "Toko Manual")
    auth_db.tambah_user("dipakaisudah", "password123", role="admin", tenant_id=tenant_id)

    r = _daftar_tenant_baru(app_client, email="baru@example.com", username="dipakaisudah")
    assert r.status_code == 422, r.text
    assert "username" in r.json()["detail"].lower()


def test_registrasi_username_tersimpan_dan_bisa_langsung_login(app_client):
    """Item 6 spesifikasi: username yang DIPILIH pengguna (BUKAN email)
    langsung tersimpan bersama akun Owner & bisa dipakai login begitu
    email diverifikasi."""
    r = _daftar_tenant_baru(app_client, email="pemilik@example.com", username="pemiliktoko99")
    assert r.status_code == 200, r.text

    user = email_auth_db.get_user_by_email("pemilik@example.com")
    assert user["username"] == "pemiliktoko99"

    token = _ambil_token_verifikasi(user["id"])
    app_client.post("/api/auth/verifikasi-email", json={"token": token})

    # Login pakai USERNAME yang dipilih, BUKAN pakai email.
    r_login = app_client.post("/api/auth/login", json={"username": "pemiliktoko99", "password": "password123"})
    assert r_login.status_code == 200, r_login.text

    # Email itu sendiri BUKAN username yang valid (membuktikan keduanya
    # sungguhan field terpisah, bukan diam-diam disamakan lagi).
    r_login_email = app_client.post("/api/auth/login", json={"username": "pemilik@example.com", "password": "password123"})
    assert r_login_email.status_code == 401


# ---------------------------------------------------------------------------
# Regresi: Super Admin & login biasa tidak terpengaruh sama sekali
# ---------------------------------------------------------------------------

def test_superadmin_login_tidak_terpengaruh(app_client):
    auth_db.tambah_user("sa_test", "password123", role="superadmin", tenant_id=None)
    r = app_client.post("/api/auth/login", json={"username": "sa_test", "password": "password123"})
    assert r.status_code == 200


def test_login_biasa_single_tenant_tidak_terpengaruh(single_tenant):
    r = single_tenant["client"].post("/api/auth/login", json={"username": "owner1", "password": "password123"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 10 (Integrasi Resend): token verifikasi email SEKARANG sekali pakai juga
# ---------------------------------------------------------------------------

def test_verifikasi_token_sekali_pakai_klik_ulang_pesan_beda_tapi_tetap_200(app_client):
    """Item 5 spesifikasi ("hanya dapat digunakan satu kali") -- BEDA dari
    desain awal (idempotent). Klik ulang link yang SUDAH dipakai TETAP
    200 (bukan dianggap error tajam ke pengguna), tapi pesannya berbeda
    dari klik PERTAMA yang benar-benar berhasil."""
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    token = _ambil_token_verifikasi(user["id"])

    r1 = app_client.post("/api/auth/verifikasi-email", json={"token": token})
    r2 = app_client.post("/api/auth/verifikasi-email", json={"token": token})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["message"] != r2.json()["message"]
    assert "sebelumnya" in r2.json()["message"].lower()

    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT used_at FROM email_verification_tokens WHERE token = ?", (token,)
        ).fetchone()
    assert row["used_at"] is not None


def test_verifikasi_token_kedaluwarsa_tetap_ditolak_walau_belum_dipakai(app_client):
    _daftar_tenant_baru(app_client)
    user = email_auth_db.get_user_by_email("owner@example.com")
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE email_verification_tokens SET expires_at = '2000-01-01T00:00:00' WHERE user_id = ?",
            (user["id"],),
        )
    token = _ambil_token_verifikasi(user["id"])
    r = app_client.post("/api/auth/verifikasi-email", json={"token": token})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 11 (Integrasi Resend): Undangan User Tenant
# ---------------------------------------------------------------------------

def test_tambah_user_dengan_email_kirim_undangan_tanpa_blokir_login(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Rudi", uang_harian=50000, tenant_id=tenant_id)

    r = client.post("/api/pengaturan/user", headers=headers, json={
        "username": "rudi_barber", "password": "password123", "role": "barber",
        "barber_id": barber_id, "email": "rudi@example.com",
    })
    assert r.status_code == 200, r.text
    new_user = auth_db.get_user_by_username("rudi_barber", tenant_id=tenant_id)
    assert new_user["email"] == "rudi@example.com"
    assert new_user["email_verified"] == 0
    # KHUSUS undangan -- TIDAK PERNAH blokir_sampai_verifikasi (BEDA dari
    # Registrasi mandiri) -- karyawan baru langsung bisa login dengan
    # password yang diatur Owner, TIDAK menunggu verifikasi apa pun.
    assert new_user["blokir_sampai_verifikasi"] == 0

    with db.get_conn() as conn:
        jumlah_token = conn.execute(
            "SELECT COUNT(*) AS n FROM email_verification_tokens WHERE user_id = ?", (new_user["id"],)
        ).fetchone()["n"]
    assert jumlah_token == 1

    r_login = client.post("/api/auth/login", json={"username": "rudi_barber", "password": "password123"})
    assert r_login.status_code == 200, r_login.text


def test_tambah_user_tanpa_email_perilaku_lama_apa_adanya(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Tanpa Email", uang_harian=50000, tenant_id=tenant_id)

    r = client.post("/api/pengaturan/user", headers=headers, json={
        "username": "tanpa_email_barber", "password": "password123", "role": "barber", "barber_id": barber_id,
    })
    assert r.status_code == 200, r.text
    new_user = auth_db.get_user_by_username("tanpa_email_barber", tenant_id=tenant_id)
    assert new_user["email"] in (None, "")

    r_login = client.post("/api/auth/login", json={"username": "tanpa_email_barber", "password": "password123"})
    assert r_login.status_code == 200


def test_tambah_user_email_sudah_dipakai_akun_lain_ditolak(two_tenants):
    client = two_tenants["client"]
    email_auth_db.set_email_user(
        auth_db.get_user_by_username("ownerB", tenant_id=two_tenants["tenant_b"])["id"], "dipakai2@example.com"
    )
    barber_id = db.add_barber("Barber A", uang_harian=50000, tenant_id=two_tenants["tenant_a"])
    r = client.post("/api/pengaturan/user", headers=two_tenants["headers_a"], json={
        "username": "barber_a", "password": "password123", "role": "barber",
        "barber_id": barber_id, "email": "dipakai2@example.com",
    })
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 12 (Integrasi Resend): header From "Nama <email>"
# ---------------------------------------------------------------------------

def test_email_service_from_header_gabungan_nama_dan_alamat():
    """Item 4 spesifikasi: "From: Rivoir <noreply@rivoirsett.com>" -- default
    MAIL_FROM/MAIL_FROM_NAME (env var TIDAK diisi di lingkungan test) HARUS
    menghasilkan header From persis format ini."""
    import email_service
    assert email_service.MAIL_FROM == "noreply@rivoirsett.com"
    assert email_service.MAIL_FROM_NAME == "Rivoir"
    assert email_service._FROM_HEADER == "Rivoir <noreply@rivoirsett.com>"
