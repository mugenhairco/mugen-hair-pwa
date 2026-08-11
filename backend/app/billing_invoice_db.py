"""billing_invoice_db.py — FONDASI Multi-Tenant Phase 4: Invoice & Checkout
=============================================================================
Tabel `subscription_invoices` -- SATU baris per percobaan checkout Payment
Gateway, BUKAN per periode langganan (Owner boleh checkout berkali-kali,
mis. transaksi pertama expired lalu coba lagi -- setiap percobaan tetap
tercatat, TIDAK saling menimpa). `tenant_id` TANPA foreign key (pola sama
seperti seluruh tabel lain di proyek ini, lihat catatan panjang di
postgres_schema.py) -- `package_kode`/`package_nama`/`jumlah`/`durasi_hari`
DISALIN sebagai SNAPSHOT saat invoice dibuat (BUKAN join real-time ke
subscription_packages), supaya kalau Super Admin mengubah harga/nama paket
SETELAH invoice ini dibuat, riwayat invoice lama tetap menampilkan apa yang
BENAR-BENAR dibayar customer saat itu.

`order_id` (field DB `snap_token`/`snap_redirect_url` -- nama kolom historis,
TIDAK diganti supaya tidak perlu migrasi skema, lihat billing_gateway_client.py
untuk provider RESMI yang sekarang mengisinya: Faspay Xpress v4, murni
redirect_url tanpa token) DIBUAT lebih dulu (buat_order_id(), murni generate
string, TIDAK menyentuh DB) SEBELUM baris invoice ini dibuat -- routers/
billing.py::checkout() memanggil Payment Gateway DULU pakai order_id itu,
baru insert baris di sini SETELAH provider mengonfirmasi (dapat redirect_url).
Ini SENGAJA supaya tidak ada baris invoice "menggantung" (status pending
tanpa redirect_url sama sekali) kalau panggilan ke provider gagal di tengah
jalan.

Status Payment Notification Faspay Xpress v4 (payment_status_code 0-9,
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
        # Riwayat Transaksi (Implementasi Payment Gateway & Riwayat Transaksi
        # Multi-Tenant): baris BARU tiap kali status invoice benar-benar
        # berubah (bukan snapshot kolom `status` yang menimpa nilai lama) --
        # dipakai Detail Transaksi Super Admin ("Riwayat perubahan status
        # pembayaran") tanpa mengubah kolom subscription_invoices yang sudah
        # ada. Diisi dari billing_webhook.py::proses_notifikasi(), pola sama
        # seperti superadmin_audit_log (write-once, tidak pernah diedit/
        # dihapus dari sisi aplikasi).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_invoice_status_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id      INTEGER NOT NULL,
                status_lama     TEXT,
                status_baru     TEXT NOT NULL,
                sumber          TEXT NOT NULL,
                waktu           TEXT NOT NULL
            )
        """)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def buat_order_id(tenant_id: int) -> str:
    """Murni generate string (TIDAK menyentuh DB) -- dipakai sebagai `bill_no`
    di panggilan Payment Gateway (Faspay Xpress v4) SEBELUM baris invoice ini
    benar-benar dibuat (lihat docstring modul)."""
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


def update_invoice(invoice_id: int, **fields) -> dict:
    """Dipanggil billing_webhook.py::proses_notifikasi() SETELAH signature/
    order_id/amount lolos validasi -- `order_id`/`nomor_invoice`/`tenant_id`/
    `package_kode`/`package_nama`/`jumlah`/`durasi_hari` (snapshot checkout)
    SENGAJA TIDAK BISA diubah lewat sini, hanya kolom yang memang berubah
    seiring status pembayaran."""
    if get_invoice(invoice_id) is None:
        raise ValueError("Invoice tidak ditemukan.")
    kolom_diizinkan = {
        "status", "metode_pembayaran", "payment_type", "snap_token", "snap_redirect_url",
        "periode_mulai", "periode_selesai", "raw_notification", "paid_at",
    }
    aman = {k: v for k, v in fields.items() if k in kolom_diizinkan}
    if not aman:
        return get_invoice(invoice_id)
    if "status" in aman and aman["status"] not in STATUS_VALID:
        raise ValueError(f"Status invoice tidak dikenal: {aman['status']}")
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    params = list(aman.values()) + [_now(), invoice_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE subscription_invoices SET {set_clause}, updated_at = ? WHERE id = ?", params)
    return get_invoice(invoice_id)


def catat_status_log(invoice_id: int, status_lama: str, status_baru: str, sumber: str = "webhook"):
    """Dipanggil billing_webhook.py::proses_notifikasi() TEPAT SEBELUM
    update_invoice() -- SATU baris per transisi status sungguhan (webhook
    yang idempoten/status sama TIDAK memanggil ini sama sekali, lihat
    penjaga di proses_notifikasi())."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO subscription_invoice_status_log (invoice_id, status_lama, status_baru, sumber, waktu) "
            "VALUES (?, ?, ?, ?, ?)",
            (invoice_id, status_lama, status_baru, sumber, _now()),
        )


def list_status_log(invoice_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM subscription_invoice_status_log WHERE invoice_id = ? ORDER BY id ASC", (invoice_id,)
        ).fetchall()
        return [dict(r) for r in rows]
