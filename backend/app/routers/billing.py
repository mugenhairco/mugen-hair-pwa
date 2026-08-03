"""routers/billing.py — FONDASI Multi-Tenant Phase 4: Billing & Payment (Midtrans)
=============================================================================
Modul "konfigurasi paket" (task pertama Phase 4) -- KHUSUS Super Admin
mengatur atribut subscription_packages (nama/harga/durasi/status/urutan/
deskripsi/limit pemakaian). Endpoint Owner (checkout/invoice/webhook/dst)
menyusul di file terpisah sesuai modul, lihat billing_db.py untuk penjelasan
lengkap kenapa tabel ini BUKAN sistem paket baru.

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
