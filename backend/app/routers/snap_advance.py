"""routers/snap_advance.py — Migrasi Faspay SNAP Advance: konfigurasi (Super
Admin) + SATU webhook endpoint untuk Merchant ID Faspay
=============================================================================
Dua router dalam SATU file (pola sama seperti routers/booking.py):
1. `router` (prefix `/api/superadmin/snap-advance`) -- konfigurasi
   kredensial platform-wide, HANYA require_superadmin (pola SAMA PERSIS
   routers/payment_gateway.py), setiap perubahan tercatat superadmin_audit_log.
2. `public_router` (prefix `/api/public/gateway`) -- SATU webhook endpoint
   `POST /snap-notification` untuk KEDUA jenis transaksi (Booking + SaaS
   Billing), SESUAI instruksi migrasi #3 "Jangan membuat dua webhook Faspay
   yang berbeda untuk Merchant ID yang sama". Faspay SUDAH mengonfirmasi
   eksplisit (audit lanjutan): satu Merchant ID (37070) hanya boleh punya
   SATU Payment Notification URL -- Owner memutuskan Xpress v4 TIDAK LAGI
   dipakai, URL ini ("/snap-notification") jadi SATU-SATUNYA yang
   didaftarkan ke Faspay (menggantikan `/faspay-notification` Xpress lama,
   routers/gateway_notification.py -- modul itu TIDAK dihapus, lihat audit
   dependency, tapi tidak lagi menerima trafik nyata begitu Faspay
   mengalihkan registrasinya)."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import snap_advance_db
import snap_webhook
import superadmin_audit_db
from auth import require_superadmin
from gateway_client_base import GatewayError

router = APIRouter(prefix="/api/superadmin/snap-advance", tags=["snap-advance-superadmin"])
public_router = APIRouter(prefix="/api/public/gateway", tags=["snap-advance-webhook"])


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
    client_secret: str | None = None
    private_key: str | None = None
    faspay_public_key: str | None = None
    webhook_secret: str | None = None
    timeout_detik: int | None = None
    retry_max: int | None = None
    channel_aktif: list[str] | None = None
    channel_id: str | None = None
    va_channel_code: str | None = None
    qris_channel_code: str | None = None


@router.put("/config")
def ubah_config(body: ConfigBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = snap_advance_db.update_config(
            environment=body.environment, sandbox_base_url=body.sandbox_base_url,
            production_base_url=body.production_base_url, merchant_id=body.merchant_id,
            partner_id=body.partner_id, client_id=body.client_id, client_secret=body.client_secret,
            private_key=body.private_key, faspay_public_key=body.faspay_public_key,
            webhook_secret=body.webhook_secret, timeout_detik=body.timeout_detik,
            retry_max=body.retry_max, channel_aktif=body.channel_aktif,
            channel_id=body.channel_id, va_channel_code=body.va_channel_code,
            qris_channel_code=body.qris_channel_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_config_snap_advance",
                               detail=f"environment={hasil['snap_environment']}, channel_aktif={hasil['snap_channel_aktif']}")
    return hasil


@public_router.post("/snap-notification")
async def snap_notification(request: Request):
    """URL Payment Notification SNAP Advance -- SATU-SATUNYA URL notifikasi
    yang didaftarkan Faspay untuk Merchant ID 37070 (Owner memutuskan Xpress
    v4 tidak lagi dipakai, lihat catatan modul). VA, Direct Debit, & QRIS
    sudah diimplementasikan sungguhan (snap_webhook.proses_notifikasi()) --
    balas 400 untuk signature tidak valid/referensi tidak dikenal/status
    tidak didukung, 503 HANYA kalau proses_notifikasi() melempar GatewayError
    (mis. channel E-Wallet di luar QRIS yang masih PENDING FASPAY total).

    BUGFIX (audit lanjutan): balas HTTP dengan body acknowledgment SESUAI
    dokumen resmi Faspay (snap_webhook.balas_notifikasi(), bentuknya BEDA
    per jenis servis), BUKAN echo objek transaksi internal kita -- respons
    yang tidak sesuai format berisiko Faspay mengira notifikasi gagal
    diproses & mengirim ulang terus-menerus."""
    raw_body = (await request.body()).decode("utf-8", errors="replace")
    signature_header = request.headers.get("X-SIGNATURE", "")
    timestamp_header = request.headers.get("X-TIMESTAMP")
    try:
        snap_webhook.proses_notifikasi(raw_body, signature_header, timestamp_header)
        return snap_webhook.balas_notifikasi(json.loads(raw_body))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GatewayError as e:
        raise HTTPException(status_code=503, detail=str(e))
