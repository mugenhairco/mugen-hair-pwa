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


_SCRIPT_POOL_TIMEOUT = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {app_dir!r})
    os.environ["DATABASE_URL"] = {database_url!r}

    import db_compat
    pool = db_compat._get_pool()
    kwargs = pool._kwargs

    assert kwargs.get("connect_timeout"), (
        "connect_timeout tidak diset -- percobaan koneksi baru ke server yang "
        "tidak membalas bisa menggantung tanpa batas waktu"
    )
    assert kwargs.get("keepalives") == 1, (
        "TCP keepalive tidak aktif -- koneksi basi yang tersimpan idle di pool "
        "bisa menggantung tanpa batas saat dipakai ulang"
    )
    assert kwargs.get("keepalives_idle"), "keepalives_idle tidak diset"
    assert "statement_timeout" in (kwargs.get("options") or ""), (
        "statement_timeout tidak diset -- satu query individual bisa "
        "menggantung tanpa batas kalau tertahan lock/kontensi"
    )

    # Pool dengan konfigurasi ini TETAP harus bisa dipakai normal terhadap
    # server yang sungguhan menyala (timeout/keepalive HANYA memengaruhi
    # kasus server tidak membalas, bukan koneksi sehat biasa).
    with db_compat.get_conn() as conn:
        row = conn.execute("SELECT 1 AS ok").fetchone()
        assert row["ok"] == 1

    print("SUBPROCESS_OK")
""")


@requires_postgres
def test_pool_postgres_pakai_connect_timeout_dan_keepalive():
    """Regresi HOTFIX (produksi macet total di "Memuat aplikasi..." --
    SEMUA endpoint yang menyentuh database, termasuk GET /api/tenant/
    branding yang PALING PERTAMA dipanggil saat aplikasi boot, tidak
    pernah membalas sama sekali, BUKAN error, benar-benar menggantung):
    pool psycopg2 (db_compat.py::_get_pool()) SEBELUMNYA dibuat tanpa
    connect_timeout/keepalive/statement_timeout apa pun -- percobaan
    koneksi baru ke server yang tidak membalas (paket jaringan hilang,
    server bermasalah, dst) bisa menggantung TANPA BATAS WAKTU tanpa
    exception apa pun. Dibuktikan manual lewat simulasi iptables DROP
    (butuh akses root, tidak portable dijalankan otomatis di sini):
    SEBELUM perbaikan menggantung tanpa henti, SESUDAH perbaikan gagal
    PERSIS dalam batas connect_timeout yang diatur. Test ini memverifikasi
    konfigurasi pool SUNGGUHAN terpasang benar (perilaku connect_timeout/
    keepalive itu sendiri murni tanggung jawab libpq/psycopg2, sudah
    teruji di level library) DAN pool dengan konfigurasi ini tetap bisa
    dipakai normal terhadap server yang sungguhan menyala."""
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT_POOL_TIMEOUT.format(app_dir=APP_DIR, database_url=DATABASE_URL)],
        capture_output=True, text=True, timeout=30,
    )
    assert "SUBPROCESS_OK" in proc.stdout, (
        f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )


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


_SCRIPT_LOCK_TIMEOUT_BOOT = textwrap.dedent("""
    import os, sys, threading, time
    sys.path.insert(0, {app_dir!r})
    os.environ["DATABASE_URL"] = {database_url!r}

    import db_compat
    with db_compat.get_conn() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

    import postgres_schema
    postgres_schema.create_all()

    with db_compat.get_conn() as conn:
        conn.execute(
            "INSERT INTO tenants (slug, nama_barbershop, status, created_at) "
            "VALUES ('toko-terkunci', 'Toko Terkunci', 'aktif', '2020-01-01T00:00:00')"
        )
        tenant_id = conn.execute("SELECT id FROM tenants WHERE slug = 'toko-terkunci'").fetchone()["id"]

    # Sesi TERPISAH (koneksi psycopg2 langsung, BUKAN lewat pool db_compat)
    # memegang row lock di tenant ini lewat transaksi yang SENGAJA belum
    # di-commit -- mensimulasikan sesi basi/zombie dari percobaan deploy
    # sebelumnya yang macet, seperti yang terjadi di produksi.
    import psycopg2
    lock_conn = psycopg2.connect({database_url!r})
    lock_cur = lock_conn.cursor()
    lock_cur.execute("BEGIN")
    lock_cur.execute("UPDATE tenants SET nama_barbershop = nama_barbershop WHERE id = %s", (tenant_id,))

    def lepas_lock_setelah(detik):
        time.sleep(detik)
        lock_conn.commit()
        lock_conn.close()

    pelepas = threading.Thread(target=lepas_lock_setelah, args=(8,))
    pelepas.start()

    # HOTFIX v4->v5: lock dipegang 8 detik (lebih lama dari lock_timeout
    # backfill 5 detik) -- _backfill_booking_slug() HARUS tetap kembali
    # normal (TIDAK menggantung, TIDAK melempar exception) dalam waktu
    # singkat, melewati tenant yang terkunci untuk boot ini.
    t0 = time.monotonic()
    postgres_schema._backfill_booking_slug()
    elapsed = time.monotonic() - t0
    assert elapsed < 7, f"_backfill_booking_slug() menggantung {{elapsed}}s -- seharusnya dilewati cepat lewat lock_timeout"

    with db_compat.get_conn() as conn:
        row = conn.execute("SELECT booking_slug FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    assert row["booking_slug"] is None, "seharusnya masih kosong -- dilewati karena lock, bukan diisi paksa"

    pelepas.join()

    # Restart berikutnya (lock sudah lepas): backfill harus berhasil normal.
    postgres_schema._backfill_booking_slug()
    with db_compat.get_conn() as conn:
        row2 = conn.execute("SELECT booking_slug FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    assert row2["booking_slug"] == "tokoterkunci", "seharusnya terisi di percobaan berikutnya setelah lock lepas"

    print("SUBPROCESS_OK")
""")


@requires_postgres
def test_backfill_booking_slug_lewati_tenant_terkunci_tanpa_menggantung():
    """Regresi HOTFIX v4->v5 (produksi macet total lagi setelah PR #84 --
    log bertahap membuktikan create_all() SELESAI CEPAT (1.38s) tapi
    _backfill_booking_slug() macet TOTAL di percobaan UPDATE tenant
    PERTAMA, tanpa error apa pun, sampai Render membatalkan deploy karena
    port-scan timeout -- padahal jumlah tenant di produksi SEDIKIT,
    menyingkirkan hipotesis "banyak round-trip". Dugaan paling mungkin:
    baris tenant itu terkunci sesi lain (sisa percobaan deploy sebelumnya
    yang gagal/dibatalkan tidak bersih) dan statement_timeout dari
    `options` koneksi pool TERNYATA tidak cukup diandalkan sebagai satu-
    satunya lapisan proteksi di produksi.

    Diperbaiki dengan SET LOCAL lock_timeout eksplisit (perintah SQL biasa
    lewat koneksi yang sama, bukan parameter startup) sebelum tiap
    percobaan UPDATE -- kalau tertahan lock lebih dari 5 detik, tenant itu
    DILEWATI (bukan fatal) untuk boot ini, otomatis dicoba ulang restart
    berikutnya, TIDAK PERNAH menghalangi seluruh aplikasi gagal start.
    Test ini mereproduksi persis skenario itu: sesi terpisah memegang row
    lock di satu tenant, memverifikasi _backfill_booking_slug() tetap
    kembali cepat (TIDAK menggantung) dan tenant lain/berikutnya tidak
    ikut terganggu."""
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT_LOCK_TIMEOUT_BOOT.format(app_dir=APP_DIR, database_url=DATABASE_URL)],
        capture_output=True, text=True, timeout=60,
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
