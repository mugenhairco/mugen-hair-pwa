"""billing_invoice_db.py — FONDASI Multi-Tenant Phase 4: Invoice & Checkout
=============================================================================
Tabel `subscription_invoices` -- SATU baris per percobaan checkout Midtrans
(Snap), BUKAN per periode langganan (Owner boleh checkout berkali-kali,
mis. transaksi pertama expired lalu coba lagi -- setiap percobaan tetap
tercatat, TIDAK saling menimpa). `tenant_id` TANPA foreign key (pola sama
seperti seluruh tabel lain di proyek ini, lihat catatan panjang di
postgres_schema.py) -- `package_kode`/`package_nama`/`jumlah`/`durasi_hari`
DISALIN sebagai SNAPSHOT saat invoice dibuat (BUKAN join real-time ke
subscription_packages), supaya kalau Super Admin mengubah harga/nama paket
SETELAH invoice ini dibuat, riwayat invoice lama tetap menampilkan apa yang
BENAR-BENAR dibayar customer saat itu.

`order_id` (dikirim ke Midtrans, harus unik) DIBUAT lebih dulu (buat_order_id(),
murni generate string, TIDAK menyentuh DB) SEBELUM baris invoice ini dibuat --
routers/billing.py::checkout() memanggil Midtrans DULU pakai order_id itu,
baru insert baris di sini SETELAH Midtrans mengonfirmasi (dapat snap_token).
Ini SENGAJA supaya tidak ada baris invoice "menggantung" (status pending
tanpa token sama sekali) kalau panggilan ke Midtrans gagal di tengah jalan.

Status webhook Midtrans (settlement/capture/pending/expire/cancel/deny,
lihat billing_webhook.py -- modul berikutnya) dipetakan ke STATUS_VALID di
sini yang lebih sederhana untuk ditampilkan ke Owner/Super Admin."""

import uuid
from datetime import datetime

from database import get_conn

STATUS_VALID = {"pending", "paid", "denied", "cancelled", "expired"}


def init_billing_invoice_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_invoices (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
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
            )
        """)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def buat_order_id(tenant_id: int) -> str:
    """Murni generate string (TIDAK menyentuh DB) -- dipakai sebagai
    `transaction_details.order_id` di panggilan Midtrans SEBELUM baris
    invoice ini benar-benar dibuat (lihat docstring modul)."""
    return f"SUB-{tenant_id}-{uuid.uuid4().hex[:16]}"


def _buat_nomor_invoice() -> str:
    return f"INV-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


def buat_invoice(order_id: str, tenant_id: int, package: dict,
                  snap_token: str = None, snap_redirect_url: str = None) -> dict:
    """`package`: baris subscription_packages (billing_db.get_package_by_kode()/
    get_package()) -- kode/nama/harga/durasi_hari disalin sebagai snapshot."""
    nomor_invoice = _buat_nomor_invoice()
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO subscription_invoices "
            "(nomor_invoice, order_id, tenant_id, package_kode, package_nama, jumlah, durasi_hari, "
            "status, snap_token, snap_redirect_url, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
            (nomor_invoice, order_id, tenant_id, package["kode"], package["nama"], package["harga"],
             package["durasi_hari"], snap_token, snap_redirect_url, now, now),
        )
    return get_invoice_by_order_id(order_id)


def get_invoice(invoice_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_invoices WHERE id = ?", (invoice_id,)).fetchone()
        return dict(row) if row else None


def get_invoice_by_order_id(order_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subscription_invoices WHERE order_id = ?", (order_id,)).fetchone()
        return dict(row) if row else None


def list_invoices(tenant_id: int = None) -> list:
    with get_conn() as conn:
        q = "SELECT * FROM subscription_invoices"
        params = []
        if tenant_id is not None:
            q += " WHERE tenant_id = ?"
            params.append(tenant_id)
        q += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(q, params).fetchall()]
