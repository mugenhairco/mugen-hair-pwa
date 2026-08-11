"""routers/transaction_report.py — Riwayat Transaksi Super Admin
(Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant)
=============================================================================
KHUSUS Super Admin (require_superadmin) -- pusat monitoring SELURUH
transaksi pembayaran platform (booking customer + langganan SaaS), murni
membaca lewat transaction_report_db.py (lihat modul itu untuk kenapa ini
BUKAN "modul ketiga" yang menyatukan business logic, hanya lapisan
laporan). TIDAK ADA endpoint tulis di sini sama sekali -- status pembayaran
HANYA boleh berubah lewat webhook resmi (billing_webhook.py/
booking_gateway_webhook.py), TIDAK PERNAH dari Super Admin mengklik apa
pun di laporan ini."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import transaction_report_db
from auth import require_superadmin

router = APIRouter(prefix="/api/superadmin/transactions", tags=["transaction-report-superadmin"])


def _filter_dari_query(tenant_id, tanggal_mulai, tanggal_selesai, status, metode_pembayaran,
                        channel_pembayaran, jenis, cari):
    return dict(
        tenant_id=tenant_id, tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
        status=status, metode_pembayaran=metode_pembayaran, channel_pembayaran=channel_pembayaran,
        jenis=jenis, cari=cari,
    )


@router.get("")
def list_transactions(
    tenant_id: int = None, tanggal_mulai: str = None, tanggal_selesai: str = None,
    status: str = None, metode_pembayaran: str = None, channel_pembayaran: str = None,
    jenis: str = None, cari: str = None,
    user: dict = Depends(require_superadmin),
):
    data = transaction_report_db.list_transactions(**_filter_dari_query(
        tenant_id, tanggal_mulai, tanggal_selesai, status, metode_pembayaran, channel_pembayaran, jenis, cari,
    ))
    return {"transactions": data, "summary": transaction_report_db.get_summary(data)}


@router.get("/{jenis}/{transaction_id}")
def detail_transaction(jenis: str, transaction_id: int, user: dict = Depends(require_superadmin)):
    try:
        hasil = transaction_report_db.get_transaction_detail(jenis, transaction_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if hasil is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")
    return hasil


_KOLOM_EXPORT = [
    "nomor_transaksi", "tanggal", "jenis", "tenant_nama", "customer_nama", "booking_id",
    "barber_nama", "layanan", "nominal", "metode_pembayaran", "channel_pembayaran",
    "status_unified", "transaction_id_provider", "reference_id_provider", "paid_at",
]


@router.get("/export")
def export_transactions(
    tenant_id: int = None, tanggal_mulai: str = None, tanggal_selesai: str = None,
    status: str = None, metode_pembayaran: str = None, channel_pembayaran: str = None,
    jenis: str = None, cari: str = None,
    user: dict = Depends(require_superadmin),
):
    data = transaction_report_db.list_transactions(**_filter_dari_query(
        tenant_id, tanggal_mulai, tanggal_selesai, status, metode_pembayaran, channel_pembayaran, jenis, cari,
    ))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_KOLOM_EXPORT, extrasaction="ignore")
    writer.writeheader()
    for row in data:
        writer.writerow(row)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=riwayat-transaksi.csv"},
    )
