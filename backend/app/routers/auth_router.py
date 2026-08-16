"""routers/auth_router.py — /api/auth/*: login & data akun sendiri.

FITUR Email, Verifikasi Email, Lupa Kata Sandi: tiga endpoint publik baru
ditambahkan di bagian bawah file ini (verifikasi-email, lupa-password,
reset-password) -- lihat email_auth_db.py untuk logika token, email_service.py
untuk pengiriman. login() sendiri mendapat SATU gerbang tambahan (lihat
komentar di dalamnya) -- SELAIN itu, endpoint/alur login yang sudah ada
TIDAK diubah sama sekali."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

import auth_db
import email_auth_db
import email_service
import email_templates
import tenant_db
from auth import buat_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str
    # FONDASI Multi-Tenant Phase 2.0: slug tenant OPSIONAL -- kosong (default,
    # perilaku LAMA) berarti "cari otomatis lintas tenant" (lihat login() di
    # bawah), diisi berarti "saya tahu persis toko mana, jangan tebak-tebak".
    tenant: str | None = None


def _tenant_ringkas(t: dict) -> dict:
    return {"id": t["id"], "slug": t["slug"], "nama_barbershop": t["nama_barbershop"]}


@router.post("/login")
def login(body: LoginBody, request: Request):
    """FONDASI Multi-Tenant Phase 2.0: penyelesaian penuh keterbatasan yang
    didokumentasikan di Phase 1 ("dua tenant BERBEDA yang kebetulan memilih
    username yang SAMA PERSIS akan membuat login ambigu").

    Alur:
    1. `body.tenant` diisi (atau ter-resolve dari middleware -- header
       X-Tenant-Slug/subdomain, lihat tenant_middleware.py): login
       di-scope KETAT ke tenant itu. Slug tidak ditemukan/tidak aktif ->
       404 (pesan SAMA seperti resolve_tenant_publik(), tidak membedakan
       "tidak ada" vs "tidak aktif" ke pengguna publik).
    2. `body.tenant` KOSONG (kasus paling umum -- 100% instalasi yang cuma
       py punya satu tenant, DAN mayoritas kasus walau sudah multi-tenant):
       auth_db.autentikasi() mencari lintas tenant, hasilnya:
       - None -> 401 "Username atau password salah." (TIDAK PERNAH
         membedakan "username tidak ada" vs "password salah" vs "ada di
         >1 tenant tapi password salah semua" -- brute-force tidak dapat
         info tambahan apa pun dari sini, sama seperti sebelumnya).
       - dict (SATU kecocokan, >99% kasus nyata) -> login berhasil,
         perilaku 100% sama seperti sebelum Phase 2.0.
       - list (LEBIH DARI SATU kecocokan -- dua tenant BERBEDA kebetulan
         pakai username+password IDENTIK) -> 409 Conflict, body berisi
         daftar toko (`tenants: [{slug, nama_barbershop}, ...]`) supaya
         frontend bisa menampilkan pemilih tenant, lalu login ULANG
         dengan `tenant` diisi. Ambiguitas ini HANYA terungkap ke
         pemanggil yang SUDAH terbukti tahu password yang benar (lihat
         auth_db.autentikasi()), jadi tidak membuka celah enumerasi akun."""
    slug = body.tenant or getattr(request.state, "requested_tenant_slug", None)

    tenant_id = None
    if slug:
        # FITUR Subdomain Tenant Otomatis: `slug` (subdomain dashboard/staff,
        # PRIORITAS -- perilaku LAMA tidak berubah sama sekali) dicoba dulu,
        # baru fallback ke `booking_slug` (lihat tenant_db.py::
        # get_tenant_by_slug_atau_booking_slug()) -- supaya Login TETAP bisa
        # diakses dari subdomain <booking_slug>.rivoirsett.com begitu Owner
        # sudah mengubahnya berbeda dari `slug` awal (item 4/5 spesifikasi:
        # "Login tenant... harus menggunakan subdomain tersebut", "Backend
        # harus mengidentifikasi tenant berdasarkan subdomain yang diakses").
        t = tenant_db.get_tenant_by_slug_atau_booking_slug(slug)
        if t is None or t["status"] != "aktif":
            raise HTTPException(status_code=404, detail="Barbershop tidak ditemukan.")
        tenant_id = t["id"]

    hasil = auth_db.autentikasi(body.username, body.password, tenant_id=tenant_id)

    if isinstance(hasil, list):
        # Ambigu: password benar untuk >1 tenant sekaligus -- minta pengguna
        # memilih toko secara eksplisit, lalu login ulang dengan `tenant` diisi.
        tenants = []
        for u in hasil:
            t = tenant_db.get_tenant(u["tenant_id"])
            if t is not None and t["status"] == "aktif":
                tenants.append(_tenant_ringkas(t))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Username & password ini terdaftar di lebih dari satu toko. Pilih toko Anda.",
                "tenants": tenants,
            },
        )

    user = hasil
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Username atau password salah.")
    if not user.get("aktif"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Akun tidak aktif, hubungi Owner.")

    # FITUR Verifikasi Email: blokir_sampai_verifikasi HANYA pernah diset
    # True oleh Registrasi mandiri BARU (routers/tenant_registration.py) --
    # tenant lama/karyawan/email yang ditambahkan lewat Pengaturan > Profil
    # TIDAK PERNAH kena gerbang ini (lihat email_auth_migrasi.py), SESUAI
    # permintaan eksplisit "Jangan memblokir tenant lama". detail berupa
    # dict terstruktur (pola SAMA seperti 409 ambigu-toko di atas) supaya
    # frontend (login.js) bisa menampilkan tombol "Kirim Ulang Email
    # Verifikasi" tanpa menebak-nebak dari teks pesan.
    if user.get("blokir_sampai_verifikasi") and not user.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "email_belum_terverifikasi",
                "message": "Email Anda belum diverifikasi. Silakan cek email Anda, atau kirim ulang link verifikasi.",
                "email": user.get("email"),
            },
        )

    # BUGFIX: superadmin (akun PLATFORM, mengelola SELURUH tenant) HARUS
    # SELALU bisa login apa pun status tenant mana pun -- role dicek
    # LANGSUNG di sini (bukan hanya bergantung pada invarian "superadmin
    # selalu tenant_id=None" yang ditegakkan tambah_user()), supaya tidak
    # ikut ditolak kalau invarian itu ternyata dilanggar. Hanya akun
    # owner/admin ('admin'), staff, dan barber -- yang memang terikat SATU
    # tenant -- yang divalidasi terhadap status tenant di bawah ini.
    tenant_info = None
    if user["role"] != "superadmin" and user.get("tenant_id") is not None:
        t = tenant_db.get_tenant(user["tenant_id"])
        if t is None or t["status"] != "aktif":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                 detail="Akun barbershop ini sedang tidak aktif. Hubungi penyedia layanan.")
        tenant_info = _tenant_ringkas(t)

    token = buat_token(user["id"])
    return {"token": token, "user": user, "tenant": tenant_info}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


# REVISI UI/UX: preferensi Dark/Light Mode per akun -- endpoint ini bisa
# dipanggil siapa pun yang sudah login (admin maupun barber), HANYA
# mengubah tema milik akun itu sendiri (user_id dari token, bukan dari
# parameter apa pun yang bisa dimanipulasi lewat client).
class TemaBody(BaseModel):
    tema: str


@router.put("/tema")
def simpan_tema(body: TemaBody, user: dict = Depends(get_current_user)):
    try:
        auth_db.set_tema_user(user["id"], body.tema)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    diperbarui = auth_db.get_user(user["id"])
    diperbarui.pop("password_hash", None)
    return diperbarui


# FITUR Izin Lokasi APK Android -- "lokasi terakhir" akun ybs, dikirim
# SEKALI oleh android-app/ (native_app.js) begitu izin lokasi diberikan
# saat login pertama di dalam APK. Best-effort murni (lihat native_app.js),
# TIDAK berhubungan dengan Absensi GPS Geofencing (routers/attendance.py).
class LokasiBody(BaseModel):
    lat: float
    lng: float


@router.put("/lokasi")
def simpan_lokasi(body: LokasiBody, user: dict = Depends(get_current_user)):
    auth_db.set_lokasi_user(user["id"], body.lat, body.lng)
    return {"ok": True}


# ---------------------------------------------------------------------------
# FITUR Verifikasi Email & Lupa Kata Sandi -- SEMUA endpoint di bawah ini
# PUBLIK (tidak butuh login, sesuai sifatnya: pengguna yang memanggilnya
# JUSTRU belum/tidak bisa login).
# ---------------------------------------------------------------------------

class VerifikasiEmailBody(BaseModel):
    token: str = ""


@router.post("/verifikasi-email")
def verifikasi_email(body: VerifikasiEmailBody):
    """Token sekali pakai (lihat email_auth_db.py) -- klik ulang link yang
    SUDAH pernah dipakai TIDAK dianggap error (status "sudah_dipakai" ->
    tetap 200, pesan berbeda), supaya membuka link yang sama dua kali
    (dua tab, email client yang me-render ulang) tidak menakuti pengguna
    dengan pesan error padahal akunnya sebenarnya sudah terverifikasi."""
    hasil = email_auth_db.verifikasi_email_dengan_token((body.token or "").strip())
    if hasil["status"] == "tidak_valid":
        raise HTTPException(status_code=422, detail="Link verifikasi tidak valid atau sudah kedaluwarsa.")
    if hasil["status"] == "sudah_dipakai":
        return {"ok": True, "message": "Email ini sudah diverifikasi sebelumnya. Silakan login."}
    return {"ok": True, "message": "Email berhasil diverifikasi. Silakan login."}


class LupaPasswordBody(BaseModel):
    email: str = ""


_PESAN_LUPA_PASSWORD_GENERIK = "Kalau email tersebut terdaftar sebagai akun Owner, kami telah mengirimkan link reset password. Silakan periksa kotak masuk (dan folder spam) Anda."


@router.post("/lupa-password")
def lupa_password(body: LupaPasswordBody):
    """Item 4 (spesifikasi Lupa Kata Sandi): TIGA hasil berbeda tergantung
    jenis akun, TIDAK PERNAH membedakan lewat status code HTTP (SELALU 200)
    supaya tidak jadi sinyal tambahan bagi siapa pun yang mengetes endpoint
    ini otomatis:
    1. Email tidak ditemukan -> pesan generik (TIDAK mengonfirmasi/menolak).
    2. Email milik Owner (role='admin') -> kirim email reset, pesan generik
       yang SAMA PERSIS seperti kasus (1) -- respons TIDAK membocorkan
       apakah email ini benar terdaftar sebagai Owner atau tidak ditemukan
       sama sekali.
    3. Email milik karyawan (role selain 'admin') -> TIDAK kirim email,
       pesan EKSPLISIT mengarahkan ke Owner (SENGAJA beda dari kasus 1 & 2
       -- ini memang harus menginformasikan langkah yang benar ke pengguna
       ber-akun karyawan, sesuai instruksi eksplisit)."""
    email = (body.email or "").strip().lower()
    if not email:
        return {"message": _PESAN_LUPA_PASSWORD_GENERIK}
    user = email_auth_db.get_user_by_email(email)
    if user is None:
        return {"message": _PESAN_LUPA_PASSWORD_GENERIK}
    if user["role"] != "admin":
        return {
            "message": "Password akun karyawan hanya dapat direset oleh Owner Tenant. "
                       "Silakan hubungi pemilik atau administrator toko Anda."
        }
    token = email_auth_db.buat_token_reset(user["id"])
    link = email_service.link_reset_password(token)
    tenant = tenant_db.get_tenant(user["tenant_id"]) if user.get("tenant_id") else None
    nama = (tenant or {}).get("owner_name") or user["username"]
    email_service.kirim_email(
        email, "Atur ulang password Rivoir Anda",
        email_templates.template_reset_password(nama, link, email_auth_db.MASA_BERLAKU_RESET_JAM),
    )
    return {"message": _PESAN_LUPA_PASSWORD_GENERIK}


class ResetPasswordBody(BaseModel):
    token: str = ""
    password: str = ""
    confirm_password: str = ""


@router.post("/reset-password")
def reset_password(body: ResetPasswordBody):
    if body.password != body.confirm_password:
        raise HTTPException(status_code=422, detail="Konfirmasi password tidak cocok.")
    try:
        email_auth_db.pakai_token_reset((body.token or "").strip(), body.password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True, "message": "Password berhasil diubah. Silakan login dengan password baru Anda."}
