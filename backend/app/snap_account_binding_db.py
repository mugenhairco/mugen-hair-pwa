"""snap_account_binding_db.py — Registrasi/Account Binding Faspay SNAP Advance
(prasyarat channel Direct Debit)
=============================================================================
SNAP Direct Debit (BEDA dari Dynamic VA/QRIS/E-Wallet yang satu langkah
"create-transaction lalu tunggu bayar") mewajibkan customer/tenant
MENAUTKAN rekening/kartu mereka lebih dulu (Account Binding, lewat OTP/
OAuth2 di sisi provider) SEBELUM satu pun pembayaran direct debit bisa
diminta -- dikonfirmasi dari dokumentasi publik SNAP (BI/ASPI, lihat
laporan analisis "Faspay SNAP Migration"). Token hasil binding itu
(`bank_card_token`) yang kemudian dipakai `snap_advance_client.
buat_transaksi_direct_debit()`.

Modul ini MURNI CRUD baris `snap_account_bindings` (pola sama seperti
snap_payment_db.py) -- proses binding SUNGGUHAN (endpoint registrasi,
redirect OTP, tukar authorization code) ada di snap_advance_client.py,
SELURUHNYA masih PENDING FASPAY (lihat docstring di sana). TERPADU untuk
BOOKING (customer yang menautkan rekeningnya sendiri, `customer_identifier`
= nomor WhatsApp) maupun SAAS_BILLING (tenant/Owner menautkan kartu mereka
sendiri untuk bayar langganan, `customer_identifier` = NULL -- satu binding
per tenant) -- SAMA PERSIS pola dualitas snap_payment_transactions."""

import uuid
from datetime import datetime

from database import get_conn

BINDING_STATUS_PENDING = "PENDING"
BINDING_STATUS_ACTIVE = "ACTIVE"
BINDING_STATUS_FAILED = "FAILED"
BINDING_STATUS_REVOKED = "REVOKED"
BINDING_STATUS_VALID = {BINDING_STATUS_PENDING, BINDING_STATUS_ACTIVE, BINDING_STATUS_FAILED, BINDING_STATUS_REVOKED}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def buat_binding(transaction_type: str, tenant_id: int, customer_identifier: str = None) -> dict:
    """Baris baru berstatus PENDING -- MURNI pencatatan lokal, dipanggil
    SEBELUM snap_advance_client.daftarkan_binding_akun() (yang masih PENDING
    FASPAY total). `customer_identifier` WAJIB untuk BOOKING (nomor
    WhatsApp customer), WAJIB kosong untuk SAAS_BILLING (binding milik
    tenant sendiri, bukan satu customer tertentu)."""
    from snap_payment_db import TRANSACTION_TYPE_BOOKING, TRANSACTION_TYPE_SAAS_BILLING
    if transaction_type == TRANSACTION_TYPE_BOOKING:
        if not customer_identifier:
            raise ValueError("Binding BOOKING wajib mengisi customer_identifier (nomor WhatsApp customer).")
    elif transaction_type == TRANSACTION_TYPE_SAAS_BILLING:
        if customer_identifier is not None:
            raise ValueError("Binding SAAS_BILLING TIDAK boleh mengisi customer_identifier (binding milik tenant sendiri).")
    else:
        raise ValueError(f"transaction_type tidak dikenal: {transaction_type}")

    internal_binding_id = uuid.uuid4().hex
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO snap_account_bindings "
            "(internal_binding_id, provider, transaction_type, tenant_id, customer_identifier, "
            "binding_status, created_at, updated_at) "
            "VALUES (?, 'snap_advance', ?, ?, ?, 'PENDING', ?, ?)",
            (internal_binding_id, transaction_type, tenant_id, customer_identifier, now, now),
        )
    return get_binding_by_internal_id(internal_binding_id)


def get_binding(binding_id: int, tenant_id: int = None) -> dict | None:
    with get_conn() as conn:
        if tenant_id is not None:
            row = conn.execute("SELECT * FROM snap_account_bindings WHERE id = ? AND tenant_id = ?",
                                (binding_id, tenant_id)).fetchone()
        else:
            row = conn.execute("SELECT * FROM snap_account_bindings WHERE id = ?", (binding_id,)).fetchone()
        return dict(row) if row else None


def get_binding_by_internal_id(internal_binding_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM snap_account_bindings WHERE internal_binding_id = ?",
                            (internal_binding_id,)).fetchone()
        return dict(row) if row else None


def list_binding_aktif(transaction_type: str, tenant_id: int, customer_identifier: str = None) -> list:
    """Binding berstatus ACTIVE milik tenant (+ customer tertentu untuk
    BOOKING) -- dipakai UI/orkestrasi untuk menawarkan "bayar pakai rekening
    yang sudah ditautkan" tanpa perlu binding ulang setiap transaksi."""
    q = "SELECT * FROM snap_account_bindings WHERE transaction_type = ? AND tenant_id = ? AND binding_status = 'ACTIVE'"
    params = [transaction_type, tenant_id]
    if customer_identifier is not None:
        q += " AND customer_identifier = ?"; params.append(customer_identifier)
    q += " ORDER BY id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def catat_hasil_binding(binding_id: int, *, bank_card_token: str = None,
                         provider_response: str = None, status: str = None) -> dict:
    """Simpan hasil panggilan snap_advance_client.daftarkan_binding_akun()
    SETELAH sukses -- pola `v is not None` sama seperti snap_payment_db.
    catat_hasil_create_transaction() (field kosong TIDAK menimpa NULL)."""
    if status is not None and status not in BINDING_STATUS_VALID:
        raise ValueError(f"Status binding tidak dikenal: {status}")
    kolom = {"bank_card_token": bank_card_token, "provider_response": provider_response, "binding_status": status}
    aman = {k: v for k, v in kolom.items() if v is not None}
    if not aman:
        return get_binding(binding_id)
    set_clause = ", ".join(f"{k} = ?" for k in aman)
    with get_conn() as conn:
        conn.execute(f"UPDATE snap_account_bindings SET {set_clause}, updated_at = ? WHERE id = ?",
                      list(aman.values()) + [_now(), binding_id])
    return get_binding(binding_id)


def cabut_binding(binding_id: int):
    """Tandai REVOKED -- idempoten (binding yang sudah REVOKED tetap
    REVOKED, tidak ada transisi mundur). MURNI ubah status lokal --
    memberi tahu Faspay bahwa binding dicabut (kalau memang ada endpoint
    unbinding) adalah tanggung jawab pemanggil lewat snap_advance_client.py
    (belum diimplementasikan, PENDING FASPAY)."""
    with get_conn() as conn:
        conn.execute("UPDATE snap_account_bindings SET binding_status = 'REVOKED', updated_at = ? "
                     "WHERE id = ? AND binding_status != 'REVOKED'", (_now(), binding_id))
    return get_binding(binding_id)
