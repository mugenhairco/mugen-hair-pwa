"""payment_gateway_client.py — Klien Payment Gateway untuk Booking Customer
=============================================================================
CATATAN ARSITEKTUR (Implementasi Payment Gateway & Riwayat Transaksi
Multi-Tenant): sistem ini memakai SATU provider Payment Gateway yang boleh
sama untuk KEDUA jenis transaksi (langganan SaaS & booking customer), TAPI
diimplementasikan sebagai DUA modul TERPISAH TOTAL -- file ini (booking)
vs billing_gateway_client.py (langganan SaaS). Yang BOLEH dipakai bersama
HANYA komponen level-rendah (gateway_client_base.py: HTTP client, error
handling, verifikasi signature generik) -- business logic/webhook
processing/riwayat transaksi/pengelolaan pembayaran TETAP terpisah total,
TIDAK saling bergantung sama sekali. Mengubah salah satu modul TIDAK PERNAH
memengaruhi modul yang lain.

PROVIDER RESMI: Faspay Xpress v4 (konfirmasi kredensial development dari
tim Faspay -- Merchant ID 37070, akun "RivoiR"). Dokumentasi resmi:
https://docs.faspay.co.id/merchant-integration/api-reference-1/xpress/xpress-version-4

Kredensial dibaca DINAMIS dari `payment_gateway_db.get_config()` (tabel
`settings`, dikelola Super Admin lewat UI) SETIAP fungsi di sini dipanggil.
Field generik proyek ini dipetakan ke istilah Faspay sebagai berikut
(field DB TIDAK diganti nama -- supaya provider lain di masa depan tetap
bisa memakai slot yang sama tanpa migrasi skema):
- `pgw_merchant_id` -> Merchant ID Faspay
- `pgw_server_key`  -> User ID Faspay
- `pgw_secret_key`  -> Password Faspay
- `pgw_client_key`/`pgw_api_key` -> TIDAK dipakai Faspay Xpress (tidak ada
  JS SDK/client-side key -- checkout murni redirect ke halaman Faspay,
  lihat client_script_url() di bawah)

- Merchant ID/User ID/Password kosong -> enabled=False. Endpoint checkout
  booking (routers/booking.py) WAJIB mengecek is_enabled() -- kalau tenant
  mengaktifkan metode "gateway" TAPI Super Admin belum mengisi kredensial
  platform-wide, booking dengan metode itu WAJIB ditolak (503) SEBELUM
  slot booking dibuat sama sekali, BUKAN dibuat lalu menggantung.
- Terisi -> enabled=True, buat_transaksi() memanggil REST API Faspay
  Xpress v4 sungguhan (Sandbox ATAU Production).

verifikasi_signature() TIDAK bergantung pada enabled() sama sekali --
fungsi MURNI, dipanggil booking_gateway_webhook.py untuk memvalidasi
SETIAP notifikasi masuk SEBELUM mempercayai isi payload-nya sama sekali --
status pembayaran booking TIDAK PERNAH boleh berubah dari klaim
customer/frontend, HANYA dari notifikasi resmi yang sudah tervalidasi di
sini.

CATATAN keterbatasan (disepakati eksplisit, JANGAN diimplementasikan
berdasarkan tebakan): dokumentasi resmi Faspay Xpress v4 yang dipakai
belum mencakup endpoint Inquiry/Check Status -- cek_status_transaksi() di
bawah SENGAJA melempar error jelas (bukan menebak endpoint), fitur "Cek
Ulang ke Provider" untuk booking nonaktif sementara sampai dokumentasi
resmi endpoint itu tersedia. `payment_channel` (daftar channel yang
ditampilkan di halaman Faspay) SENGAJA TIDAK dikirim di buat_transaksi()
-- dokumentasi contoh hanya memberi kode angka tanpa tabel arti lengkap;
kalau tidak dikirim, Faspay menampilkan SEMUA channel aktif di akun
Merchant ini (perilaku default resmi, bukan tebakan)."""

from datetime import timedelta

import gateway_client_base as core
import payment_gateway_db

_TIMEOUT_DETIK = 15

# Konfirmasi resmi tim Faspay: Sandbox development.
_SANDBOX_URL = "https://xpress-sandbox.faspay.co.id/v4/post"
# Konfirmasi resmi tim Faspay (chat WhatsApp, daftar lengkap endpoint
# Production Faspay -- Xpress V4 termasuk di dalamnya): URL ini SAMA PERSIS
# dengan dugaan sebelumnya (pola penamaan Sandbox -> Production), sekarang
# resmi terkonfirmasi, aman dipakai untuk cutover Production.
_PRODUCTION_URL = "https://xpress.faspay.co.id/v4/post"

# Konfirmasi resmi tim Faspay: HANYA SATU Return URL statis bisa
# didaftarkan per Merchant ID -- endpoint ini murni tampilan (relay),
# TIDAK PERNAH mengubah status pembayaran (lihat routers/gateway_notification.py).
# Field `return_url` di request checkout tetap WAJIB diisi (Mandatory di
# dokumentasi) walau menurut konfirmasi tim Faspay hanya benar-benar dipakai
# untuk channel Kartu Kredit -- channel lain (QRIS/VA/e-wallet/dst) tidak
# pernah mendarat di sini.
RETURN_URL_RELAY = "https://api.rivoirsett.com/api/public/gateway/faspay-return"

# Faspay mewajibkan field `email` (Mandatory) tapi form booking publik
# SENGAJA hanya meminta Nama + WhatsApp (keputusan eksplisit -- TIDAK
# menambah field email di UI booking) -- fallback ini dipakai HANYA untuk
# memenuhi syarat API Faspay, TIDAK PERNAH dikirim/ditampilkan ke customer.
_EMAIL_FALLBACK = "support@rivoirsett.com"
# Faspay mewajibkan `msisdn` (Mandatory) -- fallback ini HANYA dipakai kalau
# benar-benar tidak ada nomor tersimpan sama sekali (seharusnya tidak
# pernah terjadi untuk booking, customer_whatsapp sudah wajib diisi di form).
_MSISDN_FALLBACK = "628000000000"
_MERCHANT_LOGO = "https://rivoirsett.com/icons/icon-192.png"


def is_enabled() -> bool:
    cfg = payment_gateway_db.get_config()
    return bool(cfg["pgw_merchant_id"] and cfg["pgw_server_key"] and cfg["pgw_secret_key"])


def is_production() -> bool:
    return payment_gateway_db.get_config()["pgw_environment"] == "production"


def client_key() -> str | None:
    """Faspay Xpress v4 TIDAK punya JS SDK/client-side key -- checkout
    murni redirect penuh ke halaman Faspay (lihat buat_transaksi()).
    Return None (bukan string kosong) supaya frontend (book_public.js)
    mengenali "tidak ada script checkout untuk dimuat" dan otomatis jatuh
    ke jalur redirect_url yang SUDAH ADA (tidak perlu perubahan frontend)."""
    return None


def client_script_url() -> str | None:
    """Lihat catatan client_key() -- Faspay Xpress v4 tidak butuh script
    apa pun dimuat di browser."""
    return None


def _base_url(is_prod: bool) -> str:
    return _PRODUCTION_URL if is_prod else _SANDBOX_URL


def buat_transaksi(order_id: str, gross_amount: int, item_details: list,
                    customer_details: dict = None, enabled_channels: list = None) -> dict:
    """Buat transaksi checkout Faspay Xpress v4 untuk SATU booking -- return
    {"token": None, "redirect_url": ...} (Faspay tidak punya konsep token
    checkout seperti Snap, HANYA redirect_url penuh ke halaman Faspay).
    `enabled_channels` SENGAJA TIDAK dipakai (lihat catatan modul soal
    `payment_channel`). Melempar GatewayNotConfiguredError kalau belum
    dikonfigurasi, GatewayTimeoutError/GatewayRequestError kalau
    providernya sendiri bermasalah -- pemanggil (routers/booking.py) tetap
    WAJIB mengecek is_enabled() lebih dulu supaya bisa balas 503 yang jelas."""
    cfg = payment_gateway_db.get_config()
    merchant_id, user_id, password = cfg["pgw_merchant_id"], cfg["pgw_server_key"], cfg["pgw_secret_key"]
    if not (merchant_id and user_id and password):
        raise core.GatewayNotConfiguredError("Payment Gateway booking belum dikonfigurasi Super Admin (Merchant ID/User ID/Password kosong).")

    customer_details = customer_details or {}
    cust_name = (customer_details.get("first_name") or "Customer").strip()[:32]
    msisdn = (customer_details.get("phone") or "").strip() or _MSISDN_FALLBACK
    email = (customer_details.get("email") or "").strip() or _EMAIL_FALLBACK
    cust_no = msisdn

    sekarang = core.now_wib()
    bill_total = int(gross_amount)
    payload = {
        "merchant_id": str(merchant_id),
        "bill_no": order_id,
        "bill_date": sekarang.strftime("%Y-%m-%d %H:%M:%S"),
        "bill_expired": (sekarang + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
        "bill_desc": f"Pembayaran booking #{order_id}"[:128],
        "bill_gross": str(bill_total),
        "bill_miscfee": "0",
        "bill_total": str(bill_total),
        "cust_no": cust_no,
        "cust_name": cust_name,
        "return_url": RETURN_URL_RELAY,
        "msisdn": msisdn,
        "email": email,
        "item": [
            {"product": core.sanitize_item_product(it.get("name"), fallback="Layanan"),
             "qty": str(it.get("quantity") or 1), "amount": str(it["price"])}
            for it in item_details
        ],
        "merchant_logo": _MERCHANT_LOGO,
        "signature": core.sign_sha1_of_md5([user_id, password, order_id, str(bill_total)]),
    }
    data = core.post_json(_base_url(cfg["pgw_environment"] == "production"), payload,
                           {"Content-Type": "application/json"}, timeout=_TIMEOUT_DETIK)
    if str(data.get("response_code")) != "00":
        raise core.GatewayRequestError(f"Faspay menolak permintaan checkout: {data.get('response_desc')}")
    return {"token": None, "redirect_url": data["redirect_url"]}


def cek_status_transaksi(order_id: str) -> dict:
    """SENGAJA belum diimplementasikan -- dokumentasi resmi Faspay Xpress
    v4 yang dipakai TIDAK mencakup endpoint Inquiry/Check Status (keputusan
    eksplisit: jangan menebak endpoint). Fitur "Cek Ulang ke Provider"
    (routers/booking.py::cek_ulang_transaksi_gateway() ->
    booking_gateway_webhook.rekonsiliasi_manual()) akan melempar error ini
    apa adanya (dibungkus 502 oleh router) sampai dokumentasi resmi endpoint
    ini tersedia dan fungsi ini diisi sungguhan."""
    raise core.GatewayError(
        "Faspay Xpress: endpoint Inquiry/Check Status belum tersedia di dokumentasi resmi -- "
        "fitur \"Cek Ulang ke Provider\" nonaktif sementara. Notifikasi webhook Faspay tetap "
        "otomatis dikirim ulang hingga 3x, tunggu notifikasi resmi berikutnya."
    )


def verifikasi_signature(bill_no: str, payment_status_code: str, signature_key: str) -> bool:
    """SHA1(MD5(user_id + password + bill_no + payment_status_code)) --
    formula RESMI Faspay untuk Payment Notification/Return URL (BEDA dari
    formula signature checkout, lihat buat_transaksi()). Return False kalau
    kredensial belum dikonfigurasi -- TIDAK ADA cara notifikasi dianggap
    valid tanpa kredensial untuk membandingkannya."""
    cfg = payment_gateway_db.get_config()
    user_id, password = cfg["pgw_server_key"], cfg["pgw_secret_key"]
    if not (user_id and password):
        return False
    return core.verify_sha1_of_md5([user_id, password, bill_no, payment_status_code], signature_key)
