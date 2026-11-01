"""test_rekap_suntik_baris.py — FITUR "Rekap tidak refresh, cuma tambah baris
diam-diam" (PERMINTAAN Owner, pola sama Transaksi Hari Ini POS/Booking
Mandiri)
=============================================================================
Cakupan: database.py::get_rekap_transaksi_baris() (satu baris Rekap Transaksi
untuk satu transaksi yang baru dibuat, dipakai input_data.js menyuntik baris
baru TANPA fetch ulang seluruh daftar) HARUS menghasilkan nilai komisi/
pendapatan/uang_harian/keterangan yang SAMA PERSIS dengan baris yang sama di
get_rekap_transaksi_list() -- TIDAK ADA rumus terpisah yang bisa drift.
Endpoint GET /api/rekap/transaksi/baris/{id}: 404 untuk id tidak ada/beda
tenant, 403 untuk akun Barber yang bukan pemilik transaksinya."""

import database as db


def _siapkan_uang_harian(tenant_id, service_id, target=1):
    db.set_uang_harian_acuan_ids([service_id], tenant_id=tenant_id)
    db.set_setting("uang_harian_target_service_harian", str(target), tenant_id=tenant_id)


def test_get_rekap_transaksi_baris_sama_persis_dengan_baris_di_list(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Suntik Baris", uang_harian=60000, tenant_id=tenant_id)
    service_id = db.add_service("SB Dry Cut", 35000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, service_id)

    transaksi_id = db.tambah_transaksi("2026-08-04", barber_id, [{"service_id": service_id, "jumlah": 1}],
                                        tips=50000, catatan="Catatan uji")

    baris_tunggal = db.get_rekap_transaksi_baris(transaksi_id, tenant_id=tenant_id)
    daftar = db.get_rekap_transaksi_list(tahun=2026, bulan=8, barber_id=barber_id, tenant_id=tenant_id)
    assert len(daftar) == 1
    baris_dari_list = daftar[0]

    assert baris_tunggal == baris_dari_list
    assert baris_tunggal["komisi"] == 14000
    assert baris_tunggal["pendapatan"] == 14000 + 50000
    assert baris_tunggal["keterangan"] == "Catatan uji"


def test_get_rekap_transaksi_baris_id_tidak_ada_return_none(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    assert db.get_rekap_transaksi_baris(999999, tenant_id=tenant_id) is None


def test_get_rekap_transaksi_baris_tenant_lain_return_none(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_id = db.add_barber("Milik Tenant A", tenant_id=tenant_a)
    service_id = db.add_service("Service Tenant A", 20000, tenant_id=tenant_a)
    transaksi_id = db.tambah_transaksi("2026-08-05", barber_id, [{"service_id": service_id, "jumlah": 1}])

    assert db.get_rekap_transaksi_baris(transaksi_id, tenant_id=tenant_b) is None
    assert db.get_rekap_transaksi_baris(transaksi_id, tenant_id=tenant_a) is not None


def test_endpoint_rekap_transaksi_baris_404_untuk_id_tidak_ada(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/rekap/transaksi/baris/999999", headers=headers)
    assert r.status_code == 404


def test_endpoint_rekap_transaksi_baris_sukses(single_tenant):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    barber_id = db.add_barber("Suntik Endpoint", tenant_id=tenant_id)
    service_id = db.add_service("SE Service", 25000, tenant_id=tenant_id)
    transaksi_id = db.tambah_transaksi("2026-08-06", barber_id, [{"service_id": service_id, "jumlah": 1}])

    r = client.get(f"/api/rekap/transaksi/baris/{transaksi_id}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == transaksi_id
    assert data["tipe"] == "transaksi"
    assert data["barber_id"] == barber_id
