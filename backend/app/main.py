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

import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import database as db
import auth_db
import sync_helper
from auth import require_admin
from pengeluaran_migrasi import migrasi_pengeluaran
from pengaturan_migrasi import migrasi_pengaturan
from sync_migrasi import migrasi_sync
from revisi_bonus_migrasi import migrasi_revisi_bonus
from booking_migrasi import migrasi_booking
from booking_form_migrasi import migrasi_booking_form
from produk_migrasi import migrasi_produk
from bonus_service_migrasi import migrasi_bonus_service
from tampilan_migrasi import migrasi_tampilan
from revisi_setting_migrasi import migrasi_revisi_setting
import booking_db
from routers import auth_router, dashboard, input_data, rekap, pengeluaran, pengaturan, produk, sync, booking

app = FastAPI(title="MUGEN Hair Co. API")

# AUDIT SINKRONISASI: logging terstruktur ke stdout (Render/hosting mana pun
# menangkap stdout sebagai log platform secara otomatis, tidak perlu setup
# tambahan) -- setiap request dicatat method/path/status/durasi (lihat
# middleware _log_dan_no_store di bawah), supaya kalau ada laporan "data
# tidak tersimpan/tidak sinkron" bisa ditelusuri dari log: apakah request-nya
# benar-benar sampai ke server, berhasil, atau gagal (dan kenapa).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("mugen")

# AUDIT SINKRONISASI: identitas proses ini -- kalau backend berjalan lebih
# dari satu instance sekaligus (mis. Render "Number of Instances" > 1),
# masing-masing instance akan punya _INSTANCE_ID dan _BOOT_TIME BERBEDA
# walau kodenya identik, karena keduanya dibuat sekali saat modul ini
# pertama kali diimpor (satu kali per proses). Ini SENGAJA diekspos lewat
# /api/health dan /api/health/diagnostik (lihat di bawah) supaya bisa
# dibandingkan langsung dari dua device: kalau device A dan device B
# melihat _INSTANCE_ID yang BERBEDA padahal memanggil URL backend yang
# SAMA, itu bukti request mereka dilayani oleh proses/database yang
# berbeda (root cause paling umum untuk "kadang sinkron kadang tidak"
# pada arsitektur SQLite berbasis file seperti aplikasi ini -- SQLite
# adalah database FILE TUNGGAL, bukan server terpusat, jadi kalau ada
# lebih dari satu instance/disk yang tidak persisten, masing-masing
# instance punya salinan file .db-nya SENDIRI-SENDIRI).
_INSTANCE_ID = uuid.uuid4().hex[:12]
_BOOT_TIME = datetime.now(timezone.utc)

# CORS: daftar origin frontend yang boleh memanggil API ini, dipisah koma di
# environment variable ALLOWED_ORIGINS (diisi saat deploy).
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


@app.middleware("http")
async def _log_dan_no_store(request: Request, call_next):
    """
    AUDIT SINKRONISASI -- satu middleware, dua tugas:
    1. Cache-Control: no-store di SETIAP respons /api/* -- lapis pertahanan
       tambahan (di luar Service Worker yang sudah membiarkan /api/* lewat
       tanpa disentuh sama sekali, lihat service-worker.js) supaya TIDAK ADA
       cache HTTP di lapisan mana pun (browser, proxy/CDN perantara) yang
       bisa menyajikan balasan API basi -- sebelumnya tidak ada header ini
       sama sekali, jadi murni bergantung pada default browser.
    2. Log method/path/status/durasi/instance_id tiap request -- supaya
       laporan "data tidak tersimpan" bisa dicek langsung dari log: apakah
       request Simpan/Edit/Hapus itu benar-benar sampai, berhasil (2xx),
       atau gagal (4xx/5xx) beserta durasinya (durasi tinggi bisa jadi
       tanda kontensi lock database, lihat get_conn() di database.py).
    """
    mulai = time.monotonic()
    response = await call_next(request)
    durasi_ms = round((time.monotonic() - mulai) * 1000, 1)

    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"

    if request.url.path.startswith("/api/"):
        level = logging.INFO if response.status_code < 400 else logging.WARNING
        logger.log(
            level,
            "[%s] %s %s -> %s (%sms)",
            _INSTANCE_ID, request.method, request.url.path, response.status_code, durasi_ms,
        )
    return response


app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(input_data.router)
app.include_router(rekap.router)
app.include_router(pengeluaran.router)
app.include_router(pengaturan.router)
app.include_router(produk.router)
app.include_router(sync.router)
app.include_router(booking.router)
app.include_router(booking.public_router)


@app.on_event("startup")
def on_startup():
    # init_db() dari database.py: CREATE TABLE IF NOT EXISTS — sama seperti saat
    # main.py Tkinter dijalankan, tidak pernah menimpa data yang sudah ada.
    db.init_db()
    auth_db.init_auth_db()
    booking_db.init_booking_db()  # BOOKING: tabel bookings/booking_items/closed_slot (idempotent)
    migrasi_pengeluaran()  # TAHAP 9: tambah kolom kategori/barber_id/aktif ke tabel pengeluaran (idempotent)
    migrasi_pengaturan()   # TAHAP 10: kolom modal di services + seed setting identitas (idempotent)
    migrasi_sync()         # TAHAP 12: tabel sync_meta (status sinkronisasi, idempotent)
    migrasi_revisi_bonus() # REVISI: kolom uang_harian per-barber + seed tier bonus (idempotent)
    migrasi_booking()      # BOOKING: kolom durasi_menit di services + seed setting booking (idempotent)
    migrasi_booking_form() # PENYEMPURNAAN FORM BOOKING: status_booking/foto/urutan barber, urutan service (idempotent)
    migrasi_produk()        # REVISI: harga_modal/harga_jual produk + snapshot harga di produk_mutasi (idempotent)
    migrasi_bonus_service() # REVISI: seed Setting Bonus Service & Setting Uang Harian dari hardcode lama (idempotent)
    migrasi_tampilan()      # REVISI UI/UX: kolom users.tema untuk Dark/Light Mode per akun (idempotent)
    migrasi_revisi_setting()  # REVISI Setting: target Uang Harian bisa diatur + Harga Modal per-service (idempotent)
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
    """
    AUDIT SINKRONISASI: diperluas dari sebelumnya cuma {"status":"ok"} --
    sekarang menyertakan _INSTANCE_ID (dibuat sekali per proses, lihat
    komentar di atas) dan waktu proses ini mulai berjalan (boot_time) +
    umurnya (uptime_detik). TIDAK butuh login (sengaja tetap publik seperti
    sebelumnya, sekadar info teknis non-sensitif) -- cara termudah membuktikan
    dari DUA DEVICE APAKAH keduanya sedang bicara dengan proses backend yang
    SAMA: buka endpoint ini dari device A dan device B secara bersamaan,
    kalau instance_id berbeda berarti ada lebih dari satu instance backend
    berjalan (mis. Render "Number of Instances" > 1) -- masing-masing
    instance SQLite berbasis file ini punya salinan database SENDIRI-SENDIRI,
    itulah salah satu penyebab utama data "kadang sinkron kadang tidak".
    Kalau boot_time berubah setiap dicek ulang (proses baru saja restart)
    padahal tidak ada deploy baru yang disengaja, itu tanda disk TIDAK
    persisten (lihat README bagian Deployment) -- data ditulis ulang ke
    default setiap restart.
    """
    uptime = (datetime.now(timezone.utc) - _BOOT_TIME).total_seconds()
    return {
        "status": "ok",
        "instance_id": _INSTANCE_ID,
        "boot_time": _BOOT_TIME.isoformat(),
        "uptime_detik": round(uptime, 1),
    }


@app.get("/api/health/diagnostik")
def health_diagnostik(user: dict = Depends(require_admin)):
    """
    AUDIT SINKRONISASI: versi lengkap /api/health, KHUSUS admin (menyertakan
    info lebih rinci tentang file database itu sendiri -- bukan data bisnis,
    tapi tetap dibatasi ke admin sebagai kebiasaan aman). Dipakai untuk
    membuktikan langsung dari Setting/DevTools di dua device:
    - db_path / db_size_bytes / db_mtime: kalau db_mtime jauh lebih baru
      dari kapan terakhir kali ada yang menyimpan data (mis. baru saja,
      padahal tidak ada yang menekan Simpan), itu tanda proses baru saja
      restart dan menulis ulang file database dari awal (disk tidak
      persisten).
    - jumlah_baris: hitungan baris tabel-tabel inti -- device A dan device B
      HARUS melihat angka yang SAMA PERSIS kalau memang sinkron dengan
      benar (satu database yang sama). Kalau berbeda, itu bukti langsung
      kedua device sedang bicara dengan salinan database yang berbeda.
    """
    db_stat = os.stat(db.DB_PATH) if os.path.exists(db.DB_PATH) else None
    with db.get_conn() as conn:
        jumlah_baris = {
            "users": conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"],
            "barbers": conn.execute("SELECT COUNT(*) AS n FROM barbers").fetchone()["n"],
            "transaksi": conn.execute("SELECT COUNT(*) AS n FROM transaksi").fetchone()["n"],
            "bookings": conn.execute("SELECT COUNT(*) AS n FROM bookings").fetchone()["n"],
        }
    return {
        "instance_id": _INSTANCE_ID,
        "boot_time": _BOOT_TIME.isoformat(),
        "uptime_detik": round((datetime.now(timezone.utc) - _BOOT_TIME).total_seconds(), 1),
        "db_path": db.DB_PATH,
        "db_size_bytes": db_stat.st_size if db_stat else None,
        "db_mtime": datetime.fromtimestamp(db_stat.st_mtime, tz=timezone.utc).isoformat() if db_stat else None,
        "jumlah_baris": jumlah_baris,
    }
