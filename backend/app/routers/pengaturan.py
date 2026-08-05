"""routers/pengaturan.py — /api/pengaturan/*  (TAHAP 10)
Router khusus untuk menu Setting, terpisah dari router lain. Semua endpoint
KHUSUS admin (require_admin), KECUALI:
- GET /identitas dan GET /logo: sengaja PUBLIC (tanpa login) karena halaman
  Login (belum ada token) juga perlu menampilkan nama & logo barbershop.
  Isinya bukan data sensitif (nama toko, alamat, kontak publik, logo),
  sama seperti info yang biasa terpampang di depan toko.

Tahap 10 TIDAK mengubah Dashboard/Login-flow/Input Data/Rekap/Pengeluaran/
Produk/Perhitungan Komisi/struktur API yang sudah ada — router ini murni
tambahan baru di path /api/pengaturan/*."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

import auth_db
import billing_limits
import branding_db
import database as db
import db_compat
import email_auth_db
import email_service
import email_templates
import laporan_pdf
import pengaturan_barber
import pengaturan_backup
import pengaturan_bonus
import pengaturan_identitas
import pengaturan_service
import pengaturan_user
import permissions
import r2_storage
from auth import require_admin, require_feature, require_owner_or_staff, require_permission, resolve_tenant_hibrid

router = APIRouter(prefix="/api/pengaturan", tags=["pengaturan"])


def _cek_target_barber_untuk_staff(user: dict, target: dict, aksi: str):
    """'staff' (Admin) HANYA boleh menyasar user ber-role 'barber' -- tidak
    pernah 'admin' (Owner) maupun 'staff' lain, apa pun izin yang diberikan
    Owner (izin di Setting > Hak Akses Admin hanya mengatur AKSI-nya, bukan
    menaikkan siapa yang boleh disasar). 'admin' (Owner) tidak dibatasi di
    sini -- aturan Owner-terakhir tetap berlaku terpisah, lihat
    _cek_bukan_owner_terakhir."""
    if user["role"] == "staff" and target["role"] != "barber":
        raise HTTPException(status_code=403, detail=f"Admin hanya boleh {aksi} akun ber-role Barber.")


def _cek_bukan_owner_terakhir(target: dict):
    """Berlaku untuk SIAPA PUN pemanggilnya (termasuk Owner) -- minimal
    harus selalu ada satu akun Owner aktif DI TENANT YANG SAMA (lihat
    catatan tenant_id di auth_db.hitung_owner_aktif())."""
    if target["role"] == "admin" and auth_db.hitung_owner_aktif(target.get("tenant_id")) <= 1:
        raise HTTPException(status_code=403,
                             detail="Tidak bisa menonaktifkan Owner terakhir. Minimal harus ada satu akun Owner aktif.")

# Key setting yang boleh diubah lewat menu "Pengaturan Komisi" (semuanya
# SUDAH ADA di database.DEFAULT_SETTINGS sejak Tahap 2 — router ini cuma
# membuka jalan untuk mengedit, TIDAK menambah/mengubah rumus apapun).
# REVISI: uang_harian_barber/uang_harian_rafiq dipindah jadi per-barber
# (lihat endpoint /barber di bawah); bonus_kehadiran/maksimal_hari_libur
# dihapus total (fitur Bonus Kehadiran dihapus); target_bonus_customer/
# nominal_bonus_customer diganti daftar tier bertingkat (lihat endpoint
# /bonus-tiers di bawah) — semua itu TIDAK ADA lagi di sini.
# REVISI Struktur Setting: potongan_modal_chemical DIHAPUS dari sini --
# digantikan Harga Modal PER-SERVICE (kolom services.modal, lihat endpoint
# /service di bawah dan hitung_komisi_service di database.py). Nilai lama
# setting ini TETAP tersimpan di tabel settings (tidak dihapus), hanya
# tidak lagi dipakai/diedit lewat sini.
KOMISI_KEYS = [
    "persentase_komisi",
    "maksimal_hari_libur_bonus_customer", "potongan_bonus_customer_persen",
]


# ================= IDENTITAS BARBERSHOP =================

class IdentitasBody(BaseModel):
    nama_barbershop: str
    email: str = ""


@router.get("/identitas")
def ambil_identitas(tenant_id: int = Depends(resolve_tenant_hibrid)):
    # FONDASI Multi-Tenant Phase 1: endpoint ini SENGAJA PUBLIC (lihat
    # docstring router di atas -- halaman Login belum ada token). Tenant
    # diresolve lewat query string opsional `?tenant=<slug>` (lihat
    # auth.resolve_tenant_publik()) -- SAMA seperti mekanisme booking publik
    # (Tahap 32). Kosong = tenant default, perilaku LAMA tidak berubah.
    # Mekanisme berbasis subdomain (halaman Login TIDAK bisa membaca query
    # string sebelum tahu URL-nya sendiri sama sekali) ada di luar cakupan
    # Phase 1 -- lihat roadmap audit Fase 2.
    return pengaturan_identitas.get_identitas(tenant_id=tenant_id)


@router.put("/identitas")
def simpan_identitas(body: IdentitasBody, user: dict = Depends(require_permission("izin_setting_identitas"))):
    try:
        pengaturan_identitas.update_identitas(body.model_dump(), tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return pengaturan_identitas.get_identitas(tenant_id=user["tenant_id"])


@router.post("/logo")
async def upload_logo(file: UploadFile = File(...), user: dict = Depends(require_permission("izin_setting_branding"))):
    # BOOKING UI/UX #1: tab Setting > Identitas Barbershop (yang dulu satu-
    # satunya pemanggil endpoint ini lewat PUT /identitas) sudah dihapus --
    # tab Branding sekarang satu-satunya jalur upload logo, jadi izin yang
    # dicek di sini diikutkan ke izin_setting_branding (bukan
    # izin_setting_identitas lagi, yang sudah tidak bisa diberikan Owner ke
    # Admin lewat UI Hak Akses Admin manapun).
    konten = await file.read()
    try:
        pengaturan_identitas.simpan_logo(file.filename, konten, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return pengaturan_identitas.get_identitas(tenant_id=user["tenant_id"])


@router.get("/logo")
def ambil_logo(v: str | None = None, tenant_id: int = Depends(resolve_tenant_hibrid)):
    # FONDASI Multi-Tenant Phase 1: sama seperti GET /identitas di atas.
    data, content_type = pengaturan_identitas.get_logo_data(tenant_id=tenant_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Logo belum diatur.")
    return Response(content=data, media_type=content_type)


# ================= BRANDING (Phase 2.2: Tenant & Platform Branding) =================
# Field GABUNGAN dari Identitas (nama_barbershop, email) + Website Content
# (tagline, alamat, whatsapp) + field BARU milik branding_db.py sendiri
# (primary_color, secondary_color, website_url, favicon) -- lihat docstring
# branding_db.py untuk kenapa TIDAK diduplikasi/dipindah dari modul asalnya.
# GET publik ada di routers/branding.py (/api/tenant/branding, dipakai
# halaman Login juga) -- di sini HANYA endpoint TULIS + serve file favicon.

class BrandingBody(BaseModel):
    nama_barbershop: str | None = None
    email: str | None = None
    tagline: str | None = None
    alamat: str | None = None
    whatsapp: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    website_url: str | None = None


@router.put("/branding")
def simpan_branding(body: BrandingBody, user: dict = Depends(require_permission("izin_setting_branding"))):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        branding_db.update_branding(data, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return branding_db.get_branding(tenant_id=user["tenant_id"])


@router.post("/favicon")
async def upload_favicon(file: UploadFile = File(...), user: dict = Depends(require_permission("izin_setting_branding"))):
    konten = await file.read()
    try:
        branding_db.simpan_favicon(file.filename, konten, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return branding_db.get_branding(tenant_id=user["tenant_id"])


@router.delete("/favicon")
def hapus_favicon(user: dict = Depends(require_permission("izin_setting_branding"))):
    """Kembali ke favicon platform (fallback statis di index.html/manifest.json)
    -- lihat routers/branding.py: favicon_url None ditafsirkan SAMA baik
    untuk "belum pernah upload" maupun "sengaja dihapus"."""
    branding_db.hapus_favicon(tenant_id=user["tenant_id"])
    return branding_db.get_branding(tenant_id=user["tenant_id"])


@router.get("/favicon")
def ambil_favicon(v: str | None = None, tenant_id: int = Depends(resolve_tenant_hibrid)):
    # FONDASI Multi-Tenant Phase 2.2: PUBLIC sama seperti GET /logo -- favicon
    # sendiri bukan data sensitif, dan browser butuh mengambilnya tanpa token
    # (tag <link rel="icon">, lihat frontend/js/brand.js).
    data, content_type = branding_db.get_favicon_data(tenant_id=tenant_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Favicon belum diatur.")
    return Response(content=data, media_type=content_type)


# ================= PENGATURAN KOMISI & BONUS =================

class KomisiBody(BaseModel):
    persentase_komisi: float
    maksimal_hari_libur_bonus_customer: float
    potongan_bonus_customer_persen: float


@router.get("/komisi")
def ambil_komisi(user: dict = Depends(require_admin)):
    semua = db.get_all_settings(tenant_id=user["tenant_id"])
    return {k: semua.get(k) for k in KOMISI_KEYS}


@router.put("/komisi")
def simpan_komisi(body: KomisiBody, user: dict = Depends(require_admin)):
    data = body.model_dump()
    for k, v in data.items():
        if v < 0:
            raise HTTPException(status_code=422, detail=f"{k} tidak boleh negatif.")
    db.set_settings_bulk(data, tenant_id=user["tenant_id"])
    semua = db.get_all_settings(tenant_id=user["tenant_id"])
    return {k: semua.get(k) for k in KOMISI_KEYS}


# ================= TARGET BONUS SERVICE (tier bertingkat) — REVISI =================
# Sebelumnya cuma satu target/nominal (di /komisi) -- diganti daftar tier
# bertingkat (mis. 100 service -> Rp100.000, 115 service -> Rp150.000, dst),
# supaya admin bisa tambah/ubah/hapus target sebebas mungkin tanpa hardcode.

class BonusTierBody(BaseModel):
    target: int
    bonus: int


class BonusTierUpdateBody(BaseModel):
    target: int
    bonus: int


@router.get("/bonus-tiers")
def list_bonus_tiers(user: dict = Depends(require_admin)):
    return db.get_bonus_customer_tiers(tenant_id=user["tenant_id"])


@router.post("/bonus-tiers")
def tambah_bonus_tier(body: BonusTierBody, user: dict = Depends(require_admin)):
    try:
        return pengaturan_bonus.tambah_tier(body.target, body.bonus, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/bonus-tiers/{target}")
def ubah_bonus_tier(target: int, body: BonusTierUpdateBody, user: dict = Depends(require_admin)):
    try:
        return pengaturan_bonus.ubah_tier(target, body.target, body.bonus, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/bonus-tiers/{target}")
def hapus_bonus_tier(target: int, user: dict = Depends(require_admin)):
    try:
        return pengaturan_bonus.hapus_tier(target, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ================= REVISI: SETTING BONUS SERVICE & SETTING UANG HARIAN =================
# Menggantikan hardcode lama (konstanta SERVICE_UANG_HARIAN di database.py,
# selalu "Dry Cut" + "Cut & Wash") -- Owner sekarang memilih SENDIRI service
# mana saja yang jadi acuan Target Bonus Service (tier bulanan) dan service
# mana saja yang jadi acuan syarat cair Uang Harian (>= 3/hari). Keduanya
# pengaturan INDEPENDEN (lihat database.py bagian "ACUAN SERVICE").

class AcuanServiceBody(BaseModel):
    service_ids: list[int]


@router.get("/bonus-service-acuan")
def ambil_bonus_service_acuan(user: dict = Depends(require_admin)):
    return {"service_ids": db.get_bonus_service_acuan_ids(tenant_id=user["tenant_id"])}


@router.put("/bonus-service-acuan")
def simpan_bonus_service_acuan(body: AcuanServiceBody, user: dict = Depends(require_admin)):
    db.set_bonus_service_acuan_ids(body.service_ids, tenant_id=user["tenant_id"])
    return {"service_ids": db.get_bonus_service_acuan_ids(tenant_id=user["tenant_id"])}


@router.get("/uang-harian-acuan")
def ambil_uang_harian_acuan(user: dict = Depends(require_admin)):
    return {"service_ids": db.get_uang_harian_acuan_ids(tenant_id=user["tenant_id"])}


@router.put("/uang-harian-acuan")
def simpan_uang_harian_acuan(body: AcuanServiceBody, user: dict = Depends(require_admin)):
    db.set_uang_harian_acuan_ids(body.service_ids, tenant_id=user["tenant_id"])
    return {"service_ids": db.get_uang_harian_acuan_ids(tenant_id=user["tenant_id"])}


# REVISI Struktur Setting: target jumlah service/hari supaya Uang Harian cair
# sekarang bisa diatur bebas Owner (dulu hardcode 3, lihat
# revisi_setting_migrasi.py untuk migrasi default-nya & database.py
# target_uang_harian_per_hari() untuk pemakaiannya).
class UangHarianTargetBody(BaseModel):
    target: int


@router.get("/uang-harian-target")
def ambil_uang_harian_target(user: dict = Depends(require_admin)):
    return {"target": db.target_uang_harian_per_hari(tenant_id=user["tenant_id"])}


@router.put("/uang-harian-target")
def simpan_uang_harian_target(body: UangHarianTargetBody, user: dict = Depends(require_admin)):
    if body.target <= 0:
        raise HTTPException(status_code=422, detail="Target harus lebih dari 0.")
    db.set_setting("uang_harian_target_service_harian", body.target, tenant_id=user["tenant_id"])
    return {"target": db.target_uang_harian_per_hari(tenant_id=user["tenant_id"])}


# ================= MANAJEMEN KARYAWAN (Barber + Kasir/OB/Kru) =================
# Tabel `barbers` digeneralisasi lewat kolom `jabatan` (lihat
# karyawan_migrasi.py) -- endpoint di sini KHUSUS Setting, jadi WAJIB
# menampilkan SEMUA jabatan (db.get_karyawan(), bukan db.get_barbers()
# yang otomatis ter-filter jabatan='barber' untuk pemanggil lain).

class BarberBody(BaseModel):
    nama: str
    is_rafiq: bool = False
    uang_harian: int = 0
    jabatan: str = "barber"
    gaji_per_hari: int = 0


class BarberUpdateBody(BaseModel):
    nama: str | None = None
    is_rafiq: bool | None = None
    aktif: bool | None = None
    uang_harian: int | None = None
    jabatan: str | None = None
    gaji_per_hari: int | None = None


def _tanpa_kolom_biner(barber: dict | None) -> dict | None:
    """db.get_barber()/db.get_karyawan() lewat SELECT * -- ikut membawa
    kolom biner (foto_data BLOB, sejak Tahap 16) yang TIDAK bisa
    di-serialize jadi JSON (bug laten yang ditemukan saat audit migrasi R2:
    endpoint di bawah akan crash 500 begitu ada barber yang punya foto
    tersimpan -- murni bug pre-existing, tidak terkait R2, tapi baru
    kelihatan sekarang karena baru diuji end-to-end dengan foto sungguhan).
    Dibuang di sini SEBELUM dikembalikan ke client -- frontend Setting >
    Barber tidak pernah membaca foto_data/foto_r2_key dari respons endpoint
    ini (foto ditampilkan lewat foto_url dari endpoint Booking)."""
    if barber:
        barber.pop("foto_data", None)
        barber.pop("foto_r2_key", None)
    return barber


def _pastikan_barber_tenant_sama(user: dict, target: dict | None):
    """FONDASI Multi-Tenant Phase 1: sama seperti _pastikan_target_tenant_sama
    (lihat penjelasan di sana), versi untuk endpoint /barber/{id} -- 404
    dipakai supaya tidak membocorkan "barber ini ADA tapi milik tenant lain"."""
    if target is None or target.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan.")


@router.get("/barber")
def list_barber(user: dict = Depends(require_admin)):
    # tampilkan semua jabatan, aktif & nonaktif, di halaman Setting
    return [_tanpa_kolom_biner(b) for b in db.get_karyawan(hanya_aktif=False, tenant_id=user["tenant_id"])]


@router.post("/barber")
def tambah_barber(body: BarberBody, user: dict = Depends(require_admin)):
    try:
        billing_limits.pastikan_boleh_tambah_barber(user["tenant_id"])  # FONDASI Multi-Tenant Phase 4
        new_id = pengaturan_barber.tambah_barber_validated(
            body.nama, body.is_rafiq, body.uang_harian, jabatan=body.jabatan, gaji_per_hari=body.gaji_per_hari,
            tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _tanpa_kolom_biner(db.get_barber(new_id))


@router.put("/barber/{barber_id}")
def update_barber(barber_id: int, body: BarberUpdateBody, user: dict = Depends(require_admin)):
    _pastikan_barber_tenant_sama(user, db.get_barber(barber_id))
    try:
        pengaturan_barber.update_barber_validated(
            barber_id, nama=body.nama, is_rafiq=body.is_rafiq, aktif=body.aktif,
            uang_harian=body.uang_harian, jabatan=body.jabatan, gaji_per_hari=body.gaji_per_hari,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _tanpa_kolom_biner(db.get_barber(barber_id))


@router.delete("/barber/{barber_id}")
def hapus_barber(barber_id: int, user: dict = Depends(require_admin)):
    _pastikan_barber_tenant_sama(user, db.get_barber(barber_id))
    try:
        pengaturan_barber.hapus_barber(barber_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


# ================= MANAJEMEN LAYANAN =================

class ServiceBody(BaseModel):
    nama: str
    harga: int
    modal: int = 0
    pakai_potongan_chemical: bool | None = None
    durasi_menit: int = 60  # BOOKING: durasi standar (menit) untuk hitung slot jadwal


class ServiceUpdateBody(BaseModel):
    nama: str | None = None
    harga: int | None = None
    modal: int | None = None
    pakai_potongan_chemical: bool | None = None
    aktif: bool | None = None
    durasi_menit: int | None = None


def _pastikan_service_tenant_sama(user: dict, target: dict | None):
    """FONDASI Multi-Tenant Phase 1: sama seperti _pastikan_barber_tenant_sama,
    versi untuk endpoint /service/{id}."""
    if target is None or target.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Layanan tidak ditemukan.")


@router.get("/service")
def list_service(user: dict = Depends(require_admin)):
    return db.get_services(hanya_aktif=False, tenant_id=user["tenant_id"])


@router.post("/service")
def tambah_service(body: ServiceBody, user: dict = Depends(require_admin)):
    try:
        billing_limits.pastikan_boleh_tambah_layanan(user["tenant_id"])  # FONDASI Multi-Tenant Phase 4
        new_id = pengaturan_service.tambah_service_lengkap(
            body.nama, body.harga, body.modal, body.pakai_potongan_chemical, body.durasi_menit,
            tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_service(new_id)


@router.put("/service/{service_id}")
def update_service(service_id: int, body: ServiceUpdateBody, user: dict = Depends(require_admin)):
    _pastikan_service_tenant_sama(user, db.get_service(service_id))
    try:
        pengaturan_service.update_service_lengkap(
            service_id, nama=body.nama, harga=body.harga, modal=body.modal,
            pakai_potongan_chemical=body.pakai_potongan_chemical, aktif=body.aktif,
            durasi_menit=body.durasi_menit,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_service(service_id)


@router.delete("/service/{service_id}")
def hapus_service(service_id: int, user: dict = Depends(require_admin)):
    _pastikan_service_tenant_sama(user, db.get_service(service_id))
    try:
        db.hapus_service(service_id)  # fungsi Tahap 2, sudah menolak kalau pernah dipakai transaksi
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


# ================= MANAJEMEN USER =================

class UserBody(BaseModel):
    username: str
    password: str
    role: str
    barber_id: int | None = None


class UsernameBody(BaseModel):
    username: str


class PasswordBody(BaseModel):
    password: str


def _pastikan_target_tenant_sama(user: dict, target: dict):
    """FONDASI Multi-Tenant Phase 1: satu-satunya penegakan isolasi yang
    dibutuhkan untuk endpoint /user/{id}/* -- semuanya sudah memakai pola
    "ambil dulu baris user targetnya, baru diproses" (fetch-then-authorize),
    jadi cukup SATU pengecekan tambahan di sini per endpoint, bukan
    mengubah query auth_db.get_user() itu sendiri. 404 (bukan 403) sengaja
    dipakai supaya tidak membocorkan informasi "user itu ADA tapi milik
    tenant lain" ke pemanggil."""
    if target.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")


def _pastikan_bukan_akun_dilindungi(target: dict):
    """Akun Super Admin (role='superadmin', tenant_id=NULL -- lihat
    auth_db.tambah_user()) adalah akun PLATFORM, bukan milik tenant mana
    pun -- tidak boleh diubah/dihapus/direset passwordnya lewat endpoint
    /user/* milik satu tenant, walau pemanggil entah bagaimana tahu/
    menebak ID-nya. 403 (BUKAN 404 seperti _pastikan_target_tenant_sama di
    atas) sengaja dipakai di sini -- ini bukan soal isolasi data antar
    tenant (yang memang harus disamarkan jadi "tidak ditemukan"), tapi
    larangan eksplisit terhadap akun yang dilindungi: akun ini ADA, dan
    permintaannya DITOLAK. Dipanggil SEBELUM _pastikan_target_tenant_sama
    supaya percobaan menyasar Super Admin selalu dapat 403, bukan 404."""
    if target["role"] == "superadmin":
        raise HTTPException(status_code=403, detail="Akun ini dilindungi dan tidak bisa diubah dari sini.")


@router.get("/user")
def list_user(user: dict = Depends(require_owner_or_staff)):
    if user["role"] == "staff" and not permissions.has("izin_setting_user", tenant_id=user["tenant_id"]):
        raise HTTPException(status_code=403, detail="Admin tidak punya akses ke tab User.")
    daftar = auth_db.get_user_list(tenant_id=user["tenant_id"])
    for u in daftar:
        u.pop("password_hash", None)  # jangan pernah kirim hash ke frontend
    return daftar


@router.post("/user")
def tambah_user(body: UserBody, user: dict = Depends(require_owner_or_staff)):
    if user["role"] == "staff":
        if not permissions.has("izin_setting_user", tenant_id=user["tenant_id"]) or not permissions.has("izin_user_tambah", tenant_id=user["tenant_id"]):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk membuat user.")
        if body.role != "barber":
            raise HTTPException(status_code=403, detail="Admin hanya boleh membuat user ber-role Barber.")
    if body.barber_id is not None:
        barber_target = db.get_barber(body.barber_id)
        if barber_target is None or barber_target.get("tenant_id") != user["tenant_id"]:
            raise HTTPException(status_code=422, detail="Barber tidak ditemukan.")
    try:
        billing_limits.pastikan_boleh_tambah_user(user["tenant_id"])  # FONDASI Multi-Tenant Phase 4
        new_id = auth_db.tambah_user(body.username, body.password, body.role, body.barber_id,
                                      tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    hasil = auth_db.get_user(new_id)
    hasil.pop("password_hash", None)
    return hasil


# Ganti Username SENGAJA TETAP Owner-murni (require_admin) -- bukan bagian
# dari daftar izin yang bisa diberikan ke Admin (spesifikasi hanya menyebut
# Membuat/Menghapus/Mengubah Password untuk grup "User").
@router.put("/user/{user_id}/username")
def ganti_username(user_id: int, body: UsernameBody, user: dict = Depends(require_admin)):
    target = auth_db.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")
    _pastikan_bukan_akun_dilindungi(target)
    _pastikan_target_tenant_sama(user, target)
    try:
        pengaturan_user.ganti_username(user_id, body.username)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.put("/user/{user_id}/password")
def ganti_password(user_id: int, body: PasswordBody, user: dict = Depends(require_owner_or_staff)):
    target = auth_db.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")
    _pastikan_bukan_akun_dilindungi(target)
    _pastikan_target_tenant_sama(user, target)
    if user["role"] == "staff":
        if not permissions.has("izin_setting_user", tenant_id=user["tenant_id"]) or not permissions.has("izin_user_ganti_password", tenant_id=user["tenant_id"]):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk mengubah password user.")
        _cek_target_barber_untuk_staff(user, target, "mengubah password")
    try:
        auth_db.ganti_password(user_id, body.password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.put("/user/{user_id}/nonaktifkan")
def nonaktifkan_user(user_id: int, user: dict = Depends(require_owner_or_staff)):
    target = auth_db.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")
    _pastikan_bukan_akun_dilindungi(target)
    _pastikan_target_tenant_sama(user, target)
    if user["role"] == "staff":
        if not permissions.has("izin_setting_user", tenant_id=user["tenant_id"]) or not permissions.has("izin_user_hapus", tenant_id=user["tenant_id"]):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk menonaktifkan user.")
        _cek_target_barber_untuk_staff(user, target, "menonaktifkan")
    _cek_bukan_owner_terakhir(target)
    auth_db.nonaktifkan_user(user_id)
    return {"ok": True}


@router.put("/user/{user_id}/aktifkan")
def aktifkan_user(user_id: int, user: dict = Depends(require_owner_or_staff)):
    target = auth_db.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")
    _pastikan_bukan_akun_dilindungi(target)
    _pastikan_target_tenant_sama(user, target)
    if user["role"] == "staff":
        if not permissions.has("izin_setting_user", tenant_id=user["tenant_id"]) or not permissions.has("izin_user_hapus", tenant_id=user["tenant_id"]):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk mengaktifkan user.")
        _cek_target_barber_untuk_staff(user, target, "mengaktifkan")
    try:
        pengaturan_user.aktifkan_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.delete("/user/{user_id}")
def hapus_user(user_id: int, user: dict = Depends(require_owner_or_staff)):
    """Hapus PERMANEN (beda dari Nonaktifkan yang cuma menonaktifkan status
    login) -- dipakai izin `izin_user_hapus` yang sama seperti Nonaktifkan/
    Aktifkan (satu izin "hak kelola status/keberadaan user", bukan izin
    baru terpisah)."""
    target = auth_db.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")
    _pastikan_bukan_akun_dilindungi(target)
    _pastikan_target_tenant_sama(user, target)
    if target["id"] == user["id"]:
        raise HTTPException(status_code=403, detail="Tidak bisa menghapus akun sendiri.")
    if user["role"] == "staff":
        if not permissions.has("izin_setting_user", tenant_id=user["tenant_id"]) or not permissions.has("izin_user_hapus", tenant_id=user["tenant_id"]):
            raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk menghapus user.")
        _cek_target_barber_untuk_staff(user, target, "menghapus")
    if target["role"] == "admin" and auth_db.hitung_owner_aktif(user["tenant_id"]) <= 1:
        raise HTTPException(status_code=403,
                             detail="Tidak bisa menghapus Owner terakhir. Minimal harus ada satu akun Owner aktif.")
    auth_db.hapus_user(user_id)
    return {"ok": True}


# ================= HAK AKSES ADMIN (REVISI) =================
# Menu Setting > Hak Akses Admin, HANYA Owner (require_admin murni, bukan
# require_owner_or_staff -- Admin TIDAK BOLEH mengatur hak aksesnya sendiri
# ataupun Admin lain). Lihat permissions.py untuk daftar lengkap key & default.

class HakAksesAdminBody(BaseModel):
    izin: dict[str, bool]


# GET boleh dibaca 'staff' JUGA (bukan hanya Owner) -- staff perlu tahu hak
# aksesnya sendiri supaya frontend-nya bisa menampilkan tab/aksi yang sesuai
# (lihat pages/pengaturan.js). Mengubahnya (PUT di bawah) TETAP Owner-murni.
@router.get("/hak-akses-admin")
def ambil_hak_akses_admin(user: dict = Depends(require_owner_or_staff)):
    return permissions.get_all(tenant_id=user["tenant_id"])


@router.put("/hak-akses-admin")
def simpan_hak_akses_admin(body: HakAksesAdminBody, user: dict = Depends(require_admin)):
    try:
        return permissions.set_bulk(body.izin, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ================= BACKUP DATABASE =================

def _cek_izin_backup(user: dict, key: str, aksi: str):
    if user["role"] == "staff":
        if not permissions.has("izin_setting_backup", tenant_id=user["tenant_id"]) or not permissions.has(key, tenant_id=user["tenant_id"]):
            raise HTTPException(status_code=403, detail=f"Admin tidak punya izin untuk {aksi} database.")


def _tolak_backup_sqlite_multi_tenant():
    """FONDASI Multi-Tenant Phase 1.1: jalur SQLite meng-copy FILE UTUH
    (tidak ada cara mem-filter sebagian baris), jadi HANYA aman kalau
    instalasi ini benar-benar cuma punya satu tenant -- lihat penjelasan
    lengkap di docstring pengaturan_backup.py."""
    if pengaturan_backup.sqlite_punya_lebih_dari_satu_tenant():
        raise HTTPException(
            status_code=409,
            detail="Export/Import Database (file .db utuh) tidak tersedia karena instalasi ini "
                   "sudah punya lebih dari satu toko (tenant) -- file .db tidak bisa difilter per "
                   "toko. Hubungi penyedia layanan untuk migrasi ke PostgreSQL, yang mendukung "
                   "Export/Import per toko.",
        )


@router.get("/backup/export")
def export_database(user: dict = Depends(require_owner_or_staff)):
    _cek_izin_backup(user, "izin_backup_export", "export")
    if db_compat.IS_POSTGRES:
        konten = pengaturan_backup.export_database_postgres(user["tenant_id"])
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return Response(
            content=konten, media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="mugen_hair_backup_{stamp}.json"'},
        )
    _tolak_backup_sqlite_multi_tenant()
    return FileResponse(db.DB_PATH, media_type="application/octet-stream",
                         filename="mugen_hair_backup.db")


@router.post("/backup/import")
async def import_database(file: UploadFile = File(...), user: dict = Depends(require_owner_or_staff)):
    _cek_izin_backup(user, "izin_backup_import", "import")
    konten = await file.read()
    try:
        if db_compat.IS_POSTGRES:
            backup_path = pengaturan_backup.import_database_postgres(konten, user["tenant_id"])
        else:
            _tolak_backup_sqlite_multi_tenant()
            backup_path = pengaturan_backup.import_database(konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True, "backup_sebelumnya": backup_path}


# ================= LAPORAN PDF =================

@router.get("/laporan/pdf")
def download_laporan_pdf(jenis: str, barber_id: int | None = None,
                          tanggal_mulai: str | None = None, tanggal_selesai: str | None = None,
                          tahun: int | None = None, bulan: int | None = None,
                          user: dict = Depends(require_owner_or_staff),
                          _fitur: dict = Depends(require_feature("export_pdf"))):
    if user["role"] == "staff" and not permissions.has("izin_laporan_pdf", tenant_id=user["tenant_id"]):
        raise HTTPException(status_code=403, detail="Admin tidak punya izin untuk mengunduh laporan PDF.")
    try:
        konten, filename = laporan_pdf.buat_laporan(
            jenis, barber_id, dicetak_oleh=user["username"],
            tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai, tahun=tahun, bulan=bulan,
            tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ================= PROFIL (akun Owner sendiri) =================
# FITUR Email, Verifikasi Email, Lupa Kata Sandi -- item 5: tenant LAMA
# (dibuat sebelum fitur email ini ada, atau lewat Super Admin) belum tentu
# punya email tersimpan sama sekali. Endpoint ini KHUSUS Owner (require_admin
# -- BUKAN require_owner_or_staff, staff/karyawan TIDAK mengatur email
# Owner) menambah/mengubah email AKUN SENDIRI, memicu email verifikasi --
# TIDAK PERNAH menyetel blokir_sampai_verifikasi (HANYA milik alur
# Registrasi mandiri baru, lihat email_auth_migrasi.py), jadi Owner tenant
# lama TIDAK PERNAH terblokir login karena ini walau belum sempat
# memverifikasi emailnya.

class ProfilEmailBody(BaseModel):
    email: str = ""


@router.put("/profil/email")
def ubah_email_profil(body: ProfilEmailBody, user: dict = Depends(require_admin)):
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Format email tidak valid.")
    existing = email_auth_db.get_user_by_email(email)
    if existing is not None and existing["id"] != user["id"]:
        raise HTTPException(status_code=422, detail="Email sudah dipakai akun lain.")
    email_auth_db.set_email_user(user["id"], email)
    token = email_auth_db.buat_token_verifikasi(user["id"])
    link = email_service.link_verifikasi_email(token)
    email_service.kirim_email(
        email, "Verifikasi email Rivoir Anda",
        email_templates.template_verifikasi_email(user["username"], link, email_auth_db.MASA_BERLAKU_VERIFIKASI_JAM),
    )
    diperbarui = auth_db.get_user(user["id"])
    diperbarui.pop("password_hash", None)
    return diperbarui


@router.post("/profil/kirim-ulang-verifikasi")
def kirim_ulang_verifikasi_profil(user: dict = Depends(require_admin)):
    """Tombol "Kirim Ulang" di halaman Profil -- BEDA dari /api/public/
    registration/resend-verification (endpoint PUBLIK untuk akun yang
    BELUM BISA login sama sekali): endpoint ini untuk Owner yang SUDAH
    login (tenant lama menambah email, tapi belum sempat klik link-nya)."""
    if not user.get("email"):
        raise HTTPException(status_code=422, detail="Belum ada email tersimpan -- isi email Anda dulu.")
    if user.get("email_verified"):
        return {"ok": True, "message": "Email Anda sudah terverifikasi."}
    token = email_auth_db.buat_token_verifikasi(user["id"])
    link = email_service.link_verifikasi_email(token)
    email_service.kirim_email(
        user["email"], "Verifikasi email Rivoir Anda",
        email_templates.template_verifikasi_email(user["username"], link, email_auth_db.MASA_BERLAKU_VERIFIKASI_JAM),
    )
    return {"ok": True, "message": "Email verifikasi telah dikirim ulang."}
