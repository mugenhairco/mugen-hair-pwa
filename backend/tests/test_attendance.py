"""Modul BARU Absensi (GPS Check In/Out Geofencing) -- test suite.

Mengikuti pola test suite yang sudah ada (conftest.py::single_tenant/
two_tenants) -- lihat test_tenant_isolation_karyawan.py untuk pola
isolasi tenant yang sama. Absensi SENGAJA TIDAK terhubung ke izin_cuti/
absensi_libur (keputusan eksplisit Owner), jadi test di sini murni
berdiri sendiri, tidak menyentuh modul lain."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import attendance_db

WIB = ZoneInfo("Asia/Jakarta")

# Titik toko (Monas, Jakarta) & titik ~50m/~2km darinya, dipakai berulang.
TOKO_LAT, TOKO_LNG = -6.175392, 106.827153
DEKAT_LAT, DEKAT_LNG = -6.175800, 106.827153  # ~45 meter dari toko
JAUH_LAT, JAUH_LNG = -6.200000, 106.850000    # ~3.6 km dari toko


def _atur_lokasi_toko(tenant_id, radius=500):
    attendance_db.set_settings(tenant_id, jam_masuk="09:00", toleransi_menit=15, jam_pulang="20:00",
                                radius_meter=radius, lokasi_nama="Toko Test",
                                lokasi_latitude=TOKO_LAT, lokasi_longitude=TOKO_LNG)


def _barber(tenant_id, nama="Barber Test"):
    import database
    return database.add_barber(nama, tenant_id=tenant_id)


def test_haversine_zero_distance():
    assert attendance_db.haversine_meter(TOKO_LAT, TOKO_LNG, TOKO_LAT, TOKO_LNG) == pytest.approx(0, abs=0.01)


def test_haversine_titik_dekat_dan_jauh():
    dekat = attendance_db.haversine_meter(TOKO_LAT, TOKO_LNG, DEKAT_LAT, DEKAT_LNG)
    jauh = attendance_db.haversine_meter(TOKO_LAT, TOKO_LNG, JAUH_LAT, JAUH_LNG)
    assert 30 < dekat < 60
    assert jauh > 3000


def test_settings_lazy_create_dan_update(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    default = attendance_db.get_settings(tenant_id)
    assert default["jam_masuk"] == "09:00"
    assert default["radius_meter"] == 500

    updated = attendance_db.set_settings(tenant_id, jam_masuk="08:30", toleransi_menit=10,
                                          jam_pulang="19:00", radius_meter=250)
    assert updated["jam_masuk"] == "08:30"
    assert updated["toleransi_menit"] == 10
    assert updated["radius_meter"] == 250


def test_settings_radius_invalid_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    with pytest.raises(ValueError):
        attendance_db.set_settings(tenant_id, radius_meter=333)


def test_settings_jam_format_invalid_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    with pytest.raises(ValueError):
        attendance_db.set_settings(tenant_id, jam_masuk="25:99")


def test_hitung_status_belum_check_in_dan_tidak_check_in(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    settings = attendance_db.get_settings(tenant_id)  # default jam_pulang 20:00
    tanggal = "2026-08-13"
    sebelum_pulang = datetime(2026, 8, 13, 10, 0, tzinfo=WIB)
    sesudah_pulang = datetime(2026, 8, 13, 21, 0, tzinfo=WIB)
    assert attendance_db.hitung_status_hari_ini(None, settings, sebelum_pulang) == "belum_check_in"
    assert attendance_db.hitung_status_hari_ini(None, settings, sesudah_pulang) == "tidak_check_in"


def test_hitung_status_sedang_bekerja_dan_tidak_check_out(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    settings = attendance_db.get_settings(tenant_id)
    log = {"check_in_at": "2026-08-13T09:05:00+07:00", "check_out_at": None}
    sebelum_pulang = datetime(2026, 8, 13, 15, 0, tzinfo=WIB)
    sesudah_pulang = datetime(2026, 8, 13, 21, 0, tzinfo=WIB)
    assert attendance_db.hitung_status_hari_ini(log, settings, sebelum_pulang) == "sedang_bekerja"
    assert attendance_db.hitung_status_hari_ini(log, settings, sesudah_pulang) == "tidak_check_out"


def test_hitung_status_sudah_check_out(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    settings = attendance_db.get_settings(tenant_id)
    log = {"check_in_at": "2026-08-13T09:05:00+07:00", "check_out_at": "2026-08-13T20:10:00+07:00"}
    assert attendance_db.hitung_status_hari_ini(
        log, settings, datetime(2026, 8, 13, 21, 0, tzinfo=WIB)) == "sudah_check_out"


def test_check_in_sukses_tepat_waktu_dan_terlambat(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id, "Barber A")
    barber_b = _barber(tenant_id, "Barber B")

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 5, tzinfo=WIB))
    hasil = attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    assert hasil["check_in_status"] == "tepat_waktu"
    assert hasil["status"] == "sedang_bekerja"

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 30, tzinfo=WIB))
    hasil2 = attendance_db.check_in(tenant_id, barber_b, TOKO_LAT, TOKO_LNG, accuracy=15)
    assert hasil2["check_in_status"] == "terlambat"


def test_check_in_duplikat_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 5, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    with pytest.raises(ValueError, match="sudah Check In"):
        attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)


def test_check_in_luar_radius_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id, radius=100)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 5, tzinfo=WIB))
    with pytest.raises(ValueError, match="luar radius"):
        attendance_db.check_in(tenant_id, barber_a, JAUH_LAT, JAUH_LNG, accuracy=15)


def test_check_in_akurasi_buruk_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 5, tzinfo=WIB))
    with pytest.raises(ValueError, match="Fake GPS"):
        attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=500)


def test_check_in_setelah_jam_pulang_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 20, 30, tzinfo=WIB))
    with pytest.raises(ValueError, match="jam pulang"):
        attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)


def test_check_out_sebelum_check_in_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 20, 30, tzinfo=WIB))
    with pytest.raises(ValueError, match="belum Check In"):
        attendance_db.check_out(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)


def test_check_out_sebelum_jam_pulang_diizinkan_tapi_tercatat_pulang_awal(single_tenant, monkeypatch):
    """REVISI (feedback Owner): Check Out sebelum jam_pulang TIDAK LAGI
    ditolak -- diizinkan, tapi mengurangi limit "pulang lebih awal" bulanan
    (lihat test_ringkasan_bulan_pulang_awal untuk perhitungan limitnya)."""
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 5, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 12, 0, tzinfo=WIB))
    hasil = attendance_db.check_out(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    assert hasil["status"] == "sudah_check_out"
    assert hasil["check_out_at"].startswith("2026-08-13T12:00")


def test_check_out_sukses_dan_durasi_kerja(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 20, 30, tzinfo=WIB))
    hasil = attendance_db.check_out(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    assert hasil["status"] == "sudah_check_out"
    assert hasil["durasi_kerja_menit"] == 690  # 09:00 -> 20:30 = 11j30m

    with pytest.raises(ValueError, match="sudah Check Out"):
        attendance_db.check_out(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)


def test_audit_log_mencatat_sukses_dan_gagal(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    attendance_db.catat_audit(barber_a, "check_in", False, alasan_gagal="Sudah Check In hari ini.",
                               tenant_id=tenant_id)
    audit = attendance_db.get_audit_list(tenant_id)
    assert len(audit) == 2
    assert any(a["sukses"] == 1 for a in audit)
    assert any(a["sukses"] == 0 for a in audit)


def test_dashboard_ringkasan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_hadir = _barber(tenant_id, "Hadir")
    _barber(tenant_id, "Tidak Hadir")  # tidak check in sama sekali

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_hadir, TOKO_LAT, TOKO_LNG, accuracy=15)

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 15, 0, tzinfo=WIB))
    ringkasan = attendance_db.get_ringkasan_dashboard(tenant_id)
    assert ringkasan["total_barber"] == 2
    assert ringkasan["hadir"] == 1
    assert ringkasan["belum_hadir"] == 1
    assert ringkasan["sedang_bekerja"] == 1


def test_tenant_isolation(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    _atur_lokasi_toko(tenant_a)
    barber_a = _barber(tenant_a, "Barber A")
    barber_b = _barber(tenant_b, "Barber B")

    with pytest.raises(ValueError):
        attendance_db.check_in(tenant_a, barber_b, TOKO_LAT, TOKO_LNG, accuracy=15)

    assert attendance_db.get_log_hari_ini(barber_a, tenant_b) is None
    assert len(attendance_db.get_log_list(tenant_a)) == 1  # baris semu "belum_check_in" utk barber_a
    assert len(attendance_db.get_log_list(tenant_b)) == 1  # baris semu utk barber_b


# ---------------------------------------------------------------------------
# API-level: hak akses (routers/attendance.py)
# ---------------------------------------------------------------------------

def test_api_settings_get_izin_lihat_tanpa_permission(single_tenant):
    """staff SELALU boleh MELIHAT settings (pola sama pengeluaran.py) --
    hanya MENGUBAH yang butuh izin_absensi_pengaturan."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import auth_db
    auth_db.tambah_user("staff1", "passwordS123", role="staff", tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "staff1", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}

    assert client.get("/api/attendance/settings", headers=headers_staff).status_code == 200
    r = client.put("/api/attendance/settings", json={"jam_masuk": "08:00"}, headers=headers_staff)
    assert r.status_code == 403

    r2 = client.put("/api/attendance/settings", json={"jam_masuk": "08:00"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["jam_masuk"] == "08:00"


def test_api_settings_staff_dengan_izin_boleh_ubah(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import auth_db
    auth_db.tambah_user("staff2", "passwordS123", role="staff", tenant_id=tenant_id)
    client.put("/api/pengaturan/hak-akses-admin", json={"izin": {"izin_absensi_pengaturan": True}}, headers=headers)

    r_login = client.post("/api/auth/login", json={"username": "staff2", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login.json()['token']}"}
    r = client.put("/api/attendance/settings", json={"jam_masuk": "07:30"}, headers=headers_staff)
    assert r.status_code == 200
    assert r.json()["jam_masuk"] == "07:30"


def test_api_barber_check_in_dan_today(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    # Jendela jam kerja dilebarkan (00:00-23:59) supaya test ini TIDAK
    # bergantung pada jam berapa sungguhan test dijalankan (default
    # 09:00-20:00 akan gagal kalau dijalankan malam hari WIB) -- beda dari
    # test_check_in_*/test_check_out_* di atas yang sengaja monkeypatch
    # attendance_db._sekarang_wib() langsung, endpoint API di sini lebih
    # sederhana dilebarkan jendelanya saja.
    r = client.put("/api/attendance/settings",
                    json={"lokasi_latitude": TOKO_LAT, "lokasi_longitude": TOKO_LNG, "radius_meter": 500,
                          "jam_masuk": "00:00", "jam_pulang": "23:59"},
                    headers=headers)
    assert r.status_code == 200

    import auth_db
    barber_id = _barber(tenant_id, "Barber API")
    auth_db.tambah_user("barberapi", "passwordB123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "barberapi", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r_today = client.get("/api/attendance/today", headers=headers_barber)
    assert r_today.status_code == 200
    assert r_today.json()["log"] is None

    r_checkin = client.post("/api/attendance/check-in",
                             json={"latitude": TOKO_LAT, "longitude": TOKO_LNG, "accuracy": 15},
                             headers=headers_barber)
    assert r_checkin.status_code == 200, r_checkin.text
    assert r_checkin.json()["check_in_status"] in ("tepat_waktu", "terlambat")

    # Owner (admin) TIDAK bisa memakai endpoint self-service Barber.
    assert client.post("/api/attendance/check-in", json={"latitude": TOKO_LAT, "longitude": TOKO_LNG},
                        headers=headers).status_code == 403

    # Owner boleh melihat dashboard & daftar (view-only, tanpa syarat izin apa pun).
    assert client.get("/api/attendance/dashboard", headers=headers).status_code == 200
    assert client.get("/api/attendance", headers=headers).status_code == 200

    # Barber TIDAK boleh mengakses dashboard/daftar/audit Owner.
    assert client.get("/api/attendance/dashboard", headers=headers_barber).status_code == 403
    assert client.get("/api/attendance/audit", headers=headers_barber).status_code == 403


# ---------------------------------------------------------------------------
# FITUR: Batas minimal jam Check In (feedback Owner)
# ---------------------------------------------------------------------------

def test_check_in_sebelum_jam_masuk_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)  # jam_masuk default 09:00
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 8, 0, tzinfo=WIB))
    with pytest.raises(ValueError, match="Belum waktunya Check In"):
        attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)


def test_check_in_tepat_jam_masuk_diizinkan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 0, tzinfo=WIB))
    hasil = attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    assert hasil["check_in_status"] == "tepat_waktu"


# ---------------------------------------------------------------------------
# FITUR: Ringkasan limit Keterlambatan & Pulang Lebih Awal (bulanan)
# ---------------------------------------------------------------------------

def test_ringkasan_bulan_keterlambatan_dan_limit_habis(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)  # jam_masuk 09:00, toleransi 15
    barber_a = _barber(tenant_id)

    # 3 hari, masing-masing terlambat 50 menit (check-in jam 09:50) -->
    # total 150 menit, melewati limit 120 di hari ketiga.
    for hari in (10, 11, 12):
        monkeypatch.setattr(attendance_db, "_sekarang_wib",
                             lambda hari=hari: datetime(2026, 8, hari, 9, 50, tzinfo=WIB))
        attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)

    ringkasan = attendance_db.hitung_ringkasan_bulan(barber_a, tenant_id, 2026, 8)
    assert ringkasan["menit_terlambat_terpakai"] == 150
    assert ringkasan["sisa_limit_terlambat"] == 0

    catatan_hari_10 = ringkasan["keterangan_per_tanggal"]["2026-08-10"]
    assert "Terlambat 50 menit pada 10 Agustus 2026" in catatan_hari_10
    assert not any("habis" in c for c in catatan_hari_10)

    catatan_hari_12 = ringkasan["keterangan_per_tanggal"]["2026-08-12"]
    assert any("limit keterlambatan bulan ini sudah habis" in c for c in catatan_hari_12)


def test_ringkasan_bulan_pulang_awal(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)  # jam_pulang 20:00
    barber_a = _barber(tenant_id)

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 19, 45, tzinfo=WIB))
    attendance_db.check_out(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)

    ringkasan = attendance_db.hitung_ringkasan_bulan(barber_a, tenant_id, 2026, 8)
    assert ringkasan["menit_pulang_awal_terpakai"] == 15
    assert ringkasan["sisa_limit_pulang_awal"] == 105
    assert "Pulang lebih awal 15 menit pada 13 Agustus 2026" in ringkasan["keterangan_per_tanggal"]["2026-08-13"]


def test_ringkasan_bulan_default_bulan_berjalan(single_tenant, monkeypatch):
    """tahun/bulan boleh dikosongkan -- default bulan berjalan (WIB)."""
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 13, 9, 50, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)
    ringkasan = attendance_db.hitung_ringkasan_bulan(barber_a, tenant_id)
    assert ringkasan["tahun"] == 2026 and ringkasan["bulan"] == 8
    assert ringkasan["menit_terlambat_terpakai"] == 50


# ---------------------------------------------------------------------------
# FITUR: Koreksi Absensi (barber lupa Check In/Check Out)
# ---------------------------------------------------------------------------

def test_koreksi_ajukan_approve_membuat_log_baru(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)

    koreksi = attendance_db.buat_pengajuan_koreksi(
        barber_a, "2026-08-05", "check_in", "09:10", "Lupa check-in, HP mati",
        diajukan_oleh="barberapi", tenant_id=tenant_id,
    )
    assert koreksi["status"] == "pending"

    hasil = attendance_db.set_status_koreksi(koreksi["id"], "disetujui", catatan_approval="OK",
                                              disetujui_oleh="owner")
    assert hasil["status"] == "disetujui"

    daftar = attendance_db.get_log_list(tenant_id, tanggal="2026-08-05", barber_id=barber_a)
    assert len(daftar) == 1
    log = daftar[0]
    assert log["check_in_at"].startswith("2026-08-05T09:10")
    assert log["check_in_status"] == "tepat_waktu"  # 09:10 < 09:00+15menit toleransi
    assert log["check_in_browser"] == "(Dikoreksi Admin/Owner)"


def test_koreksi_check_out_melengkapi_durasi_kerja(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 6, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_a, TOKO_LAT, TOKO_LNG, accuracy=15)

    koreksi = attendance_db.buat_pengajuan_koreksi(
        barber_a, "2026-08-06", "check_out", "19:00", "Lupa check-out", tenant_id=tenant_id,
    )
    attendance_db.set_status_koreksi(koreksi["id"], "disetujui")

    daftar = attendance_db.get_log_list(tenant_id, tanggal="2026-08-06", barber_id=barber_a)
    log = daftar[0]
    assert log["check_out_at"].startswith("2026-08-06T19:00")
    assert log["durasi_kerja_menit"] == 600  # 09:00 -> 19:00


def test_koreksi_ditolak_tidak_mengubah_log(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id)
    koreksi = attendance_db.buat_pengajuan_koreksi(
        barber_a, "2026-08-07", "check_in", "09:10", "Lupa", tenant_id=tenant_id,
    )
    attendance_db.set_status_koreksi(koreksi["id"], "ditolak", catatan_approval="Tidak valid")
    daftar = attendance_db.get_log_list(tenant_id, tanggal="2026-08-07", barber_id=barber_a)
    assert daftar == []


def test_koreksi_duplikat_pending_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id)
    attendance_db.buat_pengajuan_koreksi(barber_a, "2026-08-08", "check_out", "19:30", "Lupa",
                                          tenant_id=tenant_id)
    with pytest.raises(ValueError, match="Sudah ada pengajuan"):
        attendance_db.buat_pengajuan_koreksi(barber_a, "2026-08-08", "check_out", "19:40", "Lupa lagi",
                                              tenant_id=tenant_id)


def test_koreksi_hapus_pending_sukses_tapi_bukan_setelah_diproses(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id)
    koreksi = attendance_db.buat_pengajuan_koreksi(barber_a, "2026-08-09", "check_in", "09:05", "Lupa",
                                                     tenant_id=tenant_id)
    attendance_db.hapus_pengajuan_koreksi(koreksi["id"])
    assert attendance_db.get_koreksi(koreksi["id"]) is None

    koreksi2 = attendance_db.buat_pengajuan_koreksi(barber_a, "2026-08-10", "check_in", "09:05", "Lupa",
                                                      tenant_id=tenant_id)
    attendance_db.set_status_koreksi(koreksi2["id"], "disetujui")
    with pytest.raises(ValueError, match="sudah diproses"):
        attendance_db.hapus_pengajuan_koreksi(koreksi2["id"])


def test_api_koreksi_ajukan_dan_approve(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    client.put("/api/attendance/settings",
               json={"lokasi_latitude": TOKO_LAT, "lokasi_longitude": TOKO_LNG, "radius_meter": 500,
                     "jam_masuk": "09:00", "jam_pulang": "20:00"},
               headers=headers)

    import auth_db
    barber_id = _barber(tenant_id, "Barber Koreksi")
    auth_db.tambah_user("barberkoreksi", "passwordB123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "barberkoreksi", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r_post = client.post("/api/attendance/koreksi",
                          json={"tanggal": "2026-08-05", "jenis": "check_in", "waktu_diajukan": "09:05",
                                "alasan": "Lupa check-in"},
                          headers=headers_barber)
    assert r_post.status_code == 200, r_post.text
    koreksi_id = r_post.json()["id"]
    assert r_post.json()["status"] == "pending"

    # Barber TIDAK boleh approve/reject (miliknya sendiri sekalipun).
    r_approve_barber = client.put(f"/api/attendance/koreksi/{koreksi_id}/status",
                                   json={"status": "disetujui"}, headers=headers_barber)
    assert r_approve_barber.status_code == 403

    # staff TANPA izin_absensi_koreksi ditolak.
    auth_db.tambah_user("staffkoreksi", "passwordS123", role="staff", tenant_id=tenant_id)
    r_login_staff = client.post("/api/auth/login", json={"username": "staffkoreksi", "password": "passwordS123"})
    headers_staff = {"Authorization": f"Bearer {r_login_staff.json()['token']}"}
    r_approve_staff_denied = client.put(f"/api/attendance/koreksi/{koreksi_id}/status",
                                         json={"status": "disetujui"}, headers=headers_staff)
    assert r_approve_staff_denied.status_code == 403

    # staff TAPI sudah diberi izin -- boleh.
    client.put("/api/pengaturan/hak-akses-admin", json={"izin": {"izin_absensi_koreksi": True}}, headers=headers)
    r_login_staff2 = client.post("/api/auth/login", json={"username": "staffkoreksi", "password": "passwordS123"})
    headers_staff2 = {"Authorization": f"Bearer {r_login_staff2.json()['token']}"}
    r_approve = client.put(f"/api/attendance/koreksi/{koreksi_id}/status",
                            json={"status": "disetujui", "catatan_approval": "OK"}, headers=headers_staff2)
    assert r_approve.status_code == 200, r_approve.text
    assert r_approve.json()["status"] == "disetujui"

    r_list = client.get("/api/attendance", params={"tanggal": "2026-08-05"}, headers=headers)
    assert any(row["barber_id"] == barber_id and row.get("check_in_at") for row in r_list.json())


def test_api_ringkasan_bulan(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    _atur_lokasi_toko(tenant_id)
    barber_a = _barber(tenant_id, "Ringkasan API")

    r = client.get("/api/attendance/ringkasan-bulan", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert any(item["barber_id"] == barber_a for item in r.json())
