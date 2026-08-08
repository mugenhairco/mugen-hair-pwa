"""payment_gateway_db.py — Konfigurasi Payment Gateway (PLATFORM-WIDE)
=========================================================================
SATU merchant account PGW dipakai bersama oleh SELURUH tenant (customer
booking di toko mana pun membayar lewat channel yang sama) -- BEDA dari
Midtrans di midtrans_client.py/routers/billing.py, yang untuk Owner
membayar LANGGANAN platform ini, bukan customer membayar booking. Kedua
integrasi ini sengaja terpisah total, tidak saling berbagi kredensial.

Kredensial (API key/server key/client key/merchant ID/secret key) DB-backed
lewat tabel `settings` generik dengan `tenant_id=None` (key POLOS, tidak
diprefix per-tenant) -- pola SAMA PERSIS dengan
subscription_db.get_platform_config()/landing_db.get_contact(), BUKAN env
var seperti midtrans_client.py -- supaya Super Admin bisa mengisi/mengubah
kapan saja lewat UI tanpa perlu redeploy.

Belum ada panggilan API sungguhan ke provider PGW mana pun di sini (lihat
booking_db.py::buat_booking() -- booking "gateway" langsung dianggap
terverifikasi begitu wizard publik melapor pembayaran sukses) -- modul ini
murni tempat menyimpan kredensial yang akan dipakai begitu integrasi
sungguhan dipasang, dan tempat mengatur channel mana yang aktif + urutan
tampilnya di wizard booking publik.
"""

import json

import database as db

_KEYS_KREDENSIAL = [
    "pgw_provider", "pgw_environment", "pgw_api_key", "pgw_server_key",
    "pgw_client_key", "pgw_merchant_id", "pgw_secret_key", "pgw_webhook_url",
]
_KUNCI_METODE_AKTIF = "pgw_metode_aktif"

ENVIRONMENT_VALID = {"sandbox", "production"}

# Channel yang didukung -- urutan dict ini HANYA fallback (dipakai kalau
# Super Admin belum pernah mengatur pgw_metode_aktif sama sekali); urutan
# TAMPIL sesungguhnya selalu ikut array pgw_metode_aktif yang tersimpan.
CHANNEL_LABEL = {
    "qris": "QRIS",
    "va": "Virtual Account",
    "gopay": "GoPay",
    "shopeepay": "ShopeePay",
    "dana": "DANA",
    "ovo": "OVO",
    "kartu": "Kartu Debit/Kredit",
}
CHANNEL_VALID = set(CHANNEL_LABEL.keys())
_DEFAULT_METODE_AKTIF = json.dumps(["qris", "va", "gopay", "shopeepay", "dana", "ovo"])


def get_config() -> dict:
    """Config LENGKAP termasuk kredensial -- HANYA dipanggil dari endpoint
    require_superadmin (routers/payment_gateway.py), tidak pernah diekspos
    ke tenant/publik. Lihat get_public_channels() untuk yang aman dipublikasikan."""
    data = {k: db.get_setting(k, "", tenant_id=None) for k in _KEYS_KREDENSIAL}
    try:
        metode_aktif = json.loads(db.get_setting(_KUNCI_METODE_AKTIF, _DEFAULT_METODE_AKTIF, tenant_id=None))
    except (TypeError, ValueError):
        metode_aktif = []
    data["metode_aktif"] = metode_aktif
    data["channel_label"] = CHANNEL_LABEL
    return data


def update_config(provider: str = None, environment: str = None, api_key: str = None,
                   server_key: str = None, client_key: str = None, merchant_id: str = None,
                   secret_key: str = None, webhook_url: str = None, metode_aktif: list = None) -> dict:
    data = {}
    if provider is not None:
        data["pgw_provider"] = provider.strip()
    if environment is not None:
        if environment not in ENVIRONMENT_VALID:
            raise ValueError("Environment harus 'sandbox' atau 'production'.")
        data["pgw_environment"] = environment
    if api_key is not None:
        data["pgw_api_key"] = api_key.strip()
    if server_key is not None:
        data["pgw_server_key"] = server_key.strip()
    if client_key is not None:
        data["pgw_client_key"] = client_key.strip()
    if merchant_id is not None:
        data["pgw_merchant_id"] = merchant_id.strip()
    if secret_key is not None:
        data["pgw_secret_key"] = secret_key.strip()
    if webhook_url is not None:
        data["pgw_webhook_url"] = webhook_url.strip()
    if metode_aktif is not None:
        tidak_valid = [m for m in metode_aktif if m not in CHANNEL_VALID]
        if tidak_valid:
            raise ValueError(f"Channel pembayaran tidak dikenal: {', '.join(tidak_valid)}.")
        data[_KUNCI_METODE_AKTIF] = json.dumps(metode_aktif)
    if data:
        db.set_settings_bulk(data, tenant_id=None)
    return get_config()


def get_public_channels() -> dict:
    """Aman untuk endpoint publik -- HANYA daftar channel aktif (urut) +
    labelnya, TIDAK PERNAH menyertakan kredensial apa pun."""
    cfg = get_config()
    return {
        "aktif": cfg["metode_aktif"],
        "nama": {k: CHANNEL_LABEL[k] for k in cfg["metode_aktif"] if k in CHANNEL_LABEL},
    }
