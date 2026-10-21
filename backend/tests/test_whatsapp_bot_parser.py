"""test_whatsapp_bot_parser.py — FITUR WA Bot: parsing perintah & dispatch
=============================================================================
Cakupan: whatsapp_bot_parser.py (resolusi akses Owner/Barber, SEMUA
command, alur konfirmasi YA/BATAL, klarifikasi kode ambigu) + idempotensi
(whatsapp_bot_db.pesan_duplikat()) + penolakan Booking tanggal lewat untuk
Barber + Cuti/Izin terbuka untuk semua barber. Lihat whatsapp_bot_parser.py
untuk arsitektur lengkap."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import attendance_db
import booking_db
import database as db
import izin_cuti_db
import uang_harian_dinamis_db as uhd
import whatsapp_bot_db as wb_db
import whatsapp_bot_parser as wbp
from booking_db import _hari_ini_wib


def _tanggal_hari(nama_hari_target, offset_awal=0):
    """Cari tanggal terdekat yang jatuh pada nama_hari_target -- sama
    persis pola di test_booking_libur_mingguan.py/test_kuota_libur.py."""
    idx_target = booking_db.HARI_LIST.index(nama_hari_target)
    tanggal = _hari_ini_wib() + timedelta(days=offset_awal)
    while tanggal.weekday() != idx_target:
        tanggal += timedelta(days=1)
    return tanggal.isoformat()

WIB = ZoneInfo("Asia/Jakarta")


def _config(tenant_id, nomor_owner="628110000000", device_token="token-x"):
    wb_db.upsert_config(tenant_id, "device-1", device_token, nomor_owner_whatsapp=nomor_owner)
    wb_db.set_aktif(tenant_id, True)
    return wb_db.get_config(tenant_id)


def _barber(tenant_id, nama, nomor_whatsapp=None):
    return db.add_barber(nama, tenant_id=tenant_id, nomor_whatsapp=nomor_whatsapp)


def _service(tenant_id, nama, harga, modal=0):
    sid = db.add_service(nama, harga, tenant_id=tenant_id)
    with db.get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (modal, sid))
    return sid


def _produk(tenant_id, nama, harga_jual, stok=100):
    pid = db.tambah_produk(nama, harga_modal=0, harga_jual=harga_jual, tenant_id=tenant_id)
    db.restock_produk(pid, "2026-01-01", stok)
    return pid


# ---------------------------------------------------------------------------
# resolve_role()
# ---------------------------------------------------------------------------

def test_resolve_role_owner(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    role, barber = wbp.resolve_role(tenant_id, config, "628110000000")
    assert role == "owner"
    assert barber is None


def test_resolve_role_owner_nomor_beda_format_tetap_cocok(single_tenant):
    """0811... vs 62811... dianggap nomor yang sama (lihat _normalisasi_nomor)."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    role, _ = wbp.resolve_role(tenant_id, config, "08110000000")
    assert role == "owner"


def test_resolve_role_owner_nomor_kedua_juga_dikenali(single_tenant):
    """PERMINTAAN OWNER: maksimal 2 nomor setara akses Owner penuh per
    tenant -- nomor kedua (nomor_owner_whatsapp_2) HARUS dikenali sama
    seperti nomor pertama."""
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "device-1", "token-x", nomor_owner_whatsapp="628110000000",
                         nomor_owner_whatsapp_2="628120000000")
    wb_db.set_aktif(tenant_id, True)
    config = wb_db.get_config(tenant_id)

    role1, _ = wbp.resolve_role(tenant_id, config, "628110000000")
    assert role1 == "owner"
    role2, _ = wbp.resolve_role(tenant_id, config, "628120000000")
    assert role2 == "owner"
    role_tidak_dikenal, _ = wbp.resolve_role(tenant_id, config, "628130000000")
    assert role_tidak_dikenal is None


def test_upsert_config_nomor_owner_1_dan_2_sama_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        wb_db.upsert_config(tenant_id, "device-1", "token-x", nomor_owner_whatsapp="628110000000",
                             nomor_owner_whatsapp_2="08110000000")  # format beda, nomor sama
        assert False, "harus raise ValueError"
    except ValueError as e:
        assert "tidak boleh sama" in str(e)


def test_resolve_role_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id)
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    role, barber = wbp.resolve_role(tenant_id, config, "628199999999")
    assert role == "barber"
    assert barber["nama"] == "Jaka"


def test_resolve_role_tidak_dikenal(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id)
    role, barber = wbp.resolve_role(tenant_id, config, "628100000099")
    assert role is None
    assert barber is None


# ---------------------------------------------------------------------------
# adalah_command_baca() -- klasifikasi teks murni (tanpa DB), dipakai
# routers/whatsapp_bot.py untuk mempersempit proteksi anti-dobel supaya
# cuma berlaku untuk command TULIS (permintaan Owner).
# ---------------------------------------------------------------------------

def test_adalah_command_baca_true_untuk_command_baca():
    for teks in ["Rekap 18 oktober", "rekap 18 oktober - 20 oktober", "Absensi 18 oktober",
                 "Absen hari ini", "Cuti Oktober", "Izin Oktober", "Booking hari ini",
                 "Kuota Libur", "Kuota Libur Romen", "Keterlambatan", "Menu", "Help", "Bantuan",
                 "Daftar Produk", "Rekap Produk Oktober"]:
        assert wbp.adalah_command_baca(teks) is True, teks


def test_adalah_command_baca_false_untuk_command_tulis_atau_ambigu():
    for teks in ["YA", "BATAL", "ya", "batal", "", "   ", "Romen 18 oktober", "Mifta libur",
                 "Produk 18 oktober"]:
        assert wbp.adalah_command_baca(teks) is False, teks


def test_proses_pesan_nomor_tidak_dikenal_tidak_membalas(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id)
    assert wbp.proses_pesan(tenant_id, config, "628100000099", "Menu") is None


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

def test_menu_owner_dan_barber_beda(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    balasan_owner = wbp.proses_pesan(tenant_id, config, "628110000000", "Menu")
    balasan_barber = wbp.proses_pesan(tenant_id, config, "628199999999", "Menu")
    assert "Input data" in balasan_owner
    assert "Input data" not in balasan_barber


def test_pesan_tidak_dikenali_balas_singkat_bukan_menu_lengkap(single_tenant):
    """REVISI (permintaan Owner): pesan tidak dikenali JANGAN langsung
    dibalas daftar Menu lengkap -- cukup pesan singkat yang mengarahkan
    ketik "Menu". Menu lengkap TETAP dikirim kalau diminta EKSPLISIT
    (lihat test_menu_eksplisit_tetap_lengkap di bawah)."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "asdfghjkl random teks")
    assert "tidak dikenali" in balasan.lower()
    assert "Input data service" not in balasan  # bukan daftar Menu lengkap


def test_menu_eksplisit_tetap_lengkap(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Menu")
    assert "Input data service" in balasan


def test_ya_tanpa_pending_balas_singkat_bukan_menu(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "tidak dikenali" in balasan.lower()


# ---------------------------------------------------------------------------
# Input Service -- happy path + ambigu + akses
# ---------------------------------------------------------------------------

def test_input_service_preview_lalu_konfirmasi_ya(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    barber_id = _barber(tenant_id, "Romen")
    _service(tenant_id, "Potong Rambut Test", 105000, modal=5000)
    db.set_setting("persentase_komisi", "50", tenant_id=tenant_id)

    pesan = "Romen 11 oktober 2026\nPotong 2\nTips 30rb"
    preview = wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    assert "Konfirmasi Input Data" in preview
    assert "Potong Rambut Test x2" in preview
    assert "YA" in preview

    # belum tersimpan sebelum konfirmasi
    assert db.get_transaksi_list(barber_id=barber_id, tenant_id=tenant_id) == []

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "berhasil disimpan" in balasan
    daftar = db.get_transaksi_list(barber_id=barber_id, tenant_id=tenant_id)
    assert len(daftar) == 1
    assert daftar[0]["sumber"] == "wa_bot"
    assert daftar[0]["tips"] == 30000
    assert daftar[0]["items"][0]["jumlah"] == 2


def test_input_service_batal_tidak_menyimpan(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    barber_id = _barber(tenant_id, "Romen")
    _service(tenant_id, "Potong Rambut Test", 105000)

    wbp.proses_pesan(tenant_id, config, "628110000000", "Romen 11 oktober 2026\nPotong 2\nTips 0")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "BATAL")
    assert "dibatalkan" in balasan
    assert db.get_transaksi_list(barber_id=barber_id, tenant_id=tenant_id) == []


def test_input_service_tanpa_tanggal_pakai_hari_ini(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    _service(tenant_id, "Potong Rambut Test", 105000)
    preview = wbp.proses_pesan(tenant_id, config, "628110000000", "Romen\nPotong 1\nTips 0")
    assert "Konfirmasi Input Data" in preview


def test_input_service_kode_ambigu_minta_klarifikasi_dan_tidak_simpan_pending(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    _service(tenant_id, "Design Perm", 200000)
    _service(tenant_id, "Daily Pack", 300000)  # akronim SAMA ("DP") dengan di atas -- sengaja ambigu

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Romen\nDp 1\nTips 0")
    assert "bisa jadi beberapa pilihan" in balasan
    # tidak ada pending tersimpan setelah ambigu
    assert wb_db.ambil_pending(tenant_id, "628110000000") is None


def test_input_service_ditolak_untuk_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    _service(tenant_id, "Potong Rambut Test", 105000)
    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Romen\nPotong 1\nTips 0")
    # Barber bukan Owner -> baris pertama TIDAK diproses sebagai Input Service,
    # jatuh ke Menu (bukan command yang dikenali untuk role ini).
    assert "Input data" not in balasan


def test_input_baru_menimpa_pending_lama(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    barber_id = _barber(tenant_id, "Romen")
    _barber(tenant_id, "Jaka")
    _service(tenant_id, "Potong Rambut Test", 105000)

    wbp.proses_pesan(tenant_id, config, "628110000000", "Romen\nPotong 1\nTips 0")
    wbp.proses_pesan(tenant_id, config, "628110000000", "Jaka\nPotong 2\nTips 0")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "Jaka" in balasan
    daftar_romen = db.get_transaksi_list(barber_id=barber_id, tenant_id=tenant_id)
    assert daftar_romen == []  # input Romen yang lama TIDAK ikut tersimpan


# ---------------------------------------------------------------------------
# Tandai Libur via WA
# ---------------------------------------------------------------------------

def test_tandai_libur_via_wa(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    barber_id = _barber(tenant_id, "Mifta")

    preview = wbp.proses_pesan(tenant_id, config, "628110000000", "Mifta libur 11 oktober 2026")
    assert "Konfirmasi Tandai Libur" in preview
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "LIBUR" in balasan
    assert db.get_hari_libur(barber_id, 2026, 10) == 1


def test_tandai_libur_bentrok_cuti_disetujui_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    barber_id = _barber(tenant_id, "Mifta")
    pengajuan = izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-10-11", "2026-10-12", "alasan test")
    izin_cuti_db.set_status_pengajuan(pengajuan["id"], "disetujui", disetujui_oleh="owner1")

    wbp.proses_pesan(tenant_id, config, "628110000000", "Mifta libur 11 oktober 2026")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "❌" in balasan
    assert db.get_hari_libur(barber_id, 2026, 10) == 0


# ---------------------------------------------------------------------------
# Input Produk & Daftar Produk
# ---------------------------------------------------------------------------

def test_daftar_produk(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _produk(tenant_id, "Captain Clay 30gr", 45000)
    _produk(tenant_id, "Captain Clay 80gr", 95000)
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Daftar Produk")
    assert "1. Captain Clay 30gr" in balasan
    assert "2. Captain Clay 80gr" in balasan


def test_daftar_produk_tampilkan_sisa_stok(single_tenant):
    """Permintaan Owner: Daftar Produk ikut tampilkan sisa stok per produk."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _produk(tenant_id, "Captain Clay 30gr", 45000, stok=7)
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Daftar Produk")
    assert "Sisa: 7" in balasan


def test_restock_produk_pakai_nomor(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    p1 = _produk(tenant_id, "Captain Clay 30gr", 45000, stok=5)

    preview = wbp.proses_pesan(tenant_id, config, "628110000000", "Restock 11 oktober 2026\n1 10")
    assert "Konfirmasi Restock Produk" in preview
    assert "Captain Clay 30gr +10" in preview

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "berhasil disimpan" in balasan
    assert db.get_stok_produk(p1) == 15  # 5 awal + 10 restock


def test_restock_produk_ditolak_untuk_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    _produk(tenant_id, "Captain Clay 30gr", 45000)
    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Restock\nCaptain Clay 30 10")
    assert "khusus" in balasan.lower() or "Owner" in balasan


def test_tester_produk_pakai_nama_mengurangi_stok_tanpa_omzet(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    p1 = _produk(tenant_id, "Captain Clay 30gr", 45000, stok=5)

    preview = wbp.proses_pesan(tenant_id, config, "628110000000",
                                "Tester 11 oktober 2026\nCaptain Clay 30 2")
    assert "Konfirmasi Tester Produk" in preview
    assert "Captain Clay 30gr -2" in preview
    assert "TIDAK dihitung omzet" in preview

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "berhasil disimpan" in balasan
    assert db.get_stok_produk(p1) == 3  # 5 awal - 2 tester
    mutasi = db.get_mutasi_produk_list(produk_id=p1, tipe="tester", tenant_id=tenant_id)
    assert len(mutasi) == 1
    omzet = db.get_omzet_penjualan_produk(tahun=2026, bulan=10, tenant_id=tenant_id)
    assert omzet == 0  # tester TIDAK ikut omzet


def test_tester_produk_stok_tidak_cukup_gagal(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _produk(tenant_id, "Captain Clay 30gr", 45000, stok=1)

    wbp.proses_pesan(tenant_id, config, "628110000000", "Tester 11 oktober 2026\nCaptain Clay 30 5")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "GAGAL" in balasan


def test_tester_produk_ditolak_untuk_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    _produk(tenant_id, "Captain Clay 30gr", 45000)
    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Tester\nCaptain Clay 30 1")
    assert "khusus" in balasan.lower() or "Owner" in balasan


def test_input_produk_pakai_nama_dan_nomor(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    p1 = _produk(tenant_id, "Captain Clay 30gr", 45000)
    _produk(tenant_id, "Chief Shampo 400ml", 110000)

    preview = wbp.proses_pesan(tenant_id, config, "628110000000",
                                "Produk 11 oktober 2026\nCaptain Clay 30 1\n2 2")
    assert "Konfirmasi Penjualan Produk" in preview
    assert "Captain Clay 30gr x1" in preview
    assert "Chief Shampo 400ml x2" in preview

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "berhasil disimpan" in balasan
    mutasi = db.get_mutasi_produk_list(produk_id=p1, tipe="jual", tenant_id=tenant_id)
    assert len(mutasi) == 1
    assert mutasi[0]["sumber"] == "wa_bot"


def test_input_produk_tanpa_nama_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _produk(tenant_id, "Captain Clay 30gr", 45000)
    preview = wbp.proses_pesan(tenant_id, config, "628110000000", "Produk\nCaptain Clay 30 1")
    assert "Romen" not in preview  # tidak ada nama barber di mana pun


def test_input_produk_ditolak_untuk_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    _produk(tenant_id, "Captain Clay 30gr", 45000)
    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Produk\nCaptain Clay 30 1")
    assert "khusus" in balasan.lower() or "Owner" in balasan


def test_rekap_produk_bulan(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    pid = _produk(tenant_id, "Captain Clay 30gr", 45000)
    db.jual_produk(pid, "2026-10-05", 3)
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap Produk Oktober 2026")
    assert "Captain Clay 30gr: 3 terjual" in balasan
    assert "Rp135.000" in balasan


# ---------------------------------------------------------------------------
# Rekap
# ---------------------------------------------------------------------------

def test_rekap_satu_tanggal_barber_self_only(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    jaka_id = _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    _barber(tenant_id, "Romen")
    sid = _service(tenant_id, "Potong Rambut Test", 100000, modal=0)
    db.set_setting("persentase_komisi", "50", tenant_id=tenant_id)
    db.tambah_transaksi("2026-10-11", jaka_id, [{"service_id": sid, "jumlah": 1}], tips=10000)

    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Rekap 11 oktober 2026")
    assert "Jaka" in balasan
    assert "Romen" not in balasan
    assert "Potong Rambut Test x1" in balasan
    assert "Rp50.000" in balasan  # komisi


def test_rekap_nama_bulan_singkatan_dikenali(single_tenant):
    """Feedback Owner: "Rekap 18 okt 2026" (singkatan 3 huruf) harus tetap
    dikenali, bukan cuma nama bulan lengkap. Tahun disebut eksplisit supaya
    test ini TIDAK bergantung ke tahun berjalan saat dijalankan (hindari
    flaky lintas tahun, lihat juga test tanpa tahun di bawah)."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    sid = _service(tenant_id, "Potong Rambut Test", 100000)
    db.tambah_transaksi("2026-10-18", romen_id, [{"service_id": sid, "jumlah": 1}])

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 18 okt 2026")
    assert "Potong Rambut Test x1" in balasan


def test_rekap_nama_bulan_singkatan_tanpa_tahun_pakai_tahun_berjalan(single_tenant):
    """Singkatan bulan TANPA tahun tetap default ke tahun berjalan, sama
    seperti nama bulan lengkap tanpa tahun -- dites pakai date.today()
    supaya tidak flaky lintas tahun."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    sid = _service(tenant_id, "Potong Rambut Test", 100000)
    hari_ini = date.today()
    db.tambah_transaksi(hari_ini.isoformat(), romen_id, [{"service_id": sid, "jumlah": 1}])

    bulan_singkat = {1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "mei", 6: "jun", 7: "jul",
                     8: "agu", 9: "sep", 10: "okt", 11: "nov", 12: "des"}[hari_ini.month]
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", f"Rekap {hari_ini.day} {bulan_singkat}")
    assert "Potong Rambut Test x1" in balasan


def test_rekap_nama_bulan_lengkap_tidak_terpotong_singkatannya_sendiri(single_tenant):
    """BUGFIX: menambahkan singkatan "okt" ke _BULAN_ID TIDAK BOLEH bikin
    "11 oktober 2026" malah ke-parse jadi cuma "11 okt" (alternasi regex
    berhenti di match PERTAMA, bukan terpanjang) -- itu bikin grup tahun
    opsional gagal cocok dan diam-diam jatuh ke tahun ini, bukan 2026.
    Dites dengan tahun yang BEDA dari tahun berjalan supaya kegagalan ini
    pasti ketahuan (transaksi di 2026 tidak akan ketemu kalau bot salah
    sangka ini "tahun ini")."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    sid = _service(tenant_id, "Potong Rambut Test", 100000)
    db.tambah_transaksi("2026-10-11", romen_id, [{"service_id": sid, "jumlah": 1}])

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 11 oktober 2026")
    assert "11 Okt 2026" in balasan
    assert "Potong Rambut Test x1" in balasan


def test_rekap_owner_semua_barber_termasuk_libur(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    mifta_id = _barber(tenant_id, "Mifta")
    db.tandai_libur(mifta_id, "2026-10-11")
    _barber(tenant_id, "Romen")

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 11 oktober 2026")
    assert "Mifta" in balasan and "LIBUR" in balasan
    assert "Romen" in balasan and "Tidak ada transaksi" in balasan


def test_rekap_periode_sampai_10_hari_dipecah_per_hari(single_tenant):
    """PERMINTAAN OWNER: rekap periode <= 10 hari dipecah per tanggal
    (bukan agregat total keseluruhan) -- tiap hari tetap muncul walau
    tidak ada transaksi, supaya Owner lihat lengkap semua hari."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    sid = _service(tenant_id, "Potong Rambut Test", 100000)
    db.tambah_transaksi("2026-10-11", romen_id, [{"service_id": sid, "jumlah": 1}])
    db.tambah_transaksi("2026-10-13", romen_id, [{"service_id": sid, "jumlah": 2}])

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 11 oktober - 15 oktober 2026")
    assert "Periode" in balasan
    assert "11 Okt 2026" in balasan and "Potong Rambut Test x1" in balasan
    assert "13 Okt 2026" in balasan and "Potong Rambut Test x2" in balasan
    assert "12 Okt 2026" in balasan and "14 Okt 2026" in balasan and "15 Okt 2026" in balasan
    assert "Tanpa keterangan" in balasan  # hari 12/14/15 tidak ada transaksi & tidak absen
    assert "Total Komisi: Rp120.000" in balasan  # komisi (bukan harga) qty 1 + qty 2


def test_rekap_periode_lebih_dari_10_hari_tetap_agregat(single_tenant):
    """Periode > 10 hari TETAP format agregat lama (tidak dipecah per
    hari) supaya pesan tidak kepanjangan."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    sid = _service(tenant_id, "Potong Rambut Test", 100000)
    db.tambah_transaksi("2026-10-01", romen_id, [{"service_id": sid, "jumlah": 1}])
    db.tambah_transaksi("2026-10-11", romen_id, [{"service_id": sid, "jumlah": 2}])

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 1 oktober - 15 oktober 2026")
    assert "Periode" in balasan
    assert "Potong Rambut Test x3" in balasan  # agregat 1+2, bukan per hari
    assert "Tanpa keterangan" not in balasan


def test_rekap_periode_dengan_nama_barber_sebelum_tanggal_tidak_tampilkan_semua(single_tenant):
    """BUGFIX laporan Owner: "Rekap Romen 11 oktober - 16 oktober 2026" --
    nama barber yang ditulis SEBELUM rentang tanggal sebelumnya hilang di
    _parse_periode() (cuma teks SETELAH tanggal kedua yang diambil), jadi
    _cmd_rekap() jatuh ke default "semua barber" walau nama sudah jelas
    disebut. Harus tetap terbatas ke Romen saja, Mifta tidak boleh ikut
    muncul."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    _barber(tenant_id, "Mifta")
    sid = _service(tenant_id, "Potong Rambut Test", 100000)
    db.tambah_transaksi("2026-10-11", romen_id, [{"service_id": sid, "jumlah": 1}])

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000",
                                "Rekap Romen 11 oktober - 16 oktober 2026")
    assert "Romen" in balasan
    assert "Mifta" not in balasan


def test_rekap_periode_uang_harian_ikut_dihitung(single_tenant):
    """BUGFIX: sebelumnya Uang Harian cuma dihitung kalau tanggal_mulai ==
    tanggal_selesai -- rekap PERIODE selalu Rp0/hilang tanpa pernah
    memanggil hitung_uang_harian_dinamis_rentang() yang sudah ada."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    with db.get_conn() as conn:
        conn.execute("UPDATE barbers SET uang_harian = ? WHERE id = ?", (100000, romen_id))
    sid = _service(tenant_id, "Potong Rambut Test", 100000)
    db.set_uang_harian_acuan_ids([sid], tenant_id=tenant_id)
    db.set_setting("uang_harian_target_service_harian", "1", tenant_id=tenant_id)
    db.tambah_transaksi("2026-10-11", romen_id, [{"service_id": sid, "jumlah": 1}])
    db.tambah_transaksi("2026-10-12", romen_id, [{"service_id": sid, "jumlah": 1}])

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000",
                                "Rekap 11 oktober - 12 oktober 2026")
    assert "Uang Harian: Rp200.000" in balasan  # 2 hari x Rp100.000


def test_rekap_per_hari_bedakan_tanpa_keterangan_dan_tidak_ada_transaksi(single_tenant, monkeypatch):
    """PERMINTAAN OWNER: hari tanpa transaksi dibedakan -- "Tanpa
    keterangan" kalau barber TIDAK absen/check-in hari itu, "Tidak ada
    transaksi." kalau sudah check-in tapi memang tidak ada transaksi."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    attendance_db.set_settings(tenant_id, jam_masuk="09:00", jam_pulang="18:00",
                                lokasi_latitude=-6.175392, lokasi_longitude=106.827153, radius_meter=500)
    romen_id = _barber(tenant_id, "Romen")

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 10, 12, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, romen_id, -6.175392, 106.827153, accuracy=15)

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 11 oktober - 13 oktober 2026")
    assert "*11 Okt 2026*\nTanpa keterangan" in balasan  # tidak absen
    assert "*12 Okt 2026*\nTidak ada transaksi." in balasan  # sudah absen, tidak ada transaksi
    assert "*13 Okt 2026*\nTanpa keterangan" in balasan


def test_rekap_toggle_sembunyikan_potongan_keterlambatan(single_tenant, monkeypatch):
    """PERMINTAAN OWNER: Superadmin bisa matikan tampilan potongan
    keterlambatan khusus di WA Bot -- Uang Harian yang DITAMPILKAN
    mengabaikan potongan keterlambatan (toleransi ATAU limit, sama-sama
    masuk keterlambatan["potongan_persen"] di evaluasi_hari()), potongan
    lain TETAP berlaku. Angka ASLI (Dashboard/Slip Gaji) tidak berubah --
    dicek lewat db.hitung_uang_harian_per_hari() langsung."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    attendance_db.set_settings(tenant_id, jam_masuk="09:00", toleransi_menit=30, jam_pulang="18:00",
                                lokasi_latitude=-6.175392, lokasi_longitude=106.827153, radius_meter=500)
    romen_id = _barber(tenant_id, "Romen")
    db.update_barber(romen_id, uang_harian=60000)
    uhd.set_config(tenant_id, aktif=True, keterlambatan_gunakan_toleransi=True,
                   keterlambatan_gunakan_limit=False, keterlambatan_potongan_persen=20)
    sid = _service(tenant_id, "Potong Rambut Test", 50000)
    db.tambah_transaksi("2026-10-11", romen_id, [{"service_id": sid, "jumlah": 1}])

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 10, 11, 9, 35, tzinfo=WIB))
    attendance_db.check_in(tenant_id, romen_id, -6.175392, 106.827153, accuracy=15)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 10, 11, 18, 0, tzinfo=WIB))
    attendance_db.check_out(tenant_id, romen_id, -6.175392, 106.827153, accuracy=15)

    barber = db.get_barber(romen_id)
    assert db.hitung_uang_harian_per_hari(barber, "2026-10-11") == 48000  # 60rb - 20%

    balasan_default = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 11 oktober 2026")
    assert "Uang Harian: Rp48.000" in balasan_default  # default: tampilkan potongan apa adanya

    wb_db.set_tampilkan_potongan_keterlambatan(tenant_id, False)
    config_off = wb_db.get_config(tenant_id)
    balasan_off = wbp.proses_pesan(tenant_id, config_off, "628110000000", "Rekap 11 oktober 2026")
    assert "Uang Harian: Rp60.000" in balasan_off  # potongan keterlambatan disembunyikan

    # Angka ASLI (dipakai Dashboard/Slip Gaji) TETAP 48.000, tidak ikut berubah.
    assert db.hitung_uang_harian_per_hari(barber, "2026-10-11") == 48000


# ---------------------------------------------------------------------------
# Absensi
# ---------------------------------------------------------------------------

def test_absensi_empat_status(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    attendance_db.set_settings(tenant_id, jam_masuk="09:00", jam_pulang="18:00",
                                lokasi_latitude=-6.2, lokasi_longitude=106.8, radius_meter=500)
    lengkap_id = _barber(tenant_id, "Lengkap")
    belum_pulang_id = _barber(tenant_id, "BelumPulang")
    belum_checkin_id = _barber(tenant_id, "BelumCheckin")
    libur_id = _barber(tenant_id, "Librr")
    db.tandai_libur(libur_id, "2026-10-11")

    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 10, 11, 9, 0, tzinfo=WIB))
    attendance_db.check_in(tenant_id, lengkap_id, -6.2, 106.8, accuracy=10)
    attendance_db.check_in(tenant_id, belum_pulang_id, -6.2, 106.8, accuracy=10)
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 10, 11, 18, 0, tzinfo=WIB))
    attendance_db.check_out(tenant_id, lengkap_id, -6.2, 106.8, accuracy=10)

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Absensi 11 oktober 2026")
    assert "Lengkap: Masuk 09:00, Pulang 18:00" in balasan
    assert "BelumPulang: Masuk 09:00, belum Check Out" in balasan
    assert "BelumCheckin: Belum Check In" in balasan
    assert "Librr: LIBUR" in balasan


def test_absen_hari_ini_barber_self_only(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    jaka_id = _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    _barber(tenant_id, "Romen")
    monkeypatch.setattr(attendance_db, "tanggal_hari_ini", lambda: "2026-10-11")
    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Absen hari ini")
    assert "Jaka" in balasan
    assert "Romen" not in balasan


# ---------------------------------------------------------------------------
# Cuti/Izin -- terbuka untuk semua barber (BUKAN self-only)
# ---------------------------------------------------------------------------

def test_cuti_terbuka_untuk_barber_lihat_semua(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    jaka_id = _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    izin_cuti_db.buat_pengajuan(romen_id, "cuti", "2026-10-20", "2026-10-25", "alasan test")

    # Jaka (barber lain) minta Cuti Oktober -- tetap lihat punya Romen.
    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Cuti Oktober 2026")
    assert "Romen" in balasan
    assert "Menunggu Persetujuan" in balasan


def test_cuti_rentang_melintasi_bulan_muncul_di_kedua_bulan(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    pengajuan = izin_cuti_db.buat_pengajuan(romen_id, "cuti", "2026-10-30", "2026-11-03", "alasan test")
    izin_cuti_db.set_status_pengajuan(pengajuan["id"], "disetujui", disetujui_oleh="owner1")

    balasan_okt = wbp.proses_pesan(tenant_id, config, "628110000000", "Cuti Oktober 2026")
    balasan_nov = wbp.proses_pesan(tenant_id, config, "628110000000", "Cuti November 2026")
    assert "Romen" in balasan_okt
    assert "Romen" in balasan_nov


def test_cuti_kosong(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Cuti Desember 2026")
    assert "Tidak ada pengajuan" in balasan


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

def test_booking_barber_tanggal_lewat_ditolak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    monkeypatch.setattr(wbp, "date", wbp.date)  # no-op (dipakai hanya untuk kejelasan patch point)

    import whatsapp_bot_parser as mod
    kelas_date_asli = mod.date

    class _TanggalPalsu(kelas_date_asli):
        @classmethod
        def today(cls):
            return kelas_date_asli(2026, 10, 16)

    monkeypatch.setattr(mod, "date", _TanggalPalsu)
    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Booking 15 oktober 2026")
    assert "sudah lewat" in balasan


def test_booking_owner_boleh_tanggal_lewat(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Booking 11 oktober 2026")
    assert "sudah lewat" not in balasan


# ---------------------------------------------------------------------------
# Kuota Libur & Keterlambatan
# ---------------------------------------------------------------------------

def test_kuota_libur_self_only(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    _barber(tenant_id, "Romen")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=5)

    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Kuota Libur")
    assert "Jaka" in balasan
    assert "Romen" not in balasan


def test_keterlambatan_tanpa_pengaturan_tampilkan_limit(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Keterlambatan")
    assert "Romen" in balasan
    assert "Keterlambatan: 0/120 menit (sisa 120 menit)" in balasan
    assert "Pulang Cepat: 0/120 menit (sisa 120 menit)" in balasan


# ---------------------------------------------------------------------------
# Kuota pesan/bulan & idempotensi -- lewat endpoint webhook penuh
# ---------------------------------------------------------------------------

def test_webhook_kuota_tidak_terpakai_untuk_pengirim_tidak_dikenal(single_tenant, monkeypatch):
    monkeypatch.setattr("routers.whatsapp_bot._WEBHOOK_SECRET", "secret-rahasia")
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "pnid-1", "token-1")
    wb_db.set_aktif(tenant_id, True)

    client = single_tenant["client"]
    r = client.post("/api/whatsapp-bot/webhook/secret-rahasia",
                     data={"device": "pnid-1", "sender": "628100000099", "message": "Menu"})
    assert r.status_code == 200, r.text
    assert wb_db.kuota_terpakai_bulan_ini(tenant_id) == 0


def test_webhook_pesan_duplikat_diproses_sekali_saja(single_tenant, monkeypatch):
    """REVISI (permintaan Owner): proteksi anti-dobel sekarang cuma
    berlaku untuk command TULIS (lihat adalah_command_baca()) -- dites
    pakai pesan yang BUKAN command baca ("Halo", tidak cocok pola apa
    pun = diklasifikasi TULIS/berpotensi Input Service) supaya tetap
    menguji skenario asli (webhook retry Fonnte), bukan kena pengecualian
    command baca yang sekarang SELALU diproses ulang (lihat test
    test_webhook_post_command_baca_sama_persis_tetap_diproses_ulang di
    test_whatsapp_bot.py)."""
    monkeypatch.setattr("routers.whatsapp_bot._WEBHOOK_SECRET", "secret-rahasia")
    tenant_id = single_tenant["tenant_id"]
    config = wb_db.upsert_config(tenant_id, "pnid-2", "token-2", nomor_owner_whatsapp="628110000000")
    wb_db.set_aktif(tenant_id, True)

    client = single_tenant["client"]
    data = {"device": "pnid-2", "sender": "628110000000", "message": "Halo"}
    client.post("/api/whatsapp-bot/webhook/secret-rahasia", data=data)
    client.post("/api/whatsapp-bot/webhook/secret-rahasia", data=data)  # dikirim ulang (retry)
    assert wb_db.kuota_terpakai_bulan_ini(tenant_id) == 1  # BUKAN 2


# ---------------------------------------------------------------------------
# INPUT HARIAN (gabungan banyak barber + Libur + Produk, koreksi interaktif)
# ---------------------------------------------------------------------------

def test_input_harian_lengkap_tanpa_koreksi_lalu_ya(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen = _barber(tenant_id, "Romen")
    ozi = _barber(tenant_id, "Ozi")
    mifta = _barber(tenant_id, "Mifta")
    _service(tenant_id, "Dandan Cepat", 100000, modal=10000)
    _service(tenant_id, "Hebat Wangi", 150000, modal=20000)
    _produk(tenant_id, "Wax Pomade", 50000)
    db.set_setting("persentase_komisi", "50", tenant_id=tenant_id)

    pesan = (
        "Input Harian 20 oktober 2026\n"
        "Romen\n"
        "Dc 3\n"
        "Tips 60000\n"
        "Ozi\n"
        "Dc 2\n"
        "Hw 2\n"
        "Tips 55000\n"
        "Libur: Mifta\n"
        "Produk:\n"
        "Wax Pomade 1"
    )
    preview = wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    assert "Konfirmasi Input Harian" in preview
    assert "Romen" in preview and "Ozi" in preview
    assert "Mifta" in preview
    assert "Wax Pomade x1" in preview
    assert "YA" in preview
    # belum tersimpan apa pun sebelum konfirmasi
    assert db.get_transaksi_list(barber_id=romen, tenant_id=tenant_id) == []

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "diproses" in balasan
    assert "Romen" in balasan and "Ozi" in balasan and "Mifta" in balasan

    daftar_romen = db.get_transaksi_list(barber_id=romen, tenant_id=tenant_id)
    assert len(daftar_romen) == 1
    assert daftar_romen[0]["tips"] == 60000
    assert daftar_romen[0]["sumber"] == "wa_bot"

    daftar_ozi = db.get_transaksi_list(barber_id=ozi, tenant_id=tenant_id)
    assert len(daftar_ozi) == 1
    assert len(daftar_ozi[0]["items"]) == 2

    assert db.get_hari_libur(mifta, 2026, 10) == 1
    mutasi = db.get_mutasi_produk_list(tipe="jual", tenant_id=tenant_id)
    assert len(mutasi) == 1
    assert mutasi[0]["jumlah"] == 1


def test_input_harian_koreksi_kode_servis_lalu_lanjut(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen = _barber(tenant_id, "Romen")
    _service(tenant_id, "Dandan Cepat", 100000)

    pesan = "Input Harian 20 oktober 2026\nRomen\nXyz 3\nTips 0"
    tanya = wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    assert "tidak dikenali" in tanya
    assert "Romen" in tanya  # konteks baris disebut di bagian barber mana

    # belum tersimpan sebagai pending siap-YA (masih draft koreksi)
    pending = wb_db.ambil_pending(tenant_id, "628110000000")
    assert pending["jenis"] == "input_harian_draft"

    balasan_koreksi = wbp.proses_pesan(tenant_id, config, "628110000000", "Dc")
    assert "Konfirmasi Input Harian" in balasan_koreksi
    assert "Dandan Cepat x3" in balasan_koreksi

    hasil = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "diproses" in hasil
    daftar = db.get_transaksi_list(barber_id=romen, tenant_id=tenant_id)
    assert daftar[0]["items"][0]["jumlah"] == 3


def test_input_harian_koreksi_nama_barber_lalu_lanjut(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen = _barber(tenant_id, "Romen")
    _service(tenant_id, "Dandan Cepat", 100000)

    pesan = "Input Harian 20 oktober 2026\nRomenn\nDc 1\nTips 0"
    tanya = wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    assert "tidak" in tanya.lower()

    balasan_koreksi = wbp.proses_pesan(tenant_id, config, "628110000000", "Romen")
    assert "Konfirmasi Input Harian" in balasan_koreksi
    assert "Romen" in balasan_koreksi

    wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert len(db.get_transaksi_list(barber_id=romen, tenant_id=tenant_id)) == 1


def test_input_harian_koreksi_nama_produk_lalu_lanjut(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    _service(tenant_id, "Dandan Cepat", 100000)
    pid = _produk(tenant_id, "Wax Pomade", 50000)

    pesan = "Input Harian 20 oktober 2026\nRomen\nDc 1\nTips 0\nProduk:\nWex Pomade 2"
    tanya = wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    assert "produk" in tanya.lower()

    balasan_koreksi = wbp.proses_pesan(tenant_id, config, "628110000000", "Wax Pomade")
    assert "Wax Pomade x2" in balasan_koreksi

    wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    mutasi = db.get_mutasi_produk_list(produk_id=pid, tipe="jual", tenant_id=tenant_id)
    assert len(mutasi) == 1
    assert mutasi[0]["jumlah"] == 2


def test_input_harian_koreksi_nama_libur_lalu_lanjut(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    mifta = _barber(tenant_id, "Mifta")
    _service(tenant_id, "Dandan Cepat", 100000)

    pesan = "Input Harian 20 oktober 2026\nRomen\nDc 1\nTips 0\nLibur: Miftah"
    tanya = wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    assert "Libur" in tanya

    balasan_koreksi = wbp.proses_pesan(tenant_id, config, "628110000000", "Mifta")
    assert "Konfirmasi Input Harian" in balasan_koreksi
    assert "Mifta" in balasan_koreksi

    wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert db.get_hari_libur(mifta, 2026, 10) == 1


def test_input_harian_batal_saat_menunggu_koreksi_membatalkan_semua(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen = _barber(tenant_id, "Romen")
    _service(tenant_id, "Dandan Cepat", 100000)

    pesan = "Input Harian 20 oktober 2026\nRomen\nXyz 3\nTips 0"
    wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "BATAL")
    assert "dibatalkan" in balasan
    assert wb_db.ambil_pending(tenant_id, "628110000000") is None
    assert db.get_transaksi_list(barber_id=romen, tenant_id=tenant_id) == []


def test_input_harian_libur_kena_cascade_kuota_ditampilkan_di_hasil(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    mifta = _barber(tenant_id, "Mifta")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=0)  # 0 = tidak dibatasi -> selalu "libur" murni
    # Set kuota 1 lalu habiskan dulu supaya baris Libur di Input Harian jatuh ke cascade Cuti.
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_libur_bulanan=1)
    db.tandai_libur(mifta, "2026-10-01")  # kuota Libur bulan itu sudah terpakai 1/1

    pesan = "Input Harian 20 oktober 2026\nLibur: Mifta"
    preview = wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    assert "Konfirmasi Input Harian" in preview

    hasil = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "CUTI" in hasil


def test_input_harian_ditolak_untuk_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    _barber(tenant_id, "Jaka", nomor_whatsapp="628199999999")
    _service(tenant_id, "Dandan Cepat", 100000)
    balasan = wbp.proses_pesan(tenant_id, config, "628199999999", "Input Harian\nRomen\nDc 1\nTips 0")
    assert "khusus" in balasan.lower() or "Owner" in balasan


def test_input_harian_tanpa_tanggal_pakai_hari_ini(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    _service(tenant_id, "Dandan Cepat", 100000)
    preview = wbp.proses_pesan(tenant_id, config, "628110000000", "Input Harian\nRomen\nDc 1\nTips 0")
    assert "Konfirmasi Input Harian" in preview


# ---------------------------------------------------------------------------
# PERMINTAAN OWNER: Tandai Libur (standalone "<barber> libur" MAUPUN baris
# "Libur:" di Input Harian) DITOLAK kalau tanggal itu sudah otomatis Libur
# Mingguan (Barber Holiday) -- lihat kuota_libur_db.tandai_libur_dengan_kuota()/
# test_kuota_libur.py untuk cakupan lengkap fungsi intinya. Test di sini
# cuma memastikan guard itu TEREFLEKSI dengan benar lewat kedua jalur WA Bot.
# ---------------------------------------------------------------------------

_BULAN_NAMA_ID = {1: "januari", 2: "februari", 3: "maret", 4: "april", 5: "mei", 6: "juni",
                   7: "juli", 8: "agustus", 9: "september", 10: "oktober", 11: "november", 12: "desember"}


def _ke_teks_tanggal_id(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {_BULAN_NAMA_ID[m]} {y}"


def test_tandai_libur_standalone_ditolak_kalau_jadwal_mingguan(single_tenant, monkeypatch):
    """"Hari ini" DIBEKUKAN PERSIS di tanggal target (bukan dari
    _tanggal_hari()/jam dinding sungguhan) -- sejak kuota_libur_db.py::
    pastikan_libur_mingguan_tercatat() ada, get_hari_libur() BENAR-BENAR
    mematerialisasi tanggal jadwal mingguan LAIN di bulan yang sama yang
    kebetulan sudah lewat -- lihat test_kuota_libur.py untuk cakupan
    lengkapnya. Tanggal dipilih di hari ke-1..7 (jaminan kemunculan
    PERTAMA hari itu bulan ini, tidak ada tanggal jadwal mingguan lain
    sebelumnya) supaya hasil hitung deterministik."""
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    barber_id = _barber(tenant_id, "Romen")
    booking_db.set_hari_libur_mingguan(barber_id, ["senin"])
    tanggal = "2026-08-03"  # Senin, hari ke-3 -- kemunculan PERTAMA "senin" bulan itu
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 3, 9, 0, tzinfo=WIB))

    preview = wbp.proses_pesan(tenant_id, config, "628110000000", f"Romen libur {_ke_teks_tanggal_id(tanggal)}")
    assert "Konfirmasi Tandai Libur" in preview  # preview tidak prediksi cascade, sama seperti kuota

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "Libur Mingguan" in balasan
    # Baris MANUAL ditolak, TAPI tanggal ini TETAP otomatis ter-materialisasi
    # sebagai Libur Mingguan begitu get_hari_libur() dipanggil.
    assert db.get_hari_libur(barber_id, 2026, 8) == 1


def test_input_harian_libur_ditolak_kalau_jadwal_mingguan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    barber_id = _barber(tenant_id, "Romen")
    booking_db.set_hari_libur_mingguan(barber_id, ["senin"])
    tanggal = "2026-08-03"  # Senin, hari ke-3 -- kemunculan PERTAMA "senin" bulan itu
    monkeypatch.setattr(attendance_db, "_sekarang_wib", lambda: datetime(2026, 8, 3, 9, 0, tzinfo=WIB))

    pesan = f"Input Harian {_ke_teks_tanggal_id(tanggal)}\nLibur: Romen"
    preview = wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    assert "Konfirmasi Input Harian" in preview  # preview tidak prediksi cascade, sama seperti kasus kuota

    hasil = wbp.proses_pesan(tenant_id, config, "628110000000", "YA")
    assert "Libur Mingguan" in hasil
    assert db.get_hari_libur(barber_id, 2026, 8) == 1


# ---------------------------------------------------------------------------
# PERBAIKAN Owner (audit "tidak boleh input dobel"): idempotency_key per
# pending Transaksi (input_service & Input Harian) -- menutup celah race
# condition (dua webhook diproses BERSAMAAN, keduanya membawa pending yang
# SAMA sebelum salah satu sempat hapus_pending(), atau Fonnte mengirim
# ulang webhook di LUAR jendela whatsapp_bot_db.pesan_duplikat() 2 menit).
# ---------------------------------------------------------------------------

def test_input_service_konfirmasi_race_dengan_pending_sama_tidak_dobel(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    barber_id = _barber(tenant_id, "Romen")
    _service(tenant_id, "Potong Rambut Test", 105000)

    pesan = "Romen 11 oktober 2026\nPotong 2"
    wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    pending = wb_db.ambil_pending(tenant_id, "628110000000")
    assert pending is not None
    assert pending["payload"].get("idempotency_key")

    # Simulasi dua request "YA" yang diproses BERSAMAAN -- keduanya
    # membawa pending yang SAMA (idempotency_key sama persis), karena
    # keduanya terlanjur membaca pending ini SEBELUM salah satu sempat
    # hapus_pending() (lihat _proses_konfirmasi()).
    balasan1 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    balasan2 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    assert "berhasil disimpan" in balasan1
    assert "berhasil disimpan" in balasan2

    daftar = db.get_transaksi_list(barber_id=barber_id, tenant_id=tenant_id)
    assert len(daftar) == 1


def test_input_harian_konfirmasi_race_dengan_pending_sama_tidak_dobel(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen = _barber(tenant_id, "Romen")
    _service(tenant_id, "Dandan Cepat", 100000, modal=10000)

    pesan = "Input Harian 20 oktober 2026\nRomen\nDc 3\nTips 60000"
    wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    pending = wb_db.ambil_pending(tenant_id, "628110000000")
    assert pending is not None
    assert pending["payload"]["barbers"][0].get("idempotency_key")

    balasan1 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    balasan2 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    assert "diproses" in balasan1
    assert "diproses" in balasan2

    daftar = db.get_transaksi_list(barber_id=romen, tenant_id=tenant_id)
    assert len(daftar) == 1


def test_input_produk_konfirmasi_race_dengan_pending_sama_tidak_dobel(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    produk_id = _produk(tenant_id, "Captain Clay 30gr", 45000, stok=10)

    wbp.proses_pesan(tenant_id, config, "628110000000", "Produk\nCaptain Clay 30 2")
    pending = wb_db.ambil_pending(tenant_id, "628110000000")
    assert pending is not None
    assert pending["payload"]["items"][0].get("idempotency_key")

    balasan1 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    balasan2 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    assert "berhasil disimpan" in balasan1
    assert "berhasil disimpan" in balasan2
    assert db.get_stok_produk(produk_id) == 8  # HANYA terpotong sekali (bukan 6)


def test_restock_produk_konfirmasi_race_dengan_pending_sama_tidak_dobel(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    produk_id = _produk(tenant_id, "Captain Clay 30gr", 45000, stok=5)

    wbp.proses_pesan(tenant_id, config, "628110000000", "Restock\nCaptain Clay 30 10")
    pending = wb_db.ambil_pending(tenant_id, "628110000000")
    assert pending["payload"]["items"][0].get("idempotency_key")

    balasan1 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    balasan2 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    assert "berhasil disimpan" in balasan1
    assert "berhasil disimpan" in balasan2
    assert db.get_stok_produk(produk_id) == 15  # HANYA bertambah sekali (bukan 25)


def test_tester_produk_konfirmasi_race_dengan_pending_sama_tidak_dobel(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    produk_id = _produk(tenant_id, "Captain Clay 30gr", 45000, stok=10)

    wbp.proses_pesan(tenant_id, config, "628110000000", "Tester\nCaptain Clay 30 2")
    pending = wb_db.ambil_pending(tenant_id, "628110000000")
    assert pending["payload"]["items"][0].get("idempotency_key")

    balasan1 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    balasan2 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    assert "berhasil disimpan" in balasan1
    assert "berhasil disimpan" in balasan2
    assert db.get_stok_produk(produk_id) == 8  # HANYA terpotong sekali (bukan 6)


def test_input_harian_produk_konfirmasi_race_dengan_pending_sama_tidak_dobel(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen = _barber(tenant_id, "Romen")
    _service(tenant_id, "Dandan Cepat", 100000, modal=10000)
    produk_id = _produk(tenant_id, "Wax Pomade", 50000, stok=10)

    pesan = "Input Harian 20 oktober 2026\nRomen\nDc 1\nTips 0\nProduk:\nWax Pomade 2"
    wbp.proses_pesan(tenant_id, config, "628110000000", pesan)
    pending = wb_db.ambil_pending(tenant_id, "628110000000")
    assert pending["payload"]["produk"][0].get("idempotency_key")

    balasan1 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    balasan2 = wbp._proses_konfirmasi(tenant_id, "628110000000", pending, "YA")
    assert "diproses" in balasan1
    assert "diproses" in balasan2
    assert db.get_stok_produk(produk_id) == 8  # HANYA terpotong sekali (bukan 6)
