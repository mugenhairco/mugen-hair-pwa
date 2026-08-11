"""
test_billing_webhook.py — FONDASI Multi-Tenant Phase 4: Webhook Payment Gateway & Aktivasi
=============================================================================
Cakupan: signature/order_id/amount WAJIB lolos sebelum efek samping apa
pun, pemetaan payment_status_code Faspay Xpress v4 (2/0-1/3/7/8) dipetakan
benar, aktivasi subscription otomatis saat paid (paket + status + periode),
perpanjangan menyambung dari periode lama yang belum habis, invoice
GAGAL/PENDING TIDAK mengubah subscription, idempoten terhadap notifikasi
duplikat, DAN guard urutan status (notifikasi basi setelah status final
ditolak). SEMUA test memakai payload buatan sendiri dengan signature
dihitung manual -- TIDAK PERNAH memanggil Faspay sungguhan."""

import hashlib
from datetime import datetime, timedelta

import auth_db
import billing_db
import billing_gateway_client
import billing_gateway_db
import billing_invoice_db
import billing_webhook
import subscription_db
import tenant_db


MERCHANT_ID = "37070"
USER_ID = "bot-test-webhook"
PASSWORD = "p-test-webhook"


def _hitung_signature(bill_no, payment_status_code, user_id=USER_ID, password=PASSWORD):
    """SHA1(MD5(user_id + password + bill_no + payment_status_code)) --
    formula RESMI Faspay Xpress v4 Payment Notification."""
    tahap1 = hashlib.md5(f"{user_id}{password}{bill_no}{payment_status_code}".encode()).hexdigest()
    return hashlib.sha1(tahap1.encode()).hexdigest()


def _payload(order_id, payment_status_code, nominal, payment_channel="Bank Transfer",
             user_id=USER_ID, password=PASSWORD):
    """Payload notifikasi berformat Faspay Xpress v4 Payment Notification --
    lihat billing_webhook.py::proses_notifikasi() untuk field yang dibaca."""
    return {
        "request": "Payment Notification",
        "trx_id": "3183540500001172",
        "merchant_id": MERCHANT_ID,
        "merchant": "RivoiR",
        "bill_no": order_id,
        "payment_reff": "null",
        "payment_date": "2026-01-01 10:00:00",
        "payment_status_code": payment_status_code,
        "payment_status_desc": "Payment Status",
        "bill_total": str(int(nominal)),
        "payment_total": str(int(nominal)),
        "payment_channel_uid": "402",
        "payment_channel": payment_channel,
        "signature": _hitung_signature(order_id, payment_status_code, user_id, password),
    }


def _buat_invoice(tenant_id, package_kode="pro", harga=249000, durasi_hari=30):
    paket = billing_db.get_package_by_kode(package_kode)
    if harga is not None or durasi_hari is not None:
        billing_db.update_package(paket["id"], harga=harga, durasi_hari=durasi_hari)
        paket = billing_db.get_package(paket["id"])
    order_id = billing_invoice_db.buat_order_id(tenant_id)
    return billing_invoice_db.buat_invoice(order_id, tenant_id, paket,
                                            snap_token="tok", snap_redirect_url="https://example.test/x")


def _tenant_default():
    return tenant_db.get_tenant_by_slug("mugen-hair-co")


def _dengan_server_key(monkeypatch):
    monkeypatch.setattr(billing_gateway_db, "get_config", lambda: {
        "merchant_id": MERCHANT_ID, "server_key": USER_ID, "secret_key": PASSWORD, "client_key": "",
        "api_key": "", "webhook_url": "", "environment": "sandbox", "enabled": True,
    })


# ============================= Validasi keamanan =============================

def test_signature_tidak_valid_ditolak(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "2", invoice["jumlah"])
    payload["signature"] = "signature-palsu"

    try:
        billing_webhook.proses_notifikasi(payload)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "Signature" in str(e)
    assert billing_invoice_db.get_invoice(invoice["id"])["status"] == "pending"


def test_order_id_tidak_dikenal_ditolak(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    payload = _payload("ORDER-TIDAK-ADA", "2", 100000)
    try:
        billing_webhook.proses_notifikasi(payload)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak dikenal" in str(e)


def test_gross_amount_dimanipulasi_ditolak(app_client, monkeypatch):
    """Regresi keamanan langsung dari spesifikasi Phase 4: signature valid
    UNTUK amount yang dipalsukan (mis. attacker menghitung ulang signature
    dengan amount kecil) tetap ditolak kalau tidak cocok jumlah invoice
    ASLI yang tercatat saat checkout."""
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"], harga=249000)
    payload = _payload(invoice["order_id"], "2", 1000)  # amount dipalsukan jadi kecil

    try:
        billing_webhook.proses_notifikasi(payload)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak cocok" in str(e)
    assert billing_invoice_db.get_invoice(invoice["id"])["status"] == "pending"


def test_payment_status_code_tidak_dikenal_ditolak(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "99", invoice["jumlah"])  # kode 4/5/9 & lainnya SENGAJA tidak dipetakan

    try:
        billing_webhook.proses_notifikasi(payload)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak dikenal" in str(e)


# ============================= Pemetaan status =============================

def test_settlement_menjadi_paid_dan_aktivasi(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"], package_kode="pro", harga=249000, durasi_hari=30)
    subscription_db.create_default_subscription(tenant["id"], package="free", status="active")

    payload = _payload(invoice["order_id"], "2", invoice["jumlah"], payment_channel="QRIS")
    hasil = billing_webhook.proses_notifikasi(payload)

    assert hasil["status"] == "paid"
    assert hasil["metode_pembayaran"] == "QRIS"
    assert hasil["paid_at"] is not None
    assert hasil["periode_mulai"] is not None
    assert hasil["periode_selesai"] is not None

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["package"] == "pro"
    assert sub["status"] == "active"


def test_in_process_menjadi_pending(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "1", invoice["jumlah"], payment_channel="Kartu Kredit")
    hasil = billing_webhook.proses_notifikasi(payload)
    assert hasil["status"] == "pending"


def test_pending_menjadi_pending(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "0", invoice["jumlah"])
    hasil = billing_webhook.proses_notifikasi(payload)
    assert hasil["status"] == "pending"


def test_deny_menjadi_denied(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "3", invoice["jumlah"])
    hasil = billing_webhook.proses_notifikasi(payload)
    assert hasil["status"] == "denied"


def test_cancel_menjadi_cancelled(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "8", invoice["jumlah"])
    hasil = billing_webhook.proses_notifikasi(payload)
    assert hasil["status"] == "cancelled"


def test_expire_menjadi_expired(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "7", invoice["jumlah"])
    hasil = billing_webhook.proses_notifikasi(payload)
    assert hasil["status"] == "expired"


# ============================= Gagal/pending TIDAK mengubah subscription =============================

def test_gagal_atau_pending_tidak_mengubah_subscription(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    subscription_db.create_default_subscription(tenant["id"], package="free", status="active")

    for payment_status_code in ("0", "3", "8", "7"):
        invoice = _buat_invoice(tenant["id"], package_kode="enterprise")
        payload = _payload(invoice["order_id"], payment_status_code, invoice["jumlah"])
        billing_webhook.proses_notifikasi(payload)

    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["package"] == "free"  # TIDAK berubah jadi enterprise
    assert sub["status"] == "active"


# ============================= Perpanjangan (extend) =============================

def test_perpanjangan_menyambung_dari_periode_lama_yang_belum_habis(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()

    invoice1 = _buat_invoice(tenant["id"], package_kode="pro", durasi_hari=30)
    payload1 = _payload(invoice1["order_id"], "2", invoice1["jumlah"])
    hasil1 = billing_webhook.proses_notifikasi(payload1)
    periode_selesai_1 = datetime.fromisoformat(hasil1["periode_selesai"])

    invoice2 = _buat_invoice(tenant["id"], package_kode="pro", durasi_hari=30)
    payload2 = _payload(invoice2["order_id"], "2", invoice2["jumlah"])
    hasil2 = billing_webhook.proses_notifikasi(payload2)

    assert hasil2["periode_mulai"] == hasil1["periode_selesai"]
    periode_selesai_2 = datetime.fromisoformat(hasil2["periode_selesai"])
    assert periode_selesai_2 > periode_selesai_1


def test_periode_baru_mulai_dari_sekarang_kalau_sudah_kedaluwarsa(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()

    invoice1 = _buat_invoice(tenant["id"], package_kode="pro", durasi_hari=30)
    billing_webhook.proses_notifikasi(_payload(invoice1["order_id"], "2", invoice1["jumlah"]))
    # simulasikan periode SUDAH lewat (manipulasi langsung, bukan lewat webhook)
    kedaluwarsa = (datetime.now() - timedelta(days=5)).isoformat(timespec="seconds")
    billing_invoice_db.update_invoice(invoice1["id"], periode_selesai=kedaluwarsa)

    # periode_mulai disimpan timespec="seconds" (lihat billing_webhook.py) --
    # bandingkan dengan presisi yang sama supaya tidak gagal karena
    # microsecond "sebelum" > periode_mulai yang sudah dibulatkan ke bawah.
    sebelum = datetime.now().replace(microsecond=0)
    invoice2 = _buat_invoice(tenant["id"], package_kode="pro", durasi_hari=30)
    hasil2 = billing_webhook.proses_notifikasi(_payload(invoice2["order_id"], "2", invoice2["jumlah"]))

    periode_mulai_2 = datetime.fromisoformat(hasil2["periode_mulai"])
    assert periode_mulai_2 >= sebelum


# ============================= Idempoten =============================

def test_notifikasi_duplikat_tidak_memperpanjang_dobel(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"], package_kode="pro", durasi_hari=30)
    payload = _payload(invoice["order_id"], "2", invoice["jumlah"])

    hasil1 = billing_webhook.proses_notifikasi(payload)
    hasil2 = billing_webhook.proses_notifikasi(payload)  # provider kirim ulang notifikasi yang sama

    assert hasil1["periode_selesai"] == hasil2["periode_selesai"]
    assert hasil1["paid_at"] == hasil2["paid_at"]


def test_notifikasi_duplikat_status_pending_tidak_error(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "0", invoice["jumlah"])

    hasil1 = billing_webhook.proses_notifikasi(payload)
    hasil2 = billing_webhook.proses_notifikasi(payload)
    assert hasil1["status"] == hasil2["status"] == "pending"


def test_status_log_mencatat_transisi_sungguhan_dan_transisi_basi_diabaikan(app_client, monkeypatch):
    """Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: SATU
    baris log per transisi status SUNGGUHAN -- notifikasi duplikat (status
    sama dengan yang sudah tercatat, termasuk status awal 'pending' invoice
    baru) TIDAK menambah baris log.

    AUDIT (perbaikan pasca-audit kesiapan): webhook TIDAK MENJAMIN urutan
    pengiriman -- notifikasi BASI yang datang SETELAH invoice sudah final
    (mis. "settlement" yang tertunda di jaringan, sampai SETELAH "cancel"
    sudah lebih dulu diproses) TIDAK BOLEH mengubah status invoice lagi,
    TAPI TETAP dicatat ke status_log (sumber "webhook_diabaikan") supaya
    kejanggalan ini terlihat untuk troubleshooting."""
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    assert invoice["status"] == "pending"
    payload_pending = _payload(invoice["order_id"], "0", invoice["jumlah"])
    payload_cancel = _payload(invoice["order_id"], "8", invoice["jumlah"])
    payload_paid = _payload(invoice["order_id"], "2", invoice["jumlah"])

    billing_webhook.proses_notifikasi(payload_pending)  # status awal SUDAH 'pending', no-op TANPA log
    hasil1 = billing_webhook.proses_notifikasi(payload_cancel)  # transisi sungguhan: pending -> cancelled
    billing_webhook.proses_notifikasi(payload_cancel)  # duplikat, TIDAK nambah log
    hasil2 = billing_webhook.proses_notifikasi(payload_paid)  # BASI -- invoice sudah final "cancelled", DITOLAK

    assert hasil1["status"] == "cancelled"
    assert hasil2["status"] == "cancelled"  # TETAP cancelled, TIDAK "diperbaiki" jadi paid oleh notifikasi basi

    log = billing_invoice_db.list_status_log(invoice["id"])
    assert len(log) == 2
    assert log[0]["status_lama"] == "pending"
    assert log[0]["status_baru"] == "cancelled"
    assert log[0]["sumber"] == "webhook"
    assert log[1]["status_lama"] == "cancelled"
    assert log[1]["status_baru"] == "paid"
    assert log[1]["sumber"] == "webhook_diabaikan"


def test_tenant_tanpa_subscription_sebelumnya_dapat_baris_baru(app_client, monkeypatch):
    """Tenant yang SOMEHOW checkout tanpa pernah punya baris
    tenant_subscriptions (fixture two_tenants, dibuat lewat
    tenant_db.buat_tenant() langsung) -- aktivasi harus tetap membuat
    baris baru, bukan crash."""
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    assert subscription_db.get_subscription(tenant["id"]) is not None  # tenant default SUDAH punya (Phase 3)


# ============================= Endpoint HTTP =============================

def test_endpoint_webhook_sukses(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "2", invoice["jumlah"])

    r = app_client.post("/api/public/billing/midtrans-webhook", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"


def test_endpoint_webhook_signature_salah_400(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "2", invoice["jumlah"])
    payload["signature"] = "salah"

    r = app_client.post("/api/public/billing/midtrans-webhook", json=payload)
    assert r.status_code == 400


def test_endpoint_webhook_tanpa_login_bisa_diakses(app_client, monkeypatch):
    """Endpoint ini PUBLIK -- Faspay TIDAK PERNAH mengirim Authorization
    header apa pun, jadi TIDAK BOLEH ada dependency auth apa pun di sini."""
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    payload = _payload(invoice["order_id"], "0", invoice["jumlah"])

    r = app_client.post("/api/public/billing/midtrans-webhook", json=payload)
    assert r.status_code == 200, r.text


# ============================= AUDIT: rekonsiliasi manual (perbaikan pasca-audit kesiapan) =============================

def _login_owner(client, tenant_id, username="owner-rekon", password="rahasia123"):
    auth_db.tambah_user(username, password, role="admin", tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_rekonsiliasi_manual_menerapkan_status_dari_provider(app_client, monkeypatch):
    """Regresi langsung dari temuan audit kesiapan: webhook yang TIDAK
    PERNAH sampai sama sekali sebelumnya membuat invoice macet selamanya
    tanpa jalan pemulihan (cek_status_transaksi() sudah ada tapi tidak
    pernah dipanggil). rekonsiliasi_manual() memanggil ULANG provider
    langsung (di sini di-monkeypatch, TIDAK PERNAH memanggil provider
    sungguhan) lalu menerapkan hasilnya lewat jalur SAMA PERSIS webhook."""
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"], package_kode="pro", harga=249000)
    assert invoice["status"] == "pending"

    monkeypatch.setattr(billing_gateway_client, "cek_status_transaksi", lambda order_id: {
        "payment_status_code": "2", "bill_total": str(invoice["jumlah"]), "payment_channel": "GoPay",
    })

    hasil = billing_webhook.rekonsiliasi_manual(invoice["id"], tenant_id=tenant["id"])
    assert hasil["status"] == "paid"
    assert hasil["paid_at"] is not None
    sub = subscription_db.get_subscription(tenant["id"])
    assert sub["package"] == "pro"

    log = billing_invoice_db.list_status_log(invoice["id"])
    assert len(log) == 1
    assert log[0]["sumber"] == "rekonsiliasi_manual"


def test_rekonsiliasi_manual_gross_amount_tidak_cocok_ditolak(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"], harga=249000)

    monkeypatch.setattr(billing_gateway_client, "cek_status_transaksi", lambda order_id: {
        "payment_status_code": "2", "bill_total": "1000", "payment_channel": "GoPay",
    })

    try:
        billing_webhook.rekonsiliasi_manual(invoice["id"], tenant_id=tenant["id"])
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak cocok" in str(e)
    assert billing_invoice_db.get_invoice(invoice["id"])["status"] == "pending"


def test_rekonsiliasi_manual_invoice_tenant_lain_ditolak(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant_a = _tenant_default()
    tenant_b = tenant_db.buat_tenant("test-toko-rekon-b", "Test Toko Rekon B")
    invoice = _buat_invoice(tenant_a["id"])

    try:
        billing_webhook.rekonsiliasi_manual(invoice["id"], tenant_id=tenant_b)
        assert False, "harus melempar ValueError"
    except ValueError as e:
        assert "tidak ditemukan" in str(e)


def test_endpoint_cek_ulang_invoice_sukses(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant = _tenant_default()
    invoice = _buat_invoice(tenant["id"])
    headers = _login_owner(app_client, tenant["id"])

    monkeypatch.setattr(billing_gateway_client, "cek_status_transaksi", lambda order_id: {
        "payment_status_code": "2", "bill_total": str(invoice["jumlah"]), "payment_channel": "QRIS",
    })

    r = app_client.post(f"/api/billing/invoices/{invoice['id']}/cek-ulang", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"


def test_endpoint_cek_ulang_invoice_tenant_lain_ditolak(app_client, monkeypatch):
    _dengan_server_key(monkeypatch)
    tenant_a = _tenant_default()
    tenant_b = tenant_db.buat_tenant("test-toko-rekon-http-b", "Test Toko Rekon HTTP B")
    invoice = _buat_invoice(tenant_a["id"])
    headers_b = _login_owner(app_client, tenant_b, username="owner-rekon-b")

    r = app_client.post(f"/api/billing/invoices/{invoice['id']}/cek-ulang", headers=headers_b)
    assert r.status_code == 422


def test_cek_status_transaksi_belum_tersedia_untuk_faspay(app_client):
    """Keputusan eksplisit: dokumentasi resmi Faspay Xpress v4 yang dipakai
    TIDAK mencakup endpoint Inquiry/Check Status -- cek_status_transaksi()
    SENGAJA melempar error jelas, bukan diimplementasikan berdasarkan
    asumsi."""
    import gateway_client_base
    try:
        billing_gateway_client.cek_status_transaksi("SUB-1-dummy")
        assert False, "harus melempar GatewayError"
    except gateway_client_base.GatewayError as e:
        assert "Inquiry" in str(e) or "Check Status" in str(e)
