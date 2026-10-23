"""
sales_db.py — Program Afiliasi Sales/Marketing (Kode Referral & Komisi)
=============================================================================
Memungkinkan Super Admin merekrut tim Sales/Marketing lewat akun login
ber-role 'sales' (tenant_id=NULL, pola identik 'superadmin' -- lihat
auth_db.py). Tiap akun sales dipasangkan satu kode referral yang bisa
diisi tenant saat mendaftar sendiri (routers/tenant_registration.py), atau
ditempel manual oleh Super Admin lewat set_tenant_referral() di bawah.

Dua jenis insentif, PERSENTASE KOMISI FLEKSIBEL per kode referral (Super
Admin bisa override 3 angka ini kapan pun lewat update_kode_referral(),
TIDAK hardcode 50/20/30 di mana pun selain sebagai nilai default saat kode
baru dibuat):
  A. Penjualan Paket Langganan (bulanan/6 bulan/tahunan) -- komisi dihitung
     OTOMATIS begitu Super Admin menandai pembayaran langganan (tabel
     tenant_subscription_payments, lihat subscription_db.py) lunas, lewat
     catat_komisi_dari_subscription_payment() di bawah (dipanggil dari
     routers/subscription.py::ubah_status_payment(), BUKAN dari modul ini
     sendiri -- sales_db.py TIDAK mengimpor subscription_db.py sama sekali,
     supaya dua modul penyimpanan murni ini tidak saling bergantung,
     orkestrasi terjadi di layer router, pola sama seperti kasbon_db.py/
     slip_gaji_db.py). Nominal dihitung dari `amount` aktual yang Super
     Admin catat di baris pembayaran itu -- SUDAH otomatis angka setelah
     diskon apa pun (Super Admin memang mengetik nominal yang BENAR-BENAR
     diterima, bukan harga katalog), jadi tidak perlu logika diskon
     terpisah di sini. Pendaftaran/pembelian PERTAMA tenant itu (hitung
     dari jumlah pembayaran 'paid' sebelumnya == 0) -> persen "baru".
     Pembayaran kedua dan seterusnya (perpanjangan, SELAMANYA selama masih
     berlangganan) -> persen "repeat".
  B. Penjualan Lisensi Lifetime -- Super Admin memilih tenant + paket
     (nominal diisi otomatis dari subscription_packages.harga_lifetime,
     lihat buat_lifetime_purchase()), lalu transaksi pembayarannya NYATA
     lewat gateway Faspay SNAP Advance yang SAMA dipakai checkout
     langganan biasa (payment_provider_client.py -> snap_payment_db.py,
     lihat routers/sales.py::buat_lifetime() yang menirukan PERSIS pola
     routers/billing.py::checkout()) -- TIDAK LAGI VA/provider diketik
     manual (REVISI: desain awal keliru, Faspay tidak punya dashboard
     manusia untuk membuat VA, VA hanya bisa dibuat lewat API). Baris
     tenant_lifetime_purchases di bawah ini MURNI mencatat intent
     pembelian (tenant, paket, nominal, kode referral) -- instrumen
     pembayaran nyata (nomor VA/QR) tersimpan di
     snap_payment_transactions.lifetime_purchase_id, status LUNAS
     ditentukan webhook SNAP (snap_webhook.py::_cascade_lifetime_license())
     yang memanggil tandai_status_lifetime() di bawah, SEKALIGUS (1)
     meng-upgrade status langganan tenant itu jadi 'lifetime' (akses
     tidak pernah diblokir lagi, lihat subscription_db.STATUS_VALID/
     STATUS_AKSES_DIBLOKIR) dan (2) mencatat komisi otomatis kalau kode
     referral terpasang.

Tabel baru murni milik modul ini (pola sama seperti kasbon_db.py) --
init_sales_db() dipanggil dari main.py on_startup() jalur SQLite. Jalur
PostgreSQL: tabel yang SAMA dibuat di postgres_schema.py. Kolom
tenants.referral_code_id ditambah lewat migrasi_tenant_referral_code()
(SQLite) / ALTER TABLE ... ADD COLUMN IF NOT EXISTS (Postgres)."""

from datetime import datetime

from database import get_conn
from db_compat import IntegrityError

JENIS_KOMISI_VALID = {"baru", "repeat", "lifetime"}
STATUS_KOMISI_VALID = {"belum_dibayar", "sudah_dibayar"}
PAYMENT_STATUS_VALID = {"pending", "paid", "expired", "failed", "cancelled"}

KOMISI_PERSEN_BARU_DEFAULT = 50
KOMISI_PERSEN_REPEAT_DEFAULT = 20
KOMISI_PERSEN_LIFETIME_DEFAULT = 30


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init_sales_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sales_referral_codes (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                kode                    TEXT NOT NULL UNIQUE,
                user_id                 INTEGER NOT NULL,
                nama_sales              TEXT NOT NULL,
                komisi_persen_baru      REAL NOT NULL DEFAULT 50,
                komisi_persen_repeat    REAL NOT NULL DEFAULT 20,
                komisi_persen_lifetime  REAL NOT NULL DEFAULT 30,
                aktif                   INTEGER NOT NULL DEFAULT 1,
                created_at              TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sales_commissions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                referral_code_id  INTEGER NOT NULL,
                tenant_id         INTEGER NOT NULL,
                jenis             TEXT NOT NULL,
                sumber_tabel      TEXT NOT NULL,
                sumber_id         INTEGER NOT NULL,
                nominal_dibayar   INTEGER NOT NULL,
                persen_komisi     REAL NOT NULL,
                nominal_komisi    INTEGER NOT NULL,
                status            TEXT NOT NULL DEFAULT 'belum_dibayar',
                dibuat_at         TEXT NOT NULL,
                dibayar_at        TEXT,
                UNIQUE(sumber_tabel, sumber_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenant_lifetime_purchases (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id               INTEGER NOT NULL,
                package_kode            TEXT NOT NULL,
                amount                  INTEGER NOT NULL,
                provider                TEXT NOT NULL,
                virtual_account_number  TEXT NOT NULL,
                referral_code_id        INTEGER,
                payment_status          TEXT NOT NULL DEFAULT 'pending',
                expired_at              TEXT,
                paid_at                 TEXT,
                dibuat_oleh             TEXT,
                created_at              TEXT NOT NULL
            )
        """)


def migrasi_tenant_referral_code():
    """JALUR SQLITE SAJA (dipanggil dari main.py::on_startup(), SETELAH
    migrasi_tenant()) -- menambah kolom tenants.referral_code_id (idempotent).
    Jalur PostgreSQL: kolom yang sama sudah langsung dibuat lewat
    ALTER TABLE ... ADD COLUMN IF NOT EXISTS di postgres_schema.py."""
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(tenants)").fetchall()]
        if "referral_code_id" not in kolom:
            conn.execute("ALTER TABLE tenants ADD COLUMN referral_code_id INTEGER")


# ============================= Kode Referral =============================

def buat_kode_referral(kode: str, user_id: int, nama_sales: str,
                        komisi_persen_baru: float = KOMISI_PERSEN_BARU_DEFAULT,
                        komisi_persen_repeat: float = KOMISI_PERSEN_REPEAT_DEFAULT,
                        komisi_persen_lifetime: float = KOMISI_PERSEN_LIFETIME_DEFAULT) -> dict:
    kode = (kode or "").strip().upper()
    nama_sales = (nama_sales or "").strip()
    if not kode:
        raise ValueError("Kode referral tidak boleh kosong.")
    if not nama_sales:
        raise ValueError("Nama sales tidak boleh kosong.")
    for label, nilai in [("baru", komisi_persen_baru), ("repeat", komisi_persen_repeat),
                          ("lifetime", komisi_persen_lifetime)]:
        if nilai is None or nilai < 0 or nilai > 100:
            raise ValueError(f"Persentase komisi {label} harus di antara 0-100.")
    now = _now()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO sales_referral_codes "
                "(kode, user_id, nama_sales, komisi_persen_baru, komisi_persen_repeat, "
                "komisi_persen_lifetime, aktif, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                (kode, user_id, nama_sales, komisi_persen_baru, komisi_persen_repeat,
                 komisi_persen_lifetime, now),
            )
        except IntegrityError:
            raise ValueError(f"Kode referral '{kode}' sudah dipakai.")
        new_id = cur.lastrowid
    return get_kode_referral(new_id)


def get_kode_referral(id_: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sales_referral_codes WHERE id = ?", (id_,)).fetchone()
        return dict(row) if row else None


def get_kode_referral_by_kode(kode: str) -> dict | None:
    kode = (kode or "").strip().upper()
    if not kode:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sales_referral_codes WHERE kode = ?", (kode,)).fetchone()
        return dict(row) if row else None


def get_kode_referral_by_user(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sales_referral_codes WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_kode_referral() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM sales_referral_codes ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def update_kode_referral(id_: int, **fields) -> dict:
    if get_kode_referral(id_) is None:
        raise ValueError("Kode referral tidak ditemukan.")
    kolom_boleh = {"nama_sales", "komisi_persen_baru", "komisi_persen_repeat",
                    "komisi_persen_lifetime", "aktif"}
    set_klausa, nilai = [], []
    for k, v in fields.items():
        if k not in kolom_boleh:
            continue
        if k in ("komisi_persen_baru", "komisi_persen_repeat", "komisi_persen_lifetime"):
            if v is None or v < 0 or v > 100:
                raise ValueError("Persentase komisi harus di antara 0-100.")
        set_klausa.append(f"{k} = ?")
        nilai.append(v)
    if not set_klausa:
        return get_kode_referral(id_)
    nilai.append(id_)
    with get_conn() as conn:
        conn.execute(f"UPDATE sales_referral_codes SET {', '.join(set_klausa)} WHERE id = ?", nilai)
    return get_kode_referral(id_)


# ============================= Atribusi Tenant -> Kode Referral =============================

def set_tenant_referral(tenant_id: int, referral_code_id: int | None):
    """Dipanggil SEKALI saat tenant mendaftar sendiri (lewat kode referral
    opsional di form Register) ATAU manual oleh Super Admin lewat Dashboard
    Sales & Referral. Menimpa nilai lama kalau dipanggil ulang (Super Admin
    boleh mengoreksi) -- TIDAK ada validasi "hanya sekali", murni tanggung
    jawab pemanggil."""
    with get_conn() as conn:
        conn.execute("UPDATE tenants SET referral_code_id = ? WHERE id = ?", (referral_code_id, tenant_id))


def get_tenant_referral_code_id(tenant_id: int) -> int | None:
    with get_conn() as conn:
        row = conn.execute("SELECT referral_code_id FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        return row["referral_code_id"] if row else None


def list_tenant_ids_by_referral(referral_code_id: int) -> list[int]:
    """Dipakai Portal Sales (routers/sales.py) menampilkan daftar tenant
    yang terdaftar lewat kode miliknya -- hanya mengembalikan id, caller
    menggabungkan dengan tenant_db.get_tenant()/subscription_db untuk
    detail tampilan (sales_db.py sengaja tidak mengimpor modul lain)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM tenants WHERE referral_code_id = ? ORDER BY id DESC", (referral_code_id,)
        ).fetchall()
        return [r["id"] for r in rows]


# ============================= Komisi =============================

def _buat_baris_komisi(referral_code_id: int, tenant_id: int, jenis: str, sumber_tabel: str,
                        sumber_id: int, nominal_dibayar: int, persen_komisi: float) -> dict:
    nominal_komisi = round(nominal_dibayar * persen_komisi / 100)
    now = _now()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO sales_commissions (referral_code_id, tenant_id, jenis, sumber_tabel, "
                "sumber_id, nominal_dibayar, persen_komisi, nominal_komisi, status, dibuat_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'belum_dibayar', ?)",
                (referral_code_id, tenant_id, jenis, sumber_tabel, sumber_id,
                 nominal_dibayar, persen_komisi, nominal_komisi, now),
            )
        except IntegrityError:
            # Idempotent: sudah pernah dicatat utk sumber ini (mis. status
            # pembayaran ditandai lunas dua kali) -- kembalikan baris lama,
            # jangan duplikat komisi.
            with get_conn() as conn2:
                row = conn2.execute(
                    "SELECT * FROM sales_commissions WHERE sumber_tabel = ? AND sumber_id = ?",
                    (sumber_tabel, sumber_id),
                ).fetchone()
                return dict(row) if row else None
        new_id = cur.lastrowid
    return get_komisi(new_id)


def catat_komisi_dari_subscription_payment(payment: dict) -> dict | None:
    """Dipanggil dari routers/subscription.py SETELAH suatu baris
    tenant_subscription_payments ditandai 'paid' -- menentukan sendiri
    apakah ini pembayaran PERTAMA tenant itu (persen "baru") atau
    perpanjangan (persen "repeat", berlaku SELAMANYA, bukan hanya sekali)
    dengan menghitung baris 'paid' LAIN milik tenant yang sama. Return None
    (tanpa efek apa pun) kalau tenant itu tidak punya kode referral
    terpasang, atau kodenya sudah tidak aktif."""
    tenant_id = payment["tenant_id"]
    referral_code_id = get_tenant_referral_code_id(tenant_id)
    if referral_code_id is None:
        return None
    kode = get_kode_referral(referral_code_id)
    if kode is None or not kode["aktif"]:
        return None
    with get_conn() as conn:
        jumlah_paid_lain = conn.execute(
            "SELECT COUNT(*) AS n FROM tenant_subscription_payments "
            "WHERE tenant_id = ? AND payment_status = 'paid' AND id != ?",
            (tenant_id, payment["id"]),
        ).fetchone()["n"]
    jenis = "baru" if jumlah_paid_lain == 0 else "repeat"
    persen = kode["komisi_persen_baru"] if jenis == "baru" else kode["komisi_persen_repeat"]
    return _buat_baris_komisi(referral_code_id, tenant_id, jenis, "tenant_subscription_payments",
                               payment["id"], payment["amount"], persen)


def catat_komisi_dari_lifetime(purchase: dict) -> dict | None:
    """Dipanggil dari tandai_lifetime_dibayar() di bawah. Return None kalau
    transaksi Lifetime itu tidak dipasangkan kode referral apa pun (Super
    Admin boleh menjual Lifetime tanpa melalui sales mana pun)."""
    referral_code_id = purchase.get("referral_code_id")
    if referral_code_id is None:
        return None
    kode = get_kode_referral(referral_code_id)
    if kode is None or not kode["aktif"]:
        return None
    return _buat_baris_komisi(referral_code_id, purchase["tenant_id"], "lifetime",
                               "tenant_lifetime_purchases", purchase["id"],
                               purchase["amount"], kode["komisi_persen_lifetime"])


def get_komisi(id_: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sales_commissions WHERE id = ?", (id_,)).fetchone()
        return dict(row) if row else None


def list_komisi_by_referral_code(referral_code_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sales_commissions WHERE referral_code_id = ? ORDER BY id DESC",
            (referral_code_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_komisi_semua() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM sales_commissions ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def tandai_komisi(id_: int, status: str) -> dict:
    if status not in STATUS_KOMISI_VALID:
        raise ValueError(f"status harus salah satu dari: {', '.join(sorted(STATUS_KOMISI_VALID))}.")
    if get_komisi(id_) is None:
        raise ValueError("Catatan komisi tidak ditemukan.")
    dibayar_at = _now() if status == "sudah_dibayar" else None
    with get_conn() as conn:
        conn.execute("UPDATE sales_commissions SET status = ?, dibayar_at = ? WHERE id = ?",
                     (status, dibayar_at, id_))
    return get_komisi(id_)


# ============================= Lifetime Purchases =============================

def buat_lifetime_purchase(tenant_id: int, package_kode: str, amount: int,
                            referral_code_id: int | None = None, dibuat_oleh: str | None = None) -> dict:
    """MURNI mencatat intent pembelian (REVISI: provider/virtual_account_number
    TIDAK LAGI diterima di sini -- instrumen pembayaran nyata dibuat lewat
    gateway SNAP Advance SETELAH baris ini ada, lihat routers/sales.py::
    buat_lifetime() yang menirukan routers/billing.py::checkout(), VA/QR
    tersimpan di snap_payment_transactions, bukan di tabel ini). Kolom
    `provider`/`virtual_account_number` tabel ini diisi placeholder tetap
    (riwayat -- dulu wajib diketik manual) supaya skema TIDAK perlu
    migrasi NOT NULL."""
    package_kode = (package_kode or "").strip().lower()
    if package_kode not in {"basic", "pro", "enterprise"}:
        raise ValueError("Paket lisensi harus 'basic', 'pro', atau 'enterprise'.")
    if amount is None or amount <= 0:
        raise ValueError("Amount harus lebih besar dari 0.")
    if referral_code_id is not None and get_kode_referral(referral_code_id) is None:
        raise ValueError("Kode referral tidak ditemukan.")
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tenant_lifetime_purchases (tenant_id, package_kode, amount, provider, "
            "virtual_account_number, referral_code_id, payment_status, expired_at, dibuat_oleh, created_at) "
            "VALUES (?, ?, ?, 'snap_advance', '', ?, 'pending', NULL, ?, ?)",
            (tenant_id, package_kode, amount, referral_code_id, dibuat_oleh, now),
        )
        new_id = cur.lastrowid
    return get_lifetime_purchase(new_id)


def get_lifetime_purchase(id_: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenant_lifetime_purchases WHERE id = ?", (id_,)).fetchone()
        return dict(row) if row else None


def list_lifetime_purchases(tenant_id: int | None = None) -> list:
    with get_conn() as conn:
        if tenant_id is None:
            rows = conn.execute("SELECT * FROM tenant_lifetime_purchases ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tenant_lifetime_purchases WHERE tenant_id = ? ORDER BY id DESC", (tenant_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def tandai_status_lifetime(id_: int, payment_status: str) -> dict:
    """Mengubah status transaksi Lifetime. Kalau 'paid': SEKALIGUS meng-
    upgrade subscription tenant itu jadi akses permanen (status 'lifetime',
    package = tier yang dibeli) dan mencatat komisi otomatis -- lihat
    docstring modul ini. Import subscription_db DI DALAM fungsi (lokal)
    supaya tidak ada import silang antar modul penyimpanan murni di level
    modul, konsisten dengan pola auth.py/routers lain di proyek ini."""
    if payment_status not in PAYMENT_STATUS_VALID:
        raise ValueError(f"payment_status harus salah satu dari: {', '.join(sorted(PAYMENT_STATUS_VALID))}.")
    purchase = get_lifetime_purchase(id_)
    if purchase is None:
        raise ValueError("Transaksi Lifetime tidak ditemukan.")
    paid_at = _now() if payment_status == "paid" else purchase.get("paid_at")
    with get_conn() as conn:
        conn.execute("UPDATE tenant_lifetime_purchases SET payment_status = ?, paid_at = ? WHERE id = ?",
                     (payment_status, paid_at, id_))
    purchase = get_lifetime_purchase(id_)
    if payment_status == "paid":
        import subscription_db
        subscription_db.update_package(purchase["tenant_id"], purchase["package_kode"])
        subscription_db.update_status(purchase["tenant_id"], "lifetime")
        catat_komisi_dari_lifetime(purchase)
    return purchase
