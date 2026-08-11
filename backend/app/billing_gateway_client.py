"""billing_gateway_client.py — Klien Payment Gateway untuk Langganan SaaS
=============================================================================
REVISI (proyek TIDAK terikat satu provider): file ini SEBELUMNYA bernama
`midtrans_client.py` -- direname supaya tidak lagi mengasumsikan Midtrans
sebagai provider TETAP proyek ini. Kredensial (lihat billing_gateway_db.py,
field generik: provider/environment/api_key/server_key/client_key/
merchant_id/secret_key/webhook_url) dan HTTP/error handling (gateway_client_base.py)
sudah generik -- SATU-SATUNYA bagian yang masih spesifik satu provider di
bawah ini adalah BENTUK KONKRET permintaan/respons (endpoint Snap/Core API,
field `token`/`redirect_url`, formula signature order_id+status_code+
gross_amount+ServerKey) -- itu KARENA provider Payment Gateway resmi belum
ditentukan/belum ada credential-nya saat file ini ditulis, dan bentuk ini
SATU-SATUNYA protokol nyata yang sudah terbukti bekerja & teruji penuh di
proyek ini. Anggap fungsi-fungsi di bawah sebagai ADAPTER KONKRET SAAT INI,
BUKAN kontrak permanen -- begitu provider resmi ditentukan & credential-nya
datang, HANYA ISI fungsi-fungsi ini yang perlu diganti mengikuti dokumentasi
provider itu (nama fungsi/pemanggil di routers/billing.py & billing_webhook.py
TIDAK perlu berubah sama sekali, itulah gunanya modul terpisah ini).

Kredensial dibaca DINAMIS dari `billing_gateway_db.get_config()` (tabel
`settings`, dikelola Super Admin lewat UI) SETIAP fungsi di sini dipanggil
-- BUKAN konstanta module-level -- supaya perubahan kredensial lewat Super
Admin langsung berlaku SAAT ITU JUGA, tanpa perlu restart/redeploy proses
backend.

- Server Key/Client Key kosong -> enabled=False. Endpoint checkout
  (routers/billing.py) WAJIB mengecek is_enabled() dan balas 503 dengan
  pesan jelas -- modul ini TIDAK PERNAH membuat proses gagal boot hanya
  karena kredensial belum diisi (Super Admin belum sempat mengisi Billing
  SaaS Payment Gateway di halaman Super Admin).
- Terisi -> enabled=True, buat_transaksi()/cek_status_transaksi()
  memanggil REST API provider sungguhan (Sandbox ATAU Production, sesuai
  environment yang tersimpan).

verifikasi_signature() TIDAK bergantung pada enabled() sama sekali --
fungsi MURNI (SHA512 + satu baca config, tanpa network), dipanggil webhook
handler untuk memvalidasi SETIAP notifikasi masuk SEBELUM mempercayai isi
payload-nya sama sekali -- SESUAI aturan keamanan "validasi Signature Key,
Server Key, Order ID, transaction amount, jangan pernah percaya data dari
client begitu saja"."""

import base64

import billing_gateway_db
import gateway_client_base as core

_TIMEOUT_DETIK = 15


def is_enabled() -> bool:
    return billing_gateway_db.get_config()["enabled"]


def is_production() -> bool:
    return billing_gateway_db.get_config()["environment"] == "production"


def client_key() -> str:
    """Client Key MEMANG dirancang dipakai di frontend (beda dengan Server
    Key yang tidak pernah dikirim ke client sama sekali) -- dipakai
    frontend Owner memuat script checkout provider dan memicu popup bayar."""
    return billing_gateway_db.get_config()["client_key"]


def client_script_url() -> str:
    """URL script checkout hosted provider (dimuat frontend, lihat
    billing.js) -- SAAT INI mengarah ke Snap.js Midtrans (adapter konkret
    placeholder, lihat catatan modul), ganti sesuai dokumentasi provider
    resmi begitu ditentukan."""
    is_prod = billing_gateway_db.get_config()["environment"] == "production"
    return "https://app.midtrans.com/snap/snap.js" if is_prod else "https://app.sandbox.midtrans.com/snap/snap.js"


def _checkout_base_url(is_prod: bool) -> str:
    return "https://app.midtrans.com/snap/v1" if is_prod else "https://app.sandbox.midtrans.com/snap/v1"


def _status_base_url(is_prod: bool) -> str:
    return "https://api.midtrans.com/v2" if is_prod else "https://api.sandbox.midtrans.com/v2"


def _auth_header(server_key: str) -> dict:
    """Basic Auth: Server Key sebagai username, password kosong -- SESUAI
    dokumentasi resmi provider saat ini (base64("SERVER_KEY:"))."""
    token = base64.b64encode(f"{server_key}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json", "Accept": "application/json"}


def buat_transaksi(order_id: str, gross_amount: int, item_details: list,
                    customer_details: dict = None) -> dict:
    """Buat transaksi checkout hosted -- return {"token", "redirect_url"}
    dari provider (frontend memanggil script checkout dengan ini). Melempar
    GatewayNotConfiguredError kalau belum dikonfigurasi, GatewayTimeoutError/
    GatewayRequestError kalau providernya sendiri bermasalah -- pemanggil
    (endpoint checkout) tetap WAJIB mengecek is_enabled() lebih dulu supaya
    bisa balas 503 yang jelas."""
    cfg = billing_gateway_db.get_config()
    if not cfg["enabled"]:
        raise core.GatewayNotConfiguredError("Payment Gateway langganan SaaS belum dikonfigurasi Super Admin (Server Key/Client Key kosong).")
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": int(gross_amount)},
        "item_details": item_details,
    }
    if customer_details:
        payload["customer_details"] = customer_details
    data = core.post_json(f"{_checkout_base_url(cfg['environment'] == 'production')}/transactions", payload,
                           _auth_header(cfg["server_key"]), timeout=_TIMEOUT_DETIK)
    return {"token": data["token"], "redirect_url": data["redirect_url"]}


def cek_status_transaksi(order_id: str) -> dict:
    """GET status transaksi (Core API, BUKAN checkout API) -- dipakai untuk
    rekonsiliasi manual/troubleshooting (mis. webhook tidak pernah sampai
    karena masalah jaringan), TIDAK dipakai di alur normal (webhook handler
    sudah cukup dari notifikasi POST langsung)."""
    cfg = billing_gateway_db.get_config()
    if not cfg["enabled"]:
        raise core.GatewayNotConfiguredError("Payment Gateway langganan SaaS belum dikonfigurasi Super Admin (Server Key/Client Key kosong).")
    return core.get_json(f"{_status_base_url(cfg['environment'] == 'production')}/{order_id}/status",
                          _auth_header(cfg["server_key"]), timeout=_TIMEOUT_DETIK)


def verifikasi_signature(order_id: str, status_code: str, gross_amount: str, signature_key: str) -> bool:
    """SHA512(order_id + status_code + gross_amount + ServerKey) -- formula
    SESUAI dokumentasi provider saat ini (adapter konkret placeholder,
    lihat catatan modul -- ganti urutan field di sini kalau provider resmi
    nanti pakai formula berbeda, callernya di billing_webhook.py TIDAK perlu
    berubah). `gross_amount` HARUS string PERSIS seperti dikirim provider di
    payload notifikasi (mis. "150000.00", bukan angka Python) -- signature
    dihitung dari representasi teksnya, bukan nilai numeriknya."""
    server_key = billing_gateway_db.get_config()["server_key"]
    return core.verify_sha512([order_id, status_code, gross_amount], server_key, signature_key)
