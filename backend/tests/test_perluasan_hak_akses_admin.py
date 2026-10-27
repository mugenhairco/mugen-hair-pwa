"""test_perluasan_hak_akses_admin.py — Perluasan Hak Akses Admin (diminta Owner)
=============================================================================
Cakupan: kode izin (permissions.py) yang menggerbang modul operasional yang
SEBELUMNYA staff ('Admin') selalu akses PENUH tanpa syarat apa pun --
Booking (izin_booking_closed_slot/hapus/payment_settings), Produk
(izin_produk_kelola/hapus), Pengeluaran (izin_pengeluaran_kelola/hapus),
Pemasukan (izin_pemasukan_kelola/hapus), Uang Kas (izin_uang_kas_kelola/
hapus), Data Non-Barber (izin_data_non_barber_kelola/hapus), Input Data /
Transaksi Harian (izin_input_data_kelola/hapus).

REVISI BESAR Hak Akses (hapus Role "Admin" bawaan/default, satu checklist
dropdown per menu/tab/sub-item -- lihat permissions.py::PERMISSION_TREE):
TIDAK ADA LAGI default TRUE (grandfather) untuk staff tanpa Role eksplisit
-- SETIAP Role baru mulai 100% kosong (fail-closed), termasuk SELURUH key
di file ini. Pola test SAMA PERSIS test_role_custom.py: Owner membuat Role
custom, staff WAJIB diberi custom_role_id-nya, lalu (1) TANPA izin
eksplisit staff selalu 403, (2) Owner mengaktifkan satu key lewat PUT
/user-roles/{id}/permissions -> staff baru boleh, (3) Owner ('admin')
SELALU lolos tanpa syarat terlepas dari isi Role apa pun (lihat
auth.require_permission)."""

import database as db


def _buat_role_dan_staff(client, headers_owner, tenant_id, nama_role="Kasir",
                          username="staff1", password="passwordS123"):
    import auth_db
    role = client.post("/api/pengaturan/user-roles", json={"nama": nama_role}, headers=headers_owner).json()
    auth_db.tambah_user(username, password, role="staff", tenant_id=tenant_id, custom_role_id=role["id"])
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    headers_staff = {"Authorization": f"Bearer {r.json()['token']}"}
    return role["id"], headers_staff


def _beri_izin(client, headers_owner, role_id: int, key: str):
    r = client.put(f"/api/pengaturan/user-roles/{role_id}/permissions",
                    json={"izin": {key: True}}, headers=headers_owner)
    assert r.status_code == 200, r.text


# ============================= Fail-closed (Role baru mulai kosong) =============================

def test_semua_izin_baru_default_false(single_tenant):
    """REVISI (hapus grandfather lama): Role baru TIDAK PERNAH mulai dengan
    izin apa pun menyala -- lihat test_permission_tree.py::test_role_baru_
    fail_closed_semua_false untuk versi generik (SELURUH key), di sini
    cukup dibuktikan untuk 14 key spesifik modul ini."""
    import permissions
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kosong"}, headers=headers).json()
    izin = permissions.get_all(role_id=role["id"])
    kunci = [
        "izin_booking_closed_slot", "izin_booking_hapus", "izin_booking_payment_settings",
        "izin_produk_kelola", "izin_produk_hapus",
        "izin_pengeluaran_kelola", "izin_pengeluaran_hapus",
        "izin_pemasukan_kelola", "izin_pemasukan_hapus",
        "izin_uang_kas_kelola", "izin_uang_kas_hapus",
        "izin_data_non_barber_kelola", "izin_data_non_barber_hapus",
        "izin_input_data_kelola", "izin_input_data_hapus",
    ]
    for key in kunci:
        assert izin[key] is False, f"{key} harus default False (fail-closed)"


# ============================= Booking =============================

def test_booking_closed_slot_tanpa_izin_403_lalu_owner_tetap_lolos(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Izin", tenant_id=tenant_id)
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    body = {"barber_id": barber_id, "tanggal": "2026-09-01", "jam_mulai": "09:00", "jam_selesai": "10:00"}
    r_staff = client.post("/api/booking/closed-slot", json=body, headers=headers_staff)
    assert r_staff.status_code == 403
    assert r_staff.json()["detail"] == "Admin tidak punya izin untuk aksi ini. Hubungi Owner."

    r_owner = client.post("/api/booking/closed-slot", json=body, headers=headers)
    assert r_owner.status_code == 200, r_owner.text

    _beri_izin(client, headers, role_id, "izin_booking_closed_slot")
    r_staff2 = client.post("/api/booking/closed-slot", json=body, headers=headers_staff)
    assert r_staff2.status_code == 200, r_staff2.text


def test_booking_hapus_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.delete("/api/booking/riwayat", headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_booking_hapus")
    r2 = client.delete("/api/booking/riwayat", headers=headers_staff)
    assert r2.status_code == 200, r2.text


# test_booking_payment_settings_tanpa_izin_403 DIHAPUS -- endpoint
# PUT /api/booking/payment-settings (Owner-side) sudah dihapus total dari
# routers/booking.py (PERMINTAAN Owner: payment settings sekarang dikelola
# PENUH oleh Superadmin per tenant, lihat routers/superadmin.py). Key izin
# "izin_booking_payment_settings" DIBIARKAN apa adanya di permissions.py
# (sekarang tidak menggerbang endpoint apa pun -- orphaned, bukan bug, lihat
# user_roles_db.py::migrasi_role_staff_default() yang masih mewarisi key
# ini untuk tenant lama) -- tidak dihapus di sini supaya tidak menyentuh
# migrasi itu di luar cakupan perbaikan test ini.


# ============================= Produk =============================

def test_produk_kelola_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.post("/api/produk", json={"nama": "Pomade Izin", "harga_modal": 10000, "harga_jual": 20000},
                     headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_produk_kelola")
    r2 = client.post("/api/produk", json={"nama": "Pomade Izin", "harga_modal": 10000, "harga_jual": 20000},
                      headers=headers_staff)
    assert r2.status_code == 200, r2.text


def test_produk_hapus_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    produk_id = db.tambah_produk("Pomade Hapus", 10000, 20000, tenant_id=tenant_id)
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.delete(f"/api/produk/{produk_id}", headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_produk_hapus")
    r2 = client.delete(f"/api/produk/{produk_id}", headers=headers_staff)
    assert r2.status_code == 200, r2.text


# ============================= Pengeluaran =============================

def test_pengeluaran_kelola_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import uang_kas_db
    uang_kas_db.set_saldo_awal(1_000_000, "owner1", tenant_id)
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    body = {"tanggal": "2026-09-01", "kategori": "Lainnya", "keterangan": "Tes", "jumlah": 10000}
    r = client.post("/api/pengeluaran", json=body, headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_pengeluaran_kelola")
    r2 = client.post("/api/pengeluaran", json=body, headers=headers_staff)
    assert r2.status_code == 200, r2.text


def test_pengeluaran_hapus_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import pengeluaran_db
    import uang_kas_db
    # BUGFIX (audit) uang_kas_db.tambah_penyesuaian() sekarang menolak
    # penyesuaian "kurang" yang membuat saldo kas jadi negatif -- saldo
    # awal tenant baru = 0, jadi Saldo Kas Awal diisi dulu supaya
    # pengeluaran sumber_dana="kas" di bawah ini (bukan fokus test ini,
    # murni butuh SATU baris pengeluaran untuk diuji hapus-nya) berhasil.
    uang_kas_db.set_saldo_awal(1_000_000, "owner1", tenant_id)
    pengeluaran_id = pengeluaran_db.tambah_pengeluaran(
        tanggal="2026-09-01", kategori="Lainnya", keterangan="Tes", jumlah=10000,
        barber_id=None, aktif=True, sumber_dana="kas", dibuat_oleh="owner1", tenant_id=tenant_id,
    )
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.delete(f"/api/pengeluaran/{pengeluaran_id}", headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_pengeluaran_hapus")
    r2 = client.delete(f"/api/pengeluaran/{pengeluaran_id}", headers=headers_staff)
    assert r2.status_code == 200, r2.text


# ============================= Pemasukan =============================

def test_pemasukan_kelola_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    body = {"tanggal": "2026-09-01", "kategori": "Lainnya", "keterangan": "Tes", "jumlah": 10000}
    r = client.post("/api/pemasukan", json=body, headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_pemasukan_kelola")
    r2 = client.post("/api/pemasukan", json=body, headers=headers_staff)
    assert r2.status_code == 200, r2.text


def test_pemasukan_hapus_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import pemasukan_db
    pemasukan_id = pemasukan_db.tambah_pemasukan(
        tanggal="2026-09-01", kategori="Lainnya", keterangan="Tes", jumlah=10000,
        barber_id=None, aktif=True, tenant_id=tenant_id,
    )
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.delete(f"/api/pemasukan/{pemasukan_id}", headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_pemasukan_hapus")
    r2 = client.delete(f"/api/pemasukan/{pemasukan_id}", headers=headers_staff)
    assert r2.status_code == 200, r2.text


# ============================= Uang Kas =============================

def test_uang_kas_kelola_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.put("/api/uang-kas/saldo-awal", json={"saldo": 500000}, headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_uang_kas_kelola")
    r2 = client.put("/api/uang-kas/saldo-awal", json={"saldo": 500000}, headers=headers_staff)
    assert r2.status_code == 200, r2.text


def test_uang_kas_hapus_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import uang_kas_db
    penyesuaian_id = uang_kas_db.tambah_penyesuaian(
        tanggal="2026-09-01", jenis="tambah", jumlah=10000, keterangan="Tes",
        dibuat_oleh="owner1", tenant_id=tenant_id,
    )
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.delete(f"/api/uang-kas/{penyesuaian_id}", headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_uang_kas_hapus")
    r2 = client.delete(f"/api/uang-kas/{penyesuaian_id}", headers=headers_staff)
    assert r2.status_code == 200, r2.text


# ============================= Data Non-Barber =============================

def test_data_non_barber_kelola_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    karyawan_id = db.add_barber("Kasir Izin", jabatan="Kasir", tenant_id=tenant_id)
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    body = {
        "barber_id": karyawan_id, "tanggal_mulai": "2026-09-01", "tanggal_selesai": "2026-09-01",
        "gaji_per_hari": 100000, "hari_masuk": 1,
    }
    r = client.post("/api/data-non-barber", json=body, headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_data_non_barber_kelola")
    r2 = client.post("/api/data-non-barber", json=body, headers=headers_staff)
    assert r2.status_code == 200, r2.text


def test_data_non_barber_hapus_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import data_non_barber_db
    karyawan_id = db.add_barber("Kasir Hapus", jabatan="Kasir", tenant_id=tenant_id)
    entry = data_non_barber_db.tambah_data_non_barber(
        karyawan_id, "2026-09-01", "2026-09-01", 100000, 1,
        dibuat_oleh="owner1", tenant_id=tenant_id,
    )
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.delete(f"/api/data-non-barber/{entry['id']}", headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_data_non_barber_hapus")
    r2 = client.delete(f"/api/data-non-barber/{entry['id']}", headers=headers_staff)
    assert r2.status_code == 200, r2.text


# ============================= Input Data / Transaksi =============================

def test_input_data_kelola_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Transaksi", tenant_id=tenant_id)
    service_id = db.add_service("Potong Izin", 50000, tenant_id=tenant_id)
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    body = {"tanggal": "2026-09-01", "barber_id": barber_id, "items": [{"service_id": service_id, "jumlah": 1}]}
    r = client.post("/api/input-data/transaksi", json=body, headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_input_data_kelola")
    r2 = client.post("/api/input-data/transaksi", json=body, headers=headers_staff)
    assert r2.status_code == 200, r2.text


def test_input_data_hapus_tanpa_izin_403(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Transaksi Hapus", tenant_id=tenant_id)
    service_id = db.add_service("Potong Izin Hapus", 50000, tenant_id=tenant_id)
    transaksi_id = db.tambah_transaksi(
        tanggal="2026-09-01", barber_id=barber_id, items=[{"service_id": service_id, "jumlah": 1}],
        tips=0, catatan=None,
    )
    role_id, headers_staff = _buat_role_dan_staff(client, headers, tenant_id)

    r = client.delete(f"/api/input-data/transaksi/{transaksi_id}", headers=headers_staff)
    assert r.status_code == 403

    _beri_izin(client, headers, role_id, "izin_input_data_hapus")
    r2 = client.delete(f"/api/input-data/transaksi/{transaksi_id}", headers=headers_staff)
    assert r2.status_code == 200, r2.text
