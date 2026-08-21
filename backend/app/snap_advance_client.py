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
dokumen resmi SNAP VA & SNAP Direct Debit)
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
- **QRIS**: TETAP PENDING FASPAY TOTAL -- dokumen resmi SNAP QRIS belum
  diberikan Owner (per instruksi eksplisit "jangan menebak endpoint/payload,
  kalau dokumentasi belum cukup jangan implementasikan").
- **E-Wallet**: TETAP PENDING FASPAY TOTAL -- di luar cakupan yang diminta.

=============================================================================
CATATAN SIGNATURE -- BELUM 100% terverifikasi ke halaman resmi Faspay
=============================================================================
Fungsi di bawah memakai primitif signature SNAP standar BI/ASPI
(gateway_client_base.py::sign_sha256_rsa() untuk B2B token, sign_hmac_sha512()
untuk service call) -- formula INI SENDIRI adalah spesifikasi SNAP yang
DIWAJIBKAN lintas seluruh PJP berlisensi, bukan tebakan bebas. TAPI halaman
"Signature details" resmi Faspay (dirujuk dari dokumen VA/DD yang diberikan
Owner: docs.faspay.co.id/merchant-integration/api-reference-1/snap/
signature-snap) TIDAK BISA diakses dari lingkungan kerja ini (domain
diblokir proxy jaringan) -- BELUM dicocokkan 1:1 ke halaman itu. **WAJIB**
diverifikasi ulang (baca halaman resmi tsb, atau uji langsung lewat Faspay
Simulator) SEBELUM dipakai terhadap sandbox/production sungguhan.

Path endpoint get-token B2B (`PATH_ACCESS_TOKEN_B2B` di bawah) JUGA belum
ada di dokumen yang diberikan Owner (hanya VA & Direct Debit yang diberikan)
-- dipakai konvensi path SNAP standar (`/v1.0/access-token/b2b`), SAMA gaya
penulisan path dengan endpoint VA/DD yang SUDAH terkonfirmasi di base domain
yang sama, TAPI belum dikonfirmasi tertulis oleh Faspay. Tandai sebagai gap
untuk dikonfirmasi sebelum uji sandbox sungguhan."""

import json
import re

import gateway_client_base as core
import snap_advance_db

_TIMEOUT_DEFAULT = 30

# ---------------------------------------------------------------------------
# Path endpoint -- lihat catatan modul soal mana yang terkonfirmasi dokumen
# resmi Faspay (VA & Direct Debit) vs mana yang masih konvensi SNAP standar.
# ---------------------------------------------------------------------------
PATH_ACCESS_TOKEN_B2B = "/v1.0/access-token/b2b"  # BELUM ada di dokumen resmi yang diberikan -- konvensi SNAP standar, WAJIB dicek ulang
PATH_VA_CREATE = "/v1.0/transfer-va/create-va"  # terkonfirmasi dokumen resmi Faspay
PATH_VA_INQUIRY_STATUS = "/v1.0/transfer-va/status"  # terkonfirmasi dokumen resmi Faspay ("Inquiry Status", servis 26)
PATH_DD_PAYMENT = "/v1.0/debit/payment-host-to-host"  # terkonfirmasi dokumen resmi Faspay
PATH_DD_STATUS = "/v1.0/debit/status"  # terkonfirmasi dokumen resmi Faspay


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
    """Token akses B2B SNAP -- signature ASYMMETRIC (RSA-SHA256) atas
    `client_id + "|" + X-TIMESTAMP`, ditandatangani private key merchant.
    Lihat catatan modul soal path endpoint yang belum terkonfirmasi
    dokumen resmi Faspay."""
    cfg = snap_advance_db.get_config_internal()
    _cfg_wajib(cfg, "snap_client_id", "snap_private_key")
    ts = core.snap_timestamp_wib()
    string_to_sign = f"{cfg['snap_client_id']}|{ts}"
    signature = core.sign_sha256_rsa(string_to_sign, cfg["snap_private_key"])
    headers = {
        "Content-Type": "application/json",
        "X-TIMESTAMP": ts,
        "X-SIGNATURE": signature,
        "X-CLIENT-KEY": cfg["snap_client_id"],
    }
    url = _base_url(is_production()) + PATH_ACCESS_TOKEN_B2B
    resp = core.post_json_raw(url, _minify({"grantType": "client_credentials"}), headers, timeout=cfg["snap_timeout_detik"])
    token = resp.get("accessToken") or resp.get("access_token")
    if not token:
        raise core.GatewayRequestError(f"Respons token B2B SNAP Advance tidak berisi accessToken: {resp}")
    return token


def _headers_service(access_token: str, method: str, path: str, raw_body: str, cfg: dict) -> dict:
    """Header lengkap untuk service call SETELAH token B2B didapat --
    signature SYMMETRIC (HMAC-SHA512), lihat gateway_client_base.py::
    sign_hmac_sha512() untuk formula string-to-sign persisnya. `raw_body`
    HARUS string PERSIS yang nanti dikirim lewat core.post_json_raw() --
    lihat catatan post_json_raw() soal kenapa hash body harus dihitung dari
    bytes yang SAMA PERSIS dengan yang benar-benar terkirim."""
    _cfg_wajib(cfg, "snap_partner_id", "snap_channel_id", "snap_client_secret")
    ts = core.snap_timestamp_wib()
    body_hash = core.sha256_lowercase_hex(raw_body)
    string_to_sign = f"{method}:{path}:{access_token}:{body_hash}:{ts}"
    signature = core.sign_hmac_sha512(string_to_sign, cfg["snap_client_secret"])
    return {
        "Content-Type": "application/json",
        "X-TIMESTAMP": ts,
        "X-SIGNATURE": signature,
        "X-PARTNER-ID": cfg["snap_partner_id"],
        "X-EXTERNAL-ID": core.buat_external_id(),
        "CHANNEL-ID": cfg["snap_channel_id"],
        "Authorization": f"Bearer {access_token}",
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


def buat_transaksi_va(payment_reference: str, amount: int, customer_details: dict = None) -> dict:
    """Create Dynamic VA -- POST {base}/v1.0/transfer-va/create-va (dokumen
    resmi Faspay). `customer_details` opsional: {"nama", "email", "whatsapp"}.
    `payment_reference` dipakai sebagai `trxId` (WAJIB, maks 32 karakter per
    dokumen -- format payment_reference proyek ini, mis.
    "BOOKING-1-42-abcdef123456", secara wajar tetap di bawah batas itu untuk
    id tenant/entity yang tidak terlalu besar; DIPOTONG kalau kebetulan
    melebihi, TIDAK melempar error, supaya create VA tidak gagal hanya
    karena panjang string -- risiko tabrakan trxId dianggap dapat diterima
    mengingat sufiks UUID 12-hex di akhir referensi)."""
    cfg = snap_advance_db.get_config_internal()
    _cfg_wajib(cfg, "snap_va_channel_code")
    if cfg["snap_va_channel_code"] not in snap_advance_db.VA_CHANNEL_CODE_VALID:
        raise core.GatewayNotConfiguredError(
            f"channelCode VA default belum/tidak valid: {cfg['snap_va_channel_code']!r}."
        )
    customer_details = customer_details or {}
    token = ambil_token_b2b()
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
            "channelCode": cfg["snap_va_channel_code"],
            "billDescription": "Pembayaran"[:18],
        },
    }
    if customer_details.get("email"):
        body["virtualAccountEmail"] = customer_details["email"][:128]
    if customer_details.get("whatsapp"):
        body["virtualAccountPhone"] = _format_msisdn_62(customer_details["whatsapp"])[:30]
    raw_body = _minify(body)
    headers = _headers_service(token, "POST", PATH_VA_CREATE, raw_body, cfg)
    url = _base_url(is_production()) + PATH_VA_CREATE
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2002500":
        raise core.GatewayRequestError(f"Create VA SNAP Advance ditolak Faspay: {resp}")
    va = resp["virtualAccountData"]
    return {
        "va_number": va["virtualAccountNo"],
        "provider_transaction_id": va.get("trxId"),
        "expired_at": va.get("expiredDate"),
        "provider_response": json.dumps(resp),
    }


def inquiry_status_va(payment_reference: str, virtual_account_no: str) -> dict:
    """Inquiry Status VA -- POST {base}/v1.0/transfer-va/status (servis 26,
    dokumen resmi Faspay). `virtual_account_no` = va_number hasil
    buat_transaksi_va() (snap_payment_transactions.va_number)."""
    cfg = snap_advance_db.get_config_internal()
    _cfg_wajib(cfg, "snap_va_channel_code")
    token = ambil_token_b2b()
    partner_service_id = virtual_account_no[:8]
    customer_no = virtual_account_no[8:]
    body = {
        "partnerServiceId": partner_service_id,
        "customerNo": customer_no,
        "virtualAccountNo": virtual_account_no,
        "additionalInfo": {"channelCode": cfg["snap_va_channel_code"], "trxId": payment_reference[:32]},
    }
    raw_body = _minify(body)
    headers = _headers_service(token, "POST", PATH_VA_INQUIRY_STATUS, raw_body, cfg)
    url = _base_url(is_production()) + PATH_VA_INQUIRY_STATUS
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2002600":
        raise core.GatewayRequestError(f"Inquiry Status VA SNAP Advance ditolak Faspay: {resp}")
    return resp["virtualAccountData"]


def buat_transaksi_qris(payment_reference: str, amount: int, customer_details: dict = None) -> dict:
    """Create Dynamic QRIS -- TETAP PENDING FASPAY TOTAL. Dokumen resmi SNAP
    QRIS BELUM diberikan Owner (per instruksi eksplisit: jangan menebak
    endpoint/payload kalau dokumentasi belum cukup)."""
    raise pending_faspay(
        "Dynamic QRIS -- buat_transaksi_qris()",
        "Dokumen resmi SNAP QRIS Faspay belum diberikan -- endpoint/payload TIDAK ditebak, menunggu dokumen resmi.",
    )


def buat_transaksi_ewallet(payment_reference: str, amount: int, ewallet_provider: str,
                            customer_details: dict = None) -> dict:
    """Create Dynamic E-Wallet -- PENDING FASPAY TOTAL, di luar cakupan
    dokumen yang diberikan sejauh ini."""
    raise pending_faspay(
        "Dynamic E-Wallet -- buat_transaksi_ewallet()",
        "Jalur teknis E-Wallet belum terkonfirmasi Faspay -- di luar cakupan dokumen VA/Direct Debit yang diberikan.",
    )


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
    payment-host-to-host (dokumen resmi Faspay). `channel_code` = kode
    channel Direct Debit (mis. "812"=OVO, "819"=DANA, "714"=BRI Direct
    Debit -- lihat tabel lengkap di dokumen resmi). `bank_card_token` HANYA
    diperlukan untuk channel BRI Direct Debit (714) per dokumen resmi --
    TIDAK divalidasi wajib di sini untuk channel lain (lihat catatan
    daftarkan_binding_akun() soal kenapa asumsi "semua channel butuh
    binding" TIDAK dibuat)."""
    cfg = snap_advance_db.get_config_internal()
    _cfg_wajib(cfg, "snap_merchant_id")
    customer_details = customer_details or {}
    token = ambil_token_b2b()
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
    headers = _headers_service(token, "POST", PATH_DD_PAYMENT, raw_body, cfg)
    url = _base_url(is_production()) + PATH_DD_PAYMENT
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2005400":
        raise core.GatewayRequestError(f"Direct Debit Payment SNAP Advance ditolak Faspay: {resp}")
    return {
        "provider_transaction_id": resp.get("referenceNo"),
        "ewallet_deeplink_url": resp.get("webRedirectUrl") or resp.get("appRedirectUrl"),
        "provider_response": json.dumps(resp),
    }


def status_direct_debit(original_partner_reference_no: str, original_reference_no: str,
                         channel_code: str, merchant_id: str = None) -> dict:
    """Direct Debit Payment Status -- POST {base}/v1.0/debit/status (servis
    55, dokumen resmi Faspay)."""
    cfg = snap_advance_db.get_config_internal()
    merchant_id = merchant_id or cfg["snap_merchant_id"]
    _cfg_wajib({"merchant_id": merchant_id}, "merchant_id")
    token = ambil_token_b2b()
    body = {
        "originalPartnerReferenceNo": original_partner_reference_no[:32],
        "originalReferenceNo": original_reference_no[:16],
        "serviceCode": "55",
        "merchantId": merchant_id[:5],
        "additionalInfo": {"channelCode": channel_code},
    }
    raw_body = _minify(body)
    headers = _headers_service(token, "POST", PATH_DD_STATUS, raw_body, cfg)
    url = _base_url(is_production()) + PATH_DD_STATUS
    resp = core.post_json_raw(url, raw_body, headers, timeout=cfg["snap_timeout_detik"])
    if resp.get("responseCode") != "2005500":
        raise core.GatewayRequestError(f"Direct Debit Status SNAP Advance ditolak Faspay: {resp}")
    return resp


def cek_status_transaksi(payment_reference: str, channel: str = None, **kwargs) -> dict:
    """Inquiry/Cek Status manual -- dispatcher tipis ke inquiry_status_va()/
    status_direct_debit() (fitur "Cek Ulang ke Provider", rekonsiliasi
    transaksi yang macet karena webhook tidak pernah sampai). `channel`
    WAJIB diisi pemanggil (va/direct_debit) beserta kwargs yang relevan
    (virtual_account_no untuk VA; original_reference_no/channel_code untuk
    Direct Debit) -- lihat inquiry_status_va()/status_direct_debit() untuk
    parameter lengkapnya. QRIS/E-Wallet TETAP PENDING FASPAY."""
    if channel == "va":
        return inquiry_status_va(payment_reference, kwargs["virtual_account_no"])
    if channel == "direct_debit":
        return status_direct_debit(payment_reference, kwargs["original_reference_no"],
                                    kwargs["channel_code"], kwargs.get("merchant_id"))
    raise pending_faspay(
        "Inquiry/Cek Status -- cek_status_transaksi()",
        f"Channel {channel!r} belum diimplementasikan (hanya va/direct_debit yang sudah didokumentasikan resmi).",
    )


def verifikasi_signature_webhook(raw_body: str, signature_header: str, timestamp_header: str = None,
                                  method: str = "POST", path: str = "/api/public/gateway/snap-notification") -> bool:
    """Verifikasi X-SIGNATURE Payment Notification -- ASYMMETRIC (RSA-SHA256),
    diverifikasi pakai public key Faspay (snap_faspay_public_key). String-
    to-sign standar SNAP notifikasi: `{method}:{path}:{sha256_lowercase_hex(raw_body)}:{X-TIMESTAMP}`.

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
