"""booking_gateway_webhook.py — Implementasi Payment Gateway & Riwayat
Transaksi Multi-Tenant: Update Otomatis dari Webhook Payment Gateway Booking
=============================================================================
Logika MURNI (tanpa FastAPI/Request), pola SAMA PERSIS dengan
billing_webhook.py (langganan SaaS) -- TAPI TERPISAH TOTAL, TIDAK
mengimpor/memanggil billing_webhook.py sama sekali (dua jenis transaksi,
dua modul webhook independen, sesuai arsitektur yang diminta). File ini
SATU-SATUNYA tempat status pembayaran booking boleh berubah jadi
"berhasil" -- TIDAK PERNAH dari aksi frontend/tombol/klaim customer.

KEAMANAN (SAMA PERSIS aturan billing_webhook.py -- "jangan pernah percaya
data dari client begitu saja") -- SEMUA TIGA harus lolos sebelum satu baris
pun diubah:
1. Signature Key (payment_gateway_client.verifikasi_signature()).
2. order_id HARUS transaksi yang benar-benar dibuat lewat checkout booking
   (bukan dikarang begitu saja).
3. gross_amount HARUS SAMA PERSIS dengan `nominal` yang tercatat di
   transaksi saat checkout dibuat -- BUKAN dipercaya dari payload notifikasi.

IDEMPOTEN: provider SECARA RESMI bisa mengirim notifikasi yang sama lebih
dari sekali (retry) -- booking_gateway_db.update_status() sudah menjaga ini
(tidak ada perubahan/log kalau status sama).

CASCADE ke tabel `bookings` (SESUAI alur bisnis, TIDAK mengubah kolom
bookings selain status_pembayaran/status_booking yang SUDAH ADA):
- "berhasil" -> bookings.status_pembayaran = 'terverifikasi' (booking_db.
  verifikasi_pembayaran(), SAMA fungsi yang dipakai staff untuk verifikasi
  manual transfer/QRIS).
- "gagal"/"kedaluwarsa"/"dibatalkan" -> bookings.status_booking =
  'dibatalkan' (booking_db.batalkan_booking(), MEMBEBASKAN slot yang
  sebelumnya terisi booking belum-terbayar ini).
- "diproses"/"menunggu_pembayaran"/"refund" -> TIDAK ada cascade ke
  `bookings` (booking tetap seperti apa adanya, hanya baris transaksi yang
  berubah -- refund adalah peristiwa PASCA booking selesai, tidak pernah
  membatalkan/mengaktifkan ulang booking secara otomatis)."""

import json
from datetime import datetime

import booking_db
import booking_gateway_db
import payment_gateway_client

_TRANSACTION_STATUS_VALID = {"capture", "settlement", "pending", "deny", "cancel", "expire", "refund", "partial_refund"}


def _map_status(transaction_status: str, fraud_status: str = None) -> str:
    if transaction_status not in _TRANSACTION_STATUS_VALID:
        raise ValueError(f"transaction_status tidak dikenal: {transaction_status}")
    if transaction_status == "capture":
        if fraud_status == "accept":
            return "berhasil"
        if fraud_status == "challenge":
            return "diproses"
        return "gagal"
    return {
        "settlement": "berhasil",
        "pending": "menunggu_pembayaran",
        "deny": "gagal",
        "cancel": "dibatalkan",
        "expire": "kedaluwarsa",
        "refund": "refund",
        "partial_refund": "refund",
    }[transaction_status]


def proses_notifikasi(payload: dict) -> dict:
    """Return transaksi TERBARU setelah diproses. Melempar ValueError untuk
    SEMUA kegagalan validasi (signature/order_id/amount/status tidak
    dikenal) -- routers/booking_gateway_webhook.py menerjemahkannya jadi
    HTTP 400, TANPA efek samping (transaksi/booking) tersisa kalau validasi
    manapun gagal."""
    order_id = str(payload.get("order_id") or "")
    status_code = str(payload.get("status_code") or "")
    gross_amount = str(payload.get("gross_amount") or "")
    signature_key = str(payload.get("signature_key") or "")
    transaction_status = str(payload.get("transaction_status") or "")
    fraud_status = payload.get("fraud_status")
    payment_type = payload.get("payment_type")

    if not payment_gateway_client.verifikasi_signature(order_id, status_code, gross_amount, signature_key):
        raise ValueError("Signature tidak valid.")

    transaksi = booking_gateway_db.get_transaksi_by_order_id(order_id)
    if transaksi is None:
        raise ValueError(f"order_id tidak dikenal: {order_id}")

    try:
        gross_amount_angka = int(float(gross_amount))
    except (TypeError, ValueError):
        raise ValueError("gross_amount tidak valid.")
    if gross_amount_angka != int(transaksi["nominal"]):
        raise ValueError(
            f"gross_amount tidak cocok dengan transaksi (payload={gross_amount_angka}, "
            f"transaksi={transaksi['nominal']})."
        )

    status_baru = _map_status(transaction_status, fraud_status)

    if transaksi["status_pembayaran"] == status_baru:
        # Notifikasi duplikat (retry provider) -- tidak ada apa pun yang
        # perlu diubah lagi, TERMASUK tidak mengulang cascade ke `bookings`
        # (booking_db.verifikasi_pembayaran()/batalkan_booking() sudah
        # idempoten sendiri, tapi lebih murah/jelas dihentikan di sini).
        return transaksi

    extra = {
        "channel_pembayaran": payment_type,
        "raw_notification": json.dumps(payload),
    }
    transaction_id_provider = payload.get("transaction_id")
    if transaction_id_provider:
        extra["transaction_id_provider"] = str(transaction_id_provider)
    reference_id_provider = payload.get("reference_id") or payload.get("biller_reference") or payload.get("approval_code")
    if reference_id_provider:
        extra["reference_id_provider"] = str(reference_id_provider)
    if status_baru == "berhasil":
        extra["paid_at"] = datetime.now().isoformat(timespec="seconds")

    booking_gateway_db.update_status(transaksi["id"], status_baru, sumber="webhook", **extra)

    if status_baru == "berhasil":
        try:
            booking_db.verifikasi_pembayaran(transaksi["booking_id"])
        except ValueError:
            pass  # booking sudah dibatalkan duluan (mis. kedaluwarsa manual) -- transaksi tetap tercatat "berhasil" apa adanya, tidak menimpa keputusan pembatalan
    elif status_baru in ("gagal", "kedaluwarsa", "dibatalkan"):
        try:
            booking_db.batalkan_booking(transaksi["booking_id"])
        except ValueError:
            pass  # booking sudah tidak ada -- abaikan, transaksi tetap tercatat

    return booking_gateway_db.get_transaksi(transaksi["id"])
