"""routers/uang_kas.py — /api/uang-kas/* (Modul Keuangan, pengganti Transfer Kas/Bank)
Router Saldo Kas Awal + penyesuaian manual (tambah/kurang) -- pola akses
SAMA PERSIS routers/pemasukan.py: data operasional TOKO, Barber ditolak
total DI BACKEND (require_owner_or_staff), staff ('Admin') akses PENUH
sama persis Owner, TANPA sistem izin sama sekali."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import laporan_pdf
import uang_kas_db as db_uang_kas
from auth import require_owner_or_staff

router = APIRouter(prefix="/api/uang-kas", tags=["uang-kas"])


def _pastikan_penyesuaian_tenant_sama(user: dict, row: dict | None):
    """FONDASI Multi-Tenant Phase 1.1: fetch-then-authorize, pola sama
    seperti routers/pengeluaran.py -- 404 supaya tidak membocorkan bahwa
    penyesuaian_id itu sebenarnya ada, milik tenant lain."""
    if row is None or row.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Penyesuaian kas tidak ditemukan.")


class SaldoAwalBody(BaseModel):
    saldo: int


class PenyesuaianBody(BaseModel):
    tanggal: str
    jenis: str
    jumlah: int
    keterangan: str = ""


@router.get("/saldo-awal")
def ambil_saldo_awal(user: dict = Depends(require_owner_or_staff)):
    return db_uang_kas.get_saldo_awal(tenant_id=user["tenant_id"])


@router.put("/saldo-awal")
def ubah_saldo_awal(body: SaldoAwalBody, user: dict = Depends(require_owner_or_staff)):
    try:
        return db_uang_kas.set_saldo_awal(body.saldo, diubah_oleh=user["username"], tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/saldo")
def ambil_saldo_kas(user: dict = Depends(require_owner_or_staff)):
    return {"saldo": db_uang_kas.get_saldo_kas(tenant_id=user["tenant_id"])}


@router.get("/pdf")
def list_penyesuaian_pdf(tahun: int = None, bulan: int = None, user: dict = Depends(require_owner_or_staff)):
    """Route ini didaftarkan SEBELUM /{penyesuaian_id} supaya 'pdf' tidak
    ditangkap sebagai path parameter penyesuaian_id."""
    konten = laporan_pdf.buat_pdf_uang_kas_list(tahun, bulan, user["username"], tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("uang_kas")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("")
def list_penyesuaian(tahun: int = None, bulan: int = None, user: dict = Depends(require_owner_or_staff)):
    return db_uang_kas.get_penyesuaian_list(tahun=tahun, bulan=bulan, tenant_id=user["tenant_id"])


@router.get("/{penyesuaian_id}")
def detail_penyesuaian(penyesuaian_id: int, user: dict = Depends(require_owner_or_staff)):
    row = db_uang_kas.get_penyesuaian(penyesuaian_id)
    _pastikan_penyesuaian_tenant_sama(user, row)
    return row


@router.post("")
def tambah_penyesuaian(body: PenyesuaianBody, user: dict = Depends(require_owner_or_staff)):
    try:
        new_id = db_uang_kas.tambah_penyesuaian(
            tanggal=body.tanggal, jenis=body.jenis, jumlah=body.jumlah,
            keterangan=body.keterangan, dibuat_oleh=user["username"], tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db_uang_kas.get_penyesuaian(new_id)


@router.put("/{penyesuaian_id}")
def edit_penyesuaian(penyesuaian_id: int, body: PenyesuaianBody, user: dict = Depends(require_owner_or_staff)):
    _pastikan_penyesuaian_tenant_sama(user, db_uang_kas.get_penyesuaian(penyesuaian_id))
    try:
        db_uang_kas.edit_penyesuaian(
            penyesuaian_id, tanggal=body.tanggal, jenis=body.jenis,
            jumlah=body.jumlah, keterangan=body.keterangan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db_uang_kas.get_penyesuaian(penyesuaian_id)


@router.delete("/{penyesuaian_id}")
def hapus_penyesuaian(penyesuaian_id: int, user: dict = Depends(require_owner_or_staff)):
    _pastikan_penyesuaian_tenant_sama(user, db_uang_kas.get_penyesuaian(penyesuaian_id))
    db_uang_kas.hapus_penyesuaian(penyesuaian_id)
    return {"ok": True}
