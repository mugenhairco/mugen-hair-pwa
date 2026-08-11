"""billing_webhook.py — FONDASI Multi-Tenant Phase 4: Aktivasi Otomatis dari Webhook Payment Gateway
=============================================================================
Logika MURNI (tanpa FastAPI/Request) supaya bisa diuji langsung dengan
payload buatan sendiri, tanpa HTTP -- routers/billing_webhook.py (endpoint
publik `POST /api/public/billing/midtrans-webhook` -- URL SENGAJA TIDAK
diganti nama walau kodenya sudah generik, lihat catatan di router itu)
hanya membaca body JSON lalu memanggil proses_notifikasi() di sini,
menerjemahkan ValueError jadi HTTP 400.

Webhook langganan SaaS ini TERPISAH TOTAL dari booking_gateway_webhook.py
(webhook Payment Gateway booking customer) -- dua jenis transaksi, dua
modul webhook, TIDAK saling bergantung/berbagi logika bisnis sama sekali
(lihat catatan arsitektur di payment_gateway_client.py).

KEAMANAN (SESUAI aturan eksplisit Phase 4 "jangan pernah percaya data dari
client begitu saja") -- SEMUA TIGA harus lolos sebelum satu baris pun
diubah:
1. Signature Key (billing_gateway_client.verifikasi_signature()) -- notifikasi
   yang signature-nya tidak cocok DITOLAK TOTAL, tidak peduli isi payload-nya.
2. order_id HARUS invoice yang benar-benar dibuat lewat checkout (bukan
   dikarang begitu saja).
3. gross_amount HARUS SAMA PERSIS dengan `jumlah` yang tercatat di invoice
   saat checkout dibuat -- BUKAN dipercaya dari payload notifikasi.

IDEMPOTEN: provider SECARA RESMI bisa mengirim notifikasi yang sama lebih
dari sekali (retry) -- kalau status invoice yang tersimpan SUDAH SAMA
dengan status baru dari notifikasi ini, tidak ada perubahan apa pun yang
dilakukan lagi (mencegah periode aktif "diperpanjang dobel" oleh
notifikasi duplikat untuk transaksi yang sama).

RIWAYAT STATUS: setiap transisi status SUNGGUHAN (bukan notifikasi
idempoten) dicatat ke `subscription_invoice_status_log`
(billing_invoice_db.catat_status_log()) -- dipakai Detail Transaksi Super
Admin, TIDAK memengaruhi logika aktivasi di atas sama sekali."""

import json
from datetime import datetime, timedelta

import billing_gateway_client
import billing_invoice_db
import subscription_db

STATUS_PAID = "paid"
STATUS_PENDING = "pending"
STATUS_DENIED = "denied"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"

# AUDIT (perbaikan pasca-audit kesiapan): begitu invoice mencapai salah satu
# status ini, TIDAK ADA transisi lanjutan yang sah sama sekali (beda dari
# booking_gateway_db.STATUS_FINAL yang masih mengizinkan "berhasil" ->
# "refund" -- langganan SaaS TIDAK punya konsep refund, lihat
# billing_invoice_db.STATUS_VALID). Webhook TIDAK MENJAMIN urutan pengiriman
# -- notifikasi basi yang datang setelah status final TIDAK BOLEH menurunkan/
# mengubah status lagi (lihat _terapkan_status_invoice() di bawah).
STATUS_FINAL = {STATUS_PAID, STATUS_DENIED, STATUS_CANCELLED, STATUS_EXPIRED}

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


def _terapkan_status_invoice(invoice: dict, status_baru: str, sumber: str,
                              payment_type: str = None, raw_notification: str = None) -> dict:
    """Titik SATU-SATUNYA yang benar-benar menulis perubahan status invoice +
    aktivasi subscription -- dipanggil proses_notifikasi() (webhook resmi)
    DAN rekonsiliasi_manual() (Owner cek ulang manual ke provider, untuk
    invoice yang macet karena webhook TIDAK PERNAH sampai sama sekali),
    supaya KEDUA jalur PERSIS sama aturannya.

    AUDIT (perbaikan pasca-audit kesiapan): webhook TIDAK MENJAMIN urutan
    pengiriman -- notifikasi basi yang datang SETELAH invoice sudah "paid"/
    final TIDAK BOLEH menurunkan status lagi (lihat STATUS_FINAL di atas --
    BEDA dari booking_gateway_db.STATUS_FINAL, di sini TIDAK ADA pengecualian
    sama sekali karena langganan SaaS tidak punya status refund). Transisi
    yang ditolak dicatat ke status_log dengan sumber "webhook_diabaikan"/
    "rekonsiliasi_diabaikan" untuk audit/troubleshooting, TANPA mengubah
    status invoice tersimpan."""
    if invoice["status"] == status_baru:
        # Notifikasi duplikat (retry provider) untuk status yang SAMA
        # dengan yang sudah tercatat -- tidak ada apa pun yang perlu
        # diubah lagi (lihat catatan IDEMPOTEN di docstring modul), TERMASUK
        # TIDAK menambah baris status_log (log hanya mencatat TRANSISI
        # sungguhan, bukan notifikasi yang diam-diam sama).
        return invoice

    if invoice["status"] in STATUS_FINAL:
        sumber_diabaikan = "rekonsiliasi_diabaikan" if sumber == "rekonsiliasi_manual" else "webhook_diabaikan"
        billing_invoice_db.catat_status_log(invoice["id"], invoice["status"], status_baru, sumber=sumber_diabaikan)
        return invoice

    billing_invoice_db.catat_status_log(invoice["id"], invoice["status"], status_baru, sumber=sumber)

    fields = {"status": status_baru}
    if payment_type is not None:
        fields["payment_type"] = payment_type
        fields["metode_pembayaran"] = payment_type
    if raw_notification is not None:
        fields["raw_notification"] = raw_notification
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

    if not billing_gateway_client.verifikasi_signature(order_id, status_code, gross_amount, signature_key):
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
    return _terapkan_status_invoice(invoice, status_baru, sumber="webhook", payment_type=payment_type,
                                     raw_notification=json.dumps(payload))


def rekonsiliasi_manual(invoice_id: int, tenant_id: int) -> dict:
    """AUDIT (perbaikan pasca-audit kesiapan): jalur RESMI satu-satunya
    untuk memperbaiki invoice yang macet karena webhook TIDAK PERNAH sampai
    sama sekali (beda dari retry/notifikasi basi yang sudah ditangani
    proses_notifikasi()+_terapkan_status_invoice() di atas) -- dipakai Owner
    lewat tombol "Cek Ulang ke Provider" di Billing > Riwayat Invoice.
    `tenant_id` WAJIB dari sesi login -- invoice tenant lain TIDAK PERNAH
    bisa direkonsiliasi lewat sini.

    TIDAK memerlukan verifikasi signature -- panggilan ini KELUAR ke provider
    memakai Server Key milik server sendiri (billing_gateway_client.
    cek_status_transaksi(), Core API GET), BUKAN data masuk dari luar --
    tapi tetap memvalidasi gross_amount dari respons provider (defense-in-
    depth) dan tetap lewat _terapkan_status_invoice() yang SAMA PERSIS
    dipakai webhook resmi."""
    invoice = billing_invoice_db.get_invoice(invoice_id)
    if invoice is None or invoice["tenant_id"] != tenant_id:
        raise ValueError("Invoice tidak ditemukan.")

    hasil_provider = billing_gateway_client.cek_status_transaksi(invoice["order_id"])
    transaction_status = str(hasil_provider.get("transaction_status") or "")
    fraud_status = hasil_provider.get("fraud_status")
    gross_amount = str(hasil_provider.get("gross_amount") or "")

    try:
        gross_amount_angka = int(float(gross_amount))
    except (TypeError, ValueError):
        gross_amount_angka = None
    if gross_amount_angka is not None and gross_amount_angka != int(invoice["jumlah"]):
        raise ValueError(
            f"gross_amount dari provider tidak cocok dengan invoice (provider={gross_amount_angka}, "
            f"invoice={invoice['jumlah']})."
        )

    status_baru = _map_status(transaction_status, fraud_status)
    return _terapkan_status_invoice(invoice, status_baru, sumber="rekonsiliasi_manual",
                                     payment_type=hasil_provider.get("payment_type"),
                                     raw_notification=json.dumps(hasil_provider))
