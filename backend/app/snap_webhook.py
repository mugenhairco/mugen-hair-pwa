"""snap_webhook.py — Webhook Faspay SNAP Advance: SATU endpoint untuk DUA
domain (Booking Payment Tenant + SaaS Billing)
=============================================================================
SESUAI instruksi migrasi #3: "Implementasikan SATU webhook endpoint untuk
Merchant ID Faspay... Jangan membuat dua webhook Faspay yang berbeda untuk
Merchant ID yang sama." Flow:

    Faspay Webhook
    -> Payment Transaction (snap_payment_db.get_transaksi_by_reference())
    -> Determine Transaction Type (snap_payment_db.tentukan_tipe_transaksi())
    -> idempotency check + update status (snap_payment_db.update_status())
    -> cascade ke domain masing-masing:
       - BOOKING -> booking_db.verifikasi_pembayaran()/batalkan_booking()
         (FUNGSI YANG SAMA dipakai staff manual & webhook Xpress lama --
         TIDAK ditulis ulang, lihat booking_gateway_webhook.py untuk pola
         yang ditiru PERSIS di sini).
       - SAAS_BILLING -> billing_webhook._terapkan_status_invoice() (FUNGSI
         YANG SAMA dipakai webhook Xpress lama untuk billing -- TIDAK
         ditulis ulang, TERMASUK lock per-tenant billing_webhook._kunci_tenant()
         yang sudah menangani race condition penyambungan periode
         langganan, lihat catatan lengkap di modul itu).

DUA FUNGSI TERPISAH SENGAJA (pola sama seperti booking_gateway_webhook.py::
_terapkan_status() vs proses_notifikasi()):
1. `terapkan_status_transaksi()` -- CORE, NYATA, DIUJI PENUH. Menerima
   payment_reference + status_baru yang SUDAH divalidasi/dipetakan --
   TIDAK menyentuh HTTP/signature/parsing payload mentah Faspay sama
   sekali, jadi bisa diuji end-to-end SEKARANG tanpa menunggu Faspay
   (idempotency, dispatch tipe, cross-domain isolation -- SEMUA nyata).
2. `proses_notifikasi()` -- ENVELOPE luar yang menerima payload mentah
   Faspay, PENDING FASPAY (memanggil snap_advance_client.verifikasi_signature_webhook()
   yang masih stub) -- begitu Faspay mengonfirmasi skema webhook, HANYA
   fungsi ini yang perlu diisi sungguhan (parsing field mentah -> panggil
   terapkan_status_transaksi()), CORE di atas TIDAK PERNAH perlu disentuh."""

import json

import billing_invoice_db
import billing_webhook
import booking_db
import snap_advance_client
import snap_payment_db

# Pemetaan vocabulary SNAP Advance (CREATED/PENDING/PAID/FAILED/EXPIRED/
# CANCELLED, lihat snap_payment_db.py) -> vocabulary billing_webhook.py yang
# SUDAH ADA (paid/pending/denied/cancelled/expired) -- MURNI pemetaan string
# internal proyek ini sendiri (BUKAN sesuatu yang perlu dikonfirmasi Faspay),
# supaya cascade SAAS_BILLING bisa memanggil billing_webhook._terapkan_status_invoice()
# TANPA mengubah vocabulary status invoice yang sudah proven & dipakai luas.
_STATUS_KE_VOCAB_BILLING = {
    snap_payment_db.STATUS_PAID: billing_webhook.STATUS_PAID,
    snap_payment_db.STATUS_PENDING: billing_webhook.STATUS_PENDING,
    snap_payment_db.STATUS_FAILED: billing_webhook.STATUS_DENIED,
    snap_payment_db.STATUS_EXPIRED: billing_webhook.STATUS_EXPIRED,
    snap_payment_db.STATUS_CANCELLED: billing_webhook.STATUS_CANCELLED,
}


def terapkan_status_transaksi(transaksi: dict, status_baru: str, sumber: str,
                               provider_transaction_id: str = None, paid_at: str = None) -> dict:
    """Titik SATU-SATUNYA yang benar-benar menulis perubahan status transaksi
    SNAP + cascade ke domain masing-masing -- dipanggil proses_notifikasi()
    (webhook resmi, PENDING) DAN akan dipanggil rekonsiliasi manual (kalau/
    begitu cek_status_transaksi() sudah nyata), supaya KEDUA jalur PERSIS
    sama aturannya (guard status final/idempotency/cascade), TIDAK ada jalur
    pintas kedua yang berperilaku beda -- pola SAMA PERSIS
    booking_gateway_webhook.py::_terapkan_status()."""
    transaksi_setelah = snap_payment_db.update_status(
        transaksi["id"], status_baru, sumber=sumber,
        provider_transaction_id=provider_transaction_id, paid_at=paid_at,
    )
    if transaksi_setelah["status"] != status_baru:
        # Idempoten (status sudah sama) ATAU ditolak guard status final --
        # KEDUANYA berarti tidak ada apa pun yang berubah, cascade TIDAK
        # boleh dieksekusi (SESUAI instruksi migrasi #6: "Booking tetap
        # hanya sekali dianggap PAID").
        return transaksi_setelah

    if transaksi["transaction_type"] == snap_payment_db.TRANSACTION_TYPE_BOOKING:
        _cascade_booking(transaksi["booking_id"], status_baru)
    elif transaksi["transaction_type"] == snap_payment_db.TRANSACTION_TYPE_SAAS_BILLING:
        _cascade_saas_billing(transaksi["subscription_invoice_id"], status_baru, sumber)

    return snap_payment_db.get_transaksi(transaksi["id"])


def _cascade_booking(booking_id: int, status_baru: str):
    """Domain BOOKING -- reuse TOTAL booking_db.py, TIDAK ada logika bisnis
    booking baru ditulis di sini (SESUAI instruksi migrasi #7: "Jangan
    mengubah aturan bisnis booking yang tidak berkaitan dengan payment
    gateway"). `oleh=None` -- tidak ada admin manusia di jalur webhook,
    SAMA seperti cascade Xpress lama (booking_gateway_webhook.py)."""
    if status_baru == snap_payment_db.STATUS_PAID:
        try:
            booking_db.verifikasi_pembayaran(booking_id, oleh=None)
        except ValueError:
            pass  # booking sudah dibatalkan duluan -- transaksi SNAP tetap tercatat PAID apa adanya
    elif status_baru in (snap_payment_db.STATUS_FAILED, snap_payment_db.STATUS_EXPIRED, snap_payment_db.STATUS_CANCELLED):
        try:
            booking_db.batalkan_booking(booking_id)
        except ValueError:
            pass  # booking sudah tidak ada/sudah dibatalkan -- abaikan, transaksi tetap tercatat


def _cascade_saas_billing(subscription_invoice_id: int, status_baru: str, sumber: str):
    """Domain SAAS_BILLING -- reuse TOTAL billing_webhook._terapkan_status_invoice()
    (TERMASUK lock per-tenant billing_webhook._kunci_tenant(), lihat
    catatan lengkap race condition penyambungan periode di modul itu) --
    TIDAK ada logika bisnis billing baru ditulis di sini (SESUAI instruksi
    migrasi #8: "Pastikan payment booking dan payment SaaS tidak tercampur")."""
    invoice = billing_invoice_db.get_invoice(subscription_invoice_id)
    if invoice is None:
        return  # invoice sudah dihapus/tidak ada -- transaksi SNAP tetap tercatat apa adanya
    status_billing = _STATUS_KE_VOCAB_BILLING[status_baru]
    with billing_webhook._kunci_tenant(invoice["tenant_id"]):
        billing_webhook._terapkan_status_invoice(invoice, status_billing, sumber=sumber)


def proses_notifikasi(raw_body: str, signature_header: str, timestamp_header: str = None) -> dict:
    """Envelope luar webhook -- PENDING FASPAY (lihat docstring modul &
    snap_advance_client.verifikasi_signature_webhook()). Melempar
    SnapAdvancePendingError sampai skema payload/signature Faspay
    terkonfirmasi -- routers/snap_advance.py menerjemahkannya jadi HTTP 503
    (BUKAN 400/500 -- ini bukan kegagalan validasi ataupun bug, murni
    "belum siap", supaya Faspay/monitoring bisa membedakan)."""
    # BUGFIX-guard SENGAJA di posisi ini (SEBELUM parsing payload apa pun):
    # signature WAJIB divalidasi dulu sebelum satu field pun dari body
    # dipercaya -- pola SAMA PERSIS booking_gateway_webhook.py::
    # proses_notifikasi() (verifikasi_signature() dipanggil SEBELUM
    # get_transaksi_by_order_id()).
    snap_advance_client.verifikasi_signature_webhook(raw_body, signature_header, timestamp_header)
    # Baris di bawah TIDAK PERNAH tercapai hari ini (baris di atas SELALU
    # melempar PENDING FASPAY) -- disiapkan sebagai KERANGKA supaya begitu
    # Faspay mengonfirmasi skema payload, hanya bagian PARSING (ekstrak
    # payment_reference/status/dst dari `payload`) yang perlu diisi --
    # panggilan ke terapkan_status_transaksi() di bawah TIDAK berubah.
    payload = json.loads(raw_body)  # pragma: no cover -- lihat catatan di atas
    payment_reference = payload.get("partnerReferenceNo") or payload.get("originalPartnerReferenceNo")
    transaksi = snap_payment_db.get_transaksi_by_reference(payment_reference)
    if transaksi is None:
        raise ValueError(f"payment_reference tidak dikenal: {payment_reference}")
    snap_payment_db.catat_webhook_diterima(transaksi["id"], raw_body, berhasil=True)
    # PENDING FASPAY: pemetaan status code SNAP Advance -> vocabulary
    # internal (CREATED/PENDING/PAID/FAILED/EXPIRED/CANCELLED) belum bisa
    # ditulis -- field & nilai kode status SNAP Faspay belum terkonfirmasi.
    raise snap_advance_client.pending_faspay(
        "Parsing payload webhook -- proses_notifikasi()",
        "Field status code & nilai resminya di payload Payment Notification SNAP Faspay belum terkonfirmasi.",
    )
