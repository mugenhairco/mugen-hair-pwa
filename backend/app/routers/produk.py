"""routers/produk.py — /api/produk/*
Produk (penjualan, restock, sisa stok). Ditulis di Tahap 10 tapi belum
dihubungkan ke main.py; Tahap 11 menghubungkannya (lihat README).

Produk adalah data operasional TOKO (persediaan barang dagang), bukan milik
barber manapun — seluruh endpoint di sini KHUSUS Owner ('admin') dan Admin
('staff'). Barber tetap bisa melihat/menjual produk lewat halaman Input
Data di tahap lanjut kalau nanti diminta eksplisit; untuk saat ini, kelola
stok sepenuhnya di tangan Owner/Admin.

REVISI (Perluasan Hak Akses Admin, diminta Owner): endpoint LIHAT (GET)
sekarang `require_menu_read("produk")` (level menu "Produk", lihat
permissions.py::MENU_DEFS) -- endpoint TULIS (tambah/edit produk,
restock/jual/tester, koreksi mutasi) tetap
`require_permission("izin_produk_kelola")`, endpoint HAPUS (nonaktifkan
produk, hapus mutasi) tetap `require_permission("izin_produk_hapus")` (lihat
permissions.py, default TRUE supaya staff yang sudah pakai modul ini tidak
tiba-tiba terkunci).

Semua logika hitung stok (validasi saldo tidak boleh negatif, dsb) ada di
database.py (TIDAK diubah di sini) — router ini hanya meneruskan request ke
fungsi yang sudah ada di sana dan mengubah ValueError jadi HTTP 422."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import database as db
import laporan_pdf
from auth import require_feature, require_permission, require_menu_read

router = APIRouter(prefix="/api/produk", tags=["produk"])


class ProdukBody(BaseModel):
    nama: str
    harga_modal: int = 0
    harga_jual: int = 0


class ProdukUpdateBody(BaseModel):
    nama: str | None = None
    harga_modal: int | None = None
    harga_jual: int | None = None


class MutasiBody(BaseModel):
    tanggal: str
    jumlah: int
    catatan: str | None = None


class KoreksiMutasiBody(BaseModel):
    tanggal: str
    jumlah: int
    catatan: str | None = None


def _pastikan_produk_tenant_sama(user: dict, produk: dict | None):
    """FONDASI Multi-Tenant Phase 1: fetch-then-authorize, pola sama seperti
    _pastikan_barber_tenant_sama di routers/pengaturan.py -- 404 supaya
    tidak membocorkan bahwa produk_id itu sebenarnya ada, milik tenant lain."""
    if produk is None or produk.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")


def _pastikan_mutasi_tenant_sama(user: dict, mutasi: dict | None):
    """Sama seperti _pastikan_produk_tenant_sama, versi untuk /mutasi/{id}
    (get_mutasi_produk() sudah menyertakan tenant_id produknya, lihat
    database.py)."""
    if mutasi is None or mutasi.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data mutasi tidak ditemukan.")


@router.get("")
def list_produk(hanya_aktif: bool = True, user: dict = Depends(require_menu_read("produk"))):
    return db.get_produk_list(hanya_aktif=hanya_aktif, tenant_id=user["tenant_id"])


@router.post("")
def tambah_produk(body: ProdukBody, user: dict = Depends(require_permission("izin_produk_kelola"))):
    try:
        produk_id = db.tambah_produk(body.nama, body.harga_modal, body.harga_jual, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_produk(produk_id)


@router.put("/{produk_id}")
def update_produk(produk_id: int, body: ProdukUpdateBody, user: dict = Depends(require_permission("izin_produk_kelola"))):
    _pastikan_produk_tenant_sama(user, db.get_produk(produk_id))
    try:
        db.update_produk(produk_id, nama=body.nama, harga_modal=body.harga_modal, harga_jual=body.harga_jual)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_produk(produk_id)


@router.delete("/{produk_id}")
def nonaktifkan_produk(produk_id: int, user: dict = Depends(require_permission("izin_produk_hapus"))):
    _pastikan_produk_tenant_sama(user, db.get_produk(produk_id))
    db.nonaktifkan_produk(produk_id)
    return {"ok": True}


@router.post("/{produk_id}/restock")
def restock_produk(produk_id: int, body: MutasiBody, user: dict = Depends(require_permission("izin_produk_kelola"))):
    _pastikan_produk_tenant_sama(user, db.get_produk(produk_id))
    try:
        mutasi_id = db.restock_produk(produk_id, body.tanggal, body.jumlah, body.catatan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_mutasi_produk(mutasi_id)


@router.post("/{produk_id}/jual")
def jual_produk(produk_id: int, body: MutasiBody, user: dict = Depends(require_permission("izin_produk_kelola"))):
    _pastikan_produk_tenant_sama(user, db.get_produk(produk_id))
    try:
        mutasi_id = db.jual_produk(produk_id, body.tanggal, body.jumlah, body.catatan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_mutasi_produk(mutasi_id)


@router.post("/{produk_id}/tester")
def tester_produk(produk_id: int, body: MutasiBody, user: dict = Depends(require_permission("izin_produk_kelola"))):
    """REVISI: tipe transaksi baru 'Tester' -- mengurangi stok sama seperti
    Jual, TAPI TIDAK menambah omzet (lihat db.tester_produk/
    db.get_omzet_penjualan_produk), tetap tercatat penuh di riwayat mutasi."""
    _pastikan_produk_tenant_sama(user, db.get_produk(produk_id))
    try:
        mutasi_id = db.tester_produk(produk_id, body.tanggal, body.jumlah, body.catatan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_mutasi_produk(mutasi_id)


@router.get("/mutasi")
def list_mutasi(produk_id: int = None, tipe: str = None, tahun: int = None,
                bulan: int = None, user: dict = Depends(require_menu_read("produk"))):
    return db.get_mutasi_produk_list(produk_id=produk_id, tipe=tipe, tahun=tahun, bulan=bulan,
                                      tenant_id=user["tenant_id"])


@router.get("/mutasi/pdf")
def list_mutasi_pdf(produk_id: int = None, tipe: str = None, tahun: int = None, bulan: int = None,
                     user: dict = Depends(require_menu_read("produk")), _fitur: dict = Depends(require_feature("export_pdf"))):
    """Cetak Riwayat Mutasi Produk -- filter SAMA PERSIS dengan GET /mutasi
    di atas (dipanggil tombol Cetak PDF di produk.js dengan filter aktif
    yang sedang tampil di layar), sumber data SAMA (db.get_mutasi_produk_list())
    supaya isi PDF selalu identik dengan tabel di layar."""
    konten = laporan_pdf.buat_pdf_mutasi_produk(produk_id, tipe, tahun, bulan, user["username"],
                                                 tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("riwayat-mutasi-produk")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.put("/mutasi/{mutasi_id}")
def koreksi_mutasi(mutasi_id: int, body: KoreksiMutasiBody, user: dict = Depends(require_permission("izin_produk_kelola"))):
    _pastikan_mutasi_tenant_sama(user, db.get_mutasi_produk(mutasi_id))
    try:
        db.koreksi_mutasi_produk(mutasi_id, body.tanggal, body.jumlah, body.catatan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_mutasi_produk(mutasi_id)


@router.delete("/mutasi/{mutasi_id}")
def hapus_mutasi(mutasi_id: int, user: dict = Depends(require_permission("izin_produk_hapus"))):
    _pastikan_mutasi_tenant_sama(user, db.get_mutasi_produk(mutasi_id))
    try:
        db.hapus_mutasi_produk(mutasi_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}
