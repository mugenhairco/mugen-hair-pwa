"""routers/pos.py — /api/pos/* (Point of Sale, Kasir walk-in)
=============================================================================
Menu BARU khusus hak akses sendiri (izin_pos_lihat/izin_pos_kelola, lihat
permissions.py) -- Kasir pilih Barber/Produk, Service, lalu Payment (QRIS
manual/Payment Gateway, SAMA PERSIS metode booking publik, lihat
booking_db.get_payment_settings()). Seluruh logika bisnis (mode eksklusif,
rebuild Rekap 1x/barber/hari, cascade produk) ada di pos_db.py -- router ini
HANYA meneruskan request & mengubah ValueError jadi HTTP 422, pola SAMA
PERSIS router lain di aplikasi ini."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import database as db
import booking_db
import payment_provider_client
import pos_db
import snap_payment_db
import snap_webhook
from auth import require_menu_read, require_permission

router = APIRouter(prefix="/api/pos", tags=["pos"])

WIB = ZoneInfo("Asia/Jakarta")
METODE_POS_VALID = {"qris", "gateway"}


def _hari_ini_wib() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d")


@router.get("/pengaturan")
def ambil_pengaturan(user: dict = Depends(require_menu_read("pos"))):
    """Barber/Service/Produk aktif + metode pembayaran -- SATU panggilan di
    awal (cache penuh di frontend, TANPA loading lagi tiap pindah langkah
    pilih Barber/Service/Produk, pola SAMA PERSIS wizard booking publik)."""
    tenant_id = user["tenant_id"]
    payment_settings = booking_db.get_payment_settings(tenant_id=tenant_id)
    metode_aktif = [m for m in payment_settings["metode_aktif"] if m in METODE_POS_VALID]
    return {
        "barbers": db.get_barbers(hanya_aktif=True, tenant_id=tenant_id),
        "services": db.get_services(hanya_aktif=True, tenant_id=tenant_id),
        "produk": db.get_produk_list(hanya_aktif=True, tenant_id=tenant_id),
        "metode_aktif": metode_aktif,
        "metode_nama": payment_settings["metode_nama"],
        "metode_instruksi": payment_settings["metode_instruksi"],
        "qris_merchant_nama": payment_settings["qris_merchant_nama"],
        "qris_url": payment_settings["qris_url"],
        "snap_gateway_enabled": payment_provider_client.is_enabled(),
        "snap_channel_aktif": payment_provider_client.channel_aktif() if payment_provider_client.is_enabled() else [],
        "snap_va_bank_aktif": payment_provider_client.va_bank_aktif(),
        "snap_qris_label": payment_provider_client.channel_label("qris"),
    }


class ProdukItemBody(BaseModel):
    produk_id: int
    jumlah: int


class BuatTransaksiBody(BaseModel):
    barber_id: int | None = None
    service_ids: list[int] = []
    produk_items: list[ProdukItemBody] = []
    metode_pembayaran: str
    channel: str | None = None
    bank_code: str | None = None


@router.post("/transaksi")
def buat_transaksi(body: BuatTransaksiBody, user: dict = Depends(require_permission("izin_pos_kelola"))):
    try:
        return pos_db.buat_transaksi(
            user["tenant_id"], barber_id=body.barber_id, service_ids=body.service_ids,
            produk_items=[item.model_dump() for item in body.produk_items],
            metode_pembayaran=body.metode_pembayaran, channel=body.channel, bank_code=body.bank_code,
            dibuat_oleh=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _pastikan_pos_tenant_sama(user: dict, pos: dict | None):
    if pos is None or pos.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Transaksi Point of Sale tidak ditemukan.")


@router.get("/transaksi/{pos_id}")
def ambil_transaksi(pos_id: int, user: dict = Depends(require_permission("izin_pos_kelola"))):
    pos = pos_db.get_pos_transaksi(pos_id)
    _pastikan_pos_tenant_sama(user, pos)
    return pos


@router.post("/transaksi/{pos_id}/verifikasi")
def verifikasi_manual(pos_id: int, user: dict = Depends(require_permission("izin_pos_kelola"))):
    """Tombol "Payment Diterima" (metode QRIS manual) -- Kasir sendiri yang
    melihat notifikasi pembayaran masuk, lihat docstring pos_db.
    verifikasi_manual()."""
    _pastikan_pos_tenant_sama(user, pos_db.get_pos_transaksi(pos_id))
    try:
        return pos_db.verifikasi_manual(pos_id, user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/transaksi/{pos_id}/status")
def status_transaksi(pos_id: int, user: dict = Depends(require_permission("izin_pos_kelola"))):
    """Polling status Payment Gateway -- dipakai frontend tiap beberapa
    detik selagi menunggu konfirmasi (pola SAMA PERSIS routers/booking.py::
    public_snap_status())."""
    pos = pos_db.get_pos_transaksi(pos_id)
    _pastikan_pos_tenant_sama(user, pos)
    if pos["metode_pembayaran"] != "gateway":
        raise HTTPException(status_code=422, detail="Transaksi ini bukan Payment Gateway.")
    transaksi = snap_payment_db.get_transaksi_terkini_untuk_pos(pos_id)
    if transaksi is None:
        raise HTTPException(status_code=404, detail="Transaksi pembayaran tidak ditemukan.")
    return {"status": transaksi["status"], "pos_status": pos_db.get_pos_transaksi(pos_id)["status"]}


@router.post("/transaksi/{pos_id}/cek-ulang")
def cek_ulang(pos_id: int, user: dict = Depends(require_permission("izin_pos_kelola"))):
    """Tombol "Saya Sudah Bayar"/rekonsiliasi manual Payment Gateway --
    reuse TOTAL snap_webhook.rekonsiliasi_manual() (SAMA PERSIS dipakai
    booking/billing), lihat modul itu."""
    pos = pos_db.get_pos_transaksi(pos_id)
    _pastikan_pos_tenant_sama(user, pos)
    if pos["metode_pembayaran"] != "gateway":
        raise HTTPException(status_code=422, detail="Transaksi ini bukan Payment Gateway.")
    transaksi = snap_payment_db.get_transaksi_terkini_untuk_pos(pos_id)
    if transaksi is None:
        raise HTTPException(status_code=404, detail="Transaksi pembayaran tidak ditemukan.")
    try:
        hasil = snap_webhook.rekonsiliasi_manual(transaksi["id"], user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": hasil["status"], "pos_status": pos_db.get_pos_transaksi(pos_id)["status"]}


@router.get("/transaksi-hari-ini")
def transaksi_hari_ini(tanggal: str = None, user: dict = Depends(require_menu_read("pos"))):
    """Tab "Transaksi Hari Ini" -- gabungan booking online (terverifikasi)
    + transaksi POS (lunas) pada tanggal ini, lihat pos_db.
    get_transaksi_hari_ini(). Default hari ini (WIB) kalau `tanggal` tidak
    diisi."""
    return pos_db.get_transaksi_hari_ini(user["tenant_id"], tanggal or _hari_ini_wib())
