"""FITUR Uang Harian Dinamis Berdasarkan Absensi -- test suite.

Mengikuti pola test_attendance.py (conftest.py::single_tenant/two_tenants,
monkeypatch attendance_db._sekarang_wib() untuk kontrol waktu deterministik)
+ database.py untuk seed barber/service/transaksi. 23 skenario wajib sesuai
permintaan Owner (lihat komentar per fungsi)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import attendance_db
import database
import uang_harian_dinamis_db as uhd

WIB = ZoneInfo("Asia/Jakarta")
TOKO_LAT, TOKO_LNG = -6.175392, 106.827153


def _setup(tenant_id, uang_harian=60000, toleransi_menit=30, toleransi_pulang_awal_menit=30,
           batas_menit_terlambat=120, batas_menit_pulang_awal=120, nama="Dyn Barber"):
    attendance_db.set_settings(tenant_id, jam_masuk="09:00", toleransi_menit=toleransi_menit,
                                jam_pulang="18:00", radius_meter=500, lokasi_nama="Toko Test",
                                lokasi_latitude=TOKO_LAT, lokasi_longitude=TOKO_LNG,
                                batas_menit_terlambat=batas_menit_terlambat,
                                batas_menit_pulang_awal=batas_menit_pulang_awal,
                                toleransi_pulang_awal_menit=toleransi_pulang_awal_menit)
    # `nama` UNIK GLOBAL di skema SQLite (lihat database.py::add_barber) --
    # BEDA dari Postgres (unik PER TENANT, idx_barbers_tenant_nama), pola
    # lama di codebase ini yang TIDAK diubah di sini -- caller multi-tenant
    # (test isolasi) WAJIB kasih `nama` unik sendiri per tenant.
    barber_id = database.add_barber(nama, tenant_id=tenant_id)
    database.update_barber(barber_id, uang_harian=uang_harian)
    return database.get_barber(barber_id)


def _checkin(monkeypatch, tenant_id, barber_id, tanggal, jam, menit):
    monkeypatch.setattr(attendance_db, "_sekarang_wib",
                         lambda: datetime(*[int(x) for x in tanggal.split("-")], jam, menit, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_id, TOKO_LAT, TOKO_LNG, accuracy=15)


def _checkout(monkeypatch, tenant_id, barber_id, tanggal, jam, menit):
    monkeypatch.setattr(attendance_db, "_sekarang_wib",
                         lambda: datetime(*[int(x) for x in tanggal.split("-")], jam, menit, tzinfo=WIB))
    attendance_db.check_out(tenant_id, barber_id, TOKO_LAT, TOKO_LNG, accuracy=15)


def _service(tenant_id):
    sid = database.add_service("Cukur Test", 20000, tenant_id=tenant_id)
    database.set_uang_harian_acuan_ids([sid], tenant_id=tenant_id)
    return sid


def _isi_service(barber_id, tanggal, service_id, jumlah):
    database.tambah_transaksi(tanggal, barber_id, [{"service_id": service_id, "jumlah": jumlah}])


# 1. Tanpa Absensi (default) -- perilaku SAMA PERSIS sistem lama.
def test_tanpa_absensi_pakai_sistem_lama(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    sid = _service(tenant_id)
    database.set_setting("uang_harian_target_service_harian", "2", tenant_id=tenant_id)
    _isi_service(barber["id"], "2026-08-03", sid, 2)
    assert database.hitung_uang_harian_per_hari(barber, "2026-08-03") == 60000
    _isi_service(barber["id"], "2026-08-04", sid, 1)
    assert database.hitung_uang_harian_per_hari(barber, "2026-08-04") == 0
    assert uhd.get_config(tenant_id)["aktif"] is False


# 2. Hanya Toleransi Harian.
def test_hanya_toleransi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_gunakan_limit=False, keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 35)  # terlambat 35 > toleransi 30
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["uang_harian_final"] == 48000
    assert b["keterlambatan"]["dilanggar"] is True


# 3. Hanya Limit Bulanan.
def test_hanya_limit(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=False,
                   keterlambatan_gunakan_limit=True, keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 35)  # cumulative 35 < limit 120
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["uang_harian_final"] == 60000
    assert b["keterlambatan"]["dilanggar"] is False


# 4. Toleransi + Limit (kombinasi, dites detail di test OR/AND di bawah).
def test_toleransi_dan_limit_keduanya_aktif(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_gunakan_limit=True, keterlambatan_potongan_persen=20, kombinasi_metode="OR")
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 35)
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["keterlambatan"]["gunakan_toleransi"] and b["keterlambatan"]["gunakan_limit"]


# 5. Toleransi tidak dilanggar -> 100%.
def test_toleransi_tidak_dilanggar_seratus_persen(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 15)  # 15 < toleransi 30
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    assert uhd.breakdown_hari(barber, "2026-08-03")["uang_harian_final"] == 60000


# 6+7. Toleransi dilanggar tapi Limit tersedia -- hasil tergantung mode: Hanya
# Toleransi memicu, Hanya Limit TIDAK (tetap 100% selama limit belum habis).
def test_toleransi_dilanggar_limit_tersedia_tergantung_mode(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_gunakan_limit=False, keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 35)
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    assert uhd.breakdown_hari(barber, "2026-08-03")["uang_harian_final"] == 48000  # Hanya Toleransi -> trigger

    uhd.set_config(tenant_id, keterlambatan_gunakan_toleransi=False, keterlambatan_gunakan_limit=True)
    assert uhd.breakdown_hari(barber, "2026-08-03")["uang_harian_final"] == 60000  # Hanya Limit -> tidak trigger


# 8. Limit terlampaui -> trigger.
def test_limit_terlampaui_trigger(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id, batas_menit_terlambat=120)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=False,
                   keterlambatan_gunakan_limit=True, keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-01", 10, 30)  # terlambat 90, cum 90
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-01", 18, 0)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-05", 9, 40)  # terlambat 40, cum 130 > 120
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-05", 18, 0)
    assert uhd.breakdown_hari(barber, "2026-08-01")["uang_harian_final"] == 60000
    b5 = uhd.breakdown_hari(barber, "2026-08-05")
    assert b5["uang_harian_final"] == 48000
    assert b5["keterlambatan"]["limit_lampaui"] is True


# 9. Kombinasi OR.
def test_kombinasi_or(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_gunakan_limit=True, keterlambatan_potongan_persen=20, kombinasi_metode="OR")
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 35)  # toleransi dilanggar, limit belum habis
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    assert uhd.breakdown_hari(barber, "2026-08-03")["uang_harian_final"] == 48000


# 10. Kombinasi AND.
def test_kombinasi_and(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_gunakan_limit=True, keterlambatan_potongan_persen=20, kombinasi_metode="AND")
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 35)  # toleransi dilanggar, limit belum habis
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    assert uhd.breakdown_hari(barber, "2026-08-03")["uang_harian_final"] == 60000  # AND butuh keduanya


# 11. Keterlambatan & pulang awal dikonfigurasi berbeda (asimetris).
def test_konfigurasi_asimetris_per_jenis(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_gunakan_limit=False, pulang_awal_gunakan_toleransi=False,
                   pulang_awal_gunakan_limit=True)
    cfg = uhd.get_config(tenant_id)
    assert cfg["keterlambatan_gunakan_toleransi"] is True and cfg["keterlambatan_gunakan_limit"] is False
    assert cfg["pulang_awal_gunakan_toleransi"] is False and cfg["pulang_awal_gunakan_limit"] is True


# 12+13. Terlambat & pulang awal sekaligus -> HANYA satu potongan (MAX, bukan SUM),
# dan kalau persentase beda dipakai yang TERTINGGI.
def test_terlambat_dan_pulang_awal_pakai_max_bukan_sum(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20, pulang_awal_gunakan_toleransi=True,
                   pulang_awal_potongan_persen=30)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 35)  # terlambat 35 > toleransi 30
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 17, 0)  # pulang awal 60 > toleransi 30
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["potongan_persen"] == 30  # MAX(20, 30), BUKAN 50
    assert b["uang_harian_final"] == 42000


# 14. Limit reset tanggal 1 (bulan baru).
def test_limit_reset_tiap_bulan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id, batas_menit_terlambat=120)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=False,
                   keterlambatan_gunakan_limit=True, keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-30", 11, 0)  # terlambat 120, cum 120 (habis)
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-30", 18, 0)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-09-01", 9, 40)  # bulan BARU, cum 40 (reset)
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-09-01", 18, 0)
    b_agustus = uhd.breakdown_hari(barber, "2026-08-30")
    b_september = uhd.breakdown_hari(barber, "2026-09-01")
    assert b_agustus["keterlambatan"]["limit_lampaui"] is True
    assert b_september["keterlambatan"]["limit_lampaui"] is False
    assert b_september["uang_harian_final"] == 60000


# 15. Koreksi Pending -- belum memengaruhi apa pun (data resmi masih kosong).
def test_koreksi_pending_tidak_finalisasi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    attendance_db.buat_pengajuan_koreksi(barber["id"], "2026-08-03", "check_in", "09:35",
                                          "Lupa check-in", tenant_id=tenant_id)
    b = uhd.breakdown_hari(barber, "2026-08-03")
    # Belum ada log Absensi RESMI sama sekali (koreksi masih pending) --
    # PERMINTAAN OWNER: tidak ada check-in+check-out lengkap = Rp0 mutlak
    # (lihat _hasil_absensi_tidak_lengkap()).
    assert b["sumber"] == "tidak_ada_absensi"
    assert b["absensi_tidak_lengkap"] is True
    assert b["uang_harian_final"] == 0


# 16. Koreksi Approved -- data koreksi jadi resmi, dihitung ulang.
def test_koreksi_approved_dipakai_sebagai_data_resmi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    koreksi = attendance_db.buat_pengajuan_koreksi(barber["id"], "2026-08-03", "check_in", "09:35",
                                                     "Lupa check-in", tenant_id=tenant_id)
    attendance_db.set_status_koreksi(koreksi["id"], "disetujui")
    # PERMINTAAN OWNER: check-in SAJA (biar sudah dikoreksi/disetujui) masih
    # "absensi tidak lengkap" selama check-out hari itu belum ada -- barber
    # tetap check-out normal supaya hari ini lengkap dan dievaluasi penuh.
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["keterlambatan"]["menit"] == 35
    assert b["uang_harian_final"] == 48000


# 17. Koreksi Rejected -- tidak menyentuh apa pun (data resmi tetap seperti sebelumnya).
def test_koreksi_ditolak_tidak_mengubah_data(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    koreksi = attendance_db.buat_pengajuan_koreksi(barber["id"], "2026-08-03", "check_in", "09:35",
                                                     "Lupa check-in", tenant_id=tenant_id)
    attendance_db.set_status_koreksi(koreksi["id"], "ditolak")
    b = uhd.breakdown_hari(barber, "2026-08-03")
    # Koreksi ditolak TIDAK PERNAH menyentuh attendance_logs -- tetap tidak
    # ada log Absensi resmi sama sekali, Rp0 mutlak sama seperti kasus pending.
    assert b["sumber"] == "tidak_ada_absensi"
    assert b["uang_harian_final"] == 0


# 18+19. Service Rule -- terpenuhi vs tidak terpenuhi (mode SYARAT).
def test_service_rule_syarat(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    sid = _service(tenant_id)
    uhd.set_config(tenant_id, aktif=True, service_rule_mode="SYARAT", service_rule_minimal=2)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 0)
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    _isi_service(barber["id"], "2026-08-03", sid, 2)
    assert uhd.breakdown_hari(barber, "2026-08-03")["uang_harian_final"] == 60000  # terpenuhi

    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-04", 9, 0)
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-04", 18, 0)
    _isi_service(barber["id"], "2026-08-04", sid, 1)
    assert uhd.breakdown_hari(barber, "2026-08-04")["uang_harian_final"] == 0  # tidak terpenuhi


# 20. Service + Absensi -- potongan Absensi TETAP berlaku walau Service terpenuhi
# (Service tidak menghilangkan potongan Absensi, digabung lewat MAX yang sama).
def test_service_terpenuhi_absensi_tetap_potong(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    sid = _service(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20, service_rule_mode="SYARAT", service_rule_minimal=2)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 35)  # toleransi dilanggar
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-03", 18, 0)
    _isi_service(barber["id"], "2026-08-03", sid, 2)  # service terpenuhi
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["service"]["terpenuhi"] is True
    assert b["uang_harian_final"] == 48000  # potongan absensi tetap berlaku


# 21. Tenant berbeda punya rule berbeda (isolasi multi-tenant).
def test_isolasi_konfigurasi_antar_tenant(two_tenants, monkeypatch):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = _setup(tenant_a, nama="Dyn Barber A")
    barber_b = _setup(tenant_b, nama="Dyn Barber B")
    uhd.set_config(tenant_a, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    # tenant_b TIDAK diatur -- harus tetap default (aktif=False).
    assert uhd.get_config(tenant_a)["aktif"] is True
    assert uhd.get_config(tenant_b)["aktif"] is False
    _checkin(monkeypatch, tenant_a, barber_a["id"], "2026-08-03", 9, 35)
    _checkout(monkeypatch, tenant_a, barber_a["id"], "2026-08-03", 18, 0)
    _checkin(monkeypatch, tenant_b, barber_b["id"], "2026-08-03", 9, 35)
    assert uhd.breakdown_hari(barber_a, "2026-08-03")["uang_harian_final"] == 48000
    assert database.hitung_uang_harian_per_hari(barber_b, "2026-08-03") == 0  # sistem lama, tanpa service


# 22. Tenant lama (belum opt-in) tidak berubah sama sekali -- duplikat eksplisit dari #1
# dengan assert TAMBAHAN: hitung_uang_harian_bulan/_rentang JUGA tidak berubah.
def test_tenant_lama_byte_identik_bulan_dan_rentang(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    sid = _service(tenant_id)
    database.set_setting("uang_harian_target_service_harian", "2", tenant_id=tenant_id)
    _isi_service(barber["id"], "2026-08-03", sid, 2)
    assert database.hitung_uang_harian_bulan(barber, 2026, 8) == 60000
    assert database.hitung_uang_harian_rentang(barber, "2026-08-01", "2026-08-31") == 60000


# 23. Payroll (hitung_uang_harian_bulan) menghasilkan angka final yang SAMA
# dengan penjumlahan breakdown_hari per hari (satu sumber kebenaran).
def test_payroll_bulan_konsisten_dengan_breakdown_harian(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id, batas_menit_terlambat=120)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=False,
                   keterlambatan_gunakan_limit=True, keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-01", 10, 30)  # cum 90
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-01", 18, 0)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-05", 9, 40)  # cum 130 > 120 -> trigger
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-05", 18, 0)
    total_bulan = database.hitung_uang_harian_bulan(barber, 2026, 8)
    total_manual = (uhd.breakdown_hari(barber, "2026-08-01")["uang_harian_final"]
                     + uhd.breakdown_hari(barber, "2026-08-05")["uang_harian_final"])
    assert total_bulan == total_manual == 60000 + 48000


# PERMINTAAN OWNER: tanggal yang TIDAK punya data Absensi sama sekali --
# Uang Harian MUTLAK Rp0, TIDAK lagi fallback ke sistem lama (jumlah
# service vs target) seperti sebelumnya -- apa pun jumlah service hari itu.
def test_tanggal_tanpa_absensi_mutlak_nol(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    sid = _service(tenant_id)
    database.set_setting("uang_harian_target_service_harian", "2", tenant_id=tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    # TIDAK ADA check-in sama sekali untuk tanggal ini -- hanya transaksi
    # service, target TERCAPAI (2 >= 2) -- tetap Rp0 karena tidak ada Absensi.
    _isi_service(barber["id"], "2020-01-15", sid, 2)
    b = uhd.breakdown_hari(barber, "2020-01-15")
    assert b["sumber"] == "tidak_ada_absensi"
    assert b["absensi_tidak_lengkap"] is True
    assert b["uang_harian_final"] == 0


# Breakdown per-hari dan agregat bulanan HARUS konsisten untuk tanggal tanpa
# Absensi -- keduanya Rp0.
def test_breakdown_dan_agregat_bulanan_konsisten_untuk_tanggal_tanpa_absensi(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    sid = _service(tenant_id)
    database.set_setting("uang_harian_target_service_harian", "2", tenant_id=tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    _isi_service(barber["id"], "2020-01-15", sid, 2)  # tanpa Absensi, target tercapai -- tetap Rp0
    breakdown_final = uhd.breakdown_hari(barber, "2020-01-15")["uang_harian_final"]
    bulan_total = uhd.hitung_uang_harian_dinamis_bulan(barber, 2020, 1)
    assert breakdown_final == bulan_total == 0


# Bulan CAMPURAN: sebagian tanggal punya Absensi LENGKAP (dievaluasi mesin
# baru), sebagian lain hanya punya transaksi service tanpa Absensi (Rp0
# mutlak) -- total bulan harus menjumlahkan HASIL BENAR dari keduanya.
def test_bulan_campuran_absensi_dan_tanpa_absensi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id, batas_menit_terlambat=120)
    sid = _service(tenant_id)
    database.set_setting("uang_harian_target_service_harian", "2", tenant_id=tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    # Tanggal 1: ADA Absensi LENGKAP, terlambat 35 > toleransi 30 -> potongan 20% -> 48000
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-01", 9, 35)
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-08-01", 18, 0)
    # Tanggal 15: TIDAK ADA Absensi, hanya service (target tercapai) -- tetap Rp0
    _isi_service(barber["id"], "2026-08-15", sid, 2)
    # Tanggal 20: TIDAK ADA Absensi, hanya service (target TIDAK tercapai) -- tetap Rp0
    _isi_service(barber["id"], "2026-08-20", sid, 1)
    total = uhd.hitung_uang_harian_dinamis_bulan(barber, 2026, 8)
    assert total == 48000 + 0 + 0


# Audit menyeluruh: hitung_uang_harian_dinamis_rentang() (dipakai Laporan
# PDF, BUKAN cuma _bulan yang dites di atas) HARUS ikut aturan Rp0 mutlak
# untuk tanggal tanpa Absensi juga -- termasuk saat rentangnya melintasi 2
# bulan kalender (limit akumulasi reset per bulan).
def test_rentang_absensi_tidak_lengkap_mutlak_nol_lintas_bulan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id, batas_menit_terlambat=120)
    sid = _service(tenant_id)
    database.set_setting("uang_harian_target_service_harian", "2", tenant_id=tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    # Bulan Juli: ADA Absensi LENGKAP, terlambat 35 > toleransi 30 -> potongan 20% -> 48000
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-07-31", 9, 35)
    _checkout(monkeypatch, tenant_id, barber["id"], "2026-07-31", 18, 0)
    # Bulan Agustus: TIDAK ADA Absensi, hanya service (target tercapai) -- tetap Rp0
    _isi_service(barber["id"], "2026-08-01", sid, 2)
    # Bulan Agustus: TIDAK ADA Absensi, hanya service (target TIDAK tercapai) -- tetap Rp0
    _isi_service(barber["id"], "2026-08-02", sid, 1)
    total = uhd.hitung_uang_harian_dinamis_rentang(barber, "2026-07-31", "2026-08-02")
    assert total == 48000 + 0 + 0
    # breakdown per-hari harus konsisten dengan kontribusi rentang di atas
    assert uhd.breakdown_hari(barber, "2026-08-01")["sumber"] == "tidak_ada_absensi"
    assert uhd.breakdown_hari(barber, "2026-08-01")["uang_harian_final"] == 0


# PERMINTAAN OWNER: HANYA Check In (lupa Check Out) -- Uang Harian MUTLAK
# Rp0, walau check-in-nya sendiri tepat waktu (tidak ada pelanggaran
# toleransi/limit apa pun yang bisa dievaluasi).
def test_hanya_check_in_tanpa_check_out_mutlak_nol(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 0)  # tepat waktu, TIDAK check-out
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["sumber"] == "absensi_tidak_lengkap"
    assert b["absensi_tidak_lengkap"] is True
    assert b["uang_harian_final"] == 0


# PERMINTAAN OWNER: HANYA Check Out (barber TIDAK PERNAH Check In hari itu
# sama sekali -- baris hanya ada lewat Koreksi Absensi check_out yang
# disetujui, lihat attendance_db._terapkan_koreksi_ke_log()) -- Uang Harian
# tetap MUTLAK Rp0 selama check_in_at masih kosong. (Normal Check Out lewat
# attendance_db.check_out() SENDIRI sudah menolak kalau belum Check In hari
# itu -- "hanya check-out" secara nyata HANYA bisa terjadi lewat Koreksi.)
def test_hanya_check_out_tanpa_check_in_mutlak_nol(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    koreksi = attendance_db.buat_pengajuan_koreksi(barber["id"], "2026-08-03", "check_out", "18:00",
                                                     "Lupa check-out, lupa check-in juga", tenant_id=tenant_id)
    attendance_db.set_status_koreksi(koreksi["id"], "disetujui")
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["sumber"] == "absensi_tidak_lengkap"
    assert b["absensi_tidak_lengkap"] is True
    assert b["uang_harian_final"] == 0


# PERMINTAAN OWNER: begitu Koreksi Absensi untuk bagian yang kosong
# disetujui (melengkapi check-in DAN check-out hari itu), Uang Harian
# otomatis kembali dievaluasi normal -- TIDAK lagi Rp0.
def test_koreksi_melengkapi_absensi_kembali_dievaluasi_normal(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber = _setup(tenant_id)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_potongan_persen=20)
    _checkin(monkeypatch, tenant_id, barber["id"], "2026-08-03", 9, 0)  # tepat waktu, TIDAK check-out
    assert uhd.breakdown_hari(barber, "2026-08-03")["uang_harian_final"] == 0  # belum lengkap

    koreksi = attendance_db.buat_pengajuan_koreksi(barber["id"], "2026-08-03", "check_out", "18:00",
                                                     "Lupa check-out", tenant_id=tenant_id)
    attendance_db.set_status_koreksi(koreksi["id"], "disetujui")
    b = uhd.breakdown_hari(barber, "2026-08-03")
    assert b["sumber"] == "absensi"
    assert b["uang_harian_final"] == 60000  # lengkap & tidak ada pelanggaran -> cair penuh


# Audit menyeluruh (feedback Owner): GET /breakdown dengan `tanggal` format
# salah HARUS 422 rapi (sebelumnya int(tanggal[:4]) di breakdown_hari() bisa
# lolos tanpa validasi router lalu meledak ValueError -> 500 tak tertangani).
def test_breakdown_endpoint_tanggal_invalid_dapat_422(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/uang-harian-dinamis/breakdown", params={"tanggal": "bukan-tanggal"}, headers=headers)
    assert r.status_code == 422


# Validasi tambahan: potongan% di luar 0-100 ditolak (kualitas input, bukan
# salah satu dari 23 skenario tapi wajar diverifikasi bersama modul ini).
def test_set_config_menolak_potongan_invalid(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    with pytest.raises(ValueError):
        uhd.set_config(tenant_id, keterlambatan_potongan_persen=150)
    with pytest.raises(ValueError):
        uhd.set_config(tenant_id, kombinasi_metode="XOR")
