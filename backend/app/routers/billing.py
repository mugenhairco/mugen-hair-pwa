"""routers/billing.py — FONDASI Multi-Tenant Phase 4: Billing & Payment (Midtrans)
=============================================================================
Dua router dalam SATU file ini (pola sama seperti routers/subscription.py):

1. `router` (prefix `/api/billing`) — Owner SATU TENANT sendiri
   (require_admin, sama seperti /api/subscription/me di Phase 3): lihat
   katalog paket aktif untuk upgrade, checkout Midtrans Snap, riwayat
   invoice/pembayaran miliknya sendiri.
2. `superadmin_router` (prefix `/api/superadmin/billing`) — KHUSUS
   Super Admin: konfigurasi atribut subscription_packages (nama/harga/
   durasi/status/urutan/deskripsi/limit pemakaian), katalog fitur
   (subscription_features + checkbox per paket), dan MONITORING seluruh
   invoice/pembayaran SEMUA tenant. SETIAP aksi ubah konfigurasi tercatat
   ke superadmin_audit_log, pola sama persis dengan routers/subscription.py.

Webhook Midtrans (publik, tanpa login) ada di file TERPISAH
(routers/billing_webhook.py, modul berikutnya) -- BUKAN di sini, supaya
endpoint publik yang menerima payload dari luar tetap gampang diaudit
terpisah dari endpoint berlogin."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import billing_db
import billing_invoice_db
import midtrans_client
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
def config_midtrans(user: dict = Depends(require_admin)):
    """Info PUBLIK Midtrans (Client Key MEMANG dirancang dipakai di
    frontend, beda dengan Server Key yang tidak pernah dikirim ke client
    sama sekali) -- dipakai frontend memutuskan mau memuat snap.js
    Sandbox atau Production, dan `enabled=False` dipakai menampilkan
    pesan "Billing belum aktif" alih-alih tombol checkout yang pasti
    gagal kalau Super Admin belum mengisi env var MIDTRANS_*."""
    return {
        "enabled": midtrans_client.IS_ENABLED,
        "client_key": midtrans_client.MIDTRANS_CLIENT_KEY,
        "is_production": midtrans_client.MIDTRANS_IS_PRODUCTION,
        "snap_js_url": midtrans_client.SNAP_JS_URL,
    }


class CheckoutBody(BaseModel):
    package_id: int


@router.post("/checkout")
def checkout(body: CheckoutBody, user: dict = Depends(require_admin)):
    if not midtrans_client.IS_ENABLED:
        raise HTTPException(status_code=503,
                             detail="Pembayaran online belum aktif -- hubungi penyedia layanan.")
    paket = billing_db.get_package(body.package_id)
    if paket is None or not paket["aktif"]:
        raise HTTPException(status_code=422, detail="Paket tidak ditemukan atau tidak aktif.")
    if paket["harga"] <= 0:
        raise HTTPException(status_code=422, detail="Paket ini tidak memerlukan pembayaran.")

    tenant = tenant_db.get_tenant(user["tenant_id"])
    order_id = billing_invoice_db.buat_order_id(user["tenant_id"])
    item_details = [{
        "id": paket["kode"], "price": paket["harga"], "quantity": 1,
        "name": f"Paket {paket['nama']} ({paket['durasi_hari']} hari)"[:50],
    }]
    customer_details = {"first_name": (tenant["nama_barbershop"] if tenant else "Owner")[:50]}
    try:
        hasil_midtrans = midtrans_client.buat_transaksi_snap(
            order_id, paket["harga"], item_details, customer_details=customer_details,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Gagal membuat transaksi pembayaran: {e}")

    invoice = billing_invoice_db.buat_invoice(
        order_id, user["tenant_id"], paket,
        snap_token=hasil_midtrans["token"], snap_redirect_url=hasil_midtrans["redirect_url"],
    )
    return invoice


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


# ============================= Super Admin =============================


@superadmin_router.get("/packages")
def list_packages(user: dict = Depends(require_superadmin)):
    return billing_db.list_packages()


class PackageUpdateBody(BaseModel):
    nama: str | None = None
    harga: int | None = None
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


class FeatureBody(BaseModel):
    kode: str
    nama: str
    deskripsi: str = ""


@superadmin_router.post("/features")
def tambah_feature(body: FeatureBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = billing_db.create_feature(body.kode, body.nama, body.deskripsi)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "tambah_fitur_billing", detail=f"kode={hasil['kode']}")
    return hasil


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
