"""routers/live_chat.py — FITUR BARU "Live Chat": Inbox WhatsApp customer
terintegrasi (lihat docstring live_chat_db.py untuk arsitektur lengkap)
=============================================================================
PERMINTAAN Owner: Live Chat HANYA lewat koneksi WhatsApp Web sendiri (lihat
routers/live_chat_baileys.py, library Baileys) -- jalur webhook Fonnte +
fallback kirimnya (whatsapp_service.kirim_whatsapp()) SUDAH DIHAPUS TOTAL
dari modul ini. Fonnte TETAP dipakai whatsapp_service.py untuk reminder/
OTP/notifikasi booking otomatis -- SAMA SEKALI TIDAK terpengaruh perubahan
ini, modul itu tidak diubah sedikit pun.

`authed_router` (/api/live-chat): require_permission("izin_live_chat_lihat")
-- lihat permissions.py. Daftar kontak, thread per nomor, kirim balasan
(lewat routers/live_chat_baileys.py::kirim_pesan_lewat_baileys(), WAJIB
tenant sudah tersambung Baileys -- lihat kirim_balasan() di bawah), serve
gambar."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from fastapi.responses import Response

import live_chat_baileys_db
import live_chat_db
from auth import require_permission
from routers.live_chat_baileys import kirim_pesan_lewat_baileys

logger = logging.getLogger("mugen.live_chat")

authed_router = APIRouter(prefix="/api/live-chat", tags=["live-chat"])


class KirimBalasanBody(BaseModel):
    pesan: str


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
    # PERMINTAAN Owner: Live Chat HANYA lewat Baileys -- Fonnte sudah tidak
    # ada jalur fallback-nya lagi di sini sama sekali (lihat docstring
    # modul). Tenant WAJIB sudah tersambung (status 'tersambung', scan QR
    # dulu lewat kartu "Hubungkan WhatsApp" di halaman Live Chat) sebelum
    # bisa kirim balasan sama sekali.
    if not live_chat_baileys_db.kirim_terpasang(user["tenant_id"]):
        raise HTTPException(status_code=409, detail="WhatsApp toko belum terhubung -- hubungkan dulu lewat kartu di atas sebelum mengirim pesan.")
    try:
        baileys_msg_id = kirim_pesan_lewat_baileys(user["tenant_id"], nomor_wa, body.pesan)
    except Exception as e:
        logger.error("Gagal kirim lewat Baileys tenant_id=%s: %s: %s", user["tenant_id"], type(e).__name__, e)
        raise HTTPException(status_code=502, detail="Gagal mengirim WhatsApp lewat koneksi Baileys.")
    live_chat_db.simpan_pesan_teks_keluar(user["tenant_id"], nomor_wa, body.pesan, baileys_msg_id)
    return {"ok": True}


@authed_router.get("/gambar/{pesan_id}")
def ambil_gambar(pesan_id: int, user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    data, content_type = live_chat_db.get_gambar(user["tenant_id"], pesan_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Gambar tidak ditemukan.")
    return Response(content=data, media_type=content_type)
