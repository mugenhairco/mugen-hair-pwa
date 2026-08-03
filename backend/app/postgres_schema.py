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
import os
from datetime import datetime, timedelta

import db_compat

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
    "booking_metode_aktif": '["cash", "transfer"]',
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
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL,
    barber_id     INTEGER REFERENCES barbers(id),
    aktif         INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    tema          TEXT NOT NULL DEFAULT 'terang'
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

-- FONDASI Multi-Tenant Phase 4 (Billing & Payment Midtrans) -- lihat
-- billing_db.py (jalur SQLite) untuk penjelasan lengkap. `kode` TANPA
-- foreign key ke mana pun (dicocokkan ke tenant_subscriptions.package di
-- kode aplikasi, bukan di database), sama seperti tenant_id di tabel lain.
CREATE TABLE IF NOT EXISTS subscription_packages (
    id           SERIAL PRIMARY KEY,
    kode         TEXT NOT NULL UNIQUE,
    nama         TEXT NOT NULL,
    harga        INTEGER NOT NULL DEFAULT 0,
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
"""


def create_all():
    """Idempotent -- aman dipanggil tiap kali proses ini boot (sama seperti
    init_db() di jalur SQLite). TIDAK PERNAH menghapus/menimpa data yang
    sudah ada (CREATE TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING)."""
    with db_compat.get_conn() as conn:
        for statement in _TABLES.strip().split(";\n\n"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)

        # FONDASI Multi-Tenant Phase 1: tenant default (merepresentasikan
        # data produksi yang sudah berjalan) + backfill tenant_id untuk
        # baris yang belum punya (baris BARU setelah Phase 1 aktif sudah
        # diisi tenant_id-nya sendiri saat dibuat, jadi TIDAK ikut tertimpa
        # di sini -- lihat _TABEL_TENANT_LANGSUNG, WHERE tenant_id IS NULL).
        tenant_default_id = _pastikan_tenant_default(conn)
        for tabel in ("users", "barbers", "services", "produk", "pengeluaran",
                      "website_gallery", "bookings", "closed_slot", "toko_libur",
                      # FONDASI Multi-Tenant Phase 1.1 -- lihat ALTER TABLE di atas.
                      "pemasukan", "kas_saldo_awal", "kas_penyesuaian"):
            conn.execute(f"UPDATE {tabel} SET tenant_id = ? WHERE tenant_id IS NULL", (tenant_default_id,))

        # FONDASI Multi-Tenant Phase 1: salin (bukan pindah/hapus) SEMUA
        # baris `settings` LAMA (key polos, dari sebelum Phase 1 aktif) ke
        # bentuk ber-prefix tenant default -- WAJIB dijalankan SEBELUM
        # seeding default hardcode di bawah, supaya toko produksi yang
        # SUDAH mengustomisasi setting (mis. persentase_komisi diubah dari
        # 40 ke nilai lain) tidak diam-diam ter-reset ke nilai pabrik begitu
        # get_setting() mulai membaca key ber-prefix (lihat database.py).
        _migrasi_prefix_settings(conn, tenant_default_id)

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

        _normalisasi_urutan_service_kolisi(conn)
        _normalisasi_urutan_barber_kolisi(conn)
        _migrasi_subscription(conn)
        _migrasi_billing_packages(conn)


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
    dua file skema yang sudah terpisah sejak awal proyek ini (lihat db_compat.py)."""
    row = conn.execute("SELECT id FROM tenants WHERE slug = ?", (TENANT_DEFAULT_SLUG,)).fetchone()
    if row:
        return row["id"]
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO tenants (slug, nama_barbershop, status, created_at) VALUES (?, ?, 'aktif', ?)",
        (TENANT_DEFAULT_SLUG, TENANT_DEFAULT_NAMA, now),
    )
    return cur.lastrowid


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
