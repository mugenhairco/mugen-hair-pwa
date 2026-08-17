"""
postgres_schema.py — Skema PostgreSQL LENGKAP (TAHAP migrasi Neon)
=============================================================================
HANYA dipanggil dari main.py saat DATABASE_URL diisi (db_compat.IS_POSTGRES
True) -- lihat on_startup(). Ditulis TERPISAH dari 11 file *_migrasi.py yang
sudah ada (bukan menjalankannya satu per satu di atas Postgres) karena
file-file itu isinya "ALTER TABLE" bertahap dipandu "PRAGMA table_info" --
mekanisme cek kolom KHUSUS SQLite yang tidak berlaku di PostgreSQL. Untuk
instalasi PostgreSQL yang benar-benar baru, tidak ada gunanya mereplay
sejarah 11 tahap itu satu per satu -- lebih aman & lebih sederhana membuat
LANGSUNG skema akhir (hasil gabungan seluruh migrasi itu) dalam satu langkah,
idempotent (aman dipanggil ulang tiap kali proses restart, lewat
"CREATE TABLE IF NOT EXISTS" + "ON CONFLICT DO NOTHING" -- TIDAK PERNAH
menghapus/menimpa data yang sudah ada).

Kolom & default di bawah ini disalin PERSIS dari akumulasi seluruh
database.py + auth_db.py + booking_db.py + 11 file *_migrasi.py di jalur
SQLite, supaya perilaku aplikasi di atas PostgreSQL identik dengan di atas
SQLite (lihat README bagian Migrasi PostgreSQL untuk pemetaan lengkapnya).
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta

import db_compat

# Logger BERNAMA SAMA dengan main.py ("mugen") -- basicConfig() sudah
# dipanggil di sana sebelum modul ini pernah diimpor (create_all() hanya
# dipanggil dari main.py::on_startup()), jadi logger ini otomatis memakai
# konfigurasi (format + level + output stdout) yang sama, tanpa perlu
# import main.py (hindari import siklik).
_logger = logging.getLogger("mugen")

# FONDASI Multi-Tenant Phase 1 -- SAMA PERSIS dengan tenant_migrasi.py
# (jalur SQLite), lihat file itu untuk penjelasan arsitektur lengkap.
TENANT_DEFAULT_SLUG = "mugen-hair-co"
TENANT_DEFAULT_NAMA = "MUGEN Hair Co."

DEFAULT_SETTINGS = {
    "persentase_komisi": "40",
    "potongan_modal_chemical": "15000",
    "uang_harian_barber": "50000",
    "uang_harian_rafiq": "75000",
    "bonus_kehadiran": "100000",
    "maksimal_hari_libur": "2",
    "target_bonus_customer": "60",
    "nominal_bonus_customer": "150000",
    "maksimal_hari_libur_bonus_customer": "5",
    "potongan_bonus_customer_persen": "50",
    "uang_harian_target_service_harian": "3",
}

IDENTITAS_DEFAULT = {
    "nama_barbershop": "MUGEN Hair Co.",
    "alamat": "",
    "whatsapp": "",
    "email": "",
    "instagram": "",
    "jam_operasional": "",
    "logo_filename": "",
}

DEFAULT_BOOKING_SETTINGS = {
    "booking_jam_buka": "10:00",
    "booking_jam_tutup": "20:00",
    "booking_interval_menit": "60",
    "booking_maksimal_hari_kedepan": "30",
    "booking_metode_aktif": '["transfer"]',
    "booking_qris_merchant_nama": "",
    "booking_qris_filename": "",
    "booking_bank_nama": "",
    "booking_bank_nomor_rekening": "",
    "booking_bank_nama_pemilik": "",
}

DEFAULT_SERVICES = [
    ("Dry Cut", 35000, 0),
    ("Cut & Wash", 45000, 0),
    ("Hair Do", 60000, 0),
    ("Beard Trim", 25000, 0),
    ("Wet Shave", 30000, 0),
    ("Hair Coloring", 150000, 1),
    ("Smoothing", 250000, 1),
    ("Keratin Treatment", 300000, 1),
]

# Setara satu tier dari skema lama (target_bonus_customer/nominal_bonus_customer)
# -- lihat revisi_bonus_migrasi.py::_migrasi_bonus_tiers untuk versi SQLite.
DEFAULT_BONUS_TIERS = [{"target": 60, "bonus": 150000}]

# Service acuan Bonus Service & Uang Harian default -- lihat
# bonus_service_migrasi.py untuk versi SQLite (nama yang sama persis).
_SEED_ACUAN_NAMA = ("Dry Cut", "Cut & Wash")

# PENTING -- dua jebakan db_compat._translate() yang WAJIB dihindari di
# SETIAP baris teks (termasuk komentar SQL "--") di dalam string _TABLES
# di bawah ini, karena create_all() mengeksekusinya lewat conn.execute()
# yang sama seperti query berparameter biasa:
# 1. Karakter tanda tanya literal -- _translate() tidak mengerti komentar
#    SQL, jadi tanda tanya APA PUN di luar string ber-kutip-satu akan ikut
#    diterjemahkan jadi placeholder posisi Postgres.
# 2. Text yang kebetulan berbentuk sama seperti placeholder posisi
#    Postgres (huruf 's' tepat setelah tanda persen) -- psycopg2 membaca
#    SELURUH teks query mencari pola itu untuk substitusi parameter, TIDAK
#    peduli itu ada di dalam komentar SQL atau tidak.
# KEDUANYA membuat create_all() gagal saat runtime dengan "IndexError:
# tuple index out of range" (parameter kosong tidak cukup untuk mengisi
# placeholder yang ditemukan) -- BUKAN error sintaks SQL, jadi py_compile/
# linter TIDAK PERNAH menangkapnya, hanya kelihatan saat benar-benar
# dieksekusi lewat koneksi PostgreSQL sungguhan. Baris tenant_subscriptions
# di bawah ini pernah kena KEDUA jebakan ini sekaligus (lihat riwayat git).
_TABLES = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Tahap 16: aset slot tunggal (Logo, Hero Image/Video, Foto About,
-- Background Website, QRIS) -- pindah dari disk lokal ke sini (disk lokal
-- Render Free tier TIDAK persisten, lihat README) -- lihat file_asset_db.py.
-- Tabel BARU murni, aman langsung CREATE TABLE IF NOT EXISTS (tidak ada
-- gap instalasi existing seperti kolom baru di tabel lama).
CREATE TABLE IF NOT EXISTS file_asset (
    key           TEXT PRIMARY KEY,
    filename      TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    data          BYTEA NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS barbers (
    id              SERIAL PRIMARY KEY,
    nama            TEXT NOT NULL UNIQUE,
    is_rafiq        INTEGER NOT NULL DEFAULT 0,
    aktif           INTEGER NOT NULL DEFAULT 1,
    uang_harian     INTEGER NOT NULL DEFAULT 0,
    status_booking  TEXT NOT NULL DEFAULT 'aktif',
    foto_filename   TEXT,
    urutan          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS services (
    id                      SERIAL PRIMARY KEY,
    nama                    TEXT NOT NULL UNIQUE,
    harga                   INTEGER NOT NULL,
    pakai_potongan_chemical INTEGER NOT NULL DEFAULT 0,
    aktif                   INTEGER NOT NULL DEFAULT 1,
    modal                   INTEGER NOT NULL DEFAULT 0,
    durasi_menit            INTEGER NOT NULL DEFAULT 60,
    urutan                  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transaksi (
    id          SERIAL PRIMARY KEY,
    tanggal     TEXT NOT NULL,
    barber_id   INTEGER NOT NULL REFERENCES barbers(id),
    tips        INTEGER NOT NULL DEFAULT 0,
    catatan     TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS transaksi_detail (
    id            SERIAL PRIMARY KEY,
    transaksi_id  INTEGER NOT NULL REFERENCES transaksi(id) ON DELETE CASCADE,
    service_id    INTEGER NOT NULL REFERENCES services(id),
    nama_service  TEXT NOT NULL,
    harga         INTEGER NOT NULL,
    jumlah        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS absensi_libur (
    id        SERIAL PRIMARY KEY,
    barber_id INTEGER NOT NULL REFERENCES barbers(id),
    tanggal   TEXT NOT NULL,
    UNIQUE(barber_id, tanggal)
);

CREATE TABLE IF NOT EXISTS produk (
    id           SERIAL PRIMARY KEY,
    nama         TEXT NOT NULL UNIQUE,
    aktif        INTEGER NOT NULL DEFAULT 1,
    harga_modal  INTEGER NOT NULL DEFAULT 0,
    harga_jual   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS produk_mutasi (
    id                      SERIAL PRIMARY KEY,
    produk_id               INTEGER NOT NULL REFERENCES produk(id),
    tanggal                 TEXT NOT NULL,
    tipe                    TEXT NOT NULL,
    jumlah                  INTEGER NOT NULL,
    catatan                 TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT,
    harga_modal_saat_itu    INTEGER,
    harga_jual_saat_itu     INTEGER
);

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL,
    barber_id       INTEGER REFERENCES barbers(id),
    aktif           INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    tema            TEXT NOT NULL DEFAULT 'terang',
    custom_role_id  INTEGER
);

CREATE TABLE IF NOT EXISTS bookings (
    id                  SERIAL PRIMARY KEY,
    barber_id           INTEGER NOT NULL REFERENCES barbers(id),
    tanggal             TEXT NOT NULL,
    jam_mulai           TEXT NOT NULL,
    jam_selesai         TEXT NOT NULL,
    customer_nama       TEXT NOT NULL,
    customer_whatsapp   TEXT NOT NULL,
    total_harga         INTEGER NOT NULL,
    total_durasi_menit  INTEGER NOT NULL,
    metode_pembayaran   TEXT NOT NULL,
    status_pembayaran   TEXT NOT NULL DEFAULT 'menunggu_verifikasi',
    status_booking      TEXT NOT NULL DEFAULT 'aktif',
    catatan             TEXT,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS booking_items (
    id            SERIAL PRIMARY KEY,
    booking_id    INTEGER NOT NULL REFERENCES bookings(id),
    service_id    INTEGER NOT NULL REFERENCES services(id),
    nama_service  TEXT NOT NULL,
    harga         INTEGER NOT NULL,
    durasi_menit  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS closed_slot (
    id          SERIAL PRIMARY KEY,
    barber_id   INTEGER NOT NULL REFERENCES barbers(id),
    tanggal     TEXT NOT NULL,
    jam_mulai   TEXT NOT NULL,
    jam_selesai TEXT NOT NULL,
    keterangan  TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS toko_libur (
    id          SERIAL PRIMARY KEY,
    tanggal     TEXT NOT NULL UNIQUE,
    keterangan  TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS website_gallery (
    id          SERIAL PRIMARY KEY,
    filename    TEXT NOT NULL,
    urutan      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- Tahap 16: isi foto Gallery (BLOB) pindah dari disk lokal ke sini (disk
-- lokal Render Free tier TIDAK persisten).
ALTER TABLE website_gallery ADD COLUMN IF NOT EXISTS data BYTEA;

-- Gallery bisa diisi video (format apa saja, sama seperti Hero Video)
-- selain foto -- baris lama otomatis 'foto' (DEFAULT).
ALTER TABLE website_gallery ADD COLUMN IF NOT EXISTS tipe TEXT NOT NULL DEFAULT 'foto';

-- Modul Karyawan (Fase 1): Slip Gaji Otomatis. gaji_pokok lewat ALTER TABLE
-- terpisah (BUKAN dibakukan ke blok CREATE TABLE barbers di atas) supaya
-- instalasi Postgres yang SUDAH ADA (tabel barbers sudah lama berdiri,
-- CREATE TABLE IF NOT EXISTS jadi no-op untuknya) tetap kebagian kolom baru
-- ini -- PostgreSQL punya ADD COLUMN IF NOT EXISTS asli, jadi idempoten
-- tanpa perlu trik PRAGMA table_info seperti jalur SQLite.
ALTER TABLE barbers ADD COLUMN IF NOT EXISTS gaji_pokok INTEGER NOT NULL DEFAULT 0;

-- Karyawan Non-Barber (Kasir/OB/Kru): generalisasi tabel barbers lewat
-- kolom jabatan (default 'barber' -- baris lama otomatis kompatibel) +
-- gaji_per_hari (hanya relevan non-barber, lihat karyawan_migrasi.py
-- untuk penjelasan lengkap & pasangan jalur SQLite-nya).
ALTER TABLE barbers ADD COLUMN IF NOT EXISTS jabatan TEXT NOT NULL DEFAULT 'barber';
ALTER TABLE barbers ADD COLUMN IF NOT EXISTS gaji_per_hari INTEGER NOT NULL DEFAULT 0;

-- Tahap 16: isi foto barber (BLOB) pindah dari disk lokal ke sini (disk
-- lokal Render Free tier TIDAK persisten) -- foto_filename (kolom lama)
-- TETAP dipakai untuk tentukan Content-Type dari ekstensi, tidak berubah.
ALTER TABLE barbers ADD COLUMN IF NOT EXISTS foto_data BYTEA;

CREATE TABLE IF NOT EXISTS slip_gaji (
    id                SERIAL PRIMARY KEY,
    barber_id         INTEGER NOT NULL REFERENCES barbers(id),
    tahun             INTEGER NOT NULL,
    bulan             INTEGER NOT NULL,
    gaji_pokok        INTEGER NOT NULL DEFAULT 0,
    komisi            INTEGER NOT NULL DEFAULT 0,
    tips              INTEGER NOT NULL DEFAULT 0,
    uang_harian       INTEGER NOT NULL DEFAULT 0,
    bonus_customer    INTEGER NOT NULL DEFAULT 0,
    potongan_kasbon   INTEGER NOT NULL DEFAULT 0,
    potongan_lain     INTEGER NOT NULL DEFAULT 0,
    catatan_potongan  TEXT,
    total_diterima    INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'belum_dibayar',
    tanggal_dibayar   TEXT,
    dibuat_oleh       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);

-- Modul Karyawan (Fase 2): Kasbon Karyawan. Dua tabel baru murni, tidak
-- perlu ALTER TABLE apa pun ke tabel lama.
CREATE TABLE IF NOT EXISTS kasbon (
    id           SERIAL PRIMARY KEY,
    barber_id    INTEGER NOT NULL REFERENCES barbers(id),
    tanggal      TEXT NOT NULL,
    jumlah       INTEGER NOT NULL,
    keterangan   TEXT,
    status       TEXT NOT NULL DEFAULT 'belum_lunas',
    sisa         INTEGER NOT NULL,
    dibuat_oleh  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS kasbon_pembayaran (
    id            SERIAL PRIMARY KEY,
    kasbon_id     INTEGER NOT NULL REFERENCES kasbon(id),
    tanggal       TEXT NOT NULL,
    jumlah        INTEGER NOT NULL,
    sumber        TEXT NOT NULL DEFAULT 'manual',
    slip_gaji_id  INTEGER REFERENCES slip_gaji(id),
    keterangan    TEXT,
    dibuat_oleh   TEXT,
    created_at    TEXT NOT NULL
);

-- Modul Karyawan (Fase 3): Komisi (Audit & Penyesuaian). penyesuaian_komisi
-- lewat ALTER TABLE terpisah (pola sama seperti barbers.gaji_pokok di atas)
-- karena tabel slip_gaji sudah ada sejak Fase 1 -- CREATE TABLE IF NOT
-- EXISTS jadi no-op untuk instalasi yang sudah berjalan.
ALTER TABLE slip_gaji ADD COLUMN IF NOT EXISTS penyesuaian_komisi INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS komisi_penyesuaian (
    id           SERIAL PRIMARY KEY,
    barber_id    INTEGER NOT NULL REFERENCES barbers(id),
    tahun        INTEGER NOT NULL,
    bulan        INTEGER NOT NULL,
    jenis        TEXT NOT NULL,
    jumlah       INTEGER NOT NULL,
    keterangan   TEXT NOT NULL,
    dibuat_oleh  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);

-- Modul Karyawan (Fase 4): Reimburse. `reimburse` di slip_gaji lewat ALTER
-- TABLE terpisah, pola sama seperti penyesuaian_komisi di atas.
ALTER TABLE slip_gaji ADD COLUMN IF NOT EXISTS reimburse INTEGER NOT NULL DEFAULT 0;

-- Karyawan Non-Barber (Kasir/OB/Kru): jumlah_hari_masuk (NULL untuk slip
-- Barber, gaji dihitung jumlah_hari_masuk x barbers.gaji_per_hari lalu
-- disimpan ke kolom gaji_pokok slip ini apa adanya) + bonus_manual (semua
-- jabatan, pola ALTER TABLE sama seperti reimburse di atas).
ALTER TABLE slip_gaji ADD COLUMN IF NOT EXISTS jumlah_hari_masuk INTEGER;
ALTER TABLE slip_gaji ADD COLUMN IF NOT EXISTS bonus_manual INTEGER NOT NULL DEFAULT 0;

-- Tahap 13: Periode rentang tanggal bebas untuk Kasir/OB/Kru (gaji mereka
-- TIDAK dibayar bulanan seperti Barber, bisa >1 slip dalam bulan kalender
-- yang sama) -- NULL untuk slip Barber (tetap pakai tahun/bulan).
-- Constraint UNIQUE(barber_id, tahun, bulan) yang lama (inline di CREATE
-- TABLE slip_gaji di atas, SUDAH DIHAPUS dari sana) diganti index UNIQUE
-- PARSIAL di bawah -- barber (tanggal_mulai NULL) tetap 1 slip/bulan
-- seperti sekarang, non-barber diidentifikasi lewat rentang tanggalnya
-- sendiri. DROP CONSTRAINT IF EXISTS supaya instalasi yang SUDAH ADA (nama
-- constraint auto-generated Postgres dari definisi UNIQUE(...) inline yang
-- lama) ikut terlepas, bukan cuma no-op di instalasi baru.
ALTER TABLE slip_gaji ADD COLUMN IF NOT EXISTS tanggal_mulai TEXT;
ALTER TABLE slip_gaji ADD COLUMN IF NOT EXISTS tanggal_selesai TEXT;
ALTER TABLE slip_gaji DROP CONSTRAINT IF EXISTS slip_gaji_barber_id_tahun_bulan_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_slip_gaji_bulanan ON slip_gaji(barber_id, tahun, bulan) WHERE tanggal_mulai IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_slip_gaji_rentang ON slip_gaji(barber_id, tanggal_mulai, tanggal_selesai) WHERE tanggal_mulai IS NOT NULL;

CREATE TABLE IF NOT EXISTS reimburse (
    id                SERIAL PRIMARY KEY,
    barber_id         INTEGER NOT NULL REFERENCES barbers(id),
    tanggal           TEXT NOT NULL,
    kategori          TEXT NOT NULL,
    keterangan        TEXT,
    nominal           INTEGER NOT NULL,
    bukti_filename    TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    catatan_approval  TEXT,
    diajukan_oleh     TEXT,
    disetujui_oleh    TEXT,
    tanggal_approval  TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);

-- Tahap 16: isi bukti reimburse (BLOB) pindah dari disk lokal ke sini
-- (disk lokal Render Free tier TIDAK persisten).
ALTER TABLE reimburse ADD COLUMN IF NOT EXISTS bukti_data BYTEA;

-- Modul Karyawan (Fase 5): Izin & Cuti. Tabel baru murni, tidak perlu ALTER
-- TABLE apa pun ke tabel lama (berdiri sendiri, tidak terhubung Slip Gaji).
CREATE TABLE IF NOT EXISTS izin_cuti (
    id                SERIAL PRIMARY KEY,
    barber_id         INTEGER NOT NULL REFERENCES barbers(id),
    jenis             TEXT NOT NULL,
    tanggal_mulai     TEXT NOT NULL,
    tanggal_selesai   TEXT NOT NULL,
    alasan            TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    catatan_approval  TEXT,
    diajukan_oleh     TEXT,
    disetujui_oleh    TEXT,
    tanggal_approval  TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);

-- FITUR Kebijakan Cuti Dinamis (feedback Owner): SATU baris per tenant,
-- default 0/off penuh -- tenant yang belum membuka kartu "Pengaturan Izin
-- & Cuti" (menu Pengaturan > Karyawan) TIDAK terpengaruh sama sekali.
-- HANYA berlaku jenis='cuti' (lihat izin_cuti_db.py::_validasi_kebijakan_cuti()),
-- 'izin' tidak pernah divalidasi lewat mekanisme ini.
CREATE TABLE IF NOT EXISTS izin_cuti_settings (
    tenant_id              INTEGER PRIMARY KEY,
    kuota_periode_bulan    INTEGER NOT NULL DEFAULT 0,
    kuota_maksimal_hari    INTEGER NOT NULL DEFAULT 0,
    kuota_boleh_dipecah    INTEGER NOT NULL DEFAULT 1,
    h_min_pengajuan        INTEGER NOT NULL DEFAULT 0,
    maksimal_bersamaan     INTEGER NOT NULL DEFAULT 0,
    updated_at             TEXT
);

-- Modul Keuangan (Fase 1): Pemasukan. Cermin persis tabel `pengeluaran`
-- yang sudah ada (lihat blok CREATE TABLE pengeluaran di atas), sengaja
-- TIDAK di-ALTER TABLE-kan ke tabel itu -- pemasukan lain di luar
-- pendapatan service/booking pantas jadi tabel terpisah, bukan bercampur
-- dengan catatan pengeluaran.
CREATE TABLE IF NOT EXISTS pemasukan (
    id           SERIAL PRIMARY KEY,
    tanggal      TEXT NOT NULL,
    kategori     TEXT NOT NULL,
    keterangan   TEXT NOT NULL,
    jumlah       INTEGER NOT NULL,
    barber_id    INTEGER REFERENCES barbers(id),
    aktif        INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);

-- Modul Keuangan (Fase 2, pengganti Transfer Kas/Bank yang dihapus):
-- Uang Kas. kas_saldo_awal SATU baris tetap (id=1, seed lewat
-- ON CONFLICT DO NOTHING di create_all() di bawah, sama seperti
-- settings). kas_penyesuaian ledger tambah/kurang.
CREATE TABLE IF NOT EXISTS kas_saldo_awal (
    id           INTEGER PRIMARY KEY,
    saldo        INTEGER NOT NULL DEFAULT 0,
    diubah_oleh  TEXT,
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS kas_penyesuaian (
    id           SERIAL PRIMARY KEY,
    tanggal      TEXT NOT NULL,
    jenis        TEXT NOT NULL,
    jumlah       INTEGER NOT NULL,
    keterangan   TEXT,
    dibuat_oleh  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);

-- Pindah ke sini (setelah kas_penyesuaian & reimburse) supaya untuk
-- instalasi BARU, tabel yang direferensikan FK sumber_dana/
-- kas_penyesuaian_id/reimburse_id (ditambahkan lewat ALTER TABLE di
-- bawah) sudah pasti ada duluan. CREATE TABLE ini SENGAJA hanya berisi
-- kolom dasar (BUKAN sumber_dana/kas_penyesuaian_id/reimburse_id) --
-- pola yang sama seperti barbers.jabatan/gaji_pokok & slip_gaji.reimburse:
-- di instalasi PRODUKSI yang sudah ada, tabel `pengeluaran` ini SUDAH ADA
-- dari Tahap 9, jadi "CREATE TABLE IF NOT EXISTS" jadi no-op di sana --
-- taruh kolom baru di sini akan membuatnya TIDAK PERNAH ditambahkan lewat
-- jalur produksi (BUG yang sempat terjadi -- lihat ALTER TABLE di bawah,
-- itu satu-satunya jalur yang aman untuk tabel yang sudah ada).
CREATE TABLE IF NOT EXISTS pengeluaran (
    id          SERIAL PRIMARY KEY,
    tanggal     TEXT NOT NULL,
    keterangan  TEXT NOT NULL,
    jumlah      INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    kategori    TEXT,
    barber_id   INTEGER REFERENCES barbers(id),
    aktif       INTEGER NOT NULL DEFAULT 1
);

-- Tahap 12: Sumber Dana Pengeluaran (Uang Kas / Uang Karyawan) -- ALTER
-- TABLE (bukan taruh langsung di CREATE TABLE di atas) supaya tabel
-- `pengeluaran` yang SUDAH ADA di produksi (sejak Tahap 9) tetap dapat
-- kolom baru ini juga, bukan cuma instalasi baru.
ALTER TABLE pengeluaran ADD COLUMN IF NOT EXISTS sumber_dana TEXT NOT NULL DEFAULT 'kas';
ALTER TABLE pengeluaran ADD COLUMN IF NOT EXISTS kas_penyesuaian_id INTEGER REFERENCES kas_penyesuaian(id);
ALTER TABLE pengeluaran ADD COLUMN IF NOT EXISTS reimburse_id INTEGER REFERENCES reimburse(id);

-- Input Data Non-Barber (Kasir/OB/Kru/role lainnya): tabel baru murni,
-- berdiri sendiri dari `transaksi` (Barber) maupun `slip_gaji` -- lihat
-- data_non_barber_db.py. total_gaji = gaji_per_hari x hari_masuk + bonus -
-- potongan, dihitung & disimpan saat tambah/edit (bukan live dihitung ulang
-- tiap query, sama pola-nya seperti slip_gaji.total_diterima).
CREATE TABLE IF NOT EXISTS data_non_barber (
    id               SERIAL PRIMARY KEY,
    barber_id        INTEGER NOT NULL REFERENCES barbers(id),
    tanggal_mulai    TEXT NOT NULL,
    tanggal_selesai  TEXT NOT NULL,
    gaji_per_hari    INTEGER NOT NULL DEFAULT 0,
    hari_masuk       INTEGER NOT NULL DEFAULT 0,
    hari_libur       INTEGER NOT NULL DEFAULT 0,
    bonus            INTEGER NOT NULL DEFAULT 0,
    potongan         INTEGER NOT NULL DEFAULT 0,
    catatan          TEXT,
    total_gaji       INTEGER NOT NULL DEFAULT 0,
    dibuat_oleh      TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);

-- Migrasi Cloudflare R2 (Storage File): empat kolom baru (nullable, TIDAK
-- menyentuh data lama) yang menyimpan OBJECT KEY R2 -- lihat r2_storage.py
-- untuk arsitektur lengkap & r2_storage_migrasi.py untuk pasangan jalur
-- SQLite-nya. Kolom BLOB/BYTEA lama (`data`/`foto_data`/`bukti_data`) TIDAK
-- dihapus -- baris lama tetap bisa dibaca dari situ sampai di-backfill
-- lewat migrate_blobs_to_r2.py (dijalankan manual, TIDAK otomatis di sini).
ALTER TABLE file_asset ADD COLUMN IF NOT EXISTS r2_key TEXT;
ALTER TABLE website_gallery ADD COLUMN IF NOT EXISTS r2_key TEXT;
ALTER TABLE barbers ADD COLUMN IF NOT EXISTS foto_r2_key TEXT;
ALTER TABLE reimburse ADD COLUMN IF NOT EXISTS bukti_r2_key TEXT;

-- FONDASI Multi-Tenant (SaaS) Phase 1: lihat tenant_migrasi.py (jalur
-- SQLite) untuk penjelasan arsitektur lengkap -- ringkasnya: tabel baru
-- `tenants` + kolom `tenant_id` (nullable, di-backfill ke SATU tenant
-- default yang merepresentasikan data produksi yang sudah berjalan) di
-- sembilan tabel root data milik toko. Tabel lain (transaksi/absensi_libur/
-- produk_mutasi/booking_items/dst) TIDAK mendapat kolom baru -- tenant-
-- scoped TRANSITIF lewat JOIN ke tabel yang sudah bertenant_id di sini
-- (lihat database.py, perubahan query dijelaskan di komentar masing-masing
-- fungsi). `settings`/`file_asset` JUGA TIDAK mendapat kolom baru --
-- isolasi keduanya lewat prefix di dalam kolom `key` yang sudah ada
-- (lihat database.py::_kunci_tenant()/file_asset_db.py), BUKAN lewat
-- ALTER TABLE, supaya tidak perlu mengubah PRIMARY KEY(key) yang sudah ada.
CREATE TABLE IF NOT EXISTS tenants (
    id                 SERIAL PRIMARY KEY,
    slug               TEXT NOT NULL UNIQUE,
    nama_barbershop    TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'aktif',
    masa_aktif_sampai  TEXT,
    custom_domain      TEXT,
    booking_slug       TEXT,
    created_at         TEXT NOT NULL
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE barbers ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE services ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE produk ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE pengeluaran ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE website_gallery ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE closed_slot ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE toko_libur ADD COLUMN IF NOT EXISTS tenant_id INTEGER;

-- FONDASI Multi-Tenant Phase 5 (Landing Page SaaS): kolom identitas Owner
-- yang dikumpulkan lewat form Register publik -- lihat landing_migrasi.py
-- (jalur SQLite) untuk penjelasan lengkap kenapa kolom ini baru ditambahkan
-- sekarang (tabel `tenants` sebelumnya tidak pernah butuh data ini, dibuat
-- eksklusif oleh Super Admin lewat Dashboard tanpa email/whatsapp).
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS owner_name TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS whatsapp TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_email ON tenants(email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_whatsapp ON tenants(whatsapp) WHERE whatsapp IS NOT NULL;

-- FITUR URL Booking Publik per Tenant: booking_slug TERPISAH dari `slug`
-- (subdomain dashboard/staff, TIDAK BERUBAH sama sekali) -- URL booking
-- publik sendiri per tenant (`<booking_slug>.rivoirsett.com/book`,
-- lihat tenant_db.py::get_booking_url()/set_booking_slug()). ALTER TABLE
-- ADD COLUMN IF NOT EXISTS di sini untuk instalasi Postgres yang SUDAH ADA
-- sebelum kolom ini ditambahkan ke CREATE TABLE di atas (instalasi BARU
-- sudah dapat kolomnya langsung dari CREATE TABLE) -- backfill tenant lama
-- dilakukan Python di _backfill_booking_slug() di bawah (BUKAN SQL murni,
-- perlu algoritma slugify + collision-numbering yang sama dengan
-- tenant_db.py::buat_slug_unik()).
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS booking_slug TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_booking_slug ON tenants(booking_slug) WHERE booking_slug IS NOT NULL;

-- HOTFIX Migrasi Subdomain (insiden kehilangan data toko utama): flag
-- PERMANEN, TIDAK PERNAH berubah lagi setelah di-set sekali oleh
-- _backfill_toko_utama() di bawah -- SATU-SATUNYA yang dicek
-- tenant_db.py::hapus_tenant() untuk melindungi toko utama produksi,
-- menggantikan pengecekan slug == TENANT_DEFAULT_SLUG yang TERBUKTI rapuh
-- (berhenti berlaku begitu slug tenant itu diganti lewat fitur "Ubah
-- Slug", lihat kronologi lengkap di docstring _pastikan_tenant_default()
-- dan _backfill_toko_utama() di bawah).
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_toko_utama BOOLEAN NOT NULL DEFAULT FALSE;

-- FONDASI Multi-Tenant Phase 5 (Landing Page SaaS): FAQ yang ditampilkan di
-- Landing Page publik, dikelola Super Admin (bukan hardcode, lihat
-- landing_db.py). Berdiri sendiri, TIDAK bertenant_id (konten platform,
-- bukan milik satu toko).
CREATE TABLE IF NOT EXISTS landing_faq (
    id           SERIAL PRIMARY KEY,
    pertanyaan   TEXT NOT NULL,
    jawaban      TEXT NOT NULL,
    urutan       INTEGER NOT NULL DEFAULT 0,
    aktif        INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- REVISI Restrukturisasi Super Admin & Landing Page: fitur Testimonial
-- dihapus total -- tabel landing_testimonials (kalau sempat terbuat di
-- instalasi lama) di-DROP di sini, BUKAN dibuat lagi.
DROP TABLE IF EXISTS landing_testimonials;

-- FONDASI Multi-Tenant Phase 1.1: pemasukan.barber_id NULLABLE dan
-- kas_saldo_awal/kas_penyesuaian TIDAK PUNYA barber_id sama sekali (saldo
-- kas milik TOKO, bukan satu karyawan) -- ketiganya TIDAK BISA di-scope
-- transitif lewat JOIN ke barbers seperti kasbon/reimburse/dst, jadi dapat
-- tenant_id LANGSUNG (lihat tenant_migrasi.py untuk penjelasan lengkap).
ALTER TABLE pemasukan ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE kas_saldo_awal ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
ALTER TABLE kas_penyesuaian ADD COLUMN IF NOT EXISTS tenant_id INTEGER;

-- Kolom `nama` di barbers/services SENGAJA TIDAK lagi unik GLOBAL --
-- dilonggarkan jadi unik PER TENANT (dua toko boleh sama-sama punya
-- barber "Andi" atau service "Dry Cut"). Nama constraint di bawah ini
-- (```_nama_key```) adalah nama otomatis Postgres untuk `UNIQUE(nama)`
-- inline di CREATE TABLE -- DROP CONSTRAINT IF EXISTS aman dipanggil
-- berulang (no-op kalau sudah pernah dijalankan/tidak pernah ada).
ALTER TABLE barbers DROP CONSTRAINT IF EXISTS barbers_nama_key;
ALTER TABLE services DROP CONSTRAINT IF EXISTS services_nama_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_barbers_tenant_nama ON barbers(tenant_id, nama);
CREATE UNIQUE INDEX IF NOT EXISTS idx_services_tenant_nama ON services(tenant_id, nama);

-- users.username: sama alasannya -- dua tenant boleh sama-sama punya
-- username "admin".
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tenant_username ON users(tenant_id, username);

-- FONDASI Multi-Tenant Phase 2.1: audit log Super Admin -- lihat
-- superadmin_audit_db.py (jalur SQLite) untuk penjelasan lengkap. Baris di
-- sini milik SELURUH sistem (bukan satu tenant), jadi SENGAJA tidak punya
-- kolom tenant_id sendiri.
CREATE TABLE IF NOT EXISTS superadmin_audit_log (
    id                    SERIAL PRIMARY KEY,
    waktu                 TEXT NOT NULL,
    superadmin_username   TEXT NOT NULL,
    aksi                  TEXT NOT NULL,
    tenant_id             INTEGER,
    tenant_slug           TEXT,
    detail                TEXT
);

-- FONDASI Multi-Tenant Phase 3: tenant_id tanpa foreign key ke tenants
-- (lihat komentar Python di atas definisi _TABLES untuk penjelasan lengkap).
CREATE TABLE IF NOT EXISTS tenant_subscriptions (
    id           SERIAL PRIMARY KEY,
    tenant_id    INTEGER NOT NULL UNIQUE,
    package      TEXT NOT NULL DEFAULT 'free',
    status       TEXT NOT NULL DEFAULT 'trial',
    trial_start  TEXT,
    trial_end    TEXT,
    grace_start  TEXT,
    grace_end    TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant_subscription_payments (
    id                      SERIAL PRIMARY KEY,
    tenant_id               INTEGER NOT NULL,
    provider                TEXT NOT NULL,
    virtual_account_number  TEXT NOT NULL,
    payment_status          TEXT NOT NULL DEFAULT 'pending',
    amount                  INTEGER NOT NULL,
    expired_at              TEXT,
    paid_at                 TEXT,
    created_at              TEXT NOT NULL
);

-- FONDASI Multi-Tenant Phase 4 (Billing & Payment Gateway) -- lihat
-- billing_db.py (jalur SQLite) untuk penjelasan lengkap. `kode` TANPA
-- foreign key ke mana pun (dicocokkan ke tenant_subscriptions.package di
-- kode aplikasi, bukan di database), sama seperti tenant_id di tabel lain.
CREATE TABLE IF NOT EXISTS subscription_packages (
    id           SERIAL PRIMARY KEY,
    kode         TEXT NOT NULL UNIQUE,
    nama         TEXT NOT NULL,
    harga        INTEGER NOT NULL DEFAULT 0,
    harga_6bulan INTEGER,
    durasi_hari  INTEGER NOT NULL DEFAULT 30,
    aktif        INTEGER NOT NULL DEFAULT 1,
    urutan       INTEGER NOT NULL DEFAULT 0,
    deskripsi    TEXT,
    max_barber   INTEGER,
    max_user     INTEGER,
    max_layanan  INTEGER,
    max_booking  INTEGER,
    max_cabang   INTEGER,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- FITUR Landing Page & Pricing (paket 6 bulan): instalasi Postgres yang
-- SUDAH ADA sebelum kolom ini ditambahkan ke CREATE TABLE di atas
-- (instalasi baru sudah dapat kolomnya langsung) -- lihat billing_db.py
-- untuk penjelasan lengkap kenapa NULL = paket ini tidak menawarkan
-- siklus 6 bulan.
ALTER TABLE subscription_packages ADD COLUMN IF NOT EXISTS harga_6bulan INTEGER;

CREATE TABLE IF NOT EXISTS subscription_features (
    id           SERIAL PRIMARY KEY,
    kode         TEXT NOT NULL UNIQUE,
    nama         TEXT NOT NULL,
    deskripsi    TEXT,
    aktif        INTEGER NOT NULL DEFAULT 1,
    urutan       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- package_id/feature_id PAKAI foreign key (lihat catatan Python di
-- billing_db.py::init_billing_db() -- kedua tabel di atas BARU dibuat di
-- sini sendiri dengan PRIMARY KEY yang benar, beda dengan tabel `tenants`
-- produksi lama yang jadi sumber insiden FK tenant_id di catatan lain).
CREATE TABLE IF NOT EXISTS subscription_package_features (
    id           SERIAL PRIMARY KEY,
    package_id   INTEGER NOT NULL REFERENCES subscription_packages(id),
    feature_id   INTEGER NOT NULL REFERENCES subscription_features(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    UNIQUE(package_id, feature_id)
);

-- FITUR Role Custom (diminta Owner, lihat user_roles_db.py jalur SQLite
-- untuk penjelasan lengkap): role_id PAKAI foreign key (tabel BARU, sama
-- alasannya seperti subscription_package_features di atas).
CREATE TABLE IF NOT EXISTS user_roles (
    id           SERIAL PRIMARY KEY,
    tenant_id    INTEGER,
    nama         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_role_permissions (
    id           SERIAL PRIMARY KEY,
    role_id      INTEGER NOT NULL REFERENCES user_roles(id) ON DELETE CASCADE,
    izin_key     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    UNIQUE(role_id, izin_key)
);

-- FONDASI Multi-Tenant Phase 4 (Billing & Payment Gateway langganan SaaS) --
-- lihat billing_invoice_db.py (jalur SQLite) untuk penjelasan lengkap.
-- tenant_id TANPA foreign key (pola sama seperti tabel lain di proyek ini).
CREATE TABLE IF NOT EXISTS subscription_invoices (
    id                  SERIAL PRIMARY KEY,
    nomor_invoice       TEXT NOT NULL UNIQUE,
    order_id            TEXT NOT NULL UNIQUE,
    tenant_id           INTEGER NOT NULL,
    package_kode        TEXT NOT NULL,
    package_nama        TEXT NOT NULL,
    jumlah              INTEGER NOT NULL,
    durasi_hari         INTEGER NOT NULL,
    metode_pembayaran   TEXT,
    payment_type        TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    snap_token          TEXT,
    snap_redirect_url   TEXT,
    periode_mulai       TEXT,
    periode_selesai     TEXT,
    raw_notification    TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    paid_at             TEXT
);

-- Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: riwayat
-- transisi status invoice (lihat billing_invoice_db.py::catat_status_log()
-- jalur SQLite untuk penjelasan lengkap) -- dipakai Detail Transaksi Super
-- Admin, write-once dari sisi aplikasi.
CREATE TABLE IF NOT EXISTS subscription_invoice_status_log (
    id              SERIAL PRIMARY KEY,
    invoice_id      INTEGER NOT NULL,
    status_lama     TEXT,
    status_baru     TEXT NOT NULL,
    sumber          TEXT NOT NULL,
    waktu           TEXT NOT NULL
);

-- Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: Payment
-- Gateway BOOKING customer -- lihat booking_gateway_migrasi.py (jalur
-- SQLite) untuk penjelasan lengkap. TERPISAH TOTAL dari
-- subscription_invoices/subscription_invoice_status_log di atas (langganan
-- SaaS) -- dua jenis transaksi, TIDAK saling bergantung sama sekali.
CREATE TABLE IF NOT EXISTS booking_payment_transactions (
    id                      SERIAL PRIMARY KEY,
    tenant_id               INTEGER NOT NULL,
    tenant_nama             TEXT NOT NULL,
    booking_id              INTEGER NOT NULL,
    order_id                TEXT NOT NULL UNIQUE,
    nomor_transaksi         TEXT NOT NULL UNIQUE,
    customer_nama           TEXT NOT NULL,
    barber_nama             TEXT NOT NULL,
    layanan                 TEXT NOT NULL,
    nominal                 INTEGER NOT NULL,
    metode_pembayaran       TEXT NOT NULL DEFAULT 'gateway',
    channel_pembayaran      TEXT,
    status_pembayaran       TEXT NOT NULL DEFAULT 'menunggu_pembayaran',
    transaction_id_provider TEXT,
    reference_id_provider   TEXT,
    checkout_token          TEXT,
    checkout_redirect_url   TEXT,
    raw_notification        TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    paid_at                 TEXT
);

CREATE TABLE IF NOT EXISTS booking_payment_status_log (
    id              SERIAL PRIMARY KEY,
    transaction_id  INTEGER NOT NULL,
    status_lama     TEXT,
    status_baru     TEXT NOT NULL,
    sumber          TEXT NOT NULL,
    waktu           TEXT NOT NULL
);

-- FITUR Email, Verifikasi Email, Lupa Kata Sandi -- lihat penjelasan
-- lengkap di email_auth_migrasi.py (jalur SQLite, SAMA PERSIS niatnya).
-- `email`/`email_verified`/`blokir_sampai_verifikasi` TIDAK mengubah
-- kolom `users` yang sudah ada -- `username` TETAP satu-satunya identitas
-- login. `blokir_sampai_verifikasi` HANYA diset TRUE oleh Registrasi
-- mandiri BARU -- tenant lama/email yang ditambahkan lewat Pengaturan >
-- Profil TIDAK PERNAH diblokir login karenanya.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS blokir_sampai_verifikasi INTEGER NOT NULL DEFAULT 0;

-- FITUR Izin Lokasi APK Android -- lihat lokasi_user_migrasi.py (jalur
-- SQLite, SAMA PERSIS niatnya) + routers/auth_router.py::simpan_lokasi().
-- "Lokasi TERAKHIR diketahui" per akun, best-effort, nullable, TIDAK ADA
-- default wajib -- baris lama TIDAK ikut berubah sama sekali.
ALTER TABLE users ADD COLUMN IF NOT EXISTS lokasi_lat DOUBLE PRECISION;
ALTER TABLE users ADD COLUMN IF NOT EXISTS lokasi_lng DOUBLE PRECISION;
ALTER TABLE users ADD COLUMN IF NOT EXISTS lokasi_updated_at TEXT;
-- FITUR Role Custom (diminta Owner): referensi opsional ke user_roles.id
-- (lihat user_roles_db.py) -- NULL (default, TERMASUK semua akun staff
-- yang sudah ada) berarti "pakai set izin default tenant", TIDAK BERUBAH
-- sama sekali dari perilaku lama.
ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_role_id INTEGER;

-- Token sekali pakai (kedaluwarsa lewat expires_at) -- TERPISAH TOTAL dari
-- mekanisme token sesi login (auth.py, tidak disentuh migrasi ini).
-- BUGFIX DEPLOY: `user_id` SENGAJA TANPA "REFERENCES users(id)" (pola SAMA
-- seperti tenant_id/user_id di SELURUH tabel lain proyek ini, lihat mis.
-- subscription_invoices/pemasukan di atas) -- versi awal fitur ini SEMPAT
-- memakainya, dan langsung meng-crash boot produksi:
-- "psycopg2.errors.InvalidForeignKey: there is no unique constraint
-- matching given keys for referenced table 'users'" -- tabel `users` di
-- database produksi yang SUDAH BERJALAN ternyata TIDAK (lagi) punya
-- constraint UNIQUE/PRIMARY KEY murni pada `id` yang bisa dirujuk FK baru
-- (riwayat korupsi tenant_id sebelumnya di tabel ini, lihat log commit
-- "BUGFIX KRITIS ... tenant_id korup di DB") -- CREATE TABLE IF NOT EXISTS
-- users (...) di atas TIDAK PERNAH benar-benar dieksekusi ulang pada
-- instalasi yang sudah ada, jadi definisi PRIMARY KEY di sana tidak
-- menolong sama sekali. Menghapus FK ini (sama seperti pola tabel lain)
-- membuat migrasi ini idempotent & aman dijalankan pada schema produksi
-- apa adanya, tanpa perlu memperbaiki tabel `users` yang sudah berjalan.
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    used_at     TEXT
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    used_at     TEXT
);

-- REVISI Integrasi Resend: token verifikasi email SEKARANG sekali pakai
-- juga (item 5 spesifikasi "hanya dapat digunakan satu kali") -- BEDA
-- dari desain awal (idempotent, klik ulang aman) -- lihat
-- email_auth_db.py::verifikasi_email_dengan_token() untuk penjelasan UX
-- klik ulang (tidak dianggap error, pesan "sudah diverifikasi
-- sebelumnya"). CREATE TABLE di atas sudah membawa kolom ini untuk
-- instalasi BARU; ALTER di bawah untuk instalasi yang SUDAH ADA.
ALTER TABLE email_verification_tokens ADD COLUMN IF NOT EXISTS used_at TEXT;

-- BUGFIX performa (produksi: psycopg2.pool.PoolError "connection pool
-- exhausted" di Dashboard Owner, grafik-harian/grafik-bulanan sampai
-- puluhan detik) -- diaudit sampai akar penyebabnya: TIDAK ADA index sama
-- sekali di seluruh skema ini sebelumnya (SELAIN primary key), jadi SETIAP
-- query yang menyaring `transaksi` (tabel paling sering diakses -- Rekap,
-- Dashboard, Laporan PDF) selalu full table scan. Empat index di bawah
-- (kolom yang paling sering dipakai WHERE/JOIN, lihat get_transaksi_list()/
-- _lengkapi_transaksi_batch() di database.py) murni PENAMBAHAN struktur
-- baca (TIDAK mengubah satu baris data pun) -- aman & idempotent lewat
-- "IF NOT EXISTS", sama seperti pola ALTER TABLE di seluruh file ini.
CREATE INDEX IF NOT EXISTS idx_transaksi_tanggal ON transaksi(tanggal);
CREATE INDEX IF NOT EXISTS idx_transaksi_barber_id ON transaksi(barber_id);
CREATE INDEX IF NOT EXISTS idx_transaksi_detail_transaksi_id ON transaksi_detail(transaksi_id);
CREATE INDEX IF NOT EXISTS idx_barbers_tenant_id ON barbers(tenant_id);

-- FITUR Absensi (GPS Check In/Out Geofencing) -- modul BARU, MANDIRI (lihat
-- docstring lengkap di attendance_db.py, jalur SQLite yang SAMA PERSIS).
-- SENGAJA TIDAK terhubung ke izin_cuti/absensi_libur sama sekali (keputusan
-- eksplisit Owner). Index tenant_id/barber_id/tanggal ditambahkan LANGSUNG
-- sejak awal (pelajaran dari BUGFIX performa index transaksi di atas -- tidak
-- menunggu sampai jadi masalah produksi).
CREATE TABLE IF NOT EXISTS attendance_settings (
    id                INTEGER PRIMARY KEY,
    jam_masuk         TEXT NOT NULL DEFAULT '09:00',
    toleransi_menit   INTEGER NOT NULL DEFAULT 15,
    jam_pulang        TEXT NOT NULL DEFAULT '20:00',
    radius_meter      INTEGER NOT NULL DEFAULT 500,
    lokasi_nama       TEXT,
    lokasi_latitude   DOUBLE PRECISION,
    lokasi_longitude  DOUBLE PRECISION,
    updated_at        TEXT,
    tenant_id         INTEGER
);

-- REVISI: besar anggaran limit Keterlambatan & Pulang Lebih Awal (menit/
-- bulan, lihat attendance_db.py::hitung_ringkasan_bulan()) sekarang bisa
-- diatur Owner/Admin lewat menu Absensi, bukan konstanta tetap 120 --
-- ADD COLUMN IF NOT EXISTS untuk instalasi Postgres yang SUDAH ADA (pola
-- sama seperti barbers.gaji_pokok di atas).
ALTER TABLE attendance_settings ADD COLUMN IF NOT EXISTS batas_menit_terlambat INTEGER NOT NULL DEFAULT 120;
ALTER TABLE attendance_settings ADD COLUMN IF NOT EXISTS batas_menit_pulang_awal INTEGER NOT NULL DEFAULT 120;

-- FITUR Uang Harian Dinamis: toleransi harian untuk pulang lebih awal TIDAK
-- ADA sebelumnya (pulang_awal SELALU dihitung dari jam_pulang tanpa
-- toleransi -- lihat attendance_db.py::_menit_pulang_awal_baris(), TIDAK
-- diubah sama sekali oleh kolom ini). Kolom ini KHUSUS dipakai mesin
-- kalkulasi Uang Harian Dinamis (lihat uang_harian_dinamis_db.py) sebagai
-- pasangan simetris toleransi_menit (keterlambatan) di atas -- default 0
-- supaya perilaku LAMA (tanpa toleransi pulang awal) tetap sama persis
-- untuk tenant yang belum mengatur.
ALTER TABLE attendance_settings ADD COLUMN IF NOT EXISTS toleransi_pulang_awal_menit INTEGER NOT NULL DEFAULT 0;

-- FITUR Toleransi Absen Lebih Awal (feedback Owner): SEBELUMNYA Check In
-- SELALU ditolak keras sebelum jam_masuk PERSIS -- kolom ini (menit,
-- opsional per tenant) menggeser BATAS AWAL yang diizinkan Check In jadi
-- (jam_masuk - toleransi_absen_awal_menit), TIDAK mengubah jam_masuk itu
-- sendiri (tetap acuan tunggal utk status tepat_waktu/terlambat, lihat
-- attendance_db.py::validasi_checkin()). Default 0 = perilaku lama (harus
-- tepat jam_masuk atau lebih) tetap sama persis untuk tenant yang belum
-- mengatur.
ALTER TABLE attendance_settings ADD COLUMN IF NOT EXISTS toleransi_absen_awal_menit INTEGER NOT NULL DEFAULT 0;

-- FITUR Uang Harian Dinamis: konfigurasi PER TENANT (lihat docstring lengkap
-- di uang_harian_dinamis_db.py) -- `aktif=FALSE` (default) berarti Uang
-- Harian TETAP memakai sistem lama (database.py, murni jumlah service)
-- TANPA PERUBAHAN, jadi tabel ini baru relevan untuk Tenant yang SENGAJA
-- opt-in lewat menu Pengaturan.
CREATE TABLE IF NOT EXISTS uang_harian_dinamis_settings (
    tenant_id                       INTEGER PRIMARY KEY,
    aktif                           INTEGER NOT NULL DEFAULT 0,
    keterlambatan_gunakan_toleransi INTEGER NOT NULL DEFAULT 0,
    keterlambatan_gunakan_limit     INTEGER NOT NULL DEFAULT 0,
    keterlambatan_potongan_persen   INTEGER NOT NULL DEFAULT 0,
    pulang_awal_gunakan_toleransi   INTEGER NOT NULL DEFAULT 0,
    pulang_awal_gunakan_limit       INTEGER NOT NULL DEFAULT 0,
    pulang_awal_potongan_persen     INTEGER NOT NULL DEFAULT 0,
    kombinasi_metode                TEXT NOT NULL DEFAULT 'OR',
    service_rule_mode                TEXT NOT NULL DEFAULT 'TIDAK_DIGUNAKAN',
    service_rule_minimal            INTEGER NOT NULL DEFAULT 0,
    service_rule_potongan_persen    INTEGER NOT NULL DEFAULT 0,
    updated_at                       TEXT
);

-- FITUR Notifikasi Push (Web Push/VAPID, termasuk iPhone lewat PWA "Add to
-- Home Screen" sejak iOS 16.4): SATU baris per Push Subscription (endpoint
-- + kunci enkripsi p256dh/auth dari browser) -- SATU akun bisa punya
-- BANYAK subscription sekaligus (HP + laptop, dst), UNIQUE di endpoint
-- sendiri (bukan per-user) supaya subscribe ulang dari endpoint yang SAMA
-- meng-update kunci tanpa duplikat (lihat push_db.py::simpan_subscription()).
-- `user_id`/`tenant_id` SENGAJA TANPA "REFERENCES ..." (pola SAMA seperti
-- seluruh tabel lain di file ini -- lihat catatan panjang HOTFIX DEPLOY
-- tepat di bawah ini untuk kejadian PERSIS sama pada tabel lain).
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    tenant_id  INTEGER,
    endpoint   TEXT NOT NULL,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(endpoint)
);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id ON push_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_tenant_id ON push_subscriptions(tenant_id);

-- HOTFIX DEPLOY: `barber_id` SENGAJA TANPA "REFERENCES barbers(id)" (pola
-- SAMA seperti user_id/tenant_id di tabel lain sepanjang file ini, lihat
-- catatan panjang di email_verification_tokens di atas untuk kejadian
-- PERSIS sama pada tabel `users`) -- versi awal fitur ini SEMPAT memakainya,
-- dan langsung meng-crash boot produksi: "psycopg2.errors.InvalidForeignKey:
-- there is no unique constraint matching given keys for referenced table
-- 'barbers'" -- tabel `barbers` di database produksi yang SUDAH BERJALAN
-- ternyata TIDAK (lagi) punya constraint UNIQUE/PRIMARY KEY murni pada `id`
-- yang bisa dirujuk FK baru (CREATE TABLE IF NOT EXISTS barbers (...) di
-- atas TIDAK PERNAH benar-benar dieksekusi ulang pada instalasi yang sudah
-- ada, jadi definisi PRIMARY KEY di sana tidak menolong sama sekali).
-- Menghapus FK ini membuat migrasi ini idempotent & aman dijalankan pada
-- schema produksi apa adanya.
CREATE TABLE IF NOT EXISTS attendance_logs (
    id                    SERIAL PRIMARY KEY,
    barber_id             INTEGER NOT NULL,
    tanggal               TEXT NOT NULL,
    check_in_at           TEXT,
    check_in_latitude     DOUBLE PRECISION,
    check_in_longitude    DOUBLE PRECISION,
    check_in_accuracy     DOUBLE PRECISION,
    check_in_speed        DOUBLE PRECISION,
    check_in_heading      DOUBLE PRECISION,
    check_in_jarak_meter  DOUBLE PRECISION,
    check_in_status       TEXT,
    check_in_browser      TEXT,
    check_in_device       TEXT,
    check_in_ip           TEXT,
    check_out_at          TEXT,
    check_out_latitude    DOUBLE PRECISION,
    check_out_longitude   DOUBLE PRECISION,
    check_out_accuracy    DOUBLE PRECISION,
    check_out_speed       DOUBLE PRECISION,
    check_out_heading     DOUBLE PRECISION,
    check_out_jarak_meter DOUBLE PRECISION,
    check_out_browser     TEXT,
    check_out_device      TEXT,
    check_out_ip          TEXT,
    durasi_kerja_menit    INTEGER,
    created_at            TEXT NOT NULL,
    updated_at            TEXT,
    tenant_id             INTEGER,
    UNIQUE(barber_id, tanggal)
);

CREATE TABLE IF NOT EXISTS attendance_audit_logs (
    id           SERIAL PRIMARY KEY,
    barber_id    INTEGER,
    aksi         TEXT NOT NULL,
    sukses       INTEGER NOT NULL,
    alasan_gagal TEXT,
    waktu_server TEXT NOT NULL,
    latitude     DOUBLE PRECISION,
    longitude    DOUBLE PRECISION,
    accuracy     DOUBLE PRECISION,
    browser      TEXT,
    device       TEXT,
    ip_address   TEXT,
    tenant_id    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_attendance_logs_tenant_tanggal ON attendance_logs(tenant_id, tanggal);
CREATE INDEX IF NOT EXISTS idx_attendance_logs_barber_id ON attendance_logs(barber_id);
CREATE INDEX IF NOT EXISTS idx_attendance_audit_logs_tenant_id ON attendance_audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_audit_logs_barber_id ON attendance_audit_logs(barber_id);

-- FITUR Koreksi Absensi -- barber lupa Check In/Check Out mengajukan
-- koreksi, Owner/Admin approve/reject (lihat attendance_db.py, jalur
-- SQLite yang SAMA PERSIS). barber_id SENGAJA TANPA FK, pola sama seperti
-- attendance_logs.barber_id di atas (lihat catatan HOTFIX DEPLOY di atas).
CREATE TABLE IF NOT EXISTS attendance_koreksi (
    id                SERIAL PRIMARY KEY,
    barber_id         INTEGER NOT NULL,
    tanggal           TEXT NOT NULL,
    jenis             TEXT NOT NULL,
    waktu_diajukan    TEXT NOT NULL,
    alasan            TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    catatan_approval  TEXT,
    diajukan_oleh     TEXT,
    disetujui_oleh    TEXT,
    tanggal_approval  TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    tenant_id         INTEGER
);

CREATE INDEX IF NOT EXISTS idx_attendance_koreksi_tenant_id ON attendance_koreksi(tenant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_koreksi_barber_id ON attendance_koreksi(barber_id);

-- DIY error monitoring (bukan Sentry, lihat error_log_db.py): SATU tabel
-- menampung catatan error frontend (POST /api/log-error) maupun backend
-- (auto-capture crash tak terduga, lihat main.py::_tangani_exception_global()).
-- `tenant_id` SENGAJA TANPA "REFERENCES tenants(id)", pola sama seperti
-- SELURUH tabel lain di file ini (lihat catatan HOTFIX DEPLOY di atas) --
-- juga SENGAJA nullable (error sebelum tenant sempat diketahui, mis. di
-- halaman Login, ATAU crash backend yang exception handler globalnya tidak
-- tahu sesi tenant mana yang sedang aktif).
CREATE TABLE IF NOT EXISTS error_logs (
    id         SERIAL PRIMARY KEY,
    tenant_id  INTEGER,
    sumber     TEXT NOT NULL,
    pesan      TEXT NOT NULL,
    detail     TEXT,
    url        TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_error_logs_tenant_id ON error_logs(tenant_id);
"""


def _pastikan_primary_key_settings(conn) -> None:
    """HOTFIX (produksi: HTTP 500 di SETIAP endpoint Setting yang menyimpan
    lewat database.py::set_setting()/set_settings_bulk() -- Komisi, Bonus
    Service, Uang Harian, Target Bonus Service, Hak Akses Admin, SEMUANYA
    lewat fungsi yang sama -- log traceback produksi menunjukkan
    psycopg2.errors.InvalidColumnReference "there is no unique or
    exclusion constraint matching the ON CONFLICT specification").

    set_setting()/set_settings_bulk() memakai
    "INSERT ... ON CONFLICT(key) DO UPDATE" -- bentuk ON CONFLICT dengan
    target kolom eksplisit ini WAJIB ada UNIQUE/PRIMARY KEY constraint
    PERSIS di kolom `key` di PostgreSQL, atau Postgres MENOLAK statement-nya
    SAMA SEKALI (untuk baris apa pun, bukan cuma yang benar-benar bentrok).
    Tabel `settings` DIDEKLARASIKAN dengan `key TEXT PRIMARY KEY` di _TABLES
    di atas -- TAPI constraint itu TIDAK ADA di database produksi yang
    sudah berjalan: `CREATE TABLE IF NOT EXISTS` (dipakai supaya data lama
    tidak pernah terhapus) TIDAK PERNAH mengubah tabel yang SUDAH ADA, jadi
    kalau tabel ini pernah terbentuk (versi kode/langkah lama, atau proses
    migrasi awal) tanpa constraint tsb, constraint itu tidak pernah otomatis
    muncul di deploy manapun sesudahnya walau kode di _TABLES sudah benar.

    Efek samping dari constraint yang hilang ini: seeding DEFAULT_SETTINGS/
    IDENTITAS_DEFAULT/dst di bawah SENGAJA memakai "ON CONFLICT DO NOTHING"
    TANPA target kolom (bentuk itu TIDAK butuh constraint apa pun, makanya
    create_all() sendiri tidak pernah error) -- tapi tanpa constraint, tidak
    ada yang mendeteksi baris itu sebagai "bentrok", jadi SETIAP boot/
    restart proses ini kemungkinan diam-diam menyisipkan BARIS DUPLIKAT
    baru per key, bukan di-skip. Makanya fungsi ini membersihkan duplikat
    (menyisakan SATU baris per key -- untuk key seeding hardcode nilainya
    identik jadi baris mana pun yang tersisa tidak masalah) SEBELUM
    menambahkan constraint, supaya ALTER TABLE tidak ikut gagal karena data
    yang sudah kadung duplikat."""
    ada = conn.execute(
        "SELECT 1 FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name AND tc.table_name = kcu.table_name "
        "WHERE tc.table_name = 'settings' AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE') "
        "  AND kcu.column_name = 'key'"
    ).fetchone()
    if ada:
        return
    _logger.warning(
        "[postgres_schema] create_all(): tabel settings TIDAK punya PRIMARY KEY/UNIQUE "
        "constraint di kolom key -- membersihkan duplikat & menambahkan constraint sekarang."
    )
    conn.execute("DELETE FROM settings a USING settings b WHERE a.key = b.key AND a.ctid < b.ctid")
    conn.execute("ALTER TABLE settings ADD CONSTRAINT settings_pkey PRIMARY KEY (key)")
    _logger.warning("[postgres_schema] create_all(): constraint settings_pkey berhasil ditambahkan.")


def create_all():
    """Idempotent -- aman dipanggil tiap kali proses ini boot (sama seperti
    init_db() di jalur SQLite). TIDAK PERNAH menghapus/menimpa data yang
    sudah ada (CREATE TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING).

    HOTFIX v3->v4 (produksi macet total di boot -- "No open ports detected"
    berulang-ulang di log Render sampai port-scan timeout, MENGGANTIKAN
    masalah "out of shared memory" yang SEBELUMNYA ada di sini): versi v3
    memecah SELURUH fungsi ini (90+ statement DDL DITAMBAH setiap fungsi
    migrasi/seeding) jadi satu transaksi TERPISAH per statement/fungsi --
    itu memang menghilangkan resiko shared-memory exhaustion, TAPI
    mengorbankan performa jauh lebih besar dari yang diperlukan: SETIAP
    transaksi baru berarti SATU ROUND-TRIP jaringan penuh ke database
    (bukan cuma di localhost seperti pengujian lokal -- di produksi,
    database bisa satu region/network hop yang jauh lebih lambat),
    sehingga proses boot yang tadinya hitungan detik jadi puluhan-ratusan
    detik, cukup lama untuk membuat Render mengira proses ini tidak
    pernah membuka port sama sekali dan MEMBATALKAN deploy-nya sendiri --
    OUTAGE BARU yang lebih parah dari sebelumnya.

    Root cause "out of shared memory" yang SEBENARNYA (dibuktikan lewat
    reproduksi terhadap PostgreSQL sungguhan, lihat riwayat commit)
    TERNYATA bukan "90 statement DDL dalam satu transaksi" (versi kode
    SEBELUM booking_slug ada pun TETAP lolos skenario itu tanpa masalah,
    diuji ulang khusus untuk memastikan) -- akar masalah SPESIFIK di
    SAVEPOINT/subtransaksi yang (versi v2, SUDAH DIHAPUS) dipakai
    _backfill_booking_slug() untuk mencoba banyak kandidat slug berurutan
    per tenant. SAVEPOINT itu SENDIRI (bukan DDL biasa) yang melewati
    fast-path lock manager Postgres dan menumpuk tekanan shared memory
    sebanding jumlah PERCOBAAN, bukan jumlah tabel.

    Diperbaiki dengan mengembalikan SELURUH DDL + fungsi migrasi/seeding
    di bawah ini ke SATU transaksi (SAMA seperti sebelum v3 -- terbukti
    aman lewat reproduksi PostgreSQL sungguhan, TIDAK butuh dipecah sama
    sekali), dan HANYA _backfill_booking_slug() -- SATU-SATUNYA bagian
    yang TERBUKTI jadi akar masalah shared-memory -- yang tetap terpisah
    dengan desain transaksi-per-percobaan-kandidat tanpa SAVEPOINT sama
    sekali (lihat docstring-nya). Ini titik keseimbangan yang benar:
    performa boot kembali cepat (SATU round-trip untuk hampir semua isi
    fungsi ini) TANPA mengembalikan resiko shared-memory yang sudah
    terbukti nyata di produksi.

    HOTFIX observability (deploy commit d3c0ca7/PR #84 TETAP gagal port-scan
    timeout di produksi walau tenant di database SEDIKIT -- hipotesis
    "banyak tenant -> banyak round-trip" jadi TIDAK BERLAKU, membuktikan
    fungsi ini benar-benar MENGGANTUNG, bukan cuma lambat): ditambahkan log
    bertahap PER FASE (dengan elapsed time) di bawah ini SEHINGGA deploy
    berikutnya yang gagal akan menunjukkan PERSIS fase mana yang terakhir
    selesai sebelum macet -- tanpa ini, log produksi cuma diam total sejak
    "Menjalankan postgres_schema.create_all()" sampai timeout, tidak
    memberi petunjuk apa pun sedang macet di baris/fase mana.

    HOTFIX v4->v5 (lihat juga docstring _backfill_booking_slug() di bawah
    untuk kronologi lengkap): dibuktikan lewat reproduksi lokal bahwa DDL
    di sini (ALTER TABLE tenants dkk.) SAMA-SAMA bisa tertahan kalau ada
    transaksi lain sedang memegang lock di tabel `tenants` -- dan
    dibuktikan juga bahwa statement_timeout dari `options` koneksi pool
    (db_compat.py) TIDAK BISA diandalkan 100% sebagai satu-satunya lapisan
    proteksi (di produksi, macet total tanpa error apa pun sampai timeout
    Render, PADAHAL statement_timeout seharusnya membatalkan dalam 30
    detik). SET LOCAL lock_timeout eksplisit di bawah -- perintah SQL
    biasa lewat koneksi yang sama, BUKAN parameter startup yang bisa
    diam-diam tidak berlaku -- jadi lapisan proteksi TERPISAH yang lebih
    bisa dipercaya: kalau transaksi ini tertahan lock, GAGAL CEPAT (10
    detik) dengan traceback jelas di log, bukan menggantung diam sampai
    timeout deploy."""
    _mulai = time.monotonic()
    _logger.info("[postgres_schema] create_all(): mulai -- membuka koneksi/transaksi.")
    with db_compat.get_conn() as conn:
        conn.execute("SET LOCAL lock_timeout = '10s'")
        _logger.info("[postgres_schema] create_all(): koneksi didapat (%.2fs) -- mulai DDL.", time.monotonic() - _mulai)
        for statement in _TABLES.strip().split(";\n\n"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
        _logger.info("[postgres_schema] create_all(): DDL selesai (%.2fs).", time.monotonic() - _mulai)

        _pastikan_primary_key_settings(conn)
        _logger.info("[postgres_schema] create_all(): constraint settings.key diverifikasi (%.2fs).",
                     time.monotonic() - _mulai)

        # FONDASI Multi-Tenant Phase 1: tenant default (merepresentasikan
        # data produksi yang sudah berjalan) + backfill tenant_id untuk
        # baris yang belum punya (baris BARU setelah Phase 1 aktif sudah
        # diisi tenant_id-nya sendiri saat dibuat, jadi TIDAK ikut tertimpa
        # di sini -- lihat _TABEL_TENANT_LANGSUNG, WHERE tenant_id IS NULL).
        tenant_default_id = _pastikan_tenant_default(conn)
        _backfill_toko_utama(conn)
        _logger.info("[postgres_schema] create_all(): tenant default id=%s siap (%.2fs).",
                     tenant_default_id, time.monotonic() - _mulai)
        for tabel in ("users", "barbers", "services", "produk", "pengeluaran",
                      "website_gallery", "bookings", "closed_slot", "toko_libur",
                      # FONDASI Multi-Tenant Phase 1.1 -- lihat ALTER TABLE di atas.
                      "pemasukan", "kas_saldo_awal", "kas_penyesuaian"):
            conn.execute(f"UPDATE {tabel} SET tenant_id = ? WHERE tenant_id IS NULL", (tenant_default_id,))
        _logger.info("[postgres_schema] create_all(): backfill tenant_id per-tabel selesai (%.2fs).",
                     time.monotonic() - _mulai)

        # FONDASI Multi-Tenant Phase 1: salin (bukan pindah/hapus) SEMUA
        # baris `settings` LAMA (key polos, dari sebelum Phase 1 aktif) ke
        # bentuk ber-prefix tenant default -- WAJIB dijalankan SEBELUM
        # seeding default hardcode di bawah, supaya toko produksi yang
        # SUDAH mengustomisasi setting (mis. persentase_komisi diubah dari
        # 40 ke nilai lain) tidak diam-diam ter-reset ke nilai pabrik begitu
        # get_setting() mulai membaca key ber-prefix (lihat database.py).
        _migrasi_prefix_settings(conn, tenant_default_id)
        _logger.info("[postgres_schema] create_all(): migrasi prefix settings selesai (%.2fs).",
                     time.monotonic() - _mulai)

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
                         (_kunci_tenant(tenant_default_id, key), value))
        for key, value in IDENTITAS_DEFAULT.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
                         (_kunci_tenant(tenant_default_id, key), value))
        for key, value in DEFAULT_BOOKING_SETTINGS.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
                         (_kunci_tenant(tenant_default_id, key), value))
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (_kunci_tenant(tenant_default_id, "bonus_customer_tiers"), json.dumps(DEFAULT_BONUS_TIERS)),
        )

        # BUGFIX (ditemukan lewat laporan Komisi selalu Rp 0): seeding
        # DEFAULT_SETTINGS di atas HANYA untuk tenant_default_id -- tenant
        # LAIN (dibuat lewat tenant_db.buat_tenant(), dipakai routers/
        # tenant_registration.py registrasi mandiri MAUPUN routers/
        # superadmin.py provisioning manual) TIDAK PERNAH mendapat baris
        # settings apa pun sebelum perbaikan ini, sehingga get_setting()/
        # _setting_float() diam-diam fallback ke "0" (mis. persentase_komisi
        # seharusnya 40%). tenant_db.buat_tenant() sendiri sudah diperbaiki
        # untuk men-seed tenant BARU langsung saat dibuat -- backfill di
        # sini KHUSUS untuk tenant yang SUDAH TERLANJUR ada sebelum
        # perbaikan itu dipasang (jalan tiap boot, aman & idempotent lewat
        # ON CONFLICT DO NOTHING, TIDAK PERNAH menimpa setting yang sudah
        # eksplisit diisi/diubah Owner tenant mana pun).
        semua_tenant_id = [r["id"] for r in conn.execute("SELECT id FROM tenants").fetchall()]
        _logger.info("[postgres_schema] create_all(): jumlah tenant=%s (%.2fs) -- mulai backfill DEFAULT_SETTINGS per-tenant.",
                     len(semua_tenant_id), time.monotonic() - _mulai)
        for tid in semua_tenant_id:
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
                             (_kunci_tenant(tid, key), value))
        _logger.info("[postgres_schema] create_all(): backfill DEFAULT_SETTINGS per-tenant selesai (%.2fs).",
                     time.monotonic() - _mulai)

        jumlah_service = conn.execute("SELECT COUNT(*) AS n FROM services WHERE tenant_id = ?",
                                       (tenant_default_id,)).fetchone()["n"]
        if jumlah_service == 0:
            # MAINTENANCE #1 (bugfix): `urutan` diisi eksplisit sesuai urutan
            # daftar di atas (bukan mengandalkan default kolom 0 untuk
            # SEMUANYA -- lihat catatan lengkap di
            # database.py::add_service()/_normalisasi_urutan_service_kolisi()
            # di booking_form_migrasi.py untuk kenapa itu masalah).
            for i, (nama, harga, pakai_potongan) in enumerate(DEFAULT_SERVICES):
                conn.execute(
                    "INSERT INTO services (nama, harga, pakai_potongan_chemical, tenant_id, urutan) VALUES (?, ?, ?, ?, ?)",
                    (nama, harga, pakai_potongan, tenant_default_id, i),
                )

        for key in ("bonus_service_acuan_service_ids", "uang_harian_acuan_service_ids"):
            kunci = _kunci_tenant(tenant_default_id, key)
            existing = conn.execute("SELECT value FROM settings WHERE key = ?", (kunci,)).fetchone()
            if existing is not None:
                continue
            placeholder = ", ".join("?" for _ in _SEED_ACUAN_NAMA)
            rows = conn.execute(f"SELECT id FROM services WHERE nama IN ({placeholder}) AND tenant_id = ?",
                                 list(_SEED_ACUAN_NAMA) + [tenant_default_id]).fetchall()
            service_ids = [r["id"] for r in rows]
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
                         (kunci, json.dumps(service_ids)))

        conn.execute("INSERT INTO kas_saldo_awal (id, saldo) VALUES (1, 0) ON CONFLICT DO NOTHING")
        _logger.info("[postgres_schema] create_all(): seed service/acuan/kas_saldo_awal selesai (%.2fs).",
                     time.monotonic() - _mulai)

        _normalisasi_urutan_service_kolisi(conn)
        _logger.info("[postgres_schema] create_all(): normalisasi urutan service selesai (%.2fs).",
                     time.monotonic() - _mulai)
        _normalisasi_urutan_barber_kolisi(conn)
        _logger.info("[postgres_schema] create_all(): normalisasi urutan barber selesai (%.2fs).",
                     time.monotonic() - _mulai)
        _migrasi_subscription(conn)
        _logger.info("[postgres_schema] create_all(): migrasi subscription selesai (%.2fs).",
                     time.monotonic() - _mulai)
        _migrasi_billing_packages(conn)
        _migrasi_billing_features(conn)
        _migrasi_seed_fitur_paket(conn)
        _migrasi_hapus_fitur_dekoratif(conn)
        _migrasi_seed_fitur_baru_digerbang(conn)
        _migrasi_harga_pricing_v2(conn)
        _logger.info("[postgres_schema] create_all(): migrasi billing packages/features selesai (%.2fs) -- commit transaksi.",
                     time.monotonic() - _mulai)

    _logger.info("[postgres_schema] create_all(): transaksi utama COMMIT (%.2fs) -- mulai _backfill_booking_slug().",
                 time.monotonic() - _mulai)
    _backfill_booking_slug()
    _logger.info("[postgres_schema] create_all(): SELESAI TOTAL (%.2fs).", time.monotonic() - _mulai)


def _migrasi_subscription(conn):
    """FONDASI Multi-Tenant Phase 3 -- versi PostgreSQL, SAMA PERSIS
    logikanya dengan subscription_migrasi.py::migrasi_subscription() (jalur
    SQLite, lihat docstring modul itu untuk penjelasan lengkap termasuk
    kenapa TIDAK ADA status permanen yang di-hardcode untuk tenant mana
    pun) -- diduplikasi di sini murni supaya modul ini TIDAK perlu import
    subscription_db.py (lihat catatan _kunci_tenant() di atas untuk alasan
    yang sama). SETIAP tenant yang belum punya baris tenant_subscriptions
    (termasuk tenant_default_id di atas) dapat baris default -- idempotent,
    baris yang SUDAH ADA tidak pernah ditimpa."""
    package = os.environ.get("SUBSCRIPTION_SEED_DEFAULT_PACKAGE", "free").strip().lower()
    if package not in {"free", "basic", "pro", "enterprise"}:
        package = "free"
    status = os.environ.get("SUBSCRIPTION_SEED_DEFAULT_STATUS", "active").strip().lower()
    if status not in {"trial", "active", "grace_period", "expired", "suspended", "cancelled"}:
        status = "active"
    now = datetime.now().isoformat(timespec="seconds")
    trial_start = trial_end = None
    if status == "trial":
        # Kunci platform-wide TANPA prefix tenant (sama seperti
        # subscription_db.py::get_platform_config()/_KUNCI_TRIAL_HARI) --
        # kalau Super Admin belum pernah mengatur lewat PUT
        # /api/superadmin/subscriptions/config, pakai default pabrik 14
        # hari (subscription_db.DEFAULT_TRIAL_HARI di jalur SQLite).
        row = conn.execute("SELECT value FROM settings WHERE key = 'subscription_trial_hari'").fetchone()
        trial_hari = int(row["value"]) if row else 14
        trial_start = now
        trial_end = (datetime.now() + timedelta(days=trial_hari)).isoformat(timespec="seconds")
    tenant_ids = [r["id"] for r in conn.execute("SELECT id FROM tenants").fetchall()]
    for tenant_id in tenant_ids:
        existing = conn.execute(
            "SELECT id FROM tenant_subscriptions WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        if existing is not None:
            continue
        conn.execute(
            "INSERT INTO tenant_subscriptions "
            "(tenant_id, package, status, trial_start, trial_end, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, package, status, trial_start, trial_end, now, now),
        )


def _migrasi_billing_packages(conn):
    """FONDASI Multi-Tenant Phase 4 -- versi PostgreSQL, SAMA PERSIS logikanya
    dengan billing_db.py::seed_default_packages() (jalur SQLite) --
    diduplikasi di sini dengan alasan yang sama seperti _migrasi_subscription()
    di atas (modul ini TIDAK mengimpor billing_db.py). Idempotent -- baris
    yang SUDAH ADA (Super Admin mungkin sudah mengubah harga/nama/dst lewat
    Dashboard) TIDAK PERNAH ditimpa."""
    urutan_default = {"free": 1, "basic": 2, "pro": 3, "enterprise": 4}
    nama_default = {"free": "Free", "basic": "Basic", "pro": "Pro", "enterprise": "Enterprise"}
    harga_default = {"free": 0, "basic": 99000, "pro": 249000, "enterprise": 599000}
    now = datetime.now().isoformat(timespec="seconds")
    existing = {r["kode"] for r in conn.execute("SELECT kode FROM subscription_packages").fetchall()}
    for kode in sorted(urutan_default, key=lambda k: urutan_default[k]):
        if kode in existing:
            continue
        conn.execute(
            "INSERT INTO subscription_packages "
            "(kode, nama, harga, durasi_hari, aktif, urutan, deskripsi, created_at, updated_at) "
            "VALUES (?, ?, ?, 30, 1, ?, '', ?, ?)",
            (kode, nama_default[kode], harga_default[kode], urutan_default[kode], now, now),
        )


_FITUR_DEFAULT_POSTGRES = (
    ("booking_online", "Booking Online"),
    ("export_pdf", "Export PDF"),
    ("export_excel", "Export Excel"),
    ("qris", "QRIS"),
    ("whatsapp_reminder", "WhatsApp Reminder"),
    ("log_error", "Log Error"),
    # SAMA PERSIS billing_db.py::_FITUR_DEFAULT -- lihat docstring di sana.
    # TIDAK ADA grandfather untuk kedua kode ini (keputusan eksplisit
    # Owner), jadi TIDAK ADA fungsi _migrasi_seed_fitur_baru_digerbang()
    # kedua untuk keduanya -- cukup masuk katalog di sini.
    ("barber_app", "Aplikasi Barber (Login Barber)"),
    ("absensi", "Absensi Karyawan"),
)
_FITUR_NYATA_DEFAULT_POSTGRES = ("booking_online", "qris", "export_pdf")
_KODE_FITUR_TANPA_FUNGSI_NYATA_POSTGRES = (
    "dashboard_owner", "dashboard_barber", "multi_barber", "multi_cabang",
    "google_calendar", "virtual_account", "api", "priority_support",
)
_KODE_FITUR_BARU_DIGERBANG_POSTGRES = ("export_excel", "whatsapp_reminder")
_KUNCI_SEED_FITUR_PAKET = "billing_seed_fitur_nyata_paket_selesai"
_KUNCI_HAPUS_FITUR_DEKORATIF = "billing_hapus_fitur_tanpa_fungsi_nyata_selesai"
_KUNCI_SEED_FITUR_BARU_DIGERBANG = "billing_seed_fitur_baru_digerbang_selesai"


def _migrasi_billing_features(conn):
    """FONDASI Multi-Tenant Phase 4 -- versi PostgreSQL, SAMA PERSIS logikanya
    dengan billing_db.py::seed_default_features() (jalur SQLite) --
    diduplikasi di sini dengan alasan yang sama seperti
    _migrasi_billing_packages() di atas. Idempotent, tidak pernah menimpa
    baris yang sudah ada.

    REVISI (audit "fitur hardcode di Superadmin"): daftar dipangkas dari 14
    ke 6 kode -- HANYA yang sungguhan ditegakkan di kode (lihat
    billing_db.py::_FITUR_DEFAULT untuk audit lengkap kenapa 8 kode lain
    dihapus & 2 kode -- export_excel/whatsapp_reminder -- baru digerbang).
    "log_error" SEBELUMNYA TERLEWAT di jalur Postgres ini (hanya ada di
    billing_db.py._FITUR_DEFAULT, tidak pernah disalin ke sini) -- audit
    yang sama menemukan & memperbaiki gap ini sekalian."""
    now = datetime.now().isoformat(timespec="seconds")
    existing = {r["kode"] for r in conn.execute("SELECT kode FROM subscription_features").fetchall()}
    for urutan, (kode, nama) in enumerate(_FITUR_DEFAULT_POSTGRES):
        if kode in existing:
            continue
        conn.execute(
            "INSERT INTO subscription_features (kode, nama, deskripsi, aktif, urutan, created_at, updated_at) "
            "VALUES (?, ?, '', 1, ?, ?, ?)",
            (kode, nama, urutan, now, now),
        )


def _ambil_flag(conn, kunci: str) -> bool:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (kunci,)).fetchone()
    return row is not None and row["value"] == "1"


def _set_flag(conn, kunci: str):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (kunci, "1"),
    )


def _assign_fitur_ke_semua_paket(conn, kode_list):
    """Helper bersama _migrasi_seed_fitur_paket()/_migrasi_seed_fitur_baru_
    digerbang() di bawah -- gabungkan (bukan ganti) `kode_list` ke daftar
    fitur yang SUDAH dicentang tiap paket, pola SAMA PERSIS
    billing_db.py::seed_default_package_features()."""
    fitur_ids = [r["id"] for r in conn.execute(
        f"SELECT id FROM subscription_features WHERE kode IN ({', '.join(['?'] * len(kode_list))})",
        list(kode_list),
    ).fetchall()]
    if not fitur_ids:
        return
    paket_ids = [r["id"] for r in conn.execute("SELECT id FROM subscription_packages").fetchall()]
    now = datetime.now().isoformat(timespec="seconds")
    for package_id in paket_ids:
        sudah_ada = {r["feature_id"] for r in conn.execute(
            "SELECT feature_id FROM subscription_package_features WHERE package_id = ?", (package_id,)
        ).fetchall()}
        for feature_id in fitur_ids:
            if feature_id in sudah_ada:
                continue
            conn.execute(
                "INSERT INTO subscription_package_features (package_id, feature_id, created_at) VALUES (?, ?, ?)",
                (package_id, feature_id, now),
            )


def _migrasi_seed_fitur_paket(conn):
    """FONDASI Multi-Tenant Phase 4 lanjutan (Feature Gating) -- versi
    PostgreSQL, SAMA PERSIS logikanya dengan billing_db.py::seed_default_
    package_features() (jalur SQLite) -- diduplikasi di sini dengan alasan
    yang sama seperti _migrasi_billing_packages() di atas.

    CELAH YANG DIPERBAIKI (ditemukan saat audit "fitur hardcode di
    Superadmin"): fungsi ini SEBELUMNYA TIDAK PERNAH ADA di jalur Postgres
    -- jalur SQLite sudah punya assign otomatis booking_online/qris/
    export_pdf ke semua paket sejak Feature Gating dibangun, tapi jalur
    Postgres (dipakai deployment production sungguhan) TIDAK PERNAH
    menjalankan langkah yang setara, hanya membuat baris katalog fitur
    TANPA pernah mencentangnya ke paket mana pun. Kunci flag SAMA PERSIS
    dengan jalur SQLite (`billing_seed_fitur_nyata_paket_selesai`) supaya
    kalau baris `subscription_package_features` sudah sempat diisi manual
    lewat Dashboard Super Admin sebelum perbaikan ini, migrasi ini TETAP
    jalan sekali (flag belum pernah di-set jalur Postgres) tapi AMAN --
    helper di atas hanya MENAMBAH yang belum ada, tidak pernah menghapus
    centang yang sudah dibuat Super Admin secara manual."""
    if _ambil_flag(conn, _KUNCI_SEED_FITUR_PAKET):
        return
    _assign_fitur_ke_semua_paket(conn, _FITUR_NYATA_DEFAULT_POSTGRES)
    _set_flag(conn, _KUNCI_SEED_FITUR_PAKET)


def _migrasi_hapus_fitur_dekoratif(conn):
    """Versi PostgreSQL, SAMA PERSIS logikanya dengan billing_db.py::hapus_
    fitur_tanpa_fungsi_nyata() (jalur SQLite) -- lihat docstring itu untuk
    audit lengkap. `ON DELETE CASCADE` di subscription_package_features
    (lihat CREATE TABLE di atas) otomatis melepas kode ini dari paket mana
    pun yang sudah mencentangnya."""
    if _ambil_flag(conn, _KUNCI_HAPUS_FITUR_DEKORATIF):
        return
    placeholder = ", ".join("?" for _ in _KODE_FITUR_TANPA_FUNGSI_NYATA_POSTGRES)
    conn.execute(
        f"DELETE FROM subscription_features WHERE kode IN ({placeholder})",
        _KODE_FITUR_TANPA_FUNGSI_NYATA_POSTGRES,
    )
    _set_flag(conn, _KUNCI_HAPUS_FITUR_DEKORATIF)


def _migrasi_seed_fitur_baru_digerbang(conn):
    """Versi PostgreSQL, SAMA PERSIS logikanya dengan billing_db.py::seed_
    grandfather_fitur_baru_digerbang() (jalur SQLite) -- export_excel/
    whatsapp_reminder baru digerbang di audit yang sama, SEKALI assign ke
    SEMUA paket yang sudah ada supaya tenant production yang sudah
    memakainya (selalu gratis sebelum ini) tidak tiba-tiba kehilangan
    akses begitu deploy ini jalan."""
    if _ambil_flag(conn, _KUNCI_SEED_FITUR_BARU_DIGERBANG):
        return
    _assign_fitur_ke_semua_paket(conn, _KODE_FITUR_BARU_DIGERBANG_POSTGRES)
    _set_flag(conn, _KUNCI_SEED_FITUR_BARU_DIGERBANG)


_HARGA_PRICING_V2 = {
    "basic": (188000, 950000),
    "pro": (250000, 1200000),
    "enterprise": (350000, 1800000),
}
_KUNCI_MIGRASI_HARGA_PRICING_2 = "billing_migrasi_harga_pricing_2_selesai"


def _migrasi_harga_pricing_v2(conn):
    """FITUR Landing Page & Pricing (revisi paket 6 bulan) -- versi
    PostgreSQL, SAMA PERSIS logikanya dengan
    billing_db.py::migrasi_harga_pricing_v2() (jalur SQLite) -- diduplikasi
    di sini dengan alasan yang sama seperti _migrasi_billing_packages() di
    atas (modul ini TIDAK mengimpor billing_db.py). SEKALI SAJA sepanjang
    umur database (flag `settings`, kunci SAMA PERSIS dengan jalur SQLite
    supaya konsisten lintas backend) menetapkan harga bulanan + harga 6
    bulan BARU untuk basic/pro/enterprise -- SEKALI dijalankan, Super Admin
    100% memegang kendali penuh lewat Dashboard tanpa gangguan apa pun dari
    migrasi ini lagi, PERSIS seperti paket free (tidak disentuh migrasi
    ini)."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (_KUNCI_MIGRASI_HARGA_PRICING_2,)).fetchone()
    if row is not None and row["value"] == "1":
        return
    now = datetime.now().isoformat(timespec="seconds")
    for kode, (harga, harga_6bulan) in _HARGA_PRICING_V2.items():
        conn.execute(
            "UPDATE subscription_packages SET harga = ?, harga_6bulan = ?, updated_at = ? WHERE kode = ?",
            (harga, harga_6bulan, now, kode),
        )
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_KUNCI_MIGRASI_HARGA_PRICING_2, "1"),
    )


def _normalisasi_urutan_service_kolisi(conn):
    """MAINTENANCE #1 (bugfix) -- versi PostgreSQL, SAMA PERSIS logikanya
    dengan booking_form_migrasi.py::_normalisasi_urutan_service_kolisi()
    (jalur SQLite, lihat docstring itu untuk penjelasan lengkap akar
    masalahnya) -- diduplikasi di sini murni supaya modul ini TIDAK perlu
    import database.py (lihat catatan _kunci_tenant() di atas untuk alasan
    yang sama)."""
    tenant_ids = [r["tenant_id"] for r in conn.execute("SELECT DISTINCT tenant_id FROM services").fetchall()]
    for tenant_id in tenant_ids:
        if tenant_id is None:
            rows = conn.execute("SELECT id, urutan FROM services WHERE tenant_id IS NULL ORDER BY urutan, nama").fetchall()
        else:
            rows = conn.execute("SELECT id, urutan FROM services WHERE tenant_id = ? ORDER BY urutan, nama",
                                 (tenant_id,)).fetchall()
        urutan_terpakai = [r["urutan"] for r in rows]
        if len(set(urutan_terpakai)) == len(urutan_terpakai):
            continue  # tidak ada tabrakan untuk tenant ini, tidak perlu apa-apa
        for i, row in enumerate(rows):
            if row["urutan"] != i:
                conn.execute("UPDATE services SET urutan = ? WHERE id = ?", (i, row["id"]))


def _normalisasi_urutan_barber_kolisi(conn):
    """BOOKING UI/UX #1 (bugfix) -- versi PostgreSQL, SAMA PERSIS logikanya
    dengan booking_form_migrasi.py::_normalisasi_urutan_barber_kolisi()
    (jalur SQLite) -- diduplikasi di sini dengan alasan yang sama seperti
    _normalisasi_urutan_service_kolisi() di atas."""
    tenant_ids = [r["tenant_id"] for r in conn.execute("SELECT DISTINCT tenant_id FROM barbers").fetchall()]
    for tenant_id in tenant_ids:
        if tenant_id is None:
            rows = conn.execute("SELECT id, urutan FROM barbers WHERE tenant_id IS NULL ORDER BY urutan, nama").fetchall()
        else:
            rows = conn.execute("SELECT id, urutan FROM barbers WHERE tenant_id = ? ORDER BY urutan, nama",
                                 (tenant_id,)).fetchall()
        urutan_terpakai = [r["urutan"] for r in rows]
        if len(set(urutan_terpakai)) == len(urutan_terpakai):
            continue  # tidak ada tabrakan untuk tenant ini, tidak perlu apa-apa
        for i, row in enumerate(rows):
            if row["urutan"] != i:
                conn.execute("UPDATE barbers SET urutan = ? WHERE id = ?", (i, row["id"]))


def _pastikan_tenant_default(conn) -> int:
    """Sama persis logikanya dengan tenant_migrasi.py::_pastikan_tenant_default()
    (jalur SQLite) -- diduplikasi murni karena jalur Postgres/SQLite memang
    dua file skema yang sudah terpisah sejak awal proyek ini (lihat db_compat.py).

    INSIDEN kehilangan data toko utama (HOTFIX Migrasi Subdomain): SEBELUM
    perbaikan ini, fungsi ini HANYA mengecek `WHERE slug = TENANT_DEFAULT_SLUG`
    -- begitu Super Admin mengganti slug toko utama lewat fitur "Ubah Slug"
    (mis. "mugen-hair-co" -> "mugen", bagian dari migrasi arsitektur
    subdomain), pengecekan itu SELALU gagal menemukan tenant mana pun sejak
    saat itu, sehingga fungsi ini (dipanggil SETIAP kali proses ini boot/
    restart, lihat create_all()) mengira toko utama "hilang" dan diam-diam
    MEMBUAT TENANT BARU YANG KOSONG bernama sama pada RESTART BERIKUTNYA --
    tenant asli (dengan slug baru, berikut SELURUH data barbers/transaksi/
    users-nya) sebenarnya tetap ada, tapi Super Admin yang menghapus tenant
    lain lewat Dashboard bisa keliru mengira tenant baru-kosong inilah yang
    asli (dua-duanya sempat tampil dengan nama "MUGEN Hair Co.") dan
    menghapus tenant yang salah -- kombinasi bug ini dengan hapus_tenant()
    yang JUGA masih mengecek slug (lihat riwayat perbaikan di sana)
    berujung toko utama produksi benar-benar terhapus permanen tanpa
    backup. Diperbaiki dengan mengecek APAKAH ADA TENANT SAMA SEKALI
    (bukan lagi slug spesifik) -- tenant baru HANYA dibuat kalau tabel
    `tenants` benar-benar kosong total (instalasi pertama kali); kalau
    sudah ada tenant lain (apa pun slug-nya, mis. karena rename yang sah),
    tenant PALING LAMA (id terkecil) yang dipakai sebagai target backfill
    baris legacy tanpa tenant_id -- TIDAK PERNAH membuat baris baru lagi
    selama masih ada tenant yang tersisa."""
    row = conn.execute("SELECT id FROM tenants WHERE slug = ?", (TENANT_DEFAULT_SLUG,)).fetchone()
    if row:
        return row["id"]
    row = conn.execute("SELECT id FROM tenants ORDER BY id LIMIT 1").fetchone()
    if row:
        return row["id"]
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO tenants (slug, nama_barbershop, status, created_at) VALUES (?, ?, 'aktif', ?)",
        (TENANT_DEFAULT_SLUG, TENANT_DEFAULT_NAMA, now),
    )
    return cur.lastrowid


def _backfill_toko_utama(conn) -> None:
    """HOTFIX Migrasi Subdomain (insiden kehilangan data toko utama): set
    flag PERMANEN `tenants.is_toko_utama` -- SATU-SATUNYA yang dicek
    tenant_db.py::hapus_tenant() untuk melindungi toko utama dari
    penghapusan, menggantikan pengecekan slug yang TERBUKTI rapuh (lihat
    docstring _pastikan_tenant_default() di atas untuk kronologi lengkap
    insidennya).

    Idempotent & SEKALI SAJA seumur hidup database: no-op begitu ADA tenant
    mana pun yang sudah ter-flag (TIDAK PERNAH memindahkan/menimpa flag ke
    tenant lain walau slug tenant yang sudah ter-flag berubah lagi di masa
    depan) -- kalau belum ada satu pun yang ter-flag, tenant yang SAAT INI
    bernama sesuai TENANT_DEFAULT_SLUG yang dipilih (kasus normal: instalasi
    lama yang baru pertama kali menjalankan migrasi ini). WAJIB dipanggil
    SETELAH _pastikan_tenant_default() (supaya tenant defaultnya sudah
    pasti ada)."""
    sudah_ada = conn.execute("SELECT 1 FROM tenants WHERE is_toko_utama = TRUE LIMIT 1").fetchone()
    if sudah_ada:
        return
    conn.execute("UPDATE tenants SET is_toko_utama = TRUE WHERE slug = ?", (TENANT_DEFAULT_SLUG,))


def _kunci_tenant(tenant_id: int, key: str) -> str:
    """SAMA PERSIS dengan database.py::_kunci_tenant() -- diduplikasi di sini
    murni supaya modul ini tidak perlu import database.py (hindari import
    siklik: database.py tidak pernah mengimpor postgres_schema.py)."""
    return f"{tenant_id}:{key}"


def _key_sudah_diprefix(key: str) -> bool:
    depan = key.split(":", 1)[0]
    return depan.isdigit()


def _migrasi_prefix_settings(conn, tenant_id_default: int):
    """Generik -- TIDAK perlu tahu daftar key satu-satu (default setting
    tersebar di banyak modul: database.py, pengaturan_identitas.py,
    website_content.py, booking_db.py, dst). Menyalin SETIAP baris `settings`
    yang key-nya masih polos (belum berbentuk "<tenant_id>:asli") ke bentuk
    baru diprefix tenant default, dengan NILAI SAAT INI (bukan nilai
    default) -- baris lama TETAP dibiarkan ada, sekadar jadi baris "mati"
    yang tidak lagi dibaca begitu kode mulai memakai key ber-prefix.
    Idempotent: kalau key ber-prefix-nya sudah ada (mis. sudah pernah
    dijalankan, atau sudah diedit ulang lewat Setting setelah Phase 1
    aktif), baris itu TIDAK ditimpa."""
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    for r in rows:
        key = r["key"]
        if _key_sudah_diprefix(key):
            continue
        kunci_baru = _kunci_tenant(tenant_id_default, key)
        existing = conn.execute("SELECT value FROM settings WHERE key = ?", (kunci_baru,)).fetchone()
        if existing is None:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
                         (kunci_baru, r["value"]))


def _backfill_booking_slug():
    """FITUR URL Booking Publik per Tenant: backfill tenant LAMA (dibuat
    sebelum kolom booking_slug ada).

    HOTFIX v3 (crash produksi "psycopg2.errors.OutOfMemory: out of shared
    memory" -- TERBUKTI lewat reproduksi terhadap PostgreSQL sungguhan,
    traceback persis menunjuk ke UPDATE di dalam fungsi ini): versi
    SEBELUMNYA (v2) memakai SAVEPOINT per kandidat, TAPI seluruh loop ini
    (semua tenant, semua percobaan kandidat tiap tenant) masih berjalan di
    DALAM SATU TRANSAKSI BESAR yang sama (dibungkus create_all()).
    SAVEPOINT adalah SUBTRANSAKSI -- lock yang diambil DI DALAM subtransaksi
    TIDAK BISA lewat "fast path" lock manager Postgres (optimasi yang
    HANYA berlaku untuk transaksi tingkat-atas), jadi SETIAP percobaan
    kandidat (bukan cuma setiap tenant -- tenant yang bernama sama/mirip
    bisa butuh BANYAK percobaan berurutan) menambah tekanan ke shared lock
    table yang kapasitasnya TERBATAS. Reproduksi lokal terhadap PostgreSQL
    sungguhan (bukan simulasi) MEMBUKTIKAN: sekumpulan tenant yang saling
    bertabrakan nama memicu banyak SAVEPOINT berurutan dalam satu
    transaksi dan gagal persis dengan pesan yang sama seperti produksi.

    Diperbaiki dengan MENGHILANGKAN subtransaksi sama sekali: setiap
    PERCOBAAN kandidat sekarang transaksi PENUH tersendiri (bukan
    savepoint di dalam transaksi bersama) -- berhasil = commit, bentrok
    (IntegrityError) = transaksi itu sendiri otomatis rollback (lewat
    db_compat.get_conn(), lihat modul itu) lalu kandidat berikutnya
    dicoba di transaksi BARU. Locknya dilepas SEPENUHNYA setelah setiap
    percobaan, tidak pernah menumpuk lintas tenant ATAU lintas percobaan
    manapun. Verifikasi keunikan TETAP langsung ke database setiap saat
    (sifat "coba lalu mundur" dari v2 dipertahankan, cuma batas
    transaksinya yang diperkecil) -- tidak bergantung pada kalkulasi di
    memori yang bisa basi kalau ada penulis lain.

    HOTFIX v4->v5 (produksi MACET TOTAL persis di UPDATE pertama fungsi ini
    -- dibuktikan lewat log bertahap: create_all() di atas SELESAI 1.38
    detik, lalu "_backfill_booking_slug(): N tenant total, M perlu
    backfill." tercatat, TAPI TIDAK ADA log apa pun sesudahnya, bahkan
    untuk tenant PERTAMA, sampai Render timeout -- tenant di database
    dikonfirmasi SEDIKIT, jadi bukan soal volume): pool sudah punya
    statement_timeout=30 detik (lihat db_compat.py) yang SEHARUSNYA
    membatalkan statement yang menunggu lock terlalu lama -- tapi diamnya
    log berlanjut JAUH melewati 30 detik itu tanpa error apa pun, artinya
    UPDATE ini menunggu SESUATU (kemungkinan besar row lock yang masih
    dipegang sesi basi dari percobaan deploy SEBELUMNYA yang gagal/
    dibatalkan tidak bersih) TANPA benar-benar dibatasi statement_timeout
    pada koneksi yang dipakai ulang ini.

    Diperbaiki dengan lock_timeout EKSPLISIT (perintah SQL biasa, dikirim
    langsung lewat koneksi yang sama -- TIDAK BISA diam-diam diabaikan
    seperti parameter startup) SEBELUM setiap percobaan UPDATE, dan
    percobaan yang gagal karena lock_timeout TIDAK dianggap fatal --
    backfill booking_slug untuk tenant LAMA bukan syarat aplikasi ini bisa
    boot (tenant BARU sudah dapat booking_slug langsung saat dibuat, lihat
    tenant_db.py::buat_tenant()) -- tenant itu dilewati untuk boot ini dan
    otomatis dicoba ulang di restart berikutnya (fungsi ini idempotent,
    lihat docstring modul), TIDAK PERNAH menghalangi seluruh aplikasi
    gagal start hanya karena satu baris tenant lama kebetulan sedang
    terkunci sesi lain.

    HOTFIX v5->v6 (produksi TETAP macet total di titik yang PERSIS SAMA
    walau commit 3639757 -- MERGE PR #86 yang membawa SET LOCAL
    lock_timeout eksplisit -- sudah dikonfirmasi live: dikonfirmasi lewat
    "Klik event deploy" oleh user, commit yang gagal MEMANG commit yang
    membawa fix itu. TIDAK ADA log "DILEWATI" atau log sukses apa pun
    sesudah "N tenant total, M perlu backfill." -- kalau SET LOCAL
    lock_timeout benar-benar terkirim, seharusnya SALAH SATU dari dua log
    itu muncul dalam <=5 detik. Diamnya berlanjut jauh melampaui itu,
    artinya macetnya BUKAN di eksekusi statement SQL yang tertahan lock
    (yang sudah dibatasi lock_timeout) -- macet SEBELUM statement itu
    sempat terkirim sama sekali lewat koneksi yang dipakai ulang dari
    pool (koneksi FISIK yang sama sudah dipakai lebih dari 15 kali
    berturut-turut sepanjang boot ini, di create_all() dan SELECT tenant
    di atas -- SATU-SATUNYA hal yang benar-benar baru di percobaan
    UPDATE pertama loop ini adalah: reuse koneksi pool YANG KE-SEKIAN
    KALINYA, bukan soal lock Postgres).

    Diperbaiki dengan BERHENTI memakai koneksi pool sama sekali di sini:
    setiap percobaan sekarang membuka koneksi psycopg2 BARU secara
    langsung (bukan db_compat.get_conn()/pool), dengan connect_timeout
    (mekanisme libpq paling dasar & paling teruji untuk membatasi fase
    KONEKSI -- BEDA dari options/SET LOCAL yang sudah terbukti dua kali
    tidak bisa diandalkan pada koneksi yang dipakai ulang), lalu ditutup
    eksplisit (TIDAK PERNAH dikembalikan ke pool) segera setelah dipakai.
    Ini menghilangkan variabel "koneksi lama yang entah kenapa bermasalah
    saat dipakai ulang" sama sekali dari persamaan, apa pun akar
    masalahnya persisnya. Kegagalan APA PUN pada satu percobaan (gagal
    konek, lock, bentrok kandidat, atau error lain yang tidak terduga)
    TIDAK PERNAH dianggap fatal -- backfill tenant lama tetap bukan
    syarat aplikasi ini bisa boot, tenant yang gagal cukup dilewati dan
    otomatis dicoba ulang di restart berikutnya."""
    import re

    import tenant_middleware  # import lokal: hindari import siklik

    with db_compat.get_conn() as conn:
        rows = conn.execute("SELECT id, slug, nama_barbershop, booking_slug FROM tenants").fetchall()

    _mulai = time.monotonic()
    _perlu_backfill = [r for r in rows if not r["booking_slug"]]
    _logger.info("[postgres_schema] _backfill_booking_slug(): %s tenant total, %s perlu backfill.",
                 len(rows), len(_perlu_backfill))

    for r in rows:
        if r["booking_slug"]:
            continue
        dasar = re.sub(r"[^a-z0-9]+", "", (r["nama_barbershop"] or r["slug"] or "").strip().lower()) or "toko"
        kandidat = dasar
        percobaan = 1
        while True:
            if kandidat in tenant_middleware.LABEL_BUKAN_TENANT:
                percobaan += 1
                kandidat = f"{dasar}{percobaan}"
                continue
            hasil = _coba_backfill_koneksi_baru(r["id"], kandidat)
            if hasil == "bentrok":
                percobaan += 1
                kandidat = f"{dasar}{percobaan}"
                continue
            if hasil == "dilewati":
                _logger.warning(
                    "[postgres_schema] _backfill_booking_slug(): tenant id=%s DILEWATI (%.2fs) -- lihat log "
                    "di atas untuk alasannya. TIDAK fatal, akan dicoba ulang otomatis di restart berikutnya.",
                    r["id"], time.monotonic() - _mulai,
                )
                break
            _logger.info("[postgres_schema] _backfill_booking_slug(): tenant id=%s -> booking_slug=%s (%.2fs).",
                         r["id"], kandidat, time.monotonic() - _mulai)
            break


def _coba_backfill_koneksi_baru(tenant_id: int, kandidat: str) -> str:
    """Satu percobaan UPDATE tenants.booking_slug lewat koneksi psycopg2
    yang BENAR-BENAR BARU (connect() langsung, BUKAN db_compat.get_conn()/
    pool) -- lihat docstring HOTFIX v5->v6 di _backfill_booking_slug() di
    atas untuk alasan lengkapnya. Koneksi ini SELALU ditutup di akhir
    (finally), TIDAK PERNAH dikembalikan ke pool mana pun.

    Return: "ok" (berhasil), "bentrok" (booking_slug ini sudah dipakai
    tenant lain, coba kandidat berikutnya), atau "dilewati" (gagal karena
    sebab lain -- koneksi timeout, lock timeout, atau error tak terduga
    apa pun -- TIDAK PERNAH melempar exception ke pemanggil, supaya SATU
    tenant yang bermasalah tidak pernah menggagalkan seluruh boot)."""
    import psycopg2
    import psycopg2.extras

    _t0 = time.monotonic()
    conn = None
    try:
        conn = psycopg2.connect(
            db_compat.DATABASE_URL,
            connect_timeout=10,
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
            options="-c lock_timeout=5000 -c statement_timeout=10000",
        )
        _logger.info("[postgres_schema] _backfill_booking_slug(): tenant id=%s koneksi baru didapat (%.2fs).",
                     tenant_id, time.monotonic() - _t0)
        cur = conn.cursor()
        # SET eksplisit sebagai pertahanan LAPIS KEDUA -- kalau parameter
        # `options` di atas (startup parameter) ternyata tidak berlaku di
        # lingkungan tertentu, perintah SQL biasa ini tidak bisa diam-diam
        # diabaikan dengan cara yang sama.
        cur.execute("SET lock_timeout = '5s'")
        cur.execute("SET statement_timeout = '10s'")
        cur.execute("UPDATE tenants SET booking_slug = %s WHERE id = %s", (kandidat, tenant_id))
        conn.commit()
        return "ok"
    except psycopg2.IntegrityError:
        return "bentrok"
    except Exception as e:
        _logger.warning(
            "[postgres_schema] _backfill_booking_slug(): tenant id=%s GAGAL (%.2fs) -- %s: %s",
            tenant_id, time.monotonic() - _t0, type(e).__name__, e,
        )
        return "dilewati"
    finally:
        if conn is not None:
            conn.close()
