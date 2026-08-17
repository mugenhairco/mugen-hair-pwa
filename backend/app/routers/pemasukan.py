"""routers/pemasukan.py — /api/pemasukan/* (Modul Keuangan, Fase 1)
Router CRUD Pemasukan -- pola akses SAMA PERSIS routers/pengeluaran.py:
data operasional TOKO (bukan milik barber manapun), Barber ditolak total
DI BACKEND (require_owner_or_staff).

REVISI (Perluasan Hak Akses Admin -- diminta Owner): endpoint LIHAT (GET)
tetap `require_owner_or_staff` (staff SELALU boleh melihat) -- endpoint
TULIS (tambah/edit) sekarang `require_permission("izin_pemasukan_kelola")`,
endpoint HAPUS `require_permission("izin_pemasukan_hapus")` (lihat
permissions.py, default TRUE supaya staff yang sudah pakai modul ini tidak
tiba-tiba terkunci)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import laporan_pdf
import pemasukan_db as db_pemasukan
from auth import require_feature, require_owner_or_staff, require_permission

router = APIRouter(prefix="/api/pemasukan", tags=["pemasukan"])


class PemasukanBody(BaseModel):
    tanggal: str
    kategori: str
    keterangan: str
    jumlah: int
    barber_id: int | None = None
    aktif: bool = True


def _pastikan_pemasukan_tenant_sama(user: dict, row: dict | None):
    """FONDASI Multi-Tenant Phase 1.1: fetch-then-authorize, pola sama
    seperti routers/pengeluaran.py -- 404 supaya tidak membocorkan bahwa
    pemasukan_id itu sebenarnya ada, milik tenant lain."""
    if row is None or row.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data pemasukan tidak ditemukan.")


@router.get("/kategori")
def daftar_kategori(user: dict = Depends(require_owner_or_staff)):
    return db_pemasukan.get_kategori_list(tenant_id=user["tenant_id"])


@router.get("")
def list_pemasukan(tahun: int = None, bulan: int = None, tanggal: str = None,
                    kategori: str = None, cari: str = None, hanya_aktif: bool = None,
                    user: dict = Depends(require_owner_or_staff)):
    return db_pemasukan.get_pemasukan_list(
        tahun=tahun, bulan=bulan, tanggal=tanggal,
        kategori=kategori, cari=cari, hanya_aktif=hanya_aktif,
        tenant_id=user["tenant_id"],
    )


@router.get("/pdf")
def list_pemasukan_pdf(tahun: int, bulan: int, kategori: str = None, cari: str = None,
                        user: dict = Depends(require_owner_or_staff), _fitur: dict = Depends(require_feature("export_pdf"))):
    """Route ini didaftarkan SEBELUM /{pemasukan_id} supaya 'pdf' tidak
    ditangkap sebagai path parameter pemasukan_id."""
    konten = laporan_pdf.buat_pdf_pemasukan_list(tahun, bulan, kategori, cari, user["username"],
                                                  tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("pemasukan")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{pemasukan_id}")
def detail_pemasukan(pemasukan_id: int, user: dict = Depends(require_owner_or_staff)):
    row = db_pemasukan.get_pemasukan(pemasukan_id)
    _pastikan_pemasukan_tenant_sama(user, row)
    return row


@router.post("")
def tambah_pemasukan(body: PemasukanBody, user: dict = Depends(require_permission("izin_pemasukan_kelola"))):
    try:
        new_id = db_pemasukan.tambah_pemasukan(
            tanggal=body.tanggal, kategori=body.kategori, keterangan=body.keterangan,
            jumlah=body.jumlah, barber_id=body.barber_id, aktif=body.aktif,
            tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db_pemasukan.get_pemasukan(new_id)


@router.put("/{pemasukan_id}")
def koreksi_pemasukan(pemasukan_id: int, body: PemasukanBody, user: dict = Depends(require_permission("izin_pemasukan_kelola"))):
    _pastikan_pemasukan_tenant_sama(user, db_pemasukan.get_pemasukan(pemasukan_id))
    try:
        db_pemasukan.koreksi_pemasukan(
            pemasukan_id, tanggal=body.tanggal, kategori=body.kategori, keterangan=body.keterangan,
            jumlah=body.jumlah, barber_id=body.barber_id, aktif=body.aktif,
            tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db_pemasukan.get_pemasukan(pemasukan_id)


@router.delete("/{pemasukan_id}")
def hapus_pemasukan(pemasukan_id: int, user: dict = Depends(require_permission("izin_pemasukan_hapus"))):
    _pastikan_pemasukan_tenant_sama(user, db_pemasukan.get_pemasukan(pemasukan_id))
    db_pemasukan.hapus_pemasukan(pemasukan_id)
    return {"ok": True}
