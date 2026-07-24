"""app/__init__.py — bugfix startup lokal (`uvicorn app.main:app`).

Seluruh modul di paket ini (main.py, database.py, auth.py, routers/, dst)
memakai import "flat" (mis. `import database`, `from routers import
auth_router`) sejak Tahap 1, BUKAN relative import paket (`from . import
database`). Itu TIDAK diubah di sini — mengedit puluhan baris import di
banyak file sekaligus untuk sekadar mengubah cara menjalankan backend
adalah risiko regresi yang tidak sepadan.

Import flat itu selama ini berfungsi karena dijalankan dengan
`cd backend/app && uvicorn main:app`, yang otomatis menambahkan folder
backend/app/ ke sys.path. Kalau backend dijalankan dari folder backend/
dengan `uvicorn app.main:app`, folder yang otomatis masuk sys.path adalah
backend/ (bukan backend/app/), sehingga `import database` gagal
(`ModuleNotFoundError: No module named 'database'`).

Baris di bawah ini menambahkan folder file ini sendiri (backend/app/) ke
sys.path begitu paket `app` diimpor, supaya import flat di atas tetap
berfungsi tanpa diubah — KEDUA cara menjalankan backend (dari backend/app/
ATAU dari backend/) sama-sama berfungsi setelah ini."""

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
