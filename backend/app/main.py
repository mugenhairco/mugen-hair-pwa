"""
main.py — Entry point backend PWA MUGEN Hair Co.

TAHAP 3-7: login & hak akses, router Dashboard (Owner + Barber), Input Data,
dan Rekap sudah terpasang.
TAHAP 9: routers/pengeluaran.py (CRUD Pengeluaran, khusus admin) terpasang.
TAHAP 10: routers/pengaturan.py (Setting — identitas, komisi, barber,
layanan, user, backup) terpasang.
TAHAP 11: routers/produk.py (Persediaan — restock/jual/riwayat mutasi,
khusus admin) terpasang. Router & halaman frontend-nya sudah disiapkan sejak
Tahap 10 tapi belum dihubungkan; Tahap 11 menghubungkannya.
TAHAP 12: routers/sync.py (Status Sinkronisasi Google Sheets, khusus admin)
terpasang + loop retry sinkron otomatis di background (lihat sync_helper.py).

BUGFIX startup lokal (`uvicorn app.main:app`): seluruh modul di folder ini
(database.py, auth.py, auth_db.py, routers/, dst) memakai import "flat"
(`import database`, bukan `from . import database`), yang hanya berfungsi
kalau folder file ini sendiri (backend/app/) ada di sys.path. `app/__init__.py`
sudah menambahkan folder itu ke sys.path begitu paket `app` diimpor -- baris
di bawah ini MENGULANGI hal yang sama secara mandiri, langsung di baris
paling atas file ini (sebelum `import database` dkk di bawah), supaya tidak
bergantung sama sekali pada urutan/mekanisme import package Python maupun
cara proses child di-spawn ulang oleh `--reload` (beberapa platform, mis.
Windows, memakai metode 'spawn' untuk proses reload yang tidak selalu
mewarisi state se-transparan 'fork' di Linux/Mac) -- aman dipanggil
berkali-kali (idempotent, lihat `if ... not in sys.path`), dan TIDAK
mengubah satu pun logika bisnis/import module lain."""

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import database as db
import auth_db
import sync_helper
from pengeluaran_migrasi import migrasi_pengeluaran
from pengaturan_migrasi import migrasi_pengaturan
from sync_migrasi import migrasi_sync
from routers import auth_router, dashboard, input_data, rekap, pengeluaran, pengaturan, produk, sync

app = FastAPI(title="MUGEN Hair Co. API")

# CORS: daftar origin frontend yang boleh memanggil API ini, dipisah koma di
# environment variable ALLOWED_ORIGINS (diisi saat deploy, lihat render.yaml).
# Default di bawah ini untuk development lokal supaya tidak perlu setting apapun dulu.
_default_origins = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,http://localhost:8000"
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(input_data.router)
app.include_router(rekap.router)
app.include_router(pengeluaran.router)
app.include_router(pengaturan.router)
app.include_router(produk.router)
app.include_router(sync.router)


@app.on_event("startup")
def on_startup():
    # init_db() dari database.py: CREATE TABLE IF NOT EXISTS — sama seperti saat
    # main.py Tkinter dijalankan, tidak pernah menimpa data yang sudah ada.
    db.init_db()
    auth_db.init_auth_db()
    migrasi_pengeluaran()  # TAHAP 9: tambah kolom kategori/barber_id/aktif ke tabel pengeluaran (idempotent)
    migrasi_pengaturan()   # TAHAP 10: kolom modal di services + seed setting identitas (idempotent)
    migrasi_sync()         # TAHAP 12: tabel sync_meta (status sinkronisasi, idempotent)
    _bootstrap_admin_pertama()
    _reset_admin_darurat()
    sync_helper.start_background_retry_loop()  # TAHAP 12: retry sinkron otomatis berkala


def _bootstrap_admin_pertama():
    """Kalau tabel users masih benar-benar kosong (instalasi baru), buatkan
    SATU akun admin dari environment variable, supaya ada cara login pertama
    kali tanpa akses langsung ke database (ayam-telur: tanpa user tidak bisa
    login, tanpa login tidak bisa membuat user). Hanya jalan kalau users
    kosong — tidak akan pernah menimpa/duplikat akun yang sudah dibuat manual."""
    if auth_db.get_user_list():
        return
    username = os.environ.get("ADMIN_BOOTSTRAP_USERNAME", "owner")
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "ganti-password-ini")
    auth_db.tambah_user(username=username, password=password, role="admin")


def _reset_admin_darurat():
    """'Break-glass' pemulihan akses admin untuk server yang SUDAH berjalan
    (beda dengan _bootstrap_admin_pertama() di atas, yang hanya jalan kalau
    users benar-benar kosong). Dipakai kalau admin lupa username/password di
    production dan tidak ada cara lain masuk (chicken-and-egg: reset password
    lewat menu Setting butuh sudah login sebagai admin).

    HANYA berjalan kalau DUA environment variable di bawah diisi eksplisit
    oleh operator (mis. lewat dashboard Render) -- default keduanya kosong,
    jadi fungsi ini no-op total di semua deployment lain, TIDAK PERNAH
    otomatis/diam-diam mengubah akun siapa pun:
    - ADMIN_RESET_USERNAME
    - ADMIN_RESET_PASSWORD

    Kalau username itu sudah ada, password-nya di-reset (+ dipaksa jadi role
    admin & diaktifkan lagi kalau sempat nonaktif). Kalau belum ada, dibuat
    baru sebagai admin. Baris user lain dan seluruh tabel bisnis lain TIDAK
    disentuh sama sekali (lihat auth_db.reset_atau_buat_admin_darurat()).

    PENTING (dicetak juga saat startup): setelah berhasil login, SEGERA
    hapus kedua environment variable ini dari server lalu ganti password
    lewat menu Setting > User -- kalau dibiarkan, TIAP KALI server restart
    akan mereset ulang ke password yang sama."""
    username = os.environ.get("ADMIN_RESET_USERNAME", "").strip()
    password = os.environ.get("ADMIN_RESET_PASSWORD", "")
    if not username or not password:
        return
    hasil = auth_db.reset_atau_buat_admin_darurat(username, password)
    print(
        f"[ADMIN_RESET] Akun admin '{username}' berhasil {hasil}. "
        "SEGERA hapus environment variable ADMIN_RESET_USERNAME dan "
        "ADMIN_RESET_PASSWORD dari server, lalu ganti password lewat menu "
        "Setting > User setelah berhasil login -- kalau dibiarkan, restart "
        "berikutnya akan mereset ulang ke password yang sama."
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}
