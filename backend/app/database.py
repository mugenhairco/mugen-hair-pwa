"""
database.py
============
Satu-satunya tempat LOGIKA BISNIS untuk aplikasi MUGEN Hair Co.

ATURAN PENTING (jangan dilanggar saat maintenance):
- UI TIDAK BOLEH menghitung komisi / bonus / uang harian sendiri.
  UI hanya memanggil fungsi di file ini dan menampilkan hasilnya.
- TIDAK ADA nilai hardcode untuk aturan bisnis. Semua berasal dari tabel `settings`.
- database.py TIDAK berkomunikasi dengan Google API. Itu tugas sync.py.
"""

import json
import sqlite3
import os
from datetime import datetime, date
from contextlib import contextmanager

import db_compat
from db_compat import IntegrityError

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mugen_hair.db")

# Nama-nama service yang memakai skema komisi "Harga x Persentase" (tanpa potongan chemical)
SERVICE_TANPA_POTONGAN = {"Dry Cut", "Cut & Wash", "Hair Do", "Beard Trim", "Wet Shave"}

# REVISI: konstanta SERVICE_UANG_HARIAN (dulu di sini) DIHAPUS -- acuan
# service untuk Target Bonus Service dan syarat Uang Harian sekarang
# masing-masing pengaturan independen milik Owner lewat Setting > Bonus
# Service / Setting > Uang Harian (lihat get_bonus_service_acuan_ids() /
# get_uang_harian_acuan_ids() di bagian "ACUAN SERVICE" di bawah).

DEFAULT_SETTINGS = {
    "persentase_komisi": "40",          # dalam persen, misal 40 = 40%
    "potongan_modal_chemical": "15000", # rupiah, dikurangkan dari harga sebelum dikali komisi
    "uang_harian_barber": "50000",      # rupiah/hari untuk barber selain RAFIQ
    "uang_harian_rafiq": "75000",       # rupiah/hari khusus RAFIQ
    "bonus_kehadiran": "100000",        # rupiah/bulan jika syarat terpenuhi
    "maksimal_hari_libur": "2",         # hari/bulan, jika lebih dari ini bonus kehadiran = 0
    "target_bonus_customer": "60",      # jumlah customer/bulan untuk dapat bonus
    "nominal_bonus_customer": "150000", # rupiah/bulan jika target tercapai
    "maksimal_hari_libur_bonus_customer": "5",  # hari/bulan, syarat khusus utk Bonus Customer
    "potongan_bonus_customer_persen": "50",     # % potongan bonus customer jika hari libur > maksimal di atas
}


@contextmanager
def get_conn():
    """
    AUDIT SINKRONISASI (lihat README/CHANGELOG untuk detail lengkap):
    sebelumnya SQLite dibuka dengan mode jurnal default (rollback journal)
    dan tanpa busy_timeout eksplisit -- di bawah mode itu, SETIAP transaksi
    tulis mengunci SELURUH file database sehingga koneksi lain (baik mau
    membaca maupun menulis, dari device lain mana pun yang sedang memanggil
    API di saat bersamaan) harus menunggu, dan kalau menunggu lebih lama
    dari batas waktu default Python (5 detik) akan gagal dengan
    "database is locked" -- request itu gagal, dan kalau requestnya adalah
    GET yang dipanggil dengan useCache=true, frontend akan diam-diam jatuh
    ke data cache lokal yang lama (lihat js/api.js) alih-alih menunjukkan
    error, persis gejala "kadang sinkron kadang tidak" antar device.
    Diperbaiki dengan mode WAL (Write-Ahead Logging): penulis TIDAK
    memblokir pembaca (dan sebaliknya) sama sekali, hanya penulis-vs-penulis
    yang masih perlu bergiliran -- jauh lebih jarang terjadi untuk beban
    kerja aplikasi ini. busy_timeout dinaikkan ke 30 detik sebagai jaring
    pengaman tambahan untuk kasus penulis-vs-penulis yang tetap bisa terjadi
    (mis. dua device menyimpan transaksi persis di detik yang sama).

    TAHAP migrasi Postgres: kalau DATABASE_URL diisi, seluruh fungsi di file
    ini (dan auth_db.py/booking_db.py/dst yang memakai get_conn() yang sama
    ini) otomatis jalan di atas PostgreSQL lewat db_compat.get_conn(), tanpa
    satu baris pun di bawah sini perlu diubah -- lihat db_compat.py.
    """
    if db_compat.IS_POSTGRES:
        with db_compat.get_conn() as conn:
            yield conn
        return
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Buat semua tabel jika belum ada, dan isi setting default jika kosong.
    Aman dipanggil berulang kali (idempotent) — tidak akan menghapus data lama."""
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS barbers (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                nama     TEXT NOT NULL UNIQUE,
                is_rafiq INTEGER NOT NULL DEFAULT 0,
                aktif    INTEGER NOT NULL DEFAULT 1
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                nama                    TEXT NOT NULL UNIQUE,
                harga                   INTEGER NOT NULL,
                pakai_potongan_chemical INTEGER NOT NULL DEFAULT 0,
                aktif                   INTEGER NOT NULL DEFAULT 1
            )
        """)

        # --- MIGRASI skema lama (1 transaksi = 1 service) ke skema baru
        #     (1 transaksi = header, banyak service di transaksi_detail).
        #     Aman dipanggil berulang: hanya berjalan jika kolom lama masih terdeteksi.
        cols_lama = [r["name"] for r in c.execute("PRAGMA table_info(transaksi)").fetchall()]
        if "service_id" in cols_lama:
            c.execute("ALTER TABLE transaksi RENAME TO transaksi_migrasi_lama")
        else:
            cols_lama = []

        c.execute("""
            CREATE TABLE IF NOT EXISTS transaksi (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal          TEXT NOT NULL,   -- format YYYY-MM-DD
                barber_id        INTEGER NOT NULL,
                tips             INTEGER NOT NULL DEFAULT 0,
                catatan          TEXT,
                created_at       TEXT NOT NULL,
                updated_at       TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS transaksi_detail (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                transaksi_id     INTEGER NOT NULL,
                service_id       INTEGER NOT NULL,
                nama_service     TEXT NOT NULL,   -- disalin saat transaksi dibuat (histori aman walau service diubah/dihapus)
                harga            INTEGER NOT NULL,-- disalin saat transaksi dibuat
                jumlah           INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (transaksi_id) REFERENCES transaksi(id) ON DELETE CASCADE,
                FOREIGN KEY (service_id) REFERENCES services(id)
            )
        """)

        if cols_lama:
            # pindahkan tiap baris lama menjadi 1 header transaksi + 1 baris detail (jumlah=1),
            # id header dipertahankan sama supaya histori/link lama tetap konsisten.
            baris_lama = c.execute("SELECT * FROM transaksi_migrasi_lama").fetchall()
            for r in baris_lama:
                c.execute(
                    """INSERT INTO transaksi (id, tanggal, barber_id, tips, catatan, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (r["id"], r["tanggal"], r["barber_id"], r["tips"], r["catatan"],
                     r["created_at"], r["updated_at"]),
                )
                c.execute(
                    """INSERT INTO transaksi_detail (transaksi_id, service_id, nama_service, harga, jumlah)
                       VALUES (?, ?, ?, ?, 1)""",
                    (r["id"], r["service_id"], r["nama_service"], r["harga"]),
                )
            # tabel lama TIDAK dihapus (disimpan sebagai backup): transaksi_migrasi_lama

        c.execute("""
            CREATE TABLE IF NOT EXISTS absensi_libur (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id INTEGER NOT NULL,
                tanggal   TEXT NOT NULL,  -- format YYYY-MM-DD
                UNIQUE(barber_id, tanggal),
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS pengeluaran (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal    TEXT NOT NULL,   -- format YYYY-MM-DD
                keterangan TEXT NOT NULL,   -- untuk apa pengeluaran itu
                jumlah     INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS produk (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                nama   TEXT NOT NULL UNIQUE,
                aktif  INTEGER NOT NULL DEFAULT 1
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS produk_mutasi (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                produk_id  INTEGER NOT NULL,
                tanggal    TEXT NOT NULL,     -- format YYYY-MM-DD
                tipe       TEXT NOT NULL,     -- 'restock' atau 'jual'
                jumlah     INTEGER NOT NULL,  -- selalu positif, arah ditentukan oleh 'tipe'
                catatan    TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (produk_id) REFERENCES produk(id)
            )
        """)

        # isi setting default hanya jika belum ada key tersebut (tidak menimpa yang sudah diubah user)
        # "ON CONFLICT DO NOTHING" (tanpa target) -- dialek-netral, berlaku sama
        # persis dengan "INSERT OR IGNORE" di SQLite 3.24+ maupun PostgreSQL.
        for key, value in DEFAULT_SETTINGS.items():
            c.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING", (key, value))

        # seed service default (hanya jika tabel masih kosong)
        c.execute("SELECT COUNT(*) FROM services")
        if c.fetchone()[0] == 0:
            default_services = [
                ("Dry Cut", 35000, 0),
                ("Cut & Wash", 45000, 0),
                ("Hair Do", 60000, 0),
                ("Beard Trim", 25000, 0),
                ("Wet Shave", 30000, 0),
                ("Hair Coloring", 150000, 1),
                ("Smoothing", 250000, 1),
                ("Keratin Treatment", 300000, 1),
            ]
            c.executemany(
                "INSERT INTO services (nama, harga, pakai_potongan_chemical) VALUES (?, ?, ?)",
                default_services,
            )


# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------

def _kunci_tenant(tenant_id, key: str) -> str:
    """FONDASI Multi-Tenant Phase 1: `settings`/`file_asset` TIDAK mendapat
    kolom `tenant_id` baru (keduanya pakai `key TEXT PRIMARY KEY`, mengubah
    PRIMARY KEY di SQLite butuh membangun ulang tabel -- terlalu berisiko
    untuk tabel yang paling sering dibaca-tulis di aplikasi ini). Isolasi
    tenant dilakukan dengan menyisipkan tenant_id KE DALAM string key itu
    sendiri (mis. "1:persentase_komisi"), murni di lapisan Python.
    tenant_id=None mengembalikan key APA ADANYA (perilaku LAMA, sebelum
    Phase 1) -- lihat tenant_migrasi.py::_migrasi_prefix_settings() untuk
    migrasi satu-kali yang menyalin baris polos yang SUDAH ADA ke bentuk
    ber-prefix tenant default (bukan reset ke nilai pabrik)."""
    return f"{tenant_id}:{key}" if tenant_id is not None else key


def get_setting(key: str, default=None, tenant_id=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (_kunci_tenant(tenant_id, key),)).fetchone()
        return row["value"] if row else default


def get_all_settings(tenant_id=None) -> dict:
    """tenant_id diisi: hanya setting milik tenant itu (prefix dibuang dari
    key hasil). tenant_id=None: SEMUA baris apa adanya termasuk prefiknya --
    HANYA untuk kode lama/migrasi, endpoint API ber-login WAJIB mengisi
    tenant_id (lihat catatan _kunci_tenant())."""
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    if tenant_id is None:
        return {r["key"]: r["value"] for r in rows}
    prefix = f"{tenant_id}:"
    return {r["key"][len(prefix):]: r["value"] for r in rows if r["key"].startswith(prefix)}


def set_setting(key: str, value, tenant_id=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_kunci_tenant(tenant_id, key), str(value)),
        )


def set_settings_bulk(data: dict, tenant_id=None):
    """Update banyak setting sekaligus (dipakai oleh halaman Setting saat SIMPAN)."""
    with get_conn() as conn:
        for key, value in data.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_kunci_tenant(tenant_id, key), str(value)),
            )


def _setting_float(key: str, tenant_id=None) -> float:
    return float(get_setting(key, "0", tenant_id=tenant_id))


# ---------------------------------------------------------------------------
# BARBERS
# ---------------------------------------------------------------------------

def get_barbers(hanya_aktif=True, tenant_id=None):
    """HANYA baris jabatan='barber' -- Input Data, Dashboard, Rekap Bulanan,
    dan Booking publik semuanya lewat fungsi ini, jadi Karyawan non-barber
    (Kasir/OB/Kru) otomatis TIDAK PERNAH muncul di sini tanpa perlu guard
    tambahan di masing-masing pemanggil. Untuk daftar SEMUA karyawan
    (termasuk non-barber), lihat get_karyawan() di bawah.

    FONDASI Multi-Tenant Phase 1: `tenant_id` opsional (default None = tidak
    difilter, dipakai booking_db.public_barbers() yang sudah menyaring
    tenant di query TERPISAH -- lihat catatan di sana) supaya SATU baris
    WHERE tambahan ini TIDAK mengubah rumus/urutan hasil sama sekali,
    murni menyaring baris. Endpoint API ber-login WAJIB mengisi ini.

    BOOKING UI/UX #1 (bugfix, sama seperti get_services() di bawah): ORDER
    BY sebelumnya `nama` (alfabetis) -- diurutkan `urutan` dulu di sini
    (satu sumber kebenaran) supaya SELURUH pemanggil (termasuk yang belum
    sempat sortir ulang sendiri) otomatis mengikuti urutan Settings >
    Karyawan, bukan cuma yang sudah sortir ulang di sisi frontend."""
    with get_conn() as conn:
        q = "SELECT * FROM barbers WHERE jabatan = 'barber'"
        params = []
        if hanya_aktif:
            q += " AND aktif = 1"
        if tenant_id is not None:
            q += " AND tenant_id = ?"; params.append(tenant_id)
        q += " ORDER BY urutan, nama"
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_karyawan(hanya_aktif=True, tenant_id=None):
    """SEMUA karyawan (barber + Kasir/OB/Kru), tanpa filter jabatan --
    dipakai modul yang harus menampilkan seluruh karyawan (Slip Gaji,
    Kasbon, Reimburse, Izin & Cuti, filter Rekap Transaksi).
    `tenant_id`: lihat catatan di get_barbers()."""
    with get_conn() as conn:
        klausa = []
        params = []
        if hanya_aktif:
            klausa.append("aktif = 1")
        if tenant_id is not None:
            klausa.append("tenant_id = ?"); params.append(tenant_id)
        q = "SELECT * FROM barbers"
        if klausa:
            q += " WHERE " + " AND ".join(klausa)
        q += " ORDER BY urutan, nama"
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_barber(barber_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM barbers WHERE id = ?", (barber_id,)).fetchone()
        return dict(row) if row else None


def add_barber(nama: str, is_rafiq: bool = False, uang_harian: int = 0,
                jabatan: str = "barber", gaji_per_hari: int = 0, tenant_id: int = None):
    """BOOKING UI/UX #1 (bugfix, sama seperti add_service() di services.py):
    SEBELUMNYA `urutan` tidak pernah diisi di sini, jadi selalu memakai
    default kolom (0) -- begitu 2+ karyawan berbagi urutan=0, tombol ↑/↓ di
    Settings > Karyawan (yang menukar NILAI urutan dua baris bersebelahan)
    jadi tidak berefek (menukar 0 dengan 0). Sekarang karyawan baru selalu
    mendapat urutan berikutnya (MAX + 1, di-scope per tenant)."""
    with get_conn() as conn:
        if tenant_id is not None:
            urutan_maks = conn.execute(
                "SELECT COALESCE(MAX(urutan), -1) AS m FROM barbers WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()["m"]
        else:
            urutan_maks = conn.execute("SELECT COALESCE(MAX(urutan), -1) AS m FROM barbers").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO barbers (nama, is_rafiq, uang_harian, jabatan, gaji_per_hari, tenant_id, urutan) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nama.strip(), 1 if is_rafiq else 0, int(uang_harian), jabatan, int(gaji_per_hari), tenant_id, urutan_maks + 1),
        )
        return cur.lastrowid


def update_barber(barber_id: int, nama: str = None, is_rafiq: bool = None, aktif: bool = None,
                   uang_harian: int = None, jabatan: str = None, gaji_per_hari: int = None):
    fields, values = [], []
    if nama is not None:
        fields.append("nama = ?"); values.append(nama.strip())
    if is_rafiq is not None:
        fields.append("is_rafiq = ?"); values.append(1 if is_rafiq else 0)
    if aktif is not None:
        fields.append("aktif = ?"); values.append(1 if aktif else 0)
    if uang_harian is not None:
        fields.append("uang_harian = ?"); values.append(int(uang_harian))
    if jabatan is not None:
        fields.append("jabatan = ?"); values.append(jabatan)
    if gaji_per_hari is not None:
        fields.append("gaji_per_hari = ?"); values.append(int(gaji_per_hari))
    if not fields:
        return
    values.append(barber_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE barbers SET {', '.join(fields)} WHERE id = ?", values)


# ---------------------------------------------------------------------------
# SERVICES
# ---------------------------------------------------------------------------

def get_services(hanya_aktif=True, tenant_id=None):
    """`tenant_id`: lihat catatan di get_barbers().

    MAINTENANCE #1 (bugfix): ORDER BY sebelumnya `nama` (alfabetis) --
    Setting > Layanan dan halaman Booking sudah menyusun ulang di sisi
    frontend/Python memakai kolom `urutan` (lihat pages/pengaturan.js,
    routers/booking.py), TAPI Input Data (routers/input_data.py, endpoint
    /api/input-data/services) memakai hasil fungsi ini APA ADANYA tanpa
    sortir ulang, jadi dropdown-nya selalu alfabetis, mengabaikan urutan
    yang sudah diatur Owner. Diurutkan `urutan` dulu di sini (satu sumber
    kebenaran) supaya SELURUH pemanggil otomatis konsisten."""
    with get_conn() as conn:
        klausa = []
        params = []
        if hanya_aktif:
            klausa.append("aktif = 1")
        if tenant_id is not None:
            klausa.append("tenant_id = ?"); params.append(tenant_id)
        q = "SELECT * FROM services"
        if klausa:
            q += " WHERE " + " AND ".join(klausa)
        q += " ORDER BY urutan, nama"
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_service(service_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
        return dict(row) if row else None


def add_service(nama: str, harga: int, pakai_potongan_chemical: bool = None, tenant_id: int = None):
    """Jika pakai_potongan_chemical tidak diisi, otomatis ditentukan berdasarkan
    daftar 5 layanan utama (Dry Cut, Cut & Wash, Hair Do, Beard Trim, Wet Shave).

    MAINTENANCE #1 (bugfix): SEBELUMNYA `urutan` tidak pernah diisi di sini,
    jadi selalu memakai default kolom (0) -- begitu ada lebih dari satu
    layanan ber-urutan 0, tombol ↑/↓ (Setting > Layanan, menukar nilai
    urutan dua baris bersebelahan) jadi tidak berpengaruh (menukar 0
    dengan 0). Sekarang layanan baru selalu mendapat urutan berikutnya
    (MAX + 1, di-scope per tenant), sama seperti pola tambah_gallery_foto()
    di website_content.py."""
    if pakai_potongan_chemical is None:
        pakai_potongan_chemical = nama not in SERVICE_TANPA_POTONGAN
    with get_conn() as conn:
        if tenant_id is not None:
            urutan_maks = conn.execute(
                "SELECT COALESCE(MAX(urutan), -1) AS m FROM services WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()["m"]
        else:
            urutan_maks = conn.execute("SELECT COALESCE(MAX(urutan), -1) AS m FROM services").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO services (nama, harga, pakai_potongan_chemical, tenant_id, urutan) VALUES (?, ?, ?, ?, ?)",
            (nama.strip(), int(harga), 1 if pakai_potongan_chemical else 0, tenant_id, urutan_maks + 1),
        )
        return cur.lastrowid


def update_service(service_id: int, nama: str = None, harga: int = None,
                    pakai_potongan_chemical: bool = None, aktif: bool = None):
    fields, values = [], []
    if nama is not None:
        fields.append("nama = ?"); values.append(nama.strip())
    if harga is not None:
        fields.append("harga = ?"); values.append(int(harga))
    if pakai_potongan_chemical is not None:
        fields.append("pakai_potongan_chemical = ?"); values.append(1 if pakai_potongan_chemical else 0)
    if aktif is not None:
        fields.append("aktif = ?"); values.append(1 if aktif else 0)
    if not fields:
        return
    values.append(service_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE services SET {', '.join(fields)} WHERE id = ?", values)


def service_sudah_dipakai(service_id: int) -> bool:
    """True jika service pernah dipakai pada minimal satu baris transaksi_detail
    (baik transaksi masih ada maupun sudah lama)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM transaksi_detail WHERE service_id = ?", (service_id,)
        ).fetchone()
        return row["jumlah"] > 0


def hapus_service(service_id: int):
    """Hapus PERMANEN service dari database (bukan sekadar nonaktifkan).
    HANYA boleh dipanggil jika service tersebut belum pernah dipakai di transaksi
    manapun — supaya histori transaksi lama tidak kehilangan data/rusak.
    Jika sudah pernah dipakai, menolak dengan ValueError berisi pesan yang siap
    ditampilkan ke user (arahkan ke fitur Nonaktifkan Service)."""
    if service_sudah_dipakai(service_id):
        raise ValueError(
            "Service ini sudah digunakan pada transaksi dan tidak dapat dihapus. "
            "Silakan gunakan fitur Nonaktifkan Service."
        )
    with get_conn() as conn:
        conn.execute("DELETE FROM services WHERE id = ?", (service_id,))


# ---------------------------------------------------------------------------
# PERHITUNGAN KOMISI (per transaksi)
# ---------------------------------------------------------------------------

def hitung_komisi_service(harga: int, modal: int = 0, tenant_id=None) -> float:
    """
    REVISI Struktur Setting: Komisi = (Harga - Harga Modal) x Persentase Komisi.
    `modal` datang dari Harga Modal per-service (Setting > Layanan, kolom
    `services.modal`) -- default 0 kalau tidak diisi Owner (service dianggap
    tanpa biaya modal, komisi dihitung penuh dari Harga x Persentase).
    Menggantikan skema lama (nama service tertentu dikecualikan dari
    Potongan Modal Chemical global) -- lihat revisi_setting_migrasi.py untuk
    migrasi yang menjaga nominal komisi service yang sudah berjalan TIDAK
    berubah akibat pergantian skema ini.

    FONDASI Multi-Tenant Phase 1.1: `tenant_id` opsional -- persentase_komisi
    adalah setting PER TOKO (lihat _setting_float/_kunci_tenant), jadi tanpa
    ini fungsi selalu membaca persentase_komisi milik tenant DEFAULT
    (tenant_id=None) apa pun tenant transaksi/preview yang sedang dihitung.
    BUG Phase 1 yang diperbaiki di sini: komisi tenant lain sebelumnya
    memakai persentase komisi tenant default, bukan persentase tenant itu
    sendiri, begitu Owner tenant lain mengubah persentase_komisi miliknya.
    """
    persentase = _setting_float("persentase_komisi", tenant_id=tenant_id) / 100.0
    dasar = max(0, harga - modal)
    return round(dasar * persentase)


# ---------------------------------------------------------------------------
# TRANSAKSI (Input Data: SIMPAN & KOREKSI)
# ---------------------------------------------------------------------------

def _validasi_tanggal(tanggal: str):
    datetime.strptime(tanggal, "%Y-%m-%d")  # akan raise ValueError jika format salah


def _bersihkan_items(items):
    """Ambil hanya item dengan jumlah > 0 dari daftar {'service_id':.., 'jumlah':..}."""
    hasil = []
    for it in items or []:
        try:
            jumlah = int(it.get("jumlah", 0))
        except (TypeError, ValueError):
            jumlah = 0
        if jumlah > 0:
            hasil.append({"service_id": it["service_id"], "jumlah": jumlah})
    return hasil


def tambah_transaksi(tanggal: str, barber_id: int, items: list, tips: int = 0, catatan: str = None):
    """SIMPAN data baru. Selalu membuat header transaksi baru + baris transaksi_detail
    untuk setiap service yang jumlahnya > 0.
    `items` = list of {'service_id': int, 'jumlah': int}."""
    _validasi_tanggal(tanggal)
    valid_items = _bersihkan_items(items)
    if not valid_items:
        raise ValueError("Minimal satu service harus diisi jumlahnya (lebih dari 0).")

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO transaksi (tanggal, barber_id, tips, catatan, created_at) VALUES (?, ?, ?, ?, ?)",
            (tanggal, barber_id, int(tips), catatan, now),
        )
        transaksi_id = cur.lastrowid
        for it in valid_items:
            service = conn.execute("SELECT * FROM services WHERE id = ?", (it["service_id"],)).fetchone()
            if service is None:
                raise ValueError("Service tidak ditemukan")
            conn.execute(
                """INSERT INTO transaksi_detail (transaksi_id, service_id, nama_service, harga, jumlah)
                   VALUES (?, ?, ?, ?, ?)""",
                (transaksi_id, service["id"], service["nama"], service["harga"], it["jumlah"]),
            )
        return transaksi_id


def koreksi_transaksi(transaksi_id: int, tanggal: str = None, barber_id: int = None,
                       items: list = None, tips: int = None, catatan: str = None):
    """KOREKSI = update data lama. TIDAK PERNAH membuat transaksi baru.
    Jika `items` diisi, seluruh baris transaksi_detail lama diganti dengan yang baru
    (bukan ditambahkan), supaya hasil koreksi selalu mencerminkan input di form."""
    existing = get_transaksi(transaksi_id)
    if existing is None:
        raise ValueError("Transaksi tidak ditemukan")

    valid_items = None
    if items is not None:
        valid_items = _bersihkan_items(items)
        if not valid_items:
            raise ValueError("Minimal satu service harus diisi jumlahnya (lebih dari 0).")

    fields, values = [], []
    if tanggal is not None:
        _validasi_tanggal(tanggal)
        fields.append("tanggal = ?"); values.append(tanggal)
    if barber_id is not None:
        fields.append("barber_id = ?"); values.append(barber_id)
    if tips is not None:
        fields.append("tips = ?"); values.append(int(tips))
    if catatan is not None:
        fields.append("catatan = ?"); values.append(catatan)

    with get_conn() as conn:
        if fields:
            fields.append("updated_at = ?")
            values.append(datetime.now().isoformat(timespec="seconds"))
            values.append(transaksi_id)
            conn.execute(f"UPDATE transaksi SET {', '.join(fields)} WHERE id = ?", values)

        if valid_items is not None:
            conn.execute("DELETE FROM transaksi_detail WHERE transaksi_id = ?", (transaksi_id,))
            for it in valid_items:
                service = conn.execute("SELECT * FROM services WHERE id = ?", (it["service_id"],)).fetchone()
                if service is None:
                    raise ValueError("Service tidak ditemukan")
                conn.execute(
                    """INSERT INTO transaksi_detail (transaksi_id, service_id, nama_service, harga, jumlah)
                       VALUES (?, ?, ?, ?, ?)""",
                    (transaksi_id, service["id"], service["nama"], service["harga"], it["jumlah"]),
                )


def hapus_transaksi(transaksi_id: int):
    """Menghapus header transaksi. Seluruh baris transaksi_detail terkait ikut terhapus
    otomatis lewat ON DELETE CASCADE."""
    with get_conn() as conn:
        conn.execute("DELETE FROM transaksi WHERE id = ?", (transaksi_id,))


def _peta_modal_service(conn) -> dict:
    """Peta {service_id: modal} SEKALI ambil (tabel services kecil, jumlah layanan
    barbershop biasanya belasan) -- dipakai _lengkapi_transaksi/_lengkapi_transaksi_batch/
    hitung_preview_items supaya hitung_komisi_service() tidak perlu query per item."""
    return {r["id"]: (r["modal"] or 0) for r in conn.execute("SELECT id, modal FROM services").fetchall()}


def _tenant_id_barber(conn, barber_id) -> int | None:
    """FONDASI Multi-Tenant Phase 1.1: tenant pemilik satu barber (untuk
    diteruskan ke hitung_komisi_service, lihat _lengkapi_transaksi)."""
    if barber_id is None:
        return None
    row = conn.execute("SELECT tenant_id FROM barbers WHERE id = ?", (barber_id,)).fetchone()
    return row["tenant_id"] if row else None


def _peta_tenant_barber(conn, barber_ids) -> dict:
    """Versi batch dari _tenant_id_barber() -- {barber_id: tenant_id} SEKALI
    ambil, dipakai _lengkapi_transaksi_batch supaya tidak query per header."""
    ids = sorted({bid for bid in barber_ids if bid is not None})
    if not ids:
        return {}
    placeholder = ", ".join("?" for _ in ids)
    rows = conn.execute(f"SELECT id, tenant_id FROM barbers WHERE id IN ({placeholder})", ids).fetchall()
    return {r["id"]: r["tenant_id"] for r in rows}


def _lengkapi_transaksi(conn, header: dict) -> dict:
    """Tambahkan daftar item + total (harga, komisi) yang dihitung dari transaksi_detail
    ke satu dict header transaksi. Dipakai oleh get_transaksi & get_transaksi_list."""
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM transaksi_detail WHERE transaksi_id = ? ORDER BY id", (header["id"],)
    ).fetchall()]
    modal_map = _peta_modal_service(conn)
    tenant_id = _tenant_id_barber(conn, header.get("barber_id"))
    header["items"] = items
    header["jumlah_item"] = sum(it["jumlah"] for it in items)
    header["total_harga"] = sum(it["harga"] * it["jumlah"] for it in items)
    header["total_komisi"] = sum(
        hitung_komisi_service(it["harga"], modal_map.get(it["service_id"], 0), tenant_id=tenant_id) * it["jumlah"]
        for it in items
    )
    header["daftar_service"] = ", ".join(f"{it['nama_service']} x{it['jumlah']}" for it in items)
    return header


def _lengkapi_transaksi_batch(conn, headers: list) -> list:
    """Versi teroptimasi dari _lengkapi_transaksi() untuk BANYAK transaksi sekaligus:
    mengambil SEMUA transaksi_detail terkait dalam beberapa query saja (dikelompokkan
    per 500 id sekali ambil, karena SQLite membatasi jumlah parameter per query),
    bukan satu query per transaksi seperti sebelumnya. Hasil akhir tiap transaksi
    IDENTIK dengan _lengkapi_transaksi (rumus harga/komisi sama persis) — ini murni
    optimasi jumlah round-trip ke database, dipakai saat daftar transaksi bisa
    berjumlah banyak (mis. halaman Rekap Transaksi tanpa filter Bulan/Tahun)."""
    if not headers:
        return []
    ids = [h["id"] for h in headers]
    detail_per_transaksi = {tid: [] for tid in ids}
    CHUNK = 500
    for i in range(0, len(ids), CHUNK):
        potongan = ids[i:i + CHUNK]
        placeholder = ", ".join("?" for _ in potongan)
        rows = conn.execute(
            f"""SELECT * FROM transaksi_detail WHERE transaksi_id IN ({placeholder})
                ORDER BY transaksi_id, id""",
            potongan,
        ).fetchall()
        for r in rows:
            detail_per_transaksi[r["transaksi_id"]].append(dict(r))

    modal_map = _peta_modal_service(conn)  # SATU query untuk seluruh batch (bukan per transaksi)
    tenant_map = _peta_tenant_barber(conn, (h.get("barber_id") for h in headers))
    for header in headers:
        items = detail_per_transaksi.get(header["id"], [])
        tenant_id = tenant_map.get(header.get("barber_id"))
        header["items"] = items
        header["jumlah_item"] = sum(it["jumlah"] for it in items)
        header["total_harga"] = sum(it["harga"] * it["jumlah"] for it in items)
        header["total_komisi"] = sum(
            hitung_komisi_service(it["harga"], modal_map.get(it["service_id"], 0), tenant_id=tenant_id) * it["jumlah"]
            for it in items
        )
        header["daftar_service"] = ", ".join(f"{it['nama_service']} x{it['jumlah']}" for it in items)
    return headers


def get_transaksi(transaksi_id: int):
    """Mengembalikan satu transaksi lengkap dengan daftar service (items) dan totalnya."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM transaksi WHERE id = ?", (transaksi_id,)).fetchone()
        if row is None:
            return None
        return _lengkapi_transaksi(conn, dict(row))


def get_transaksi_list(tahun: int = None, bulan: int = None, barber_id: int = None,
                        tanggal: str = None, tanggal_mulai: str = None, tanggal_selesai: str = None,
                        limit: int = None, tenant_id: int = None):
    """Dipakai oleh Rekap, Dashboard, dan Laporan PDF. Urutan default: tanggal
    terbaru dulu. Setiap baris hasil = satu transaksi (kunjungan customer)
    lengkap dengan daftar service & totalnya (lihat _lengkapi_transaksi_batch).
    tanggal_mulai/tanggal_selesai (format 'YYYY-MM-DD', inklusif di kedua
    ujung) dipakai Laporan PDF untuk rentang tanggal bebas -- BEDA dari
    tahun/bulan (satu bulan/tahun penuh) yang dipakai Rekap.

    FONDASI Multi-Tenant Phase 1: `transaksi` TIDAK punya kolom tenant_id
    sendiri (tenant-scoped TRANSITIF lewat JOIN ke barbers, lihat
    tenant_migrasi.py) -- `tenant_id` opsional (default None = tidak
    difilter, PENTING untuk endpoint ber-login yang bisa menampilkan
    SEMUA barber sekaligus, mis. Rekap tanpa filter Barber)."""
    q = "SELECT t.*, b.nama AS nama_barber FROM transaksi t JOIN barbers b ON b.id = t.barber_id WHERE 1=1"
    params = []
    if tahun is not None:
        q += " AND t.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND t.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if barber_id is not None:
        q += " AND t.barber_id = ?"; params.append(barber_id)
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if tanggal is not None:
        q += " AND t.tanggal = ?"; params.append(tanggal)
    if tanggal_mulai is not None:
        q += " AND t.tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND t.tanggal <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY t.tanggal DESC, t.id DESC"
    if limit is not None:
        q += " LIMIT ?"; params.append(limit)
    with get_conn() as conn:
        headers = [dict(r) for r in conn.execute(q, params).fetchall()]
        return _lengkapi_transaksi_batch(conn, headers)


def hitung_preview_items(items: list, tenant_id=None) -> dict:
    """Dipakai oleh Input Data untuk menampilkan pratinjau total harga & komisi
    SEBELUM disimpan, tanpa UI menghitung apa pun sendiri.
    `items` = list of {'service_id': int, 'jumlah': int}.

    FONDASI Multi-Tenant Phase 1.1: `tenant_id` opsional -- endpoint ber-login
    (routers/input_data.py) WAJIB mengisi user["tenant_id"] supaya (1) service
    milik tenant lain tidak ikut dihitung (walau service_id ditebak/dikirim
    manual) dan (2) hitung_komisi_service memakai persentase_komisi milik
    tenant yang benar, bukan tenant default."""
    valid_items = _bersihkan_items(items)
    rincian = []
    total_harga = 0
    total_komisi = 0
    with get_conn() as conn:
        for it in valid_items:
            service = conn.execute("SELECT * FROM services WHERE id = ?", (it["service_id"],)).fetchone()
            if service is None:
                continue
            if tenant_id is not None and service["tenant_id"] != tenant_id:
                continue
            jumlah = it["jumlah"]
            komisi_satuan = hitung_komisi_service(service["harga"], service["modal"] or 0, tenant_id=tenant_id)
            subtotal = service["harga"] * jumlah
            komisi = komisi_satuan * jumlah
            total_harga += subtotal
            total_komisi += komisi
            rincian.append({
                "nama": service["nama"], "harga": service["harga"], "jumlah": jumlah,
                "subtotal": subtotal, "komisi": komisi,
            })
    return {"rincian": rincian, "total_harga": total_harga, "total_komisi": total_komisi}


# ---------------------------------------------------------------------------
# ABSENSI / HARI LIBUR (dipakai untuk Bonus Kehadiran)
# ---------------------------------------------------------------------------

def tandai_libur(barber_id: int, tanggal: str):
    _validasi_tanggal(tanggal)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO absensi_libur (barber_id, tanggal) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (barber_id, tanggal),
        )


def batalkan_libur(barber_id: int, tanggal: str):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM absensi_libur WHERE barber_id = ? AND tanggal = ?",
            (barber_id, tanggal),
        )


def get_hari_libur(barber_id: int, tahun: int, bulan: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS jumlah FROM absensi_libur
               WHERE barber_id = ? AND tanggal LIKE ?""",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%"),
        ).fetchone()
        return row["jumlah"]


def get_hari_libur_rentang(barber_id: int, tanggal_mulai: str, tanggal_selesai: str) -> int:
    """Versi rentang tanggal bebas dari get_hari_libur() di atas -- dipakai
    Laporan PDF (Laporan Transaksi dgn filter Dari/Sampai custom)."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS jumlah FROM absensi_libur
               WHERE barber_id = ? AND tanggal >= ? AND tanggal <= ?""",
            (barber_id, tanggal_mulai, tanggal_selesai),
        ).fetchone()
        return row["jumlah"]


# ---------------------------------------------------------------------------
# ACUAN SERVICE: BONUS SERVICE & UANG HARIAN (REVISI)
# Sebelumnya Target Bonus Service (tier bulanan) DAN syarat cair Uang Harian
# (>= 3 service/hari) SAMA-SAMA hardcode ke konstanta SERVICE_UANG_HARIAN =
# {"Dry Cut", "Cut & Wash"}. Revisi ini memisahkan jadi DUA pengaturan
# INDEPENDEN yang bisa diatur Owner sendiri lewat menu Setting > Bonus
# Service dan Setting > Uang Harian (masing-masing daftar service_id
# pilihan sendiri) -- mengubah salah satu TIDAK memengaruhi yang lain.
# Disimpan di tabel `settings` (JSON list of service id, dipilih lewat id
# bukan nama supaya tidak ikut berubah kalau nama service diedit
# belakangan). Nilai awal (di-seed lewat bonus_service_migrasi.py) SAMA
# PERSIS dengan konstanta lama supaya tidak ada perubahan perilaku sampai
# Owner sengaja mengubahnya.
# ---------------------------------------------------------------------------

def get_bonus_service_acuan_ids(tenant_id=None) -> list:
    raw = get_setting("bonus_service_acuan_service_ids", "[]", tenant_id=tenant_id)
    try:
        return [int(x) for x in json.loads(raw)] if raw else []
    except (TypeError, ValueError):
        return []


def set_bonus_service_acuan_ids(service_ids: list, tenant_id=None) -> None:
    bersih = sorted({int(x) for x in service_ids})
    set_setting("bonus_service_acuan_service_ids", json.dumps(bersih), tenant_id=tenant_id)


def get_bonus_service_acuan_nama(tenant_id=None) -> list:
    """Nama service acuan Bonus Service SAAT INI (mengikuti pilihan Owner di
    Setting > Bonus Service) -- dipakai frontend supaya label di Dashboard
    ('X service (...) bulan ini') tidak lagi hardcode 'Dry Cut + Cut & Wash'."""
    ids = get_bonus_service_acuan_ids(tenant_id=tenant_id)
    if not ids:
        return []
    placeholder = ", ".join("?" for _ in ids)
    with get_conn() as conn:
        rows = conn.execute(f"SELECT nama FROM services WHERE id IN ({placeholder}) ORDER BY nama", ids).fetchall()
        return [r["nama"] for r in rows]


def get_uang_harian_acuan_ids(tenant_id=None) -> list:
    raw = get_setting("uang_harian_acuan_service_ids", "[]", tenant_id=tenant_id)
    try:
        return [int(x) for x in json.loads(raw)] if raw else []
    except (TypeError, ValueError):
        return []


def set_uang_harian_acuan_ids(service_ids: list, tenant_id=None) -> None:
    bersih = sorted({int(x) for x in service_ids})
    set_setting("uang_harian_acuan_service_ids", json.dumps(bersih), tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# UANG HARIAN
# Dihitung dari service yang dipilih Owner lewat Setting > Uang Harian
# (get_uang_harian_acuan_ids, lihat komentar "ACUAN SERVICE" di atas), dan
# hanya jika di HARI itu jumlah service-service tsb (gabungan) minimal
# target_uang_harian_per_hari() (REVISI Struktur Setting: dulu hardcode 3,
# sekarang bisa diatur bebas Owner lewat Setting > Uang Harian -- default
# tetap 3 lewat revisi_setting_migrasi.py supaya nominal yang sedang
# berjalan TIDAK berubah sampai Owner sengaja menggantinya).
# REVISI: nominal harian sekarang per-barber (kolom barbers.uang_harian,
# diatur bebas oleh admin lewat menu Setting > Barber), BUKAN lagi dari dua
# setting global uang_harian_barber/uang_harian_rafiq berdasarkan is_rafiq
# (lihat revisi_bonus_migrasi.py untuk migrasi kolomnya).
# ---------------------------------------------------------------------------

def target_uang_harian_per_hari(tenant_id=None) -> int:
    return int(_setting_float("uang_harian_target_service_harian", tenant_id=tenant_id) or 3)


def hitung_uang_harian_per_hari(barber: dict, tanggal: str) -> int:
    """FONDASI Multi-Tenant Phase 1: tenant_id diambil dari `barber` yang
    sudah diterima fungsi ini (bukan parameter baru) -- lihat get_barbers()."""
    tenant_id = barber.get("tenant_id")
    acuan_ids = set(get_uang_harian_acuan_ids(tenant_id=tenant_id))
    target = target_uang_harian_per_hari(tenant_id=tenant_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT td.service_id, td.jumlah FROM transaksi_detail td
               JOIN transaksi t ON t.id = td.transaksi_id
               WHERE t.barber_id = ? AND t.tanggal = ?""",
            (barber["id"], tanggal),
        ).fetchall()
    jumlah_service_utama = sum(r["jumlah"] for r in rows if r["service_id"] in acuan_ids)
    if jumlah_service_utama < target:
        return 0
    return int(barber["uang_harian"] or 0)


def hitung_uang_harian_bulan(barber: dict, tahun: int, bulan: int) -> int:
    """Dioptimalkan (performa): SATU query untuk ambil seluruh transaksi_detail barber
    ini pada bulan tsb (bukan satu query terpisah PER HARI seperti sebelumnya), lalu
    dikelompokkan per tanggal di Python. Aturan tetap SAMA: Uang Harian hari itu cair
    hanya jika total service acuan (Setting > Uang Harian) hari itu >= target
    (lihat target_uang_harian_per_hari()), nominalnya dari kolom uang_harian milik
    barber itu sendiri (REVISI: per-barber, lihat komentar di atas
    hitung_uang_harian_per_hari)."""
    tenant_id = barber.get("tenant_id")
    acuan_ids = set(get_uang_harian_acuan_ids(tenant_id=tenant_id))
    target = target_uang_harian_per_hari(tenant_id=tenant_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT t.tanggal AS tanggal, td.service_id AS service_id, td.jumlah AS jumlah
               FROM transaksi_detail td JOIN transaksi t ON t.id = td.transaksi_id
               WHERE t.barber_id = ? AND t.tanggal LIKE ?""",
            (barber["id"], f"{tahun:04d}-{bulan:02d}-%"),
        ).fetchall()

    jumlah_per_hari = {}
    for r in rows:
        if r["service_id"] in acuan_ids:
            jumlah_per_hari[r["tanggal"]] = jumlah_per_hari.get(r["tanggal"], 0) + r["jumlah"]

    nominal = int(barber["uang_harian"] or 0)
    return sum(nominal for jumlah in jumlah_per_hari.values() if jumlah >= target)


def hitung_uang_harian_rentang(barber: dict, tanggal_mulai: str, tanggal_selesai: str) -> int:
    """Versi rentang tanggal bebas dari hitung_uang_harian_bulan() di atas --
    dipakai Laporan PDF (Laporan Transaksi dgn filter Dari/Sampai custom,
    BUKAN satu bulan kalender penuh). Aturan hitungnya SAMA PERSIS."""
    tenant_id = barber.get("tenant_id")
    acuan_ids = set(get_uang_harian_acuan_ids(tenant_id=tenant_id))
    target = target_uang_harian_per_hari(tenant_id=tenant_id)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT t.tanggal AS tanggal, td.service_id AS service_id, td.jumlah AS jumlah
               FROM transaksi_detail td JOIN transaksi t ON t.id = td.transaksi_id
               WHERE t.barber_id = ? AND t.tanggal >= ? AND t.tanggal <= ?""",
            (barber["id"], tanggal_mulai, tanggal_selesai),
        ).fetchall()

    jumlah_per_hari = {}
    for r in rows:
        if r["service_id"] in acuan_ids:
            jumlah_per_hari[r["tanggal"]] = jumlah_per_hari.get(r["tanggal"], 0) + r["jumlah"]

    nominal = int(barber["uang_harian"] or 0)
    return sum(nominal for jumlah in jumlah_per_hari.values() if jumlah >= target)


# ---------------------------------------------------------------------------
# BONUS CUSTOMER / TARGET BONUS SERVICE (bulanan)
# Syarat dapat Bonus Customer:
#   1. Jumlah service acuan (dipilih Owner lewat Setting > Bonus Service,
#      lihat get_bonus_service_acuan_ids/komentar "ACUAN SERVICE" di atas)
#      bulan itu mencapai SATU ATAU LEBIH tier target dari daftar
#      `bonus_customer_tiers` (Setting > Komisi & Bonus > Target Bonus
#      Service) -- bonus yang dipakai adalah dari tier TERTINGGI yang
#      tercapai (bertingkat, mis. 100 service -> Rp100.000, 115 service ->
#      Rp150.000, dst; kalau tercapai 120 service, dapat bonus tier 115
#      karena itu tier tertinggi yang masih terpenuhi).
#   2. Jumlah hari libur barber tsb bulan itu <= maksimal_hari_libur_bonus_customer.
#      - Jika hari libur melebihi batas ini, bonus TIDAK hangus, tapi dipotong
#        sebesar potongan_bonus_customer_persen (default 50%).
#      - Jika syarat #1 (tidak ada satu tier pun tercapai) tidak terpenuhi,
#        bonus tetap 0 berapa pun hari liburnya.
# REVISI: sebelumnya cuma SATU target (target_bonus_customer/
# nominal_bonus_customer) -- diganti daftar tier bertingkat yang bisa
# ditambah/diubah/dihapus admin lewat menu Setting, tanpa nilai hardcode
# apa pun (lihat get_bonus_customer_tiers/set_bonus_customer_tiers).
# ---------------------------------------------------------------------------

def get_jumlah_service_dry_cut_cut_wash_bulan(barber_id: int, tahun: int, bulan: int) -> int:
    """Total jumlah service ACUAN (dipilih Owner lewat Setting > Bonus Service,
    BUKAN lagi hardcode Dry Cut + Cut & Wash -- nama fungsi dipertahankan
    supaya pemanggil lain tidak perlu diubah) seorang barber dalam satu
    bulan. Dipakai sebagai acuan Target Service pada Bonus Customer."""
    acuan_ids = get_bonus_service_acuan_ids()
    if not acuan_ids:
        return 0
    placeholder = ", ".join("?" for _ in acuan_ids)
    with get_conn() as conn:
        row = conn.execute(
            f"""SELECT COALESCE(SUM(td.jumlah), 0) AS jumlah
                FROM transaksi_detail td JOIN transaksi t ON t.id = td.transaksi_id
                WHERE t.barber_id = ? AND t.tanggal LIKE ?
                AND td.service_id IN ({placeholder})""",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%", *acuan_ids),
        ).fetchone()
    return row["jumlah"]


def get_jumlah_service_bulan(barber_id: int, tahun: int, bulan: int) -> int:
    """Total jumlah SELURUH service (semua jenis) seorang barber dalam satu bulan."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(td.jumlah), 0) AS jumlah
               FROM transaksi_detail td JOIN transaksi t ON t.id = td.transaksi_id
               WHERE t.barber_id = ? AND t.tanggal LIKE ?""",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%"),
        ).fetchone()
    return row["jumlah"]


def get_rincian_service_bulan(barber_id: int, tahun: int, bulan: int) -> list:
    """Rincian jumlah per JENIS service (Dry Cut, Cut & Wash, dst) seorang barber
    dalam satu bulan. Dipakai kartu 'Service Bulan Ini' di Dashboard. Terurut dari
    yang jumlahnya paling banyak. Hanya service yang jumlahnya > 0 yang dikembalikan."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT td.nama_service AS nama_service, SUM(td.jumlah) AS jumlah
               FROM transaksi_detail td JOIN transaksi t ON t.id = td.transaksi_id
               WHERE t.barber_id = ? AND t.tanggal LIKE ?
               GROUP BY td.nama_service
               ORDER BY jumlah DESC, td.nama_service ASC""",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%"),
        ).fetchall()
    return [{"nama_service": r["nama_service"], "jumlah": r["jumlah"]} for r in rows]


def get_rincian_service_periode(tahun: int = None, bulan: int = None, barber_id: int = None,
                                 tanggal_mulai: str = None, tanggal_selesai: str = None,
                                 tenant_id: int = None) -> list:
    """Sama seperti get_rincian_service_bulan() di atas, TAPI lebih generik --
    barber_id OPSIONAL (kalau kosong, rincian digabung dari SEMUA barber) dan
    mendukung tanggal_mulai/tanggal_selesai sebagai alternatif tahun/bulan
    (rentang tanggal bebas). Dipakai ringkasan "Rincian" di PDF Rekap
    Transaksi (Tahap 15). Service yang jumlahnya 0 otomatis tidak pernah
    muncul (SUM cuma menghasilkan baris untuk service yang benar-benar
    pernah dipakai pada periode itu). `tenant_id`: lihat catatan di
    get_transaksi_list() -- JOIN ke barbers hanya ditambahkan kalau diisi."""
    q = """SELECT td.nama_service AS nama_service, SUM(td.jumlah) AS jumlah
           FROM transaksi_detail td JOIN transaksi t ON t.id = td.transaksi_id"""
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = t.barber_id"
    q += " WHERE 1=1"
    params = []
    if barber_id is not None:
        q += " AND t.barber_id = ?"; params.append(barber_id)
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if tahun is not None:
        q += " AND t.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND t.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal_mulai is not None:
        q += " AND t.tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND t.tanggal <= ?"; params.append(tanggal_selesai)
    q += " GROUP BY td.nama_service ORDER BY jumlah DESC, td.nama_service ASC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"nama_service": r["nama_service"], "jumlah": r["jumlah"]} for r in rows]


def get_rincian_service_rentang(tanggal_mulai: str, tanggal_selesai: str, barber_id: int = None,
                                 tenant_id: int = None) -> list:
    """Versi rentang tanggal bebas dari get_rincian_service_bulan() di atas --
    BEDA juga karena bisa LINTAS BARBER (barber_id=None = seluruh barber
    digabung), dipakai Laporan PDF > Laporan Transaksi untuk baris ringkasan
    'Total Jumlah per Service' di bawah tabel rekap. Sama seperti fungsi di
    atas: hanya service yang jumlahnya > 0 yang dikembalikan, terurut dari
    yang jumlahnya paling banyak. `tenant_id`: lihat catatan di
    get_transaksi_list() -- JOIN ke barbers hanya ditambahkan kalau diisi."""
    q = "SELECT td.nama_service AS nama_service, SUM(td.jumlah) AS jumlah FROM transaksi_detail td JOIN transaksi t ON t.id = td.transaksi_id"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = t.barber_id"
    q += " WHERE t.tanggal >= ? AND t.tanggal <= ?"
    params = [tanggal_mulai, tanggal_selesai]
    if barber_id is not None:
        q += " AND t.barber_id = ?"
        params.append(barber_id)
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"
        params.append(tenant_id)
    q += " GROUP BY td.nama_service ORDER BY jumlah DESC, td.nama_service ASC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{"nama_service": r["nama_service"], "jumlah": r["jumlah"]} for r in rows]


def get_bonus_customer_tiers(tenant_id=None) -> list:
    """Daftar tier {target, bonus} untuk Bonus Customer/Target Bonus Service,
    terurut naik berdasarkan target. Disimpan sebagai JSON di tabel
    `settings` (key 'bonus_customer_tiers', key-value generik yang sudah ada
    sejak Tahap 2) -- tidak perlu tabel baru."""
    raw = get_setting("bonus_customer_tiers", "[]", tenant_id=tenant_id)
    try:
        mentah = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        mentah = []
    hasil = []
    for t in mentah:
        try:
            hasil.append({"target": int(t["target"]), "bonus": int(t["bonus"])})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(hasil, key=lambda t: t["target"])


def set_bonus_customer_tiers(tiers: list, tenant_id=None) -> None:
    """Timpa PENUH daftar tier (dipakai lewat pengaturan_bonus.py, yang
    menjaga aturan tambah/ubah/hapus per-target). Validasi dasar di sini
    supaya data yang tersimpan selalu konsisten apa pun jalur pemanggilnya."""
    bersih = []
    target_terpakai = set()
    for t in tiers:
        target = int(t["target"])
        bonus = int(t["bonus"])
        if target <= 0:
            raise ValueError("Target service harus lebih dari 0.")
        if bonus < 0:
            raise ValueError("Nominal bonus tidak boleh negatif.")
        if target in target_terpakai:
            raise ValueError(f"Target {target} service sudah ada, tidak boleh duplikat.")
        target_terpakai.add(target)
        bersih.append({"target": target, "bonus": bonus})
    bersih.sort(key=lambda t: t["target"])
    set_setting("bonus_customer_tiers", json.dumps(bersih), tenant_id=tenant_id)


def hitung_bonus_customer(barber_id: int, tahun: int, bulan: int, hari_libur: int = None) -> dict:
    """FONDASI Multi-Tenant Phase 1: fungsi ini hanya menerima barber_id
    (bukan dict barber lengkap) -- tenant_id diambil lewat satu get_barber()
    tambahan di sini (bukan mengubah signature fungsi, dipanggil dari banyak
    tempat) supaya setting Bonus Customer (tiers/maksimal libur/potongan)
    yang dibaca konsisten milik tenant barber ini, bukan tenant lain."""
    barber = get_barber(barber_id)
    tenant_id = barber.get("tenant_id") if barber else None
    jumlah_service = get_jumlah_service_dry_cut_cut_wash_bulan(barber_id, tahun, bulan)
    tiers = get_bonus_customer_tiers(tenant_id=tenant_id)

    tier_tercapai = None
    tier_berikutnya = None
    for tier in tiers:  # sudah terurut naik dari get_bonus_customer_tiers()
        if jumlah_service >= tier["target"]:
            tier_tercapai = tier
        elif tier_berikutnya is None:
            tier_berikutnya = tier

    tercapai = tier_tercapai is not None
    nominal = tier_tercapai["bonus"] if tier_tercapai else 0

    if hari_libur is None:
        hari_libur = get_hari_libur(barber_id, tahun, bulan)
    maksimal_libur = int(_setting_float("maksimal_hari_libur_bonus_customer", tenant_id=tenant_id))
    potongan_persen = _setting_float("potongan_bonus_customer_persen", tenant_id=tenant_id) / 100.0
    libur_melebihi = hari_libur > maksimal_libur

    if not tercapai:
        bonus = 0
    elif libur_melebihi:
        bonus = round(nominal * (1 - potongan_persen))
    else:
        bonus = nominal

    # "target" untuk keperluan progress bar: tier BERIKUTNYA yang belum
    # tercapai (supaya progress % masuk akal, mis. "72/100 menuju tier
    # berikutnya"); kalau semua tier sudah tercapai, pakai tier tertinggi
    # (progress otomatis 100%+ -- maksimal tercapai).
    target_progress = (
        tier_berikutnya["target"] if tier_berikutnya
        else (tier_tercapai["target"] if tier_tercapai else 0)
    )

    return {
        "jumlah_service": jumlah_service,
        "nama_service_acuan": get_bonus_service_acuan_nama(),
        "tiers": tiers,
        "tier_tercapai": tier_tercapai,
        "tier_berikutnya": tier_berikutnya,
        "target": target_progress,
        "tercapai": tercapai,
        "hari_libur": hari_libur,
        "maksimal_hari_libur": maksimal_libur,
        "libur_melebihi": libur_melebihi,
        "potongan_persen": int(_setting_float("potongan_bonus_customer_persen")),
        "bonus": bonus,
    }


# ---------------------------------------------------------------------------
# RINGKASAN BULANAN (dipakai Dashboard & Rekap)
# ---------------------------------------------------------------------------

def get_ringkasan_barber_bulan(barber_id: int, tahun: int, bulan: int) -> dict:
    """
    Mengembalikan semua komponen pendapatan seorang barber untuk satu bulan.
    Total Pendapatan = Komisi + Tips + Uang Harian + Bonus Customer
    REVISI: Bonus Kehadiran dihapus total dari perhitungan/tampilan (lihat
    catatan revisi di README) -- tidak lagi ikut dijumlahkan di sini.
    """
    barber = get_barber(barber_id)
    if barber is None:
        raise ValueError("Barber tidak ditemukan")

    transaksi_bulan = get_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id)

    nilai_service = sum(t["total_harga"] for t in transaksi_bulan)
    tips = sum(t["tips"] for t in transaksi_bulan)
    komisi = sum(t["total_komisi"] for t in transaksi_bulan)
    uang_harian = hitung_uang_harian_bulan(barber, tahun, bulan)
    jumlah_service_bulan = get_jumlah_service_bulan(barber_id, tahun, bulan)
    rincian_service = get_rincian_service_bulan(barber_id, tahun, bulan)
    hari_libur = get_hari_libur(barber_id, tahun, bulan)
    bonus_customer = hitung_bonus_customer(barber_id, tahun, bulan, hari_libur=hari_libur)

    total_pendapatan = komisi + tips + uang_harian + bonus_customer["bonus"]

    return {
        "barber": barber,
        "tahun": tahun,
        "bulan": bulan,
        "jumlah_customer": len(transaksi_bulan),
        "jumlah_service_bulan": jumlah_service_bulan,
        "rincian_service": rincian_service,
        "nilai_service": nilai_service,
        "komisi": komisi,
        "tips": tips,
        "uang_harian": uang_harian,
        "bonus_customer": bonus_customer["bonus"],
        "bonus_customer_detail": bonus_customer,
        "total_pendapatan": total_pendapatan,
        "target_bonus_customer": bonus_customer["target"],
        "progress_target": (
            round(bonus_customer["jumlah_service"] / bonus_customer["target"] * 100, 1)
            if bonus_customer["target"] else 0
        ),
    }


def get_pendapatan_transaksi(transaksi: dict) -> int:
    """Pendapatan barber ATAS SATU transaksi = total komisi semua service di transaksi itu
    (transaksi_detail) + tips transaksi itu. (Uang harian & bonus dihitung level
    harian/bulanan, bukan per transaksi — dipakai Rekap untuk kolom 'Pendapatan' per baris
    transaksi.) `transaksi` harus berasal dari get_transaksi()/get_transaksi_list() supaya
    sudah memiliki field 'total_komisi'."""
    return transaksi["total_komisi"] + transaksi["tips"]


# ---------------------------------------------------------------------------
# LIBUR (dipakai utk keterangan "Libur" di Rekap Transaksi)
# ---------------------------------------------------------------------------

def get_libur_list(barber_id: int = None, tahun: int = None, bulan: int = None,
                    tanggal: str = None, tanggal_mulai: str = None, tanggal_selesai: str = None,
                    tenant_id: int = None) -> list:
    """tanggal_mulai/tanggal_selesai (inklusif di kedua ujung) dipakai Rekap
    Transaksi untuk periode PDF rentang tanggal bebas -- BEDA dari
    tahun/bulan (satu bulan/tahun penuh) yang dipakai tampilan layarnya.
    `tenant_id`: lihat catatan di get_transaksi_list() -- `absensi_libur`
    tenant-scoped TRANSITIF lewat JOIN ke barbers, hanya di-JOIN kalau
    tenant_id diisi (query tanpa tenant_id identik persis seperti sebelum
    Phase 1)."""
    q = "SELECT al.barber_id AS barber_id, al.tanggal AS tanggal FROM absensi_libur al"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = al.barber_id"
    q += " WHERE 1=1"
    params = []
    if barber_id is not None:
        q += " AND al.barber_id = ?"; params.append(barber_id)
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if tahun is not None:
        q += " AND al.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND al.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal is not None:
        q += " AND al.tanggal = ?"; params.append(tanggal)
    if tanggal_mulai is not None:
        q += " AND al.tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND al.tanggal <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY al.tanggal DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


# ---------------------------------------------------------------------------
# REKAP TRANSAKSI (gabungan) & REKAP BULANAN (dipakai halaman Rekap)
# Rekap Bulanan adalah AKUMULASI dari transaksi sebulan (termasuk total Uang
# Harian) per barber. Rekap Bulanan inilah yang menentukan dapat/tidaknya
# Bonus Customer (lihat hitung_bonus_customer di atas).
# ---------------------------------------------------------------------------

def get_rekap_transaksi_list(tahun: int = None, bulan: int = None, barber_id: int = None,
                              tanggal: str = None, tanggal_mulai: str = None,
                              tanggal_selesai: str = None, tenant_id: int = None) -> list:
    """Dipakai oleh halaman Rekap Transaksi. Satu baris = satu transaksi, DITAMBAH
    baris keterangan "Libur" untuk tanggal yang barber-nya ditandai libur di Input
    Data tapi tidak punya transaksi (supaya hari libur tetap kelihatan di rekap).
    Setiap baris transaksi juga membawa Uang Harian HARI itu (dihitung dari total
    service acuan Setting > Uang Harian hari itu, lihat hitung_uang_harian_per_hari)
    dan Jumlah Service (total qty seluruh service di transaksi itu). Urutan: tanggal
    terbaru dulu. tanggal_mulai/tanggal_selesai dipakai periode PDF rentang tanggal
    bebas -- BEDA dari tahun/bulan yang dipakai tampilan layar.

    Baris bertipe "transaksi" membawa "id" (primary key tabel transaksi) --
    dipakai tombol Hapus khusus Owner di halaman Rekap Transaksi (lihat
    routers/input_data.py hapus_transaksi(), endpoint yang sudah ada,
    dipakai ulang). Baris "libur"/hasil gabungan reimburse/kasbon TIDAK
    punya "id" ini -- sengaja, supaya frontend tahu baris mana yang boleh
    dihapus lewat endpoint itu."""
    transaksi_list = get_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id, tanggal=tanggal,
                                         tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
                                         tenant_id=tenant_id)
    libur_list = get_libur_list(barber_id=barber_id, tahun=tahun, bulan=bulan, tanggal=tanggal,
                                 tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
                                 tenant_id=tenant_id)
    libur_set = {(l["barber_id"], l["tanggal"]) for l in libur_list}

    barber_cache = {}
    def _barber(bid):
        if bid not in barber_cache:
            barber_cache[bid] = get_barber(bid)
        return barber_cache[bid]

    uang_harian_cache = {}
    def _uang_harian(bid, tgl):
        key = (bid, tgl)
        if key not in uang_harian_cache:
            uang_harian_cache[key] = hitung_uang_harian_per_hari(_barber(bid), tgl)
        return uang_harian_cache[key]

    hasil = []
    hari_dengan_transaksi = set()
    for t in transaksi_list:
        key = (t["barber_id"], t["tanggal"])
        hari_dengan_transaksi.add(key)
        # Keterangan: catatan manual (Input Data) + "Libur" (kalau hari yang
        # sama juga ditandai libur, kasus jarang tapi mungkin) digabung --
        # sebelumnya catatan TIDAK PERNAH muncul di Rekap Transaksi sama
        # sekali (field ini kosong terus kecuali "Libur").
        bagian_ket = []
        if (t.get("catatan") or "").strip():
            bagian_ket.append(t["catatan"].strip())
        if key in libur_set:
            bagian_ket.append("Libur")
        hasil.append({
            "tipe": "transaksi",
            "id": t["id"],
            "tanggal": t["tanggal"],
            "barber_id": t["barber_id"],
            "nama_barber": t["nama_barber"],
            "daftar_service": t["daftar_service"],
            "jumlah_service": sum(it["jumlah"] for it in t["items"]),
            "tips": t["tips"],
            "uang_harian": _uang_harian(t["barber_id"], t["tanggal"]),
            # REVISI Rekap Transaksi (Barber): "komisi" field TERPISAH dari
            # "pendapatan" (yang tetap komisi+tips apa adanya, TIDAK diubah --
            # dipakai layar Owner/Admin & PDF lama tanpa perubahan sama
            # sekali) supaya kolom Komisi baru khusus tampilan Barber bisa
            # ditampilkan tanpa menghitung ulang apa pun di frontend.
            "komisi": t["total_komisi"],
            "pendapatan": get_pendapatan_transaksi(t),
            "keterangan": "; ".join(bagian_ket),
        })

    for l in libur_list:
        key = (l["barber_id"], l["tanggal"])
        if key in hari_dengan_transaksi:
            continue  # sudah terwakili baris transaksi di atas (keterangan-nya sudah "Libur")
        barber = _barber(l["barber_id"])
        if barber is None:
            continue
        hasil.append({
            "tipe": "libur",
            "tanggal": l["tanggal"],
            "barber_id": l["barber_id"],
            "nama_barber": barber["nama"],
            "daftar_service": "",
            "jumlah_service": 0,
            "tips": 0,
            "uang_harian": 0,
            "pendapatan": 0,
            "keterangan": "Libur",
        })

    hasil.sort(key=lambda r: r["nama_barber"])
    hasil.sort(key=lambda r: r["tanggal"], reverse=True)
    return hasil


def get_rekap_bulanan_list(tahun: int, bulan: int, barber_id: int = None, tenant_id: int = None) -> list:
    """Satu baris = satu barber untuk satu bulan, akumulasi dari transaksi sebulan
    (termasuk total Uang Harian), lengkap dengan detail Bonus Customer (target
    berupa jumlah service acuan Setting > Bonus Service, dan syarat hari libur) yang
    menentukan bonus itu cair atau tidak."""
    barbers = [get_barber(barber_id)] if barber_id is not None else get_barbers(tenant_id=tenant_id)
    hasil = []
    for barber in barbers:
        if barber is None:
            continue
        ringkasan = get_ringkasan_barber_bulan(barber["id"], tahun, bulan)
        bonus_customer = ringkasan["bonus_customer_detail"]
        hasil.append({
            "tahun": tahun,
            "bulan": bulan,
            "barber_id": barber["id"],
            "nama_barber": barber["nama"],
            "jumlah_service": ringkasan["jumlah_service_bulan"],
            "total_komisi": ringkasan["komisi"],
            "tips": ringkasan["tips"],
            "uang_harian": ringkasan["uang_harian"],
            "hari_libur": bonus_customer["hari_libur"],
            "maksimal_hari_libur_bonus_customer": bonus_customer["maksimal_hari_libur"],
            "libur_melebihi": bonus_customer["libur_melebihi"],
            "target_service": bonus_customer["target"],
            "jumlah_service_dc_cw": bonus_customer["jumlah_service"],
            "target_tercapai": bonus_customer["tercapai"],
            "bonus_customer": ringkasan["bonus_customer"],
            "total_pendapatan": ringkasan["total_pendapatan"],
        })
    return hasil


def get_laporan_transaksi_rekap(tanggal_mulai: str, tanggal_selesai: str, barber_id: int = None,
                                 tenant_id: int = None) -> list:
    """Satu baris = satu barber, akumulasi dari transaksi pada RENTANG TANGGAL
    BEBAS (dipakai Laporan PDF > Laporan Transaksi -- BEDA dari
    get_rekap_bulanan_list() di atas yang selalu satu bulan kalender penuh,
    dan formatnya juga beda: Laporan Transaksi tidak lagi satu baris per
    kunjungan customer, tapi dirangkum per barber untuk seluruh periode).
    'catatan_list' = daftar {'tanggal','catatan'} dari catatan manual per
    transaksi yang diisi Owner/Admin lewat Input Data (kolom 'catatan' yang
    sudah ada di tabel transaksi, lihat tambah_transaksi()/update_transaksi())
    -- format tampilannya (gabung jadi satu teks kolom Ket) diserahkan ke
    laporan_pdf.py, di sini murni data mentah apa adanya. 'total' = Komisi +
    Tips + Uang Harian."""
    barbers = [get_barber(barber_id)] if barber_id is not None else get_barbers(tenant_id=tenant_id)
    hasil = []
    for barber in barbers:
        if barber is None:
            continue
        transaksi_list = get_transaksi_list(
            tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai, barber_id=barber["id"],
        )
        komisi = sum(t["total_komisi"] for t in transaksi_list)
        tips = sum(t["tips"] for t in transaksi_list)
        uang_harian = hitung_uang_harian_rentang(barber, tanggal_mulai, tanggal_selesai)
        hari_libur = get_hari_libur_rentang(barber["id"], tanggal_mulai, tanggal_selesai)
        # get_transaksi_list() urutannya tanggal TERBARU dulu (lihat docstring-nya) --
        # dibalik di sini supaya catatan di kolom Ket terbaca kronologis (tanggal
        # tertua dulu), bukan mundur.
        catatan_list = sorted(
            (
                {"tanggal": t["tanggal"], "catatan": t["catatan"].strip()}
                for t in transaksi_list if (t.get("catatan") or "").strip()
            ),
            key=lambda c: c["tanggal"],
        )
        hasil.append({
            "barber_id": barber["id"],
            "nama_barber": barber["nama"],
            "komisi": komisi,
            "tips": tips,
            "uang_harian": uang_harian,
            "hari_libur": hari_libur,
            "total": komisi + tips + uang_harian,
            "catatan_list": catatan_list,
        })
    return hasil


# ---------------------------------------------------------------------------
# PENGELUARAN
# Dicatat terpisah dari transaksi barber (bukan komisi/bonus siapa pun) —
# ini pengeluaran operasional toko (mis. beli bahan, listrik, dll).
# ---------------------------------------------------------------------------

def tambah_pengeluaran(tanggal: str, keterangan: str, jumlah: int, tenant_id: int = None) -> int:
    _validasi_tanggal(tanggal)
    keterangan = (keterangan or "").strip()
    if not keterangan:
        raise ValueError("Keterangan pengeluaran tidak boleh kosong.")
    if jumlah is None or jumlah < 0:
        raise ValueError("Jumlah pengeluaran harus diisi dan tidak boleh negatif.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pengeluaran (tanggal, keterangan, jumlah, created_at, tenant_id) VALUES (?, ?, ?, ?, ?)",
            (tanggal, keterangan, int(jumlah), now, tenant_id),
        )
        return cur.lastrowid


def koreksi_pengeluaran(pengeluaran_id: int, tanggal: str, keterangan: str, jumlah: int):
    _validasi_tanggal(tanggal)
    keterangan = (keterangan or "").strip()
    if not keterangan:
        raise ValueError("Keterangan pengeluaran tidak boleh kosong.")
    if jumlah is None or jumlah < 0:
        raise ValueError("Jumlah pengeluaran harus diisi dan tidak boleh negatif.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "UPDATE pengeluaran SET tanggal = ?, keterangan = ?, jumlah = ?, updated_at = ? WHERE id = ?",
            (tanggal, keterangan, int(jumlah), now, pengeluaran_id),
        )


def hapus_pengeluaran(pengeluaran_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM pengeluaran WHERE id = ?", (pengeluaran_id,))


def get_pengeluaran(pengeluaran_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pengeluaran WHERE id = ?", (pengeluaran_id,)).fetchone()
        return dict(row) if row else None


def get_pengeluaran_list(tahun: int = None, bulan: int = None, tanggal: str = None,
                          tenant_id: int = None) -> list:
    """Urutan: tanggal terbaru dulu."""
    q = "SELECT * FROM pengeluaran WHERE 1=1"
    params = []
    if tahun is not None:
        q += " AND tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal is not None:
        q += " AND tanggal = ?"; params.append(tanggal)
    if tenant_id is not None:
        q += " AND tenant_id = ?"; params.append(tenant_id)
    q += " ORDER BY tanggal DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]


def get_total_pengeluaran(tahun: int = None, bulan: int = None, tenant_id: int = None) -> int:
    return sum(p["jumlah"] for p in get_pengeluaran_list(tahun=tahun, bulan=bulan, tenant_id=tenant_id))


# ---------------------------------------------------------------------------
# PRODUK (penjualan, restock, sisa stok)
#
# Stok TIDAK disimpan sebagai angka tunggal yang diubah langsung — supaya tidak
# pernah "nyasar"/tidak sinkron. Stok selalu DIHITUNG ULANG dari riwayat mutasi
# (produk_mutasi): sisa stok = total 'restock' - total 'jual'.
#
# Setiap kali ada mutasi baru/diubah/dihapus, sistem mensimulasikan SALDO
# STOK SECARA KRONOLOGIS (urut tanggal) dan MENOLAK perubahan apa pun yang akan
# membuat saldo negatif di titik manapun — bukan cuma di akhir. Ini mencegah,
# misalnya, menghapus data restock lama padahal stoknya sudah kepakai buat
# penjualan sesudahnya.
# ---------------------------------------------------------------------------

def _ambil_semua_mutasi(conn, produk_id: int) -> list:
    rows = conn.execute(
        "SELECT id, tanggal, tipe, jumlah FROM produk_mutasi WHERE produk_id = ?",
        (produk_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _saldo_valid(mutasi_list: list) -> bool:
    """True jika saldo stok TIDAK PERNAH negatif di titik manapun, dihitung
    berurutan berdasarkan tanggal (lalu id sebagai tie-breaker).

    CATATAN PENTING (bug fix): baris baru yang belum tersimpan (id masih None,
    mis. saat jual_produk() mengecek transaksi yang SEDANG mau disimpan) harus
    dianggap terjadi PALING TERAKHIR di antara mutasi lain pada tanggal yang
    sama — bukan paling awal. Kalau id=None disamakan dengan 0 (kode lama),
    baris baru itu malah diurutkan SEBELUM restock lain yang sudah ada di
    tanggal yang sama (karena id asli di database mulai dari 1 ke atas),
    sehingga penjualan dianggap terjadi SEBELUM stoknya masuk -> saldo
    dihitung negatif padahal total stok sebenarnya cukup. Inilah yang
    menyebabkan penjualan ditolak keliru meski 'Sisa stok saat ini' yang
    ditampilkan sudah mencukupi."""
    urutan = sorted(
        mutasi_list,
        key=lambda r: (r["tanggal"], r.get("id") if r.get("id") is not None else float("inf")),
    )
    saldo = 0
    for r in urutan:
        saldo += r["jumlah"] if r["tipe"] == "restock" else -r["jumlah"]
        if saldo < 0:
            return False
    return True


def tambah_produk(nama: str, harga_modal: int = 0, harga_jual: int = 0, tenant_id: int = None) -> int:
    """FONDASI Multi-Tenant Phase 1: kolom `nama` MASIH unik GLOBAL (belum
    dilonggarkan per-tenant seperti barbers/services/users -- di luar
    sembilan tabel yang diaudit eksplisit butuh itu) -- dua tenant BELUM
    bisa sama-sama punya produk bernama sama persis, keterbatasan yang
    diketahui & didokumentasikan, BUKAN kebocoran data (baris tetap
    kepunyaan tenant masing-masing lewat tenant_id di bawah)."""
    nama = (nama or "").strip()
    if not nama:
        raise ValueError("Nama produk tidak boleh kosong.")
    if harga_modal < 0 or harga_jual < 0:
        raise ValueError("Harga tidak boleh negatif.")
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO produk (nama, harga_modal, harga_jual, tenant_id) VALUES (?, ?, ?, ?)",
                (nama, int(harga_modal), int(harga_jual), tenant_id),
            )
        except IntegrityError:
            raise ValueError(f"Produk dengan nama '{nama}' sudah ada.")
        return cur.lastrowid


def update_produk(produk_id: int, nama: str = None, harga_modal: int = None, harga_jual: int = None):
    """REVISI: sebelumnya update_nama_produk() (hanya nama) -- diperluas jadi
    update parsial (nama/harga_modal/harga_jual semuanya opsional) supaya
    Owner bisa mengubah harga tanpa mengubah nama, atau sebaliknya, lewat
    SATU form yang sama di menu Produk."""
    fields, values = [], []
    if nama is not None:
        nama = nama.strip()
        if not nama:
            raise ValueError("Nama produk tidak boleh kosong.")
        fields.append("nama = ?"); values.append(nama)
    if harga_modal is not None:
        if harga_modal < 0:
            raise ValueError("Harga Modal tidak boleh negatif.")
        fields.append("harga_modal = ?"); values.append(int(harga_modal))
    if harga_jual is not None:
        if harga_jual < 0:
            raise ValueError("Harga Jual tidak boleh negatif.")
        fields.append("harga_jual = ?"); values.append(int(harga_jual))
    if not fields:
        return
    values.append(produk_id)
    with get_conn() as conn:
        try:
            conn.execute(f"UPDATE produk SET {', '.join(fields)} WHERE id = ?", values)
        except IntegrityError:
            raise ValueError(f"Produk dengan nama '{nama}' sudah ada.")


def nonaktifkan_produk(produk_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE produk SET aktif = 0 WHERE id = ?", (produk_id,))


def get_produk(produk_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM produk WHERE id = ?", (produk_id,)).fetchone()
        return dict(row) if row else None


def get_stok_produk(produk_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN tipe = 'restock' THEN jumlah ELSE -jumlah END), 0) AS stok
               FROM produk_mutasi WHERE produk_id = ?""",
            (produk_id,),
        ).fetchone()
        return row["stok"]


def get_produk_list(hanya_aktif: bool = True, tenant_id: int = None) -> list:
    """Setiap produk disertai 'stok' (sisa stok saat ini, hasil hitung ulang)."""
    with get_conn() as conn:
        klausa = []
        params = []
        if hanya_aktif:
            klausa.append("aktif = 1")
        if tenant_id is not None:
            klausa.append("tenant_id = ?"); params.append(tenant_id)
        q = "SELECT * FROM produk"
        if klausa:
            q += " WHERE " + " AND ".join(klausa)
        q += " ORDER BY nama ASC"
        produk_rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        for p in produk_rows:
            p["stok"] = get_stok_produk(p["id"])
        return produk_rows


def restock_produk(produk_id: int, tanggal: str, jumlah: int, catatan: str = None) -> int:
    """Restock = satu-satunya cara menambah stok. Selalu aman (tidak mungkin
    membuat saldo negatif), jadi tidak perlu divalidasi kronologis."""
    _validasi_tanggal(tanggal)
    if jumlah is None or jumlah <= 0:
        raise ValueError("Jumlah restock harus lebih dari 0.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO produk_mutasi (produk_id, tanggal, tipe, jumlah, catatan, created_at)
               VALUES (?, ?, 'restock', ?, ?, ?)""",
            (produk_id, tanggal, int(jumlah), catatan, now),
        )
        return cur.lastrowid


def _catat_keluar_produk(produk_id: int, tanggal: str, jumlah: int, tipe: str,
                          catatan: str = None, kata_kerja: str = "dipakai") -> int:
    """Dipakai bersama oleh jual_produk() dan tester_produk() -- keduanya
    MENGURANGI stok dan divalidasi kronologis dengan cara SAMA PERSIS (lihat
    get_stok_produk/_saldo_valid: tipe apa pun SELAIN 'restock' otomatis
    dihitung mengurangi stok, jadi 'tester' bekerja tanpa perlu ubah logika
    saldo sama sekali). Harga modal/jual produk SAAT INI ikut disimpan
    (snapshot) di baris mutasi supaya laporan omzet (get_omzet_penjualan_produk,
    hanya menjumlahkan tipe='jual') bulan lalu TIDAK berubah kalau harga
    produk diedit belakangan."""
    _validasi_tanggal(tanggal)
    if jumlah is None or jumlah <= 0:
        raise ValueError("Jumlah harus lebih dari 0.")
    produk = get_produk(produk_id)
    with get_conn() as conn:
        mutasi = _ambil_semua_mutasi(conn, produk_id)
        mutasi.append({"id": None, "tanggal": tanggal, "tipe": tipe, "jumlah": int(jumlah)})
        if not _saldo_valid(mutasi):
            stok_sekarang = get_stok_produk(produk_id)
            raise ValueError(
                f"Stok tidak mencukupi. Sisa stok saat ini: {stok_sekarang}, "
                f"jumlah yang mau {kata_kerja}: {jumlah}."
            )
        now = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            """INSERT INTO produk_mutasi
               (produk_id, tanggal, tipe, jumlah, catatan, created_at,
                harga_modal_saat_itu, harga_jual_saat_itu)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (produk_id, tanggal, tipe, int(jumlah), catatan, now,
             produk["harga_modal"], produk["harga_jual"]),
        )
        return cur.lastrowid


def jual_produk(produk_id: int, tanggal: str, jumlah: int, catatan: str = None) -> int:
    """Penjualan = mengurangi stok DAN menambah omzet (lihat
    get_omzet_penjualan_produk). DITOLAK kalau membuat saldo stok jadi
    negatif di titik manapun secara kronologis (bukan cuma dicek di akhir)."""
    return _catat_keluar_produk(produk_id, tanggal, jumlah, "jual", catatan, kata_kerja="dijual")


def tester_produk(produk_id: int, tanggal: str, jumlah: int, catatan: str = None) -> int:
    """Tester = mengurangi stok SAMA PERSIS seperti Jual (dipakai untuk
    dicoba customer, sample, dsb), TAPI TIDAK menambah nilai penjualan --
    get_omzet_penjualan_produk() hanya menjumlahkan tipe='jual', tipe
    'tester' sengaja dilewati. Tetap tercatat penuh di riwayat mutasi
    (GET /api/produk/mutasi) seperti tipe lainnya."""
    return _catat_keluar_produk(produk_id, tanggal, jumlah, "tester", catatan, kata_kerja="dipakai tester")


def koreksi_mutasi_produk(mutasi_id: int, tanggal: str, jumlah: int, catatan: str = None):
    """Mengoreksi tanggal/jumlah/catatan sebuah mutasi (tipe restock/jual TIDAK berubah).
    DITOLAK kalau perubahan ini membuat saldo stok jadi negatif di titik manapun."""
    _validasi_tanggal(tanggal)
    if jumlah is None or jumlah <= 0:
        raise ValueError("Jumlah harus lebih dari 0.")
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM produk_mutasi WHERE id = ?", (mutasi_id,)).fetchone()
        if existing is None:
            raise ValueError("Data mutasi tidak ditemukan.")
        produk_id = existing["produk_id"]

        mutasi = _ambil_semua_mutasi(conn, produk_id)
        for m in mutasi:
            if m["id"] == mutasi_id:
                m["tanggal"] = tanggal
                m["jumlah"] = int(jumlah)
        if not _saldo_valid(mutasi):
            raise ValueError(
                "Perubahan ini akan membuat saldo stok menjadi negatif pada suatu tanggal "
                "(kemungkinan ada penjualan lain yang bergantung pada stok ini). Tidak disimpan."
            )

        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE produk_mutasi SET tanggal = ?, jumlah = ?, catatan = ?, updated_at = ? WHERE id = ?",
            (tanggal, int(jumlah), catatan, now, mutasi_id),
        )


def hapus_mutasi_produk(mutasi_id: int):
    """DITOLAK kalau menghapus mutasi ini membuat saldo stok jadi negatif pada
    suatu tanggal (mis. menghapus restock lama padahal stoknya sudah kepakai)."""
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM produk_mutasi WHERE id = ?", (mutasi_id,)).fetchone()
        if existing is None:
            return
        produk_id = existing["produk_id"]

        mutasi = [m for m in _ambil_semua_mutasi(conn, produk_id) if m["id"] != mutasi_id]
        if not _saldo_valid(mutasi):
            raise ValueError(
                "Data ini tidak bisa dihapus karena akan membuat saldo stok menjadi negatif "
                "pada suatu tanggal (kemungkinan ada penjualan lain yang bergantung pada stok ini)."
            )
        conn.execute("DELETE FROM produk_mutasi WHERE id = ?", (mutasi_id,))


def get_mutasi_produk(mutasi_id: int):
    """FONDASI Multi-Tenant Phase 1: `p.tenant_id` ikut disertakan (produk_mutasi
    sendiri TIDAK punya kolom tenant_id -- tenant-scoped TRANSITIF lewat JOIN
    ke produk, lihat tenant_migrasi.py) supaya router bisa memverifikasi
    kepemilikan tenant lewat fetch-then-authorize tanpa query tambahan."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT pm.*, p.nama AS nama_produk, p.tenant_id AS tenant_id FROM produk_mutasi pm
               JOIN produk p ON p.id = pm.produk_id WHERE pm.id = ?""",
            (mutasi_id,),
        ).fetchone()
        return dict(row) if row else None


def get_mutasi_produk_list(produk_id: int = None, tipe: str = None,
                            tahun: int = None, bulan: int = None, tenant_id: int = None) -> list:
    """Urutan: tanggal terbaru dulu. Ikut menyertakan nama_produk supaya UI tidak
    perlu join sendiri. `tenant_id`: lihat catatan di get_mutasi_produk().

    REVISI Branding Rivoir (Produk PDF): tiap baris juga disertai
    `sisa_stok` -- SISA STOK PRODUK ITU SAAT INI (sama seperti kolom "Sisa
    Stok" di get_produk_list(), BUKAN saldo berjalan setelah transaksi itu
    -- kolom "Sisa Stok" di seluruh halaman Produk sudah konsisten berarti
    stok terkini, jadi baris riwayat mutasi mengikuti arti yang sama supaya
    tidak ada dua makna "Sisa Stok" berbeda di halaman yang sama). Dihitung
    ulang PER produk_id (di-cache di sini) supaya produk dengan banyak
    baris mutasi tidak memicu query berulang."""
    q = """SELECT pm.*, p.nama AS nama_produk FROM produk_mutasi pm
           JOIN produk p ON p.id = pm.produk_id WHERE 1=1"""
    params = []
    if produk_id is not None:
        q += " AND pm.produk_id = ?"; params.append(produk_id)
    if tenant_id is not None:
        q += " AND p.tenant_id = ?"; params.append(tenant_id)
    if tipe is not None:
        q += " AND pm.tipe = ?"; params.append(tipe)
    if tahun is not None:
        q += " AND pm.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND pm.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    q += " ORDER BY pm.tanggal DESC, pm.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    stok_cache = {}
    for r in rows:
        if r["produk_id"] not in stok_cache:
            stok_cache[r["produk_id"]] = get_stok_produk(r["produk_id"])
        r["sisa_stok"] = stok_cache[r["produk_id"]]
    return rows


def get_omzet_penjualan_produk(tahun: int = None, bulan: int = None, tenant_id: int = None) -> int:
    """Total omzet (nilai penjualan) SELURUH produk dari transaksi bertipe
    'jual' SAJA -- Restock tidak relevan (bukan penjualan), Tester SENGAJA
    tidak dihitung (tidak menambah nilai penjualan, lihat tester_produk())
    meski tetap mengurangi stok & tercatat di riwayat. Pakai
    harga_jual_saat_itu (snapshot per transaksi, lihat _catat_keluar_produk),
    BUKAN harga_jual produk saat ini, supaya angka bulan lalu tidak berubah
    kalau harga produk diedit belakangan. Dipakai kartu 'Penjualan Produk'
    di Dashboard Owner.

    FONDASI Multi-Tenant Phase 1: `produk_mutasi` TIDAK punya kolom
    tenant_id sendiri (tenant-scoped TRANSITIF lewat JOIN ke produk, lihat
    tenant_migrasi.py) -- JOIN hanya ditambahkan kalau tenant_id diisi
    (query tanpa tenant_id identik persis seperti sebelum Phase 1)."""
    q = "SELECT COALESCE(SUM(pm.jumlah * COALESCE(pm.harga_jual_saat_itu, 0)), 0) AS omzet FROM produk_mutasi pm"
    if tenant_id is not None:
        q += " JOIN produk p ON p.id = pm.produk_id"
    q += " WHERE pm.tipe = 'jual'"
    params = []
    if tenant_id is not None:
        q += " AND p.tenant_id = ?"; params.append(tenant_id)
    if tahun is not None:
        q += " AND pm.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND pm.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    with get_conn() as conn:
        return conn.execute(q, params).fetchone()["omzet"]


if __name__ == "__main__":
    # Membuat / memastikan struktur database saat file dijalankan langsung
    init_db()
    print(f"Database siap di: {DB_PATH}")
