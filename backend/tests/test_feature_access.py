"""
test_feature_access.py — FONDASI Multi-Tenant Phase 4 lanjutan: Feature Gating per Paket
=============================================================================
Cakupan: tenant_has_feature() (unit), require_feature() melewatkan superadmin
tanpa syarat (unit langsung memanggil dependency-nya, tidak lewat HTTP --
tidak ada endpoint yang mengizinkan role superadmin DAN digerbang
require_feature sekaligus untuk diuji end-to-end), penegakan endpoint
(export_pdf lewat /api/uang-kas/pdf, salah satu dari 14 endpoint PDF yang
digerbang -- polanya identik untuk 13 lainnya; booking_online lewat
routers/booking.py), dan yang PALING PENTING: propagasi langsung (live
propagation) -- mengubah penugasan fitur lewat endpoint superadmin yang
SUDAH ADA (PUT /api/superadmin/billing/packages/{id}/features, pola sama
seperti test_billing.py) langsung berlaku di panggilan BERIKUTNYA, TANPA
restart/deploy ulang -- membuktikan feature_access.py tidak menyimpan cache
apa pun di lapisan server.

CATATAN PENTING soal fixture app_client di sini: billing_db.seed_default_
package_features() (dipanggil main.py on_startup(), lihat docstring
lengkapnya di billing_db.py) SUDAH otomatis meng-assign booking_online/
export_pdf ke KEEMPAT paket default sejak boot pertama -- supaya
instalasi lama (sebelum Feature Gating ini ada) tidak tiba-tiba kehilangan
fitur yang sebelumnya selalu menyala. Konsekuensinya: setiap test di bawah
yang ingin membuktikan skenario "paket TIDAK punya fitur ini" harus
EKSPLISIT mencabutnya dulu lewat _set_fitur_paket_persis() (BUKAN
mengasumsikan paket baru mulai kosong). "qris" TIDAK LAGI ada di katalog
sama sekali (diminta Owner -- QRIS adalah metode pembayaran inti untuk
SEMUA paket, bukan checkbox opsional)."""

import pytest

import billing_db
import feature_access
import subscription_db


@pytest.fixture(autouse=True)
def _default_barber_app_dan_absensi_aktif():
    """OVERRIDE fixture autouse SAMA PERSIS namanya di conftest.py (yang
    memonkeypatch feature_access.tenant_has_feature() supaya kode
    "barber_app"/"absensi" SELALU aktif secara default di seluruh test
    suite lain, lihat docstring lengkapnya di sana) -- file INI justru
    tempat perilaku ASLI (fail-CLOSED tanpa grandfather) kedua gate itu
    sungguhan diuji (lihat bagian "Aplikasi Barber"/"Absensi Karyawan" di
    bawah), jadi override ini SENGAJA no-op (TIDAK memonkeypatch apa pun)
    supaya tenant_has_feature() yang SUNGGUHAN berlaku untuk test di file
    ini."""
    yield


def _buat_superadmin_dan_login(client, username="superadmin1", password="rahasia123"):
    import auth_db
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _set_fitur_paket_persis(client, headers, package_kode: str, *fitur_kodes):
    """Pola sama persis seperti test_billing.py::test_superadmin_centang_fitur_untuk_paket
    -- lewat endpoint HTTP superadmin sungguhan (bukan panggil billing_db
    langsung), supaya test ini juga membuktikan jalur propagasinya nyata.
    MENGGANTI SELURUH daftar fitur paket ini persis jadi `fitur_kodes` yang
    dikirim (termasuk mengosongkan total kalau dipanggil tanpa argumen) --
    dipakai untuk MENCABUT fitur real-default (lihat catatan modul di atas)
    supaya skenario "paket ini tidak punya fitur X" bisa diuji secara
    eksplisit, dan untuk MEMBERI fitur guna membuktikan propagasi langsung."""
    paket = billing_db.get_package_by_kode(package_kode)
    ids = [billing_db.get_feature_by_kode(k)["id"] for k in fitur_kodes]
    r = client.put(f"/api/superadmin/billing/packages/{paket['id']}/features", headers=headers,
                    json={"feature_ids": ids})
    assert r.status_code == 200, r.text


# ============================= tenant_has_feature() (unit) =============================

def test_tenant_tanpa_baris_subscription_tidak_punya_fitur_apa_pun(single_tenant):
    """tenant_db.buat_tenant() (dipakai fixture ini) TIDAK membuat baris
    tenant_subscriptions -- fail-CLOSED (beda dari billing_limits.py yang
    fail-open untuk limit angka), lihat docstring feature_access.py."""
    assert feature_access.tenant_has_feature(single_tenant["tenant_id"], "export_pdf") is False


def test_tenant_dengan_paket_setelah_fitur_dicabut(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    free = billing_db.get_package_by_kode("free")
    billing_db.set_package_features(free["id"], [])  # cabut fitur real-default (lihat catatan modul)
    assert feature_access.tenant_has_feature(single_tenant["tenant_id"], "export_pdf") is False


def test_tenant_dengan_paket_yang_punya_fitur(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    free = billing_db.get_package_by_kode("free")
    export_pdf = billing_db.get_feature_by_kode("export_pdf")
    billing_db.set_package_features(free["id"], [export_pdf["id"]])
    assert feature_access.tenant_has_feature(single_tenant["tenant_id"], "export_pdf") is True


# ============================= require_feature() superadmin bypass (unit) =============================

def test_require_feature_selalu_meloloskan_superadmin_walau_tanpa_tenant():
    from auth import require_feature
    dep = require_feature("export_pdf")
    user = {"role": "superadmin", "tenant_id": None, "username": "superadmin1"}
    assert dep(user=user) is user


# ============================= Endpoint PDF (export_pdf) =============================

def test_pdf_endpoint_403_upgrade_required_tanpa_fitur_export_pdf(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free")  # cabut semua fitur real-default

    r = single_tenant["client"].get("/api/uang-kas/pdf", headers=single_tenant["headers"])
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["upgrade_required"] is True
    assert detail["feature"] == "export_pdf"


def test_pdf_endpoint_sukses_setelah_fitur_diassign_lewat_superadmin_tanpa_restart(app_client):
    """Ini test propagasi langsung yang diminta plan: cabut fitur -> 403,
    assign lagi lewat endpoint superadmin yang SUDAH ADA (bukan restart/
    deploy ulang apa pun) -> panggilan BERIKUTNYA langsung 200."""
    import tenant_db
    import auth_db

    tenant_id = tenant_db.buat_tenant("test-toko-live", "Test Toko Live")
    auth_db.tambah_user("ownerlive", "passwordLive123", role="admin", tenant_id=tenant_id)
    r = app_client.post("/api/auth/login", json={"username": "ownerlive", "password": "passwordLive123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    subscription_db.create_default_subscription(tenant_id, package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(app_client)
    _set_fitur_paket_persis(app_client, superadmin_headers, "free")  # cabut semua dulu

    r1 = app_client.get("/api/uang-kas/pdf", headers=headers)
    assert r1.status_code == 403

    _set_fitur_paket_persis(app_client, superadmin_headers, "free", "export_pdf")

    r2 = app_client.get("/api/uang-kas/pdf", headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.headers["content-type"] == "application/pdf"


def test_pdf_endpoint_akun_lain_paket_lain_tidak_ikut_terpengaruh(two_tenants):
    """Cabut export_pdf dari paket tenant B saja -- tenant A (paket
    berbeda, masih punya fitur real-default bawaan) tidak ikut terpengaruh."""
    subscription_db.create_default_subscription(two_tenants["tenant_a"], package="free", status="active")
    subscription_db.create_default_subscription(two_tenants["tenant_b"], package="basic", status="active")
    superadmin_headers = _buat_superadmin_dan_login(two_tenants["client"])
    _set_fitur_paket_persis(two_tenants["client"], superadmin_headers, "basic")  # cabut semua dari basic

    ra = two_tenants["client"].get("/api/uang-kas/pdf", headers=two_tenants["headers_a"])
    assert ra.status_code == 200, ra.text  # free masih punya fitur real-default bawaan

    rb = two_tenants["client"].get("/api/uang-kas/pdf", headers=two_tenants["headers_b"])
    assert rb.status_code == 403


# ============================= Export Excel (routers/attendance.py, AUDIT "fitur hardcode di Superadmin") =============================
# export_excel BEDA dari export_pdf/booking_online (bukan _FITUR_NYATA_
# DEFAULT) -- fitur ini di-grandfather lewat billing_db.py::seed_grandfather_
# fitur_baru_digerbang() (SEKALI, ke SEMUA paket, karena sebelum audit ini
# selalu gratis untuk semua tenant), jadi tenant dengan subscription APA PUN
# otomatis sudah punya fitur ini TANPA assign manual -- beda dari log_error
# yang fail-CLOSED murni (lihat test_error_log.py).
#
# CATATAN (FITUR Feature Gating "Absensi Karyawan", ditambah belakangan):
# /api/attendance/excel SEKARANG JUGA tergerbang "absensi" di level router
# (lihat bagian "Absensi Karyawan" di bawah) SELAIN "export_excel" sendiri
# -- kedua test di bawah eksplisit meng-grant "absensi" supaya HANYA
# perilaku export_excel yang diuji di sini (isolasi), fixture autouse
# global di conftest.py TIDAK berlaku di file ini (lihat override no-op
# di atas).

def test_excel_endpoint_403_upgrade_required_tanpa_fitur_export_excel(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free", "absensi")  # HANYA absensi, TANPA export_excel

    r = single_tenant["client"].get("/api/attendance/excel", headers=single_tenant["headers"])
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["upgrade_required"] is True
    assert detail["feature"] == "export_excel"


def test_excel_endpoint_sukses_dengan_fitur_grandfather_default(single_tenant):
    """export_excel di-grandfather ke SEMUA paket sejak boot -- TIDAK perlu
    assign manual apa pun untuk skenario "menyala" (lihat catatan modul di
    atas). "absensi" TIDAK di-grandfather (fitur baru, lihat bagian
    "Absensi Karyawan" di bawah) -- WAJIB di-assign eksplisit di sini
    supaya gate router-level itu tidak ikut menolak."""
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free", "export_excel", "absensi")

    r = single_tenant["client"].get("/api/attendance/excel", headers=single_tenant["headers"])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ============================= Migrasi katalog fitur (billing_db.py, AUDIT "fitur hardcode di Superadmin") =============================

def test_hapus_fitur_tanpa_fungsi_nyata_menghapus_8_kode_dekoratif(app_client):
    """Sudah otomatis terhapus saat boot (fixture app_client memicu
    on_startup()) -- migrasi ini idempotent/sekali-jalan, di sini murni
    memverifikasi hasilnya (bukan memanggil ulang)."""
    kode_sekarang = {f["kode"] for f in billing_db.list_features()}
    assert not (set(billing_db._KODE_FITUR_TANPA_FUNGSI_NYATA) & kode_sekarang)
    for kode in billing_db._KODE_FITUR_TANPA_FUNGSI_NYATA:
        assert billing_db.get_feature_by_kode(kode) is None


def test_hapus_fitur_tanpa_fungsi_nyata_tidak_menghapus_lagi_kalau_superadmin_tambah_ulang(app_client):
    """Flag sekali-jalan -- kalau Super Admin (via akses DB langsung/masa
    depan) menambah balik salah satu kode yang sudah dihapus, memanggil
    migrasi ini lagi TIDAK BOLEH menghapusnya lagi (migrasi ini SUDAH
    tercatat selesai)."""
    now = billing_db._now()
    with billing_db.get_conn() as conn:
        conn.execute(
            "INSERT INTO subscription_features (kode, nama, deskripsi, aktif, urutan, created_at, updated_at) "
            "VALUES ('multi_cabang', 'Multi Cabang', '', 1, 99, ?, ?)", (now, now),
        )
    billing_db.hapus_fitur_tanpa_fungsi_nyata()
    assert billing_db.get_feature_by_kode("multi_cabang") is not None


def test_seed_grandfather_fitur_baru_digerbang_assign_ke_semua_paket(app_client):
    for kode in ("export_excel", "whatsapp_reminder"):
        fitur = billing_db.get_feature_by_kode(kode)
        for paket in billing_db.list_packages():
            assert fitur["id"] in {f["id"] for f in billing_db.get_package_features(paket["id"])}


def test_seed_grandfather_fitur_baru_digerbang_tidak_mengembalikan_yang_dicabut_manual(app_client):
    """Pola SAMA PERSIS seed_default_package_features() -- flag sekali-jalan
    supaya mencabut fitur ini manual lewat Superadmin TIDAK diam-diam
    dikembalikan setiap kali migrasi ini dipanggil ulang (mis. restart)."""
    free = billing_db.get_package_by_kode("free")
    billing_db.set_package_features(free["id"], [])

    billing_db.seed_grandfather_fitur_baru_digerbang()

    assert billing_db.get_package_features(free["id"]) == []


# ============================= Booking Online + QRIS (routers/booking.py) =============================

def test_public_pengaturan_booking_online_false_tanpa_fitur(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free")  # cabut semua

    r = single_tenant["client"].get("/api/public/booking/pengaturan", params={"tenant": "test-toko"})
    assert r.status_code == 200, r.text
    assert r.json() == {"booking_online": False}


def test_public_pengaturan_booking_online_true_dengan_fitur_real_default(single_tenant):
    """Fitur real-default sudah otomatis menyala sejak boot (lihat catatan
    modul) -- TIDAK perlu assign manual apa pun untuk skenario "menyala"."""
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")

    r = single_tenant["client"].get("/api/public/booking/pengaturan", params={"tenant": "test-toko"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["booking_online"] is True
    assert "jam_mulai" in data or "maksimal_hari_kedepan" in data  # payload penuh, bukan short-circuit


def test_public_buat_booking_403_tanpa_fitur_booking_online(single_tenant):
    """Lapisan pertahanan kedua -- panggilan langsung ke endpoint POST tanpa
    lewat wizard /book sekalipun (public_pengaturan sudah menyembunyikannya
    dari frontend, tapi endpoint publik ini masih bisa dipanggil langsung)."""
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free")  # cabut semua

    body = {
        "barber_id": 1, "tanggal": "2026-08-10", "jam_mulai": "10:00",
        "service_ids": [1], "customer_nama": "Budi", "customer_whatsapp": "081234567890",
        "metode_pembayaran": "tunai",
    }
    r = single_tenant["client"].post("/api/public/booking", params={"tenant": "test-toko"}, json=body)
    assert r.status_code == 403


def test_qris_endpoints_bekerja_tanpa_subscription_atau_fitur_apa_pun(single_tenant):
    """REVISI (diminta Owner): "qris" DIHAPUS dari katalog Feature Gating --
    QRIS adalah metode pembayaran INTI yang harus tersedia untuk SEMUA
    paket tanpa kecuali, bukan checkbox opsional. Endpoint QRIS (publik
    maupun Owner) sekarang HARUS tetap bekerja normal walau tenant TIDAK
    PUNYA baris subscription sama sekali (fail-closed feature lain, mis.
    booking_online, TIDAK berlaku untuk qris lagi)."""
    r_hapus = single_tenant["client"].delete("/api/booking/qris", headers=single_tenant["headers"])
    assert r_hapus.status_code == 200, r_hapus.text

    r_publik = single_tenant["client"].get("/api/public/booking/qris", params={"tenant": "test-toko"})
    # 404 di sini murni "QRIS belum diunggah" (data kosong) -- BUKAN gate
    # fitur (lihat routers/booking.py::public_qris(), tidak ada lagi
    # pengecekan tenant_has_feature untuk "qris").
    assert r_publik.status_code == 404
    assert r_publik.json()["detail"] == "QRIS belum diatur."


def test_qris_tidak_lagi_ada_di_katalog_fitur(app_client):
    """Kode "qris" DIHAPUS TOTAL dari katalog -- bukan lagi sesuatu yang
    bisa dicentang/dihapus-centang Super Admin per paket sama sekali."""
    assert billing_db.get_feature_by_kode("qris") is None


# ============================= Aplikasi Barber (barber_app, routers/auth_router.py::login()) =============================
# Diminta Owner: gate LOGIN akun ber-role 'barber' -- fail-CLOSED SEJAK
# AWAL, TIDAK ADA grandfather (beda dari export_excel/whatsapp_reminder di
# atas) -- lihat billing_db.py::_FITUR_DEFAULT. Fixture autouse global di
# conftest.py yang menganggap kode ini SELALU aktif di-override no-op di
# awal file ini (lihat fixture _default_barber_app_dan_absensi_aktif di
# atas) supaya perilaku ASLI diuji di sini.

def _buat_barber(tenant_id, username="barber1", password="passwordB123"):
    import database
    import auth_db

    barber_id = database.add_barber("Barber Test", tenant_id=tenant_id)
    auth_db.tambah_user(username, password, role="barber", barber_id=barber_id, tenant_id=tenant_id)
    return barber_id


def test_login_barber_403_tanpa_fitur_barber_app(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    _buat_barber(single_tenant["tenant_id"])

    r = single_tenant["client"].post("/api/auth/login", json={"username": "barber1", "password": "passwordB123"})
    assert r.status_code == 403
    assert "tidak tersedia" in r.json()["detail"].lower()


def test_login_barber_403_tanpa_baris_subscription_sama_sekali(single_tenant):
    """Fail-closed jaga-jaga -- tenant tanpa baris subscription apa pun
    (lihat catatan fixture single_tenant/two_tenants di conftest.py) juga
    tidak boleh meloloskan login barber."""
    _buat_barber(single_tenant["tenant_id"])

    r = single_tenant["client"].post("/api/auth/login", json={"username": "barber1", "password": "passwordB123"})
    assert r.status_code == 403


def test_login_barber_sukses_dengan_fitur_barber_app(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free", "barber_app")
    _buat_barber(single_tenant["tenant_id"])

    r = single_tenant["client"].post("/api/auth/login", json={"username": "barber1", "password": "passwordB123"})
    assert r.status_code == 200, r.text
    assert r.json()["token"]


def test_login_owner_tidak_terpengaruh_gate_barber_app(single_tenant):
    """Gate ini HANYA berlaku untuk role='barber' -- Owner (role='admin')
    TIDAK PERNAH terkena, walau paketnya sama sekali tidak punya fitur
    "barber_app" (bahkan TANPA baris subscription sekalipun, lihat fixture
    single_tenant -- login Owner sudah berhasil sejak awal fixture ini)."""
    r = single_tenant["client"].post("/api/auth/login", json={"username": "owner1", "password": "password123"})
    assert r.status_code == 200, r.text


def test_login_staff_tidak_terpengaruh_gate_barber_app(single_tenant):
    """Gate ini HANYA berlaku untuk role='barber' -- akun 'staff' (Admin)
    tidak pernah terkena walau paket tidak punya fitur "barber_app"."""
    import auth_db

    auth_db.tambah_user("staff1", "passwordS123", role="staff", tenant_id=single_tenant["tenant_id"])
    r = single_tenant["client"].post("/api/auth/login", json={"username": "staff1", "password": "passwordS123"})
    assert r.status_code == 200, r.text


# ============================= Absensi Karyawan (absensi, routers/attendance.py, SELURUH modul) =============================
# Diminta Owner: SATU gate `dependencies=[Depends(require_feature("absensi"))]`
# di level router menggerbang SELURUH endpoint /api/attendance/* sekaligus
# (Check In/Out, dashboard, riwayat, pengaturan, koreksi, export) -- fail-
# CLOSED SEJAK AWAL, TIDAK ADA grandfather, independen dari gate
# "barber_app" di atas (tenant bisa punya satu tanpa yang lain).

def test_absensi_dashboard_403_tanpa_fitur_absensi(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")

    r = single_tenant["client"].get("/api/attendance/dashboard", headers=single_tenant["headers"])
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["upgrade_required"] is True
    assert detail["feature"] == "absensi"


def test_absensi_dashboard_sukses_dengan_fitur_absensi(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free", "absensi")

    r = single_tenant["client"].get("/api/attendance/dashboard", headers=single_tenant["headers"])
    assert r.status_code == 200, r.text


def test_absensi_settings_403_tanpa_fitur_absensi(single_tenant):
    """Endpoint LAIN di router yang sama (bukan cuma /dashboard) ikut
    tergerbang -- membuktikan `dependencies=` di level router benar-benar
    menggerbang SELURUH endpoint, bukan cuma satu titik."""
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")

    r = single_tenant["client"].get("/api/attendance/settings", headers=single_tenant["headers"])
    assert r.status_code == 403


def test_absensi_checkin_barber_403_tanpa_fitur_absensi_walau_barber_app_aktif(single_tenant):
    """Kedua gate INDEPENDEN -- tenant bisa punya "barber_app" (barber
    boleh login) TANPA "absensi" (barber tetap tidak bisa Check In/Out
    sama sekali)."""
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free", "barber_app")  # HANYA barber_app
    _buat_barber(single_tenant["tenant_id"])

    r_login = single_tenant["client"].post("/api/auth/login", json={"username": "barber1", "password": "passwordB123"})
    assert r_login.status_code == 200, r_login.text
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r = single_tenant["client"].get("/api/attendance/today", headers=headers_barber)
    assert r.status_code == 403
    assert r.json()["detail"]["feature"] == "absensi"


def test_absensi_checkin_barber_sukses_dengan_barber_app_dan_absensi_aktif(single_tenant):
    subscription_db.create_default_subscription(single_tenant["tenant_id"], package="free", status="active")
    superadmin_headers = _buat_superadmin_dan_login(single_tenant["client"])
    _set_fitur_paket_persis(single_tenant["client"], superadmin_headers, "free", "barber_app", "absensi")
    _buat_barber(single_tenant["tenant_id"])

    r_login = single_tenant["client"].post("/api/auth/login", json={"username": "barber1", "password": "passwordB123"})
    assert r_login.status_code == 200, r_login.text
    headers_barber = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r = single_tenant["client"].get("/api/attendance/today", headers=headers_barber)
    assert r.status_code == 200, r.text


def test_absensi_akun_lain_paket_lain_tidak_ikut_terpengaruh(two_tenants):
    """Pola sama seperti test_pdf_endpoint_akun_lain_paket_lain_tidak_ikut_
    terpengaruh() di atas -- assign "absensi" HANYA ke paket tenant A."""
    subscription_db.create_default_subscription(two_tenants["tenant_a"], package="free", status="active")
    subscription_db.create_default_subscription(two_tenants["tenant_b"], package="basic", status="active")
    superadmin_headers = _buat_superadmin_dan_login(two_tenants["client"])
    _set_fitur_paket_persis(two_tenants["client"], superadmin_headers, "free", "absensi")

    ra = two_tenants["client"].get("/api/attendance/dashboard", headers=two_tenants["headers_a"])
    assert ra.status_code == 200, ra.text

    rb = two_tenants["client"].get("/api/attendance/dashboard", headers=two_tenants["headers_b"])
    assert rb.status_code == 403
