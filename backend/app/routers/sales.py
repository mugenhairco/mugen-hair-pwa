"""routers/sales.py — Program Afiliasi Sales/Marketing (sales_db.py)
=============================================================================
Dua router dalam SATU file ini (pola sama seperti routers/subscription.py):

1. `superadmin_router` (prefix `/api/superadmin/sales`) — KHUSUS role
   'superadmin': merekrut akun sales (+ kode referral pertamanya
   sekaligus), mengubah persentase komisi (fleksibel per kode), menempel
   kode referral manual ke tenant tertentu, melihat SELURUH komisi lintas
   sales + toggle status bayar, dan mengelola transaksi Lisensi Lifetime
   (dicatat manual, ditandai lunas di sini -- lihat sales_db.py untuk efek
   sampingnya: upgrade subscription + komisi otomatis). SETIAP aksi
   tercatat ke superadmin_audit_log, pola sama persis routers/subscription.py.

2. `router` (prefix `/api/sales`) — KHUSUS role 'sales' (require_sales):
   Portal Sales miliknya sendiri, read-only -- kode referral miliknya,
   daftar tenant yang terdaftar lewat kode itu, dan rincian komisinya
   (termasuk mana yang sudah/belum dibayar). TIDAK ADA endpoint tulis di
   sini -- sales TIDAK BISA mengubah persentase komisi atau menandai
   komisinya sendiri lunas (hanya Super Admin, poin 1 di atas)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth_db
import sales_db
import subscription_db
import superadmin_audit_db
import tenant_db
from auth import require_sales, require_superadmin

superadmin_router = APIRouter(prefix="/api/superadmin/sales", tags=["sales-superadmin"])
router = APIRouter(prefix="/api/sales", tags=["sales"])


# ============================= Super Admin: Akun & Kode Referral =============================

class BuatAkunSalesBody(BaseModel):
    username: str
    password: str
    nama_sales: str
    kode: str
    komisi_persen_baru: float = sales_db.KOMISI_PERSEN_BARU_DEFAULT
    komisi_persen_repeat: float = sales_db.KOMISI_PERSEN_REPEAT_DEFAULT
    komisi_persen_lifetime: float = sales_db.KOMISI_PERSEN_LIFETIME_DEFAULT


@superadmin_router.post("/akun")
def buat_akun_sales(body: BuatAkunSalesBody, user: dict = Depends(require_superadmin)):
    """Membuat akun login (role='sales', tenant_id=None) sekaligus kode
    referral pertamanya dalam satu panggilan -- Super Admin tinggal
    memberikan username/password itu ke orang sales yang direkrut, lalu
    orang itu login lewat halaman login yang SAMA dipakai semua role
    (frontend mengarahkan berdasarkan role, lihat router.js)."""
    try:
        user_id = auth_db.tambah_user(body.username, body.password, "sales", tenant_id=None)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        kode = sales_db.buat_kode_referral(
            body.kode, user_id, body.nama_sales,
            komisi_persen_baru=body.komisi_persen_baru,
            komisi_persen_repeat=body.komisi_persen_repeat,
            komisi_persen_lifetime=body.komisi_persen_lifetime,
        )
    except ValueError as e:
        # Kode referral gagal (mis. sudah dipakai) -- akun login sudah
        # terlanjur dibuat di atas, hapus lagi supaya tidak ada akun
        # "menggantung" tanpa kode referral sama sekali.
        auth_db.hapus_user(user_id)
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "buat_akun_sales",
                               detail=f"username={body.username}, kode={kode['kode']}")
    return kode


@superadmin_router.get("/kode-referral")
def list_kode_referral(user: dict = Depends(require_superadmin)):
    # REVISI (laporan Superadmin): tiap baris dilengkapi `username` akun
    # login sales-nya -- dibutuhkan frontend untuk tombol "Ganti Password"
    # (lihat PUT /akun/{user_id}/password di bawah) dan supaya Superadmin
    # tahu username mana yang harus diberikan ke orangnya, tanpa perlu buka
    # tabel users secara terpisah.
    hasil = []
    for kode in sales_db.list_kode_referral():
        akun = auth_db.get_user(kode["user_id"])
        hasil.append({**kode, "username": akun["username"] if akun else None})
    return hasil


class UbahKodeReferralBody(BaseModel):
    nama_sales: str | None = None
    komisi_persen_baru: float | None = None
    komisi_persen_repeat: float | None = None
    komisi_persen_lifetime: float | None = None
    aktif: bool | None = None


@superadmin_router.put("/kode-referral/{id_}")
def ubah_kode_referral(id_: int, body: UbahKodeReferralBody, user: dict = Depends(require_superadmin)):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        hasil = sales_db.update_kode_referral(id_, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_kode_referral",
                               detail=f"kode_id={id_}, kode={hasil['kode']}")
    return hasil


class GantiPasswordSalesBody(BaseModel):
    password: str


@superadmin_router.put("/akun/{user_id}/password")
def ganti_password_sales(user_id: int, body: GantiPasswordSalesBody, user: dict = Depends(require_superadmin)):
    """FITUR (laporan Superadmin): password akun sales TIDAK PERNAH bisa
    dilihat (hash satu arah, sama seperti seluruh akun lain di aplikasi
    ini -- tidak ada cara menampilkan password asli siapa pun, bahkan untuk
    Super Admin), tapi SEBELUMNYA juga tidak ada cara mengubahnya kalau
    sales lupa/butuh diganti -- endpoint ini mengisi celah itu, khusus
    akun ber-role 'sales' (menolak tegas kalau user_id yang dikirim
    ternyata akun role lain, supaya endpoint ini tidak disalahgunakan jadi
    jalan pintas reset password akun Owner/Admin/Barber tenant mana pun)."""
    target = auth_db.get_user(user_id)
    if target is None or target["role"] != "sales":
        raise HTTPException(status_code=404, detail="Akun sales tidak ditemukan.")
    try:
        auth_db.ganti_password(user_id, body.password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_password_sales", detail=f"user_id={user_id}, username={target['username']}")
    return {"ok": True}


# ============================= Super Admin: Atribusi Tenant =============================

class TempelReferralBody(BaseModel):
    referral_code_id: int | None = None


@superadmin_router.put("/tenant/{tenant_id}/referral")
def tempel_referral_tenant(tenant_id: int, body: TempelReferralBody, user: dict = Depends(require_superadmin)):
    t = tenant_db.get_tenant(tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    if body.referral_code_id is not None and sales_db.get_kode_referral(body.referral_code_id) is None:
        raise HTTPException(status_code=422, detail="Kode referral tidak ditemukan.")
    sales_db.set_tenant_referral(tenant_id, body.referral_code_id)
    superadmin_audit_db.catat(user["username"], "tempel_referral_tenant", tenant_id=tenant_id,
                               tenant_slug=t["slug"], detail=f"referral_code_id={body.referral_code_id}")
    return {"ok": True}


# ============================= Super Admin: Komisi =============================

def _lengkapi_komisi(k: dict) -> dict:
    kode = sales_db.get_kode_referral(k["referral_code_id"])
    t = tenant_db.get_tenant(k["tenant_id"])
    return {
        **k,
        "kode_referral": kode["kode"] if kode else None,
        "nama_sales": kode["nama_sales"] if kode else None,
        "nama_tenant": t["nama_barbershop"] if t else None,
    }


@superadmin_router.get("/komisi")
def list_komisi_semua(user: dict = Depends(require_superadmin)):
    return [_lengkapi_komisi(k) for k in sales_db.list_komisi_semua()]


class UbahStatusKomisiBody(BaseModel):
    status: str


@superadmin_router.put("/komisi/{id_}/status")
def ubah_status_komisi(id_: int, body: UbahStatusKomisiBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = sales_db.tandai_komisi(id_, body.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_status_komisi",
                               detail=f"komisi_id={id_}, status={body.status}")
    return _lengkapi_komisi(hasil)


# ============================= Super Admin: Lisensi Lifetime (Beli Putus) =============================

def _lengkapi_lifetime(p: dict) -> dict:
    t = tenant_db.get_tenant(p["tenant_id"])
    kode = sales_db.get_kode_referral(p["referral_code_id"]) if p.get("referral_code_id") else None
    return {**p, "nama_tenant": t["nama_barbershop"] if t else None,
            "kode_referral": kode["kode"] if kode else None}


@superadmin_router.get("/lifetime")
def list_lifetime(user: dict = Depends(require_superadmin)):
    return [_lengkapi_lifetime(p) for p in sales_db.list_lifetime_purchases()]


class BuatLifetimeBody(BaseModel):
    tenant_id: int
    package_kode: str
    amount: int
    provider: str = "faspay"
    virtual_account_number: str
    referral_code_id: int | None = None
    expired_at: str | None = None


@superadmin_router.post("/lifetime")
def buat_lifetime(body: BuatLifetimeBody, user: dict = Depends(require_superadmin)):
    t = tenant_db.get_tenant(body.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    try:
        hasil = sales_db.buat_lifetime_purchase(
            body.tenant_id, body.package_kode, body.amount, body.provider,
            body.virtual_account_number, referral_code_id=body.referral_code_id,
            expired_at=body.expired_at, dibuat_oleh=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "buat_transaksi_lifetime", tenant_id=body.tenant_id,
                               tenant_slug=t["slug"],
                               detail=f"package={body.package_kode}, amount={body.amount}")
    return _lengkapi_lifetime(hasil)


class UbahStatusLifetimeBody(BaseModel):
    payment_status: str


@superadmin_router.put("/lifetime/{id_}/status")
def ubah_status_lifetime(id_: int, body: UbahStatusLifetimeBody, user: dict = Depends(require_superadmin)):
    purchase = sales_db.get_lifetime_purchase(id_)
    if purchase is None:
        raise HTTPException(status_code=404, detail="Transaksi Lifetime tidak ditemukan.")
    try:
        hasil = sales_db.tandai_status_lifetime(id_, body.payment_status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    t = tenant_db.get_tenant(purchase["tenant_id"])
    superadmin_audit_db.catat(user["username"], "ubah_status_lifetime", tenant_id=purchase["tenant_id"],
                               tenant_slug=t["slug"] if t else None,
                               detail=f"lifetime_id={id_}, payment_status={body.payment_status}")
    return _lengkapi_lifetime(hasil)


# ============================= Portal Sales (read-only, milik sendiri) =============================

def _kode_milik_user(user: dict) -> dict:
    kode = sales_db.get_kode_referral_by_user(user["id"])
    if kode is None:
        raise HTTPException(status_code=404, detail="Akun ini belum dipasangkan kode referral apa pun.")
    return kode


@router.get("/me")
def sales_saya(user: dict = Depends(require_sales)):
    return _kode_milik_user(user)


@router.get("/me/tenants")
def sales_tenant_saya(user: dict = Depends(require_sales)):
    kode = _kode_milik_user(user)
    hasil = []
    for tenant_id in sales_db.list_tenant_ids_by_referral(kode["id"]):
        t = tenant_db.get_tenant(tenant_id)
        if t is None:
            continue
        sub = subscription_db.get_subscription(tenant_id)
        hasil.append({
            "tenant_id": tenant_id,
            "nama_barbershop": t["nama_barbershop"],
            "slug": t["slug"],
            "created_at": t.get("created_at"),
            "package": sub["package"] if sub else None,
            "status": sub["status"] if sub else None,
        })
    return hasil


@router.get("/me/komisi")
def sales_komisi_saya(user: dict = Depends(require_sales)):
    kode = _kode_milik_user(user)
    daftar = sales_db.list_komisi_by_referral_code(kode["id"])
    for k in daftar:
        t = tenant_db.get_tenant(k["tenant_id"])
        k["nama_tenant"] = t["nama_barbershop"] if t else None
    total_belum = sum(k["nominal_komisi"] for k in daftar if k["status"] == "belum_dibayar")
    total_sudah = sum(k["nominal_komisi"] for k in daftar if k["status"] == "sudah_dibayar")
    return {"komisi": daftar, "total_belum_dibayar": total_belum, "total_sudah_dibayar": total_sudah}
