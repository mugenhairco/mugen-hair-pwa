"""
superadmin_audit_db.py — FONDASI Multi-Tenant Phase 2.1: Audit Log Super Admin
=============================================================================
Mencatat SETIAP aksi Super Admin yang mengubah lifecycle tenant (buat toko,
aktifkan, nonaktifkan -- dan hapus tenant kalau fitur itu ditambahkan nanti)
-- akun `role='superadmin'` bisa mempengaruhi SELURUH tenant sekaligus, jadi
setiap aksinya WAJIB tercatat & bisa diaudit, beda dengan aksi Owner/Admin
biasa yang sudah cukup terisolasi lewat tenant_id.

Tabel baru murni milik modul ini, TIDAK terhubung ke tenant_id mana pun
(baris log ini milik SELURUH sistem, bukan satu tenant) -- init_*_db()
dipanggil dari main.py jalur SQLite; tabel yang SAMA dibuat di
postgres_schema.py untuk jalur PostgreSQL."""

from datetime import datetime

from database import get_conn

AKSI_VALID = {
    "buat_tenant", "aktifkan_tenant", "nonaktifkan_tenant",
    # FONDASI Multi-Tenant Phase 3 (Subscription & Tenant Lifecycle) --
    # lihat routers/subscription.py, subscription_db.py.
    "ubah_package_subscription", "ubah_status_subscription",
    "ubah_trial_subscription", "ubah_grace_subscription",
    "ubah_config_subscription", "buat_pembayaran_subscription",
    "ubah_status_pembayaran_subscription",
    # FONDASI Multi-Tenant Phase 4 (Billing & Payment Midtrans) -- lihat
    # routers/billing.py, billing_db.py.
    "ubah_paket_billing",
}


def init_superadmin_audit_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS superadmin_audit_log (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                waktu                 TEXT NOT NULL,
                superadmin_username   TEXT NOT NULL,
                aksi                  TEXT NOT NULL,
                tenant_id             INTEGER,
                tenant_slug           TEXT,
                detail                TEXT
            )
        """)


def catat(superadmin_username: str, aksi: str, tenant_id: int = None, tenant_slug: str = None, detail: str = None):
    """Dipanggil SETELAH aksi berhasil (bukan sebelum -- kalau aksi gagal,
    tidak ada apa pun yang perlu diaudit). `tenant_slug` disimpan sebagai
    SNAPSHOT terpisah dari `tenant_id` supaya riwayat tetap terbaca dengan
    jelas walau tenant itu nanti berganti slug atau (kalau fitur hapus
    tenant pernah ada) sudah tidak ada lagi baris `tenants`-nya."""
    if aksi not in AKSI_VALID:
        raise ValueError(f"Aksi audit tidak dikenal: {aksi}")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO superadmin_audit_log (waktu, superadmin_username, aksi, tenant_id, tenant_slug, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now, superadmin_username, aksi, tenant_id, tenant_slug, detail),
        )


def list_log(limit: int = 200) -> list:
    """Terbaru dulu -- log audit dilihat sebagai riwayat, bukan diedit/
    dihapus (tabel ini WRITE-ONCE dari sisi aplikasi, tidak ada fungsi
    UPDATE/DELETE sama sekali di modul ini, sengaja)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM superadmin_audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
