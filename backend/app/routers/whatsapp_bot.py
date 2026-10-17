"""routers/whatsapp_bot.py — FITUR WA Bot (Input Data & Rekap via WhatsApp)
=============================================================================
Dua kelompok endpoint, lihat whatsapp_bot_db.py untuk arsitektur lengkap:

1. `public_router` (/api/whatsapp-bot/webhook): dipanggil Meta WhatsApp
   Cloud API -- SENGAJA TIDAK memakai sesi login Rivoir sama sekali (Meta
   tidak punya token Rivoir). GET = handshake verifikasi webhook (Meta
   mengirim hub.verify_token, kita cocokkan ke env var
   WHATSAPP_BOT_VERIFY_TOKEN, pola SAMA seperti CRON_REMINDER_SECRET di
   routers/cron_reminder.py -- fail-CLOSED kalau env var belum diisi). POST
   = pesan masuk sungguhan, tenant-nya diketahui dari `phone_number_id` di
   payload (lihat whatsapp_bot_db.get_config_by_phone_number_id()).

   TAHAP INI (fondasi): pesan masuk dicatat (whatsapp_bot_db.catat_pesan())
   + kuota dicek, lalu dibalas konfirmasi sederhana lewat Graph API --
   PARSING pesan jadi transaksi/libur SUNGGUHAN (format "Romen Dry Cut 3,
   Tips 30rb...") & pembatasan akses per role (barber cuma lihat rekap
   miliknya sendiri) adalah tahap LANJUTAN, belum dibangun di sini.

2. `superadmin_router` (/api/superadmin/whatsapp-bot): KHUSUS Superadmin
   (require_superadmin) -- daftarkan/ubah Phone Number ID per tenant +
   aktifkan/nonaktifkan + atur kuota pesan/bulan. Permintaan Owner eksplisit:
   "yang memiliki hak untuk mengaktifkan atau mengatur [WA Bot] hanya
   superadmin" -- Owner/Admin tenant TIDAK PUNYA endpoint untuk mengubah
   ini sama sekali."""

import logging
import os

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

import tenant_db
import whatsapp_bot_db
from auth import require_superadmin

logger = logging.getLogger("mugen.whatsapp_bot")

public_router = APIRouter(prefix="/api/whatsapp-bot", tags=["whatsapp-bot"])
superadmin_router = APIRouter(prefix="/api/superadmin/whatsapp-bot", tags=["whatsapp-bot-superadmin"])

_VERIFY_TOKEN = os.environ.get("WHATSAPP_BOT_VERIFY_TOKEN", "").strip()
_ACCESS_TOKEN = os.environ.get("WHATSAPP_BOT_ACCESS_TOKEN", "").strip()
_GRAPH_API_VERSION = "v23.0"
_GRAPH_BASE_URL = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"


# ---------------------------------------------------------------------------
# Webhook publik (Meta) -- TANPA sesi login Rivoir
# ---------------------------------------------------------------------------

@public_router.get("/webhook")
def verifikasi_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    """Handshake SEKALI SAJA saat Superadmin klik "Verify and save" di Meta
    App Dashboard -- WAJIB fail-CLOSED kalau WHATSAPP_BOT_VERIFY_TOKEN
    belum diisi (jangan sampai verifikasi lolos tanpa proteksi apa pun)."""
    if not _VERIFY_TOKEN or hub_mode != "subscribe" or hub_verify_token != _VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Verifikasi gagal.")
    return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge


def _kirim_balasan(phone_number_id: str, ke_wa_id: str, teks: str) -> None:
    """Best-effort -- kegagalan kirim balasan TIDAK BOLEH menggagalkan
    pemrosesan webhook (Meta tetap butuh respons 200 dari endpoint POST
    terlepas dari berhasil/tidaknya balasan terkirim, supaya Meta tidak
    mengulang-ulang kirim payload yang sama)."""
    if not _ACCESS_TOKEN:
        logger.warning("WA Bot: WHATSAPP_BOT_ACCESS_TOKEN belum diisi -- balasan TIDAK dikirim.")
        return
    try:
        resp = requests.post(
            f"{_GRAPH_BASE_URL}/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": ke_wa_id, "type": "text", "text": {"body": teks}},
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.error("WA Bot: gagal kirim balasan ke %s: HTTP %s %s", ke_wa_id, resp.status_code, resp.text)
    except Exception as e:
        logger.error("WA Bot: gagal kirim balasan ke %s: %s: %s", ke_wa_id, type(e).__name__, e)


@public_router.post("/webhook")
async def terima_webhook(request: Request):
    """SELALU balas 200 (bahkan untuk payload yang diabaikan/gagal) --
    Meta akan mengulang-ulang kirim payload yang sama kalau dapat status
    non-2xx, yang justru bikin masalah dobel, bukan membantu."""
    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            if not phone_number_id:
                continue
            pesan_list = value.get("messages")
            if not pesan_list:
                continue  # "statuses" (status terkirim/gagal pesan KELUAR) -- bukan pesan masuk, abaikan
            config = whatsapp_bot_db.get_config_by_phone_number_id(phone_number_id)
            for pesan in pesan_list:
                wa_id_pengirim = pesan.get("from", "")
                isi_pesan = pesan.get("text", {}).get("body", "")
                if config is None:
                    continue  # nomor ini tidak terdaftar/dinonaktifkan Superadmin -- diam-diam diabaikan
                tenant_id = config["tenant_id"]
                kuota = whatsapp_bot_db.cek_kuota(tenant_id)
                if kuota["habis"]:
                    whatsapp_bot_db.catat_pesan(tenant_id, wa_id_pengirim, isi_pesan, "ditolak_kuota")
                    _kirim_balasan(phone_number_id, wa_id_pengirim,
                                    "Kuota pesan WA Bot bulan ini sudah habis. Hubungi Owner/Admin.")
                    continue
                # TAHAP FONDASI: catat + balas konfirmasi diterima. Parsing
                # jadi transaksi/libur sungguhan (format "Romen Dry Cut 3,
                # Tips 30rb...") menyusul di tahap lanjutan.
                whatsapp_bot_db.catat_pesan(tenant_id, wa_id_pengirim, isi_pesan, "diproses")
                _kirim_balasan(phone_number_id, wa_id_pengirim,
                                "Pesan diterima Rivoir WA Bot. Fitur pemrosesan otomatis sedang disiapkan.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Superadmin -- kelola nomor/aktif/kuota per tenant
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
    phone_number_id: str
    nama_nomor: str | None = None
    kuota_pesan_bulanan: int | None = None


@superadmin_router.put("/{tenant_id}")
def atur_konfigurasi(tenant_id: int, body: KonfigurasiBody, user: dict = Depends(require_superadmin)):
    if tenant_db.get_tenant(tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    try:
        return whatsapp_bot_db.upsert_config(
            tenant_id, body.phone_number_id, nama_nomor=body.nama_nomor,
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
