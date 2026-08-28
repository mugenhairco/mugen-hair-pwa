"""test_hak_akses_menu.py — AUDIT Hak Akses User / Kelola Izin (permintaan
Owner): setiap menu sidebar sekarang punya SATU level -- "Tidak Ada Akses"/
"Baca"/"Baca & Edit" -- dibangun DI ATAS katalog izin_* yang sudah ada
(permissions.py::MENU_DEFS/get_menu_level/set_menu_level/get_all_menu_levels/
set_all_menu_levels), BUKAN sistem penyimpanan baru. Cakupan:
- Fungsi murni MENU_DEFS/get_menu_level/set_menu_level/get_all_menu_levels/
  set_all_menu_levels (permissions.py).
- Endpoint HTTP baru: GET /hak-akses-admin membawa field "menu", PUT
  /hak-akses-admin-menu, GET/PUT /user-roles/{id}/menu-permissions.
- Penegakan BACKEND (bukan cuma UI) di endpoint GET yang SEBELUMNYA selalu
  terbuka untuk staff (Booking/Input Data/Produk/Pengeluaran/Pemasukan/
  Uang Kas/Dashboard/Rekap/Riwayat Transaksi) -- sekarang menolak staff
  dengan level "Tidak Ada Akses" walau dipanggil LANGSUNG (bukan lewat UI).
- Modul Karyawan (Kasbon/Komisi/Slip Gaji/Reimburse/Izin Cuti): level "Baca"
  SEKARANG cukup untuk GET (sebelumnya HARUS izin tulis untuk bisa lihat
  sama sekali), level "Baca" tetap menolak endpoint tulis.
- Skenario POS 2 (contoh eksplisit Owner): Absensi=Baca & Edit, Rekap=Baca,
  menu lain=Tidak Ada Akses -- dites end-to-end lewat Role Custom.
- Owner ('admin') SELALU lolos tanpa syarat, Barber TIDAK terpengaruh sama
  sekali (di luar sistem izin_* ini, lihat auth.py::require_menu_read())."""

import auth_db
import permissions
import user_roles_db


def _buat_owner_dan_login(client, tenant_id, username="ownermenu", password="passwordO123"):
    auth_db.tambah_user(username, password, role="admin", tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_staff_dan_login(client, tenant_id, username="staffmenu", password="passwordS123", custom_role_id=None):
    auth_db.tambah_user(username, password, role="staff", tenant_id=tenant_id, custom_role_id=custom_role_id)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_barber_dan_login(client, tenant_id, barber_id, username="barbermenu", password="passwordB123"):
    auth_db.tambah_user(username, password, role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------------------------------------------------------------------------
# permissions.py -- fungsi murni MENU_DEFS/get_menu_level/set_menu_level
# ---------------------------------------------------------------------------

def test_menu_defs_lengkap_16_menu():
    # 15 menu asli + "settlement_faspay" (fitur Settlement Faspay per
    # Terminal/Tenant, ditambah belakangan lewat pola MENU_DEFS yang sama).
    assert len(permissions.MENU_DEFS) == 16
    assert "setting" not in permissions.MENU_DEFS  # di luar cakupan (delegasi tab sendiri)
    assert "billing" not in permissions.MENU_DEFS  # selalu Owner-murni


def test_get_menu_level_default_sesuai_katalog(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    # Belum pernah diatur Owner -- default dari PERMISSION_DEFS. Booking
    # SEKARANG "read" (bukan "write") karena izin_booking_hapus (kemampuan
    # BARU, Hapus Booking Permanen) default False -- SENGAJA, beda dari
    # ketiga write_keys booking lain yang default True (lihat catatan
    # izin_booking_hapus di permissions.py). "write" butuh SEMUA write_keys
    # true, jadi default sekarang efektif "read".
    assert permissions.get_menu_level("booking", tenant_id=tenant_id) == "read"
    # Kasbon default False untuk semua key -- "Tidak Ada Akses".
    assert permissions.get_menu_level("kasbon", tenant_id=tenant_id) == "none"


def test_set_menu_level_none_mematikan_baca_dan_tulis(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("booking", "none", tenant_id=tenant_id)
    assert permissions.get_menu_level("booking", tenant_id=tenant_id) == "none"
    izin = permissions.get_all(tenant_id=tenant_id)
    assert izin["izin_booking_lihat"] is False
    assert izin["izin_booking_kelola"] is False
    assert izin["izin_booking_batalkan"] is False
    assert izin["izin_booking_hapus"] is False
    assert izin["izin_booking_pengaturan"] is False


def test_set_menu_level_read_hanya_nyalakan_baca(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("kasbon", "read", tenant_id=tenant_id)
    assert permissions.get_menu_level("kasbon", tenant_id=tenant_id) == "read"
    izin = permissions.get_all(tenant_id=tenant_id)
    assert izin["izin_kasbon_lihat"] is True
    assert izin["izin_kasbon"] is False  # write key TIDAK ikut nyala


def test_set_menu_level_write_nyalakan_semua_key_tulis(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("uang_kas", "write", tenant_id=tenant_id)
    assert permissions.get_menu_level("uang_kas", tenant_id=tenant_id) == "write"
    izin = permissions.get_all(tenant_id=tenant_id)
    assert izin["izin_uang_kas_lihat"] is True
    assert izin["izin_uang_kas_kelola"] is True
    assert izin["izin_uang_kas_hapus"] is True


def test_get_menu_level_sebagian_key_tulis_nyala_tanpa_lihat_tetap_dianggap_baca(single_tenant):
    """Data lama/kombinasi tidak biasa: SEBAGIAN key tulis True (bukan
    SEMUA) dan key baca eksplisit False -- tetap dianggap MINIMAL "read"
    (tulis tanpa bisa baca tidak masuk akal). Booking dipakai di sini karena
    punya 4 key tulis (kelola/batalkan/hapus/pengaturan) -- perlu SEBAGIAN
    saja true supaya "write" (butuh SEMUA true) tidak ikut terpicu."""
    tenant_id = single_tenant["tenant_id"]
    permissions.set_bulk({
        "izin_booking_lihat": False,
        "izin_booking_kelola": True,
        "izin_booking_batalkan": False,
        "izin_booking_pengaturan": False,
    }, tenant_id=tenant_id)
    assert permissions.get_menu_level("booking", tenant_id=tenant_id) == "read"


def test_get_all_menu_levels_menu_tanpa_write_keys_dashboard_rekap(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("dashboard", "write", tenant_id=tenant_id)
    # dashboard/rekap tidak punya write_keys -- level "write" TETAP "read"
    # secara efektif (tidak ada apa pun buat "diedit" di sana).
    assert permissions.get_menu_level("dashboard", tenant_id=tenant_id) == "read"


def test_set_all_menu_levels_bulk(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    hasil = permissions.set_all_menu_levels(
        {"absensi": "write", "rekap": "read", "booking": "none"}, tenant_id=tenant_id,
    )
    assert hasil["absensi"] == "write"
    assert hasil["rekap"] == "read"
    assert hasil["booking"] == "none"


def test_set_all_menu_levels_menu_tidak_dikenal_ditolak(single_tenant):
    import pytest
    tenant_id = single_tenant["tenant_id"]
    with pytest.raises(ValueError):
        permissions.set_all_menu_levels({"menu_tidak_ada": "write"}, tenant_id=tenant_id)


def test_role_custom_mulai_kosong_semua_none(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    role = user_roles_db.create_role(tenant_id, "Role Kosong")
    levels = permissions.get_all_menu_levels(role_id=role["id"])
    assert all(v == "none" for v in levels.values())


# ---------------------------------------------------------------------------
# Endpoint HTTP baru
# ---------------------------------------------------------------------------

def test_endpoint_hak_akses_admin_membawa_field_menu(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/pengaturan/hak-akses-admin", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "menu" in data
    assert set(data["menu"].keys()) == set(permissions.MENU_DEFS.keys())


def test_endpoint_put_hak_akses_admin_menu(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.put("/api/pengaturan/hak-akses-admin-menu", json={"menu": {"kasbon": "write"}}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["kasbon"] == "write"
    assert permissions.get_menu_level("kasbon", tenant_id=single_tenant["tenant_id"]) == "write"


def test_endpoint_put_hak_akses_admin_menu_staff_ditolak(single_tenant):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    headers_staff = _buat_staff_dan_login(client, tenant_id)
    r = client.put("/api/pengaturan/hak-akses-admin-menu", json={"menu": {"kasbon": "write"}}, headers=headers_staff)
    assert r.status_code == 403


def test_endpoint_role_custom_menu_permissions_get_put(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    role = client.post("/api/pengaturan/user-roles", json={"nama": "Kasir"}, headers=headers).json()
    # GET /permissions (endpoint LAMA, dipakai UI baru juga) sekarang
    # membawa "menu" -- TIDAK ADA endpoint GET /menu-permissions terpisah
    # (hanya PUT, lihat routers/pengaturan.py).
    r_get = client.get(f"/api/pengaturan/user-roles/{role['id']}/permissions", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["menu"]["booking"] == "none"  # Role Custom mulai kosong

    r_put = client.put(f"/api/pengaturan/user-roles/{role['id']}/menu-permissions",
                        json={"menu": {"absensi": "write", "rekap": "read"}}, headers=headers)
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["absensi"] == "write"
    assert r_put.json()["rekap"] == "read"

    r_get2 = client.get(f"/api/pengaturan/user-roles/{role['id']}/permissions", headers=headers)
    assert r_get2.json()["menu"]["absensi"] == "write"
    assert r_get2.json()["menu"]["rekap"] == "read"


# ---------------------------------------------------------------------------
# Penegakan BACKEND -- modul Pattern A (GET SEBELUMNYA selalu terbuka)
# ---------------------------------------------------------------------------

def test_staff_tanpa_akses_booking_ditolak_get_langsung(single_tenant):
    """Backend HARUS menolak walau dipanggil LANGSUNG (bukan lewat UI) --
    inti permintaan Owner poin #6."""
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("booking", "none", tenant_id=tenant_id)
    headers_staff = _buat_staff_dan_login(client, tenant_id, username="staffbooking")

    r = client.get("/api/booking", headers=headers_staff)
    assert r.status_code == 403


def test_staff_baca_booking_bisa_get_tapi_verifikasi_ditolak(single_tenant):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("booking", "read", tenant_id=tenant_id)
    headers_staff = _buat_staff_dan_login(client, tenant_id, username="staffbookingread")

    r_get = client.get("/api/booking", headers=headers_staff)
    assert r_get.status_code == 200

    import database as db
    barber_id = db.add_barber("Barber HAM", tenant_id=tenant_id)
    service_id = db.add_service("Service HAM", 50000, tenant_id=tenant_id)
    from datetime import timedelta
    from booking_db import _hari_ini_wib
    import booking_db
    booking_db.update_payment_settings(metode_aktif=["transfer"], tenant_id=tenant_id)
    booking = booking_db.buat_booking(
        barber_id=barber_id, tanggal=(_hari_ini_wib() + timedelta(days=1)).isoformat(), jam_mulai="10:00",
        service_ids=[service_id], customer_nama="Rudi", customer_whatsapp="081234567895",
        metode_pembayaran="transfer", tenant_id=tenant_id,
    )
    r_verif = client.post(f"/api/booking/{booking['id']}/verifikasi", headers=headers_staff)
    assert r_verif.status_code == 403


def test_staff_write_booking_bisa_verifikasi(single_tenant, monkeypatch):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp", lambda *a, **kw: True)
    permissions.set_menu_level("booking", "write", tenant_id=tenant_id)
    headers_staff = _buat_staff_dan_login(client, tenant_id, username="staffbookingwrite")

    import database as db
    barber_id = db.add_barber("Barber HAM2", tenant_id=tenant_id)
    service_id = db.add_service("Service HAM2", 50000, tenant_id=tenant_id)
    from datetime import timedelta
    from booking_db import _hari_ini_wib
    import booking_db
    booking_db.update_payment_settings(metode_aktif=["transfer"], tenant_id=tenant_id)
    booking = booking_db.buat_booking(
        barber_id=barber_id, tanggal=(_hari_ini_wib() + timedelta(days=1)).isoformat(), jam_mulai="10:00",
        service_ids=[service_id], customer_nama="Sinta", customer_whatsapp="081234567896",
        metode_pembayaran="transfer", tenant_id=tenant_id,
    )
    r_verif = client.post(f"/api/booking/{booking['id']}/verifikasi", headers=headers_staff)
    assert r_verif.status_code == 200, r_verif.text


def test_staff_tanpa_akses_rekap_ditolak(single_tenant):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("rekap", "none", tenant_id=tenant_id)
    headers_staff = _buat_staff_dan_login(client, tenant_id, username="staffrekap")
    r = client.get("/api/rekap/transaksi", headers=headers_staff)
    assert r.status_code == 403


def test_barber_akses_rekap_tidak_terpengaruh_menu_staff(single_tenant):
    """Barber TIDAK ikut sistem izin_* ini sama sekali -- level menu "Rekap"
    diatur "none" untuk staff TIDAK mempengaruhi Barber sama sekali."""
    client = single_tenant["client"]
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("rekap", "none", tenant_id=tenant_id)
    import database as db
    barber_id = db.add_barber("Barber Rekap HAM", tenant_id=tenant_id)
    headers_barber = _buat_barber_dan_login(client, tenant_id, barber_id)
    r = client.get("/api/rekap/transaksi", headers=headers_barber)
    assert r.status_code == 200


def test_owner_selalu_lolos_walau_menu_none(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("booking", "none", tenant_id=tenant_id)
    permissions.set_menu_level("produk", "none", tenant_id=tenant_id)
    assert client.get("/api/booking", headers=headers).status_code == 200
    assert client.get("/api/produk", headers=headers).status_code == 200


# ---------------------------------------------------------------------------
# Penegakan BACKEND -- modul Pattern B (Karyawan: satu key dulu gerbang baca+tulis)
# ---------------------------------------------------------------------------

def test_staff_baca_kasbon_bisa_lihat_tapi_tidak_bisa_tambah(single_tenant):
    """SEBELUM revisi ini: staff HARUS izin_kasbon (write) untuk bisa lihat
    sama sekali. SEKARANG: level "Baca" (izin_kasbon_lihat) cukup untuk GET,
    endpoint tulis tetap ditolak."""
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("kasbon", "read", tenant_id=tenant_id)
    headers_staff = _buat_staff_dan_login(client, tenant_id, username="staffkasbonread")

    r_get = client.get("/api/kasbon", headers=headers_staff)
    assert r_get.status_code == 200

    import database as db
    barber_id = db.add_barber("Barber Kasbon HAM", tenant_id=tenant_id)
    r_post = client.post("/api/kasbon", json={
        "barber_id": barber_id, "tanggal": "2026-08-01", "jumlah": 100000, "keterangan": "test",
    }, headers=headers_staff)
    assert r_post.status_code == 403


def test_staff_tanpa_akses_kasbon_ditolak_get(single_tenant):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("kasbon", "none", tenant_id=tenant_id)
    headers_staff = _buat_staff_dan_login(client, tenant_id, username="staffkasbonnone")
    r = client.get("/api/kasbon", headers=headers_staff)
    assert r.status_code == 403


def test_barber_akses_kasbon_sendiri_tidak_terpengaruh(single_tenant):
    client = single_tenant["client"]
    tenant_id = single_tenant["tenant_id"]
    permissions.set_menu_level("kasbon", "none", tenant_id=tenant_id)
    import database as db
    barber_id = db.add_barber("Barber Kasbon Sendiri", tenant_id=tenant_id)
    headers_barber = _buat_barber_dan_login(client, tenant_id, barber_id, username="barberkasbon")
    r = client.get("/api/kasbon", headers=headers_barber)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Skenario POS 2 (contoh eksplisit Owner, spek item #5)
# ---------------------------------------------------------------------------

def test_skenario_pos2_absensi_edit_rekap_baca_lainnya_tidak_ada_akses(single_tenant):
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]

    role = user_roles_db.create_role(tenant_id, "POS 2")
    permissions.set_all_menu_levels(
        {"absensi": "write", "rekap": "read"}, role_id=role["id"],
    )  # menu lain otomatis tetap "none" (Role Custom mulai kosong)
    headers_pos2 = _buat_staff_dan_login(client, tenant_id, username="pos2user", custom_role_id=role["id"])

    # Absensi -> Baca & Edit: dashboard-nya (view) boleh.
    r_absensi = client.get("/api/attendance/dashboard", headers=headers_pos2)
    assert r_absensi.status_code == 200, r_absensi.text

    # Rekap -> Baca: GET boleh.
    r_rekap = client.get("/api/rekap/transaksi", headers=headers_pos2)
    assert r_rekap.status_code == 200, r_rekap.text

    # Menu lain (Booking, Kasbon, Produk, Input Data) -> Tidak Ada Akses: 403.
    assert client.get("/api/booking", headers=headers_pos2).status_code == 403
    assert client.get("/api/kasbon", headers=headers_pos2).status_code == 403
    assert client.get("/api/produk", headers=headers_pos2).status_code == 403
    assert client.get("/api/input-data/barbers", headers=headers_pos2).status_code == 403


def test_ganti_role_pos2_ke_admin_langsung_berubah_akses(single_tenant):
    """Efek REVISI Role Custom (kompatibel mundur): melepas custom_role_id
    (balik ke Role "Admin") langsung mengembalikan akses default tenant,
    tanpa perlu logout/login ulang -- setiap request re-resolve dari DB."""
    client, headers_owner = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    role = user_roles_db.create_role(tenant_id, "POS 2 v2")
    permissions.set_all_menu_levels({"absensi": "write"}, role_id=role["id"])
    headers_pos2 = _buat_staff_dan_login(client, tenant_id, username="pos2v2", custom_role_id=role["id"])

    assert client.get("/api/produk", headers=headers_pos2).status_code == 403  # Role Custom: none

    user_row = auth_db.get_user_by_username("pos2v2")
    client.put(f"/api/pengaturan/user/{user_row['id']}/role", json={"custom_role_id": None}, headers=headers_owner)
    r2 = client.get("/api/produk", headers=headers_pos2)
    assert r2.status_code == 200  # sekarang pakai default tenant (produk default write)
