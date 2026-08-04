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
lolos dengan sendirinya. Owner LANGSUNG di-login-kan (token dikembalikan di
response) supaya bisa lanjut ke halaman #/billing tanpa login manual lagi
-- router.js perlu satu pengecualian sempit supaya #/billing bisa diakses
walau statusnya masih 'expired' (lihat router.js, BUKAN bagian backend ini)."""

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

import auth_db
import subscription_db
import superadmin_audit_db
import tenant_db
from auth import buat_token

public_router = APIRouter(prefix="/api/public/registration", tags=["registration-public"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _slugify(nama: str) -> str:
    slug = nama.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "toko"


def _buat_slug_unik(nama_barbershop: str) -> str:
    dasar = _slugify(nama_barbershop)
    slug = dasar
    percobaan = 1
    while tenant_db.get_tenant_by_slug(slug) is not None:
        percobaan += 1
        slug = f"{dasar}-{percobaan}"
    return slug


class RegisterBody(BaseModel):
    nama_barbershop: str
    owner_name: str
    email: str
    whatsapp: str
    password: str
    confirm_password: str

    @model_validator(mode="after")
    def _validasi(self):
        if self.password != self.confirm_password:
            raise ValueError("Konfirmasi password tidak cocok.")
        if not _EMAIL_RE.match((self.email or "").strip()):
            raise ValueError("Format email tidak valid.")
        if not (self.whatsapp or "").strip():
            raise ValueError("Nomor WhatsApp tidak boleh kosong.")
        if not (self.nama_barbershop or "").strip():
            raise ValueError("Nama Barbershop tidak boleh kosong.")
        if not (self.owner_name or "").strip():
            raise ValueError("Nama Owner tidak boleh kosong.")
        return self


@public_router.post("/register")
def register(body: RegisterBody):
    email = body.email.strip().lower()
    whatsapp = body.whatsapp.strip()

    if tenant_db.get_tenant_by_email(email) is not None:
        raise HTTPException(status_code=422, detail="Email sudah terdaftar.")
    if tenant_db.get_tenant_by_whatsapp(whatsapp) is not None:
        raise HTTPException(status_code=422, detail="Nomor WhatsApp sudah terdaftar.")

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

    superadmin_audit_db.catat(
        "registrasi-publik", "registrasi_publik", tenant_id=tenant_id, tenant_slug=slug,
        detail=f"nama_barbershop={body.nama_barbershop!r}, email={email!r}",
    )

    user = auth_db.get_user(user_id)
    token = buat_token(user_id)
    user.pop("password_hash", None)
    tenant = tenant_db.get_tenant(tenant_id)
    return {"token": token, "user": user, "tenant": tenant}
