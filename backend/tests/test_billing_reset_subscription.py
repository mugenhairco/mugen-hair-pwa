"""test_billing_reset_subscription.py -- Perbaikan Billing/Subscription
(requirement Owner poin 3-6, 14, 15): "↻ Reset Subscription" Super Admin --
koreksi package/periode/status SATU tenant TANPA menyentuh invoice/payment/
webhook log sama sekali, mencatat audit log, dan hasil Reset jadi anchor
baru untuk perpanjangan berikutnya."""

import auth_db
import billing_db
import billing_invoice_db
import billing_webhook
import snap_payment_db
import subscription_db
import superadmin_audit_db
import tenant_db


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _buat_superadmin_dan_login(client, username="superadmin-reset", password="rahasia123"):
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    return _login(client, username, password)


def _tenant_default():
    return tenant_db.get_tenant_by_slug("mugen-hair-co")


def test_reset_menulis_package_periode_status_baru(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = _tenant_default()

    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/reset", headers=headers, json={
        "package": "pro", "tanggal_mulai": "2026-08-01", "tanggal_selesai": "2026-08-30", "status": "active",
    })
    assert r.status_code == 200, r.text
    hasil = r.json()
    assert hasil["package"] == "pro"
    assert hasil["status"] == "active"
    assert hasil["periode_mulai"] == "2026-08-01T00:00:00"
    assert hasil["periode_selesai"] == "2026-08-30T23:59:59"

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["periode_selesai"] == "2026-08-30T23:59:59"


def test_reset_tidak_membuat_atau_menghapus_invoice_payment_transaksi(app_client):
    """requirement poin 5: Reset TIDAK PERNAH menyentuh invoice/payment/
    transaksi gateway sama sekali -- hanya UPDATE tenant_subscriptions."""
    headers = _buat_superadmin_dan_login(app_client)
    tenant = _tenant_default()

    paket = billing_db.get_package_by_kode("pro")
    order_id = billing_invoice_db.buat_order_id(tenant["id"])
    invoice = billing_invoice_db.buat_invoice(order_id, tenant["id"], paket)
    transaksi = snap_payment_db.buat_transaksi(snap_payment_db.TRANSACTION_TYPE_SAAS_BILLING, tenant["id"],
                                                paket["harga"], subscription_invoice_id=invoice["id"])

    jumlah_invoice_sebelum = len(billing_invoice_db.list_invoices(tenant_id=tenant["id"]))
    jumlah_transaksi_sebelum = len(snap_payment_db.list_transaksi(tenant["id"]))
    invoice_sebelum = billing_invoice_db.get_invoice(invoice["id"])
    transaksi_sebelum = snap_payment_db.get_transaksi(transaksi["id"])

    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/reset", headers=headers, json={
        "package": "basic", "tanggal_mulai": "2026-01-01", "tanggal_selesai": "2026-01-31", "status": "active",
    })
    assert r.status_code == 200, r.text

    assert len(billing_invoice_db.list_invoices(tenant_id=tenant["id"])) == jumlah_invoice_sebelum
    assert len(snap_payment_db.list_transaksi(tenant["id"])) == jumlah_transaksi_sebelum
    assert billing_invoice_db.get_invoice(invoice["id"]) == invoice_sebelum
    assert snap_payment_db.get_transaksi(transaksi["id"]) == transaksi_sebelum


def test_reset_mencatat_audit_log_dengan_before_after(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = _tenant_default()
    subscription_db.update_package(tenant["id"], "free")
    subscription_db.update_status(tenant["id"], "active")

    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/reset", headers=headers, json={
        "package": "enterprise", "tanggal_mulai": "2026-08-01", "tanggal_selesai": "2026-08-30", "status": "active",
    })
    assert r.status_code == 200, r.text

    log = superadmin_audit_db.list_log()
    baris = next(l for l in log if l["aksi"] == "reset_subscription" and l["tenant_id"] == tenant["id"])
    assert "free" in baris["detail"]
    assert "enterprise" in baris["detail"]
    assert "2026-08-30T23:59:59" in baris["detail"]


def test_reset_menjadi_anchor_baru_untuk_perpanjangan_berikutnya(app_client, monkeypatch):
    """requirement poin 6: hasil Reset (periode_selesai) jadi anchor untuk
    perpanjangan pembayaran berikutnya -- pakai jalur pembayaran sungguhan
    (billing_webhook) supaya membuktikan koherensi lintas-modul, bukan cuma
    baca kolom yang sama."""
    from test_billing_webhook import _buat_invoice, _dengan_server_key, _payload

    headers = _buat_superadmin_dan_login(app_client)
    tenant = _tenant_default()

    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/reset", headers=headers, json={
        "package": "pro", "tanggal_mulai": "2026-08-01", "tanggal_selesai": "2026-08-30", "status": "active",
    })
    assert r.status_code == 200, r.text

    _dengan_server_key(monkeypatch)
    invoice = _buat_invoice(tenant["id"], package_kode="pro", durasi_hari=30)
    hasil = billing_webhook.proses_notifikasi(_payload(invoice["order_id"], "2", invoice["jumlah"]))
    assert hasil["periode_mulai"] == "2026-08-30T23:59:59"


def test_reset_package_tidak_valid_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = _tenant_default()
    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/reset", headers=headers, json={
        "package": "diamond", "tanggal_mulai": "2026-08-01", "tanggal_selesai": "2026-08-30", "status": "active",
    })
    assert r.status_code == 422


def test_reset_status_tidak_valid_ditolak(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    tenant = _tenant_default()
    r = app_client.put(f"/api/superadmin/subscriptions/{tenant['id']}/reset", headers=headers, json={
        "package": "pro", "tanggal_mulai": "2026-08-01", "tanggal_selesai": "2026-08-30", "status": "dibekukan",
    })
    assert r.status_code == 422


def test_reset_hanya_superadmin(two_tenants):
    r = two_tenants["client"].put(
        f"/api/superadmin/subscriptions/{two_tenants['tenant_a']}/reset", headers=two_tenants["headers_a"],
        json={"package": "pro", "tanggal_mulai": "2026-08-01", "tanggal_selesai": "2026-08-30", "status": "active"},
    )
    assert r.status_code == 403


def test_reset_tenant_tidak_ada_404(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.put("/api/superadmin/subscriptions/999999/reset", headers=headers, json={
        "package": "pro", "tanggal_mulai": "2026-08-01", "tanggal_selesai": "2026-08-30", "status": "active",
    })
    assert r.status_code == 404
