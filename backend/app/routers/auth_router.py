"""routers/auth_router.py — /api/auth/*: login & data akun sendiri."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

import auth_db
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
        t = tenant_db.get_tenant_by_slug(slug)
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

    tenant_info = None
    if user.get("tenant_id") is not None:
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
