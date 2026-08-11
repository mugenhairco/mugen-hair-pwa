"""booking_gateway_migrasi.py — Implementasi Payment Gateway & Riwayat
Transaksi Multi-Tenant: tabel baru untuk Payment Gateway booking customer
=============================================================================
Tabel BARU murni (pola sama seperti landing_migrasi.py) -- TIDAK mengubah
tabel `bookings`/`booking_items` yang sudah ada sama sekali. Dipanggil
SEKALI tiap boot dari main.py (jalur SQLite), aman dipanggil berulang kali
(idempotent, CREATE TABLE IF NOT EXISTS).

`booking_payment_transactions`: SATU baris per percobaan checkout Payment
Gateway booking (SATU booking bisa punya lebih dari satu percobaan kalau
transaksi pertama expired/gagal dan customer coba lagi -- BUKAN diedit,
baris lama tetap ada sebagai riwayat). `tenant_id`/`booking_id` TANPA
foreign key (pola sama seperti tabel lain di proyek ini). `tenant_nama`/
`barber_nama`/`layanan`/`customer_nama` DISALIN sebagai SNAPSHOT saat
transaksi dibuat (bukan join real-time) supaya riwayat lama tetap terbaca
benar walau data aslinya berubah/dihapus di kemudian hari.

`booking_payment_status_log`: riwayat transisi status (pola SAMA PERSIS
dengan subscription_invoice_status_log di billing_invoice_db.py) -- dipakai
Detail Booking/Riwayat Transaksi Tenant & Super Admin."""

from database import get_conn


def migrasi_booking_gateway():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_payment_transactions (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id               INTEGER NOT NULL,
                tenant_nama             TEXT NOT NULL,
                booking_id              INTEGER NOT NULL,
                order_id                TEXT NOT NULL UNIQUE,
                nomor_transaksi         TEXT NOT NULL UNIQUE,
                customer_nama           TEXT NOT NULL,
                barber_nama             TEXT NOT NULL,
                layanan                 TEXT NOT NULL,
                nominal                 INTEGER NOT NULL,
                metode_pembayaran       TEXT NOT NULL DEFAULT 'gateway',
                channel_pembayaran      TEXT,
                status_pembayaran       TEXT NOT NULL DEFAULT 'menunggu_pembayaran',
                transaction_id_provider TEXT,
                reference_id_provider   TEXT,
                checkout_token          TEXT,
                checkout_redirect_url   TEXT,
                raw_notification        TEXT,
                created_at              TEXT NOT NULL,
                updated_at              TEXT NOT NULL,
                paid_at                 TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_payment_status_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id  INTEGER NOT NULL,
                status_lama     TEXT,
                status_baru     TEXT NOT NULL,
                sumber          TEXT NOT NULL,
                waktu           TEXT NOT NULL
            )
        """)
