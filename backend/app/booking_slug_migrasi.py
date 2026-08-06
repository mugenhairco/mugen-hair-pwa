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
`slug` masing-masing tenant (tenant_db.buat_slug_unik(), pool keunikan
gabungan slug+booking_slug -- lihat docstring-nya), SEKALI SAJA per tenant
(hanya baris yang booking_slug-nya MASIH NULL/kosong, tidak pernah menimpa
booking_slug yang sudah diisi/diedit Owner). Jalan tiap boot, aman diulang."""

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
    # Kolom (+ index) di atas WAJIB sudah ter-COMMIT (with-block di atas
    # selesai) SEBELUM backfill di bawah jalan -- backfill memanggil
    # tenant_db.buat_slug_unik(), yang membuka KONEKSI BARUNYA SENDIRI
    # (lihat tenant_db.py, TIDAK menerima `conn` yang sedang berjalan) --
    # kalau ALTER TABLE di atas belum ter-commit, koneksi baru itu akan
    # gagal "no such column: booking_slug".
    _backfill_booking_slug()


def _backfill_booking_slug():
    import tenant_db  # import lokal: hindari import siklik saat modul ini dimuat lebih dulu

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, slug, nama_barbershop FROM tenants WHERE booking_slug IS NULL OR booking_slug = ''"
        ).fetchall()
    for r in rows:
        # SATU koneksi/commit TERPISAH per tenant (BUKAN satu transaksi
        # besar mencakup seluruh loop) -- WAJIB supaya buat_slug_unik()
        # pada iterasi BERIKUTNYA langsung melihat booking_slug tenant
        # SEBELUMNYA yang baru saja disimpan (buat_slug_unik() membuka
        # koneksinya sendiri lewat tenant_db.py, tidak ikut satu transaksi
        # dengan baris ini) -- mencegah dua tenant bernama sama kebagian
        # hasil backfill booking_slug yang SAMA (lihat _slug_dipakai()).
        booking_slug = tenant_db.buat_slug_unik(r["nama_barbershop"] or r["slug"], kecuali_tenant_id=r["id"])
        with get_conn() as conn:
            conn.execute("UPDATE tenants SET booking_slug = ? WHERE id = ?", (booking_slug, r["id"]))
