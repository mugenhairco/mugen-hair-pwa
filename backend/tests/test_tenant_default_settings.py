"""
test_tenant_default_settings.py — BUGFIX: tenant baru tidak pernah dapat
default settings (persentase_komisi dkk selalu diam-diam 0)
=============================================================================
Ditemukan lewat laporan Komisi selalu Rp 0 di Rekap Transaksi/Bulanan &
Dashboard Barber. Akar masalah: tenant_db.buat_tenant() (dipakai KEDUA
jalur pembuatan tenant -- routers/tenant_registration.py registrasi
mandiri dan routers/superadmin.py provisioning manual) sebelumnya hanya
membuat baris `tenants` itu sendiri, tidak pernah men-seed satu setting
pun -- database.py::get_setting()/_setting_float() lalu diam-diam fallback
ke "0" (BUKAN nilai default pabrik seperti persentase_komisi 40%).

Dua lapis perbaikan diverifikasi di sini:
1. tenant_db.buat_tenant() sekarang men-seed DEFAULT_SETTINGS LANGSUNG saat
   tenant baru dibuat.
2. tenant_migrasi.py::_backfill_default_settings_semua_tenant() (jalan
   tiap boot lewat migrasi_tenant()) mem-backfill tenant yang SUDAH
   TERLANJUR ada sebelum perbaikan #1 dipasang -- aman & idempotent, TIDAK
   PERNAH menimpa setting yang sudah eksplisit diisi/diubah Owner."""

import database as db
import tenant_db
import tenant_migrasi


def test_buat_tenant_langsung_seed_default_settings(app_client):
    tenant_id = tenant_db.buat_tenant("toko-baru-seed", "Toko Baru Seed")
    assert db._setting_float("persentase_komisi", tenant_id=tenant_id) == 40.0
    assert db._setting_float("target_bonus_customer", tenant_id=tenant_id) == 60.0
    assert db._setting_float("nominal_bonus_customer", tenant_id=tenant_id) == 150000.0


def test_hitung_komisi_service_tidak_nol_untuk_tenant_baru(app_client):
    """Regresi langsung dari laporan bug: transaksi normal (harga > modal)
    untuk tenant BARU harus menghasilkan komisi > 0, bukan diam-diam 0."""
    tenant_id = tenant_db.buat_tenant("toko-baru-komisi", "Toko Baru Komisi")
    komisi = db.hitung_komisi_service(100000, 0, tenant_id=tenant_id)
    assert komisi == 40000  # 40% dari 100000


def test_backfill_memperbaiki_tenant_lama_tanpa_settings(app_client):
    """Simulasikan tenant "korban" yang dibuat SEBELUM perbaikan ini
    dipasang (baris `tenants` polos tanpa satu pun baris settings
    ber-prefix, lewat SQL langsung -- BUKAN tenant_db.buat_tenant() yang
    sudah diperbaiki) -- boot BERIKUTNYA (migrasi_tenant() dipanggil ulang,
    sama seperti restart proses produksi) harus otomatis mem-backfill-nya."""
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tenants (slug, nama_barbershop, status, created_at) VALUES (?, ?, 'aktif', ?)",
            ("korban-lama", "Toko Korban Lama", "2026-01-01T00:00:00"),
        )
        korban_id = cur.lastrowid

    assert db._setting_float("persentase_komisi", tenant_id=korban_id) == 0.0  # kondisi bug

    tenant_migrasi.migrasi_tenant()  # simulasi boot berikutnya

    assert db._setting_float("persentase_komisi", tenant_id=korban_id) == 40.0
    assert db._setting_float("target_bonus_customer", tenant_id=korban_id) == 60.0


def test_backfill_tidak_menimpa_setting_yang_sudah_dikustomisasi(single_tenant):
    """Jaminan paling penting dari backfill ini: Owner yang SUDAH mengubah
    persentase_komisi (termasuk ke nilai yang "kebetulan" sama dengan
    fallback lama, 0) TIDAK BOLEH diam-diam dikembalikan ke nilai pabrik."""
    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "77", tenant_id=tenant_id)

    tenant_migrasi.migrasi_tenant()  # backfill jalan lagi, TIDAK boleh menimpa

    assert db._setting_float("persentase_komisi", tenant_id=tenant_id) == 77.0
