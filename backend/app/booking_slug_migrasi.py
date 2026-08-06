"""
booking_slug_migrasi.py — FITUR URL Booking Publik per Tenant
=============================================================================
Menambahkan kolom `tenants.booking_slug` -- URL booking publik SENDIRI per
tenant (`<booking_slug>.rivoirsett.com/app/#/book`, lihat tenant_db.py::
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
    """HOTFIX (crash produksi "duplicate key value violates unique
    constraint idx_tenants_booking_slug" saat startup, menyebabkan
    crash-loop): versi SEBELUMNYA membuka SATU KONEKSI/TRANSAKSI TERPISAH
    per tenant (lewat tenant_db.buat_slug_unik(), yang punya get_conn()
    sendiri) -- kandidat slug dihitung benar untuk SATU proses, tapi kalau
    proses ini (main.py::on_startup()) kebetulan berjalan lebih dari SATU
    KALI bersamaan (mis. restart cepat berturut-turut sebelum proses lama
    benar-benar berhenti), dua transaksi independen bisa menghitung
    kandidat yang SAMA dari snapshot data yang sama sebelum salah satunya
    commit -- proses kedua gagal UniqueViolation.

    Diperbaiki dengan memakai `conn` (SATU transaksi yang SAMA dengan
    ALTER TABLE/CREATE INDEX di migrasi_booking_slug() di atas, BUKAN
    koneksi baru) untuk SELURUH backfill -- SQLite otomatis menahan lock
    tulis (busy_timeout 30 detik, lihat database.py::get_conn()) selama
    transaksi ini berlangsung, jadi proses KEDUA yang mencoba menulis di
    saat bersamaan akan MENUNGGU sampai transaksi ini selesai (bukan
    membaca snapshot basi lalu bertabrakan) -- begitu proses kedua
    lanjut, seluruh tenant sudah punya booking_slug, tidak ada lagi yang
    perlu di-backfill. Logika slugify + collision-numbering DIDUPLIKASI
    di sini (bukan memanggil tenant_db.buat_slug_unik(), yang MEMBUKA
    KONEKSINYA SENDIRI -- persis akar masalah di atas) -- SAMA PERSIS
    pola postgres_schema.py::_backfill_booking_slug(), lihat docstring
    tenant_migrasi.py untuk alasan duplikasi SQLite/Postgres semacam ini."""
    import tenant_middleware  # import lokal: hindari import siklik saat modul ini dimuat lebih dulu

    rows = conn.execute("SELECT id, slug, nama_barbershop, booking_slug FROM tenants").fetchall()
    terpakai = set(tenant_middleware.LABEL_BUKAN_TENANT)
    for r in rows:
        if r["slug"]:
            terpakai.add(r["slug"])
        if r["booking_slug"]:
            terpakai.add(r["booking_slug"])
    for r in rows:
        if r["booking_slug"]:
            continue
        dasar = re.sub(r"[^a-z0-9]+", "", (r["nama_barbershop"] or r["slug"] or "").strip().lower()) or "toko"
        slug = dasar
        percobaan = 1
        while slug in terpakai:
            percobaan += 1
            slug = f"{dasar}{percobaan}"
        terpakai.add(slug)
        conn.execute("UPDATE tenants SET booking_slug = ? WHERE id = ?", (slug, r["id"]))
