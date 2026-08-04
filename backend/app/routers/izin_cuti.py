"""routers/izin_cuti.py — /api/izin-cuti/* (Modul Karyawan, Fase 5)
=============================================================================
Pola akses SAMA PERSIS dengan routers/reimburse.py (self-service): barber
boleh mengajukan/melihat/mengedit/menghapus pengajuan MILIKNYA SENDIRI
(selama masih 'pending') tanpa perlu permission apa pun. Approve/Reject
TETAP eksklusif admin/staff(izin_cuti_karyawan)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import izin_cuti_db
import laporan_pdf
import permissions
from auth import get_current_user, require_feature, require_permission


router = APIRouter(prefix="/api/izin-cuti", tags=["izin-cuti"])


def _cek_akses_lihat(user: dict, pengajuan: dict = None):
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        if not permissions.has("izin_cuti_karyawan", tenant_id=user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Izin & Cuti. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if pengajuan is not None and pengajuan["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Tidak bisa melihat pengajuan milik barber lain.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def _pastikan_pemilik_atau_admin(user: dict, pengajuan: dict):
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        if not permissions.has("izin_cuti_karyawan", tenant_id=user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Izin & Cuti. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if pengajuan["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Bukan pengajuan milik Anda.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def _pastikan_pengajuan_tenant_sama(user: dict, pengajuan: dict | None):
    """FONDASI Multi-Tenant Phase 1.1: fetch-then-authorize -- 404 (bukan
    403) supaya tidak membocorkan bahwa pengajuan_id itu sebenarnya ada,
    milik tenant lain."""
    if pengajuan is None or pengajuan.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Pengajuan tidak ditemukan.")


@router.get("")
def list_pengajuan(barber_id: int = None, status: str = None, jenis: str = None,
                    tahun: int = None, bulan: int = None, user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return izin_cuti_db.get_pengajuan_list(barber_id=barber_id, status=status, jenis=jenis,
                                            tahun=tahun, bulan=bulan, tenant_id=user["tenant_id"])


@router.get("/pdf")
def list_pengajuan_pdf(barber_id: int = None, status: str = None, jenis: str = None,
                        user: dict = Depends(get_current_user), _fitur: dict = Depends(require_feature("export_pdf"))):
    """Route ini didaftarkan SEBELUM /{pengajuan_id} supaya 'pdf' tidak
    ditangkap sebagai path parameter pengajuan_id."""
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    konten = laporan_pdf.buat_pdf_izin_cuti_list(barber_id, jenis, status, user["username"],
                                                  tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("izin_cuti")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/pending-count")
def pending_count(user: dict = Depends(get_current_user)):
    """Badge notifikasi sidebar -- HANYA admin/staff (izin_cuti_karyawan)
    yang berkepentingan, barber selalu dapat 0 (tidak ditampilkan di UI)."""
    if user["role"] == "admin" or (user["role"] == "staff" and
                                    permissions.has("izin_cuti_karyawan", tenant_id=user.get("tenant_id"))):
        return {"jumlah": izin_cuti_db.get_jumlah_pending(tenant_id=user["tenant_id"])}
    return {"jumlah": 0}


@router.get("/{pengajuan_id}")
def ambil_pengajuan(pengajuan_id: int, user: dict = Depends(get_current_user)):
    pengajuan = izin_cuti_db.get_pengajuan(pengajuan_id)
    _pastikan_pengajuan_tenant_sama(user, pengajuan)
    _cek_akses_lihat(user, pengajuan)
    return pengajuan


class PengajuanBody(BaseModel):
    barber_id: int | None = None  # diabaikan untuk role barber, wajib untuk role admin/staff
    jenis: str
    tanggal_mulai: str
    tanggal_selesai: str
    alasan: str


@router.post("")
def buat_pengajuan(body: PengajuanBody, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        if user.get("barber_id") is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
        barber_id = user["barber_id"]
    elif user["role"] in ("admin", "staff"):
        if user["role"] == "staff" and not permissions.has("izin_cuti_karyawan", tenant_id=user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Izin & Cuti. Hubungi Owner.")
        if body.barber_id is None:
            raise HTTPException(status_code=422, detail="barber_id wajib diisi.")
        barber_id = body.barber_id
    else:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        return izin_cuti_db.buat_pengajuan(barber_id, body.jenis, body.tanggal_mulai, body.tanggal_selesai,
                                            body.alasan, diajukan_oleh=user["username"],
                                            tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class PengajuanEditBody(BaseModel):
    jenis: str | None = None
    tanggal_mulai: str | None = None
    tanggal_selesai: str | None = None
    alasan: str | None = None


@router.put("/{pengajuan_id}")
def edit_pengajuan(pengajuan_id: int, body: PengajuanEditBody, user: dict = Depends(get_current_user)):
    pengajuan = izin_cuti_db.get_pengajuan(pengajuan_id)
    _pastikan_pengajuan_tenant_sama(user, pengajuan)
    _pastikan_pemilik_atau_admin(user, pengajuan)
    try:
        return izin_cuti_db.edit_pengajuan(pengajuan_id, jenis=body.jenis, tanggal_mulai=body.tanggal_mulai,
                                            tanggal_selesai=body.tanggal_selesai, alasan=body.alasan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{pengajuan_id}")
def hapus_pengajuan(pengajuan_id: int, user: dict = Depends(get_current_user)):
    pengajuan = izin_cuti_db.get_pengajuan(pengajuan_id)
    _pastikan_pengajuan_tenant_sama(user, pengajuan)
    _pastikan_pemilik_atau_admin(user, pengajuan)
    try:
        izin_cuti_db.hapus_pengajuan(pengajuan_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


class StatusBody(BaseModel):
    status: str
    catatan_approval: str = ""


@router.put("/{pengajuan_id}/status")
def ubah_status_pengajuan(pengajuan_id: int, body: StatusBody,
                           user: dict = Depends(require_permission("izin_cuti_karyawan"))):
    _pastikan_pengajuan_tenant_sama(user, izin_cuti_db.get_pengajuan(pengajuan_id))
    try:
        return izin_cuti_db.set_status_pengajuan(pengajuan_id, body.status,
                                                  catatan_approval=body.catatan_approval,
                                                  disetujui_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
