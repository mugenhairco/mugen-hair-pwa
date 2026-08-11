"""routers/subscription.py — FONDASI Multi-Tenant Phase 3: Subscription & Tenant Lifecycle
=============================================================================
Dua router dalam SATU file ini (pola sama seperti routers/booking.py):

1. `router` (prefix `/api/subscription`) — Owner SATU TENANT sendiri
   (require_admin, HANYA role 'admin' -- BUKAN require_owner_or_staff, sesuai
   cakupan Phase 3: "Owner hanya dapat melihat informasi subscription
   (read-only)", akun 'staff' TIDAK ikut melihat). Read-only total -- TIDAK
   ADA endpoint PUT/POST di router ini. Kekecualian: GET /status (di bawah
   GET /me) SENGAJA terbuka untuk SEMUA role tenant (Owner/Admin/Barber,
   get_current_user polos) -- BUKAN "informasi subscription" (package/
   trial/grace/dst, tetap Owner-murni lewat /me), hanya SATU boolean
   akses_diblokir supaya frontend (router.js) bisa mengalihkan SELURUH
   akun toko yang diblokir ke halaman status, bukan cuma Owner.
2. `superadmin_router` (prefix `/api/superadmin/subscriptions`) — KHUSUS
   role 'superadmin' (require_superadmin), mengelola package/status/trial/
   grace/config platform/pembayaran VA SELURUH tenant. SETIAP aksi tercatat
   ke superadmin_audit_log (lihat superadmin_audit_db.py), pola SAMA PERSIS
   dengan routers/superadmin.py (buat_tenant/ubah_status_tenant)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import billing_db
import subscription_db
import superadmin_audit_db
import tenant_db
from auth import get_current_user, require_admin, require_superadmin

router = APIRouter(prefix="/api/subscription", tags=["subscription"])
superadmin_router = APIRouter(prefix="/api/superadmin/subscriptions", tags=["subscription-superadmin"])


# ============================= Owner (read-only) =============================

@router.get("/me")
def subscription_saya(user: dict = Depends(require_admin)):
    """Read-only -- Owner HANYA melihat, tidak ada cara mengubah apa pun dari
    endpoint ini. `akses_diblokir` dikirim eksplisit supaya frontend tidak
    perlu duplikasi logika STATUS_AKSES_DIBLOKIR sendiri (lihat
    subscription_db.py)."""
    sub = subscription_db.get_subscription(user["tenant_id"])
    if sub is None:
        raise HTTPException(status_code=404, detail="Data subscription belum tersedia untuk toko ini.")
    sub = dict(sub)
    sub["akses_diblokir"] = sub["status"] in subscription_db.STATUS_AKSES_DIBLOKIR
    return sub


@router.get("/status")
def subscription_status(user: dict = Depends(get_current_user)):
    """Lihat catatan akses di docstring modul -- terbuka untuk SEMUA role
    tenant (bukan hanya Owner), murni boolean untuk kebutuhan routing
    frontend. `tenant_id=None` (akun superadmin) dianggap TIDAK diblokir --
    superadmin tidak terikat tenant mana pun, endpoint ini tidak relevan
    untuknya (router.js frontend tidak pernah memanggil endpoint ini untuk
    sesi superadmin, ini murni jaring pengaman).

    Feature Gating: `package` + `features` (daftar kode fitur yang
    TERMASUK di paket tenant ini) diikutkan di sini juga -- frontend
    (subscription.js::MugenSubscription) sudah menyimpan APA ADANYA respons
    endpoint ini ke cache-nya, jadi menambah field di sini otomatis membuat
    MugenSubscription.get().features tersedia SINKRON di seluruh halaman
    tanpa perlu endpoint/refresh terpisah. Upgrade/downgrade paket (lewat
    Superadmin atau webhook Payment Gateway) langsung berlaku di panggilan
    berikutnya -- tidak ada apa pun yang di-cache di sisi server."""
    if user.get("tenant_id") is None:
        return {"akses_diblokir": False, "package": None, "features": []}
    tenant_id = user["tenant_id"]
    sub = subscription_db.get_subscription(tenant_id)
    fitur = []
    if sub is not None:
        paket = billing_db.get_package_by_kode(sub["package"])
        if paket is not None:
            fitur = [f["kode"] for f in billing_db.get_package_features(paket["id"])]
    return {
        "akses_diblokir": subscription_db.akses_diblokir(tenant_id),
        "package": sub["package"] if sub else None,
        "features": fitur,
    }


# ============================= Super Admin =============================

def _tenant_wajib_ada(tenant_id: int) -> dict:
    t = tenant_db.get_tenant(tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    return t


@superadmin_router.get("")
def list_subscriptions(user: dict = Depends(require_superadmin)):
    """Digabung dengan slug/nama_barbershop tiap tenant supaya Dashboard
    Super Admin tidak perlu query terpisah -- pola sama seperti
    routers/superadmin.py::_tenant_dengan_ringkasan()."""
    tenants_by_id = {t["id"]: t for t in tenant_db.list_tenants()}
    hasil = []
    for sub in subscription_db.list_subscriptions():
        t = tenants_by_id.get(sub["tenant_id"])
        baris = dict(sub)
        baris["tenant_slug"] = t["slug"] if t else None
        baris["nama_barbershop"] = t["nama_barbershop"] if t else None
        hasil.append(baris)
    return hasil


@superadmin_router.get("/config")
def ambil_config(user: dict = Depends(require_superadmin)):
    return subscription_db.get_platform_config()


class ConfigBody(BaseModel):
    trial_hari: int | None = None
    grace_hari: int | None = None


@superadmin_router.put("/config")
def ubah_config(body: ConfigBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = subscription_db.set_platform_config(trial_hari=body.trial_hari, grace_hari=body.grace_hari)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_config_subscription",
                               detail=f"trial_hari={hasil['trial_hari']}, grace_hari={hasil['grace_hari']}")
    return hasil


@superadmin_router.get("/{tenant_id}")
def detail_subscription(tenant_id: int, user: dict = Depends(require_superadmin)):
    _tenant_wajib_ada(tenant_id)
    sub = subscription_db.get_subscription(tenant_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Tenant ini belum punya data subscription.")
    return sub


class PackageBody(BaseModel):
    package: str


@superadmin_router.put("/{tenant_id}/package")
def ubah_package(tenant_id: int, body: PackageBody, user: dict = Depends(require_superadmin)):
    t = _tenant_wajib_ada(tenant_id)
    try:
        hasil = subscription_db.update_package(tenant_id, body.package)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_package_subscription", tenant_id=tenant_id,
                               tenant_slug=t["slug"], detail=f"package={body.package}")
    return hasil


class StatusBody(BaseModel):
    status: str


@superadmin_router.put("/{tenant_id}/status")
def ubah_status(tenant_id: int, body: StatusBody, user: dict = Depends(require_superadmin)):
    t = _tenant_wajib_ada(tenant_id)
    try:
        hasil = subscription_db.update_status(tenant_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_status_subscription", tenant_id=tenant_id,
                               tenant_slug=t["slug"], detail=f"status={body.status}")
    return hasil


class TrialBody(BaseModel):
    trial_start: str | None = None
    trial_end: str | None = None
    hari: int | None = None


@superadmin_router.put("/{tenant_id}/trial")
def ubah_trial(tenant_id: int, body: TrialBody, user: dict = Depends(require_superadmin)):
    t = _tenant_wajib_ada(tenant_id)
    try:
        hasil = subscription_db.set_trial(tenant_id, trial_start=body.trial_start,
                                           trial_end=body.trial_end, hari=body.hari)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_trial_subscription", tenant_id=tenant_id,
                               tenant_slug=t["slug"],
                               detail=f"trial_start={hasil['trial_start']}, trial_end={hasil['trial_end']}")
    return hasil


class GraceBody(BaseModel):
    grace_start: str | None = None
    grace_end: str | None = None
    hari: int | None = None


@superadmin_router.put("/{tenant_id}/grace")
def ubah_grace(tenant_id: int, body: GraceBody, user: dict = Depends(require_superadmin)):
    t = _tenant_wajib_ada(tenant_id)
    try:
        hasil = subscription_db.set_grace(tenant_id, grace_start=body.grace_start,
                                           grace_end=body.grace_end, hari=body.hari)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_grace_subscription", tenant_id=tenant_id,
                               tenant_slug=t["slug"],
                               detail=f"grace_start={hasil['grace_start']}, grace_end={hasil['grace_end']}")
    return hasil


# ============================= Payments (VA) — struktur saja =============================

@superadmin_router.get("/{tenant_id}/payments")
def list_payments(tenant_id: int, user: dict = Depends(require_superadmin)):
    _tenant_wajib_ada(tenant_id)
    return subscription_db.list_payments(tenant_id)


class PaymentBody(BaseModel):
    provider: str
    virtual_account_number: str
    amount: int
    expired_at: str | None = None


@superadmin_router.post("/{tenant_id}/payments")
def buat_payment(tenant_id: int, body: PaymentBody, user: dict = Depends(require_superadmin)):
    t = _tenant_wajib_ada(tenant_id)
    try:
        hasil = subscription_db.create_payment(tenant_id, body.provider, body.virtual_account_number,
                                                 body.amount, expired_at=body.expired_at)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "buat_pembayaran_subscription", tenant_id=tenant_id,
                               tenant_slug=t["slug"],
                               detail=f"provider={body.provider}, va={body.virtual_account_number}, amount={body.amount}")
    return hasil


class PaymentStatusBody(BaseModel):
    payment_status: str
    paid_at: str | None = None


@superadmin_router.put("/payments/{payment_id}/status")
def ubah_status_payment(payment_id: int, body: PaymentStatusBody, user: dict = Depends(require_superadmin)):
    payment = subscription_db.get_payment(payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Catatan pembayaran tidak ditemukan.")
    try:
        hasil = subscription_db.tandai_status_pembayaran(payment_id, body.payment_status, paid_at=body.paid_at)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    t = tenant_db.get_tenant(payment["tenant_id"])
    superadmin_audit_db.catat(user["username"], "ubah_status_pembayaran_subscription",
                               tenant_id=payment["tenant_id"], tenant_slug=t["slug"] if t else None,
                               detail=f"payment_id={payment_id}, payment_status={body.payment_status}")
    return hasil
