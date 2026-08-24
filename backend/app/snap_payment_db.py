"""snap_payment_db.py — Riwayat Transaksi Faspay SNAP Advance (Booking Payment
Tenant + SaaS Billing TERPADU)
=============================================================================
CRUD `snap_payment_transactions`/`snap_payment_status_log` (lihat
snap_payment_migrasi.py untuk skema & alasan "satu tabel, dua use case").
State machine (STATUS_VALID/STATUS_FINAL/update_status()) SENGAJA meniru
PERSIS pola booking_gateway_db.py -- compare-and-swap SQL untuk race-safety,
guard status final -- yang SUDAH terbukti benar & teruji lewat integrasi
Xpress v4 existing (lihat laporan analisis "Faspay SNAP Migration" Tahap 1),
BUKAN ditulis ulang dari nol.

`payment_reference` (bukan row id) yang jadi SATU-SATUNYA cara webhook
menentukan BOOKING vs SAAS_BILLING (instruksi migrasi eksplisit: "Jangan
mengandalkan nominal atau nama customer... Gunakan payment reference/internal
transaction ID yang deterministic") -- lihat tentukan_tipe_transaksi()."""

import json
import uuid
from datetime import datetime

from database import get_conn

TRANSACTION_TYPE_BOOKING = "BOOKING"
TRANSACTION_TYPE_SAAS_BILLING = "SAAS_BILLING"

# Prefix deterministic -- dikirim ke Faspay sebagai bagian dari referensi
# transaksi (nama field SISI FASPAY persis PENDING FASPAY, lihat
# snap_advance_client.py) DAN dipakai webhook untuk dispatch tipe transaksi.
# Format konsep dari instruksi migrasi (`BOOKING-{tenant}-{booking_id}`/
# `SUBSCRIPTION-{tenant}-{invoice_id}`) DITAMBAH sufiks UUID pendek supaya
# unik per PERCOBAAN checkout (satu booking/invoice bisa punya lebih dari
# satu percobaan kalau yang sebelumnya expired/gagal, pola sama seperti
# booking_gateway_db.buat_order_id()) -- panjang/batasan karakter PERSIS
# yang diterima field Faspay (partnerReferenceNo/bill_no) PENDING FASPAY,
# format ini sengaja ringkas (prefix + 2 angka + 12 hex) untuk aman
# terhadap batas panjang field yang lazim di API pembayaran (~64 karakter).
PREFIX_BOOKING = "BOOKING-"
PREFIX_SAAS_BILLING = "SUBSCRIPTION-"

STATUS_CREATED = "CREATED"
STATUS_PENDING = "PENDING"
STATUS_PAID = "PAID"
STATUS_FAILED = "FAILED"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELLED = "CANCELLED"
STATUS_VALID = {STATUS_CREATED, STATUS_PENDING, STATUS_PAID, STATUS_FAILED, STATUS_EXPIRED, STATUS_CANCELLED}
# SESUAI instruksi migrasi #5: begitu transaksi mencapai salah satu status
# ini, TIDAK ADA transisi lanjutan yang sah -- TERMASUK PAID (beda dari
# booking_gateway_db.STATUS_FINAL yang masih mengizinkan "berhasil"->"refund"
# -- scope SNAP Advance instruksi migrasi TIDAK menyebutkan status refund
# sama sekali, jadi TIDAK ditambahkan di sini supaya tidak mengarang state
# yang tidak diminta). Contoh eksplisit dari instruksi: "PAID -> PENDING
# tidak boleh terjadi hanya karena webhook terlambat."
STATUS_FINAL = {STATUS_PAID, STATUS_FAILED, STATUS_EXPIRED, STATUS_CANCELLED}

CHANNEL_VALID = {"va", "qris", "ewallet", "direct_debit"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def buat_payment_reference(transaction_type: str, tenant_id: int, entity_id: int) -> str:
    """Murni generate string (TIDAK menyentuh DB) -- dipakai SEBELUM baris
    transaksi dibuat, pola sama seperti booking_gateway_db.buat_order_id().
    `entity_id` = booking_id (BOOKING) atau subscription_invoice_id
    (SAAS_BILLING)."""
    if transaction_type == TRANSACTION_TYPE_BOOKING:
        prefix = PREFIX_BOOKING
    elif transaction_type == TRANSACTION_TYPE_SAAS_BILLING:
        prefix = PREFIX_SAAS_BILLING
    else:
        raise ValueError(f"transaction_type tidak dikenal: {transaction_type}")
    return f"{prefix}{tenant_id}-{entity_id}-{uuid.uuid4().hex[:12]}"


def tentukan_tipe_transaksi(payment_reference: str) -> str:
    """SATU-SATUNYA cara webhook menentukan BOOKING vs SAAS_BILLING (SESUAI
    instruksi migrasi -- TIDAK PERNAH menebak dari nominal/nama customer).
    Melempar ValueError kalau prefix tidak dikenal -- pemanggil (snap_webhook.py)
    WAJIB menolak notifikasi yang referensinya tidak dikenal, BUKAN
    menebak jenisnya."""
    if payment_reference.startswith(PREFIX_BOOKING):
        return TRANSACTION_TYPE_BOOKING
    if payment_reference.startswith(PREFIX_SAAS_BILLING):
        return TRANSACTION_TYPE_SAAS_BILLING
    raise ValueError(f"payment_reference tidak dikenali sebagai transaksi BOOKING maupun SAAS_BILLING: {payment_reference}")


def buat_transaksi(transaction_type: str, tenant_id: int, amount: int, *,
                    booking_id: int = None, subscription_invoice_id: int = None,
                    channel: str = None, ewallet_provider: str = None, binding_id: int = None,
                    provider: str = "snap_advance") -> dict:
    """Buat baris transaksi baru berstatus CREATED -- MURNI pencatatan
    lokal, TIDAK memanggil Faspay sama sekali (pemanggil di lapisan atas
    yang memanggil snap_advance_client.buat_transaksi_*() SETELAH baris ini
    dibuat, pola sama seperti booking_gateway_db.buat_transaksi() dipanggil
    SETELAH payment_gateway_client.buat_transaksi() sukses -- lihat
    routers/booking.py::public_buat_booking() untuk urutan yang sudah
    proven). `booking_id` WAJIB diisi (subscription_invoice_id KOSONG) untuk
    BOOKING, sebaliknya untuk SAAS_BILLING -- validasi silang di bawah
    mencegah baris "amfibi" yang datanya ambigu.

    `binding_id` HANYA relevan untuk channel="direct_debit" (rujukan ke
    snap_account_bindings -- lihat snap_account_binding_db.py) -- channel
    lain (va/qris/ewallet) TIDAK butuh binding sama sekali, jadi TIDAK
    divalidasi wajib di sini (pemanggil yang tahu channel mana yang
    butuh binding).

    `provider` SENGAJA parameter (default "snap_advance", BUKAN literal
    hardcoded di SQL) -- kolom `provider` di tabel ini adalah seam resmi
    untuk penyedia pembayaran lain di masa depan (lihat
    payment_provider_client.py, dipanggil SATU-SATUNYA lewat sana oleh
    routers/booking.py & routers/billing.py) TANPA perlu mengubah modul ini
    lagi kalau providernya berganti."""
    if transaction_type == TRANSACTION_TYPE_BOOKING:
        if not booking_id or subscription_invoice_id is not None:
            raise ValueError("Transaksi BOOKING wajib mengisi booking_id, TIDAK boleh mengisi subscription_invoice_id.")
        entity_id = booking_id
    elif transaction_type == TRANSACTION_TYPE_SAAS_BILLING:
        if not subscription_invoice_id or booking_id is not None:
            raise ValueError("Transaksi SAAS_BILLING wajib mengisi subscription_invoice_id, TIDAK boleh mengisi booking_id.")
        entity_id = subscription_invoice_id
    else:
        raise ValueError(f"transaction_type tidak dikenal: {transaction_type}")
    if channel is not None and channel not in CHANNEL_VALID:
        raise ValueError(f"Channel SNAP Advance tidak dikenal: {channel}")

    payment_reference = buat_payment_reference(transaction_type, tenant_id, entity_id)
    internal_transaction_id = uuid.uuid4().hex
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO snap_payment_transactions "
            "(internal_transaction_id, provider, payment_reference, transaction_type, tenant_id, "
            "booking_id, subscription_invoice_id, channel, ewallet_provider, binding_id, amount, status, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)",
            (internal_transaction_id, provider, payment_reference, transaction_type, tenant_id,
             booking_id, subscription_invoice_id, channel, ewallet_provider, binding_id, amount, now, now),
        )
    return get_transaksi_by_reference(payment_reference)


def get_transaksi(transaksi_id: int, tenant_id: int = None) -> dict | None:
    """`tenant_id` diisi dari endpoint tenant-login kalau dipanggil dari
    konteks itu -- None untuk webhook/superadmin (pola sama persis
    booking_gateway_db.get_transaksi())."""
    with get_conn() as conn:
        if tenant_id is not None:
            row = conn.execute(
                "SELECT * FROM snap_payment_transactions WHERE id = ? AND tenant_id = ?",
                (transaksi_id, tenant_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM snap_payment_transactions WHERE id = ?", (transaksi_id,)).fetchone()
        return dict(row) if row else None


def get_transaksi_by_reference(payment_reference: str) -> dict | None:
    """Dipakai snap_webhook.py -- payment_reference datang dari payload
    notifikasi provider, BUKAN dari sesi tenant manapun, jadi TIDAK di-scope
    tenant_id di sini (pola sama persis booking_gateway_db.get_transaksi_by_order_id())."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM snap_payment_transactions WHERE payment_reference = ?",
                            (payment_reference,)).fetchone()
        return dict(row) if row else None


def list_transaksi(tenant_id: int, transaction_type: str = None, status: str = None) -> list:
    q = "SELECT * FROM snap_payment_transactions WHERE tenant_id = ?"
    params = [tenant_id]
    if transaction_type is not None:
        q += " AND transaction_type = ?"; params.append(transaction_type)
    if status is not None:
        q += " AND status = ?"; params.append(status)
    q += " ORDER BY id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_transaksi_terkini_untuk_booking(booking_id: int) -> dict | None:
    """Baris SNAP Advance TERBARU untuk satu booking (bisa lebih dari satu
    percobaan checkout kalau yang sebelumnya expired/gagal) -- dipakai
    booking_db.py::_perkaya_status_gateway() sebagai fallback begitu
    booking_gateway_db (Xpress v4) tidak menemukan apa pun untuk booking
    ini, supaya booking hasil checkout SNAP juga tampil status gateway-nya
    di halaman Booking/Riwayat Transaksi."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM snap_payment_transactions WHERE booking_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (booking_id,),
        ).fetchone()
        return dict(row) if row else None


def get_transaksi_terkini_untuk_booking_batch(booking_ids: list) -> dict:
    """Versi BATCH get_transaksi_terkini_untuk_booking() -- dipakai
    booking_db.get_booking_list() supaya memperkaya SATU HALAMAN booking
    tidak memicu satu query terpisah per baris, pola SAMA PERSIS
    booking_gateway_db.get_transaksi_terkini_untuk_booking_batch(). Return
    {booking_id: baris transaksi TERBARU}, booking_id tanpa transaksi SNAP
    sama sekali TIDAK muncul sebagai key."""
    if not booking_ids:
        return {}
    placeholder = ", ".join("?" for _ in booking_ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM snap_payment_transactions WHERE booking_id IN ({placeholder}) ORDER BY id ASC",
            booking_ids,
        ).fetchall()
    hasil = {}
    for r in rows:
        hasil[r["booking_id"]] = dict(r)  # baris TERAKHIR per booking_id menang (ORDER BY id ASC)
    return hasil


def get_transaksi_terkini_untuk_subscription_invoice(subscription_invoice_id: int) -> dict | None:
    """Sama seperti get_transaksi_terkini_untuk_booking() tapi untuk sisi
    SAAS_BILLING -- dipakai routers/billing.py untuk melengkapi detail
    invoice (nomor VA/QR) kalau Owner reload halaman di tengah pembayaran."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM snap_payment_transactions WHERE subscription_invoice_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (subscription_invoice_id,),
        ).fetchone()
        return dict(row) if row else None


def catat_hasil_create_transaction(transaksi_id: int, *, provider_transaction_id: str = None,
                                    va_number: str = None, qr_content: str = None, qr_url: str = None,
                                    ewallet_deeplink_url: str = None, expired_at: str = None,
                                    provider_response: str = None, status: str = None) -> dict:
    """Simpan hasil panggilan snap_advance_client.buat_transaksi_*() SETELAH
    sukses -- field yang TIDAK diisi (None) TIDAK disentuh (pola `v is not
    None` sama seperti booking_gateway_db.update_status(), supaya panggilan
    parsial tidak menimpa field lain jadi NULL)."""
    kolom = {
        "provider_transaction_id": provider_transaction_id, "va_number": va_number,
        "qr_content": qr_content, "qr_url": qr_url, "ewallet_deeplink_url": ewallet_deeplink_url,
        "expired_at": expired_at, "provider_response": provider_response, "status": status,
    }
    aman = {k: v for k, v in kolom.items() if v is not None}
    if not aman:
        return get_transaksi(transaksi_id)
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    with get_conn() as conn:
        conn.execute(f"UPDATE snap_payment_transactions SET {set_clause}, updated_at = ? WHERE id = ?",
                      list(aman.values()) + [_now(), transaksi_id])
    return get_transaksi(transaksi_id)


def catat_webhook_diterima(transaksi_id: int, raw_payload: str, berhasil: bool):
    """Audit trail MURNI (instruksi migrasi #4 "webhook processing status") --
    TIDAK PERNAH memutuskan status transaksi (itu tugas update_status() di
    bawah), hanya mencatat bahwa SATU webhook masuk & apakah berhasil
    diproses (signature valid & referensi ditemukan) atau ditolak."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE snap_payment_transactions SET webhook_raw_payload = ?, webhook_processing_status = ?, "
            "updated_at = ? WHERE id = ?",
            (raw_payload, "diterima_sukses" if berhasil else "diterima_gagal_validasi", _now(), transaksi_id),
        )


def update_status(transaksi_id: int, status_baru: str, sumber: str = "webhook", **extra_fields) -> dict:
    """Idempoten -- state machine SENGAJA meniru PERSIS
    booking_gateway_db.update_status() (compare-and-swap SQL + guard status
    final TANPA pengecualian, lihat STATUS_FINAL di atas -- beda dari
    booking_gateway_db yang mengizinkan "berhasil"->"refund"). `extra_fields`
    yang diizinkan: provider_transaction_id, expired_at, paid_at.

    SESUAI instruksi migrasi #6 (idempotency): "Jika webhook PAID diterima 5
    kali: transaksi tetap hanya sekali dianggap PAID" -- dicapai lewat DUA
    lapis guard SEKALIGUS: (1) `status_lama == status_baru` -> no-op (lihat
    di bawah), (2) compare-and-swap SQL `WHERE status = ?` -- kalau baris
    sudah berubah oleh proses lain di antara baca & tulis kita (race dua
    notifikasi nyaris bersamaan), UPDATE gagal (rowcount 0) dan fungsi ini
    memanggil dirinya sendiri ulang terhadap state TERBARU supaya SELURUH
    pengecekan (duplikat/final) dinilai ulang, bukan diam-diam menimpa."""
    if status_baru not in STATUS_VALID:
        raise ValueError(f"Status pembayaran SNAP Advance tidak dikenal: {status_baru}")
    transaksi = get_transaksi(transaksi_id)
    if transaksi is None:
        raise ValueError("Transaksi SNAP Advance tidak ditemukan.")
    status_lama = transaksi["status"]
    if status_lama == status_baru:
        return transaksi
    if status_lama in STATUS_FINAL:
        sumber_diabaikan = "rekonsiliasi_diabaikan" if sumber == "rekonsiliasi_manual" else "webhook_diabaikan"
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO snap_payment_status_log (transaction_id, status_lama, status_baru, sumber, waktu) "
                "VALUES (?, ?, ?, ?, ?)",
                (transaksi_id, status_lama, status_baru, sumber_diabaikan, _now()),
            )
        return transaksi

    kolom_diizinkan = {"provider_transaction_id", "expired_at", "paid_at"}
    aman = {k: v for k, v in extra_fields.items() if k in kolom_diizinkan and v is not None}
    aman["status"] = status_baru
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE snap_payment_transactions SET {set_clause}, updated_at = ? WHERE id = ? AND status = ?",
            list(aman.values()) + [_now(), transaksi_id, status_lama],
        )
        if cur.rowcount == 0:
            gagal_race = True
        else:
            conn.execute(
                "INSERT INTO snap_payment_status_log (transaction_id, status_lama, status_baru, sumber, waktu) "
                "VALUES (?, ?, ?, ?, ?)",
                (transaksi_id, status_lama, status_baru, sumber, _now()),
            )
            gagal_race = False
    if gagal_race:
        return update_status(transaksi_id, status_baru, sumber=sumber, **extra_fields)
    return get_transaksi(transaksi_id)


def list_status_log(transaksi_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM snap_payment_status_log WHERE transaction_id = ? ORDER BY id ASC", (transaksi_id,)
        ).fetchall()
        return [dict(r) for r in rows]
