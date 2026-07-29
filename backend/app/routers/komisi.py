"""routers/komisi.py — /api/komisi/* (Modul Karyawan, Fase 3)
=============================================================================
Pola akses SAMA PERSIS dengan routers/kasbon.py (satu endpoint, tiga sudut
pandang):
- 'admin' (Owner): akses PENUH tanpa syarat.
- 'staff' (Admin): HANYA kalau diberi izin `izin_komisi` lewat Setting >
  Hak Akses Admin -- berlaku untuk MELIHAT maupun mengelola.
- 'barber': HANYA boleh melihat penyesuaian komisi miliknya SENDIRI
  (dipaksa dari barber_id di token), read-only -- tidak pernah bisa
  membuat/mengedit/menghapus penyesuaian.

"Riwayat Komisi" (angka komisi dasar per barber/periode) SENGAJA TIDAK
punya endpoint baru di sini -- frontend memakai ULANG /api/rekap/bulanan
yang sudah ada apa adanya (lihat routers/rekap.py), supaya perhitungan
komisi dasar tidak pernah diduplikasi/diimplementasikan ulang di modul ini.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import komisi_penyesuaian_db
import laporan_pdf
import permissions
from auth import get_current_user, require_permission


router = APIRouter(prefix="/api/komisi", tags=["komisi"])


def _cek_akses_lihat(user: dict, penyesuaian: dict = None):
    """Raise 403 kalau user TIDAK BOLEH melihat data ini. penyesuaian=None
    dipakai untuk endpoint list (pengecekan level-role saja, filter
    barber_id dilakukan terpisah di pemanggil)."""
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        if not permissions.has("izin_komisi"):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Komisi. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if penyesuaian is not None and penyesuaian["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Tidak bisa melihat penyesuaian komisi milik barber lain.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


@router.get("/penyesuaian")
def list_penyesuaian(barber_id: int = None, tahun: int = None, bulan: int = None, jenis: str = None,
                      user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return komisi_penyesuaian_db.get_penyesuaian_list(barber_id=barber_id, tahun=tahun, bulan=bulan, jenis=jenis)


@router.get("/pdf")
def list_penyesuaian_pdf(barber_id: int = None, tahun: int = None, bulan: int = None, jenis: str = None,
                          user: dict = Depends(get_current_user)):
    """Route ini didaftarkan SEBELUM /penyesuaian/{penyesuaian_id} supaya
    'pdf' tidak ditangkap sebagai path parameter."""
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    if not tahun or not bulan:
        raise HTTPException(status_code=422, detail="Tahun dan Bulan wajib diisi.")
    konten = laporan_pdf.buat_pdf_komisi_list(barber_id, jenis, tahun, bulan, user["username"])
    filename = laporan_pdf.buat_nama_file("komisi")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/saldo/{barber_id}")
def saldo_periode(barber_id: int, tahun: int, bulan: int, user: dict = Depends(get_current_user)):
    if user["role"] == "barber" and barber_id != user.get("barber_id"):
        raise HTTPException(status_code=403, detail="Tidak bisa melihat saldo komisi barber lain.")
    _cek_akses_lihat(user)
    return {"barber_id": barber_id, "tahun": tahun, "bulan": bulan,
            "saldo": komisi_penyesuaian_db.get_saldo_periode(barber_id, tahun, bulan)}


@router.get("/penyesuaian/{penyesuaian_id}")
def ambil_penyesuaian(penyesuaian_id: int, user: dict = Depends(get_current_user)):
    penyesuaian = komisi_penyesuaian_db.get_penyesuaian(penyesuaian_id)
    if penyesuaian is None:
        raise HTTPException(status_code=404, detail="Penyesuaian komisi tidak ditemukan.")
    _cek_akses_lihat(user, penyesuaian)
    return penyesuaian


class PenyesuaianBody(BaseModel):
    barber_id: int
    tahun: int
    bulan: int
    jenis: str
    jumlah: int
    keterangan: str


@router.post("/penyesuaian")
def buat_penyesuaian(body: PenyesuaianBody, user: dict = Depends(require_permission("izin_komisi"))):
    try:
        return komisi_penyesuaian_db.buat_penyesuaian(
            body.barber_id, body.tahun, body.bulan, body.jenis, body.jumlah,
            body.keterangan, dibuat_oleh=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class PenyesuaianEditBody(BaseModel):
    jenis: str | None = None
    jumlah: int | None = None
    keterangan: str | None = None


@router.put("/penyesuaian/{penyesuaian_id}")
def edit_penyesuaian(penyesuaian_id: int, body: PenyesuaianEditBody,
                      user: dict = Depends(require_permission("izin_komisi"))):
    try:
        return komisi_penyesuaian_db.edit_penyesuaian(
            penyesuaian_id, jenis=body.jenis, jumlah=body.jumlah, keterangan=body.keterangan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/penyesuaian/{penyesuaian_id}")
def hapus_penyesuaian(penyesuaian_id: int, user: dict = Depends(require_permission("izin_komisi"))):
    try:
        komisi_penyesuaian_db.hapus_penyesuaian(penyesuaian_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}
