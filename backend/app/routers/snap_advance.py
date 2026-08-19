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
   yang berbeda untuk Merchant ID yang sama" -- TERPISAH dari
   `/faspay-notification` (Xpress v4 lama, routers/gateway_notification.py,
   TIDAK disentuh) karena skema payload/signature SNAP beda total, endpoint
   BEDA path memang wajar (satu Merchant ID tetap boleh punya lebih dari
   satu URL webhook KALAU keduanya produk API yang berbeda -- batasan resmi
   Faspay "satu Payment Notification URL" yang dikonfirmasi sebelumnya
   berlaku untuk Xpress v4, BELUM dikonfirmasi berlaku sama untuk SNAP;
   PENDING FASPAY -- lihat laporan analisis)."""

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
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_config_snap_advance",
                               detail=f"environment={hasil['snap_environment']}, channel_aktif={hasil['snap_channel_aktif']}")
    return hasil


@public_router.post("/snap-notification")
async def snap_notification(request: Request):
    """URL Payment Notification SNAP Advance -- lihat catatan modul soal
    KENAPA path ini terpisah dari /faspay-notification (Xpress lama).
    PENDING FASPAY total (lihat snap_webhook.proses_notifikasi()) -- balas
    503 (BUKAN 400/500) selama masih PENDING, supaya jelas ini "belum siap
    diimplementasikan", bukan kegagalan validasi permintaan yang masuk."""
    raw_body = (await request.body()).decode("utf-8", errors="replace")
    signature_header = request.headers.get("X-SIGNATURE", "")
    timestamp_header = request.headers.get("X-TIMESTAMP")
    try:
        return snap_webhook.proses_notifikasi(raw_body, signature_header, timestamp_header)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GatewayError as e:
        raise HTTPException(status_code=503, detail=str(e))
