"""test_bandwidth_cache_header.py -- Optimasi bandwidth Render (HTTP).

Cakupan: endpoint penyajian file upload (logo/favicon/hero image/hero
video/foto About/foto galeri/foto barber publik/QRIS publik) sekarang
immutable-cacheable SELAMA query `?v=<nama_file_unik>` ada di request
(nama file selalu uuid4 per upload, lihat r2_storage.py) -- browser/CDN
boleh menyimpannya selama-lamanya karena URL berubah otomatis begitu file
diganti. Permintaan TANPA `v` (jalur lama/langsung) dan SEMUA endpoint
JSON biasa TETAP `Cache-Control: no-store` seperti sebelum perbaikan ini,
tidak ada perubahan perilaku untuk kasus itu."""

import io

import database as db
import subscription_db


def _png_1x1():
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )


def _files():
    return {"file": ("foto.png", io.BytesIO(_png_1x1()), "image/png")}


def test_logo_dengan_v_immutable_cacheable(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    r_upload = client.post("/api/pengaturan/logo", headers=headers, files=_files())
    assert r_upload.status_code == 200, r_upload.text
    logo_url = r_upload.json()["logo_url"]
    assert "?v=" in logo_url

    r = client.get(logo_url, headers=headers)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_logo_tanpa_v_tetap_no_store(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    client.post("/api/pengaturan/logo", headers=headers, files=_files())

    r = client.get("/api/pengaturan/logo", headers=headers)  # TANPA query ?v=
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"


def test_favicon_dengan_v_immutable_cacheable(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    r_upload = client.post("/api/pengaturan/favicon", headers=headers, files=_files())
    assert r_upload.status_code == 200, r_upload.text
    favicon_url = r_upload.json()["favicon_url"]
    assert "?v=" in favicon_url

    r = client.get(favicon_url, headers=headers)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_hero_image_dengan_v_immutable_cacheable(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    r_upload = client.post("/api/website/hero-image", headers=headers, files=_files())
    assert r_upload.status_code == 200, r_upload.text
    hero_url = r_upload.json()["hero_image_url"]
    assert "?v=" in hero_url

    r = client.get(hero_url, headers=headers)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_about_foto_dengan_v_immutable_cacheable(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    r_upload = client.post("/api/website/about-foto", headers=headers, files=_files())
    assert r_upload.status_code == 200, r_upload.text
    foto_url = r_upload.json()["about_foto_url"]
    assert "?v=" in foto_url

    r = client.get(foto_url, headers=headers)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_gallery_foto_dengan_v_immutable_cacheable(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    r_upload = client.post("/api/website/gallery", headers=headers, files=_files())
    assert r_upload.status_code == 200, r_upload.text
    foto_url = r_upload.json()[0]["foto_url"]
    assert "?v=" in foto_url

    r = client.get(foto_url, headers=headers)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_barber_foto_publik_dengan_v_immutable_cacheable(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    barber_id = db.add_barber("Andi Saputra", tenant_id=single_tenant["tenant_id"])
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    r_upload = client.post(f"/api/booking/barber/{barber_id}/foto", headers=headers, files=_files())
    assert r_upload.status_code == 200, r_upload.text

    r_list = client.get("/api/public/booking/barbers", params={"tenant": "test-toko"})
    assert r_list.status_code == 200, r_list.text
    foto_url = next(b["foto_url"] for b in r_list.json() if b["id"] == barber_id)
    assert "?v=" in foto_url

    r = client.get(foto_url)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_qris_publik_dengan_v_immutable_cacheable(single_tenant):
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    r_upload = client.post("/api/booking/qris", headers=headers, files=_files())
    assert r_upload.status_code == 200, r_upload.text

    r_pengaturan = client.get("/api/public/booking/pengaturan", params={"tenant": "test-toko"})
    assert r_pengaturan.status_code == 200, r_pengaturan.text
    qris_url = r_pengaturan.json()["qris_url"]
    assert "?v=" in qris_url

    r = client.get(qris_url)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_endpoint_json_biasa_tetap_no_store(single_tenant):
    """Regresi: endpoint JSON apa pun (bukan penyajian file upload) TIDAK
    ikut kena pengecualian -- tetap no-store seperti sebelum perbaikan."""
    client = single_tenant["client"]
    headers = single_tenant["headers"]
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"


def test_gzip_middleware_terpasang():
    """Optimasi bandwidth: GZipMiddleware terpasang di app -- Starlette
    sendiri yang menangani kompresi transparan per-response berdasarkan
    header Accept-Encoding client, tidak perlu diuji ulang di sini (sudah
    dites proyek Starlette sendiri); cukup pastikan middleware-nya benar
    terpasang pada app ini."""
    import main
    from starlette.middleware.gzip import GZipMiddleware

    assert any(mw.cls is GZipMiddleware for mw in main.app.user_middleware)
