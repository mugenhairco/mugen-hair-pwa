"""midtrans_client.py — FONDASI Multi-Tenant Phase 4: Klien Midtrans Snap API
=============================================================================
Kredensial dibaca DINAMIS dari `billing_gateway_db.get_config()` (tabel
`settings`, dikelola Super Admin lewat UI) SETIAP fungsi di sini dipanggil
-- BUKAN lagi konstanta module-level yang dihitung SEKALI saat modul ini
diimpor dari environment variable MIDTRANS_* (pola LAMA, lihat riwayat git
modul ini). Ini supaya perubahan kredensial lewat Super Admin langsung
berlaku SAAT ITU JUGA, tanpa perlu restart/redeploy proses backend.

- Server Key/Client Key kosong -> enabled=False. Endpoint checkout
  (routers/billing.py) WAJIB mengecek is_enabled() dan balas 503 dengan
  pesan jelas -- modul ini TIDAK PERNAH membuat proses gagal boot hanya
  karena kredensial belum diisi (Super Admin belum sempat mengisi Billing
  SaaS Payment Gateway di halaman Super Admin).
- Terisi -> enabled=True, buat_transaksi_snap()/cek_status_transaksi()
  memanggil REST API Midtrans sungguhan (Sandbox ATAU Production, sesuai
  environment yang tersimpan).

verifikasi_signature() TIDAK bergantung pada enabled() sama sekali --
fungsi MURNI (SHA512 + satu baca config, tanpa network), dipanggil webhook
handler untuk memvalidasi SETIAP notifikasi masuk SEBELUM mempercayai isi
payload-nya sama sekali -- SESUAI aturan keamanan Phase 4 "validasi
Signature Key, Server Key, Order ID, transaction amount, jangan pernah
percaya data dari client begitu saja"."""

import base64
import hashlib
import logging

import requests

import billing_gateway_db

logger = logging.getLogger("mugen.midtrans")

_TIMEOUT_DETIK = 15


def is_enabled() -> bool:
    return billing_gateway_db.get_config()["enabled"]


def is_production() -> bool:
    return billing_gateway_db.get_config()["environment"] == "production"


def client_key() -> str:
    """Client Key MEMANG dirancang dipakai di frontend (beda dengan Server
    Key yang tidak pernah dikirim ke client sama sekali) -- dipakai
    frontend Owner memuat Snap.js dan memanggil `snap.pay()`."""
    return billing_gateway_db.get_config()["client_key"]


def snap_js_url() -> str:
    is_prod = billing_gateway_db.get_config()["environment"] == "production"
    return "https://app.midtrans.com/snap/snap.js" if is_prod else "https://app.sandbox.midtrans.com/snap/snap.js"


def _snap_base_url(is_prod: bool) -> str:
    return "https://app.midtrans.com/snap/v1" if is_prod else "https://app.sandbox.midtrans.com/snap/v1"


def _core_api_base_url(is_prod: bool) -> str:
    return "https://api.midtrans.com/v2" if is_prod else "https://api.sandbox.midtrans.com/v2"


def _auth_header(server_key: str) -> dict:
    """Basic Auth Midtrans: Server Key sebagai username, password kosong --
    SESUAI dokumentasi resmi (base64("SERVER_KEY:"))."""
    token = base64.b64encode(f"{server_key}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json", "Accept": "application/json"}


def buat_transaksi_snap(order_id: str, gross_amount: int, item_details: list,
                         customer_details: dict = None) -> dict:
    """POST /snap/v1/transactions -- return {"token", "redirect_url"} dari
    Midtrans (frontend memanggil `snap.pay(token)` dengan ini). Melempar
    RuntimeError kalau belum dikonfigurasi ATAU Midtrans menolak permintaan
    -- pemanggil (endpoint checkout) tetap WAJIB mengecek is_enabled() lebih
    dulu supaya bisa balas 503 yang jelas, bukan mengandalkan exception ini
    yang lebih cocok jadi 502 (Midtrans-nya sendiri yang bermasalah)."""
    cfg = billing_gateway_db.get_config()
    if not cfg["enabled"]:
        raise RuntimeError("Midtrans Billing SaaS belum dikonfigurasi Super Admin (Server Key/Client Key kosong).")
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": int(gross_amount)},
        "item_details": item_details,
    }
    if customer_details:
        payload["customer_details"] = customer_details
    resp = requests.post(f"{_snap_base_url(cfg['environment'] == 'production')}/transactions", json=payload,
                          headers=_auth_header(cfg["server_key"]), timeout=_TIMEOUT_DETIK)
    if resp.status_code >= 400:
        logger.error("Midtrans Snap gagal (order_id=%s): HTTP %s %s", order_id, resp.status_code, resp.text)
        raise RuntimeError(f"Midtrans menolak permintaan transaksi (HTTP {resp.status_code}).")
    data = resp.json()
    return {"token": data["token"], "redirect_url": data["redirect_url"]}


def cek_status_transaksi(order_id: str) -> dict:
    """GET /v2/{order_id}/status (Core API, BUKAN Snap API) -- dipakai untuk
    rekonsiliasi manual/troubleshooting (mis. webhook tidak pernah sampai
    karena masalah jaringan), TIDAK dipakai di alur normal (webhook handler
    sudah cukup dari notifikasi POST langsung)."""
    cfg = billing_gateway_db.get_config()
    if not cfg["enabled"]:
        raise RuntimeError("Midtrans Billing SaaS belum dikonfigurasi Super Admin (Server Key/Client Key kosong).")
    resp = requests.get(f"{_core_api_base_url(cfg['environment'] == 'production')}/{order_id}/status",
                         headers=_auth_header(cfg["server_key"]), timeout=_TIMEOUT_DETIK)
    if resp.status_code >= 400:
        logger.error("Midtrans cek status gagal (order_id=%s): HTTP %s %s", order_id, resp.status_code, resp.text)
        raise RuntimeError(f"Midtrans menolak permintaan cek status (HTTP {resp.status_code}).")
    return resp.json()


def verifikasi_signature(order_id: str, status_code: str, gross_amount: str, signature_key: str) -> bool:
    """SHA512(order_id + status_code + gross_amount + ServerKey) -- SESUAI
    dokumentasi resmi Midtrans. `gross_amount` HARUS string PERSIS seperti
    dikirim Midtrans di payload notifikasi (mis. "150000.00", bukan angka
    Python) -- signature dihitung dari representasi teksnya, bukan nilai
    numeriknya. Return False (bukan exception) kalau Server Key belum
    dikonfigurasi -- pemanggil (webhook handler) HARUS menolak notifikasi
    mana pun selama Midtrans belum aktif, TIDAK ADA cara notifikasi apa pun
    dianggap valid tanpa Server Key untuk membandingkannya."""
    server_key = billing_gateway_db.get_config()["server_key"]
    if not server_key:
        return False
    raw = f"{order_id}{status_code}{gross_amount}{server_key}"
    hitung = hashlib.sha512(raw.encode()).hexdigest()
    return hitung == signature_key
