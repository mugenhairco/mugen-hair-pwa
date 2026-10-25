"""
subscription_db.py — FONDASI Multi-Tenant Phase 3: Subscription & Tenant Lifecycle
=============================================================================
Struktur database + backend untuk langganan (subscription) tiap tenant --
package (Free/Basic/Pro/Enterprise), status lifecycle (Trial/Active/Expired/
Suspended/Cancelled/Lifetime), dan catatan pembayaran Virtual Account
(VA). SESUAI CAKUPAN PHASE 3: hanya struktur data + CRUD, TIDAK ADA integrasi
payment gateway sungguhan (tidak ada yang membuat VA baru ke provider mana
pun, atau menerima webhook pembayaran) -- pencatatan pembayaran di sini
murni MANUAL lewat Dashboard Super Admin, sebagai tempat untuk data itu
kalau/ketika gateway sungguhan dipasang di fase berikutnya.

Terpisah TOTAL dari `tenants.status` ('aktif'/'nonaktif', lihat tenant_db.py)
yang SUDAH ADA sejak Phase 1 sebagai kill-switch keras Super Admin (401 total
lewat auth.py::get_current_user(), TIDAK disentuh sama sekali di sini) --
subscription.status di modul ini adalah lapisan validasi TERPISAH:
- trial / active / lifetime -> akses normal.
- expired / suspended / cancelled -> akses DIBLOKIR (dashboard internal
  menampilkan halaman status subscription read-only, halaman publik /book
  diblokir total) -- lihat akses_diblokir() di bawah, dipakai
  routers/subscription.py (endpoint Owner "/subscription/me") dan
  routers/booking.py (resolve_tenant_publik_aktif).

Satu tenant = SATU baris `tenant_subscriptions` (tenant_id UNIQUE) -- bukan
riwayat, kolom-kolomnya ditimpa langsung tiap kali Super Admin mengubah
package/status/trial (riwayat perubahan tercatat terpisah lewat
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

import math
from datetime import datetime, timedelta

from database import get_conn, get_setting, set_setting

PACKAGE_VALID = {"free", "basic", "pro", "enterprise"}
# REVISI (diminta Owner): status 'grace_period' DIHAPUS TOTAL dari sini --
# dulu dua mekanisme toleransi berjalan paralel (grace_period manual Super
# Admin, DAN SUSPEND_GRACE_HARI 7 hari otomatis setelah periode_selesai
# lewat, lihat _auto_suspend_jika_lewat() di bawah) yang sekarang
# diganti SATU pendekatan: peringatan H-7 SEBELUM periode_selesai (lihat
# routers/subscription.py::subscription_status()), BUKAN toleransi
# SESUDAHNYA. Baris lama yang kebetulan masih berstatus 'grace_period'
# dikonversi ke 'active' oleh migrasi sekali-jalan, lihat
# migrasi_hapus_grace_period() di bawah.
STATUS_VALID = {"trial", "active", "expired", "suspended", "cancelled", "lifetime"}
STATUS_AKSES_DIBLOKIR = {"expired", "suspended", "cancelled"}
# FITUR Program Afiliasi Sales (sales_db.py) -- Lisensi Beli Putus: status
# BARU 'lifetime' SENGAJA tidak dimasukkan ke STATUS_AKSES_DIBLOKIR (akses
# tidak pernah diblokir) dan _auto_suspend_jika_lewat() di bawah HANYA
# bertindak untuk status 'active' (lihat fungsinya) -- status 'lifetime'
# otomatis kebal dari auto-suspend berbasis periode_selesai TANPA perlu
# logika baru, karena tenant lifetime memang tidak pernah diberi
# periode_selesai (tidak ada siklus perpanjangan apa pun lagi).
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

# Kunci `settings` PLATFORM-WIDE (tenant_id=None, TIDAK diprefix per-tenant --
# lihat database.py::_kunci_tenant()) -- satu nilai berlaku untuk SELURUH
# tenant baru, bukan per-toko.
_KUNCI_TRIAL_HARI = "subscription_trial_hari"

# Peringatan H-7 sebelum periode_selesai (pengganti grace_period/
# SUSPEND_GRACE_HARI yang dihapus) -- lihat subscription_status() di
# routers/subscription.py. BUKAN kunci `settings` yang bisa diatur Super
# Admin (diminta Owner: cukup angka tetap, tidak perlu UI konfigurasi).
PERINGATAN_KADALUARSA_HARI = 7


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
    }


def set_platform_config(trial_hari: int = None) -> dict:
    if trial_hari is not None:
        if trial_hari < 1:
            raise ValueError("Durasi Trial minimal 1 hari.")
        set_setting(_KUNCI_TRIAL_HARI, str(trial_hari), tenant_id=None)
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

    REVISI (diminta Owner, hapus toleransi grace): sebelum memeriksa status
    tersimpan, cek dulu apakah periode_selesai sudah lewat -- kalau iya,
    _auto_suspend_jika_lewat() LANGSUNG menulis status jadi 'suspended' di
    sini juga (opportunistic, tanpa cron/background job terpisah, konsisten
    dengan filosofi "gerbang di satu titik" -- fungsi ini SUDAH dipanggil
    di setiap request lewat auth.py). TIDAK ADA LAGI toleransi hari
    (SUSPEND_GRACE_HARI dihapus total) -- sebagai gantinya, Owner diberi
    peringatan H-7 SEBELUM tanggal ini (lihat routers/subscription.py::
    subscription_status())."""
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


def _auto_suspend_jika_lewat(sub: dict) -> dict:
    """Opportunistic, dijalankan di SETIAP panggilan akses_diblokir() --
    HANYA berlaku untuk subscription berstatus 'active' yang punya
    periode_selesai (kolom baru di atas). REVISI (diminta Owner, hapus
    toleransi grace): dulu ada SUSPEND_GRACE_HARI (7 hari) sebelum status
    berubah -- SEKARANG begitu periode_selesai lewat, status LANGSUNG
    'suspended' pada panggilan berikutnya, tanpa toleransi sama sekali.
    Pembayaran sukses menulis ulang periode_selesai ke masa depan lewat
    billing_webhook._aktifkan_subscription() -> set_periode() DAN
    mengembalikan status ke 'active' lewat update_status(), jadi begitu
    tenant bayar, kondisi suspend ini otomatis tidak lagi terpenuhi --
    requirement poin 12/13 TIDAK butuh kode "un-suspend" terpisah.

    TIDAK PERNAH menyentuh status 'trial'/'cancelled'/'suspended' yang
    sudah ada -- mekanisme trial Fase 3 dan override manual Super Admin
    (mis. 'cancelled') SAMA SEKALI TIDAK disentuh di sini."""
    if sub["status"] != "active" or not sub.get("periode_selesai"):
        return sub
    batas = datetime.fromisoformat(sub["periode_selesai"])
    if _sekarang() < batas:
        return sub
    return update_status(sub["tenant_id"], "suspended")


def hari_tersisa_dari_tanggal(tanggal_iso: str | None) -> int | None:
    """Jumlah hari (bisa negatif kalau sudah lewat) sampai `tanggal_iso` --
    None kalau kosong. Dipakai hari_tersisa_periode() (periode_selesai,
    status 'active') DAN langsung oleh subscription_status()
    (routers/subscription.py, trial_end, status 'trial') untuk peringatan
    H-7 (diminta Owner: "perluas juga ke masa trial") -- pengganti
    grace_period lama.

    DIBULATKAN KE ATAS (bukan timedelta.days polos yang membulatkan ke
    bawah/nol) -- periode_selesai/trial_end disimpan jam 23:59:59-an, jadi
    "5 hari lagi" yang dihitung beberapa detik setelah set_periode()/
    set_trial() dipanggil (mis. H-5 pukul 00:00:01) TIDAK BOLEH keliru
    terbaca "4 hari lagi" hanya karena belum genap 5x24 jam -- yang relevan
    buat Owner adalah tanggal kalender, bukan jam presisi."""
    if not tanggal_iso:
        return None
    selisih_detik = (datetime.fromisoformat(tanggal_iso) - _sekarang()).total_seconds()
    if selisih_detik >= 0:
        return math.ceil(selisih_detik / 86400)
    return -math.ceil(-selisih_detik / 86400)


def hari_tersisa_periode(sub: dict) -> int | None:
    """Jumlah hari (bisa negatif kalau sudah lewat) sampai periode_selesai --
    None kalau tenant tidak punya periode_selesai sama sekali (mis. paket
    'free'/trial yang belum pernah bayar, atau status 'lifetime' yang
    memang tidak pernah diberi periode_selesai)."""
    return hari_tersisa_dari_tanggal(sub.get("periode_selesai"))


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


_KUNCI_HAPUS_GRACE_PERIOD = "subscription_hapus_grace_period_selesai"


def migrasi_hapus_grace_period():
    """SEKALI SAJA sepanjang umur database (pola sama persis seperti
    billing_db.py::seed_default_package_features(), ditandai lewat
    `settings`) -- REVISI (diminta Owner): status 'grace_period' manual
    Super Admin dihapus total dari sistem (lihat STATUS_VALID di atas),
    diganti peringatan H-7 SEBELUM periode_selesai. Baris tenant_subscriptions
    yang KEBETULAN sedang berstatus 'grace_period' pada saat migrasi ini
    jalan (dibuat sebelum revisi ini) dikonversi ke 'active' -- SAMA PERSIS
    semantik lama 'grace_period' ("akses normal, belum diblokir"), jadi
    tenant yang terdampak TIDAK tiba-tiba kehilangan akses. Setelah ini,
    _auto_suspend_jika_lewat() yang mengambil alih berdasarkan
    periode_selesai tenant itu sendiri, sama seperti tenant 'active' lain.
    Kolom grace_start/grace_end TIDAK dihapus dari skema (proyek ini tidak
    punya migrasi destruktif, lihat tests/test_migration.py) -- sekadar
    berhenti ditulis/dibaca kode mana pun lagi."""
    if get_setting(_KUNCI_HAPUS_GRACE_PERIOD, default=None) == "1":
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenant_subscriptions SET status = 'active', updated_at = ? WHERE status = 'grace_period'",
            (_now(),),
        )
    set_setting(_KUNCI_HAPUS_GRACE_PERIOD, "1", tenant_id=None)


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
