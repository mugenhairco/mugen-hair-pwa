"""routers/tenant_registration.py — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
=============================================================================
Register TENANT self-service lewat Landing Page publik (TANPA login,
TANPA Super Admin) -- SATU-SATUNYA endpoint publik yang membuat tenant baru
di seluruh aplikasi (di luar ini, hanya Super Admin lewat
routers/superadmin.py::buat_tenant()).

KEPUTUSAN ARSITEKTUR PENTING (lihat plan Phase 5 untuk detail lengkap):
tenant + akun Owner dibuat DI SINI, SAAT REGISTER -- BUKAN oleh webhook
Midtrans saat pembayaran berhasil (billing_webhook.py TIDAK DISENTUH SAMA
SEKALI, sesuai instruksi eksplisit "JANGAN mengubah logika Webhook").
Subscription tenant baru langsung diberi status 'expired' (SALAH SATU
status yang SUDAH ADA di subscription_db.STATUS_AKSES_DIBLOKIR, TIDAK ADA
status baru yang ditambahkan) -- tenant baru otomatis TERBLOKIR dari
seluruh dashboard (mekanisme akses_diblokir() yang SUDAH ADA sejak Phase 3,
TIDAK DIUBAH) sampai memilih paket & membayar lewat alur checkout Phase 4
yang SUDAH ADA (billing.py::checkout(), TIDAK DIUBAH) -- begitu webhook
(TIDAK DIUBAH) mengaktifkan subscription-nya, akses_diblokir() otomatis
lolos dengan sendirinya.

REVISI FITUR Verifikasi Email: Owner SEBELUMNYA langsung di-login-kan di
sini (token dikembalikan di response register()) supaya bisa lanjut ke
#/billing tanpa login manual. SEKARANG akun baru WAJIB verifikasi email
dulu sebelum bisa login sama sekali (blokir_sampai_verifikasi, lihat
email_auth_migrasi.py) -- register() TIDAK LAGI mengembalikan token/
auto-login, hanya konfirmasi "cek email Anda". Begitu email diverifikasi,
Owner login NORMAL lewat /api/auth/login (TIDAK DIUBAH) -- mekanisme
akses_diblokir()/redirect ke #/billing di atas TETAP jalan APA ADANYA
persis seperti sebelumnya begitu mereka login (status masih 'expired'),
jadi alur checkout Phase 4 TIDAK berubah SAMA SEKALI, hanya titik "kapan
pertama kali login" yang bergeser dari "saat register" jadi "setelah
verifikasi email"."""

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import auth_db
import email_auth_db
import email_service
import email_templates
import subscription_db
import superadmin_audit_db
import tenant_db
from tenant_middleware import LABEL_BUKAN_TENANT

public_router = APIRouter(prefix="/api/public/registration", tags=["registration-public"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _slugify(nama: str) -> str:
    """FITUR Subdomain Otomatis per Tenant: slug JADI langsung dipakai
    sebagai subdomain (`<slug>.rivoirsett.com`, lihat tenant_middleware.py)
    -- SELURUH karakter selain huruf/angka dibuang TOTAL (BUKAN diganti
    "-", label DNS boleh mengandung "-" tapi spesifikasi produk ini
    eksplisit minta tanpa pemisah, mis. "MUGEN Hair Co." -> "mugenhairco",
    "Bubble Shot" -> "bubbleshot")."""
    slug = re.sub(r"[^a-z0-9]+", "", nama.strip().lower())
    return slug or "toko"


def _slug_terpakai(slug: str) -> bool:
    """`slug` dianggap "terpakai" juga kalau bertabrakan dengan label
    subdomain yang DIRESERVASI platform (admin/www/api/app/dst, lihat
    tenant_middleware.py) -- supaya barbershop bernama persis "Admin" TIDAK
    PERNAH kebagian slug "admin" (yang HARUS selalu berarti Dashboard
    Super Admin, tidak pernah tenant mana pun) -- otomatis mendapat
    "admin2" dst lewat mekanisme angka collision yang sama."""
    return slug in LABEL_BUKAN_TENANT or tenant_db.get_tenant_by_slug(slug) is not None


def _buat_slug_unik(nama_barbershop: str) -> str:
    """Angka collision LANGSUNG menempel tanpa pemisah (mis. "mugenhairco2",
    BUKAN "mugenhairco-2") -- SESUAI spesifikasi produk eksplisit."""
    dasar = _slugify(nama_barbershop)
    slug = dasar
    percobaan = 1
    while _slug_terpakai(slug):
        percobaan += 1
        slug = f"{dasar}{percobaan}"
    return slug


class RegisterBody(BaseModel):
    nama_barbershop: str = ""
    owner_name: str = ""
    email: str = ""
    whatsapp: str = ""
    password: str = ""
    confirm_password: str = ""


def _validasi(body: RegisterBody) -> None:
    """Validasi manual (BUKAN Pydantic validator) -- SENGAJA, supaya pesan
    error-nya string polos di `detail` (pola sama persis dengan SELURUH
    endpoint lain di aplikasi ini, lihat superadmin.py/billing.py: ValueError
    -> HTTPException(422, detail=str(e))). Pydantic model_validator yang
    raise ValueError dibungkus FastAPI jadi ARRAY objek error terstruktur
    (RequestValidationError), BUKAN string -- frontend (register.js) hanya
    tahu cara menampilkan `detail` yang berupa string, jadi validator
    Pydantic akan membuat pesan error tidak terbaca ("[object Object]")."""
    if not (body.nama_barbershop or "").strip():
        raise HTTPException(status_code=422, detail="Nama Barbershop tidak boleh kosong.")
    if not (body.owner_name or "").strip():
        raise HTTPException(status_code=422, detail="Nama Owner tidak boleh kosong.")
    if not _EMAIL_RE.match((body.email or "").strip()):
        raise HTTPException(status_code=422, detail="Format email tidak valid.")
    if not (body.whatsapp or "").strip():
        raise HTTPException(status_code=422, detail="Nomor WhatsApp tidak boleh kosong.")
    if body.password != body.confirm_password:
        raise HTTPException(status_code=422, detail="Konfirmasi password tidak cocok.")
    # Dicek DI SINI (SEBELUM tenant/user dibuat) supaya password terlalu
    # pendek TIDAK meninggalkan baris `tenants` yatim tanpa akun Owner --
    # auth_db.tambah_user() menegakkan aturan yang SAMA (dipanggil setelah
    # ini juga, sebagai lapis pertahanan kedua), pesannya disamakan persis.
    if not body.password or len(body.password) < 4:
        raise HTTPException(status_code=422, detail="Password minimal 4 karakter.")


def _kirim_email_verifikasi(user_id: int, email: str, nama_penerima: str) -> None:
    """Best-effort -- kegagalan pengiriman TIDAK PERNAH melempar exception
    ke pemanggil (email_service.kirim_email() sendiri sudah menangkap
    SEMUA kegagalan & mengembalikan bool, lihat modul itu), SESUAI aturan
    eksplisit "kegagalan pengiriman email tidak menyebabkan aplikasi
    crash". Dipakai register() (kirim pertama) & resend_verification()
    (kirim ulang) supaya isi emailnya identik."""
    token = email_auth_db.buat_token_verifikasi(user_id)
    link = email_service.link_verifikasi_email(token)
    email_service.kirim_email(
        email, "Verifikasi email Rivoir Anda",
        email_templates.template_verifikasi_email(nama_penerima, link, email_auth_db.MASA_BERLAKU_VERIFIKASI_JAM),
    )


@public_router.post("/register")
def register(body: RegisterBody):
    _validasi(body)
    email = body.email.strip().lower()
    whatsapp = body.whatsapp.strip()

    if tenant_db.get_tenant_by_email(email) is not None:
        raise HTTPException(status_code=422, detail="Email sudah terdaftar.")
    if tenant_db.get_tenant_by_whatsapp(whatsapp) is not None:
        raise HTTPException(status_code=422, detail="Nomor WhatsApp sudah terdaftar.")
    # FITUR Verifikasi Email: "Email wajib unik" ditegakkan juga lewat
    # kolom users.email (BARU) -- get_tenant_by_email() di atas HANYA
    # mengecek data registrant tenant, belum tentu sama dengan users.email
    # kalau di masa depan ada jalur lain yang mengisi email tanpa lewat
    # sini (mis. Pengaturan > Profil tenant lama).
    if email_auth_db.get_user_by_email(email) is not None:
        raise HTTPException(status_code=422, detail="Email sudah terdaftar.")

    slug = _buat_slug_unik(body.nama_barbershop)
    try:
        tenant_id = tenant_db.buat_tenant(slug, body.nama_barbershop.strip())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    tenant_db.set_registrant_info(tenant_id, body.owner_name.strip(), email, whatsapp)

    try:
        user_id = auth_db.tambah_user(username=email, password=body.password, role="admin", tenant_id=tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Toko dibuat, tapi akun Owner gagal: {e}")

    # Status 'expired' (BUKAN status baru -- lihat docstring modul ini):
    # tenant baru langsung terblokir dari dashboard sampai membayar,
    # memakai mekanisme akses_diblokir() Phase 3 yang SUDAH ADA apa adanya.
    subscription_db.create_default_subscription(tenant_id, status="expired")

    # FITUR Verifikasi Email: akun BARU (lihat docstring modul ini di atas
    # untuk penjelasan lengkap kenapa register() TIDAK LAGI auto-login).
    email_auth_db.set_email_user(user_id, email)
    email_auth_db.tandai_blokir_sampai_verifikasi(user_id)
    _kirim_email_verifikasi(user_id, email, body.owner_name.strip())

    superadmin_audit_db.catat(
        "registrasi-publik", "registrasi_publik", tenant_id=tenant_id, tenant_slug=slug,
        detail=f"nama_barbershop={body.nama_barbershop!r}, email={email!r}",
    )

    return {
        "registered": True,
        "email": email,
        "message": "Registrasi berhasil. Silakan cek email Anda untuk memverifikasi akun sebelum bisa login.",
    }


class ResendVerificationBody(BaseModel):
    email: str = ""


@public_router.post("/resend-verification")
def resend_verification(body: ResendVerificationBody):
    """Tombol "Kirim Ulang Email Verifikasi" -- respons SELALU generik
    (tidak membedakan email ditemukan/tidak/sudah terverifikasi) supaya
    endpoint publik ini tidak bisa dipakai menebak-nebak email mana yang
    terdaftar, konsisten dengan prinsip yang sama dipakai routers/
    email_auth.py::lupa_password()."""
    email = (body.email or "").strip().lower()
    pesan = "Kalau email tersebut terdaftar dan belum diverifikasi, kami telah mengirimkan ulang link verifikasi."
    if not email:
        return {"message": pesan}
    user = email_auth_db.get_user_by_email(email)
    if user is not None and not user["email_verified"]:
        # Nama penerima: owner_name tersimpan di tenants (set_registrant_info()
        # saat register()), bukan di users -- diambil dari sana kalau ada,
        # fallback ke username supaya tetap terkirim walau tenant-nya (jarang
        # terjadi) tidak punya baris registrant info.
        tenant = tenant_db.get_tenant(user["tenant_id"]) if user.get("tenant_id") else None
        nama = (tenant or {}).get("owner_name") or user["username"]
        _kirim_email_verifikasi(user["id"], email, nama)
    return {"message": pesan}
