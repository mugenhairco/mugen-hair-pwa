"""Verifikasi migrasi database Phase 1.1 (poin 3 permintaan hardening):
- Database baru dibuat dari nol tanpa error, seluruh kolom tenant_id ada.
- Database LAMA (skema sebelum Phase 1.1, termasuk kas_saldo_awal id=1
  tunggal) dimigrasikan dengan aman -- data lama tidak hilang, di-backfill
  ke tenant default dengan benar.

Tidak ada migrasi destruktif di proyek ini (semua kolom baru NULLABLE,
tidak ada DROP/ALTER TYPE) -- desain ini sengaja membuat rollback tidak
diperlukan, jadi tidak ada test rollback terpisah."""

import sqlite3


def test_fresh_db_membuat_semua_tabel_dan_kolom_tenant_id(app_client, db_path):
    import database

    with database.get_conn() as conn:
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "pemasukan" in tables
        assert "kas_saldo_awal" in tables
        assert "kasbon" in tables

        for t in ("pemasukan", "kas_saldo_awal", "kas_penyesuaian"):
            cols = [c["name"] for c in conn.execute(f"PRAGMA table_info({t})").fetchall()]
            assert "tenant_id" in cols, f"{t} kehilangan kolom tenant_id"


def test_migrasi_database_lama_tanpa_kehilangan_data(tmp_path):
    """Simulasi database SEBELUM Phase 1.1: tabel pemasukan/kas_saldo_awal/
    kas_penyesuaian dibuat manual TANPA kolom tenant_id, diisi data
    sungguhan, lalu boot aplikasi normal (yang menjalankan migrasi_tenant())
    -- data lama harus tetap ada & ter-backfill ke tenant default,
    kas_saldo_awal id=1 lama harus tetap terbaca dan tidak hilang."""
    db_path = str(tmp_path / "database_lama.db")

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE pemasukan (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, kategori TEXT NOT NULL,
            keterangan TEXT NOT NULL, jumlah INTEGER NOT NULL, barber_id INTEGER,
            aktif INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO pemasukan (tanggal, kategori, keterangan, jumlah, aktif, created_at) "
        "VALUES ('2026-01-01', 'Modal Tambahan', 'data lama sebelum Phase 1.1', 999000, 1, "
        "'2026-01-01T00:00:00')"
    )
    conn.execute("""
        CREATE TABLE kas_saldo_awal (
            id INTEGER PRIMARY KEY, saldo INTEGER NOT NULL DEFAULT 0, diubah_oleh TEXT, updated_at TEXT
        )
    """)
    conn.execute("INSERT INTO kas_saldo_awal (id, saldo) VALUES (1, 5000000)")
    conn.execute("""
        CREATE TABLE kas_penyesuaian (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, jenis TEXT NOT NULL,
            jumlah INTEGER NOT NULL, keterangan TEXT, dibuat_oleh TEXT, created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO kas_penyesuaian (tanggal, jenis, jumlah, created_at) "
        "VALUES ('2026-01-02', 'tambah', 100000, '2026-01-02T00:00:00')"
    )
    conn.commit()
    conn.close()

    import database
    import auth_db

    database.DB_PATH = db_path
    auth_db.DB_PATH = db_path

    import main
    from fastapi.testclient import TestClient

    with TestClient(main.app):
        import tenant_db
        import uang_kas_db

        default_tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
        assert default_tenant is not None
        default_id = default_tenant["id"]

        with database.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM pemasukan WHERE keterangan = 'data lama sebelum Phase 1.1'").fetchone()
            assert row is not None, "data pemasukan lama hilang setelah migrasi"
            assert row["tenant_id"] == default_id
            assert row["jumlah"] == 999000

            saldo_row = conn.execute("SELECT * FROM kas_saldo_awal WHERE id = 1").fetchone()
            assert saldo_row is not None
            assert saldo_row["tenant_id"] == default_id
            assert saldo_row["saldo"] == 5000000

            kas_row = conn.execute("SELECT * FROM kas_penyesuaian WHERE jumlah = 100000").fetchone()
            assert kas_row is not None
            assert kas_row["tenant_id"] == default_id

        # Tenant BARU yang dibuat setelah migrasi harus punya baris
        # kas_saldo_awal sendiri (id = tenant_id), tidak mewarisi/bentrok
        # dengan baris id=1 milik tenant default di atas.
        tenant_baru = tenant_db.buat_tenant("toko-baru", "Toko Baru")
        saldo_baru = uang_kas_db.get_saldo_awal(tenant_baru)
        assert saldo_baru["saldo"] == 0
        assert saldo_baru["id"] == tenant_baru
        assert uang_kas_db.get_saldo_awal(default_id)["saldo"] == 5000000
