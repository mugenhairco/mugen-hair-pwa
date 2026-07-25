"""routers/dashboard.py — /api/dashboard/*
Owner: bisa lihat ringkasan SEMUA barber untuk bulan manapun.
Barber: HANYA bisa lihat ringkasan miliknya sendiri (barber_id diambil dari
akun login-nya di tabel users, bukan dari parameter request — supaya Barber
tidak bisa mengintip data barber lain hanya dengan mengubah query string)."""

import calendar
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
    # REVISI: kartu "Penjualan Produk" -- omzet HANYA dari transaksi produk
    # bertipe Jual (Restock bukan penjualan, Tester sengaja tidak dihitung,
    # lihat database.get_omzet_penjualan_produk). SENGAJA TIDAK diikutkan ke
    # laba_kotor di bawah -- bukan diminta, rumus laba kotor toko lama tetap
    # sama persis seperti sebelumnya.
    penjualan_produk = db.get_omzet_penjualan_produk(tahun=tahun, bulan=bulan)

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
        "penjualan_produk": penjualan_produk,
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


def _barber_terpilih(barber_id: int):
    """Dipakai kedua endpoint grafik di bawah: barber_id kosong (None) berarti
    gabungan SEMUA barber aktif; kalau diisi, hanya barber itu (dicari
    langsung by id, bukan cuma dari daftar aktif -- konsisten dengan endpoint
    lain yang tetap bisa menampilkan data historis barber yang sudah
    dinonaktifkan)."""
    if barber_id is not None:
        barber = db.get_barber(barber_id)
        return [barber] if barber else []
    return db.get_barbers()


@router.get("/owner/grafik-harian")
def grafik_harian(tahun: int, bulan: int, barber_id: int = None, user: dict = Depends(require_admin)):
    """Diagram batang PENDAPATAN HARIAN (khusus Owner) untuk satu bulan --
    satu batang per tanggal (1 s.d. jumlah hari di bulan itu), termasuk
    tanggal yang belum ada transaksi (nilainya 0, supaya sumbu tanggal tetap
    utuh/tidak "loncat"). barber_id kosong = gabungan SEMUA barber.

    Pendapatan di sini = Komisi + Tips + Uang Harian hari itu (memakai
    hitung_uang_harian_per_hari yang sudah ada, aturan >=3 Dry Cut/Cut & Wash
    per hari TIDAK diubah sama sekali). Bonus Customer SENGAJA tidak
    diikutkan -- itu perhitungan BULANAN (lihat hitung_bonus_customer), tidak
    ada cara membaginya secara berarti per tanggal, jadi disertakan penuh di
    /owner/grafik-bulanan (total_pendapatan bulan itu) supaya tidak ada
    angka yang menyesatkan di kedua grafik."""
    jumlah_hari = calendar.monthrange(tahun, bulan)[1]
    barbers = _barber_terpilih(barber_id)

    pendapatan_per_hari = {h: 0 for h in range(1, jumlah_hari + 1)}
    for b in barbers:
        for t in db.get_transaksi_list(tahun=tahun, bulan=bulan, barber_id=b["id"]):
            hari = int(t["tanggal"][8:10])
            pendapatan_per_hari[hari] = pendapatan_per_hari.get(hari, 0) + t["total_komisi"] + t["tips"]
        for hari in range(1, jumlah_hari + 1):
            tanggal_iso = f"{tahun:04d}-{bulan:02d}-{hari:02d}"
            pendapatan_per_hari[hari] += db.hitung_uang_harian_per_hari(b, tanggal_iso)

    return [{"tanggal": h, "pendapatan": pendapatan_per_hari[h]} for h in range(1, jumlah_hari + 1)]


@router.get("/owner/grafik-bulanan")
def grafik_bulanan(tahun: int, barber_id: int = None, user: dict = Depends(require_admin)):
    """Diagram batang PENDAPATAN BULANAN (khusus Owner) untuk satu tahun --
    satu batang per bulan (Januari s.d. Desember), termasuk bulan yang belum
    ada data (nilainya 0). barber_id kosong = gabungan SEMUA barber.
    Pendapatan di sini = total_pendapatan PENUH (Komisi + Tips + Uang Harian
    + Bonus Customer) dari get_ringkasan_barber_bulan yang sudah ada --
    bonus wajar diikutkan di sini karena memang perhitungan bulanan."""
    barbers = _barber_terpilih(barber_id)

    hasil = []
    for bulan in range(1, 13):
        total = sum(db.get_ringkasan_barber_bulan(b["id"], tahun, bulan)["total_pendapatan"] for b in barbers)
        hasil.append({"bulan": bulan, "pendapatan": total})
    return hasil
