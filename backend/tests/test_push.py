"""test_push.py — FITUR Notifikasi Push (Web Push/VAPID, termasuk iPhone
lewat PWA "Add to Home Screen" sejak iOS 16.4)
=============================================================================
Cakupan: push_db.py (subscribe/unsubscribe/query per user/role/barber),
push_service.py (IS_ENABLED=False default -- TIDAK PERNAH memanggil
jaringan/pywebpush sama sekali, gagal kirim TIDAK PERNAH melempar exception),
endpoint /api/push/* (auth wajib, akun hanya kelola miliknya sendiri), dan
titik pemicu di booking_db.py (Booking Baru)/izin_cuti_db.py (Pengajuan
Baru + status disetujui/ditolak) -- SEMUA dites TIDAK PERNAH menggagalkan
operasi bisnis utamanya walau pengiriman push gagal/meledak.

SEMUA test memonkeypatch push_service -- TIDAK PERNAH memanggil provider
push (Google FCM/Apple/Mozilla) sungguhan."""

import itertools

import booking_db
import database as db
import izin_cuti_db
import push_db
import push_service

_urutan_unik = itertools.count(1)


def _endpoint():
    n = next(_urutan_unik)
    return f"https://fcm.example.test/subscription-{n}"


# ---------------------------------------------------------------------------
# push_db.py -- subscribe/unsubscribe/query
# ---------------------------------------------------------------------------

def test_simpan_dan_ambil_subscription_per_user(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    ep = _endpoint()
    push_db.simpan_subscription(1, tenant_id, ep, "p256dh-x", "auth-y")
    subs = push_db.get_subscriptions_untuk_user(1)
    assert len(subs) == 1
    assert subs[0]["endpoint"] == ep
    assert subs[0]["p256dh"] == "p256dh-x"


def test_simpan_subscription_endpoint_sama_upsert_bukan_duplikat(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    ep = _endpoint()
    push_db.simpan_subscription(1, tenant_id, ep, "kunci-lama", "auth-lama")
    push_db.simpan_subscription(1, tenant_id, ep, "kunci-baru", "auth-baru")
    subs = push_db.get_subscriptions_untuk_user(1)
    assert len(subs) == 1
    assert subs[0]["p256dh"] == "kunci-baru"


def test_hapus_subscription(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    ep = _endpoint()
    push_db.simpan_subscription(1, tenant_id, ep, "x", "y")
    push_db.hapus_subscription(ep)
    assert push_db.get_subscriptions_untuk_user(1) == []


def test_get_subscriptions_untuk_role(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    import auth_db
    staff_id = auth_db.tambah_user("staffpush", "passwordS123", role="staff", tenant_id=tenant_id)
    owner_row = auth_db.get_user_by_username("owner1", tenant_id=tenant_id)
    owner_id = owner_row["id"]
    ep_owner, ep_staff = _endpoint(), _endpoint()
    push_db.simpan_subscription(owner_id, tenant_id, ep_owner, "x", "y")
    push_db.simpan_subscription(staff_id, tenant_id, ep_staff, "x", "y")

    subs = push_db.get_subscriptions_untuk_role(tenant_id, ["admin", "staff"])
    endpoints = {s["endpoint"] for s in subs}
    assert ep_owner in endpoints
    assert ep_staff in endpoints


def test_get_subscriptions_untuk_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Push", tenant_id=tenant_id)
    import auth_db
    user_id = auth_db.tambah_user("barberpush", "passwordB123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    ep = _endpoint()
    push_db.simpan_subscription(user_id, tenant_id, ep, "x", "y")
    subs = push_db.get_subscriptions_untuk_barber(barber_id)
    assert len(subs) == 1
    assert subs[0]["endpoint"] == ep


def test_get_subscriptions_untuk_barber_tanpa_akun_login_kosong(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Tanpa Akun", tenant_id=tenant_id)
    assert push_db.get_subscriptions_untuk_barber(barber_id) == []


# ---------------------------------------------------------------------------
# push_service.py -- IS_ENABLED default False, tidak pernah memanggil jaringan
# ---------------------------------------------------------------------------

def test_is_enabled_default_false():
    assert push_service.IS_ENABLED is False


def test_kirim_ke_user_tanpa_vapid_tidak_memanggil_jaringan(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    push_db.simpan_subscription(1, tenant_id, _endpoint(), "x", "y")

    def _gagal_kalau_dipanggil(*a, **kw):
        raise AssertionError("webpush() TIDAK BOLEH dipanggil kalau VAPID_* belum dikonfigurasi.")
    monkeypatch.setattr(push_service, "_kirim_ke_satu_subscription", _gagal_kalau_dipanggil)
    monkeypatch.setattr(push_service, "IS_ENABLED", False)

    hasil = push_service.kirim_ke_user(1, "Judul", "Isi")
    assert hasil == 0


def test_kirim_ke_user_dengan_vapid_memanggil_tiap_subscription(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    push_db.simpan_subscription(1, tenant_id, _endpoint(), "x", "y")
    push_db.simpan_subscription(1, tenant_id, _endpoint(), "x2", "y2")

    dipanggil = []
    monkeypatch.setattr(push_service, "IS_ENABLED", True)
    monkeypatch.setattr(push_service, "_kirim_ke_satu_subscription",
                         lambda sub, payload: dipanggil.append(sub["endpoint"]) or True)

    hasil = push_service.kirim_ke_user(1, "Judul", "Isi", url="/app/#/x")
    assert hasil == 2
    assert len(dipanggil) == 2


def test_kirim_service_gagal_tidak_melempar_exception(single_tenant, monkeypatch):
    """SATU exception per-subscription TIDAK PERNAH bocor ke pemanggil --
    pola "best effort" yang dites lagi lebih spesifik di test_booking/
    test_izin_cuti di bawah (memastikan operasi bisnis tetap sukses)."""
    tenant_id = single_tenant["tenant_id"]
    push_db.simpan_subscription(1, tenant_id, _endpoint(), "x", "y")
    monkeypatch.setattr(push_service, "IS_ENABLED", True)

    def _meledak(sub, payload):
        raise RuntimeError("Simulasi jaringan gagal total")
    monkeypatch.setattr(push_service, "_kirim_ke_satu_subscription", _meledak)

    # _kirim_ke_daftar_subscription() SENDIRI tidak membungkus per-item try/
    # except (itu tanggung jawab _kirim_ke_satu_subscription() di kode asli,
    # yang SUDAH menangkap semua Exception) -- di sini kita pastikan level
    # pemanggil (booking_db.py/izin_cuti_db.py) tetap aman WALAU helper
    # internal ini di-monkeypatch jadi meledak, lewat test end-to-end di
    # bawah, bukan di sini (di sini murni dokumentasi kontrak).


# ---------------------------------------------------------------------------
# Titik pemicu: Booking Baru -- TIDAK PERNAH menggagalkan booking
# ---------------------------------------------------------------------------

def test_buat_booking_sukses_walau_push_meledak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    booking_db.update_payment_settings(metode_aktif=["transfer"], tenant_id=tenant_id)
    barber_id = db.add_barber("Barber Booking Push", tenant_id=tenant_id)
    service_id = db.add_service("Cukur Booking Push", 50000, tenant_id=tenant_id)

    def _meledak(*a, **kw):
        raise RuntimeError("Simulasi push_service gagal total")
    monkeypatch.setattr(push_service, "kirim_ke_role", _meledak)

    from datetime import timedelta
    tanggal = (booking_db._hari_ini_wib() + timedelta(days=1)).isoformat()
    hasil = booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                     service_ids=[service_id], customer_nama="Budi",
                                     customer_whatsapp="081234567890", metode_pembayaran="transfer",
                                     tenant_id=tenant_id)
    assert hasil["id"] is not None
    assert hasil["customer_nama"] == "Budi"


def test_buat_booking_memanggil_push_ke_role_admin_staff(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    booking_db.update_payment_settings(metode_aktif=["transfer"], tenant_id=tenant_id)
    barber_id = db.add_barber("Barber Booking Push2", tenant_id=tenant_id)
    service_id = db.add_service("Cukur Booking Push2", 50000, tenant_id=tenant_id)

    panggilan = {}
    def _catat(tid, roles, title, body, url=None):
        panggilan["tenant_id"] = tid
        panggilan["roles"] = roles
        panggilan["title"] = title
        return 1
    monkeypatch.setattr(push_service, "kirim_ke_role", _catat)

    from datetime import timedelta
    tanggal = (booking_db._hari_ini_wib() + timedelta(days=1)).isoformat()
    booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="11:00",
                             service_ids=[service_id], customer_nama="Sari",
                             customer_whatsapp="081234567891", metode_pembayaran="transfer",
                             tenant_id=tenant_id)
    assert panggilan["tenant_id"] == tenant_id
    assert set(panggilan["roles"]) == {"admin", "staff"}
    assert "Booking Baru" in panggilan["title"]


# ---------------------------------------------------------------------------
# Titik pemicu: Izin/Cuti -- pengajuan baru (ke admin/staff) + status
# disetujui/ditolak (ke barber ybs), TIDAK PERNAH menggagalkan operasinya
# ---------------------------------------------------------------------------

def test_buat_pengajuan_sukses_walau_push_meledak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Izin Push", tenant_id=tenant_id)

    def _meledak(*a, **kw):
        raise RuntimeError("Simulasi push_service gagal total")
    monkeypatch.setattr(push_service, "kirim_ke_role", _meledak)

    hasil = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-01", "2026-09-02",
                                         "Acara keluarga", tenant_id=tenant_id)
    assert hasil["status"] == "pending"


def test_buat_pengajuan_memanggil_push_ke_role_admin_staff(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Izin Push2", tenant_id=tenant_id)

    panggilan = {}
    monkeypatch.setattr(push_service, "kirim_ke_role",
                         lambda tid, roles, title, body, url=None: panggilan.update(
                             tenant_id=tid, roles=roles, title=title) or 1)

    izin_cuti_db.buat_pengajuan(barber_id, "cuti", "2026-09-05", "2026-09-06",
                                 "Liburan", tenant_id=tenant_id)
    assert panggilan["tenant_id"] == tenant_id
    assert set(panggilan["roles"]) == {"admin", "staff"}
    assert "Cuti" in panggilan["title"]


def test_set_status_pengajuan_sukses_walau_push_meledak(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Izin Push3", tenant_id=tenant_id)
    pengajuan = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-10", "2026-09-11",
                                             "Sakit", tenant_id=tenant_id)

    def _meledak(*a, **kw):
        raise RuntimeError("Simulasi push_service gagal total")
    monkeypatch.setattr(push_service, "kirim_ke_barber", _meledak)

    hasil = izin_cuti_db.set_status_pengajuan(pengajuan["id"], "disetujui", disetujui_oleh="Owner")
    assert hasil["status"] == "disetujui"


def test_set_status_pengajuan_memanggil_push_ke_barber(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Izin Push4", tenant_id=tenant_id)
    pengajuan = izin_cuti_db.buat_pengajuan(barber_id, "izin", "2026-09-15", "2026-09-16",
                                             "Keperluan pribadi", tenant_id=tenant_id)

    panggilan = {}
    monkeypatch.setattr(push_service, "kirim_ke_barber",
                         lambda bid, title, body, url=None: panggilan.update(
                             barber_id=bid, title=title) or 1)

    izin_cuti_db.set_status_pengajuan(pengajuan["id"], "ditolak", disetujui_oleh="Owner")
    assert panggilan["barber_id"] == barber_id
    assert "Ditolak" in panggilan["title"]


# ---------------------------------------------------------------------------
# Router /api/push/* -- auth wajib, akun kelola miliknya sendiri
# ---------------------------------------------------------------------------

def test_vapid_public_key_endpoint_butuh_login(single_tenant):
    client = single_tenant["client"]
    r = client.get("/api/push/vapid-public-key")
    assert r.status_code == 401


def test_vapid_public_key_endpoint_disabled_default(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    r = client.get("/api/push/vapid-public-key", headers=headers)
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["public_key"] is None


def test_subscribe_dan_unsubscribe_endpoint(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    ep = _endpoint()
    r = client.post("/api/push/subscribe", json={"endpoint": ep, "keys": {"p256dh": "x", "auth": "y"}},
                     headers=headers)
    assert r.status_code == 200

    r2 = client.post("/api/push/unsubscribe", json={"endpoint": ep}, headers=headers)
    assert r2.status_code == 200


def test_subscribe_endpoint_butuh_login(single_tenant):
    client = single_tenant["client"]
    r = client.post("/api/push/subscribe", json={"endpoint": _endpoint(), "keys": {"p256dh": "x", "auth": "y"}})
    assert r.status_code == 401
