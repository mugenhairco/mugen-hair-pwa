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
    assert hasil["detail"][0]["tanggal_cuti"] == ["2026-07-02"]


def test_tidak_memproses_toko_libur(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    booking_db.tambah_toko_libur("2026-07-01", "Libur Nasional", tenant_id=tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil["jumlah_dibuat"] == 1
    assert hasil["detail"][0]["tanggal_cuti"] == ["2026-07-02"]


def test_tidak_memproses_bukan_hari_operasional(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    # 2026-07-05 = Minggu -- toko TIDAK buka hari Minggu.
    booking_db.update_booking_settings(
        hari_operasional=["senin", "selasa", "rabu", "kamis", "jumat", "sabtu"], tenant_id=tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-06")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    tanggal_dibuat = hasil["detail"][0]["tanggal_cuti"]
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
    assert hasil["detail"][0]["tanggal_cuti"] == ["2026-07-02"]


def test_tidak_memproses_yang_sudah_ada_izin_cuti(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-07-01", "2026-07-01", "Sudah izin resmi",
                                 tenant_id=tenant_id, override=True)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil["jumlah_dibuat"] == 1
    assert hasil["detail"][0]["tanggal_cuti"] == ["2026-07-02"]


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
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-07-01", auto_libur_tidak_absen_aktif=True)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-06")
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-07-06")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil["jumlah_dibuat"] == 5

    saldo = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo["aktif"] is True
    assert saldo["sisa_gabungan"] == 5  # 10 - 5 hari auto-libur


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


# ---------------------------------------------------------------------------
# KOREKSI Owner: tidak absen check-in dianggap LIBUR dulu (mengurangi Kuota
# Libur/bulan), baru jatuh ke kuota gabungan Izin&Cuti kalau Kuota Libur
# sudah habis, dan tetap dicatat Libur (distabilo merah di Rekap Bulanan)
# kalau KEDUA kuota itu sama-sama habis.
# ---------------------------------------------------------------------------

def test_kuota_libur_dipakai_lebih_dulu_sebelum_kuota_gabungan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id, kuota_libur_bulanan=2)  # kuota gabungan izin&cuti TIDAK dipakai (unlimited)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-05")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    # 1-4 Juli: 2 hari pertama -> Libur (Kuota Libur), 2 hari berikutnya -> Cuti.
    assert hasil["jumlah_dibuat"] == 4
    detail = hasil["detail"][0]
    assert detail["tanggal_libur"] == ["2026-07-01", "2026-07-02"]
    assert detail["tanggal_cuti"] == ["2026-07-03", "2026-07-04"]
    assert detail["tanggal_kelebihan_kuota"] == []
    assert db.get_hari_libur(barber_id, 2026, 7) == 2
    assert len(izin_cuti_db.get_pengajuan_list(barber_id=barber_id, jenis="cuti")) == 2


def test_kedua_kuota_habis_tetap_dicatat_libur_dan_distabilo(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=1,
                                    periode_mulai_dasar="2026-07-01", auto_libur_tidak_absen_aktif=True,
                                    kuota_libur_bulanan=1)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-05")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    # 1-4 Juli: hari 1 -> Libur (Kuota Libur=1 habis), hari 2 -> Cuti (kuota
    # gabungan=1 habis setelah ini), hari 3-4 -> KEDUA kuota sudah habis,
    # tetap dicatat Libur (kelebihan).
    assert hasil["jumlah_dibuat"] == 4
    detail = hasil["detail"][0]
    assert detail["tanggal_libur"] == ["2026-07-01"]
    assert detail["tanggal_cuti"] == ["2026-07-02"]
    assert detail["tanggal_kelebihan_kuota"] == ["2026-07-03", "2026-07-04"]
    assert db.get_hari_libur(barber_id, 2026, 7) == 3  # 1 Libur normal + 2 kelebihan
    assert auto_libur_db.ada_kelebihan_kuota_bulan_ini(barber_id, 2026, 7) is True


def test_tidak_ada_kelebihan_kuota_kalau_kuota_cukup(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id, kuota_libur_bulanan=10)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")
    auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert auto_libur_db.ada_kelebihan_kuota_bulan_ini(barber_id, 2026, 7) is False


def test_barber_holiday_manual_tidak_ikut_kuota_libur_bulanan(single_tenant, monkeypatch):
    """Barber Holiday manual (sumber NULL, di luar Auto-Libur) TIDAK ikut
    mengurangi Kuota Libur/bulan -- hanya baris yang dibuat Auto-Libur
    sendiri yang dihitung."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id, kuota_libur_bulanan=1)
    db.tandai_libur(barber_id, "2026-07-01")  # manual, sumber NULL
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")

    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    # 1 Juli dilewati (sudah Barber Holiday manual) -- 2 Juli TETAP masuk
    # Kuota Libur (belum terpakai sama sekali dari sisi Auto-Libur).
    assert hasil["detail"][0]["tanggal_libur"] == ["2026-07-02"]
    assert db.get_hari_libur(barber_id, 2026, 7) == 2  # 1 manual + 1 auto


def test_kuota_libur_off_default_semua_jadi_cuti_seperti_sebelumnya(single_tenant, monkeypatch):
    """kuota_libur_bulanan=0 (default, tidak diisi Owner) -- perilaku PERSIS
    versi Auto-Libur sebelumnya (semua langsung jadi Cuti)."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")
    hasil = auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert hasil["detail"][0]["tanggal_libur"] == []
    assert hasil["detail"][0]["tanggal_cuti"] == ["2026-07-01", "2026-07-02"]


def test_rekap_bulanan_stabilo_merah_saat_kuota_habis(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=1,
                                    periode_mulai_dasar="2026-07-01", auto_libur_tidak_absen_aktif=True,
                                    kuota_libur_bulanan=1)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-05")
    auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)

    r = client.get("/api/rekap/bulanan?tahun=2026&bulan=7", headers=headers)
    assert r.status_code == 200
    baris = next(b for b in r.json() if b["barber_id"] == barber_id)
    assert baris["kuota_habis"] is True


def test_rekap_bulanan_tidak_stabilo_kalau_kuota_cukup(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id, kuota_libur_bulanan=10)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")
    auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)

    r = client.get("/api/rekap/bulanan?tahun=2026&bulan=7", headers=headers)
    assert r.status_code == 200
    baris = next(b for b in r.json() if b["barber_id"] == barber_id)
    assert baris["kuota_habis"] is False


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: kartu Sisa Kuota Libur (pindah ke Absensi) -- sisa kuota
# libur BULAN KALENDER BERJALAN (auto_libur_db.get_sisa_kuota_libur_bulan_ini())
# + ringkasan semua barber (GET /api/izin-cuti/saldo-semua-barber, dipakai
# Absensi > Owner).
# ---------------------------------------------------------------------------

def test_get_sisa_kuota_libur_bulan_ini_off_default(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    hasil = auto_libur_db.get_sisa_kuota_libur_bulan_ini(barber_id, tenant_id)
    assert hasil == {"aktif": False, "kuota": None, "terpakai": None, "sisa": None}


def test_get_sisa_kuota_libur_bulan_ini_terpakai_setelah_proses(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id, kuota_libur_bulanan=3)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-05")

    auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    # 1-4 Juli: 3 hari pertama -> Libur (kuota=3 habis), hari ke-4 -> Cuti
    # (kuota gabungan izin&cuti tidak dipakai/unlimited).
    hasil = auto_libur_db.get_sisa_kuota_libur_bulan_ini(barber_id, tenant_id)
    assert hasil == {"aktif": True, "kuota": 3, "terpakai": 3, "sisa": 0}


def test_router_saldo_semua_barber(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=1,
                                    periode_mulai_dasar="2026-07-01", auto_libur_tidak_absen_aktif=True,
                                    kuota_libur_bulanan=1)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-05")
    auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)

    r = client.get("/api/izin-cuti/saldo-semua-barber", headers=headers)
    assert r.status_code == 200
    baris = next(b for b in r.json() if b["barber_id"] == barber_id)
    assert baris["nama_barber"]
    assert baris["libur"]["aktif"] is True
    assert baris["kuota_habis"] is True


def test_router_saldo_semua_barber_barber_ditolak(single_tenant):
    """Endpoint ini mengembalikan data SEMUA barber -- barber TIDAK boleh
    mengaksesnya sama sekali (beda dari /saldo miliknya sendiri)."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import auth_db
    barber_id = db.add_barber("Barber Tolak SemuaKuota", tenant_id=tenant_id)
    auth_db.tambah_user("barbertolaksemuakuota", "passwordB123", role="barber", barber_id=barber_id,
                         tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "barbertolaksemuakuota", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}
    r = client.get("/api/izin-cuti/saldo-semua-barber", headers=headers_barber)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: Koreksi Absensi (barber lupa check-in) disetujui UNTUK
# tanggal yang SUDAH TERLANJUR diproses Auto-Libur -- catatan Libur/Cuti
# otomatis itu harus dibatalkan (auto_libur_db.batalkan_auto_libur_untuk_tanggal()).
# ---------------------------------------------------------------------------

def test_batalkan_auto_libur_membatalkan_libur(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id, kuota_libur_bulanan=5)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")
    auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert db.get_hari_libur(barber_id, 2026, 7) == 2  # 2026-07-01 & 07-02

    hasil = auto_libur_db.batalkan_auto_libur_untuk_tanggal(barber_id, "2026-07-01")
    assert hasil == {"dibatalkan_libur": True, "dibatalkan_cuti": False}
    assert db.get_hari_libur(barber_id, 2026, 7) == 1  # tinggal 07-02


def test_batalkan_auto_libur_membatalkan_cuti(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    _aktifkan(tenant_id)  # kuota_libur_bulanan=0 -> semua langsung jadi Cuti
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")
    auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert len(izin_cuti_db.get_pengajuan_list(barber_id=barber_id, jenis="cuti")) == 2

    hasil = auto_libur_db.batalkan_auto_libur_untuk_tanggal(barber_id, "2026-07-01")
    assert hasil == {"dibatalkan_libur": False, "dibatalkan_cuti": True}
    daftar = izin_cuti_db.get_pengajuan_list(barber_id=barber_id, jenis="cuti")
    assert len(daftar) == 1
    assert daftar[0]["tanggal_mulai"] == "2026-07-02"


def test_batalkan_auto_libur_tidak_ada_apa_apa_kasus_normal(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    hasil = auto_libur_db.batalkan_auto_libur_untuk_tanggal(barber_id, "2026-07-01")
    assert hasil == {"dibatalkan_libur": False, "dibatalkan_cuti": False}


def test_batalkan_auto_libur_tidak_menyentuh_barber_holiday_manual(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    db.tandai_libur(barber_id, "2026-07-01")  # manual, sumber NULL
    hasil = auto_libur_db.batalkan_auto_libur_untuk_tanggal(barber_id, "2026-07-01")
    assert hasil == {"dibatalkan_libur": False, "dibatalkan_cuti": False}
    assert db.get_hari_libur(barber_id, 2026, 7) == 1  # tetap ada, tidak ikut terhapus


def test_batalkan_auto_libur_tidak_menyentuh_cuti_asli_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-07-01", "2026-07-01", "Cuti asli",
                                 tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(
        izin_cuti_db.get_pengajuan_list(barber_id=barber_id)[0]["id"], "disetujui", disetujui_oleh="Owner")
    hasil = auto_libur_db.batalkan_auto_libur_untuk_tanggal(barber_id, "2026-07-01")
    assert hasil == {"dibatalkan_libur": False, "dibatalkan_cuti": False}
    assert len(izin_cuti_db.get_pengajuan_list(barber_id=barber_id)) == 1


def test_router_koreksi_disetujui_membatalkan_auto_libur(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    client.put("/api/attendance/settings",
               json={"lokasi_latitude": -6.2, "lokasi_longitude": 106.8, "radius_meter": 500,
                     "jam_masuk": "09:00", "jam_pulang": "20:00"},
               headers=headers)
    import auth_db
    barber_id = _barber(tenant_id, "Barber Koreksi AutoLibur")
    auth_db.tambah_user("barberkoreksiautolibur", "passwordB123", role="barber", barber_id=barber_id,
                         tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "barberkoreksiautolibur", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}

    _aktifkan(tenant_id, kuota_libur_bulanan=5)
    monkeypatch.setattr(auto_libur_db, "_hari_ini_wib", lambda: "2026-07-03")
    auto_libur_db.proses_auto_libur(tenant_id, 2026, 7)
    assert db.get_hari_libur(barber_id, 2026, 7) == 2

    r_koreksi = client.post("/api/attendance/koreksi",
                             json={"tanggal": "2026-07-01", "jenis": "check_in", "waktu_diajukan": "09:05",
                                   "alasan": "Lupa check-in"},
                             headers=headers_barber)
    assert r_koreksi.status_code == 200, r_koreksi.text
    koreksi_id = r_koreksi.json()["id"]

    r_approve = client.put(f"/api/attendance/koreksi/{koreksi_id}/status",
                            json={"status": "disetujui"}, headers=headers)
    assert r_approve.status_code == 200, r_approve.text
    assert r_approve.json()["auto_libur_dibatalkan"] == {"dibatalkan_libur": True, "dibatalkan_cuti": False}
    assert db.get_hari_libur(barber_id, 2026, 7) == 1  # 07-01 dibatalkan, 07-02 tetap ada
