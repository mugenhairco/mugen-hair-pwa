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
import database as db
import izin_cuti_db
import whatsapp_bot_db as wb_db
import whatsapp_bot_parser as wbp

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


def test_pesan_tidak_dikenali_balas_menu(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "asdfghjkl random teks")
    assert "Menu" in balasan


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


def test_rekap_owner_semua_barber_termasuk_libur(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    mifta_id = _barber(tenant_id, "Mifta")
    db.tandai_libur(mifta_id, "2026-10-11")
    _barber(tenant_id, "Romen")

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 11 oktober 2026")
    assert "Mifta" in balasan and "LIBUR" in balasan
    assert "Romen" in balasan and "Tidak ada transaksi" in balasan


def test_rekap_periode(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    romen_id = _barber(tenant_id, "Romen")
    sid = _service(tenant_id, "Potong Rambut Test", 100000)
    db.tambah_transaksi("2026-10-11", romen_id, [{"service_id": sid, "jumlah": 1}])
    db.tambah_transaksi("2026-10-13", romen_id, [{"service_id": sid, "jumlah": 2}])

    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Rekap 11 oktober - 15 oktober 2026")
    assert "Periode" in balasan
    assert "Potong Rambut Test x3" in balasan  # agregat 1+2


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


def test_keterlambatan_tanpa_pengaturan_nol(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = _config(tenant_id, nomor_owner="628110000000")
    _barber(tenant_id, "Romen")
    balasan = wbp.proses_pesan(tenant_id, config, "628110000000", "Keterlambatan")
    assert "Romen: Telat 0x, Pulang Cepat 0x" in balasan


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
    monkeypatch.setattr("routers.whatsapp_bot._WEBHOOK_SECRET", "secret-rahasia")
    tenant_id = single_tenant["tenant_id"]
    config = wb_db.upsert_config(tenant_id, "pnid-2", "token-2", nomor_owner_whatsapp="628110000000")
    wb_db.set_aktif(tenant_id, True)

    client = single_tenant["client"]
    data = {"device": "pnid-2", "sender": "628110000000", "message": "Menu"}
    client.post("/api/whatsapp-bot/webhook/secret-rahasia", data=data)
    client.post("/api/whatsapp-bot/webhook/secret-rahasia", data=data)  # dikirim ulang (retry)
    assert wb_db.kuota_terpakai_bulan_ini(tenant_id) == 1  # BUKAN 2
