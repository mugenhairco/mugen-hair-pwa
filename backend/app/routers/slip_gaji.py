"""routers/slip_gaji.py — /api/slip-gaji/* (Modul Karyawan, Fase 1)
=============================================================================
Satu endpoint, tiga sudut pandang (pola yang sama seperti routers/rekap.py):
- 'admin' (Owner): akses PENUH tanpa syarat -- lihat/generate/tandai status/
  hapus/unduh PDF slip SIAPA PUN.
- 'staff' (Admin): HANYA kalau diberi izin `izin_slip_gaji` lewat
  Setting > Hak Akses Admin (permissions.py) -- berlaku untuk MELIHAT
  maupun mengelola (data gaji tergolong sensitif, beda dari Rekap yang
  selalu terbuka untuk staff).
- 'barber': HANYA boleh melihat/mengunduh PDF slip miliknya SENDIRI
  (dipaksa dari barber_id di token, bukan dari query), tidak pernah bisa
  generate/tandai status/hapus."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import laporan_pdf
import permissions
import slip_gaji_db
from auth import get_current_user, require_permission


router = APIRouter(prefix="/api/slip-gaji", tags=["slip-gaji"])


def _cek_akses_lihat(user: dict, slip: dict = None):
    """Raise 403 kalau user TIDAK BOLEH melihat data ini. slip=None dipakai
    untuk endpoint list (pengecekan level-role saja, filter barber_id
    dilakukan terpisah di pemanggil)."""
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        if not permissions.has("izin_slip_gaji"):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Slip Gaji. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if slip is not None and slip["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Tidak bisa melihat Slip Gaji milik barber lain.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


@router.get("")
def list_slip_gaji(tahun: int = None, bulan: int = None, barber_id: int = None,
                    user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return slip_gaji_db.get_slip_gaji_list(tahun=tahun, bulan=bulan, barber_id=barber_id)


@router.get("/{slip_id}")
def ambil_slip_gaji(slip_id: int, user: dict = Depends(get_current_user)):
    slip = slip_gaji_db.get_slip_gaji(slip_id)
    if slip is None:
        raise HTTPException(status_code=404, detail="Slip Gaji tidak ditemukan.")
    _cek_akses_lihat(user, slip)
    return slip


class SlipGajiGenerateBody(BaseModel):
    barber_id: int
    tahun: int
    bulan: int
    gaji_pokok: int | None = None
    potongan_kasbon: int = 0
    potongan_lain: int = 0
    catatan_potongan: str = ""


@router.post("")
def generate_slip_gaji(body: SlipGajiGenerateBody, user: dict = Depends(require_permission("izin_slip_gaji"))):
    try:
        return slip_gaji_db.buat_slip_gaji(
            body.barber_id, body.tahun, body.bulan, gaji_pokok=body.gaji_pokok,
            potongan_kasbon=body.potongan_kasbon, potongan_lain=body.potongan_lain,
            catatan_potongan=body.catatan_potongan, dibuat_oleh=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class StatusBody(BaseModel):
    status: str


@router.put("/{slip_id}/status")
def ubah_status_slip_gaji(slip_id: int, body: StatusBody, user: dict = Depends(require_permission("izin_slip_gaji"))):
    try:
        return slip_gaji_db.tandai_status(slip_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{slip_id}")
def hapus_slip_gaji(slip_id: int, user: dict = Depends(require_permission("izin_slip_gaji"))):
    try:
        slip_gaji_db.hapus_slip_gaji(slip_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.get("/{slip_id}/pdf")
def unduh_pdf_slip_gaji(slip_id: int, user: dict = Depends(get_current_user)):
    slip = slip_gaji_db.get_slip_gaji(slip_id)
    if slip is None:
        raise HTTPException(status_code=404, detail="Slip Gaji tidak ditemukan.")
    _cek_akses_lihat(user, slip)
    konten = laporan_pdf.buat_slip_gaji_pdf(slip)
    filename = f"slip_gaji_{slip['nama_barber']}_{slip['tahun']}-{slip['bulan']:02d}.pdf"
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})
