"""email_service.py — FITUR Email, Verifikasi Email, Lupa Kata Sandi: klien
Resend (pengiriman email transaksional)
=============================================================================
Kredensial ditentukan SEKALI saat modul ini pertama kali diimpor, dari
environment variable RESEND_API_KEY/MAIL_FROM/MAIL_FROM_NAME (pola SAMA
PERSIS seperti midtrans_client.py menentukan MIDTRANS_*/r2_storage.py
menentukan R2_*):

- RESEND_API_KEY kosong -> IS_ENABLED=False. kirim_email() TIDAK PERNAH
  memanggil jaringan sama sekali, cukup mencatat log & mengembalikan False
  -- endpoint pemanggil (routers/tenant_registration.py, routers/
  email_auth.py) TETAP berhasil menyelesaikan permintaan aslinya (bikin
  akun/tenant, dst) walau email tidak terkirim, SESUAI aturan "kegagalan
  pengiriman email tidak boleh membuat aplikasi crash".
- Terisi -> IS_ENABLED=True, kirim_email() memanggil REST API Resend
  sungguhan (POST /emails), header From selalu "MAIL_FROM_NAME
  <MAIL_FROM>" (mis. "Rivoir <noreply@rivoirsett.com>") -- SATU tempat
  ini membentuknya, tidak pernah dirakit ulang di pemanggil mana pun.

Cloudflare Email Routing (penerima email masuk ke noreply@rivoirsett.com,
diteruskan ke Gmail) TIDAK melibatkan modul ini sama sekali -- itu murni
konfigurasi DNS/Cloudflare, terpisah total dari jalur KIRIM email (Resend)
yang diurus di sini. Lihat catatan konfigurasi lengkap di ringkasan PR."""

import logging
import os

import requests

logger = logging.getLogger("mugen.email")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@rivoirsett.com").strip()
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "Rivoir").strip()
# Header "From" lengkap dibentuk SEKALI di sini (format standar RFC 5322
# "Nama <email>", yang juga dipahami Resend) -- kirim_email() di bawah
# TIDAK PERNAH merakit ulang string ini, supaya SETIAP email yang terkirim
# lewat modul ini (verifikasi/reset password/undangan user) selalu
# konsisten "Rivoir <noreply@rivoirsett.com>" apa adanya.
_FROM_HEADER = f"{MAIL_FROM_NAME} <{MAIL_FROM}>" if MAIL_FROM_NAME else MAIL_FROM

# Dipakai membentuk link verifikasi/reset password di dalam isi email
# (routers/tenant_registration.py, routers/auth_router.py, routers/
# pengaturan.py) -- domain ROOT platform (BUKAN subdomain tenant mana
# pun), karena link ini murni berbasis token (tidak butuh konteks tenant
# sama sekali, lihat email_auth_db.py) dan supaya satu env var ini cukup
# untuk SEMUA tenant sekaligus, konsisten dengan pola ALLOWED_ORIGIN_REGEX
# (main.py) yang juga satu nilai untuk seluruh *.rivoirsett.com.
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "https://rivoirsett.com").rstrip("/")

IS_ENABLED = bool(RESEND_API_KEY)

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_DETIK = 15


def link_verifikasi_email(token: str) -> str:
    return f"{FRONTEND_BASE_URL}/app/#/verify-email?token={token}"


def link_reset_password(token: str) -> str:
    return f"{FRONTEND_BASE_URL}/app/#/reset-password?token={token}"


def kirim_email(to: str, subject: str, html: str) -> bool:
    """Kirim SATU email HTML lewat Resend. SELALU aman dipanggil -- TIDAK
    PERNAH melempar exception ke pemanggil (ditangkap & dicatat log di
    sini), dan mengembalikan False (bukan crash) kalau IS_ENABLED False
    ATAU permintaan ke Resend gagal (kredensial salah, jaringan turun,
    dst). Pemanggil (routers/tenant_registration.py, routers/
    email_auth.py) TIDAK PERNAH boleh membiarkan hasil False di sini
    menggagalkan operasi utamanya (bikin akun, ganti password, dst) --
    email HANYA "best effort", pengguna tetap punya jalur "Kirim Ulang"
    kalau memang gagal terkirim."""
    if not IS_ENABLED:
        logger.warning("Email KE %s ('%s') TIDAK dikirim -- RESEND_API_KEY belum dikonfigurasi.", to, subject)
        return False
    try:
        resp = requests.post(
            _RESEND_URL,
            json={"from": _FROM_HEADER, "to": [to], "subject": subject, "html": html},
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            timeout=_TIMEOUT_DETIK,
        )
        if resp.status_code >= 400:
            logger.error("Resend menolak email KE %s: HTTP %s %s", to, resp.status_code, resp.text)
            return False
        return True
    except Exception as e:
        # SEGALA kegagalan jaringan/tak terduga (timeout, DNS, dst) --
        # ditangkap MENYELURUH (bukan cuma requests.RequestException) SESUAI
        # aturan eksplisit "kegagalan pengiriman email tidak menyebabkan
        # aplikasi crash", pengiriman email BUKAN bagian kritis alur mana pun.
        logger.error("Gagal mengirim email KE %s ('%s'): %s: %s", to, subject, e.__class__.__name__, e)
        return False
