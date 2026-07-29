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
   - `Depends(require_owner_or_staff)`: Owner/Admin, full access (lihat semua
     booking, kalender, tutup slot, jam operasional, payment settings,
     QRIS).
   - `Depends(require_barber)` (hanya endpoint `/mine`): Barber, HANYA
     booking miliknya sendiri (barber_id diambil dari akun login, sama
     persis pola seperti /api/dashboard/barber -- bukan dari parameter
     request, supaya Barber tidak bisa mengintip booking barber lain).

Barber Holiday SENGAJA tidak punya endpoint baru di sini -- dikelola
lewat /api/input-data/libur yang SUDAH ADA (lihat catatan di booking_db.py)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

import booking_db
import database as db
from auth import require_owner_or_staff, require_barber

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
    relevan untuk booking baru), diurutkan sesuai `urutan` yang diatur
    Owner. Status 'libur hari ini' / 'cuti' disertakan untuk tampilan awal
    (abu-abu/On Vacation) sebelum tanggal dipilih -- validasi yang
    SEBENARNYA tetap dicek ulang per tanggal lewat /slot dan saat submit."""
    hari_ini = date.today().isoformat()
    barbers = sorted(db.get_barbers(hanya_aktif=True), key=lambda b: (b.get("urutan") or 0, b["nama"]))
    hasil = []
    for b in barbers:
        cuti = b.get("status_booking") == "cuti"
        hasil.append({
            "id": b["id"], "nama": b["nama"],
            "foto_url": f"/api/public/booking/barber-foto/{b['id']}?v={b['foto_filename']}" if b.get("foto_filename") else None,
            "libur_hari_ini": cuti or booking_db.is_barber_libur(b["id"], hari_ini),
        })
    return hasil


@public_router.get("/barber-foto/{barber_id}")
def public_barber_foto(barber_id: int):
    data, content_type = booking_db.get_foto_barber_data(barber_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Foto belum diatur.")
    return Response(content=data, media_type=content_type)


@public_router.get("/services")
def public_services():
    services = sorted(db.get_services(hanya_aktif=True), key=lambda s: (s.get("urutan") or 0, s["nama"]))
    return [
        {"id": s["id"], "nama": s["nama"], "harga": s["harga"], "durasi_menit": s.get("durasi_menit") or 60}
        for s in services
    ]


@public_router.get("/pengaturan")
def public_pengaturan():
    """Semua yang dibutuhkan wizard /book: jam operasional, hari operasional,
    interval slot, maksimal hari booking ke depan, teks header/footer/pesan,
    metode pembayaran aktif + label/instruksi + info QRIS/transfer bank
    (kalau aktif), dan daftar tanggal Toko Libur dalam rentang kalender yang
    terlihat (supaya kalender bisa langsung meng-abu-kan tanggal itu tanpa
    perlu tebak-tebakan per tanggal)."""
    booking_settings = booking_db.get_booking_settings()
    hari_ini = date.today()
    batas = hari_ini + timedelta(days=booking_settings["maksimal_hari_kedepan"])
    toko_libur_tanggal = [
        tl["tanggal"] for tl in booking_db.get_toko_libur_list()
        if hari_ini.isoformat() <= tl["tanggal"] <= batas.isoformat()
    ]
    return {
        **booking_settings,
        **booking_db.get_payment_settings(),
        "toko_libur_tanggal": toko_libur_tanggal,
    }


@public_router.get("/slot")
def public_slot(barber_id: int, tanggal: str, service_ids: str = None):
    try:
        return booking_db.hitung_slot(barber_id, tanggal, _parse_service_ids(service_ids))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@public_router.get("/qris")
def public_qris(v: str | None = None):
    data, content_type = booking_db.get_qris_data()
    if data is None:
        raise HTTPException(status_code=404, detail="QRIS belum diatur.")
    return Response(content=data, media_type=content_type)


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
                  status_booking: str = None, user: dict = Depends(require_owner_or_staff)):
    """Dipakai Booking List & Calendar (Calendar cukup mengelompokkan hasil
    yang sama per tanggal di frontend, tidak perlu endpoint terpisah)."""
    return booking_db.get_booking_list(barber_id=barber_id, tahun=tahun, bulan=bulan,
                                        status_booking=status_booking)


@router.get("/belum-dikonfirmasi")
def jumlah_belum_dikonfirmasi(user: dict = Depends(require_owner_or_staff)):
    """REVISI: Notifikasi Booking Baru -- di-poll berkala oleh frontend
    (nav.js) untuk badge menu Booking + pemicu notifikasi suara. Ringan
    (SATU angka COUNT(*), bukan daftar booking) supaya aman dipanggil
    tiap beberapa detik tanpa membebani server."""
    return {"jumlah": booking_db.hitung_booking_belum_dikonfirmasi()}


@router.post("/{booking_id}/verifikasi")
def verifikasi_booking(booking_id: int, user: dict = Depends(require_owner_or_staff)):
    try:
        booking_db.verifikasi_pembayaran(booking_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_booking(booking_id)


@router.post("/{booking_id}/batalkan")
def batalkan_booking(booking_id: int, user: dict = Depends(require_owner_or_staff)):
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
                      user: dict = Depends(require_owner_or_staff)):
    return booking_db.get_closed_slot_list(barber_id=barber_id, tahun=tahun, bulan=bulan)


@router.post("/closed-slot")
def tambah_closed_slot(body: ClosedSlotBody, user: dict = Depends(require_owner_or_staff)):
    try:
        new_id = booking_db.tambah_closed_slot(
            body.barber_id, body.tanggal, body.jam_mulai, body.jam_selesai, body.keterangan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": new_id}


@router.delete("/closed-slot/{closed_slot_id}")
def hapus_closed_slot(closed_slot_id: int, user: dict = Depends(require_owner_or_staff)):
    booking_db.hapus_closed_slot(closed_slot_id)
    return {"ok": True}


class BookingSettingsBody(BaseModel):
    jam_buka: str | None = None
    jam_tutup: str | None = None
    interval_menit: int | None = None
    maksimal_hari_kedepan: int | None = None
    hari_operasional: list[str] | None = None
    pesan_penutup: str | None = None
    pesan_nama_kosong: str | None = None
    pesan_whatsapp_invalid: str | None = None


@router.get("/pengaturan")
def ambil_booking_settings(user: dict = Depends(require_owner_or_staff)):
    return booking_db.get_booking_settings()


@router.put("/pengaturan")
def simpan_booking_settings(body: BookingSettingsBody, user: dict = Depends(require_owner_or_staff)):
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
    metode_nama: dict[str, str] | None = None
    metode_instruksi: dict[str, str] | None = None


@router.get("/payment-settings")
def ambil_payment_settings(user: dict = Depends(require_owner_or_staff)):
    return booking_db.get_payment_settings()


@router.put("/payment-settings")
def simpan_payment_settings(body: PaymentSettingsBody, user: dict = Depends(require_owner_or_staff)):
    try:
        booking_db.update_payment_settings(**body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_payment_settings()


@router.post("/qris")
async def upload_qris(file: UploadFile = File(...), user: dict = Depends(require_owner_or_staff)):
    konten = await file.read()
    try:
        booking_db.simpan_qris(file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_payment_settings()


@router.delete("/qris")
def hapus_qris_endpoint(user: dict = Depends(require_owner_or_staff)):
    booking_db.hapus_qris()
    return booking_db.get_payment_settings()


# ---- TOKO LIBUR (hari libur SELURUH toko, beda dari Barber Holiday) ----

class TokoLiburBody(BaseModel):
    tanggal: str
    keterangan: str | None = None


@router.get("/toko-libur")
def list_toko_libur(tahun: int = None, bulan: int = None, user: dict = Depends(require_owner_or_staff)):
    return booking_db.get_toko_libur_list(tahun=tahun, bulan=bulan)


@router.post("/toko-libur")
def tambah_toko_libur(body: TokoLiburBody, user: dict = Depends(require_owner_or_staff)):
    try:
        new_id = booking_db.tambah_toko_libur(body.tanggal, body.keterangan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": new_id}


@router.delete("/toko-libur/{toko_libur_id}")
def hapus_toko_libur(toko_libur_id: int, user: dict = Depends(require_owner_or_staff)):
    booking_db.hapus_toko_libur(toko_libur_id)
    return {"ok": True}


# ---- BARBER: status booking, foto, urutan (field TAMBAHAN modul Booking;
# nama/harga/aktif/dst tetap lewat /api/pengaturan/barber yang sudah ada) ----

class BarberStatusBody(BaseModel):
    status_booking: str


class BarberUrutanBody(BaseModel):
    urutan: int


@router.put("/barber/{barber_id}/status")
def ubah_status_barber(barber_id: int, body: BarberStatusBody, user: dict = Depends(require_owner_or_staff)):
    try:
        booking_db.set_status_booking_barber(barber_id, body.status_booking)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_barber(barber_id)


@router.put("/barber/{barber_id}/urutan")
def ubah_urutan_barber(barber_id: int, body: BarberUrutanBody, user: dict = Depends(require_owner_or_staff)):
    try:
        booking_db.set_urutan_barber(barber_id, body.urutan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_barber(barber_id)


@router.post("/barber/{barber_id}/foto")
async def upload_foto_barber(barber_id: int, file: UploadFile = File(...), user: dict = Depends(require_owner_or_staff)):
    konten = await file.read()
    try:
        booking_db.simpan_foto_barber(barber_id, file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_barber(barber_id)


@router.delete("/barber/{barber_id}/foto")
def hapus_foto_barber_endpoint(barber_id: int, user: dict = Depends(require_owner_or_staff)):
    try:
        booking_db.hapus_foto_barber(barber_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_barber(barber_id)


# ---- SERVICE: urutan (field TAMBAHAN modul Booking; nama/harga/durasi/dst
# tetap lewat /api/pengaturan/service yang sudah ada) ----

class ServiceUrutanBody(BaseModel):
    urutan: int


@router.put("/service/{service_id}/urutan")
def ubah_urutan_service(service_id: int, body: ServiceUrutanBody, user: dict = Depends(require_owner_or_staff)):
    try:
        booking_db.set_urutan_service(service_id, body.urutan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_service(service_id)


# =====================================================================
# BARBER -- hanya booking miliknya sendiri
# =====================================================================


@router.get("/mine")
def booking_saya(tahun: int = None, bulan: int = None, user: dict = Depends(require_barber)):
    barber_id = user.get("barber_id")
    if barber_id is None:
        raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber. Hubungi Owner.")
    return booking_db.get_booking_list(barber_id=barber_id, tahun=tahun, bulan=bulan)
