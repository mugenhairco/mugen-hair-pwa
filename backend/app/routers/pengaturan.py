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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

import auth_db
import database as db
import pengaturan_barber
import pengaturan_backup
import pengaturan_bonus
import pengaturan_identitas
import pengaturan_service
import pengaturan_user
from auth import require_admin

router = APIRouter(prefix="/api/pengaturan", tags=["pengaturan"])

# Key setting yang boleh diubah lewat menu "Pengaturan Komisi" (semuanya
# SUDAH ADA di database.DEFAULT_SETTINGS sejak Tahap 2 — router ini cuma
# membuka jalan untuk mengedit, TIDAK menambah/mengubah rumus apapun).
# REVISI: uang_harian_barber/uang_harian_rafiq dipindah jadi per-barber
# (lihat endpoint /barber di bawah); bonus_kehadiran/maksimal_hari_libur
# dihapus total (fitur Bonus Kehadiran dihapus); target_bonus_customer/
# nominal_bonus_customer diganti daftar tier bertingkat (lihat endpoint
# /bonus-tiers di bawah) — semua itu TIDAK ADA lagi di sini.
KOMISI_KEYS = [
    "persentase_komisi", "potongan_modal_chemical",
    "maksimal_hari_libur_bonus_customer", "potongan_bonus_customer_persen",
]


# ================= IDENTITAS BARBERSHOP =================

class IdentitasBody(BaseModel):
    nama_barbershop: str
    alamat: str = ""
    whatsapp: str = ""
    email: str = ""
    instagram: str = ""
    jam_operasional: str = ""
    # PENYEMPURNAAN FORM BOOKING: field baru, dipakai halaman /book
    tagline: str = ""
    deskripsi: str = ""
    website: str = ""


@router.get("/identitas")
def ambil_identitas():
    return pengaturan_identitas.get_identitas()


@router.put("/identitas")
def simpan_identitas(body: IdentitasBody, user: dict = Depends(require_admin)):
    try:
        pengaturan_identitas.update_identitas(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return pengaturan_identitas.get_identitas()


@router.post("/logo")
async def upload_logo(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    konten = await file.read()
    try:
        pengaturan_identitas.simpan_logo(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return pengaturan_identitas.get_identitas()


@router.get("/logo")
def ambil_logo(v: str | None = None):
    path, content_type = pengaturan_identitas.get_logo_file_path()
    if path is None:
        raise HTTPException(status_code=404, detail="Logo belum diatur.")
    return FileResponse(path, media_type=content_type)


# PENYEMPURNAAN FORM BOOKING: Banner, pola SAMA PERSIS seperti Logo di atas
# (upload khusus admin, GET publik -- dipakai header halaman booking /book).
@router.post("/banner")
async def upload_banner(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    konten = await file.read()
    try:
        pengaturan_identitas.simpan_banner(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return pengaturan_identitas.get_identitas()


@router.get("/banner")
def ambil_banner(v: str | None = None):
    path, content_type = pengaturan_identitas.get_banner_file_path()
    if path is None:
        raise HTTPException(status_code=404, detail="Banner belum diatur.")
    return FileResponse(path, media_type=content_type)


# ================= PENGATURAN KOMISI & BONUS =================

class KomisiBody(BaseModel):
    persentase_komisi: float
    potongan_modal_chemical: float
    maksimal_hari_libur_bonus_customer: float
    potongan_bonus_customer_persen: float


@router.get("/komisi")
def ambil_komisi(user: dict = Depends(require_admin)):
    semua = db.get_all_settings()
    return {k: semua.get(k) for k in KOMISI_KEYS}


@router.put("/komisi")
def simpan_komisi(body: KomisiBody, user: dict = Depends(require_admin)):
    data = body.model_dump()
    for k, v in data.items():
        if v < 0:
            raise HTTPException(status_code=422, detail=f"{k} tidak boleh negatif.")
    db.set_settings_bulk(data)
    semua = db.get_all_settings()
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
    return db.get_bonus_customer_tiers()


@router.post("/bonus-tiers")
def tambah_bonus_tier(body: BonusTierBody, user: dict = Depends(require_admin)):
    try:
        return pengaturan_bonus.tambah_tier(body.target, body.bonus)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/bonus-tiers/{target}")
def ubah_bonus_tier(target: int, body: BonusTierUpdateBody, user: dict = Depends(require_admin)):
    try:
        return pengaturan_bonus.ubah_tier(target, body.target, body.bonus)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/bonus-tiers/{target}")
def hapus_bonus_tier(target: int, user: dict = Depends(require_admin)):
    try:
        return pengaturan_bonus.hapus_tier(target)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ================= MANAJEMEN BARBER =================

class BarberBody(BaseModel):
    nama: str
    is_rafiq: bool = False
    uang_harian: int = 0


class BarberUpdateBody(BaseModel):
    nama: str | None = None
    is_rafiq: bool | None = None
    aktif: bool | None = None
    uang_harian: int | None = None


@router.get("/barber")
def list_barber(user: dict = Depends(require_admin)):
    return db.get_barbers(hanya_aktif=False)  # tampilkan semua (aktif & nonaktif) di halaman Setting


@router.post("/barber")
def tambah_barber(body: BarberBody, user: dict = Depends(require_admin)):
    try:
        new_id = pengaturan_barber.tambah_barber_validated(body.nama, body.is_rafiq, body.uang_harian)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_barber(new_id)


@router.put("/barber/{barber_id}")
def update_barber(barber_id: int, body: BarberUpdateBody, user: dict = Depends(require_admin)):
    try:
        pengaturan_barber.update_barber_validated(
            barber_id, nama=body.nama, is_rafiq=body.is_rafiq, aktif=body.aktif,
            uang_harian=body.uang_harian,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_barber(barber_id)


@router.delete("/barber/{barber_id}")
def hapus_barber(barber_id: int, user: dict = Depends(require_admin)):
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


@router.get("/service")
def list_service(user: dict = Depends(require_admin)):
    return db.get_services(hanya_aktif=False)


@router.post("/service")
def tambah_service(body: ServiceBody, user: dict = Depends(require_admin)):
    try:
        new_id = pengaturan_service.tambah_service_lengkap(
            body.nama, body.harga, body.modal, body.pakai_potongan_chemical, body.durasi_menit,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_service(new_id)


@router.put("/service/{service_id}")
def update_service(service_id: int, body: ServiceUpdateBody, user: dict = Depends(require_admin)):
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


@router.get("/user")
def list_user(user: dict = Depends(require_admin)):
    daftar = auth_db.get_user_list()
    for u in daftar:
        u.pop("password_hash", None)  # jangan pernah kirim hash ke frontend
    return daftar


@router.post("/user")
def tambah_user(body: UserBody, user: dict = Depends(require_admin)):
    try:
        new_id = auth_db.tambah_user(body.username, body.password, body.role, body.barber_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    hasil = auth_db.get_user(new_id)
    hasil.pop("password_hash", None)
    return hasil


@router.put("/user/{user_id}/username")
def ganti_username(user_id: int, body: UsernameBody, user: dict = Depends(require_admin)):
    try:
        pengaturan_user.ganti_username(user_id, body.username)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.put("/user/{user_id}/password")
def ganti_password(user_id: int, body: PasswordBody, user: dict = Depends(require_admin)):
    try:
        auth_db.ganti_password(user_id, body.password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


@router.put("/user/{user_id}/nonaktifkan")
def nonaktifkan_user(user_id: int, user: dict = Depends(require_admin)):
    auth_db.nonaktifkan_user(user_id)
    return {"ok": True}


@router.put("/user/{user_id}/aktifkan")
def aktifkan_user(user_id: int, user: dict = Depends(require_admin)):
    try:
        pengaturan_user.aktifkan_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


# ================= BACKUP DATABASE =================

@router.get("/backup/export")
def export_database(user: dict = Depends(require_admin)):
    return FileResponse(db.DB_PATH, media_type="application/octet-stream",
                         filename="mugen_hair_backup.db")


@router.post("/backup/import")
async def import_database(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    konten = await file.read()
    try:
        backup_path = pengaturan_backup.import_database(konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True, "backup_sebelumnya": backup_path}
