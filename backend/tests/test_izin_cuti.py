"""test_izin_cuti.py — Modul Karyawan: Izin & Cuti + FITUR Kebijakan Cuti
Dinamis (Kuota per periode, H-min pengajuan, Maksimal bersamaan)
=============================================================================
Cakupan: perilaku DASAR yang sudah ada (buat/edit/hapus/approve/reject,
riwayat) TIDAK BOLEH berubah -- semua skenario WAJIB dari spesifikasi Owner
(kuota dipecah 3 bulan, kuota tahunan, H-min ditolak/diizinkan, bentrok 1
orang & 2 orang PERSIS contoh Owner, status ditolak/dihapus tidak
menghalangi, override Owner/Admin/Staff, isolasi per-tenant, jenis='izin'
TIDAK PERNAH tersentuh kebijakan ini sama sekali)."""

import itertools

import database as db
import izin_cuti_db

_urutan_unik = itertools.count(1)


def _barber(tenant_id, nama=None):
    n = next(_urutan_unik)
    return db.add_barber(nama or f"Barber Cuti {n}", tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Perilaku DASAR (SUDAH ADA sebelum fitur ini) -- tidak boleh berubah
# ---------------------------------------------------------------------------

def test_buat_pengajuan_dasar_tetap_berfungsi(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-02",
                                         "Acara keluarga", tenant_id=tenant_id)
    assert hasil["status"] == "pending"
    assert hasil["jenis"] == "izin"


def test_edit_hapus_approve_reject_dasar_tetap_berfungsi(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    p = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-02",
                                     "Sakit", tenant_id=tenant_id)
    edited = izin_cuti_db.edit_pengajuan(p["id"], alasan="Sakit demam")
    assert edited["alasan"] == "Sakit demam"

    approved = izin_cuti_db.set_status_pengajuan(p["id"], "disetujui", disetujui_oleh="Owner")
    assert approved["status"] == "disetujui"

    p2 = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-10", "2026-09-11",
                                      "Urusan pribadi", tenant_id=tenant_id)
    izin_cuti_db.hapus_pengajuan(p2["id"])
    assert izin_cuti_db.get_pengajuan(p2["id"]) is None


# ---------------------------------------------------------------------------
# Default OFF -- backward compatible penuh (tenant belum konfigurasi apa pun)
# ---------------------------------------------------------------------------

def test_kebijakan_default_off_tidak_membatasi_apa_pun(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    assert settings["kuota_periode_bulan"] == 0
    assert settings["h_min_pengajuan"] == 0
    assert settings["maksimal_bersamaan"] == 0
    # Cuti besok (H-1) dan 30 hari sekaligus -- tidak ada batasan apa pun.
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-17", "2026-09-15",
                                         "Liburan panjang", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


# ---------------------------------------------------------------------------
# Kuota Cuti Dinamis -- Contoh 1 spesifikasi Owner: 10 hari / 3 bulan
# ---------------------------------------------------------------------------

def test_kuota_3_bulan_dipecah_multi_bulan_sesuai_contoh_owner(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_maksimal_hari=10,
                                    kuota_boleh_dipecah=True)
    # Januari 3 hari, Februari 2 hari, Maret 5 hari -> total 10 hari (Q1).
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-01-05", "2026-01-07", "Cuti 1", tenant_id=tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-02-10", "2026-02-11", "Cuti 2", tenant_id=tenant_id)
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-03-01", "2026-03-05", "Cuti 3", tenant_id=tenant_id)
    assert hasil["status"] == "pending"

    # Kuota SUDAH HABIS (10/10) -- pengajuan cuti berikutnya di periode yang
    # sama (Q1) HARUS ditolak.
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-03-20", "2026-03-20",
                                     "Cuti 4 (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (kuota habis)"
    except ValueError as e:
        assert "kuota" in str(e).lower() or "tersisa" in str(e).lower()


def test_kuota_melebihi_batas_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_maksimal_hari=10)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-01-05", "2026-01-12", "Cuti 8 hari", tenant_id=tenant_id)
    # Sisa 2 hari, mengajukan 3 hari -> ditolak.
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-02-01", "2026-02-03",
                                     "Cuti 3 hari (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (melebihi kuota)"
    except ValueError as e:
        assert "tersisa 2 hari" in str(e)


def test_kuota_tahunan_sesuai_contoh_owner(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=12, kuota_maksimal_hari=12,
                                    kuota_boleh_dipecah=True)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-01-05", "2026-01-06", "Jan", tenant_id=tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-03-10", "2026-03-12", "Mar", tenant_id=tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-06-01", "2026-06-02", "Jun", tenant_id=tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-01", "2026-09-02", "Sep", tenant_id=tenant_id)
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-12-01", "2026-12-03", "Des", tenant_id=tenant_id)
    assert hasil["status"] == "pending"  # total tepat 12 hari

    # Periode BARU (2027) -- kuota reset, boleh cuti lagi.
    hasil_2027 = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2027-01-05", "2027-01-06",
                                              "Jan tahun depan", tenant_id=tenant_id)
    assert hasil_2027["status"] == "pending"


def test_kuota_boleh_dipecah_false_menolak_pengajuan_kedua(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_maksimal_hari=10,
                                    kuota_boleh_dipecah=False)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-01-05", "2026-01-07", "Cuti pertama", tenant_id=tenant_id)
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-02-01", "2026-02-02",
                                     "Cuti kedua (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (kuota tidak boleh dipecah)"
    except ValueError as e:
        assert "dipecah" in str(e).lower()


def test_kuota_periode_lain_barber_tidak_saling_memengaruhi(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Kuota A")
    barber_b = _barber(tenant_id, "Barber Kuota B")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_maksimal_hari=10)
    izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-01-05", "2026-01-12", "A pakai 8 hari", tenant_id=tenant_id)
    # Barber B kuotanya SENDIRI, belum terpakai sama sekali.
    hasil = izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-01-05", "2026-01-12",
                                         "B pakai 8 hari juga", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


# ---------------------------------------------------------------------------
# Minimal H- pengajuan
# ---------------------------------------------------------------------------

def test_h_min_ditolak_kurang_dari_batas(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, h_min_pengajuan=3)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-16", "2026-08-16",
                                     "H+1 (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (H-min belum terpenuhi)"
    except ValueError as e:
        assert "H-3" in str(e)


def test_h_min_diizinkan_tepat_batas(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, h_min_pengajuan=3)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-18", "2026-08-18",
                                         "Tepat H-3", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


def test_h_min_default_off_boleh_mendadak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-15", "2026-08-15",
                                         "Cuti hari ini juga", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


# ---------------------------------------------------------------------------
# Maksimal karyawan cuti bersamaan -- PERSIS skenario spesifikasi Owner
# ---------------------------------------------------------------------------

def test_bersamaan_1_orang_skenario_owner(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Bentrok A")
    barber_b = _barber(tenant_id, "Barber Bentrok B")
    izin_cuti_db.set_cuti_settings(tenant_id, maksimal_bersamaan=1)
    izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-07-16", "2026-07-19", "A cuti", tenant_id=tenant_id)

    for mulai, selesai in [("2026-07-16", "2026-07-18"), ("2026-07-18", "2026-07-20"), ("2026-07-19", "2026-07-21")]:
        try:
            izin_cuti_db.buat_pengajuan(barber_b, "cuti", mulai, selesai,
                                         "B (harusnya ditolak)", tenant_id=tenant_id)
            assert False, f"Seharusnya ValueError utk rentang {mulai}..{selesai}"
        except ValueError as e:
            assert "1 orang" in str(e) or "karyawan lain" in str(e).lower()

    # 20 Juli dan seterusnya (TIDAK beririsan dengan 16-19 Juli) tetap boleh.
    hasil = izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-07-20", "2026-07-22",
                                         "B boleh", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


def test_bersamaan_2_orang_skenario_owner(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber 2Org A")
    barber_b = _barber(tenant_id, "Barber 2Org B")
    barber_c = _barber(tenant_id, "Barber 2Org C")
    izin_cuti_db.set_cuti_settings(tenant_id, maksimal_bersamaan=2)
    izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-07-16", "2026-07-19", "A", tenant_id=tenant_id)
    # B 18-20 Juli -- pada 18-19 jumlahnya jadi 2 orang, MASIH DIIZINKAN.
    hasil_b = izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-07-18", "2026-07-20", "B", tenant_id=tenant_id)
    assert hasil_b["status"] == "pending"
    # C 19-21 Juli -- tanggal 19 sudah 2 orang (A+B), DITOLAK.
    try:
        izin_cuti_db.buat_pengajuan(barber_c, "cuti", "2026-07-19", "2026-07-21",
                                     "C (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (tanggal 19 sudah 2 orang)"
    except ValueError as e:
        assert "2 orang" in str(e) or "karyawan lain" in str(e).lower()


def test_bersamaan_default_off_tidak_dibatasi(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Bebas A")
    barber_b = _barber(tenant_id, "Barber Bebas B")
    barber_c = _barber(tenant_id, "Barber Bebas C")
    izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-07-16", "2026-07-19", "A", tenant_id=tenant_id)
    izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-07-16", "2026-07-19", "B", tenant_id=tenant_id)
    hasil_c = izin_cuti_db.buat_pengajuan(barber_c, "cuti", "2026-07-16", "2026-07-19", "C", tenant_id=tenant_id)
    assert hasil_c["status"] == "pending"


# ---------------------------------------------------------------------------
# Status yang diperhitungkan: pending & disetujui SAJA -- ditolak/dihapus
# TIDAK PERNAH menghalangi tanggal orang lain
# ---------------------------------------------------------------------------

def test_status_ditolak_tidak_menghalangi_bentrok(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Ditolak A")
    barber_b = _barber(tenant_id, "Barber Ditolak B")
    izin_cuti_db.set_cuti_settings(tenant_id, maksimal_bersamaan=1)
    p = izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-07-16", "2026-07-19", "A", tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p["id"], "ditolak", disetujui_oleh="Owner")
    # A sudah DITOLAK -- B boleh ambil tanggal yang sama persis.
    hasil_b = izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-07-16", "2026-07-19",
                                           "B (harusnya boleh)", tenant_id=tenant_id)
    assert hasil_b["status"] == "pending"


def test_status_dihapus_tidak_menghalangi_bentrok(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Hapus A")
    barber_b = _barber(tenant_id, "Barber Hapus B")
    izin_cuti_db.set_cuti_settings(tenant_id, maksimal_bersamaan=1)
    p = izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-07-16", "2026-07-19", "A", tenant_id=tenant_id)
    izin_cuti_db.hapus_pengajuan(p["id"])
    hasil_b = izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-07-16", "2026-07-19",
                                           "B (harusnya boleh)", tenant_id=tenant_id)
    assert hasil_b["status"] == "pending"


def test_status_disetujui_tetap_menghalangi_bentrok(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Disetujui A")
    barber_b = _barber(tenant_id, "Barber Disetujui B")
    izin_cuti_db.set_cuti_settings(tenant_id, maksimal_bersamaan=1)
    p = izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-07-16", "2026-07-19", "A", tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui", disetujui_oleh="Owner")
    try:
        izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-07-16", "2026-07-19",
                                     "B (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (A sudah disetujui, masih menghalangi)"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# jenis='izin' TIDAK PERNAH tersentuh kebijakan ini sama sekali
# ---------------------------------------------------------------------------

def test_izin_tidak_terpengaruh_kebijakan_apa_pun(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Izin A")
    barber_b = _barber(tenant_id, "Barber Izin B")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_maksimal_hari=1,
                                    h_min_pengajuan=30, maksimal_bersamaan=1)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    # A ambil izin mendadak (H+0, jauh di bawah H-30) dan dobel dengan izin B.
    izin_cuti_db.buat_pengajuan(barber_a, "izin", "2026-08-15", "2026-08-20", "Sakit A", tenant_id=tenant_id)
    hasil_b = izin_cuti_db.buat_pengajuan(barber_b, "izin", "2026-08-15", "2026-08-20",
                                           "Sakit B juga", tenant_id=tenant_id)
    assert hasil_b["status"] == "pending"


# ---------------------------------------------------------------------------
# Override Owner/Admin/Staff -- melewati SELURUH kebijakan
# ---------------------------------------------------------------------------

def test_override_melewati_h_min(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, h_min_pengajuan=30)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-16", "2026-08-16",
                                         "Dibuatkan Owner", tenant_id=tenant_id, override=True)
    assert hasil["status"] == "pending"


def test_override_melewati_kuota_dan_bentrok(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Override A")
    barber_b = _barber(tenant_id, "Barber Override B")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_maksimal_hari=1, maksimal_bersamaan=1)
    izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-07-16", "2026-07-19", "A", tenant_id=tenant_id,
                                 override=True)
    hasil_b = izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-07-16", "2026-07-25",
                                           "B (10 hari, bentrok A)", tenant_id=tenant_id, override=True)
    assert hasil_b["status"] == "pending"


# ---------------------------------------------------------------------------
# edit_pengajuan() divalidasi ULANG -- tidak bisa dipakai membypass kebijakan
# ---------------------------------------------------------------------------

def test_edit_pengajuan_divalidasi_ulang(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, h_min_pengajuan=3)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-20", "2026-08-20",
                                     "Valid H-5", tenant_id=tenant_id)
    try:
        izin_cuti_db.edit_pengajuan(p["id"], tanggal_mulai="2026-08-16", tanggal_selesai="2026-08-16")
        assert False, "Seharusnya ValueError (edit ke H-1, melanggar H-3)"
    except ValueError as e:
        assert "H-3" in str(e)


def test_edit_pengajuan_tidak_menghitung_dirinya_sendiri_sebagai_bentrok(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, maksimal_bersamaan=1)
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-07-16", "2026-07-19",
                                     "Cuti asli", tenant_id=tenant_id)
    # Edit alasan saja (tanggal SAMA) -- tidak boleh dianggap "bentrok
    # dengan dirinya sendiri" dan ditolak.
    hasil = izin_cuti_db.edit_pengajuan(p["id"], alasan="Alasan diperbarui")
    assert hasil["alasan"] == "Alasan diperbarui"


def test_edit_pengajuan_override_melewati_validasi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, h_min_pengajuan=3)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-20", "2026-08-20",
                                     "Valid H-5", tenant_id=tenant_id)
    hasil = izin_cuti_db.edit_pengajuan(p["id"], tanggal_mulai="2026-08-16", tanggal_selesai="2026-08-16",
                                         override=True)
    assert hasil["tanggal_mulai"] == "2026-08-16"


# ---------------------------------------------------------------------------
# Isolasi per-tenant -- kebijakan tenant A tidak bocor ke tenant B
# ---------------------------------------------------------------------------

def test_isolasi_kebijakan_antar_tenant(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = _barber(tenant_a, "Barber Isolasi A")
    barber_b = _barber(tenant_b, "Barber Isolasi B")
    izin_cuti_db.set_cuti_settings(tenant_a, h_min_pengajuan=30, maksimal_bersamaan=1)
    # Tenant B TIDAK pernah mengatur apa pun -- tetap 100% bebas.
    hasil = izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-08-16", "2026-08-16",
                                         "Tenant B bebas", tenant_id=tenant_b)
    assert hasil["status"] == "pending"
    settings_b = izin_cuti_db.get_cuti_settings(tenant_b)
    assert settings_b["h_min_pengajuan"] == 0


# ---------------------------------------------------------------------------
# set_cuti_settings() -- validasi input
# ---------------------------------------------------------------------------

def test_set_cuti_settings_menolak_nilai_negatif(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    for key in ("kuota_periode_bulan", "kuota_maksimal_hari", "h_min_pengajuan", "maksimal_bersamaan"):
        try:
            izin_cuti_db.set_cuti_settings(tenant_id, **{key: -1})
            assert False, f"Seharusnya ValueError utk {key}=-1"
        except ValueError:
            pass


def test_set_cuti_settings_menolak_periode_tanpa_maksimal_hari(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_maksimal_hari=0)
        assert False, "Seharusnya ValueError (periode aktif tapi maksimal hari 0)"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Router /api/izin-cuti/pengaturan
# ---------------------------------------------------------------------------

def test_router_pengaturan_get_put(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/izin-cuti/pengaturan", headers=headers)
    assert r.status_code == 200
    assert r.json()["kuota_periode_bulan"] == 0

    r2 = client.put("/api/izin-cuti/pengaturan",
                     json={"kuota_periode_bulan": 3, "kuota_maksimal_hari": 10, "h_min_pengajuan": 3,
                           "maksimal_bersamaan": 1}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["kuota_maksimal_hari"] == 10


def test_router_pengaturan_butuh_login(single_tenant):
    client = single_tenant["client"]
    r = client.get("/api/izin-cuti/pengaturan")
    assert r.status_code == 401


def test_router_barber_ditolak_karena_h_min(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import auth_db
    barber_id = db.add_barber("Barber Router HMin", tenant_id=tenant_id)
    user_id = auth_db.tambah_user("barberhmin", "passwordB123", role="barber", barber_id=barber_id,
                                   tenant_id=tenant_id)
    client.put("/api/izin-cuti/pengaturan", json={"h_min_pengajuan": 30}, headers=headers)
    r_login = client.post("/api/auth/login", json={"username": "barberhmin", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}

    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    r = client.post("/api/izin-cuti", json={"jenis": "cuti", "tanggal_mulai": "2026-08-16",
                                             "tanggal_selesai": "2026-08-16", "alasan": "Mendadak"},
                     headers=headers_barber)
    assert r.status_code == 422
    assert "H-30" in r.json()["detail"]


def test_router_admin_override_boleh_walau_h_min(single_tenant, monkeypatch):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Router Override", tenant_id=tenant_id)
    client.put("/api/izin-cuti/pengaturan", json={"h_min_pengajuan": 30}, headers=headers)

    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    r = client.post("/api/izin-cuti", json={"barber_id": barber_id, "jenis": "cuti",
                                             "tanggal_mulai": "2026-08-16", "tanggal_selesai": "2026-08-16",
                                             "alasan": "Dibuatkan Owner"}, headers=headers)
    assert r.status_code == 200
