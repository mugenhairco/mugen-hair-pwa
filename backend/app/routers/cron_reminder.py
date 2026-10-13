"""routers/cron_reminder.py — Endpoint pemicu EKSTERNAL untuk Reminder Absensi
=============================================================================
SATU-SATUNYA endpoint di sini SENGAJA TIDAK memakai sesi login/tenant sama
sekali -- dipanggil layanan penjadwal GRATIS dari LUAR aplikasi (mis.
cron-job.org) setiap beberapa menit, BUKAN dari frontend. Lihat catatan
lengkap kenapa pemicu berbasis waktu ini TIDAK dijalankan sebagai proses
latar belakang di dalam aplikasi sendiri di absensi_reminder_db.py.

Dilindungi kunci rahasia (env var CRON_REMINDER_SECRET, diisi manual lewat
dashboard Render, TIDAK PERNAH ikut git -- pola SAMA seperti SECRET_KEY)
dikirim layanan penjadwal lewat header `X-Cron-Secret`. Fail-CLOSED kalau
env var ini belum diisi SAMA SEKALI (menolak SEMUA permintaan, BUKAN
menyala tanpa proteksi) -- pola sama seperti push_service.IS_ENABLED/
whatsapp_service.is_enabled() di modul lain."""

import logging
import os

from fastapi import APIRouter, Header, HTTPException

import absensi_reminder_db

logger = logging.getLogger("mugen.cron_reminder")

router = APIRouter(prefix="/api/cron", tags=["cron"])

_SECRET = os.environ.get("CRON_REMINDER_SECRET", "").strip()


@router.post("/absensi-reminder")
def pemicu_absensi_reminder(x_cron_secret: str | None = Header(default=None)):
    if not _SECRET or x_cron_secret != _SECRET:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        return absensi_reminder_db.jalankan_pengecekan()
    except Exception as e:
        logger.error("Pengecekan Reminder Absensi GAGAL: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Pengecekan gagal, lihat log server.")
