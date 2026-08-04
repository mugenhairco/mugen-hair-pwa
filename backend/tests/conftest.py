"""
conftest.py — Fixture bersama untuk test suite backend
=============================================================================
FONDASI Multi-Tenant Phase 1.1 (technical debt): sebelum file ini ada,
seluruh verifikasi isolasi tenant/regresi fitur dilakukan lewat script
ad-hoc di scratchpad sesi kerja -- TIDAK pernah tersimpan permanen di
repo, jadi TIDAK PERNAH otomatis dijalankan ulang (CI, sebelum merge PR,
dst). File-file di direktori `tests/` ini memindahkan skenario yang sama
jadi test suite pytest permanen.

Pola dasar tiap test: reassign `database.DB_PATH`/`auth_db.DB_PATH` ke
file SQLite temporer KOSONG SEBELUM membuat `TestClient(main.app)` --
`TestClient` sebagai context manager memicu event `startup` FastAPI
(termasuk seluruh `init_*_db()` dan `migrasi_tenant()`) tiap kali dipakai,
jadi setiap test function otomatis dapat database bersih & terisolasi
satu sama lain (fixture `client`/`two_tenant` di bawah scope="function").
"""

import os
import sys
import tempfile

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


@pytest.fixture()
def db_path(tmp_path):
    """Path file SQLite temporer, unik per test function (tmp_path pytest
    bawaan sudah otomatis dibersihkan setelah test selesai)."""
    return str(tmp_path / "mugen_test.db")


@pytest.fixture()
def app_client(db_path):
    """TestClient dengan database SQLite kosong yang baru di-boot penuh
    (termasuk migrasi_tenant()) -- dipakai HAMPIR SEMUA test di suite ini."""
    import database
    import auth_db

    database.DB_PATH = db_path
    auth_db.DB_PATH = db_path

    import main
    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def two_tenants(app_client):
    """Dua tenant + akun Owner masing-masing, sudah login -- dipakai SEMUA
    test isolasi lintas tenant. Return dict berisi client + tenant_id +
    header Authorization siap pakai untuk masing-masing tenant.

    SENGAJA TIDAK membuat baris tenant_subscriptions (beda dari tenant
    sungguhan yang selalu lewat routers/superadmin.py::buat_tenant()) --
    test_subscription.py::test_tenant_tanpa_baris_subscription_tidak_diblokir_fail_open
    justru bergantung pada fixture ini TIDAK punya baris subscription sama
    sekali (mendokumentasikan perilaku fail-open Phase 3). Test yang butuh
    tenant dengan subscription "sungguhan" (mis. test_feature_access.py)
    memanggil subscription_db.create_default_subscription() sendiri secara
    eksplisit di badan test-nya, BUKAN lewat fixture ini."""
    import tenant_db
    import auth_db

    tenant_a = tenant_db.buat_tenant("test-toko-a", "Test Toko A")
    tenant_b = tenant_db.buat_tenant("test-toko-b", "Test Toko B")

    auth_db.tambah_user("ownerA", "passwordA123", role="admin", tenant_id=tenant_a)
    auth_db.tambah_user("ownerB", "passwordB123", role="admin", tenant_id=tenant_b)

    def _login(username, password):
        r = app_client.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["token"]

    token_a = _login("ownerA", "passwordA123")
    token_b = _login("ownerB", "passwordB123")

    return {
        "client": app_client,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "headers_b": {"Authorization": f"Bearer {token_b}"},
    }


@pytest.fixture()
def single_tenant(app_client):
    """Satu tenant + akun Owner, sudah login -- dipakai test regresi
    fungsional (bukan isolasi) yang cukup satu tenant saja.

    SENGAJA TIDAK membuat baris tenant_subscriptions -- lihat catatan
    panjang sama persis di fixture two_tenants() di atas."""
    import tenant_db
    import auth_db

    tenant_id = tenant_db.buat_tenant("test-toko", "Test Toko")
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=tenant_id)

    r = app_client.post("/api/auth/login", json={"username": "owner1", "password": "password123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    return {
        "client": app_client,
        "tenant_id": tenant_id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def has_postgres() -> bool:
    """True kalau ada PostgreSQL yang bisa diajak konek di localhost:5432
    dengan kredensial default test (postgres/postgres, database
    'mugen_test') -- test PostgreSQL-only (lihat test_backup_postgres.py)
    di-skip otomatis kalau ini False, supaya suite tetap jalan penuh di
    lingkungan CI yang tidak menyediakan PostgreSQL."""
    if os.environ.get("MUGEN_TEST_DATABASE_URL"):
        return True
    try:
        import psycopg2
    except ImportError:
        return False
    try:
        conn = psycopg2.connect(
            "postgresql://postgres:postgres@localhost:5432/mugen_test", connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not has_postgres(),
    reason="Butuh PostgreSQL lokal (postgres/postgres@localhost:5432/mugen_test) -- "
           "lihat MUGEN_TEST_DATABASE_URL untuk override connection string.",
)
