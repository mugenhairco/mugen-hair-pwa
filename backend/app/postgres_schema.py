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

import db_compat

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

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING", (key, value))
        for key, value in IDENTITAS_DEFAULT.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING", (key, value))
        for key, value in DEFAULT_BOOKING_SETTINGS.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING", (key, value))
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('bonus_customer_tiers', ?) ON CONFLICT DO NOTHING",
            (json.dumps(DEFAULT_BONUS_TIERS),),
        )

        jumlah_service = conn.execute("SELECT COUNT(*) AS n FROM services").fetchone()["n"]
        if jumlah_service == 0:
            for nama, harga, pakai_potongan in DEFAULT_SERVICES:
                conn.execute(
                    "INSERT INTO services (nama, harga, pakai_potongan_chemical) VALUES (?, ?, ?)",
                    (nama, harga, pakai_potongan),
                )

        for key in ("bonus_service_acuan_service_ids", "uang_harian_acuan_service_ids"):
            existing = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if existing is not None:
                continue
            placeholder = ", ".join("?" for _ in _SEED_ACUAN_NAMA)
            rows = conn.execute(f"SELECT id FROM services WHERE nama IN ({placeholder})", _SEED_ACUAN_NAMA).fetchall()
            service_ids = [r["id"] for r in rows]
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING",
                         (key, json.dumps(service_ids)))

        conn.execute("INSERT INTO kas_saldo_awal (id, saldo) VALUES (1, 0) ON CONFLICT DO NOTHING")
