"""
booking_slug_migrasi.py — FITUR URL Booking Publik per Tenant
=============================================================================
Menambahkan kolom `tenants.booking_slug` -- URL booking publik SENDIRI per
tenant (`<booking_slug>.rivoirsett.com/book`, lihat tenant_db.py::
get_booking_url()/set_booking_slug()), TERPISAH dari `slug` (subdomain
dashboard/staff, TIDAK BERUBAH sama sekali). Idempotent (ALTER TABLE ADD
COLUMN dicek dulu, sama pola dengan landing_migrasi.py), WAJIB dipanggil
SETELAH migrasi_tenant() (kolom `tenants` sudah harus ada).

Backfill: tenant LAMA (dibuat sebelum fitur ini ada) belum punya
booking_slug -- diisi OTOMATIS di sini dengan basis yang SAMA PERSIS dengan
`slug` masing-masing tenant (algoritma sama dengan tenant_db.buat_slug_unik()
-- DIDUPLIKASI di sini, lihat _backfill_booking_slug() untuk alasannya),
SEKALI SAJA per tenant (hanya baris yang booking_slug-nya MASIH NULL/kosong,
tidak pernah menimpa booking_slug yang sudah diisi/diedit Owner). Jalan
tiap boot, aman diulang."""

import re

from database import get_conn
from db_compat import IntegrityError


def migrasi_booking_slug():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(tenants)").fetchall()]
        if "booking_slug" not in kolom:
            conn.execute("ALTER TABLE tenants ADD COLUMN booking_slug TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_booking_slug "
            "ON tenants(booking_slug) WHERE booking_slug IS NOT NULL"
        )
        _backfill_booking_slug(conn)


def _backfill_booking_slug(conn):
    """HOTFIX v2 (crash produksi "duplicate key value violates unique
    constraint idx_tenants_booking_slug" TERUS TERJADI walau versi
    SEBELUMNYA sudah memakai satu transaksi utuh -- lihat
    postgres_schema.py::_backfill_booking_slug() untuk penjelasan lengkap,
    logika di sini didesain ulang IDENTIK): pendekatan "hitung SELURUH
    kandidat di memori Python dari SATU snapshot SELECT, baru UPDATE
    polos" diam-diam mengasumsikan TIDAK ADA proses/koneksi LAIN yang
    menulis kolom slug/booking_slug SELAMA backfill ini berjalan --
    asumsi itu TIDAK CUKUP kuat di produksi (proses lain, termasuk
    instance dengan kode versi LEBIH LAMA yang tidak tahu-menahu soal
    perlindungan apa pun di sini, tetap bisa menulis).

    Diperbaiki total dengan pendekatan "coba lalu mundur": setiap kandidat
    langsung dicoba lewat UPDATE SUNGGUHAN di dalam SAVEPOINT -- kalau
    bentrok (IntegrityError, SIAPA PUN/KAPAN PUN penyebabnya), savepoint
    itu di-ROLLBACK (transaksi TETAP sehat, TIDAK menggagalkan migrasi
    lain di migrasi_booking_slug() atau proses boot secara keseluruhan)
    dan kandidat berikutnya dicoba -- verifikasi keunikan LANGSUNG ke
    database saat itu juga, bukan lagi lewat kalkulasi di memori yang
    bisa basi kalau ada penulis lain."""
    import tenant_middleware  # import lokal: hindari import siklik saat modul ini dimuat lebih dulu

    rows = conn.execute("SELECT id, slug, nama_barbershop, booking_slug FROM tenants").fetchall()
    for r in rows:
        if r["booking_slug"]:
            continue
        dasar = re.sub(r"[^a-z0-9]+", "", (r["nama_barbershop"] or r["slug"] or "").strip().lower()) or "toko"
        kandidat = dasar
        percobaan = 1
        while True:
            if kandidat in tenant_middleware.LABEL_BUKAN_TENANT:
                percobaan += 1
                kandidat = f"{dasar}{percobaan}"
                continue
            conn.execute("SAVEPOINT booking_slug_backfill")
            try:
                conn.execute("UPDATE tenants SET booking_slug = ? WHERE id = ?", (kandidat, r["id"]))
            except IntegrityError:
                conn.execute("ROLLBACK TO SAVEPOINT booking_slug_backfill")
                percobaan += 1
                kandidat = f"{dasar}{percobaan}"
                continue
            conn.execute("RELEASE SAVEPOINT booking_slug_backfill")
            break
