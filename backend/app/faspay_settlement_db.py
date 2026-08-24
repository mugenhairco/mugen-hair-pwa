"""faspay_settlement_db.py — Settlement Faspay per Terminal (Tenant)
=============================================================================
"Terminal" = Tenant (keputusan eksplisit Owner) -- fokus HANYA transaksi
Faspay SNAP Advance (snap_payment_transactions/snap_payment_db.py), TIDAK
menyentuh modul Xpress v4 (booking_payment_transactions/subscription_invoices)
maupun flow checkout/webhook/return URL/polling SNAP yang sudah ada sama
sekali -- modul ini MURNI membaca snap_payment_transactions (sumber data
yang SUDAH ADA & teruji) lalu menambah lapisan closing/rekonsiliasi baru di
atasnya.

DUA TAHAP pencocokan (SESUAI instruksi: real-time TIDAK boleh menganggap
data Faspay tersedia langsung, H+1 baru rekonsiliasi final):

1. REAL-TIME (buat_settlement(), saat closing diajukan) -- MURNI mengecek
   konsistensi data LOKAL kita sendiri (hasil webhook Payment Notification
   yang sudah masuk): transaksi yang statusnya SUDAH final (PAID/FAILED/
   EXPIRED/CANCELLED) dianggap "match", yang masih menggantung (CREATED/
   PENDING -- webhook belum/tidak pernah sampai) ditandai "pending_faspay"
   (WARNING). TIDAK memanggil Faspay sama sekali di tahap ini.

2. H+1 (jalankan_rekonsiliasi_h1(), MANUAL dipicu Super Admin -- proyek ini
   TIDAK punya infrastruktur scheduler/cron sama sekali, pola konsisten
   dengan "Cek Ulang ke Provider" yang sudah ada di booking.py) -- untuk
   TIAP transaksi, panggil Inquiry API SNAP Advance yang SUDAH
   diimplementasikan sungguhan (snap_advance_client.inquiry_status_va()/
   query_payment_qris()/status_direct_debit(), dikonfirmasi 1:1 ke dokumen
   resmi Faspay) sebagai sumber independen, lalu bandingkan nominal/status/
   reference terhadap data lokal.

KETERBATASAN JUJUR (BUKAN diselesaikan dengan menebak):
- "Missing in Terminal Settlement" (Faspay punya transaksi yang TIDAK kita
  ketahui) TIDAK bisa dideteksi -- Inquiry SNAP Advance yang terdokumentasi
  HANYA lookup-per-referensi (per transaksi kita SUDAH tahu), BUKAN endpoint
  daftar/laporan settlement per periode. Kategori ini TIDAK PERNAH
  dihasilkan modul ini.
- Item channel "direct_debit"/"ewallet" butuh `channel_code` spesifik (1
  dari 14 kode resmi) yang DIPILIH SAAT PEMBAYARAN DIBUAT tapi TIDAK
  tersimpan per-transaksi di snap_payment_transactions (gap skema yang SUDAH
  ADA sebelum modul ini, BUKAN diperkenalkan di sini) -- item kategori ini
  ditandai "tidak_bisa_dicek" di H+1, TIDAK ditebak channel_code-nya.
- QRIS memakai `snap_qris_channel_code` KONFIGURASI PLATFORM SAAT INI
  (bukan snapshot per-transaksi -- kolom itu juga tidak ada) sebagai
  best-effort; kalau Super Admin mengubah default ini SETELAH transaksi
  lama dibuat, Inquiry H+1 transaksi lama bisa salah channel -- item
  tersebut akan gagal Inquiry dan masuk "tidak_bisa_dicek", BUKAN
  disalahartikan diam-diam."""

from datetime import date, datetime

import gateway_client_base as core
import snap_advance_client
import snap_advance_db
import snap_payment_db
import snap_webhook
from database import get_conn

STATUS_RECONCILED = "RECONCILED"
STATUS_WARNING = "WARNING"
STATUS_FINAL_MISMATCH = "FINAL_MISMATCH"
STATUS_VALID = {STATUS_RECONCILED, STATUS_WARNING, STATUS_FINAL_MISMATCH}

MATCH_MATCH = "match"
MATCH_PENDING_FASPAY = "pending_faspay"

H1_FINAL_MATCH = "final_match"
# Didefinisikan untuk kelengkapan skema (UI perlu tahu kategori ini ADA)
# TAPI TIDAK PERNAH dihasilkan modul ini saat ini -- snap_advance_client.py
# belum membedakan "Faspay bilang referensi tidak ditemukan" dari error lain
# (GatewayRequestError generik untuk SEMUA responseCode gagal), jadi
# _cek_transaksi_ke_faspay() TIDAK menebak sebuah error berarti "missing di
# Faspay" -- selalu jatuh ke H1_TIDAK_BISA_DICEK yang jujur.
H1_MISSING_DI_FASPAY = "missing_di_faspay"
H1_AMOUNT_MISMATCH = "amount_mismatch"
H1_STATUS_MISMATCH = "status_mismatch"
H1_REFERENCE_MISMATCH = "reference_mismatch"
H1_TIDAK_BISA_DICEK = "tidak_bisa_dicek"

# Channel SNAP yang Inquiry-nya SUDAH diimplementasikan sungguhan (lihat
# snap_advance_client.py) -- "ewallet" DISPATCH lewat status_direct_debit()
# yang sama (E-Wallet = kategori channel di dalam Direct Debit, BUKAN
# produk terpisah, lihat catatan snap_advance_client.py audit lanjutan #4).
_CHANNEL_BISA_DICEK_LANGSUNG = {"va"}  # qris/direct_debit/ewallet perlu channel_code, lihat _cek_transaksi_ke_faspay()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ambil_transaksi_tenant_tanggal(tenant_id: int, tanggal: str) -> list:
    """`tanggal`: 'YYYY-MM-DD'. Filter `created_at` (BUKAN paid_at) supaya
    "seluruh transaksi Faspay pada tanggal tersebut" ikut mencakup yang
    masih pending/gagal, bukan cuma yang berhasil dibayar (pola sama
    seperti transaction_report_db.py::list_transactions() untuk filter
    tanggal)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM snap_payment_transactions WHERE tenant_id = ? "
            "AND created_at >= ? AND created_at <= ? ORDER BY id ASC",
            (tenant_id, f"{tanggal}T00:00:00", f"{tanggal}T23:59:59"),
        ).fetchall()
        return [dict(r) for r in rows]


def _hitung_item_realtime(transaksi: dict) -> tuple:
    """Return (match_status, match_detail) MURNI dari data lokal -- TIDAK
    memanggil Faspay (lihat catatan modul, tahap real-time)."""
    if transaksi["status"] in snap_payment_db.STATUS_FINAL:
        return MATCH_MATCH, None
    return MATCH_PENDING_FASPAY, (
        f"Status lokal masih '{transaksi['status']}' -- belum ada notifikasi "
        f"final dari Faspay saat closing ini diajukan."
    )


def preview_settlement(tenant_id: int, tanggal: str) -> dict:
    """Dipanggil endpoint GET preview (TIDAK menulis apa pun) -- terminal
    melihat daftar & total SEBELUM benar-benar Submit Settlement."""
    transaksi_list = _ambil_transaksi_tenant_tanggal(tenant_id, tanggal)
    items = []
    jumlah_match = 0
    jumlah_warning = 0
    for t in transaksi_list:
        match_status, match_detail = _hitung_item_realtime(t)
        if match_status == MATCH_MATCH:
            jumlah_match += 1
        else:
            jumlah_warning += 1
        items.append({
            "snap_transaction_id": t["id"], "order_id": t["payment_reference"],
            "reference_id_provider": t["provider_transaction_id"], "payment_method": t["channel"],
            "nominal": t["amount"], "status_pembayaran": t["status"], "timestamp_transaksi": t["created_at"],
            "match_status": match_status, "match_detail": match_detail,
        })
    return {
        "tanggal": tanggal, "jumlah_transaksi": len(items),
        "total_nominal": sum(t["amount"] for t in transaksi_list),
        "jumlah_match": jumlah_match, "jumlah_warning": jumlah_warning,
        "status_rekonsiliasi": STATUS_WARNING if jumlah_warning else STATUS_RECONCILED,
        "items": items,
    }


def sudah_ada_settlement(tenant_id: int, tanggal: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM faspay_settlements WHERE tenant_id = ? AND tanggal = ?", (tenant_id, tanggal),
        ).fetchone()
        return row is not None


def buat_settlement(tenant_id: int, tenant_nama: str, tanggal: str, user: dict) -> dict:
    """Submit Settlement -- SEKALI dibuat, TIDAK ADA endpoint UPDATE/DELETE
    untuk tenant sama sekali (immutable dari sisi terminal, sesuai
    spesifikasi "settlement dikunci dan tidak dapat diubah oleh terminal").
    Menolak (ValueError) kalau tenant ini SUDAH submit untuk tanggal yang
    sama -- satu closing per tenant per hari, pola sama seperti tutup_hari()
    di manual_customer_db.py."""
    if sudah_ada_settlement(tenant_id, tanggal):
        raise ValueError(f"Settlement Faspay untuk tanggal {tanggal} sudah pernah diajukan tenant ini.")

    ringkas = preview_settlement(tenant_id, tanggal)
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO faspay_settlements "
            "(tenant_id, tenant_nama, tanggal, dibuat_oleh_user_id, dibuat_oleh_nama, "
            "jumlah_transaksi, total_nominal, jumlah_match, jumlah_warning, jumlah_final_mismatch, "
            "status_rekonsiliasi, submitted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            (tenant_id, tenant_nama, tanggal, user["id"], user.get("username") or "-",
             ringkas["jumlah_transaksi"], ringkas["total_nominal"], ringkas["jumlah_match"],
             ringkas["jumlah_warning"], ringkas["status_rekonsiliasi"], now),
        )
        settlement_id = cur.lastrowid
        for it in ringkas["items"]:
            conn.execute(
                "INSERT INTO faspay_settlement_items "
                "(settlement_id, snap_transaction_id, order_id, reference_id_provider, payment_method, "
                "nominal, status_pembayaran, timestamp_transaksi, match_status, match_detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (settlement_id, it["snap_transaction_id"], it["order_id"], it["reference_id_provider"],
                 it["payment_method"], it["nominal"], it["status_pembayaran"], it["timestamp_transaksi"],
                 it["match_status"], it["match_detail"]),
            )
    return get_settlement(settlement_id)


def get_settlement(settlement_id: int, tenant_id: int = None) -> dict | None:
    """`tenant_id` diisi dari endpoint tenant-login (isolasi Tenant ->
    Terminal -> Periode) -- None untuk Super Admin, pola sama persis
    booking_gateway_db.get_transaksi()."""
    with get_conn() as conn:
        if tenant_id is not None:
            row = conn.execute(
                "SELECT * FROM faspay_settlements WHERE id = ? AND tenant_id = ?", (settlement_id, tenant_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM faspay_settlements WHERE id = ?", (settlement_id,)).fetchone()
        if row is None:
            return None
        settlement = dict(row)
        items = conn.execute(
            "SELECT * FROM faspay_settlement_items WHERE settlement_id = ? ORDER BY id ASC", (settlement_id,),
        ).fetchall()
        settlement["items"] = [dict(i) for i in items]
        return settlement


def list_settlements(tenant_id: int = None, status: str = None,
                      tanggal_mulai: str = None, tanggal_selesai: str = None) -> list:
    """`tenant_id=None` -- SELURUH tenant (khusus Super Admin, lihat
    routers/faspay_settlement_superadmin.py). Diisi -- hanya tenant itu
    (endpoint tenant-login, isolasi WAJIB)."""
    q = "SELECT * FROM faspay_settlements WHERE 1=1"
    params = []
    if tenant_id is not None:
        q += " AND tenant_id = ?"; params.append(tenant_id)
    if status is not None:
        q += " AND status_rekonsiliasi = ?"; params.append(status)
    if tanggal_mulai is not None:
        q += " AND tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND tanggal <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def _bisa_h1(settlement: dict) -> bool:
    """H+1 -- literally "hari setelah" tanggal closing diajukan, BUKAN
    24 jam presisi (sesuai spesifikasi "Jangan menganggap Settlement Report
    Faspay tersedia secara real-time")."""
    tanggal_submit = datetime.fromisoformat(settlement["submitted_at"]).date()
    return date.today() > tanggal_submit


def _cek_transaksi_ke_faspay(transaksi: dict) -> tuple:
    """Panggil Inquiry API SNAP Advance SUNGGUHAN untuk SATU transaksi --
    return (status_code_faspay_atau_None, nominal_faspay_atau_None,
    reference_faspay_atau_None, error_atau_None). `error` diisi kalau
    panggilan gagal/channel tidak bisa dicek (lihat catatan modul) --
    pemanggil (jalankan_rekonsiliasi_h1()) yang menerjemahkan jadi
    h1_match_status, fungsi ini TIDAK PERNAH menebak."""
    channel = transaksi["channel"]
    try:
        if channel == "va":
            if not transaksi.get("va_number"):
                return None, None, None, "va_number tidak tersedia secara lokal -- tidak bisa memanggil Inquiry Status VA."
            # Fitur multi-bank VA: channel_code WAJIB dari baris transaksi ini
            # SENDIRI (bank yang dipakai saat dibuat), BUKAN config Super
            # Admin saat ini -- lihat snap_webhook.py::rekonsiliasi_manual()
            # untuk alasan lengkapnya (pola SAMA PERSIS di sini).
            if not transaksi.get("channel_code"):
                return None, None, None, "channel_code (bank VA) tidak tersedia secara lokal -- tidak bisa memanggil Inquiry Status VA."
            data = snap_advance_client.inquiry_status_va(
                transaksi["payment_reference"], transaksi["va_number"], transaksi["channel_code"])
            return (data.get("latestTransactionStatus"), data.get("paidAmount", {}).get("value")
                    if isinstance(data.get("paidAmount"), dict) else data.get("paidAmount"),
                    data.get("trxId"), None)
        if channel == "qris":
            if not transaksi.get("provider_transaction_id"):
                return None, None, None, "provider_transaction_id (referenceNo) tidak tersedia -- tidak bisa memanggil Query Payment QRIS."
            cfg = snap_advance_db.get_config_internal()
            if not cfg.get("snap_qris_channel_code"):
                return None, None, None, "channelCode QRIS platform belum dikonfigurasi Super Admin."
            data = snap_advance_client.query_payment_qris(
                transaksi["payment_reference"], transaksi["provider_transaction_id"], cfg["snap_qris_channel_code"],
            )
            amt = data.get("amount", {})
            return (data.get("latestTransactionStatus"), amt.get("value") if isinstance(amt, dict) else None,
                    data.get("originalReferenceNo"), None)
        if channel in ("direct_debit", "ewallet"):
            return None, None, None, (
                "channel_code spesifik (1 dari 14 kode resmi Direct Debit) tidak tersimpan per-transaksi "
                "di snap_payment_transactions -- tidak bisa memastikan channel mana yang harus di-Inquiry "
                "tanpa menebak (lihat catatan modul faspay_settlement_db.py)."
            )
        return None, None, None, f"Channel tidak dikenal: {channel!r}."
    except core.GatewayError as e:
        return None, None, None, str(e)


def _bandingkan_h1(transaksi: dict, status_code: str, nominal_faspay, reference_faspay: str) -> tuple:
    """Return (h1_match_status, h1_match_detail) SETELAH Inquiry SUKSES --
    order_id/reference SEBAGAI primary key (item ini SUDAH ditemukan lewat
    payment_reference kita sendiri, jadi "Reference Mismatch" di sini
    berarti Faspay mengembalikan referensi provider yang BEDA dari yang
    tercatat lokal, BUKAN referensi tidak ditemukan sama sekali -- itu
    sudah tercakup di jalur error _cek_transaksi_ke_faspay())."""
    try:
        status_faspay = snap_webhook._map_latest_transaction_status(status_code) if status_code else None
    except ValueError as e:
        return H1_TIDAK_BISA_DICEK, str(e)

    if status_faspay is not None and status_faspay != transaksi["status"]:
        return H1_STATUS_MISMATCH, (
            f"Status lokal '{transaksi['status']}' vs status Faspay '{status_faspay}' "
            f"(kode asli {status_code!r})."
        )
    if nominal_faspay is not None:
        try:
            if round(float(nominal_faspay)) != transaksi["amount"]:
                return H1_AMOUNT_MISMATCH, f"Nominal lokal Rp{transaksi['amount']:,} vs Faspay Rp{round(float(nominal_faspay)):,}."
        except (TypeError, ValueError):
            pass
    if (reference_faspay and transaksi.get("provider_transaction_id")
            and reference_faspay != transaksi["provider_transaction_id"]):
        return H1_REFERENCE_MISMATCH, (
            f"Reference lokal {transaksi['provider_transaction_id']!r} vs Faspay {reference_faspay!r}."
        )
    return H1_FINAL_MATCH, None


def jalankan_rekonsiliasi_h1(settlement_id: int, dijalankan_oleh: str) -> dict:
    """Rekonsiliasi FINAL (H+1) -- Super Admin. Idempoten/boleh diulang
    (mis. percobaan pertama sebagian gagal karena Faspay timeout) --
    SETIAP kali dijalankan, seluruh item dinilai ulang dari nol terhadap
    Inquiry API TERKINI, hasil sebelumnya ditimpa (bukan diakumulasi)."""
    settlement = get_settlement(settlement_id)
    if settlement is None:
        raise ValueError("Settlement tidak ditemukan.")
    if not _bisa_h1(settlement):
        raise ValueError(
            "Rekonsiliasi H+1 baru bisa dijalankan mulai hari setelah closing diajukan -- "
            "Settlement Report Faspay tidak dianggap tersedia secara real-time."
        )

    jumlah_final_mismatch = 0
    now = _now()
    with get_conn() as conn:
        for item in settlement["items"]:
            transaksi = conn.execute(
                "SELECT * FROM snap_payment_transactions WHERE id = ?", (item["snap_transaction_id"],),
            ).fetchone()
            if transaksi is None:
                # BUKAN H1_MISSING_DI_FASPAY -- itu istilahnya "Faspay tidak
                # punya referensi ini", sedangkan kasus ini kebalikannya
                # (baris LOKAL kita yang sudah tidak ada, belum sempat
                # bertanya ke Faspay sama sekali). Realistisnya tidak pernah
                # terjadi (tidak ada kode di proyek ini yang menghapus baris
                # snap_payment_transactions) -- guard defensif murni.
                h1_status, h1_detail = H1_TIDAK_BISA_DICEK, "Baris transaksi lokal sudah tidak ada (terhapus)."
            else:
                transaksi = dict(transaksi)
                status_code, nominal_faspay, reference_faspay, error = _cek_transaksi_ke_faspay(transaksi)
                if error is not None:
                    h1_status, h1_detail = H1_TIDAK_BISA_DICEK, error
                else:
                    h1_status, h1_detail = _bandingkan_h1(transaksi, status_code, nominal_faspay, reference_faspay)
            if h1_status not in (H1_FINAL_MATCH,):
                jumlah_final_mismatch += 1
            conn.execute(
                "UPDATE faspay_settlement_items SET h1_match_status = ?, h1_match_detail = ?, h1_checked_at = ? "
                "WHERE id = ?",
                (h1_status, h1_detail, now, item["id"]),
            )
        status_final = STATUS_FINAL_MISMATCH if jumlah_final_mismatch else STATUS_RECONCILED
        conn.execute(
            "UPDATE faspay_settlements SET status_rekonsiliasi = ?, jumlah_final_mismatch = ?, "
            "h1_dijalankan_at = ?, h1_dijalankan_oleh = ? WHERE id = ?",
            (status_final, jumlah_final_mismatch, now, dijalankan_oleh, settlement_id),
        )
    return get_settlement(settlement_id)
