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

SAMA seperti billing_gateway_client.py: provider Payment Gateway RESMI
proyek ini BELUM ditentukan/belum ada credential-nya saat file ini
ditulis. Bentuk konkret permintaan/respons di bawah (endpoint checkout
hosted, field token/redirect_url, formula signature) memakai protokol
Midtrans Snap/Core API sebagai ADAPTER PLACEHOLDER -- satu-satunya
protokol nyata yang sudah terbukti bekerja di proyek ini (lihat
billing_gateway_client.py). Anggap sebagai legacy/sementara -- begitu
provider resmi ditentukan & credential-nya datang, HANYA ISI fungsi-fungsi
ini yang perlu diganti mengikuti dokumentasi provider itu (pemanggil di
routers/booking.py & booking_gateway_webhook.py TIDAK perlu berubah).

Kredensial dibaca DINAMIS dari `payment_gateway_db.get_config()` (tabel
`settings`, dikelola Super Admin lewat UI) SETIAP fungsi di sini dipanggil.

- Server Key/Client Key kosong -> enabled=False. Endpoint checkout booking
  (routers/booking.py) WAJIB mengecek is_enabled() -- kalau tenant
  mengaktifkan metode "gateway" TAPI Super Admin belum mengisi kredensial
  platform-wide, booking dengan metode itu WAJIB ditolak (503) SEBELUM
  slot booking dibuat sama sekali, BUKAN dibuat lalu menggantung.
- Terisin -> enabled=True, buat_transaksi()/cek_status_transaksi()
  memanggil REST API provider sungguhan (Sandbox ATAU Production).

verifikasi_signature() TIDAK bergantung pada enabled() sama sekali --
fungsi MURNI, dipanggil booking_gateway_webhook.py untuk memvalidasi
SETIAP notifikasi masuk SEBELUM mempercayai isi payload-nya sama sekali --
status pembayaran booking TIDAK PERNAH boleh berubah dari klaim
customer/frontend, HANYA dari notifikasi resmi yang sudah tervalidasi di
sini."""

import base64

import gateway_client_base as core
import payment_gateway_db

_TIMEOUT_DETIK = 15


def is_enabled() -> bool:
    cfg = payment_gateway_db.get_config()
    return bool(cfg["pgw_server_key"] and cfg["pgw_client_key"])


def is_production() -> bool:
    return payment_gateway_db.get_config()["pgw_environment"] == "production"


def client_key() -> str:
    """Client Key MEMANG dirancang dipakai di frontend -- dipakai wizard
    booking publik (book_public.js) memuat script checkout hosted provider."""
    return payment_gateway_db.get_config()["pgw_client_key"]


def client_script_url() -> str:
    """URL script checkout hosted provider (dimuat wizard booking publik) --
    SAAT INI mengarah ke Snap.js Midtrans (adapter konkret placeholder,
    lihat catatan modul), ganti sesuai dokumentasi provider resmi begitu
    ditentukan."""
    is_prod = payment_gateway_db.get_config()["pgw_environment"] == "production"
    return "https://app.midtrans.com/snap/snap.js" if is_prod else "https://app.sandbox.midtrans.com/snap/snap.js"


def _checkout_base_url(is_prod: bool) -> str:
    return "https://app.midtrans.com/snap/v1" if is_prod else "https://app.sandbox.midtrans.com/snap/v1"


def _status_base_url(is_prod: bool) -> str:
    return "https://api.midtrans.com/v2" if is_prod else "https://api.sandbox.midtrans.com/v2"


def _auth_header(server_key: str) -> dict:
    token = base64.b64encode(f"{server_key}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json", "Accept": "application/json"}


def buat_transaksi(order_id: str, gross_amount: int, item_details: list,
                    customer_details: dict = None, enabled_channels: list = None) -> dict:
    """Buat transaksi checkout hosted untuk SATU booking -- return
    {"token", "redirect_url"} dari provider. `enabled_channels` (opsional):
    daftar channel yang diizinkan tampil di halaman checkout hosted (lihat
    payment_gateway_db.CHANNEL_LABEL untuk kode channel yang didukung) --
    SESUAI konfigurasi Super Admin (pgw_metode_aktif), dikirim apa adanya
    ke provider lewat parameter `enabled_payments` (nama parameter Snap
    API -- adapter konkret placeholder, ganti sesuai provider resmi nanti).
    Melempar GatewayNotConfiguredError kalau belum dikonfigurasi,
    GatewayTimeoutError/GatewayRequestError kalau providernya sendiri
    bermasalah -- pemanggil (routers/booking.py) tetap WAJIB mengecek
    is_enabled() lebih dulu supaya bisa balas 503 yang jelas."""
    cfg = payment_gateway_db.get_config()
    if not (cfg["pgw_server_key"] and cfg["pgw_client_key"]):
        raise core.GatewayNotConfiguredError("Payment Gateway booking belum dikonfigurasi Super Admin (Server Key/Client Key kosong).")
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": int(gross_amount)},
        "item_details": item_details,
    }
    if customer_details:
        payload["customer_details"] = customer_details
    if enabled_channels:
        payload["enabled_payments"] = enabled_channels
    data = core.post_json(f"{_checkout_base_url(cfg['pgw_environment'] == 'production')}/transactions", payload,
                           _auth_header(cfg["pgw_server_key"]), timeout=_TIMEOUT_DETIK)
    return {"token": data["token"], "redirect_url": data["redirect_url"]}


def cek_status_transaksi(order_id: str) -> dict:
    """GET status transaksi (Core API, BUKAN checkout API) -- dipakai untuk
    rekonsiliasi manual/troubleshooting (mis. webhook tidak pernah sampai),
    TIDAK dipakai di alur normal (webhook handler sudah cukup dari
    notifikasi POST langsung)."""
    cfg = payment_gateway_db.get_config()
    if not (cfg["pgw_server_key"] and cfg["pgw_client_key"]):
        raise core.GatewayNotConfiguredError("Payment Gateway booking belum dikonfigurasi Super Admin (Server Key/Client Key kosong).")
    return core.get_json(f"{_status_base_url(cfg['pgw_environment'] == 'production')}/{order_id}/status",
                          _auth_header(cfg["pgw_server_key"]), timeout=_TIMEOUT_DETIK)


def verifikasi_signature(order_id: str, status_code: str, gross_amount: str, signature_key: str) -> bool:
    """SHA512(order_id + status_code + gross_amount + ServerKey) -- formula
    SESUAI dokumentasi provider saat ini (adapter konkret placeholder,
    lihat catatan modul). `gross_amount` HARUS string PERSIS seperti
    dikirim provider di payload notifikasi."""
    server_key = payment_gateway_db.get_config()["pgw_server_key"]
    return core.verify_sha512([order_id, status_code, gross_amount], server_key, signature_key)
