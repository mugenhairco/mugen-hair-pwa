"""routers/sales.py — Program Afiliasi Sales/Marketing (sales_db.py)
=============================================================================
Dua router dalam SATU file ini (pola sama seperti routers/subscription.py):

1. `superadmin_router` (prefix `/api/superadmin/sales`) — KHUSUS role
   'superadmin': merekrut akun sales (+ kode referral pertamanya
   sekaligus), mengubah persentase komisi (fleksibel per kode), menempel
   kode referral manual ke tenant tertentu, melihat SELURUH komisi lintas
   sales + toggle status bayar, dan membuat transaksi Lisensi Lifetime
   lewat gateway Faspay SNAP Advance NYATA (menirukan routers/billing.py::
   checkout(), lihat sales_db.py untuk efek samping begitu webhook
   menandainya lunas: upgrade subscription + komisi otomatis). SETIAP
   aksi tercatat ke superadmin_audit_log, pola sama persis routers/subscription.py.

2. `router` (prefix `/api/sales`) — KHUSUS role 'sales' (require_sales):
   Portal Sales miliknya sendiri, read-only -- kode referral miliknya,
   daftar tenant yang terdaftar lewat kode itu, dan rincian komisinya
   (termasuk mana yang sudah/belum dibayar). TIDAK ADA endpoint tulis di
   sini -- sales TIDAK BISA mengubah persentase komisi atau menandai
   komisinya sendiri lunas (hanya Super Admin, poin 1 di atas)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth_db
import billing_db
import gateway_client_base
import payment_provider_client
import sales_db
import snap_advance_db
import snap_payment_db
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
# REVISI (desain awal keliru -- Faspay tidak punya dashboard manusia untuk
# membuat VA, VA hanya bisa dibuat lewat API): transaksi Lifetime SEKARANG
# dibayar lewat gateway SNAP Advance NYATA yang SAMA dipakai checkout
# langganan biasa (payment_provider_client.py), pola di bawah ini MENIRU
# PERSIS routers/billing.py::checkout() -- lihat sales_db.py untuk alasan
# lengkap kenapa tenant_lifetime_purchases sekarang hanya mencatat intent
# (VA/QR nyata ada di snap_payment_transactions).

def _lengkapi_lifetime(p: dict) -> dict:
    t = tenant_db.get_tenant(p["tenant_id"])
    kode = sales_db.get_kode_referral(p["referral_code_id"]) if p.get("referral_code_id") else None
    transaksi = snap_payment_db.get_transaksi_terkini_untuk_lifetime_purchase(p["id"])
    return {
        **p, "nama_tenant": t["nama_barbershop"] if t else None,
        "kode_referral": kode["kode"] if kode else None,
        "channel": transaksi["channel"] if transaksi else None,
        "channel_code": transaksi["channel_code"] if transaksi else None,
        "va_bank_label": snap_advance_db.VA_CHANNEL_CODE_LABEL.get(transaksi["channel_code"]) if transaksi else None,
        "va_number": transaksi["va_number"] if transaksi else None,
        "qr_url": transaksi["qr_url"] if transaksi else None,
        "qr_content": transaksi["qr_content"] if transaksi else None,
        "snap_status": transaksi["status"] if transaksi else None,
        "snap_expired_at": transaksi["expired_at"] if transaksi else None,
    }


@superadmin_router.get("/lifetime")
def list_lifetime(user: dict = Depends(require_superadmin)):
    return [_lengkapi_lifetime(p) for p in sales_db.list_lifetime_purchases()]


class BuatLifetimeBody(BaseModel):
    tenant_id: int
    package_kode: str
    # Nominal BOLEH dikosongkan -- diisi otomatis dari katalog
    # subscription_packages.harga_lifetime (lihat billing_db.py), Super
    # Admin hanya perlu override manual kalau harga transaksi ini memang
    # sengaja beda dari katalog.
    amount: int | None = None
    channel: str
    bank_code: str | None = None
    referral_code_id: int | None = None


@superadmin_router.post("/lifetime")
def buat_lifetime(body: BuatLifetimeBody, user: dict = Depends(require_superadmin)):
    t = tenant_db.get_tenant(body.tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    if not payment_provider_client.is_enabled():
        raise HTTPException(status_code=503, detail="Pembayaran online belum aktif -- hubungi penyedia layanan.")
    if body.channel not in payment_provider_client.channel_aktif():
        raise HTTPException(status_code=422, detail="Channel pembayaran tidak tersedia -- silakan pilih channel lain.")
    if body.channel == "va" and body.bank_code not in payment_provider_client.va_bank_aktif():
        raise HTTPException(status_code=422, detail="Bank VA tidak tersedia -- silakan pilih bank lain.")
    if body.channel == "qris" and not t.get("whatsapp"):
        raise HTTPException(status_code=422, detail="Nomor WhatsApp tenant wajib diisi untuk pembayaran QRIS.")

    paket = billing_db.get_package_by_kode(body.package_kode)
    if paket is None:
        raise HTTPException(status_code=422, detail="Paket tidak ditemukan.")
    amount = body.amount if body.amount is not None else paket.get("harga_lifetime")
    if not amount or amount <= 0:
        raise HTTPException(status_code=422,
                             detail="Nominal Lifetime belum diatur untuk paket ini -- isi harga_lifetime di tab Paket, atau isi nominal manual.")

    try:
        purchase = sales_db.buat_lifetime_purchase(
            body.tenant_id, body.package_kode, amount,
            referral_code_id=body.referral_code_id, dibuat_oleh=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    row = snap_payment_db.buat_transaksi(
        snap_payment_db.TRANSACTION_TYPE_LIFETIME_LICENSE, body.tenant_id, amount,
        lifetime_purchase_id=purchase["id"], channel=body.channel,
        channel_code=body.bank_code if body.channel == "va" else None,
    )
    customer_details = {
        "nama": (t["nama_barbershop"] or "Tenant")[:128],
        "whatsapp": t.get("whatsapp"),
    }
    try:
        hasil = payment_provider_client.buat_transaksi(
            body.channel, row["payment_reference"], amount, customer_details,
            channel_code=body.bank_code if body.channel == "va" else None,
        )
    except gateway_client_base.GatewayError as e:
        snap_payment_db.update_status(row["id"], "FAILED", sumber="create_gagal")
        sales_db.tandai_status_lifetime(purchase["id"], "failed")
        raise HTTPException(status_code=502, detail=f"Gagal membuat transaksi pembayaran: {e}")

    snap_payment_db.catat_hasil_create_transaction(
        row["id"], provider_transaction_id=hasil.get("provider_transaction_id"),
        va_number=hasil.get("va_number"), qr_content=hasil.get("qr_content"), qr_url=hasil.get("qr_url"),
        expired_at=hasil.get("expired_at"), provider_response=hasil.get("provider_response"), status="PENDING",
    )
    superadmin_audit_db.catat(user["username"], "buat_transaksi_lifetime", tenant_id=body.tenant_id,
                               tenant_slug=t["slug"],
                               detail=f"package={body.package_kode}, amount={amount}")
    return _lengkapi_lifetime(sales_db.get_lifetime_purchase(purchase["id"]))


class UbahStatusLifetimeBody(BaseModel):
    payment_status: str


# Status yang berarti "transaksi ini SELESAI, tidak lagi menunggu
# pembayaran" -- dipakai di bawah untuk ikut menghentikan transaksi SNAP
# yang masih menggantung (lihat ubah_status_lifetime()).
_PAYMENT_STATUS_KE_SNAP_STATUS = {"cancelled": "CANCELLED", "failed": "FAILED", "expired": "EXPIRED"}


@superadmin_router.put("/lifetime/{id_}/status")
def ubah_status_lifetime(id_: int, body: UbahStatusLifetimeBody, user: dict = Depends(require_superadmin)):
    """Koreksi MANUAL -- status lunas SEKARANG normalnya otomatis lewat
    webhook SNAP Advance (lihat snap_webhook.py::_cascade_lifetime_license()),
    endpoint ini tetap dipertahankan untuk kasus pengecualian (mis. Super
    Admin menerima pembayaran lewat jalur lain di luar gateway, atau perlu
    membatalkan transaksi yang macet -- tombol "Batalkan" di Dashboard
    Sales & Referral lewat endpoint ini juga).

    Membatalkan/menggagalkan (`payment_status` masuk
    `_PAYMENT_STATUS_KE_SNAP_STATUS`) ikut menghentikan transaksi SNAP
    Advance terkait (kalau masih aktif) -- SEKADAR mencegah webhook yang
    telat datang mengira transaksi ini masih perlu diproses (TIDAK bisa
    membatalkan transfer bank yang SUDAH terlanjur dilakukan tenant --
    itu perlu ditangani manual/refund di luar aplikasi). sales_db.
    tandai_status_lifetime() SENDIRI sudah idempoten terhadap status final
    (lihat PAYMENT_STATUS_FINAL) -- lapis INI murni jaga-jaga supaya sisi
    gateway juga konsisten, bukan satu-satunya proteksi."""
    purchase = sales_db.get_lifetime_purchase(id_)
    if purchase is None:
        raise HTTPException(status_code=404, detail="Transaksi Lifetime tidak ditemukan.")
    try:
        hasil = sales_db.tandai_status_lifetime(id_, body.payment_status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    snap_status_baru = _PAYMENT_STATUS_KE_SNAP_STATUS.get(body.payment_status)
    if snap_status_baru:
        transaksi = snap_payment_db.get_transaksi_terkini_untuk_lifetime_purchase(id_)
        if transaksi is not None and transaksi["status"] not in snap_payment_db.STATUS_FINAL:
            snap_payment_db.update_status(transaksi["id"], snap_status_baru, sumber="dibatalkan_manual_superadmin")

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
