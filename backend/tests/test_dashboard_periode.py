"""test_dashboard_periode.py — Dashboard Owner mode "Periode" (rentang
tanggal bebas, GET /api/dashboard/owner/periode) -- diminta Owner sebagai
alternatif mode "Bulanan" yang sudah ada (satu bulan kalender penuh).
Cakupan: (1) angka SAMA PERSIS dengan mode Bulanan kalau rentang yang
dipilih kebetulan pas satu bulan kalender penuh (rumus harus identik,
lihat get_ringkasan_semua_barber_periode() vs get_ringkasan_semua_barber_bulan()),
(2) rentang parsial (bukan satu bulan penuh) menghitung benar, (3) Bonus
Customer SENGAJA None (bukan 0) di seluruh respons karena keputusan
eksplisit Owner: nominalnya berdasar tier bulanan penuh, tidak berarti
untuk rentang bebas, (4) Laba Kotor mengikuti (tanpa suku Bonus Customer),
(5) staff tetap difilter sesuai hak akses, (6) isolasi tenant."""

import database as db


def _setup(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Periode", uang_harian=20000, tenant_id=tenant_id)
    service_id = db.add_service("Potong Periode", 50000, tenant_id=tenant_id)
    return tenant_id, barber_id, service_id


def test_periode_pas_satu_bulan_penuh_sama_dengan_mode_bulanan(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    for tgl in ("2026-09-01", "2026-09-15", "2026-09-30"):
        r = client.post("/api/input-data/transaksi", json={
            "tanggal": tgl, "barber_id": barber_id,
            "items": [{"service_id": service_id, "jumlah": 1}], "tips": 1000,
        }, headers=headers)
        assert r.status_code == 200, r.text

    r_bulanan = client.get("/api/dashboard/owner?tahun=2026&bulan=9", headers=headers)
    assert r_bulanan.status_code == 200, r_bulanan.text
    bulanan = r_bulanan.json()

    r_periode = client.get("/api/dashboard/owner/periode?tanggal_mulai=2026-09-01&tanggal_selesai=2026-09-30", headers=headers)
    assert r_periode.status_code == 200, r_periode.text
    periode = r_periode.json()

    assert periode["total_toko"]["nilai_service"] == bulanan["total_toko"]["nilai_service"]
    assert periode["total_toko"]["komisi"] == bulanan["total_toko"]["komisi"]
    assert periode["total_toko"]["tips"] == bulanan["total_toko"]["tips"]
    assert periode["total_toko"]["uang_harian"] == bulanan["total_toko"]["uang_harian"]
    assert periode["total_toko"]["jumlah_customer"] == bulanan["total_toko"]["jumlah_customer"]
    assert periode["rincian_service_semua_barber"] == bulanan["rincian_service_semua_barber"]
    assert periode["total_pengeluaran"] == bulanan["total_pengeluaran"]
    assert periode["penjualan_produk"] == bulanan["penjualan_produk"]


def test_periode_rentang_parsial_hanya_hitung_dalam_rentang(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-08-05", "barber_id": barber_id,
        "items": [{"service_id": service_id, "jumlah": 1}], "tips": 2000,
    }, headers=headers)
    client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-08-20", "barber_id": barber_id,
        "items": [{"service_id": service_id, "jumlah": 1}], "tips": 3000,
    }, headers=headers)

    r = client.get("/api/dashboard/owner/periode?tanggal_mulai=2026-08-01&tanggal_selesai=2026-08-10", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_toko"]["nilai_service"] == 50000
    assert data["total_toko"]["tips"] == 2000
    assert data["total_toko"]["jumlah_customer"] == 1


def test_periode_bonus_customer_selalu_none_dan_laba_kotor_tanpa_bonus(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    # Set tier Bonus Customer rendah supaya PASTI tercapai kalau (secara
    # keliru) mode Bulanan sempat dipakai untuk menghitungnya.
    db.set_bonus_customer_tiers([{"target": 1, "bonus": 99999}], tenant_id=tenant_id)
    client.put("/api/pengaturan/bonus-service-acuan", json={"service_ids": [service_id]}, headers=headers)

    client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-08-05", "barber_id": barber_id,
        "items": [{"service_id": service_id, "jumlah": 1}],
    }, headers=headers)

    r = client.get("/api/dashboard/owner/periode?tanggal_mulai=2026-08-01&tanggal_selesai=2026-08-10", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_toko"]["bonus_customer"] is None
    assert data["per_barber"][0]["bonus_customer"] is None
    assert data["per_barber"][0]["bonus_customer_detail"] is None
    # Laba Kotor TIDAK boleh diam-diam mengurangi bonus 99999 yang tidak pernah dihitung.
    assert data["laba_kotor"] == data["total_toko"]["nilai_service"] - data["total_toko"]["komisi"] - data["total_toko"]["uang_harian"] - data["total_pengeluaran"]


def test_periode_staff_tetap_difilter_hak_akses(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)
    import auth_db
    auth_db.tambah_user("staffperiode", "passwordS123", role="staff", tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "staffperiode", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}

    client.put("/api/pengaturan/hak-akses-admin", json={"izin": {"izin_dashboard_total_komisi": False}}, headers=headers)

    r = client.get("/api/dashboard/owner/periode?tanggal_mulai=2026-08-01&tanggal_selesai=2026-08-31", headers=headers_staff)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_toko"]["komisi"] is None
    assert data["per_barber"] == []  # rincian per-barber di luar cakupan Dashboard Admin


def test_periode_isolasi_tenant(two_tenants):
    client = two_tenants["client"]
    headers_a, headers_b = two_tenants["headers_a"], two_tenants["headers_b"]
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = db.add_barber("Barber A Periode", tenant_id=tenant_a)
    service_a = db.add_service("Service A Periode", 40000, tenant_id=tenant_a)

    client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-08-05", "barber_id": barber_a,
        "items": [{"service_id": service_a, "jumlah": 1}],
    }, headers=headers_a)

    r_b = client.get("/api/dashboard/owner/periode?tanggal_mulai=2026-08-01&tanggal_selesai=2026-08-31", headers=headers_b)
    assert r_b.status_code == 200, r_b.text
    assert r_b.json()["total_toko"]["nilai_service"] == 0
    assert r_b.json()["per_barber"] == []


def test_get_total_pengeluaran_rentang_tanggal(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.tambah_pengeluaran("2026-08-05", "Beli bahan", 15000, tenant_id=tenant_id)
    db.tambah_pengeluaran("2026-08-25", "Listrik", 25000, tenant_id=tenant_id)

    total = db.get_total_pengeluaran(tanggal_mulai="2026-08-01", tanggal_selesai="2026-08-10", tenant_id=tenant_id)
    assert total == 15000
    total_penuh = db.get_total_pengeluaran(tanggal_mulai="2026-08-01", tanggal_selesai="2026-08-31", tenant_id=tenant_id)
    assert total_penuh == 40000
