"""Regresi FITUR URL Booking Publik per Tenant (booking_slug):
- Auto-generate saat tenant dibuat (item 2 spesifikasi).
- Format + keunikan (pool gabungan slug+booking_slug+label reservasi).
- Resolusi publik lewat booking_slug (fallback dari slug, item 3/4).
- Endpoint edit (item 7): validasi format/keunikan, Booking URL ikut
  berubah otomatis.
- Super Admin: kolom booking_url (item 8).
- Regresi: login/branding/dashboard/Super Admin TIDAK terganggu (item 10)."""

import tenant_db


def test_booking_slug_dibuat_otomatis_saat_tenant_dibuat(app_client):
    tenant_id = tenant_db.buat_tenant("bubbleshot", "Bubble Shot")
    t = tenant_db.get_tenant(tenant_id)
    assert t["booking_slug"] == "bubbleshot"


def test_buat_slug_unik_slugify_dan_collision_numbering(app_client):
    """Sama persis contoh spesifikasi: "Bubble Shot" -> "bubbleshot",
    tabrakan -> "bubbleshot2", "bubbleshot3", dst -- angka LANGSUNG
    menempel tanpa pemisah. (BUKAN "Mugen Hair Co" -- tenant DEFAULT hasil
    boot aplikasi persis bernama itu, lihat tenant_migrasi.py, jadi basis
    "mugenhairco" SUDAH terpakai booking_slug-nya sejak app_client boot --
    dites terpisah di test_booking_slug_direservasi_kalau_bertabrakan_....)."""
    assert tenant_db.buat_slug_unik("Bubble Shot") == "bubbleshot"
    tenant_db.buat_tenant("bubbleshot", "Bubble Shot")
    assert tenant_db.buat_slug_unik("Bubble Shot") == "bubbleshot2"
    tenant_db.buat_tenant("bubbleshot2", "Bubble Shot (Cabang 2)")
    assert tenant_db.buat_slug_unik("Bubble Shot") == "bubbleshot3"


def test_buat_slug_unik_hanya_huruf_kecil_dan_angka(app_client):
    assert tenant_db.buat_slug_unik("Bubble Shot!! ") == "bubbleshot"
    assert tenant_db.buat_slug_unik("  ") == "toko"


def test_booking_slug_direservasi_kalau_bertabrakan_dengan_slug_tenant_lain(app_client):
    """FITUR URL Booking Publik per Tenant: pool keunikan GABUNGAN --
    booking_slug tenant baru tidak boleh sama dengan `slug` MAUPUN
    `booking_slug` tenant lain manapun, supaya tidak pernah ada dua tenant
    kebagian subdomain publik yang sama. Dibuktikan lewat tenant DEFAULT
    hasil boot aplikasi (slug "mugen-hair-co", nama "MUGEN Hair Co.",
    lihat tenant_migrasi.py) -- booking_slug-nya di-backfill OTOMATIS ke
    "mugenhairco" saat app_client boot (lihat booking_slug_migrasi.py),
    jadi tenant BARU bernama sama harus otomatis dapat "mugenhairco2"."""
    assert tenant_db.get_tenant_by_slug("mugen-hair-co")["booking_slug"] == "mugenhairco"
    assert tenant_db.buat_slug_unik("MUGEN Hair Co") == "mugenhairco2"


def test_booking_slug_reservasi_label_sistem(app_client):
    import tenant_middleware
    assert tenant_db.buat_slug_unik("Admin") not in tenant_middleware.LABEL_BUKAN_TENANT
    assert tenant_db.buat_slug_unik("Admin") == "admin2"


def test_resolusi_publik_lewat_booking_slug_setelah_diedit(two_tenants):
    """Item 3/4/7: booking_slug tenant diedit jadi berbeda dari slug-nya
    sendiri -- endpoint publik booking (via query string `tenant=`, SAMA
    mekanisme dengan resolusi subdomain lewat middleware) HARUS tetap
    menemukan tenant yang benar lewat booking_slug baru itu."""
    client = two_tenants["client"]
    r = client.put(
        "/api/booking/booking-slug", json={"booking_slug": "customslugunik"},
        headers=two_tenants["headers_a"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["booking_slug"] == "customslugunik"
    assert r.json()["booking_url"].startswith("https://customslugunik.")
    assert r.json()["booking_url"].endswith("/app/#/book")

    # Resolusi publik: slug LAMA ("test-toko-a") TIDAK LAGI relevan untuk
    # booking_slug (kolom `slug` tenant TIDAK IKUT berubah, tetap valid
    # lewat jalur `slug` sendiri) -- booking_slug BARU harus resolve ke
    # tenant yang sama (barbers publik tenant A kosong tapi endpoint harus
    # tetap 200, BUKAN 404 "Barbershop tidak ditemukan").
    r2 = client.get("/api/public/booking/barbers?tenant=customslugunik")
    assert r2.status_code == 200, r2.text


def test_edit_booking_slug_ditolak_kalau_format_salah(two_tenants):
    client = two_tenants["client"]
    for buruk in ("Ada Spasi", "huruf-strip", "huruf_underscore", "", "kapital ALL"):
        r = client.put("/api/booking/booking-slug", json={"booking_slug": buruk},
                        headers=two_tenants["headers_a"])
        assert r.status_code == 422, buruk


def test_edit_booking_slug_ditolak_kalau_sudah_dipakai_tenant_lain(two_tenants):
    client = two_tenants["client"]
    slug_b = tenant_db.get_tenant(two_tenants["tenant_b"])["booking_slug"]
    r = client.put("/api/booking/booking-slug", json={"booking_slug": slug_b},
                    headers=two_tenants["headers_a"])
    assert r.status_code == 422, r.text
    assert "tidak tersedia" in r.json()["detail"] or "sudah dipakai" in r.json()["detail"]


def test_edit_booking_slug_boleh_dipertahankan_sama_seperti_semula(two_tenants):
    """`kecuali_tenant_id` di set_booking_slug() -- tenant tidak dianggap
    bertabrakan dengan slug/booking_slug MILIKNYA SENDIRI saat disimpan
    ulang dengan nilai yang sama."""
    client = two_tenants["client"]
    slug_a = tenant_db.get_tenant(two_tenants["tenant_a"])["booking_slug"]
    r = client.put("/api/booking/booking-slug", json={"booking_slug": slug_a},
                    headers=two_tenants["headers_a"])
    assert r.status_code == 200, r.text


def test_ambil_booking_slug(two_tenants):
    client = two_tenants["client"]
    r = client.get("/api/booking/booking-slug", headers=two_tenants["headers_a"])
    assert r.status_code == 200, r.text
    assert r.json()["booking_slug"]
    assert r.json()["booking_url"].endswith("/app/#/book")


def test_booking_page_not_found_saat_slug_tidak_dikenal(app_client):
    """Item 9 spesifikasi: slug/booking_slug yang TIDAK ADA sama sekali ->
    404 (BUKAN error server 500) -- frontend book_public.js yang
    menerjemahkan status 404 ini jadi "Booking page not found"."""
    r = app_client.get("/api/public/booking/subscription-status?tenant=tidak-ada-begini")
    assert r.status_code == 404, r.text


def test_superadmin_tenant_list_ada_kolom_booking_url(two_tenants):
    """Item 8 spesifikasi: Super Admin -- kolom booking_url."""
    import auth_db
    auth_db.tambah_user("superadmin1", "passwordsuper123", role="superadmin", tenant_id=None)
    r = two_tenants["client"].post(
        "/api/auth/login", json={"username": "superadmin1", "password": "passwordsuper123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    r2 = two_tenants["client"].get("/api/superadmin/tenants", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200, r2.text
    daftar = {t["slug"]: t for t in r2.json()}
    assert daftar["test-toko-a"]["booking_url"].endswith("/app/#/book")
    assert "customslugunik" not in daftar  # sanity: belum diedit di test ini


def test_regresi_login_branding_tidak_terganggu(two_tenants):
    """Item 10 spesifikasi: fitur booking_slug TIDAK BOLEH mengganggu
    Login/Dashboard/Branding sama sekali -- sanity check singkat."""
    client = two_tenants["client"]
    r = client.post("/api/auth/login", json={"username": "ownerA", "password": "passwordA123"})
    assert r.status_code == 200, r.text
    assert r.json()["tenant"]["slug"] == "test-toko-a"

    r2 = client.get("/api/tenant/branding", headers={"X-Tenant-Slug": "test-toko-a"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["is_platform_default"] is False


def test_regresi_branding_subdomain_booking_slug_tidak_dianggap_tenant_tidak_ditemukan(two_tenants):
    """FITUR URL Booking Publik per Tenant: begitu tenant mengedit
    booking_slug jadi berbeda dari slug, subdomain booking_slug BARU harus
    tetap dianggap "tenant ditemukan" lewat /api/tenant/branding (dipakai
    tenant_guard.js) -- BUKAN "Tenant Tidak Ditemukan", supaya customer
    yang membuka subdomain booking_slug tidak diblokir sebelum sempat
    masuk ke halaman booking sama sekali."""
    client = two_tenants["client"]
    client.put("/api/booking/booking-slug", json={"booking_slug": "bslugberbeda"},
               headers=two_tenants["headers_a"])
    r = client.get("/api/tenant/branding", headers={"X-Tenant-Slug": "bslugberbeda"})
    assert r.status_code == 200, r.text
    assert r.json()["is_platform_default"] is False
