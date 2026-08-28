"""
subscription_db.py — FONDASI Multi-Tenant Phase 3: Subscription & Tenant Lifecycle
=============================================================================
Struktur database + backend untuk langganan (subscription) tiap tenant --
package (Free/Basic/Pro/Enterprise), status lifecycle (Trial/Active/Grace
Period/Expired/Suspended/Cancelled), dan catatan pembayaran Virtual Account
(VA). SESUAI CAKUPAN PHASE 3: hanya struktur data + CRUD, TIDAK ADA integrasi
payment gateway sungguhan (tidak ada yang membuat VA baru ke provider mana
pun, atau menerima webhook pembayaran) -- pencatatan pembayaran di sini
murni MANUAL lewat Dashboard Super Admin, sebagai tempat untuk data itu
kalau/ketika gateway sungguhan dipasang di fase berikutnya.

Terpisah TOTAL dari `tenants.status` ('aktif'/'nonaktif', lihat tenant_db.py)
yang SUDAH ADA sejak Phase 1 sebagai kill-switch keras Super Admin (401 total
lewat auth.py::get_current_user(), TIDAK disentuh sama sekali di sini) --
subscription.status di modul ini adalah lapisan validasi TERPISAH:
- trial / active / grace_period -> akses normal.
- expired / suspended / cancelled -> akses DIBLOKIR (dashboard internal
  menampilkan halaman status subscription read-only, halaman publik /book
  diblokir total) -- lihat akses_diblokir() di bawah, dipakai
  routers/subscription.py (endpoint Owner "/subscription/me") dan
  routers/booking.py (resolve_tenant_publik_aktif).

Satu tenant = SATU baris `tenant_subscriptions` (tenant_id UNIQUE) -- bukan
riwayat, kolom-kolomnya ditimpa langsung tiap kali Super Admin mengubah
package/status/trial/grace (riwayat perubahan tercatat terpisah lewat
superadmin_audit_db.py, lihat routers/subscription.py).

Tabel baru murni milik modul ini (pola sama seperti kasbon_db.py/
superadmin_audit_db.py) -- init_subscription_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.

Tenant TANPA baris `tenant_subscriptions` sama sekali (mis. dibuat lewat
tenant_db.buat_tenant() langsung -- dipakai fixture test conftest.py, di
luar alur routers/superadmin.py yang sudah dilengkapi Phase 3 ini) DIANGGAP
TIDAK DIBLOKIR (akses_diblokir() -> False) -- fail-open, bukan fail-closed,
supaya tenant yang belum pernah "dikenalkan" ke sistem subscription (baik
data lama sebelum migrasi backfill sempat jalan, maupun tenant hasil
pemanggilan langsung tenant_db.buat_tenant() di luar Dashboard Super Admin)
tidak tiba-tiba terkunci tanpa sebab yang jelas."""

from datetime import datetime, timedelta

from database import get_conn, get_setting, set_setting

PACKAGE_VALID = {"free", "basic", "pro", "enterprise"}
STATUS_VALID = {"trial", "active", "grace_period", "expired", "suspended", "cancelled"}
STATUS_AKSES_DIBLOKIR = {"expired", "suspended", "cancelled"}
PAYMENT_STATUS_VALID = {"pending", "paid", "expired", "failed"}

# Default platform (dipakai kalau Super Admin belum pernah mengatur lewat
# GET/PUT /api/superadmin/subscriptions/config) -- durasi dalam HARI.
# FITUR Landing Page & Pricing (Free Trial): dinaikkan dari 14 -> 30 supaya
# tenant self-service (routers/tenant_registration.py) benar-benar mendapat
# "Free Trial 30 Hari" seperti yang dijanjikan Landing Page -- HANYA nilai
# default-nya yang berubah, mekanisme trial itu sendiri (set_trial()/
# STATUS_VALID/dst di bawah) SAMA SEKALI TIDAK disentuh. Super Admin tetap
# bebas mengubah nilai ini kapan pun lewat Dashboard-nya.
DEFAULT_TRIAL_HARI = 30
DEFAULT_GRACE_HARI = 7

# Kunci `settings` PLATFORM-WIDE (tenant_id=None, TIDAK diprefix per-tenant --
# lihat database.py::_kunci_tenant()) -- satu nilai berlaku untuk SELURUH
# tenant baru, bukan per-toko.
_KUNCI_TRIAL_HARI = "subscription_trial_hari"
_KUNCI_GRACE_HARI = "subscription_grace_hari"


def init_subscription_db():
    # BUGFIX Phase 3: tenant_id SENGAJA TANPA "FOREIGN KEY ... REFERENCES
    # tenants(id)" -- SAMA seperti SEMUA kolom tenant_id lain di proyek ini
    # (tenant_migrasi.py hanya "ALTER TABLE ... ADD COLUMN tenant_id
    # INTEGER" polos, tidak ada satu pun FK ke tabel tenants) -- isolasi
    # tenant SELALU ditegakkan di lapisan APLIKASI (WHERE tenant_id = ?),
    # tidak pernah lewat foreign key constraint. Versi awal Phase 3 sempat
    # menambahkan FK ke sini, dan meniru pola yang SAMA di postgres_schema.py
    # menyebabkan deploy produksi GAGAL TOTAL (psycopg2.errors.
    # InvalidForeignKey -- tabel `tenants` produksi ternyata tidak punya
    # unique constraint yang bisa dipakai FK reference) -- dihapus dari
    # KEDUA jalur (SQLite di sini, Postgres di postgres_schema.py) supaya
    # perilakunya konsisten.
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenant_subscriptions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id    INTEGER NOT NULL UNIQUE,
                package      TEXT NOT NULL DEFAULT 'free',
                status       TEXT NOT NULL DEFAULT 'trial',
                trial_start  TEXT,
                trial_end    TEXT,
                grace_start  TEXT,
                grace_end    TEXT,
                periode_mulai   TEXT,
                periode_selesai TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenant_subscription_payments (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id               INTEGER NOT NULL,
                provider                TEXT NOT NULL,
                virtual_account_number  TEXT NOT NULL,
                payment_status          TEXT NOT NULL DEFAULT 'pending',
                amount                  INTEGER NOT NULL,
                expired_at              TEXT,
                paid_at                 TEXT,
                created_at              TEXT NOT NULL
            )
        """)


def migrasi_periode_subscription():
    """JALUR SQLITE SAJA (dipanggil dari main.py::on_startup() bersama
    migrasi_*() lain, SETELAH migrasi_subscription()) -- menambah kolom
    periode_mulai/periode_selesai ke tenant_subscriptions (idempotent) untuk
    Perbaikan Billing/Subscription: anchor otoritatif perpanjangan
    langganan (requirement 1/6). Jalur PostgreSQL: kolom yang sama sudah
    langsung dibuat lewat `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` di
    postgres_schema.py."""
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(tenant_subscriptions)").fetchall()]
        if "periode_mulai" not in kolom:
            conn.execute("ALTER TABLE tenant_subscriptions ADD COLUMN periode_mulai TEXT")
        if "periode_selesai" not in kolom:
            conn.execute("ALTER TABLE tenant_subscriptions ADD COLUMN periode_selesai TEXT")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sekarang() -> datetime:
    """Seam terpisah dari _now() (yang mengembalikan string ISO untuk
    penulisan kolom) -- dipakai _auto_suspend_jika_lewat() supaya test bisa
    monkeypatch subscription_db._sekarang untuk mensimulasikan waktu."""
    return datetime.now()


# ============================= Platform Config =============================

def get_platform_config() -> dict:
    return {
        "trial_hari": int(get_setting(_KUNCI_TRIAL_HARI, str(DEFAULT_TRIAL_HARI), tenant_id=None)),
        "grace_hari": int(get_setting(_KUNCI_GRACE_HARI, str(DEFAULT_GRACE_HARI), tenant_id=None)),
    }


def set_platform_config(trial_hari: int = None, grace_hari: int = None) -> dict:
    if trial_hari is not None:
        if trial_hari < 1:
            raise ValueError("Durasi Trial minimal 1 hari.")
        set_setting(_KUNCI_TRIAL_HARI, str(trial_hari), tenant_id=None)
    if grace_hari is not None:
        if grace_hari < 1:
            raise ValueError("Durasi Grace Period minimal 1 hari.")
        set_setting(_KUNCI_GRACE_HARI, str(grace_hari), tenant_id=None)
    return get_platform_config()


# ============================= Subscription =============================

def get_subscription(tenant_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenant_subscriptions WHERE tenant_id = ?", (tenant_id,)).fetchone()
        return dict(row) if row else None


def list_subscriptions() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tenant_subscriptions ORDER BY tenant_id").fetchall()
        return [dict(r) for r in rows]


def akses_diblokir(tenant_id: int) -> bool:
    """False (TIDAK diblokir) kalau tenant belum punya baris subscription
    sama sekali -- lihat penjelasan fail-open di docstring modul ini.

    requirement Owner Billing/Subscription poin 8/9: sebelum memeriksa
    status tersimpan, cek dulu apakah periode_selesai sudah lewat lebih
    dari SUSPEND_GRACE_HARI hari -- kalau iya, _auto_suspend_jika_lewat()
    menulis status jadi 'suspended' di sini juga (opportunistic, tanpa
    cron/background job terpisah, konsisten dengan filosofi "gerbang di
    satu titik" -- fungsi ini SUDAH dipanggil di setiap request lewat
    auth.py). Selama masih dalam 7 hari (poin 8), status TETAP 'active' --
    akses TIDAK diblokir, halaman Billing cukup menampilkan pesan periode
    berakhir secara terpisah (lihat routers/subscription.py)."""
    sub = get_subscription(tenant_id)
    if sub is None:
        return False
    sub = _auto_suspend_jika_lewat(sub)
    return bool(sub["status"] in STATUS_AKSES_DIBLOKIR)


def create_default_subscription(tenant_id: int, package: str = "free", status: str = "active") -> dict:
    """Dipanggil SEKALI per tenant: saat tenant baru dibuat lewat Dashboard
    Super Admin (routers/superadmin.py::buat_tenant()) maupun saat backfill
    migrasi untuk tenant yang sudah ada sebelum Phase 3 (lihat
    subscription_migrasi.py). Idempotent -- kalau baris untuk tenant_id ini
    SUDAH ADA, dikembalikan apa adanya, TIDAK ditimpa (supaya backfill migrasi
    yang dijalankan ulang tidak diam-diam me-reset subscription yang sudah
    diatur Super Admin)."""
    existing = get_subscription(tenant_id)
    if existing is not None:
        return existing
    if package not in PACKAGE_VALID:
        raise ValueError(f"Package harus salah satu dari: {', '.join(sorted(PACKAGE_VALID))}.")
    if status not in STATUS_VALID:
        raise ValueError(f"Status harus salah satu dari: {', '.join(sorted(STATUS_VALID))}.")
    now = _now()
    trial_start = trial_end = None
    if status == "trial":
        hari = get_platform_config()["trial_hari"]
        trial_start = now
        trial_end = (datetime.now() + timedelta(days=hari)).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tenant_subscriptions "
            "(tenant_id, package, status, trial_start, trial_end, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, package, status, trial_start, trial_end, now, now),
        )
    return get_subscription(tenant_id)


def _wajib_ada(tenant_id: int) -> dict:
    sub = get_subscription(tenant_id)
    if sub is None:
        raise ValueError("Tenant ini belum punya data subscription.")
    return sub


def update_package(tenant_id: int, package: str) -> dict:
    if package not in PACKAGE_VALID:
        raise ValueError(f"Package harus salah satu dari: {', '.join(sorted(PACKAGE_VALID))}.")
    _wajib_ada(tenant_id)
    with get_conn() as conn:
        conn.execute("UPDATE tenant_subscriptions SET package = ?, updated_at = ? WHERE tenant_id = ?",
                     (package, _now(), tenant_id))
    return get_subscription(tenant_id)


def update_status(tenant_id: int, status: str) -> dict:
    if status not in STATUS_VALID:
        raise ValueError(f"Status harus salah satu dari: {', '.join(sorted(STATUS_VALID))}.")
    _wajib_ada(tenant_id)
    with get_conn() as conn:
        conn.execute("UPDATE tenant_subscriptions SET status = ?, updated_at = ? WHERE tenant_id = ?",
                     (status, _now(), tenant_id))
    return get_subscription(tenant_id)


def set_periode(tenant_id: int, periode_mulai: str, periode_selesai: str) -> dict:
    """Menulis periode_mulai/periode_selesai tenant_subscriptions --
    SATU-SATUNYA anchor otoritatif requirement Owner Billing/Subscription
    poin 1/6 (perpanjangan langganan SELALU menyambung dari periode_selesai
    di sini, TIDAK PERNAH dari tanggal bayar). Dipanggil
    billing_webhook._aktifkan_subscription() setiap kali invoice paid, DAN
    reset_subscription() di bawah (Super Admin) -- keduanya sengaja lewat
    fungsi tunggal ini supaya penulisan kolom ini konsisten."""
    _wajib_ada(tenant_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenant_subscriptions SET periode_mulai = ?, periode_selesai = ?, updated_at = ? "
            "WHERE tenant_id = ?",
            (periode_mulai, periode_selesai, _now(), tenant_id),
        )
    return get_subscription(tenant_id)


def reset_subscription(tenant_id: int, package: str, periode_mulai: str, periode_selesai: str,
                        status: str) -> dict:
    """Super Admin SAJA (dipanggil dari routers/subscription.py, endpoint
    PUT /{tenant_id}/reset) -- requirement Owner Billing/Subscription poin
    3-6: koreksi package/periode/status SATU tenant (mis. tanggal keliru
    dari sandbox/gateway/kesalahan admin) TANPA menyentuh invoice/payment/
    webhook log SAMA SEKALI (poin 5) -- fungsi ini HANYA UPDATE
    tenant_subscriptions, tidak menyentuh tabel lain apa pun. TIDAK
    menyentuh trial_start/trial_end/grace_start/grace_end (di luar cakupan,
    murni urusan Fase 3). periode_selesai yang ditulis di sini otomatis
    jadi anchor BARU untuk perpanjangan berikutnya (poin 6) karena
    _hitung_periode_baru() di billing_webhook.py SELALU membaca kolom ini,
    tidak ada logika terpisah untuk "hasil Reset"."""
    if package not in PACKAGE_VALID:
        raise ValueError(f"Package harus salah satu dari: {', '.join(sorted(PACKAGE_VALID))}.")
    if status not in STATUS_VALID:
        raise ValueError(f"Status harus salah satu dari: {', '.join(sorted(STATUS_VALID))}.")
    _wajib_ada(tenant_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenant_subscriptions SET package = ?, periode_mulai = ?, periode_selesai = ?, "
            "status = ?, updated_at = ? WHERE tenant_id = ?",
            (package, periode_mulai, periode_selesai, status, _now(), tenant_id),
        )
    return get_subscription(tenant_id)


SUSPEND_GRACE_HARI = 7  # requirement Owner Billing/Subscription poin 9: 7 hari
                        # setelah periode_selesai lewat tanpa pembayaran sukses
                        # berikutnya -> tenant otomatis "suspended".


def _auto_suspend_jika_lewat(sub: dict) -> dict:
    """Opportunistic, dijalankan di SETIAP panggilan akses_diblokir() --
    HANYA berlaku untuk subscription berstatus 'active' yang punya
    periode_selesai (kolom baru di atas) DAN sudah lewat SUSPEND_GRACE_HARI
    hari tanpa pembayaran sukses berikutnya (pembayaran sukses menulis
    ulang periode_selesai ke masa depan lewat
    billing_webhook._aktifkan_subscription() -> set_periode() DAN
    mengembalikan status ke 'active' lewat update_status(), jadi begitu
    tenant bayar, kondisi suspend ini otomatis tidak lagi terpenuhi --
    requirement poin 12/13 TIDAK butuh kode "un-suspend" terpisah).

    TIDAK PERNAH menyentuh status 'trial'/'grace_period'/'cancelled'/
    'suspended' yang sudah ada -- mekanisme trial/grace Fase 3 dan
    override manual Super Admin (mis. 'cancelled') SAMA SEKALI TIDAK
    disentuh di sini, sesuai batasan Owner "jangan mengubah requirement
    sebelumnya"."""
    if sub["status"] != "active" or not sub.get("periode_selesai"):
        return sub
    batas = datetime.fromisoformat(sub["periode_selesai"]) + timedelta(days=SUSPEND_GRACE_HARI)
    if _sekarang() < batas:
        return sub
    return update_status(sub["tenant_id"], "suspended")


def set_trial(tenant_id: int, trial_start: str = None, trial_end: str = None, hari: int = None) -> dict:
    """`hari` opsional: kalau diisi (dan trial_end tidak diisi manual),
    trial_end dihitung otomatis dari trial_start + hari (default trial_start
    = sekarang). Status TIDAK otomatis diubah jadi 'trial' di sini -- Super
    Admin mengatur status secara terpisah lewat update_status() supaya jelas
    tindakannya (mis. bisa saja mengisi ULANG tanggal trial tenant yang
    statusnya sekarang 'active', untuk keperluan pencatatan)."""
    _wajib_ada(tenant_id)
    if trial_start is None:
        trial_start = _now()
    if trial_end is None:
        hari = hari if hari is not None else get_platform_config()["trial_hari"]
        trial_end = (datetime.fromisoformat(trial_start) + timedelta(days=hari)).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenant_subscriptions SET trial_start = ?, trial_end = ?, updated_at = ? WHERE tenant_id = ?",
            (trial_start, trial_end, _now(), tenant_id),
        )
    return get_subscription(tenant_id)


def set_grace(tenant_id: int, grace_start: str = None, grace_end: str = None, hari: int = None) -> dict:
    """Sama polanya dengan set_trial() -- lihat catatan di sana."""
    _wajib_ada(tenant_id)
    if grace_start is None:
        grace_start = _now()
    if grace_end is None:
        hari = hari if hari is not None else get_platform_config()["grace_hari"]
        grace_end = (datetime.fromisoformat(grace_start) + timedelta(days=hari)).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenant_subscriptions SET grace_start = ?, grace_end = ?, updated_at = ? WHERE tenant_id = ?",
            (grace_start, grace_end, _now(), tenant_id),
        )
    return get_subscription(tenant_id)


# ============================= Payments (VA) =============================
# Struktur SAJA -- lihat docstring modul, TIDAK ADA panggilan ke provider VA
# mana pun. `payment_status` diubah MANUAL oleh Super Admin lewat
# tandai_lunas() (simulasi "webhook pembayaran diterima" sampai integrasi
# gateway sungguhan ada di fase berikutnya).

def create_payment(tenant_id: int, provider: str, virtual_account_number: str,
                    amount: int, expired_at: str = None) -> dict:
    provider = (provider or "").strip()
    virtual_account_number = (virtual_account_number or "").strip()
    if not provider:
        raise ValueError("Provider tidak boleh kosong.")
    if not virtual_account_number:
        raise ValueError("Nomor Virtual Account tidak boleh kosong.")
    if amount is None or amount <= 0:
        raise ValueError("Amount harus lebih besar dari 0.")
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tenant_subscription_payments "
            "(tenant_id, provider, virtual_account_number, payment_status, amount, expired_at, created_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
            (tenant_id, provider, virtual_account_number, amount, expired_at, now),
        )
        payment_id = cur.lastrowid
    return get_payment(payment_id)


def get_payment(payment_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tenant_subscription_payments WHERE id = ?", (payment_id,)).fetchone()
        return dict(row) if row else None


def list_payments(tenant_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tenant_subscription_payments WHERE tenant_id = ? ORDER BY id DESC", (tenant_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def tandai_status_pembayaran(payment_id: int, payment_status: str, paid_at: str = None) -> dict:
    if payment_status not in PAYMENT_STATUS_VALID:
        raise ValueError(f"payment_status harus salah satu dari: {', '.join(sorted(PAYMENT_STATUS_VALID))}.")
    if get_payment(payment_id) is None:
        raise ValueError("Catatan pembayaran tidak ditemukan.")
    if payment_status == "paid" and paid_at is None:
        paid_at = _now()
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenant_subscription_payments SET payment_status = ?, paid_at = ? WHERE id = ?",
            (payment_status, paid_at, payment_id),
        )
    return get_payment(payment_id)
