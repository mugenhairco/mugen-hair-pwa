"""test_izin_cuti_migrasi.py — REVISI Sistem Dinamis Cuti & Izin: migrasi
kolom settings baru + seed saldo awal Agustus 2026 (izin_cuti_migrasi.py)
=============================================================================
Cakupan: seed_konfigurasi_awal_agustus_2026() -- SEKALI SAJA, HANYA tenant
yang punya PERSIS kelima nama karyawan (Jack/Roma/Rafik/Rendi/Mifta)
sekaligus, idempotent, tidak pernah menimpa pengaturan yang sudah diubah
Owner, tidak ambigu antar-tenant."""

import database as db
import izin_cuti_db
import izin_cuti_migrasi
import tenant_db

_NAMA_LIMA_KARYAWAN = ["Jack", "Roma", "Rafik", "Rendi", "Mifta"]
_SALDO_HARAPAN = {"jack": 5, "roma": 3, "rafik": 7, "rendi": 0, "mifta": 0}


def _buat_tenant_dengan_lima_karyawan(slug, nama_toko, nama_karyawan=None):
    tenant_id = tenant_db.buat_tenant(slug, nama_toko)
    for nama in (nama_karyawan or _NAMA_LIMA_KARYAWAN):
        db.add_barber(nama, tenant_id=tenant_id)
    return tenant_id


def test_seed_tidak_berjalan_tanpa_kelima_nama_karyawan(app_client):
    tenant_id = tenant_db.buat_tenant("test-tanpa-lima", "Toko Tanpa Lima")
    db.add_barber("Jack", tenant_id=tenant_id)
    db.add_barber("Roma", tenant_id=tenant_id)
    # HANYA 2 dari 5 nama -- seed HARUS dilewati.
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()
    assert izin_cuti_db.get_saldo_awal(tenant_id) == []
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    assert settings["kuota_periode_bulan"] == 0
    assert settings["periode_mulai_dasar"] is None


def test_seed_berjalan_dengan_kelima_nama_karyawan_persis(app_client):
    tenant_id = _buat_tenant_dengan_lima_karyawan("test-lima-persis", "Toko Lima Persis")
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()

    saldo = izin_cuti_db.get_saldo_awal(tenant_id)
    assert len(saldo) == 5
    per_nama = {s["nama_barber"].lower(): s for s in saldo}
    for nama, saldo_harapan in _SALDO_HARAPAN.items():
        assert per_nama[nama]["saldo_hari"] == saldo_harapan
        assert per_nama[nama]["berlaku_sampai"] == "2026-08-31"
        assert per_nama[nama]["jenis"] == "cuti"

    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    assert settings["kuota_periode_bulan"] == 3
    assert settings["kuota_maksimal_hari"] == 10
    assert settings["periode_mulai_dasar"] == "2026-09-01"


def test_seed_case_insensitive_dan_trim(app_client):
    """Nama karyawan asli boleh beda kapitalisasi/spasi -- pencocokan tetap
    berhasil (case-insensitive + trim)."""
    tenant_id = _buat_tenant_dengan_lima_karyawan(
        "test-lima-variasi", "Toko Lima Variasi",
        nama_karyawan=[" JACK ", "roma", "Rafik", "  Rendi", "MIFTA  "],
    )
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()
    saldo = izin_cuti_db.get_saldo_awal(tenant_id)
    assert len(saldo) == 5


def test_seed_idempotent_tidak_duplikat_saat_dipanggil_ulang(app_client):
    tenant_id = _buat_tenant_dengan_lima_karyawan("test-lima-idem", "Toko Lima Idem")
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()
    assert len(izin_cuti_db.get_saldo_awal(tenant_id)) == 5


def test_cari_tenant_ambigu_dua_tenant_return_none():
    """Unit test langsung ke _cari_tenant_seed_awal() (BUKAN lewat
    add_barber()/DB sungguhan) -- tabel `barbers.nama` di aplikasi ini
    punya UNIQUE constraint GLOBAL (bukan per-tenant, lihat database.py),
    jadi skenario "2 tenant sama-sama punya nama Jack/Roma/dst" TIDAK
    PERNAH bisa terjadi lewat jalur normal aplikasi -- tapi fungsi
    pencocokan tenant di izin_cuti_migrasi.py tetap ditulis defensif untuk
    kasus itu (mis. kalau constraint-nya suatu saat dilonggarkan). Diuji
    langsung lewat objek tiruan minimal supaya tidak bentrok dengan
    constraint tersebut."""

    class _KoneksiTiruan:
        def execute(self, query, params=()):
            return self

        def fetchall(self):
            return [{"tenant_id": tid, "nama_norm": nama.lower()}
                    for tid in (101, 102) for nama in _NAMA_LIMA_KARYAWAN]

    assert izin_cuti_migrasi._cari_tenant_seed_awal(_KoneksiTiruan()) is None


def test_seed_tidak_menimpa_pengaturan_yang_sudah_diubah_owner(app_client):
    """Owner sudah mengatur sendiri kuota periode SEBELUM seed sempat
    jalan (mis. server pernah restart di antara deploy) -- seed TIDAK
    BOLEH menimpa pengaturan Owner ini."""
    tenant_id = _buat_tenant_dengan_lima_karyawan("test-sudah-diatur", "Toko Sudah Diatur")
    izin_cuti_db.set_cuti_settings(tenant_id, kuota_periode_bulan=6, kuota_maksimal_hari=12,
                                    periode_mulai_dasar="2026-01-01")
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()
    settings = izin_cuti_db.get_cuti_settings(tenant_id)
    assert settings["kuota_periode_bulan"] == 6
    assert settings["kuota_maksimal_hari"] == 12
    assert settings["periode_mulai_dasar"] == "2026-01-01"
    # Saldo awal (bagian TERPISAH dari konfigurasi periode) tetap dicatat.
    assert len(izin_cuti_db.get_saldo_awal(tenant_id)) == 5


def test_seed_tidak_menyentuh_tenant_lain_yang_tidak_cocok(app_client):
    tenant_cocok = _buat_tenant_dengan_lima_karyawan("test-cocok", "Toko Cocok")
    tenant_lain = tenant_db.buat_tenant("test-tidak-cocok", "Toko Tidak Cocok")
    db.add_barber("Budi", tenant_id=tenant_lain)
    db.add_barber("Andi", tenant_id=tenant_lain)
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()
    assert len(izin_cuti_db.get_saldo_awal(tenant_cocok)) == 5
    assert izin_cuti_db.get_saldo_awal(tenant_lain) == []
    settings_lain = izin_cuti_db.get_cuti_settings(tenant_lain)
    assert settings_lain["kuota_periode_bulan"] == 0


def test_router_saldo_awal_barber_hanya_lihat_miliknya(app_client):
    """GET /api/izin-cuti/saldo-awal -- barber HANYA boleh lihat miliknya
    sendiri, admin boleh lihat semua."""
    import auth_db

    tenant_id = _buat_tenant_dengan_lima_karyawan("test-router-saldo-awal", "Toko Router Saldo Awal")
    izin_cuti_migrasi.seed_konfigurasi_awal_agustus_2026()
    auth_db.tambah_user("ownersaldo", "passwordS123", role="admin", tenant_id=tenant_id)
    r_login = app_client.post("/api/auth/login", json={"username": "ownersaldo", "password": "passwordS123"})
    headers = {"Authorization": f"Bearer {r_login.json()['token']}"}

    r_admin = app_client.get("/api/izin-cuti/saldo-awal", headers=headers)
    assert r_admin.status_code == 200
    assert len(r_admin.json()) == 5

    jack_id = next(b["id"] for b in db.get_barbers(tenant_id=tenant_id) if b["nama"] == "Jack")
    auth_db.tambah_user("jackbarber", "passwordJ123", role="barber", barber_id=jack_id, tenant_id=tenant_id)
    r_login_jack = app_client.post("/api/auth/login", json={"username": "jackbarber", "password": "passwordJ123"})
    headers_jack = {"Authorization": f"Bearer {r_login_jack.json()['token']}"}
    r_jack = app_client.get("/api/izin-cuti/saldo-awal", headers=headers_jack)
    assert r_jack.status_code == 200
    assert len(r_jack.json()) == 1
    assert r_jack.json()[0]["saldo_hari"] == 5
