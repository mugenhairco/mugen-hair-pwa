"""snap_advance_client.py — Klien Faspay SNAP Advance
=============================================================================
Migrasi Faspay SNAP Advance -- lihat laporan analisis "Faspay SNAP Migration"
(Tahap 2) & laporan audit lanjutan untuk sumber & batasan lengkap. Provider
BARU, TERPISAH TOTAL dari payment_gateway_client.py/billing_gateway_client.py
(Xpress v4) -- per keputusan Owner, Xpress v4 TIDAK LAGI jadi payment flow
yang dipakai (satu-satunya Payment Notification URL Faspay untuk Merchant ID
37070 sekarang mengarah ke SNAP, lihat routers/snap_advance.py), TAPI modul
Xpress TIDAK dihapus di sini (audit dependency terpisah, lihat laporan --
booking_db.py/billing_webhook.py/billing_invoice_db.py yang dipakai cascade
SNAP di bawah adalah modul BERSAMA, bukan modul Xpress itu sendiri).

INTERFACE modul ini (nama fungsi/parameter) SENGAJA meniru pola
payment_gateway_client.py (is_enabled(), buat_transaksi_*(),
verifikasi_signature_webhook(), cek_status_transaksi()) supaya pemanggil di
lapisan atas TIDAK PERNAH perlu tahu detail wire-protocol provider.

=============================================================================
STATUS IMPLEMENTASI per channel (audit lanjutan, setelah Faspay memberikan
dokumen resmi SNAP VA, SNAP Direct Debit, DAN SNAP QRIS)
=============================================================================
- **VA (Virtual Account)**: Create VA, Inquiry Status VA, parsing Payment
  Notification SUDAH diimplementasikan sungguhan dari dokumen resmi Faspay
  (path/field endpoint dikonfirmasi dari dokumen yang diberikan Owner).
- **Direct Debit**: Payment (host-to-host), Status, parsing Notification
  SUDAH diimplementasikan sungguhan dari dokumen resmi yang sama. Registrasi/
  Account Binding TETAP PENDING FASPAY TOTAL (lihat daftarkan_binding_akun()
  di bawah) -- dokumen yang diberikan TIDAK menyertakan bagian ini sama
  sekali, dan TIDAK ADA asumsi dibuat soal channel mana yang butuh binding
  (per instruksi eksplisit Owner "jangan membuat asumsi mengenai Account
  Binding untuk semua channel Direct Debit").
- **QRIS**: Generate QRIS, Query Payment, parsing Payment Notification SUDAH
  diimplementasikan sungguhan dari dokumen resmi Faspay yang diberikan
  Owner (buat_transaksi_qris()/query_payment_qris()). `phoneNo` WAJIB
  (beda dari VA yang opsional) -- melempar ValueError kalau tidak diisi.
- **E-Wallet**: audit lanjutan #4 -- Faspay mengonfirmasi tertulis E-Wallet
  BUKAN produk SNAP terpisah, melainkan KATEGORI channel di dalam Direct
  Debit (14 channelCode resmi, lihat snap_advance_db.DIRECT_DEBIT_CHANNEL_CODE_LABEL).
  Fungsi `buat_transaksi_ewallet()` yang tadinya PENDING FASPAY terpisah
  DIHAPUS -- transaksi E-Wallet (OVO/DANA/ShopeePay/LinkAja/dst) sekarang
  lewat buat_transaksi_direct_debit() dengan channel code berkategori
  "E-Wallet". Registrasi/Account Binding (daftarkan_binding_akun()) TETAP
  PENDING FASPAY -- klarifikasi ini TIDAK menyelesaikan gap itu.

=============================================================================
CATATAN SIGNATURE -- SUDAH dikonfirmasi 1:1 ke halaman resmi Faspay
=============================================================================
Owner memberikan isi halaman resmi "Signature SNAP" Faspay
(docs.faspay.co.id/merchant-integration/api-reference-1/snap/signature-snap).
Formula DIVERIFIKASI MANUAL byte-demi-byte terhadap DUA contoh angka resmi
di halaman itu (hash body SHA-256 & signature RSA-SHA256 Create VA, DAN
hash body contoh Verifying Signature VA Inquiry) -- KEDUANYA cocok persis.
Kesimpulan PENTING yang mengoreksi asumsi audit sebelumnya:

1. **Signature SEMUA request SNAP (bukan cuma /access-token/b2b) memakai
   ASYMMETRIC RSA-SHA256** dengan private key merchant -- BUKAN symmetric
   HMAC seperti dugaan awal (dugaan awal itu KELIRU, sudah diperbaiki).
2. **stringToSign TIDAK menyertakan access token sama sekali**:
   `HTTPMethod + ":" + EndpointUrl + ":" + Lowercase(HexEncode(SHA256(minify(RequestBody)))) + ":" + TimeStamp`
   -- lihat gateway_client_base.py::sign_sha256_rsa()/sha256_lowercase_hex().
3. **Sample Request Header resmi Create VA TIDAK menyertakan header
   Authorization/Bearer token sama sekali** (hanya X-TIMESTAMP/X-SIGNATURE/
   X-PARTNER-ID/X-EXTERNAL-ID/CHANNEL-ID) -- karena itu `ambil_token_b2b()`
   di bawah TIDAK dipanggil dari jalur VA/Direct Debit manapun. Fungsi itu
   TETAP disimpan (endpoint `/access-token/b2b` genuinely bagian standar
   SNAP, disebut di tabel EndpointURL halaman Signature SNAP untuk produk
   lain seperti SNAP Disbursement) TAPI statusnya UNCONFIRMED-UNUSED untuk
   VA/Direct Debit -- kalau Faspay mengonfirmasi token TETAP dibutuhkan,
   tinggal disambungkan kembali di _headers_service().

`minify(RequestBody)` = JSON compact TANPA spasi (json.dumps separators=
(",", ":")) -- dikonfirmasi PERSIS lewat kedua contoh di atas."""

import json
import re

import gateway_client_base as core
import snap_advance_db

_TIMEOUT_DEFAULT = 30

# ---------------------------------------------------------------------------
# Path endpoint -- lihat catatan modul soal mana yang terkonfirmasi dokumen
# resmi Faspay (VA & Direct Debit) vs mana yang masih konvensi SNAP standar.
# ---------------------------------------------------------------------------
PATH_ACCESS_TOKEN_B2B = "/v1.0/access-token/b2b"  # disebut di tabel EndpointURL halaman resmi "Signature SNAP", TAPI UNCONFIRMED-UNUSED untuk VA/Direct Debit/QRIS (lihat catatan modul)
PATH_VA_CREATE = "/v1.0/transfer-va/create-va"  # terkonfirmasi dokumen resmi Faspay
PATH_VA_INQUIRY_STATUS = "/v1.0/transfer-va/status"  # terkonfirmasi dokumen resmi Faspay ("Inquiry Status", servis 26)
PATH_DD_PAYMENT = "/v1.0/debit/payment-host-to-host"  # terkonfirmasi dokumen resmi Faspay
PATH_DD_STATUS = "/v1.0/debit/status"  # terkonfirmasi dokumen resmi Faspay
PATH_QRIS_GENERATE = "/v1.0/qr/qr-mpm-generate"  # terkonfirmasi dokumen resmi Faspay (servis 47)
PATH_QRIS_QUERY = "/v1.0/qr/qr-mpm-query"  # terkonfirmasi dokumen resmi Faspay (servis 51)


class SnapAdvancePendingError(core.GatewayError):
    """Ditandai TERPISAH dari GatewayError generik (walau tetap turunannya,
    supaya router yang sudah menangkap GatewayError otomatis ikut menangkap
    ini) -- supaya log/monitoring bisa membedakan dengan jelas "belum
    diimplementasikan karena menunggu Faspay" dari kegagalan jaringan/
    provider sungguhan (GatewayTimeoutError/GatewayRequestError)."""


def pending_faspay(area: str, detail: str) -> SnapAdvancePendingError:
    return SnapAdvancePendingError(
        f"SNAP Advance -- {area}: PENDING FASPAY. {detail} "
        f"Lihat laporan analisis \"Faspay SNAP Migration\" & laporan audit lanjutan."
    )


def is_enabled() -> bool:
    """Config MINIMAL sudah diisi Super Admin -- BUKAN jaminan create-
    transaction sungguhan berfungsi, murni penanda "siap dicoba"."""
    return snap_advance_db.get_config()["enabled"]


def is_production() -> bool:
    return snap_advance_db.get_config()["snap_environment"] == "production"


def _base_url(is_prod: bool) -> str:
    cfg = snap_advance_db.get_config_internal()
    url = cfg["snap_production_base_url"] if is_prod else cfg["snap_sandbox_base_url"]
    if not url:
        raise core.GatewayNotConfiguredError(
            f"Base URL SNAP Advance ({'production' if is_prod else 'sandbox'}) belum diisi Super Admin."
        )
    return url.rstrip("/")


def _cfg_wajib(cfg: dict, *fields: str) -> None:
    hilang = [f for f in fields if not cfg.get(f)]
    if hilang:
        raise core.GatewayNotConfiguredError(
            f"SNAP Advance belum lengkap: {', '.join(hilang)} belum diisi Super Admin."
        )


def _minify(body: dict) -> str:
    return json.dumps(body, separators=(",", ":"))


def ambil_token_b2b() -> str:
    """Token akses B2B SNAP -- endpoint `/access-token/b2b` disebut di
    tabel EndpointURL halaman resmi "Signature SNAP" (Faspay, untuk produk
    lain seperti SNAP Disbursement), TAPI TIDAK terbukti dibutuhkan untuk
    VA/Direct Debit (sample Request Header resmi Create VA TIDAK
    menyertakan Authorization/Bearer sama sekali -- lihat catatan modul).
    Fungsi ini TIDAK dipanggil dari jalur VA/Direct Debit manapun saat ini
    -- disimpan sebagai utilitas standalone kalau-kalau dibutuhkan produk
    lain/dikonfirmasi Faspay di kemudian hari. Signature memakai formula
    YANG SAMA dengan seluruh service call SNAP (lihat _headers_service()),
    KONSISTEN dengan halaman resmi yang tidak menunjukkan formula berbeda
    untuk endpoint token -- request body ("grantType": "client_credentials")
    sendiri MASIH KONVENSI (belum ada contoh persis dari Faspay)."""
    cfg = snap_advance_db.get_config_internal()
    _cfg_wajib(cfg, "snap_private_key")
    raw_body = _minify({"grantType": "client_credentials"})
    headers = _headers_service("POST", PATH_ACCESS_TOKEN_B2B, raw_body, cfg)
    url = _base_url(is_production()) + PATH_ACCESS_TOKEN_B2B
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    token = resp.get("accessToken") or resp.get("access_token")
    if not token:
        raise core.GatewayRequestError(f"Respons token B2B SNAP Advance tidak berisi accessToken: {resp}")
    return token


def _headers_service(method: str, path: str, raw_body: str, cfg: dict) -> dict:
    """Header lengkap untuk SELURUH service call SNAP -- signature
    ASYMMETRIC (RSA-SHA256, private key merchant), DIKONFIRMASI 1:1 ke
    halaman resmi Faspay "Signature SNAP" (lihat catatan modul: dua contoh
    resmi diverifikasi manual byte-demi-byte, keduanya cocok). Formula:
    `{method}:{path}:{sha256_lowercase_hex(raw_body)}:{X-TIMESTAMP}`, TANPA
    komponen access token. `raw_body` HARUS string PERSIS yang nanti
    dikirim lewat core.post_json_raw() -- lihat catatan post_json_raw()
    soal kenapa hash body harus dihitung dari bytes yang SAMA PERSIS dengan
    yang benar-benar terkirim. TIDAK ADA header Authorization/Bearer di
    sini -- sample resmi Faspay untuk Create VA tidak menyertakannya."""
    _cfg_wajib(cfg, "snap_partner_id", "snap_channel_id", "snap_private_key")
    ts = core.snap_timestamp_wib()
    body_hash = core.sha256_lowercase_hex(raw_body)
    string_to_sign = f"{method}:{path}:{body_hash}:{ts}"
    signature = core.sign_sha256_rsa(string_to_sign, cfg["snap_private_key"])
    return {
        "Content-Type": "application/json",
        "X-TIMESTAMP": ts,
        "X-SIGNATURE": signature,
        "X-PARTNER-ID": cfg["snap_partner_id"],
        "X-EXTERNAL-ID": core.buat_external_id(),
        "CHANNEL-ID": cfg["snap_channel_id"],
    }


def _format_msisdn_62(nomor: str) -> str:
    """Format nomor WhatsApp jadi "62xxxxxxxxxxxxx" sesuai field
    `virtualAccountPhone` dokumen resmi -- nomor lokal di sistem ini bisa
    tersimpan berformat "08xx"/"+62xx"/"62xx", dirapikan di sini supaya
    konsisten sebelum dikirim ke Faspay."""
    digit = re.sub(r"\D", "", nomor or "")
    if digit.startswith("0"):
        digit = "62" + digit[1:]
    elif not digit.startswith("62"):
        digit = "62" + digit
    return digit


def buat_transaksi_va(payment_reference: str, amount: int, customer_details: dict = None,
                       *, channel_code: str) -> dict:
    """Create Dynamic VA -- POST {base}/v1.0/transfer-va/create-va (dokumen
    resmi Faspay). `customer_details` opsional: {"nama", "email", "whatsapp"}.
    `payment_reference` dipakai sebagai `trxId` (WAJIB, maks 32 karakter per
    dokumen -- format payment_reference proyek ini, mis.
    "BOOKING-1-42-abcdef123456", secara wajar tetap di bawah batas itu untuk
    id tenant/entity yang tidak terlalu besar; DIPOTONG kalau kebetulan
    melebihi, TIDAK melempar error, supaya create VA tidak gagal hanya
    karena panjang string -- risiko tabrakan trxId dianggap dapat diterima
    mengingat sufiks UUID 12-hex di akhir referensi).

    `channel_code` (kode bank VA, mis. "702"=BCA) WAJIB diisi PEMANGGIL
    (fitur multi-bank VA -- customer memilih bank di halaman booking/billing,
    lihat payment_provider_client.py) -- TIDAK LAGI dibaca dari config
    (snap_va_channel_code DIHAPUS, digantikan snap_va_bank_aktif yang cuma
    daftar bank yang BOLEH dipilih, bukan satu default)."""
    cfg = snap_advance_db.get_config_internal()
    if channel_code not in snap_advance_db.VA_CHANNEL_CODE_VALID:
        raise core.GatewayNotConfiguredError(f"channelCode VA tidak dikenal: {channel_code!r}.")
    customer_details = customer_details or {}
    now = core.now_wib()
    ts_now = core.snap_timestamp_wib()
    expired = now.replace(hour=23, minute=59, second=59)
    body = {
        "virtualAccountName": (customer_details.get("nama") or "Customer")[:128],
        "trxId": payment_reference[:32],
        "totalAmount": {"value": f"{amount:.2f}", "currency": "IDR"},
        "expiredDate": expired.strftime("%Y-%m-%dT%H:%M:%S") + ts_now[-6:],
        "additionalInfo": {
            "billDate": ts_now,
            "channelCode": channel_code,
            "billDescription": "Pembayaran"[:18],
        },
    }
    if customer_details.get("email"):
        body["virtualAccountEmail"] = customer_details["email"][:128]
    if customer_details.get("whatsapp"):
        body["virtualAccountPhone"] = _format_msisdn_62(customer_details["whatsapp"])[:30]
    raw_body = _minify(body)
    headers = _headers_service("POST", PATH_VA_CREATE, raw_body, cfg)
    url = _base_url(is_production()) + PATH_VA_CREATE
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    # BUGFIX (dikonfirmasi dari respons SUKSES sungguhan sandbox Faspay,
    # bukan cuma dokumen): Create VA BRI (channelCode 800) mengembalikan
    # responseCode "2002700" ("Success") -- BUKAN "2002500" seperti yang
    # sebelumnya diasumsikan dari dokumen. Kode lama membuat transaksi yang
    # SEBENARNYA BERHASIL di sisi Faspay (VA sudah terbentuk) malah
    # ditolak/dibatalkan di sisi kita sendiri.
    if resp.get("responseCode") != "2002700":
        raise core.GatewayRequestError(f"Create VA SNAP Advance ditolak Faspay: {resp}")
    va = resp["virtualAccountData"]
    return {
        "va_number": va["virtualAccountNo"],
        "provider_transaction_id": va.get("trxId"),
        "expired_at": va.get("expiredDate"),
        "channel_code": channel_code,
        "provider_response": json.dumps(resp),
    }


def inquiry_status_va(payment_reference: str, virtual_account_no: str, channel_code: str) -> dict:
    """Inquiry Status VA -- POST {base}/v1.0/transfer-va/status (servis 26,
    dokumen resmi Faspay). `virtual_account_no` = va_number hasil
    buat_transaksi_va() (snap_payment_transactions.va_number). `channel_code`
    WAJIB = kode bank yang BENAR-BENAR dipakai saat transaksi ini dibuat
    (snap_payment_transactions.channel_code) -- fitur multi-bank VA berarti
    TIDAK ADA lagi satu default config yang bisa dipakai di sini (bisa beda
    dari bank yang sedang aktif SEKARANG kalau Super Admin sudah ubah
    pilihan sejak transaksi ini dibuat)."""
    cfg = snap_advance_db.get_config_internal()
    partner_service_id = virtual_account_no[:8]
    customer_no = virtual_account_no[8:]
    body = {
        "partnerServiceId": partner_service_id,
        "customerNo": customer_no,
        "virtualAccountNo": virtual_account_no,
        "additionalInfo": {"channelCode": channel_code, "trxId": payment_reference[:32]},
    }
    raw_body = _minify(body)
    headers = _headers_service("POST", PATH_VA_INQUIRY_STATUS, raw_body, cfg)
    url = _base_url(is_production()) + PATH_VA_INQUIRY_STATUS
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2002600":
        raise core.GatewayRequestError(f"Inquiry Status VA SNAP Advance ditolak Faspay: {resp}")
    return resp["virtualAccountData"]


def buat_transaksi_qris(payment_reference: str, amount: int, customer_details: dict = None) -> dict:
    """Generate QRIS -- POST {base}/v1.0/qr/qr-mpm-generate (servis 47,
    dokumen resmi Faspay). `phoneNo` WAJIB per dokumen (beda dari VA yang
    opsional) -- melempar ValueError jelas kalau `customer_details` tidak
    berisi nomor WhatsApp, BUKAN mengirim field kosong ke Faspay.
    `channelCode` (715=LinkAja QRIS/711=ShopeePay QRIS/842=CIMB QRIS) diambil
    dari config `snap_qris_channel_code` -- MASIH satu default tunggal (beda
    dari buat_transaksi_va() yang sekarang multi-bank, channel_code dikirim
    pemanggil, bukan dibaca dari config)."""
    cfg = snap_advance_db.get_config_internal()
    _cfg_wajib(cfg, "snap_qris_channel_code", "snap_merchant_id")
    if cfg["snap_qris_channel_code"] not in snap_advance_db.QRIS_CHANNEL_CODE_VALID:
        raise core.GatewayNotConfiguredError(
            f"channelCode QRIS default belum/tidak valid: {cfg['snap_qris_channel_code']!r}."
        )
    customer_details = customer_details or {}
    if not customer_details.get("whatsapp"):
        raise ValueError(
            "Generate QRIS SNAP Advance wajib menyertakan nomor WhatsApp customer "
            "(field phoneNo, Mandatory per dokumen resmi Faspay)."
        )
    ts_now = core.snap_timestamp_wib()
    valid_until = core.now_wib().replace(hour=23, minute=59, second=59)
    body = {
        "partnerReferenceNo": payment_reference[:32],
        "amount": {"value": f"{amount:.2f}", "currency": "IDR"},
        "merchantId": cfg["snap_merchant_id"][:5],
        "validityPeriod": valid_until.strftime("%Y-%m-%dT%H:%M:%S") + ts_now[-6:],
        "additionalInfo": {
            "billDate": ts_now,
            "billDescription": "Pembayaran"[:128],
            "channelCode": cfg["snap_qris_channel_code"],
            "phoneNo": _format_msisdn_62(customer_details["whatsapp"])[:30],
        },
    }
    raw_body = _minify(body)
    headers = _headers_service("POST", PATH_QRIS_GENERATE, raw_body, cfg)
    url = _base_url(is_production()) + PATH_QRIS_GENERATE
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2004700":
        raise core.GatewayRequestError(f"Generate QRIS SNAP Advance ditolak Faspay: {resp}")
    info = resp.get("additionalInfo", {})
    return {
        "provider_transaction_id": resp.get("referenceNo"),
        # `qr_url` = qrUrl (URL gambar QR langsung, conditional -- "hanya
        # untuk direct merchant" per dokumen). `qr_content` dipakai untuk
        # qrImageUrl (redirect ke halaman Faspay yang menampilkan QR) --
        # keduanya kolom yang SUDAH ADA di snap_payment_transactions
        # (snap_payment_migrasi.py), TIDAK perlu migrasi tambahan.
        "qr_url": resp.get("qrUrl"),
        "qr_content": info.get("qrImageUrl"),
        "provider_response": json.dumps(resp),
    }


def query_payment_qris(payment_reference: str, provider_reference_no: str, channel_code: str) -> dict:
    """Query Payment QRIS -- POST {base}/v1.0/qr/qr-mpm-query (servis 51,
    dokumen resmi Faspay). `provider_reference_no` = referenceNo hasil
    buat_transaksi_qris() (snap_payment_transactions.provider_transaction_id)."""
    cfg = snap_advance_db.get_config_internal()
    _cfg_wajib(cfg, "snap_merchant_id")
    body = {
        "originalReferenceNo": provider_reference_no[:16],
        "originalPartnerReferenceNo": payment_reference[:32],
        "serviceCode": "47",
        "merchantId": cfg["snap_merchant_id"][:5],
        "additionalInfo": {"channelCode": channel_code},
    }
    raw_body = _minify(body)
    headers = _headers_service("POST", PATH_QRIS_QUERY, raw_body, cfg)
    url = _base_url(is_production()) + PATH_QRIS_QUERY
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2005100":
        raise core.GatewayRequestError(f"Query Payment QRIS SNAP Advance ditolak Faspay: {resp}")
    return resp


def daftarkan_binding_akun(transaction_type: str, customer_details: dict = None) -> dict:
    """Registrasi/Account Binding Direct Debit -- TETAP PENDING FASPAY
    TOTAL. Dokumen Direct Debit resmi yang diberikan Owner TIDAK menyertakan
    bagian Registrasi/Binding sama sekali (hanya Payment/Status/Cancel/
    Notification) -- dan dokumen tsb JUSTRU menunjukkan `bankCardToken`
    HANYA "Mandatory for payment channel BRI Direct Debit", channel lain
    (OVO/DANA/LinkAja/dst) tidak menyebutkan kebutuhan token/binding sama
    sekali di request Payment. SENGAJA TIDAK diasumsikan "semua channel
    Direct Debit butuh binding" (per instruksi eksplisit Owner) -- gap ini
    WAJIB dikonfirmasi ke Faspay: channel mana saja yang benar-benar butuh
    Registrasi/Account Binding lebih dulu, dan bagaimana alurnya (OTP/OAuth2)."""
    raise pending_faspay(
        "Direct Debit -- Registrasi/Account Binding (daftarkan_binding_akun())",
        "Dokumen resmi yang diberikan tidak menyertakan bagian Registrasi/Binding sama sekali -- "
        "channel mana yang benar-benar butuh binding (kemungkinan HANYA BRI Direct Debit berdasarkan "
        "field bankCardToken di dokumen Payment) belum dikonfirmasi Faspay, TIDAK diasumsikan di sini.",
    )


def buat_transaksi_direct_debit(payment_reference: str, amount: int, channel_code: str, *,
                                 bank_card_token: str = None, customer_details: dict = None,
                                 valid_menit: int = 60) -> dict:
    """Direct Debit Payment (host-to-host) -- POST {base}/v1.0/debit/
    payment-host-to-host (dokumen resmi Faspay). `channel_code` = salah
    satu dari 14 channelCode resmi di snap_advance_db.DIRECT_DEBIT_CHANNEL_CODE_LABEL
    (kategori Bank & E-Wallet, lihat catatan modul soal E-Wallet BUKAN
    produk terpisah -- audit lanjutan #4). `bank_card_token` HANYA
    diperlukan untuk channel BRI Direct Debit (714) per dokumen resmi --
    TIDAK divalidasi wajib di sini untuk channel lain (lihat catatan
    daftarkan_binding_akun() soal kenapa asumsi "semua channel butuh
    binding" TIDAK dibuat)."""
    if channel_code not in snap_advance_db.DIRECT_DEBIT_CHANNEL_CODE_VALID:
        raise ValueError(
            f"channelCode Direct Debit tidak dikenal: {channel_code!r}. Lihat "
            f"snap_advance_db.DIRECT_DEBIT_CHANNEL_CODE_LABEL untuk daftar 14 channel resmi Faspay."
        )
    cfg = snap_advance_db.get_config_internal()
    _cfg_wajib(cfg, "snap_merchant_id")
    customer_details = customer_details or {}
    now = core.now_wib()
    ts_now = core.snap_timestamp_wib()
    valid_up_to = now.replace(second=0, microsecond=0)
    from datetime import timedelta
    valid_up_to = valid_up_to + timedelta(minutes=valid_menit)
    body = {
        "partnerReferenceNo": payment_reference[:32],
        "merchantId": cfg["snap_merchant_id"][:5],
        "amount": {"value": f"{amount:.2f}", "currency": "IDR"},
        "validUpTo": valid_up_to.strftime("%Y-%m-%dT%H:%M:%S") + ts_now[-6:],
        "additionalInfo": {
            "channelCode": channel_code,
            "billDate": ts_now,
            "billDescription": "Pembayaran"[:128],
        },
    }
    if bank_card_token:
        body["bankCardToken"] = bank_card_token
    if customer_details.get("nama"):
        body["additionalInfo"]["customerName"] = customer_details["nama"][:128]
    if customer_details.get("whatsapp"):
        body["additionalInfo"]["phoneNo"] = _format_msisdn_62(customer_details["whatsapp"])[:30]
    if customer_details.get("email"):
        body["additionalInfo"]["email"] = customer_details["email"][:128]
    raw_body = _minify(body)
    headers = _headers_service("POST", PATH_DD_PAYMENT, raw_body, cfg)
    url = _base_url(is_production()) + PATH_DD_PAYMENT
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2005400":
        raise core.GatewayRequestError(f"Direct Debit Payment SNAP Advance ditolak Faspay: {resp}")
    return {
        "provider_transaction_id": resp.get("referenceNo"),
        # BUGFIX (audit lanjutan #4): dokumen resmi Direct Debit menyebutkan
        # TIGA field redirect (appRedirectUrl/webRedirectUrl/webUrl) di
        # response Payment -- sebelumnya HANYA 2 dari 3 dibaca (webUrl diam-
        # diam hilang). Ketiganya sekarang ditangkap TERPISAH & apa adanya
        # (TIDAK menebak mana yang "benar" dipakai -- perbedaan semantik
        # PERSIS kapan tiap field muncul/dipakai BELUM dikonfirmasi dari teks
        # dokumen). CATATAN: ini BEDA dari Return/Landing Page URL (audit
        # lanjutan #5) yang SUDAH selesai & diimplementasikan (Faspay
        # mengonfirmasi bebas ditentukan merchant, lihat frontend/app/js/
        # pages/book_public.js::renderPembayaranKembali()) -- yang belum
        # jelas HANYA cara tiga field response DI SINI dipakai/dipilih.
        # `ewallet_deeplink_url` dipertahankan sebagai field kompatibilitas
        # (dipakai kode lama) -- prioritas fallback MURNI supaya field lawas
        # ini tidak pernah kosong kalau salah satu dari ketiganya terisi,
        # BUKAN klaim urutan mana yang paling "benar" dipakai.
        "app_redirect_url": resp.get("appRedirectUrl"),
        "web_redirect_url": resp.get("webRedirectUrl"),
        "web_url": resp.get("webUrl"),
        "ewallet_deeplink_url": resp.get("webRedirectUrl") or resp.get("webUrl") or resp.get("appRedirectUrl"),
        "provider_response": json.dumps(resp),
    }


def status_direct_debit(original_partner_reference_no: str, original_reference_no: str,
                         channel_code: str, merchant_id: str = None) -> dict:
    """Direct Debit Payment Status -- POST {base}/v1.0/debit/status (servis
    55, dokumen resmi Faspay)."""
    cfg = snap_advance_db.get_config_internal()
    merchant_id = merchant_id or cfg["snap_merchant_id"]
    _cfg_wajib({"merchant_id": merchant_id}, "merchant_id")
    body = {
        "originalPartnerReferenceNo": original_partner_reference_no[:32],
        "originalReferenceNo": original_reference_no[:16],
        "serviceCode": "55",
        "merchantId": merchant_id[:5],
        "additionalInfo": {"channelCode": channel_code},
    }
    raw_body = _minify(body)
    headers = _headers_service("POST", PATH_DD_STATUS, raw_body, cfg)
    url = _base_url(is_production()) + PATH_DD_STATUS
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2005500":
        raise core.GatewayRequestError(f"Direct Debit Status SNAP Advance ditolak Faspay: {resp}")
    return resp


def cek_status_transaksi(payment_reference: str, channel: str = None, **kwargs) -> dict:
    """Inquiry/Cek Status manual -- dispatcher tipis ke inquiry_status_va()/
    status_direct_debit()/query_payment_qris() (fitur "Cek Ulang ke
    Provider", rekonsiliasi transaksi yang macet karena webhook tidak
    pernah sampai). `channel` WAJIB diisi pemanggil (va/direct_debit/qris)
    beserta kwargs yang relevan (virtual_account_no + channel_code untuk VA;
    original_reference_no/channel_code untuk Direct Debit & QRIS) -- lihat
    fungsi masing-masing untuk parameter lengkapnya. E-Wallet (kategori
    channel di dalam Direct Debit, lihat catatan modul) TERCAKUP lewat
    `channel="direct_debit"` -- TIDAK ada channel dispatch "ewallet"
    terpisah."""
    if channel == "va":
        return inquiry_status_va(payment_reference, kwargs["virtual_account_no"], kwargs["channel_code"])
    if channel == "direct_debit":
        return status_direct_debit(payment_reference, kwargs["original_reference_no"],
                                    kwargs["channel_code"], kwargs.get("merchant_id"))
    if channel == "qris":
        return query_payment_qris(payment_reference, kwargs["original_reference_no"], kwargs["channel_code"])
    raise pending_faspay(
        "Inquiry/Cek Status -- cek_status_transaksi()",
        f"Channel {channel!r} belum diimplementasikan (hanya va/direct_debit/qris yang sudah didokumentasikan resmi).",
    )


def verifikasi_signature_webhook(raw_body: str, signature_header: str, timestamp_header: str = None,
                                  method: str = "POST", *, path: str) -> bool:
    """Verifikasi X-SIGNATURE Payment Notification -- ASYMMETRIC (RSA-SHA256),
    diverifikasi pakai public key Faspay (snap_faspay_public_key). String-
    to-sign standar SNAP notifikasi: `{method}:{path}:{sha256_lowercase_hex(raw_body)}:{X-TIMESTAMP}`.

    `path` WAJIB diisi eksplisit oleh pemanggil (routers/snap_advance.py lewat
    snap_webhook.py::proses_notifikasi()) -- salah satu dari tiga path resmi
    Faspay (/v1.0/transfer-va/payment, /v1.0/qr/qr-mpm-notify,
    /v1.0/debit/notify). TIDAK ADA default lagi (dulu default-nya endpoint
    gabungan lama yang sudah dihapus, lihat catatan modul routers/snap_advance.py)
    -- kalau sampai lupa dioper, ini SENGAJA meledak (TypeError) daripada
    diam-diam salah verifikasi pakai path basi.

    CATATAN: formula ini BELUM dicocokkan 1:1 ke halaman resmi Faspay (lihat
    catatan modul) -- kalau uji Simulator menunjukkan formula ini SALAH,
    HANYA fungsi ini yang perlu diubah, pemanggil (snap_webhook.py) tidak
    perlu disentuh."""
    cfg = snap_advance_db.get_config_internal()
    if not (cfg.get("snap_faspay_public_key") and signature_header and timestamp_header):
        return False
    body_hash = core.sha256_lowercase_hex(raw_body)
    string_to_sign = f"{method}:{path}:{body_hash}:{timestamp_header}"
    return core.verify_sha256_rsa(string_to_sign, signature_header, cfg["snap_faspay_public_key"])
