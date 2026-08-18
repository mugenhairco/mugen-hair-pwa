"""routers/tenant_registration.py — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
=============================================================================
Register TENANT self-service lewat Landing Page publik (TANPA login,
TANPA Super Admin) -- SATU-SATUNYA endpoint publik yang membuat tenant baru
di seluruh aplikasi (di luar ini, hanya Super Admin lewat
routers/superadmin.py::buat_tenant()).

KEPUTUSAN ARSITEKTUR PENTING (lihat plan Phase 5 untuk detail lengkap):
tenant + akun Owner dibuat DI SINI, SAAT REGISTER -- BUKAN oleh webhook
Payment Gateway saat pembayaran berhasil (billing_webhook.py TIDAK DISENTUH
SAMA SEKALI, sesuai instruksi eksplisit "JANGAN mengubah logika Webhook").

FITUR Landing Page & Pricing (Free Trial 30 Hari): subscription tenant baru
SEKARANG langsung diberi status 'trial' (SEBELUMNYA 'expired' -- lihat
riwayat git untuk versi lama) lewat subscription_db.create_default_
subscription() yang SUDAH ADA (TIDAK ADA status/tabel/mekanisme baru --
'trial' SUDAH menjadi salah satu STATUS_VALID sejak Phase 3, hanya SEKARANG
benar-benar dipakai di titik register() ini) -- trial_start/trial_end
otomatis terisi dari DEFAULT_TRIAL_HARI (subscription_db.py, 30 hari) atau
konfigurasi Super Admin kalau sudah pernah diatur (get_platform_config()).
Selama trial, tenant TIDAK diblokir (status 'trial' BUKAN anggota
STATUS_AKSES_DIBLOKIR) -- Owner bisa langsung memakai seluruh fitur begitu
email terverifikasi, TANPA membayar dulu. Begitu trial_end lewat, Super
Admin (manual, ATAU proses batch terpisah di masa depan -- TIDAK ADA di
cakupan task ini) mengubah status jadi 'expired'/'grace_period', barulah
akses_diblokir() (TIDAK DIUBAH sejak Phase 3) mulai berlaku -- Owner
memilih paket & membayar lewat alur checkout Phase 4 yang SUDAH ADA
(billing.py::checkout(), TIDAK DIUBAH selain penambahan siklus 6 bulan)
untuk keluar dari blokir, PERSIS seperti alur upgrade dari trial expired
manapun -- mekanisme webhook (TIDAK DIUBAH) yang mengaktifkan subscription
tetap sama persis.

REVISI FITUR Verifikasi Email: Owner SEBELUMNYA langsung di-login-kan di
sini (token dikembalikan di response register()) supaya bisa lanjut ke
#/billing tanpa login manual. SEKARANG akun baru WAJIB verifikasi email
dulu sebelum bisa login sama sekali (blokir_sampai_verifikasi, lihat
email_auth_migrasi.py) -- register() TIDAK LAGI mengembalikan token/
auto-login, hanya konfirmasi "cek email Anda". Begitu email diverifikasi,
Owner login NORMAL lewat /api/auth/login (TIDAK DIUBAH) langsung masuk ke
Dashboard (BUKAN #/billing lagi -- status masih 'trial', TIDAK diblokir),
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

public_router = APIRouter(prefix="/api/public/registration", tags=["registration-public"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterBody(BaseModel):
    nama_barbershop: str = ""
    owner_name: str = ""
    username: str = ""
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
    if not (body.username or "").strip():
        raise HTTPException(status_code=422, detail="Username tidak boleh kosong.")
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
    username = body.username.strip()

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
    # FITUR Username Registrasi Mandiri: unik di SELURUH sistem (lintas
    # tenant) -- SENGAJA beda dari constraint asli users(tenant_id,
    # username) di auth_db.tambah_user()/skema (per-tenant, dua tenant
    # BOLEH punya username sama -- tetap berlaku apa adanya untuk jalur
    # LAIN yang membuat user, mis. Setting > User Owner/Super Admin,
    # TIDAK disentuh di sini). Dicek DI SINI (SEBELUM tenant/user dibuat,
    # pola sama dengan pengecekan email/whatsapp di atas) supaya username
    # bentrok tidak meninggalkan baris `tenants` yatim tanpa akun Owner.
    # get_user_by_username() TANPA tenant_id (auth_db.py) mencari lintas
    # SELURUH tenant -- fungsi yang SUDAH ADA, tidak perlu diubah.
    if auth_db.get_user_by_username(username) is not None:
        raise HTTPException(status_code=422, detail="Username sudah digunakan, silakan pilih username lain.")

    slug = tenant_db.buat_slug_unik(body.nama_barbershop)
    try:
        tenant_id = tenant_db.buat_tenant(slug, body.nama_barbershop.strip())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    tenant_db.set_registrant_info(tenant_id, body.owner_name.strip(), email, whatsapp)

    try:
        user_id = auth_db.tambah_user(username=username, password=body.password, role="admin", tenant_id=tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Toko dibuat, tapi akun Owner gagal: {e}")

    # FITUR Landing Page & Pricing (Free Trial 30 Hari): status 'trial'
    # (BUKAN status baru -- lihat docstring modul ini) -- tenant baru
    # langsung mendapat akses penuh selama masa trial (DEFAULT_TRIAL_HARI,
    # subscription_db.py), memakai mekanisme trial_start/trial_end Phase 3
    # yang SUDAH ADA apa adanya.
    subscription_db.create_default_subscription(tenant_id, status="trial")

    # FITUR Verifikasi Email: akun BARU (lihat docstring modul ini di atas
    # untuk penjelasan lengkap kenapa register() TIDAK LAGI auto-login).
    # BUGFIX (audit): get_user_by_email() di baris 133 sudah mengecek email
    # ini belum dipakai, TAPI itu check-then-act -- kalau dua pendaftaran
    # dengan email PERSIS sama menyelip di antara pengecekan itu dan baris
    # ini (jendela race yang sangat sempit), unique index case-insensitive
    # di users.email (email_auth_migrasi.py) jadi penentu akhir & akan
    # menolak salah satunya di sini alih-alih diam-diam membuat dua akun
    # dengan email yang sama.
    try:
        email_auth_db.set_email_user(user_id, email)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Toko dibuat, tapi email gagal disimpan: {e}")
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
