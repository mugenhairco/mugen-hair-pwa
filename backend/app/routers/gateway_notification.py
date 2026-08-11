"""routers/gateway_notification.py — Implementasi Payment Gateway & Riwayat
Transaksi Multi-Tenant: satu pintu masuk Payment Notification & Return URL
Faspay
=============================================================================
Konfirmasi RESMI tim Faspay: SATU Merchant ID (37070, akun "RivoiR") hanya
bisa mendaftarkan SATU Payment Notification URL dan SATU Return URL --
DUA endpoint publik di sini itulah yang benar-benar didaftarkan ke Faspay.
Endpoint webhook lama (routers/booking_gateway_webhook.py,
routers/billing_webhook.py) TETAP ADA & berfungsi penuh -- BUKAN yang
didaftarkan Faspay sekarang, tapi siap dipakai kalau nanti booking &
langganan SaaS dipisah ke Merchant ID/provider berbeda (lihat catatan
lengkap di gateway_notification_dispatch.py).

Endpoint di sini MURNI: (1) terjemahkan ValueError dari dispatcher jadi
HTTP 400 + bangun respons berformat resmi Faspay, (2) tampilkan halaman
Return URL statis TANPA PERNAH membaca/mempercayai status pembayaran dari
query string -- dokumentasi Faspay sendiri: "Don't ever update the payment
status on the merchant to this process". NOL logika bisnis di kedua
endpoint ini."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

import gateway_notification_dispatch

public_router = APIRouter(prefix="/api/public/gateway", tags=["gateway-notification"])


@public_router.post("/faspay-notification")
async def faspay_notification(request: Request):
    """URL Payment Notification yang didaftarkan ke Faspay untuk Merchant
    ID 37070 -- Faspay mengirim notifikasi hingga 3x kalau percobaan
    pertama tidak dapat respons OK, jadi endpoint ini SELALU balas 200
    untuk notifikasi yang berhasil diproses (termasuk idempoten/basi --
    lihat guard urutan status di booking_gateway_webhook.py/
    billing_webhook.py), HANYA 400 untuk validasi yang benar-benar gagal
    (signature/bill_no/amount tidak valid)."""
    payload = await request.json()
    try:
        gateway_notification_dispatch.proses(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Format respons SESUAI dokumentasi resmi Faspay Payment Notification --
    # dibangun dari payload yang MASUK (bukan hasil dari modul tujuan)
    # supaya bentuknya konsisten terlepas notifikasi ini untuk booking atau
    # langganan SaaS.
    return {
        "response": "Payment Notification",
        "trx_id": payload.get("trx_id"),
        "merchant_id": payload.get("merchant_id"),
        "bill_no": payload.get("bill_no"),
        "response_code": "00",
        "response_desc": "Success",
        "response_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _halaman_relay(pesan: str) -> str:
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><title>Pembayaran Diproses</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;background:#F5F7FA;color:#1a1a1a;text-align:center;padding:24px;}}
.box{{max-width:420px;}}
h1{{font-size:20px;margin-bottom:8px;}}
p{{color:#555;line-height:1.5;}}
button{{margin-top:16px;padding:10px 24px;border:none;border-radius:8px;background:#111;color:#fff;
font-size:15px;cursor:pointer;}}
</style></head>
<body><div class="box">
<h1>✓ Pembayaran Diproses</h1>
<p>{pesan}</p>
<button type="button" onclick="window.close()">Tutup Tab</button>
</div>
<script>setTimeout(function () {{ try {{ window.close(); }} catch (e) {{}} }}, 3000);</script>
</body></html>"""


@public_router.get("/faspay-return")
async def faspay_return(bill_no: str = None):
    """Return URL STATIS yang didaftarkan ke Faspay (konfirmasi resmi tim
    Faspay: hanya satu bisa didaftarkan per Merchant ID -- dan menurut
    konfirmasi mereka HANYA benar-benar dipakai untuk channel Kartu Kredit,
    channel lain seperti QRIS/VA/e-wallet tidak pernah mendarat di sini).

    MURNI tampilan -- endpoint ini TIDAK PERNAH membaca/mempercayai `status`
    dari query string Faspay untuk apa pun (dokumentasi Faspay sendiri:
    "Don't ever update the payment status on the merchant to this
    process"). book_public.js/billing.js membuka halaman checkout Faspay
    lewat window.open() (tab baru) -- tab ASLI tetap polling status lewat
    endpoint publik yang sudah ada, jadi halaman ini cukup memberi tahu
    pengguna boleh menutup tab (dan mencoba menutup sendiri)."""
    bn = bill_no or ""
    if bn.startswith("BOOK-"):
        pesan = "Status booking Anda akan diperbarui otomatis di tab booking begitu dikonfirmasi. Anda bisa menutup tab ini."
    elif bn.startswith("SUB-"):
        pesan = "Status pembayaran akan diperbarui otomatis di halaman Billing begitu dikonfirmasi. Anda bisa menutup tab ini."
    else:
        pesan = "Terima kasih atas pembayaran Anda."
    return HTMLResponse(content=_halaman_relay(pesan))
