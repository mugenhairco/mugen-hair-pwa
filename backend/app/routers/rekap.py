"""routers/rekap.py — /api/rekap/*
- Rekap Transaksi & Rekap Bulanan: Owner bisa lihat semua barber (atau filter
  satu barber), Barber otomatis dibatasi ke data miliknya sendiri saja.
- Rekap Pengeluaran: data operasional TOKO (bukan milik barber manapun),
  jadi khusus Owner. TAHAP 9: diarahkan ke pengeluaran_db (sumber yang sama
  dipakai CRUD Pengeluaran) supaya rekap ini otomatis ikut kategori & nama
  barber, bukan lagi hanya baca kolom dasar dari database.py."""

from fastapi import APIRouter, Depends

import database as db
import pengeluaran_db
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
    daftar = pengeluaran_db.get_pengeluaran_list(tahun=tahun, bulan=bulan)
    total = sum(p["jumlah"] for p in daftar)
    return {"daftar": daftar, "total": total}
