"""routers/manual_customer.py — /api/manual-customer/*
FITUR BARU: Input Data metode "Manual Customer" (Waiting List/Booking) --
akses SAMA PERSIS seperti /api/input-data/* dan /api/data-non-barber/*
(Owner 'admin' dan Admin 'staff', Barber tidak pernah akses). Endpoint LIHAT
(GET) `require_owner_or_staff`, endpoint TULIS (POST/PUT tambah/koreksi/
Closing) `require_permission("izin_input_data_kelola")`, endpoint HAPUS
(DELETE/Reset) `require_permission("izin_input_data_hapus")` -- MENGIKUTI
PERSIS pola akses routers/input_data.py (Perluasan Hak Akses Admin) supaya
staff yang sudah diberi izin Input Data otomatis juga bisa memakai Manual
Customer, tidak perlu izin terpisah baru. Lihat manual_customer_db.py untuk
penjelasan lengkap desain modul ini."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import manual_customer_db
from auth import require_permission, require_menu_read

router = APIRouter(prefix="/api/manual-customer", tags=["manual-customer"])


def _pastikan_entry_tenant_sama(user: dict, entry: dict | None):
    """Fetch-then-authorize -- 404 (bukan 403) supaya tidak membocorkan
    bahwa entry_id itu sebenarnya ada, milik tenant lain (pola sama persis
    routers/data_non_barber.py)."""
    if entry is None or entry.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data Manual Customer tidak ditemukan.")


class ManualCustomerBody(BaseModel):
    tanggal: str
    nama_customer: str
    jenis: str  # "waiting_list" | "booking"
    jam_booking: str | None = None  # wajib untuk jenis="booking", diabaikan untuk waiting_list
    barber_id: int | None = None
    service_ids: list[int] = []
    tips: int = 0
    catatan: str | None = None


class ManualCustomerEditBody(BaseModel):
    nama_customer: str | None = None
    barber_id: int | None = None
    service_ids: list[int] | None = None
    tips: int | None = None
    catatan: str | None = None


@router.get("/status")
def status_hari(tanggal: str, user: dict = Depends(require_menu_read("input_data"))):
    return manual_customer_db.get_status_hari(user["tenant_id"], tanggal)


@router.get("/transaksi")
def list_transaksi(tanggal: str, user: dict = Depends(require_menu_read("input_data"))):
    return manual_customer_db.get_manual_customer_list(user["tenant_id"], tanggal)


@router.post("/transaksi")
def tambah_transaksi(body: ManualCustomerBody, user: dict = Depends(require_permission("izin_input_data_kelola"))):
    try:
        return manual_customer_db.tambah_manual_customer(
            tenant_id=user["tenant_id"], tanggal=body.tanggal, nama_customer=body.nama_customer,
            jenis=body.jenis, jam_booking=body.jam_booking, barber_id=body.barber_id,
            service_ids=body.service_ids, tips=body.tips, catatan=body.catatan,
            dibuat_oleh=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/transaksi/{entry_id}")
def edit_transaksi(entry_id: int, body: ManualCustomerEditBody, user: dict = Depends(require_permission("izin_input_data_kelola"))):
    _pastikan_entry_tenant_sama(user, manual_customer_db.get_manual_customer(entry_id))
    try:
        return manual_customer_db.edit_manual_customer(
            entry_id, tenant_id=user["tenant_id"], nama_customer=body.nama_customer,
            barber_id=body.barber_id, service_ids=body.service_ids, tips=body.tips, catatan=body.catatan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/transaksi/{entry_id}")
def hapus_transaksi_endpoint(entry_id: int, user: dict = Depends(require_permission("izin_input_data_hapus"))):
    _pastikan_entry_tenant_sama(user, manual_customer_db.get_manual_customer(entry_id))
    try:
        manual_customer_db.hapus_manual_customer(entry_id, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.post("/close")
def tutup_hari(tanggal: str, user: dict = Depends(require_permission("izin_input_data_kelola"))):
    try:
        return manual_customer_db.tutup_hari(user["tenant_id"], tanggal, ditutup_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/reset")
def reset_hari(tanggal: str, user: dict = Depends(require_permission("izin_input_data_hapus"))):
    manual_customer_db.reset_hari(user["tenant_id"], tanggal)
    return {"ok": True}
