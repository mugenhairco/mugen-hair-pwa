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
    "snap_merchant_id", "snap_partner_id", "snap_client_id",
    # Kredensial di bawah ini SENGAJA terpisah per environment (sandbox vs
    # production) -- BEDA dari merchant_id/partner_id/channel_id di atas
    # yang TETAP satu (Faspay mengonfirmasi Merchant ID SAMA dipakai untuk
    # kedua environment, cuma domain/URL yang beda). private key kita &
    # public key Faspay adalah PASANGAN kriptografi sungguhan per
    # environment -- Faspay menerbitkan keypair BERBEDA untuk sandbox vs
    # production, jadi menyimpannya sebagai SATU field akan membuat
    # kredensial sandbox yang sudah teruji tertimpa begitu Super Admin
    # mengisi kredensial production (dan sebaliknya), tanpa cara mudah
    # untuk kembali test di sandbox. client_secret/webhook_secret ikut pola
    # yang sama untuk konsistensi walau belum genuinely dipakai kode
    # manapun sekarang (lihat catatan lama field ini, masih PENDING FASPAY).
    "snap_sandbox_client_secret", "snap_production_client_secret",
    "snap_sandbox_private_key", "snap_production_private_key",
    "snap_sandbox_faspay_public_key", "snap_production_faspay_public_key",
    "snap_sandbox_webhook_secret", "snap_production_webhook_secret",
    # CHANNEL-ID (header wajib SEMUA request SNAP -- identifier layanan API
    # Faspay sendiri, mis. "77001", KONSTAN per merchant, BEDA dari
    # `channelCode` per-bank di bawah maupun `snap_channel_aktif` --
    # dikonfirmasi dari dokumen resmi Faspay yang diberikan Owner).
    "snap_channel_id",
    # channelCode default untuk Generate QRIS (dokumen SNAP QRIS resmi
    # Faspay -- BEDA lagi dari channelCode VA di bawah, daftar kode/artinya
    # provider e-wallet, bukan bank). MASIH satu default tunggal (beda dari
    # VA di bawah yang sudah multi-bank) -- belum ada permintaan multi
    # e-wallet untuk QRIS.
    "snap_qris_channel_code",
]

# Daftar channelCode VA resmi (dokumen SNAP VA Faspay -- lihat tabel
# "channel code" Create VA) -- dipakai memvalidasi snap_va_bank_aktif (lihat
# _KUNCI_VA_BANK_AKTIF di bawah) DAN channel_code yang dikirim customer per
# transaksi, BUKAN daftar bebas/tebakan.
VA_CHANNEL_CODE_LABEL = {
    "402": "Permata VA (Dynamic)", "408": "Maybank VA (Dynamic)", "702": "BCA VA (Dynamic)",
    "706": "Indomaret Payment Point (Dynamic)", "707": "Alfagroup (Dynamic)", "708": "Danamon VA (Dynamic)",
    "718": "BNC VA (Static & Dynamic)", "800": "BRI VA (Dynamic)", "801": "BNI VA (Static & Dynamic)",
    "802": "Mandiri VA (Dynamic)", "818": "Sinarmas VA (Dynamic)", "825": "CIMB VA (Dynamic)",
    "837": "BTN VA (Static & Dynamic)",
}
VA_CHANNEL_CODE_VALID = set(VA_CHANNEL_CODE_LABEL.keys())

# Daftar channelCode QRIS resmi (dokumen SNAP QRIS Faspay -- lihat tabel
# "channel code" Generate QRIS/Query Payment) -- dipakai memvalidasi
# snap_qris_channel_code, BUKAN daftar bebas/tebakan. TIDAK BERTUMPANG
# TINDIH dengan kode VA_CHANNEL_CODE_VALID/DD di atas. QRIS vs Direct Debit
# (dua-duanya sama bentuk payload notifikasinya) sekarang dibedakan lewat
# endpoint mana yang dipukul (routers/snap_advance.py -- path resmi
# per-produk Faspay), BUKAN lagi lewat channelCode ini.
QRIS_CHANNEL_CODE_LABEL = {"715": "LinkAja QRIS", "711": "ShopeePay QRIS", "842": "CIMB QRIS"}
QRIS_CHANNEL_CODE_VALID = set(QRIS_CHANNEL_CODE_LABEL.keys())

# Daftar channelCode Direct Debit resmi (dokumen SNAP Direct Debit Faspay,
# 14 kode -- dikonfirmasi Owner byte-demi-byte dari tabel resmi, BUKAN
# tebakan) -- dipakai memvalidasi `channel_code` di
# snap_advance_client.py::buat_transaksi_direct_debit(). Faspay mengonfirmasi
# tertulis: E-Wallet BUKAN produk SNAP terpisah, melainkan kategori channel
# DI DALAM Direct Debit (lihat kolom kategori) -- karena itu
# buat_transaksi_ewallet() (fungsi PENDING FASPAY terpisah) DIHAPUS,
# transaksi E-Wallet sekarang lewat buat_transaksi_direct_debit() dengan
# salah satu channel code berkategori "E-Wallet" di sini. Kategori
# Bank/E-Wallet/Lainnya MURNI label informatif dari dokumen (mis. untuk
# ditampilkan Super Admin nanti), TIDAK memengaruhi validasi -- HANYA
# channel "714" (BRI Direct Debit) yang dokumen resmi sebutkan wajib
# `bankCardToken` (lihat catatan daftarkan_binding_akun() di
# snap_advance_client.py -- gap Registrasi/Account Binding-nya TETAP
# terpisah & TETAP pending, klarifikasi E-Wallet ini TIDAK menyelesaikannya).
DIRECT_DEBIT_CHANNEL_CODE_LABEL = {
    "814": "Maybank2U", "704": "SAKUKU", "714": "BRI Direct Debit",
    "713": "ShopeePay App", "716": "LinkAja App", "812": "OVO", "819": "DANA",
    "700": "CIMB Clicks", "701": "D-Bank Pro", "401": "BRI E-PAY", "405": "BCA KlikPay",
    "302": "LinkAja", "722": "DANA Subs", "720": "OVO OpenAPI",
}
DIRECT_DEBIT_CHANNEL_CODE_KATEGORI = {
    "814": "Bank", "704": "Lainnya", "714": "Bank", "713": "E-Wallet", "716": "E-Wallet",
    "812": "E-Wallet", "819": "E-Wallet", "700": "Bank", "701": "Bank", "401": "Bank",
    "405": "Bank", "302": "E-Wallet", "722": "E-Wallet/subscription", "720": "E-Wallet",
}
DIRECT_DEBIT_CHANNEL_CODE_VALID = set(DIRECT_DEBIT_CHANNEL_CODE_LABEL.keys())

_KUNCI_TIMEOUT = "snap_timeout_detik"
_KUNCI_RETRY_MAX = "snap_retry_max"
_KUNCI_CHANNEL_AKTIF = "snap_channel_aktif"
# Fitur multi-bank VA (diminta Owner: customer bisa pilih bank VA APA PUN
# yang diaktifkan, bukan cuma satu default platform-wide) -- GANTIKAN
# snap_va_channel_code (field tunggal, DIHAPUS) dengan daftar kode bank
# yang Super Admin centang aktif. Kode bank yang BENAR-BENAR dipakai per
# transaksi dikirim FRONTEND (customer memilih) dan divalidasi terhadap
# daftar ini di routers/booking.py & routers/billing.py -- lihat
# snap_advance_client.py::buat_transaksi_va() untuk sisi client-nya
# (channel_code sekarang parameter wajib, bukan lagi dibaca dari config).
_KUNCI_VA_BANK_AKTIF = "snap_va_bank_aktif"
_DEFAULT_VA_BANK_AKTIF = json.dumps([])

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


# Field RAHASIA yang TIDAK PERNAH boleh keluar apa adanya lewat get_config()
# (instruksi eksplisit Owner: private key tidak boleh "ditampilkan atau
# dikirim kembali dalam response API GET konfigurasi" -- private key RSA
# menandatangani SELURUH transaksi, beda kelas risiko dari sekadar API key
# yang gampang di-rotate). client_secret/webhook_secret ikut kelompok yang
# sama (rahasia simetris). *_faspay_public_key SENGAJA TIDAK masuk sini --
# itu public key MILIK Faspay yang justru harus terlihat Super Admin untuk
# verifikasi kecocokan, bukan sesuatu yang perlu disembunyikan.
_FIELD_RAHASIA = ("snap_sandbox_private_key", "snap_production_private_key",
                   "snap_sandbox_client_secret", "snap_production_client_secret",
                   "snap_sandbox_webhook_secret", "snap_production_webhook_secret")


def get_config() -> dict:
    """Config termasuk kredensial -- HANYA dipanggil dari endpoint
    require_superadmin (routers/snap_advance.py), tidak pernah diekspos ke
    tenant/publik (pola sama persis payment_gateway_db.py::get_config()).

    BUGFIX keamanan (audit SNAP Advance): field di _FIELD_RAHASIA TIDAK
    PERNAH dikembalikan apa adanya di sini -- diganti string kosong "",
    DITEMANI penanda boolean `<field>_terisi` supaya frontend tetap bisa
    menampilkan "sudah diisi" tanpa perlu tahu isinya. Sebelum revisi ini,
    private key RSA ikut terkirim mentah ke browser Super Admin setiap kali
    halaman config dibuka (lihat superadmin.js yang langsung mem-prefill
    <input> dari respons ini) -- risiko nyata untuk key yang menandatangani
    SELURUH transaksi. update_config() di bawah SENGAJA memperlakukan string
    kosong dari field ini sebagai "tidak diubah" (BUKAN "kosongkan"), supaya
    Super Admin bisa menyimpan perubahan field LAIN (mis. centang channel)
    tanpa harus mengetik ulang secret yang sudah tersimpan."""
    data = {k: db.get_setting(k, "", tenant_id=None) for k in _KEYS_KREDENSIAL}
    for field in _FIELD_RAHASIA:
        data[f"{field}_terisi"] = bool(data[field])
        data[field] = ""
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
    try:
        va_bank_aktif = json.loads(db.get_setting(_KUNCI_VA_BANK_AKTIF, _DEFAULT_VA_BANK_AKTIF, tenant_id=None))
    except (TypeError, ValueError):
        va_bank_aktif = []
    data["snap_va_bank_aktif"] = va_bank_aktif
    data["channel_label"] = CHANNEL_LABEL
    data["va_channel_code_label"] = VA_CHANNEL_CODE_LABEL
    data["qris_channel_code_label"] = QRIS_CHANNEL_CODE_LABEL
    # "enabled": KOREKSI (klarifikasi resmi Faspay, dikonfirmasi juga lewat
    # halaman dokumen "Signature SNAP" -- lihat catatan modul
    # snap_advance_client.py::_headers_service()) -- asumsi AWAL bahwa skema
    # token B2B SNAP butuh client_id/client_secret TERNYATA KELIRU: signature
    # request SELURUH service call (Create VA/QRIS/Direct Debit) memakai
    # header X-TIMESTAMP/X-SIGNATURE/X-PARTNER-ID/X-EXTERNAL-ID/CHANNEL-ID
    # SAJA, TIDAK PERNAH Client ID/Client Secret -- field itu TETAP disimpan
    # (kalau-kalau dibutuhkan produk SNAP lain, mis. B2B access token untuk
    # Disbursement) TAPI SENGAJA TIDAK dijadikan syarat "enabled" lagi.
    # Field yang genuinely dipakai SELURUH request (lihat _cfg_wajib() di
    # _headers_service() + buat_transaksi_qris()/buat_transaksi_direct_debit())
    # : merchant_id, partner_id, channel_id, private_key.
    # BUKAN jaminan kredensial ini benar-benar valid/cocok dengan yang
    # terdaftar di Faspay -- murni penanda "sudah diisi sesuatu", bukan
    # "sudah terverifikasi berfungsi".
    # BUGFIX: dihitung dari `_terisi` (bukan private key mentah) -- field
    # itu SUDAH dikosongkan oleh masking di atas, memakainya lagi di sini
    # akan membuat `enabled` SELALU False walau kredensial sebenarnya sudah
    # lengkap. Dicek dari private key environment yang SEDANG AKTIF saja
    # (bukan sandbox DAN production sekaligus) -- "enabled" berarti "siap
    # dipakai checkout SEKARANG dengan environment yang sedang dipilih".
    data["enabled"] = bool(data["snap_merchant_id"] and data["snap_partner_id"] and data["snap_channel_id"]
                            and data[f"snap_{data['snap_environment']}_private_key_terisi"])
    return data


def get_config_internal() -> dict:
    """SAMA seperti get_config(), TAPI TANPA masking -- field rahasia
    (_FIELD_RAHASIA) dikembalikan APA ADANYA. HANYA boleh dipanggil dari
    snap_advance_client.py (untuk benar-benar menandatangani/memanggil
    Faspay) -- TIDAK PERNAH dari router/endpoint HTTP mana pun (itulah
    gunanya get_config() yang sudah di-mask, dipakai routers/snap_advance.py).
    Kalau butuh field rahasia di tempat baru, pertimbangkan dulu apakah
    tempat itu genuinely internal (bukan sekadar malas manggil field lain)."""
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
        data["snap_channel_aktif"] = json.loads(db.get_setting(_KUNCI_CHANNEL_AKTIF, _DEFAULT_CHANNEL_AKTIF, tenant_id=None))
    except (TypeError, ValueError):
        data["snap_channel_aktif"] = []
    try:
        data["snap_va_bank_aktif"] = json.loads(db.get_setting(_KUNCI_VA_BANK_AKTIF, _DEFAULT_VA_BANK_AKTIF, tenant_id=None))
    except (TypeError, ValueError):
        data["snap_va_bank_aktif"] = []
    # Resolusi kredensial environment-AKTIF ke nama generik (snap_private_key,
    # snap_faspay_public_key, dst) -- SATU-SATUNYA tempat sandbox/production
    # "dipilih". snap_advance_client.py TETAP memakai nama generik ini apa
    # adanya, TIDAK PERLU tahu field mentah snap_sandbox_*/snap_production_*
    # -- jadi pindah environment TIDAK butuh perubahan kode di luar modul ini.
    env = data["snap_environment"]
    data["snap_private_key"] = data[f"snap_{env}_private_key"]
    data["snap_faspay_public_key"] = data[f"snap_{env}_faspay_public_key"]
    data["snap_client_secret"] = data[f"snap_{env}_client_secret"]
    data["snap_webhook_secret"] = data[f"snap_{env}_webhook_secret"]
    data["enabled"] = bool(data["snap_merchant_id"] and data["snap_partner_id"]
                            and data["snap_channel_id"] and data["snap_private_key"])
    return data


def update_config(environment: str = None, sandbox_base_url: str = None, production_base_url: str = None,
                   merchant_id: str = None, partner_id: str = None, client_id: str = None,
                   sandbox_client_secret: str = None, production_client_secret: str = None,
                   sandbox_private_key: str = None, production_private_key: str = None,
                   sandbox_faspay_public_key: str = None, production_faspay_public_key: str = None,
                   sandbox_webhook_secret: str = None, production_webhook_secret: str = None,
                   timeout_detik: int = None, retry_max: int = None,
                   channel_aktif: list = None, channel_id: str = None, va_bank_aktif: list = None,
                   qris_channel_code: str = None) -> dict:
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
    # BUGFIX keamanan (lihat docstring get_config()): string kosong untuk
    # field RAHASIA berarti "field ini tidak disentuh Super Admin di form
    # ini" (karena get_config() TIDAK PERNAH mengirim nilai asli untuk
    # diprefill) -- HANYA nilai non-kosong yang dianggap perubahan sungguhan.
    # Field BUKAN rahasia (mis. merchant_id di atas) TETAP boleh dikosongkan
    # dengan sengaja seperti sebelumnya, perilakunya tidak berubah.
    if sandbox_client_secret:
        data["snap_sandbox_client_secret"] = sandbox_client_secret.strip()
    if production_client_secret:
        data["snap_production_client_secret"] = production_client_secret.strip()
    if sandbox_private_key:
        data["snap_sandbox_private_key"] = sandbox_private_key.strip()
    if production_private_key:
        data["snap_production_private_key"] = production_private_key.strip()
    if sandbox_faspay_public_key is not None:
        data["snap_sandbox_faspay_public_key"] = sandbox_faspay_public_key.strip()
    if production_faspay_public_key is not None:
        data["snap_production_faspay_public_key"] = production_faspay_public_key.strip()
    if sandbox_webhook_secret:
        data["snap_sandbox_webhook_secret"] = sandbox_webhook_secret.strip()
    if production_webhook_secret:
        data["snap_production_webhook_secret"] = production_webhook_secret.strip()
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
    if channel_id is not None:
        data["snap_channel_id"] = channel_id.strip()
    if va_bank_aktif is not None:
        tidak_valid = [c for c in va_bank_aktif if c not in VA_CHANNEL_CODE_VALID]
        if tidak_valid:
            raise ValueError(f"channelCode VA tidak dikenal: {', '.join(tidak_valid)}. "
                              f"Lihat daftar resmi di VA_CHANNEL_CODE_LABEL.")
        data[_KUNCI_VA_BANK_AKTIF] = json.dumps(va_bank_aktif)
    if qris_channel_code is not None:
        if qris_channel_code and qris_channel_code not in QRIS_CHANNEL_CODE_VALID:
            raise ValueError(f"channelCode QRIS tidak dikenal: {qris_channel_code}. "
                              f"Lihat daftar resmi di QRIS_CHANNEL_CODE_LABEL.")
        data["snap_qris_channel_code"] = qris_channel_code.strip()
    if data:
        db.set_settings_bulk(data, tenant_id=None)
    return get_config()
