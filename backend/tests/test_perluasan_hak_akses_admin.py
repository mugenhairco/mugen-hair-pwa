"""test_perluasan_hak_akses_admin.py — Perluasan Hak Akses Admin (diminta Owner)
=============================================================================
Cakupan: 14 kode izin baru (permissions.py) yang menggerbang modul
operasional yang SEBELUMNYA staff ('Admin') selalu akses PENUH tanpa syarat
apa pun -- Booking (izin_booking_kelola/batalkan/pengaturan), Produk
(izin_produk_kelola/hapus), Pengeluaran (izin_pengeluaran_kelola/hapus),
Pemasukan (izin_pemasukan_kelola/hapus), Uang Kas (izin_uang_kas_kelola/
hapus), Data Non-Barber (izin_data_non_barber_kelola/hapus), Input Data /
Transaksi Harian (izin_input_data_kelola/hapus).

Pola test SAMA PERSIS test_attendance.py (izin_absensi_pengaturan/koreksi):
SATU endpoint representatif per kode izin (bukan seluruh endpoint yang
digerbang -- pola-nya identik untuk endpoint lain di modul yang sama),
membuktikan (1) default TRUE -- staff langsung bisa tanpa Owner mengatur
apa pun (grandfather, staff yang sudah pakai modul ini tidak tiba-tiba
terkunci), (2) Owner bisa mematikannya lewat PUT /hak-akses-admin -> staff
403 dengan pesan jelas, (3) Owner ('admin') SELALU lolos tanpa syarat
terlepas dari pengaturan izin apa pun (lihat auth.require_permission)."""

import database as db
import permissions


def _buat_staff(client, headers_owner, tenant_id, username="staff1", password="passwordS123"):
    import auth_db
    auth_db.tambah_user(username, password, role="staff", tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _matikan_izin(client, headers_owner, key: str):
    r = client.put("/api/pengaturan/hak-akses-admin", json={"izin": {key: False}}, headers=headers_owner)
    assert r.status_code == 200, r.text


# ============================= Default TRUE (grandfather) =============================

def test_semua_izin_baru_default_true(single_tenant):
    izin = permissions.get_all(tenant_id=single_tenant["tenant_id"])
    kunci_baru = [
        "izin_booking_kelola", "izin_booking_batalkan", "izin_booking_pengaturan",
        "izin_produk_kelola", "izin_produk_hapus",
        "izin_pengeluaran_kelola", "izin_pengeluaran_hapus",
        "izin_pemasukan_kelola", "izin_pemasukan_hapus",
        "izin_uang_kas_kelola", "izin_uang_kas_hapus",
        "izin_data_non_barber_kelola", "izin_data_non_barber_hapus",
        "izin_input_data_kelola", "izin_input_data_hapus",
    ]
    for key in kunci_baru:
        assert izin[key] is True, f"{key} harus default True (grandfather)"


# ============================= Booking =============================

def test_booking_kelola_off_403_lalu_owner_tetap_lolos(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Izin", tenant_id=tenant_id)
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_booking_kelola")

    body = {"barber_id": barber_id, "tanggal": "2026-09-01", "jam_mulai": "09:00", "jam_selesai": "10:00"}
    r_staff = client.post("/api/booking/closed-slot", json=body, headers=headers_staff)
    assert r_staff.status_code == 403
    assert r_staff.json()["detail"] == "Admin tidak punya izin untuk aksi ini. Hubungi Owner."

    r_owner = client.post("/api/booking/closed-slot", json=body, headers=headers)
    assert r_owner.status_code == 200, r_owner.text


def test_booking_batalkan_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_booking_batalkan")

    r = client.delete("/api/booking/riwayat", headers=headers_staff)
    assert r.status_code == 403


def test_booking_pengaturan_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_booking_pengaturan")

    r = client.put("/api/booking/payment-settings", json={"metode_aktif": ["transfer"]}, headers=headers_staff)
    assert r.status_code == 403


# ============================= Produk =============================

def test_produk_kelola_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_produk_kelola")

    r = client.post("/api/produk", json={"nama": "Pomade Izin", "harga_modal": 10000, "harga_jual": 20000},
                     headers=headers_staff)
    assert r.status_code == 403


def test_produk_hapus_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    produk_id = db.tambah_produk("Pomade Hapus", 10000, 20000, tenant_id=tenant_id)
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_produk_hapus")

    r = client.delete(f"/api/produk/{produk_id}", headers=headers_staff)
    assert r.status_code == 403


# ============================= Pengeluaran =============================

def test_pengeluaran_kelola_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_pengeluaran_kelola")

    body = {"tanggal": "2026-09-01", "kategori": "Lainnya", "keterangan": "Tes", "jumlah": 10000}
    r = client.post("/api/pengeluaran", json=body, headers=headers_staff)
    assert r.status_code == 403


def test_pengeluaran_hapus_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import pengeluaran_db
    pengeluaran_id = pengeluaran_db.tambah_pengeluaran(
        tanggal="2026-09-01", kategori="Lainnya", keterangan="Tes", jumlah=10000,
        barber_id=None, aktif=True, sumber_dana="kas", dibuat_oleh="owner1", tenant_id=tenant_id,
    )
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_pengeluaran_hapus")

    r = client.delete(f"/api/pengeluaran/{pengeluaran_id}", headers=headers_staff)
    assert r.status_code == 403


# ============================= Pemasukan =============================

def test_pemasukan_kelola_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_pemasukan_kelola")

    body = {"tanggal": "2026-09-01", "kategori": "Lainnya", "keterangan": "Tes", "jumlah": 10000}
    r = client.post("/api/pemasukan", json=body, headers=headers_staff)
    assert r.status_code == 403


def test_pemasukan_hapus_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import pemasukan_db
    pemasukan_id = pemasukan_db.tambah_pemasukan(
        tanggal="2026-09-01", kategori="Lainnya", keterangan="Tes", jumlah=10000,
        barber_id=None, aktif=True, tenant_id=tenant_id,
    )
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_pemasukan_hapus")

    r = client.delete(f"/api/pemasukan/{pemasukan_id}", headers=headers_staff)
    assert r.status_code == 403


# ============================= Uang Kas =============================

def test_uang_kas_kelola_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_uang_kas_kelola")

    r = client.put("/api/uang-kas/saldo-awal", json={"saldo": 500000}, headers=headers_staff)
    assert r.status_code == 403


def test_uang_kas_hapus_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import uang_kas_db
    penyesuaian_id = uang_kas_db.tambah_penyesuaian(
        tanggal="2026-09-01", jenis="tambah", jumlah=10000, keterangan="Tes",
        dibuat_oleh="owner1", tenant_id=tenant_id,
    )
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_uang_kas_hapus")

    r = client.delete(f"/api/uang-kas/{penyesuaian_id}", headers=headers_staff)
    assert r.status_code == 403


# ============================= Data Non-Barber =============================

def test_data_non_barber_kelola_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    karyawan_id = db.add_barber("Kasir Izin", jabatan="Kasir", tenant_id=tenant_id)
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_data_non_barber_kelola")

    body = {
        "barber_id": karyawan_id, "tanggal_mulai": "2026-09-01", "tanggal_selesai": "2026-09-01",
        "gaji_per_hari": 100000, "hari_masuk": 1,
    }
    r = client.post("/api/data-non-barber", json=body, headers=headers_staff)
    assert r.status_code == 403


def test_data_non_barber_hapus_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import data_non_barber_db
    karyawan_id = db.add_barber("Kasir Hapus", jabatan="Kasir", tenant_id=tenant_id)
    entry = data_non_barber_db.tambah_data_non_barber(
        karyawan_id, "2026-09-01", "2026-09-01", 100000, 1,
        dibuat_oleh="owner1", tenant_id=tenant_id,
    )
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_data_non_barber_hapus")

    r = client.delete(f"/api/data-non-barber/{entry['id']}", headers=headers_staff)
    assert r.status_code == 403


# ============================= Input Data / Transaksi =============================

def test_input_data_kelola_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Transaksi", tenant_id=tenant_id)
    service_id = db.add_service("Potong Izin", 50000, tenant_id=tenant_id)
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_input_data_kelola")

    body = {"tanggal": "2026-09-01", "barber_id": barber_id, "items": [{"service_id": service_id, "jumlah": 1}]}
    r = client.post("/api/input-data/transaksi", json=body, headers=headers_staff)
    assert r.status_code == 403


def test_input_data_hapus_off_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Transaksi Hapus", tenant_id=tenant_id)
    service_id = db.add_service("Potong Izin Hapus", 50000, tenant_id=tenant_id)
    transaksi_id = db.tambah_transaksi(
        tanggal="2026-09-01", barber_id=barber_id, items=[{"service_id": service_id, "jumlah": 1}],
        tips=0, catatan=None,
    )
    headers_staff = _buat_staff(client, headers, tenant_id)
    _matikan_izin(client, headers, "izin_input_data_hapus")

    r = client.delete(f"/api/input-data/transaksi/{transaksi_id}", headers=headers_staff)
    assert r.status_code == 403
