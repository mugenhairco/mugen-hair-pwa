"""routers/dashboard.py — /api/dashboard/*
Owner: bisa lihat ringkasan SEMUA barber untuk bulan manapun.
Barber: HANYA bisa lihat ringkasan miliknya sendiri (barber_id diambil dari
akun login-nya di tabel users, bukan dari parameter request — supaya Barber
tidak bisa mengintip data barber lain hanya dengan mengubah query string)."""

import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

import database as db
import permissions
from auth import require_admin, require_barber, require_owner_or_staff

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _bulan_ini():
    today = date.today()
    return today.year, today.month


def _tanpa_kolom_biner_ringkasan(ringkasan: dict) -> dict:
    """db.get_ringkasan_barber_bulan() menyisipkan dict barber APA ADANYA
    (dari db.get_barber(), SELECT *) di key "barber" -- ikut membawa kolom
    biner (foto_data BLOB, sejak Tahap 16) yang TIDAK bisa di-serialize jadi
    JSON (bug laten yang ditemukan saat audit migrasi R2: Dashboard Owner
    MAUPUN Dashboard Barber akan crash 500 begitu barber yang disasar punya
    foto tersimpan -- murni bug pre-existing di database.py, tidak terkait
    R2, dan TIDAK diperbaiki di database.py itu sendiri karena file itu
    harus tetap identik dengan aplikasi Desktop -- dibuang di sini, di
    lapisan API, sebelum dikembalikan ke client. Frontend Dashboard tidak
    pernah membaca foto_data/foto_r2_key dari respons endpoint ini)."""
    if ringkasan.get("barber"):
        ringkasan["barber"].pop("foto_data", None)
        ringkasan["barber"].pop("foto_r2_key", None)
    return ringkasan


def _filter_dashboard_untuk_staff(hasil: dict, tenant_id: int) -> dict:
    """'staff' (Admin) HANYA melihat kartu ringkasan toko yang diizinkan
    Owner lewat Setting > Hak Akses Admin (lihat permissions.py) -- rincian
    per-barber (komisi/tips/dst masing-masing orang) dan grafik pendapatan
    TIDAK PERNAH ikut dikirim untuk role ini sama sekali, sesuai spesifikasi
    Dashboard Admin (hanya 4 kartu ringkasan toko, bukan rincian per orang)."""
    izin = permissions.get_all(tenant_id=tenant_id)
    if not izin.get("izin_dashboard_nilai_service"):
        hasil["total_toko"]["nilai_service"] = None
    if not izin.get("izin_dashboard_total_komisi"):
        hasil["total_toko"]["komisi"] = None
    if not izin.get("izin_dashboard_total_tips"):
        hasil["total_toko"]["tips"] = None
    if not izin.get("izin_dashboard_uang_harian"):
        hasil["total_toko"]["uang_harian"] = None
    if not izin.get("izin_dashboard_bonus_customer"):
        hasil["total_toko"]["bonus_customer"] = None
    if not izin.get("izin_dashboard_pengeluaran_toko"):
        hasil["total_pengeluaran"] = None
    if not izin.get("izin_dashboard_penjualan_produk"):
        hasil["penjualan_produk"] = None
    if not izin.get("izin_dashboard_laba_kotor"):
        hasil["laba_kotor"] = None
    if not izin.get("izin_dashboard_jumlah_service"):
        hasil["rincian_service_semua_barber"] = []
    hasil["per_barber"] = []  # rincian per-barber: di luar cakupan Dashboard Admin
    return hasil


@router.get("/owner")
def dashboard_owner(tahun: int = None, bulan: int = None, user: dict = Depends(require_owner_or_staff)):
    """Ringkasan SEMUA barber aktif untuk satu bulan, plus total keseluruhan toko.
    REVISI: Bonus Kehadiran dihapus total (lihat database.get_ringkasan_barber_bulan).
    `rincian_service_semua_barber` ditambahkan (gabungan rincian_service seluruh
    barber, dijumlahkan per nama service) supaya dropdown "Semua Barber" pada
    kartu Service Bulan Ini tidak perlu menghitung apa pun sendiri di frontend."""
    if tahun is None or bulan is None:
        tahun, bulan = _bulan_ini()
    barbers = db.get_barbers(tenant_id=user["tenant_id"])
    # AUDIT KONEKSI (psycopg2.pool.PoolError "connection pool exhausted" di
    # produksi): SEBELUMNYA memanggil db.get_ringkasan_barber_bulan() satu-
    # satu per barber, masing-masing ~15 checkout koneksi terpisah -- untuk
    # toko dengan banyak barber, SATU load Dashboard Owner bisa menghabiskan
    # ratusan checkout sekaligus. get_ringkasan_semua_barber_bulan() (versi
    # batch, rumus IDENTIK, lihat docstring-nya) menghitung SEMUA barber
    # lewat segelintir query saja.
    ringkasan_per_barber = [_tanpa_kolom_biner_ringkasan(r) for r in db.get_ringkasan_semua_barber_bulan(barbers, tahun, bulan, tenant_id=user["tenant_id"])]
    total_toko = {
        "nilai_service": sum(r["nilai_service"] for r in ringkasan_per_barber),
        "komisi": sum(r["komisi"] for r in ringkasan_per_barber),
        "tips": sum(r["tips"] for r in ringkasan_per_barber),
        "uang_harian": sum(r["uang_harian"] for r in ringkasan_per_barber),
        "bonus_customer": sum(r["bonus_customer"] for r in ringkasan_per_barber),
        "total_pendapatan": sum(r["total_pendapatan"] for r in ringkasan_per_barber),
        "jumlah_customer": sum(r["jumlah_customer"] for r in ringkasan_per_barber),
    }
    total_pengeluaran = db.get_total_pengeluaran(tahun=tahun, bulan=bulan, tenant_id=user["tenant_id"])
    # REVISI: kartu "Penjualan Produk" -- omzet HANYA dari transaksi produk
    # bertipe Jual (Restock bukan penjualan, Tester sengaja tidak dihitung,
    # lihat database.get_omzet_penjualan_produk). SENGAJA TIDAK diikutkan ke
    # laba_kotor di bawah -- bukan diminta, rumus laba kotor toko lama tetap
    # sama persis seperti sebelumnya.
    penjualan_produk = db.get_omzet_penjualan_produk(tahun=tahun, bulan=bulan, tenant_id=user["tenant_id"])

    rincian_gabungan = {}
    for r in ringkasan_per_barber:
        for item in r["rincian_service"]:
            rincian_gabungan[item["nama_service"]] = rincian_gabungan.get(item["nama_service"], 0) + item["jumlah"]
    rincian_service_semua_barber = sorted(
        [{"nama_service": k, "jumlah": v} for k, v in rincian_gabungan.items() if v > 0],
        key=lambda x: (-x["jumlah"], x["nama_service"]),
    )

    hasil = {
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
    if user["role"] == "staff":
        hasil = _filter_dashboard_untuk_staff(hasil, user["tenant_id"])
    return hasil


@router.get("/barber")
def dashboard_barber(tahun: int = None, bulan: int = None, user: dict = Depends(require_barber)):
    if tahun is None or bulan is None:
        tahun, bulan = _bulan_ini()
    barber_id = user.get("barber_id")
    if barber_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Akun ini belum dikaitkan ke data Barber. Hubungi Owner.")
    return _tanpa_kolom_biner_ringkasan(db.get_ringkasan_barber_bulan(barber_id, tahun, bulan))


def _barber_terpilih(barber_id: int, tenant_id: int):
    """Dipakai kedua endpoint grafik di bawah: barber_id kosong (None) berarti
    gabungan SEMUA barber aktif; kalau diisi, hanya barber itu (dicari
    langsung by id, bukan cuma dari daftar aktif -- konsisten dengan endpoint
    lain yang tetap bisa menampilkan data historis barber yang sudah
    dinonaktifkan).
    FONDASI Multi-Tenant Phase 1: barber_id dari query string bebas ditulis
    siapa pun yang memanggil endpoint -- kalau ID itu ternyata milik tenant
    LAIN, kembalikan [] (bukan 404/403) supaya perilaku sama seperti
    "barber_id tidak ditemukan" tanpa membocorkan bahwa ID itu sebenarnya ada."""
    if barber_id is not None:
        barber = db.get_barber(barber_id)
        if barber is None or barber.get("tenant_id") != tenant_id:
            return []
        return [barber]
    return db.get_barbers(tenant_id=tenant_id)


@router.get("/owner/grafik-harian")
def grafik_harian(tahun: int, bulan: int, barber_id: int = None, user: dict = Depends(require_admin)):
    """Diagram batang PENDAPATAN HARIAN (khusus Owner) untuk satu bulan --
    satu batang per tanggal (1 s.d. jumlah hari di bulan itu), termasuk
    tanggal yang belum ada transaksi (nilainya 0, supaya sumbu tanggal tetap
    utuh/tidak "loncat"). barber_id kosong = gabungan SEMUA barber.

    Pendapatan di sini = Komisi + Tips + Uang Harian hari itu (memakai
    hitung_uang_harian_per_hari yang sudah ada, aturan target service acuan
    per hari -- lihat Setting > Uang Harian -- TIDAK diubah sama sekali).
    Bonus Customer SENGAJA tidak
    diikutkan -- itu perhitungan BULANAN (lihat hitung_bonus_customer), tidak
    ada cara membaginya secara berarti per tanggal, jadi disertakan penuh di
    /owner/grafik-bulanan (total_pendapatan bulan itu) supaya tidak ada
    angka yang menyesatkan di kedua grafik."""
    jumlah_hari = calendar.monthrange(tahun, bulan)[1]
    barbers = _barber_terpilih(barber_id, user["tenant_id"])

    # AUDIT KONEKSI: SEBELUMNYA satu checkout koneksi per barber PER HARI
    # (sampai ~31x per barber) -- get_pendapatan_harian_semua_barber() (versi
    # batch, rumus IDENTIK, lihat docstring-nya) mengambil seluruh transaksi
    # bulan itu lewat SATU query lalu mengelompokkan per hari di Python.
    pendapatan_per_hari = db.get_pendapatan_harian_semua_barber(barbers, tahun, bulan, jumlah_hari, tenant_id=user["tenant_id"])

    return [{"tanggal": h, "pendapatan": pendapatan_per_hari[h]} for h in range(1, jumlah_hari + 1)]


@router.get("/owner/grafik-bulanan")
def grafik_bulanan(tahun: int, barber_id: int = None, user: dict = Depends(require_admin)):
    """Diagram batang PENDAPATAN BULANAN (khusus Owner) untuk satu tahun --
    satu batang per bulan (Januari s.d. Desember), termasuk bulan yang belum
    ada data (nilainya 0). barber_id kosong = gabungan SEMUA barber.
    Pendapatan di sini = total_pendapatan PENUH (Komisi + Tips + Uang Harian
    + Bonus Customer) dari get_ringkasan_barber_bulan yang sudah ada --
    bonus wajar diikutkan di sini karena memang perhitungan bulanan."""
    barbers = _barber_terpilih(barber_id, user["tenant_id"])

    # AUDIT KONEKSI: SEBELUMNYA get_ringkasan_barber_bulan() (per barber, ~15
    # checkout koneksi) dipanggil untuk SETIAP barber x SETIAP bulan (12x) --
    # sekarang get_ringkasan_semua_barber_bulan() dipanggil sekali PER BULAN
    # (bukan lagi per barber juga), rumus IDENTIK.
    hasil = []
    for bulan in range(1, 13):
        ringkasan_bulan = db.get_ringkasan_semua_barber_bulan(barbers, tahun, bulan, tenant_id=user["tenant_id"])
        total = sum(r["total_pendapatan"] for r in ringkasan_bulan)
        hasil.append({"bulan": bulan, "pendapatan": total})
    return hasil
