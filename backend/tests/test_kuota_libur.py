"""test_kuota_libur.py -- Kuota Libur Bulanan (cascade Tandai Libur manual
-> Cuti, kuota_libur_db.py).

PERMINTAAN OWNER: Tandai Libur manual (Input Data) sekarang punya jatah
"Kuota Libur per Bulan" opsional per tenant (izin_cuti_settings.
kuota_libur_bulanan, 0 = tidak dibatasi/tidak ada cascade). Begitu kuota
itu habis, Tandai Libur berikutnya di bulan yang sama OTOMATIS dicatat
sebagai Cuti (mengurangi kuota gabungan Izin & Cuti). Kalau KEDUA kuota
itu sama-sama habis, tanggal tetap dicatat Libur tapi ditandai
sumber='kelebihan_kuota' (dipakai Rekap Bulanan untuk stabilo merah)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import attendance_db
import database as db
import izin_cuti_db
import kuota_libur_db as kld

WIB = ZoneInfo("Asia/Jakarta")


def _barber(tenant_id, nama="Kuota Libur Barber"):
    return db.add_barber(nama, tenant_id=tenant_id)


def _patch_hari_ini(monkeypatch, tanggal):
    """get_sisa_kuota_libur_bulan_ini()/ada_kelebihan_kuota_bulan_ini_sekarang()
    menganggap "bulan berjalan" sebagai BULAN WIB SAAT INI (attendance_db.
    tanggal_hari_ini()) -- dipatch di sini supaya test deterministik,
    sama seperti pola di test_uang_harian_dinamis.py/test_attendance.py."""
    y, m, d = (int(x) for x in tanggal.split("-"))
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(y, m, d, 12, 0, tzinfo=WIB))


# 1. Kuota TIDAK diatur (default 0) -- Tandai Libur berjalan seperti biasa,
# TIDAK ADA cascade apa pun (backward compatible, perilaku lama).
def test_tandai_libur_tanpa_kuota_diatur_tidak_ada_cascade(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    for tanggal in ("2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05"):
        jenis = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, tanggal)
        assert jenis == "libur"
    assert db.get_hari_libur(barber_id, 2026, 8) == 5
    assert izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)["aktif"] is False  # kuota periode juga belum diatur


# 2. Kuota diatur, masih tersedia -- Tandai Libur normal (jenis 'libur').
def test_tandai_libur_di_bawah_kuota(single_tenant, monkeypatch):
    _patch_hari_ini(monkeypatch, "2026-08-15")
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=3)
    jenis = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")
    assert jenis == "libur"
    assert db.get_hari_libur(barber_id, 2026, 8) == 1

    saldo = kld.get_sisa_kuota_libur_bulan_ini(barber_id, tenant_id)
    assert saldo == {"aktif": True, "kuota": 3, "terpakai": 1, "sisa": 2}


# 3. Kuota Libur HABIS, kuota gabungan Izin&Cuti TERSEDIA (atau belum
# dikonfigurasi/unlimited) -- Tandai Libur berikutnya OTOMATIS jadi Cuti.
def test_tandai_libur_melebihi_kuota_jadi_cuti(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=1)

    jenis1 = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")
    assert jenis1 == "libur"

    jenis2 = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-02")
    assert jenis2 == "cuti"
    # tanggal KEDUA TIDAK tercatat sebagai Libur -- dicatat sebagai Cuti disetujui.
    assert db.get_hari_libur(barber_id, 2026, 8) == 1
    pengajuan = izin_cuti_db.get_pengajuan_list(barber_id=barber_id, tenant_id=tenant_id)
    cuti_otomatis = [p for p in pengajuan if p["tanggal_mulai"] == "2026-08-02"]
    assert len(cuti_otomatis) == 1
    assert cuti_otomatis[0]["jenis"] == "cuti"
    assert cuti_otomatis[0]["status"] == "disetujui"
    assert cuti_otomatis[0]["diajukan_oleh"] == kld.DIAJUKAN_OLEH_KUOTA_LIBUR


# 4. KEDUA kuota (Libur DAN Izin&Cuti gabungan) sama-sama habis -- tetap
# ditandai Libur, TAPI sumber='kelebihan_kuota' (stabilo merah di Rekap).
def test_tandai_libur_kedua_kuota_habis_jadi_kelebihan_kuota(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=1, kuota_periode_bulan=1,
                                    periode_mulai_dasar="2026-08-01", kuota_gabungan_hari=1)
    # Habiskan kuota gabungan Izin&Cuti (1 hari) lewat pengajuan Cuti asli lain.
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-15", "2026-08-15",
                                 "Cuti biasa", tenant_id=tenant_id, override=True)

    jenis1 = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")  # kuota libur dipakai
    assert jenis1 == "libur"

    jenis2 = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-02")  # KEDUA kuota sudah habis
    assert jenis2 == "kelebihan_kuota"
    assert db.get_hari_libur(barber_id, 2026, 8) == 2  # tanggal 1 & 2 TETAP tercatat Libur
    assert kld.ada_kelebihan_kuota_bulan_ini(barber_id, 2026, 8) is True


# 5. Kartu "Sisa Kuota Libur" nonaktif selama Owner belum mengisi kuota_libur_bulanan.
def test_get_sisa_kuota_libur_default_nonaktif(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    assert kld.get_sisa_kuota_libur_bulan_ini(barber_id, tenant_id) == {
        "aktif": False, "kuota": None, "terpakai": None, "sisa": None,
    }


# 6. Setting kuota_libur_bulanan tersimpan & tervalidasi lewat set_cuti_settings
# (tidak boleh negatif) -- fungsi ini TIDAK disentuh, hanya dipastikan tetap jalan.
def test_set_cuti_settings_kuota_libur_bulanan_tersimpan(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    hasil = izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=5)
    assert hasil["kuota_libur_bulanan"] == 5


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: Tandai Libur DITOLAK kalau tanggal sudah tercakup
# pengajuan Izin/Cuti yang DISETUJUI -- cegah satu tanggal tercatat ganda
# (Libur DAN Cuti/Izin sekaligus), yang sebelumnya bikin Rekap & Bonus
# Customer (hari_libur) salah hitung.
# ---------------------------------------------------------------------------

def test_tandai_libur_ditolak_kalau_sedang_cuti(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-10-10", "2026-10-13",
                                 "Cuti keluarga", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(
        izin_cuti_db.get_pengajuan_list(barber_id=barber_id, tenant_id=tenant_id)[0]["id"],
        "disetujui", disetujui_oleh="Owner",
    )
    try:
        kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-10-11")
        assert False, "Seharusnya ValueError"
    except ValueError as e:
        assert "Cuti" in str(e)
    assert db.get_hari_libur(barber_id, 2026, 10) == 0  # tidak ada baris Libur yang kebuat


def test_tandai_libur_ditolak_kalau_sedang_izin(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-10-11", "2026-10-11",
                                 "Keperluan keluarga", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(
        izin_cuti_db.get_pengajuan_list(barber_id=barber_id, tenant_id=tenant_id)[0]["id"],
        "disetujui", disetujui_oleh="Owner",
    )
    try:
        kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-10-11")
        assert False, "Seharusnya ValueError"
    except ValueError as e:
        assert "Izin" in str(e)


def test_tandai_libur_tetap_boleh_di_luar_rentang_cuti(single_tenant):
    """Validasi hanya menolak tanggal yang MEMANG tercakup rentang Cuti/Izin
    -- tanggal lain tetap bisa ditandai Libur seperti biasa."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-10-10", "2026-10-13",
                                 "Cuti keluarga", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(
        izin_cuti_db.get_pengajuan_list(barber_id=barber_id, tenant_id=tenant_id)[0]["id"],
        "disetujui", disetujui_oleh="Owner",
    )
    jenis = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-10-14")  # sehari setelah cuti berakhir
    assert jenis == "libur"


def test_tandai_libur_tetap_boleh_kalau_cuti_masih_pending(single_tenant):
    """Validasi hanya menolak pengajuan yang SUDAH disetujui -- yang masih
    pending tidak menghalangi Tandai Libur."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-10-10", "2026-10-13",
                                 "Cuti keluarga", tenant_id=tenant_id, override=True)  # tetap 'pending'
    jenis = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-10-11")
    assert jenis == "libur"


def test_router_tandai_libur_ditolak_422_kalau_sedang_cuti(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-10-10", "2026-10-13",
                                 "Cuti keluarga", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(
        izin_cuti_db.get_pengajuan_list(barber_id=barber_id, tenant_id=tenant_id)[0]["id"],
        "disetujui", disetujui_oleh="Owner",
    )
    r = client.post("/api/input-data/libur", json={"barber_id": barber_id, "tanggal": "2026-10-11"}, headers=headers)
    assert r.status_code == 422
    assert "Cuti" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Router-level (HTTP) -- pastikan wiring routers/input_data.py,
# routers/izin_cuti.py, routers/rekap.py benar.
# ---------------------------------------------------------------------------

def test_router_tandai_libur_mengembalikan_jenis(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    client.put("/api/izin-cuti/pengaturan", json={"kuota_libur_bulanan": 1}, headers=headers)

    r1 = client.post("/api/input-data/libur", json={"barber_id": barber_id, "tanggal": "2026-08-01"}, headers=headers)
    assert r1.status_code == 200, r1.text
    assert r1.json() == {"ok": True, "jenis": "libur"}

    r2 = client.post("/api/input-data/libur", json={"barber_id": barber_id, "tanggal": "2026-08-02"}, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json() == {"ok": True, "jenis": "cuti"}


def test_router_saldo_menyertakan_libur(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    client.put("/api/izin-cuti/pengaturan", json={"kuota_libur_bulanan": 3}, headers=headers)
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")

    r = client.get(f"/api/izin-cuti/saldo?barber_id={barber_id}", headers=headers)
    assert r.status_code == 200, r.text
    libur = r.json()["libur"]
    assert libur["aktif"] is True
    assert libur["kuota"] == 3


def test_router_saldo_semua_barber_menyertakan_libur_dan_kuota_habis(single_tenant, monkeypatch):
    _patch_hari_ini(monkeypatch, "2026-08-15")
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    client.put("/api/izin-cuti/pengaturan", json={"kuota_libur_bulanan": 1, "kuota_periode_bulan": 1,
                                                   "periode_mulai_dasar": "2026-08-01", "kuota_gabungan_hari": 1},
               headers=headers)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-15", "2026-08-15",
                                 "Cuti biasa", tenant_id=tenant_id, override=True)
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-02")  # kelebihan_kuota

    r = client.get("/api/izin-cuti/saldo-semua-barber", headers=headers)
    assert r.status_code == 200, r.text
    baris = next(b for b in r.json() if b["barber_id"] == barber_id)
    assert baris["libur"]["aktif"] is True
    assert baris["kuota_habis"] is True


def test_router_rekap_bulanan_menyertakan_kuota_habis(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    client.put("/api/izin-cuti/pengaturan", json={"kuota_libur_bulanan": 1, "kuota_periode_bulan": 1,
                                                   "periode_mulai_dasar": "2026-08-01", "kuota_gabungan_hari": 1},
               headers=headers)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-15", "2026-08-15",
                                 "Cuti biasa", tenant_id=tenant_id, override=True)
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-02")  # kelebihan_kuota

    r = client.get("/api/rekap/bulanan", params={"tahun": 2026, "bulan": 8, "barber_id": barber_id}, headers=headers)
    assert r.status_code == 200, r.text
    baris = next(b for b in r.json() if b["barber_id"] == barber_id)
    assert baris["kuota_habis"] is True


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: tanda visual beda di kolom Keterangan Rekap Transaksi
# untuk tanggal yang Tandai Libur-nya "nebeng" kuota lain (bukan kuota
# Libur asli) -- lihat kuota_libur_db.py::tandai_rekap_transaksi_kuota().
# ---------------------------------------------------------------------------

def test_rekap_transaksi_tandai_libur_dari_kuota_cuti_izin(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=1)
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")  # kuota libur dipakai
    jenis = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-02")  # auto-Cuti
    assert jenis == "cuti"

    data = db.get_rekap_transaksi_list(tahun=2026, bulan=8, barber_id=barber_id, tenant_id=tenant_id)
    data = kld.tandai_rekap_transaksi_kuota(data, tahun=2026, bulan=8, barber_id=barber_id, tenant_id=tenant_id)

    baris_asli = next(r for r in data if r["tanggal"] == "2026-08-01")
    assert baris_asli["keterangan"] == "Libur"
    assert baris_asli.get("dari_kuota_cuti_izin") is not True

    baris_otomatis = next(r for r in data if r["tanggal"] == "2026-08-02")
    assert baris_otomatis["tipe"] == "libur"
    assert baris_otomatis["keterangan"] == "Libur ⚠️"
    assert baris_otomatis["dari_kuota_cuti_izin"] is True
    assert baris_otomatis["barber_id"] == barber_id


def test_rekap_transaksi_tandai_libur_kelebihan_kuota(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=1, kuota_periode_bulan=1,
                                    periode_mulai_dasar="2026-08-01", kuota_gabungan_hari=1)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-15", "2026-08-15",
                                 "Cuti biasa", tenant_id=tenant_id, override=True)
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")  # kuota libur dipakai
    jenis = kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-02")  # kelebihan_kuota
    assert jenis == "kelebihan_kuota"

    data = db.get_rekap_transaksi_list(tahun=2026, bulan=8, barber_id=barber_id, tenant_id=tenant_id)
    data = kld.tandai_rekap_transaksi_kuota(data, tahun=2026, bulan=8, barber_id=barber_id, tenant_id=tenant_id)

    baris = next(r for r in data if r["tanggal"] == "2026-08-02")
    assert baris["keterangan"] == "Libur 🔴"
    assert baris.get("dari_kuota_cuti_izin") is not True  # tombol Hapus Libur TETAP ada


def test_router_rekap_transaksi_menandai_libur_dari_kuota(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=1)
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-01")
    kld.tandai_libur_dengan_kuota(barber_id, tenant_id, "2026-08-02")  # auto-Cuti

    r = client.get("/api/rekap/transaksi", params={"tahun": 2026, "bulan": 8, "barber_id": barber_id},
                    headers=headers)
    assert r.status_code == 200, r.text
    baris = next(b for b in r.json() if b["tanggal"] == "2026-08-02")
    assert baris["keterangan"] == "Libur ⚠️"
    assert baris["dari_kuota_cuti_izin"] is True
