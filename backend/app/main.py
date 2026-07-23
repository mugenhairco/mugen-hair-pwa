"""
main.py — Entry point backend PWA MUGEN Hair Co.

TAHAP 1-2 (skeleton): baru menyediakan endpoint diagnosa untuk memverifikasi
database.py (logika bisnis, disalin VERBATIM dari aplikasi Python Desktop)
bisa diakses dengan benar lewat FastAPI, dan hasil hitungnya identik dengan
aplikasi Desktop. Endpoint API sesungguhnya (Dashboard, Input Data, Rekap,
dst) menyusul di tahap berikutnya.
"""

from fastapi import FastAPI

import database as db
import auth_db

app = FastAPI(title="MUGEN Hair Co. API")


@app.on_event("startup")
def on_startup():
    # init_db() dari database.py: CREATE TABLE IF NOT EXISTS — sama seperti saat
    # main.py Tkinter dijalankan, tidak pernah menimpa data yang sudah ada.
    db.init_db()
    auth_db.init_auth_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/_diagnostik/ringkasan")
def _diagnostik_ringkasan(barber_id: int, tahun: int, bulan: int):
    """SEMENTARA, hanya untuk Tahap 1-2: membuktikan get_ringkasan_barber_bulan()
    dari database.py bisa dipanggil apa adanya lewat API dan hasilnya sama persis
    dengan yang dipakai Dashboard di aplikasi Desktop. Endpoint ini akan diganti
    endpoint Dashboard resmi (dengan otentikasi) di Tahap 5."""
    return db.get_ringkasan_barber_bulan(barber_id, tahun, bulan)
