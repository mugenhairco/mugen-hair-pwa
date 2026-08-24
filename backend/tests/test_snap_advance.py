"""test_snap_advance.py — Migrasi Faspay SNAP Advance
=============================================================================
Cakupan: arsitektur, unified payment reference, state machine, webhook
dispatch BOOKING vs SAAS_BILLING, idempotency, cross-domain isolation,
konfigurasi -- DITAMBAH (audit lanjutan, dokumen resmi SNAP VA/Direct
Debit/QRIS dari Faspay) flow VA/Direct Debit/QRIS SUNGGUHAN: header/
signature lengkap, Create/Inquiry/Status/Notification per produk,
verifikasi signature webhook, dan proses_notifikasi() end-to-end (BUKAN
lagi PENDING FASPAY). E-Wallet (audit lanjutan #4, konfirmasi tertulis
Faspay) BUKAN produk terpisah -- kategori channel DI DALAM Direct Debit,
diuji lewat buat_transaksi_direct_debit() yang sama dengan channel code
E-Wallet resmi (snap_advance_db.DIRECT_DEBIT_CHANNEL_CODE_LABEL).
Registrasi/Account Binding Direct Debit TETAP diuji sebagai PENDING
FASPAY (dokumen resmi belum menyertakan bagian itu, sengaja tidak
ditebak).

TIDAK ADA test yang memanggil Faspay SUNGGUHAN lewat jaringan -- panggilan
HTTP ke Faspay di-mock lewat monkeypatch atas gateway_client_base.post_json_raw()
(lihat _RekamPanggilan di bawah), supaya request-building (header/signature/
payload) teruji tanpa kredensial sandbox sungguhan."""

import itertools
import json

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
import tenant_db
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


def test_buat_transaksi_qris_belum_dikonfigurasi_melempar_not_configured(single_tenant):
    """QRIS sudah diimplementasikan sungguhan -- tanpa channelCode QRIS
    default terisi, melempar GatewayNotConfiguredError (BUKAN lagi PENDING
    FASPAY)."""
    with pytest.raises(core.GatewayNotConfiguredError):
        snap_advance_client.buat_transaksi_qris("BOOKING-1-1-abc", 100000, {"whatsapp": "081234567890"})


def test_buat_transaksi_va_channel_code_tidak_dikenal_melempar_not_configured(single_tenant):
    """Fitur multi-bank VA: channel_code sekarang parameter WAJIB dari
    pemanggil (bukan lagi dibaca dari config) -- kode bank yang tidak
    dikenal/valid tetap melempar GatewayNotConfiguredError."""
    with pytest.raises(core.GatewayNotConfiguredError):
        snap_advance_client.buat_transaksi_va("BOOKING-1-1-abc", 100000, channel_code="999")


def test_cek_status_channel_belum_didukung_melempar_pending_faspay():
    """cek_status_transaksi() tanpa channel (atau channel selain
    va/direct_debit/qris) TETAP PENDING FASPAY -- dispatcher generik, lihat
    inquiry_status_va()/status_direct_debit()/query_payment_qris() untuk
    channel yang sudah diimplementasikan."""
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.cek_status_transaksi("BOOKING-1-1-abc")
    with pytest.raises(snap_advance_client.SnapAdvancePendingError):
        snap_advance_client.cek_status_transaksi("BOOKING-1-1-abc", channel="ewallet")


def test_verifikasi_signature_webhook_tanpa_konfigurasi_return_false(single_tenant):
    """Signature verification SUDAH diimplementasikan sungguhan -- tanpa
    Faspay Public Key terisi, return False (BUKAN exception), pola sama
    persis gateway_client_base.py::verify_sha256_rsa() dkk (pemanggil WAJIB
    menolak notifikasi selama kredensial belum dikonfigurasi)."""
    assert snap_advance_client.verifikasi_signature_webhook(
        "{}", "signature-apa-saja", "2026-08-21T10:00:00+07:00", path="/v1.0/transfer-va/payment") is False


def test_ambil_token_b2b_belum_dikonfigurasi_melempar_not_configured():
    with pytest.raises(core.GatewayNotConfiguredError):
        snap_advance_client.ambil_token_b2b()


def test_proses_notifikasi_webhook_signature_tidak_valid_ditolak(single_tenant):
    """Envelope webhook LUAR SUDAH diimplementasikan sungguhan -- tanpa
    Faspay Public Key terisi (atau signature yang memang salah), DITOLAK
    lewat ValueError (endpoint HTTP membungkusnya jadi 400, BUKAN lagi 503
    "PENDING FASPAY" -- lihat test router di bawah)."""
    with pytest.raises(ValueError, match="[Ss]ignature"):
        snap_webhook.proses_notifikasi("{}", "signature-apa-saja", "2026-08-21T10:00:00+07:00",
                                        "va", "/v1.0/transfer-va/payment")


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
    """"enabled" TIDAK LAGI mensyaratkan Client ID/Client Secret (KOREKSI --
    klarifikasi resmi Faspay: signature SELURUH request SNAP hanya memakai
    X-TIMESTAMP/X-SIGNATURE/X-PARTNER-ID/X-EXTERNAL-ID/CHANNEL-ID, Client
    ID/Secret TIDAK PERNAH dipakai) -- field yang genuinely disyaratkan:
    merchant_id, partner_id, channel_id, private_key."""
    snap_advance_db.update_config(merchant_id="TEST-MID", partner_id="TEST-PID", channel_id="77001",
                                   private_key="-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----")
    cfg = snap_advance_db.get_config()
    assert cfg["enabled"] is True
    assert cfg["snap_merchant_id"] == "TEST-MID"


def test_update_config_enabled_tetap_false_tanpa_client_id_secret():
    """Client ID/Client Secret SENGAJA tidak jadi syarat "enabled" -- boleh
    dikosongkan sepenuhnya (sesuai instruksi tertulis Faspay), asalkan
    merchant_id/partner_id/channel_id/private_key sudah lengkap."""
    snap_advance_db.update_config(merchant_id="TEST-MID", partner_id="TEST-PID", channel_id="77001",
                                   private_key="-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----",
                                   client_id="", client_secret="")
    cfg = snap_advance_db.get_config()
    assert cfg["enabled"] is True
    assert cfg["snap_client_id"] == ""


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


def test_endpoint_webhook_tanpa_signature_balas_400_bukan_crash(app_client):
    """Signature verification SUDAH sungguhan -- payload tanpa signature
    valid (atau Faspay Public Key belum dikonfigurasi Super Admin) ditolak
    400 (validasi gagal), BUKAN lagi 503 "PENDING FASPAY". Path RESMI VA
    (audit lanjutan #3, klarifikasi Faspay) -- lihat routers/snap_advance.py."""
    r = app_client.post("/v1.0/transfer-va/payment", json={"apa": "saja"})
    assert r.status_code == 400
    assert "ignature" in r.json()["detail"]


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


def test_buat_transaksi_direct_debit_belum_dikonfigurasi_melempar_not_configured(single_tenant):
    """Direct Debit Payment SUDAH diimplementasikan sungguhan (dokumen resmi
    Faspay) -- tanpa Merchant ID terisi, melempar GatewayNotConfiguredError
    (BUKAN lagi PENDING FASPAY). `channel_code` (bukan lagi bank_card_token)
    sekarang parameter positional ke-3 -- lihat docstring buat_transaksi_direct_debit()."""
    with pytest.raises(core.GatewayNotConfiguredError):
        snap_advance_client.buat_transaksi_direct_debit("BOOKING-1-1-abc", 100000, "812")


# ---------------------------------------------------------------------------
# Audit lanjutan -- flow VA & Direct Debit SUNGGUHAN (dokumen resmi Faspay)
# ---------------------------------------------------------------------------

def _pasang_kredensial_snap():
    """Isi kredensial minimal SNAP Advance (sandbox) supaya flow VA/Direct
    Debit/QRIS bisa diuji end-to-end tanpa jaringan sungguhan (lihat
    _RekamPanggilan)."""
    private_pem, public_pem = _buat_keypair_rsa()
    snap_advance_db.update_config(
        environment="sandbox", sandbox_base_url="https://debit-sandbox.faspay.co.id",
        merchant_id="37070", partner_id="37070", client_id="CLIENT-TEST", client_secret="SECRET-TEST",
        private_key=private_pem, faspay_public_key=public_pem, channel_id="77001",
        va_bank_aktif=["702"], qris_channel_code="711",
    )
    return private_pem, public_pem


class _RekamPanggilan:
    """Pengganti gateway_client_base.post_json_raw() -- merekam tiap
    panggilan (url/raw_body/headers) DAN membalas respons Faspay palsu yang
    cocok bentuknya dengan dokumen resmi, supaya request-building (header/
    signature/payload) teruji tanpa jaringan sungguhan."""
    def __init__(self):
        self.panggilan = []

    def __call__(self, url, raw_body, headers, timeout=30):
        self.panggilan.append({"url": url, "raw_body": raw_body, "headers": headers})
        body = json.loads(raw_body) if raw_body else {}
        if url.endswith("/access-token/b2b"):
            return {"accessToken": "token-uji-123"}
        if url.endswith("/transfer-va/create-va"):
            return {
                "responseCode": "2002500", "responseMessage": "Success",
                "virtualAccountData": {
                    "partnerServiceId": "70200000", "customerNo": "00000000000012345",
                    "virtualAccountNo": "7020000000000000000012345", "trxId": body.get("trxId"),
                    "expiredDate": "20261231T235959Z",
                },
            }
        if url.endswith("/transfer-va/status"):
            return {"responseCode": "2002600", "responseMessage": "Success",
                    "virtualAccountData": {"paymentFlagStatus": "00", "paymentFlagReason": {"english": "Success"}}}
        if url.endswith("/debit/payment-host-to-host"):
            return {"responseCode": "2005400", "responseMessage": "Success", "referenceNo": "REF999",
                     "partnerReferenceNo": body.get("partnerReferenceNo"),
                     "appRedirectUrl": "ovo://push/xyz",
                     "webRedirectUrl": "https://debit-sandbox.faspay.co.id/pws/xyz",
                     "webUrl": "https://debit-sandbox.faspay.co.id/pws/xyz-web"}
        if url.endswith("/debit/status"):
            return {"responseCode": "2005500", "responseMessage": "Success", "latestTransactionStatus": "00"}
        if url.endswith("/qr/qr-mpm-generate"):
            return {"responseCode": "2004700", "responseMessage": "Success", "referenceNo": "QRREF999",
                     "partnerReferenceNo": body.get("partnerReferenceNo"), "qrUrl": "https://debit-sandbox.faspay.co.id/qr/xyz.png",
                     "additionalInfo": {"qrImageUrl": "https://debit-sandbox.faspay.co.id/pws/qr-display", "merchantId": "37070",
                                         "amount": body.get("amount")}}
        if url.endswith("/qr/qr-mpm-query"):
            return {"responseCode": "2005100", "responseMessage": "Success", "latestTransactionStatus": "00"}
        raise AssertionError(f"URL tidak terduga dalam mock: {url}")


def test_buat_transaksi_va_sukses_header_dan_payload_lengkap(single_tenant, monkeypatch):
    """SATU panggilan HTTP saja (BUKAN token B2B + create VA) -- audit
    lanjutan (halaman resmi "Signature SNAP" Faspay) membuktikan Create VA
    TIDAK butuh Authorization/Bearer, signature langsung dari private key
    merchant, jadi ambil_token_b2b() TIDAK dipanggil dari jalur ini."""
    private_pem, _ = _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    hasil = snap_advance_client.buat_transaksi_va(
        "BOOKING-1-42-abc123456789", 100000, {"nama": "Budi Santoso", "whatsapp": "081234567890"},
        channel_code="702")

    assert hasil["va_number"] == "7020000000000000000012345"
    assert len(rekam.panggilan) == 1
    header_va = rekam.panggilan[0]["headers"]
    for h in ("X-TIMESTAMP", "X-SIGNATURE", "X-PARTNER-ID", "X-EXTERNAL-ID", "CHANNEL-ID"):
        assert h in header_va, f"Header {h} wajib ada di service call SNAP"
    assert "Authorization" not in header_va
    assert header_va["CHANNEL-ID"] == "77001"
    assert header_va["X-PARTNER-ID"] == "37070"
    body = json.loads(rekam.panggilan[0]["raw_body"])
    assert body["trxId"] == "BOOKING-1-42-abc123456789"
    assert body["additionalInfo"]["channelCode"] == "702"
    assert body["virtualAccountPhone"] == "6281234567890"
    assert body["totalAmount"] == {"value": "100000.00", "currency": "IDR"}


def test_buat_transaksi_va_signature_cocok_formula_resmi_faspay(single_tenant, monkeypatch):
    """Buktikan X-SIGNATURE BENAR-BENAR RSA-SHA256 atas stringToSign formula
    resmi Faspay (Method:EndpointUrl:bodyHash:Timestamp, TANPA access
    token) -- dihitung ulang dengan public key pasangan private key yang
    dipakai, bukan sekadar nilai sembarangan."""
    private_pem, public_pem = _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    snap_advance_client.buat_transaksi_va("BOOKING-1-42-abc123456789", 100000, channel_code="702")

    headers, raw_body = rekam.panggilan[0]["headers"], rekam.panggilan[0]["raw_body"]
    body_hash = core.sha256_lowercase_hex(raw_body)
    string_to_sign = f"POST:{snap_advance_client.PATH_VA_CREATE}:{body_hash}:{headers['X-TIMESTAMP']}"
    assert core.verify_sha256_rsa(string_to_sign, headers["X-SIGNATURE"], public_pem) is True


def test_inquiry_status_va_sukses(single_tenant, monkeypatch):
    _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    hasil = snap_advance_client.inquiry_status_va("BOOKING-1-42-abc", "7020000000000000000012345", "702")
    assert hasil["paymentFlagStatus"] == "00"


def test_buat_transaksi_direct_debit_sukses(single_tenant, monkeypatch):
    _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    hasil = snap_advance_client.buat_transaksi_direct_debit(
        "BOOKING-1-42-abc123456789", 50000, "812", customer_details={"nama": "Budi", "whatsapp": "081234567890"})

    assert hasil["provider_transaction_id"] == "REF999"
    # BUGFIX (audit lanjutan #4): ketiga field redirect resmi Faspay
    # (appRedirectUrl/webRedirectUrl/webUrl) HARUS ditangkap terpisah --
    # sebelumnya webUrl diam-diam hilang.
    assert hasil["app_redirect_url"] == "ovo://push/xyz"
    assert hasil["web_redirect_url"] == "https://debit-sandbox.faspay.co.id/pws/xyz"
    assert hasil["web_url"] == "https://debit-sandbox.faspay.co.id/pws/xyz-web"
    assert hasil["ewallet_deeplink_url"] == "https://debit-sandbox.faspay.co.id/pws/xyz"
    body = json.loads(rekam.panggilan[-1]["raw_body"])
    assert body["partnerReferenceNo"] == "BOOKING-1-42-abc123456789"
    assert body["merchantId"] == "37070"
    assert body["additionalInfo"]["channelCode"] == "812"
    assert "bankCardToken" not in body  # channel non-BRI TIDAK wajib bankCardToken (lihat dokumen resmi)


def test_buat_transaksi_direct_debit_channel_code_tidak_dikenal_ditolak(single_tenant):
    """channel_code Direct Debit sekarang divalidasi terhadap 14 kode resmi
    Faspay (snap_advance_db.DIRECT_DEBIT_CHANNEL_CODE_VALID, audit lanjutan
    #4) -- kode di luar daftar itu ditolak jelas, BUKAN dikirim mentah ke
    Faspay tanpa validasi."""
    _pasang_kredensial_snap()
    with pytest.raises(ValueError, match="channelCode"):
        snap_advance_client.buat_transaksi_direct_debit("BOOKING-1-42-abc", 50000, "999")


def test_buat_transaksi_direct_debit_ewallet_channel_code_diterima(single_tenant, monkeypatch):
    """E-Wallet (audit lanjutan #4, konfirmasi tertulis Faspay) BUKAN produk
    terpisah -- channel code berkategori E-Wallet (mis. ShopeePay App 713,
    LinkAja App 716, OVO 812, DANA 819, LinkAja 302, DANA Subs 722, OVO
    OpenAPI 720) lewat buat_transaksi_direct_debit() yang SAMA, TIDAK ada
    fungsi/endpoint terpisah lagi (buat_transaksi_ewallet() sudah dihapus)."""
    _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    for kode in ("713", "716", "812", "819", "302", "722", "720"):
        assert snap_advance_db.DIRECT_DEBIT_CHANNEL_CODE_KATEGORI[kode].startswith("E-Wallet")
        hasil = snap_advance_client.buat_transaksi_direct_debit("BOOKING-1-42-abc", 50000, kode)
        assert hasil["provider_transaction_id"] == "REF999"


def test_buat_transaksi_direct_debit_bri_menyertakan_bank_card_token(single_tenant, monkeypatch):
    _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    snap_advance_client.buat_transaksi_direct_debit(
        "BOOKING-1-42-abc123456789", 50000, "714", bank_card_token="card_xyz")

    body = json.loads(rekam.panggilan[-1]["raw_body"])
    assert body["bankCardToken"] == "card_xyz"


def test_status_direct_debit_sukses(single_tenant, monkeypatch):
    _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    hasil = snap_advance_client.status_direct_debit("BOOKING-1-42-abc", "REF999", "812")
    assert hasil["latestTransactionStatus"] == "00"


def test_cek_status_transaksi_dispatcher_va_dan_direct_debit(single_tenant, monkeypatch):
    _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    hasil_va = snap_advance_client.cek_status_transaksi(
        "BOOKING-1-42-abc", channel="va", virtual_account_no="7020000000000000000012345", channel_code="702")
    assert hasil_va["paymentFlagStatus"] == "00"

    hasil_dd = snap_advance_client.cek_status_transaksi(
        "BOOKING-1-42-abc", channel="direct_debit", original_reference_no="REF999", channel_code="812")
    assert hasil_dd["latestTransactionStatus"] == "00"

    hasil_qris = snap_advance_client.cek_status_transaksi(
        "BOOKING-1-42-abc", channel="qris", original_reference_no="QRREF999", channel_code="711")
    assert hasil_qris["latestTransactionStatus"] == "00"


def test_buat_transaksi_qris_sukses(single_tenant, monkeypatch):
    _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    hasil = snap_advance_client.buat_transaksi_qris(
        "BOOKING-1-42-abc123456789", 25000, {"whatsapp": "081234567890"})

    assert hasil["provider_transaction_id"] == "QRREF999"
    assert hasil["qr_url"] == "https://debit-sandbox.faspay.co.id/qr/xyz.png"
    assert hasil["qr_content"] == "https://debit-sandbox.faspay.co.id/pws/qr-display"
    body = json.loads(rekam.panggilan[-1]["raw_body"])
    assert body["partnerReferenceNo"] == "BOOKING-1-42-abc123456789"
    assert body["merchantId"] == "37070"
    assert body["additionalInfo"]["channelCode"] == "711"
    assert body["additionalInfo"]["phoneNo"] == "6281234567890"
    assert body["amount"] == {"value": "25000.00", "currency": "IDR"}


def test_buat_transaksi_qris_tanpa_whatsapp_ditolak_jelas(single_tenant):
    """phoneNo WAJIB per dokumen resmi (beda dari VA yang opsional) --
    ditolak ValueError jelas, BUKAN mengirim field kosong ke Faspay."""
    _pasang_kredensial_snap()
    with pytest.raises(ValueError, match="WhatsApp"):
        snap_advance_client.buat_transaksi_qris("BOOKING-1-42-abc", 25000)


def test_query_payment_qris_sukses(single_tenant, monkeypatch):
    _pasang_kredensial_snap()
    rekam = _RekamPanggilan()
    monkeypatch.setattr(core, "post_json_raw", rekam)

    hasil = snap_advance_client.query_payment_qris("BOOKING-1-42-abc", "QRREF999", "711")
    assert hasil["latestTransactionStatus"] == "00"


# ---------------------------------------------------------------------------
# Audit lanjutan -- verifikasi signature webhook & proses_notifikasi() SUNGGUHAN
# ---------------------------------------------------------------------------

def _tandatangani_notifikasi(raw_body: str, private_pem_faspay: str, path: str) -> tuple:
    """Simulasikan Faspay menandatangani body notifikasi dengan private key
    Faspay (di sisi kita, `snap_faspay_public_key` yang dikonfigurasi adalah
    PASANGAN public key dari private key ini) -- pola string-to-sign SAMA
    dengan snap_advance_client.py::verifikasi_signature_webhook()."""
    ts = core.snap_timestamp_wib()
    body_hash = core.sha256_lowercase_hex(raw_body)
    string_to_sign = f"POST:{path}:{body_hash}:{ts}"
    signature = core.sign_sha256_rsa(string_to_sign, private_pem_faspay)
    return signature, ts


def test_verifikasi_signature_webhook_round_trip_sukses(single_tenant):
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)
    raw_body = json.dumps({"trxId": "BOOKING-1-1-abc"})
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/transfer-va/payment")

    assert snap_advance_client.verifikasi_signature_webhook(
        raw_body, signature, ts, path="/v1.0/transfer-va/payment") is True


def test_verifikasi_signature_webhook_gagal_kalau_body_diubah(single_tenant):
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)
    raw_body = json.dumps({"trxId": "BOOKING-1-1-abc"})
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/transfer-va/payment")

    raw_body_diubah = json.dumps({"trxId": "BOOKING-1-1-LAIN"})
    assert snap_advance_client.verifikasi_signature_webhook(
        raw_body_diubah, signature, ts, path="/v1.0/transfer-va/payment") is False


def test_map_latest_transaction_status_kode_dikenal():
    assert snap_webhook._map_latest_transaction_status("00") == snap_payment_db.STATUS_PAID
    assert snap_webhook._map_latest_transaction_status("03") == snap_payment_db.STATUS_PENDING
    assert snap_webhook._map_latest_transaction_status("05") == snap_payment_db.STATUS_CANCELLED
    assert snap_webhook._map_latest_transaction_status("06") == snap_payment_db.STATUS_FAILED
    assert snap_webhook._map_latest_transaction_status("07") == snap_payment_db.STATUS_EXPIRED


def test_map_latest_transaction_status_refund_ditolak_bukan_disalahartikan():
    """"04" (Refunded) SENGAJA tidak punya representasi status internal --
    lihat catatan snap_webhook.py. Notifikasi refund ditolak jelas, TIDAK
    disalahartikan jadi status lain."""
    with pytest.raises(ValueError, match="04"):
        snap_webhook._map_latest_transaction_status("04")


def test_ekstrak_notifikasi_va_dynamic():
    payload = {
        "trxId": "BOOKING-1-1-abc", "paymentRequestId": "PR-123",
        "additionalInfo": {"latestTransactionStatus": "00", "paymentDate": "2026-08-21 10:00:00"},
    }
    ref, prov_id, status, paid_at = snap_webhook._ekstrak_notifikasi(payload, "va")
    assert (ref, prov_id, status, paid_at) == ("BOOKING-1-1-abc", "PR-123", "00", "2026-08-21 10:00:00")


def test_ekstrak_notifikasi_direct_debit_status_top_level_bukan_di_additional_info():
    """BEDA dari VA -- latestTransactionStatus Direct Debit field TOP-LEVEL,
    BUKAN di dalam additionalInfo (dokumen resmi Faspay)."""
    payload = {
        "originalPartnerReferenceNo": "BOOKING-1-1-abc", "originalReferenceNo": "REF999",
        "latestTransactionStatus": "00", "additionalInfo": {"paymentDate": "2026-08-21 10:00:00", "channelCode": "812"},
    }
    ref, prov_id, status, paid_at = snap_webhook._ekstrak_notifikasi(payload, "direct_debit")
    assert (ref, prov_id, status, paid_at) == ("BOOKING-1-1-abc", "REF999", "00", "2026-08-21 10:00:00")


def test_ekstrak_notifikasi_jenis_tidak_dikenal_ditolak():
    """`jenis` sekarang EKSPLISIT dari endpoint yang dipukul (routers/
    snap_advance.py) -- jenis di luar va/qris/direct_debit ditolak jelas,
    BUKAN ditebak dari isi payload seperti sebelum path per-produk
    dikonfirmasi Faspay (lihat catatan modul snap_webhook.py)."""
    with pytest.raises(ValueError):
        snap_webhook._ekstrak_notifikasi({"apa": "saja"}, "jenis_ngawur")


def test_ekstrak_notifikasi_qris_bentuk_sama_dengan_direct_debit():
    """QRIS & Direct Debit KEBETULAN sama persis bentuk payload notifikasi
    -- _ekstrak_notifikasi() tidak perlu cabang terpisah untuk parsing-nya,
    tapi tetap dibedakan lewat `jenis` eksplisit (endpoint mana yang
    dipukul, lihat routers/snap_advance.py) supaya balas_notifikasi() bisa
    membangun acknowledgment yang benar per produk."""
    payload = {
        "originalPartnerReferenceNo": "BOOKING-1-1-abc", "originalReferenceNo": "QRREF999",
        "latestTransactionStatus": "00", "additionalInfo": {"paymentDate": "2026-08-21 10:00:00",
                                                              "channelCode": "711", "merchantId": "37070"},
    }
    ref, prov_id, status, paid_at = snap_webhook._ekstrak_notifikasi(payload, "qris")
    assert (ref, prov_id, status, paid_at) == ("BOOKING-1-1-abc", "QRREF999", "00", "2026-08-21 10:00:00")


def test_balas_notifikasi_bentuk_sesuai_dokumen_resmi_per_jenis():
    ack_va = snap_webhook.balas_notifikasi("va", {
        "trxId": "x", "partnerServiceId": "70200000", "customerNo": "123",
        "virtualAccountNo": "70200000123", "paymentRequestId": "PR-1", "paidAmount": {"value": "1.00", "currency": "IDR"},
    })
    assert ack_va["responseCode"] == "2002500"
    assert ack_va["virtualAccountData"]["virtualAccountNo"] == "70200000123"

    ack_dd = snap_webhook.balas_notifikasi(
        "direct_debit", {"originalPartnerReferenceNo": "x", "additionalInfo": {"channelCode": "812"}})
    assert ack_dd == {"responseCode": "2005600", "responseMessage": "Request has been processed successfully"}

    ack_qris = snap_webhook.balas_notifikasi(
        "qris", {"originalPartnerReferenceNo": "x", "additionalInfo": {"channelCode": "711"}})
    assert ack_qris == {"responseCode": "2005200", "responseMessage": "Request has been processed successfully"}


def test_proses_notifikasi_va_end_to_end_transisi_ke_paid(single_tenant):
    """BUKTI UTAMA: notifikasi VA SUNGGUHAN (bukan lagi PENDING FASPAY)
    benar-benar mengubah status transaksi ke PAID & cascade ke booking --
    signature valid, trxId cocok, status ter-mapping benar."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="qris")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"],
                                                booking_id=booking["id"], channel="va")
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)

    payload = {
        "partnerServiceId": "70200000", "customerNo": "00000000000012345",
        "virtualAccountNo": "7020000000000000000012345", "paymentRequestId": "PR-1",
        "trxId": transaksi["payment_reference"],
        "paidAmount": {"value": f"{booking['total_harga']:.2f}", "currency": "IDR"},
        "additionalInfo": {"paymentDate": "2026-08-21 10:00:00", "channelCode": "702",
                            "merchantId": "37070", "latestTransactionStatus": "00",
                            "transactionStatusDesc": "success"},
    }
    raw_body = json.dumps(payload)
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/transfer-va/payment")

    hasil = snap_webhook.proses_notifikasi(raw_body, signature, ts, "va", "/v1.0/transfer-va/payment")

    assert hasil["status"] == "PAID"
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"


def test_proses_notifikasi_direct_debit_end_to_end_transisi_ke_paid(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    invoice = _siapkan_invoice(tenant_id, nominal=75000)
    transaksi = snap_payment_db.buat_transaksi("SAAS_BILLING", tenant_id, 75000,
                                                subscription_invoice_id=invoice["id"], channel="direct_debit")
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)

    payload = {
        "originalPartnerReferenceNo": transaksi["payment_reference"], "originalReferenceNo": "REF999",
        "amount": {"value": "75000.00", "currency": "IDR"},
        "additionalInfo": {"paymentDate": "2026-08-21 10:00:00", "channelCode": "812"},
        "merchantId": "37070", "latestTransactionStatus": "00", "transactionStatusDesc": "success",
    }
    raw_body = json.dumps(payload)
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/debit/notify")

    hasil = snap_webhook.proses_notifikasi(raw_body, signature, ts, "direct_debit", "/v1.0/debit/notify")

    assert hasil["status"] == "PAID"
    assert billing_invoice_db.get_invoice(invoice["id"])["status"] == "paid"


def test_proses_notifikasi_qris_end_to_end_transisi_ke_paid(single_tenant):
    """Sama seperti test Direct Debit di atas -- membuktikan notifikasi
    QRIS (bentuk payload KEBETULAN sama dengan Direct Debit, dibedakan
    lewat channelCode) diproses benar & channelCode QRIS TIDAK disalah-
    tafsirkan jadi Direct Debit."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="qris")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"],
                                                booking_id=booking["id"], channel="qris")
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)

    payload = {
        "originalPartnerReferenceNo": transaksi["payment_reference"], "originalReferenceNo": "QRREF999",
        "amount": {"value": f"{booking['total_harga']:.2f}", "currency": "IDR"},
        "additionalInfo": {"paymentDate": "2026-08-21 10:00:00", "channelCode": "711", "merchantId": "37070"},
        "latestTransactionStatus": "00", "transactionStatusDesc": "success",
    }
    raw_body = json.dumps(payload)
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/qr/qr-mpm-notify")

    hasil = snap_webhook.proses_notifikasi(raw_body, signature, ts, "qris", "/v1.0/qr/qr-mpm-notify")

    assert hasil["status"] == "PAID"
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"
    assert snap_webhook.balas_notifikasi("qris", payload)["responseCode"] == "2005200"  # ack QRIS, BUKAN Direct Debit (2005600)


def test_proses_notifikasi_idempoten_signature_valid_dikirim_dua_kali(single_tenant):
    """SESUAI instruksi migrasi #6 -- webhook dobel (walau signature-nya
    valid tiap kali) TETAP hanya satu transisi status sungguhan."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="transfer")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"],
                                                booking_id=booking["id"], channel="va")
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)
    payload = {"trxId": transaksi["payment_reference"],
               "additionalInfo": {"latestTransactionStatus": "00", "paymentDate": "2026-08-21 10:00:00"}}
    raw_body = json.dumps(payload)

    for _ in range(3):
        signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/transfer-va/payment")
        hasil = snap_webhook.proses_notifikasi(raw_body, signature, ts, "va", "/v1.0/transfer-va/payment")
        assert hasil["status"] == "PAID"

    log = snap_payment_db.list_status_log(transaksi["id"])
    transisi_sungguhan = [l for l in log if l["status_baru"] == "PAID" and l["sumber"] == "webhook"]
    assert len(transisi_sungguhan) == 1


def test_endpoint_webhook_signature_valid_balas_200_dan_transisi_paid(app_client, single_tenant):
    """Bukti end-to-end LEWAT HTTP (bukan panggil fungsi Python langsung) --
    endpoint resmi VA /v1.0/transfer-va/payment (audit lanjutan #3,
    klarifikasi Faspay) benar-benar memproses notifikasi VA yang
    signature-nya valid, BUKAN lagi 503 PENDING FASPAY."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="qris")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"],
                                                booking_id=booking["id"], channel="va")
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)
    payload = {"trxId": transaksi["payment_reference"],
               "additionalInfo": {"latestTransactionStatus": "00", "paymentDate": "2026-08-21 10:00:00"}}
    raw_body = json.dumps(payload)
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/transfer-va/payment")

    r = app_client.post("/v1.0/transfer-va/payment", content=raw_body,
                         headers={"X-SIGNATURE": signature, "X-TIMESTAMP": ts, "Content-Type": "application/json"})

    # BUGFIX (audit lanjutan): respons HTTP-nya sekarang body acknowledgment
    # RESMI Faspay (format VA), BUKAN lagi echo objek transaksi internal --
    # status PAID dibuktikan lewat efek sampingnya (booking terverifikasi).
    assert r.status_code == 200, r.text
    assert r.json()["responseCode"] == "2002500"
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"


def test_endpoint_webhook_qris_path_resmi_balas_200_dan_transisi_paid(app_client, single_tenant):
    """Bukti end-to-end LEWAT HTTP untuk path resmi QRIS
    /v1.0/qr/qr-mpm-notify (audit lanjutan #3, klarifikasi Faspay) --
    payload BENTUKNYA sama dengan Direct Debit, TAPI diproses sebagai QRIS
    (ack 2005200, BUKAN 2005600) karena endpoint yang dipukul sudah
    menyatakan jenisnya, TIDAK PERLU channelCode ditebak lagi."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="qris")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"],
                                                booking_id=booking["id"], channel="qris")
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)
    payload = {
        "originalPartnerReferenceNo": transaksi["payment_reference"], "originalReferenceNo": "QRREF999",
        "amount": {"value": f"{booking['total_harga']:.2f}", "currency": "IDR"},
        "additionalInfo": {"paymentDate": "2026-08-21 10:00:00", "channelCode": "711", "merchantId": "37070"},
        "latestTransactionStatus": "00", "transactionStatusDesc": "success",
    }
    raw_body = json.dumps(payload)
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/qr/qr-mpm-notify")

    r = app_client.post("/v1.0/qr/qr-mpm-notify", content=raw_body,
                         headers={"X-SIGNATURE": signature, "X-TIMESTAMP": ts, "Content-Type": "application/json"})

    assert r.status_code == 200, r.text
    assert r.json() == {"responseCode": "2005200", "responseMessage": "Request has been processed successfully"}
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "terverifikasi"


def test_endpoint_webhook_direct_debit_path_resmi_balas_200_dan_transisi_paid(app_client, single_tenant):
    """Bukti end-to-end LEWAT HTTP untuk path resmi Direct Debit
    /v1.0/debit/notify (audit lanjutan #3, klarifikasi Faspay)."""
    tenant_id = single_tenant["tenant_id"]
    invoice = _siapkan_invoice(tenant_id, nominal=75000)
    transaksi = snap_payment_db.buat_transaksi("SAAS_BILLING", tenant_id, 75000,
                                                subscription_invoice_id=invoice["id"], channel="direct_debit")
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)
    payload = {
        "originalPartnerReferenceNo": transaksi["payment_reference"], "originalReferenceNo": "REF999",
        "amount": {"value": "75000.00", "currency": "IDR"},
        "additionalInfo": {"paymentDate": "2026-08-21 10:00:00", "channelCode": "812"},
        "merchantId": "37070", "latestTransactionStatus": "00", "transactionStatusDesc": "success",
    }
    raw_body = json.dumps(payload)
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/debit/notify")

    r = app_client.post("/v1.0/debit/notify", content=raw_body,
                         headers={"X-SIGNATURE": signature, "X-TIMESTAMP": ts, "Content-Type": "application/json"})

    assert r.status_code == 200, r.text
    assert r.json() == {"responseCode": "2005600", "responseMessage": "Request has been processed successfully"}
    assert billing_invoice_db.get_invoice(invoice["id"])["status"] == "paid"


def test_endpoint_webhook_signature_dari_endpoint_lain_ditolak(app_client, single_tenant):
    """`path` ikut dihitung dalam formula signature (EndpointUrl di
    stringToSign) -- signature yang ditandatangani untuk path VA HARUS
    ditolak kalau dikirim ke path QRIS/Direct Debit, walau body-nya sama
    persis. Membuktikan ketiga endpoint benar-benar terisolasi satu sama
    lain, bukan cuma alias yang sama."""
    tenant_id = single_tenant["tenant_id"]
    booking = _siapkan_booking(tenant_id, metode="qris")
    transaksi = snap_payment_db.buat_transaksi("BOOKING", tenant_id, booking["total_harga"],
                                                booking_id=booking["id"], channel="va")
    private_faspay, public_faspay = _buat_keypair_rsa()
    snap_advance_db.update_config(faspay_public_key=public_faspay)
    payload = {"trxId": transaksi["payment_reference"],
               "additionalInfo": {"latestTransactionStatus": "00", "paymentDate": "2026-08-21 10:00:00"}}
    raw_body = json.dumps(payload)
    signature, ts = _tandatangani_notifikasi(raw_body, private_faspay, "/v1.0/transfer-va/payment")

    r = app_client.post("/v1.0/qr/qr-mpm-notify", content=raw_body,
                         headers={"X-SIGNATURE": signature, "X-TIMESTAMP": ts, "Content-Type": "application/json"})

    assert r.status_code == 400, r.text
    assert booking_db.get_booking(booking["id"])["status_pembayaran"] == "menunggu_verifikasi"  # TIDAK berubah


# ---------------------------------------------------------------------------
# Audit lanjutan -- config CHANNEL-ID / channelCode VA & masking secret
# ---------------------------------------------------------------------------

def test_update_config_channel_id_dan_va_bank_aktif(single_tenant):
    hasil = snap_advance_db.update_config(channel_id="77001", va_bank_aktif=["702", "801"])
    assert hasil["snap_channel_id"] == "77001"
    assert hasil["snap_va_bank_aktif"] == ["702", "801"]


def test_update_config_va_bank_aktif_kode_tidak_dikenal_ditolak(single_tenant):
    with pytest.raises(ValueError):
        snap_advance_db.update_config(va_bank_aktif=["999"])


def test_get_config_tidak_pernah_membocorkan_field_rahasia(single_tenant):
    """BUGFIX keamanan (audit): private key/client secret/webhook secret
    TIDAK PERNAH keluar apa adanya lewat get_config(), digantikan penanda
    `_terisi` -- lihat snap_advance_db.py::get_config()."""
    private_pem, _ = _buat_keypair_rsa()
    snap_advance_db.update_config(client_secret="rahasia-banget", private_key=private_pem, webhook_secret="ws-123")

    cfg = snap_advance_db.get_config()

    assert cfg["snap_client_secret"] == ""
    assert cfg["snap_private_key"] == ""
    assert cfg["snap_webhook_secret"] == ""
    assert cfg["snap_client_secret_terisi"] is True
    assert cfg["snap_private_key_terisi"] is True
    assert cfg["snap_webhook_secret_terisi"] is True
    assert cfg["enabled"] is False  # merchant_id/client_id masih kosong di test ini


def test_update_config_string_kosong_field_rahasia_tidak_menghapus(single_tenant):
    """String kosong untuk field rahasia (dikirim frontend karena get_config()
    TIDAK PERNAH mem-prefill nilai asli) berarti "tidak diubah", BUKAN
    "kosongkan" -- BEDA dari field non-rahasia yang tetap boleh dikosongkan
    dengan sengaja."""
    private_pem, _ = _buat_keypair_rsa()
    snap_advance_db.update_config(client_secret="rahasia-awal", private_key=private_pem)

    snap_advance_db.update_config(client_secret="", private_key="", merchant_id="MID-BARU")

    cfg_internal = snap_advance_db.get_config_internal()
    assert cfg_internal["snap_client_secret"] == "rahasia-awal"  # TIDAK berubah
    assert cfg_internal["snap_private_key"] == private_pem.strip()  # TIDAK berubah
    assert cfg_internal["snap_merchant_id"] == "MID-BARU"  # field non-rahasia tetap ter-update


def test_get_config_internal_mengembalikan_nilai_asli(single_tenant):
    """get_config_internal() (dipakai snap_advance_client.py untuk benar-
    benar menandatangani/memanggil Faspay) TIDAK boleh ikut ter-mask."""
    private_pem, _ = _buat_keypair_rsa()
    snap_advance_db.update_config(client_secret="rahasia-banget", private_key=private_pem)

    cfg = snap_advance_db.get_config_internal()

    assert cfg["snap_client_secret"] == "rahasia-banget"
    assert cfg["snap_private_key"] == private_pem.strip()


# ---------------------------------------------------------------------------
# Migrasi Faspay SNAP Advance -- orkestrasi checkout booking/billing lewat
# payment_provider_client.py (seam dinamis). Skenario sukses/gagal dasar
# (VA/QRIS, rollback booking dibatalkan/invoice ditandai denied) sudah
# diuji lengkap di test_booking_gateway.py/test_billing_checkout.py --
# DI SINI khusus mengisi celah yang belum tercakup di sana: guard sebelum
# memanggil provider, rekonsiliasi manual SNAP, dan penggabungan Riwayat
# Transaksi Xpress+SNAP.
# ---------------------------------------------------------------------------

def _aktifkan_snap_orkestrasi(channel_aktif=None):
    private_pem, _ = _buat_keypair_rsa()
    snap_advance_db.update_config(
        merchant_id="37070", partner_id="37070", channel_id="77001", va_bank_aktif=["702"],
        private_key=private_pem, channel_aktif=channel_aktif if channel_aktif is not None else ["va", "qris"],
    )


def _tenant_default_snap():
    """"mugen-hair-co" (dibuat lewat bootstrap main.py, lihat pola SAMA
    persis test_booking_gateway.py) -- SUDAH punya fitur "booking_online"
    aktif secara default, beda dari tenant fixture single_tenant/two_tenants
    yang dibuat MINIMAL TANPA subscription/fitur apa pun. Endpoint publik
    checkout (POST /api/public/booking) menegakkan gate ini SEBELUM apa
    pun lain -- perlu tenant yang sungguhan siap pakai."""
    return tenant_db.get_tenant_by_slug("mugen-hair-co")


def test_orkestrasi_booking_qris_tanpa_whatsapp_ditolak_422_sebelum_panggil_provider(app_client, monkeypatch):
    """buat_transaksi_qris() SNAP mewajibkan nomor WhatsApp (melempar
    ValueError bare, bukan GatewayError) -- routers/booking.py WAJIB
    menolak SEBELUM memanggil provider sama sekali, bukan membiarkan error
    mentah lolos jadi 500."""
    import payment_provider_client
    tenant = _tenant_default_snap()
    _aktifkan_snap_orkestrasi()
    barber_id = db.add_barber("Barber QRIS Guard", tenant_id=tenant["id"])
    service_id = db.add_service("Service QRIS Guard", 100000, tenant_id=tenant["id"])
    booking_db.update_payment_settings(metode_aktif=["transfer", "qris", "gateway"], tenant_id=tenant["id"])
    dipanggil = {"n": 0}
    monkeypatch.setattr(payment_provider_client, "buat_transaksi", lambda *a, **kw: dipanggil.__setitem__("n", dipanggil["n"] + 1))

    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    body = {
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "10:00", "service_ids": [service_id],
        "customer_nama": "Budi", "customer_whatsapp": "", "metode_pembayaran": "gateway", "channel": "qris",
    }
    r = app_client.post("/api/public/booking", params={"tenant": "mugen-hair-co"}, json=body)
    assert r.status_code == 422, r.text
    assert dipanggil["n"] == 0  # provider TIDAK PERNAH dipanggil


def test_orkestrasi_booking_channel_tidak_aktif_ditolak_422(app_client):
    """Channel yang belum dicentang aktif Super Admin (mis. "qris" belum
    diaktifkan, hanya "va") TIDAK BOLEH bisa dipakai checkout walau
    formatnya valid."""
    tenant = _tenant_default_snap()
    _aktifkan_snap_orkestrasi(channel_aktif=["va"])  # qris SENGAJA tidak diaktifkan
    barber_id = db.add_barber("Barber Channel Guard", tenant_id=tenant["id"])
    service_id = db.add_service("Service Channel Guard", 100000, tenant_id=tenant["id"])
    booking_db.update_payment_settings(metode_aktif=["transfer", "qris", "gateway"], tenant_id=tenant["id"])

    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    body = {
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "10:00", "service_ids": [service_id],
        "customer_nama": "Budi", "customer_whatsapp": "081234567890", "metode_pembayaran": "gateway", "channel": "qris",
    }
    r = app_client.post("/api/public/booking", params={"tenant": "mugen-hair-co"}, json=body)
    assert r.status_code == 422, r.text


def test_rekonsiliasi_manual_booking_snap_va_menerapkan_status(single_tenant, monkeypatch):
    """snap_webhook.rekonsiliasi_manual() untuk channel "va" -- memanggil
    snap_advance_client.cek_status_transaksi(channel="va", virtual_account_no=...)
    lalu menerapkan status hasilnya lewat jalur SAMA PERSIS webhook resmi."""
    booking = _siapkan_booking(single_tenant["tenant_id"], metode="gateway")
    row = snap_payment_db.buat_transaksi(
        "BOOKING", single_tenant["tenant_id"], booking["total_harga"],
        booking_id=booking["id"], channel="va",
    )
    snap_payment_db.catat_hasil_create_transaction(row["id"], va_number="70212345678901", status="PENDING")

    monkeypatch.setattr(snap_advance_client, "cek_status_transaksi",
                         lambda ref, channel=None, **kw: {"additionalInfo": {"latestTransactionStatus": "00"}})

    hasil = snap_webhook.rekonsiliasi_manual(row["id"], tenant_id=single_tenant["tenant_id"])
    assert hasil["status"] == "PAID"
    booking_terbaru = booking_db.get_booking(booking["id"])
    assert booking_terbaru["status_pembayaran"] == "terverifikasi"


def test_rekonsiliasi_manual_channel_tidak_didukung_ditolak(single_tenant):
    """Direct Debit TIDAK PERNAH bisa dicek ulang manual (channel ini tidak
    pernah bisa dipakai checkout sama sekali sejak awal, lihat
    payment_provider_client.py) -- baris dibuat langsung lewat
    snap_payment_db (bukan lewat endpoint checkout, yang sudah menolaknya)
    murni untuk membuktikan guard di rekonsiliasi_manual() sendiri."""
    booking = _siapkan_booking(single_tenant["tenant_id"], metode="gateway")
    row = snap_payment_db.buat_transaksi(
        "BOOKING", single_tenant["tenant_id"], booking["total_harga"],
        booking_id=booking["id"], channel="direct_debit",
    )
    with pytest.raises(ValueError):
        snap_webhook.rekonsiliasi_manual(row["id"], tenant_id=single_tenant["tenant_id"])


def test_list_transaksi_gateway_menggabung_xpress_dan_snap(app_client, monkeypatch):
    """GET /api/booking/transactions (Riwayat Transaksi Tenant) SEKARANG
    menggabung baris Xpress v4 (booking_payment_transactions) DAN SNAP
    Advance (snap_payment_transactions, diterjemahkan bentuknya) dalam SATU
    daftar -- masing-masing ditandai field "provider" yang benar."""
    import auth_db
    import booking_gateway_db
    import payment_provider_client
    tenant = _tenant_default_snap()
    tenant_id = tenant["id"]
    auth_db.tambah_user("ownermerge", "password123", role="admin", tenant_id=tenant_id)
    r_login = app_client.post("/api/auth/login", json={"username": "ownermerge", "password": "password123"})
    assert r_login.status_code == 200, r_login.text
    headers = {"Authorization": f"Bearer {r_login.json()['token']}"}

    # Baris Xpress v4 (lawas) -- dibuat langsung lewat booking_gateway_db,
    # TIDAK lewat checkout (tidak relevan, hanya perlu ADA barisnya).
    booking_xpress = _siapkan_booking(tenant_id, metode="gateway")
    order_id = booking_gateway_db.buat_order_id(tenant_id, booking_xpress["id"])
    booking_gateway_db.buat_transaksi(
        order_id, tenant_id, tenant["nama_barbershop"], booking_xpress["id"], booking_xpress["customer_nama"],
        booking_xpress["nama_barber"], booking_xpress["daftar_service"], booking_xpress["total_harga"],
        checkout_token=None, checkout_redirect_url="https://example.test/pay",
    )

    # Baris SNAP -- lewat checkout sungguhan (endpoint publik).
    _aktifkan_snap_orkestrasi()
    barber_id = db.add_barber("Barber Merge", tenant_id=tenant_id)
    service_id = db.add_service("Service Merge", 100000, tenant_id=tenant_id)
    booking_db.update_payment_settings(metode_aktif=["transfer", "qris", "gateway"], tenant_id=tenant_id)
    monkeypatch.setattr(payment_provider_client, "buat_transaksi",
                         lambda *a, **kw: {"va_number": "70212345678901"})
    tanggal = (_hari_ini_wib() + timedelta(days=1)).isoformat()
    body = {
        "barber_id": barber_id, "tanggal": tanggal, "jam_mulai": "11:00", "service_ids": [service_id],
        "customer_nama": "Citra", "customer_whatsapp": "081234567891", "metode_pembayaran": "gateway",
        "channel": "va", "bank_code": "702",
    }
    r_checkout = app_client.post("/api/public/booking", params={"tenant": "mugen-hair-co"}, json=body)
    assert r_checkout.status_code == 200, r_checkout.text

    r = app_client.get("/api/booking/transactions", headers=headers)
    assert r.status_code == 200, r.text
    hasil = r.json()
    providers = {row["provider"] for row in hasil}
    assert providers == {"xpress", "snap_advance"}
    baris_snap = next(row for row in hasil if row["provider"] == "snap_advance")
    assert baris_snap["channel_pembayaran"] == "va"
    # Status baru sukses dibuat -> "PENDING" (bukan "CREATED", orkestrasi
    # checkout langsung menandainya begitu VA/QR berhasil diterbitkan) ->
    # diterjemahkan "diproses" di kosakata gateway lawas.
    assert baris_snap["status_pembayaran"] == "diproses"
    assert baris_snap["nomor_transaksi"] == r_checkout.json()["nomor_transaksi"]
