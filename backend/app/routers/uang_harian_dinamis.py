"""routers/uang_harian_dinamis.py — /api/uang-harian-dinamis/* (FITUR Uang
Harian Dinamis Berdasarkan Absensi)
=============================================================================
Lihat docstring lengkap di uang_harian_dinamis_db.py untuk konsep inti.

Hak akses:
- Konfigurasi (GET/PUT /config): KHUSUS Owner (require_admin) -- pola SAMA
  seperti endpoint Uang Harian lain di routers/pengaturan.py (acuan/target).
- Breakdown (GET /breakdown): Owner/Admin boleh lihat barber mana pun
  (barber_id wajib diisi); Barber HANYA boleh lihat miliknya sendiri
  (barber_id diabaikan) -- pola akses SAMA PERSIS
  routers/attendance.py::ringkasan_bulan()."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import uang_harian_dinamis_db
from auth import get_current_user, require_admin
from database import get_barber

router = APIRouter(prefix="/api/uang-harian-dinamis", tags=["uang_harian_dinamis"])


@router.get("/config")
def ambil_config(user: dict = Depends(get_current_user)):
    """Boleh dibaca SEMUA role (termasuk Barber) -- tidak ada info sensitif
    (persentase potongan/ambang bukan rahasia), dan halaman Absensi Barber
    (pages/absensi.js) perlu tahu `aktif` untuk memutuskan menampilkan kartu
    "Rincian Uang Harian" atau tidak. HANYA mengubah (PUT di bawah) yang
    tetap KHUSUS Owner (require_admin)."""
    if user["role"] not in ("admin", "staff", "barber"):
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    return uang_harian_dinamis_db.get_config(user["tenant_id"])


class ConfigBody(BaseModel):
    aktif: bool | None = None
    keterlambatan_gunakan_toleransi: bool | None = None
    keterlambatan_gunakan_limit: bool | None = None
    keterlambatan_potongan_persen: int | None = None
    pulang_awal_gunakan_toleransi: bool | None = None
    pulang_awal_gunakan_limit: bool | None = None
    pulang_awal_potongan_persen: int | None = None
    kombinasi_metode: str | None = None
    service_rule_mode: str | None = None
    service_rule_minimal: int | None = None
    service_rule_potongan_persen: int | None = None


@router.put("/config")
def ubah_config(body: ConfigBody, user: dict = Depends(require_admin)):
    try:
        return uang_harian_dinamis_db.set_config(user["tenant_id"], **body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/breakdown")
def ambil_breakdown(tanggal: str, barber_id: int = None, user: dict = Depends(get_current_user)):
    """`tanggal` format YYYY-MM-DD, WAJIB diisi -- breakdown SATU hari
    (lihat uang_harian_dinamis_db.breakdown_hari(), section 17 permintaan
    Owner: transparansi penuh alasan potongan)."""
    if user["role"] == "barber":
        if user.get("barber_id") is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
        target_barber_id = user["barber_id"]
    elif user["role"] in ("admin", "staff"):
        if barber_id is None:
            raise HTTPException(status_code=422, detail="barber_id wajib diisi.")
        target_barber_id = barber_id
    else:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")

    barber = get_barber(target_barber_id)
    if barber is None or barber.get("tenant_id") != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Barber tidak ditemukan.")
    return uang_harian_dinamis_db.breakdown_hari(barber, tanggal)
