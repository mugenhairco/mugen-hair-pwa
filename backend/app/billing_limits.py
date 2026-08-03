"""billing_limits.py — FONDASI Multi-Tenant Phase 4: Penegakan Limit Pemakaian
=============================================================================
HANYA limit yang punya entitas nyata di aplikasi ini (barber/user/layanan/
booking) yang ditegakkan di sini -- lihat billing_db.py::LIMIT_FIELDS untuk
penjelasan lengkap kenapa max_cabang TIDAK ada (aplikasi ini belum punya
konsep "cabang" sama sekali).

Dipanggil dari LAPISAN ROUTER (routers/pengaturan.py::tambah_barber/
tambah_service/tambah_user, routers/booking.py::public_buat_booking) --
SENGAJA TIDAK ditaruh di database.py/auth_db.py/booking_db.py supaya
business logic murni CRUD tetap tidak tahu apa-apa soal billing (prinsip
sama seperti permissions.py, juga dipanggil dari router bukan dari
database.py). Setiap fungsi `pastikan_boleh_*` melempar ValueError kalau
sudah di batas -- router yang memanggil SUDAH punya pola
`except ValueError as e: raise HTTPException(422, ...)` di setiap endpoint
pembuatan barber/service/user/booking, jadi tinggal dipanggil di awal try.

Limit NULL (kolom subscription_packages.max_xxx) = TIDAK DIBATASI. Tenant
TANPA baris tenant_subscriptions ATAU paketnya TIDAK punya baris
subscription_packages sama sekali JUGA TIDAK dibatasi (fail-open, sama
seperti subscription_db.akses_diblokir() -- konfigurasi billing yang belum
lengkap/hilang tidak boleh diam-diam memblokir toko menambah data)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import auth_db
import billing_db
import booking_db
import database as db
import subscription_db

WIB = ZoneInfo("Asia/Jakarta")


def _limit_paket(tenant_id: int, kolom_limit: str) -> int | None:
    sub = subscription_db.get_subscription(tenant_id)
    if sub is None:
        return None
    paket = billing_db.get_package_by_kode(sub["package"])
    if paket is None:
        return None
    return paket.get(kolom_limit)


def pastikan_boleh_tambah_barber(tenant_id: int):
    limit = _limit_paket(tenant_id, "max_barber")
    if limit is None:
        return
    jumlah = len(db.get_barbers(hanya_aktif=True, tenant_id=tenant_id))
    if jumlah >= limit:
        raise ValueError(
            f"Paket langganan saat ini hanya mengizinkan maksimal {limit} barber aktif. "
            "Upgrade paket untuk menambah barber baru."
        )


def pastikan_boleh_tambah_user(tenant_id: int):
    limit = _limit_paket(tenant_id, "max_user")
    if limit is None:
        return
    jumlah = len(auth_db.get_user_list(tenant_id=tenant_id))
    if jumlah >= limit:
        raise ValueError(
            f"Paket langganan saat ini hanya mengizinkan maksimal {limit} akun user. "
            "Upgrade paket untuk menambah user baru."
        )


def pastikan_boleh_tambah_layanan(tenant_id: int):
    limit = _limit_paket(tenant_id, "max_layanan")
    if limit is None:
        return
    jumlah = len(db.get_services(hanya_aktif=True, tenant_id=tenant_id))
    if jumlah >= limit:
        raise ValueError(
            f"Paket langganan saat ini hanya mengizinkan maksimal {limit} layanan aktif. "
            "Upgrade paket untuk menambah layanan baru."
        )


def pastikan_boleh_tambah_booking(tenant_id: int):
    """max_booking dihitung PER BULAN KALENDER berjalan (WIB) -- bukan
    kumulatif sepanjang umur toko, supaya kuota berulang otomatis setiap
    bulan mengikuti siklus tagihan, tanpa perlu proses reset terpisah.
    Hanya booking status_booking='aktif' yang dihitung (booking yang sudah
    dibatalkan tidak memakan kuota)."""
    limit = _limit_paket(tenant_id, "max_booking")
    if limit is None:
        return
    sekarang = datetime.now(WIB)
    jumlah = len(booking_db.get_booking_list(
        tahun=sekarang.year, bulan=sekarang.month, status_booking="aktif", tenant_id=tenant_id,
    ))
    if jumlah >= limit:
        raise ValueError(
            f"Paket langganan saat ini hanya mengizinkan maksimal {limit} booking per bulan. "
            "Upgrade paket untuk menerima booking lebih banyak bulan ini."
        )


# ============================= Downgrade =============================
# SESUAI KEPUTUSAN cakupan Phase 4: downgrade diblokir TOTAL selama
# pemakaian SEKARANG melebihi limit paket TUJUAN -- TIDAK ADA penonaktifan
# otomatis barber/user/layanan/booking apa pun di sini. Owner harus
# mengurangi pemakaian sendiri lebih dulu (mis. nonaktifkan sebagian
# barber) baru downgrade bisa diproses -- lihat routers/billing.py::downgrade().

_LABEL_LIMIT = {
    "max_barber": "barber aktif",
    "max_user": "akun user",
    "max_layanan": "layanan aktif",
    "max_booking": "booking bulan ini",
}


def hitung_pemakaian(tenant_id: int) -> dict:
    """Pemakaian SEKARANG untuk setiap limit yang benar-benar ditegakkan
    (lihat docstring modul) -- max_booking dihitung bulan kalender berjalan,
    sama seperti pastikan_boleh_tambah_booking()."""
    sekarang = datetime.now(WIB)
    return {
        "max_barber": len(db.get_barbers(hanya_aktif=True, tenant_id=tenant_id)),
        "max_user": len(auth_db.get_user_list(tenant_id=tenant_id)),
        "max_layanan": len(db.get_services(hanya_aktif=True, tenant_id=tenant_id)),
        "max_booking": len(booking_db.get_booking_list(
            tahun=sekarang.year, bulan=sekarang.month, status_booking="aktif", tenant_id=tenant_id,
        )),
    }


def evaluasi_downgrade(tenant_id: int, target_package: dict) -> list:
    """Return daftar PESAN pelanggaran (list kosong = boleh downgrade).
    Limit NULL di paket tujuan = tidak dibatasi, tidak ikut dicek."""
    pemakaian = hitung_pemakaian(tenant_id)
    pelanggaran = []
    for kolom, label in _LABEL_LIMIT.items():
        limit = target_package.get(kolom)
        if limit is None:
            continue
        jumlah = pemakaian[kolom]
        if jumlah > limit:
            pelanggaran.append(f"{label} ({jumlah} terpakai, maksimal {limit} di paket tujuan)")
    return pelanggaran
