"""test_snap_advance.py — Migrasi Faspay SNAP Advance
=============================================================================
Cakupan: SEMUA bagian yang TIDAK memerlukan spesifikasi/kredensial Faspay
sungguhan (arsitektur, unified payment reference, state machine, webhook
dispatch BOOKING vs SAAS_BILLING, idempotency, cross-domain isolation,
konfigurasi) -- lihat laporan analisis "Faspay SNAP Migration" & laporan
implementasi untuk daftar lengkap PENDING FASPAY.

TIDAK ADA test yang memanggil Faspay sungguhan (tidak ada kredensial
sandbox) -- test untuk snap_advance_client.py justru MEMBUKTIKAN fungsi
create-transaction/webhook-verify MELEMPAR error PENDING FASPAY yang jelas,
BUKAN diam-diam mengembalikan data karangan."""

import itertools

import billing_db
import database as db
import billing_invoice_db
import booking_db
import gateway_client_base as core
import pytest
import snap_account_binding_db
import snap_advance_client
import snap_advance_db
import snap_payment_db
import snap_webhook
import subscription_db
from booking_db import _hari_ini_wib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import timedelta

_urutan_unik = itertools.count(1)


def _buat_superadmin_dan_login(client, username=None, password="rahasia123"):
    import auth_db
    username = username or f"snapsuperadmin{next(_urutan_unik)}"
    auth_db.tambah_user(username=username, password=password, role="superadmin", tenant_id=None)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _siapkan_booking(tenant_id, metode="transfer", nominal=100000):
    booking_db.update_payment_settings(metode_aktif=["transfer", "qris", "gateway"], tenant_id=tenant_id)
    n = next(_urutan_unik)
    barber_id = db.add_barber(f"Barber Snap T{tenant_id}-{n}", tenant_id=tenant_id)
    service_id = db.add_service(f"Service Snap T{tenant_id}-{n}", nominal, tenant_id=tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    return booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="10:00",
                                    service_ids=[service_id], customer_nama="Budi Snap",
                                    customer_whatsapp="081234567890", metode_pembayaran=metode,
                                    tenant_id=tenant_id)


def _siapkan_invoice(tenant_id, nominal=150000):
    subscription_db.create_default_subscription(tenant_id, package="free", status="active")
    paket = billing_db.get_package_by_kode("basic")
    paket = {**paket, "harga": nominal}
    order_id = billing_invoice_db.buat_order_id(tenant_id)
    return billing_invoice_db.buat_invoice(order_id, tenant_id, paket)


# ---------------------------------------------------------------------------
# Unified payment reference -- generator & type detection
# ---------------------------------------------------------------------------

def test_payment_reference_booking_dan_saas_billing_berbeda_prefix():
    ref_booking = snap_payment_db.buat_payment_reference("BOOKING", tenant_id=1, entity_id=42)
    ref_billing = snap_payment_db.buat_payment_reference("SAAS_BILLING", tenant_id=1, entity_id=42)
    assert ref_booking.startswith("BOOKING-1-42-")
    assert ref_billing.startswith("SUBSCRIPTION-1-42-")
    assert ref_booking != ref_billing


def test_payment_reference_unik_setiap_dipanggil():
    a = snap_payment_db.buat_payment_reference("BOOKING", tenant_id=1, entity_id=42)
    b = snap_payment_db.buat_payment_reference("BOOKING", tenant_id=1, entity_id=42)
    assert a != b  # dua percobaan checkout untuk booking yang sama tetap unik (sufiks uuid)


def test_tentukan_tipe_transaksi_deteksi_dari_prefix():
    assert snap_payment_db.tentukan_tipe_transaksi("BOOKING-1-42-abc123") == "BOOKING"
    assert snap_payment_db.tentukan_tipe_transaksi("SUBSCRIPTION-1-42-abc123") == "SAAS_BILLING"


def test_tentukan_tipe_transaksi_prefix_tidak_dikenal_ditolak():
    """SESUAI instruksi migrasi: TIDAK PERNAH menebak jenis transaksi dari
    nominal/nama customer -- referensi yang tidak dikenal harus DITOLAK,
    bukan diasumsikan salah satu jenis."""
    with pytest.raises(ValueError):
        snap_payment_db.tentukan_tipe_transaksi("SESUATU-YANG-ASING-123")


# ---------------------------------------------------------------------------
# snap_payment_db -- CRUD & validasi silang BOOKING/SAAS_BILLING
# ---------------------------------------------------------------------------

def test_buat_transaksi_booking_wajib_booking_id_tanpa_invoice_id(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"])
    assert transaksi["transaction_type"] == "BOOKING"
    assert transaksi["booking_id"] == booking["id"]
    assert transaksi["subscription_invoice_id"] is None
    assert transaksi["status"] == "CREATED"
    assert transaksi["payment_reference"].startswith(f"BOOKING-{tenant_id}-{booking['id']}-")


def test_buat_transaksi_booking_tanpa_booking_id_ditolak(single_tenant):
    with pytest.raises(ValueError):
        snap_payment_db.buat_transaksi("BOOKING", single_tenant["tenant_id"], 100000)


def test_buat_transaksi_booking_dengan_invoice_id_ditolak_ambigu(single_tenant):
    """Baris "amfibi" (kedua FK terisi) TIDAK boleh terjadi -- validasi
    silang mencegah data ambigu yang bisa membingungkan cascade webhook."""
    with pytest.raises(ValueError):
        snap_payment_db.buat_transaksi("BOOKING", single_tenant["tenant_id"], 100000,
                                        booking_id=1, subscription_invoice_id=1)


def test_buat_transaksi_saas_billing_wajib_invoice_id_tanpa_booking_id(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    invoice = _siapkan_invoice(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("SAAS_BILLING", tenant_id, 150000,
                                                subscription_invoice_id=invoice["id"])
    assert transaksi["transaction_type"] == "SAAS_BILLING"
    assert transaksi["subscription_invoice_id"] == invoice["id"]
    assert transaksi["booking_id"] is None
    assert transaksi["payment_reference"].startswith(f"SUBSCRIPTION-{tenant_id}-{invoice['id']}-")


def test_get_transaksi_by_reference(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"])
    ditemukan = snap_payment_db.get_transaksi_by_reference(transaksi["payment_reference"])
    assert ditemukan["id"] == transaksi["id"]
    assert snap_payment_db.get_transaksi_by_reference("REF-TIDAK-ADA") is None


def test_catat_hasil_create_transaction_tidak_menimpa_field_kosong(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"])
    hasil1 = snap_payment_db.catat_hasil_create_transaction(transaksi["id"], va_number="88812345678")
    assert hasil1["va_number"] == "88812345678"
    hasil2 = snap_payment_db.catat_hasil_create_transaction(transaksi["id"], provider_transaction_id="TRX-999")
    assert hasil2["va_number"] == "88812345678"  # TIDAK ditimpa NULL oleh panggilan kedua
    assert hasil2["provider_transaction_id"] == "TRX-999"


# ---------------------------------------------------------------------------
# State machine -- idempotency & guard status final (instruksi migrasi #5/#6)
# ---------------------------------------------------------------------------

def test_update_status_transisi_normal(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"])
    hasil = snap_payment_db.update_status(transaksi["id"], "PENDING", sumber="webhook")
    assert hasil["status"] == "PENDING"
    hasil2 = snap_payment_db.update_status(transaksi["id"], "PAID", sumber="webhook", paid_at="2026-08-19T10:00:00")
    assert hasil2["status"] == "PAID"
    assert hasil2["paid_at"] == "2026-08-19T10:00:00"


def test_update_status_paid_ke_pending_tidak_boleh_mundur(single_tenant):
    """Contoh EKSPLISIT dari instruksi migrasi: "PAID -> PENDING tidak boleh
    terjadi hanya karena webhook terlambat"."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"])
    snap_payment_db.update_status(transaksi["id"], "PAID", sumber="webhook")

    hasil = snap_payment_db.update_status(transaksi["id"], "PENDING", sumber="webhook")
    assert hasil["status"] == "PAID"  # TETAP PAID, TIDAK mundur

    log = snap_payment_db.list_status_log(transaksi["id"])
    assert any(l["status_baru"] == "PENDING" and l["sumber"] == "webhook_diabaikan" for l in log)  # tetap tercatat untuk audit


def test_update_status_idempoten_lima_kali_paid_hanya_satu_transisi(single_tenant):
    """SESUAI instruksi migrasi #6: "Jika webhook PAID diterima 5 kali:
    Booking tetap hanya sekali dianggap PAID"."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"])
    for _ in range(5):
        hasil = snap_payment_db.update_status(transaksi["id"], "PAID", sumber="webhook")
        assert hasil["status"] == "PAID"
    log = snap_payment_db.list_status_log(transaksi["id"])
    transisi_paid_sungguhan = [l for l in log if l["status_baru"] == "PAID" and l["sumber"] == "webhook"]
    assert len(transisi_paid_sungguhan) == 1  # HANYA transisi PERTAMA yang tercatat sebagai transisi sungguhan


def test_update_status_final_ke_final_lain_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"])
    snap_payment_db.update_status(transaksi["id"], "EXPIRED", sumber="webhook")
    hasil = snap_payment_db.update_status(transaksi["id"], "PAID", sumber="webhook")
    assert hasil["status"] == "EXPIRED"  # status final TIDAK bisa diubah lagi ke final lain


def test_update_status_tidak_dikenal_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"])
    with pytest.raises(ValueError):
        snap_payment_db.update_status(transaksi["id"], "STATUS_NGAWUR", sumber="webhook")


# ---------------------------------------------------------------------------
# snap_webhook.terapkan_status_transaksi() -- dispatch BOOKING vs SAAS_BILLING
# ---------------------------------------------------------------------------

def test_cascade_booking_paid_memverifikasi_pembayaran_booking(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="transfer")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"], booking_id=booking["id"])
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "menunggu_verifikasi"

    hasil = snap_webhook.terapkan_status_transaksi(transaksi, "PAID", sumber="webhook")

    assert hasil["status"] == "PAID"
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"


def test_cascade_booking_expired_membatalkan_booking(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="qris")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"], booking_id=booking["id"])

    snap_webhook.terapkan_status_transaksi(transaksi, "EXPIRED", sumber="webhook")

    assert booking_db.get_booking(booking["id"])["status_booking"] == "dibatalkan"


def test_cascade_booking_idempoten_webhook_dobel_hanya_satu_efek_bisnis(single_tenant, monkeypatch):
    """SESUAI instruksi migrasi #6: "Jika webhook PAID diterima 5 kali:
    Booking tetap hanya sekali dianggap PAID." Guard idempoten berlapis dua
    (SAMA pola dengan webhook Xpress lama): snap_payment_db.update_status()
    mencegah CASCADE terulang begitu status transaksi SNAP sudah berubah
    (rejected/idempotent-noop dibedakan lewat status_lama==status_baru di
    dalamnya), DAN booking_db.verifikasi_pembayaran() SENDIRI idempoten
    (guard sudah_terverifikasi) -- jadi WALAU _cascade_booking() dipanggil
    lebih dari sekali (pola SAMA seperti booking_gateway_webhook.py yang
    sudah proven, TIDAK diubah di sini), business effect (kirim WA, catat
    waktu) TETAP hanya terjadi SEKALI -- dibuktikan lewat pembayaran_diterima_at
    yang TIDAK berubah antar panggilan berulang."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="transfer")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"], booking_id=booking["id"])

    panggilan_wa = []
    monkeypatch.setattr("booking_db.whatsapp_service.kirim_whatsapp",
                         lambda *a, **kw: panggilan_wa.append(1) or True)

    for _ in range(5):
        snap_webhook.terapkan_status_transaksi(snap_payment_db.get_transaksi(transaksi["id"]), "PAID", sumber="webhook")

    assert len(panggilan_wa) <= 1  # WA (kalau fitur aktif) TIDAK PERNAH terkirim lebih dari sekali
    hasil = booking_db.get_booking(booking["id"])
    assert hasil["status_pembayaran"] == "terverifikasi"
    tercatat_pertama = hasil["pembayaran_diterima_at"]
    snap_webhook.terapkan_status_transaksi(snap_payment_db.get_transaksi(transaksi["id"]), "PAID", sumber="webhook")
    assert booking_db.get_booking(booking["id"])["pembayaran_diterima_at"] == tercatat_pertama  # TIDAK ditimpa ulang


def test_cascade_saas_billing_paid_mengaktifkan_subscription(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    invoice = _siapkan_invoice(tenant_id, nominal=150000)
    transaksi = snap_payment_db.buat_transaksi("SAAS_BILLING", tenant_id, 150000,
                                                subscription_invoice_id=invoice["id"])
    assert billing_invoice_db.get_invoice(invoice["id"])["status"] == "pending"

    snap_webhook.terapkan_status_transaksi(transaksi, "PAID", sumber="webhook")

    invoice_setelah = billing_invoice_db.get_invoice(invoice["id"])
    assert invoice_setelah["status"] == "paid"
    langganan = subscription_db.get_subscription(tenant_id)
    assert langganan["package"] == "basic"
    assert langganan["status"] == "active"


def test_cascade_saas_billing_failed_memetakan_ke_denied(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    invoice = _siapkan_invoice(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("SAAS_BILLING", tenant_id, invoice["jumlah"],
                                                subscription_invoice_id=invoice["id"])
    snap_webhook.terapkan_status_transaksi(transaksi, "FAILED", sumber="webhook")
    assert billing_invoice_db.get_invoice(invoice["id"])["status"] == "denied"


def test_cascade_saas_billing_idempoten_webhook_dobel_hanya_aktivasi_sekali(single_tenant, monkeypatch):
    tenant_id = single_tenant["tenant_id"]
    invoice = _siapkan_invoice(tenant_id)
    transaksi = snap_payment_db.buat_transaksi("SAAS_BILLING", tenant_id, invoice["jumlah"],
                                                subscription_invoice_id=invoice["id"])

    panggilan = []
    asli = subscription_db.update_status
    def _hitung(*a, **kw):
        panggilan.append(1)
        return asli(*a, **kw)
    monkeypatch.setattr("billing_webhook.subscription_db.update_status", _hitung)

    for _ in range(5):
        snap_webhook.terapkan_status_transaksi(snap_payment_db.get_transaksi(transaksi["id"]), "PAID", sumber="webhook")

    assert len(panggilan) == 1


def test_cross_domain_isolation_booking_tidak_pernah_sentuh_invoice(single_tenant):
    """SESUAI instruksi migrasi #14: "Booking payment tidak pernah dapat
    mengubah SaaS invoice"."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="transfer")
    invoice = _siapkan_invoice(tenant_id)
    transaksi_booking = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"],
                                                         booking_id=booking["id"])

    snap_webhook.terapkan_status_transaksi(transaksi_booking, "PAID", sumber="webhook")

    assert billing_invoice_db.get_invoice(invoice["id"])["status"] == "pending"  # TIDAK tersentuh sama sekali


def test_cross_domain_isolation_saas_billing_tidak_pernah_sentuh_booking(single_tenant):
    """SESUAI instruksi migrasi #14: "SaaS payment tidak pernah dapat
    mengubah booking"."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="transfer")
    invoice = _siapkan_invoice(tenant_id)
    transaksi_billing = snap_payment_db.buat_transaksi("SAAS_BILLING", tenant_id, invoice["jumlah"],
                                                         subscription_invoice_id=invoice["id"])

    snap_webhook.terapkan_status_transaksi(transaksi_billing, "PAID", sumber="webhook")

    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "menunggu_verifikasi"  # TIDAK tersentuh


# ---------------------------------------------------------------------------
# snap_advance_client -- stub PENDING FASPAY (bukti TIDAK ada yang dikarang)
# ---------------------------------------------------------------------------

def test_is_enabled_default_false_tanpa_konfigurasi(single_tenant):
    assert snap_advance_client.is_enabled() is False


def test_channel_create_transaction_semua_melempar_pending_faspay():
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.buat_transaksi_va("BOOKING-1-1-abc", 100000)
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.buat_transaksi_qris("BOOKING-1-1-abc", 100000)
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.buat_transaksi_ewallet("BOOKING-1-1-abc", 100000, "gopay")


def test_cek_status_dan_verifikasi_signature_melempar_pending_faspay():
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.cek_status_transaksi("BOOKING-1-1-abc")
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.verifikasi_signature_webhook("{}", "signature-apa-saja")


def test_ambil_token_b2b_belum_dikonfigurasi_melempar_not_configured():
    with pytest.raises(core.GatewayNotConfiguredError):
        snap_advance_client.ambil_token_b2b()


def test_proses_notifikasi_webhook_melempar_pending_bukan_crash():
    """Envelope webhook LUAR juga PENDING FASPAY (lewat verifikasi_signature_webhook())
    -- endpoint HTTP membungkusnya jadi 503, bukan 500 (lihat test router
    di bawah)."""
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_webhook.proses_notifikasi("{}", "signature-apa-saja")


# ---------------------------------------------------------------------------
# gateway_client_base -- primitif RSA-SHA256 (standar SNAP) SUNGGUHAN, bukan stub
# ---------------------------------------------------------------------------

def _buat_keypair_rsa():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def test_sign_dan_verify_sha256_rsa_round_trip():
    private_pem, public_pem = _buat_keypair_rsa()
    string_to_sign = "client-id-contoh|2026-08-19T10:00:00+07:00"
    signature = core.sign_sha256_rsa(string_to_sign, private_pem)
    assert core.verify_sha256_rsa(string_to_sign, signature, public_pem) is True


def test_verify_sha256_rsa_gagal_kalau_pesan_diubah():
    private_pem, public_pem = _buat_keypair_rsa()
    signature = core.sign_sha256_rsa("pesan-asli", private_pem)
    assert core.verify_sha256_rsa("pesan-yang-diubah", signature, public_pem) is False


def test_verify_sha256_rsa_gagal_kalau_public_key_atau_signature_kosong():
    _, public_pem = _buat_keypair_rsa()
    assert core.verify_sha256_rsa("pesan", "", public_pem) is False
    assert core.verify_sha256_rsa("pesan", "signature-abal", "") is False


def test_sign_sha256_rsa_private_key_kosong_ditolak():
    with pytest.raises(ValueError):
        core.sign_sha256_rsa("pesan", "")


# ---------------------------------------------------------------------------
# snap_advance_db -- konfigurasi
# ---------------------------------------------------------------------------

def test_config_default_kosong_dan_disabled():
    cfg = snap_advance_db.get_config()
    assert cfg["enabled"] is False
    assert cfg["snap_environment"] == "sandbox"
    assert cfg["snap_timeout_detik"] == 30
    assert cfg["snap_retry_max"] == 3


def test_update_config_dan_enabled_true_setelah_lengkap():
    snap_advance_db.update_config(merchant_id="TEST-MID", client_id="TEST-CID",
                                   client_secret="TEST-SECRET", private_key="-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----")
    cfg = snap_advance_db.get_config()
    assert cfg["enabled"] is True
    assert cfg["snap_merchant_id"] == "TEST-MID"


def test_update_config_channel_ewallet_ditolak():
    """"ewallet" SENGAJA belum masuk CHANNEL_VALID (Tahap 2.3: jalur teknis
    belum terkonfirmasi) -- Super Admin TIDAK BISA mengaktifkannya sampai
    ada kepastian, mencegah tenant "memilih" channel yang belum berfungsi."""
    with pytest.raises(ValueError):
        snap_advance_db.update_config(channel_aktif=["ewallet"])


def test_update_config_channel_va_qris_diterima():
    hasil = snap_advance_db.update_config(channel_aktif=["va", "qris"])
    assert hasil["snap_channel_aktif"] == ["va", "qris"]


def test_update_config_environment_tidak_valid_ditolak():
    with pytest.raises(ValueError):
        snap_advance_db.update_config(environment="staging")


# ---------------------------------------------------------------------------
# Router -- konfigurasi superadmin & endpoint webhook
# ---------------------------------------------------------------------------

def test_endpoint_config_superadmin_bisa_lihat_dan_ubah(app_client):
    headers = _buat_superadmin_dan_login(app_client)
    r = app_client.get("/api/superadmin/snap-advance/config", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False

    r2 = app_client.put("/api/superadmin/snap-advance/config", json={"merchant_id": "MID-TEST"}, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["snap_merchant_id"] == "MID-TEST"


def test_endpoint_config_akun_biasa_ditolak(two_tenants):
    client, headers = two_tenants["client"], two_tenants["headers_a"]
    assert client.get("/api/superadmin/snap-advance/config", headers=headers).status_code == 403
    assert client.put("/api/superadmin/snap-advance/config", json={"merchant_id": "x"}, headers=headers).status_code == 403


def test_endpoint_webhook_pending_faspay_balas_503_bukan_crash(app_client):
    r = app_client.post("/api/public/gateway/snap-notification", json={"apa": "saja"})
    assert r.status_code == 503
    assert "PENDING FASPAY" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Channel Direct Debit -- Registrasi/Account Binding (snap_account_binding_db.py)
# ---------------------------------------------------------------------------

def test_channel_valid_menyertakan_direct_debit():
    assert "direct_debit" in snap_payment_db.CHANNEL_VALID


def test_direct_debit_belum_selectable_super_admin():
    """SESUAI keputusan arsitektur: berbeda dari "ewallet", endpoint payment
    Direct Debit LEBIH terkonfirmasi -- TAPI prasyarat binding-nya belum,
    jadi TETAP tidak boleh dipilih Super Admin sebagai channel aktif."""
    assert "direct_debit" not in snap_advance_db.CHANNEL_LABEL
    with pytest.raises(ValueError):
        snap_advance_db.update_config(channel_aktif=["direct_debit"])


def test_buat_binding_booking_wajib_customer_identifier(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    with pytest.raises(ValueError):
        snap_account_binding_db.buat_binding("BOOKING", tenant_id, customer_identifier=None)

    binding = snap_account_binding_db.buat_binding("BOOKING", tenant_id, customer_identifier="081234567890")
    assert binding["transaction_type"] == "BOOKING"
    assert binding["customer_identifier"] == "081234567890"
    assert binding["binding_status"] == "PENDING"
    assert binding["bank_card_token"] is None


def test_buat_binding_saas_billing_tolak_customer_identifier(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    with pytest.raises(ValueError):
        snap_account_binding_db.buat_binding("SAAS_BILLING", tenant_id, customer_identifier="081234567890")

    binding = snap_account_binding_db.buat_binding("SAAS_BILLING", tenant_id)
    assert binding["transaction_type"] == "SAAS_BILLING"
    assert binding["customer_identifier"] is None


def test_catat_hasil_binding_tidak_menimpa_field_kosong(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    binding = snap_account_binding_db.buat_binding("BOOKING", tenant_id, customer_identifier="081234567890")
    hasil1 = snap_account_binding_db.catat_hasil_binding(binding["id"], bank_card_token="tok-abc")
    assert hasil1["bank_card_token"] == "tok-abc"
    hasil2 = snap_account_binding_db.catat_hasil_binding(binding["id"], status="ACTIVE")
    assert hasil2["bank_card_token"] == "tok-abc"  # TIDAK ditimpa NULL oleh panggilan kedua
    assert hasil2["binding_status"] == "ACTIVE"


def test_catat_hasil_binding_status_tidak_dikenal_ditolak(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    binding = snap_account_binding_db.buat_binding("SAAS_BILLING", tenant_id)
    with pytest.raises(ValueError):
        snap_account_binding_db.catat_hasil_binding(binding["id"], status="STATUS_NGAWUR")


def test_list_binding_aktif_hanya_status_active(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    b1 = snap_account_binding_db.buat_binding("BOOKING", tenant_id, customer_identifier="081111111111")
    b2 = snap_account_binding_db.buat_binding("BOOKING", tenant_id, customer_identifier="081111111111")
    snap_account_binding_db.catat_hasil_binding(b1["id"], status="ACTIVE")  # b2 tetap PENDING

    aktif = snap_account_binding_db.list_binding_aktif("BOOKING", tenant_id, customer_identifier="081111111111")
    assert [b["id"] for b in aktif] == [b1["id"]]


def test_cabut_binding_idempoten(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    binding = snap_account_binding_db.buat_binding("SAAS_BILLING", tenant_id)
    snap_account_binding_db.catat_hasil_binding(binding["id"], status="ACTIVE")

    hasil1 = snap_account_binding_db.cabut_binding(binding["id"])
    assert hasil1["binding_status"] == "REVOKED"
    hasil2 = snap_account_binding_db.cabut_binding(binding["id"])  # panggilan kedua, tetap aman
    assert hasil2["binding_status"] == "REVOKED"


def test_buat_transaksi_dengan_binding_id(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id)
    binding = snap_account_binding_db.buat_binding("BOOKING", tenant_id, customer_identifier="081234567890")
    snap_account_binding_db.catat_hasil_binding(binding["id"], status="ACTIVE", bank_card_token="tok-abc")

    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, 100000, booking_id=booking["id"],
                                                channel="direct_debit", binding_id=binding["id"])
    assert transaksi["channel"] == "direct_debit"
    assert transaksi["binding_id"] == binding["id"]


def test_daftarkan_binding_akun_melempar_pending_faspay():
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.daftarkan_binding_akun("BOOKING", customer_details={"phone": "081234567890"})


def test_buat_transaksi_direct_debit_melempar_pending_faspay():
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.buat_transaksi_direct_debit("BOOKING-1-1-abc", 100000, "tok-abc")
