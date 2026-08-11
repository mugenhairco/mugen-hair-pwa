"""gateway_notification_dispatch.py — Implementasi Payment Gateway & Riwayat
Transaksi Multi-Tenant: satu pintu masuk Payment Notification Faspay
=============================================================================
Konfirmasi RESMI tim Faspay: SATU Merchant ID (37070, akun "RivoiR") HANYA
bisa mendaftarkan SATU Payment Notification URL dan SATU Return URL --
TIDAK BISA didaftarkan terpisah untuk booking customer vs langganan SaaS
walau kedua sistem itu tetap dirancang terpisah total secara arsitektur.

File ini MURNI dispatcher -- NOL logika bisnis, NOL validasi signature/
amount, NOL penulisan database sama sekali. SATU-SATUNYA yang dilakukan:
baca prefix `bill_no` (order_id) lalu teruskan payload MENTAH ke salah satu
proses_notifikasi() yang SUDAH ADA dan tetap terpisah total
(booking_gateway_webhook.py untuk "BOOK-", billing_webhook.py untuk
"SUB-") -- masing-masing modul itu SENDIRI yang memvalidasi signature/
order_id/amount dan menulis status, PERSIS seperti kalau dipanggil lewat
endpoint webhook khusus modul itu (routers/booking_gateway_webhook.py /
routers/billing_webhook.py, KEDUANYA tetap ada & berfungsi penuh, lihat
routers/gateway_notification.py).

KENAPA INI TIDAK MELANGGAR PEMISAHAN BUSINESS LOGIC/WEBHOOK PROCESSING
YANG DIMINTA: dispatcher ini tidak pernah membaca/menulis
booking_payment_transactions atau subscription_invoices, tidak pernah
memanggil booking_db/billing_invoice_db langsung, tidak pernah tahu
formula signature atau aturan pemetaan status Faspay -- SEMUA itu tetap
100% di dalam modul masing-masing. Kalau nanti booking & langganan SaaS
dipisah ke Merchant ID atau provider yang berbeda, HANYA konfigurasi
provider per modul yang berubah (payment_gateway_db.py/billing_gateway_db.py)
-- dispatcher ini dan kedua modul webhook TIDAK PERNAH perlu disentuh."""

import billing_webhook
import booking_gateway_webhook

PREFIX_BOOKING = "BOOK-"
PREFIX_LANGGANAN = "SUB-"


def proses(payload: dict) -> dict:
    """Return dict transaksi/invoice terbaru dari modul tujuan. Melempar
    ValueError kalau `bill_no` tidak dikenali formatnya ATAU validasi di
    modul tujuan gagal -- routers/gateway_notification.py menerjemahkan
    ValueError jadi HTTP 400, SAMA seperti kedua endpoint webhook lama."""
    bill_no = str(payload.get("bill_no") or "")
    if bill_no.startswith(PREFIX_BOOKING):
        return booking_gateway_webhook.proses_notifikasi(payload)
    if bill_no.startswith(PREFIX_LANGGANAN):
        return billing_webhook.proses_notifikasi(payload)
    raise ValueError(f"bill_no tidak dikenali sebagai transaksi booking maupun langganan: {bill_no}")
