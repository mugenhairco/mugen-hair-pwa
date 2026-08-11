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
  membatalkan/mengaktifkan ulang booking secara otomatis).

PROVIDER RESMI: Faspay Xpress v4 -- payload notifikasi memakai field
`bill_no`/`payment_status_code`/`bill_total`/`signature` (BUKAN
`order_id`/`transaction_status`/`gross_amount`/`signature_key` ala
Midtrans), lihat payment_gateway_client.py untuk pemetaan lengkap."""

import json
from datetime import datetime

import booking_db
import booking_gateway_db
import payment_gateway_client

# 9 kode status resmi Faspay (dokumentasi Payment Notification): 0
# Unprocessed, 1 In Process, 2 Payment Success, 3 Payment Failed, 4 Payment
# Reversal, 5 No bills found, 7 Payment Expired, 8 Payment Cancelled, 9
# Unknown. Kode 5 & 9 SENGAJA TIDAK dipetakan (ditolak sebagai "tidak
# dikenal") -- keduanya menandakan sesuatu yang janggal di sisi Faspay
# sendiri, bukan status pembayaran yang sah untuk diterapkan.
_STATUS_CODE_KE_UNIFIED = {
    "0": "menunggu_pembayaran",
    "1": "diproses",
    "2": "berhasil",
    "3": "gagal",
    "4": "refund",
    "7": "kedaluwarsa",
    "8": "dibatalkan",
}


def _map_status(payment_status_code: str) -> str:
    if payment_status_code not in _STATUS_CODE_KE_UNIFIED:
        raise ValueError(f"payment_status_code tidak dikenal: {payment_status_code}")
    return _STATUS_CODE_KE_UNIFIED[payment_status_code]


def _terapkan_status(transaksi: dict, status_baru: str, sumber: str, payment_type: str = None,
                      transaction_id_provider=None, reference_id_provider=None, raw_notification: str = None) -> dict:
    """Titik SATU-SATUNYA yang benar-benar menulis perubahan status transaksi
    booking + cascade ke `bookings` -- dipanggil proses_notifikasi() (webhook
    resmi) DAN rekonsiliasi_manual() (staff cek ulang manual ke provider
    lewat Core API, untuk transaksi yang macet karena webhook TIDAK PERNAH
    sampai sama sekali), supaya KEDUA jalur PERSIS sama aturannya (guard
    urutan status, cascade, idempotensi) -- tidak ada jalur pintas kedua yang
    berperilaku beda.

    AUDIT (perbaikan pasca-audit kesiapan): booking_gateway_db.update_status()
    bisa MENOLAK transisi (transaksi sudah final, notifikasi ini basi/keluar
    urutan -- lihat docstring-nya) -- kalau ditolak, status_pembayaran hasil
    TIDAK SAMA dengan status_baru yang diminta, dan cascade ke `bookings`
    WAJIB TIDAK dieksekusi sama sekali (sebelumnya cascade selalu jalan
    berdasarkan status_baru yang DIMINTA, bukan status yang BENAR-BENAR
    tersimpan -- celah yang memungkinkan notifikasi basi tetap membatalkan
    booking yang sudah terverifikasi/dibayar)."""
    transaksi_setelah = booking_gateway_db.update_status(
        transaksi["id"], status_baru, sumber=sumber,
        channel_pembayaran=payment_type, transaction_id_provider=transaction_id_provider,
        reference_id_provider=reference_id_provider, raw_notification=raw_notification,
        paid_at=datetime.now().isoformat(timespec="seconds") if status_baru == "berhasil" else None,
    )

    if transaksi_setelah["status_pembayaran"] != status_baru:
        # Idempoten (status sudah sama) ATAU ditolak guard urutan status --
        # KEDUANYA berarti tidak ada apa pun yang berubah, cascade TIDAK
        # boleh dieksekusi (booking_db.verifikasi_pembayaran()/batalkan_booking()
        # sudah idempoten sendiri, tapi lebih murah/jelas dihentikan di sini).
        return transaksi_setelah

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


def proses_notifikasi(payload: dict) -> dict:
    """Return transaksi TERBARU setelah diproses. Melempar ValueError untuk
    SEMUA kegagalan validasi (signature/bill_no/bill_total/status tidak
    dikenal) -- routers/gateway_notification.py & routers/booking_gateway_webhook.py
    menerjemahkannya jadi HTTP 400, TANPA efek samping (transaksi/booking)
    tersisa kalau validasi manapun gagal.

    Payload SESUAI format resmi Faspay Xpress v4 Payment Notification --
    lihat payment_gateway_client.py::verifikasi_signature() untuk formula
    signature (BEDA dari formula checkout)."""
    bill_no = str(payload.get("bill_no") or "")
    payment_status_code = str(payload.get("payment_status_code") or "")
    bill_total = str(payload.get("bill_total") or "")
    signature_key = str(payload.get("signature") or "")
    payment_channel = payload.get("payment_channel")
    trx_id = payload.get("trx_id")
    payment_reff = payload.get("payment_reff")

    if not payment_gateway_client.verifikasi_signature(bill_no, payment_status_code, signature_key):
        raise ValueError("Signature tidak valid.")

    transaksi = booking_gateway_db.get_transaksi_by_order_id(bill_no)
    if transaksi is None:
        raise ValueError(f"order_id tidak dikenal: {bill_no}")

    try:
        bill_total_angka = int(float(bill_total))
    except (TypeError, ValueError):
        raise ValueError("bill_total tidak valid.")
    if bill_total_angka != int(transaksi["nominal"]):
        raise ValueError(
            f"bill_total tidak cocok dengan transaksi (payload={bill_total_angka}, "
            f"transaksi={transaksi['nominal']})."
        )

    status_baru = _map_status(payment_status_code)

    return _terapkan_status(
        transaksi, status_baru, sumber="webhook", payment_type=payment_channel,
        transaction_id_provider=str(trx_id) if trx_id else None,
        reference_id_provider=str(payment_reff) if payment_reff and payment_reff != "null" else None,
        raw_notification=json.dumps(payload),
    )


def rekonsiliasi_manual(transaksi_id: int, tenant_id: int) -> dict:
    """AUDIT (perbaikan pasca-audit kesiapan): jalur RESMI satu-satunya untuk
    memperbaiki transaksi yang macet karena webhook TIDAK PERNAH sampai sama
    sekali (beda dari retry/notifikasi basi yang sudah ditangani
    proses_notifikasi()+_terapkan_status() di atas) -- dipakai Owner/staff
    lewat tombol "Cek Ulang ke Provider" di Riwayat Transaksi Tenant.
    `tenant_id` WAJIB dari sesi login -- transaksi tenant lain TIDAK PERNAH
    bisa direkonsiliasi lewat sini (lihat booking_gateway_db.get_transaksi()).

    TIDAK memerlukan verifikasi signature -- panggilan ini KELUAR ke provider
    memakai Server Key milik server sendiri (payment_gateway_client.
    cek_status_transaksi(), Core API GET), BUKAN data masuk dari luar yang
    perlu divalidasi asalnya -- tapi tetap memvalidasi gross_amount dari
    respons provider (defense-in-depth) dan tetap lewat _terapkan_status()
    yang SAMA PERSIS dipakai webhook resmi, supaya tidak ada jalur pintas
    kedua yang berperilaku beda (guard urutan status/cascade/log tetap
    seragam)."""
    transaksi = booking_gateway_db.get_transaksi(transaksi_id, tenant_id=tenant_id)
    if transaksi is None:
        raise ValueError("Transaksi tidak ditemukan.")

    hasil_provider = payment_gateway_client.cek_status_transaksi(transaksi["order_id"])
    payment_status_code = str(hasil_provider.get("payment_status_code") or "")
    bill_total = str(hasil_provider.get("bill_total") or "")

    try:
        bill_total_angka = int(float(bill_total))
    except (TypeError, ValueError):
        bill_total_angka = None
    if bill_total_angka is not None and bill_total_angka != int(transaksi["nominal"]):
        raise ValueError(
            f"bill_total dari provider tidak cocok dengan transaksi (provider={bill_total_angka}, "
            f"transaksi={transaksi['nominal']})."
        )

    status_baru = _map_status(payment_status_code)
    trx_id = hasil_provider.get("trx_id")
    payment_reff = hasil_provider.get("payment_reff")

    return _terapkan_status(
        transaksi, status_baru, sumber="rekonsiliasi_manual", payment_type=hasil_provider.get("payment_channel"),
        transaction_id_provider=str(trx_id) if trx_id else None,
        reference_id_provider=str(payment_reff) if payment_reff and payment_reff != "null" else None,
        raw_notification=json.dumps(hasil_provider),
    )
