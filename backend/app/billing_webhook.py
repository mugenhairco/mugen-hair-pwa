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
import threading
from collections import defaultdict
from datetime import datetime, timedelta

import billing_gateway_client
import billing_invoice_db
import billing_periode
import subscription_db

# BUGFIX (audit, race condition #20): _hitung_periode_mulai() membaca invoice
# PAID LAIN milik tenant yang SAMA untuk memutuskan penyambungan periode --
# ini query LINTAS BARIS, jadi compare-and-swap per-baris (lihat
# billing_invoice_db.update_invoice()) TIDAK cukup melindunginya: dua
# notifikasi webhook untuk DUA invoice BERBEDA milik tenant yang sama, kalau
# diproses benar-benar bersamaan, bisa sama-sama membaca state "sebelum"
# sebelum salah satu commit, dan sama-sama menghitung periode_mulai=sekarang
# alih-alih salah satu menyambung setelah yang lain. Lock per-tenant di sini
# menyerialkan SELURUH proses_notifikasi()/rekonsiliasi_manual() untuk
# tenant yang sama -- cukup untuk topologi deployment aplikasi ini (SATU
# proses uvicorn, lihat render.yaml, TANPA --workers), karena FastAPI
# menjalankan endpoint sync ini di thread pool DALAM proses yang sama;
# threading.Lock menyerialkan lintas thread itu dengan benar. (Kalau suatu
# saat deployment berubah ke multi-proses/multi-mesin, lock in-process ini
# tidak lagi cukup -- perlu advisory lock di level database.)
_kunci_per_tenant: dict[int, threading.Lock] = defaultdict(threading.Lock)


def _kunci_tenant(tenant_id: int) -> threading.Lock:
    """Migrasi Faspay SNAP Advance: SEKARANG juga dipakai LANGSUNG oleh
    snap_webhook.py::_cascade_saas_billing() (lihat catatan pemanggil ketiga
    di _terapkan_status_invoice() di atas) -- lock per-tenant yang SAMA
    dipakai KEDUA webhook (Xpress lama & SNAP baru) supaya notifikasi dari
    KEDUANYA untuk tenant yang sama tetap terserialisasi dengan benar
    selama masa transisi dua provider berjalan berdampingan."""
    return _kunci_per_tenant[tenant_id]

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

# PROVIDER RESMI: Faspay Xpress v4 -- 9 kode payment_status_code resmi
# (dokumentasi Payment Notification): 0 Unprocessed, 1 In Process, 2
# Payment Success, 3 Payment Failed, 4 Payment Reversal, 5 No bills found,
# 7 Payment Expired, 8 Payment Cancelled, 9 Unknown. Kode 4/5/9 SENGAJA
# TIDAK dipetakan (ditolak sebagai "tidak dikenal") -- langganan SaaS TIDAK
# punya konsep refund/reversal (lihat billing_invoice_db.STATUS_VALID,
# beda dari booking_gateway_db yang punya status "refund"), dan 5/9
# menandakan sesuatu yang janggal di sisi Faspay sendiri.
_STATUS_CODE_KE_STATUS = {
    "0": STATUS_PENDING,
    "1": STATUS_PENDING,
    "2": STATUS_PAID,
    "3": STATUS_DENIED,
    "7": STATUS_EXPIRED,
    "8": STATUS_CANCELLED,
}


def _map_status(payment_status_code: str) -> str:
    if payment_status_code not in _STATUS_CODE_KE_STATUS:
        raise ValueError(f"payment_status_code tidak dikenal: {payment_status_code}")
    return _STATUS_CODE_KE_STATUS[payment_status_code]


def _hitung_periode_baru(tenant_id: int, invoice: dict, sekarang: datetime) -> tuple[datetime, datetime]:
    """Perbaikan Billing/Subscription (requirement Owner poin 1, 2, 6, 13):

    ANCHOR (poin 1/6/13): periode_mulai yang baru SELALU dibaca dari
    tenant_subscriptions.periode_selesai TERSIMPAN (lihat subscription_db.
    set_periode()) -- BUKAN dari `sekarang`/tanggal bayar, dan BUKAN LAGI
    dari scan invoice PAID lain (cara lama _hitung_periode_mulai(), yang
    fallback ke `sekarang` begitu tidak ketemu invoice lain dengan
    periode_selesai di masa depan -- bug PERSIS yang dikeluhkan Owner:
    pembayaran TELAT setelah periode lama sudah lewat menggeser siklus ke
    tanggal bayar). Kolom periode_selesai itu sendiri ditulis
    _aktifkan_subscription() di bawah SETELAH SETIAP pembayaran sukses, DAN
    bisa ditulis manual oleh Super Admin lewat subscription_db.
    reset_subscription() -- jadi hasil Reset otomatis jadi anchor
    berikutnya tanpa logika terpisah. Fallback ke `sekarang` HANYA kalau
    tenant belum pernah punya periode_selesai sama sekali (pembayaran
    PERTAMA tenant ini).

    KALENDER (poin 2): kalau invoice ini tahu jumlah_bulan-nya (checkout
    SEKARANG mengisi kolom itu, lihat routers/billing.py), durasi
    ditambahkan lewat billing_periode.tambah_bulan_kalender() (bulan
    kalender sungguhan, clamp akhir bulan) -- BUKAN timedelta(days=...).
    Invoice LAMA/buatan test tanpa jumlah_bulan (None) TETAP memakai
    timedelta(days=durasi_hari) apa adanya, TIDAK ADA perubahan perilaku
    untuk baris itu."""
    sub = subscription_db.get_subscription(tenant_id)
    anchor = sekarang
    if sub and sub.get("periode_selesai"):
        anchor = datetime.fromisoformat(sub["periode_selesai"])
    if invoice.get("jumlah_bulan"):
        selesai = billing_periode.tambah_bulan_kalender(anchor, invoice["jumlah_bulan"])
    else:
        selesai = anchor + timedelta(days=invoice["durasi_hari"])
    return anchor, selesai


def _aktifkan_subscription(tenant_id: int, package_kode: str, periode_mulai: str = None,
                            periode_selesai: str = None):
    """SESUAI cakupan Phase 4: mengaktifkan PAKET + STATUS 'active' saja --
    trial_start/trial_end/grace_start/grace_end (murni urusan Phase 3)
    SAMA SEKALI TIDAK disentuh di sini.

    Perbaikan Billing/Subscription: `periode_mulai`/`periode_selesai`
    (opsional) ditulis lewat subscription_db.set_periode() SETELAH
    package/status -- ini SATU-SATUNYA penulis anchor periode di jalur
    pembayaran (lihat _hitung_periode_baru() di atas), dan ini juga yang
    membuat requirement poin 12/13 (un-suspend otomatis setelah bayar,
    anchor tetap dari periode lama) berjalan TANPA kode tambahan: status
    selalu kembali 'active' di sini, terlepas dari status sebelumnya."""
    if subscription_db.get_subscription(tenant_id) is None:
        subscription_db.create_default_subscription(tenant_id, package=package_kode, status="active")
    else:
        subscription_db.update_package(tenant_id, package_kode)
        subscription_db.update_status(tenant_id, "active")
    if periode_mulai and periode_selesai:
        subscription_db.set_periode(tenant_id, periode_mulai, periode_selesai)


def _terapkan_status_invoice(invoice: dict, status_baru: str, sumber: str,
                              payment_type: str = None, raw_notification: str = None) -> dict:
    """Titik SATU-SATUNYA yang benar-benar menulis perubahan status invoice +
    aktivasi subscription -- dipanggil proses_notifikasi() (webhook resmi)
    DAN rekonsiliasi_manual() (Owner cek ulang manual ke provider, untuk
    invoice yang macet karena webhook TIDAK PERNAH sampai sama sekali),
    supaya KEDUA jalur PERSIS sama aturannya.

    Migrasi Faspay SNAP Advance: SEKARANG punya PEMANGGIL KETIGA --
    snap_webhook.py::_cascade_saas_billing() (webhook SNAP Advance yang
    baru, TERPADU dengan Booking lewat satu endpoint -- lihat modul itu)
    memanggil fungsi INI LANGSUNG (dengan `invoice` hasil query sendiri dan
    lock `_kunci_tenant()` yang SAMA di bawah), BUKAN lewat proses_notifikasi()
    (payload SNAP beda total format dari Xpress). Kalau fungsi ini di-rename/
    diubah tanda tangannya, snap_webhook.py WAJIB ikut disesuaikan.

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

    fields = {"status": status_baru}
    if payment_type is not None:
        fields["payment_type"] = payment_type
        fields["metode_pembayaran"] = payment_type
    if raw_notification is not None:
        fields["raw_notification"] = raw_notification
    if status_baru == STATUS_PAID:
        sekarang = datetime.now()
        periode_mulai, periode_selesai = _hitung_periode_baru(invoice["tenant_id"], invoice, sekarang)
        fields["periode_mulai"] = periode_mulai.isoformat(timespec="seconds")
        fields["periode_selesai"] = periode_selesai.isoformat(timespec="seconds")
        fields["paid_at"] = sekarang.isoformat(timespec="seconds")

    # BUGFIX (audit, race condition): dulu catat_status_log() + update_invoice()
    # dipanggil begitu saja setelah pengecekan status di atas -- pengecekan
    # ITU dan penulisan INI dua langkah terpisah (check-then-act di Python,
    # bukan atomik di SQL), jadi dua notifikasi webhook nyaris bersamaan
    # untuk invoice yang SAMA (Faspay mendokumentasikan retry sampai 3x)
    # bisa SAMA-SAMA lolos pengecekan "belum final/belum status ini" lalu
    # SAMA-SAMA menulis -- baris status_log ganda & aktivasi subscription
    # dipanggil dua kali. UPDATE sekarang bersyarat `WHERE status = ?`
    # (compare-and-swap atomik di level SQL, lihat billing_invoice_db.
    # update_invoice()) -- kalau GAGAL (status sudah berubah oleh proses
    # lain di antara baca & tulis kita), invoice diambil ulang & fungsi ini
    # dipanggil ULANG dari awal supaya SELURUH pengecekan (duplikat/final)
    # dinilai ulang terhadap state TERBARU, bukan diam-diam menimpa.
    berhasil = billing_invoice_db.update_invoice(invoice["id"], expected_status_lama=invoice["status"], **fields)
    if not berhasil:
        invoice_terbaru = billing_invoice_db.get_invoice(invoice["id"])
        return _terapkan_status_invoice(invoice_terbaru, status_baru, sumber, payment_type, raw_notification)

    billing_invoice_db.catat_status_log(invoice["id"], invoice["status"], status_baru, sumber=sumber)

    if status_baru == STATUS_PAID:
        _aktifkan_subscription(invoice["tenant_id"], invoice["package_kode"],
                                periode_mulai=fields["periode_mulai"], periode_selesai=fields["periode_selesai"])

    return billing_invoice_db.get_invoice(invoice["id"])


def proses_notifikasi(payload: dict) -> dict:
    """Return invoice TERBARU setelah diproses. Melempar ValueError untuk
    SEMUA kegagalan validasi (signature/bill_no/bill_total/status tidak
    dikenal) -- routers/gateway_notification.py & routers/billing_webhook.py
    menerjemahkannya jadi HTTP 400, TANPA efek samping (invoice/subscription)
    tersisa kalau validasi manapun gagal.

    Payload SESUAI format resmi Faspay Xpress v4 Payment Notification --
    lihat billing_gateway_client.py::verifikasi_signature() untuk formula
    signature."""
    bill_no = str(payload.get("bill_no") or "")
    # BUGFIX (audit): "0" (Unprocessed) adalah kode status VALID dari
    # Faspay, bukan "kosong" -- `x or ""` salah menganggap int 0 sebagai
    # falsy dan menjatuhkannya ke string kosong (_map_status("") lalu
    # gagal dengan ValueError "tidak dikenal" alih-alih terpetakan ke
    # menunggu_pembayaran). Hanya jatuh ke "" kalau field-nya benar-benar
    # TIDAK ADA (None), bukan kalau nilainya falsy-tapi-hadir.
    _kode = payload.get("payment_status_code")
    payment_status_code = str(_kode) if _kode is not None else ""
    bill_total = str(payload.get("bill_total") or "")
    signature_key = str(payload.get("signature") or "")
    payment_channel = payload.get("payment_channel")

    if not billing_gateway_client.verifikasi_signature(bill_no, payment_status_code, signature_key):
        raise ValueError("Signature tidak valid.")

    invoice = billing_invoice_db.get_invoice_by_order_id(bill_no)
    if invoice is None:
        raise ValueError(f"order_id tidak dikenal: {bill_no}")

    try:
        bill_total_angka = int(float(bill_total))
    except (TypeError, ValueError):
        raise ValueError("bill_total tidak valid.")
    if bill_total_angka != int(invoice["jumlah"]):
        raise ValueError(
            f"bill_total tidak cocok dengan invoice (payload={bill_total_angka}, "
            f"invoice={invoice['jumlah']})."
        )

    status_baru = _map_status(payment_status_code)
    with _kunci_tenant(invoice["tenant_id"]):
        return _terapkan_status_invoice(invoice, status_baru, sumber="webhook", payment_type=payment_channel,
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
    tapi tetap memvalidasi bill_total dari respons provider (defense-in-
    depth) dan tetap lewat _terapkan_status_invoice() yang SAMA PERSIS
    dipakai webhook resmi."""
    invoice = billing_invoice_db.get_invoice(invoice_id)
    if invoice is None or invoice["tenant_id"] != tenant_id:
        raise ValueError("Invoice tidak ditemukan.")

    hasil_provider = billing_gateway_client.cek_status_transaksi(invoice["order_id"])
    # BUGFIX (audit): lihat catatan sama persis di verifikasi_notifikasi() di atas.
    _kode = hasil_provider.get("payment_status_code")
    payment_status_code = str(_kode) if _kode is not None else ""
    bill_total = str(hasil_provider.get("bill_total") or "")

    try:
        bill_total_angka = int(float(bill_total))
    except (TypeError, ValueError):
        bill_total_angka = None
    if bill_total_angka is not None and bill_total_angka != int(invoice["jumlah"]):
        raise ValueError(
            f"bill_total dari provider tidak cocok dengan invoice (provider={bill_total_angka}, "
            f"invoice={invoice['jumlah']})."
        )

    status_baru = _map_status(payment_status_code)
    with _kunci_tenant(invoice["tenant_id"]):
        return _terapkan_status_invoice(invoice, status_baru, sumber="rekonsiliasi_manual",
                                         payment_type=hasil_provider.get("payment_channel"),
                                         raw_notification=json.dumps(hasil_provider))
