"""
test_transaction_report.py — Implementasi Payment Gateway & Riwayat
Transaksi Multi-Tenant: Riwayat Transaksi Super Admin
=============================================================================
Cakupan transaction_report_db.py/routers/transaction_report.py: gabungan
booking + langganan SaaS ditampilkan sebagai satu daftar seragam, filter
(tenant/tanggal/status/jenis) & pencarian bekerja benar, ringkasan
mengikuti data yang SUDAH difilter (bukan dihitung ulang dari semua data),
endpoint HANYA bisa diakses require_superadmin, detail per jenis transaksi
mengembalikan raw_notification + status_log, dan export CSV berisi baris
yang sesuai filter. SEMUA transaksi dibuat langsung lewat modul Python
(booking_gateway_db.py/billing_invoice_db.py + webhook masing-masing) --
TIDAK PERNAH memanggil provider sungguhan."""

import csv
import io
import itertools

import billing_db
import billing_gateway_db
import billing_invoice_db
import billing_webhook
import booking_db
import booking_gateway_db
import booking_gateway_webhook
import database as db
import gateway_client_base
import payment_gateway_db
import tenant_db

# PROVIDER RESMI: Faspay Xpress v4 -- kredensial test SENGAJA nilai fiktif
# (BEDA dari kredensial development sungguhan Merchant ID 37070/User ID
# bot37070/Password p@ssw0rd yang dikirim tim Faspay), lihat catatan
# keamanan yang sama di test_billing_webhook.py/test_booking_gateway.py.
BILLING_USER_ID = "bot-test-transaction-report"
BILLING_PASSWORD = "p-test-transaction-report"
PGW_USER_ID = "bot-test-transaction-report-pgw"
PGW_PASSWORD = "p-test-transaction-report-pgw"
_urutan_unik = itertools.count(1)


def _buat_superadmin_dan_login(client, username="superadmin-trx", password="rahasia123"):
    import auth_db
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _hitung_signature_billing(bill_no, payment_status_code, user_id=BILLING_USER_ID, password=BILLING_PASSWORD):
    return gateway_client_base.sign_sha1_of_md5([user_id, password, bill_no, payment_status_code])


def _buat_invoice_paid(tenant_id, package_kode="pro", harga=249000):
    billing_gateway_db.update_config(server_key=BILLING_USER_ID, secret_key=BILLING_PASSWORD, merchant_id="37070-test")
    paket = billing_db.get_package_by_kode(package_kode)
    billing_db.update_package(paket["id"], harga=harga, durasi_hari=30)
    paket = billing_db.get_package(paket["id"])
    order_id = billing_invoice_db.buat_order_id(tenant_id)
    invoice = billing_invoice_db.buat_invoice(order_id, tenant_id, paket,
                                               snap_token=None, snap_redirect_url="https://example.test/x")
    payment_status_code = "2"
    bill_total = f"{invoice['jumlah']}.00"
    payload = {
        "bill_no": order_id, "payment_status_code": payment_status_code, "bill_total": bill_total,
        "payment_channel": "Bank Transfer", "trx_id": "TRX-TEST-1",
        "signature": _hitung_signature_billing(order_id, payment_status_code),
    }
    return billing_webhook.proses_notifikasi(payload)


def _buat_invoice_pending(tenant_id, package_kode="basic", harga=99000):
    billing_gateway_db.update_config(server_key=BILLING_USER_ID, secret_key=BILLING_PASSWORD, merchant_id="37070-test")
    paket = billing_db.get_package_by_kode(package_kode)
    billing_db.update_package(paket["id"], harga=harga, durasi_hari=30)
    paket = billing_db.get_package(paket["id"])
    order_id = billing_invoice_db.buat_order_id(tenant_id)
    return billing_invoice_db.buat_invoice(order_id, tenant_id, paket,
                                            snap_token=None, snap_redirect_url="https://example.test/x")


def _hitung_signature_pgw(bill_no, payment_status_code, user_id=PGW_USER_ID, password=PGW_PASSWORD):
    return gateway_client_base.sign_sha1_of_md5([user_id, password, bill_no, payment_status_code])


def _siapkan_barber_dan_service(tenant_id, nominal=100000):
    """`barbers.nama`/`services.nama` UNIQUE GLOBAL -- sertakan tenant_id +
    counter unik supaya beberapa panggilan/tenant tidak bentrok."""
    booking_db.update_payment_settings(metode_aktif=["transfer", "gateway"], tenant_id=tenant_id)
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber Trx T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Layanan Trx T{tenant_id}-{n}", nominal, tenant_id=tenant_id)
    return barber_id, service_id


def _buat_booking_transaksi_paid(tenant_id, customer_nama="Budi Santoso", nominal=100000, hari_offset=1):
    from datetime import timedelta
    from booking_db import _hari_ini_wib

    payment_gateway_db.update_config(server_key=PGW_USER_ID, secret_key=PGW_PASSWORD, merchant_id="37070-test")
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id, nominal)
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    booking = booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                       service_ids=[service_id], customer_nama=customer_nama,
                                       customer_whatsapp="081234567890", metode_pembayaran="gateway",
                                       tenant_id=tenant_id)
    tenant = tenant_db.get_tenant(tenant_id)
    order_id = booking_gateway_db.buat_order_id(tenant_id, booking["id"])
    transaksi = booking_gateway_db.buat_transaksi(
        order_id, tenant_id, tenant["nama_barbershop"], booking["id"],
        booking["customer_nama"], booking["nama_barber"], booking["daftar_service"], booking["total_harga"],
        checkout_token="tok-test", checkout_redirect_url="https://example.test/pay",
    )
    payment_status_code = "2"
    bill_total = f"{transaksi['nominal']}.00"
    payload = {
        "bill_no": order_id, "payment_status_code": payment_status_code, "bill_total": bill_total,
        "payment_channel": "Bank Transfer", "trx_id": "TRX-TEST-2",
        "signature": _hitung_signature_pgw(order_id, payment_status_code),
    }
    return booking_gateway_webhook.proses_notifikasi(payload)


def _buat_booking_transaksi_pending(tenant_id, customer_nama="Ani Wijaya", nominal=75000, hari_offset=2):
    from datetime import timedelta
    from booking_db import _hari_ini_wib

    payment_gateway_db.update_config(server_key=PGW_USER_ID, secret_key=PGW_PASSWORD, merchant_id="37070-test")
    barber_id, service_id = _siapkan_barber_dan_service(tenant_id, nominal)
    tanggal = (_hari_ini_wib() + timedelta(days=hari_offset)).isoformat()
    booking = booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                       service_ids=[service_id], customer_nama=customer_nama,
                                       customer_whatsapp="081234567891", metode_pembayaran="gateway",
                                       tenant_id=tenant_id)
    tenant = tenant_db.get_tenant(tenant_id)
    order_id = booking_gateway_db.buat_order_id(tenant_id, booking["id"])
    return booking_gateway_db.buat_transaksi(
        order_id, tenant_id, tenant["nama_barbershop"], booking["id"],
        booking["customer_nama"], booking["nama_barber"], booking["daftar_service"], booking["total_harga"],
        checkout_token="tok-test", checkout_redirect_url="https://example.test/pay",
    )


# ============================= Akses (require_superadmin) =============================

def test_endpoint_ditolak_untuk_non_superadmin(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/transactions", headers=two_tenants["headers_a"])
    assert r.status_code == 403


def test_endpoint_ditolak_tanpa_login(two_tenants):
    r = two_tenants["client"].get("/api/superadmin/transactions")
    assert r.status_code == 401


# ============================= Gabungan booking + langganan =============================

def test_list_menggabungkan_booking_dan_langganan(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a)
    _buat_invoice_paid(tenant_a)

    r = client.get("/api/superadmin/transactions", headers=headers_super)
    assert r.status_code == 200, r.text
    body = r.json()
    jenis_set = {t["jenis"] for t in body["transactions"]}
    assert jenis_set == {"booking", "langganan"}
    assert body["summary"]["total_transaksi"] == 2
    assert body["summary"]["total_booking"] == 1
    assert body["summary"]["total_langganan"] == 1
    assert body["summary"]["total_berhasil"] == 2


def test_filter_jenis_booking_saja(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a)
    _buat_invoice_paid(tenant_a)

    r = client.get("/api/superadmin/transactions", params={"jenis": "booking"}, headers=headers_super)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["transactions"]) == 1
    assert body["transactions"][0]["jenis"] == "booking"


def test_filter_status_berhasil_vs_pending(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a)
    _buat_booking_transaksi_pending(tenant_a)

    r = client.get("/api/superadmin/transactions", params={"status": "berhasil", "jenis": "booking"},
                    headers=headers_super)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["transactions"]) == 1
    assert body["transactions"][0]["status_unified"] == "berhasil"

    r2 = client.get("/api/superadmin/transactions", params={"status": "menunggu_pembayaran", "jenis": "booking"},
                     headers=headers_super)
    body2 = r2.json()
    assert len(body2["transactions"]) == 1
    assert body2["transactions"][0]["status_unified"] == "menunggu_pembayaran"


def test_pencarian_by_customer_nama(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a, customer_nama="Rudi Hartono Unik")
    _buat_booking_transaksi_pending(tenant_a, customer_nama="Sari Dewi")

    r = client.get("/api/superadmin/transactions", params={"cari": "Rudi Hartono"}, headers=headers_super)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["transactions"]) == 1
    assert body["transactions"][0]["customer_nama"] == "Rudi Hartono Unik"


# ============================= Filter tenant (isolasi) =============================

def test_filter_tenant_id_hanya_tenant_itu(two_tenants):
    client = two_tenants["client"]
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a)
    _buat_booking_transaksi_paid(tenant_b)

    r = client.get("/api/superadmin/transactions", params={"tenant_id": tenant_a}, headers=headers_super)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["transactions"]) == 1
    assert body["transactions"][0]["tenant_id"] == tenant_a


def test_summary_per_tenant_mengikuti_filter(two_tenants):
    client = two_tenants["client"]
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a, nominal=150000)
    _buat_booking_transaksi_paid(tenant_b, nominal=200000)

    r = client.get("/api/superadmin/transactions", headers=headers_super)
    assert r.status_code == 200, r.text
    per_tenant = {row["tenant_id"]: row for row in r.json()["summary"]["per_tenant"]}
    assert per_tenant[tenant_a]["omzet"] == 150000
    assert per_tenant[tenant_b]["omzet"] == 200000
    assert r.json()["summary"]["total_nilai"] == 350000


# ============================= Detail transaksi =============================

def test_detail_booking_menyertakan_raw_notification_dan_status_log(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    transaksi = _buat_booking_transaksi_paid(tenant_a)
    r = client.get(f"/api/superadmin/transactions/booking/{transaksi['id']}", headers=headers_super)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status_unified"] == "berhasil"
    assert detail["raw_notification"] is not None
    assert len(detail["status_log"]) == 1
    assert detail["checkout_token"] == "tok-test"


def test_detail_langganan_menyertakan_periode(two_tenants):
    client = two_tenants["client"]
    tenant_a = two_tenants["tenant_a"]
    headers_super = _buat_superadmin_dan_login(client)

    invoice = _buat_invoice_paid(tenant_a)
    r = client.get(f"/api/superadmin/transactions/langganan/{invoice['id']}", headers=headers_super)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status_unified"] == "berhasil"
    assert detail["periode_mulai"] is not None
    assert detail["periode_selesai"] is not None


def test_detail_jenis_tidak_dikenal_422(two_tenants):
    client = two_tenants["client"]
    headers_super = _buat_superadmin_dan_login(client)
    r = client.get("/api/superadmin/transactions/tidak-ada/1", headers=headers_super)
    assert r.status_code == 422


def test_detail_tidak_ditemukan_404(two_tenants):
    client = two_tenants["client"]
    headers_super = _buat_superadmin_dan_login(client)
    r = client.get("/api/superadmin/transactions/booking/999999", headers=headers_super)
    assert r.status_code == 404


# ============================= Export CSV =============================

def test_export_csv_berisi_baris_sesuai_filter(two_tenants):
    client = two_tenants["client"]
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    headers_super = _buat_superadmin_dan_login(client)

    _buat_booking_transaksi_paid(tenant_a, customer_nama="Customer Export A")
    _buat_booking_transaksi_paid(tenant_b, customer_nama="Customer Export B")

    r = client.get("/api/superadmin/transactions/export", params={"tenant_id": tenant_a}, headers=headers_super)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")

    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["customer_nama"] == "Customer Export A"
    assert rows[0]["jenis"] == "booking"
    assert "nomor_transaksi" in reader.fieldnames
    assert "transaction_id_provider" in reader.fieldnames
