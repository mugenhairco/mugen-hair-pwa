"""routers/snap_advance.py — Migrasi Faspay SNAP Advance: konfigurasi (Super
Admin) + webhook Payment Notification PER PRODUK
=============================================================================
TIGA router dalam SATU file (pola sama seperti routers/booking.py):
1. `router` (prefix `/api/superadmin/snap-advance`) -- konfigurasi
   kredensial platform-wide, HANYA require_superadmin (pola SAMA PERSIS
   routers/payment_gateway.py), setiap perubahan tercatat superadmin_audit_log.
2. `notification_router` (TANPA prefix -- path resmi Faspay WAJIB persis)
   -- TIGA endpoint Payment Notification TERPISAH, SATU per produk SNAP,
   BUKAN lagi satu URL gabungan (KOREKSI dari asumsi awal, lihat catatan
   di bawah).

KOREKSI PENTING (audit lanjutan #3, klarifikasi resmi Faspay): asumsi
sebelumnya "satu Merchant ID = satu Payment Notification URL gabungan
untuk semua produk SNAP" TERNYATA KELIRU. Faspay mengonfirmasi tertulis:
mereka hanya mengatur SATU domain/url_merchant per Merchant ID
(`https://api.rivoirsett.com`), TAPI tiap PRODUK SNAP (VA/QRIS/Direct
Debit) punya PATH notification-nya SENDIRI di bawah domain itu -- PERSIS
path yang sudah tercantum di masing-masing dokumen resmi produk
("Payment Notification POST url_merchant + /v1.0/...."):
  - VA           -> POST {url_merchant}/v1.0/transfer-va/payment
  - QRIS         -> POST {url_merchant}/v1.0/qr/qr-mpm-notify
  - Direct Debit -> POST {url_merchant}/v1.0/debit/notify
Endpoint gabungan LAMA (`/api/public/gateway/snap-notification`) TIDAK
PERNAH didaftarkan ke Faspay (baru dibangun berdasarkan asumsi, belum
sempat dipakai produksi) -- DIHAPUS SELURUHNYA di sini, BUKAN
dipertahankan sebagai "internal compatibility route", supaya tidak ada
endpoint basi yang bisa membingungkan siapa pun yang mengecek konfigurasi
Faspay di kemudian hari (lihat laporan audit lanjutan #3 untuk detail).

Ketiga path notification_router SENGAJA di ROOT (bukan di bawah `/api/...`
seperti endpoint lain proyek ini) -- WAJIB persis sama dengan yang
didaftarkan ke Faspay, path itu SENDIRI ikut dihitung dalam formula
signature (`EndpointUrl` di stringToSign, lihat gateway_client_base.py::
sign_sha256_rsa()). Aman dari tabrakan dengan frontend -- backend & frontend
proyek ini DUA Render service terpisah (lihat render.yaml), backend tidak
pernah melayani file statis apa pun di root.

Logic INTERNAL (verifikasi signature, parsing payload, state machine,
cascade booking/billing) SAMA SEKALI TIDAK berubah -- lihat snap_webhook.py.
HANYA jenis notifikasi yang tadinya DITEBAK dari channelCode (workaround
untuk satu endpoint gabungan) sekarang EKSPLISIT dari endpoint mana yang
dipukul -- lebih robust, tidak lagi bergantung pada daftar channelCode
QRIS vs Direct Debit tidak pernah bertumpang tindih."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import snap_advance_db
import snap_webhook
import superadmin_audit_db
from auth import require_superadmin
from gateway_client_base import GatewayError

router = APIRouter(prefix="/api/superadmin/snap-advance", tags=["snap-advance-superadmin"])
notification_router = APIRouter(tags=["snap-advance-webhook"])


@router.get("/config")
def ambil_config(user: dict = Depends(require_superadmin)):
    return snap_advance_db.get_config()


class ConfigBody(BaseModel):
    environment: str | None = None
    sandbox_base_url: str | None = None
    production_base_url: str | None = None
    merchant_id: str | None = None
    partner_id: str | None = None
    client_id: str | None = None
    sandbox_client_secret: str | None = None
    production_client_secret: str | None = None
    sandbox_private_key: str | None = None
    production_private_key: str | None = None
    sandbox_faspay_public_key: str | None = None
    production_faspay_public_key: str | None = None
    sandbox_webhook_secret: str | None = None
    production_webhook_secret: str | None = None
    timeout_detik: int | None = None
    retry_max: int | None = None
    channel_aktif: list[str] | None = None
    channel_id: str | None = None
    va_bank_aktif: list[str] | None = None
    qris_channel_code: str | None = None


@router.put("/config")
def ubah_config(body: ConfigBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = snap_advance_db.update_config(
            environment=body.environment, sandbox_base_url=body.sandbox_base_url,
            production_base_url=body.production_base_url, merchant_id=body.merchant_id,
            partner_id=body.partner_id, client_id=body.client_id,
            sandbox_client_secret=body.sandbox_client_secret, production_client_secret=body.production_client_secret,
            sandbox_private_key=body.sandbox_private_key, production_private_key=body.production_private_key,
            sandbox_faspay_public_key=body.sandbox_faspay_public_key,
            production_faspay_public_key=body.production_faspay_public_key,
            sandbox_webhook_secret=body.sandbox_webhook_secret, production_webhook_secret=body.production_webhook_secret,
            timeout_detik=body.timeout_detik,
            retry_max=body.retry_max, channel_aktif=body.channel_aktif,
            channel_id=body.channel_id, va_bank_aktif=body.va_bank_aktif,
            qris_channel_code=body.qris_channel_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_config_snap_advance",
                               detail=f"environment={hasil['snap_environment']}, channel_aktif={hasil['snap_channel_aktif']}")
    return hasil


async def _tangani_notifikasi(request: Request, jenis: str, path: str):
    """Helper BERSAMA ketiga endpoint di bawah -- SATU-SATUNYA tempat
    envelope HTTP (baca body/header, terjemahkan exception jadi status
    code) ditulis, supaya perilaku ketiganya PERSIS konsisten. `jenis`
    EKSPLISIT dari endpoint mana yang dipukul (va/qris/direct_debit) --
    TIDAK LAGI ditebak dari isi payload (lihat catatan modul). `path`
    HARUS path resmi Faspay endpoint ini (dipakai verifikasi signature,
    lihat snap_advance_client.py::verifikasi_signature_webhook()).

    BUKTI SERTIFIKASI + TROUBLESHOOTING (sama alasannya dengan
    gateway_client_base.post_json_raw()): request MASUK dari Faspay dicatat
    UTUH ke log server (level INFO, Render Logs) SEBELUM verifikasi
    signature dilakukan -- supaya kalau Faspay genuinely mengirim notifikasi
    tapi ditolak (mis. public key belum dikonfigurasi, atau formula
    signature webhook yang BELUM dicocokkan 1:1 ke dokumen resmi, lihat
    catatan verifikasi_signature_webhook()), penyebabnya kelihatan dari log
    -- BUKAN cuma baris akses "400 Bad Request" tanpa detail apa pun."""
    raw_body = (await request.body()).decode("utf-8", errors="replace")
    signature_header = request.headers.get("X-SIGNATURE", "")
    timestamp_header = request.headers.get("X-TIMESTAMP")
    logger = logging.getLogger("mugen.gateway")
    # BUKTI SERTIFIKASI + TROUBLESHOOTING (lanjutan): snap_faspay_public_key
    # BUKAN rahasia (public key, lihat snap_advance_db.py -- SENGAJA tidak
    # masuk daftar field yang di-mask), jadi AMAN dicatat statusnya di sini
    # -- membedakan "belum dikonfigurasi sama sekali" vs "sudah diisi tapi
    # signature tetap tidak cocok" TANPA mengubah pesan error yang dibalas
    # ke Faspay (tetap generik, pola sengaja SAMA seperti gateway_client_base.py::
    # verify_sha512() -- lihat catatan snap_webhook.py::proses_notifikasi()).
    _cfg_publik = snap_advance_db.get_config()
    public_key_terisi = bool(_cfg_publik.get(f"snap_{_cfg_publik['snap_environment']}_faspay_public_key"))
    logger.info("SNAP WEBHOOK IN -- POST %s -- X-TIMESTAMP: %s -- X-SIGNATURE: %s -- snap_faspay_public_key terisi: %s -- BODY: %s",
                path, timestamp_header, signature_header, public_key_terisi, raw_body)
    try:
        snap_webhook.proses_notifikasi(raw_body, signature_header, timestamp_header, jenis, path)
        balasan = snap_webhook.balas_notifikasi(jenis, json.loads(raw_body))
        logger.info("SNAP WEBHOOK IN -- POST %s -- diterima, balasan: %s", path, balasan)
        return balasan
    except ValueError as e:
        logger.error("SNAP WEBHOOK IN -- POST %s -- DITOLAK: %s", path, e)
        raise HTTPException(status_code=400, detail=str(e))
    except GatewayError as e:
        logger.error("SNAP WEBHOOK IN -- POST %s -- error provider: %s", path, e)
        raise HTTPException(status_code=503, detail=str(e))


@notification_router.post("/v1.0/transfer-va/payment")
async def snap_notification_va(request: Request):
    """Payment Notification SNAP VA -- path RESMI dikonfirmasi Faspay
    (menggantikan asumsi endpoint gabungan lama, lihat catatan modul).
    Payload dicocokkan lewat `trxId` (BUKAN partnerReferenceNo) -- lihat
    snap_webhook.py::_ekstrak_notifikasi()."""
    return await _tangani_notifikasi(request, "va", "/v1.0/transfer-va/payment")


@notification_router.post("/v1.0/qr/qr-mpm-notify")
async def snap_notification_qris(request: Request):
    """Payment Notification SNAP QRIS -- path RESMI dikonfirmasi Faspay.
    Bentuk payload SAMA dengan Direct Debit (originalPartnerReferenceNo),
    TAPI sekarang tidak perlu ditebak channelCode-nya -- path endpoint ini
    SENDIRI sudah menyatakan jenisnya dengan pasti."""
    return await _tangani_notifikasi(request, "qris", "/v1.0/qr/qr-mpm-notify")


@notification_router.post("/v1.0/debit/notify")
async def snap_notification_direct_debit(request: Request):
    """Payment Notification SNAP Direct Debit -- path RESMI dikonfirmasi
    Faspay. Payload dicocokkan lewat `originalPartnerReferenceNo`, field
    `latestTransactionStatus` TOP-LEVEL (beda dari VA yang bersarang di
    additionalInfo) -- lihat snap_webhook.py::_ekstrak_notifikasi()."""
    return await _tangani_notifikasi(request, "direct_debit", "/v1.0/debit/notify")
