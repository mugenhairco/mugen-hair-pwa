"""routers/booking_gateway_webhook.py — Implementasi Payment Gateway &
Riwayat Transaksi Multi-Tenant: Webhook Payment Gateway Booking Customer
=============================================================================
Endpoint PUBLIK (tanpa login sama sekali -- provider Payment Gateway
memanggil ini langsung dari server mereka) yang menerima notifikasi status
transaksi booking dan memperbarui status pembayaran/booking otomatis.
SENGAJA dipisah dari routers/booking.py (endpoint berlogin/publik biasa)
supaya endpoint yang menerima payload dari luar sistem tetap gampang
diaudit terpisah -- pola SAMA PERSIS dengan routers/billing_webhook.py
(langganan SaaS), TAPI TERPISAH TOTAL (webhook booking TIDAK mengimpor
billing_webhook.py sama sekali, dua modul independen).

Seluruh logika validasi (signature/order_id/amount) & cascade status ada
di booking_gateway_webhook.py (bukan di sini) -- file ini murni
menerjemahkan ValueError jadi HTTP 400. SELALU balas 200 untuk notifikasi
yang berhasil diproses (termasuk yang idempoten/duplikat) supaya provider
tidak retry terus menerus untuk sesuatu yang sebenarnya sudah beres."""

from fastapi import APIRouter, HTTPException, Request

import booking_gateway_webhook

public_router = APIRouter(prefix="/api/public/booking", tags=["booking-gateway-webhook"])


@public_router.post("/gateway-webhook")
async def gateway_webhook(request: Request):
    payload = await request.json()
    try:
        transaksi = booking_gateway_webhook.proses_notifikasi(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "transaction_id": transaksi["id"], "status": transaksi["status_pembayaran"]}
