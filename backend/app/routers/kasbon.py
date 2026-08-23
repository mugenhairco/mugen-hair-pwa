"""routers/kasbon.py — /api/kasbon/* (Modul Karyawan, Fase 2)
=============================================================================
Pola akses SAMA PERSIS dengan routers/slip_gaji.py (satu endpoint, tiga
sudut pandang):
- 'admin' (Owner): akses PENUH tanpa syarat.
- 'staff' (Admin): HANYA kalau diberi izin `izin_kasbon` lewat
  Setting > Hak Akses Admin -- berlaku untuk MELIHAT maupun mengelola.
- 'barber': HANYA boleh melihat kasbon & riwayat pembayaran miliknya
  SENDIRI (dipaksa dari barber_id di token), read-only -- tidak pernah
  bisa membuat/mengedit/menghapus/membayar kasbon.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import database as db
import kasbon_db
import laporan_pdf
import permissions
from auth import get_current_user, require_feature, require_permission


router = APIRouter(prefix="/api/kasbon", tags=["kasbon"])


def _cek_akses_lihat(user: dict, kasbon: dict = None):
    """Raise 403 kalau user TIDAK BOLEH melihat data ini. kasbon=None dipakai
    untuk endpoint list (pengecekan level-role saja, filter barber_id
    dilakukan terpisah di pemanggil)."""
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        # Hak Akses Menu (permintaan Owner): level "Baca" (izin_kasbon_lihat)
        # SEKARANG cukup untuk MELIHAT -- sebelumnya hanya izin_kasbon (yang
        # juga menyalakan tulis) yang dicek di sini, jadi staff "Baca"-saja
        # tidak bisa lihat sama sekali. izin_kasbon (write) TETAP otomatis
        # meloloskan lihat juga (masuk akal: bisa edit berarti bisa lihat).
        if not permissions.has_any(["izin_kasbon_lihat", "izin_kasbon"],
                                    tenant_id=user.get("tenant_id"), role_id=user.get("custom_role_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Kasbon. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if kasbon is not None and kasbon["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Tidak bisa melihat Kasbon milik barber lain.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def _pastikan_kasbon_tenant_sama(user: dict, kasbon: dict | None):
    """FONDASI Multi-Tenant Phase 1.1: fetch-then-authorize -- 404 (bukan
    403) supaya tidak membocorkan bahwa kasbon_id itu sebenarnya ada, milik
    tenant lain (pola sama seperti routers/pengeluaran.py)."""
    if kasbon is None or kasbon.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Kasbon tidak ditemukan.")


def _pastikan_pembayaran_tenant_sama(user: dict, pembayaran: dict | None):
    if pembayaran is None or pembayaran.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Riwayat pembayaran kasbon tidak ditemukan.")


@router.get("")
def list_kasbon(barber_id: int = None, status: str = None, tahun: int = None, bulan: int = None,
                 user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return kasbon_db.get_kasbon_list(barber_id=barber_id, status=status, tahun=tahun, bulan=bulan,
                                      tenant_id=user["tenant_id"])


@router.get("/pdf")
def list_kasbon_pdf(barber_id: int = None, status: str = None, tahun: int = None, bulan: int = None,
                     user: dict = Depends(get_current_user), _fitur: dict = Depends(require_feature("export_pdf"))):
    """Route ini didaftarkan SEBELUM /{kasbon_id} supaya 'pdf' tidak
    ditangkap sebagai path parameter kasbon_id."""
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    konten = laporan_pdf.buat_pdf_kasbon_list(barber_id, status, tahun, bulan, user["username"],
                                               tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("kasbon")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/saldo/{barber_id}")
def saldo_barber(barber_id: int, user: dict = Depends(get_current_user)):
    if user["role"] == "barber" and barber_id != user.get("barber_id"):
        raise HTTPException(status_code=403, detail="Tidak bisa melihat saldo kasbon barber lain.")
    _cek_akses_lihat(user)
    barber = db.get_barber(barber_id)
    if barber is None or barber["tenant_id"] != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Barber tidak ditemukan.")
    return {"barber_id": barber_id, "saldo": kasbon_db.get_saldo_barber(barber_id)}


@router.get("/{kasbon_id}")
def ambil_kasbon(kasbon_id: int, user: dict = Depends(get_current_user)):
    kasbon = kasbon_db.get_kasbon(kasbon_id)
    _pastikan_kasbon_tenant_sama(user, kasbon)
    _cek_akses_lihat(user, kasbon)
    return kasbon


@router.get("/{kasbon_id}/pembayaran")
def riwayat_pembayaran(kasbon_id: int, user: dict = Depends(get_current_user)):
    kasbon = kasbon_db.get_kasbon(kasbon_id)
    _pastikan_kasbon_tenant_sama(user, kasbon)
    _cek_akses_lihat(user, kasbon)
    return kasbon_db.get_riwayat_pembayaran(kasbon_id)


class KasbonBody(BaseModel):
    barber_id: int
    tanggal: str
    jumlah: int
    keterangan: str = ""


@router.post("")
def buat_kasbon(body: KasbonBody, user: dict = Depends(require_permission("izin_kasbon"))):
    try:
        return kasbon_db.buat_kasbon(body.barber_id, body.tanggal, body.jumlah,
                                      keterangan=body.keterangan, dibuat_oleh=user["username"],
                                      tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class KasbonEditBody(BaseModel):
    tanggal: str | None = None
    jumlah: int | None = None
    keterangan: str | None = None


@router.put("/{kasbon_id}")
def edit_kasbon(kasbon_id: int, body: KasbonEditBody, user: dict = Depends(require_permission("izin_kasbon"))):
    _pastikan_kasbon_tenant_sama(user, kasbon_db.get_kasbon(kasbon_id))
    try:
        return kasbon_db.edit_kasbon(kasbon_id, tanggal=body.tanggal, jumlah=body.jumlah,
                                      keterangan=body.keterangan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{kasbon_id}")
def hapus_kasbon(kasbon_id: int, user: dict = Depends(require_permission("izin_kasbon"))):
    _pastikan_kasbon_tenant_sama(user, kasbon_db.get_kasbon(kasbon_id))
    try:
        kasbon_db.hapus_kasbon(kasbon_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.delete("/pembayaran/{pembayaran_id}")
def batalkan_pembayaran(pembayaran_id: int, user: dict = Depends(require_permission("izin_kasbon"))):
    """Batalkan satu baris pembayaran kasbon MANUAL -- dipakai tombol
    Batalkan di Rekap Transaksi. Path ini didaftarkan SEBELUM /{kasbon_id}
    tidak masalah karena kedalamannya beda (2 segmen vs 1), jadi tidak
    pernah ambigu dengan GET /{kasbon_id}."""
    _pastikan_pembayaran_tenant_sama(user, kasbon_db.get_pembayaran_kasbon(pembayaran_id))
    try:
        kasbon_db.batalkan_pembayaran_kasbon(pembayaran_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


class PembayaranBody(BaseModel):
    tanggal: str
    jumlah: int
    keterangan: str = ""


@router.post("/{kasbon_id}/pembayaran")
def bayar_kasbon(kasbon_id: int, body: PembayaranBody, user: dict = Depends(require_permission("izin_kasbon"))):
    _pastikan_kasbon_tenant_sama(user, kasbon_db.get_kasbon(kasbon_id))
    try:
        return kasbon_db.bayar_kasbon(kasbon_id, body.tanggal, body.jumlah,
                                       keterangan=body.keterangan, dibuat_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
