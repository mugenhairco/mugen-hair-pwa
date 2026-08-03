"""
test_branding.py — FONDASI Multi-Tenant Phase 2.2: Tenant & Platform Branding
=============================================================================
Cakupan: fallback branding platform ("Rivoir") saat tenant belum
dikenali, isolasi branding dua tenant, resolusi sesi vs query string,
superadmin selalu platform branding, upload/hapus favicon + validasi,
validasi warna, dan bugfix header/logo PDF (Phase 2.2 juga memperbaiki
laporan_pdf.py -- lihat test_pdf_header_ikut_tenant_yang_benar)."""

import io

import auth_db
import branding_db
import laporan_pdf


def test_branding_platform_default_tanpa_sinyal_tenant(app_client):
    """Tanpa login, tanpa ?tenant=, tanpa header/subdomain -- HARUS branding
    platform ("Rivoir"), BUKAN diam-diam jatuh ke tenant default pertama
    (beda sengaja dari resolve_tenant_publik() yang dipakai /book dkk)."""
    r = app_client.get("/api/tenant/branding")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nama_barbershop"] == "Rivoir"
    assert data["logo_url"] is None
    assert data["favicon_url"] is None
    assert data["is_platform_default"] is True


def test_branding_anonim_dengan_query_tenant(two_tenants):
    client = two_tenants["client"]
    # Owner A mengubah nama tokonya lewat endpoint Branding.
    r = client.put("/api/pengaturan/branding", headers=two_tenants["headers_a"],
                    json={"nama_barbershop": "Toko A Kustom"})
    assert r.status_code == 200, r.text

    r2 = client.get("/api/tenant/branding?tenant=test-toko-a")
    assert r2.status_code == 200, r2.text
    assert r2.json()["nama_barbershop"] == "Toko A Kustom"
    assert r2.json()["is_platform_default"] is False


def test_branding_slug_tidak_dikenal_atau_nonaktif_jatuh_ke_platform(two_tenants):
    client = two_tenants["client"]
    r = client.get("/api/tenant/branding?tenant=toko-yang-tidak-ada")
    assert r.status_code == 200
    assert r.json()["is_platform_default"] is True


def test_branding_isolasi_dua_tenant(two_tenants):
    client = two_tenants["client"]
    client.put("/api/pengaturan/branding", headers=two_tenants["headers_a"],
                json={"nama_barbershop": "Barbershop Alpha", "primary_color": "#FF0000",
                      "tagline": "Tagline Alpha"})
    client.put("/api/pengaturan/branding", headers=two_tenants["headers_b"],
                json={"nama_barbershop": "Barbershop Beta", "primary_color": "#00FF00",
                      "tagline": "Tagline Beta"})

    branding_a = client.get("/api/tenant/branding?tenant=test-toko-a").json()
    branding_b = client.get("/api/tenant/branding?tenant=test-toko-b").json()
    assert branding_a["nama_barbershop"] == "Barbershop Alpha"
    assert branding_a["primary_color"] == "#FF0000"
    assert branding_a["tagline"] == "Tagline Alpha"
    assert branding_b["nama_barbershop"] == "Barbershop Beta"
    assert branding_b["primary_color"] == "#00FF00"
    assert branding_b["tagline"] == "Tagline Beta"
    # Isolasi: tidak ada bocoran silang.
    assert branding_a["nama_barbershop"] != branding_b["nama_barbershop"]


def test_branding_sesi_login_menang_atas_query_string(two_tenants):
    """Owner Tenant A yang sedang login TETAP melihat branding Tenant A
    walau (secara hipotetis, mis. dari cache lama) query string mencoba
    minta tenant lain -- sesi login SELALU prioritas utama, tidak bisa
    disuntik lewat parameter apa pun."""
    client = two_tenants["client"]
    client.put("/api/pengaturan/branding", headers=two_tenants["headers_a"], json={"nama_barbershop": "Punya A"})
    client.put("/api/pengaturan/branding", headers=two_tenants["headers_b"], json={"nama_barbershop": "Punya B"})

    r = client.get("/api/tenant/branding?tenant=test-toko-b", headers=two_tenants["headers_a"])
    assert r.status_code == 200
    assert r.json()["nama_barbershop"] == "Punya A"


def test_superadmin_selalu_branding_platform(app_client):
    auth_db.tambah_user("superadmin1", "password123", role="superadmin", tenant_id=None)
    r = app_client.post("/api/auth/login", json={"username": "superadmin1", "password": "password123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    # Bahkan dengan ?tenant= eksplisit -- superadmin TIDAK PERNAH ikut
    # branding tenant mana pun (sesuai spesifikasi).
    r2 = app_client.get("/api/tenant/branding?tenant=mugen-hair-co", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["nama_barbershop"] == "Rivoir"
    assert r2.json()["is_platform_default"] is True


def test_logout_branding_tidak_berubah_ke_tenant_lain(two_tenants):
    """Endpoint branding TIDAK bergantung status login sama sekali (murni
    query/slug untuk anonim) -- setelah 'logout' (token dibuang di sisi
    client, di server tidak ada state apa pun yang berubah), permintaan
    anonim dengan slug yang SAMA tetap menampilkan tenant yang sama."""
    client = two_tenants["client"]
    client.put("/api/pengaturan/branding", headers=two_tenants["headers_a"], json={"nama_barbershop": "Toko A"})
    sebelum = client.get("/api/tenant/branding?tenant=test-toko-a").json()
    # simulasikan logout: request berikutnya tanpa Authorization header sama sekali
    sesudah = client.get("/api/tenant/branding?tenant=test-toko-a").json()
    assert sebelum["nama_barbershop"] == sesudah["nama_barbershop"] == "Toko A"


def test_branding_staff_tanpa_izin_ditolak(two_tenants):
    client = two_tenants["client"]
    auth_db.tambah_user("staffA", "password123", role="staff", tenant_id=two_tenants["tenant_a"])
    r = client.post("/api/auth/login", json={"username": "staffA", "password": "password123"})
    headers_staff = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.put("/api/pengaturan/branding", headers=headers_staff, json={"nama_barbershop": "Coba Ubah"})
    assert r2.status_code == 403


def test_branding_staff_dengan_izin_bisa_ubah(two_tenants):
    client = two_tenants["client"]
    client.put("/api/pengaturan/hak-akses-admin", headers=two_tenants["headers_a"],
                json={"izin": {"izin_setting_branding": True}})
    auth_db.tambah_user("staffB", "password123", role="staff", tenant_id=two_tenants["tenant_a"])
    r = client.post("/api/auth/login", json={"username": "staffB", "password": "password123"})
    headers_staff = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.put("/api/pengaturan/branding", headers=headers_staff, json={"nama_barbershop": "Diubah Staff"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["nama_barbershop"] == "Diubah Staff"


def test_branding_warna_tidak_valid_ditolak(two_tenants):
    client = two_tenants["client"]
    r = client.put("/api/pengaturan/branding", headers=two_tenants["headers_a"],
                    json={"primary_color": "bukan-warna"})
    assert r.status_code == 422


def _png_1x1() -> bytes:
    # PNG 1x1 transparan minimal (base64 didekode) -- cukup untuk lolos
    # validasi format/MIME, tidak perlu file gambar sungguhan.
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )


def test_upload_favicon_dan_fallback_setelah_hapus(two_tenants):
    client = two_tenants["client"]
    headers = two_tenants["headers_a"]

    # Belum upload -> favicon_url None (fallback platform di frontend).
    assert client.get("/api/tenant/branding?tenant=test-toko-a").json()["favicon_url"] is None

    files = {"file": ("favicon.png", io.BytesIO(_png_1x1()), "image/png")}
    r = client.post("/api/pengaturan/favicon", headers=headers, files=files)
    assert r.status_code == 200, r.text
    favicon_url = r.json()["favicon_url"]
    assert favicon_url is not None

    # GET /favicon dipakai resolve_tenant_hibrid (sama seperti GET /logo) --
    # dites di sini DENGAN sesi login (frontend selalu punya token saat
    # menampilkan preview favicon di tab Branding), bukan anonim murni.
    r2 = client.get(favicon_url, headers=headers)
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "image/png"

    r3 = client.delete("/api/pengaturan/favicon", headers=headers)
    assert r3.status_code == 200
    assert r3.json()["favicon_url"] is None


def test_favicon_format_tidak_valid_ditolak(two_tenants):
    client = two_tenants["client"]
    files = {"file": ("virus.exe", io.BytesIO(b"bukan gambar"), "application/octet-stream")}
    r = client.post("/api/pengaturan/favicon", headers=two_tenants["headers_a"], files=files)
    assert r.status_code == 422


def test_favicon_ukuran_terlalu_besar_ditolak(two_tenants):
    client = two_tenants["client"]
    konten_besar = b"\x89PNG\r\n\x1a\n" + b"0" * (branding_db.MAKS_UKURAN_FAVICON_BYTES + 1)
    files = {"file": ("besar.png", io.BytesIO(konten_besar), "image/png")}
    r = client.post("/api/pengaturan/favicon", headers=two_tenants["headers_a"], files=files)
    assert r.status_code == 422


def test_favicon_isolasi_dua_tenant(two_tenants):
    client = two_tenants["client"]
    files = {"file": ("favicon.png", io.BytesIO(_png_1x1()), "image/png")}
    client.post("/api/pengaturan/favicon", headers=two_tenants["headers_a"], files=files)

    # Tenant B TIDAK ikut punya favicon hanya karena Tenant A upload.
    assert client.get("/api/tenant/branding?tenant=test-toko-b").json()["favicon_url"] is None


def test_favicon_file_lama_dihapus_saat_diganti(two_tenants):
    """Slot tunggal (sama seperti Logo) -- upload KEDUA menggantikan yang
    pertama, bukan menambah baris baru (lihat file_asset_db.py::simpan())."""
    import file_asset_db
    client = two_tenants["client"]
    headers = two_tenants["headers_a"]
    tenant_id = two_tenants["tenant_a"]

    files1 = {"file": ("favicon1.png", io.BytesIO(_png_1x1()), "image/png")}
    client.post("/api/pengaturan/favicon", headers=headers, files=files1)
    nama_file_1 = file_asset_db.ambil_meta("favicon", tenant_id=tenant_id)

    files2 = {"file": ("favicon2.png", io.BytesIO(_png_1x1()), "image/png")}
    client.post("/api/pengaturan/favicon", headers=headers, files=files2)
    nama_file_2 = file_asset_db.ambil_meta("favicon", tenant_id=tenant_id)

    assert nama_file_1 != nama_file_2
    # Hanya SATU baris file_asset untuk key favicon tenant ini (slot tunggal).
    import database as db
    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM file_asset WHERE key LIKE ?",
                          (f"%favicon%",)).fetchone()["n"]
    assert n == 1


def test_pdf_header_ikut_tenant_yang_benar(two_tenants):
    """FONDASI Multi-Tenant Phase 2.2 (bugfix): SEBELUM perbaikan ini,
    _header_footer_factory() tidak pernah menerima tenant_id -- PDF Tenant
    B akan tercetak dengan nama Tenant A. Diverifikasi di sini dengan
    membaca ISI TEKS PDF (bukan cuma "tidak error")."""
    from pypdf import PdfReader

    client = two_tenants["client"]
    client.put("/api/pengaturan/branding", headers=two_tenants["headers_a"], json={"nama_barbershop": "PDF Toko Alpha"})
    client.put("/api/pengaturan/branding", headers=two_tenants["headers_b"], json={"nama_barbershop": "PDF Toko Beta"})

    pdf_a = laporan_pdf.buat_pdf_kasbon_list(barber_id=None, status=None, tahun=None, bulan=None,
                                              dicetak_oleh="tester", tenant_id=two_tenants["tenant_a"])
    pdf_b = laporan_pdf.buat_pdf_kasbon_list(barber_id=None, status=None, tahun=None, bulan=None,
                                              dicetak_oleh="tester", tenant_id=two_tenants["tenant_b"])

    teks_a = PdfReader(io.BytesIO(pdf_a)).pages[0].extract_text()
    teks_b = PdfReader(io.BytesIO(pdf_b)).pages[0].extract_text()

    assert "PDF Toko Alpha" in teks_a
    assert "PDF Toko Beta" not in teks_a
    assert "PDF Toko Beta" in teks_b
    assert "PDF Toko Alpha" not in teks_b


def test_pdf_slip_gaji_header_ikut_tenant_yang_benar(two_tenants):
    """buat_slip_gaji_pdf() beda jalur (baca tenant_id dari dict `slip`,
    BUKAN parameter terpisah -- lihat komentar di laporan_pdf.py), jadi
    diverifikasi terpisah dari test di atas."""
    from pypdf import PdfReader

    client = two_tenants["client"]
    client.put("/api/pengaturan/branding", headers=two_tenants["headers_a"], json={"nama_barbershop": "Slip Toko Alpha"})

    slip_dummy = {
        "nama_barber": "Budi", "tahun": 2026, "bulan": 7,
        "gaji_pokok": 0, "komisi": 0, "tips": 0, "uang_harian": 0, "bonus_customer": 0,
        "penyesuaian_komisi": 0, "reimburse": 0, "bonus_manual": 0, "potongan_kasbon": 0,
        "potongan_lain": 0, "total_diterima": 0, "status": "belum_dibayar", "catatan_potongan": "",
        "dibuat_oleh": "tester", "tenant_id": two_tenants["tenant_a"],
    }
    pdf_bytes = laporan_pdf.buat_slip_gaji_pdf(slip_dummy)
    teks = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()
    assert "Slip Toko Alpha" in teks
