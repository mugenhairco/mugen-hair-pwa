"""Regresi fungsional Phase 1.1 (poin 4 permintaan hardening): memastikan
fitur yang SUDAH ADA (bukan isolasi lintas tenant, itu di
test_tenant_isolation_*.py) tetap berfungsi normal dalam SATU tenant
setelah seluruh perubahan tenant-aware. Satu alur end-to-end panjang
(bukan banyak test kecil) supaya urutan realistis (barber -> service ->
transaksi -> rekap -> dst) tetap terlihat jelas kalau ada yang gagal."""


def test_alur_lengkap_satu_tenant(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    # Feature Gating "export_pdf" (FONDASI Multi-Tenant Phase 4 lanjutan):
    # slip gaji PDF di bawah SEKARANG digerbang require_feature("export_pdf")
    # -- single_tenant sengaja TIDAK punya baris tenant_subscriptions (lihat
    # conftest.py), jadi tanpa baris ini akan 403. Tenant SUNGGUHAN selalu
    # dapat baris ini otomatis (routers/superadmin.py::buat_tenant()).
    import subscription_db
    subscription_db.create_default_subscription(single_tenant["tenant_id"])

    # --- Barbers & Services ---
    r = client.post("/api/pengaturan/barber", json={"nama": "Budi", "uang_harian": 50000}, headers=headers)
    assert r.status_code == 200, r.text
    barber_id = r.json()["id"]

    r = client.get("/api/pengaturan/barber", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.post("/api/pengaturan/service", json={"nama": "Potong Rambut", "harga": 50000, "modal": 5000},
                     headers=headers)
    assert r.status_code == 200, r.text
    service_id = r.json()["id"]

    r = client.put("/api/pengaturan/komisi", json={
        "persentase_komisi": 40, "maksimal_hari_libur_bonus_customer": 4,
        "potongan_bonus_customer_persen": 25,
    }, headers=headers)
    assert r.status_code == 200, r.text

    # --- Preview & Transaksi (komisi = (50000-5000)*40% = 18000) ---
    r = client.post("/api/input-data/preview", json={"items": [{"service_id": service_id, "jumlah": 1}]},
                     headers=headers)
    assert r.status_code == 200 and r.json()["total_komisi"] == 18000, r.text

    r = client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-07-15", "barber_id": barber_id, "tips": 10000,
        "items": [{"service_id": service_id, "jumlah": 1}],
    }, headers=headers)
    assert r.status_code == 200, r.text

    r = client.get("/api/input-data/transaksi?tahun=2026&bulan=7", headers=headers)
    assert r.status_code == 200 and r.json()[0]["total_komisi"] == 18000, r.text

    # --- Rekap & Dashboard ---
    assert client.get("/api/rekap/transaksi?tahun=2026&bulan=7", headers=headers).status_code == 200
    assert client.get("/api/rekap/bulanan?tahun=2026&bulan=7", headers=headers).status_code == 200
    assert client.get("/api/dashboard/owner?tahun=2026&bulan=7", headers=headers).status_code == 200

    # --- Pengeluaran ---
    # BUGFIX (audit) uang_kas_db.tambah_penyesuaian() sekarang menolak
    # penyesuaian "kurang" yang membuat saldo kas jadi negatif -- saldo
    # awal tenant baru = 0, jadi Saldo Kas Awal diisi dulu supaya
    # pengeluaran sumber_dana="kas" (default) di bawah ini berhasil.
    r = client.put("/api/uang-kas/saldo-awal", json={"saldo": 1_000_000}, headers=headers)
    assert r.status_code == 200, r.text
    r = client.post("/api/pengeluaran", json={
        "tanggal": "2026-07-15", "kategori": "Operasional", "keterangan": "Beli sabun", "jumlah": 20000,
    }, headers=headers)
    assert r.status_code == 200, r.text
    pengeluaran_id = r.json()["id"]
    assert len(client.get("/api/pengeluaran", headers=headers).json()) == 1
    r = client.put(f"/api/pengeluaran/{pengeluaran_id}", json={
        "tanggal": "2026-07-15", "kategori": "Operasional", "keterangan": "Beli sabun (koreksi)",
        "jumlah": 25000,
    }, headers=headers)
    assert r.status_code == 200, r.text

    # --- Produk ---
    r = client.post("/api/produk", json={"nama": "Pomade", "harga_modal": 20000, "harga_jual": 35000},
                     headers=headers)
    assert r.status_code == 200, r.text
    produk_id = r.json()["id"]
    assert client.post(f"/api/produk/{produk_id}/restock", json={"tanggal": "2026-07-15", "jumlah": 10},
                        headers=headers).status_code == 200
    assert client.post(f"/api/produk/{produk_id}/jual", json={"tanggal": "2026-07-16", "jumlah": 2},
                        headers=headers).status_code == 200
    assert len(client.get("/api/produk", headers=headers).json()) == 1

    # --- Kasbon / Reimburse / Komisi / Izin Cuti / Slip Gaji ---
    r = client.post("/api/kasbon", json={"barber_id": barber_id, "tanggal": "2026-07-01", "jumlah": 100000},
                     headers=headers)
    assert r.status_code == 200, r.text
    kasbon_id = r.json()["id"]
    assert client.post(f"/api/kasbon/{kasbon_id}/pembayaran",
                        json={"tanggal": "2026-07-10", "jumlah": 50000}, headers=headers).status_code == 200

    r = client.post("/api/reimburse", json={"barber_id": barber_id, "tanggal": "2026-07-01",
                                             "kategori": "Transportasi", "nominal": 15000}, headers=headers)
    assert r.status_code == 200, r.text
    reimburse_id = r.json()["id"]
    assert client.put(f"/api/reimburse/{reimburse_id}/status", json={"status": "disetujui"},
                       headers=headers).status_code == 200

    assert client.post("/api/komisi/penyesuaian", json={
        "barber_id": barber_id, "tahun": 2026, "bulan": 7, "jenis": "bonus", "jumlah": 5000,
        "keterangan": "test",
    }, headers=headers).status_code == 200

    assert client.post("/api/izin-cuti", json={
        "barber_id": barber_id, "jenis": "cuti", "tanggal_mulai": "2026-08-01",
        "tanggal_selesai": "2026-08-02", "alasan": "liburan",
    }, headers=headers).status_code == 200

    r = client.post("/api/slip-gaji", json={"barber_id": barber_id, "tahun": 2026, "bulan": 7,
                                             "gaji_pokok": 1000000}, headers=headers)
    assert r.status_code == 200, r.text
    slip_id = r.json()["id"]
    r = client.get(f"/api/slip-gaji/{slip_id}/pdf", headers=headers)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"

    # --- Pemasukan / Uang Kas ---
    assert client.post("/api/pemasukan", json={
        "tanggal": "2026-07-01", "kategori": "Modal Tambahan", "keterangan": "suntik modal",
        "jumlah": 500000,
    }, headers=headers).status_code == 200

    assert client.put("/api/uang-kas/saldo-awal", json={"saldo": 1000000}, headers=headers).status_code == 200
    r = client.get("/api/uang-kas/saldo", headers=headers)
    # 1000000 (saldo awal) - 25000 (kas_penyesuaian otomatis dari koreksi
    # pengeluaran sumber_dana='kas' di atas) = 975000 -- perilaku BENAR.
    assert r.status_code == 200 and r.json()["saldo"] == 975000, r.text

    # --- Data Non-Barber ---
    r = client.post("/api/pengaturan/barber", json={"nama": "Kasir Ani", "jabatan": "kasir",
                                                      "gaji_per_hari": 100000}, headers=headers)
    assert r.status_code == 200, r.text
    kasir_id = r.json()["id"]
    assert client.post("/api/data-non-barber", json={
        "barber_id": kasir_id, "tanggal_mulai": "2026-07-01", "tanggal_selesai": "2026-07-15",
        "gaji_per_hari": 100000, "hari_masuk": 10,
    }, headers=headers).status_code == 200

    # --- Sanity seluruh endpoint PDF ---
    for url in [
        "/api/kasbon/pdf?tahun=2026&bulan=7",
        "/api/reimburse/pdf?tahun=2026&bulan=7",
        "/api/komisi/pdf?tahun=2026&bulan=7",
        "/api/izin-cuti/pdf",
        "/api/slip-gaji/pdf?tahun=2026&bulan=7",
        "/api/pemasukan/pdf?tahun=2026&bulan=7",
        "/api/uang-kas/pdf?tahun=2026&bulan=7",
        "/api/pengeluaran/pdf?tahun=2026&bulan=7",
        "/api/rekap/transaksi/pdf?tahun=2026&bulan=7",
        "/api/rekap/bulanan/pdf?tahun=2026&bulan=7",
    ]:
        r = client.get(url, headers=headers)
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf", (url, r.text[:200])
