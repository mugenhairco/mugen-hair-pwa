"""routers/rekap.py — /api/rekap/*
- Rekap Transaksi & Rekap Bulanan: Owner bisa lihat semua barber (atau filter
  satu barber), Barber otomatis dibatasi ke data miliknya sendiri saja.
- Rekap Pengeluaran: data operasional TOKO (bukan milik barber manapun),
  jadi khusus Owner."""

from fastapi import APIRouter, Depends

import database as db
from auth import get_current_user, require_admin

router = APIRouter(prefix="/api/rekap", tags=["rekap"])


@router.get("/transaksi")
def rekap_transaksi(tahun: int = None, bulan: int = None, barber_id: int = None,
                     tanggal: str = None, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return db.get_rekap_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id, tanggal=tanggal)


@router.get("/bulanan")
def rekap_bulanan(tahun: int, bulan: int, barber_id: int = None, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return db.get_rekap_bulanan_list(tahun=tahun, bulan=bulan, barber_id=barber_id)


@router.get("/pengeluaran")
def rekap_pengeluaran(tahun: int = None, bulan: int = None, user: dict = Depends(require_admin)):
    daftar = db.get_pengeluaran_list(tahun=tahun, bulan=bulan)
    total = db.get_total_pengeluaran(tahun=tahun, bulan=bulan)
    return {"daftar": daftar, "total": total}
