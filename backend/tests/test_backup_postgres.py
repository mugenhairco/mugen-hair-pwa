"""Regresi Phase 1.1 (celah kritis Export/Import Database) terhadap
PostgreSQL SUNGGUHAN, bukan simulasi -- lihat conftest.requires_postgres.

CATATAN TEKNIS: db_compat.IS_POSTGRES ditentukan SEKALI saat db_compat
pertama kali di-import di satu proses Python (dari DATABASE_URL env var
saat itu) dan tidak pernah berubah lagi -- tidak bisa dites bolak-balik
SQLite<->Postgres dalam SATU proses pytest yang sama dengan test lain di
suite ini (yang semuanya jalur SQLite). Test ini sengaja menjalankan
skenarionya di SUBPROCESS terpisah dengan DATABASE_URL di-set SEBELUM
import apa pun, meniru persis bagaimana proses backend sungguhan boot di
produksi (DATABASE_URL sudah ada di environment SEBELUM main.py dijalankan)."""

import os
import subprocess
import sys
import textwrap

from conftest import requires_postgres, APP_DIR

DATABASE_URL = os.environ.get(
    "MUGEN_TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mugen_test")

_SCRIPT = textwrap.dedent("""
    import os, sys, json
    sys.path.insert(0, {app_dir!r})
    os.environ["DATABASE_URL"] = {database_url!r}

    import db_compat
    with db_compat.get_conn() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

    import postgres_schema
    postgres_schema.create_all()

    import tenant_db
    tenant_a = tenant_db.buat_tenant("pytest-toko-a", "Pytest Toko A")
    tenant_b = tenant_db.buat_tenant("pytest-toko-b", "Pytest Toko B")

    import database as db
    import kasbon_db
    barber_a = db.add_barber("Barber A", tenant_id=tenant_a)
    barber_b = db.add_barber("Barber B", tenant_id=tenant_b)
    kasbon_a = kasbon_db.buat_kasbon(barber_a, "2026-07-01", 100000, tenant_id=tenant_a)
    kasbon_db.buat_kasbon(barber_b, "2026-07-01", 200000, tenant_id=tenant_b)

    import pengaturan_backup
    dump_a = pengaturan_backup.export_database_postgres(tenant_a)
    data_a = json.loads(dump_a)
    assert len(data_a["tabel"]["barbers"]) == 1
    assert len(data_a["tabel"]["kasbon"]) == 1
    assert data_a["tabel"]["kasbon"][0]["id"] == kasbon_a["id"]

    pengaturan_backup.import_database_postgres(dump_a, tenant_a)
    with db_compat.get_conn() as conn:
        barbers_b = conn.execute("SELECT * FROM barbers WHERE tenant_id = %s", (tenant_b,)).fetchall()
        barbers_a = conn.execute("SELECT * FROM barbers WHERE tenant_id = %s", (tenant_a,)).fetchall()
    assert len(barbers_b) == 1 and barbers_b[0]["id"] == barber_b, "restore tenant A menyentuh tenant B!"
    assert len(barbers_a) == 1 and barbers_a[0]["id"] == barber_a

    try:
        pengaturan_backup.import_database_postgres(dump_a, tenant_b)
        raise AssertionError("restore backup tenant A ke tenant B seharusnya ditolak")
    except ValueError as e:
        assert "bukan milik toko" in str(e)

    print("SUBPROCESS_OK")
""")


@requires_postgres
def test_export_import_tenant_scoped_terhadap_postgres_sungguhan():
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT.format(app_dir=APP_DIR, database_url=DATABASE_URL)],
        capture_output=True, text=True, timeout=60,
    )
    assert "SUBPROCESS_OK" in proc.stdout, (
        f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )


_SCRIPT_BACKFILL_BOOKING_SLUG = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {app_dir!r})
    os.environ["DATABASE_URL"] = {database_url!r}

    import db_compat
    with db_compat.get_conn() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

    import postgres_schema
    postgres_schema.create_all()

    # HOTFIX v3 (psycopg2.errors.OutOfMemory: out of shared memory --
    # lihat docstring postgres_schema.py::create_all()/_backfill_booking_slug()
    # untuk penjelasan lengkap akar masalah): sekumpulan tenant LAMA
    # bernama PERSIS SAMA (skenario yang membuktikan bug ini di produksi --
    # setiap tenant butuh percobaan kandidat berurutan panjang) harus
    # tetap di-backfill benar TANPA error, walau jumlahnya banyak.
    with db_compat.get_conn() as conn:
        for i in range(60):
            conn.execute(
                "INSERT INTO tenants (slug, nama_barbershop, status, created_at) "
                "VALUES (?, ?, 'aktif', ?)",
                (f"legacy-{{i}}", "Exact Same Name", "2020-01-01T00:00:00"),
            )

    postgres_schema.create_all()

    with db_compat.get_conn() as conn:
        rows = conn.execute(
            "SELECT booking_slug FROM tenants WHERE slug LIKE ?", ("legacy-%",)
        ).fetchall()
    slugs = [r["booking_slug"] for r in rows]
    assert len(slugs) == 60
    assert all(s for s in slugs), "ada booking_slug yang masih kosong setelah backfill"
    assert len(set(slugs)) == 60, "ada booking_slug yang bentrok (tidak unik) setelah backfill"

    # Idempotent: dipanggil ulang tidak mengubah hasil yang sudah ada.
    postgres_schema.create_all()
    with db_compat.get_conn() as conn:
        rows2 = conn.execute(
            "SELECT booking_slug FROM tenants WHERE slug LIKE ?", ("legacy-%",)
        ).fetchall()
    assert sorted(r["booking_slug"] for r in rows2) == sorted(slugs)

    print("SUBPROCESS_OK")
""")


@requires_postgres
def test_backfill_booking_slug_banyak_tenant_bentrok_nama_terhadap_postgres_sungguhan():
    """Regresi HOTFIX v3 produksi: psycopg2.errors.OutOfMemory ("out of
    shared memory" / "increase max_locks_per_transaction") saat startup,
    dipicu SPESIFIK oleh _backfill_booking_slug() -- versi SEBELUMNYA
    (v2) memakai SAVEPOINT per kandidat TAPI seluruh loop tetap satu
    transaksi besar, sehingga tenant yang saling bertabrakan nama (butuh
    banyak percobaan kandidat berurutan) menumpuk banyak subtransaksi
    dalam satu transaksi -- subtransaksi TIDAK bisa lewat fast-path lock
    manager Postgres, menghabiskan shared lock table. Reproduksi PENUH
    (memaksa error itu sungguhan) butuh mengecilkan max_connections/
    max_locks_per_transaction server (lihat investigasi manual, tidak
    praktis dilakukan otomatis dalam test ini karena mengubah konfigurasi
    server Postgres bersama) -- test ini fokus memastikan KEBENARAN
    algoritma (unik, lengkap, idempotent) tetap terjaga terhadap
    PostgreSQL sungguhan setelah restrukturisasi transaksi di HOTFIX v3."""
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT_BACKFILL_BOOKING_SLUG.format(app_dir=APP_DIR, database_url=DATABASE_URL)],
        capture_output=True, text=True, timeout=120,
    )
    assert "SUBPROCESS_OK" in proc.stdout, (
        f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )


def test_tables_tidak_mengandung_karakter_pemicu_placeholder_psycopg2():
    """Regresi bug produksi (Phase 3): db_compat._translate() menerjemahkan
    SETIAP tanda tanya literal di _TABLES (postgres_schema.py) -- termasuk
    yang ada di dalam komentar SQL "--" -- jadi placeholder posisi
    Postgres, dan psycopg2 ikut mencari pola placeholder itu di SELURUH
    teks query (termasuk komentar) saat parameter diberikan. Kalau salah
    satu jebakan ini kena, create_all() gagal saat runtime dengan
    "IndexError: tuple index out of range" -- BUKAN error sintaks SQL, jadi
    TIDAK PERNAH tertangkap py_compile/linter, hanya kelihatan saat
    benar-benar dieksekusi lewat koneksi PostgreSQL sungguhan (lihat test
    di atas). Test statis ini (TIDAK butuh Postgres sungguhan, selalu
    jalan) mendeteksi dua jebakan itu lebih awal & lebih cepat."""
    import sys

    sys.path.insert(0, APP_DIR)
    import postgres_schema

    tables = postgres_schema._TABLES
    assert "?" not in tables, "Tanda tanya literal di _TABLES akan diterjemahkan jadi placeholder Postgres."
    assert "%s" not in tables, "'%s' literal di _TABLES akan disalahartikan psycopg2 sebagai placeholder posisi."
