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
import payment_provider_client
import snap_advance_db
import snap_payment_db
import snap_webhook
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
        # Migrasi Faspay SNAP Advance: checkout langganan SaaS sekarang
        # lewat SNAP (VA/QRIS), BUKAN lagi Xpress v4 -- `enabled` HARUS
        # dibaca dari payment_provider_client.py (seam dinamis), bukan
        # billing_gateway_client.py (Xpress) lagi, supaya Owner tidak
        # melihat "Billing belum aktif" selamanya pasca migrasi ini.
        "enabled": payment_provider_client.is_enabled(),
        "channel_aktif": payment_provider_client.channel_aktif() if payment_provider_client.is_enabled() else [],
        # Migrasi multi-bank VA: bukan lagi satu label tunggal -- daftar
        # {channelCode: label} bank yang Super Admin aktifkan, Owner memilih
        # salah satu (lihat CheckoutBody.bank_code di bawah).
        "va_bank_aktif": payment_provider_client.va_bank_aktif(),
        "qris_label": payment_provider_client.channel_label("qris"),
        # Field lama (SNAP tidak punya script/hosted widget, sama seperti
        # Xpress dulu) -- TETAP dikirim None supaya cabang window.snap.pay()
        # lawas di billing.js tetap tidak pernah terpicu, TIDAK PERLU
        # diubah di frontend.
        "client_key": None,
        "is_production": payment_provider_client.is_production(),
        "checkout_script_url": None,
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
    # Migrasi Faspay SNAP Advance: billing SEBELUMNYA tidak punya pilihan
    # metode sama sekali (Xpress v4 = satu jalur checkout tunggal) --
    # SEKARANG WAJIB diisi ("va"/"qris") karena SNAP butuh tahu channel di
    # muka (tidak ada halaman hosted seperti Xpress dulu yang menawarkan
    # semua channel sekaligus).
    channel: str
    # Fitur multi-bank VA: WAJIB diisi kalau channel="va" (bank yang dipilih
    # Owner), divalidasi terhadap payment_provider_client.va_bank_aktif().
    bank_code: str | None = None


@router.post("/checkout")
def checkout(body: CheckoutBody, user: dict = Depends(require_admin)):
    if not payment_provider_client.is_enabled():
        raise HTTPException(status_code=503,
                             detail="Pembayaran online belum aktif -- hubungi penyedia layanan.")
    if body.channel not in payment_provider_client.channel_aktif():
        raise HTTPException(status_code=422, detail="Channel pembayaran tidak tersedia -- silakan pilih channel lain.")
    if body.channel == "va" and body.bank_code not in payment_provider_client.va_bank_aktif():
        raise HTTPException(status_code=422, detail="Bank VA tidak tersedia -- silakan pilih bank lain.")
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
    # tenant["whatsapp"] diisi Owner saat registrasi
    # (tenant_db.set_registrant_info()) -- boleh kosong untuk tenant lama.
    # QRIS SNAP mewajibkan nomor WhatsApp (lihat snap_advance_client.py::
    # buat_transaksi_qris() -- melempar ValueError bare kalau kosong, BUKAN
    # GatewayError, jadi TIDAK tertangkap except di bawah) -- ditolak rapi
    # di sini SEBELUM invoice dibuat sama sekali.
    if body.channel == "qris" and not (tenant and tenant.get("whatsapp")):
        raise HTTPException(status_code=422, detail="Nomor WhatsApp toko wajib diisi untuk pembayaran QRIS -- lengkapi di Pengaturan.")

    # Migrasi Faspay SNAP Advance: invoice dibuat LEBIH DULU (BUKAN setelah
    # panggilan provider sukses seperti Xpress dulu) -- snap_payment_db.buat_transaksi()
    # butuh subscription_invoice_id yang sudah ada. snap_token/snap_redirect_url
    # (kolom lawas Xpress) SENGAJA dibiarkan kosong -- SNAP tidak punya
    # padanannya, detail VA/QR tersimpan di snap_payment_transactions.
    order_id = billing_invoice_db.buat_order_id(user["tenant_id"])
    invoice = billing_invoice_db.buat_invoice(order_id, user["tenant_id"], paket)
    row = snap_payment_db.buat_transaksi(
        snap_payment_db.TRANSACTION_TYPE_SAAS_BILLING, user["tenant_id"], paket["harga"],
        subscription_invoice_id=invoice["id"], channel=body.channel,
        channel_code=body.bank_code if body.channel == "va" else None,
    )
    customer_details = {
        "nama": (tenant["nama_barbershop"] if tenant else "Owner")[:128],
        "whatsapp": tenant.get("whatsapp") if tenant else None,
    }
    try:
        hasil = payment_provider_client.buat_transaksi(
            body.channel, row["payment_reference"], paket["harga"], customer_details,
            channel_code=body.bank_code if body.channel == "va" else None,
        )
    except gateway_client_base.GatewayError as e:
        snap_payment_db.update_status(row["id"], "FAILED", sumber="create_gagal")
        billing_invoice_db.update_invoice(invoice["id"], status="denied")
        raise HTTPException(status_code=502, detail=f"Gagal membuat transaksi pembayaran: {e}")

    snap_payment_db.catat_hasil_create_transaction(
        row["id"], provider_transaction_id=hasil.get("provider_transaction_id"),
        va_number=hasil.get("va_number"), qr_content=hasil.get("qr_content"), qr_url=hasil.get("qr_url"),
        expired_at=hasil.get("expired_at"), provider_response=hasil.get("provider_response"), status="PENDING",
    )
    return {
        **invoice, "channel": body.channel, "payment_reference": row["payment_reference"],
        "va_number": hasil.get("va_number"),
        "va_bank_label": snap_advance_db.VA_CHANNEL_CODE_LABEL.get(hasil.get("channel_code")),
        "qr_url": hasil.get("qr_url"),
        "qr_content": hasil.get("qr_content"), "expired_at": hasil.get("expired_at"),
    }


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
    # Migrasi Faspay SNAP Advance: lengkapi nomor VA/QR kalau invoice ini
    # dibayar lewat SNAP (None untuk invoice lawas Xpress, atau invoice
    # SNAP yang belum sempat buat transaksi) -- supaya Owner yang reload
    # halaman di tengah pembayaran tetap melihat nomor VA/QR-nya, BUKAN
    # hanya di respons checkout awal. SENGAJA TIDAK dilakukan di
    # daftar_invoice_saya() (list) -- list tidak butuh VA/QR, hanya status,
    # menghindari N+1 query per baris.
    transaksi_snap = snap_payment_db.get_transaksi_terkini_untuk_subscription_invoice(invoice_id)
    if transaksi_snap is not None:
        invoice = {
            **invoice, "channel": transaksi_snap["channel"], "payment_reference": transaksi_snap["payment_reference"],
            "va_number": transaksi_snap["va_number"],
            "va_bank_label": snap_advance_db.VA_CHANNEL_CODE_LABEL.get(transaksi_snap["channel_code"]),
            "qr_url": transaksi_snap["qr_url"],
            "qr_content": transaksi_snap["qr_content"], "expired_at": transaksi_snap["expired_at"],
        }
    return invoice


@router.post("/invoices/{invoice_id}/cek-ulang")
def cek_ulang_invoice(invoice_id: int, user: dict = Depends(require_admin)):
    """AUDIT (Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant --
    perbaikan pasca-audit kesiapan): jalur RESMI untuk invoice yang macet
    karena webhook TIDAK PERNAH sampai sama sekali. TIDAK PERNAH menerima
    klaim status dari Owner -- endpoint ini murni memicu server memanggil
    ULANG API provider (Server Key sendiri) lalu menerapkan hasilnya lewat
    jalur SAMA PERSIS dengan webhook resmi (lihat billing_webhook.py::
    rekonsiliasi_manual()). Migrasi Faspay SNAP Advance: invoice yang
    dibayar lewat SNAP dicek ulang lewat snap_webhook.rekonsiliasi_manual()
    (transaksi_id, BUKAN invoice_id -- ditemukan lewat
    snap_payment_db.get_transaksi_terkini_untuk_subscription_invoice()),
    invoice Xpress lawas tetap lewat jalur billing_webhook lama."""
    transaksi_snap = snap_payment_db.get_transaksi_terkini_untuk_subscription_invoice(invoice_id)
    try:
        if transaksi_snap is not None:
            return snap_webhook.rekonsiliasi_manual(transaksi_snap["id"], tenant_id=user["tenant_id"])
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
