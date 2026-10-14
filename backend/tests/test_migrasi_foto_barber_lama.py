"""test_migrasi_foto_barber_lama.py — endpoint SEKALI-PAKAI (routers/
migrasi_foto_barber.py) yang menjalankan perkecil_foto_barber_lama.py::
jalankan_migrasi() di dalam proses backend production. Pola test IDENTIK
dengan test_absensi_reminder.py untuk cron_reminder.py (secret yang sama,
CRON_REMINDER_SECRET, dipakai lewat header X-Cron-Secret).

jalankan_migrasi() ASLI butuh DATABASE_URL Postgres + R2_* sungguhan (lihat
test_perkecil_foto_barber_lama_menolak_kalau_bukan_postgres() untuk jalur
itu, dites TANPA mock apa pun karena suite ini sendiri jalan di SQLite) --
jalur SUKSES endpoint di-mock lewat monkeypatch persis seperti
test_absensi_reminder.py menguji cron_reminder.py, supaya tidak perlu
membangun Postgres+R2 palsu hanya untuk menguji routing/otorisasi endpoint."""

import perkecil_foto_barber_lama


def test_jalankan_migrasi_menolak_kalau_bukan_postgres():
    """Suite test ini jalan di SQLite (db_compat.IS_POSTGRES=False) --
    jalankan_migrasi() HARUS menolak, bukan diam-diam jalan ke DB tes."""
    import pytest
    with pytest.raises(perkecil_foto_barber_lama.MigrasiTidakDiizinkan):
        perkecil_foto_barber_lama.jalankan_migrasi(dry_run=True)


def test_endpoint_menolak_tanpa_secret_atau_secret_salah(single_tenant, monkeypatch):
    from routers import migrasi_foto_barber
    monkeypatch.setattr(migrasi_foto_barber, "_SECRET", "rahasia-123")
    r = single_tenant["client"].post("/api/cron/perkecil-foto-barber-lama")
    assert r.status_code == 403
    r2 = single_tenant["client"].post("/api/cron/perkecil-foto-barber-lama", headers={"X-Cron-Secret": "salah"})
    assert r2.status_code == 403


def test_endpoint_menolak_total_kalau_secret_belum_dikonfigurasi(single_tenant, monkeypatch):
    from routers import migrasi_foto_barber
    monkeypatch.setattr(migrasi_foto_barber, "_SECRET", "")
    r = single_tenant["client"].post(
        "/api/cron/perkecil-foto-barber-lama", headers={"X-Cron-Secret": "apa-saja"})
    assert r.status_code == 403


def test_endpoint_balas_400_kalau_bukan_postgres_walau_secret_benar(single_tenant, monkeypatch):
    from routers import migrasi_foto_barber
    monkeypatch.setattr(migrasi_foto_barber, "_SECRET", "rahasia-123")
    r = single_tenant["client"].post(
        "/api/cron/perkecil-foto-barber-lama", headers={"X-Cron-Secret": "rahasia-123"})
    assert r.status_code == 400


def test_endpoint_sukses_dengan_secret_benar_dan_meneruskan_dry_run(single_tenant, monkeypatch):
    from routers import migrasi_foto_barber
    monkeypatch.setattr(migrasi_foto_barber, "_SECRET", "rahasia-123")

    dipanggil = {}

    def _fake_jalankan_migrasi(dry_run):
        dipanggil["dry_run"] = dry_run
        return {"dry_run": dry_run, "total_barber_punya_foto": 2, "diproses": 1,
                "dilewati": 1, "total_ukuran_lama_bytes": 1000, "total_ukuran_baru_bytes": 100,
                "hemat_persen_total": 90, "rincian": []}

    monkeypatch.setattr(migrasi_foto_barber.perkecil_foto_barber_lama, "jalankan_migrasi", _fake_jalankan_migrasi)

    r = single_tenant["client"].post(
        "/api/cron/perkecil-foto-barber-lama?dry_run=false", headers={"X-Cron-Secret": "rahasia-123"})
    assert r.status_code == 200, r.text
    assert dipanggil["dry_run"] is False
    assert r.json()["hemat_persen_total"] == 90

    r2 = single_tenant["client"].post(
        "/api/cron/perkecil-foto-barber-lama", headers={"X-Cron-Secret": "rahasia-123"})
    assert r2.status_code == 200, r2.text
    assert dipanggil["dry_run"] is True, "default dry_run HARUS True kalau query param tidak dikirim"
