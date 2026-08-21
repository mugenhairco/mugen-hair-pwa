"""snap_webhook.py — Webhook Faspay SNAP Advance: TIGA endpoint per produk
(VA/QRIS/Direct Debit), DUA domain (Booking Payment Tenant + SaaS Billing)
=============================================================================
KOREKSI (audit lanjutan #3, klarifikasi resmi Faspay): instruksi migrasi #3
awalnya diartikan "satu URL notifikasi gabungan untuk semua produk" --
TERNYATA KELIRU. Faspay mengonfirmasi tertulis: mereka mengatur SATU
domain/url_merchant per Merchant ID, TAPI tiap PRODUK SNAP (VA/QRIS/Direct
Debit) punya PATH notification sendiri di bawah domain itu (lihat
routers/snap_advance.py untuk ketiga path resmi & alasan lengkapnya). "Satu
webhook Faspay per Merchant ID" tetap benar levelnya -- SATU Merchant ID
TETAP hanya berurusan dengan SATU domain/url_merchant, cuma path di bawahnya
BUKAN satu, melainkan tiga (satu per produk). Modul INI (business logic:
verifikasi signature, parsing payload, state machine, cascade) TIDAK
berubah sama sekali akibat koreksi ini -- HANYA jenis notifikasi yang
tadinya ditebak dari isi payload (workaround endpoint gabungan) sekarang
EKSPLISIT dari parameter `jenis` yang dioper pemanggil (routers/snap_advance.py,
tahu persis endpoint mana yang dipukul). Flow:

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
import snap_advance_db
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


# Pemetaan `latestTransactionStatus` (dokumen resmi VA & Direct Debit yang
# diberikan Owner, KEDUANYA memakai daftar kode yang sama) -> vocabulary
# status internal snap_payment_db.py. "04" (Refunded) SENGAJA TIDAK
# dipetakan -- snap_payment_db.STATUS_VALID tidak punya representasi refund
# (keputusan arsitektur sebelumnya: scope migrasi tidak menyebutkan refund
# sama sekali, TIDAK ditambahkan supaya tidak mengarang state yang tidak
# diminta) -- notifikasi berkode "04" akan DITOLAK dengan pesan jelas (lihat
# _map_latest_transaction_status()) supaya kelihatan perlu penanganan
# manual, BUKAN diam-diam disalahartikan jadi status lain yang keliru.
_STATUS_CODE_KE_INTERNAL = {
    "00": snap_payment_db.STATUS_PAID,       # Success
    "01": snap_payment_db.STATUS_PENDING,    # Initiated
    "02": snap_payment_db.STATUS_PENDING,    # Paying
    "03": snap_payment_db.STATUS_PENDING,    # Pending
    "05": snap_payment_db.STATUS_CANCELLED,  # Canceled
    "06": snap_payment_db.STATUS_FAILED,     # Failed
    "07": snap_payment_db.STATUS_EXPIRED,    # Not Found / Expired (dokumen Faspay memakai kode "07" dobel untuk 2 arti -- perlu klarifikasi Faspay, "Expired" dipakai di sini karena lebih actionable utk notifikasi push)
}


def _map_latest_transaction_status(status_code: str) -> str:
    if status_code not in _STATUS_CODE_KE_INTERNAL:
        raise ValueError(
            f"latestTransactionStatus SNAP Advance tidak didukung: {status_code!r}. "
            f"Kalau ini kode \"04\" (Refunded), sistem ini belum punya representasi status refund -- "
            f"perlu penanganan manual, lihat catatan snap_payment_db.STATUS_VALID."
        )
    return _STATUS_CODE_KE_INTERNAL[status_code]


JENIS_VALID = {"va", "qris", "direct_debit"}


def _ekstrak_notifikasi(payload: dict, jenis: str) -> tuple:
    """Payload VA Dynamic vs Direct Debit/QRIS BEDA BENTUK (dikonfirmasi
    dari dokumen resmi Faspay yang diberikan Owner):
    - VA Dynamic: transaksi diidentifikasi lewat `trxId` (BUKAN
      partnerReferenceNo), `latestTransactionStatus` bersarang di
      `additionalInfo`.
    - Direct Debit & QRIS: KEBETULAN SAMA PERSIS bentuk payload notifikasinya
      -- transaksi diidentifikasi lewat `originalPartnerReferenceNo`,
      `latestTransactionStatus` field TOP-LEVEL (BUKAN di dalam
      `additionalInfo` seperti VA -- beda dari VA, gampang salah kalau
      disamakan).
    `jenis` EKSPLISIT dari pemanggil (routers/snap_advance.py tahu persis
    endpoint mana yang dipukul, lihat catatan modul) -- TIDAK LAGI ditebak
    dari isi payload seperti sebelum path notification per-produk
    dikonfirmasi Faspay.
    Return (payment_reference, provider_transaction_id, status_code, paid_at)."""
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis notifikasi SNAP Advance tidak dikenal: {jenis!r}.")
    info = payload.get("additionalInfo") or {}
    if jenis == "va":
        return (payload.get("trxId"), payload.get("paymentRequestId"),
                info.get("latestTransactionStatus"), info.get("paymentDate"))
    return (payload.get("originalPartnerReferenceNo"), payload.get("originalReferenceNo"),
            payload.get("latestTransactionStatus"), info.get("paymentDate"))


def balas_notifikasi(jenis: str, payload: dict) -> dict:
    """Body acknowledgment SESUAI dokumen resmi Faspay per jenis notifikasi
    -- WAJIB dipakai sebagai respons HTTP endpoint webhook (routers/
    snap_advance.py) SETELAH proses_notifikasi() sukses, BUKAN echo
    transaksi internal kita (bentuknya tidak dijamin cocok ekspektasi
    Faspay, berisiko Faspay mengira gagal & retry terus-menerus). `jenis`
    EKSPLISIT dari pemanggil (lihat _ekstrak_notifikasi())."""
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis notifikasi SNAP Advance tidak dikenal: {jenis!r}.")
    if jenis == "va":
        return {
            "responseCode": "2002500", "responseMessage": "Successful",
            "virtualAccountData": {
                "partnerServiceId": payload.get("partnerServiceId"),
                "customerNo": payload.get("customerNo"),
                "virtualAccountNo": payload.get("virtualAccountNo"),
                "paymentRequestId": payload.get("paymentRequestId"),
                "paidAmount": payload.get("paidAmount"),
            },
        }
    if jenis == "qris":
        return {"responseCode": "2005200", "responseMessage": "Request has been processed successfully"}
    return {"responseCode": "2005600", "responseMessage": "Request has been processed successfully"}


def proses_notifikasi(raw_body: str, signature_header: str, timestamp_header: str, jenis: str, path: str) -> dict:
    """Envelope luar webhook -- memverifikasi signature (mencakup `path`
    endpoint resmi yang dipukul, WAJIB untuk formula stringToSign SNAP,
    lihat gateway_client_base.py::sign_sha256_rsa()), mem-parsing payload
    VA/Direct Debit/QRIS SESUAI `jenis` (lihat _ekstrak_notifikasi()), lalu
    memanggil terapkan_status_transaksi() (CORE, sudah diuji penuh sejak
    awal). `jenis`/`path` dioper EKSPLISIT oleh routers/snap_advance.py
    (satu endpoint per produk, lihat catatan modul) -- E-Wallet di luar
    QRIS BELUM punya endpoint/handler sama sekali (skema payloadnya PENDING
    FASPAY)."""
    # BUGFIX-guard SENGAJA di posisi ini (SEBELUM parsing payload apa pun):
    # signature WAJIB divalidasi dulu sebelum satu field pun dari body
    # dipercaya -- pola SAMA PERSIS booking_gateway_webhook.py::
    # proses_notifikasi() (verifikasi_signature() dipanggil SEBELUM
    # get_transaksi_by_order_id()). verifikasi_signature_webhook() return
    # False (BUKAN exception) baik untuk "belum dikonfigurasi" MAUPUN
    # "signature tidak valid" -- KEDUANYA ditolak sama (pola sama persis
    # gateway_client_base.py::verify_sha512() dkk).
    if not snap_advance_client.verifikasi_signature_webhook(raw_body, signature_header, timestamp_header, path=path):
        raise ValueError("Signature Payment Notification SNAP Advance tidak valid atau belum dikonfigurasi.")
    payload = json.loads(raw_body)
    payment_reference, provider_transaction_id, status_code, paid_at = _ekstrak_notifikasi(payload, jenis)
    if not payment_reference:
        raise ValueError("Payload notifikasi SNAP Advance tidak berisi referensi transaksi.")
    transaksi = snap_payment_db.get_transaksi_by_reference(payment_reference)
    if transaksi is None:
        raise ValueError(f"payment_reference tidak dikenal: {payment_reference}")
    snap_payment_db.catat_webhook_diterima(transaksi["id"], raw_body, berhasil=True)
    status_baru = _map_latest_transaction_status(status_code)
    return terapkan_status_transaksi(transaksi, status_baru, sumber="webhook",
                                      provider_transaction_id=provider_transaction_id, paid_at=paid_at)
