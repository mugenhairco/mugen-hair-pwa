"""routers/error_log.py — /api/log-error
DIY error monitoring (bukan Sentry, lihat error_log_db.py untuk latar
belakang lengkap). POST TIDAK PERNAH memerlukan login -- error bisa terjadi
SEBELUM user sempat login (mis. di halaman Login itu sendiri), jadi tenant
diresolve best-effort lewat auth.resolve_tenant_untuk_branding (sesi login
kalau ada, kalau tidak dari slug publik, None kalau benar-benar tidak
diketahui) -- SENGAJA dipakai di sini walau dokumentasinya menyebut "KHUSUS"
endpoint branding, karena semantiknya PERSIS yang dibutuhkan: tenant kalau
bisa diketahui, None (bukan 404) kalau tidak, tidak ada fungsi lain di
auth.py yang punya perilaku non-fatal seperti ini.

Endpoint ini SENGAJA tidak pernah melempar error balik ke pemanggil (lihat
try/except di bawah) -- kegagalan mencatat error TIDAK BOLEH jadi error
baru yang terlihat user, sama prinsipnya dengan push_service.py (gagal
kirim push TIDAK PERNAH menggagalkan operasi bisnis utama)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import error_log_db
from auth import require_admin, resolve_tenant_untuk_branding

router = APIRouter(prefix="/api/log-error", tags=["log-error"])

_SUMBER_VALID = ("frontend", "backend")


class LogErrorBody(BaseModel):
    pesan: str
    detail: str | None = None
    url: str | None = None
    user_agent: str | None = None
    sumber: str = "frontend"


@router.post("")
def kirim_log_error(body: LogErrorBody, tenant_id: int | None = Depends(resolve_tenant_untuk_branding)):
    try:
        error_log_db.catat_error(
            sumber=body.sumber if body.sumber in _SUMBER_VALID else "frontend",
            pesan=body.pesan, detail=body.detail, url=body.url,
            user_agent=body.user_agent, tenant_id=tenant_id,
        )
    except Exception:
        pass
    return {"ok": True}


@router.get("")
def daftar_log_error(sumber: str = None, user: dict = Depends(require_admin)):
    return error_log_db.get_error_log_list(tenant_id=user["tenant_id"], sumber=sumber)
