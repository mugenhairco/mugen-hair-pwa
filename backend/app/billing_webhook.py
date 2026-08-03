"""billing_webhook.py — FONDASI Multi-Tenant Phase 4: Aktivasi Otomatis dari Webhook Midtrans
=============================================================================
Logika MURNI (tanpa FastAPI/Request) supaya bisa diuji langsung dengan
payload buatan sendiri, tanpa HTTP -- routers/billing_webhook.py (endpoint
publik `POST /api/public/billing/midtrans-webhook`) hanya membaca body JSON
lalu memanggil proses_notifikasi() di sini, menerjemahkan ValueError jadi
HTTP 400.

KEAMANAN (SESUAI aturan eksplisit Phase 4 "jangan pernah percaya data dari
client begitu saja") -- SEMUA TIGA harus lolos sebelum satu baris pun
diubah:
1. Signature Key (midtrans_client.verifikasi_signature()) -- notifikasi
   yang signature-nya tidak cocok DITOLAK TOTAL, tidak peduli isi payload-nya.
2. order_id HARUS invoice yang benar-benar dibuat lewat checkout (bukan
   dikarang begitu saja).
3. gross_amount HARUS SAMA PERSIS dengan `jumlah` yang tercatat di invoice
   saat checkout dibuat -- BUKAN dipercaya dari payload notifikasi.

IDEMPOTEN: Midtrans SECARA RESMI bisa mengirim notifikasi yang sama lebih
dari sekali (retry) -- kalau status invoice yang tersimpan SUDAH SAMA
dengan status baru dari notifikasi ini, tidak ada perubahan apa pun yang
dilakukan lagi (mencegah periode aktif "diperpanjang dobel" oleh
notifikasi duplikat untuk transaksi yang sama)."""

import json
from datetime import datetime, timedelta

import billing_invoice_db
import midtrans_client
import subscription_db

STATUS_PAID = "paid"
STATUS_PENDING = "pending"
STATUS_DENIED = "denied"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"

# SESUAI cakupan Phase 4: enam transaction_status Midtrans yang wajib
# ditangani (settlement/capture/pending/expire/cancel/deny).
_TRANSACTION_STATUS_VALID = {"capture", "settlement", "pending", "deny", "cancel", "expire"}


def _map_status(transaction_status: str, fraud_status: str = None) -> str:
    """capture+accept -> paid, capture+challenge -> pending (perlu tinjauan
    manual, KHUSUS kartu kredit), capture+lainnya -> denied. settlement
    selalu paid (VA/QRIS/dst -- tidak ada tahap fraud review)."""
    if transaction_status not in _TRANSACTION_STATUS_VALID:
        raise ValueError(f"transaction_status tidak dikenal: {transaction_status}")
    if transaction_status == "capture":
        if fraud_status == "accept":
            return STATUS_PAID
        if fraud_status == "challenge":
            return STATUS_PENDING
        return STATUS_DENIED
    return {
        "settlement": STATUS_PAID,
        "pending": STATUS_PENDING,
        "deny": STATUS_DENIED,
        "cancel": STATUS_CANCELLED,
        "expire": STATUS_EXPIRED,
    }[transaction_status]


def _hitung_periode_mulai(tenant_id: int, sekarang: datetime, exclude_invoice_id: int) -> datetime:
    """"Perpanjangan otomatis": kalau tenant masih punya invoice PAID LAIN
    dengan periode_selesai di MASA DEPAN (langganan berjalan belum habis),
    periode baru MENYAMBUNG dari situ -- bukan dari sekarang, supaya sisa
    hari yang sudah dibayar tidak hilang begitu Owner memperpanjang lebih
    awal. Kalau tidak ada (pertama kali bayar, atau langganan sebelumnya
    sudah kedaluwarsa), periode baru dimulai dari sekarang."""
    sekarang_iso = sekarang.isoformat(timespec="seconds")
    kandidat = [
        inv for inv in billing_invoice_db.list_invoices(tenant_id=tenant_id)
        if inv["id"] != exclude_invoice_id and inv["status"] == STATUS_PAID
        and inv["periode_selesai"] and inv["periode_selesai"] > sekarang_iso
    ]
    if not kandidat:
        return sekarang
    terbaru = max(kandidat, key=lambda inv: inv["periode_selesai"])
    return datetime.fromisoformat(terbaru["periode_selesai"])


def _aktifkan_subscription(tenant_id: int, package_kode: str):
    """SESUAI cakupan Phase 4: mengaktifkan PAKET + STATUS 'active' saja --
    trial_start/trial_end/grace_start/grace_end (murni urusan Phase 3)
    SAMA SEKALI TIDAK disentuh di sini."""
    if subscription_db.get_subscription(tenant_id) is None:
        subscription_db.create_default_subscription(tenant_id, package=package_kode, status="active")
        return
    subscription_db.update_package(tenant_id, package_kode)
    subscription_db.update_status(tenant_id, "active")


def proses_notifikasi(payload: dict) -> dict:
    """Return invoice TERBARU setelah diproses. Melempar ValueError untuk
    SEMUA kegagalan validasi (signature/order_id/amount/status tidak
    dikenal) -- routers/billing_webhook.py menerjemahkannya jadi HTTP 400,
    TANPA efek samping (invoice/subscription) tersisa kalau validasi
    manapun gagal."""
    order_id = str(payload.get("order_id") or "")
    status_code = str(payload.get("status_code") or "")
    gross_amount = str(payload.get("gross_amount") or "")
    signature_key = str(payload.get("signature_key") or "")
    transaction_status = str(payload.get("transaction_status") or "")
    fraud_status = payload.get("fraud_status")
    payment_type = payload.get("payment_type")

    if not midtrans_client.verifikasi_signature(order_id, status_code, gross_amount, signature_key):
        raise ValueError("Signature tidak valid.")

    invoice = billing_invoice_db.get_invoice_by_order_id(order_id)
    if invoice is None:
        raise ValueError(f"order_id tidak dikenal: {order_id}")

    try:
        gross_amount_angka = int(float(gross_amount))
    except (TypeError, ValueError):
        raise ValueError("gross_amount tidak valid.")
    if gross_amount_angka != int(invoice["jumlah"]):
        raise ValueError(
            f"gross_amount tidak cocok dengan invoice (payload={gross_amount_angka}, "
            f"invoice={invoice['jumlah']})."
        )

    status_baru = _map_status(transaction_status, fraud_status)

    if invoice["status"] == status_baru:
        # Notifikasi duplikat (retry Midtrans) untuk status yang SAMA
        # dengan yang sudah tercatat -- tidak ada apa pun yang perlu
        # diubah lagi (lihat catatan IDEMPOTEN di docstring modul).
        return invoice

    fields = {
        "status": status_baru,
        "payment_type": payment_type,
        "metode_pembayaran": payment_type,
        "raw_notification": json.dumps(payload),
    }
    if status_baru == STATUS_PAID:
        sekarang = datetime.now()
        periode_mulai = _hitung_periode_mulai(invoice["tenant_id"], sekarang, exclude_invoice_id=invoice["id"])
        periode_selesai = periode_mulai + timedelta(days=invoice["durasi_hari"])
        fields["periode_mulai"] = periode_mulai.isoformat(timespec="seconds")
        fields["periode_selesai"] = periode_selesai.isoformat(timespec="seconds")
        fields["paid_at"] = sekarang.isoformat(timespec="seconds")

    billing_invoice_db.update_invoice(invoice["id"], **fields)

    if status_baru == STATUS_PAID:
        _aktifkan_subscription(invoice["tenant_id"], invoice["package_kode"])

    return billing_invoice_db.get_invoice(invoice["id"])
