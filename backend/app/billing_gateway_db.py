"""billing_gateway_db.py — Konfigurasi Payment Gateway Billing SaaS (Midtrans, PLATFORM-WIDE)
=================================================================================
Kredensial untuk Owner tenant membayar LANGGANAN platform ini (paket Free/
Basic/Pro/Enterprise, menu Billing > Perpanjang Paket) -- SATU merchant
Midtrans milik platform (Rivoir), dipakai SELURUH tenant, dibayarkan KE
platform (bukan ke tenant mana pun). TERPISAH TOTAL dari
`payment_gateway_db.py` (kredensial PGW untuk CUSTOMER membayar BOOKING ke
tenant, channel QRIS/VA/GoPay/dst) -- dua merchant/dua tujuan uang yang
berbeda, sengaja disimpan di modul & key `settings` yang berbeda, TIDAK
saling bergantung sama sekali (mengubah salah satu tidak pernah memengaruhi
yang lain).

Sebelumnya kredensial ini murni environment variable (MIDTRANS_SERVER_KEY/
MIDTRANS_CLIENT_KEY/MIDTRANS_IS_PRODUCTION, dibaca SEKALI oleh
midtrans_client.py saat modul itu pertama kali diimpor -- lihat riwayat git
modul ini) -- sekarang dipindah ke tabel `settings` yang SUDAH ADA
(tenant_id=None, key POLOS tidak diprefix, pola SAMA PERSIS dengan
`payment_gateway_db.py`/`subscription_db.get_platform_config()`/
`landing_db.get_contact()`) supaya Super Admin bisa mengubahnya lewat UI
kapan saja TANPA redeploy. TIDAK ADA tabel baru -- murni baris baru di
tabel key-value generik yang sudah ada.

`migrasi_billing_gateway()` (dipanggil sekali tiap boot, lihat main.py)
mem-BOOTSTRAP nilai DB dari env var MIDTRANS_* LAMA HANYA kalau DB belum
pernah diisi sama sekali -- SEKALI SAJA, idempotent -- supaya kredensial
production yang sudah berjalan (env var Render yang sudah diisi sebelum
perubahan ini) tidak tiba-tiba berhenti berfungsi begitu upgrade ini
di-deploy. Setelah bootstrap awal itu, env var MIDTRANS_* TIDAK PERNAH
dibaca lagi -- database adalah SATU-SATUNYA sumber kebenaran seterusnya."""

import os

import database as db

ENVIRONMENT_VALID = {"sandbox", "production"}

_KUNCI_SERVER_KEY = "billing_pgw_server_key"
_KUNCI_CLIENT_KEY = "billing_pgw_client_key"
_KUNCI_ENVIRONMENT = "billing_pgw_environment"


def get_config() -> dict:
    server_key = db.get_setting(_KUNCI_SERVER_KEY, "", tenant_id=None)
    client_key = db.get_setting(_KUNCI_CLIENT_KEY, "", tenant_id=None)
    environment = db.get_setting(_KUNCI_ENVIRONMENT, "sandbox", tenant_id=None)
    if environment not in ENVIRONMENT_VALID:
        environment = "sandbox"
    return {
        "server_key": server_key,
        "client_key": client_key,
        "environment": environment,
        "enabled": bool(server_key and client_key),
    }


def update_config(server_key: str = None, client_key: str = None, environment: str = None) -> dict:
    data = {}
    if server_key is not None:
        data[_KUNCI_SERVER_KEY] = server_key.strip()
    if client_key is not None:
        data[_KUNCI_CLIENT_KEY] = client_key.strip()
    if environment is not None:
        if environment not in ENVIRONMENT_VALID:
            raise ValueError("Environment harus 'sandbox' atau 'production'.")
        data[_KUNCI_ENVIRONMENT] = environment
    if data:
        db.set_settings_bulk(data, tenant_id=None)
    return get_config()


def migrasi_billing_gateway():
    """Idempotent, aman dipanggil berkali-kali -- HANYA menulis kalau key
    `billing_pgw_server_key` belum pernah ada sama sekali di `settings`
    (bukan sekadar kosong -- lihat `db.get_setting(..., default=None)` di
    bawah, beda dari get_config() yang defaultnya string kosong) supaya
    TIDAK PERNAH menimpa nilai yang sudah diatur ulang Super Admin lewat UI
    (mis. Super Admin sengaja mengosongkan/mengganti kredensial)."""
    sudah_pernah_diisi = db.get_setting(_KUNCI_SERVER_KEY, None, tenant_id=None) is not None
    if sudah_pernah_diisi:
        return
    env_server_key = os.environ.get("MIDTRANS_SERVER_KEY", "").strip()
    env_client_key = os.environ.get("MIDTRANS_CLIENT_KEY", "").strip()
    if not (env_server_key and env_client_key):
        return  # tidak ada apa pun di env var untuk di-bootstrap
    env_is_production = os.environ.get("MIDTRANS_IS_PRODUCTION", "").strip().lower() in ("1", "true", "ya")
    db.set_settings_bulk({
        _KUNCI_SERVER_KEY: env_server_key,
        _KUNCI_CLIENT_KEY: env_client_key,
        _KUNCI_ENVIRONMENT: "production" if env_is_production else "sandbox",
    }, tenant_id=None)
