"""
landing_migrasi.py — Migrasi skema FONDASI Multi-Tenant Phase 5 (Landing Page SaaS)
====================================================================================
Menambahkan:
- Kolom `owner_name`/`email`/`whatsapp` di tabel `tenants` -- dibutuhkan
  Register publik (landing page), tabel `tenants` sebelumnya tidak pernah
  menyimpan data ini (dibuat eksklusif lewat Dashboard Super Admin, tanpa
  email/whatsapp -- lihat tenant_migrasi.py). Ditambah lewat ALTER TABLE,
  BUKAN membuat ulang tabel `tenants`, sama seperti pola pengeluaran_migrasi.py.
- Tabel BARU `landing_faq` -- konten Landing Page publik yang dikelola
  Super Admin (bukan hardcode).

REVISI Restrukturisasi Super Admin & Landing Page: fitur Testimonial
dihapus total -- tabel `landing_testimonials` (kalau sempat terbuat di
instalasi lama) di-DROP di sini, BUKAN dibuat lagi.

Aman dipanggil berulang kali (idempotent), TIDAK PERNAH menghapus/menimpa
data lama SELAIN landing_testimonials di atas (permintaan eksplisit
pembersihan fitur Testimonial). WAJIB dipanggil setelah migrasi_tenant()
(kolom `tenants` yang ditambah di sini mengasumsikan tabel `tenants` sudah
ada)."""

from database import get_conn


def migrasi_landing():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(tenants)").fetchall()]
        if "owner_name" not in kolom:
            conn.execute("ALTER TABLE tenants ADD COLUMN owner_name TEXT")
        if "email" not in kolom:
            conn.execute("ALTER TABLE tenants ADD COLUMN email TEXT")
        if "whatsapp" not in kolom:
            conn.execute("ALTER TABLE tenants ADD COLUMN whatsapp TEXT")

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_email ON tenants(email) WHERE email IS NOT NULL"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_whatsapp ON tenants(whatsapp) WHERE whatsapp IS NOT NULL"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS landing_faq (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                pertanyaan   TEXT NOT NULL,
                jawaban      TEXT NOT NULL,
                urutan       INTEGER NOT NULL DEFAULT 0,
                aktif        INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)

        conn.execute("DROP TABLE IF EXISTS landing_testimonials")
