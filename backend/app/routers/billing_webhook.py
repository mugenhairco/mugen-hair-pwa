"""routers/billing_webhook.py — FONDASI Multi-Tenant Phase 4: Webhook Payment Gateway (Langganan SaaS)
=============================================================================
Endpoint PUBLIK (tanpa login sama sekali -- provider Payment Gateway
memanggil ini langsung dari server mereka, tidak ada sesi user) yang
menerima notifikasi status transaksi dan mengaktifkan subscription
otomatis begitu pembayaran berhasil. SENGAJA dipisah dari routers/billing.py
(endpoint berlogin) supaya endpoint yang menerima payload dari luar sistem
tetap gampang diaudit terpisah.

URL `/midtrans-webhook` SENGAJA TIDAK diganti nama walau kode di baliknya
sudah generik (lihat billing_gateway_client.py) -- provider produksi
mungkin sudah didaftarkan memakai URL ini di dashboard mereka, mengubahnya
berisiko mematuskan webhook yang sedang berjalan tanpa peringatan apa pun.
Kalau kelak pindah provider dengan URL webhook baru, tambahkan endpoint
BARU di sini alih-alih mengganti yang lama.

Seluruh logika validasi (signature/order_id/amount) & aktivasi ada di
billing_webhook.py (bukan di sini) -- file ini murni menerjemahkan
ValueError jadi HTTP 400. SELALU balas 200 untuk notifikasi yang berhasil
diproses (termasuk yang idempoten/duplikat) supaya provider tidak retry
terus menerus untuk sesuatu yang sebenarnya sudah beres."""

from fastapi import APIRouter, HTTPException, Request

import billing_webhook

public_router = APIRouter(prefix="/api/public/billing", tags=["billing-webhook"])


@public_router.post("/midtrans-webhook")
async def gateway_webhook(request: Request):
    payload = await request.json()
    try:
        invoice = billing_webhook.proses_notifikasi(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "invoice_id": invoice["id"], "status": invoice["status"]}
