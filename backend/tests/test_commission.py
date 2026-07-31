"""Regresi bug Phase 1.1: hitung_komisi_service() sebelumnya selalu
membaca persentase_komisi milik tenant DEFAULT, bukan tenant transaksi
yang sedang dihitung -- lihat database.py::hitung_komisi_service()."""


def test_komisi_tenant_terpisah(two_tenants):
    import database

    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]

    database.set_setting("persentase_komisi", "40", tenant_id=tenant_a)
    database.set_setting("persentase_komisi", "55", tenant_id=tenant_b)

    barber_a = database.add_barber("Barber A", tenant_id=tenant_a)
    barber_b = database.add_barber("Barber B", tenant_id=tenant_b)
    service_a = database.add_service("Potong A", 100000, tenant_id=tenant_a)
    service_b = database.add_service("Potong B", 100000, tenant_id=tenant_b)

    assert database.hitung_komisi_service(100000, 0, tenant_id=tenant_a) == 40000
    assert database.hitung_komisi_service(100000, 0, tenant_id=tenant_b) == 55000

    tx_a = database.tambah_transaksi("2026-07-01", barber_a, [{"service_id": service_a, "jumlah": 1}])
    tx_b = database.tambah_transaksi("2026-07-01", barber_b, [{"service_id": service_b, "jumlah": 1}])

    assert database.get_transaksi(tx_a)["total_komisi"] == 40000
    assert database.get_transaksi(tx_b)["total_komisi"] == 55000

    # Batch path (get_transaksi_list -> _lengkapi_transaksi_batch) harus
    # menghasilkan angka yang SAMA dengan single-row path di atas.
    assert database.get_transaksi_list(tenant_id=tenant_a)[0]["total_komisi"] == 40000
    assert database.get_transaksi_list(tenant_id=tenant_b)[0]["total_komisi"] == 55000

    preview_a = database.hitung_preview_items([{"service_id": service_a, "jumlah": 1}], tenant_id=tenant_a)
    preview_b = database.hitung_preview_items([{"service_id": service_b, "jumlah": 1}], tenant_id=tenant_b)
    assert preview_a["total_komisi"] == 40000
    assert preview_b["total_komisi"] == 55000


def test_preview_menolak_service_tenant_lain(two_tenants):
    import database

    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    service_b = database.add_service("Potong B", 100000, tenant_id=tenant_b)

    preview = database.hitung_preview_items([{"service_id": service_b, "jumlah": 1}], tenant_id=tenant_a)
    assert preview["rincian"] == []
    assert preview["total_harga"] == 0
