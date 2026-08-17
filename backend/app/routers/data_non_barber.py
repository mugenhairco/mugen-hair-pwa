"""routers/data_non_barber.py — /api/data-non-barber/*
Input Data Non-Barber (Kasir/OB/Kru/role lainnya) -- akses Owner 'admin'
dan Admin 'staff' (Barber tidak pernah akses) supaya konsisten dengan
halaman Input Data yang menaunginya (lihat data_non_barber_db.py untuk
kenapa modul ini berdiri sendiri dari sistem Barber).

REVISI (Perluasan Hak Akses Admin -- diminta Owner): endpoint LIHAT (GET)
tetap `require_owner_or_staff` (staff SELALU boleh melihat) -- endpoint
TULIS (tambah/edit) sekarang `require_permission("izin_data_non_barber_kelola")`,
endpoint HAPUS `require_permission("izin_data_non_barber_hapus")` (lihat
permissions.py, default TRUE supaya staff yang sudah pakai modul ini tidak
tiba-tiba terkunci)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import data_non_barber_db
from auth import require_owner_or_staff, require_permission

router = APIRouter(prefix="/api/data-non-barber", tags=["data-non-barber"])


def _pastikan_entry_tenant_sama(user: dict, entry: dict | None):
    """FONDASI Multi-Tenant Phase 1.1: fetch-then-authorize -- 404 (bukan
    403) supaya tidak membocorkan bahwa entry_id itu sebenarnya ada, milik
    tenant lain."""
    if entry is None or entry.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data Non-Barber tidak ditemukan.")


class DataNonBarberBody(BaseModel):
    barber_id: int
    tanggal_mulai: str
    tanggal_selesai: str
    gaji_per_hari: int
    hari_masuk: int
    hari_libur: int = 0
    bonus: int = 0
    potongan: int = 0
    catatan: str = ""


class DataNonBarberEditBody(BaseModel):
    barber_id: int | None = None
    tanggal_mulai: str | None = None
    tanggal_selesai: str | None = None
    gaji_per_hari: int | None = None
    hari_masuk: int | None = None
    hari_libur: int | None = None
    bonus: int | None = None
    potongan: int | None = None
    catatan: str | None = None


@router.get("")
def list_data_non_barber(barber_id: int = None, tahun: int = None, bulan: int = None,
                          user: dict = Depends(require_owner_or_staff)):
    return data_non_barber_db.get_data_non_barber_list(barber_id=barber_id, tahun=tahun, bulan=bulan,
                                                         tenant_id=user["tenant_id"])


@router.post("")
def tambah_data_non_barber(body: DataNonBarberBody, user: dict = Depends(require_permission("izin_data_non_barber_kelola"))):
    try:
        return data_non_barber_db.tambah_data_non_barber(
            body.barber_id, body.tanggal_mulai, body.tanggal_selesai, body.gaji_per_hari, body.hari_masuk,
            hari_libur=body.hari_libur, bonus=body.bonus, potongan=body.potongan, catatan=body.catatan,
            dibuat_oleh=user["username"], tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/{entry_id}")
def edit_data_non_barber(entry_id: int, body: DataNonBarberEditBody, user: dict = Depends(require_permission("izin_data_non_barber_kelola"))):
    _pastikan_entry_tenant_sama(user, data_non_barber_db.get_data_non_barber(entry_id))
    try:
        return data_non_barber_db.edit_data_non_barber(
            entry_id, barber_id=body.barber_id, tanggal_mulai=body.tanggal_mulai,
            tanggal_selesai=body.tanggal_selesai, gaji_per_hari=body.gaji_per_hari, hari_masuk=body.hari_masuk,
            hari_libur=body.hari_libur, bonus=body.bonus, potongan=body.potongan, catatan=body.catatan,
            tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{entry_id}")
def hapus_data_non_barber(entry_id: int, user: dict = Depends(require_permission("izin_data_non_barber_hapus"))):
    _pastikan_entry_tenant_sama(user, data_non_barber_db.get_data_non_barber(entry_id))
    try:
        data_non_barber_db.hapus_data_non_barber(entry_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}
