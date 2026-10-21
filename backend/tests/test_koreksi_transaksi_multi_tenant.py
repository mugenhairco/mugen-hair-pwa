"""test_koreksi_transaksi_multi_tenant.py — Celah lintas-tenant di Koreksi Transaksi
=============================================================================
PERBAIKAN Owner (audit "celah atau hal yang tidak wajar"): POST
/api/input-data/transaksi (tambah_transaksi) SUDAH memverifikasi
`barber_id` yang diminta memang milik tenant pemanggil lewat
_resolve_barber_id() -- tapi PUT /api/input-data/transaksi/{id} (koreksi)
TIDAK PERNAH diberi pengecekan yang sama. Owner Tenant A bisa memindahkan
transaksi MILIKNYA SENDIRI ke barber_id milik Tenant B hanya dengan
menebak/menaikkan id, membuat transaksi itu (dan komisinya) ikut masuk ke
pembukuan/komisi/slip gaji Tenant B. Lihat routers/input_data.py::
koreksi_transaksi()."""

import database as db


def _setup_dua_tenant(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = db.add_barber("Barber A", tenant_id=tenant_a)
    barber_b = db.add_barber("Barber B", tenant_id=tenant_b)
    service_a = db.add_service("Potong A", 100000, tenant_id=tenant_a)
    return barber_a, barber_b, service_a


def test_koreksi_transaksi_ditolak_pindah_ke_barber_tenant_lain(two_tenants):
    client, headers_a = two_tenants["client"], two_tenants["headers_a"]
    barber_a, barber_b, service_a = _setup_dua_tenant(two_tenants)

    r_buat = client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-09-01", "barber_id": barber_a,
        "items": [{"service_id": service_a, "jumlah": 1}], "tips": 0,
    }, headers=headers_a)
    assert r_buat.status_code == 200, r_buat.text
    transaksi_id = r_buat.json()["id"]

    # Owner Tenant A mencoba memindahkan transaksinya SENDIRI ke barber_id
    # milik Tenant B (ditebak/dinaikkan) -- HARUS ditolak.
    r_koreksi = client.put(f"/api/input-data/transaksi/{transaksi_id}", json={
        "barber_id": barber_b,
    }, headers=headers_a)
    assert r_koreksi.status_code == 422, r_koreksi.text

    # Data tidak berubah -- transaksi TETAP milik barber_a.
    assert db.get_transaksi(transaksi_id)["barber_id"] == barber_a


def test_koreksi_transaksi_boleh_pindah_ke_barber_tenant_sendiri(two_tenants):
    client, headers_a = two_tenants["client"], two_tenants["headers_a"]
    tenant_a = two_tenants["tenant_a"]
    barber_a, barber_b, service_a = _setup_dua_tenant(two_tenants)
    barber_a2 = db.add_barber("Barber A2", tenant_id=tenant_a)

    r_buat = client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-09-02", "barber_id": barber_a,
        "items": [{"service_id": service_a, "jumlah": 1}], "tips": 0,
    }, headers=headers_a)
    transaksi_id = r_buat.json()["id"]

    r_koreksi = client.put(f"/api/input-data/transaksi/{transaksi_id}", json={
        "barber_id": barber_a2,
    }, headers=headers_a)
    assert r_koreksi.status_code == 200, r_koreksi.text
    assert db.get_transaksi(transaksi_id)["barber_id"] == barber_a2
