"""test_absensi_reminder.py — FITUR Reminder Absensi via WhatsApp
=============================================================================
Menguji absensi_reminder_db.jalankan_pengecekan() (dipanggil endpoint
routers/cron_reminder.py) -- waktu "sekarang" di-monkeypatch ke nilai TETAP
(bukan bergantung jam sungguhan saat test dijalankan) supaya deterministik
dan aman lintas zona waktu/jam berapa pun test ini dijalankan."""

from datetime import datetime

import absensi_reminder_db
import booking_db
import database as db
import izin_cuti_db
import whatsapp_service
from absensi_reminder_db import WIB
from database import get_conn

# PENTING: tanggal yang dipakai SELALU "hari ini" sungguhan (BUKAN tanggal
# tetap seperti 2026-01-14) -- absensi_reminder_db._sekarang_wib() di-
# monkeypatch per test (lihat _patch_now()), TAPI attendance_db.
# get_log_hari_ini() yang dipanggil jalankan_pengecekan() TIDAK ikut
# di-patch (modul lain) dan tetap memakai TANGGAL SUNGGUHAN hari ini --
# kalau tanggal di sini tidak cocok dengan itu, log Check In/Out yang
# disiapkan test tidak akan pernah ketemu. Jam-nya BOLEH bebas (tidak
# perlu cocok jam sungguhan) karena HANYA tanggal yang dibaca ulang dari
# modul lain, bukan jam-nya.
def _hari_ini() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d")


def _jam(waktu_hhmm: str) -> datetime:
    tahun, bulan, hari = (int(x) for x in _hari_ini().split("-"))
    jam, menit = (int(x) for x in waktu_hhmm.split(":"))
    return datetime(tahun, bulan, hari, jam, menit, tzinfo=WIB)


def _patch_now(monkeypatch, waktu):
    monkeypatch.setattr(absensi_reminder_db, "_sekarang_wib", lambda: waktu)


def _setup_jam_operasional(tenant_id, jam_buka="10:00", jam_tutup="20:00"):
    booking_db.update_booking_settings(jam_buka=jam_buka, jam_tutup=jam_tutup, tenant_id=tenant_id)


def _tambah_barber(tenant_id, nama, nomor_whatsapp="081234567890"):
    return db.add_barber(nama, uang_harian=0, tenant_id=tenant_id, nomor_whatsapp=nomor_whatsapp)


def _insert_log(barber_id, tenant_id, tanggal, check_in=True, check_out=False):
    now_iso = datetime.now(WIB).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO attendance_logs (barber_id, tanggal, check_in_at, check_out_at, created_at, tenant_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (barber_id, tanggal, now_iso if check_in else None, now_iso if check_out else None, now_iso, tenant_id),
        )


def _mock_wa(monkeypatch, berhasil=True):
    terkirim = []

    def _fake(nomor, pesan, tenant_id=None):
        terkirim.append({"nomor": nomor, "pesan": pesan, "tenant_id": tenant_id})
        return berhasil

    monkeypatch.setattr(whatsapp_service, "kirim_whatsapp", _fake)
    return terkirim


def _siapkan(tenant_id, jam_buka="10:00", jam_tutup="20:00"):
    _setup_jam_operasional(tenant_id, jam_buka, jam_tutup)
    absensi_reminder_db.set_aktif(True, tenant_id=tenant_id)
    whatsapp_service.set_token("dummy-token", tenant_id=tenant_id)


def test_checkin_terkirim_sekali_lalu_idempoten(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    barber_id = _tambah_barber(tenant_id, "Budi")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkin_terkirim"] == 1
    assert len(terkirim) == 1
    assert "Budi" in terkirim[0]["pesan"]
    assert terkirim[0]["nomor"] == "081234567890"

    # Dipanggil lagi (simulasi cron berikutnya) -- TIDAK boleh kirim ulang.
    hasil2 = absensi_reminder_db.jalankan_pengecekan()
    assert hasil2["checkin_terkirim"] == 0
    assert len(terkirim) == 1


def test_checkin_tidak_dikirim_kalau_sudah_checkin(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    barber_id = _tambah_barber(tenant_id, "Sari")
    _insert_log(barber_id, tenant_id, _hari_ini(), check_in=True, check_out=False)
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkin_terkirim"] == 0
    assert len(terkirim) == 0


def test_checkin_tidak_dikirim_sebelum_jam_buka(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    _tambah_barber(tenant_id, "Dedi")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("09:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkin_terkirim"] == 0
    assert len(terkirim) == 0


def test_checkin_dilewati_untuk_barber_libur(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    barber_id = _tambah_barber(tenant_id, "Eko")
    db.tandai_libur(barber_id, _hari_ini())
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkin_terkirim"] == 0
    assert len(terkirim) == 0


def test_checkin_dilewati_untuk_barber_cuti_disetujui(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    barber_id = _tambah_barber(tenant_id, "Fani")
    pengajuan = izin_cuti_db.buat_pengajuan(
        barber_id, "cuti", _hari_ini(), _hari_ini(), "Acara keluarga",
        tenant_id=tenant_id, override=True,
    )
    izin_cuti_db.set_status_pengajuan(pengajuan["id"], "disetujui", disetujui_oleh="owner1")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkin_terkirim"] == 0
    assert len(terkirim) == 0


def test_checkin_dilewati_untuk_barber_izin_disetujui(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    barber_id = _tambah_barber(tenant_id, "Gita")
    pengajuan = izin_cuti_db.buat_pengajuan(
        barber_id, "izin", _hari_ini(), _hari_ini(), "Sakit",
        tenant_id=tenant_id, override=True,
    )
    izin_cuti_db.set_status_pengajuan(pengajuan["id"], "disetujui", disetujui_oleh="owner1")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkin_terkirim"] == 0
    assert len(terkirim) == 0


def test_checkin_dilewati_tanpa_nomor_whatsapp(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    _tambah_barber(tenant_id, "Hadi", nomor_whatsapp="")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkin_terkirim"] == 0
    assert len(terkirim) == 0


def test_checkout_terkirim_sekali_untuk_yang_belum_checkout(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    barber_id = _tambah_barber(tenant_id, "Indra")
    _insert_log(barber_id, tenant_id, _hari_ini(), check_in=True, check_out=False)
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("21:01"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkout_terkirim"] == 1
    assert len(terkirim) == 1
    assert "Indra" in terkirim[0]["pesan"]

    hasil2 = absensi_reminder_db.jalankan_pengecekan()
    assert hasil2["checkout_terkirim"] == 0
    assert len(terkirim) == 1


def test_checkout_tidak_dikirim_kalau_sudah_checkout(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    barber_id = _tambah_barber(tenant_id, "Joko")
    _insert_log(barber_id, tenant_id, _hari_ini(), check_in=True, check_out=True)
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("21:01"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkout_terkirim"] == 0
    assert len(terkirim) == 0


def test_checkout_tidak_dikirim_kalau_tidak_pernah_checkin(single_tenant, monkeypatch):
    """Belum Check In sama sekali hari itu -- itu urusan pengingat Check In,
    BUKAN Check Out (tidak ada sesi kerja yang perlu ditutup)."""
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    _tambah_barber(tenant_id, "Kiki")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("21:01"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["checkout_terkirim"] == 0
    # BUGFIX-SENSITIVE: checkin_terkirim tetap 0 di sini karena
    # lewat_jam_buka ikut True (jam_buka 10:00 sudah lama lewat pada jam
    # 21:01) -- barber ini memang belum check-in, jadi SEHARUSNYA dapat
    # pengingat Check In (bukan Check Out). Pastikan itu yang terjadi.
    assert hasil["checkin_terkirim"] == 1
    assert len(terkirim) == 1
    assert "Check In" in terkirim[0]["pesan"] or "Kiki" in terkirim[0]["pesan"]


def test_tidak_dikirim_kalau_reminder_nonaktif(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _setup_jam_operasional(tenant_id)
    whatsapp_service.set_token("dummy-token", tenant_id=tenant_id)
    # absensi_reminder_db.set_aktif() SENGAJA TIDAK dipanggil -- default nonaktif.
    _tambah_barber(tenant_id, "Lulu")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["tenant_diperiksa"] == 0
    assert len(terkirim) == 0


def test_tidak_dikirim_kalau_hari_ini_bukan_hari_operasional(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    # Kecualikan HARI INI (apa pun hari sungguhan saat test dijalankan) dari
    # hari operasional -- bukan nama hari tetap, supaya tidak rapuh.
    hari_ini_nama = booking_db.HARI_LIST[datetime.now(WIB).weekday()]
    hari_operasional = [h for h in booking_db.HARI_LIST if h != hari_ini_nama]
    booking_db.update_booking_settings(hari_operasional=hari_operasional, tenant_id=tenant_id)
    _tambah_barber(tenant_id, "Mimi")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    hasil = absensi_reminder_db.jalankan_pengecekan()
    assert hasil["tenant_diperiksa"] == 0
    assert len(terkirim) == 0


def test_template_custom_dipakai_kalau_diisi(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    _siapkan(tenant_id)
    absensi_reminder_db.set_templates({"checkin": "Woi {nama_barber}, cepetan check in di {toko}!"},
                                       tenant_id=tenant_id)
    _tambah_barber(tenant_id, "Nina")
    terkirim = _mock_wa(monkeypatch)
    _patch_now(monkeypatch, _jam("11:00"))

    absensi_reminder_db.jalankan_pengecekan()
    assert len(terkirim) == 1
    assert terkirim[0]["pesan"].startswith("Woi Nina, cepetan check in di")


# ---------------------------------------------------------------------------
# Endpoint GET/PUT /api/pengaturan/absensi-reminder (setting per tenant)
# ---------------------------------------------------------------------------

def test_endpoint_pengaturan_absensi_reminder_get_default(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/pengaturan/absensi-reminder", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["aktif"] is False
    assert data["templates"]["checkin"] == ""
    assert "checkout" in data["defaults"]


def test_endpoint_pengaturan_absensi_reminder_put_aktif_dan_template(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.put("/api/pengaturan/absensi-reminder", json={
        "aktif": True, "templates": {"checkin": "Custom check in", "checkout": "Custom check out"},
    }, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["aktif"] is True
    assert data["templates"]["checkin"] == "Custom check in"
    assert data["templates"]["checkout"] == "Custom check out"


# ---------------------------------------------------------------------------
# Endpoint POST/PUT /api/pengaturan/barber -- field nomor_whatsapp
# ---------------------------------------------------------------------------

def test_endpoint_barber_simpan_dan_edit_nomor_whatsapp(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.post("/api/pengaturan/barber", json={
        "nama": "Oscar", "nomor_whatsapp": "081211112222",
    }, headers=headers)
    assert r.status_code == 200, r.text
    barber = r.json()
    assert barber["nomor_whatsapp"] == "081211112222"

    r2 = client.put(f"/api/pengaturan/barber/{barber['id']}", json={
        "nomor_whatsapp": "081299998888",
    }, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["nomor_whatsapp"] == "081299998888"


# ---------------------------------------------------------------------------
# Endpoint POST /api/cron/absensi-reminder -- pemicu eksternal
# ---------------------------------------------------------------------------

def test_cron_endpoint_menolak_tanpa_secret_cocok(single_tenant, monkeypatch):
    from routers import cron_reminder
    monkeypatch.setattr(cron_reminder, "_SECRET", "rahasia-123")
    r = single_tenant["client"].post("/api/cron/absensi-reminder")
    assert r.status_code == 403
    r2 = single_tenant["client"].post("/api/cron/absensi-reminder", headers={"X-Cron-Secret": "salah"})
    assert r2.status_code == 403


def test_cron_endpoint_menolak_total_kalau_secret_belum_dikonfigurasi(single_tenant, monkeypatch):
    from routers import cron_reminder
    monkeypatch.setattr(cron_reminder, "_SECRET", "")
    r = single_tenant["client"].post("/api/cron/absensi-reminder", headers={"X-Cron-Secret": "apa-saja"})
    assert r.status_code == 403


def test_cron_endpoint_sukses_dengan_secret_benar(single_tenant, monkeypatch):
    from routers import cron_reminder
    monkeypatch.setattr(cron_reminder, "_SECRET", "rahasia-123")
    dipanggil = {}

    def _fake_pengecekan():
        dipanggil["ya"] = True
        return {"tenant_diperiksa": 0, "checkin_terkirim": 0, "checkout_terkirim": 0}

    monkeypatch.setattr(absensi_reminder_db, "jalankan_pengecekan", _fake_pengecekan)
    r = single_tenant["client"].post("/api/cron/absensi-reminder", headers={"X-Cron-Secret": "rahasia-123"})
    assert r.status_code == 200, r.text
    assert dipanggil.get("ya") is True
    assert r.json() == {"tenant_diperiksa": 0, "checkin_terkirim": 0, "checkout_terkirim": 0}
