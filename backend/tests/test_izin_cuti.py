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
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=10,
                                    kuota_boleh_dipecah=True, periode_mulai_dasar="2026-01-01")
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
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-01-01")
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
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=12, kuota_gabungan_hari=12,
                                    kuota_boleh_dipecah=True, periode_mulai_dasar="2026-01-01")
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
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=10,
                                    kuota_boleh_dipecah=False, periode_mulai_dasar="2026-01-01")
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
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-01-01")
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
# jenis='izin' TIDAK PERNAH terikat H-min/maksimal_bersamaan (KHUSUS cuti)
# -- TAPI TETAP kena aturan sendiri (maksimal 2 hari berturut-turut, lihat
# PERBAIKAN Sistem Kuota IZIN & CUTI di bawah).
# ---------------------------------------------------------------------------

def test_izin_tidak_terikat_h_min_dan_maksimal_bersamaan_cuti(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Izin A")
    barber_b = _barber(tenant_id, "Barber Izin B")
    izin_cuti_db.set_cuti_settings(tenant_id, h_min_pengajuan=30, maksimal_bersamaan=1)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    # A ambil izin mendadak (H+0, jauh di bawah H-30 CUTI) dan dobel dengan
    # izin B pada tanggal yang sama (maksimal_bersamaan CUTI tidak berlaku).
    izin_cuti_db.buat_pengajuan(barber_a, "izin", "2026-08-15", "2026-08-16", "Sakit A", tenant_id=tenant_id)
    hasil_b = izin_cuti_db.buat_pengajuan(barber_b, "izin", "2026-08-15", "2026-08-16",
                                           "Sakit B juga", tenant_id=tenant_id)
    assert hasil_b["status"] == "pending"


def test_izin_1_hari_valid(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-08-15", "2026-08-15",
                                         "Sakit 1 hari", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


def test_izin_2_hari_berturut_turut_valid(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-08-15", "2026-08-16",
                                         "Sakit 2 hari", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


def test_izin_lebih_dari_2_hari_ditolak_harus_pakai_cuti(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-08-15", "2026-08-17",
                                     "Izin 3 hari (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (izin maksimal 2 hari berturut-turut)"
    except ValueError as e:
        assert "2 hari" in str(e) and "cuti" in str(e).lower()


def test_izin_tidak_pernah_punya_h_min_meski_field_legacy_diisi_langsung(single_tenant, monkeypatch):
    """h_min_pengajuan_izin (kolom lama, sisa historis mode 'terpisah' yang
    sudah dihapus) SUDAH TIDAK DIBACA sama sekali -- izin TETAP boleh
    mendadak walau field itu diisi langsung lewat set_cuti_settings()
    (router tidak lagi menerima field ini dari frontend sama sekali)."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, h_min_pengajuan_izin=5)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-08-16", "2026-08-16",
                                         "Izin H+1 tetap boleh", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


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
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=1, maksimal_bersamaan=1,
                                    periode_mulai_dasar="2026-01-01")
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
    for key in ("kuota_periode_bulan", "kuota_gabungan_hari", "h_min_pengajuan", "maksimal_bersamaan"):
        try:
            izin_cuti_db.set_cuti_settings(tenant_id, **{key: -1})
            assert False, f"Seharusnya ValueError utk {key}=-1"
        except ValueError:
            pass


def test_set_cuti_settings_menolak_periode_tanpa_kuota_gabungan(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=0,
                                        periode_mulai_dasar="2026-01-01")
        assert False, "Seharusnya ValueError (periode aktif tapi kuota gabungan 0)"
    except ValueError:
        pass


def test_set_cuti_settings_menolak_periode_tanpa_tanggal_mulai(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=10)
        assert False, "Seharusnya ValueError (periode aktif tapi periode_mulai_dasar kosong)"
    except ValueError as e:
        assert "tanggal mulai periode" in str(e).lower()


def test_set_cuti_settings_mode_kuota_selalu_dipaksa_gabungan(single_tenant):
    """PERBAIKAN Sistem Kuota IZIN & CUTI (permintaan Owner): model
    'terpisah' DIHAPUS -- mode_kuota SELALU 'gabungan' terlepas dari nilai
    apa pun yang dicoba dikirim (termasuk kalau seseorang memanggil
    set_cuti_settings() langsung dengan mode_kuota='terpisah')."""
    tenant_id = single_tenant["tenant_id"]
    settings = izin_cuti_db.set_cuti_settings(tenant_id, mode_kuota="terpisah")
    assert settings["mode_kuota"] == "gabungan"


def test_set_cuti_settings_menolak_kuota_libur_bulanan_negatif(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=-1)
        assert False, "Seharusnya ValueError utk kuota_libur_bulanan=-1"
    except ValueError:
        pass


def test_get_sisa_kuota_gabungan_pada_tanggal_periode_berbeda(single_tenant):
    """KOREKSI Owner (Auto-Libur): dipakai untuk tanggal MASA LALU tertentu
    -- periode kuotanya HARUS mengikuti tanggal itu sendiri, bukan "hari
    ini"."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=5,
                                    periode_mulai_dasar="2026-01-01")
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-01-05", "2026-01-07", "Cuti 3 hari",
                                 tenant_id=tenant_id, override=True)
    sisa_jan = izin_cuti_db.get_sisa_kuota_gabungan_pada_tanggal(barber_id, tenant_id, "2026-01-20")
    assert sisa_jan == 2
    # Periode Februari -- bucket BEDA, belum terpakai sama sekali.
    sisa_feb = izin_cuti_db.get_sisa_kuota_gabungan_pada_tanggal(barber_id, tenant_id, "2026-02-10")
    assert sisa_feb == 5


def test_get_sisa_kuota_gabungan_pada_tanggal_none_kalau_kuota_off(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    assert izin_cuti_db.get_sisa_kuota_gabungan_pada_tanggal(barber_id, tenant_id, "2026-01-01") is None


# ---------------------------------------------------------------------------
# Router /api/izin-cuti/pengaturan
# ---------------------------------------------------------------------------

def test_router_pengaturan_get_put(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/izin-cuti/pengaturan", headers=headers)
    assert r.status_code == 200
    assert r.json()["kuota_periode_bulan"] == 0

    r2 = client.put("/api/izin-cuti/pengaturan",
                     json={"kuota_periode_bulan": 3, "kuota_gabungan_hari": 10, "h_min_pengajuan": 3,
                           "maksimal_bersamaan": 1, "periode_mulai_dasar": "2026-01-01"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["kuota_gabungan_hari"] == 10
    assert r2.json()["mode_kuota"] == "gabungan"


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


# ---------------------------------------------------------------------------
# FITUR Running Text Info Cuti (Absensi Barber) -- get_info_cuti_marquee()
# ---------------------------------------------------------------------------

def test_marquee_sedang_cuti_disetujui_dalam_rentang(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id, "Rafik")
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-22")
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-21", "2026-08-23", "Liburan", tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui")

    hasil = izin_cuti_db.get_info_cuti_marquee(tenant_id)
    assert len(hasil) == 1
    assert hasil[0] == {"nama_barber": "Rafik", "status": "sedang_cuti",
                         "tanggal_mulai": "2026-08-21", "tanggal_selesai": "2026-08-23"}


def test_marquee_pengajuan_pending_belum_mulai(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id, "Jaka")
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-22")
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-25", "2026-08-27", "Acara keluarga", tenant_id=tenant_id)

    hasil = izin_cuti_db.get_info_cuti_marquee(tenant_id)
    assert len(hasil) == 1
    assert hasil[0]["status"] == "pengajuan"
    assert hasil[0]["nama_barber"] == "Jaka"


def test_marquee_pengajuan_disetujui_belum_mulai_tetap_muncul(single_tenant, monkeypatch):
    """Cuti yang SUDAH disetujui tapi belum mulai tetap masuk kategori
    'pengajuan' -- relevan diinformasikan ke barber lain, bukan cuma yang
    masih menunggu keputusan."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id, "Yoga")
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-22")
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-25", "2026-08-26", "Nikahan", tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui")

    hasil = izin_cuti_db.get_info_cuti_marquee(tenant_id)
    assert len(hasil) == 1
    assert hasil[0]["status"] == "pengajuan"


def test_marquee_ditolak_tidak_muncul(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-22")
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-25", "2026-08-26", "Ditolak nanti", tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p["id"], "ditolak")

    assert izin_cuti_db.get_info_cuti_marquee(tenant_id) == []


def test_marquee_pending_tanggal_mulai_sudah_lewat_tidak_muncul(single_tenant, monkeypatch):
    """Pending yang tanggal_mulai-nya sudah lewat (belum diputuskan padahal
    harusnya sudah mulai) sengaja tidak masuk kategori manapun -- bukan
    'sedang cuti' (belum disetujui), bukan 'pengajuan belum mulai'
    (tanggalnya sudah lewat)."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-15")
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-20", "2026-08-22", "Telat diproses", tenant_id=tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-25")

    assert izin_cuti_db.get_info_cuti_marquee(tenant_id) == []


def test_marquee_izin_tidak_muncul(single_tenant, monkeypatch):
    """jenis='izin' (bukan 'cuti') TIDAK PERNAH ikut running text ini --
    ad-hoc/mendadak, bukan cuti terjadwal."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-22")
    p = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-08-22", "2026-08-22", "Sakit", tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui")

    assert izin_cuti_db.get_info_cuti_marquee(tenant_id) == []


def test_marquee_sudah_selesai_tidak_muncul(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-10")
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-08-10", "2026-08-12", "Sudah lewat", tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui")
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-22")

    assert izin_cuti_db.get_info_cuti_marquee(tenant_id) == []


def test_marquee_kosong_tanpa_data(single_tenant):
    assert izin_cuti_db.get_info_cuti_marquee(single_tenant["tenant_id"]) == []


def test_marquee_multiple_urut_tanggal_mulai(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_a = _barber(tenant_id, "Barber Z")
    barber_b = _barber(tenant_id, "Barber A")
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-20")
    p1 = izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-08-20", "2026-08-21", "Cuti 1", tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p1["id"], "disetujui")
    izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-08-25", "2026-08-26", "Cuti 2", tenant_id=tenant_id)

    hasil = izin_cuti_db.get_info_cuti_marquee(tenant_id)
    assert len(hasil) == 2
    assert hasil[0]["nama_barber"] == "Barber Z" and hasil[0]["status"] == "sedang_cuti"
    assert hasil[1]["nama_barber"] == "Barber A" and hasil[1]["status"] == "pengajuan"


def test_marquee_isolasi_tenant(two_tenants, monkeypatch):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = _barber(tenant_a)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-20")
    p = izin_cuti_db.buat_pengajuan(barber_a, "cuti", "2026-08-20", "2026-08-21", "Cuti A", tenant_id=tenant_a)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui")

    assert len(izin_cuti_db.get_info_cuti_marquee(tenant_a)) == 1
    assert izin_cuti_db.get_info_cuti_marquee(tenant_b) == []


def test_router_marquee_barber_bisa_lihat_punya_barber_lain(single_tenant, monkeypatch):
    """BEDA dari GET /api/izin-cuti biasa (barber cuma lihat miliknya
    sendiri) -- endpoint /marquee SENGAJA tenant-wide, data minimal (nama +
    tanggal + status, tanpa alasan) supaya barber lain bisa melihat
    informasi cuti rekan kerjanya."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import auth_db
    barber_lain_id = db.add_barber("Barber Lain Marquee", tenant_id=tenant_id)
    barber_login_id = db.add_barber("Barber Login Marquee", tenant_id=tenant_id)
    auth_db.tambah_user("barbermarquee", "passwordB123", role="barber", barber_id=barber_login_id,
                         tenant_id=tenant_id)

    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-08-20")
    p = izin_cuti_db.buat_pengajuan(barber_lain_id, "cuti", "2026-08-20", "2026-08-21", "Cuti",
                                     tenant_id=tenant_id)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui")

    r_login = client.post("/api/auth/login", json={"username": "barbermarquee", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}
    r = client.get("/api/izin-cuti/marquee", headers=headers_barber)
    assert r.status_code == 200
    hasil = r.json()
    assert len(hasil) == 1
    assert hasil[0]["nama_barber"] == "Barber Lain Marquee"
    assert "alasan" not in hasil[0]


# ---------------------------------------------------------------------------
# REVISI Sistem Dinamis Cuti & Izin (permintaan Owner, Agustus 2026) +
# PERBAIKAN Sistem Kuota IZIN & CUTI (permintaan Owner, revisi berikutnya):
# SATU saldo kuota bersama Izin+Cuti (model 'terpisah' DIHAPUS), aturan
# pengajuan tetap beda per jenis (Izin: mendadak boleh + maks 2 hari
# berturut-turut; Cuti: H-min dinamis + maksimal bersamaan dinamis),
# periode diangkar ke tanggal bebas (BUKAN lagi selalu Januari), tanpa
# carry-over antar periode.
# ---------------------------------------------------------------------------

def test_kuota_bersama_izin_dan_cuti_mengurangi_saldo_yang_sama_contoh_owner(single_tenant, monkeypatch):
    """Contoh PERSIS spesifikasi Owner: total kuota 10 hari, CUTI 3 hari ->
    sisa 7, lalu IZIN 2 hari -> sisa 5 -- SATU saldo bersama, BUKAN dua
    kuota terpisah (kuota_izin/kuota_cuti TIDAK ADA lagi)."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-01-01")
    # get_sisa_kuota() menghitung periode AKTIF dari "hari ini" -- dipatok
    # di dalam periode Jan-Mar 2026 yang sama dengan seluruh pengajuan di
    # bawah.
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-01-20")
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-01-05", "2026-01-07", "Cuti 3 hari",
                                 tenant_id=tenant_id)
    saldo1 = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo1["aktif"] is True
    assert saldo1["mode_kuota"] == "gabungan"
    assert saldo1["sisa_gabungan"] == 7

    izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-01-10", "2026-01-11", "Izin 2 hari",
                                 tenant_id=tenant_id)
    saldo2 = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo2["sisa_gabungan"] == 5

    # Kuota TERSISA 5 -- mengajukan cuti 6 hari (lintas jenis dengan izin
    # yang sudah dipakai) harus ditolak.
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-01-15", "2026-01-20",
                                     "Cuti 6 hari (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (kuota tersisa 5 hari)"
    except ValueError as e:
        assert "tersisa 5 hari" in str(e)


def test_periode_diangkar_ke_tanggal_bebas_bukan_selalu_januari(single_tenant):
    """periode_mulai_dasar BUKAN 1 Januari -- bucket periode HARUS
    mengikuti angkar itu, bukan tahun kalender seperti perilaku lama."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-09-01")
    # Periode pertama: Sep-Nov 2026. September + Oktober -> 4+3 = 7 hari.
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-05", "2026-09-08", "Sep", tenant_id=tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-10-05", "2026-10-07", "Okt", tenant_id=tenant_id)
    saldo = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    # (get_sisa_kuota pakai HARI INI, bukan tanggal pengajuan -- cek periode
    # lewat _periode_kuota() langsung supaya independen dari hari ini.)
    periode_awal, periode_akhir = izin_cuti_db._periode_kuota("2026-11-01", 3, "2026-09-01")
    assert (periode_awal, periode_akhir) == ("2026-09-01", "2026-11-30")
    # Desember 2026 SUDAH periode BERIKUTNYA (Des-Feb), bukan lagi Sep-Nov.
    periode_des_awal, periode_des_akhir = izin_cuti_db._periode_kuota("2026-12-01", 3, "2026-09-01")
    assert (periode_des_awal, periode_des_akhir) == ("2026-12-01", "2027-02-28")
    assert saldo is not None  # sanity: get_sisa_kuota tidak error


def test_no_carry_over_periode_baru_selalu_kuota_flat(single_tenant):
    """PERSIS 4 contoh spesifikasi Owner (kuota=10hari/bulan): sisa 2 hari
    di periode lama TIDAK PERNAH terbawa ke periode baru -- periode baru
    SELALU tepat kuota yang dikonfigurasi, tidak kurang tidak lebih."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-01-01")
    # Januari: pakai 8 hari (sisa 2) -- TIDAK dibawa ke Februari.
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-01-01", "2026-01-08", "Jan 8 hari",
                                 tenant_id=tenant_id)
    # Februari: 10 hari PENUH tetap diizinkan (BUKAN 10+2=12).
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-02-01", "2026-02-10", "Feb 10 hari",
                                         tenant_id=tenant_id)
    assert hasil["status"] == "pending"
    # 11 hari di Maret HARUS ditolak (kuota flat 10, bukan lebih).
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-03-01", "2026-03-11",
                                     "Mar 11 hari (harusnya ditolak)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (kuota Maret tetap 10, bukan terakumulasi)"
    except ValueError as e:
        assert "tersisa 10 hari" in str(e)


def test_periode_mulai_dasar_tidak_berlaku_untuk_tanggal_sebelum_anchor(single_tenant):
    """Tanggal SEBELUM periode_mulai_dasar (data/pengajuan lama, sebelum
    sistem kuota dinamis diaktifkan) TIDAK PERNAH divalidasi lewat mesin
    kuota -- walau kuotanya sangat ketat (1 hari/periode)."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=3, kuota_gabungan_hari=1,
                                    periode_mulai_dasar="2026-09-01")
    # 20 hari cuti di Juni 2026 (SEBELUM angkar Sep 2026) -- tetap diizinkan.
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-06-01", "2026-06-20",
                                         "Cuti lama sebelum sistem dinamis", tenant_id=tenant_id)
    assert hasil["status"] == "pending"
    # Tapi begitu tanggal_mulai >= periode_mulai_dasar, kuota ketat berlaku.
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-05", "2026-09-06",
                                     "Cuti baru 2 hari (harusnya ditolak, kuota 1)", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (kuota periode baru aktif, 1 hari)"
    except ValueError as e:
        assert "tersisa 1 hari" in str(e)


def test_get_sisa_kuota_nonaktif_kalau_belum_dikonfigurasi(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    saldo = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo["aktif"] is False
    assert saldo["sisa_gabungan"] is None


def test_router_saldo_barber_lihat_milik_sendiri_saja(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    import auth_db
    barber_id = db.add_barber("Barber Saldo Router", tenant_id=tenant_id)
    auth_db.tambah_user("barbersaldo", "passwordB123", role="barber", barber_id=barber_id,
                         tenant_id=tenant_id)
    client.put("/api/izin-cuti/pengaturan",
               json={"kuota_periode_bulan": 3, "kuota_gabungan_hari": 10, "periode_mulai_dasar": "2026-01-01"},
               headers=headers)

    r_login = client.post("/api/auth/login", json={"username": "barbersaldo", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}
    r = client.get("/api/izin-cuti/saldo", headers=headers_barber)
    assert r.status_code == 200
    assert r.json()["mode_kuota"] == "gabungan"

    r_admin = client.get(f"/api/izin-cuti/saldo?barber_id={barber_id}", headers=headers)
    assert r_admin.status_code == 200


def test_router_saldo_menyertakan_libur_nonaktif_default(single_tenant):
    """KOREKSI Owner: /saldo SEKARANG juga menyertakan field `libur`
    (Kuota Libur bulan berjalan, auto_libur_db.py) -- default OFF (aktif
    False) selama Owner belum mengisi kuota_libur_bulanan."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    r = client.get(f"/api/izin-cuti/saldo?barber_id={barber_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["libur"] == {"aktif": False, "kuota": None, "terpakai": None, "sisa": None}


def test_router_marquee_butuh_login(single_tenant):
    client = single_tenant["client"]
    r = client.get("/api/izin-cuti/marquee")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# PERBAIKAN Owner: Izin/Cuti baru TIDAK BOLEH diajukan untuk tanggal yang
# sudah tercatat Libur (manual ATAU Auto-Libur) -- dua catatan bertentangan
# untuk hari yang sama.
# ---------------------------------------------------------------------------

def test_buat_pengajuan_ditolak_kalau_tanggal_sudah_libur_manual(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    db.tandai_libur(barber_id, "2026-09-02")
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-02",
                                     "Coba", tenant_id=tenant_id)
        assert False, "Seharusnya ValueError (tanggal sudah Libur)"
    except ValueError as e:
        assert "2026-09-02" in str(e)
        assert "Libur" in str(e)


def test_buat_pengajuan_ditolak_kalau_tanggal_sudah_libur_meski_override(single_tenant):
    """PERBAIKAN Owner: ini soal integritas DATA (bukan kebijakan kuota/
    H-min) -- SELALU dicek, TERMASUK saat Owner/Admin/Staff mengajukan
    ATAS NAMA barber (override=True)."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    db.tandai_libur(barber_id, "2026-09-01")
    try:
        izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-01", "2026-09-01",
                                     "Coba override", tenant_id=tenant_id, override=True)
        assert False, "Seharusnya ValueError meski override=True"
    except ValueError as e:
        assert "Libur" in str(e)


def test_buat_pengajuan_boleh_kalau_tidak_ada_konflik_libur(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    db.tandai_libur(barber_id, "2026-09-10")  # tanggal LAIN, tidak beririsan
    hasil = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-02",
                                         "Aman", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


def test_edit_pengajuan_ditolak_kalau_tanggal_baru_sudah_libur(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    p = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-01",
                                     "Awal", tenant_id=tenant_id)
    db.tandai_libur(barber_id, "2026-09-05")
    try:
        izin_cuti_db.edit_pengajuan(p["id"], tanggal_mulai="2026-09-05", tanggal_selesai="2026-09-05")
        assert False, "Seharusnya ValueError"
    except ValueError as e:
        assert "Libur" in str(e)


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: Check In barber vs Cuti/Izin yang sedang berjalan --
# get_pengajuan_aktif_pada_tanggal()/potong_karena_checkin() (dipakai
# routers/attendance.py -- lihat test_router_checkin_saat_sedang_cuti_*
# di bawah untuk alur router lengkapnya).
# ---------------------------------------------------------------------------

def test_get_pengajuan_aktif_pada_tanggal_ditemukan(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-01", "2026-09-07",
                                     "Cuti panjang", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui", disetujui_oleh="Owner")
    hasil = izin_cuti_db.get_pengajuan_aktif_pada_tanggal(barber_id, "2026-09-05")
    assert hasil is not None
    assert hasil["id"] == p["id"]


def test_get_pengajuan_aktif_pada_tanggal_tidak_ditemukan_kalau_pending(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-01", "2026-09-07",
                                 "Belum disetujui", tenant_id=tenant_id, override=True)
    assert izin_cuti_db.get_pengajuan_aktif_pada_tanggal(barber_id, "2026-09-05") is None


def test_potong_karena_checkin_contoh_owner_1_sampai_7_checkin_hari_ke_5(single_tenant, monkeypatch):
    """CONTOH PERSIS Owner: Cuti/Izin tanggal 1-7, Check In di hari ke-5 ->
    yang dihitung/dianggap Cuti hanya tanggal 1-4, sisa 5-7 kembali ke
    kuota."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-09-10")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-09-01")
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-01", "2026-09-07",
                                     "Cuti seminggu", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui", disetujui_oleh="Owner")

    hasil = izin_cuti_db.potong_karena_checkin(p["id"], "2026-09-05")
    assert hasil == {"aksi": "dipotong", "tanggal_selesai_baru": "2026-09-04"}
    pengajuan_baru = izin_cuti_db.get_pengajuan(p["id"])
    assert pengajuan_baru["tanggal_mulai"] == "2026-09-01"
    assert pengajuan_baru["tanggal_selesai"] == "2026-09-04"
    assert pengajuan_baru["status"] == "disetujui"

    saldo = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo["sisa_gabungan"] == 6  # 10 - 4 hari (1-4) terpakai, 5-7 kembali


def test_potong_karena_checkin_hari_pertama_menghapus_seluruh_pengajuan(single_tenant, monkeypatch):
    """PERMINTAAN OWNER (kasus Romen): Check In di hari PERTAMA rentang --
    belum ada satu hari pun yang benar-benar dijalani -> SELURUH pengajuan
    dihapus, kuota kembali penuh."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-09-10")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-09-01")
    p = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-01",
                                     "Izin ternyata masuk", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui", disetujui_oleh="Owner")

    hasil = izin_cuti_db.potong_karena_checkin(p["id"], "2026-09-01")
    assert hasil == {"aksi": "dihapus", "tanggal_selesai_baru": None}
    assert izin_cuti_db.get_pengajuan(p["id"]) is None
    saldo = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo["sisa_gabungan"] == 10


def test_potong_karena_checkin_pengajuan_pending_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    p = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-01",
                                     "Masih pending", tenant_id=tenant_id)
    try:
        izin_cuti_db.potong_karena_checkin(p["id"], "2026-09-01")
        assert False, "Seharusnya ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: Owner/Admin batalkan pengajuan yang SUDAH disetujui
# (mis. barber ternyata tetap masuk kerja) -- batalkan_pengajuan_disetujui()
# + POST /api/izin-cuti/{id}/batalkan.
# ---------------------------------------------------------------------------

def test_batalkan_pengajuan_disetujui_menghapus_dan_kembalikan_kuota(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    monkeypatch.setattr(izin_cuti_db, "_hari_ini_wib", lambda: "2026-09-10")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=1, kuota_gabungan_hari=10,
                                    periode_mulai_dasar="2026-09-01")
    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-01", "2026-09-03",
                                     "Cuti", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui", disetujui_oleh="Owner")
    saldo_sebelum = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo_sebelum["sisa_gabungan"] == 7

    hasil = izin_cuti_db.batalkan_pengajuan_disetujui(p["id"])
    assert hasil["id"] == p["id"]
    assert izin_cuti_db.get_pengajuan(p["id"]) is None
    saldo_sesudah = izin_cuti_db.get_sisa_kuota(barber_id, tenant_id)
    assert saldo_sesudah["sisa_gabungan"] == 10


def test_batalkan_pengajuan_pending_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    p = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-01",
                                     "Masih pending", tenant_id=tenant_id)
    try:
        izin_cuti_db.batalkan_pengajuan_disetujui(p["id"])
        assert False, "Seharusnya ValueError"
    except ValueError:
        pass


def test_router_batalkan_pengajuan_disetujui(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    p = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-01",
                                     "Coba", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui", disetujui_oleh="Owner")

    r = client.post(f"/api/izin-cuti/{p['id']}/batalkan", headers=headers)
    assert r.status_code == 200
    assert izin_cuti_db.get_pengajuan(p["id"]) is None


def test_router_batalkan_pengajuan_pending_ditolak_422(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    p = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-01",
                                     "Masih pending", tenant_id=tenant_id)
    r = client.post(f"/api/izin-cuti/{p['id']}/batalkan", headers=headers)
    assert r.status_code == 422


def test_router_checkin_saat_sedang_cuti_minta_konfirmasi_lalu_memotong_rentang(single_tenant, monkeypatch):
    """PERMINTAAN OWNER: barber Check In padahal tercatat sedang Cuti hari
    ini -- backend membalas 409 dulu (BELUM check-in, belum ada baris
    attendance_logs), lalu berhasil Check In + rentang Cuti dipotong begitu
    dikirim ulang dengan konfirmasi_cuti_izin=True."""
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id = single_tenant["tenant_id"]
    client.put("/api/attendance/settings",
               json={"lokasi_latitude": -6.175392, "lokasi_longitude": 106.827153, "radius_meter": 500,
                     "jam_masuk": "09:00", "jam_pulang": "20:00"},
               headers=headers)
    import auth_db
    barber_id = _barber(tenant_id, "Barber Checkin Cuti")
    auth_db.tambah_user("barbercheckincuti", "passwordB123", role="barber", barber_id=barber_id,
                         tenant_id=tenant_id)
    r_login = client.post("/api/auth/login", json={"username": "barbercheckincuti", "password": "passwordB123"})
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}

    p = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-01", "2026-09-07",
                                     "Cuti seminggu", tenant_id=tenant_id, override=True)
    izin_cuti_db.set_status_pengajuan(p["id"], "disetujui", disetujui_oleh="Owner")

    import attendance_db
    from datetime import datetime
    from zoneinfo import ZoneInfo
    wib = ZoneInfo("Asia/Jakarta")
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 9, 5, 10, 0, tzinfo=wib))

    payload = {"latitude": -6.175392, "longitude": 106.827153}
    r1 = client.post("/api/attendance/check-in", json=payload, headers=headers_barber)
    assert r1.status_code == 409
    assert r1.json()["detail"]["sedang_cuti_izin"] == {
        "jenis": "cuti", "tanggal_mulai": "2026-09-01", "tanggal_selesai": "2026-09-07",
    }
    r_today = client.get("/api/attendance/today", headers=headers_barber)
    assert r_today.json()["log"] is None  # belum benar-benar Check In

    r2 = client.post("/api/attendance/check-in", json={**payload, "konfirmasi_cuti_izin": True},
                      headers=headers_barber)
    assert r2.status_code == 200, r2.text
    assert r2.json()["cuti_izin_disesuaikan"] == {"aksi": "dipotong", "tanggal_selesai_baru": "2026-09-04"}

    pengajuan_baru = izin_cuti_db.get_pengajuan(p["id"])
    assert pengajuan_baru["tanggal_selesai"] == "2026-09-04"
