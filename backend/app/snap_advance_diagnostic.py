"""snap_advance_diagnostic.py — Alat uji SEMENTARA khusus sertifikasi SNAP
Advance Faspay
=============================================================================
Permintaan tim Faspay (feedback dokumen UAT): kolom Request/Response WAJIB
berisi nilai SUNGGUHAN untuk SETIAP skenario -- termasuk empat skenario
error generik "Any Service" (Unauthorized Signature/Missing Mandatory
Field/Invalid Field Format/Duplicate X-EXTERNAL-ID). Skenario-skenario itu
TIDAK PERNAH terjadi wajar dari pemakaian normal, karena kode checkout
produksi (snap_advance_client.py) SELALU mengirim request yang benar --
tidak ada jalur bisnis apa pun yang sengaja mengirim signature/field salah.

Modul INI (SENGAJA terpisah total dari snap_advance_client.py, TIDAK
dipanggil dari checkout/webhook/rekonsiliasi manapun) mengirim request yang
SENGAJA DIRUSAK ke sandbox Faspay memakai kredensial sungguhan (merchant/
partner/channel ID) supaya Faspay membalas error KODE ASLI mereka --
otomatis tercatat ke log server lewat gateway_client_base.post_json_raw()
(SNAP REQUEST/SNAP RESPONSE, lihat modul itu), yang lalu disalin manual ke
dokumen sertifikasi. HANYA dipicu manual oleh Super Admin lewat tombol
khusus (routers/snap_advance.py), TIDAK PERNAH otomatis/terjadwal.

PENGAMAN KERAS: _pastikan_sandbox() menolak dijalankan sama sekali kalau
environment saat ini "production" -- modul ini TIDAK BOLEH PERNAH menyentuh
Faspay produksi sungguhan. Signature untuk skenario "Unauthorized" dihitung
dari keypair RSA BARU/SEKALI PAKAI yang dibuat di tempat (BUKAN private key
konfigurasi asli yang sengaja dirusak) -- private key konfigurasi TIDAK
PERNAH dibaca/disentuh selain untuk skenario yang MEMANG harus lolos
signature (Missing Field/Invalid Format/Duplicate ID).

BOLEH DIHAPUS TOTAL (modul ini + endpoint + tombol Super Admin terkait)
begitu sertifikasi Faspay selesai -- tidak ada kode lain yang bergantung
padanya."""

import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import gateway_client_base as core
import snap_advance_client as _snap
import snap_advance_db


def _pastikan_sandbox():
    if _snap.is_production():
        raise ValueError(
            "Alat uji sertifikasi HANYA boleh dijalankan saat environment SNAP Advance = sandbox. "
            "Ubah dulu di Super Admin > SNAP Advance kalau memang sedang production."
        )


def _keypair_palsu_sekali_pakai() -> str:
    """Private key RSA baru, hanya dipakai SEKALI untuk menandatangani
    request "Unauthorized Signature" -- PASTI tidak cocok dengan public key
    yang di-whitelist Faspay untuk merchant ini, TANPA pernah menyentuh
    private key konfigurasi asli."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _headers(method: str, path: str, raw_body: str, cfg: dict, *,
             private_key_override: str = None, external_id_override: str = None) -> dict:
    ts = core.snap_timestamp_wib()
    body_hash = core.sha256_lowercase_hex(raw_body)
    string_to_sign = f"{method}:{path}:{body_hash}:{ts}"
    signature = core.sign_sha256_rsa(string_to_sign, private_key_override or cfg["snap_private_key"])
    return {
        "Content-Type": "application/json",
        "X-TIMESTAMP": ts,
        "X-SIGNATURE": signature,
        "X-PARTNER-ID": cfg["snap_partner_id"],
        "X-EXTERNAL-ID": external_id_override or core.buat_external_id(),
        "CHANNEL-ID": cfg["snap_channel_id"],
    }


def _kirim(path: str, body: dict, cfg: dict, *, private_key_override: str = None,
           external_id_override: str = None) -> dict:
    raw_body = _snap._minify(body)
    headers = _headers("POST", path, raw_body, cfg, private_key_override=private_key_override,
                        external_id_override=external_id_override)
    url = _snap._base_url(False) + path
    try:
        resp = core.post_json_raw(url, raw_body, headers)
        return {"status": "TIDAK ditolak provider -- cek log, mungkin perlu skenario lain", "response": resp}
    except core.GatewayRequestError as e:
        return {"status": "Ditolak provider (sesuai harapan) -- lihat SNAP RESPONSE di log untuk kode aslinya", "response": str(e)}


def uji_skenario_va() -> list:
    """Empat skenario "Any Service" (11.2-11.5) memakai endpoint Create VA
    sebagai representasi -- lihat catatan modul soal kenapa error generik
    ini butuh request yang SENGAJA dirusak."""
    _pastikan_sandbox()
    cfg = snap_advance_db.get_config_internal()
    _snap._cfg_wajib(cfg, "snap_partner_id", "snap_channel_id", "snap_private_key")
    ts_now = core.snap_timestamp_wib()
    expired = core.now_wib().replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%S") + ts_now[-6:]
    trx_dasar = f"UJISERTIFIKASI{uuid.uuid4().hex[:10]}"
    body_valid = {
        "virtualAccountName": "Uji Sertifikasi",
        "trxId": trx_dasar + "A",
        "totalAmount": {"value": "10000.00", "currency": "IDR"},
        "expiredDate": expired,
        "additionalInfo": {"billDate": ts_now, "channelCode": "702", "billDescription": "Uji Sertifikasi"},
    }
    hasil = []

    hasil.append({"skenario": "11.2 Unauthorized Signature",
                  **_kirim(_snap.PATH_VA_CREATE, body_valid, cfg, private_key_override=_keypair_palsu_sekali_pakai())})

    body_kurang = {k: v for k, v in body_valid.items() if k != "totalAmount"}
    body_kurang["trxId"] = trx_dasar + "B"
    hasil.append({"skenario": "11.3 Missing Mandatory Field (totalAmount dihilangkan)",
                  **_kirim(_snap.PATH_VA_CREATE, body_kurang, cfg)})

    body_salah_format = {**body_valid, "trxId": trx_dasar + "C", "totalAmount": {"value": "10000", "currency": "IDR"}}
    hasil.append({"skenario": "11.4 Invalid Field Format (totalAmount.value tanpa 2 desimal)",
                  **_kirim(_snap.PATH_VA_CREATE, body_salah_format, cfg)})

    body_dup = {**body_valid, "trxId": trx_dasar + "D"}
    external_id_sama = core.buat_external_id()
    hasil.append({"skenario": "11.5 Duplicate X-EXTERNAL-ID (percobaan ke-1, HARUS berhasil)",
                  **_kirim(_snap.PATH_VA_CREATE, body_dup, cfg, external_id_override=external_id_sama)})
    hasil.append({"skenario": "11.5 Duplicate X-EXTERNAL-ID (percobaan ke-2, HARUS ditolak Conflict)",
                  **_kirim(_snap.PATH_VA_CREATE, body_dup, cfg, external_id_override=external_id_sama)})
    return hasil


def uji_skenario_qris() -> list:
    """Empat skenario "Any Service" (18.2-18.5) memakai endpoint Generate
    QRIS sebagai representasi."""
    _pastikan_sandbox()
    cfg = snap_advance_db.get_config_internal()
    _snap._cfg_wajib(cfg, "snap_qris_channel_code", "snap_merchant_id", "snap_partner_id",
                      "snap_channel_id", "snap_private_key")
    ts_now = core.snap_timestamp_wib()
    valid_until = core.now_wib().replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%S") + ts_now[-6:]
    ref_dasar = f"UJISERTIFIKASI{uuid.uuid4().hex[:10]}"
    body_valid = {
        "partnerReferenceNo": ref_dasar + "A",
        "amount": {"value": "10000.00", "currency": "IDR"},
        "merchantId": cfg["snap_merchant_id"][:5],
        "validityPeriod": valid_until,
        "additionalInfo": {"billDate": ts_now, "billDescription": "Uji Sertifikasi",
                            "channelCode": cfg["snap_qris_channel_code"], "phoneNo": "6281234567890"},
    }
    hasil = []

    hasil.append({"skenario": "18.2 Unauthorized Signature",
                  **_kirim(_snap.PATH_QRIS_GENERATE, body_valid, cfg, private_key_override=_keypair_palsu_sekali_pakai())})

    body_kurang = {k: v for k, v in body_valid.items() if k != "amount"}
    body_kurang["partnerReferenceNo"] = ref_dasar + "B"
    hasil.append({"skenario": "18.3 Missing Mandatory Field (amount dihilangkan)",
                  **_kirim(_snap.PATH_QRIS_GENERATE, body_kurang, cfg)})

    body_salah_format = {**body_valid, "partnerReferenceNo": ref_dasar + "C", "amount": {"value": "10000", "currency": "IDR"}}
    hasil.append({"skenario": "18.4 Invalid Field Format (amount.value tanpa 2 desimal)",
                  **_kirim(_snap.PATH_QRIS_GENERATE, body_salah_format, cfg)})

    body_dup = {**body_valid, "partnerReferenceNo": ref_dasar + "D"}
    external_id_sama = core.buat_external_id()
    hasil.append({"skenario": "18.5 Duplicate X-EXTERNAL-ID (percobaan ke-1, HARUS berhasil)",
                  **_kirim(_snap.PATH_QRIS_GENERATE, body_dup, cfg, external_id_override=external_id_sama)})
    hasil.append({"skenario": "18.5 Duplicate X-EXTERNAL-ID (percobaan ke-2, HARUS ditolak Conflict)",
                  **_kirim(_snap.PATH_QRIS_GENERATE, body_dup, cfg, external_id_override=external_id_sama)})

    # 18.7 Invalid Merchant -- merchantId SENGAJA diisi ID yang tidak terdaftar.
    body_merchant_salah = {**body_valid, "partnerReferenceNo": ref_dasar + "E", "merchantId": "99999"}
    hasil.append({"skenario": "18.7 Invalid Merchant (QR MPM Generate QR)",
                  **_kirim(_snap.PATH_QRIS_GENERATE, body_merchant_salah, cfg)})

    # 18.11 Transaction Not Found -- Query Payment atas referenceNo yang TIDAK PERNAH ada.
    body_query_notfound = {
        "originalReferenceNo": "TIDAKADA" + uuid.uuid4().hex[:8],
        "originalPartnerReferenceNo": "TIDAKADA" + uuid.uuid4().hex[:8],
        "serviceCode": "47",
        "merchantId": cfg["snap_merchant_id"][:5],
        "additionalInfo": {"channelCode": cfg["snap_qris_channel_code"]},
    }
    hasil.append({"skenario": "18.11 Transaction Not Found (QR MPM Query Payment)",
                  **_kirim(_snap.PATH_QRIS_QUERY, body_query_notfound, cfg)})
    return hasil
