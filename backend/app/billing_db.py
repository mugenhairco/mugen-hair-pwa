"""
billing_db.py — FONDASI Multi-Tenant Phase 4: Billing & Payment (Midtrans)
=============================================================================
Konfigurasi paket langganan (nama/harga/durasi/status/urutan/deskripsi/
batas pemakaian) yang bisa diatur Super Admin -- TIDAK ADA satu pun nilai
di sini yang di-hardcode di kode aplikasi, semuanya baris di tabel
`subscription_packages`.

PENTING -- hubungan dengan subscription_db.py (Phase 3), SESUAI RULE Phase
4 "gunakan sistem paket yang sudah tersedia, jangan membuat tabel paket
baru kalau sudah ada, jangan mengubah fitur Phase 3": kode paket
(free/basic/pro/enterprise) TETAP PERSIS subscription_db.PACKAGE_VALID
(diimpor, BUKAN diduplikasi) -- SATU-SATUNYA "sistem paket" yang sudah ada
sebelum Phase 4 hanyalah EMPAT nilai teks itu sendiri di kolom
tenant_subscriptions.package, TANPA data harga/durasi/limit/fitur apa pun
melekat padanya. Tabel `subscription_packages` di sini BUKAN sistem paket
baru/tier baru -- murni wadah atribut yang bisa diatur Super Admin untuk
EMPAT kode yang sama itu (satu baris per kode, terhubung lewat
`subscription_packages.kode = tenant_subscriptions.package`, TANPA foreign
key -- lihat catatan panjang di postgres_schema.py soal kenapa tenant_id
dan kolom serupa di proyek ini sengaja tidak pernah pakai FK ke tabel
lain). tenant_subscriptions ITU SENDIRI (status/trial/grace/dst) SAMA
SEKALI TIDAK disentuh di sini.

Tabel baru murni milik modul ini (pola sama seperti subscription_db.py) --
init_billing_db() dipanggil dari main.py on_startup() jalur SQLite. Jalur
PostgreSQL: tabel yang SAMA dibuat di postgres_schema.py.

Modul ini JUGA berisi katalog fitur (`subscription_features` +
`subscription_package_features`, penugasan checkbox per paket) -- SESUAI
KEPUTUSAN cakupan Phase 4: murni katalog/toggle data (Super Admin bebas
tambah/hapus/aktifkan-nonaktifkan fitur & mencentang fitur mana milik
paket mana), TANPA menggerbang fungsi kode apa pun -- kebanyakan contoh
fitur di spesifikasi (Google Calendar, WhatsApp Reminder, Multi Cabang,
API, dst) belum punya implementasi nyata di aplikasi ini sama sekali.
Beda dengan LIMIT_FIELDS di bawah (barber/user/layanan/booking) yang
BENAR-BENAR ditegakkan di kode karena entitasnya nyata ada."""

from datetime import datetime

from database import get_conn
from subscription_db import PACKAGE_VALID

_FITUR_DEFAULT = (
    ("booking_online", "Booking Online"),
    ("dashboard_owner", "Dashboard Owner"),
    ("dashboard_barber", "Dashboard Barber"),
    ("multi_barber", "Multi Barber"),
    ("multi_cabang", "Multi Cabang"),
    ("google_calendar", "Google Calendar"),
    ("whatsapp_reminder", "WhatsApp Reminder"),
    ("export_excel", "Export Excel"),
    ("export_pdf", "Export PDF"),
    ("qris", "QRIS"),
    ("virtual_account", "Virtual Account"),
    ("api", "API"),
    ("priority_support", "Priority Support"),
)

# Batas pemakaian (kolom nullable di subscription_packages, NULL = tidak
# dibatasi) -- SESUAI KEPUTUSAN cakupan Phase 4: HANYA limit yang punya
# entitas nyata di aplikasi ini (barber/user/layanan/booking) yang benar-
# benar ditegakkan di kode (lihat billing_limits.py). max_cabang TETAP ada
# sebagai kolom yang bisa diisi Super Admin (aplikasi ini memang belum
# punya konsep "cabang" sama sekali -- kolom ini murni data konfigurasi/
# ditampilkan di halaman Billing, TIDAK menggerbang fungsi apa pun karena
# tidak ada jalur kode yang membuat entitas "cabang").
LIMIT_FIELDS = ("max_barber", "max_user", "max_layanan", "max_booking", "max_cabang")

_URUTAN_DEFAULT = {"free": 1, "basic": 2, "pro": 3, "enterprise": 4}
_NAMA_DEFAULT = {"free": "Free", "basic": "Basic", "pro": "Pro", "enterprise": "Enterprise"}
_HARGA_DEFAULT = {"free": 0, "basic": 99000, "pro": 249000, "enterprise": 599000}


def init_billing_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_packages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
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
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_features (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                kode         TEXT NOT NULL UNIQUE,
                nama         TEXT NOT NULL,
                deskripsi    TEXT,
                aktif        INTEGER NOT NULL DEFAULT 1,
                urutan       INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        # package_id/feature_id PAKAI foreign key (beda dengan tenant_id di
        # tabel lain) -- kedua tabel ini BARU dibuat di sini sendiri dengan
        # PRIMARY KEY yang benar sejak awal, TIDAK seperti tabel `tenants`
        # produksi lama yang jadi sumber insiden FK di catatan panjang
        # postgres_schema.py. Pola sama seperti kasbon_id/slip_gaji_id di
        # kasbon_db.py.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_package_features (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                package_id   INTEGER NOT NULL,
                feature_id   INTEGER NOT NULL,
                created_at   TEXT NOT NULL,
                UNIQUE(package_id, feature_id),
                FOREIGN KEY (package_id) REFERENCES subscription_packages(id),
                FOREIGN KEY (feature_id) REFERENCES subscription_features(id) ON DELETE CASCADE
            )
        """)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def seed_default_packages():
    """Idempotent -- SEKALI membuat baris untuk keempat kode paket yang
    belum punya baris sama sekali, dengan nilai AWAL yang masuk akal
    (bukan nilai "benar" yang dipaksakan -- Super Admin bebas mengubah
    semuanya kapan pun lewat Dashboard-nya, ini murni titik awal supaya
    sistem tidak boot dengan paket kosong tanpa harga/nama)."""
    with get_conn() as conn:
        existing = {r["kode"] for r in conn.execute("SELECT kode FROM subscription_packages").fetchall()}
        now = _now()
        for kode in sorted(PACKAGE_VALID, key=lambda k: _URUTAN_DEFAULT.get(k, 99)):
            if kode in existing:
                continue
            conn.execute(
                "INSERT INTO subscription_packages "
                "(kode, nama, harga, durasi_hari, aktif, urutan, deskripsi, created_at, updated_at) "
                "VALUES (?, ?, ?, 30, 1, ?, '', ?, ?)",
                (kode, _NAMA_DEFAULT.get(kode, kode.title()), _HARGA_DEFAULT.get(kode, 0),
                 _URUTAN_DEFAULT.get(kode, 0), now, now),
            )


def list_packages(hanya_aktif: bool = False) -> list:
    with get_conn() as conn:
        q = "SELECT * FROM subscription_packages"
        if hanya_aktif:
            q += " WHERE aktif = 1"
        q += " ORDER BY urutan, id"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_package(package_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_packages WHERE id = ?", (package_id,)).fetchone()
        return dict(row) if row else None


def get_package_by_kode(kode: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_packages WHERE kode = ?", (kode,)).fetchone()
        return dict(row) if row else None


def update_package(package_id: int, **fields) -> dict:
    """Dipanggil Super Admin (routers/billing.py) -- fields yang diterima:
    nama, harga, durasi_hari, aktif, urutan, deskripsi, + LIMIT_FIELDS.
    `kode` SENGAJA TIDAK BISA diubah lewat sini (identitas baris, dipakai
    tenant_subscriptions.package -- mengubahnya akan memutus keterkaitan
    seluruh tenant yang sudah memakai kode itu)."""
    if get_package(package_id) is None:
        raise ValueError("Paket tidak ditemukan.")
    kolom_diizinkan = {"nama", "harga", "durasi_hari", "aktif", "urutan", "deskripsi", *LIMIT_FIELDS}
    aman = {k: v for k, v in fields.items() if k in kolom_diizinkan}
    if not aman:
        return get_package(package_id)
    if "aktif" in aman:
        # bool -> 1/0 eksplisit (sama pola seperti database.py::update_barber()) --
        # kolom `aktif` INTEGER di kedua jalur SQLite & PostgreSQL, sebagian
        # driver PostgreSQL menolak binding bool langsung ke kolom INTEGER.
        aman["aktif"] = 1 if aman["aktif"] else 0
    if "nama" in aman and not (aman["nama"] or "").strip():
        raise ValueError("Nama paket tidak boleh kosong.")
    if "harga" in aman and (aman["harga"] is None or aman["harga"] < 0):
        raise ValueError("Harga tidak boleh negatif.")
    if "durasi_hari" in aman and (not aman["durasi_hari"] or aman["durasi_hari"] < 1):
        raise ValueError("Durasi langganan minimal 1 hari.")
    for limit_key in LIMIT_FIELDS:
        if limit_key in aman and aman[limit_key] is not None and aman[limit_key] < 0:
            raise ValueError(f"{limit_key} tidak boleh negatif.")
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    params = list(aman.values()) + [_now(), package_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE subscription_packages SET {set_clause}, updated_at = ? WHERE id = ?", params)
    return get_package(package_id)


# ============================= Katalog Fitur =============================

def seed_default_features():
    """Idempotent -- sama pola seperti seed_default_packages(), murni titik
    awal supaya katalog tidak kosong saat boot pertama. Super Admin bebas
    menambah/menghapus/mengubah SEMUANYA kapan pun."""
    with get_conn() as conn:
        existing = {r["kode"] for r in conn.execute("SELECT kode FROM subscription_features").fetchall()}
        now = _now()
        for urutan, (kode, nama) in enumerate(_FITUR_DEFAULT):
            if kode in existing:
                continue
            conn.execute(
                "INSERT INTO subscription_features (kode, nama, deskripsi, aktif, urutan, created_at, updated_at) "
                "VALUES (?, ?, '', 1, ?, ?, ?)",
                (kode, nama, urutan, now, now),
            )


def list_features(hanya_aktif: bool = False) -> list:
    with get_conn() as conn:
        q = "SELECT * FROM subscription_features"
        if hanya_aktif:
            q += " WHERE aktif = 1"
        q += " ORDER BY urutan, id"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_feature(feature_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_features WHERE id = ?", (feature_id,)).fetchone()
        return dict(row) if row else None


def get_feature_by_kode(kode: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_features WHERE kode = ?", (kode,)).fetchone()
        return dict(row) if row else None


def create_feature(kode: str, nama: str, deskripsi: str = "") -> dict:
    """`kode` dinormalisasi (lowercase, spasi -> underscore) supaya cocok
    dipakai sebagai slug internal -- Super Admin tetap bebas memberi `nama`
    tampilan apa pun terlepas dari kode ini."""
    kode = (kode or "").strip().lower().replace(" ", "_")
    if not kode:
        raise ValueError("Kode fitur tidak boleh kosong.")
    if not (nama or "").strip():
        raise ValueError("Nama fitur tidak boleh kosong.")
    if get_feature_by_kode(kode) is not None:
        raise ValueError(f"Kode fitur '{kode}' sudah dipakai.")
    now = _now()
    with get_conn() as conn:
        urutan = conn.execute("SELECT COALESCE(MAX(urutan), -1) AS m FROM subscription_features").fetchone()["m"] + 1
        conn.execute(
            "INSERT INTO subscription_features (kode, nama, deskripsi, aktif, urutan, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, ?, ?, ?)",
            (kode, nama.strip(), deskripsi or "", urutan, now, now),
        )
    return get_feature_by_kode(kode)


def update_feature(feature_id: int, **fields) -> dict:
    """`kode` SENGAJA TIDAK BISA diubah lewat sini -- alasan sama persis
    seperti update_package() (identitas baris, dipakai
    subscription_package_features.feature_id)."""
    if get_feature(feature_id) is None:
        raise ValueError("Fitur tidak ditemukan.")
    kolom_diizinkan = {"nama", "deskripsi", "aktif", "urutan"}
    aman = {k: v for k, v in fields.items() if k in kolom_diizinkan}
    if not aman:
        return get_feature(feature_id)
    if "aktif" in aman:
        aman["aktif"] = 1 if aman["aktif"] else 0
    if "nama" in aman and not (aman["nama"] or "").strip():
        raise ValueError("Nama fitur tidak boleh kosong.")
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    params = list(aman.values()) + [_now(), feature_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE subscription_features SET {set_clause}, updated_at = ? WHERE id = ?", params)
    return get_feature(feature_id)


def delete_feature(feature_id: int):
    """Hapus PERMANEN dari katalog (beda dengan `aktif=0` lewat
    update_feature() -- itu murni menyembunyikan dari daftar tanpa
    menghapus). ON DELETE CASCADE di subscription_package_features.feature_id
    otomatis melepas fitur ini dari SEMUA paket yang sudah mencentangnya."""
    if get_feature(feature_id) is None:
        raise ValueError("Fitur tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("DELETE FROM subscription_features WHERE id = ?", (feature_id,))


def get_package_features(package_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT f.* FROM subscription_package_features pf "
            "JOIN subscription_features f ON f.id = pf.feature_id "
            "WHERE pf.package_id = ? ORDER BY f.urutan, f.id",
            (package_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def set_package_features(package_id: int, feature_ids: list) -> list:
    """Checkbox-style: MENGGANTI SELURUH penugasan fitur paket ini dengan
    daftar `feature_ids` yang dikirim (bukan menambah satu per satu) --
    cara paling gampang dikirim langsung dari form checkbox frontend tanpa
    perlu menghitung diff sendiri."""
    if get_package(package_id) is None:
        raise ValueError("Paket tidak ditemukan.")
    feature_ids = list(dict.fromkeys(feature_ids or []))
    katalog_ids = {f["id"] for f in list_features()}
    for fid in feature_ids:
        if fid not in katalog_ids:
            raise ValueError(f"Fitur id={fid} tidak ditemukan di katalog.")
    now = _now()
    with get_conn() as conn:
        conn.execute("DELETE FROM subscription_package_features WHERE package_id = ?", (package_id,))
        for fid in feature_ids:
            conn.execute(
                "INSERT INTO subscription_package_features (package_id, feature_id, created_at) VALUES (?, ?, ?)",
                (package_id, fid, now),
            )
    return get_package_features(package_id)
