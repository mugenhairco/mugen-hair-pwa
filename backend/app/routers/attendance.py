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
import auto_libur_db
import laporan_pdf
import permissions
from auth import (get_current_user, require_admin, require_barber, require_feature, require_owner_or_staff,
                   require_permission)

# FITUR Feature Gating "Absensi Karyawan" (diminta Owner): SELURUH endpoint
# di router ini (Check In/Out, riwayat, dashboard, pengaturan, koreksi,
# audit, export PDF/Excel) digerbang SATU kode fitur "absensi" lewat
# `dependencies=` di level router -- FastAPI menjalankannya untuk SETIAP
# request ke prefix ini, TIDAK PERLU ditambahkan satu per satu ke tiap
# endpoint. Fail-CLOSED SEJAK AWAL (TIDAK ada grandfather, lihat
# billing_db.py::_FITUR_DEFAULT), keputusan eksplisit Owner -- berlaku
# untuk SEMUA role (Owner/Admin/Barber) tanpa kecuali, independen dari
# gate "barber_app" (login akun barber, lihat routers/auth_router.py) --
# tenant bisa saja punya barber_app TANPA absensi (barber tetap bisa login
# & booking, tapi menu Absensi tidak bisa dipakai sama sekali), atau
# sebaliknya.
router = APIRouter(prefix="/api/attendance", tags=["attendance"],
                    dependencies=[Depends(require_feature("absensi"))])


def _cek_akses_lihat(user: dict):
    """Owner boleh MELIHAT tanpa syarat -- 'staff' sekarang digerbang level
    menu "Absensi" (Hak Akses Menu, izin_absensi_lihat, REVISI dari
    sebelumnya yang tanpa gerbang permission sama sekali) -- barber &
    superadmin tetap ditolak total (self-service barber lewat endpoint lain,
    lihat require_barber)."""
    if user["role"] == "admin":
        return
    if user["role"] != "staff":
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    if not permissions.has_any(
        ["izin_absensi_lihat", "izin_absensi_pengaturan", "izin_absensi_koreksi"],
        tenant_id=user.get("tenant_id"), role_id=user.get("custom_role_id"),
    ):
        raise HTTPException(status_code=403, detail="Admin tidak punya akses ke menu ini. Hubungi Owner.")


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
    batas_menit_terlambat: int | None = None
    batas_menit_pulang_awal: int | None = None
    # FITUR Uang Harian Dinamis: lihat catatan lengkap di
    # attendance_db.py::DEFAULT_SETTINGS -- disimpan di attendance_settings
    # (pasangan simetris toleransi_menit) tapi TIDAK dipakai logika Absensi
    # itu sendiri, hanya oleh uang_harian_dinamis_db.py.
    toleransi_pulang_awal_menit: int | None = None
    # FITUR Toleransi Absen Lebih Awal: lihat catatan lengkap di
    # attendance_db.py::DEFAULT_SETTINGS/validasi_checkin() -- menggeser
    # batas AWAL yang diizinkan Check In (jam_masuk - nilai ini), TIDAK
    # mengubah jam_masuk/status tepat_waktu itu sendiri.
    toleransi_absen_awal_menit: int | None = None


@router.put("/settings")
def ubah_settings(body: SettingsBody, user: dict = Depends(require_permission("izin_absensi_pengaturan"))):
    try:
        return attendance_db.set_settings(
            user["tenant_id"], jam_masuk=body.jam_masuk, toleransi_menit=body.toleransi_menit,
            jam_pulang=body.jam_pulang, radius_meter=body.radius_meter, lokasi_nama=body.lokasi_nama,
            lokasi_latitude=body.lokasi_latitude, lokasi_longitude=body.lokasi_longitude,
            batas_menit_terlambat=body.batas_menit_terlambat, batas_menit_pulang_awal=body.batas_menit_pulang_awal,
            toleransi_pulang_awal_menit=body.toleransi_pulang_awal_menit,
            toleransi_absen_awal_menit=body.toleransi_absen_awal_menit,
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
                          _fitur: dict = Depends(require_feature("export_excel"))):
    """REVISI (audit "fitur hardcode di Superadmin"): SEBELUMNYA nebeng gate
    "export_pdf" (lihat riwayat git) -- "Export Excel" sudah ada sebagai
    kode fitur SENDIRI di katalog Superadmin sejak awal, jadi sekarang
    benar-benar dipakai (require_feature("export_excel")) alih-alih diam-
    diam ikut aturan Export PDF, supaya Super Admin bisa mengatur keduanya
    independen per paket (lihat billing_db.py::seed_grandfather_fitur_baru_
    digerbang() -- fitur ini sebelumnya selalu menyala gratis, di-grandfather
    ke SEMUA paket yang sudah ada supaya tenant lama tidak kehilangan akses)."""
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


@router.delete("/audit")
def hapus_audit_log(user: dict = Depends(require_admin)):
    """Hapus PERMANEN seluruh Log Audit (diminta Owner) -- KHUSUS Owner
    (require_admin, TIDAK bisa didelegasikan lewat Hak Akses Admin ke staff)
    karena log ini sendiri adalah alat investigasi Fake GPS/kecurangan --
    staff yang berkepentingan dalam hasil investigasi tidak boleh punya
    kuasa menghapus buktinya."""
    jumlah = attendance_db.hapus_semua_audit_log(user["tenant_id"])
    return {"ok": True, "jumlah_dihapus": jumlah}


@router.delete("/riwayat")
def hapus_riwayat(barber_id: int = None, user: dict = Depends(require_owner_or_staff)):
    """Reset/hapus PERMANEN riwayat Check In/Out (attendance_logs) --
    mengantisipasi data yang menumpuk (permintaan Owner). barber_id diisi ->
    hanya riwayat barber itu; kosong -> SEMUA barber. Owner ATAU Admin
    (staff) boleh -- BEDA dari DELETE /audit di atas (KHUSUS Owner), karena
    ini murni pembersihan data operasional, bukan bukti investigasi."""
    jumlah = attendance_db.hapus_riwayat_absensi(user["tenant_id"], barber_id=barber_id)
    return {"ok": True, "jumlah_dihapus": jumlah}


# ---------------------------------------------------------------------------
# Ringkasan limit Keterlambatan & Pulang Lebih Awal (bulanan)
# ---------------------------------------------------------------------------

@router.get("/ringkasan-bulan")
def ringkasan_bulan(tahun: int = None, bulan: int = None, barber_id: int = None,
                     user: dict = Depends(get_current_user)):
    """Barber: SELALU ringkasan miliknya sendiri (barber_id diabaikan).
    Owner/Admin: satu barber (barber_id diisi) atau SEMUA barber aktif
    (barber_id kosong) -- panel "Sisa Limit Bulan Ini" di menu Absensi."""
    if user["role"] == "barber":
        if user.get("barber_id") is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
        return attendance_db.hitung_ringkasan_bulan(user["barber_id"], user["tenant_id"], tahun, bulan)
    _cek_akses_lihat(user)
    if barber_id is not None:
        return attendance_db.hitung_ringkasan_bulan(barber_id, user["tenant_id"], tahun, bulan)
    return attendance_db.get_ringkasan_bulan_semua_barber(user["tenant_id"], tahun, bulan)


# ---------------------------------------------------------------------------
# Koreksi Absensi (barber lupa Check In/Check Out) -- pola akses SAMA
# PERSIS routers/izin_cuti.py: self-service (barber ajukan/hapus MILIKNYA
# sendiri selama masih 'pending'), approve/reject wajib
# izin_absensi_koreksi untuk staff (Owner selalu boleh).
# ---------------------------------------------------------------------------

def _cek_akses_koreksi(user: dict, koreksi: dict = None):
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        # Hak Akses Menu: level "Baca" (izin_absensi_lihat) atau tulis
        # (izin_absensi_pengaturan/izin_absensi_koreksi) cukup untuk melihat.
        if not permissions.has_any(
            ["izin_absensi_lihat", "izin_absensi_pengaturan", "izin_absensi_koreksi"],
            tenant_id=user.get("tenant_id"), role_id=user.get("custom_role_id"),
        ):
            raise HTTPException(status_code=403, detail="Admin tidak punya akses ke menu ini. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if koreksi is not None and koreksi["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Tidak bisa melihat pengajuan koreksi milik barber lain.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def _pastikan_koreksi_tenant_sama(user: dict, koreksi: dict | None):
    if koreksi is None or koreksi.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Pengajuan koreksi tidak ditemukan.")


@router.get("/koreksi")
def list_koreksi(barber_id: int = None, status: str = None, user: dict = Depends(get_current_user)):
    _cek_akses_koreksi(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return attendance_db.get_koreksi_list(user["tenant_id"], barber_id=barber_id, status=status)


@router.get("/koreksi/pending-count")
def koreksi_pending_count(user: dict = Depends(get_current_user)):
    """Badge notifikasi menu Absensi -- HANYA admin/staff yang berkepentingan."""
    if user["role"] in ("admin", "staff"):
        return {"jumlah": attendance_db.get_jumlah_koreksi_pending(user["tenant_id"])}
    return {"jumlah": 0}


class KoreksiBody(BaseModel):
    barber_id: int | None = None  # diabaikan untuk role barber, wajib untuk admin/staff
    tanggal: str
    jenis: str
    waktu_diajukan: str
    alasan: str


@router.post("/koreksi")
def buat_koreksi(body: KoreksiBody, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        if user.get("barber_id") is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
        barber_id = user["barber_id"]
    elif user["role"] in ("admin", "staff"):
        if body.barber_id is None:
            raise HTTPException(status_code=422, detail="barber_id wajib diisi.")
        barber_id = body.barber_id
    else:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        return attendance_db.buat_pengajuan_koreksi(
            barber_id, body.tanggal, body.jenis, body.waktu_diajukan, body.alasan,
            diajukan_oleh=user["username"], tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/koreksi/{koreksi_id}")
def hapus_koreksi(koreksi_id: int, user: dict = Depends(get_current_user)):
    koreksi = attendance_db.get_koreksi(koreksi_id)
    _pastikan_koreksi_tenant_sama(user, koreksi)
    if user["role"] == "barber" and koreksi["barber_id"] != user.get("barber_id"):
        raise HTTPException(status_code=403, detail="Bukan pengajuan milik Anda.")
    elif user["role"] not in ("admin", "staff", "barber"):
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        attendance_db.hapus_pengajuan_koreksi(koreksi_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


class KoreksiStatusBody(BaseModel):
    status: str
    catatan_approval: str = ""


@router.put("/koreksi/{koreksi_id}/status")
def ubah_status_koreksi(koreksi_id: int, body: KoreksiStatusBody,
                         user: dict = Depends(require_permission("izin_absensi_koreksi"))):
    _pastikan_koreksi_tenant_sama(user, attendance_db.get_koreksi(koreksi_id))
    try:
        hasil = attendance_db.set_status_koreksi(koreksi_id, body.status,
                                                  catatan_approval=body.catatan_approval,
                                                  disetujui_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if body.status == "disetujui":
        # PERMINTAAN OWNER: attendance_logs untuk tanggal ini SEKARANG
        # sudah terisi (koreksi barusan) -- kalau Auto-Libur SUDAH
        # TERLANJUR memproses tanggal itu sebelumnya (barber tidak pernah
        # check-in saat itu diproses), catatan Libur/Cuti otomatisnya
        # DIBATALKAN di sini supaya tidak dobel dengan absen yang baru
        # dikoreksi -- kuota yang sempat terpakai otomatis kembali (lihat
        # auto_libur_db.batalkan_auto_libur_untuk_tanggal()).
        hasil["auto_libur_dibatalkan"] = auto_libur_db.batalkan_auto_libur_untuk_tanggal(
            hasil["barber_id"], hasil["tanggal"])
    return hasil


@router.get("/{log_id}")
def detail_absensi(log_id: int, user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    log = attendance_db.get_log(log_id)
    if log is None or log.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data absensi tidak ditemukan.")
    return log
