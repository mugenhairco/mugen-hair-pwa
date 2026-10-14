"""routers/migrasi_foto_barber.py — Endpoint SEKALI-PAKAI untuk menjalankan
perkecil_foto_barber_lama.py::jalankan_migrasi() di DALAM proses backend
production (satu-satunya tempat yang sudah punya DATABASE_URL/R2_*
production siap pakai, lihat catatan lengkap di file itu)
=============================================================================
File ini SENGAJA TEMPORARY -- dihapus lagi (beserta baris pendaftarannya
di main.py) setelah migrasi foto barber lama selesai dijalankan SEKALI,
BUKAN fitur permanen. Dilindungi SECRET YANG SUDAH ADA (CRON_REMINDER_SECRET,
reuse -- lihat routers/cron_reminder.py, TIDAK perlu env var baru di Render
untuk migrasi sekali-jalan ini) lewat header `X-Cron-Secret`, pola & fail-
closed PERSIS SAMA seperti cron_reminder.py.

--dry-run jadi query param `?dry_run=true` (DEFAULT true -- harus EKSPLISIT
`?dry_run=false` untuk benar-benar menulis, bukan default terbalik yang
rawan salah pakai)."""

import logging
import os

from fastapi import APIRouter, Header, HTTPException

import perkecil_foto_barber_lama

logger = logging.getLogger("mugen.migrasi_foto_barber")

router = APIRouter(prefix="/api/cron", tags=["cron"])

_SECRET = os.environ.get("CRON_REMINDER_SECRET", "").strip()


@router.post("/perkecil-foto-barber-lama")
def pemicu_perkecil_foto_barber_lama(dry_run: bool = True, x_cron_secret: str | None = Header(default=None)):
    if not _SECRET or x_cron_secret != _SECRET:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")
    try:
        return perkecil_foto_barber_lama.jalankan_migrasi(dry_run=dry_run)
    except perkecil_foto_barber_lama.MigrasiTidakDiizinkan as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Migrasi perkecil foto barber lama GAGAL: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Migrasi gagal, lihat log server.")
