"""routers/faspay_settlement_superadmin.py — Settlement Faspay: Super Admin
=============================================================================
KHUSUS Super Admin (require_superadmin) -- monitoring settlement SELURUH
tenant ("terminal"), lihat detail transaksi mana yang match/warning, dan
MEMICU rekonsiliasi H+1 (satu-satunya aksi TULIS Super Admin di sini --
Super Admin TIDAK PERNAH bisa mengubah data pengajuan awal terminal, hanya
menambah hasil pencocokan H+1, lihat faspay_settlement_db.py::
jalankan_rekonsiliasi_h1())."""

from fastapi import APIRouter, Depends, HTTPException

import faspay_settlement_db
from auth import require_superadmin

router = APIRouter(prefix="/api/superadmin/settlement-faspay", tags=["settlement-faspay-superadmin"])


@router.get("")
def list_settlement(tenant_id: int = None, status: str = None,
                     tanggal_mulai: str = None, tanggal_selesai: str = None,
                     user: dict = Depends(require_superadmin)):
    return faspay_settlement_db.list_settlements(
        tenant_id=tenant_id, status=status, tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
    )


@router.get("/{settlement_id}")
def detail_settlement(settlement_id: int, user: dict = Depends(require_superadmin)):
    settlement = faspay_settlement_db.get_settlement(settlement_id)
    if settlement is None:
        raise HTTPException(status_code=404, detail="Settlement tidak ditemukan.")
    return settlement


@router.post("/{settlement_id}/rekonsiliasi-h1")
def jalankan_rekonsiliasi_h1(settlement_id: int, user: dict = Depends(require_superadmin)):
    if faspay_settlement_db.get_settlement(settlement_id) is None:
        raise HTTPException(status_code=404, detail="Settlement tidak ditemukan.")
    try:
        return faspay_settlement_db.jalankan_rekonsiliasi_h1(settlement_id, dijalankan_oleh=user.get("username") or "-")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
