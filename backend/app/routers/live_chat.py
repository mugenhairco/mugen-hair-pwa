"""routers/live_chat.py — FITUR BARU "Live Chat": Inbox WhatsApp customer
terintegrasi (lihat docstring live_chat_db.py untuk arsitektur lengkap)
=============================================================================
Dua kelompok endpoint:

1. `public_router` (/api/live-chat/webhook/{token}): dipanggil Fonnte --
   SENGAJA TIDAK memakai sesi login Rivoir sama sekali (Fonnte tidak punya
   token Rivoir), persis seperti webhook WA Bot yang sudah dihapus, TAPI
   `token` di sini per-tenant (live_chat_db.get_tenant_by_webhook_token()),
   BUKAN satu secret global -- Owner sendiri yang memasang URL ini di
   dashboard Fonnte miliknya (self-service), jadi tenant-nya SUDAH diketahui
   dari token itu sendiri, tidak perlu field `device` di payload untuk
   resolusi tenant (beda dari WA Bot lama yang dikelola terpusat Superadmin).

   Fonnte mengirim payload form-encoded (field `sender`, `message`, `name`,
   dan `url`/`filename` KHUSUS untuk lampiran media -- lihat
   https://docs.fonnte.com/webhook-get-attachment/, HANYA tersedia untuk
   paket Fonnte tertentu: kalau tenant belum berlangganan paket itu, field
   `url` TIDAK PERNAH terkirim -- pesan gambar customer akan terlewat diam-
   diam sampai Owner upgrade paket Fonnte-nya, BUKAN bug di sisi Rivoir).

2. `authed_router` (/api/live-chat): require_permission("izin_live_chat_lihat")
   -- lihat permissions.py. Daftar kontak, thread per nomor, kirim balasan
   (lewat whatsapp_service.kirim_whatsapp() yang SUDAH ADA, token Fonnte
   yang SAMA dipakai whatsapp_service.py untuk reminder/konfirmasi booking),
   serve gambar, dan ambil/reset URL webhook untuk dipasang Owner sendiri."""

import logging

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import Response

import live_chat_baileys_db
import live_chat_db
import push_service
import whatsapp_service
from auth import require_permission
from routers.live_chat_baileys import kirim_pesan_lewat_baileys

logger = logging.getLogger("mugen.live_chat")

public_router = APIRouter(prefix="/api/live-chat", tags=["live-chat"])
authed_router = APIRouter(prefix="/api/live-chat", tags=["live-chat"])

_UNDUH_TIMEOUT_DETIK = 20
_EKSTENSI_GAMBAR = {"jpg", "jpeg", "png", "webp"}


# ---------------------------------------------------------------------------
# Webhook publik (Fonnte) -- TANPA sesi login Rivoir
# ---------------------------------------------------------------------------

def _unduh_lampiran(url: str):
    """Best-effort -- return (bytes, nama_file) atau (None, None) kalau
    gagal diunduh/bukan gambar. TIDAK PERNAH melempar exception ke
    pemanggil (webhook HARUS tetap balas 200 ke Fonnte apa pun hasilnya)."""
    try:
        resp = requests.get(url, timeout=_UNDUH_TIMEOUT_DETIK)
        if resp.status_code >= 400 or not resp.content:
            return None, None
        nama_file = url.rsplit("/", 1)[-1].split("?", 1)[0] or "gambar.jpg"
        ext = nama_file.rsplit(".", 1)[-1].lower() if "." in nama_file else ""
        if ext not in _EKSTENSI_GAMBAR:
            # Fonnte kadang tidak menyertakan ekstensi di URL -- tebak dari
            # Content-Type sebelum menyerah (bukan gambar sama sekali, mis.
            # dokumen/voice note, TIDAK didukung fitur ini saat ini).
            content_type = (resp.headers.get("Content-Type") or "").lower()
            tebakan = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(content_type)
            if not tebakan:
                return None, None
            nama_file = f"gambar.{tebakan}"
        return resp.content, nama_file
    except Exception as e:
        logger.error("Live Chat: gagal unduh lampiran dari Fonnte: %s: %s", type(e).__name__, e)
        return None, None


@public_router.post("/webhook/{token}")
async def terima_webhook(token: str, request: Request):
    """SELALU balas 200 untuk payload yang sah tapi dilewati (bukan gambar
    yang didukung, teks kosong, dst) -- hanya token yang salah/tidak
    dikenal yang ditolak 403."""
    tenant_id = live_chat_db.get_tenant_by_webhook_token(token)
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")

    try:
        payload = await request.json()
    except Exception:
        form = await request.form()
        payload = dict(form)

    nomor_wa = str(payload.get("sender") or "").strip()
    pesan_teks = str(payload.get("message") or "")
    nama_kontak = str(payload.get("name") or "").strip() or None
    url_lampiran = str(payload.get("url") or "").strip()

    if not nomor_wa:
        return {"ok": True}  # payload tidak dikenali (mis. event non-pesan) -- abaikan

    if url_lampiran:
        konten, nama_file = _unduh_lampiran(url_lampiran)
        if konten is not None:
            try:
                pesan_id = live_chat_db.simpan_pesan_gambar_masuk(tenant_id, nomor_wa, nama_kontak, nama_file, konten)
            except ValueError as e:
                logger.warning("Live Chat: lampiran dari %s ditolak: %s", nomor_wa, e)
                return {"ok": True}
            push_service.kirim_ke_role(
                tenant_id, ["admin", "staff"], "Live Chat",
                f"{nama_kontak or nomor_wa} mengirim gambar",
                url="#/live-chat", jenis="live_chat_masuk",
                data={"nomor_wa": nomor_wa, "nama_kontak": nama_kontak, "jenis": "gambar", "pesan_id": pesan_id},
            )
            return {"ok": True}
        # Lampiran gagal diunduh/bukan gambar -- fallback ke teks di bawah
        # kalau ada caption, atau diam-diam diabaikan kalau tidak ada.

    if not pesan_teks.strip():
        return {"ok": True}

    live_chat_db.simpan_pesan_teks_masuk(tenant_id, nomor_wa, nama_kontak, pesan_teks)
    preview = pesan_teks if len(pesan_teks) <= 80 else pesan_teks[:77] + "..."
    push_service.kirim_ke_role(
        tenant_id, ["admin", "staff"], f"Live Chat -- {nama_kontak or nomor_wa}",
        preview, url="#/live-chat", jenis="live_chat_masuk",
        data={"nomor_wa": nomor_wa, "nama_kontak": nama_kontak, "jenis": "teks", "isi_teks": pesan_teks},
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# API ber-sesi (Owner/Admin/Staff yang diberi izin_live_chat_lihat)
# ---------------------------------------------------------------------------

class KirimBalasanBody(BaseModel):
    pesan: str


@authed_router.get("/webhook-info")
def ambil_webhook_info(user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    token = live_chat_db.get_or_create_webhook_token(user["tenant_id"])
    return {"webhook_path": f"/api/live-chat/webhook/{token}"}


@authed_router.post("/webhook-info/reset")
def reset_webhook_info(user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    """Owner curiga URL lama bocor -- token diganti, URL lama berhenti
    berfungsi, Owner WAJIB pasang ulang URL baru di dashboard Fonnte-nya."""
    token = live_chat_db.regenerate_webhook_token(user["tenant_id"])
    return {"webhook_path": f"/api/live-chat/webhook/{token}"}


@authed_router.get("/kontak")
def ambil_kontak(user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    return live_chat_db.list_kontak(user["tenant_id"])


@authed_router.get("/pesan/{nomor_wa}")
def ambil_thread(nomor_wa: str, user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    pesan = live_chat_db.list_pesan_thread(user["tenant_id"], nomor_wa)
    # PERMINTAAN Owner: retensi otomatis dihitung SEJAK thread ini dibuka di
    # Rivoir (bukan sejak pesan dibuat) -- ditandai SETELAH baca, supaya
    # thread yang baru pertama kali dibuka tetap menampilkan isinya dulu.
    live_chat_db.tandai_dibuka(user["tenant_id"], nomor_wa)
    return pesan


@authed_router.post("/kirim/{nomor_wa}")
def kirim_balasan(nomor_wa: str, body: KirimBalasanBody,
                   user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    if not body.pesan.strip():
        raise HTTPException(status_code=422, detail="Pesan tidak boleh kosong.")
    # FITUR Live Chat via Baileys (PERMINTAAN Owner: pesan manual dari HP
    # toko tidak pernah terlihat Rivoir lewat Fonnte -- lihat docstring
    # live_chat_baileys_db.py): tenant yang SUDAH berhasil scan QR (status
    # 'tersambung') pindah jalur kirim ke Baileys; tenant lain TETAP lewat
    # Fonnte seperti semula, TIDAK ada bedanya sama sekali dari sebelumnya.
    if live_chat_baileys_db.kirim_terpasang(user["tenant_id"]):
        try:
            baileys_msg_id = kirim_pesan_lewat_baileys(user["tenant_id"], nomor_wa, body.pesan)
        except Exception as e:
            logger.error("Gagal kirim lewat Baileys tenant_id=%s: %s: %s", user["tenant_id"], type(e).__name__, e)
            raise HTTPException(status_code=502, detail="Gagal mengirim WhatsApp lewat koneksi Baileys.")
        live_chat_db.simpan_pesan_teks_keluar(user["tenant_id"], nomor_wa, body.pesan, baileys_msg_id)
        return {"ok": True}
    terkirim = whatsapp_service.kirim_whatsapp(nomor_wa, body.pesan, tenant_id=user["tenant_id"])
    if not terkirim:
        raise HTTPException(status_code=502, detail="Gagal mengirim WhatsApp -- pastikan token Fonnte di Setting > WhatsApp sudah benar.")
    live_chat_db.simpan_pesan_teks_keluar(user["tenant_id"], nomor_wa, body.pesan)
    return {"ok": True}


@authed_router.get("/gambar/{pesan_id}")
def ambil_gambar(pesan_id: int, user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    data, content_type = live_chat_db.get_gambar(user["tenant_id"], pesan_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Gambar tidak ditemukan.")
    return Response(content=data, media_type=content_type)
