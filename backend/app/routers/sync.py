"""routers/sync.py — /api/sync/*  (TAHAP 12)

Halaman "Status Sinkronisasi" -- KHUSUS Owner (admin), pola sama seperti
Pengeluaran/Produk/Setting: ini status operasional TOKO (satu database,
satu tujuan sinkron untuk semua), bukan data milik barber manapun.

Backup/Restore Database SENGAJA TIDAK dibuat ulang di sini -- endpoint
/api/pengaturan/backup/export & /import sudah ada sejak Tahap 10 (lihat
routers/pengaturan.py) dan TIDAK disentuh sama sekali di Tahap 12 supaya
logika backup/restore hanya ada di SATU tempat. Halaman Sinkronisasi di
frontend hanya menambahkan menu/tombol yang memanggil endpoint yang sama
itu (lihat frontend/js/pages/sinkronisasi.js)."""

from fastapi import APIRouter, Depends

import sync_helper
from auth import require_admin

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status")
def status(user: dict = Depends(require_admin)):
    return sync_helper.get_status()


@router.post("/sekarang")
def sinkron_sekarang(user: dict = Depends(require_admin)):
    return sync_helper.sync_now()
