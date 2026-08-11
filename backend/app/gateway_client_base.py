"""gateway_client_base.py — Util level-rendah BERSAMA untuk kedua modul Payment
Gateway (billing_gateway_client.py untuk langganan SaaS, payment_gateway_client.py
untuk booking customer)
=============================================================================
SESUAI arsitektur yang diminta: "Satu provider Payment Gateway, dua jenis
transaksi" -- komponen level-rendah (HTTP client, penerjemahan error,
verifikasi signature, logging) BOLEH dipakai bersama KEDUA modul, TAPI
business logic/webhook processing/riwayat transaksi/pengelolaan pembayaran
TETAP terpisah total (masing-masing modul punya file/tabel/endpoint sendiri
-- lihat billing_gateway_client.py vs payment_gateway_client.py).

Modul ini TIDAK tahu apa pun soal Midtrans/provider tertentu -- murni
pembungkus `requests` (timeout + penerjemahan exception jaringan jadi error
class yang konsisten, BUKAN lolos mentah sebagai requests.exceptions.*) dan
helper verifikasi signature SHA512 generik (urutan field APA PUN, bukan
terpatok formula satu provider). Kedua modul client memanggil fungsi di
sini, TIDAK PERNAH memanggil `requests` langsung sendiri-sendiri -- supaya
perilaku timeout/error SELALU konsisten di seluruh integrasi Payment
Gateway, tidak peduli jenis transaksinya."""

import hashlib
import hmac
import logging

import requests

_TIMEOUT_DETIK_DEFAULT = 15


class GatewayError(Exception):
    """Basis seluruh error Payment Gateway -- endpoint pemanggil (routers/
    billing.py, routers/booking.py) menangkap ini (atau turunannya) untuk
    membalas HTTP yang jelas ke frontend, BUKAN membiarkan exception mentah
    bocor jadi HTTP 500 tanpa pesan yang berguna."""


class GatewayNotConfiguredError(GatewayError):
    """Kredensial (server key/client key/dst) belum diisi Super Admin --
    pemanggil WAJIB membalas 503 dengan pesan jelas."""


class GatewayTimeoutError(GatewayError):
    """Provider tidak merespons dalam batas waktu, atau koneksi gagal sama
    sekali (DNS/jaringan putus) -- pemanggil WAJIB membalas 502/504, BUKAN
    membiarkan requests.exceptions.Timeout/ConnectionError bocor mentah
    (celah yang ditemukan audit sebelumnya: exception jaringan sebelumnya
    TIDAK ditangkap sama sekali di titik manapun)."""


class GatewayRequestError(GatewayError):
    """Provider merespons TAPI menolak permintaan (HTTP status >= 400) --
    pemanggil WAJIB membalas 502 dengan pesan jelas."""


def post_json(url: str, payload: dict, headers: dict, timeout: int = _TIMEOUT_DETIK_DEFAULT) -> dict:
    """POST JSON ke provider -- membungkus SEMUA kegagalan jaringan/timeout
    jadi GatewayTimeoutError, dan status HTTP >= 400 jadi GatewayRequestError
    (dengan body respons provider disertakan di pesan error untuk membantu
    troubleshooting). Return body JSON kalau sukses."""
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as e:
        logging.getLogger("mugen.gateway").error("POST %s gagal (jaringan/timeout): %s", url, e)
        raise GatewayTimeoutError(f"Tidak dapat menghubungi Payment Gateway: {e}") from e
    if resp.status_code >= 400:
        logging.getLogger("mugen.gateway").error("POST %s ditolak provider: HTTP %s %s", url, resp.status_code, resp.text)
        raise GatewayRequestError(f"Payment Gateway menolak permintaan (HTTP {resp.status_code}).")
    return resp.json()


def get_json(url: str, headers: dict, timeout: int = _TIMEOUT_DETIK_DEFAULT) -> dict:
    """GET JSON dari provider -- pola penanganan error SAMA PERSIS dengan
    post_json() di atas (lihat docstring-nya)."""
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as e:
        logging.getLogger("mugen.gateway").error("GET %s gagal (jaringan/timeout): %s", url, e)
        raise GatewayTimeoutError(f"Tidak dapat menghubungi Payment Gateway: {e}") from e
    if resp.status_code >= 400:
        logging.getLogger("mugen.gateway").error("GET %s ditolak provider: HTTP %s %s", url, resp.status_code, resp.text)
        raise GatewayRequestError(f"Payment Gateway menolak permintaan (HTTP {resp.status_code}).")
    return resp.json()


def sign_sha1_of_md5(parts: list) -> str:
    """SHA1(MD5(concat(parts))) -- pola signature Faspay (Xpress v4): dua
    tahap hash, kredensial (user_id/password) DIMASUKKAN LANGSUNG di dalam
    `parts` pada posisi yang ditentukan pemanggil (BEDA dari verify_sha512()
    yang menempelkan `key` generik di UJUNG) -- modul ini tetap tidak tahu
    apa pun soal Faspay spesifik, murni komputasi hash dua-tahap generik."""
    joined = "".join(str(p) for p in parts)
    tahap1 = hashlib.md5(joined.encode()).hexdigest()
    return hashlib.sha1(tahap1.encode()).hexdigest()


def verify_sha1_of_md5(parts: list, signature: str) -> bool:
    """Verifikasi SHA1(MD5(concat(parts))) == signature -- lihat
    sign_sha1_of_md5(). Return False (bukan exception) kalau `signature`
    kosong -- pemanggil (webhook handler) HARUS menolak notifikasi tanpa
    signature sama sekali, bukan lolos begitu saja."""
    if not signature:
        return False
    hitung = sign_sha1_of_md5(parts)
    return hmac.compare_digest(hitung, signature)


def verify_sha512(parts: list, key: str, signature: str) -> bool:
    """Verifikasi signature SHA512(concat(parts) + key) == signature --
    GENERIK soal urutan/isi `parts` (provider berbeda bisa punya formula
    berbeda, mis. Midtrans: [order_id, status_code, gross_amount]) supaya
    modul ini tidak terpatok pada satu provider tertentu. Return False
    (bukan exception) kalau `key` kosong -- pemanggil (webhook handler)
    HARUS menolak notifikasi mana pun selama kredensial belum dikonfigurasi,
    TIDAK ADA cara notifikasi dianggap valid tanpa key untuk membandingkannya."""
    if not key:
        return False
    raw = "".join(parts) + key
    hitung = hashlib.sha512(raw.encode()).hexdigest()
    # AUDIT (perbaikan pasca-audit kesiapan): hmac.compare_digest() (bukan
    # `==` polos) -- perbandingan waktu-konstan supaya durasi perbandingan
    # tidak membocorkan informasi soal seberapa banyak karakter awal yang
    # cocok (celah timing attack teoretis, risiko nyata rendah lewat HTTPS
    # tapi ini hardening standar untuk perbandingan signature/token).
    return hmac.compare_digest(hitung, signature)
