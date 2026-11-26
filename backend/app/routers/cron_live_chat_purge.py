"""routers/cron_live_chat_purge.py — Endpoint pemicu EKSTERNAL untuk
Retensi Otomatis Live Chat
=============================================================================
SATU-SATUNYA endpoint di sini SENGAJA TIDAK memakai sesi login/tenant sama
sekali -- pola SAMA PERSIS routers/cron_reminder.py & routers/
cron_purge_data.py, dipanggil layanan penjadwal GRATIS dari LUAR aplikasi
(mis. cron-job.org), BUKAN dari frontend. HARUS dipanggil SERING (disarankan
tiap 1 jam) -- BEDA dari cron_purge_data.py yang bulanan, karena retensi
gambar di sini cuma 24 jam (lihat live_chat_db.py -- jam dihitung SEJAK
dibuka_di_rivoir_at, bukan sejak dibuat, jadi keterlambatan menjalankan
cron ini TIDAK menghapus apa pun sebelum waktunya, cuma menunda hapusnya).

Dilindungi kunci rahasia TERPISAH (env var CRON_LIVE_CHAT_PURGE_SECRET,
diisi manual lewat dashboard Render, TIDAK PERNAH ikut git) dikirim layanan
penjadwal lewat header `X-Cron-Secret` -- secret BERBEDA dari 2 cron lain
supaya kompromi salah satu endpoint tidak otomatis membuka yang lain.
Fail-CLOSED kalau env var ini belum diisi SAMA SEKALI."""

import logging
import os

from fastapi import APIRouter, Header, HTTPException

import live_chat_db

logger = logging.getLogger("mugen.cron_live_chat_purge")

router = APIRouter(prefix="/api/cron", tags=["cron"])

_SECRET = os.environ.get("CRON_LIVE_CHAT_PURGE_SECRET", "").strip()


@router.post("/live-chat-purge")
def pemicu_pembersihan_live_chat(x_cron_secret: str | None = Header(default=None)):
    if not _SECRET or x_cron_secret != _SECRET:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        return live_chat_db.hapus_kedaluwarsa()
    except Exception as e:
        logger.error("Retensi Otomatis Live Chat GAGAL: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Pembersihan gagal, lihat log server.")
