"""routers/subscription.py — FONDASI Multi-Tenant Phase 3: Subscription & Tenant Lifecycle
=============================================================================
Dua router dalam SATU file ini (pola sama seperti routers/booking.py):

1. `router` (prefix `/api/subscription`) — Owner SATU TENANT sendiri
   (require_admin, HANYA role 'admin' -- BUKAN require_owner_or_staff, sesuai
   cakupan Phase 3: "Owner hanya dapat melihat informasi subscription
   (read-only)", akun 'staff' TIDAK ikut melihat). Read-only total -- TIDAK
   ADA endpoint PUT/POST di router ini. Kekecualian: GET /status (di bawah
   GET /me) SENGAJA terbuka untuk SEMUA role tenant (Owner/Admin/Barber,
   get_current_user polos) -- BUKAN "informasi subscription" lengkap
   (trial/dst, tetap Owner-murni lewat /me), hanya `akses_diblokir` supaya
   frontend (router.js) bisa mengalihkan SELURUH akun toko yang diblokir ke
   halaman status (bukan cuma Owner), PLUS `periode_selesai`/`hari_tersisa`/
   `peringatan_kadaluarsa` (FITUR Notifikasi H-7, lihat subscription_status()
   di bawah) supaya nav.js bisa menampilkan peringatan untuk SEMUA role juga.
2. `superadmin_router` (prefix `/api/superadmin/subscriptions`) — KHUSUS
   role 'superadmin' (require_superadmin), mengelola package/status/trial/
   config platform/pembayaran VA SELURUH tenant. SETIAP aksi tercatat
   ke superadmin_audit_log (lihat superadmin_audit_db.py), pola SAMA PERSIS
   dengan routers/superadmin.py (buat_tenant/ubah_status_tenant).

REVISI (diminta Owner): fitur "Grace Period" manual (set_grace(), endpoint
PUT /{tenant_id}/grace, field grace_hari di config) DIHAPUS TOTAL dari sini
-- lihat subscription_db.py untuk penjelasan lengkap penggantinya
(peringatan H-7 di subscription_status() di bawah)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import billing_db
import subscription_db
import superadmin_audit_db
import tenant_db
from auth import get_current_user, require_admin, require_permission, require_superadmin

router = APIRouter(prefix="/api/subscription", tags=["subscription"])
superadmin_router = APIRouter(prefix="/api/superadmin/subscriptions", tags=["subscription-superadmin"])


# ============================= Owner (read-only) =============================

@router.get("/me")
def subscription_saya(user: dict = Depends(require_permission("izin_setting_subscription"))):
    """Read-only -- HANYA melihat, tidak ada cara mengubah apa pun dari
    endpoint ini (BEDA dari /api/billing/* yang tetap murni require_admin,
    TIDAK disentuh revisi ini -- menu Billing tetap Owner-only). `izin_
    setting_subscription` (permissions.py::PERMISSION_TREE) menggerbang
    tab "Subscription" di Setting -- grantable, tapi tetap read-only, jadi
    risikonya rendah. `akses_diblokir` dikirim eksplisit supaya frontend
    tidak perlu duplikasi logika STATUS_AKSES_DIBLOKIR sendiri (lihat
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
    berikutnya -- tidak ada apa pun yang di-cache di sisi server.

    REVISI (peringatan H-7, pengganti grace_period/SUSPEND_GRACE_HARI yang
    dihapus): `hari_tersisa`/`peringatan_kadaluarsa`/`periode_selesai`/
    `status` diikutkan di sini (BUKAN cuma di /me yang Owner-only) supaya
    nav.js bisa menampilkan tulisan merah di bawah nama tenant untuk SEMUA
    role tenant (kecuali 'barber', digerbang di frontend) -- lihat
    subscription_db.hari_tersisa_dari_tanggal()/PERINGATAN_KADALUARSA_HARI.
    REVISI (diminta Owner, "perluas juga ke masa trial"): peringatan ini
    SEKARANG berlaku untuk status 'trial' juga (dihitung dari trial_end),
    TIDAK HANYA 'active' (periode_selesai) -- `status` dikirim di respons
    supaya nav.js tahu teks mana yang dipakai ("Masa trial" vs
    "Langganan")."""
    if user.get("tenant_id") is None:
        return {
            "akses_diblokir": False, "package": None, "features": [], "izin_paket": [],
            "periode_selesai": None, "hari_tersisa": None, "peringatan_kadaluarsa": False,
            "status": None,
        }
    tenant_id = user["tenant_id"]
    sub = subscription_db.get_subscription(tenant_id)
    fitur = []
    izin_paket = []
    hari_tersisa = None
    periode_selesai = None
    if sub is not None:
        paket = billing_db.get_package_by_kode(sub["package"])
        if paket is not None:
            fitur = [f["kode"] for f in billing_db.get_package_features(paket["id"])]
            # Work #2 (Superadmin Package Permission Tree): daftar key izin_*
            # (permissions.PERMISSION_TREE) yang TERMASUK paket ini --
            # dikirim di respons yang SAMA dengan `features` (pola identik,
            # lihat catatan di atas) supaya frontend (feature_access.js::
            # MugenFeature.hasIzin()) bisa mengunci menu/sub-menu di sidebar
            # (nav.js) & halaman tujuan TANPA endpoint/refresh terpisah.
            izin_paket = list(billing_db.get_package_permission_keys(paket["id"]))
        periode_selesai = sub.get("periode_selesai")
        # Peringatan H-7: 'active' dihitung dari periode_selesai (periode
        # berbayar), 'trial' dari trial_end -- status LAIN ('lifetime' tidak
        # pernah punya tanggal berakhir, 'expired'/'suspended'/'cancelled'
        # sudah ditolak akses_diblokir() duluan lewat STATUS_AKSES_DIBLOKIR,
        # jadi peringatan "akan berakhir" tidak relevan lagi buat mereka).
        if sub["status"] == "active":
            hari_tersisa = subscription_db.hari_tersisa_periode(sub)
        elif sub["status"] == "trial":
            hari_tersisa = subscription_db.hari_tersisa_dari_tanggal(sub.get("trial_end"))
    peringatan_kadaluarsa = (
        hari_tersisa is not None and 0 <= hari_tersisa <= subscription_db.PERINGATAN_KADALUARSA_HARI
    )
    return {
        "akses_diblokir": subscription_db.akses_diblokir(tenant_id),
        "package": sub["package"] if sub else None,
        "features": fitur,
        "izin_paket": izin_paket,
        "status": sub["status"] if sub else None,
        "periode_selesai": periode_selesai,
        "hari_tersisa": hari_tersisa,
        "peringatan_kadaluarsa": peringatan_kadaluarsa,
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


@superadmin_router.put("/config")
def ubah_config(body: ConfigBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = subscription_db.set_platform_config(trial_hari=body.trial_hari)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_config_subscription",
                               detail=f"trial_hari={hasil['trial_hari']}")
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


class ResetBody(BaseModel):
    package: str
    tanggal_mulai: str     # "YYYY-MM-DD"
    tanggal_selesai: str   # "YYYY-MM-DD"
    status: str


@superadmin_router.put("/{tenant_id}/reset")
def reset_subscription(tenant_id: int, body: ResetBody, user: dict = Depends(require_superadmin)):
    """Perbaikan Billing/Subscription (requirement Owner poin 3-6, 14, 15):
    "↻ Reset Subscription" -- koreksi package/periode/status SATU tenant
    (mis. tanggal keliru dari sandbox/gateway/kesalahan admin) TANPA
    menyentuh invoice/payment/webhook log SAMA SEKALI (poin 5) -- lihat
    subscription_db.reset_subscription(), yang HANYA UPDATE
    tenant_subscriptions. Tanggal dari frontend (<input type="date">) SAJA,
    dinormalisasi ke awal/akhir hari supaya konsisten dengan format
    isoformat(timespec="seconds") yang dipakai kolom periode_* lain.

    periode_selesai yang ditulis di sini otomatis jadi anchor BARU untuk
    perpanjangan berikutnya (poin 6) -- lihat billing_webhook.py::
    _hitung_periode_baru(), tidak ada logika terpisah untuk "hasil Reset"."""
    t = _tenant_wajib_ada(tenant_id)
    sebelum = subscription_db.get_subscription(tenant_id)
    if sebelum is None:
        raise HTTPException(status_code=404, detail="Tenant ini belum punya data subscription.")
    periode_mulai = f"{body.tanggal_mulai}T00:00:00"
    periode_selesai = f"{body.tanggal_selesai}T23:59:59"
    try:
        hasil = subscription_db.reset_subscription(tenant_id, body.package, periode_mulai, periode_selesai,
                                                     body.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(
        user["username"], "reset_subscription", tenant_id=tenant_id, tenant_slug=t["slug"],
        detail=(
            f"package: {sebelum['package']} -> {body.package}, "
            f"periode_selesai: {sebelum.get('periode_selesai') or '-'} -> {periode_selesai}, "
            f"status: {sebelum['status']} -> {body.status}"
        ),
    )
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
    # FITUR Program Afiliasi Sales/Marketing (sales_db.py): begitu
    # pembayaran langganan ditandai lunas, cek otomatis apakah tenant ini
    # terdaftar lewat kode referral -- kalau ya, catat komisi (baru/repeat
    # ditentukan di dalam sales_db.py sendiri, berdasarkan riwayat
    # pembayaran 'paid' tenant ini). Import lokal (hindari import siklik di
    # level modul, pola sama seperti modul lain di proyek ini) -- tidak ada
    # efek apa pun kalau tenant tidak punya kode referral terpasang.
    if body.payment_status == "paid":
        import sales_db
        sales_db.catat_komisi_dari_subscription_payment(hasil)
    t = tenant_db.get_tenant(payment["tenant_id"])
    superadmin_audit_db.catat(user["username"], "ubah_status_pembayaran_subscription",
                               tenant_id=payment["tenant_id"], tenant_slug=t["slug"] if t else None,
                               detail=f"payment_id={payment_id}, payment_status={body.payment_status}")
    return hasil
