"""Regresi Phase 1.1 (celah kritis Export/Import Database): jalur SQLite
adalah file .db UTUH (tidak bisa difilter per tenant lewat copy file) --
router menolak (409) Export/Import kalau instalasi itu kebetulan sudah
punya lebih dari satu tenant. Tidak butuh PostgreSQL (murni jalur SQLite)."""


def test_export_ditolak_kalau_lebih_dari_satu_tenant(app_client):
    import tenant_db
    import auth_db
    import pengaturan_backup

    # PENTING: setiap boot SQLite otomatis membuat SATU tenant default
    # ("mugen-hair-co", lihat tenant_migrasi.py::_pastikan_tenant_default())
    # -- fixture `single_tenant` di conftest.py membuat tenant TAMBAHAN di
    # atasnya (jadi selalu >1 tenant), sengaja TIDAK dipakai di sini.
    # Skenario "instalasi benar-benar cuma satu tenant" berarti login
    # sebagai Owner tenant DEFAULT itu sendiri, tanpa tenant lain dibuat.
    default_tenant = tenant_db.get_tenant_by_slug("mugen-hair-co")
    assert default_tenant is not None
    auth_db.tambah_user("owner1", "password123", role="admin", tenant_id=default_tenant["id"])

    r = app_client.post("/api/auth/login", json={"username": "owner1", "password": "password123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    assert pengaturan_backup.sqlite_punya_lebih_dari_satu_tenant() is False
    r = app_client.get("/api/pengaturan/backup/export", headers=headers)
    assert r.status_code == 200

    tenant_db.buat_tenant("toko-kedua", "Toko Kedua")

    assert pengaturan_backup.sqlite_punya_lebih_dari_satu_tenant() is True
    r = app_client.get("/api/pengaturan/backup/export", headers=headers)
    assert r.status_code == 409
