"""
main.py — Entry point backend PWA MUGEN Hair Co.

TAHAP 3-7: login & hak akses, router Dashboard (Owner + Barber), Input Data,
dan Rekap sudah terpasang. Endpoint Produk / Pengeluaran(CRUD) / Setting
menyusul di tahap berikutnya (belum ada router-nya di folder routers/ saat ini
— Rekap Pengeluaran (baca saja) sudah ada, CRUD-nya belum).
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import database as db
import auth_db
from routers import auth_router, dashboard, input_data, rekap

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


@app.on_event("startup")
def on_startup():
    # init_db() dari database.py: CREATE TABLE IF NOT EXISTS — sama seperti saat
    # main.py Tkinter dijalankan, tidak pernah menimpa data yang sudah ada.
    db.init_db()
    auth_db.init_auth_db()
    _bootstrap_admin_pertama()


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


@app.get("/api/health")
def health():
    return {"status": "ok"}
