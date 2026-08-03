"""routers/billing.py — FONDASI Multi-Tenant Phase 4: Billing & Payment (Midtrans)
=============================================================================
Modul "konfigurasi paket" + "katalog fitur" (dua task pertama Phase 4) --
KHUSUS Super Admin mengatur atribut subscription_packages (nama/harga/
durasi/status/urutan/deskripsi/limit pemakaian) dan subscription_features
(katalog fitur checkbox per paket). Endpoint Owner (checkout/invoice/
webhook/dst) menyusul di file terpisah sesuai modul, lihat billing_db.py
untuk penjelasan lengkap kenapa tabel-tabel ini BUKAN sistem paket baru
dan kenapa katalog fitur TIDAK menggerbang fungsi apa pun.

SATU router di file ini (`superadmin_router`, prefix
`/api/superadmin/billing`) -- pola sama seperti routers/subscription.py.
Endpoint Owner-facing (GET daftar paket aktif, dsb) akan ditambahkan di
router terpisah begitu modul checkout/billing Owner mulai dibangun."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import billing_db
import superadmin_audit_db
from auth import require_superadmin

superadmin_router = APIRouter(prefix="/api/superadmin/billing", tags=["billing-superadmin"])


@superadmin_router.get("/packages")
def list_packages(user: dict = Depends(require_superadmin)):
    return billing_db.list_packages()


class PackageUpdateBody(BaseModel):
    nama: str | None = None
    harga: int | None = None
    durasi_hari: int | None = None
    aktif: bool | None = None
    urutan: int | None = None
    deskripsi: str | None = None
    max_barber: int | None = None
    max_user: int | None = None
    max_layanan: int | None = None
    max_booking: int | None = None
    max_cabang: int | None = None


@superadmin_router.put("/packages/{package_id}")
def ubah_package(package_id: int, body: PackageUpdateBody, user: dict = Depends(require_superadmin)):
    # exclude_unset: field yang TIDAK dikirim body TIDAK ikut diubah (beda
    # dengan None eksplisit, mis. max_barber=null -- sengaja jadi "tidak
    # dibatasi" -- lihat billing_db.LIMIT_FIELDS).
    fields = body.model_dump(exclude_unset=True)
    try:
        hasil = billing_db.update_package(package_id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_paket_billing", detail=f"package_id={package_id}, fields={fields}")
    return hasil


# ============================= Katalog Fitur =============================

@superadmin_router.get("/features")
def list_features(user: dict = Depends(require_superadmin)):
    return billing_db.list_features()


class FeatureBody(BaseModel):
    kode: str
    nama: str
    deskripsi: str = ""


@superadmin_router.post("/features")
def tambah_feature(body: FeatureBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = billing_db.create_feature(body.kode, body.nama, body.deskripsi)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "tambah_fitur_billing", detail=f"kode={hasil['kode']}")
    return hasil


class FeatureUpdateBody(BaseModel):
    nama: str | None = None
    deskripsi: str | None = None
    aktif: bool | None = None
    urutan: int | None = None


@superadmin_router.put("/features/{feature_id}")
def ubah_feature(feature_id: int, body: FeatureUpdateBody, user: dict = Depends(require_superadmin)):
    fields = body.model_dump(exclude_unset=True)
    try:
        hasil = billing_db.update_feature(feature_id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_fitur_billing", detail=f"feature_id={feature_id}, fields={fields}")
    return hasil


@superadmin_router.delete("/features/{feature_id}")
def hapus_feature(feature_id: int, user: dict = Depends(require_superadmin)):
    feature = billing_db.get_feature(feature_id)
    try:
        billing_db.delete_feature(feature_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "hapus_fitur_billing",
                               detail=f"feature_id={feature_id}, kode={feature['kode'] if feature else None}")
    return {"ok": True}


@superadmin_router.get("/packages/{package_id}/features")
def list_package_features(package_id: int, user: dict = Depends(require_superadmin)):
    return billing_db.get_package_features(package_id)


class PackageFeaturesBody(BaseModel):
    feature_ids: list[int]


@superadmin_router.put("/packages/{package_id}/features")
def ubah_package_features(package_id: int, body: PackageFeaturesBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = billing_db.set_package_features(package_id, body.feature_ids)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_fitur_paket_billing",
                               detail=f"package_id={package_id}, feature_ids={body.feature_ids}")
    return hasil
