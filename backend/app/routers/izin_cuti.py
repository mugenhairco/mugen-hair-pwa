"""routers/izin_cuti.py — /api/izin-cuti/* (Modul Karyawan, Fase 5)
=============================================================================
Pola akses SAMA PERSIS dengan routers/reimburse.py (self-service): barber
boleh mengajukan/melihat/mengedit/menghapus pengajuan MILIKNYA SENDIRI
(selama masih 'pending') tanpa perlu permission apa pun. Approve/Reject
TETAP eksklusif admin/staff(izin_cuti_karyawan)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import auto_libur_db
import database as db
import izin_cuti_db
import laporan_pdf
import permissions
from auth import get_current_user, require_feature, require_permission


router = APIRouter(prefix="/api/izin-cuti", tags=["izin-cuti"])


def _cek_akses_lihat(user: dict, pengajuan: dict = None):
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        # Hak Akses Menu: level "Baca" (izin_cuti_karyawan_lihat) cukup untuk
        # melihat -- izin_cuti_karyawan (write) tetap otomatis meloloskan juga.
        if not permissions.has_any(["izin_cuti_karyawan_lihat", "izin_cuti_karyawan"],
                                    tenant_id=user.get("tenant_id"), role_id=user.get("custom_role_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Izin & Cuti. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if pengajuan is not None and pengajuan["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Tidak bisa melihat pengajuan milik barber lain.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def _pastikan_pemilik_atau_admin(user: dict, pengajuan: dict):
    if user["role"] == "admin":
        return
    if user["role"] == "staff":
        if not permissions.has("izin_cuti_karyawan", tenant_id=user.get("tenant_id"), role_id=user.get("custom_role_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Izin & Cuti. Hubungi Owner.")
        return
    if user["role"] == "barber":
        if pengajuan["barber_id"] != user.get("barber_id"):
            raise HTTPException(status_code=403, detail="Bukan pengajuan milik Anda.")
        return
    raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def _pastikan_pengajuan_tenant_sama(user: dict, pengajuan: dict | None):
    """FONDASI Multi-Tenant Phase 1.1: fetch-then-authorize -- 404 (bukan
    403) supaya tidak membocorkan bahwa pengajuan_id itu sebenarnya ada,
    milik tenant lain."""
    if pengajuan is None or pengajuan.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Pengajuan tidak ditemukan.")


@router.get("")
def list_pengajuan(barber_id: int = None, status: str = None, jenis: str = None,
                    tahun: int = None, bulan: int = None, user: dict = Depends(get_current_user)):
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    return izin_cuti_db.get_pengajuan_list(barber_id=barber_id, status=status, jenis=jenis,
                                            tahun=tahun, bulan=bulan, tenant_id=user["tenant_id"])


@router.get("/pdf")
def list_pengajuan_pdf(barber_id: int = None, status: str = None, jenis: str = None,
                        user: dict = Depends(get_current_user), _fitur: dict = Depends(require_feature("export_pdf"))):
    """Route ini didaftarkan SEBELUM /{pengajuan_id} supaya 'pdf' tidak
    ditangkap sebagai path parameter pengajuan_id."""
    _cek_akses_lihat(user)
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    konten = laporan_pdf.buat_pdf_izin_cuti_list(barber_id, jenis, status, user["username"],
                                                  tenant_id=user["tenant_id"])
    filename = laporan_pdf.buat_nama_file("izin_cuti")
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/pending-count")
def pending_count(user: dict = Depends(get_current_user)):
    """Badge notifikasi sidebar -- HANYA admin/staff (izin_cuti_karyawan)
    yang berkepentingan, barber selalu dapat 0 (tidak ditampilkan di UI)."""
    if user["role"] == "admin" or (user["role"] == "staff" and
                                    permissions.has_any(["izin_cuti_karyawan_lihat", "izin_cuti_karyawan"],
                                                         tenant_id=user.get("tenant_id"), role_id=user.get("custom_role_id"))):
        return {"jumlah": izin_cuti_db.get_jumlah_pending(tenant_id=user["tenant_id"])}
    return {"jumlah": 0}


@router.get("/marquee")
def info_cuti_marquee(user: dict = Depends(get_current_user)):
    """Route ini didaftarkan SEBELUM /{pengajuan_id} supaya 'marquee' tidak
    ditangkap sebagai path parameter pengajuan_id. Info ringkas cuti
    aktif/akan datang (nama barber + tanggal, TANPA alasan) untuk running
    text Absensi Barber -- lihat izin_cuti_db.py::get_info_cuti_marquee().
    Dibuka untuk SEMUA role tenant (bukan cuma barber) karena datanya
    sendiri sudah minimal & tidak sensitif -- role mana yang MENAMPILKANNYA
    di UI murni keputusan frontend (absensi.js), bukan di sini."""
    return izin_cuti_db.get_info_cuti_marquee(user["tenant_id"])


class CutiSettingsBody(BaseModel):
    kuota_periode_bulan: int | None = None
    kuota_boleh_dipecah: bool | None = None
    h_min_pengajuan: int | None = None
    maksimal_bersamaan: int | None = None
    periode_mulai_dasar: str | None = None
    # PERBAIKAN Sistem Kuota IZIN & CUTI (permintaan Owner): SATU saldo
    # kuota bersama Izin+Cuti (bukan kuota terpisah per jenis) -- lihat
    # izin_cuti_db.py::DEFAULT_CUTI_SETTINGS/_validasi_kebijakan_pengajuan().
    # `mode_kuota`/`kuota_maksimal_hari`/`kuota_izin_hari`/
    # `h_min_pengajuan_izin` SENGAJA TIDAK diterima lagi dari sini (model
    # 'terpisah' dihapus, mode_kuota dipaksa 'gabungan' di set_cuti_settings()).
    kuota_gabungan_hari: int | None = None
    # PERMINTAAN OWNER: barber yang tidak check-in pada hari kerja otomatis
    # direkap jadi cuti & mengurangi kuota -- default OFF, lihat auto_libur_db.py.
    auto_libur_tidak_absen_aktif: bool | None = None
    # KOREKSI Owner: jatah "Kuota Libur/bulan" utk Auto-Libur, dipakai LEBIH
    # DULU sebelum kuota_gabungan_hari di atas -- 0 = tidak dipakai.
    kuota_libur_bulanan: int | None = None


@router.get("/pengaturan")
def ambil_cuti_settings(user: dict = Depends(require_permission("izin_cuti_karyawan"))):
    """Route ini didaftarkan SEBELUM /{pengajuan_id} supaya 'pengaturan'
    tidak ditangkap sebagai path parameter pengajuan_id. Permission SAMA
    persis approve/reject (izin_cuti_karyawan) -- pengaturan kebijakan
    HANYA relevan bagi yang juga bisa memproses pengajuan."""
    return izin_cuti_db.get_cuti_settings(user["tenant_id"])


@router.put("/pengaturan")
def ubah_cuti_settings(body: CutiSettingsBody, user: dict = Depends(require_permission("izin_cuti_karyawan"))):
    try:
        return izin_cuti_db.set_cuti_settings(user["tenant_id"], **body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/saldo")
def ambil_sisa_kuota(barber_id: int = None, user: dict = Depends(get_current_user)):
    """Route ini didaftarkan SEBELUM /{pengajuan_id} supaya 'saldo' tidak
    ditangkap sebagai path parameter pengajuan_id. Sisa kuota periode AKTIF
    saat ini (SATU saldo bersama Izin+Cuti) + Sisa Kuota Libur bulan
    berjalan (field `libur`, KOREKSI Owner -- lihat auto_libur_db.py::
    get_sisa_kuota_libur_bulan_ini(), reset per bulan kalender, TIDAK ikut
    periode Izin&Cuti) -- barber HANYA boleh lihat miliknya sendiri,
    admin/staff (_cek_akses_lihat) boleh lihat siapa pun lewat `barber_id`."""
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
        if barber_id is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
    else:
        _cek_akses_lihat(user)
        if barber_id is None:
            raise HTTPException(status_code=422, detail="barber_id wajib diisi.")
    hasil = izin_cuti_db.get_sisa_kuota(barber_id, user["tenant_id"])
    hasil["libur"] = auto_libur_db.get_sisa_kuota_libur_bulan_ini(barber_id, user["tenant_id"])
    return hasil


@router.get("/saldo-semua-barber")
def ambil_sisa_kuota_semua_barber(user: dict = Depends(get_current_user)):
    """Route ini didaftarkan SEBELUM /{pengajuan_id} supaya 'saldo-semua-
    barber' tidak ditangkap sebagai path parameter pengajuan_id. KOREKSI
    Owner: tabel ringkasan Sisa Kuota (Izin&Cuti + Libur) SEMUA barber
    sekaligus untuk Absensi > Owner -- pola SAMA seperti /marquee (dipakai
    lintas-halaman oleh absensi.js), HANYA admin/staff (_cek_akses_lihat),
    barber tidak perlu endpoint ini (sudah pakai /saldo miliknya sendiri).
    `kuota_habis`=True kalau ADA tanggal bulan ini yang Kuota Libur DAN
    kuota gabungan Izin&Cuti SAMA-SAMA sudah habis (lihat auto_libur_db.py::
    ada_kelebihan_kuota_bulan_ini(), sama seperti Rekap Bulanan)."""
    if user["role"] == "barber":
        # Endpoint ini mengembalikan data SEMUA barber -- BEDA dari
        # _cek_akses_lihat() biasa (yang meloloskan barber tanpa syarat
        # kalau tidak ada `pengajuan` spesifik yang dicek). Barber TIDAK
        # boleh lihat kuota siapa pun selain dirinya sendiri (sudah pakai
        # /saldo tanpa barber_id untuk itu).
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    _cek_akses_lihat(user)
    hasil = []
    for barber in db.get_barbers(tenant_id=user["tenant_id"]):
        saldo = izin_cuti_db.get_sisa_kuota(barber["id"], user["tenant_id"])
        saldo["libur"] = auto_libur_db.get_sisa_kuota_libur_bulan_ini(barber["id"], user["tenant_id"])
        saldo["barber_id"] = barber["id"]
        saldo["nama_barber"] = barber["nama"]
        saldo["kuota_habis"] = auto_libur_db.ada_kelebihan_kuota_bulan_ini_sekarang(barber["id"])
        hasil.append(saldo)
    return hasil


@router.get("/saldo-awal")
def ambil_saldo_awal(barber_id: int = None, user: dict = Depends(get_current_user)):
    """Route ini didaftarkan SEBELUM /{pengajuan_id} supaya 'saldo-awal'
    tidak ditangkap sebagai path parameter pengajuan_id. Snapshot HISTORIS
    saldo cuti per titik cut-off (mis. migrasi Agustus 2026, lihat
    izin_cuti_migrasi.py) -- murni catatan/tampilan, TIDAK dihitung mesin
    kuota dinamis. Sama seperti /saldo: barber HANYA boleh lihat miliknya
    sendiri, admin/staff boleh lihat siapa pun (atau semua kalau barber_id
    dikosongkan)."""
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
        if barber_id is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
    else:
        _cek_akses_lihat(user)
    return izin_cuti_db.get_saldo_awal(user["tenant_id"], barber_id=barber_id)


class AutoLiburBody(BaseModel):
    tahun: int
    bulan: int


@router.post("/auto-libur/proses")
def proses_auto_libur(body: AutoLiburBody, user: dict = Depends(require_permission("izin_cuti_karyawan"))):
    """Route ini didaftarkan SEBELUM /{pengajuan_id} supaya 'auto-libur'
    tidak ditangkap sebagai path parameter pengajuan_id. Pemicu MANUAL
    (TIDAK ADA scheduler di proyek ini, lihat auto_libur_db.py) -- Owner/
    staff (izin_cuti_karyawan) memproses satu bulan tertentu, dipanggil
    kapan saja/berkali-kali dengan aman (idempotent)."""
    try:
        return auto_libur_db.proses_auto_libur(user["tenant_id"], body.tahun, body.bulan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{pengajuan_id}")
def ambil_pengajuan(pengajuan_id: int, user: dict = Depends(get_current_user)):
    pengajuan = izin_cuti_db.get_pengajuan(pengajuan_id)
    _pastikan_pengajuan_tenant_sama(user, pengajuan)
    _cek_akses_lihat(user, pengajuan)
    return pengajuan


class PengajuanBody(BaseModel):
    barber_id: int | None = None  # diabaikan untuk role barber, wajib untuk role admin/staff
    jenis: str
    tanggal_mulai: str
    tanggal_selesai: str
    alasan: str


@router.post("")
def buat_pengajuan(body: PengajuanBody, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        if user.get("barber_id") is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
        barber_id = user["barber_id"]
    elif user["role"] in ("admin", "staff"):
        if user["role"] == "staff" and not permissions.has("izin_cuti_karyawan", tenant_id=user.get("tenant_id"), role_id=user.get("custom_role_id")):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk Izin & Cuti. Hubungi Owner.")
        if body.barber_id is None:
            raise HTTPException(status_code=422, detail="barber_id wajib diisi.")
        barber_id = body.barber_id
    else:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        # FITUR Kebijakan Cuti Dinamis: Owner/Admin/Staff SELALU boleh
        # melewati kebijakan (H-min/kuota/maksimal bersamaan) saat membuat
        # pengajuan ATAS NAMA barber -- HANYA barber sendiri (self-service)
        # yang tunduk penuh (lihat izin_cuti_db.py::_validasi_kebijakan_cuti()).
        return izin_cuti_db.buat_pengajuan(barber_id, body.jenis, body.tanggal_mulai, body.tanggal_selesai,
                                            body.alasan, diajukan_oleh=user["username"],
                                            tenant_id=user["tenant_id"], override=user["role"] != "barber")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class PengajuanEditBody(BaseModel):
    jenis: str | None = None
    tanggal_mulai: str | None = None
    tanggal_selesai: str | None = None
    alasan: str | None = None


@router.put("/{pengajuan_id}")
def edit_pengajuan(pengajuan_id: int, body: PengajuanEditBody, user: dict = Depends(get_current_user)):
    pengajuan = izin_cuti_db.get_pengajuan(pengajuan_id)
    _pastikan_pengajuan_tenant_sama(user, pengajuan)
    _pastikan_pemilik_atau_admin(user, pengajuan)
    try:
        return izin_cuti_db.edit_pengajuan(pengajuan_id, jenis=body.jenis, tanggal_mulai=body.tanggal_mulai,
                                            tanggal_selesai=body.tanggal_selesai, alasan=body.alasan,
                                            override=user["role"] != "barber")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{pengajuan_id}")
def hapus_pengajuan(pengajuan_id: int, user: dict = Depends(get_current_user)):
    pengajuan = izin_cuti_db.get_pengajuan(pengajuan_id)
    _pastikan_pengajuan_tenant_sama(user, pengajuan)
    _pastikan_pemilik_atau_admin(user, pengajuan)
    try:
        izin_cuti_db.hapus_pengajuan(pengajuan_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


class StatusBody(BaseModel):
    status: str
    catatan_approval: str = ""


@router.put("/{pengajuan_id}/status")
def ubah_status_pengajuan(pengajuan_id: int, body: StatusBody,
                           user: dict = Depends(require_permission("izin_cuti_karyawan"))):
    _pastikan_pengajuan_tenant_sama(user, izin_cuti_db.get_pengajuan(pengajuan_id))
    try:
        return izin_cuti_db.set_status_pengajuan(pengajuan_id, body.status,
                                                  catatan_approval=body.catatan_approval,
                                                  disetujui_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
