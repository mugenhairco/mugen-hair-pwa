"""routers/website.py — /api/website/*  (CMS "Website Content")
====================================================================
SEMUA endpoint tulis (PUT/POST/DELETE) di sini KHUSUS Owner (require_admin),
BUKAN lewat sistem izin permissions.py -- staff TIDAK PERNAH bisa diberi
akses ke Website Content, sama seperti tab Komisi/Bonus Service/Hak Akses
Admin di Setting (lihat frontend/js/pages/booking.js: tab ini hanya masuk
daftar tab kalau user.role === "admin").

Endpoint GET (konten & gambar/video/gallery) sengaja PUBLIC (tanpa login) --
ini persis tujuan datanya: ditampilkan di halaman publik /book. Tidak ada
data sensitif toko yang bocor lewat sini.

REVISI STRUKTUR WEBSITE CONTENT: endpoint SEO/Branding warna/Favicon/
Splash Screen DIHAPUS TOTAL (fitur-fitur itu sudah tidak ada lagi). Endpoint
baru: Hero Image (terpisah dari Hero Video, dulu memakai Banner di
pengaturan.py -- sekarang aset sendiri di sini) dan Background Image."""

from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

import r2_storage
import website_content
from auth import require_admin

router = APIRouter(prefix="/api/website", tags=["website"])


class WebsiteContentBody(BaseModel):
    hero_tipe: str = "image"
    tagline: str = ""
    about_judul: str = ""
    about_deskripsi: str = ""
    alamat: str = ""
    visit_maps_embed_url: str = ""
    visit_maps_link: str = ""
    instagram: str = ""
    tiktok: str = ""
    whatsapp: str = ""
    telepon: str = ""
    background_tipe: str = "light"
    background_opacity: int = 20
    booking_cta_judul: str = ""
    booking_cta_subjudul: str = ""
    booking_cta_tombol_teks: str = ""


class GalleryReorderBody(BaseModel):
    ordered_ids: List[int]


# ---------------------------------------------------------------------------
# Konten skalar
# ---------------------------------------------------------------------------

@router.get("/content")
def ambil_content():
    return website_content.get_content()


@router.put("/content")
def simpan_content(body: WebsiteContentBody, user: dict = Depends(require_admin)):
    try:
        website_content.update_content(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return website_content.get_content()


# ---------------------------------------------------------------------------
# Hero Image
# ---------------------------------------------------------------------------

@router.post("/hero-image")
async def upload_hero_image(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    konten = await file.read()
    try:
        website_content.simpan_hero_image(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return website_content.get_content()


@router.get("/hero-image")
def ambil_hero_image(v: str | None = None):
    data, content_type = website_content.get_hero_image_data()
    if data is None:
        raise HTTPException(status_code=404, detail="Hero Image belum diatur.")
    return Response(content=data, media_type=content_type)


@router.delete("/hero-image")
def hapus_hero_image_endpoint(user: dict = Depends(require_admin)):
    website_content.hapus_hero_image()
    return website_content.get_content()


# ---------------------------------------------------------------------------
# Hero Video
# ---------------------------------------------------------------------------

@router.post("/hero-video")
async def upload_hero_video(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    konten = await file.read()
    try:
        website_content.simpan_hero_video(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return website_content.get_content()


@router.get("/hero-video")
def ambil_hero_video(v: str | None = None):
    data, content_type = website_content.get_hero_video_data()
    if data is None:
        raise HTTPException(status_code=404, detail="Hero Video belum diatur.")
    return Response(content=data, media_type=content_type)


@router.delete("/hero-video")
def hapus_hero_video_endpoint(user: dict = Depends(require_admin)):
    website_content.hapus_hero_video()
    return website_content.get_content()


# ---------------------------------------------------------------------------
# Foto About
# ---------------------------------------------------------------------------

@router.post("/about-foto")
async def upload_about_foto(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    konten = await file.read()
    try:
        website_content.simpan_about_foto(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return website_content.get_content()


@router.get("/about-foto")
def ambil_about_foto(v: str | None = None):
    data, content_type = website_content.get_about_foto_data()
    if data is None:
        raise HTTPException(status_code=404, detail="Foto About belum diatur.")
    return Response(content=data, media_type=content_type)


@router.delete("/about-foto")
def hapus_about_foto_endpoint(user: dict = Depends(require_admin)):
    website_content.hapus_about_foto()
    return website_content.get_content()


# ---------------------------------------------------------------------------
# Background Website
# ---------------------------------------------------------------------------

@router.post("/background-image")
async def upload_background_image(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    konten = await file.read()
    try:
        website_content.simpan_background_image(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return website_content.get_content()


@router.get("/background-image")
def ambil_background_image(v: str | None = None):
    data, content_type = website_content.get_background_image_data()
    if data is None:
        raise HTTPException(status_code=404, detail="Background Website belum diatur.")
    return Response(content=data, media_type=content_type)


@router.delete("/background-image")
def hapus_background_image_endpoint(user: dict = Depends(require_admin)):
    website_content.hapus_background_image()
    return website_content.get_content()


# ---------------------------------------------------------------------------
# Gallery
# ---------------------------------------------------------------------------

@router.get("/gallery")
def ambil_gallery():
    return website_content.get_gallery()


@router.post("/gallery")
async def upload_gallery_foto(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    # Satu file per request (SAMA seperti seluruh endpoint upload lain di
    # aplikasi ini) supaya frontend cukup pakai MugenApi.uploadFile() yang
    # sudah ada apa adanya. "Upload banyak foto sekaligus" di sisi UI cukup
    # memanggil endpoint ini berkali-kali (satu per file yang dipilih) --
    # lihat booking.js renderWebsiteContent().
    konten = await file.read()
    try:
        website_content.tambah_gallery_foto(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return website_content.get_gallery()


@router.get("/gallery/{foto_id}/foto")
def ambil_gallery_foto(foto_id: int, v: str | None = None):
    data, content_type = website_content.get_gallery_foto_data(foto_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Foto tidak ditemukan.")
    return Response(content=data, media_type=content_type)


@router.delete("/gallery/{foto_id}")
def hapus_gallery_foto_endpoint(foto_id: int, user: dict = Depends(require_admin)):
    try:
        website_content.hapus_gallery_foto(foto_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return website_content.get_gallery()


@router.put("/gallery/reorder")
def reorder_gallery_endpoint(body: GalleryReorderBody, user: dict = Depends(require_admin)):
    try:
        website_content.reorder_gallery(body.ordered_ids)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return website_content.get_gallery()
