"""e2e_server.py — Bootstrap backend untuk suite E2E Playwright
(frontend/playwright.config.js, frontend/e2e/*.spec.js).

Menjalankan FastAPI di atas database SQLite throwaway (BUKAN database
development lokal, BUKAN production) yang sudah diisi fixture awal (Owner,
Barber, Service, Payment Method, Pengaturan Absensi, beberapa booking)
supaya skenario E2E (login, tab Booking, Check In/Out) punya data yang
konsisten dan bisa diprediksi -- tidak bergantung pada data yang kebetulan
ada di database siapa pun yang menjalankannya.

Jalankan manual (dari folder backend/):
    python3 e2e_server.py
Port: 8031 (HARUS SAMA dengan port yang dipanggil frontend/playwright.config.js
lewat fixture route interception di frontend/e2e/fixtures.js)."""

import asyncio
import datetime
import os
import sys
from zoneinfo import ZoneInfo

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
sys.path.insert(0, APP_DIR)

TEST_DB = os.environ.get("E2E_DB_PATH", "/tmp/mugen_e2e.db")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

import database
import auth_db

database.DB_PATH = TEST_DB
auth_db.DB_PATH = TEST_DB

os.environ.setdefault("ADMIN_BOOTSTRAP_USERNAME", "e2eowner")
os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "e2eowner12345")

import main  # noqa: E402  -- membuat objek app (belum memicu startup)
import tenant_db  # noqa: E402
import booking_db  # noqa: E402
import attendance_db  # noqa: E402
import error_log_db  # noqa: E402
import billing_db  # noqa: E402
import subscription_db  # noqa: E402


# BUGFIX (CI E2E gagal sejak "on_event" dipindah ke "async def"): on_startup()
# di main.py adalah coroutine (@app.on_event("startup") async def on_startup()),
# memanggilnya langsung tanpa asyncio.run() cuma membuat objek coroutine yang
# TIDAK PERNAH benar-benar dijalankan -- migrasi (bikin tabel `tenants`, dst)
# diam-diam tidak pernah terjadi, lalu baris di bawah crash "no such table:
# tenants". asyncio.run() memastikan coroutine-nya SELESAI dijalankan sebelum
# seeding di bawah mulai.
asyncio.run(main.on_startup())  # jalankan migrasi + bootstrap Owner SEBELUM seeding di bawah

tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
TENANT_ID = tenant["id"]

# Feature Gating per Paket (feature_access.py): tenant E2E TIDAK PERNAH punya
# baris tenant_subscriptions kalau tidak dibuat eksplisit di sini -- fail-
# CLOSED berarti setiap endpoint yang digerbang require_feature() (termasuk
# GET /api/log-error, lihat routers/error_log.py) akan 403 tanpa ini, membuat
# frontend/e2e/log_error.spec.js gagal (tab-nya jadi blok upgrade, bukan
# tabel log). Paket "free" sudah otomatis dapat booking_online/export_pdf
# lewat billing_db.seed_default_package_features() (dipanggil
# main.on_startup() di atas) -- "log_error" ditambahkan manual di sini
# (BUKAN bagian _FITUR_NYATA_DEFAULT, lihat catatan billing_db.py) supaya
# tab Log Error tetap testable E2E. "barber_app"/"absensi" (FITUR Feature
# Gating lanjutan, TIDAK ADA grandfather sama sekali, lihat billing_db.py)
# ditambahkan dengan alasan SAMA PERSIS -- tanpa ini, login akun barber
# E2E (absensi.spec.js/booking-barber.spec.js/login.spec.js) & seluruh
# endpoint /api/attendance/* akan 403 duluan.
subscription_db.create_default_subscription(TENANT_ID, package="free", status="active")
_paket_free = billing_db.get_package_by_kode("free")
_kode_fitur_e2e = ("log_error", "barber_app", "absensi")
if _paket_free is not None:
    _fitur_ids = {billing_db.get_feature_by_kode(k)["id"] for k in _kode_fitur_e2e if billing_db.get_feature_by_kode(k)}
    _fitur_sudah_ada = {f["id"] for f in billing_db.get_package_features(_paket_free["id"])}
    billing_db.set_package_features(_paket_free["id"], list(_fitur_sudah_ada | _fitur_ids))

BARBER_ID = database.add_barber("E2E Barber", tenant_id=TENANT_ID)
SERVICE_ID = database.add_service("E2E Haircut", 50000, tenant_id=TENANT_ID)
booking_db.update_payment_settings(metode_aktif=["transfer"], tenant_id=TENANT_ID)
auth_db.tambah_user("e2ebarber", "e2epassword123", role="barber", barber_id=BARBER_ID, tenant_id=TENANT_ID)

# Pengaturan Absensi: lokasi toko di Monas Jakarta (titik yang SAMA dipakai
# backend/tests/test_attendance.py) -- frontend/e2e/absensi.spec.js
# me-mock geolocation browser ke titik yang SAMA PERSIS. Jam masuk/pulang
# dibuka lebar (00:00-23:59) supaya tes tidak flaky tergantung jam CI jalan.
attendance_db.set_settings(
    TENANT_ID, jam_masuk="00:00", toleransi_menit=999, jam_pulang="23:59",
    radius_meter=500, lokasi_nama="Toko E2E",
    lokasi_latitude=-6.175392, lokasi_longitude=106.827153,
)

# Booking fixture -- regression-lock BUG tanggal tercampur di tab "Hari
# Ini"/"Akan Datang" (lihat PR #142): satu booking masa depan ASLI (harus
# muncul di "Akan Datang"), satu booking yang "sudah lewat" (dibuat valid
# di masa depan lalu di-patch mundur -- buat_booking() tidak mengizinkan
# tanggal masa lalu langsung, persis skenario nyata booking yang valid
# saat dibuat lalu waktu berjalan lewat) -- HARUS TIDAK PERNAH muncul di
# tab "Hari Ini" maupun "Akan Datang".
_now = datetime.datetime.now(ZoneInfo("Asia/Jakarta"))
_masa_depan_iso = (_now.date() + datetime.timedelta(days=5)).isoformat()
_kemarin_iso = (_now.date() - datetime.timedelta(days=1)).isoformat()

booking_db.buat_booking(
    barber_id=BARBER_ID, tanggal=_masa_depan_iso, jam_mulai="10:00", service_ids=[SERVICE_ID],
    customer_nama="E2E Customer Masa Depan", customer_whatsapp="081234567890",
    metode_pembayaran="transfer", tenant_id=TENANT_ID,
)
booking_db.buat_booking(
    barber_id=BARBER_ID, tanggal=_masa_depan_iso, jam_mulai="11:00", service_ids=[SERVICE_ID],
    customer_nama="E2E Customer Sudah Lewat", customer_whatsapp="081234567890",
    metode_pembayaran="transfer", tenant_id=TENANT_ID,
)
with database.get_conn() as conn:
    conn.execute(
        "UPDATE bookings SET tanggal = ? WHERE customer_nama = 'E2E Customer Sudah Lewat'",
        (_kemarin_iso,),
    )

# DIY error monitoring (bukan Sentry) -- satu baris seed supaya
# frontend/e2e/log_error.spec.js punya sesuatu untuk diverifikasi tampil di
# Setting > Log Error TANPA harus benar-benar memicu error sungguhan lewat
# browser.
error_log_db.catat_error(
    sumber="backend", pesan="Contoh error seed E2E: ValueError contoh",
    detail="Traceback (most recent call last):\n  File \"contoh.py\", line 1, in <module>\nValueError: contoh error seed E2E",
    url="/api/contoh-endpoint", tenant_id=TENANT_ID,
)

print(f"[e2e_server] Seed selesai -- tenant_id={TENANT_ID} barber_id={BARBER_ID} "
      f"service_id={SERVICE_ID} db={TEST_DB}", flush=True)

import uvicorn  # noqa: E402

uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ.get("E2E_PORT", "8031")), log_level="warning")
