"""test_whatsapp_bot.py — FITUR WA Bot (Input Data & Rekap via WhatsApp)
=============================================================================
Cakupan: whatsapp_bot_db.py (CRUD config + kuota live-computed) dan
routers/whatsapp_bot.py (webhook publik Fonnte + endpoint Superadmin).
Lihat whatsapp_bot_db.py untuk arsitektur lengkap (provider Fonnte,
device_token per tenant, dibedakan lewat phone_number_id (nomor device
Fonnte), dikelola EKSKLUSIF Superadmin)."""

import auth_db
import whatsapp_bot_db as wb_db
from routers import whatsapp_bot


def _superadmin_headers(client, username="superadmin_wa", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------------------------------------------------------------------------
# whatsapp_bot_db.py -- unit (tanpa HTTP)
# ---------------------------------------------------------------------------

def test_upsert_config_default_nonaktif(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    config = wb_db.upsert_config(tenant_id, "123456", "token-abc", nama_nomor="Nomor Test")
    assert config["aktif"] is False
    assert config["phone_number_id"] == "123456"
    assert config["device_token"] == "token-abc"
    assert config["kuota_pesan_bulanan"] == wb_db.DEFAULT_KUOTA_PESAN_BULANAN


def test_upsert_config_nomor_kosong_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        wb_db.upsert_config(tenant_id, "   ", "token-abc")
        assert False, "Seharusnya ValueError"
    except ValueError as e:
        assert "Nomor device" in str(e)


def test_upsert_config_token_kosong_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        wb_db.upsert_config(tenant_id, "123456", "   ")
        assert False, "Seharusnya ValueError"
    except ValueError as e:
        assert "Device Token" in str(e)


def test_upsert_config_kuota_negatif_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        wb_db.upsert_config(tenant_id, "123456", "token-abc", kuota_pesan_bulanan=-1)
        assert False, "Seharusnya ValueError"
    except ValueError:
        pass


def test_upsert_config_dipanggil_lagi_mengubah_baris_yang_sama(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "123456", "token-lama")
    kedua = wb_db.upsert_config(tenant_id, "999999", "token-baru", kuota_pesan_bulanan=20)
    assert kedua["phone_number_id"] == "999999"
    assert kedua["device_token"] == "token-baru"
    assert kedua["kuota_pesan_bulanan"] == 20
    assert len(wb_db.list_config()) == 1  # bukan baris baru


def test_set_aktif_tanpa_config_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    try:
        wb_db.set_aktif(tenant_id, True)
        assert False, "Seharusnya ValueError"
    except ValueError as e:
        assert "belum punya konfigurasi" in str(e)


def test_set_aktif_toggle(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "123456", "token-abc")
    diaktifkan = wb_db.set_aktif(tenant_id, True)
    assert diaktifkan["aktif"] is True
    dinonaktifkan = wb_db.set_aktif(tenant_id, False)
    assert dinonaktifkan["aktif"] is False


def test_get_config_by_phone_number_id_hanya_yang_aktif(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "123456", "token-abc")
    assert wb_db.get_config_by_phone_number_id("123456") is None  # belum diaktifkan
    wb_db.set_aktif(tenant_id, True)
    ditemukan = wb_db.get_config_by_phone_number_id("123456")
    assert ditemukan is not None
    assert ditemukan["tenant_id"] == tenant_id


def test_get_config_by_phone_number_id_tidak_terdaftar(single_tenant):
    assert wb_db.get_config_by_phone_number_id("tidak-ada") is None


def test_hapus_config(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "123456", "token-abc")
    wb_db.hapus_config(tenant_id)
    assert wb_db.get_config(tenant_id) is None


def test_cek_kuota_default_belum_ada_config(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    hasil = wb_db.cek_kuota(tenant_id)
    assert hasil == {"kuota": wb_db.DEFAULT_KUOTA_PESAN_BULANAN, "terpakai": 0,
                      "sisa": wb_db.DEFAULT_KUOTA_PESAN_BULANAN, "habis": False}


def test_cek_kuota_terpakai_dan_habis(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "123456", "token-abc", kuota_pesan_bulanan=2)
    wb_db.catat_pesan(tenant_id, "6281234567890", "Halo", "diproses")
    hasil1 = wb_db.cek_kuota(tenant_id)
    assert hasil1 == {"kuota": 2, "terpakai": 1, "sisa": 1, "habis": False}

    wb_db.catat_pesan(tenant_id, "6281234567890", "Halo lagi", "diproses")
    hasil2 = wb_db.cek_kuota(tenant_id)
    assert hasil2 == {"kuota": 2, "terpakai": 2, "sisa": 0, "habis": True}


def test_catat_pesan_status_selain_diproses_tidak_dihitung_kuota(single_tenant):
    """`ditolak_kuota` sendiri TIDAK ikut menambah hitungan kuota terpakai --
    mencegah efek bola salju (pesan yang DITOLAK karena kuota habis tidak
    boleh ikut "menghabiskan" kuota lagi)."""
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "123456", "token-abc", kuota_pesan_bulanan=1)
    wb_db.catat_pesan(tenant_id, "628111", "Halo", "diproses")
    wb_db.catat_pesan(tenant_id, "628111", "Halo lagi", "ditolak_kuota")
    assert wb_db.kuota_terpakai_bulan_ini(tenant_id) == 1


# ---------------------------------------------------------------------------
# POST /api/whatsapp-bot/webhook/{secret} -- pesan masuk Fonnte
# ---------------------------------------------------------------------------

def _url(secret: str = "secret-rahasia") -> str:
    return f"/api/whatsapp-bot/webhook/{secret}"


def test_webhook_post_secret_salah_ditolak_403(single_tenant, monkeypatch):
    monkeypatch.setattr(whatsapp_bot, "_WEBHOOK_SECRET", "secret-rahasia")
    r = single_tenant["client"].post(_url("secret-ngawur"),
                                      data={"device": "pnid-1", "sender": "6281111", "message": "Halo"})
    assert r.status_code == 403


def test_webhook_post_belum_dikonfigurasi_menolak_total(single_tenant, monkeypatch):
    monkeypatch.setattr(whatsapp_bot, "_WEBHOOK_SECRET", "")
    r = single_tenant["client"].post(_url("apa-saja"),
                                      data={"device": "pnid-1", "sender": "6281111", "message": "Halo"})
    assert r.status_code == 403


def test_webhook_post_nomor_tidak_terdaftar_diabaikan(single_tenant, monkeypatch):
    monkeypatch.setattr(whatsapp_bot, "_WEBHOOK_SECRET", "secret-rahasia")
    client = single_tenant["client"]
    r = client.post(_url(), data={"device": "tidak-ada", "sender": "6281111", "message": "Halo"})
    assert r.status_code == 200, r.text  # selalu 200 untuk payload sah yang diabaikan


def test_webhook_post_pesan_diproses_dan_tercatat(single_tenant, monkeypatch):
    monkeypatch.setattr(whatsapp_bot, "_WEBHOOK_SECRET", "secret-rahasia")
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "pnid-1", "token-1")
    wb_db.set_aktif(tenant_id, True)

    client = single_tenant["client"]
    r = client.post(_url(), data={"device": "pnid-1", "sender": "6281111", "message": "Halo"})
    assert r.status_code == 200, r.text
    assert wb_db.kuota_terpakai_bulan_ini(tenant_id) == 1


def test_webhook_post_tenant_nonaktif_diabaikan(single_tenant, monkeypatch):
    monkeypatch.setattr(whatsapp_bot, "_WEBHOOK_SECRET", "secret-rahasia")
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "pnid-2", "token-2")  # TIDAK diaktifkan

    client = single_tenant["client"]
    r = client.post(_url(), data={"device": "pnid-2", "sender": "6281111", "message": "Halo"})
    assert r.status_code == 200, r.text
    assert wb_db.kuota_terpakai_bulan_ini(tenant_id) == 0


def test_webhook_post_kuota_habis_ditolak(single_tenant, monkeypatch):
    monkeypatch.setattr(whatsapp_bot, "_WEBHOOK_SECRET", "secret-rahasia")
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "pnid-3", "token-3", kuota_pesan_bulanan=1)
    wb_db.set_aktif(tenant_id, True)

    client = single_tenant["client"]
    client.post(_url(), data={"device": "pnid-3", "sender": "6281111", "message": "Pesan 1"})
    r2 = client.post(_url(), data={"device": "pnid-3", "sender": "6281111", "message": "Pesan 2"})
    assert r2.status_code == 200, r2.text
    assert wb_db.kuota_terpakai_bulan_ini(tenant_id) == 1  # pesan ke-2 DITOLAK, tidak ikut terhitung


def test_webhook_post_payload_tanpa_sender_diabaikan(single_tenant, monkeypatch):
    """Payload event lain dari Fonnte yang tidak membawa field sender/device
    yang dikenali -- harus diabaikan tanpa error, bukan dianggap pesan masuk."""
    monkeypatch.setattr(whatsapp_bot, "_WEBHOOK_SECRET", "secret-rahasia")
    tenant_id = single_tenant["tenant_id"]
    wb_db.upsert_config(tenant_id, "pnid-4", "token-4")
    wb_db.set_aktif(tenant_id, True)

    r = single_tenant["client"].post(_url(), data={"status": "device_connected"})
    assert r.status_code == 200, r.text
    assert wb_db.kuota_terpakai_bulan_ini(tenant_id) == 0


# ---------------------------------------------------------------------------
# Superadmin -- /api/superadmin/whatsapp-bot/*
# ---------------------------------------------------------------------------

def test_superadmin_list_menyertakan_tenant_tanpa_config(single_tenant):
    client = single_tenant["client"]
    headers = _superadmin_headers(client)
    r = client.get("/api/superadmin/whatsapp-bot", headers=headers)
    assert r.status_code == 200, r.text
    baris = next(b for b in r.json() if b["tenant_id"] == single_tenant["tenant_id"])
    assert baris["config"] is None


def test_superadmin_atur_lalu_aktifkan(single_tenant):
    client = single_tenant["client"]
    headers = _superadmin_headers(client)
    tenant_id = single_tenant["tenant_id"]

    r1 = client.put(f"/api/superadmin/whatsapp-bot/{tenant_id}", headers=headers,
                     json={"phone_number_id": "pnid-super", "device_token": "token-super",
                           "nama_nomor": "Mugen", "kuota_pesan_bulanan": 30})
    assert r1.status_code == 200, r1.text
    assert r1.json()["aktif"] is False

    r2 = client.put(f"/api/superadmin/whatsapp-bot/{tenant_id}/status", headers=headers, json={"aktif": True})
    assert r2.status_code == 200, r2.text
    assert r2.json()["aktif"] is True

    r3 = client.get("/api/superadmin/whatsapp-bot", headers=headers)
    baris = next(b for b in r3.json() if b["tenant_id"] == tenant_id)
    assert baris["config"]["phone_number_id"] == "pnid-super"
    assert baris["config"]["device_token"] == "token-super"
    assert baris["config"]["aktif"] is True


def test_superadmin_atur_tanpa_token_ditolak_422(single_tenant):
    client = single_tenant["client"]
    headers = _superadmin_headers(client)
    tenant_id = single_tenant["tenant_id"]
    r = client.put(f"/api/superadmin/whatsapp-bot/{tenant_id}", headers=headers,
                    json={"phone_number_id": "pnid-x", "device_token": "   "})
    assert r.status_code == 422


def test_superadmin_hapus_konfigurasi(single_tenant):
    client = single_tenant["client"]
    headers = _superadmin_headers(client)
    tenant_id = single_tenant["tenant_id"]
    client.put(f"/api/superadmin/whatsapp-bot/{tenant_id}", headers=headers,
               json={"phone_number_id": "pnid-x", "device_token": "token-x"})
    r = client.delete(f"/api/superadmin/whatsapp-bot/{tenant_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert wb_db.get_config(tenant_id) is None


def test_superadmin_tenant_tidak_ditemukan_404(single_tenant):
    client = single_tenant["client"]
    headers = _superadmin_headers(client)
    r = client.put("/api/superadmin/whatsapp-bot/999999", headers=headers,
                    json={"phone_number_id": "pnid-y", "device_token": "token-y"})
    assert r.status_code == 404


def test_akun_tenant_biasa_ditolak_endpoint_superadmin(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/superadmin/whatsapp-bot", headers=headers)
    assert r.status_code == 403
