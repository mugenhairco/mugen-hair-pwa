"""test_data_purge.py — FITUR Pembersihan Data Bulanan Otomatis: test suite.
=============================================================================
Cakupan: database.py::arsipkan_dan_hapus_mutasi_lama() (carry-forward saldo
Produk), slip_gaji_db.py::hapus_slip_gaji_sebelum() (hapus TANPA PANDANG
STATUS + lepas rujukan kasbon_pembayaran TANPA membalikkan saldo), dan
data_purge_db.py::jalankan_pembersihan() end-to-end (penjaga TANGGAL_JALAN,
cutoff "tanggal < awal bulan berjalan", email arsip all-or-nothing untuk
Transaksi/Absensi/Produk, kategori tanpa PDF selalu terhapus terlepas dari
hasil email, idempotensi "by construction")."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import attendance_db
import data_purge_db
import database
import kasbon_db
import slip_gaji_db
import tenant_db

WIB = ZoneInfo("Asia/Jakarta")


def _set_created_at(tenant_id, tanggal):
    with database.get_conn() as conn:
        conn.execute("UPDATE tenants SET created_at = ? WHERE id = ?", (tanggal, tenant_id))


def _set_email(tenant_id, email):
    with database.get_conn() as conn:
        conn.execute("UPDATE tenants SET email = ? WHERE id = ?", (email, tenant_id))


# ---------------------------------------------------------------------------
# Carry-forward saldo Produk (database.py::arsipkan_dan_hapus_mutasi_lama)
# ---------------------------------------------------------------------------

def test_arsipkan_dan_hapus_mutasi_lama_carry_forward_saldo(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    produk_id = database.tambah_produk("Pomade Test", harga_modal=10000, harga_jual=20000, tenant_id=tenant_id)
    database.restock_produk(produk_id, "2026-07-01", 50)
    database.jual_produk(produk_id, "2026-07-10", 10)
    database.restock_produk(produk_id, "2026-08-05", 20)
    database.jual_produk(produk_id, "2026-08-15", 5)
    assert database.get_stok_produk(produk_id) == 55  # 50-10+20-5

    database.jual_produk(produk_id, "2026-09-02", 3)  # SETELAH cutoff -- harus tetap ada
    assert database.get_stok_produk(produk_id) == 52

    saldo = database.arsipkan_dan_hapus_mutasi_lama(produk_id, "2026-09-01")
    assert saldo == 55
    assert database.get_stok_produk(produk_id) == 52  # stok akhir TIDAK berubah

    tipe_tersisa = sorted(m["tipe"] for m in database.get_mutasi_produk_list(produk_id=produk_id))
    assert tipe_tersisa == ["jual", "saldo_awal"]

    # Idempotent: tidak ada lagi baris < cutoff -> None, tidak melakukan apa pun.
    assert database.arsipkan_dan_hapus_mutasi_lama(produk_id, "2026-09-01") is None


def test_arsipkan_dan_hapus_mutasi_lama_saldo_awal_diperlakukan_seperti_restock(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    produk_id = database.tambah_produk("Minyak Test", harga_modal=5000, harga_jual=15000, tenant_id=tenant_id)
    database.restock_produk(produk_id, "2026-07-01", 10)
    database.arsipkan_dan_hapus_mutasi_lama(produk_id, "2026-08-01")
    assert database.get_stok_produk(produk_id) == 10

    with pytest.raises(ValueError):
        database.jual_produk(produk_id, "2026-08-05", 15)  # melebihi saldo_awal (10) -- ditolak
    database.jual_produk(produk_id, "2026-08-05", 10)  # pas, boleh
    assert database.get_stok_produk(produk_id) == 0


# ---------------------------------------------------------------------------
# Slip Gaji -- hapus TANPA PANDANG STATUS (slip_gaji_db.hapus_slip_gaji_sebelum)
# ---------------------------------------------------------------------------

def test_hapus_slip_gaji_sebelum_hapus_semua_status_sisakan_baru(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = database.add_barber("Barber Slip Purge", tenant_id=tenant_id)
    slip_belum = slip_gaji_db.buat_slip_gaji(barber_id, tahun=2026, bulan=7, dibuat_oleh="tester", tenant_id=tenant_id)
    slip_sudah = slip_gaji_db.buat_slip_gaji(barber_id, tahun=2026, bulan=8, dibuat_oleh="tester", tenant_id=tenant_id)
    slip_gaji_db.tandai_status(slip_sudah["id"], "sudah_dibayar")
    slip_baru = slip_gaji_db.buat_slip_gaji(barber_id, tahun=2026, bulan=9, dibuat_oleh="tester", tenant_id=tenant_id)

    jumlah = slip_gaji_db.hapus_slip_gaji_sebelum(tenant_id, "2026-09-01")
    assert jumlah == 2
    assert slip_gaji_db.get_slip_gaji(slip_belum["id"]) is None
    assert slip_gaji_db.get_slip_gaji(slip_sudah["id"]) is None  # sudah_dibayar TETAP ikut terhapus
    assert slip_gaji_db.get_slip_gaji(slip_baru["id"]) is not None


def test_hapus_slip_gaji_sebelum_lepas_rujukan_kasbon_tanpa_membalikkan_saldo(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = database.add_barber("Barber Kasbon Slip", tenant_id=tenant_id)
    slip = slip_gaji_db.buat_slip_gaji(barber_id, tahun=2026, bulan=7, dibuat_oleh="tester", tenant_id=tenant_id)
    slip_gaji_db.tandai_status(slip["id"], "sudah_dibayar")

    kasbon = kasbon_db.buat_kasbon(barber_id, "2026-07-01", 100000, dibuat_oleh="tester", tenant_id=tenant_id)
    kasbon_db.bayar_kasbon(kasbon["id"], "2026-07-15", 40000, sumber="potong_gaji", slip_gaji_id=slip["id"])
    assert kasbon_db.get_kasbon(kasbon["id"])["sisa"] == 60000

    # TIDAK boleh melempar FK error (kasbon_pembayaran.slip_gaji_id -> slip_gaji).
    jumlah = slip_gaji_db.hapus_slip_gaji_sebelum(tenant_id, "2026-08-01")
    assert jumlah == 1
    assert slip_gaji_db.get_slip_gaji(slip["id"]) is None
    # Saldo kasbon TETAP seperti sudah dipotong -- TIDAK dibalik.
    assert kasbon_db.get_kasbon(kasbon["id"])["sisa"] == 60000

    with database.get_conn() as conn:
        row = conn.execute("SELECT slip_gaji_id FROM kasbon_pembayaran WHERE kasbon_id = ?",
                            (kasbon["id"],)).fetchone()
        assert row["slip_gaji_id"] is None  # rujukan dilepas, BUKAN baris kasbon_pembayaran-nya yang dihapus


# ---------------------------------------------------------------------------
# Orkestrator data_purge_db.jalankan_pembersihan() -- penjaga tanggal
# ---------------------------------------------------------------------------

def test_jalankan_pembersihan_bukan_tanggal_10_dilewati(monkeypatch):
    monkeypatch.setattr(data_purge_db, "_sekarang_wib", lambda: datetime(2026, 10, 15, 8, 0, tzinfo=WIB))
    hasil = data_purge_db.jalankan_pembersihan()
    assert hasil["dijalankan"] is False


def test_jalankan_pembersihan_paksa_lewati_penjaga_tanggal(monkeypatch):
    monkeypatch.setattr(data_purge_db, "_sekarang_wib", lambda: datetime(2026, 10, 15, 8, 0, tzinfo=WIB))
    hasil = data_purge_db.jalankan_pembersihan(paksa=True)
    assert hasil["dijalankan"] is True
    assert hasil["cutoff"] == "2026-10-01"


def test_jalankan_pembersihan_tenant_id_hanya_proses_satu_tenant(two_tenants, monkeypatch):
    """FITUR test manual Superadmin (routers/superadmin.py::
    jalankan_pembersihan_data_manual()): `tenant_id` diisi -> HANYA tenant
    itu yang diproses, tenant lain di platform TIDAK ikut tersentuh sama
    sekali (bahkan tidak muncul di `per_tenant`/`tenant_diperiksa`)."""
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    monkeypatch.setattr(data_purge_db, "_sekarang_wib", lambda: datetime(2026, 10, 15, 8, 0, tzinfo=WIB))
    hasil = data_purge_db.jalankan_pembersihan(paksa=True, tenant_id=tenant_a)
    assert hasil["tenant_diperiksa"] == 1
    assert str(tenant_a) in hasil["per_tenant"]
    assert str(tenant_b) not in hasil["per_tenant"]


# ---------------------------------------------------------------------------
# Orkestrator -- jalur penuh (email arsip sukses -> SEMUA kategori terhapus)
# ---------------------------------------------------------------------------

def test_jalankan_pembersihan_hapus_absensi_sebelum_transaksi_jaga_uang_harian(single_tenant, monkeypatch):
    """Regresi KRITIS: attendance_db.hapus_riwayat_absensi() (yang
    membekukan Uang Harian hari itu SEBELUM attendance_logs dihapus, lihat
    _bekukan_sebelum_hapus_riwayat()) HARUS dipanggil SEBELUM
    database.hapus_riwayat_transaksi() -- pembekuan Uang Harian (sistem
    lama MAUPUN Uang Harian Dinamis) membaca transaksi_detail hari itu
    LANGSUNG dari database, jadi baris Transaksi-nya HARUS masih ada saat
    pembekuan terjadi. Urutan terbalik akan membekukan Uang Harian jadi 0
    padahal barber ini sungguhan berhak dapat nominalnya -- riwayat
    historis jadi rusak permanen (TIDAK bisa dihitung ulang lagi setelah
    attendance_logs-nya hilang)."""
    tenant_id = single_tenant["tenant_id"]
    _set_created_at(tenant_id, "2026-01-01")
    _set_email(tenant_id, "owner@uang-harian.test")
    barber_id = database.add_barber("Barber Uang Harian Purge", uang_harian=50000, tenant_id=tenant_id)
    service_id = database.add_service("Service Uang Harian Purge", 20000, tenant_id=tenant_id)
    database.set_uang_harian_acuan_ids([service_id], tenant_id=tenant_id)
    # target_uang_harian_per_hari() default = 3 -- jumlah 3 MEMENUHI target.
    database.tambah_transaksi("2026-07-20", barber_id, [{"service_id": service_id, "jumlah": 3}])

    attendance_db.set_settings(tenant_id, jam_masuk="09:00", toleransi_menit=15, jam_pulang="20:00",
                                radius_meter=500, lokasi_nama="Toko Purge UH",
                                lokasi_latitude=-6.1, lokasi_longitude=106.8)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 7, 20, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_id, -6.1, 106.8, accuracy=15)

    monkeypatch.setattr(data_purge_db, "kirim_email", lambda *a, **kw: True)
    monkeypatch.setattr(data_purge_db, "_sekarang_wib", lambda: datetime(2026, 9, 10, 8, 0, tzinfo=WIB))
    hasil = data_purge_db.jalankan_pembersihan()
    per = hasil["per_tenant"][str(tenant_id)]
    assert per["absensi_dihapus"] == 1
    assert per["transaksi_dihapus"] == 1

    # Uang Harian hari itu HARUS tetap 50000 (dibekukan dengan benar dari
    # Transaksi yang MASIH ADA saat Absensi dihapus) -- BUKAN 0.
    barber = database.get_barber(barber_id)
    assert database.hitung_uang_harian_per_hari(barber, "2026-07-20") == 50000


def _siapkan_data_lengkap(tenant_id):
    """Satu barber dengan data di SEMUA 7 kategori, sebagian < cutoff
    (2026-07/08, harus terhapus) dan sebagian >= cutoff (2026-09, harus
    TETAP ADA) -- dipakai bersama oleh test sukses & test gagal-email."""
    barber_id = database.add_barber("Barber Purge E2E", tenant_id=tenant_id)
    service_id = database.add_service("Potong Purge E2E", 50000, tenant_id=tenant_id)

    database.tambah_transaksi("2026-07-15", barber_id, [{"service_id": service_id, "jumlah": 1}])
    database.tambah_transaksi("2026-09-15", barber_id, [{"service_id": service_id, "jumlah": 1}])

    produk_id = database.tambah_produk(f"Produk Purge E2E T{tenant_id}", harga_modal=5000, harga_jual=10000,
                                        tenant_id=tenant_id)
    database.restock_produk(produk_id, "2026-07-01", 30)
    database.jual_produk(produk_id, "2026-09-02", 2)

    attendance_db.set_settings(tenant_id, jam_masuk="09:00", toleransi_menit=15, jam_pulang="20:00",
                                radius_meter=500, lokasi_nama="Toko Purge",
                                lokasi_latitude=-6.1, lokasi_longitude=106.8)
    return barber_id, service_id, produk_id


def test_jalankan_pembersihan_jalur_sukses_hapus_semua_kategori(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _set_created_at(tenant_id, "2026-01-01")
    _set_email(tenant_id, "owner@purge-e2e.test")
    barber_id, service_id, produk_id = _siapkan_data_lengkap(tenant_id)

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 7, 20, 9, 0, tzinfo=WIB))
    # check_in() sendiri SUDAH mencatat 1 baris Log Audit otomatis (lihat
    # attendance_db.py::check_in() -> catat_audit()) -- TIDAK perlu
    # catat_audit() manual tambahan di sini.
    attendance_db.check_in(tenant_id, barber_id, -6.1, 106.8, accuracy=15)
    koreksi = attendance_db.buat_pengajuan_koreksi(barber_id, "2026-07-20", "check_out", "20:05", "Lupa",
                                                     tenant_id=tenant_id)
    attendance_db.set_status_koreksi(koreksi["id"], "disetujui")
    slip = slip_gaji_db.buat_slip_gaji(barber_id, tahun=2026, bulan=7, dibuat_oleh="tester", tenant_id=tenant_id)
    slip_gaji_db.tandai_status(slip["id"], "sudah_dibayar")

    # Pengajuan koreksi/absensi SETELAH cutoff -- harus TETAP ADA.
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 9, 20, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, barber_id, -6.1, 106.8, accuracy=15)

    captured = {}

    def _fake_kirim_email(to, subject, html, attachments=None):
        captured["to"] = to
        captured["attachments"] = attachments
        return True

    monkeypatch.setattr(data_purge_db, "kirim_email", _fake_kirim_email)
    monkeypatch.setattr(data_purge_db, "_sekarang_wib", lambda: datetime(2026, 9, 10, 8, 0, tzinfo=WIB))

    hasil = data_purge_db.jalankan_pembersihan()
    assert hasil["dijalankan"] is True
    assert hasil["cutoff"] == "2026-09-01"
    assert hasil["tenant_gagal"] == 0
    per = hasil["per_tenant"][str(tenant_id)]
    assert per["email_terkirim"] is True
    assert per["transaksi_dihapus"] == 1
    assert per["absensi_dihapus"] == 1
    assert per["produk_diarsipkan"] == 1
    assert per["audit_log_dihapus"] == 1
    assert per["koreksi_dihapus"] == 1
    assert per["slip_gaji_dihapus"] == 1

    assert captured["to"] == "owner@purge-e2e.test"
    nama_lampiran = [nama for nama, _ in captured["attachments"]]
    assert any("Rekap-Transaksi-" in n and "Ringkasan" not in n for n in nama_lampiran)
    assert any("Ringkasan-Semua-Barber" in n for n in nama_lampiran)
    assert any(n == "Riwayat-Absensi.pdf" for n in nama_lampiran)
    assert any(n == "Riwayat-Mutasi-Produk.pdf" for n in nama_lampiran)

    # Data lama benar-benar hilang...
    assert database.get_transaksi_list(tahun=2026, bulan=7, barber_id=barber_id, tenant_id=tenant_id) == []
    assert attendance_db.get_log_list(tenant_id, tanggal="2026-07-20", barber_id=barber_id) == []
    # Log Audit bulan Juli hilang, TAPI baris September (dari check_in()
    # kedua di atas, SETELAH cutoff) tetap ada -- bukan [] kosong total.
    audit_tersisa = attendance_db.get_audit_list(tenant_id)
    assert len(audit_tersisa) == 1
    assert audit_tersisa[0]["waktu_server"].startswith("2026-09-20")
    assert attendance_db.get_koreksi(koreksi["id"]) is None
    assert slip_gaji_db.get_slip_gaji(slip["id"]) is None
    # ...tapi stok produk & data bulan September (setelah cutoff) tetap aman.
    assert database.get_stok_produk(produk_id) == 28  # 30 - 2
    assert len(database.get_transaksi_list(tahun=2026, bulan=9, barber_id=barber_id, tenant_id=tenant_id)) == 1
    assert attendance_db.get_log_list(tenant_id, tanggal="2026-09-20", barber_id=barber_id)[0]["check_in_at"] is not None

    # Idempotensi: jalankan lagi, HARUS tidak ada apa pun lagi untuk
    # diarsipkan/dihapus/dikirim (sudah habis di siklus pertama).
    captured.clear()
    hasil2 = data_purge_db.jalankan_pembersihan()
    per2 = hasil2["per_tenant"][str(tenant_id)]
    assert per2["transaksi_dihapus"] == 0
    assert per2["absensi_dihapus"] == 0
    assert per2["produk_diarsipkan"] == 0
    assert per2["audit_log_dihapus"] == 0
    assert per2["koreksi_dihapus"] == 0
    assert per2["slip_gaji_dihapus"] == 0
    assert "to" not in captured  # email TIDAK dikirim lagi


def test_jalankan_pembersihan_tanpa_email_tenant_lewati_kategori_pdf_saja(single_tenant, monkeypatch):
    """Tenant belum punya email terdaftar -- kategori yang PERLU arsip PDF
    (Transaksi/Absensi/Produk) TIDAK dihapus siklus ini (jaring pengaman),
    TAPI kategori tanpa PDF (Log Audit/Koreksi/Slip Gaji) tetap terhapus
    seperti biasa, TIDAK bergantung pada status email sama sekali."""
    tenant_id = single_tenant["tenant_id"]
    _set_created_at(tenant_id, "2026-01-01")
    # SENGAJA tidak memanggil _set_email() -- tenant ini belum punya email.
    barber_id, service_id, produk_id = _siapkan_data_lengkap(tenant_id)

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 7, 20, 9, 0, tzinfo=WIB))
    attendance_db.catat_audit(barber_id, "check_in", True, tenant_id=tenant_id)
    koreksi = attendance_db.buat_pengajuan_koreksi(barber_id, "2026-07-20", "check_out", "20:05", "Lupa",
                                                     tenant_id=tenant_id)
    attendance_db.set_status_koreksi(koreksi["id"], "disetujui")
    slip = slip_gaji_db.buat_slip_gaji(barber_id, tahun=2026, bulan=7, dibuat_oleh="tester", tenant_id=tenant_id)

    monkeypatch.setattr(data_purge_db, "_sekarang_wib", lambda: datetime(2026, 9, 10, 8, 0, tzinfo=WIB))
    hasil = data_purge_db.jalankan_pembersihan()
    per = hasil["per_tenant"][str(tenant_id)]
    assert per["email_terkirim"] is False
    assert per["transaksi_dihapus"] == 0
    assert per["produk_diarsipkan"] == 0
    assert per["audit_log_dihapus"] == 1
    assert per["koreksi_dihapus"] == 1
    assert per["slip_gaji_dihapus"] == 1

    # Transaksi/Produk lama TETAP ADA (belum ada jaring pengaman PDF-nya).
    assert len(database.get_transaksi_list(tahun=2026, bulan=7, barber_id=barber_id, tenant_id=tenant_id)) == 1
    assert database.get_stok_produk(produk_id) == 28
    # Log Audit/Koreksi/Slip Gaji tetap terhapus walau email gagal.
    assert attendance_db.get_audit_list(tenant_id) == []
    assert attendance_db.get_koreksi(koreksi["id"]) is None
    assert slip_gaji_db.get_slip_gaji(slip["id"]) is None
