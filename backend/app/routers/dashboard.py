"""routers/dashboard.py — /api/dashboard/*
Owner: bisa lihat ringkasan SEMUA barber untuk bulan manapun.
Barber: HANYA bisa lihat ringkasan miliknya sendiri (barber_id diambil dari
akun login-nya di tabel users, bukan dari parameter request — supaya Barber
tidak bisa mengintip data barber lain hanya dengan mengubah query string)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

import database as db
from auth import require_admin, require_barber

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _bulan_ini():
    today = date.today()
    return today.year, today.month


@router.get("/owner")
def dashboard_owner(tahun: int = None, bulan: int = None, user: dict = Depends(require_admin)):
    """Ringkasan SEMUA barber aktif untuk satu bulan, plus total keseluruhan toko.
    REVISI: Bonus Kehadiran dihapus total (lihat database.get_ringkasan_barber_bulan).
    `rincian_service_semua_barber` ditambahkan (gabungan rincian_service seluruh
    barber, dijumlahkan per nama service) supaya dropdown "Semua Barber" pada
    kartu Service Bulan Ini tidak perlu menghitung apa pun sendiri di frontend."""
    if tahun is None or bulan is None:
        tahun, bulan = _bulan_ini()
    barbers = db.get_barbers()
    ringkasan_per_barber = [db.get_ringkasan_barber_bulan(b["id"], tahun, bulan) for b in barbers]
    total_toko = {
        "nilai_service": sum(r["nilai_service"] for r in ringkasan_per_barber),
        "komisi": sum(r["komisi"] for r in ringkasan_per_barber),
        "tips": sum(r["tips"] for r in ringkasan_per_barber),
        "uang_harian": sum(r["uang_harian"] for r in ringkasan_per_barber),
        "bonus_customer": sum(r["bonus_customer"] for r in ringkasan_per_barber),
        "total_pendapatan": sum(r["total_pendapatan"] for r in ringkasan_per_barber),
        "jumlah_customer": sum(r["jumlah_customer"] for r in ringkasan_per_barber),
    }
    total_pengeluaran = db.get_total_pengeluaran(tahun=tahun, bulan=bulan)

    rincian_gabungan = {}
    for r in ringkasan_per_barber:
        for item in r["rincian_service"]:
            rincian_gabungan[item["nama_service"]] = rincian_gabungan.get(item["nama_service"], 0) + item["jumlah"]
    rincian_service_semua_barber = sorted(
        [{"nama_service": k, "jumlah": v} for k, v in rincian_gabungan.items() if v > 0],
        key=lambda x: (-x["jumlah"], x["nama_service"]),
    )

    return {
        "tahun": tahun,
        "bulan": bulan,
        "per_barber": ringkasan_per_barber,
        "total_toko": total_toko,
        "total_pengeluaran": total_pengeluaran,
        "rincian_service_semua_barber": rincian_service_semua_barber,
        "laba_kotor": total_toko["nilai_service"] - total_toko["komisi"] - total_toko["uang_harian"]
        - total_toko["bonus_customer"] - total_pengeluaran,
    }


@router.get("/barber")
def dashboard_barber(tahun: int = None, bulan: int = None, user: dict = Depends(require_barber)):
    if tahun is None or bulan is None:
        tahun, bulan = _bulan_ini()
    barber_id = user.get("barber_id")
    if barber_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Akun ini belum dikaitkan ke data Barber. Hubungi Owner.")
    return db.get_ringkasan_barber_bulan(barber_id, tahun, bulan)
