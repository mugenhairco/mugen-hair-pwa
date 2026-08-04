"""routers/landing.py — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
=============================================================================
Dua router dalam SATU file ini (pola sama seperti routers/billing.py):

1. `public_router` (prefix `/api/public/landing`) — TANPA login sama sekali
   (halaman Landing Page publik): FAQ, Testimonial, statistik (live + manual),
   info kontak platform, dan katalog paket aktif (VERSI PUBLIK dari
   billing.daftar_paket_aktif -- TIDAK butuh Owner login, hanya field yang
   memang aman ditampilkan siapa saja).
2. `router` (prefix `/api/superadmin/landing`) — KHUSUS Super Admin: CRUD
   FAQ/Testimonial, ubah info kontak platform + statistik manual. SETIAP
   aksi ubah tercatat ke superadmin_audit_log, pola sama seperti
   routers/billing.py::superadmin_router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import billing_db
import landing_db
from auth import require_superadmin

public_router = APIRouter(prefix="/api/public/landing", tags=["landing-public"])
router = APIRouter(prefix="/api/superadmin/landing", tags=["landing-superadmin"])


# ============================= Public =============================


@public_router.get("/faq")
def faq_publik():
    return landing_db.list_faq(hanya_aktif=True)


@public_router.get("/testimonials")
def testimonials_publik():
    return landing_db.list_testimonials(hanya_aktif=True)


@public_router.get("/contact")
def contact_publik():
    return landing_db.get_contact()


@public_router.get("/stats")
def stats_publik():
    hasil = landing_db.get_live_stats()
    hasil.update(landing_db.get_manual_stats())
    return hasil


@public_router.get("/packages")
def packages_publik():
    """Versi PUBLIK billing.daftar_paket_aktif() -- katalog paket aktif +
    fitur checkbox per paket (untuk tabel Package Comparison), TANPA butuh
    Owner login (calon tenant belum punya akun sama sekali)."""
    hasil = []
    for paket in billing_db.list_packages(hanya_aktif=True):
        baris = dict(paket)
        baris["fitur"] = billing_db.get_package_features(paket["id"])
        hasil.append(baris)
    return hasil


# ============================= Super Admin: FAQ =============================


class FaqBody(BaseModel):
    pertanyaan: str
    jawaban: str


@router.get("/faq")
def list_faq(user: dict = Depends(require_superadmin)):
    return landing_db.list_faq()


@router.post("/faq")
def tambah_faq(body: FaqBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = landing_db.create_faq(body.pertanyaan, body.jawaban)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return hasil


class FaqUpdateBody(BaseModel):
    pertanyaan: str | None = None
    jawaban: str | None = None
    urutan: int | None = None
    aktif: bool | None = None


@router.put("/faq/{faq_id}")
def ubah_faq(faq_id: int, body: FaqUpdateBody, user: dict = Depends(require_superadmin)):
    fields = body.model_dump(exclude_unset=True)
    try:
        hasil = landing_db.update_faq(faq_id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return hasil


@router.delete("/faq/{faq_id}")
def hapus_faq(faq_id: int, user: dict = Depends(require_superadmin)):
    try:
        landing_db.delete_faq(faq_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


# ============================= Super Admin: Testimonial =============================


class TestimonialBody(BaseModel):
    nama: str
    isi: str
    jabatan_toko: str = ""
    foto_url: str | None = None
    rating: int = 5


@router.get("/testimonials")
def list_testimonials(user: dict = Depends(require_superadmin)):
    return landing_db.list_testimonials()


@router.post("/testimonials")
def tambah_testimonial(body: TestimonialBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = landing_db.create_testimonial(
            body.nama, body.isi, jabatan_toko=body.jabatan_toko, foto_url=body.foto_url, rating=body.rating,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return hasil


class TestimonialUpdateBody(BaseModel):
    nama: str | None = None
    isi: str | None = None
    jabatan_toko: str | None = None
    foto_url: str | None = None
    rating: int | None = None
    urutan: int | None = None
    aktif: bool | None = None


@router.put("/testimonials/{testimonial_id}")
def ubah_testimonial(testimonial_id: int, body: TestimonialUpdateBody, user: dict = Depends(require_superadmin)):
    fields = body.model_dump(exclude_unset=True)
    try:
        hasil = landing_db.update_testimonial(testimonial_id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return hasil


@router.delete("/testimonials/{testimonial_id}")
def hapus_testimonial(testimonial_id: int, user: dict = Depends(require_superadmin)):
    try:
        landing_db.delete_testimonial(testimonial_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


# ============================= Super Admin: Kontak & Statistik =============================


@router.get("/contact")
def contact_superadmin(user: dict = Depends(require_superadmin)):
    return landing_db.get_contact()


@router.put("/contact")
def ubah_contact(body: dict, user: dict = Depends(require_superadmin)):
    landing_db.update_contact(body)
    return landing_db.get_contact()


@router.get("/stats")
def stats_superadmin(user: dict = Depends(require_superadmin)):
    hasil = landing_db.get_live_stats()
    hasil.update(landing_db.get_manual_stats())
    return hasil


@router.put("/stats")
def ubah_stats(body: dict, user: dict = Depends(require_superadmin)):
    landing_db.update_manual_stats(body)
    hasil = landing_db.get_live_stats()
    hasil.update(landing_db.get_manual_stats())
    return hasil
