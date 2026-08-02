"""Regresi isolasi tenant Phase 1.1 -- modul Keuangan (Pemasukan, Uang
Kas). Beda dari modul Karyawan: routers/pemasukan.py & routers/uang_kas.py
sebelum Phase 1.1 TIDAK PUNYA pengecekan tenant SAMA SEKALI (bukan cuma
celah scoping) -- dan pemasukan/kas_saldo_awal/kas_penyesuaian butuh
migrasi kolom tenant_id baru (barber_id nullable/tidak ada, tidak bisa
di-scope transitif seperti modul Karyawan)."""

import pemasukan_db
import uang_kas_db


def test_pemasukan_isolasi(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]

    id_a = pemasukan_db.tambah_pemasukan("2026-07-01", "Modal Tambahan", "suntik modal", 500000,
                                          tenant_id=tenant_a)
    id_b = pemasukan_db.tambah_pemasukan("2026-07-01", "Modal Tambahan", "suntik modal", 700000,
                                          tenant_id=tenant_b)

    list_a = pemasukan_db.get_pemasukan_list(tenant_id=tenant_a)
    list_b = pemasukan_db.get_pemasukan_list(tenant_id=tenant_b)
    assert len(list_a) == 1 and list_a[0]["id"] == id_a
    assert len(list_b) == 1 and list_b[0]["id"] == id_b
    assert pemasukan_db.get_pemasukan(id_a)["tenant_id"] == tenant_a

    client, headers_b = two_tenants["client"], two_tenants["headers_b"]
    assert client.get(f"/api/pemasukan/{id_a}", headers=headers_b).status_code == 404
    headers_a = two_tenants["headers_a"]
    assert client.get(f"/api/pemasukan/{id_a}", headers=headers_a).status_code == 200


def test_uang_kas_saldo_per_tenant(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]

    uang_kas_db.set_saldo_awal(1000000, "ownerA", tenant_id=tenant_a)
    uang_kas_db.set_saldo_awal(2000000, "ownerB", tenant_id=tenant_b)

    saldo_a = uang_kas_db.get_saldo_awal(tenant_a)
    saldo_b = uang_kas_db.get_saldo_awal(tenant_b)
    assert saldo_a["saldo"] == 1000000
    assert saldo_b["saldo"] == 2000000
    # Konvensi "id = tenant_id" (bukan lagi satu baris global id=1).
    assert saldo_a["id"] == tenant_a
    assert saldo_b["id"] == tenant_b

    uang_kas_db.tambah_penyesuaian("2026-07-05", "tambah", 100000, dibuat_oleh="ownerA", tenant_id=tenant_a)
    uang_kas_db.tambah_penyesuaian("2026-07-05", "kurang", 50000, dibuat_oleh="ownerB", tenant_id=tenant_b)

    assert uang_kas_db.get_saldo_kas(tenant_a) == 1100000
    assert uang_kas_db.get_saldo_kas(tenant_b) == 1950000
    assert len(uang_kas_db.get_penyesuaian_list(tenant_id=tenant_a)) == 1
    assert len(uang_kas_db.get_penyesuaian_list(tenant_id=tenant_b)) == 1

    client, headers_a, headers_b = two_tenants["client"], two_tenants["headers_a"], two_tenants["headers_b"]
    r = client.get("/api/uang-kas/saldo-awal", headers=headers_a)
    assert r.status_code == 200 and r.json()["saldo"] == 1000000
    r = client.get("/api/uang-kas/saldo-awal", headers=headers_b)
    assert r.status_code == 200 and r.json()["saldo"] == 2000000

    penyesuaian_id_a = uang_kas_db.get_penyesuaian_list(tenant_id=tenant_a)[0]["id"]
    assert client.get(f"/api/uang-kas/{penyesuaian_id_a}", headers=headers_b).status_code == 404
    assert client.delete(f"/api/uang-kas/{penyesuaian_id_a}", headers=headers_b).status_code == 404


def test_tenant_baru_dapat_saldo_awal_sendiri(app_client):
    """Tenant baru yang dibuat setelah tenant lain sudah punya saldo kas
    HARUS mulai dari 0, bukan mewarisi/bentrok dengan baris tenant lain
    (regresi desain 'id = tenant_id' menggantikan baris global id=1 lama)."""
    import tenant_db

    tenant_lama = tenant_db.buat_tenant("toko-lama", "Toko Lama")
    uang_kas_db.set_saldo_awal(5000000, "owner", tenant_id=tenant_lama)

    tenant_baru = tenant_db.buat_tenant("toko-baru", "Toko Baru")
    saldo_baru = uang_kas_db.get_saldo_awal(tenant_baru)
    assert saldo_baru["saldo"] == 0
    assert saldo_baru["id"] == tenant_baru

    # Saldo tenant lama tidak boleh berubah gara-gara tenant baru diakses.
    assert uang_kas_db.get_saldo_awal(tenant_lama)["saldo"] == 5000000
