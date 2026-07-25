"""routers/booking.py — Modul BOOKING
=======================================
Dua router dalam SATU file ini (dipisah lewat prefix & dependency, bukan
file terpisah, supaya mudah dilihat sekali baca):

1. `public_router` (prefix `/api/public/booking`) — TANPA login sama
   sekali (halaman publik `/book`). Hanya data yang memang boleh dilihat
   siapa saja (nama barber, nama+harga+durasi service, jam operasional,
   ketersediaan slot, info pembayaran/QRIS) -- TIDAK ADA data sensitif
   toko (omzet, komisi, dst) yang bocor lewat endpoint ini.
2. `router` (prefix `/api/booking`) — dua tingkat akses lewat dependency
   berbeda per endpoint:
   - `Depends(require_admin)`: Owner/Admin, full access (lihat semua
     booking, kalender, tutup slot, jam operasional, payment settings,
     QRIS).
   - `Depends(require_barber)` (hanya endpoint `/mine`): Barber, HANYA
     booking miliknya sendiri (barber_id diambil dari akun login, sama
     persis pola seperti /api/dashboard/barber -- bukan dari parameter
     request, supaya Barber tidak bisa mengintip booking barber lain).

Barber Holiday SENGAJA tidak punya endpoint baru di sini -- dikelola
lewat /api/input-data/libur yang SUDAH ADA (lihat catatan di booking_db.py)."""

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import booking_db
import database as db
from auth import require_admin, require_barber

router = APIRouter(prefix="/api/booking", tags=["booking"])
public_router = APIRouter(prefix="/api/public/booking", tags=["booking-public"])


def _parse_service_ids(service_ids: str | None) -> list:
    if not service_ids:
        return []
    hasil = []
    for bagian in service_ids.split(","):
        bagian = bagian.strip()
        if bagian:
            hasil.append(int(bagian))
    return hasil


# =====================================================================
# PUBLIC -- halaman /book, tanpa login
# =====================================================================


@public_router.get("/barbers")
def public_barbers():
    """Semua barber AKTIF ditampilkan (barber non-aktif/dihapus Owner tidak
    relevan untuk booking baru). Status 'libur hari ini' disertakan untuk
    tampilan awal (abu-abu/On Vacation) sebelum tanggal dipilih -- validasi
    yang SEBENARNYA tetap dicek ulang per tanggal lewat /slot dan saat submit."""
    hari_ini = date.today().isoformat()
    hasil = []
    for b in db.get_barbers(hanya_aktif=True):
        hasil.append({
            "id": b["id"], "nama": b["nama"],
            "libur_hari_ini": booking_db.is_barber_libur(b["id"], hari_ini),
        })
    return hasil


@public_router.get("/services")
def public_services():
    return [
        {"id": s["id"], "nama": s["nama"], "harga": s["harga"], "durasi_menit": s.get("durasi_menit") or 60}
        for s in db.get_services(hanya_aktif=True)
    ]


@public_router.get("/pengaturan")
def public_pengaturan():
    """Semua yang dibutuhkan wizard /book: jam operasional, interval slot,
    maksimal hari booking ke depan, metode pembayaran aktif + info QRIS/
    transfer bank (kalau aktif)."""
    return {**booking_db.get_booking_settings(), **booking_db.get_payment_settings()}


@public_router.get("/slot")
def public_slot(barber_id: int, tanggal: str, service_ids: str = None):
    try:
        return booking_db.hitung_slot(barber_id, tanggal, _parse_service_ids(service_ids))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@public_router.get("/qris")
def public_qris(v: str | None = None):
    path, content_type = booking_db.get_qris_file_path()
    if path is None:
        raise HTTPException(status_code=404, detail="QRIS belum diatur.")
    return FileResponse(path, media_type=content_type)


class BookingCreateBody(BaseModel):
    barber_id: int
    tanggal: str
    jam_mulai: str
    service_ids: list[int]
    customer_nama: str
    customer_whatsapp: str
    metode_pembayaran: str
    catatan: str | None = None


@public_router.post("")
def public_buat_booking(body: BookingCreateBody):
    try:
        return booking_db.buat_booking(
            barber_id=body.barber_id, tanggal=body.tanggal, jam_mulai=body.jam_mulai,
            service_ids=body.service_ids, customer_nama=body.customer_nama,
            customer_whatsapp=body.customer_whatsapp, metode_pembayaran=body.metode_pembayaran,
            catatan=body.catatan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# =====================================================================
# ADMIN/OWNER
# =====================================================================


@router.get("")
def list_booking(tahun: int = None, bulan: int = None, barber_id: int = None,
                  status_booking: str = None, user: dict = Depends(require_admin)):
    """Dipakai Booking List & Calendar (Calendar cukup mengelompokkan hasil
    yang sama per tanggal di frontend, tidak perlu endpoint terpisah)."""
    return booking_db.get_booking_list(barber_id=barber_id, tahun=tahun, bulan=bulan,
                                        status_booking=status_booking)


@router.post("/{booking_id}/verifikasi")
def verifikasi_booking(booking_id: int, user: dict = Depends(require_admin)):
    try:
        booking_db.verifikasi_pembayaran(booking_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_booking(booking_id)


@router.post("/{booking_id}/batalkan")
def batalkan_booking(booking_id: int, user: dict = Depends(require_admin)):
    try:
        booking_db.batalkan_booking(booking_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_booking(booking_id)


class ClosedSlotBody(BaseModel):
    barber_id: int
    tanggal: str
    jam_mulai: str
    jam_selesai: str
    keterangan: str | None = None


@router.get("/closed-slot")
def list_closed_slot(barber_id: int = None, tahun: int = None, bulan: int = None,
                      user: dict = Depends(require_admin)):
    return booking_db.get_closed_slot_list(barber_id=barber_id, tahun=tahun, bulan=bulan)


@router.post("/closed-slot")
def tambah_closed_slot(body: ClosedSlotBody, user: dict = Depends(require_admin)):
    try:
        new_id = booking_db.tambah_closed_slot(
            body.barber_id, body.tanggal, body.jam_mulai, body.jam_selesai, body.keterangan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": new_id}


@router.delete("/closed-slot/{closed_slot_id}")
def hapus_closed_slot(closed_slot_id: int, user: dict = Depends(require_admin)):
    booking_db.hapus_closed_slot(closed_slot_id)
    return {"ok": True}


class BookingSettingsBody(BaseModel):
    jam_buka: str | None = None
    jam_tutup: str | None = None
    interval_menit: int | None = None
    maksimal_hari_kedepan: int | None = None


@router.get("/pengaturan")
def ambil_booking_settings(user: dict = Depends(require_admin)):
    return booking_db.get_booking_settings()


@router.put("/pengaturan")
def simpan_booking_settings(body: BookingSettingsBody, user: dict = Depends(require_admin)):
    try:
        booking_db.update_booking_settings(**body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_booking_settings()


class PaymentSettingsBody(BaseModel):
    metode_aktif: list[str] | None = None
    qris_merchant_nama: str | None = None
    bank_nama: str | None = None
    bank_nomor_rekening: str | None = None
    bank_nama_pemilik: str | None = None


@router.get("/payment-settings")
def ambil_payment_settings(user: dict = Depends(require_admin)):
    return booking_db.get_payment_settings()


@router.put("/payment-settings")
def simpan_payment_settings(body: PaymentSettingsBody, user: dict = Depends(require_admin)):
    try:
        booking_db.update_payment_settings(**body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_payment_settings()


@router.post("/qris")
async def upload_qris(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    konten = await file.read()
    try:
        booking_db.simpan_qris(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_payment_settings()


@router.delete("/qris")
def hapus_qris_endpoint(user: dict = Depends(require_admin)):
    booking_db.hapus_qris()
    return booking_db.get_payment_settings()


# =====================================================================
# BARBER -- hanya booking miliknya sendiri
# =====================================================================


@router.get("/mine")
def booking_saya(tahun: int = None, bulan: int = None, user: dict = Depends(require_barber)):
    barber_id = user.get("barber_id")
    if barber_id is None:
        raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber. Hubungi Owner.")
    return booking_db.get_booking_list(barber_id=barber_id, tahun=tahun, bulan=bulan)
