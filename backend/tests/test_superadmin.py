"""
test_superadmin.py — FONDASI Multi-Tenant Phase 2.1: Super Admin Dashboard
=============================================================================
Cakupan: akses eksklusif (superadmin vs akun tenant biasa saling ditolak
dari wilayah masing-masing), provisioning tenant baru + akun Owner
pertamanya, aktifkan/nonaktifkan tenant, dan bootstrap lewat environment
variable (lihat main.py::_bootstrap_superadmin_pertama())."""

import auth_db


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    assert r.json()["tenant"] is None  # superadmin TIDAK terikat tenant mana pun
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_tambah_user_superadmin_tenant_id_diisi_ditolak(app_client):
    import tenant_db
    tenant_a = tenant_db.buat_tenant("test-toko-a", "Test Toko A")
    try:
        auth_db.tambah_user("salahkaprah", "password123", role="superadmin", tenant_id=tenant_a)
        assert False, "Harus ditolak: superadmin tidak boleh dikaitkan ke tenant"
    except ValueError as e:
        assert "tenant" in str(e).lower()


def test_superadmin_bisa_lihat_daftar_seluruh_tenant(two_tenants):
    client = two_tenants["client"]
    headers = _buat_superadmin_dan_login(client)

    r = client.get("/api/superadmin/tenants", headers=headers)
    assert r.status_code == 200, r.text
    slugs = {t["slug"] for t in r.json()}
    # mencakup tenant default (auto dibuat migrasi_tenant() saat boot) + dua
    # tenant dari fixture two_tenants -- superadmin melihat SEMUANYA sekaligus.
    assert "test-toko-a" in slugs
    assert "test-toko-b" in slugs
    for t in r.json():
        if t["slug"] in ("test-toko-a", "test-toko-b"):
            assert t["jumlah_user"] == 1
            assert t["jumlah_owner"] == 1


def test_akun_tenant_biasa_ditolak_endpoint_superadmin(two_tenants):
    """Owner tenant biasa (role='admin', terikat tenant_id) SAMA SEKALI
    tidak boleh mengakses endpoint /api/superadmin/* -- require_superadmin
    (auth.py) menolak siapa pun yang role-nya bukan persis 'superadmin'."""
    r = two_tenants["client"].get("/api/superadmin/tenants", headers=two_tenants["headers_a"])
    assert r.status_code == 403


def test_superadmin_ditolak_endpoint_tenant_scoped(app_client):
    """Kebalikannya: akun superadmin (tenant_id=NULL) ditolak
    get_current_tenant_id() (auth.py) dari SEMUA endpoint ber-scope tenant
    biasa -- properti keamanan bawaan yang sudah ada sejak Phase 1, di sini
    diverifikasi secara eksplisit berlaku juga untuk role baru ini."""
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/dashboard/owner", headers=headers)
    assert r.status_code in (403, 404, 422)  # bukan 200 -- ditolak, bukan diteruskan


def test_buat_tenant_baru_lewat_superadmin_dan_owner_bisa_login(app_client):
    headers = _buat_superadmin_dan_login(app_client)

    r = app_client.post("/api/superadmin/tenants", headers=headers, json={
        "slug": "toko-baru", "nama_barbershop": "Toko Baru Sejahtera",
        "owner_username": "ownerbaru", "owner_password": "passwordbaru123",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["slug"] == "toko-baru"
    assert data["status"] == "aktif"
    assert data["jumlah_owner"] == 1

    # Owner toko baru langsung bisa login tanpa langkah manual tambahan.
    r2 = app_client.post("/api/auth/login", json={"username": "ownerbaru", "password": "passwordbaru123"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["tenant"]["slug"] == "toko-baru"


def test_buat_tenant_slug_duplikat_ditolak(two_tenants):
    client = two_tenants["client"]
    headers = _buat_superadmin_dan_login(client)
    r = client.post("/api/superadmin/tenants", headers=headers, json={
        "slug": "test-toko-a", "nama_barbershop": "Duplikat",
        "owner_username": "duplikat", "owner_password": "password123",
    })
    assert r.status_code == 422


def test_nonaktifkan_tenant_membuat_owner_toko_itu_tidak_bisa_login(two_tenants):
    client = two_tenants["client"]
    headers = _buat_superadmin_dan_login(client)

    r = client.put(f"/api/superadmin/tenants/{two_tenants['tenant_a']}/status",
                    headers=headers, json={"status": "nonaktif"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "nonaktif"

    # Sesi Owner Tenant A yang SUDAH login sebelumnya langsung ditolak juga
    # (get_current_user() re-check status tenant tiap request, bukan cuma
    # saat login -- lihat auth.py).
    r2 = client.get("/api/auth/me", headers=two_tenants["headers_a"])
    assert r2.status_code == 401

    # Tenant B (tidak disentuh) tetap normal.
    r3 = client.get("/api/auth/me", headers=two_tenants["headers_b"])
    assert r3.status_code == 200

    # Aktifkan lagi -- Owner Tenant A bisa login lagi.
    r4 = client.put(f"/api/superadmin/tenants/{two_tenants['tenant_a']}/status",
                     headers=headers, json={"status": "aktif"})
    assert r4.status_code == 200
    r5 = client.get("/api/auth/me", headers=two_tenants["headers_a"])
    assert r5.status_code == 200


def test_ubah_status_nilai_tidak_valid_ditolak(two_tenants):
    client = two_tenants["client"]
    headers = _buat_superadmin_dan_login(client)
    r = client.put(f"/api/superadmin/tenants/{two_tenants['tenant_a']}/status",
                    headers=headers, json={"status": "dibekukan"})
    assert r.status_code == 422


def test_detail_tenant_berisi_daftar_user_tanpa_password_hash(two_tenants):
    client = two_tenants["client"]
    headers = _buat_superadmin_dan_login(client)
    r = client.get(f"/api/superadmin/tenants/{two_tenants['tenant_a']}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["slug"] == "test-toko-a"
    assert len(data["users"]) == 1
    assert data["users"][0]["username"] == "ownerA"
    assert "password_hash" not in data["users"][0]


# ---------------------------------------------------------------------------
# FITUR Alamat Website Tenant (kolom "Alamat Website" Dashboard Super Admin)
# ---------------------------------------------------------------------------

def test_daftar_tenant_berisi_website_url_dari_slug(two_tenants):
    """Tenant TANPA custom_domain -- website_url dibentuk otomatis dari slug
    (https://<slug>.rivoirsett.com), TERSEDIA LANGSUNG begitu tenant dibuat
    (item 6), TANPA perlu langkah "simpan" tambahan apa pun."""
    client = two_tenants["client"]
    headers = _buat_superadmin_dan_login(client)
    r = client.get("/api/superadmin/tenants", headers=headers)
    assert r.status_code == 200, r.text
    by_slug = {t["slug"]: t for t in r.json()}
    assert by_slug["test-toko-a"]["website_url"] == "https://test-toko-a.rivoirsett.com"
    assert by_slug["test-toko-b"]["website_url"] == "https://test-toko-b.rivoirsett.com"


def test_website_url_ikut_custom_domain_kalau_diisi(two_tenants):
    """Kalau tenant sudah punya custom_domain (kolom SUDAH ADA di skema
    sejak Phase 1, sebelumnya tidak pernah dibaca), website_url HARUS ikut
    custom_domain itu, bukan subdomain slug lagi -- otomatis, TANPA
    mengubah baris manapun (item 7)."""
    import database as db

    client = two_tenants["client"]
    headers = _buat_superadmin_dan_login(client)
    with db.get_conn() as conn:
        conn.execute("UPDATE tenants SET custom_domain = ? WHERE id = ?",
                     ("mugenhairco.com", two_tenants["tenant_a"]))
        conn.commit()

    r = client.get("/api/superadmin/tenants", headers=headers)
    by_slug = {t["slug"]: t for t in r.json()}
    assert by_slug["test-toko-a"]["website_url"] == "https://mugenhairco.com"
    # Tenant lain (tanpa custom_domain) TIDAK ikut berubah.
    assert by_slug["test-toko-b"]["website_url"] == "https://test-toko-b.rivoirsett.com"


def test_detail_tenant_berisi_website_url(two_tenants):
    client = two_tenants["client"]
    headers = _buat_superadmin_dan_login(client)
    r = client.get(f"/api/superadmin/tenants/{two_tenants['tenant_a']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["website_url"] == "https://test-toko-a.rivoirsett.com"


def test_get_website_url_tanpa_slug_maupun_custom_domain_kembalikan_none():
    """Kasus defensif (item 5, "Belum dibuat") -- tidak pernah terjadi untuk
    tenant yang dibuat lewat tenant_db.buat_tenant() (slug wajib diisi),
    tapi fungsi murni ini harus tetap aman untuk data tidak lengkap."""
    import tenant_db
    assert tenant_db.get_website_url({"slug": "", "custom_domain": ""}) is None
    assert tenant_db.get_website_url({}) is None


def test_bootstrap_superadmin_dari_env_var(db_path, monkeypatch):
    """FONDASI Multi-Tenant Phase 2.1: main.py::_bootstrap_superadmin_pertama()
    HANYA jalan kalau KEDUA environment variable diisi eksplisit (beda dari
    _bootstrap_admin_pertama() yang selalu jalan dengan default kalau users
    kosong) -- diverifikasi di sini lewat monkeypatch SEBELUM TestClient
    (dan startup event-nya) dibuat."""
    monkeypatch.setenv("SUPERADMIN_BOOTSTRAP_USERNAME", "rootadmin")
    monkeypatch.setenv("SUPERADMIN_BOOTSTRAP_PASSWORD", "passwordroot123")

    import database
    import auth_db as auth_db_module

    database.DB_PATH = db_path
    auth_db_module.DB_PATH = db_path

    import main
    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        r = client.post("/api/auth/login", json={"username": "rootadmin", "password": "passwordroot123"})
        assert r.status_code == 200, r.text
        assert r.json()["tenant"] is None

        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        r2 = client.get("/api/superadmin/tenants", headers=headers)
        assert r2.status_code == 200


def test_tanpa_env_var_tidak_ada_superadmin_dibuat(app_client):
    """Kebalikan test di atas -- fixture app_client BAWAAN (tanpa env var
    SUPERADMIN_BOOTSTRAP_*) tidak pernah membuat akun superadmin apa pun."""
    daftar = auth_db.get_user_list()
    assert not any(u["role"] == "superadmin" for u in daftar)


def test_audit_log_mencatat_buat_tenant_dan_ubah_status(app_client):
    """FONDASI Multi-Tenant Phase 2.1 (hardening): SETIAP aksi lifecycle
    tenant lewat Dashboard Super Admin (buat toko, aktifkan, nonaktifkan)
    WAJIB tercatat di superadmin_audit_log -- lihat superadmin_audit_db.py."""
    headers = _buat_superadmin_dan_login(app_client, username="auditor1")

    r = app_client.post("/api/superadmin/tenants", headers=headers, json={
        "slug": "toko-audit", "nama_barbershop": "Toko Audit",
        "owner_username": "owneraudit", "owner_password": "password123",
    })
    assert r.status_code == 200, r.text
    tenant_id = r.json()["id"]

    app_client.put(f"/api/superadmin/tenants/{tenant_id}/status", headers=headers, json={"status": "nonaktif"})
    app_client.put(f"/api/superadmin/tenants/{tenant_id}/status", headers=headers, json={"status": "aktif"})

    r2 = app_client.get("/api/superadmin/audit-log", headers=headers)
    assert r2.status_code == 200, r2.text
    log = r2.json()
    # terbaru dulu -- tiga aksi terakhir persis urutan sebaliknya dari yang dilakukan di atas.
    aksi_tenant_audit = [e for e in log if e["tenant_slug"] == "toko-audit"]
    assert [e["aksi"] for e in aksi_tenant_audit] == ["aktifkan_tenant", "nonaktifkan_tenant", "buat_tenant"]
    for e in aksi_tenant_audit:
        assert e["superadmin_username"] == "auditor1"
        assert e["tenant_id"] == tenant_id


def test_audit_log_ditolak_untuk_akun_tenant_biasa(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/audit-log", headers=two_tenants["headers_a"])
    assert r.status_code == 403


# =============================================================================
# BUGFIX: superadmin TIDAK BOLEH PERNAH diblokir oleh status tenant mana pun,
# bahkan kalau (lewat data korup/jalur lama di luar tambah_user()) baris
# usernya entah bagaimana punya tenant_id terisi dan tenant itu 'nonaktif' --
# login() (routers/auth_router.py) dan get_current_user() (auth.py) sekarang
# mengecek role='superadmin' LANGSUNG, bukan cuma bergantung pada invarian
# "superadmin selalu tenant_id=None". Regresi tenant biasa (owner/admin/
# barber TETAP diblokir kalau tenant-nya nonaktif) tetap diverifikasi di
# bawah supaya perbaikan ini tidak melonggarkan validasi akun tenant biasa.
# =============================================================================

def test_superadmin_bisa_login_walau_tenant_id_terisi_dan_nonaktif(app_client):
    """Simulasi data korup/jalur lama di luar tambah_user() -- superadmin
    seharusnya TIDAK PERNAH dibuat dengan tenant_id terisi, tapi kalau
    entah bagaimana terjadi (mis. migrasi data lama), login harus tetap
    berhasil selama pengecekan berbasis role, bukan hanya tenant_id."""
    import tenant_db

    tenant_id = tenant_db.buat_tenant("toko-korup", "Toko Korup")
    tenant_db.set_status(tenant_id, "nonaktif")

    superadmin_id = auth_db.tambah_user("superadmin_korup", "rahasia123", role="superadmin", tenant_id=None)
    with auth_db.get_conn() as conn:
        conn.execute("UPDATE users SET tenant_id = ? WHERE id = ?", (tenant_id, superadmin_id))

    r = app_client.post("/api/auth/login", json={"username": "superadmin_korup", "password": "rahasia123"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "superadmin"

    # get_current_user() (dipakai endpoint lain, mis. /api/auth/me) juga
    # tidak boleh ikut memblokir -- bukan cuma endpoint login.
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    r2 = app_client.get("/api/auth/me", headers=headers)
    assert r2.status_code == 200, r2.text


def test_superadmin_normal_tenant_id_none_tetap_bisa_login(app_client):
    """Baseline (bukan skenario korup): superadmin yang dibuat lewat jalur
    normal (tenant_id=None, tanpa tenant sama sekali) tetap bisa login --
    memastikan perbaikan tidak mengubah perilaku jalur yang sudah benar."""
    headers = _buat_superadmin_dan_login(app_client, username="superadmin_normal")
    r = app_client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "superadmin"


def test_owner_tenant_nonaktif_tetap_ditolak_login(two_tenants):
    """Regresi: perbaikan superadmin TIDAK boleh melonggarkan validasi
    akun tenant biasa -- Owner tenant yang di-nonaktifkan tetap ditolak
    login, persis seperti sebelum perbaikan ini."""
    import tenant_db

    tenant_db.set_status(two_tenants["tenant_a"], "nonaktif")
    r = two_tenants["client"].post("/api/auth/login", json={"username": "ownerA", "password": "passwordA123"})
    assert r.status_code == 401, r.text
    assert "tidak aktif" in r.json()["detail"].lower()


def test_owner_tenant_aktif_tetap_bisa_login_normal(two_tenants):
    """Regresi: Owner tenant AKTIF tetap login normal seperti biasa."""
    r = two_tenants["client"].post("/api/auth/login", json={"username": "ownerA", "password": "passwordA123"})
    assert r.status_code == 200, r.text
    assert r.json()["tenant"]["slug"] == "test-toko-a"


# =============================================================================
# FITUR Hapus Tenant -- penghapusan PERMANEN tenant testing/development,
# lihat tenant_db.hapus_tenant() untuk daftar lengkap tabel yang dibersihkan
# & urutan FK-nya, dan routers/superadmin.py::hapus_tenant() untuk lapis
# konfirmasi slug yang ditegakkan backend.
# =============================================================================

def _isi_data_lengkap(tenant_id: int, prefix: str):
    """Isi satu tenant dengan data di banyak tabel sekaligus (barber, service,
    transaksi, transaksi_detail, settings) -- dipakai memverifikasi cascade
    delete benar-benar membersihkan SEMUANYA, bukan cuma baris `tenants`."""
    import database as db

    barber_id = db.add_barber(f"{prefix}-barber", tenant_id=tenant_id)
    service_id = db.add_service(f"{prefix}-service", 50000, tenant_id=tenant_id)
    transaksi_id = db.tambah_transaksi("2026-08-01", barber_id, [{"service_id": service_id, "jumlah": 1}])
    with db.get_conn() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (f"{tenant_id}:kunci_test", "nilai_test"))
    return {"barber_id": barber_id, "service_id": service_id, "transaksi_id": transaksi_id}


def test_hapus_tenant_membersihkan_semua_tabel_tanpa_menyentuh_tenant_lain(two_tenants):
    import database as db
    import tenant_db

    tenant_a = two_tenants["tenant_a"]
    tenant_b = two_tenants["tenant_b"]
    data_a = _isi_data_lengkap(tenant_a, "a")
    data_b = _isi_data_lengkap(tenant_b, "b")

    hasil = tenant_db.hapus_tenant(tenant_a)
    assert hasil["slug"] == "test-toko-a"

    # Tenant A + SELURUH data anaknya benar-benar hilang.
    assert tenant_db.get_tenant(tenant_a) is None
    assert db.get_barber(data_a["barber_id"]) is None
    with db.get_conn() as conn:
        assert conn.execute("SELECT * FROM services WHERE id = ?", (data_a["service_id"],)).fetchone() is None
        assert conn.execute("SELECT * FROM transaksi WHERE id = ?", (data_a["transaksi_id"],)).fetchone() is None
        assert conn.execute("SELECT * FROM transaksi_detail WHERE transaksi_id = ?",
                             (data_a["transaksi_id"],)).fetchone() is None
        assert conn.execute("SELECT * FROM settings WHERE key = ?", (f"{tenant_a}:kunci_test",)).fetchone() is None
        # users (Owner "ownerA") ikut terhapus -- tidak ada lagi akun yatim.
        assert conn.execute("SELECT * FROM users WHERE tenant_id = ?", (tenant_a,)).fetchall() == []

    # Tenant B (dan seluruh datanya) SAMA SEKALI tidak tersentuh.
    assert tenant_db.get_tenant(tenant_b) is not None
    assert db.get_barber(data_b["barber_id"]) is not None
    with db.get_conn() as conn:
        assert conn.execute("SELECT * FROM services WHERE id = ?", (data_b["service_id"],)).fetchone() is not None
        assert conn.execute("SELECT * FROM settings WHERE key = ?", (f"{tenant_b}:kunci_test",)).fetchone() is not None
        users_b = conn.execute("SELECT * FROM users WHERE tenant_id = ?", (tenant_b,)).fetchall()
        assert len(users_b) == 1


def test_hapus_tenant_tidak_bisa_hapus_mugen_hair_co(two_tenants):
    """Penjaga keselamatan KERAS -- tenant utama TIDAK PERNAH bisa dihapus
    lewat fungsi ini, apa pun alasannya."""
    import tenant_db

    default_tenant = tenant_db.get_tenant_by_slug(tenant_db.SLUG_TENANT_DEFAULT)
    assert default_tenant is not None, "tenant default seharusnya sudah dibuat migrasi saat boot"
    try:
        tenant_db.hapus_tenant(default_tenant["id"])
        assert False, "Harus ditolak: tidak boleh menghapus tenant utama"
    except ValueError as e:
        assert "utama" in str(e).lower() or "mugen-hair-co" in str(e).lower()
    # Tetap ada, tidak berubah sama sekali.
    assert tenant_db.get_tenant(default_tenant["id"]) is not None


def test_hapus_tenant_tidak_bisa_hapus_tenant_terakhir(app_client):
    """Penjaga keselamatan KERAS kedua -- kalau (secara hipotetis) hanya
    tersisa satu tenant, tenant itu tidak boleh dihapus supaya aplikasi
    tidak pernah kehilangan tenant sama sekali. Slug tenant satu-satunya
    ini diganti dulu lewat SQL langsung (bypass hapus_tenant()) supaya
    penjaga PERTAMA (tidak boleh hapus mugen-hair-co) tidak ikut memblokir
    -- murni menguji penjaga KEDUA secara terisolasi. Di produksi
    sungguhan skenario "tenant terakhir BUKAN mugen-hair-co" tidak pernah
    terjadi (tenant default selalu ada & tidak bisa dihapus) -- ini murni
    pengujian defense-in-depth untuk penjaga keduanya."""
    import tenant_db
    import database as db

    semua = tenant_db.list_tenants()
    assert len(semua) == 1  # hanya tenant default, dibuat migrasi saat boot
    tenant_id = semua[0]["id"]
    with db.get_conn() as conn:
        conn.execute("UPDATE tenants SET slug = ? WHERE id = ?", ("bukan-default", tenant_id))
    try:
        tenant_db.hapus_tenant(tenant_id)
        assert False, "Harus ditolak: tidak boleh menghapus satu-satunya tenant"
    except ValueError as e:
        assert "satu-satunya" in str(e).lower()


def test_hapus_tenant_tenant_tidak_ada_ditolak():
    import tenant_db

    try:
        tenant_db.hapus_tenant(999999)
        assert False, "Harus ditolak: tenant tidak ditemukan"
    except ValueError as e:
        assert "tidak ditemukan" in str(e).lower()


def test_endpoint_hapus_tenant_konfirmasi_slug_salah_ditolak(two_tenants):
    headers = _buat_superadmin_dan_login(two_tenants["client"])
    r = two_tenants["client"].request(
        "DELETE", f"/api/superadmin/tenants/{two_tenants['tenant_a']}",
        headers=headers, json={"konfirmasi_slug": "slug-yang-salah"},
    )
    assert r.status_code == 422, r.text
    assert "tidak cocok" in r.json()["detail"].lower()
    # Tenant TETAP ada -- konfirmasi salah tidak menghapus apa pun.
    import tenant_db
    assert tenant_db.get_tenant(two_tenants["tenant_a"]) is not None


def test_endpoint_hapus_tenant_berhasil_dan_tercatat_di_audit_log(two_tenants):
    import tenant_db
    import superadmin_audit_db

    headers = _buat_superadmin_dan_login(two_tenants["client"])
    r = two_tenants["client"].request(
        "DELETE", f"/api/superadmin/tenants/{two_tenants['tenant_a']}",
        headers=headers, json={"konfirmasi_slug": "test-toko-a"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "test-toko-a"
    assert tenant_db.get_tenant(two_tenants["tenant_a"]) is None

    log = superadmin_audit_db.list_log()
    entri = next((l for l in log if l["aksi"] == "hapus_tenant"), None)
    assert entri is not None, "aksi hapus_tenant harus tercatat di audit log"
    assert entri["tenant_slug"] == "test-toko-a"

    # Owner tenant yang sudah dihapus tidak bisa login lagi sama sekali.
    r2 = two_tenants["client"].post("/api/auth/login", json={"username": "ownerA", "password": "passwordA123"})
    assert r2.status_code == 401, r2.text


def test_endpoint_hapus_tenant_mugen_hair_co_ditolak_dengan_422(two_tenants):
    import tenant_db

    default_tenant = tenant_db.get_tenant_by_slug(tenant_db.SLUG_TENANT_DEFAULT)
    headers = _buat_superadmin_dan_login(two_tenants["client"])
    r = two_tenants["client"].request(
        "DELETE", f"/api/superadmin/tenants/{default_tenant['id']}",
        headers=headers, json={"konfirmasi_slug": default_tenant["slug"]},
    )
    assert r.status_code == 422, r.text
    assert tenant_db.get_tenant(default_tenant["id"]) is not None


def test_endpoint_hapus_tenant_akun_biasa_ditolak(two_tenants):
    """Akun tenant biasa (bukan superadmin) tidak bisa memanggil endpoint
    ini sama sekali -- require_superadmin (auth.py) menolak lebih dulu,
    sebelum sempat memeriksa konfirmasi slug apa pun."""
    r = two_tenants["client"].request(
        "DELETE", f"/api/superadmin/tenants/{two_tenants['tenant_b']}",
        headers=two_tenants["headers_a"], json={"konfirmasi_slug": "test-toko-b"},
    )
    assert r.status_code == 403
    import tenant_db
    assert tenant_db.get_tenant(two_tenants["tenant_b"]) is not None
