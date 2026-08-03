"""midtrans_client.py — FONDASI Multi-Tenant Phase 4: Klien Midtrans Snap API
=============================================================================
Kredensial ditentukan SEKALI saat modul ini pertama kali diimpor, dari
environment variable MIDTRANS_* (pola sama seperti r2_storage.py
menentukan R2_* / db_compat.py menentukan DATABASE_URL dari
env var-nya sendiri):
- MIDTRANS_SERVER_KEY/MIDTRANS_CLIENT_KEY kosong -> IS_ENABLED=False.
  Endpoint checkout (dibangun di modul billing berikutnya) WAJIB mengecek
  IS_ENABLED dan balas 503 dengan pesan jelas -- modul ini TIDAK PERNAH
  membuat proses gagal boot hanya karena kredensial belum diisi (owner
  belum sempat daftar Midtrans, atau baru mengisinya belakangan lewat
  Environment Variables di Render).
- Terisi -> IS_ENABLED=True, buat_transaksi_snap()/cek_status_transaksi()
  memanggil REST API Midtrans sungguhan (Sandbox ATAU Production,
  ditentukan MIDTRANS_IS_PRODUCTION).

verifikasi_signature() TIDAK bergantung pada IS_ENABLED sama sekali --
fungsi MURNI (SHA512, tanpa network/DB), dipanggil webhook handler untuk
memvalidasi SETIAP notifikasi masuk SEBELUM mempercayai isi payload-nya
sama sekali -- SESUAI aturan keamanan Phase 4 "validasi Signature Key,
Server Key, Order ID, transaction amount, jangan pernah percaya data dari
client begitu saja"."""

import base64
import hashlib
import logging
import os

import requests

logger = logging.getLogger("mugen.midtrans")

MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "").strip()
MIDTRANS_CLIENT_KEY = os.environ.get("MIDTRANS_CLIENT_KEY", "").strip()
MIDTRANS_IS_PRODUCTION = os.environ.get("MIDTRANS_IS_PRODUCTION", "").strip().lower() in ("1", "true", "ya")

IS_ENABLED = bool(MIDTRANS_SERVER_KEY and MIDTRANS_CLIENT_KEY)

_SNAP_BASE_URL = (
    "https://app.midtrans.com/snap/v1" if MIDTRANS_IS_PRODUCTION
    else "https://app.sandbox.midtrans.com/snap/v1"
)
_CORE_API_BASE_URL = (
    "https://api.midtrans.com/v2" if MIDTRANS_IS_PRODUCTION
    else "https://api.sandbox.midtrans.com/v2"
)
_TIMEOUT_DETIK = 15


def _auth_header() -> dict:
    """Basic Auth Midtrans: Server Key sebagai username, password kosong --
    SESUAI dokumentasi resmi (base64("SERVER_KEY:"))."""
    token = base64.b64encode(f"{MIDTRANS_SERVER_KEY}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json", "Accept": "application/json"}


def buat_transaksi_snap(order_id: str, gross_amount: int, item_details: list,
                         customer_details: dict = None) -> dict:
    """POST /snap/v1/transactions -- return {"token", "redirect_url"} dari
    Midtrans (frontend memanggil `snap.pay(token)` dengan ini). Melempar
    RuntimeError kalau IS_ENABLED False ATAU Midtrans menolak permintaan --
    pemanggil (endpoint checkout) tetap WAJIB mengecek IS_ENABLED lebih
    dulu supaya bisa balas 503 yang jelas, bukan mengandalkan exception ini
    yang lebih cocok jadi 502 (Midtrans-nya sendiri yang bermasalah)."""
    if not IS_ENABLED:
        raise RuntimeError("Midtrans belum dikonfigurasi (MIDTRANS_SERVER_KEY/MIDTRANS_CLIENT_KEY kosong).")
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": int(gross_amount)},
        "item_details": item_details,
    }
    if customer_details:
        payload["customer_details"] = customer_details
    resp = requests.post(f"{_SNAP_BASE_URL}/transactions", json=payload,
                          headers=_auth_header(), timeout=_TIMEOUT_DETIK)
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
    if not IS_ENABLED:
        raise RuntimeError("Midtrans belum dikonfigurasi (MIDTRANS_SERVER_KEY/MIDTRANS_CLIENT_KEY kosong).")
    resp = requests.get(f"{_CORE_API_BASE_URL}/{order_id}/status", headers=_auth_header(), timeout=_TIMEOUT_DETIK)
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
    if not MIDTRANS_SERVER_KEY:
        return False
    raw = f"{order_id}{status_code}{gross_amount}{MIDTRANS_SERVER_KEY}"
    hitung = hashlib.sha512(raw.encode()).hexdigest()
    return hitung == signature_key
