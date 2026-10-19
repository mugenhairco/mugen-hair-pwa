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

   PARSING pesan jadi command (Input Data, Rekap, Absensi, Cuti/Izin,
   Booking, dll) + resolusi akses Owner/Barber SEPENUHNYA ada di
   whatsapp_bot_parser.py::proses_pesan() -- handler di sini murni
   "pipa": cek duplikat (anti pesan dobel, lihat whatsapp_bot_db.
   pesan_duplikat()) -> panggil proses_pesan() -> kalau hasilnya None
   (nomor pengirim tidak dikenal) diam total, TIDAK menyentuh kuota sama
   sekali -- kalau ada balasan, BARU kuota dicek (quota berlaku SAMA untuk
   SEMUA jenis pesan yang benar-benar diproses, baca maupun tulis,
   keputusan eksplisit Owner, TIDAK dipisah).

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

import superadmin_audit_db
import tenant_db
import whatsapp_bot_db
import whatsapp_bot_parser
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
    terdaftar/tidak dikenal/kuota habis) -- hanya secret yang salah/kosong
    yang ditolak 403. Fonnte mengirim payload form-encoded (field
    `device`, `sender`, `message`, `name`) -- dicoba JSON dulu untuk jaga-
    jaga, baru fallback form."""
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

    # PERMINTAAN OWNER: proteksi anti-dobel HANYA berlaku untuk command
    # yang menulis data -- command baca (Rekap/Absensi/dst) selalu boleh
    # diproses ulang walau isinya persis sama, supaya Owner yang sengaja
    # kirim ulang command baca yang sama tetap dapat balasan (lihat
    # docstring whatsapp_bot_parser.adalah_command_baca()).
    if not whatsapp_bot_parser.adalah_command_baca(isi_pesan) and \
            whatsapp_bot_db.pesan_duplikat(tenant_id, wa_id_pengirim, isi_pesan):
        return {"ok": True}  # webhook terkirim ulang (retry Fonnte) -- SUDAH diproses, jangan diulang

    balasan = whatsapp_bot_parser.proses_pesan(tenant_id, config, wa_id_pengirim, isi_pesan)
    if balasan is None:
        return {"ok": True}  # pengirim tidak dikenal (bukan Owner, bukan barber tenant ini) -- diam total

    kuota = whatsapp_bot_db.cek_kuota(tenant_id)
    if kuota["habis"]:
        whatsapp_bot_db.catat_pesan(tenant_id, wa_id_pengirim, isi_pesan, "ditolak_kuota")
        _kirim_balasan(config["device_token"], wa_id_pengirim,
                        "Kuota pesan WA Bot bulan ini sudah habis. Hubungi Owner/Admin.")
        return {"ok": True}

    whatsapp_bot_db.catat_pesan(tenant_id, wa_id_pengirim, isi_pesan, "diproses")
    # PERMINTAAN OWNER: beri peringatan di balasan pesan TERAKHIR sebelum
    # kuota benar-benar habis (bukan cuma pesan penolakan SETELAH kuota
    # habis, yang sudah ada di atas) -- dicek SETELAH catat_pesan() di
    # atas supaya `sisa` mencerminkan kuota SETELAH pesan ini terhitung.
    kuota_setelah = whatsapp_bot_db.cek_kuota(tenant_id)
    if kuota_setelah["sisa"] == 1:
        balasan += "\n\n⚠️ Sisa kuota pesan bulan ini tinggal 1."
    _kirim_balasan(config["device_token"], wa_id_pengirim, balasan)
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
    # nomor WA yang setara akses Owner penuh lewat bot (input data siapa
    # saja + rekap siapa saja) -- OPSIONAL, maksimal 2 nomor per tenant
    # (permintaan Owner: toko dengan 2 pemilik/pengelola), lihat
    # whatsapp_bot_parser.py::resolve_role().
    nomor_owner_whatsapp: str | None = None
    nomor_owner_whatsapp_2: str | None = None


@superadmin_router.put("/{tenant_id}")
def atur_konfigurasi(tenant_id: int, body: KonfigurasiBody, user: dict = Depends(require_superadmin)):
    t = tenant_db.get_tenant(tenant_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    try:
        hasil = whatsapp_bot_db.upsert_config(
            tenant_id, body.phone_number_id, body.device_token, nama_nomor=body.nama_nomor,
            kuota_pesan_bulanan=body.kuota_pesan_bulanan, diatur_oleh=user["username"],
            nomor_owner_whatsapp=body.nomor_owner_whatsapp,
            nomor_owner_whatsapp_2=body.nomor_owner_whatsapp_2,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_config_whatsapp_bot", tenant_id=tenant_id, tenant_slug=t["slug"])
    return hasil


class StatusBody(BaseModel):
    aktif: bool


@superadmin_router.put("/{tenant_id}/status")
def ubah_status(tenant_id: int, body: StatusBody, user: dict = Depends(require_superadmin)):
    t = tenant_db.get_tenant(tenant_id)
    try:
        hasil = whatsapp_bot_db.set_aktif(tenant_id, body.aktif, diatur_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_status_whatsapp_bot", tenant_id=tenant_id,
                               tenant_slug=t["slug"] if t else None)
    return hasil


class TampilkanPotonganKeterlambatanBody(BaseModel):
    aktif: bool


@superadmin_router.put("/{tenant_id}/tampilkan-potongan-keterlambatan")
def ubah_tampilkan_potongan_keterlambatan(tenant_id: int, body: TampilkanPotonganKeterlambatanBody,
                                           user: dict = Depends(require_superadmin)):
    t = tenant_db.get_tenant(tenant_id)
    try:
        hasil = whatsapp_bot_db.set_tampilkan_potongan_keterlambatan(tenant_id, body.aktif, diatur_oleh=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    superadmin_audit_db.catat(user["username"], "ubah_tampilkan_potongan_keterlambatan_whatsapp_bot", tenant_id=tenant_id,
                               tenant_slug=t["slug"] if t else None)
    return hasil


@superadmin_router.delete("/{tenant_id}")
def hapus_konfigurasi(tenant_id: int, user: dict = Depends(require_superadmin)):
    t = tenant_db.get_tenant(tenant_id)
    whatsapp_bot_db.hapus_config(tenant_id)
    superadmin_audit_db.catat(user["username"], "hapus_config_whatsapp_bot", tenant_id=tenant_id,
                               tenant_slug=t["slug"] if t else None)
    return {"ok": True}
