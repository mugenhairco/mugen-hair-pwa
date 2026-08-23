"""faspay_settlement_migrasi.py — Settlement Faspay per Terminal (Tenant)
=============================================================================
Tabel BARU murni (pola sama seperti snap_payment_migrasi.py) -- TIDAK
mengubah snap_payment_transactions/snap_payment_status_log atau modul Xpress
v4 (booking_payment_transactions/subscription_invoices) sama sekali. Fokus
HANYA transaksi Faspay SNAP Advance ("terminal" = tenant, per keputusan
eksplisit Owner -- satu toko/tenant = satu terminal settlement, TIDAK ada
konsep sub-terminal per-kasir karena transaksi SNAP saat ini tidak pernah
tercatat milik kasir/device tertentu, hanya milik tenant).

`faspay_settlements`: SATU baris per closing (tenant + tanggal). Sekali
dibuat TIDAK PERNAH diedit dari sisi terminal (immutable dari sisi
tenant -- lihat faspay_settlement_db.py, tidak ada endpoint UPDATE/DELETE
untuk tenant sama sekali, hanya Super Admin yang bisa memicu rekonsiliasi
H+1 yang MENAMBAH hasil, bukan mengubah data pengajuan awal).

`status_rekonsiliasi`:
- 'RECONCILED'     : real-time -- semua transaksi sudah status final lokal
                     (bukan CREATED/PENDING).
- 'WARNING'         : real-time -- ada transaksi yang masih menggantung
                     (belum dikonfirmasi webhook) saat closing diajukan.
- 'FINAL_MISMATCH'  : SETELAH rekonsiliasi H+1 -- ada perbedaan sungguhan
                     terhadap Inquiry API Faspay (nominal/status/reference/
                     tidak ditemukan).
(RECONCILED tetap RECONCILED kalau H+1 mengonfirmasi semua cocok -- lihat
faspay_settlement_db.py::jalankan_rekonsiliasi_h1()).

`faspay_settlement_items`: SATU baris per transaksi SNAP yang masuk closing
ini -- snapshot lengkap field yang diminta spesifikasi (order_id/reference
provider/payment method/nominal/status/timestamp), PLUS hasil pencocokan
(match_status) yang mulanya MURNI dari data lokal (real-time), lalu ditimpa
hasil Inquiry API Faspay sungguhan begitu rekonsiliasi H+1 dijalankan --
field h1_* terpisah supaya histori hasil real-time TIDAK hilang/tertimpa."""

from database import get_conn


def migrasi_faspay_settlement():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS faspay_settlements (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id             INTEGER NOT NULL,
                tenant_nama           TEXT NOT NULL,
                tanggal               TEXT NOT NULL,
                dibuat_oleh_user_id   INTEGER NOT NULL,
                dibuat_oleh_nama      TEXT NOT NULL,
                jumlah_transaksi      INTEGER NOT NULL,
                total_nominal         INTEGER NOT NULL,
                jumlah_match          INTEGER NOT NULL,
                jumlah_warning        INTEGER NOT NULL,
                jumlah_final_mismatch INTEGER,
                status_rekonsiliasi   TEXT NOT NULL,
                submitted_at          TEXT NOT NULL,
                h1_dijalankan_at      TEXT,
                h1_dijalankan_oleh    TEXT
            )
        """)
        # Satu closing per tenant per tanggal -- mencegah submit dobel yang
        # tidak sengaja (pola sama seperti tutup_hari() di manual_customer_db.py
        # yang juga mencegah tutup dobel per barber+hari).
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_faspay_settlements_tenant_tanggal
            ON faspay_settlements (tenant_id, tanggal)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS faspay_settlement_items (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                settlement_id           INTEGER NOT NULL,
                snap_transaction_id     INTEGER NOT NULL,
                order_id                TEXT NOT NULL,
                reference_id_provider   TEXT,
                payment_method          TEXT,
                nominal                 INTEGER NOT NULL,
                status_pembayaran       TEXT NOT NULL,
                timestamp_transaksi     TEXT NOT NULL,
                match_status            TEXT NOT NULL,
                match_detail            TEXT,
                h1_match_status         TEXT,
                h1_match_detail         TEXT,
                h1_checked_at           TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_faspay_settlement_items_settlement
            ON faspay_settlement_items (settlement_id)
        """)
