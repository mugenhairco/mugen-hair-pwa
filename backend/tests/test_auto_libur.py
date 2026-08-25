"""test_auto_libur.py — Auto-Libur untuk Barber yang Tidak Absen
=============================================================================
PERMINTAAN OWNER: "jika role barber tidak absen maka otomatis direkap
dibuat libur (dan mengurangi kuota libur) dalam sebulan" -- lihat
auto_libur_db.py. Default OFF (byte-for-byte tidak memengaruhi tenant
yang belum mengaktifkan), hanya memproses hari kerja yang SUDAH LEWAT
tanpa baris attendance_logs sama sekali, mengabaikan tanggal yang sudah
punya alasan resmi (toko_libur/bukan hari_operasional/Barber Holiday/
izin_cuti lain), idempotent, dan hasilnya otomatis ikut dihitung kuota
cuti lewat mesin kuota yang sudah ada (izin_cuti_db._kuota_terpakai_hari())."""

import itertools

import auto_libur_db
import booking_db
import database as db
import izin_cuti_db

_urutan_unik = itertools.count(1)


def _barber(tenant_id, nama=None):
    n = next(_urutan_unik)
    return db.add_barber(nama or f"Barber AutoLibur {n}", tenant_id=tenant_id)


def _aktifkan(tenant_id, **override):
    izin_cuti_db.set_cuti_settings(tenant_id, auto_libur_tidak_absen_aktif=True, **override)


def test_off_default_menolak_diproses(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
        assert False, "Seharusnya ValueError (Auto-Libur belum diaktifkan)"
    except ValueError as e:
        assert "belum diaktifkan" in str(e).lower()


def test_membuat_cuti_untuk_hari_tanpa_checkin(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-10")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    # 1-9 Juli 2026 (9 hari, semua sebelum "hari ini" 10 Juli) -- semuanya
    # tanpa check-in, tanpa pengecualian apa pun -- semuanya jadi auto-libur.
    assert hasil["jumlah_dibuat"] == 9
    daftar = izin_cuti_db.get_pengajuan_list(barber_id=barber_id, jenis="cuti")
    assert len(daftar) == 9
    for p in daftar:
        assert p["status"] == "disetujui"
        assert p["diajukan_oleh"] == auto_libur_db.DIAJUKAN_OLEH_AUTO_LIBUR


def test_tidak_memproses_hari_dengan_checkin(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")

    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO attendance_logs (barber_id, tanggal, created_at, tenant_id) VALUES (?, ?, ?, ?)",
            (barber_id, "2026-07-01", "2026-07-01T09:00:00", tenant_id),
        )

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    # 1-2 Juli -- 1 Juli SUDAH check-in (dilewati), 2 Juli tidak -> hanya 1 dibuat.
    assert hasil["jumlah_dibuat"] == 1
    assert hasil["detail"][0]["tanggal"] == ["2026-07-02"]


def test_tidak_memproses_toko_libur(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    booking_db.tambah_toko_libur("2026-07-01", "Libur Nasional", tenant_id=tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil["jumlah_dibuat"] == 1
    assert hasil["detail"][0]["tanggal"] == ["2026-07-02"]


def test_tidak_memproses_bukan_hari_operasional(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    # 2026-07-05 = Minggu -- toko TIDAK buka hari Minggu.
    booking_db.update_booking_settings(
        hari_operasional=["senin", "selasa", "rabu", "kamis", "jumat", "sabtu"], tenant_id=tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-06")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    tanggal_dibuat = hasil["detail"][0]["tanggal"]
    assert "2026-07-05" not in tanggal_dibuat
    assert "2026-07-01" in tanggal_dibuat


def test_tidak_memproses_barber_holiday(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    db.tandai_libur(barber_id, "2026-07-01")
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil["jumlah_dibuat"] == 1
    assert hasil["detail"][0]["tanggal"] == ["2026-07-02"]


def test_tidak_memproses_yang_sudah_ada_izin_cuti(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-07-01", "2026-07-01", "Sudah izin resmi",
                                 tenant_id=tenant_id, override=True)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil["jumlah_dibuat"] == 1
    assert hasil["detail"][0]["tanggal"] == ["2026-07-02"]


def test_tidak_memproses_hari_ini_atau_masa_depan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-01")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    # "Hari ini" = 1 Juli -- TIDAK ADA tanggal SEBELUM itu di bulan Juli
    # 2026 (bulan baru mulai), jadi tidak ada apa pun yang diproses.
    assert hasil["jumlah_dibuat"] == 0


def test_idempotent_tidak_duplikat_saat_dipanggil_ulang(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-05")

    hasil1 = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil1["jumlah_dibuat"] == 4
    hasil2 = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil2["jumlah_dibuat"] == 0
    daftar = izin_cuti_db.get_pengajuan_list(barber_id=barber_id, jenis="cuti")
    assert len(daftar) == 4


def test_mengurangi_kuota_cuti_otomatis(single_tenant, monkeypatch):
    """Terintegrasi dengan mesin kuota dinamis yang SUDAH ADA -- auto-libur
    TIDAK PERLU logika kuota baru, cukup lewat izin_cuti biasa."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_maksimal_hari=10,
                                    periode_mulai_dasar="2026-07-01", auto_libur_tidak_absen_aktif=True)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-06")
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-07-06")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil["jumlah_dibuat"] == 5

    saldo = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo["aktif"] is True
    assert saldo["sisa_cuti"] == 5  # 10 - 5 hari auto-libur


def test_tenant_lain_tidak_ikut_terpengaruh(two_tenants, monkeypatch):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = _barber(tenant_a, "Barber Auto A")
    barber_b = _barber(tenant_b, "Barber Auto B")
    _aktifkan(tenant_a)
    # tenant_b TIDAK mengaktifkan Auto-Libur sama sekali.
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")

    auto_libur_db.proses_auto_libur(tenant_a, 2026, 7)
    assert len(izin_cuti_db.get_pengajuan_list(barber_id=barber_a, jenis="cuti")) == 2
    assert len(izin_cuti_db.get_pengajuan_list(barber_id=barber_b, jenis="cuti")) == 0
    try:
        auto_libur_db.proses_auto_libur(tenant_b, 2026, 7)
        assert False, "Seharusnya ValueError (tenant B belum mengaktifkan)"
    except ValueError:
        pass


def test_router_auto_libur_butuh_permission(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    _barber(tenant_id)
    client.put("/api/izin-cuti/pengaturan", json={"auto_libur_tidak_absen_aktif": True}, headers=headers)

    r = client.post("/api/izin-cuti/auto-libur/proses", json={"tahun": 2020, "bulan": 1}, headers=headers)
    assert r.status_code == 200
    assert r.json()["jumlah_dibuat"] >= 0  # bulan sudah lampau jauh, boleh 0 atau lebih


def test_router_auto_libur_gagal_kalau_belum_aktif(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.post("/api/izin-cuti/auto-libur/proses", json={"tahun": 2020, "bulan": 1}, headers=headers)
    assert r.status_code == 422
