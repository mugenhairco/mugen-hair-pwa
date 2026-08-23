"""routers/faspay_settlement.py — Settlement Faspay per Terminal (Tenant)
=============================================================================
Endpoint tenant-login -- SELALU di-scope tenant_id dari akun login (pola
SAMA PERSIS routers/booking.py::list_transaksi_gateway()), TIDAK PERNAH
menerima tenant_id dari parameter request. "Terminal" = tenant (keputusan
eksplisit Owner) -- lihat faspay_settlement_db.py untuk arsitektur lengkap.

`require_menu_read("settlement_faspay")`: LIHAT (preview/list/detail).
`require_permission("izin_settlement_faspay")`: TULIS (submit) -- Owner
selalu lolos, staff HANYA kalau Owner mengaktifkan lewat Setting > Hak
Akses User (default OFF, beda dari menu operasional lama yang default ON,
karena ini fitur BARU -- tidak ada staff existing yang perlu tetap bisa
akses tanpa diatur ulang)."""

from fastapi import APIRouter, Depends, HTTPException

import faspay_settlement_db
import tenant_db
from auth import require_menu_read, require_permission

router = APIRouter(prefix="/api/settlement-faspay", tags=["settlement-faspay"])


@router.get("/preview")
def preview_settlement(tanggal: str, user: dict = Depends(require_menu_read("settlement_faspay"))):
    return faspay_settlement_db.preview_settlement(user["tenant_id"], tanggal)


@router.post("")
def submit_settlement(tanggal: str, user: dict = Depends(require_permission("izin_settlement_faspay"))):
    tenant = tenant_db.get_tenant(user["tenant_id"])
    tenant_nama = tenant["nama_barbershop"] if tenant else "-"
    try:
        return faspay_settlement_db.buat_settlement(user["tenant_id"], tenant_nama, tanggal, user)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("")
def list_settlement(status: str = None, tanggal_mulai: str = None, tanggal_selesai: str = None,
                     user: dict = Depends(require_menu_read("settlement_faspay"))):
    return faspay_settlement_db.list_settlements(
        tenant_id=user["tenant_id"], status=status, tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
    )


@router.get("/{settlement_id}")
def detail_settlement(settlement_id: int, user: dict = Depends(require_menu_read("settlement_faspay"))):
    settlement = faspay_settlement_db.get_settlement(settlement_id, tenant_id=user["tenant_id"])
    if settlement is None:
        raise HTTPException(status_code=404, detail="Settlement tidak ditemukan.")
    return settlement
