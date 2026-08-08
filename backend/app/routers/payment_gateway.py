"""routers/payment_gateway.py — Konfigurasi Payment Gateway (Super Admin)
=========================================================================
Kredensial PGW platform-wide (lihat payment_gateway_db.py) -- HANYA
role 'superadmin' yang boleh membaca/mengubah (require_superadmin, pola
SAMA PERSIS dengan routers/subscription.py::superadmin_router), setiap
perubahan tercatat ke superadmin_audit_log."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import payment_gateway_db
import superadmin_audit_db
from auth import require_superadmin

router = APIRouter(prefix="/api/superadmin/payment-gateway", tags=["payment-gateway-superadmin"])


@router.get("/config")
def ambil_config(user: dict = Depends(require_superadmin)):
    return payment_gateway_db.get_config()


class ConfigBody(BaseModel):
    provider: str | None = None
    environment: str | None = None
    api_key: str | None = None
    server_key: str | None = None
    client_key: str | None = None
    merchant_id: str | None = None
    secret_key: str | None = None
    webhook_url: str | None = None
    metode_aktif: list[str] | None = None


@router.put("/config")
def ubah_config(body: ConfigBody, user: dict = Depends(require_superadmin)):
    try:
        hasil = payment_gateway_db.update_config(
            provider=body.provider, environment=body.environment, api_key=body.api_key,
            server_key=body.server_key, client_key=body.client_key, merchant_id=body.merchant_id,
            secret_key=body.secret_key, webhook_url=body.webhook_url, metode_aktif=body.metode_aktif,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_config_payment_gateway",
                               detail=f"provider={hasil['pgw_provider']}, environment={hasil['pgw_environment']}, "
                                      f"metode_aktif={hasil['metode_aktif']}")
    return hasil
