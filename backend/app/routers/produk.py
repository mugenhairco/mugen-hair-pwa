"""routers/produk.py — /api/produk/*
TAHAP 8 — Produk (penjualan, restock, sisa stok).

Produk adalah data operasional TOKO (persediaan barang dagang), bukan milik
barber manapun — sama seperti Rekap Pengeluaran (lihat routers/rekap.py),
jadi seluruh endpoint di sini KHUSUS Owner (admin). Barber tetap bisa
melihat/menjual produk lewat halaman Input Data di tahap lanjut kalau nanti
diminta eksplisit; untuk saat ini, kelola stok sepenuhnya di tangan Owner.

Semua logika hitung stok (validasi saldo tidak boleh negatif, dsb) ada di
database.py (TIDAK diubah di sini) — router ini hanya meneruskan request ke
fungsi yang sudah ada di sana dan mengubah ValueError jadi HTTP 422."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import database as db
from auth import require_admin
from sync_helper import sync_async

router = APIRouter(prefix="/api/produk", tags=["produk"])


class ProdukBody(BaseModel):
    nama: str


class MutasiBody(BaseModel):
    tanggal: str
    jumlah: int
    catatan: str | None = None


class KoreksiMutasiBody(BaseModel):
    tanggal: str
    jumlah: int
    catatan: str | None = None


@router.get("")
def list_produk(hanya_aktif: bool = True, user: dict = Depends(require_admin)):
    return db.get_produk_list(hanya_aktif=hanya_aktif)


@router.post("")
def tambah_produk(body: ProdukBody, user: dict = Depends(require_admin)):
    try:
        produk_id = db.tambah_produk(body.nama)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_produk(produk_id)


@router.put("/{produk_id}")
def update_nama_produk(produk_id: int, body: ProdukBody, user: dict = Depends(require_admin)):
    if db.get_produk(produk_id) is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    try:
        db.update_nama_produk(produk_id, body.nama)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_produk(produk_id)


@router.delete("/{produk_id}")
def nonaktifkan_produk(produk_id: int, user: dict = Depends(require_admin)):
    if db.get_produk(produk_id) is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    db.nonaktifkan_produk(produk_id)
    return {"ok": True}


@router.post("/{produk_id}/restock")
def restock_produk(produk_id: int, body: MutasiBody, user: dict = Depends(require_admin)):
    if db.get_produk(produk_id) is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    try:
        mutasi_id = db.restock_produk(produk_id, body.tanggal, body.jumlah, body.catatan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    sync_async()
    return db.get_mutasi_produk(mutasi_id)


@router.post("/{produk_id}/jual")
def jual_produk(produk_id: int, body: MutasiBody, user: dict = Depends(require_admin)):
    if db.get_produk(produk_id) is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    try:
        mutasi_id = db.jual_produk(produk_id, body.tanggal, body.jumlah, body.catatan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    sync_async()
    return db.get_mutasi_produk(mutasi_id)


@router.get("/mutasi")
def list_mutasi(produk_id: int = None, tipe: str = None, tahun: int = None,
                bulan: int = None, user: dict = Depends(require_admin)):
    return db.get_mutasi_produk_list(produk_id=produk_id, tipe=tipe, tahun=tahun, bulan=bulan)


@router.put("/mutasi/{mutasi_id}")
def koreksi_mutasi(mutasi_id: int, body: KoreksiMutasiBody, user: dict = Depends(require_admin)):
    if db.get_mutasi_produk(mutasi_id) is None:
        raise HTTPException(status_code=404, detail="Data mutasi tidak ditemukan.")
    try:
        db.koreksi_mutasi_produk(mutasi_id, body.tanggal, body.jumlah, body.catatan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    sync_async()
    return db.get_mutasi_produk(mutasi_id)


@router.delete("/mutasi/{mutasi_id}")
def hapus_mutasi(mutasi_id: int, user: dict = Depends(require_admin)):
    if db.get_mutasi_produk(mutasi_id) is None:
        raise HTTPException(status_code=404, detail="Data mutasi tidak ditemukan.")
    try:
        db.hapus_mutasi_produk(mutasi_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    sync_async()
    return {"ok": True}
