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

import base64
import hashlib
import hmac
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

_TIMEOUT_DETIK_DEFAULT = 15

# AUDIT (UAT Faspay -- "bill expired must be greater than today"): Faspay
# (perusahaan Indonesia) memvalidasi bill_date/bill_expired terhadap jam
# WIB mereka sendiri -- server Render tempat aplikasi ini berjalan default
# UTC (7 jam di BELAKANG WIB, pola sama seperti booking_db.py::_sekarang_wib()
# -- lihat catatan panjang di sana), jadi datetime.now() polos yang
# sebelumnya dipakai billing_gateway_client.py/payment_gateway_client.py
# mengirim jam yang menurut Faspay masih ~7 jam di masa lalu, ditolak
# sebagai "sudah lewat" walau sebenarnya baru saja dibuat. now_wib() di
# bawah SATU-SATUNYA sumber waktu untuk seluruh field tanggal/jam yang
# dikirim ke Faspay -- TIDAK PERNAH datetime.now() polos lagi.
WIB = ZoneInfo("Asia/Jakarta")


def now_wib() -> datetime:
    """Waktu sekarang di Asia/Jakarta (WIB) -- WAJIB dipakai untuk
    bill_date/bill_expired (dan field tanggal Faspay lain di masa depan),
    lihat catatan di atas. .strftime() pada hasil ini tetap menghasilkan
    string polos "YYYY-MM-DD HH:MM:SS" sesuai format resmi Faspay (offset
    timezone TIDAK ikut ditulis, hanya dipakai memastikan ANGKA jam/menitnya
    benar WIB)."""
    return datetime.now(WIB)


# AUDIT (UAT Faspay -- "item[product] must be alphanumeric"): field
# `item[].product` ditolak Faspay begitu berisi karakter selain huruf/
# angka/spasi -- SANGAT umum muncul di nama layanan/paket sungguhan (mis.
# "Cut & Wash", "Paket Pro (30 hari)"). Karakter terlarang diganti SATU
# spasi (bukan dihapus langsung) supaya kata tidak menempel jadi satu
# ("Cut&Wash" salah, harus jadi "Cut Wash"), baru spasi berlebih dirapikan.
_PRODUCT_TERLARANG = re.compile(r"[^A-Za-z0-9 ]+")
_PRODUCT_SPASI_GANDA = re.compile(r"\s+")


def sanitize_item_product(text: str, fallback: str, max_len: int = 50) -> str:
    """Bersihkan nama produk untuk field `item[].product` Faspay Xpress v4
    -- lihat catatan di atas. `fallback` dipakai kalau hasil akhirnya kosong
    sama sekali (mis. nama aslinya HANYA simbol, atau None/string kosong)."""
    bersih = _PRODUCT_TERLARANG.sub(" ", text or "")
    bersih = _PRODUCT_SPASI_GANDA.sub(" ", bersih).strip()
    if not bersih:
        bersih = fallback
    return bersih[:max_len]


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


# =============================================================================
# Migrasi Faspay SNAP Advance -- signature standar SNAP (Standar Nasional Open
# API Pembayaran, Bank Indonesia/ASPI)
# =============================================================================
# CATATAN SUMBER & BATASAN (WAJIB dibaca sebelum memakai fungsi di bawah):
# Algoritma "RSA-SHA256 (PKCS#1 v1.5), hasil di-base64-encode, dikirim lewat
# header X-SIGNATURE" adalah bagian dari standar SNAP yang DIWAJIBKAN Bank
# Indonesia/ASPI untuk SELURUH penyelenggara berlisensi (Faspay, Xendit,
# Espay, Duitku, dst) -- BUKAN pilihan bebas satu provider, jadi aman
# diimplementasikan sebagai primitif generik di sini (lihat laporan analisis
# "Faspay SNAP Migration", Tahap 2.4 -- dikonfirmasi dari dokumentasi publik
# SNAP lintas-provider, BUKAN tebakan).
#
# YANG TIDAK diketahui dari sini (PENDING FASPAY, TIDAK diimplementasikan di
# mana pun di proyek ini sampai dikonfirmasi tertulis oleh Faspay):
# - String-to-sign PERSIS per endpoint SNAP Faspay (urutan/isi field yang
#   digabung sebelum ditandatangani beda per jenis layanan -- get-token vs
#   create-VA vs create-QRIS vs webhook -- dan Faspay belum pernah
#   mengonfirmasi formula persisnya ke tim ini).
# - Endpoint get-token B2B Faspay yang sesungguhnya (path, header lengkap).
# - Header SNAP lain di luar X-SIGNATURE (X-TIMESTAMP/X-PARTNER-ID/
#   X-EXTERNAL-ID) -- FORMAT nilainya per Faspay belum terverifikasi.
#
# snap_advance_client.py-lah yang merangkai string-to-sign & memanggil fungsi
# di bawah ini -- MURNI stub PENDING FASPAY sampai formula itu terkonfirmasi.
# Fungsi DI SINI hanya primitif kriptografi generik (sign/verify), TIDAK tahu
# apa pun soal format SNAP Faspay spesifik -- sama seperti sign_sha1_of_md5()/
# verify_sha512() di atas yang juga tidak tahu soal Xpress/Midtrans spesifik.

def sign_sha256_rsa(string_to_sign: str, private_key_pem: str) -> str:
    """RSA-SHA256 (PKCS#1 v1.5) atas `string_to_sign`, hasil di-base64-encode
    -- primitif signature standar SNAP (lihat catatan modul di atas).
    `private_key_pem` = private key merchant format PEM (PKCS#1/PKCS#8,
    TANPA passphrase -- pemanggil bertanggung jawab men-decrypt dulu kalau
    key tersimpan terenkripsi).

    Melempar ValueError kalau `private_key_pem` kosong/tidak valid --
    pemanggil (snap_advance_client.py) WAJIB menerjemahkannya jadi
    GatewayNotConfiguredError, SAMA seperti pola kredensial kosong di
    fungsi signature lain modul ini."""
    if not private_key_pem:
        raise ValueError("Private key SNAP Advance belum diisi.")
    try:
        key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    except ValueError as e:
        raise ValueError(f"Private key SNAP Advance tidak valid: {e}") from e
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("Private key SNAP Advance harus RSA (SNAP mewajibkan RSA-SHA256).")
    tanda_tangan = key.sign(string_to_sign.encode(), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(tanda_tangan).decode()


def verify_sha256_rsa(string_to_sign: str, signature_b64: str, public_key_pem: str) -> bool:
    """Verifikasi signature RSA-SHA256 (PKCS#1 v1.5) -- pasangan
    sign_sha256_rsa() di atas, dipakai untuk memvalidasi notifikasi/webhook
    yang DATANG dari Faspay (ditandatangani dengan private key Faspay,
    diverifikasi dengan public key Faspay yang dibagikan ke merchant).
    Return False (BUKAN exception) kalau `public_key_pem`/`signature_b64`
    kosong atau signature tidak valid -- pemanggil (webhook handler) WAJIB
    menolak notifikasi tanpa signature yang valid, sama seperti
    verify_sha1_of_md5()/verify_sha512() di atas."""
    if not (public_key_pem and signature_b64):
        return False
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(key, RSAPublicKey):
            return False
        key.verify(base64.b64decode(signature_b64), string_to_sign.encode(), padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
