"""routers/cron_purge_data.py — Endpoint pemicu EKSTERNAL untuk Pembersihan
Data Bulanan Otomatis
=============================================================================
SATU-SATUNYA endpoint di sini SENGAJA TIDAK memakai sesi login/tenant sama
sekali -- pola SAMA PERSIS routers/cron_reminder.py, dipanggil layanan
penjadwal GRATIS dari LUAR aplikasi (mis. cron-job.org), BUKAN dari
frontend. Lihat data_purge_db.py untuk logika lengkap & alasan tidak
dijalankan sebagai proses latar belakang di dalam aplikasi sendiri.

Dilindungi kunci rahasia TERPISAH dari Reminder Absensi (env var
CRON_PURGE_SECRET, diisi manual lewat dashboard Render, TIDAK PERNAH ikut
git) dikirim layanan penjadwal lewat header `X-Cron-Secret` -- secret
BERBEDA supaya kompromi salah satu endpoint tidak otomatis membuka yang
lain. Fail-CLOSED kalau env var ini belum diisi SAMA SEKALI."""

import logging
import os

from fastapi import APIRouter, Header, HTTPException

import data_purge_db

logger = logging.getLogger("mugen.cron_purge_data")

router = APIRouter(prefix="/api/cron", tags=["cron"])

_SECRET = os.environ.get("CRON_PURGE_SECRET", "").strip()


@router.post("/purge-data")
def pemicu_pembersihan_data(x_cron_secret: str | None = Header(default=None)):
    if not _SECRET or x_cron_secret != _SECRET:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        return data_purge_db.jalankan_pembersihan()
    except Exception as e:
        logger.error("Pembersihan Data Bulanan Otomatis GAGAL: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Pembersihan gagal, lihat log server.")
