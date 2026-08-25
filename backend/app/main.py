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
REVISI: fitur Sinkronisasi Google Sheets (dulu TAHAP 12) DIHAPUS TOTAL --
PostgreSQL adalah satu-satunya sumber data sejak migrasi Neon selesai,
jadi tidak ada lagi kebutuhan menyalin data ke Google Sheets sebagai
cadangan. routers/sync.py, sync_helper.py, sync_meta_db.py,
google_sheets_client.py, sync_migrasi.py, dan halaman frontend
Sinkronisasi sudah dihapus seluruhnya.

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
import traceback
import uuid
from datetime import datetime, timezone

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

import database as db
import auth_db
import db_compat
from auth import require_admin
from pengeluaran_migrasi import migrasi_pengeluaran
from pengaturan_migrasi import migrasi_pengaturan
from revisi_bonus_migrasi import migrasi_revisi_bonus
from booking_migrasi import migrasi_booking
from booking_form_migrasi import migrasi_booking_form
from booking_verifikasi_migrasi import migrasi_booking_verifikasi
from nomor_transaksi_booking_migrasi import migrasi_nomor_transaksi_booking
from produk_migrasi import migrasi_produk
from bonus_service_migrasi import migrasi_bonus_service
from tampilan_migrasi import migrasi_tampilan
from revisi_setting_migrasi import migrasi_revisi_setting
from karyawan_migrasi import migrasi_karyawan
from email_auth_migrasi import migrasi_email_auth
from r2_storage_migrasi import migrasi_r2_storage
from lokasi_user_migrasi import migrasi_lokasi_user  # FITUR Izin Lokasi APK Android: kolom users.lokasi_lat/lokasi_lng/lokasi_updated_at (idempotent)
import tenant_migrasi
from tenant_migrasi import migrasi_tenant
import tenant_db
from tenant_middleware import TenantResolutionMiddleware
import booking_db
import website_content
import file_asset_db
import r2_storage
import slip_gaji_db
import kasbon_db
import komisi_penyesuaian_db
import reimburse_db
import izin_cuti_db
from izin_cuti_migrasi import migrasi_izin_cuti, seed_konfigurasi_awal_agustus_2026, migrasi_konsolidasi_kuota_gabungan  # REVISI Sistem Dinamis Cuti & Izin: kolom kuota/periode dinamis (idempotent, jalur SQLite) + seed saldo awal Agustus 2026 (portable, kedua jalur DB) + PERBAIKAN Sistem Kuota IZIN & CUTI: lipat mode 'terpisah' lama jadi 'gabungan' (portable, kedua jalur DB)
from auto_libur_db import migrasi_absensi_libur_sumber  # KOREKSI Owner: kolom absensi_libur.sumber (idempotent, jalur SQLite) -- bedakan baris Barber Holiday manual dari yang dibuat Auto-Libur
import pemasukan_db
import uang_kas_db
import data_non_barber_db
import manual_customer_db  # FITUR BARU Manual Customer (Waiting List/Booking): tabel input_data_hari/manual_customer_transaksi/manual_customer_transaksi_service, berdiri sendiri dari transaksi Barber (idempotent)
import superadmin_audit_db
import attendance_db  # Modul BARU Absensi (GPS Check In/Out Geofencing): tabel attendance_settings/attendance_logs/attendance_audit_logs (idempotent, berdiri sendiri)
import uang_harian_dinamis_db  # FITUR Uang Harian Dinamis: tabel uang_harian_dinamis_settings, opt-in per tenant (idempotent)
import push_db  # FITUR Notifikasi Push: tabel push_subscriptions (idempotent, berdiri sendiri)
import error_log_db  # DIY error monitoring (bukan Sentry): tabel error_logs (idempotent, berdiri sendiri)
import user_roles_db  # FITUR Role User Custom: tabel user_roles/user_role_permissions (idempotent, berdiri sendiri)
from user_roles_migrasi import migrasi_user_roles  # FITUR Role User Custom: kolom users.custom_role_id (idempotent)
from subscription_migrasi import migrasi_subscription
import billing_db  # FONDASI Multi-Tenant Phase 4: tabel subscription_packages (idempotent)
import billing_gateway_db  # Payment Gateway Billing SaaS (platform-wide): bootstrap dari env var MIDTRANS_* lama, sekali saja (idempotent)
import billing_invoice_db  # FONDASI Multi-Tenant Phase 4: tabel subscription_invoices + subscription_invoice_status_log (idempotent)
from landing_migrasi import migrasi_landing  # FONDASI Multi-Tenant Phase 5: kolom tenants + tabel landing_faq, drop landing_testimonials (idempotent)
from booking_slug_migrasi import migrasi_booking_slug  # FITUR URL Booking Publik per Tenant: kolom tenants.booking_slug + backfill tenant lama (idempotent, WAJIB setelah migrasi_tenant())
from booking_gateway_migrasi import migrasi_booking_gateway  # Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: tabel booking_payment_transactions/booking_payment_status_log (idempotent)
from faspay_settlement_migrasi import migrasi_faspay_settlement  # Settlement Faspay per Terminal (Tenant): tabel faspay_settlements/faspay_settlement_items (idempotent)
from snap_payment_migrasi import migrasi_snap_payment  # Migrasi Faspay SNAP Advance: tabel snap_payment_transactions/snap_payment_status_log TERPADU Booking+SaaS Billing (idempotent)
from routers import auth_router, dashboard, input_data, rekap, pengeluaran, pengaturan, produk, booking, website, slip_gaji, kasbon, komisi, reimburse, izin_cuti, pemasukan, uang_kas, data_non_barber, manual_customer, superadmin, branding, subscription, billing, billing_webhook, landing, tenant_registration, payment_gateway, booking_gateway_webhook, transaction_report, gateway_notification, attendance, uang_harian_dinamis, push, error_log, snap_advance, faspay_settlement, faspay_settlement_superadmin

app = FastAPI(title="Rivoir API", version="1.0.0")

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
# environment variable ALLOWED_ORIGINS (diisi saat deploy) -- SATU-SATUNYA
# cara utama mengizinkan origin custom, termasuk domain produksi sendiri.
# BUGFIX: default sebelumnya HANYA localhost -- kalau ALLOWED_ORIGINS lupa
# diisi/salah isi di dashboard hosting, permintaan dari frontend production
# ditolak total. Default di bawah menyertakan domain produksi yang diketahui
# SEBAGAI CADANGAN (bukan pengganti env var, tetap override lewat
# ALLOWED_ORIGINS kalau domain berubah/bertambah). Aman menyertakan origin
# spesifik (bukan wildcard) karena autentikasi aplikasi ini murni header
# "Authorization: Bearer <token>" yang disisipkan manual oleh JS (lihat
# frontend/js/api.js) -- BUKAN cookie -- jadi allow_credentials=True di sini
# tidak membuka celah pencurian sesi lintas origin seperti kalau aplikasi
# memakai cookie.
#
# ARSITEKTUR DUA SERVICE RENDER (render.yaml di root repo): backend ini
# (Web Service, https://api.rivoirsett.com) dan frontend (Static Site,
# https://rivoirsett.com -- Landing Page "/" + Dashboard PWA "/app/") adalah
# DUA service TERPISAH dengan URL BERBEDA. Kalau domain produksi berubah lagi
# di masa depan, cukup update daftar di bawah (dan/atau env var
# ALLOWED_ORIGINS di dashboard Render) -- tidak ada tempat lain yang perlu
# disentuh.
_default_origins = (
    "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,http://localhost:8000,"
    "https://rivoirsett.com,https://www.rivoirsett.com,https://mugen.rivoirsett.com"
)
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]

# BUGFIX CORS Multi-Tenant: SaaS ini punya SATU subdomain per tenant
# (mis. mugen.rivoirsett.com, tenant1.rivoirsett.com, dst) -- daftar
# ALLOWED_ORIGINS di atas (exact-match per origin) TIDAK BISA mengikuti
# tenant baru yang dibuat lewat registrasi mandiri/Super Admin TANPA
# menambah entry manual satu-satu tiap kali ada tenant baru, yang gampang
# ketinggalan dan menyebabkan login gagal dengan CORS error persis seperti
# laporan ini. allow_origin_regex (didukung Starlette CORSMiddleware,
# dicek TERPISAH dari allow_origins -- origin lolos kalau cocok SALAH SATU
# dari keduanya) mengizinkan SELURUH subdomain *.rivoirsett.com (termasuk
# root rivoirsett.com & www) sekali jalan, otomatis ikut tenant baru
# mana pun ke depannya, TANPA membuka akses ke domain lain di luar
# rivoirsett.com -- pola ini AMAN dipakai bersama allow_credentials=True
# karena Starlette selalu mengembalikan origin SPESIFIK yang cocok pada
# header Access-Control-Allow-Origin (bukan literal "*"), sesuai standar
# Fetch/CORS (browser MENOLAK "*" di header itu kalau request memakai
# credentials). Boleh dioverride lewat env var ALLOWED_ORIGIN_REGEX kalau
# domain produksi berubah di masa depan (satu-satunya tempat yang perlu
# disentuh, sama seperti pola ALLOWED_ORIGINS di atas).
ALLOWED_ORIGIN_REGEX = os.environ.get(
    "ALLOWED_ORIGIN_REGEX",
    r"^https://([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*rivoirsett\.com$",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Domain lama Render (*.onrender.com) -> domain produksi: permanent redirect
# HTTP 308 (bukan 301/302 -- 308 SATU-SATUNYA kode redirect yang menjamin
# method+body request tetap dipertahankan persis, penting karena endpoint di
# aplikasi ini banyak yang POST/PUT/DELETE, bukan cuma GET). Render TIDAK
# punya redirect otomatis berbasis Host header di level platform untuk Web
# Service (hanya bisa "Disable" total = 404, lihat README > Deployment >
# Render) -- middleware ini SATU-SATUNYA cara mendapat redirect sungguhan.
# `request.headers.get("host")` sudah TERBUKTI diteruskan apa adanya oleh
# Render (tenant_middleware.py sudah bergantung padanya sejak Phase 2.0),
# jadi aman dipakai sebagai sumber kebenaran domain yang sedang diakses.
_OLD_BACKEND_HOST = "mugen-hair-api.onrender.com"
_NEW_BACKEND_ORIGIN = "https://api.rivoirsett.com"


@app.middleware("http")
async def _redirect_domain_lama(request: Request, call_next):
    host = request.headers.get("host", "").split(":", 1)[0].lower()
    if host == _OLD_BACKEND_HOST:
        target = _NEW_BACKEND_ORIGIN + request.url.path
        if request.url.query:
            target += "?" + request.url.query
        return RedirectResponse(target, status_code=308)
    return await call_next(request)


# FONDASI Multi-Tenant Phase 2.0: resolusi tenant per-request di SATU
# tempat (lihat tenant_middleware.py) -- request.state.requested_tenant_slug
# dipakai auth.resolve_tenant_publik()/resolve_tenant_hibrid() dan
# routers/auth_router.py::login() sebagai sumber slug SELAIN query string
# `?tenant=` (yang tetap prioritas utama, perilaku Phase 1 tidak berubah).
app.add_middleware(TenantResolutionMiddleware)


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


@app.exception_handler(Exception)
async def _tangani_exception_global(request: Request, exc: Exception):
    """DIY error monitoring (bukan Sentry, lihat error_log_db.py untuk latar
    belakang). SEBELUM handler ini ada, exception tak tertangani HANYA
    tercatat ke stdout (logger.critical di bawah, TETAP dipertahankan) --
    Owner/dev harus buka log Render manual untuk tahu ada masalah. Sekarang
    JUGA tersimpan ke tabel error_logs supaya kelihatan lewat Setting > Log
    Error tanpa akses Render sama sekali. HANYA menangkap exception yang
    BENAR-BENAR tak terduga (bug) -- HTTPException/RequestValidationError
    yang sengaja dilempar endpoint (404/422/dst di seluruh routers/*.py)
    TETAP ditangani handler bawaan FastAPI seperti biasa (lebih spesifik,
    tidak lewat sini sama sekali), respons API normal untuk itu TIDAK
    berubah.

    tenant_id SELALU None di sini -- exception handler global tidak
    dijalankan lewat dependency injection endpoint (mis. get_current_user),
    jadi tidak tahu request ini punya sesi tenant yang mana tanpa
    mendekode header Authorization manual. Pencatatan ke error_logs
    best-effort MURNI (try/except telan diam-diam) -- exception SEKUNDER di
    sini TIDAK BOLEH menggagalkan respons 500 yang harus tetap terkirim ke
    client."""
    logger.critical(
        "[%s] Unhandled exception %s %s: %s",
        _INSTANCE_ID, request.method, request.url.path, exc, exc_info=True,
    )
    try:
        error_log_db.catat_error(
            sumber="backend", pesan=f"{exc.__class__.__name__}: {exc}",
            detail=traceback.format_exc(), url=str(request.url),
        )
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"detail": "Terjadi kesalahan pada server."})


app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(input_data.router)
app.include_router(rekap.router)
app.include_router(pengeluaran.router)
app.include_router(pengaturan.router)
app.include_router(produk.router)
app.include_router(booking.router)
app.include_router(booking.public_router)
app.include_router(website.router)
app.include_router(slip_gaji.router)
app.include_router(kasbon.router)
app.include_router(komisi.router)
app.include_router(reimburse.router)
app.include_router(izin_cuti.router)
app.include_router(pemasukan.router)
app.include_router(uang_kas.router)
app.include_router(data_non_barber.router)
app.include_router(manual_customer.router)
app.include_router(superadmin.router)
app.include_router(branding.router)
app.include_router(subscription.router)
app.include_router(subscription.superadmin_router)
app.include_router(billing.router)
app.include_router(billing.superadmin_router)
app.include_router(billing_webhook.public_router)
app.include_router(landing.public_router)
app.include_router(landing.router)
app.include_router(tenant_registration.public_router)
app.include_router(payment_gateway.router)
app.include_router(booking_gateway_webhook.public_router)
app.include_router(transaction_report.router)
app.include_router(gateway_notification.public_router)
app.include_router(snap_advance.router)
app.include_router(snap_advance.notification_router)
app.include_router(faspay_settlement.router)
app.include_router(faspay_settlement_superadmin.router)
app.include_router(attendance.router)
app.include_router(uang_harian_dinamis.router)
app.include_router(push.router)
app.include_router(error_log.router)


@app.on_event("startup")
def on_startup():
    # TAHAP migrasi Postgres: kalau DATABASE_URL diisi, seluruh proses "buat
    # tabel kalau belum ada" di bawah ini digantikan SATU LANGKAH oleh
    # postgres_schema.create_all() -- skema PostgreSQL dibuat LENGKAP sekali
    # jadi (bukan direplay dari 11 file migrasi inkremental SQLite di atas,
    # yang isinya penuh "PRAGMA table_info" & "ALTER TABLE" khusus SQLite).
    # Jalur SQLite (DATABASE_URL kosong) di bawah ini TIDAK diubah sama
    # sekali -- byte-identik dengan sebelum tahap ini, termasuk seluruh log
    # AUDIT DATA HILANG SETELAH RESTART.
    if db_compat.IS_POSTGRES:
        import postgres_schema
        logger.info(
            "[%s] BOOT: DATABASE_URL diisi -- proses ini terhubung ke PostgreSQL "
            "(bukan file SQLite lokal). Menjalankan postgres_schema.create_all().",
            _INSTANCE_ID,
        )
        postgres_schema.create_all()
    else:
        # AUDIT DATA HILANG SETELAH RESTART: dicatat SEBELUM init_db() dipanggil
        # (init_db() memakai CREATE TABLE IF NOT EXISTS -- begitu dipanggil, file
        # .db langsung ADA walau sebelumnya tidak ada sama sekali, jadi urutan di
        # sini penting supaya log ini benar-benar mencerminkan kondisi DI AWAL
        # proses ini boot, bukan sesudahnya). Dicetak dengan level CRITICAL dan
        # format yang gampang di-grep di log Render (atau platform hosting lain
        # mana pun -- semua menangkap stdout/stderr proses ini sebagai log
        # otomatis) supaya kalau ada insiden "data hilang setelah restart"
        # berikutnya, BUKTINYA langsung ada di log tanpa perlu menebak: apakah
        # file .db sudah ADA (proses ini melanjutkan data lama, normal) atau
        # BARU DIBUAT (proses ini mulai dari nol -- disk yang dipakai TIDAK
        # persisten lintas restart/deploy, lihat README bagian Deployment).
        db_ada_sebelum_boot = os.path.isfile(db.DB_PATH)
        db_size_sebelum_boot = os.path.getsize(db.DB_PATH) if db_ada_sebelum_boot else 0
        if db_ada_sebelum_boot:
            logger.info(
                "[%s] BOOT: file database SUDAH ADA di %s (%s bytes) -- melanjutkan data yang sudah ada.",
                _INSTANCE_ID, db.DB_PATH, db_size_sebelum_boot,
            )
        else:
            logger.critical(
                "[%s] BOOT: file database TIDAK DITEMUKAN di %s -- proses ini akan membuat "
                "database KOSONG dari awal (CREATE TABLE IF NOT EXISTS pada tabel yang belum "
                "ada = tabel baru, ISI KOSONG). Kalau ini BUKAN instalasi pertama kali, ini "
                "BUKTI LANGSUNG bahwa disk tempat file ini seharusnya tersimpan TIDAK PERSISTEN "
                "lintas restart/deploy (lihat README bagian 'Deployment (Produksi)' -- Persistent "
                "Disk WAJIB di-mount tepat ke folder backend/app/). SEMUA data (transaksi, "
                "setting, user, password yang sudah diubah) sebelum restart ini TIDAK BISA "
                "dipulihkan dari sini -- cek folder backups/ (kalau kebetulan ikut persisten) "
                "atau Google Sheets (kalau Sinkronisasi sempat aktif) untuk pemulihan.",
                _INSTANCE_ID, db.DB_PATH,
            )

        # init_db() dari database.py: CREATE TABLE IF NOT EXISTS — sama seperti saat
        # main.py Tkinter dijalankan, tidak pernah menimpa data yang sudah ada.
        db.init_db()
        auth_db.init_auth_db()
        booking_db.init_booking_db()  # BOOKING: tabel bookings/booking_items/closed_slot (idempotent)
        website_content.init_website_db()  # PR 1 Website Content: tabel website_gallery (idempotent)
        file_asset_db.init_file_asset_db()  # Tahap 16: tabel file_asset -- Logo/Hero/Foto About/Background/QRIS (idempotent)
        slip_gaji_db.init_slip_gaji_db()  # Modul Karyawan Fase 1: kolom barbers.gaji_pokok + tabel slip_gaji (idempotent)
        kasbon_db.init_kasbon_db()  # Modul Karyawan Fase 2: tabel kasbon + kasbon_pembayaran (idempotent)
        komisi_penyesuaian_db.init_komisi_penyesuaian_db()  # Modul Karyawan Fase 3: tabel komisi_penyesuaian (idempotent; kolom slip_gaji.penyesuaian_komisi dibuat di init_slip_gaji_db() di atas)
        reimburse_db.init_reimburse_db()  # Modul Karyawan Fase 4: tabel reimburse (idempotent; kolom slip_gaji.reimburse dibuat di init_slip_gaji_db() di atas)
        izin_cuti_db.init_izin_cuti_db()  # Modul Karyawan Fase 5: tabel izin_cuti (idempotent, berdiri sendiri)
        attendance_db.init_attendance_db()  # Modul BARU Absensi: tabel attendance_settings/attendance_logs/attendance_audit_logs (idempotent, berdiri sendiri)
        uang_harian_dinamis_db.init_uang_harian_dinamis_db()  # FITUR Uang Harian Dinamis: tabel uang_harian_dinamis_settings, opt-in per tenant (idempotent, membaca Absensi read-only)
        push_db.init_push_db()  # FITUR Notifikasi Push: tabel push_subscriptions (idempotent, berdiri sendiri)
        error_log_db.init_error_log_db()  # DIY error monitoring: tabel error_logs (idempotent, berdiri sendiri)
        pemasukan_db.init_pemasukan_db()  # Modul Keuangan Fase 1: tabel pemasukan (idempotent)
        uang_kas_db.init_uang_kas_db()  # Modul Keuangan Fase 2 (pengganti Transfer Kas/Bank): tabel kas_saldo_awal + kas_penyesuaian (idempotent)
        data_non_barber_db.init_data_non_barber_db()  # Input Data Non-Barber: tabel data_non_barber, berdiri sendiri dari transaksi Barber (idempotent)
        manual_customer_db.init_manual_customer_db()  # FITUR BARU Manual Customer (Waiting List/Booking): tabel input_data_hari/manual_customer_transaksi/manual_customer_transaksi_service (idempotent)
        superadmin_audit_db.init_superadmin_audit_db()  # FONDASI Multi-Tenant Phase 2.1: tabel superadmin_audit_log (idempotent)
        migrasi_pengeluaran()  # TAHAP 9: tambah kolom kategori/barber_id/aktif ke tabel pengeluaran (idempotent)
        migrasi_pengaturan()   # TAHAP 10: kolom modal di services + seed setting identitas (idempotent)
        migrasi_revisi_bonus() # REVISI: kolom uang_harian per-barber + seed tier bonus (idempotent)
        migrasi_booking()      # BOOKING: kolom durasi_menit di services + seed setting booking (idempotent)
        migrasi_booking_form() # PENYEMPURNAAN FORM BOOKING: status_booking/foto/urutan barber, urutan service (idempotent)
        migrasi_booking_verifikasi()  # Pembayaran Manual QRIS Tenant + Notifikasi WhatsApp: kolom verifikasi_booking_at/oleh + pembayaran_diterima_at/oleh di bookings (idempotent)
        migrasi_nomor_transaksi_booking()  # Format Baru Nomor Transaksi Booking: kolom nomor_transaksi di bookings (idempotent)
        migrasi_produk()        # REVISI: harga_modal/harga_jual produk + snapshot harga di produk_mutasi (idempotent)
        migrasi_bonus_service() # REVISI: seed Setting Bonus Service & Setting Uang Harian dari hardcode lama (idempotent)
        migrasi_tampilan()      # REVISI UI/UX: kolom users.tema untuk Dark/Light Mode per akun (idempotent)
        user_roles_db.init_user_roles_db()  # FITUR Role User Custom: tabel user_roles/user_role_permissions (idempotent)
        migrasi_user_roles()    # FITUR Role User Custom: kolom users.custom_role_id (idempotent)
        migrasi_revisi_setting()  # REVISI Setting: target Uang Harian bisa diatur + Harga Modal per-service (idempotent)
        migrasi_karyawan()      # Karyawan Non-Barber: kolom barbers.jabatan + barbers.gaji_per_hari (idempotent)
        migrasi_izin_cuti()     # REVISI Sistem Dinamis Cuti & Izin: kolom mode_kuota/kuota_izin_hari/kuota_gabungan_hari/periode_mulai_dasar/h_min_pengajuan_izin di izin_cuti_settings + tabel izin_cuti_saldo_awal (idempotent)
        migrasi_absensi_libur_sumber()  # KOREKSI Owner: kolom absensi_libur.sumber (idempotent) -- bedakan baris Barber Holiday manual dari yang dibuat Auto-Libur
        migrasi_r2_storage()    # Migrasi Cloudflare R2: kolom *_r2_key di file_asset/website_gallery/barbers/reimburse (idempotent)
        migrasi_lokasi_user()   # FITUR Izin Lokasi APK Android: kolom users.lokasi_lat/lokasi_lng/lokasi_updated_at (idempotent)
        migrasi_tenant()        # FONDASI Multi-Tenant Phase 1: tabel tenants + kolom tenant_id (idempotent)
        migrasi_subscription()  # FONDASI Multi-Tenant Phase 3: tabel tenant_subscriptions + backfill (idempotent, WAJIB setelah migrasi_tenant())
        billing_db.init_billing_db()  # FONDASI Multi-Tenant Phase 4: tabel subscription_packages + katalog fitur (idempotent)
        billing_db.seed_default_packages()  # seed 4 baris (free/basic/pro/enterprise) kalau belum ada (idempotent)
        billing_db.seed_default_features()  # seed katalog fitur contoh (Booking Online, Export PDF, dst) kalau belum ada (idempotent)
        billing_db.seed_default_package_features()  # Feature Gating: assign booking_online/export_pdf ke SEMUA paket SEKALI SAJA, supaya tenant lama tidak kehilangan fitur yang sebelumnya selalu menyala (idempotent lewat flag settings, lihat docstring)
        billing_db.hapus_fitur_tanpa_fungsi_nyata()  # AUDIT "fitur hardcode di Superadmin": hapus permanen 8 kode fitur yang TIDAK PERNAH menggerbang apa pun di kode, SEKALI SAJA (idempotent lewat flag settings, lihat docstring)
        billing_db.seed_grandfather_fitur_baru_digerbang()  # AUDIT yang sama: export_excel/whatsapp_reminder baru digerbang sekarang -- assign ke SEMUA paket SEKALI SAJA supaya tenant lama tidak kehilangan akses yang sebelumnya selalu menyala (idempotent lewat flag settings, lihat docstring)
        billing_db.hapus_gerbang_qris()  # diminta Owner: QRIS bukan lagi fitur ber-gerbang paket (metode pembayaran inti untuk semua) -- hapus permanen kode "qris" dari katalog fitur, SEKALI SAJA (idempotent lewat flag settings, lihat docstring)
        billing_db.seed_fitur_dekoratif_marketing()  # diminta Owner: 5 kode dekoratif (Manajemen Bisnis/Barber/Layanan, Role & Hak Akses, Komisi & Gaji) -- MURNI tampilan kartu harga, TIDAK menggerbang apa pun -- assign bertahap per paket SEKALI SAJA (idempotent lewat flag settings, lihat docstring)
        billing_db.migrasi_harga_pricing_v2()  # FITUR Landing Page & Pricing (paket 6 bulan): set harga bulanan + 6 bulan basic/pro/enterprise ke daftar harga resmi terbaru, SEKALI SAJA (idempotent lewat flag settings, lihat docstring)
        billing_db.migrasi_harga_tahunan_v1()  # FITUR Landing Page & Pricing (paket Tahunan): set harga_tahunan basic/pro/enterprise, SEKALI SAJA (idempotent lewat flag settings, lihat docstring)
        billing_invoice_db.init_billing_invoice_db()  # FONDASI Multi-Tenant Phase 4: tabel subscription_invoices + subscription_invoice_status_log (idempotent)
        billing_gateway_db.migrasi_billing_gateway()  # Payment Gateway Billing SaaS: bootstrap kredensial dari env var MIDTRANS_* lama ke database, HANYA kalau belum pernah diisi (idempotent)
        migrasi_booking_gateway()  # Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: tabel booking_payment_transactions + booking_payment_status_log (idempotent)
        migrasi_snap_payment()  # Migrasi Faspay SNAP Advance: tabel snap_payment_transactions + snap_payment_status_log TERPADU Booking+SaaS Billing (idempotent)
        migrasi_faspay_settlement()  # Settlement Faspay per Terminal (Tenant): tabel faspay_settlements + faspay_settlement_items (idempotent)
        migrasi_landing()  # FONDASI Multi-Tenant Phase 5: kolom tenants.owner_name/email/whatsapp + tabel landing_faq, drop landing_testimonials (idempotent, WAJIB setelah migrasi_tenant())
        migrasi_email_auth()  # Email/Verifikasi Email/Lupa Kata Sandi: kolom users.email/email_verified/blokir_sampai_verifikasi + tabel email_verification_tokens/password_reset_tokens (idempotent)
        migrasi_booking_slug()  # FITUR URL Booking Publik per Tenant: kolom tenants.booking_slug + backfill tenant lama (idempotent, WAJIB setelah migrasi_tenant())

    _bootstrap_admin_pertama()
    _reset_admin_darurat()
    _bootstrap_superadmin_pertama()
    seed_konfigurasi_awal_agustus_2026()  # REVISI Sistem Dinamis Cuti & Izin: seed saldo cuti akhir Agustus 2026 (5 karyawan) + konfigurasi periode dinamis pertama -- SEKALI SAJA, HANYA tenant yang cocok (idempotent, portable KEDUA jalur DB, lihat izin_cuti_migrasi.py)
    migrasi_konsolidasi_kuota_gabungan()  # PERBAIKAN Sistem Kuota IZIN & CUTI: lipat tenant yang masih mode_kuota='terpisah' jadi 'gabungan' (idempotent, portable KEDUA jalur DB, lihat izin_cuti_migrasi.py)

    # Migrasi Cloudflare R2 (Storage File): dicatat sekali saat boot supaya
    # langsung kelihatan di log Render kalau env var R2_* belum lengkap
    # diisi (upload logo/foto/dst tetap berfungsi lewat fallback BLOB-di-
    # database, TAPI itu artinya belum benar-benar pindah ke R2).
    if r2_storage.IS_ENABLED:
        logger.info("[%s] BOOT: Storage R2 AKTIF (bucket=%s).", _INSTANCE_ID, r2_storage.R2_BUCKET_NAME)
    else:
        logger.warning(
            "[%s] BOOT: Storage R2 BELUM dikonfigurasi (env var R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/"
            "R2_SECRET_ACCESS_KEY/R2_BUCKET_NAME/R2_ENDPOINT_URL belum lengkap) -- upload file "
            "(logo/foto/gallery/bukti/dst) sementara tetap disimpan di database (BLOB), BUKAN R2.",
            _INSTANCE_ID,
        )

    # AUDIT DATA HILANG SETELAH RESTART: ringkasan jumlah baris tabel inti,
    # dicetak SETELAH seluruh migrasi/bootstrap di atas selesai -- log ini
    # jadi "sidik jari" kondisi database tiap kali proses ini boot, gampang
    # dibandingkan dari waktu ke waktu di riwayat log Render.
    with db.get_conn() as conn:
        jumlah = {
            "users": conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"],
            "barbers": conn.execute("SELECT COUNT(*) AS n FROM barbers").fetchone()["n"],
            "transaksi": conn.execute("SELECT COUNT(*) AS n FROM transaksi").fetchone()["n"],
            "bookings": conn.execute("SELECT COUNT(*) AS n FROM bookings").fetchone()["n"],
        }
    logger.info("[%s] BOOT selesai: jumlah_baris=%s", _INSTANCE_ID, jumlah)


def _bootstrap_admin_pertama():
    """Kalau tabel users masih benar-benar kosong (instalasi baru), buatkan
    SATU akun admin dari environment variable, supaya ada cara login pertama
    kali tanpa akses langsung ke database (ayam-telur: tanpa user tidak bisa
    login, tanpa login tidak bisa membuat user). Hanya jalan kalau users
    kosong — tidak akan pernah menimpa/duplikat akun yang sudah dibuat manual.

    AUDIT DATA HILANG SETELAH RESTART: fungsi ini SEHARUSNYA hanya pernah
    jalan SEKALI sepanjang umur satu instalasi (saat benar-benar pertama
    kali dipasang). Kalau fungsi ini jalan LAGI di kemudian hari (log
    CRITICAL di bawah akan menyebutkannya), itu BUKTI tabel users kosong
    padahal seharusnya sudah berisi akun yang dibuat sebelumnya -- lihat log
    "BOOT: file database TIDAK DITEMUKAN" di on_startup() di atas untuk
    akar masalahnya."""
    if auth_db.get_user_list():
        return
    username = os.environ.get("ADMIN_BOOTSTRAP_USERNAME", "owner")
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "ganti-password-ini")
    # FONDASI Multi-Tenant Phase 1: akun pertama ini otomatis milik tenant
    # default (dibuat migrasi_tenant() sebelum baris ini dijalankan, lihat
    # urutan startup di atas) -- instalasi baru = tenant tunggal pertama.
    tenant_default = tenant_db.get_tenant_by_slug(tenant_migrasi.SLUG_TENANT_DEFAULT)
    auth_db.tambah_user(username=username, password=password, role="admin",
                         tenant_id=tenant_default["id"] if tenant_default else None)
    logger.critical(
        "[%s] BOOTSTRAP: tabel users KOSONG saat proses ini boot -- akun admin baru '%s' "
        "dibuat dari ADMIN_BOOTSTRAP_USERNAME/PASSWORD. Kalau ini bukan instalasi pertama "
        "kali, SEMUA user/password yang sudah pernah dibuat sebelumnya TIDAK ADA LAGI di "
        "database ini (lihat log BOOT di atas).",
        _INSTANCE_ID, username,
    )


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
    - ADMIN_RESET_TENANT_ID (BUGFIX audit, OPSIONAL) -- isi id tenant kalau
      deployment ini punya lebih dari satu barbershop, supaya pencarian/
      pembuatan akun di-scope ketat ke tenant itu (lihat docstring
      auth_db.reset_atau_buat_admin_darurat() untuk alasan lengkap: tanpa
      ini, username yang kebetulan ada di lebih dari satu tenant akan
      ditolak eksplisit, dan MEMBUAT admin baru yang belum pernah ada sama
      sekali WAJIB mengisi variable ini).

    Kalau username itu sudah ada, password-nya di-reset (+ dipaksa jadi role
    admin & diaktifkan lagi kalau sempat nonaktif). Kalau belum ada, dibuat
    baru sebagai admin. Baris user lain dan seluruh tabel bisnis lain TIDAK
    disentuh sama sekali (lihat auth_db.reset_atau_buat_admin_darurat()).

    PENTING (dicetak juga saat startup): setelah berhasil login, SEGERA
    hapus kedua/ketiga environment variable ini dari server lalu ganti
    password lewat menu Setting > User -- kalau dibiarkan, TIAP KALI server
    restart akan mereset ulang ke password yang sama."""
    username = os.environ.get("ADMIN_RESET_USERNAME", "").strip()
    password = os.environ.get("ADMIN_RESET_PASSWORD", "")
    if not username or not password:
        return
    tenant_id_raw = os.environ.get("ADMIN_RESET_TENANT_ID", "").strip()
    tenant_id = int(tenant_id_raw) if tenant_id_raw else None
    try:
        hasil = auth_db.reset_atau_buat_admin_darurat(username, password, tenant_id=tenant_id)
    except ValueError as e:
        # Ambigu (username ada di >1 tenant) atau butuh ADMIN_RESET_TENANT_ID
        # untuk membuat admin baru -- JANGAN sampai menggagalkan boot server
        # keseluruhan hanya karena env var break-glass ini salah isi.
        logger.critical(
            "[%s] ADMIN_RESET: GAGAL -- %s", _INSTANCE_ID, e,
        )
        return
    # AUDIT DATA HILANG SETELAH RESTART: dinaikkan ke logger.critical() (dari
    # sebelumnya print() biasa) -- kalau kedua environment variable ini
    # TIDAK SENGAJA dibiarkan terisi di server (lihat peringatan di
    # docstring di atas), fungsi ini akan diam-diam MERESET PASSWORD admin
    # ke nilai yang sama SETIAP KALI proses ini restart, persis cocok
    # dengan gejala "password kembali ke password awal setelah login" --
    # log CRITICAL ini supaya kejadian itu langsung terlihat jelas di log
    # Render (atau platform lain) setiap kali terjadi, bukan cuma print()
    # biasa yang gampang terlewat di antara log lain.
    logger.critical(
        "[%s] ADMIN_RESET: akun admin '%s' berhasil %s lewat environment variable "
        "ADMIN_RESET_USERNAME/ADMIN_RESET_PASSWORD. SEGERA hapus KEDUA environment "
        "variable ini dari server lalu ganti password lewat menu Setting > User -- "
        "SELAMA env var ini masih terisi, SETIAP restart proses akan mereset ulang "
        "password ke nilai yang sama persis (ini KEMUNGKINAN BESAR penyebab kalau ada "
        "laporan 'password kembali ke password awal setelah restart/deploy').",
        _INSTANCE_ID, username, hasil,
    )


def _bootstrap_superadmin_pertama():
    """FONDASI Multi-Tenant Phase 2.1 (Super Admin Dashboard): akun
    `role='superadmin'` (tenant_id=NULL) untuk mengelola SELURUH tenant --
    berbeda dari _bootstrap_admin_pertama() di atas (otomatis jalan kalau
    tabel users kosong, pakai password default), akun ini adalah yang PALING
    sensitif di seluruh sistem (bisa lihat & mengaktifkan/menonaktifkan
    SEMUA tenant), jadi HANYA dibuat kalau operator mengisi KEDUA environment
    variable ini secara eksplisit (pola sama seperti _reset_admin_darurat()
    di bawah) -- default kosong = fungsi ini no-op total, TIDAK PERNAH
    otomatis membuat superadmin dengan password bawaan:
    - SUPERADMIN_BOOTSTRAP_USERNAME
    - SUPERADMIN_BOOTSTRAP_PASSWORD

    Aman dipanggil tiap kali proses ini boot -- no-op begitu SATU akun
    superadmin (role apa pun statusnya) sudah pernah ada, tidak pernah
    menimpa/duplikat."""
    username = os.environ.get("SUPERADMIN_BOOTSTRAP_USERNAME", "").strip()
    password = os.environ.get("SUPERADMIN_BOOTSTRAP_PASSWORD", "")
    if not username or not password:
        return
    if any(u["role"] == "superadmin" for u in auth_db.get_user_list()):
        return
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    logger.critical(
        "[%s] BOOTSTRAP: akun Super Admin baru '%s' dibuat dari "
        "SUPERADMIN_BOOTSTRAP_USERNAME/PASSWORD (belum ada superadmin sebelumnya). "
        "Kalau ini bukan pemasangan Super Admin Dashboard pertama kali, periksa "
        "kenapa tidak ada akun superadmin yang tersimpan sebelumnya.",
        _INSTANCE_ID, username,
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
        "r2_storage_aktif": r2_storage.IS_ENABLED,
        "r2_bucket": r2_storage.R2_BUCKET_NAME if r2_storage.IS_ENABLED else None,
    }
