"""routers/reimburse.py — /api/reimburse/* (Modul Karyawan, Fase 4)
=============================================================================
BEDA dari routers/kasbon.py & routers/komisi.py: 'barber' TIDAK read-only
di sini -- reimburse adalah klaim yang DIAJUKAN SENDIRI oleh barber
(self-service), jadi barber boleh buat/lihat/edit/hapus klaim MILIKNYA
SENDIRI selama masih berstatus 'pending' (tanpa perlu permission apa pun --
ini bukan aksi "mengelola data barber lain", cukup sewajarnya diri sendiri).
Approve/Reject (mengubah status) TETAP eksklusif admin/staff(izin_reimburse),
tidak pernah barber.

- 'admin' (Owner): akses PENUH tanpa syarat -- lihat/kelola/approve SIAPA PUN.
- 'staff' (Admin): HANYA kalau diberi izin `izin_reimburse` lewat Setting >
  Hak Akses Admin -- berlaku untuk MELIHAT SEMUA maupun approve/kelola milik
  barber lain (staff TIDAK butuh izin ini untuk aksi yang sama sekali tidak
  berlaku padanya -- staff bukan barber, jadi baris ini hanya soal
  admin/staff vs barber).
- 'barber': boleh POST/PUT/DELETE/upload-bukti untuk klaim MILIKNYA SENDIRI
  (selama 'pending'), GET hanya klaim miliknya sendiri, TIDAK PERNAH boleh
  approve/reject (PUT .../status)."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import database as db
import laporan_pdf
import permissions
import r2_storage
import reimburse_db
from auth import get_current_user, require_feature, require_permission


router = APIRouter(prefix="/api/reimburse", tags=["reimburse"])


def _cek_akses_lihat(user: dict, klaim: dict = None):
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        if not permissions.has("izin_reimburse", tenant_id=user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Reimburse. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if klaim is not None and klaim["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Tidak bisa melihat klaim reimburse milik barber lain.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def _pastikan_pemilik_atau_admin(user: dict, klaim: dict):
    """Dipakai endpoint tulis (edit/hapus/upload bukti) -- admin/staff
    (izin_reimburse) boleh untuk siapa saja, barber HANYA untuk miliknya
    sendiri."""
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        if not permissions.has("izin_reimburse", tenant_id=user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Reimburse. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if klaim["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Bukan klaim reimburse milik Anda.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def _pastikan_reimburse_tenant_sama(user: dict, klaim: dict | None):
    """FONDASI Multi-Tenant Phase 1.1: fetch-then-authorize -- 404 (bukan
    403) supaya tidak membocorkan bahwa reimburse_id itu sebenarnya ada,
    milik tenant lain (pola sama seperti routers/pengeluaran.py)."""
    if klaim is None or klaim.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Reimburse tidak ditemukan.")


def _pastikan_barber_tenant_sama(user: dict, barber_id: int):
    barber = db.get_barber(barber_id)
    if barber is None or barber["tenant_id"] != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Barber tidak ditemukan.")


@router.get("")
def list_reimburse(barber_id: int = None, status: str = None, tahun: int = None, bulan: int = None,
                    kategori: str = None, user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return reimburse_db.get_reimburse_list(barber_id=barber_id, status=status, tahun=tahun,
                                            bulan=bulan, kategori=kategori, tenant_id=user["tenant_id"])


@router.get("/pdf")
def list_reimburse_pdf(barber_id: int = None, status: str = None, tahun: int = None, bulan: int = None,
                        user: dict = Depends(get_current_user), _fitur: dict = Depends(require_feature("export_pdf"))):
    """Route ini didaftarkan SEBELUM /{reimburse_id} supaya 'pdf' tidak
    ditangkap sebagai path parameter reimburse_id."""
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    konten = laporan_pdf.buat_pdf_reimburse_list(barber_id, status, tahun, bulan, user["username"],
                                                  tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("reimburse")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/kategori")
def kategori_reimburse(user: dict = Depends(get_current_user)):
    return reimburse_db.get_kategori_list(tenant_id=user["tenant_id"])


@router.get("/saldo/{barber_id}")
def saldo_periode(barber_id: int, tahun: int, bulan: int, user: dict = Depends(get_current_user)):
    if user["role"] == "barber" and barber_id != user.get("barber_id"):
        raise HTTPException(status_code=403, detail="Tidak bisa melihat saldo reimburse barber lain.")
    _cek_akses_lihat(user)
    _pastikan_barber_tenant_sama(user, barber_id)
    return {"barber_id": barber_id, "tahun": tahun, "bulan": bulan,
            "saldo": reimburse_db.get_saldo_periode(barber_id, tahun, bulan)}


@router.get("/saldo-rentang/{barber_id}")
def saldo_rentang(barber_id: int, tanggal_mulai: str, tanggal_selesai: str,
                   user: dict = Depends(get_current_user)):
    """Analog saldo_periode() di atas, tapi untuk auto-fill Reimburse di
    form Generate Slip Gaji Kasir/OB/Kru (Tahap 13: periode rentang tanggal
    bebas, BEDA dari Barber yang tetap pakai tahun/bulan)."""
    if user["role"] == "barber" and barber_id != user.get("barber_id"):
        raise HTTPException(status_code=403, detail="Tidak bisa melihat saldo reimburse barber lain.")
    _cek_akses_lihat(user)
    _pastikan_barber_tenant_sama(user, barber_id)
    return {"barber_id": barber_id, "tanggal_mulai": tanggal_mulai, "tanggal_selesai": tanggal_selesai,
            "saldo": reimburse_db.get_saldo_rentang(barber_id, tanggal_mulai, tanggal_selesai)}


@router.get("/{reimburse_id}")
def ambil_reimburse(reimburse_id: int, user: dict = Depends(get_current_user)):
    klaim = reimburse_db.get_reimburse(reimburse_id)
    _pastikan_reimburse_tenant_sama(user, klaim)
    _cek_akses_lihat(user, klaim)
    return klaim


class ReimburseBody(BaseModel):
    barber_id: int | None = None  # diabaikan untuk role barber, wajib untuk role admin/staff
    tanggal: str
    kategori: str
    nominal: int
    keterangan: str = ""


@router.post("")
def buat_reimburse(body: ReimburseBody, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        if user.get("barber_id") is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
        barber_id = user["barber_id"]
    elif user["role"] in ("admin", "staff"):
        if user["role"] == "staff" and not permissions.has("izin_reimburse", tenant_id=user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Reimburse. Hubungi Owner.")
        if body.barber_id is None:
            raise HTTPException(status_code=422, detail="barber_id wajib diisi.")
        barber_id = body.barber_id
    else:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        return reimburse_db.buat_reimburse(barber_id, body.tanggal, body.kategori, body.nominal,
                                            keterangan=body.keterangan, diajukan_oleh=user["username"],
                                            tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class ReimburseEditBody(BaseModel):
    tanggal: str | None = None
    kategori: str | None = None
    nominal: int | None = None
    keterangan: str | None = None


@router.put("/{reimburse_id}")
def edit_reimburse(reimburse_id: int, body: ReimburseEditBody, user: dict = Depends(get_current_user)):
    klaim = reimburse_db.get_reimburse(reimburse_id)
    _pastikan_reimburse_tenant_sama(user, klaim)
    _pastikan_pemilik_atau_admin(user, klaim)
    try:
        return reimburse_db.edit_reimburse(reimburse_id, tanggal=body.tanggal, kategori=body.kategori,
                                            nominal=body.nominal, keterangan=body.keterangan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{reimburse_id}")
def hapus_reimburse(reimburse_id: int, user: dict = Depends(get_current_user)):
    klaim = reimburse_db.get_reimburse(reimburse_id)
    _pastikan_reimburse_tenant_sama(user, klaim)
    _pastikan_pemilik_atau_admin(user, klaim)
    try:
        reimburse_db.hapus_reimburse(reimburse_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.delete("/{reimburse_id}/rekap")
def hapus_reimburse_dari_rekap(reimburse_id: int, user: dict = Depends(require_permission("izin_reimburse"))):
    """Hapus klaim reimburse yang SUDAH disetujui, dipakai KHUSUS tombol
    Hapus di Rekap Transaksi -- beda dari DELETE /{reimburse_id} biasa di
    atas yang cuma izinkan klaim 'pending'."""
    _pastikan_reimburse_tenant_sama(user, reimburse_db.get_reimburse(reimburse_id))
    try:
        reimburse_db.hapus_reimburse_disetujui(reimburse_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


class StatusBody(BaseModel):
    status: str
    catatan_approval: str = ""


@router.put("/{reimburse_id}/status")
def ubah_status_reimburse(reimburse_id: int, body: StatusBody,
                           user: dict = Depends(require_permission("izin_reimburse"))):
    _pastikan_reimburse_tenant_sama(user, reimburse_db.get_reimburse(reimburse_id))
    try:
        return reimburse_db.set_status_reimburse(reimburse_id, body.status,
                                                  catatan_approval=body.catatan_approval,
                                                  disetujui_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{reimburse_id}/bukti")
async def upload_bukti_reimburse(reimburse_id: int, file: UploadFile = File(...),
                                  user: dict = Depends(get_current_user)):
    klaim = reimburse_db.get_reimburse(reimburse_id)
    _pastikan_reimburse_tenant_sama(user, klaim)
    _pastikan_pemilik_atau_admin(user, klaim)
    if klaim["status"] != "pending":
        raise HTTPException(status_code=422, detail="Klaim yang sudah diproses tidak bisa diubah buktinya lagi.")
    konten = await file.read()
    try:
        reimburse_db.simpan_bukti_reimburse(reimburse_id, file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return reimburse_db.get_reimburse(reimburse_id)


@router.get("/{reimburse_id}/bukti")
def unduh_bukti_reimburse(reimburse_id: int, user: dict = Depends(get_current_user)):
    klaim = reimburse_db.get_reimburse(reimburse_id)
    _pastikan_reimburse_tenant_sama(user, klaim)
    _cek_akses_lihat(user, klaim)
    data, content_type = reimburse_db.get_bukti_data(reimburse_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Bukti belum diunggah.")
    return Response(content=data, media_type=content_type)
