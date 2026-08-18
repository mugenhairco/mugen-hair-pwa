"""routers/billing.py — FONDASI Multi-Tenant Phase 4: Billing & Payment (Langganan SaaS)
=============================================================================
Dua router dalam SATU file ini (pola sama seperti routers/subscription.py):

1. `router` (prefix `/api/billing`) — Owner SATU TENANT sendiri
   (require_admin, sama seperti /api/subscription/me di Phase 3): lihat
   katalog paket aktif untuk upgrade, checkout Payment Gateway (langganan
   SaaS), riwayat invoice/pembayaran miliknya sendiri.
2. `superadmin_router` (prefix `/api/superadmin/billing`) — KHUSUS
   Super Admin: konfigurasi atribut subscription_packages (nama/harga/
   durasi/status/urutan/deskripsi/limit pemakaian), katalog fitur
   (subscription_features + checkbox per paket), dan MONITORING seluruh
   invoice/pembayaran SEMUA tenant. SETIAP aksi ubah konfigurasi tercatat
   ke superadmin_audit_log, pola sama persis dengan routers/subscription.py.

Webhook Payment Gateway (publik, tanpa login) ada di file TERPISAH
(routers/billing_webhook.py, modul berikutnya) -- BUKAN di sini, supaya
endpoint publik yang menerima payload dari luar tetap gampang diaudit
terpisah dari endpoint berlogin. Modul client sungguhan ada di
billing_gateway_client.py -- TERPISAH TOTAL dari payment_gateway_client.py
(Payment Gateway booking customer), lihat catatan lengkap di modul itu
soal kenapa dua jenis transaksi ini dipisah walau bisa jadi satu provider
yang sama."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import billing_db
import billing_gateway_client
import billing_gateway_db
import billing_invoice_db
import billing_limits
import billing_webhook
import gateway_client_base
import subscription_db
import superadmin_audit_db
import tenant_db
from auth import require_admin, require_superadmin

router = APIRouter(prefix="/api/billing", tags=["billing"])
superadmin_router = APIRouter(prefix="/api/superadmin/billing", tags=["billing-superadmin"])


# ============================= Owner =============================

@router.get("/packages")
def daftar_paket_aktif(user: dict = Depends(require_admin)):
    """Katalog paket yang BOLEH dibeli/upgrade -- hanya yang aktif=1, ikut
    membawa daftar fitur checkbox milik masing-masing paket supaya frontend
    tidak perlu query terpisah per paket (mis. halaman pricing/upgrade)."""
    hasil = []
    for paket in billing_db.list_packages(hanya_aktif=True):
        baris = dict(paket)
        baris["fitur"] = billing_db.get_package_features(paket["id"])
        hasil.append(baris)
    return hasil


@router.get("/config")
def config_billing_gateway(user: dict = Depends(require_admin)):
    """Info PUBLIK Payment Gateway langganan SaaS (Client Key MEMANG
    dirancang dipakai di frontend, beda dengan Server Key yang tidak
    pernah dikirim ke client sama sekali) -- dipakai frontend memutuskan
    mau memuat script checkout Sandbox atau Production, dan
    `enabled=False` dipakai menampilkan pesan "Billing belum aktif"
    alih-alih tombol checkout yang pasti gagal kalau Super Admin belum
    mengisi kredensial (lihat GET/PUT /api/superadmin/billing/gateway-config
    di bawah)."""
    return {
        "enabled": billing_gateway_client.is_enabled(),
        "client_key": billing_gateway_client.client_key(),
        "is_production": billing_gateway_client.is_production(),
        "checkout_script_url": billing_gateway_client.client_script_url(),
    }


class CheckoutBody(BaseModel):
    package_id: int
    # FITUR Landing Page & Pricing (paket 6 bulan, DAN paket Tahunan): "bulanan"
    # (default, TIDAK mengubah perilaku lama sama sekali), "6bulan", atau
    # "tahunan" -- lihat blok siklus di bawah untuk cara efektif harga/
    # durasi-nya dihitung. TIDAK ADA nilai lain yang diterima (divalidasi
    # manual, BUKAN Literal[...] Pydantic, supaya pesan errornya tetap
    # format {"detail": "..."} polos yang sudah konsisten dipakai endpoint
    # lain di proyek ini).
    siklus: str = "bulanan"


@router.post("/checkout")
def checkout(body: CheckoutBody, user: dict = Depends(require_admin)):
    if not billing_gateway_client.is_enabled():
        raise HTTPException(status_code=503,
                             detail="Pembayaran online belum aktif -- hubungi penyedia layanan.")
    if body.siklus not in ("bulanan", "6bulan", "tahunan"):
        raise HTTPException(status_code=422, detail="Siklus langganan tidak dikenal.")
    paket = billing_db.get_package(body.package_id)
    if paket is None or not paket["aktif"]:
        raise HTTPException(status_code=422, detail="Paket tidak ditemukan atau tidak aktif.")
    if paket["harga"] <= 0:
        raise HTTPException(status_code=422, detail="Paket ini tidak memerlukan pembayaran.")

    # FITUR Landing Page & Pricing (paket 6 bulan, DAN paket Tahunan): siklus
    # "6bulan"/"tahunan" mengganti harga/durasi EFEKTIF yang dipakai checkout
    # ini (harga_6bulan/harga_tahunan, durasi SELALU durasi_hari*6 atau *12 --
    # lihat billing_db.py kenapa tidak ada kolom durasi terpisah) SEBELUM
    # diteruskan ke Payment Gateway & buat_invoice() di bawah -- KEDUANYA
    # murni menyalin apa pun yang ada di dict `paket` ini sebagai snapshot
    # (lihat billing_invoice_db.buat_invoice()), jadi TIDAK ADA perubahan
    # kode di billing_gateway_client.py/billing_invoice_db.py/
    # billing_webhook.py sama sekali untuk mendukung siklus baru ini --
    # masa aktif subscription (periode_selesai = periode_mulai + durasi_hari
    # invoice, lihat billing_webhook.py) otomatis ikut durasi efektif ini.
    if body.siklus == "6bulan":
        if not paket.get("harga_6bulan"):
            raise HTTPException(status_code=422, detail="Paket ini tidak menawarkan siklus 6 bulan.")
        paket = {**paket, "harga": paket["harga_6bulan"], "durasi_hari": paket["durasi_hari"] * 6}
    elif body.siklus == "tahunan":
        if not paket.get("harga_tahunan"):
            raise HTTPException(status_code=422, detail="Paket ini tidak menawarkan siklus tahunan.")
        paket = {**paket, "harga": paket["harga_tahunan"], "durasi_hari": paket["durasi_hari"] * 12}

    tenant = tenant_db.get_tenant(user["tenant_id"])
    order_id = billing_invoice_db.buat_order_id(user["tenant_id"])
    item_details = [{
        "id": paket["kode"], "price": paket["harga"], "quantity": 1,
        "name": f"Paket {paket['nama']} ({paket['durasi_hari']} hari)"[:50],
    }]
    # AUDIT (perbaikan pasca-audit kesiapan): "phone"/"email" ditambahkan
    # (SEBELUMNYA hanya "first_name") -- Faspay Xpress v4 mewajibkan
    # msisdn+email di request checkout (lihat billing_gateway_client.py).
    # tenant["whatsapp"]/tenant["email"] diisi Owner saat registrasi
    # (tenant_db.set_registrant_info()) -- boleh kosong untuk tenant lama,
    # client-nya sendiri sudah punya fallback aman kalau kosong.
    customer_details = {
        "first_name": (tenant["nama_barbershop"] if tenant else "Owner")[:50],
        "phone": tenant.get("whatsapp") if tenant else None,
        "email": tenant.get("email") if tenant else None,
    }
    try:
        hasil_gateway = billing_gateway_client.buat_transaksi(
            order_id, paket["harga"], item_details, customer_details=customer_details,
        )
    except gateway_client_base.GatewayError as e:
        raise HTTPException(status_code=502, detail=f"Gagal membuat transaksi pembayaran: {e}")

    invoice = billing_invoice_db.buat_invoice(
        order_id, user["tenant_id"], paket,
        snap_token=hasil_gateway["token"], snap_redirect_url=hasil_gateway["redirect_url"],
    )
    return invoice


class DowngradeBody(BaseModel):
    package_id: int


@router.post("/downgrade")
def downgrade(body: DowngradeBody, user: dict = Depends(require_admin)):
    """Downgrade TIDAK lewat Payment Gateway (pindah ke paket yang lebih murah/
    sama, tidak ada pembayaran) -- SESUAI KEPUTUSAN cakupan Phase 4:
    diblokir TOTAL selama pemakaian sekarang melebihi limit paket tujuan,
    TIDAK ADA penonaktifan otomatis apa pun (lihat billing_limits.py).
    Upgrade (paket lebih mahal/urutan lebih tinggi) SENGAJA ditolak di sini
    -- harus lewat /checkout supaya benar-benar dibayar."""
    target = billing_db.get_package(body.package_id)
    if target is None or not target["aktif"]:
        raise HTTPException(status_code=422, detail="Paket tidak ditemukan atau tidak aktif.")

    sub = subscription_db.get_subscription(user["tenant_id"])
    current = billing_db.get_package_by_kode(sub["package"]) if sub else None
    if current is not None and target["urutan"] > current["urutan"]:
        raise HTTPException(status_code=422,
                             detail="Ini upgrade paket -- gunakan proses checkout pembayaran, bukan downgrade.")

    pelanggaran = billing_limits.evaluasi_downgrade(user["tenant_id"], target)
    if pelanggaran:
        raise HTTPException(
            status_code=422,
            detail="Downgrade diblokir, pemakaian saat ini melebihi batas paket tujuan -- kurangi dulu: "
                   + "; ".join(pelanggaran),
        )

    try:
        hasil = subscription_db.update_package(user["tenant_id"], target["kode"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return hasil


def _pastikan_invoice_tenant_sama(user: dict, invoice: dict | None):
    if invoice is None or invoice.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Invoice tidak ditemukan.")


@router.get("/invoices")
def daftar_invoice_saya(user: dict = Depends(require_admin)):
    return billing_invoice_db.list_invoices(tenant_id=user["tenant_id"])


@router.get("/invoices/{invoice_id}")
def detail_invoice_saya(invoice_id: int, user: dict = Depends(require_admin)):
    invoice = billing_invoice_db.get_invoice(invoice_id)
    _pastikan_invoice_tenant_sama(user, invoice)
    return invoice


@router.post("/invoices/{invoice_id}/cek-ulang")
def cek_ulang_invoice(invoice_id: int, user: dict = Depends(require_admin)):
    """AUDIT (Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant --
    perbaikan pasca-audit kesiapan): jalur RESMI untuk invoice yang macet
    karena webhook TIDAK PERNAH sampai sama sekali. TIDAK PERNAH menerima
    klaim status dari Owner -- endpoint ini murni memicu server memanggil
    ULANG API provider (Server Key sendiri) lalu menerapkan hasilnya lewat
    jalur SAMA PERSIS dengan webhook resmi (lihat billing_webhook.py::
    rekonsiliasi_manual())."""
    try:
        return billing_webhook.rekonsiliasi_manual(invoice_id, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except gateway_client_base.GatewayError as e:
        raise HTTPException(status_code=502, detail=f"Gagal menghubungi Payment Gateway: {e}")


# ============================= Super Admin =============================


# ---- Payment Gateway Billing SaaS (platform-wide, provider-agnostic) ----
# TERPISAH TOTAL dari Payment Gateway Booking Customer (payment_gateway_db.py/
# routers/payment_gateway.py, prefix /api/superadmin/payment-gateway) --
# kredensial ini untuk Owner tenant membayar LANGGANAN platform (Free/
# Basic/Pro/Enterprise), bukan untuk customer membayar booking. Field-nya
# SENGAJA generik (bukan spesifik Midtrans) -- lihat billing_gateway_db.py
# untuk penjelasan lengkap kenapa TIDAK semua field wajib diisi.
@superadmin_router.get("/gateway-config")
def ambil_gateway_config(user: dict = Depends(require_superadmin)):
    return billing_gateway_db.get_config()


class BillingGatewayConfigBody(BaseModel):
    api_key: str | None = None
    server_key: str | None = None
    client_key: str | None = None
    merchant_id: str | None = None
    secret_key: str | None = None
    webhook_url: str | None = None
    environment: str | None = None


@superadmin_router.put("/gateway-config")
def ubah_gateway_config(body: BillingGatewayConfigBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = billing_gateway_db.update_config(
            api_key=body.api_key, server_key=body.server_key, client_key=body.client_key,
            merchant_id=body.merchant_id, secret_key=body.secret_key, webhook_url=body.webhook_url,
            environment=body.environment,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_config_billing_gateway",
                               detail=f"environment={hasil['environment']}, enabled={hasil['enabled']}")
    return hasil


@superadmin_router.get("/packages")
def list_packages(user: dict = Depends(require_superadmin)):
    return billing_db.list_packages()


class PackageUpdateBody(BaseModel):
    nama: str | None = None
    harga: int | None = None
    harga_6bulan: int | None = None
    harga_tahunan: int | None = None
    durasi_hari: int | None = None
    aktif: bool | None = None
    urutan: int | None = None
    deskripsi: str | None = None
    max_barber: int | None = None
    max_user: int | None = None
    max_layanan: int | None = None
    max_booking: int | None = None
    max_cabang: int | None = None


@superadmin_router.put("/packages/{package_id}")
def ubah_package(package_id: int, body: PackageUpdateBody, user: dict = Depends(require_superadmin)):
    # exclude_unset: field yang TIDAK dikirim body TIDAK ikut diubah (beda
    # dengan None eksplisit, mis. max_barber=null -- sengaja jadi "tidak
    # dibatasi" -- lihat billing_db.LIMIT_FIELDS).
    fields = body.model_dump(exclude_unset=True)
    try:
        hasil = billing_db.update_package(package_id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_paket_billing", detail=f"package_id={package_id}, fields={fields}")
    return hasil


# ============================= Katalog Fitur =============================

@superadmin_router.get("/features")
def list_features(user: dict = Depends(require_superadmin)):
    return billing_db.list_features()


# REVISI (audit "fitur hardcode di Superadmin", diminta Owner): endpoint
# POST /features (bikin kode fitur baru bebas) DIHAPUS TOTAL -- Super Admin
# sekarang HANYA bisa mencentang/hapus-centang dari daftar tetap
# billing_db._FITUR_DEFAULT (lihat docstring lengkap di sana) lewat PUT
# /packages/{id}/features di bawah, TIDAK BISA lagi mengarang nama fitur
# sendiri yang tidak punya fungsi nyata apa pun di kode.


class FeatureUpdateBody(BaseModel):
    nama: str | None = None
    deskripsi: str | None = None
    aktif: bool | None = None
    urutan: int | None = None


@superadmin_router.put("/features/{feature_id}")
def ubah_feature(feature_id: int, body: FeatureUpdateBody, user: dict = Depends(require_superadmin)):
    fields = body.model_dump(exclude_unset=True)
    try:
        hasil = billing_db.update_feature(feature_id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_fitur_billing", detail=f"feature_id={feature_id}, fields={fields}")
    return hasil


@superadmin_router.delete("/features/{feature_id}")
def hapus_feature(feature_id: int, user: dict = Depends(require_superadmin)):
    feature = billing_db.get_feature(feature_id)
    try:
        billing_db.delete_feature(feature_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "hapus_fitur_billing",
                               detail=f"feature_id={feature_id}, kode={feature['kode'] if feature else None}")
    return {"ok": True}


@superadmin_router.get("/packages/{package_id}/features")
def list_package_features(package_id: int, user: dict = Depends(require_superadmin)):
    return billing_db.get_package_features(package_id)


class PackageFeaturesBody(BaseModel):
    feature_ids: list[int]


@superadmin_router.put("/packages/{package_id}/features")
def ubah_package_features(package_id: int, body: PackageFeaturesBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = billing_db.set_package_features(package_id, body.feature_ids)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_fitur_paket_billing",
                               detail=f"package_id={package_id}, feature_ids={body.feature_ids}")
    return hasil


# ============================= Monitoring Invoice/Pembayaran (semua tenant) =============================

@superadmin_router.get("/invoices")
def list_invoices_semua_tenant(user: dict = Depends(require_superadmin)):
    """Digabung dengan slug/nama_barbershop tiap tenant, pola sama seperti
    routers/subscription.py::list_subscriptions() -- supaya Dashboard Super
    Admin tidak perlu query terpisah per tenant."""
    tenants_by_id = {t["id"]: t for t in tenant_db.list_tenants()}
    hasil = []
    for inv in billing_invoice_db.list_invoices():
        t = tenants_by_id.get(inv["tenant_id"])
        baris = dict(inv)
        baris["tenant_slug"] = t["slug"] if t else None
        baris["nama_barbershop"] = t["nama_barbershop"] if t else None
        hasil.append(baris)
    return hasil


@superadmin_router.get("/invoices/{invoice_id}")
def detail_invoice_superadmin(invoice_id: int, user: dict = Depends(require_superadmin)):
    invoice = billing_invoice_db.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice tidak ditemukan.")
    return invoice
