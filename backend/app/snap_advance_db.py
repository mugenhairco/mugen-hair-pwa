"""snap_advance_db.py — Konfigurasi Faspay SNAP Advance (PLATFORM-WIDE)
=============================================================================
Migrasi Faspay SNAP Advance (lihat laporan analisis "Faspay SNAP Migration"
dan instruksi migrasi lengkap): kredensial + konfigurasi untuk provider BARU
`snap_advance` -- dipakai BERSAMA untuk DUA jenis transaksi (Booking Payment
Tenant & SaaS Billing), SATU Merchant ID Faspay yang sama (keputusan
arsitektur eksplisit dari instruksi migrasi), TAPI modul konfigurasi ini
TERPISAH TOTAL dari payment_gateway_db.py (kredensial Xpress booking) dan
billing_gateway_db.py (kredensial Xpress billing) -- provider LAMA (Xpress
v4) TETAP berjalan penuh selama masa transisi, TIDAK disentuh sama sekali di
sini (lihat Tahap 13 instruksi migrasi: Xpress baru dihapus setelah SNAP
Advance tervalidasi produksi).

KEPUTUSAN ARSITEKTUR (deviasi SADAR dari instruksi #10 "gunakan environment
variables/secrets, jangan hardcode credential"): kredensial di sini TETAP
disimpan di tabel `settings` (tenant_id=None), BUKAN environment variable --
pola SAMA PERSIS dengan payment_gateway_db.py/billing_gateway_db.py, yang
KEDUANYA sengaja dipindah DARI env var KE database (lihat komentar sejarah
billing_gateway_db.py) supaya Super Admin bisa mengubah kredensial kapan pun
lewat UI tanpa redeploy. Payload webhook/checkout Faspay yang lain (secret_key
Xpress, dst) SUDAH tersimpan sebagai baris `settings` biasa di proyek ini --
menyimpan kredensial SNAP dengan cara BERBEDA (env var) untuk provider yang
akan MENGGANTIKAN provider itu akan memecah pola yang sudah konsisten dan
proven di seluruh proyek ini, tanpa manfaat keamanan tambahan yang nyata
(server yang sama, akses yang sama). Deviasi ini didokumentasikan eksplisit
di laporan hasil implementasi -- Owner/Super Admin bisa memutuskan lain kalau
memang menghendaki env var, tapi defaultnya mengikuti konvensi existing.

SEMUA field kredensial SNAP presisi (nama field yang benar-benar diharapkan
Faspay, format private key yang diterima, dst) masih PENDING FASPAY -- lihat
snap_advance_client.py untuk daftar lengkap yang belum bisa dipastikan. Modul
INI hanya menyediakan TEMPAT PENYIMPANAN generik (nama kolom/field di sisi
proyek kita sendiri, yang KITA kendalikan penuh) -- bukan klaim bahwa nama
field ini sudah cocok dengan APA yang diminta Faspay di form/API mereka."""

import json

import database as db

_KEYS_KREDENSIAL = [
    "snap_environment", "snap_sandbox_base_url", "snap_production_base_url",
    "snap_merchant_id", "snap_partner_id", "snap_client_id", "snap_client_secret",
    "snap_private_key", "snap_faspay_public_key", "snap_webhook_secret",
]
_KUNCI_TIMEOUT = "snap_timeout_detik"
_KUNCI_RETRY_MAX = "snap_retry_max"
_KUNCI_CHANNEL_AKTIF = "snap_channel_aktif"

ENVIRONMENT_VALID = {"sandbox", "production"}

# CATATAN (Tahap 2.3 laporan analisis): "ewallet" SENGAJA TIDAK dimasukkan ke
# CHANNEL_LABEL/CHANNEL_VALID di sini -- jalur teknisnya (lewat SNAP QRIS
# atau API terpisah) PENDING FASPAY, belum bisa dinyatakan sebagai channel
# yang "tersedia" untuk dipilih Super Admin sampai dikonfirmasi. "va"/"qris"
# dimasukkan sebagai STRUKTUR yang siap dipakai (bentuk umumnya terkonfirmasi
# dokumentasi publik SNAP), TAPI create-transaction sungguhan tetap melempar
# PENDING FASPAY sampai skema request/response persis Faspay terkonfirmasi
# (lihat snap_advance_client.py) -- kolom ini murni penyimpanan preferensi
# Super Admin, TIDAK berarti channel-nya sudah berfungsi.
#
# "direct_debit" JUGA SENGAJA TIDAK dimasukkan, TAPI dengan alasan BEDA dari
# ewallet: endpoint payment-nya sendiri sudah lebih terkonfirmasi daripada
# QRIS (lihat snap_advance_client.py::buat_transaksi_direct_debit()), TAPI
# Direct Debit punya PRASYARAT (Registrasi/Account Binding, OTP/OAuth2) yang
# SAMA SEKALI belum terkonfirmasi (snap_advance_client.py::daftarkan_binding_akun())
# -- mengaktifkan channel yang payment-nya "cukup siap" tapi binding-nya
# tidak pernah bisa jalan akan menyesatkan Super Admin (channel muncul aktif
# padahal customer/tenant tidak pernah bisa menautkan rekening mereka sama
# sekali). Skema DB (snap_account_bindings, kolom binding_id) tetap dibangun
# di muka (lihat snap_payment_migrasi.py) supaya begitu binding terkonfirmasi,
# TIDAK perlu migrasi tambahan -- hanya CHANNEL_LABEL di sini yang perlu diisi.
CHANNEL_LABEL = {"va": "Dynamic Virtual Account", "qris": "Dynamic QRIS"}
CHANNEL_VALID = set(CHANNEL_LABEL.keys())
_DEFAULT_CHANNEL_AKTIF = json.dumps([])

_DEFAULT_TIMEOUT_DETIK = 30
_DEFAULT_RETRY_MAX = 3


def get_config() -> dict:
    """Config LENGKAP termasuk kredensial -- HANYA dipanggil dari endpoint
    require_superadmin (routers/snap_advance.py), tidak pernah diekspos ke
    tenant/publik (pola sama persis payment_gateway_db.py::get_config())."""
    data = {k: db.get_setting(k, "", tenant_id=None) for k in _KEYS_KREDENSIAL}
    if data["snap_environment"] not in ENVIRONMENT_VALID:
        data["snap_environment"] = "sandbox"
    try:
        data["snap_timeout_detik"] = int(db.get_setting(_KUNCI_TIMEOUT, str(_DEFAULT_TIMEOUT_DETIK), tenant_id=None))
    except (TypeError, ValueError):
        data["snap_timeout_detik"] = _DEFAULT_TIMEOUT_DETIK
    try:
        data["snap_retry_max"] = int(db.get_setting(_KUNCI_RETRY_MAX, str(_DEFAULT_RETRY_MAX), tenant_id=None))
    except (TypeError, ValueError):
        data["snap_retry_max"] = _DEFAULT_RETRY_MAX
    try:
        channel_aktif = json.loads(db.get_setting(_KUNCI_CHANNEL_AKTIF, _DEFAULT_CHANNEL_AKTIF, tenant_id=None))
    except (TypeError, ValueError):
        channel_aktif = []
    data["snap_channel_aktif"] = channel_aktif
    data["channel_label"] = CHANNEL_LABEL
    # "enabled": SENGAJA konservatif -- field kredensial minimal yang
    # DIPERKIRAKAN dibutuhkan skema token B2B SNAP (merchant_id/client_id/
    # client_secret/private_key), TAPI ini BUKAN jaminan kredensial ini
    # benar-benar valid/cocok dengan yang diminta Faspay (PENDING FASPAY) --
    # murni penanda "sudah diisi sesuatu", bukan "sudah terverifikasi
    # berfungsi". Endpoint create-transaction TETAP melempar PENDING FASPAY
    # terlepas dari nilai enabled ini (lihat snap_advance_client.py).
    data["enabled"] = bool(data["snap_merchant_id"] and data["snap_client_id"]
                            and data["snap_client_secret"] and data["snap_private_key"])
    return data


def update_config(environment: str = None, sandbox_base_url: str = None, production_base_url: str = None,
                   merchant_id: str = None, partner_id: str = None, client_id: str = None,
                   client_secret: str = None, private_key: str = None, faspay_public_key: str = None,
                   webhook_secret: str = None, timeout_detik: int = None, retry_max: int = None,
                   channel_aktif: list = None) -> dict:
    data = {}
    if environment is not None:
        if environment not in ENVIRONMENT_VALID:
            raise ValueError("Environment harus 'sandbox' atau 'production'.")
        data["snap_environment"] = environment
    if sandbox_base_url is not None:
        data["snap_sandbox_base_url"] = sandbox_base_url.strip()
    if production_base_url is not None:
        data["snap_production_base_url"] = production_base_url.strip()
    if merchant_id is not None:
        data["snap_merchant_id"] = merchant_id.strip()
    if partner_id is not None:
        data["snap_partner_id"] = partner_id.strip()
    if client_id is not None:
        data["snap_client_id"] = client_id.strip()
    if client_secret is not None:
        data["snap_client_secret"] = client_secret.strip()
    if private_key is not None:
        data["snap_private_key"] = private_key.strip()
    if faspay_public_key is not None:
        data["snap_faspay_public_key"] = faspay_public_key.strip()
    if webhook_secret is not None:
        data["snap_webhook_secret"] = webhook_secret.strip()
    if timeout_detik is not None:
        if timeout_detik <= 0:
            raise ValueError("Timeout harus lebih dari 0 detik.")
        data[_KUNCI_TIMEOUT] = str(timeout_detik)
    if retry_max is not None:
        if retry_max < 0:
            raise ValueError("Retry max tidak boleh negatif.")
        data[_KUNCI_RETRY_MAX] = str(retry_max)
    if channel_aktif is not None:
        tidak_valid = [c for c in channel_aktif if c not in CHANNEL_VALID]
        if tidak_valid:
            raise ValueError(f"Channel SNAP Advance tidak dikenal/belum didukung: {', '.join(tidak_valid)}.")
        data[_KUNCI_CHANNEL_AKTIF] = json.dumps(channel_aktif)
    if data:
        db.set_settings_bulk(data, tenant_id=None)
    return get_config()
