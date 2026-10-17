"""routers/whatsapp_bot.py — FITUR WA Bot (Input Data & Rekap via WhatsApp)
=============================================================================
Dua kelompok endpoint, lihat whatsapp_bot_db.py untuk arsitektur lengkap:

1. `public_router` (/api/whatsapp-bot/webhook/{secret}): dipanggil Fonnte --
   SENGAJA TIDAK memakai sesi login Rivoir sama sekali (Fonnte tidak punya
   token Rivoir). Fonnte TIDAK punya handshake verifikasi webhook seperti
   Meta (tidak ada langkah GET terpisah) -- ia langsung POST ke URL yang
   diisi di dashboard device->edit->webhook begitu ada pesan masuk. Supaya
   endpoint ini tidak bisa dipanggil sembarang orang, URL webhook-nya
   membawa secret di path (`{secret}`, dicocokkan ke env var
   WHATSAPP_BOT_WEBHOOK_SECRET, pola SAMA seperti CRON_REMINDER_SECRET di
   routers/cron_reminder.py) -- fail-CLOSED kalau env var belum diisi.
   Tenant-nya diketahui dari field `device` di payload (nomor WA bot itu
   sendiri, lihat whatsapp_bot_db.get_config_by_phone_number_id()).

   TAHAP INI (fondasi): pesan masuk dicatat (whatsapp_bot_db.catat_pesan())
   + kuota dicek, lalu dibalas konfirmasi sederhana lewat Fonnte Send API --
   PARSING pesan jadi transaksi/libur SUNGGUHAN (format "Romen Dry Cut 3,
   Tips 30rb...") & pembatasan akses per role (barber cuma lihat rekap
   miliknya sendiri) adalah tahap LANJUTAN, belum dibangun di sini.

2. `superadmin_router` (/api/superadmin/whatsapp-bot): KHUSUS Superadmin
   (require_superadmin) -- daftarkan/ubah nomor+device_token per tenant +
   aktifkan/nonaktifkan + atur kuota pesan/bulan. Permintaan Owner eksplisit:
   "yang memiliki hak untuk mengaktifkan atau mengatur [WA Bot] hanya
   superadmin" -- Owner/Admin tenant TIDAK PUNYA endpoint untuk mengubah
   ini sama sekali."""

import logging
import os

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import tenant_db
import whatsapp_bot_db
from auth import require_superadmin

logger = logging.getLogger("mugen.whatsapp_bot")

public_router = APIRouter(prefix="/api/whatsapp-bot", tags=["whatsapp-bot"])
superadmin_router = APIRouter(prefix="/api/superadmin/whatsapp-bot", tags=["whatsapp-bot-superadmin"])

_WEBHOOK_SECRET = os.environ.get("WHATSAPP_BOT_WEBHOOK_SECRET", "").strip()
_FONNTE_SEND_URL = "https://api.fonnte.com/send"


def _kirim_balasan(device_token: str, ke_nomor: str, teks: str) -> None:
    """Best-effort -- kegagalan kirim balasan TIDAK BOLEH menggagalkan
    pemrosesan webhook (tetap balas 200 ke Fonnte terlepas dari
    berhasil/tidaknya balasan terkirim)."""
    if not device_token:
        logger.warning("WA Bot: device_token tenant ini kosong -- balasan TIDAK dikirim.")
        return
    try:
        resp = requests.post(
            _FONNTE_SEND_URL,
            headers={"Authorization": device_token},
            data={"target": ke_nomor, "message": teks},
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.error("WA Bot: gagal kirim balasan ke %s: HTTP %s %s", ke_nomor, resp.status_code, resp.text)
    except Exception as e:
        logger.error("WA Bot: gagal kirim balasan ke %s: %s: %s", ke_nomor, type(e).__name__, e)


# ---------------------------------------------------------------------------
# Webhook publik (Fonnte) -- TANPA sesi login Rivoir
# ---------------------------------------------------------------------------

@public_router.post("/webhook/{secret}")
async def terima_webhook(secret: str, request: Request):
    """SELALU balas 200 untuk payload yang sah tapi diabaikan (nomor tidak
    terdaftar/kuota habis) -- hanya secret yang salah/kosong yang ditolak
    403. Fonnte mengirim payload form-encoded (field `device`, `sender`,
    `message`, `name`) -- dicoba JSON dulu untuk jaga-jaga, baru fallback
    form."""
    if not _WEBHOOK_SECRET or secret != _WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")

    try:
        payload = await request.json()
    except Exception:
        form = await request.form()
        payload = dict(form)

    nomor_device = str(payload.get("device") or "").strip()
    wa_id_pengirim = str(payload.get("sender") or "").strip()
    isi_pesan = str(payload.get("message") or "")

    if not nomor_device or not wa_id_pengirim:
        return {"ok": True}  # payload tidak dikenali (mis. event non-pesan) -- abaikan

    config = whatsapp_bot_db.get_config_by_phone_number_id(nomor_device)
    if config is None:
        return {"ok": True}  # nomor ini tidak terdaftar/dinonaktifkan Superadmin -- diam-diam diabaikan

    tenant_id = config["tenant_id"]
    kuota = whatsapp_bot_db.cek_kuota(tenant_id)
    if kuota["habis"]:
        whatsapp_bot_db.catat_pesan(tenant_id, wa_id_pengirim, isi_pesan, "ditolak_kuota")
        _kirim_balasan(config["device_token"], wa_id_pengirim,
                        "Kuota pesan WA Bot bulan ini sudah habis. Hubungi Owner/Admin.")
        return {"ok": True}

    # TAHAP FONDASI: catat + balas konfirmasi diterima. Parsing jadi
    # transaksi/libur sungguhan (format "Romen Dry Cut 3, Tips 30rb...")
    # menyusul di tahap lanjutan.
    whatsapp_bot_db.catat_pesan(tenant_id, wa_id_pengirim, isi_pesan, "diproses")
    _kirim_balasan(config["device_token"], wa_id_pengirim,
                    "Pesan diterima Rivoir WA Bot. Fitur pemrosesan otomatis sedang disiapkan.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Superadmin -- kelola nomor/token/aktif/kuota per tenant
# ---------------------------------------------------------------------------

@superadmin_router.get("")
def list_konfigurasi(user: dict = Depends(require_superadmin)):
    """Daftar SEMUA tenant + status WA Bot masing-masing (tenant yang
    belum pernah diatur tetap muncul dengan `config=None`, supaya
    Superadmin bisa langsung daftarkan dari layar yang sama)."""
    config_by_tenant = {c["tenant_id"]: c for c in whatsapp_bot_db.list_config()}
    hasil = []
    for t in tenant_db.list_tenants():
        hasil.append({
            "tenant_id": t["id"],
            "nama_barbershop": t["nama_barbershop"],
            "slug": t["slug"],
            "config": config_by_tenant.get(t["id"]),
        })
    return hasil


class KonfigurasiBody(BaseModel):
    phone_number_id: str  # nomor WA device Fonnte (nomor bot itu sendiri)
    device_token: str  # token API device ini (dashboard Fonnte -> device list)
    nama_nomor: str | None = None
    kuota_pesan_bulanan: int | None = None


@superadmin_router.put("/{tenant_id}")
def atur_konfigurasi(tenant_id: int, body: KonfigurasiBody, user: dict = Depends(require_superadmin)):
    if tenant_db.get_tenant(tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    try:
        return whatsapp_bot_db.upsert_config(
            tenant_id, body.phone_number_id, body.device_token, nama_nomor=body.nama_nomor,
            kuota_pesan_bulanan=body.kuota_pesan_bulanan, diatur_oleh=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


class StatusBody(BaseModel):
    aktif: bool


@superadmin_router.put("/{tenant_id}/status")
def ubah_status(tenant_id: int, body: StatusBody, user: dict = Depends(require_superadmin)):
    try:
        return whatsapp_bot_db.set_aktif(tenant_id, body.aktif, diatur_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@superadmin_router.delete("/{tenant_id}")
def hapus_konfigurasi(tenant_id: int, user: dict = Depends(require_superadmin)):
    whatsapp_bot_db.hapus_config(tenant_id)
    return {"ok": True}
