"""snap_payment_migrasi.py — Migrasi Faspay SNAP Advance: tabel transaksi
pembayaran TERPADU (Booking Payment Tenant + SaaS Billing)
=============================================================================
Tabel BARU murni (pola sama seperti booking_gateway_migrasi.py) -- TIDAK
mengubah `booking_payment_transactions`/`booking_payment_status_log` (Xpress
booking) atau `subscription_invoices` (Xpress billing) sama sekali. Dipanggil
SEKALI tiap boot dari main.py (jalur SQLite), aman dipanggil berulang kali.

KEPUTUSAN ARSITEKTUR (instruksi migrasi #4: "Jangan menduplikasi tabel hanya
karena ada dua use case. Gunakan satu payment transaction architecture yang
dapat menangani Booking + SaaS Billing."): SATU tabel `snap_payment_transactions`
dipakai untuk KEDUA jenis transaksi -- `transaction_type` ('BOOKING' atau
'SAAS_BILLING') menentukan yang mana, `booking_id` XOR `subscription_invoice_id`
terisi sesuai jenisnya (yang lain NULL). Ini SENGAJA terpisah dari tabel
Xpress lama (bukan menimpanya) -- Xpress v4 tetap berjalan penuh selama masa
transisi (lihat Tahap 13 instruksi migrasi), tabel Xpress lama baru dihapus
setelah SNAP Advance tervalidasi produksi.

`payment_reference` = identifier deterministic yang dikirim ke Faspay sebagai
referensi transaksi (mis. calon `partnerReferenceNo`/`bill_no` -- nama field
SISI FASPAY persis PENDING FASPAY, lihat snap_advance_client.py) DAN dipakai
webhook untuk menentukan BOOKING vs SAAS_BILLING lewat prefix -- lihat
snap_payment_db.py::PREFIX_BOOKING/PREFIX_SAAS_BILLING. `internal_transaction_id`
TERPISAH (UUID murni internal, tidak pernah dikirim ke Faspay) -- dipakai
korelasi log/troubleshooting tanpa membocorkan pola/urutan row id database."""

from database import get_conn


def migrasi_snap_payment():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snap_payment_transactions (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                internal_transaction_id   TEXT NOT NULL UNIQUE,
                provider                  TEXT NOT NULL DEFAULT 'snap_advance',
                provider_transaction_id   TEXT,
                payment_reference         TEXT NOT NULL UNIQUE,
                transaction_type          TEXT NOT NULL,
                tenant_id                 INTEGER NOT NULL,
                booking_id                INTEGER,
                subscription_invoice_id   INTEGER,
                channel                   TEXT,
                ewallet_provider          TEXT,
                amount                    INTEGER NOT NULL,
                status                    TEXT NOT NULL DEFAULT 'CREATED',
                va_number                 TEXT,
                qr_content                TEXT,
                qr_url                    TEXT,
                ewallet_deeplink_url      TEXT,
                expired_at                TEXT,
                provider_response         TEXT,
                webhook_raw_payload       TEXT,
                webhook_processing_status TEXT NOT NULL DEFAULT 'belum_diterima',
                idempotency_key           TEXT,
                created_at                TEXT NOT NULL,
                updated_at                TEXT NOT NULL,
                paid_at                   TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snap_payment_status_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id  INTEGER NOT NULL,
                status_lama     TEXT,
                status_baru     TEXT NOT NULL,
                sumber          TEXT NOT NULL,
                waktu           TEXT NOT NULL
            )
        """)
