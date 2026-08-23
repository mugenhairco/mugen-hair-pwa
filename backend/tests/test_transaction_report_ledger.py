"""
test_transaction_report_ledger.py — Restrukturisasi Super Admin: Riwayat
Langganan Tenant vs Riwayat Booking Tenant (dua ledger yang TIDAK PERNAH
tercampur)
=============================================================================
Cakupan tambahan transaction_report_db.py di luar test_transaction_report.py
yang sudah ada: label `jenis_transaksi` eksplisit (Langganan Baru/
Perpanjangan Langganan/Upgrade Paket untuk langganan SaaS, Payment Booking/
Refund Booking/Pembayaran Gagal/Expired untuk booking), kolom `periode_mulai`/
`periode_selesai` ikut muncul di daftar (bukan cuma detail), dan bahwa
memfilter `jenis=langganan`/`jenis=booking` menghasilkan DUA daftar yang
sungguh-sungguh terpisah (nol baris jenis lain, total nominal masing-masing
dihitung independen)."""

import billing_db

from test_transaction_report import (
    _buat_booking_transaksi_paid,
    _buat_booking_transaksi_pending,
    _buat_invoice_paid,
    _buat_invoice_pending,
    _buat_superadmin_dan_login,
)


# ============================= jenis_transaksi -- langganan =============================

def test_jenis_transaksi_invoice_pertama_langganan_baru(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_invoice_paid(tenant_a, package_kode="basic")

    r = client.get("/api/superadmin/transactions", params={"jenis": "langganan"}, headers=headers_super)
    assert r.status_code == 200, r.text
    rows = r.json()["transactions"]
    assert len(rows) == 1
    assert rows[0]["jenis_transaksi"] == "Langganan Baru"


def test_jenis_transaksi_invoice_kedua_paket_sama_perpanjangan(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_invoice_paid(tenant_a, package_kode="basic")
    _buat_invoice_paid(tenant_a, package_kode="basic")

    r = client.get("/api/superadmin/transactions", params={"jenis": "langganan"}, headers=headers_super)
    assert r.status_code == 200, r.text
    # Tiebreak dengan `id`: dua invoice dari test ini nyaris pasti lahir di
    # detik yang sama (created_at timespec detik) -- urutan kronologis
    # sungguhan hanya bisa dipastikan lewat `id` (AUTOINCREMENT).
    rows = sorted(r.json()["transactions"], key=lambda d: (d["tanggal"], d["id"]))
    assert [row["jenis_transaksi"] for row in rows] == ["Langganan Baru", "Perpanjangan Langganan"]


def test_jenis_transaksi_invoice_paket_lebih_tinggi_upgrade(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    assert billing_db.get_package_by_kode("basic")["urutan"] < billing_db.get_package_by_kode("pro")["urutan"]

    _buat_invoice_paid(tenant_a, package_kode="basic")
    _buat_invoice_paid(tenant_a, package_kode="pro")

    r = client.get("/api/superadmin/transactions", params={"jenis": "langganan"}, headers=headers_super)
    assert r.status_code == 200, r.text
    rows = sorted(r.json()["transactions"], key=lambda d: (d["tanggal"], d["id"]))
    assert [row["jenis_transaksi"] for row in rows] == ["Langganan Baru", "Upgrade Paket"]


def test_jenis_transaksi_invoice_pending_bukan_langganan_baru(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_invoice_pending(tenant_a, package_kode="basic")

    r = client.get("/api/superadmin/transactions", params={"jenis": "langganan"}, headers=headers_super)
    assert r.status_code == 200, r.text
    rows = r.json()["transactions"]
    assert len(rows) == 1
    assert rows[0]["jenis_transaksi"] == "Menunggu Pembayaran"


def test_jenis_transaksi_tidak_pernah_downgrade_atau_refund(two_tenants):
    """Downgrade gratis (tidak lewat Payment Gateway, tidak ada invoice) dan
    subscription_invoices belum punya status "refund" -- keduanya BUKAN
    kategori yang boleh muncul di ledger langganan."""
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_invoice_paid(tenant_a, package_kode="pro")
    _buat_invoice_paid(tenant_a, package_kode="basic")  # urutan lebih rendah dari invoice sebelumnya
    _buat_invoice_pending(tenant_a, package_kode="basic")

    r = client.get("/api/superadmin/transactions", params={"jenis": "langganan"}, headers=headers_super)
    assert r.status_code == 200, r.text
    jenis_muncul = {row["jenis_transaksi"] for row in r.json()["transactions"]}
    assert "Downgrade" not in jenis_muncul
    assert "Refund" not in jenis_muncul


def test_periode_ikut_muncul_di_daftar_langganan(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_invoice_paid(tenant_a, package_kode="basic")

    r = client.get("/api/superadmin/transactions", params={"jenis": "langganan"}, headers=headers_super)
    assert r.status_code == 200, r.text
    rows = r.json()["transactions"]
    assert rows[0]["periode_mulai"] is not None
    assert rows[0]["periode_selesai"] is not None


def test_detail_langganan_juga_menyertakan_jenis_transaksi(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_invoice_paid(tenant_a, package_kode="basic")
    invoice_kedua = _buat_invoice_paid(tenant_a, package_kode="pro")

    r = client.get(f"/api/superadmin/transactions/langganan/{invoice_kedua['id']}", headers=headers_super)
    assert r.status_code == 200, r.text
    assert r.json()["jenis_transaksi"] == "Upgrade Paket"


# ============================= jenis_transaksi -- booking =============================

def test_jenis_transaksi_booking_berhasil_payment_booking(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a)

    r = client.get("/api/superadmin/transactions", params={"jenis": "booking"}, headers=headers_super)
    assert r.status_code == 200, r.text
    rows = r.json()["transactions"]
    assert rows[0]["jenis_transaksi"] == "Payment Booking"


def test_jenis_transaksi_booking_pending_bukan_payment_booking(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_pending(tenant_a)

    r = client.get("/api/superadmin/transactions", params={"jenis": "booking"}, headers=headers_super)
    assert r.status_code == 200, r.text
    rows = r.json()["transactions"]
    assert rows[0]["jenis_transaksi"] == "Menunggu Pembayaran"


# ============================= Dua ledger tidak pernah tercampur =============================

def test_filter_langganan_nol_baris_booking_dan_sebaliknya(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a, nominal=120000)
    _buat_invoice_paid(tenant_a, package_kode="basic", harga=188000)

    r_langganan = client.get("/api/superadmin/transactions", params={"jenis": "langganan"}, headers=headers_super)
    r_booking = client.get("/api/superadmin/transactions", params={"jenis": "booking"}, headers=headers_super)

    langganan = r_langganan.json()
    booking = r_booking.json()

    assert all(row["jenis"] == "langganan" for row in langganan["transactions"])
    assert all(row["jenis"] == "booking" for row in booking["transactions"])
    assert langganan["summary"]["total_transaksi"] == 1
    assert booking["summary"]["total_transaksi"] == 1
    assert langganan["summary"]["total_nilai"] == 188000
    assert booking["summary"]["total_nilai"] == 120000
