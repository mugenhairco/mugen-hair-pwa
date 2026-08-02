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
