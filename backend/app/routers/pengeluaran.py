"""routers/pengeluaran.py — /api/pengeluaran/*  (TAHAP 9; REVISI Hak Akses Admin)
Router KHUSUS untuk CRUD Pengeluaran, sengaja dipisah dari router lain
(input_data.py, rekap.py, dsb) sesuai instruksi Tahap 9.

Hak akses: Pengeluaran adalah data operasional TOKO (bukan milik barber
manapun). Barber TETAP ditolak total DI BACKEND (require_owner_or_staff
menolak role 'barber', bukan cuma disembunyikan di menu frontend).

REVISI (ketiga, Perluasan Hak Akses Admin -- diminta Owner): grup
izin_pengeluaran_* SEMPAT dihapus total di REVISI kedua (Admin/'staff'
akses PENUH tanpa syarat apa pun) -- SEKARANG DIHIDUPKAN KEMBALI dengan
nama kode BARU (izin_pengeluaran_kelola/izin_pengeluaran_hapus, lihat
permissions.py) supaya Owner bisa membatasi lagi kalau mau. Endpoint LIHAT
(GET) tetap `require_owner_or_staff` (staff SELALU boleh melihat) --
endpoint TULIS (tambah/edit) sekarang `require_permission("izin_pengeluaran_kelola")`,
endpoint HAPUS `require_permission("izin_pengeluaran_hapus")`. Default
KEDUANYA True -- staff yang sudah pakai modul ini tidak tiba-tiba
terkunci begitu perubahan ini deploy."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import laporan_pdf
import pengeluaran_db as db_pengeluaran
from auth import require_feature, require_owner_or_staff, require_permission

router = APIRouter(prefix="/api/pengeluaran", tags=["pengeluaran"])


class PengeluaranBody(BaseModel):
    tanggal: str
    kategori: str
    keterangan: str
    jumlah: int
    barber_id: int | None = None
    aktif: bool = True
    sumber_dana: str = "kas"


@router.get("/kategori")
def daftar_kategori(user: dict = Depends(require_owner_or_staff)):
    """Daftar kategori (default + yang sudah pernah dipakai) untuk dropdown
    filter & form di frontend."""
    return db_pengeluaran.get_kategori_list(tenant_id=user["tenant_id"])


@router.get("")
def list_pengeluaran(tahun: int = None, bulan: int = None, tanggal: str = None,
                      kategori: str = None, cari: str = None, hanya_aktif: bool = None,
                      user: dict = Depends(require_owner_or_staff)):
    return db_pengeluaran.get_pengeluaran_list(
        tahun=tahun, bulan=bulan, tanggal=tanggal,
        kategori=kategori, cari=cari, hanya_aktif=hanya_aktif,
        tenant_id=user["tenant_id"],
    )


def _pastikan_pengeluaran_tenant_sama(user: dict, row: dict | None):
    """FONDASI Multi-Tenant Phase 1: fetch-then-authorize, pola sama seperti
    _pastikan_barber_tenant_sama di routers/pengaturan.py -- 404 supaya tidak
    membocorkan bahwa pengeluaran_id itu sebenarnya ada, milik tenant lain."""
    if row is None or row.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data pengeluaran tidak ditemukan.")


@router.get("/pdf")
def list_pengeluaran_pdf(tahun: int, bulan: int, kategori: str = None, cari: str = None,
                          user: dict = Depends(require_owner_or_staff), _fitur: dict = Depends(require_feature("export_pdf"))):
    """Route ini didaftarkan SEBELUM /{pengeluaran_id} supaya 'pdf' tidak
    ditangkap sebagai path parameter pengeluaran_id."""
    konten = laporan_pdf.buat_pdf_pengeluaran_list(tahun, bulan, kategori, cari, user["username"],
                                                    tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("pengeluaran")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{pengeluaran_id}")
def detail_pengeluaran(pengeluaran_id: int, user: dict = Depends(require_owner_or_staff)):
    row = db_pengeluaran.get_pengeluaran(pengeluaran_id)
    _pastikan_pengeluaran_tenant_sama(user, row)
    return row


@router.post("")
def tambah_pengeluaran(body: PengeluaranBody, user: dict = Depends(require_permission("izin_pengeluaran_kelola"))):
    try:
        new_id = db_pengeluaran.tambah_pengeluaran(
            tanggal=body.tanggal, kategori=body.kategori, keterangan=body.keterangan,
            jumlah=body.jumlah, barber_id=body.barber_id, aktif=body.aktif,
            sumber_dana=body.sumber_dana, dibuat_oleh=user["username"], tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db_pengeluaran.get_pengeluaran(new_id)


@router.put("/{pengeluaran_id}")
def koreksi_pengeluaran(pengeluaran_id: int, body: PengeluaranBody, user: dict = Depends(require_permission("izin_pengeluaran_kelola"))):
    _pastikan_pengeluaran_tenant_sama(user, db_pengeluaran.get_pengeluaran(pengeluaran_id))
    try:
        db_pengeluaran.koreksi_pengeluaran(
            pengeluaran_id, tanggal=body.tanggal, kategori=body.kategori, keterangan=body.keterangan,
            jumlah=body.jumlah, barber_id=body.barber_id, aktif=body.aktif,
            sumber_dana=body.sumber_dana, dibuat_oleh=user["username"], tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db_pengeluaran.get_pengeluaran(pengeluaran_id)


@router.delete("/{pengeluaran_id}")
def hapus_pengeluaran(pengeluaran_id: int, user: dict = Depends(require_permission("izin_pengeluaran_hapus"))):
    _pastikan_pengeluaran_tenant_sama(user, db_pengeluaran.get_pengeluaran(pengeluaran_id))
    try:
        db_pengeluaran.hapus_pengeluaran(pengeluaran_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}
