"""routers/attendance.py — /api/attendance/* (Modul BARU: Absensi GPS Check In/Out)
=============================================================================
Hak akses (SESUAI SPESIFIKASI, dibahas & disetujui Owner sebelum implementasi):
- superadmin: TIDAK PUNYA akses sama sekali ke modul ini (akun platform,
  bukan operasional tenant -- tidak didaftarkan lewat get_current_user
  biasa, endpoint di sini otomatis menolaknya lewat require_owner_or_staff/
  require_barber, konsisten seluruh modul operasional lain).
- admin (Owner): akses PENUH tanpa syarat (lihat semua endpoint).
- staff (Admin, label UI): boleh MELIHAT (dashboard/riwayat/laporan/audit)
  TANPA butuh permission apa pun (pola sama seperti pengeluaran.py) --
  TAPI mengubah Pengaturan Absensi (PUT /settings) wajib izin eksplisit
  Owner (permissions.izin_absensi_pengaturan).
- barber: HANYA self-service (Check In/Out milik sendiri, status hari ini
  sendiri, riwayat sendiri) -- endpoint /settings, /dashboard, list semua
  barber, dan /audit SEMUA ditolak untuk role ini.

"Semua validasi dilakukan di backend. Frontend hanya menampilkan hasil
validasi." -- endpoint check-in/check-out di sini murni meneruskan input
mentah (koordinat GPS, accuracy, dst) ke attendance_db.check_in()/
check_out() yang melakukan SELURUH validasi (radius Haversine, jendela
waktu, akurasi GPS, dst)."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

import attendance_db
import laporan_pdf
import permissions
from auth import get_current_user, require_barber, require_feature, require_owner_or_staff, require_permission

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


def _cek_akses_lihat(user: dict):
    """Owner/Admin boleh MELIHAT tanpa syarat permission apa pun (view-only,
    sama seperti pengeluaran.py) -- HANYA barber & superadmin yang ditolak."""
    if user["role"] not in ("admin", "staff"):
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")


_UA_BROWSER_PATTERNS = [
    ("Edge", r"Edg/"), ("Samsung Internet", r"SamsungBrowser/"), ("Opera", r"OPR/|Opera/"),
    ("Chrome", r"Chrome/"), ("Firefox", r"Firefox/"), ("Safari", r"Version/.*Safari/"),
]
_UA_DEVICE_PATTERNS = [
    ("iPhone", r"iPhone"), ("iPad", r"iPad"), ("Android", r"Android"),
    ("Windows", r"Windows"), ("Mac", r"Macintosh"), ("Linux", r"Linux"),
]


def _ekstrak_metadata(request: Request) -> tuple[str, str, str]:
    """Browser/Device (parsing ringan User-Agent, TIDAK butuh dependency
    tambahan) + IP Address (X-Forwarded-For didahulukan -- Render/reverse
    proxy lain selalu ada di depan aplikasi ini, request.client.host akan
    selalu berisi IP proxy internal, BUKAN IP asli pengunjung, kalau header
    itu tidak dicek dulu)."""
    ua = request.headers.get("user-agent", "") or ""
    browser = next((nama for nama, pola in _UA_BROWSER_PATTERNS if re.search(pola, ua)), "Tidak diketahui")
    device = next((nama for nama, pola in _UA_DEVICE_PATTERNS if re.search(pola, ua)), "Tidak diketahui")
    xff = request.headers.get("x-forwarded-for")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)
    return browser, device, ip


# ---------------------------------------------------------------------------
# Pengaturan Absensi
# ---------------------------------------------------------------------------

@router.get("/settings")
def ambil_settings(user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    return attendance_db.get_settings(user["tenant_id"])


class SettingsBody(BaseModel):
    jam_masuk: str | None = None
    toleransi_menit: int | None = None
    jam_pulang: str | None = None
    radius_meter: int | None = None
    lokasi_nama: str | None = None
    lokasi_latitude: float | None = None
    lokasi_longitude: float | None = None


@router.put("/settings")
def ubah_settings(body: SettingsBody, user: dict = Depends(require_permission("izin_absensi_pengaturan"))):
    try:
        return attendance_db.set_settings(
            user["tenant_id"], jam_masuk=body.jam_masuk, toleransi_menit=body.toleransi_menit,
            jam_pulang=body.jam_pulang, radius_meter=body.radius_meter, lokasi_nama=body.lokasi_nama,
            lokasi_latitude=body.lokasi_latitude, lokasi_longitude=body.lokasi_longitude,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ---------------------------------------------------------------------------
# Self-service Barber
# ---------------------------------------------------------------------------

@router.get("/today")
def status_hari_ini(user: dict = Depends(require_barber)):
    if user.get("barber_id") is None:
        raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
    settings = attendance_db.get_settings(user["tenant_id"])
    log = attendance_db.get_log_hari_ini(user["barber_id"], user["tenant_id"])
    status = attendance_db.hitung_status_hari_ini(log, settings)
    return {"log": log, "status": status, "settings": settings}


class GpsBody(BaseModel):
    latitude: float
    longitude: float
    accuracy: float | None = None
    speed: float | None = None
    heading: float | None = None


@router.post("/check-in")
def check_in(body: GpsBody, request: Request, user: dict = Depends(require_barber)):
    if user.get("barber_id") is None:
        raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
    browser, device, ip = _ekstrak_metadata(request)
    try:
        return attendance_db.check_in(
            user["tenant_id"], user["barber_id"], body.latitude, body.longitude, accuracy=body.accuracy,
            speed=body.speed, heading=body.heading, browser=browser, device=device, ip_address=ip,
        )
    except ValueError as e:
        attendance_db.catat_audit(user["barber_id"], "check_in", False, alasan_gagal=str(e),
                                   latitude=body.latitude, longitude=body.longitude, accuracy=body.accuracy,
                                   browser=browser, device=device, ip_address=ip, tenant_id=user["tenant_id"])
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/check-out")
def check_out(body: GpsBody, request: Request, user: dict = Depends(require_barber)):
    if user.get("barber_id") is None:
        raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
    browser, device, ip = _ekstrak_metadata(request)
    try:
        return attendance_db.check_out(
            user["tenant_id"], user["barber_id"], body.latitude, body.longitude, accuracy=body.accuracy,
            speed=body.speed, heading=body.heading, browser=browser, device=device, ip_address=ip,
        )
    except ValueError as e:
        attendance_db.catat_audit(user["barber_id"], "check_out", False, alasan_gagal=str(e),
                                   latitude=body.latitude, longitude=body.longitude, accuracy=body.accuracy,
                                   browser=browser, device=device, ip_address=ip, tenant_id=user["tenant_id"])
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/history")
def riwayat_sendiri(tanggal_dari: str = None, tanggal_sampai: str = None,
                     user: dict = Depends(require_barber)):
    if user.get("barber_id") is None:
        raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
    return attendance_db.get_log_list(user["tenant_id"], tanggal_dari=tanggal_dari,
                                       tanggal_sampai=tanggal_sampai, barber_id=user["barber_id"])


# ---------------------------------------------------------------------------
# Owner/Admin: Dashboard, daftar, detail, laporan, audit
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def dashboard(user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    return attendance_db.get_ringkasan_dashboard(user["tenant_id"])


@router.get("")
def daftar_absensi(tanggal: str = None, tanggal_dari: str = None, tanggal_sampai: str = None,
                    barber_id: int = None, status: str = None, user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    return attendance_db.get_log_list(user["tenant_id"], tanggal=tanggal, tanggal_dari=tanggal_dari,
                                       tanggal_sampai=tanggal_sampai, barber_id=barber_id, status=status)


@router.get("/pdf")
def daftar_absensi_pdf(tanggal: str = None, tanggal_dari: str = None, tanggal_sampai: str = None,
                        barber_id: int = None, status: str = None, user: dict = Depends(get_current_user),
                        _fitur: dict = Depends(require_feature("export_pdf"))):
    """Route ini didaftarkan SEBELUM /{log_id} supaya 'pdf' tidak ditangkap
    sebagai path parameter log_id."""
    _cek_akses_lihat(user)
    konten = laporan_pdf.buat_pdf_absensi_list(tanggal, tanggal_dari, tanggal_sampai, barber_id, status,
                                                user["username"], tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("absensi")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/excel")
def daftar_absensi_excel(tanggal: str = None, tanggal_dari: str = None, tanggal_sampai: str = None,
                          barber_id: int = None, status: str = None, user: dict = Depends(get_current_user),
                          _fitur: dict = Depends(require_feature("export_pdf"))):
    """Feature gate SAMA dengan export PDF (paket yang boleh export PDF
    Laporan juga boleh export Excel -- tidak ada kode fitur terpisah)."""
    _cek_akses_lihat(user)
    import attendance_excel
    konten = attendance_excel.buat_excel_absensi_list(tanggal, tanggal_dari, tanggal_sampai, barber_id, status,
                                                        tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("absensi").replace(".pdf", ".xlsx")
    return Response(content=konten, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/audit")
def audit_log(barber_id: int = None, tanggal_dari: str = None, tanggal_sampai: str = None,
              user: dict = Depends(require_owner_or_staff)):
    """Investigasi Owner/Admin (bagian ANTI FAKE GPS spesifikasi) -- daftar
    percobaan check-in/out, berhasil MAUPUN gagal."""
    return attendance_db.get_audit_list(user["tenant_id"], barber_id=barber_id, tanggal_dari=tanggal_dari,
                                         tanggal_sampai=tanggal_sampai)


@router.get("/{log_id}")
def detail_absensi(log_id: int, user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    log = attendance_db.get_log(log_id)
    if log is None or log.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data absensi tidak ditemukan.")
    return log
