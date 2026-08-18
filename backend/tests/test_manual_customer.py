"""test_manual_customer.py — Input Data: Manual Customer (Waiting List / Booking)
=============================================================================
Cakupan: metode input KEDUA untuk Input Data (lihat manual_customer_db.py) --
Waiting List (nama saja, barber/service opsional, jam otomatis dari server),
Booking (nama + jam manual + barber & service wajib), aturan "satu tanggal
satu mode" (mencegah double counting dengan Input Barber lama), jam immutable,
Closing (hanya baris lengkap masuk Rekap lewat database.tambah_transaksi()
yang sama persis dipakai Input Barber, Waiting List belum lengkap tetap
histori), Closing tidak bisa dua kali, Closing TIDAK mengunci data (tetap
bisa dikoreksi/dihapus), Reset Semua Transaksi Hari Ini, dan isolasi tenant."""

import database as db


def _setup(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber MC", tenant_id=tenant_id)
    service_id = db.add_service("Potong MC", 30000, tenant_id=tenant_id)
    return tenant_id, barber_id, service_id


# ============================= Waiting List =============================

def test_waiting_list_hanya_nama_wajib_jam_otomatis(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    _setup(single_tenant)

    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-01", "nama_customer": "Budi", "jenis": "waiting_list",
    }, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nama_customer"] == "Budi"
    assert data["jenis"] == "waiting_list"
    assert data["barber_id"] is None
    assert data["service_ids"] == []
    assert data["jam"]  # terisi otomatis, format HH:MM
    assert len(data["jam"]) == 5


def test_waiting_list_nama_kosong_ditolak(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-01", "nama_customer": "   ", "jenis": "waiting_list",
    }, headers=headers)
    assert r.status_code == 422


# ============================= Booking =============================

def test_booking_wajib_jam_barber_service(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    # tanpa jam
    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-01", "nama_customer": "Andi", "jenis": "booking",
        "barber_id": barber_id, "service_ids": [service_id],
    }, headers=headers)
    assert r.status_code == 422

    # tanpa barber
    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-01", "nama_customer": "Andi", "jenis": "booking",
        "jam_booking": "14:00", "service_ids": [service_id],
    }, headers=headers)
    assert r.status_code == 422

    # tanpa service
    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-01", "nama_customer": "Andi", "jenis": "booking",
        "jam_booking": "14:00", "barber_id": barber_id,
    }, headers=headers)
    assert r.status_code == 422

    # lengkap -> sukses
    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-01", "nama_customer": "Andi", "jenis": "booking",
        "jam_booking": "14:00", "barber_id": barber_id, "service_ids": [service_id],
    }, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["jam"] == "14:00"
    assert data["nama_barber"] == "Barber MC"
    assert data["daftar_service"][0]["nama"] == "Potong MC"


def test_jam_tidak_bisa_diedit(single_tenant):
    """Rule jam immutable: PUT tidak punya field jam sama sekali -- kirim
    field lain (nama_customer) dan pastikan jam tetap sama."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-01", "nama_customer": "Citra", "jenis": "booking",
        "jam_booking": "09:30", "barber_id": barber_id, "service_ids": [service_id],
    }, headers=headers)
    entry_id = r.json()["id"]

    r2 = client.put(f"/api/manual-customer/transaksi/{entry_id}", json={"nama_customer": "Citra Updated"}, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["jam"] == "09:30"
    assert r2.json()["nama_customer"] == "Citra Updated"


# ============================= Satu tanggal satu mode =============================

def test_satu_tanggal_satu_mode_tolak_campur_manual_customer_lalu_barber(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-02", "nama_customer": "Dedi", "jenis": "waiting_list",
    }, headers=headers)
    assert r.status_code == 200, r.text

    r2 = client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-09-02", "barber_id": barber_id,
        "items": [{"service_id": service_id, "jumlah": 1}],
    }, headers=headers)
    assert r2.status_code == 422
    assert "satu metode" in r2.json()["detail"]


def test_satu_tanggal_satu_mode_tolak_campur_barber_lalu_manual_customer(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    r = client.post("/api/input-data/transaksi", json={
        "tanggal": "2026-09-03", "barber_id": barber_id,
        "items": [{"service_id": service_id, "jumlah": 1}],
    }, headers=headers)
    assert r.status_code == 200, r.text

    r2 = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-03", "nama_customer": "Eka", "jenis": "waiting_list",
    }, headers=headers)
    assert r2.status_code == 422
    assert "satu metode" in r2.json()["detail"]


def test_status_hari_endpoint(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    r = client.get("/api/manual-customer/status?tanggal=2026-09-04", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"mode": None, "status": None}

    client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-04", "nama_customer": "Fina", "jenis": "waiting_list",
    }, headers=headers)
    r2 = client.get("/api/manual-customer/status?tanggal=2026-09-04", headers=headers)
    assert r2.json() == {"mode": "manual_customer", "status": "open"}


# ============================= Closing =============================

def test_closing_hanya_proses_baris_lengkap_dan_tidak_dobel(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)
    tanggal = "2026-09-05"

    # Waiting List belum lengkap (tanpa barber/service) -- tetap histori.
    client.post("/api/manual-customer/transaksi", json={
        "tanggal": tanggal, "nama_customer": "Gita", "jenis": "waiting_list",
    }, headers=headers)
    # Booking lengkap -- akan masuk Rekap.
    client.post("/api/manual-customer/transaksi", json={
        "tanggal": tanggal, "nama_customer": "Hadi", "jenis": "booking",
        "jam_booking": "10:00", "barber_id": barber_id, "service_ids": [service_id],
    }, headers=headers)

    r = client.post(f"/api/manual-customer/close?tanggal={tanggal}", headers=headers)
    assert r.status_code == 200, r.text
    hasil = r.json()
    assert hasil["diproses"] == 1
    assert hasil["dilewati"] == 1

    # Rekap TIDAK bertambah kolom baru -- transaksi biasa via database.get_transaksi_list().
    daftar = db.get_transaksi_list(tahun=2026, bulan=9, tenant_id=tenant_id)
    assert len(daftar) == 1
    assert daftar[0]["tanggal"] == tanggal

    # Tidak bisa Closing dua kali.
    r2 = client.post(f"/api/manual-customer/close?tanggal={tanggal}", headers=headers)
    assert r2.status_code == 422
    assert "dua kali" in r2.json()["detail"]


def test_closing_tidak_mengunci_data_tetap_bisa_edit_hapus(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)
    tanggal = "2026-09-06"

    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": tanggal, "nama_customer": "Indra", "jenis": "booking",
        "jam_booking": "11:00", "barber_id": barber_id, "service_ids": [service_id],
    }, headers=headers)
    entry_id = r.json()["id"]

    client.post(f"/api/manual-customer/close?tanggal={tanggal}", headers=headers)

    # Masih boleh koreksi setelah Closing (klarifikasi eksplisit Owner).
    r2 = client.put(f"/api/manual-customer/transaksi/{entry_id}", json={"tips": 5000}, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["tips"] == 5000

    # Masih boleh hapus setelah Closing -- transaksi Rekap terkait ikut terhapus.
    r3 = client.delete(f"/api/manual-customer/transaksi/{entry_id}", headers=headers)
    assert r3.status_code == 200, r3.text
    daftar = db.get_transaksi_list(tahun=2026, bulan=9, tenant_id=tenant_id)
    assert not any(t["tanggal"] == tanggal for t in daftar)


def test_closing_tanpa_mode_manual_customer_ditolak(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.post("/api/manual-customer/close?tanggal=2026-09-07", headers=headers)
    assert r.status_code == 422


# ============================= Reset Semua Transaksi Hari Ini =============================

def test_reset_hari_menghapus_transaksi_dan_membuka_mode_baru(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)
    tanggal = "2026-09-08"

    client.post("/api/manual-customer/transaksi", json={
        "tanggal": tanggal, "nama_customer": "Joko", "jenis": "waiting_list",
    }, headers=headers)
    r_status = client.get(f"/api/manual-customer/status?tanggal={tanggal}", headers=headers)
    assert r_status.json()["mode"] == "manual_customer"

    r = client.post(f"/api/manual-customer/reset?tanggal={tanggal}", headers=headers)
    assert r.status_code == 200

    r_status2 = client.get(f"/api/manual-customer/status?tanggal={tanggal}", headers=headers)
    assert r_status2.json() == {"mode": None, "status": None}

    r_list = client.get(f"/api/manual-customer/transaksi?tanggal={tanggal}", headers=headers)
    assert r_list.json() == []

    # Mode Input Barber sekarang bebas dipilih untuk tanggal yang sama.
    r_barber = client.post("/api/input-data/transaksi", json={
        "tanggal": tanggal, "barber_id": barber_id,
        "items": [{"service_id": service_id, "jumlah": 1}],
    }, headers=headers)
    assert r_barber.status_code == 200, r_barber.text


def test_reset_hari_dengan_closing_ikut_menghapus_transaksi_rekap(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)
    tanggal = "2026-09-09"

    client.post("/api/manual-customer/transaksi", json={
        "tanggal": tanggal, "nama_customer": "Kiki", "jenis": "booking",
        "jam_booking": "13:00", "barber_id": barber_id, "service_ids": [service_id],
    }, headers=headers)
    client.post(f"/api/manual-customer/close?tanggal={tanggal}", headers=headers)
    assert len(db.get_transaksi_list(tahun=2026, bulan=9, tenant_id=tenant_id)) == 1

    r = client.post(f"/api/manual-customer/reset?tanggal={tanggal}", headers=headers)
    assert r.status_code == 200
    assert not any(t["tanggal"] == tanggal for t in db.get_transaksi_list(tahun=2026, bulan=9, tenant_id=tenant_id))


# ============================= Isolasi multi-tenant =============================

def test_isolasi_tenant_manual_customer(two_tenants):
    client = two_tenants["client"]
    headers_a, headers_b = two_tenants["headers_a"], two_tenants["headers_b"]
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = db.add_barber("Barber A", tenant_id=tenant_a)
    service_a = db.add_service("Service A", 20000, tenant_id=tenant_a)

    r = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-10", "nama_customer": "Lina", "jenis": "waiting_list",
    }, headers=headers_a)
    entry_id = r.json()["id"]

    # Tenant B tidak bisa lihat/edit/hapus data Tenant A (404, bukan 403).
    r_get = client.get("/api/manual-customer/transaksi?tanggal=2026-09-10", headers=headers_b)
    assert r_get.json() == []

    r_put = client.put(f"/api/manual-customer/transaksi/{entry_id}", json={"nama_customer": "Hacked"}, headers=headers_b)
    assert r_put.status_code == 404

    r_del = client.delete(f"/api/manual-customer/transaksi/{entry_id}", headers=headers_b)
    assert r_del.status_code == 404

    # Barber milik tenant lain tidak bisa dipakai untuk Booking tenant ini.
    r_booking = client.post("/api/manual-customer/transaksi", json={
        "tanggal": "2026-09-10", "nama_customer": "Mona", "jenis": "booking",
        "jam_booking": "10:00", "barber_id": barber_a, "service_ids": [service_a],
    }, headers=headers_b)
    assert r_booking.status_code == 422
