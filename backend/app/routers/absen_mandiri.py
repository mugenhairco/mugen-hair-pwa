"""routers/absen_mandiri.py — /api/public/absen-mandiri/* (FITUR BARU: Absen
Mandiri — Check In/Check Out GPS TANPA LOGIN untuk karyawan Non-Barber:
Kasir/OB/Kru/dst)
=============================================================================
Halaman PUBLIK (pola SAMA PERSIS booking.py::public_router -- resolusi
tenant lewat resolve_tenant_publik() + cek subscription_db.akses_diblokir(),
lihat _resolve_tenant_aktif() di bawah) -- TIDAK ADA sesi login/JWT sama
sekali di jalur ini, barber_id dikirim mentah dari body request oleh
frontend (pages/absen_mandiri.js) persis seperti booking publik mengirim
barber_id pilihan customer.

"Semua validasi dilakukan di backend" -- SELURUH logika (jendela waktu untuk
Barber vs Non-Barber, radius GPS, device-lock) tetap 100% di
attendance_db.py (dipanggil APA ADANYA, TIDAK diduplikasi di sini) --
endpoint di sini murni meneruskan input mentah + menandai `sumber=
"absen_mandiri"` pada Check In supaya baris attendance_logs yang dihasilkan
bisa dibedakan asalnya untuk audit (lihat Log Audit yang sudah ada)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import absen_mandiri_db
import attendance_db
import subscription_db
from auth import resolve_tenant_publik
from routers.attendance import _ekstrak_metadata

public_router = APIRouter(prefix="/api/public/absen-mandiri", tags=["absen-mandiri-public"])


def _resolve_tenant_aktif(tenant_id: int = Depends(resolve_tenant_publik)) -> int:
    """Pola SAMA PERSIS booking.py::resolve_tenant_publik_aktif() -- tenant
    TANPA baris subscription dianggap TIDAK diblokir (fail-open)."""
    if subscription_db.akses_diblokir(tenant_id):
        raise HTTPException(status_code=403, detail="Halaman Absen Mandiri toko ini sedang tidak tersedia. Hubungi Owner.")
    return tenant_id


@public_router.get("/karyawan")
def daftar_karyawan(tenant_id: int = Depends(_resolve_tenant_aktif)):
    return absen_mandiri_db.get_daftar_karyawan_publik(tenant_id)


@public_router.get("/status/{barber_id}")
def status_hari_ini(barber_id: int, tenant_id: int = Depends(_resolve_tenant_aktif)):
    """Dipakai halaman publik SETELAH karyawan memilih namanya -- supaya
    tombol yang tepat (Check In atau Check Out) yang ditampilkan, sebelum
    GPS diminta sama sekali."""
    karyawan = absen_mandiri_db.get_daftar_karyawan_publik(tenant_id)
    if not any(k["id"] == barber_id for k in karyawan):
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan.")
    settings = attendance_db.get_settings(tenant_id)
    log = attendance_db.get_log_hari_ini(barber_id, tenant_id)
    status = attendance_db.hitung_status_hari_ini(log, settings)
    return {"log": log, "status": status}


class GpsBodyPublik(BaseModel):
    barber_id: int
    latitude: float
    longitude: float
    accuracy: float | None = None
    speed: float | None = None
    heading: float | None = None
    # ID acak dibuat & disimpan client-side (localStorage, lihat pages/
    # absen_mandiri.js) -- lihat absen_mandiri_db.py untuk penjelasan
    # lengkap device-lock-nya.
    device_id: str


@public_router.post("/check-in")
def check_in(body: GpsBodyPublik, request: Request, tenant_id: int = Depends(_resolve_tenant_aktif)):
    browser, device, ip = _ekstrak_metadata(request)
    try:
        return attendance_db.check_in(
            tenant_id, body.barber_id, body.latitude, body.longitude, accuracy=body.accuracy,
            speed=body.speed, heading=body.heading, browser=browser, device=device, ip_address=ip,
            device_id=body.device_id, sumber="absen_mandiri",
        )
    except ValueError as e:
        attendance_db.catat_audit(body.barber_id, "check_in", False, alasan_gagal=str(e),
                                   latitude=body.latitude, longitude=body.longitude, accuracy=body.accuracy,
                                   browser=browser, device=device, ip_address=ip, tenant_id=tenant_id)
        raise HTTPException(status_code=422, detail=str(e))


@public_router.post("/check-out")
def check_out(body: GpsBodyPublik, request: Request, tenant_id: int = Depends(_resolve_tenant_aktif)):
    browser, device, ip = _ekstrak_metadata(request)
    try:
        return attendance_db.check_out(
            tenant_id, body.barber_id, body.latitude, body.longitude, accuracy=body.accuracy,
            speed=body.speed, heading=body.heading, browser=browser, device=device, ip_address=ip,
            device_id=body.device_id,
        )
    except ValueError as e:
        attendance_db.catat_audit(body.barber_id, "check_out", False, alasan_gagal=str(e),
                                   latitude=body.latitude, longitude=body.longitude, accuracy=body.accuracy,
                                   browser=browser, device=device, ip_address=ip, tenant_id=tenant_id)
        raise HTTPException(status_code=422, detail=str(e))
