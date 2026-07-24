"""routers/pengeluaran.py — /api/pengeluaran/*  (TAHAP 9)
Router KHUSUS untuk CRUD Pengeluaran, sengaja dipisah dari router lain
(input_data.py, rekap.py, dsb) sesuai instruksi Tahap 9.

Hak akses: Pengeluaran adalah data operasional TOKO (bukan milik barber
manapun), jadi KHUSUS role admin (Owner). Barber ditolak DI BACKEND lewat
dependency `require_admin` (bukan cuma disembunyikan di menu frontend) —
setiap endpoint di file ini memakainya, sehingga request barber otomatis
mendapat 403 Forbidden apapun yang dikirim dari sisi client."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import pengeluaran_db as db_pengeluaran
from auth import require_admin
from sync_helper import sync_async

router = APIRouter(prefix="/api/pengeluaran", tags=["pengeluaran"])


class PengeluaranBody(BaseModel):
    tanggal: str
    kategori: str
    keterangan: str
    jumlah: int
    barber_id: int | None = None
    aktif: bool = True


@router.get("/kategori")
def daftar_kategori(user: dict = Depends(require_admin)):
    """Daftar kategori (default + yang sudah pernah dipakai) untuk dropdown
    filter & form di frontend."""
    return db_pengeluaran.get_kategori_list()


@router.get("")
def list_pengeluaran(tahun: int = None, bulan: int = None, tanggal: str = None,
                      kategori: str = None, cari: str = None, hanya_aktif: bool = None,
                      user: dict = Depends(require_admin)):
    return db_pengeluaran.get_pengeluaran_list(
        tahun=tahun, bulan=bulan, tanggal=tanggal,
        kategori=kategori, cari=cari, hanya_aktif=hanya_aktif,
    )


@router.get("/{pengeluaran_id}")
def detail_pengeluaran(pengeluaran_id: int, user: dict = Depends(require_admin)):
    row = db_pengeluaran.get_pengeluaran(pengeluaran_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Data pengeluaran tidak ditemukan.")
    return row


@router.post("")
def tambah_pengeluaran(body: PengeluaranBody, user: dict = Depends(require_admin)):
    try:
        new_id = db_pengeluaran.tambah_pengeluaran(
            tanggal=body.tanggal, kategori=body.kategori, keterangan=body.keterangan,
            jumlah=body.jumlah, barber_id=body.barber_id, aktif=body.aktif,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    sync_async()
    return db_pengeluaran.get_pengeluaran(new_id)


@router.put("/{pengeluaran_id}")
def koreksi_pengeluaran(pengeluaran_id: int, body: PengeluaranBody, user: dict = Depends(require_admin)):
    try:
        db_pengeluaran.koreksi_pengeluaran(
            pengeluaran_id, tanggal=body.tanggal, kategori=body.kategori, keterangan=body.keterangan,
            jumlah=body.jumlah, barber_id=body.barber_id, aktif=body.aktif,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    sync_async()
    return db_pengeluaran.get_pengeluaran(pengeluaran_id)


@router.delete("/{pengeluaran_id}")
def hapus_pengeluaran(pengeluaran_id: int, user: dict = Depends(require_admin)):
    db_pengeluaran.hapus_pengeluaran(pengeluaran_id)
    sync_async()
    return {"ok": True}
