"""billing_gateway_client.py — Klien Payment Gateway untuk Langganan SaaS
=============================================================================
CATATAN ARSITEKTUR (Implementasi Payment Gateway & Riwayat Transaksi
Multi-Tenant): SATU provider Payment Gateway dipakai untuk KEDUA jenis
transaksi (langganan SaaS & booking customer), TAPI diimplementasikan
sebagai DUA modul TERPISAH TOTAL -- file ini (langganan SaaS) vs
payment_gateway_client.py (booking customer). Yang BOLEH dipakai bersama
HANYA komponen level-rendah (gateway_client_base.py) -- business logic/
webhook processing/riwayat transaksi/pengelolaan pembayaran TETAP terpisah
total, TIDAK saling bergantung sama sekali.

PROVIDER RESMI: Faspay Xpress v4 (kredensial development dikonfirmasi tim
Faspay -- Merchant ID 37070, akun "RivoiR", SATU Merchant ID dipakai untuk
KEDUA sistem sekarang -- lihat gateway_notification_dispatch.py untuk
kenapa ini tidak melanggar pemisahan business logic). Dokumentasi resmi:
https://docs.faspay.co.id/merchant-integration/api-reference-1/xpress/xpress-version-4

Kredensial dibaca DINAMIS dari `billing_gateway_db.get_config()` (tabel
`settings`, dikelola Super Admin lewat UI) SETIAP fungsi di sini dipanggil.
Field generik proyek ini dipetakan ke istilah Faspay (lihat catatan lengkap
di billing_gateway_db.py):
- `merchant_id` -> Merchant ID Faspay
- `server_key`  -> User ID Faspay
- `secret_key`  -> Password Faspay
- `client_key`/`api_key` -> TIDAK dipakai (tidak ada JS SDK, checkout murni
  redirect ke halaman Faspay, lihat client_script_url() di bawah)

- Merchant ID/Server Key/Secret Key kosong -> enabled=False. Endpoint
  checkout (routers/billing.py) WAJIB mengecek is_enabled() dan balas 503
  dengan pesan jelas.
- Terisi -> enabled=True, buat_transaksi() memanggil REST API Faspay
  Xpress v4 sungguhan (Sandbox ATAU Production).

verifikasi_signature() TIDAK bergantung pada enabled() sama sekali --
fungsi MURNI, dipanggil billing_webhook.py untuk memvalidasi SETIAP
notifikasi masuk SEBELUM mempercayai isi payload-nya sama sekali.

CATATAN keterbatasan (disepakati eksplisit, JANGAN diimplementasikan
berdasarkan tebakan): dokumentasi resmi Faspay Xpress v4 yang dipakai
belum mencakup endpoint Inquiry/Check Status -- cek_status_transaksi() di
bawah SENGAJA melempar error jelas, fitur "Cek Ulang ke Provider" untuk
langganan SaaS nonaktif sementara sampai dokumentasi resmi endpoint itu
tersedia."""

from datetime import datetime, timedelta

import billing_gateway_db
import gateway_client_base as core

_TIMEOUT_DETIK = 15

_SANDBOX_URL = "https://xpress-sandbox.faspay.co.id/v4/post"
# BELUM dikonfirmasi tim Faspay secara eksplisit -- lihat catatan yang sama
# di payment_gateway_client.py, WAJIB dikonfirmasi ulang sebelum cutover
# Production sungguhan.
_PRODUCTION_URL = "https://xpress.faspay.co.id/v4/post"

# SATU Return URL statis (konfirmasi resmi tim Faspay: hanya satu bisa
# didaftarkan per Merchant ID) -- dipakai BERSAMA payment_gateway_client.py
# (nilai yang SAMA, didefinisikan terpisah di masing-masing modul supaya
# kedua modul tetap tidak saling import satu sama lain). Endpoint ini murni
# tampilan (relay), TIDAK PERNAH mengubah status pembayaran -- lihat
# routers/gateway_notification.py.
RETURN_URL_RELAY = "https://api.rivoirsett.com/api/public/gateway/faspay-return"

_EMAIL_FALLBACK = "support@rivoirsett.com"
_MSISDN_FALLBACK = "628000000000"
_MERCHANT_LOGO = "https://rivoirsett.com/icons/icon-192.png"


def is_enabled() -> bool:
    return billing_gateway_db.get_config()["enabled"]


def is_production() -> bool:
    return billing_gateway_db.get_config()["environment"] == "production"


def client_key() -> str | None:
    """Faspay Xpress v4 TIDAK punya JS SDK/client-side key -- checkout
    murni redirect penuh ke halaman Faspay. Return None supaya frontend
    (billing.js) mengenali "tidak ada script checkout" dan jatuh ke jalur
    redirect_url."""
    return None


def client_script_url() -> str | None:
    """Lihat catatan client_key()."""
    return None


def _base_url(is_prod: bool) -> str:
    return _PRODUCTION_URL if is_prod else _SANDBOX_URL


def buat_transaksi(order_id: str, gross_amount: int, item_details: list,
                    customer_details: dict = None) -> dict:
    """Buat transaksi checkout Faspay Xpress v4 -- return {"token": None,
    "redirect_url": ...} (Faspay tidak punya konsep token checkout seperti
    Snap). Melempar GatewayNotConfiguredError kalau belum dikonfigurasi,
    GatewayTimeoutError/GatewayRequestError kalau providernya sendiri
    bermasalah -- pemanggil (routers/billing.py) tetap WAJIB mengecek
    is_enabled() lebih dulu supaya bisa balas 503 yang jelas."""
    cfg = billing_gateway_db.get_config()
    if not cfg["enabled"]:
        raise core.GatewayNotConfiguredError("Payment Gateway langganan SaaS belum dikonfigurasi Super Admin (Merchant ID/Server Key/Secret Key kosong).")

    customer_details = customer_details or {}
    cust_name = (customer_details.get("first_name") or "Owner").strip()[:32]
    msisdn = (customer_details.get("phone") or "").strip() or _MSISDN_FALLBACK
    email = (customer_details.get("email") or "").strip() or _EMAIL_FALLBACK
    cust_no = msisdn

    sekarang = datetime.now()
    bill_total = int(gross_amount)
    payload = {
        "merchant_id": str(cfg["merchant_id"]),
        "bill_no": order_id,
        "bill_date": sekarang.strftime("%Y-%m-%d %H:%M:%S"),
        "bill_expired": (sekarang + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
        "bill_desc": f"Pembayaran langganan #{order_id}"[:128],
        "bill_gross": str(bill_total),
        "bill_miscfee": "0",
        "bill_total": str(bill_total),
        "cust_no": cust_no,
        "cust_name": cust_name,
        "return_url": RETURN_URL_RELAY,
        "msisdn": msisdn,
        "email": email,
        "item": [
            {"product": str(it.get("name") or "Langganan")[:50], "qty": str(it.get("quantity") or 1), "amount": str(it["price"])}
            for it in item_details
        ],
        "merchant_logo": _MERCHANT_LOGO,
        "signature": core.sign_sha1_of_md5([cfg["server_key"], cfg["secret_key"], order_id, str(bill_total)]),
    }
    data = core.post_json(_base_url(cfg["environment"] == "production"), payload,
                           {"Content-Type": "application/json"}, timeout=_TIMEOUT_DETIK)
    if str(data.get("response_code")) != "00":
        raise core.GatewayRequestError(f"Faspay menolak permintaan checkout: {data.get('response_desc')}")
    return {"token": None, "redirect_url": data["redirect_url"]}


def cek_status_transaksi(order_id: str) -> dict:
    """SENGAJA belum diimplementasikan -- lihat catatan modul soal
    dokumentasi resmi Faspay Xpress v4 yang belum mencakup endpoint
    Inquiry/Check Status. Fitur "Cek Ulang ke Provider" akan melempar error
    ini apa adanya (dibungkus 502 oleh router) sampai dokumentasi resmi
    endpoint ini tersedia."""
    raise core.GatewayError(
        "Faspay Xpress: endpoint Inquiry/Check Status belum tersedia di dokumentasi resmi -- "
        "fitur \"Cek Ulang ke Provider\" nonaktif sementara. Notifikasi webhook Faspay tetap "
        "otomatis dikirim ulang hingga 3x, tunggu notifikasi resmi berikutnya."
    )


def verifikasi_signature(bill_no: str, payment_status_code: str, signature_key: str) -> bool:
    """SHA1(MD5(user_id + password + bill_no + payment_status_code)) --
    formula RESMI Faspay untuk Payment Notification/Return URL. Return
    False kalau kredensial belum dikonfigurasi."""
    cfg = billing_gateway_db.get_config()
    if not (cfg["server_key"] and cfg["secret_key"]):
        return False
    return core.verify_sha1_of_md5([cfg["server_key"], cfg["secret_key"], bill_no, payment_status_code], signature_key)
