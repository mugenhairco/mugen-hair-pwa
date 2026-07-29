"""routers/transfer.py — /api/transfer/* (Modul Keuangan, Fase 2)
Router CRUD Transfer Kas/Bank -- pola akses SAMA PERSIS routers/pemasukan.py/
routers/pengeluaran.py: data operasional TOKO, Barber ditolak total DI
BACKEND (require_owner_or_staff), staff ('Admin') akses PENUH sama persis
Owner, TANPA sistem izin sama sekali."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import laporan_pdf
import transfer_db as db_transfer
from auth import require_owner_or_staff

router = APIRouter(prefix="/api/transfer", tags=["transfer"])


class TransferBody(BaseModel):
    tanggal: str
    dari_akun: str
    ke_akun: str
    jumlah: int
    keterangan: str = ""


@router.get("/akun")
def daftar_akun(user: dict = Depends(require_owner_or_staff)):
    return db_transfer.get_akun_list()


@router.get("")
def list_transfer(tahun: int = None, bulan: int = None, cari: str = None,
                   user: dict = Depends(require_owner_or_staff)):
    return db_transfer.get_transfer_list(tahun=tahun, bulan=bulan, cari=cari)


@router.get("/pdf")
def list_transfer_pdf(tahun: int, bulan: int, cari: str = None, user: dict = Depends(require_owner_or_staff)):
    """Route ini didaftarkan SEBELUM /{transfer_id} supaya 'pdf' tidak
    ditangkap sebagai path parameter transfer_id."""
    konten = laporan_pdf.buat_pdf_transfer_list(tahun, bulan, cari, user["username"])
    filename = laporan_pdf.buat_nama_file("transfer")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{transfer_id}")
def detail_transfer(transfer_id: int, user: dict = Depends(require_owner_or_staff)):
    row = db_transfer.get_transfer(transfer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Data transfer tidak ditemukan.")
    return row


@router.post("")
def tambah_transfer(body: TransferBody, user: dict = Depends(require_owner_or_staff)):
    try:
        new_id = db_transfer.tambah_transfer(
            tanggal=body.tanggal, dari_akun=body.dari_akun, ke_akun=body.ke_akun,
            jumlah=body.jumlah, keterangan=body.keterangan, dibuat_oleh=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db_transfer.get_transfer(new_id)


@router.put("/{transfer_id}")
def koreksi_transfer(transfer_id: int, body: TransferBody, user: dict = Depends(require_owner_or_staff)):
    try:
        db_transfer.koreksi_transfer(
            transfer_id, tanggal=body.tanggal, dari_akun=body.dari_akun, ke_akun=body.ke_akun,
            jumlah=body.jumlah, keterangan=body.keterangan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db_transfer.get_transfer(transfer_id)


@router.delete("/{transfer_id}")
def hapus_transfer(transfer_id: int, user: dict = Depends(require_owner_or_staff)):
    db_transfer.hapus_transfer(transfer_id)
    return {"ok": True}
