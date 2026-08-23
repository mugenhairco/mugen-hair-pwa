"""routers/booking.py — Modul BOOKING
=======================================
Dua router dalam SATU file ini (dipisah lewat prefix & dependency, bukan
file terpisah, supaya mudah dilihat sekali baca):

1. `public_router` (prefix `/api/public/booking`) — TANPA login sama
   sekali (halaman publik `/book`). Hanya data yang memang boleh dilihat
   siapa saja (nama barber, nama+harga+durasi service, jam operasional,
   ketersediaan slot, info pembayaran/QRIS) -- TIDAK ADA data sensitif
   toko (omzet, komisi, dst) yang bocor lewat endpoint ini.
2. `router` (prefix `/api/booking`) — tiga tingkat akses lewat dependency
   berbeda per endpoint:
   - `Depends(require_menu_read("booking"))` (booking, kalender, tutup slot,
     jam operasional, payment settings, QRIS) / `Depends(require_menu_read(
     "riwayat_transaksi"))` (dua endpoint /transactions*): LIHAT (GET) --
     Owner selalu lolos, staff tergantung level menu "Booking"/"Riwayat
     Transaksi" (Hak Akses Menu, lihat permissions.py::MENU_DEFS -- REVISI
     dari `require_owner_or_staff` polos, yang SEBELUMNYA selalu meloloskan
     staff tanpa syarat apa pun).
   - `Depends(require_permission("izin_booking_kelola"/"izin_booking_batalkan"/
     "izin_booking_pengaturan"/"izin_riwayat_transaksi"))`: TULIS -- Owner
     selalu lolos, staff tergantung Hak Akses Menu (level "Baca & Edit"
     menyalakan key-key ini sekaligus, lihat permissions.py::MENU_DEFS;
     default SEKARANG tetap True supaya staff yang sudah pakai modul ini
     tidak tiba-tiba terkunci).
   - `Depends(require_barber)` (hanya endpoint `/mine`): Barber, HANYA
     booking miliknya sendiri (barber_id diambil dari akun login, sama
     persis pola seperti /api/dashboard/barber -- bukan dari parameter
     request, supaya Barber tidak bisa mengintip booking barber lain).

Barber Holiday SENGAJA tidak punya endpoint baru di sini -- dikelola
lewat /api/input-data/libur yang SUDAH ADA (lihat catatan di booking_db.py)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

import billing_limits
import booking_db
import booking_gateway_db
import booking_gateway_webhook
import database as db
import feature_access
import gateway_client_base
import payment_gateway_client
import payment_gateway_db
import r2_storage
import subscription_db
import tenant_db
from auth import require_barber, require_permission, require_menu_read, resolve_tenant_publik

router = APIRouter(prefix="/api/booking", tags=["booking"])
public_router = APIRouter(prefix="/api/public/booking", tags=["booking-public"])


def resolve_tenant_publik_aktif(tenant_id: int = Depends(resolve_tenant_publik)) -> int:
    """FONDASI Multi-Tenant Phase 3: pembungkus resolve_tenant_publik (auth.py,
    TIDAK disentuh sama sekali di sini) -- dipakai SEMUA endpoint publik yang
    benar-benar menyediakan/menerima data booking (barbers, foto, services,
    pengaturan, slot, qris, buat booking), TIDAK dipakai endpoint
    /subscription-status sendiri (tujuannya justru melaporkan status
    tersebut, jadi harus tetap bisa diakses walau statusnya diblokir).
    Tenant TANPA baris subscription (lihat subscription_db.akses_diblokir())
    dianggap TIDAK diblokir -- fail-open, sama seperti dashboard internal."""
    if subscription_db.akses_diblokir(tenant_id):
        raise HTTPException(
            status_code=403,
            detail="Halaman booking toko ini sedang tidak tersedia. Hubungi pemilik toko untuk informasi lebih lanjut.",
        )
    return tenant_id


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


@public_router.get("/subscription-status")
def public_subscription_status(tenant_id: int = Depends(resolve_tenant_publik)):
    """FONDASI Multi-Tenant Phase 3: dipanggil book_public.js PALING AWAL
    (sebelum endpoint publik lain mana pun) supaya halaman booking bisa
    langsung menampilkan halaman "tidak tersedia" tanpa sempat memanggil
    /barbers, /services, /pengaturan, dst yang JUSTRU akan ditolak 403 oleh
    resolve_tenant_publik_aktif() kalau statusnya diblokir. SENGAJA memakai
    resolve_tenant_publik POLOS (bukan varian _aktif) -- endpoint ini
    JUSTRU yang melaporkan status itu, jadi harus selalu bisa diakses."""
    return {"tersedia": not subscription_db.akses_diblokir(tenant_id)}


@public_router.get("/barbers")
def public_barbers(tenant_id: int = Depends(resolve_tenant_publik_aktif)):
    """Semua barber AKTIF ditampilkan (barber non-aktif/dihapus Owner tidak
    relevan untuk booking baru), diurutkan sesuai `urutan` yang diatur
    Owner. Status 'libur hari ini' / 'cuti' disertakan untuk tampilan awal
    (abu-abu/On Vacation) sebelum tanggal dipilih -- validasi yang
    SEBENARNYA tetap dicek ulang per tanggal lewat /slot dan saat submit."""
    hari_ini = date.today().isoformat()
    barbers = sorted(db.get_barbers(hanya_aktif=True, tenant_id=tenant_id), key=lambda b: (b.get("urutan") or 0, b["nama"]))
    # AUDIT 404 file media: <img src> yang memuat foto_url di bawah tidak
    # bisa membawa Bearer token/Origin (lihat tenant_db.slug_untuk_url_media()
    # untuk penjelasan lengkap) -- slug disisipkan di sini supaya GET
    # /api/public/booking/barber-foto/{id} bisa resolve tenant-nya lewat
    # query string, sama seperti perbaikan logo/favicon.
    slug = tenant_db.slug_untuk_url_media(tenant_id)
    param_tenant = f"&tenant={slug}" if slug else ""
    hasil = []
    for b in barbers:
        cuti = b.get("status_booking") == "cuti"
        hasil.append({
            "id": b["id"], "nama": b["nama"],
            "foto_url": f"/api/public/booking/barber-foto/{b['id']}?v={b['foto_filename']}{param_tenant}" if b.get("foto_filename") else None,
            "libur_hari_ini": cuti or booking_db.is_barber_libur(b["id"], hari_ini),
        })
    return hasil


@public_router.get("/barber-foto/{barber_id}")
def public_barber_foto(barber_id: int, tenant_id: int = Depends(resolve_tenant_publik_aktif)):
    barber = db.get_barber(barber_id)
    if barber is None or barber.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=404, detail="Foto belum diatur.")
    data, content_type = booking_db.get_foto_barber_data(barber_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Foto belum diatur.")
    return Response(content=data, media_type=content_type)


@public_router.get("/services")
def public_services(tenant_id: int = Depends(resolve_tenant_publik_aktif)):
    services = sorted(db.get_services(hanya_aktif=True, tenant_id=tenant_id), key=lambda s: (s.get("urutan") or 0, s["nama"]))
    return [
        {"id": s["id"], "nama": s["nama"], "harga": s["harga"], "durasi_menit": s.get("durasi_menit") or 60}
        for s in services
    ]


@public_router.get("/pengaturan")
def public_pengaturan(tenant_id: int = Depends(resolve_tenant_publik_aktif)):
    """Semua yang dibutuhkan wizard /book: jam operasional, hari operasional,
    interval slot, maksimal hari booking ke depan, teks header/footer/pesan,
    metode pembayaran aktif + label/instruksi + info QRIS/transfer bank
    (kalau aktif), dan daftar tanggal Toko Libur dalam rentang kalender yang
    terlihat (supaya kalender bisa langsung meng-abu-kan tanggal itu tanpa
    perlu tebak-tebakan per tanggal).

    Feature Gating: kalau paket tenant ini TIDAK menyertakan fitur
    "booking_online", balas payload PENDEK `{"booking_online": False}`
    (BUKAN HTTPException) -- ini panggilan BOOTSTRAP halaman /book, frontend
    (book_public.js) perlu bisa membedakan "fitur tidak tersedia" (tampilkan
    pesan ramah) dari error jaringan biasa.

    REVISI (diminta Owner): "qris" BUKAN LAGI fitur yang di-gerbang per
    paket -- QRIS adalah metode pembayaran INTI yang harus tersedia untuk
    SEMUA paket tanpa kecuali, jadi tidak masuk akal ditawarkan sebagai
    checkbox opsional per paket (beda dari WhatsApp Reminder/Export Excel
    dkk yang MEMANG opsional). Lihat billing_db.py::_FITUR_DEFAULT untuk
    audit lengkapnya -- kode "qris" DIHAPUS TOTAL dari katalog fitur."""
    if not feature_access.tenant_has_feature(tenant_id, "booking_online"):
        return {"booking_online": False}
    booking_settings = booking_db.get_booking_settings(tenant_id=tenant_id)
    hari_ini = date.today()
    batas = hari_ini + timedelta(days=booking_settings["maksimal_hari_kedepan"])
    toko_libur_tanggal = [
        tl["tanggal"] for tl in booking_db.get_toko_libur_list(tenant_id=tenant_id)
        if hari_ini.isoformat() <= tl["tanggal"] <= batas.isoformat()
    ]
    payment_settings = booking_db.get_payment_settings(tenant_id=tenant_id)
    return {
        "booking_online": True,
        **booking_settings,
        **payment_settings,
        # Payment Gateway: daftar channel (QRIS/VA/GoPay/dst) + urutannya
        # dikonfigurasi PLATFORM-WIDE oleh Super Admin (payment_gateway_db.py),
        # BUKAN per-tenant -- hanya relevan kalau tenant ini mengaktifkan
        # metode "gateway" di atas, tapi dikirim apa adanya di sini (pola
        # sama seperti qris_url/bank_nama yang juga selalu dikirim terlepas
        # metode itu aktif atau tidak).
        "pgw_channels": payment_gateway_db.get_public_channels(),
        # Payment Gateway: Client Key + URL script checkout hosted -- SENGAJA
        # dikirim apa adanya terlepas metode "gateway" aktif/tidak (Client
        # Key MEMANG dirancang untuk frontend, lihat payment_gateway_client.py),
        # dipakai book_public.js memuat script checkout PERSIS begitu customer
        # pilih metode Payment Gateway (pola sama seperti billing.js muat Snap.js).
        "pgw_client_key": payment_gateway_client.client_key() if payment_gateway_client.is_enabled() else None,
        "pgw_checkout_script_url": payment_gateway_client.client_script_url() if payment_gateway_client.is_enabled() else None,
        "toko_libur_tanggal": toko_libur_tanggal,
    }


@public_router.get("/slot")
def public_slot(barber_id: int, tanggal: str, service_ids: str = None,
                 tenant_id: int = Depends(resolve_tenant_publik_aktif)):
    try:
        return booking_db.hitung_slot(barber_id, tanggal, _parse_service_ids(service_ids), tenant_id=tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@public_router.get("/qris")
def public_qris(v: str | None = None, tenant_id: int = Depends(resolve_tenant_publik_aktif)):
    # REVISI (diminta Owner): "qris" bukan lagi fitur ber-gerbang paket --
    # lihat catatan lengkap di public_pengaturan() di atas.
    data, content_type = booking_db.get_qris_data(tenant_id=tenant_id)
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
def public_buat_booking(body: BookingCreateBody, tenant_id: int = Depends(resolve_tenant_publik_aktif)):
    # Feature Gating "booking_online": lapis pertahanan kedua (public_pengaturan
    # di atas SUDAH menyembunyikan wizard-nya dari frontend kalau fitur ini
    # tidak aktif, tapi endpoint publik ini bisa dipanggil langsung tanpa
    # lewat UI, jadi ditegakkan juga di sini).
    if not feature_access.tenant_has_feature(tenant_id, "booking_online"):
        raise HTTPException(status_code=403, detail="Booking online tidak tersedia untuk toko ini.")
    # Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: kalau
    # metode "gateway" TAPI Super Admin belum mengisi kredensial Payment
    # Gateway booking platform-wide, TOLAK SEBELUM booking dibuat sama
    # sekali -- BUKAN membuat booking yang tidak akan pernah bisa dibayar.
    if body.metode_pembayaran == "gateway" and not payment_gateway_client.is_enabled():
        raise HTTPException(status_code=503, detail="Payment Gateway belum aktif -- silakan pilih metode pembayaran lain.")
    try:
        billing_limits.pastikan_boleh_tambah_booking(tenant_id)  # FONDASI Multi-Tenant Phase 4
        booking = booking_db.buat_booking(
            barber_id=body.barber_id, tanggal=body.tanggal, jam_mulai=body.jam_mulai,
            service_ids=body.service_ids, customer_nama=body.customer_nama,
            customer_whatsapp=body.customer_whatsapp, metode_pembayaran=body.metode_pembayaran,
            catatan=body.catatan, tenant_id=tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if body.metode_pembayaran != "gateway":
        return booking

    # Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: booking
    # SUDAH tersimpan (status_pembayaran='menunggu_verifikasi', slot
    # TERISI) -- sekarang buat transaksi checkout SUNGGUHAN ke provider.
    # Gagal (provider tidak bisa dihubungi/menolak) -> booking DIBATALKAN
    # OTOMATIS (membebaskan slot lagi, TIDAK ADA booking menggantung yang
    # tidak bisa dibayar) -- BUKAN dibiarkan tersimpan tanpa jalan bayar.
    tenant = tenant_db.get_tenant(tenant_id)
    order_id = booking_gateway_db.buat_order_id(tenant_id, booking["id"])
    item_details = [
        {"id": str(it["service_id"]), "price": it["harga"], "quantity": 1, "name": it["nama_service"][:50]}
        for it in booking["items"]
    ]
    # AUDIT (perbaikan pasca-audit kesiapan): "phone" ditambahkan (SEBELUMNYA
    # hanya "first_name") -- Faspay Xpress v4 mewajibkan msisdn di request
    # checkout (lihat payment_gateway_client.py). Form booking publik
    # SENGAJA TIDAK punya field email (keputusan eksplisit) -- "email"
    # SENGAJA TIDAK diisi di sini, client-nya sendiri yang pakai fallback
    # support@rivoirsett.com HANYA untuk memenuhi syarat API Faspay.
    customer_details = {"first_name": booking["customer_nama"][:50], "phone": booking["customer_whatsapp"]}
    channels = payment_gateway_db.get_config()["metode_aktif"]
    try:
        hasil_gateway = payment_gateway_client.buat_transaksi(
            order_id, booking["total_harga"], item_details,
            customer_details=customer_details, enabled_channels=channels,
        )
    except gateway_client_base.GatewayError as e:
        booking_db.batalkan_booking(booking["id"])
        raise HTTPException(status_code=502, detail=f"Gagal membuat transaksi pembayaran: {e}")

    transaksi = booking_gateway_db.buat_transaksi(
        order_id, tenant_id, tenant["nama_barbershop"] if tenant else "-", booking["id"],
        booking["customer_nama"], booking["nama_barber"], booking["daftar_service"], booking["total_harga"],
        checkout_token=hasil_gateway["token"], checkout_redirect_url=hasil_gateway["redirect_url"],
    )
    booking["gateway_order_id"] = order_id
    booking["checkout_token"] = transaksi["checkout_token"]
    booking["checkout_redirect_url"] = transaksi["checkout_redirect_url"]
    return booking


@public_router.get("/gateway-status/{order_id}")
def public_gateway_status(order_id: str, tenant_id: int = Depends(resolve_tenant_publik_aktif)):
    """Endpoint READ-ONLY untuk wizard booking publik POLL status
    pembayaran (lihat book_public.js) -- TIDAK PERNAH mengubah status apa
    pun, murni membaca. Status pembayaran booking HANYA berubah lewat
    booking_gateway_webhook.py (notifikasi resmi provider tervalidasi
    signature), TIDAK PERNAH dari endpoint ini/klik customer. Payload
    SENGAJA minim (status + info tampilan dasar saja, TANPA data sensitif
    toko) karena endpoint ini publik tanpa login."""
    transaksi = booking_gateway_db.get_transaksi_by_order_id(order_id)
    if transaksi is None or transaksi["tenant_id"] != tenant_id:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")
    return {
        "status_pembayaran": transaksi["status_pembayaran"],
        "channel_pembayaran": transaksi["channel_pembayaran"],
        "nominal": transaksi["nominal"],
    }


# =====================================================================
# ADMIN/OWNER
# =====================================================================


def _pastikan_booking_tenant_sama(user: dict, booking: dict | None):
    """FONDASI Multi-Tenant Phase 1: fetch-then-authorize -- `bookings` sudah
    punya kolom tenant_id langsung (lihat tenant_migrasi.py), get_booking()
    sendiri sudah otomatis menyertakannya lewat SELECT bk.*."""
    if booking is None or booking.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Booking tidak ditemukan.")


def _pastikan_closed_slot_tenant_sama(user: dict, closed_slot: dict | None):
    if closed_slot is None or closed_slot.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data closed slot tidak ditemukan.")


def _pastikan_toko_libur_tenant_sama(user: dict, toko_libur: dict | None):
    if toko_libur is None or toko_libur.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Data libur toko tidak ditemukan.")


@router.get("")
def list_booking(tahun: int = None, bulan: int = None, barber_id: int = None,
                  status_booking: str = None, user: dict = Depends(require_menu_read("booking"))):
    """Dipakai Booking List & Calendar (Calendar cukup mengelompokkan hasil
    yang sama per tanggal di frontend, tidak perlu endpoint terpisah)."""
    return booking_db.get_booking_list(barber_id=barber_id, tahun=tahun, bulan=bulan,
                                        status_booking=status_booking, tenant_id=user["tenant_id"])


@router.get("/transactions")
def list_transaksi_gateway(
    tanggal_mulai: str = None, tanggal_selesai: str = None,
    status_pembayaran: str = None, metode_pembayaran: str = None,
    user: dict = Depends(require_menu_read("riwayat_transaksi")),
):
    """Riwayat Transaksi Tenant (Implementasi Payment Gateway & Riwayat
    Transaksi Multi-Tenant) -- SELALU di-scope tenant_id dari akun login,
    TIDAK PERNAH menerima tenant_id dari parameter request (lihat
    booking_gateway_db.py::list_transaksi() untuk alasan lengkap isolasi
    multi-tenant)."""
    return booking_gateway_db.list_transaksi(
        tenant_id=user["tenant_id"], tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
        status_pembayaran=status_pembayaran, metode_pembayaran=metode_pembayaran,
    )


@router.get("/transactions/{transaksi_id}")
def detail_transaksi_gateway(transaksi_id: int, user: dict = Depends(require_menu_read("riwayat_transaksi"))):
    transaksi = booking_gateway_db.get_transaksi(transaksi_id, tenant_id=user["tenant_id"])
    if transaksi is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")
    transaksi["status_log"] = booking_gateway_db.list_status_log(transaksi_id)
    return transaksi


@router.post("/transactions/{transaksi_id}/cek-ulang")
def cek_ulang_transaksi_gateway(transaksi_id: int, user: dict = Depends(require_permission("izin_riwayat_transaksi"))):
    """AUDIT (Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant --
    perbaikan pasca-audit kesiapan): jalur RESMI untuk transaksi yang macet
    karena webhook TIDAK PERNAH sampai sama sekali (bukan telat/duplikat --
    itu sudah ditangani otomatis). TIDAK PERNAH menerima klaim status dari
    staff -- endpoint ini murni memicu server memanggil ULANG API provider
    (Server Key sendiri) lalu menerapkan hasilnya lewat jalur yang SAMA
    PERSIS dengan webhook resmi (lihat booking_gateway_webhook.py::
    rekonsiliasi_manual()), TERMASUK guard urutan status yang sama."""
    try:
        return booking_gateway_webhook.rekonsiliasi_manual(transaksi_id, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except gateway_client_base.GatewayError as e:
        raise HTTPException(status_code=502, detail=f"Gagal menghubungi Payment Gateway: {e}")


@router.get("/belum-dikonfirmasi")
def jumlah_belum_dikonfirmasi(user: dict = Depends(require_menu_read("booking"))):
    """REVISI: Notifikasi Booking Baru -- di-poll berkala oleh frontend
    (nav.js) untuk badge menu Booking + pemicu notifikasi suara. Ringan
    (SATU angka COUNT(*), bukan daftar booking) supaya aman dipanggil
    tiap beberapa detik tanpa membebani server."""
    return {"jumlah": booking_db.hitung_booking_belum_dikonfirmasi(tenant_id=user["tenant_id"])}


@router.post("/{booking_id}/verifikasi")
def verifikasi_booking(booking_id: int, user: dict = Depends(require_permission("izin_booking_kelola"))):
    booking = booking_db.get_booking(booking_id)
    _pastikan_booking_tenant_sama(user, booking)
    # Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: booking
    # metode "gateway" TIDAK BOLEH diverifikasi manual oleh staff -- status
    # pembayarannya HANYA boleh berubah lewat webhook resmi provider
    # (booking_gateway_webhook.py), SAMA SEKALI TIDAK PERNAH dari klik siapa
    # pun (customer MAUPUN staff) supaya tidak ada celah "tandai lunas"
    # tanpa pembayaran nyata.
    if booking["metode_pembayaran"] == "gateway":
        raise HTTPException(
            status_code=422,
            detail="Booking Payment Gateway tidak bisa diverifikasi manual -- status hanya berubah otomatis begitu pembayaran terkonfirmasi dari provider.",
        )
    try:
        booking_db.verifikasi_pembayaran(booking_id, oleh=user.get("username"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_booking(booking_id)


@router.post("/{booking_id}/terima")
def terima_booking(booking_id: int, user: dict = Depends(require_permission("izin_booking_kelola"))):
    """FITUR Pembayaran Manual QRIS Tenant + Notifikasi WhatsApp: "Verifikasi
    Booking" -- INDEPENDEN dari endpoint verifikasi_booking() di atas
    ("Payment Diterima"), lihat booking_db.terima_booking() untuk penjelasan
    lengkap. Metode "gateway" TIDAK relevan untuk aksi manual ini (checkout
    & pembayaran 100% otomatis lewat Faspay, admin tidak pernah perlu
    "menerima" booking metode ini) -- guard SAMA seperti endpoint di atas."""
    booking = booking_db.get_booking(booking_id)
    _pastikan_booking_tenant_sama(user, booking)
    if booking["metode_pembayaran"] == "gateway":
        raise HTTPException(
            status_code=422,
            detail="Booking Payment Gateway tidak perlu diverifikasi manual -- checkout & pembayaran berjalan otomatis lewat Faspay.",
        )
    try:
        booking_db.terima_booking(booking_id, oleh=user.get("username"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_booking(booking_id)


class RescheduleBody(BaseModel):
    barber_id: int | None = None
    tanggal: str | None = None
    jam_mulai: str | None = None
    service_ids: list[int] | None = None


@router.post("/{booking_id}/reschedule")
def reschedule_booking(booking_id: int, body: RescheduleBody, user: dict = Depends(require_permission("izin_booking_kelola"))):
    """Item #3 spek Booking: admin ubah tanggal/jam/barber/service booking
    yang sudah terverifikasi -- lihat booking_db.reschedule_booking().
    Metode "gateway" ditolak di sini juga (lapis pertama, SAMA seperti
    verifikasi_booking()/terima_booking() di atas) -- payment gateway TIDAK
    BOLEH disentuh."""
    booking = booking_db.get_booking(booking_id)
    _pastikan_booking_tenant_sama(user, booking)
    if booking["metode_pembayaran"] == "gateway":
        raise HTTPException(
            status_code=422,
            detail="Booking Payment Gateway tidak bisa dijadwal ulang -- payment gateway tidak boleh diubah manual.",
        )
    try:
        return booking_db.reschedule_booking(
            booking_id, tenant_id=user["tenant_id"], barber_id=body.barber_id, tanggal=body.tanggal,
            jam_mulai=body.jam_mulai, service_ids=body.service_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{booking_id}/batalkan")
def batalkan_booking(booking_id: int, user: dict = Depends(require_permission("izin_booking_batalkan"))):
    _pastikan_booking_tenant_sama(user, booking_db.get_booking(booking_id))
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
                      user: dict = Depends(require_menu_read("booking"))):
    return booking_db.get_closed_slot_list(barber_id=barber_id, tahun=tahun, bulan=bulan,
                                            tenant_id=user["tenant_id"])


@router.post("/closed-slot")
def tambah_closed_slot(body: ClosedSlotBody, user: dict = Depends(require_permission("izin_booking_kelola"))):
    try:
        new_id = booking_db.tambah_closed_slot(
            body.barber_id, body.tanggal, body.jam_mulai, body.jam_selesai, body.keterangan,
            tenant_id=user["tenant_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": new_id}


@router.delete("/closed-slot/{closed_slot_id}")
def hapus_closed_slot(closed_slot_id: int, user: dict = Depends(require_permission("izin_booking_kelola"))):
    _pastikan_closed_slot_tenant_sama(user, booking_db.get_closed_slot(closed_slot_id))
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
def ambil_booking_settings(user: dict = Depends(require_menu_read("booking"))):
    return booking_db.get_booking_settings(tenant_id=user["tenant_id"])


@router.put("/pengaturan")
def simpan_booking_settings(body: BookingSettingsBody, user: dict = Depends(require_permission("izin_booking_pengaturan"))):
    try:
        booking_db.update_booking_settings(**body.model_dump(), tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_booking_settings(tenant_id=user["tenant_id"])


# FITUR Reset Riwayat Booking (mengantisipasi data menumpuk) -- awalnya pola
# SAMA PERSIS seperti DELETE /api/attendance/riwayat (require_owner_or_staff
# polos, TANPA delegasi permission terpisah). REVISI (Perluasan Hak Akses
# Admin -- diminta Owner, cakupan Booking): aksi ini menghapus SELURUH
# riwayat booking tenant TANPA undo (destruktif & ireversibel, mirip
# batalkan_booking) -- sekarang digerbang izin_booking_batalkan yang sama,
# BUKAN lagi dibiarkan selalu terbuka. Absensi TIDAK ikut diubah (di luar
# cakupan permintaan ini), jadi kedua endpoint yang dulu simetris sekarang
# beda perilaku -- SENGAJA, bukan lupa. `sebelum_tanggal` opsional -- kosong
# = hapus SEMUA booking tenant ini, sama seperti barber_id kosong = "Semua
# Barber" di Absensi.
@router.delete("/riwayat")
def hapus_riwayat(sebelum_tanggal: str = None, user: dict = Depends(require_permission("izin_booking_batalkan"))):
    jumlah = booking_db.hapus_riwayat_booking(tenant_id=user["tenant_id"], sebelum_tanggal=sebelum_tanggal)
    return {"ok": True, "jumlah_dihapus": jumlah}


def _booking_slug_hasil(tenant_id: int) -> dict:
    t = tenant_db.get_tenant(tenant_id)
    return {"booking_slug": t.get("booking_slug") if t else None, "booking_url": tenant_db.get_booking_url(t or {})}


@router.get("/booking-slug")
def ambil_booking_slug(user: dict = Depends(require_menu_read("booking"))):
    """FITUR URL Booking Publik per Tenant: dipakai Setting > Booking
    (kartu "Link Booking" yang SUDAH ADA, TIDAK ada menu baru) untuk
    menampilkan booking_slug TERKINI + URL lengkapnya (subdomain
    <booking_slug>.rivoirsett.com/book, lihat tenant_db.py::
    get_booking_url())."""
    return _booking_slug_hasil(user["tenant_id"])


class BookingSlugBody(BaseModel):
    booking_slug: str


@router.put("/booking-slug")
def ubah_booking_slug(body: BookingSlugBody, user: dict = Depends(require_permission("izin_booking_pengaturan"))):
    """FITUR URL Booking Publik per Tenant (item 7 spesifikasi): validasi
    format + keunikan ditegakkan DI tenant_db.py::set_booking_slug()
    (pool gabungan slug+booking_slug SELURUH tenant) -- pesan error di
    sini SELALU string polos di `detail` (pola sama seperti endpoint lain
    di aplikasi ini) supaya frontend bisa langsung menampilkannya sebagai
    "slug tidak tersedia" tanpa pemetaan tambahan."""
    try:
        tenant_db.set_booking_slug(user["tenant_id"], body.booking_slug)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _booking_slug_hasil(user["tenant_id"])


class PaymentSettingsBody(BaseModel):
    metode_aktif: list[str] | None = None
    qris_merchant_nama: str | None = None
    bank_nama: str | None = None
    bank_nomor_rekening: str | None = None
    bank_nama_pemilik: str | None = None
    metode_nama: dict[str, str] | None = None
    metode_instruksi: dict[str, str] | None = None


@router.get("/payment-settings")
def ambil_payment_settings(user: dict = Depends(require_menu_read("booking"))):
    return booking_db.get_payment_settings(tenant_id=user["tenant_id"])


@router.put("/payment-settings")
def simpan_payment_settings(body: PaymentSettingsBody, user: dict = Depends(require_permission("izin_booking_pengaturan"))):
    try:
        booking_db.update_payment_settings(**body.model_dump(), tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return booking_db.get_payment_settings(tenant_id=user["tenant_id"])


@router.post("/qris")
async def upload_qris(file: UploadFile = File(...), user: dict = Depends(require_permission("izin_booking_pengaturan"))):
    konten = await file.read()
    try:
        booking_db.simpan_qris(file.filename, konten, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return booking_db.get_payment_settings(tenant_id=user["tenant_id"])


@router.delete("/qris")
def hapus_qris_endpoint(user: dict = Depends(require_permission("izin_booking_pengaturan"))):
    booking_db.hapus_qris(tenant_id=user["tenant_id"])
    return booking_db.get_payment_settings(tenant_id=user["tenant_id"])


# ---- TOKO LIBUR (hari libur SELURUH toko, beda dari Barber Holiday) ----

class TokoLiburBody(BaseModel):
    tanggal: str
    keterangan: str | None = None


@router.get("/toko-libur")
def list_toko_libur(tahun: int = None, bulan: int = None, user: dict = Depends(require_menu_read("booking"))):
    return booking_db.get_toko_libur_list(tahun=tahun, bulan=bulan, tenant_id=user["tenant_id"])


@router.post("/toko-libur")
def tambah_toko_libur(body: TokoLiburBody, user: dict = Depends(require_permission("izin_booking_kelola"))):
    try:
        new_id = booking_db.tambah_toko_libur(body.tanggal, body.keterangan, tenant_id=user["tenant_id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": new_id}


@router.delete("/toko-libur/{toko_libur_id}")
def hapus_toko_libur(toko_libur_id: int, user: dict = Depends(require_permission("izin_booking_kelola"))):
    _pastikan_toko_libur_tenant_sama(user, booking_db.get_toko_libur(toko_libur_id))
    booking_db.hapus_toko_libur(toko_libur_id)
    return {"ok": True}


# ---- BARBER: status booking, foto, urutan (field TAMBAHAN modul Booking;
# nama/harga/aktif/dst tetap lewat /api/pengaturan/barber yang sudah ada) ----

class BarberStatusBody(BaseModel):
    status_booking: str


class BarberUrutanBody(BaseModel):
    urutan: int


def _barber_publik(barber_id: int):
    """db.get_barber() lewat SELECT * -- ikut membawa kolom biner
    (foto_data BLOB, sejak Tahap 16) yang TIDAK bisa di-serialize jadi JSON
    (bug laten yang ditemukan saat audit migrasi R2 ini: endpoint di bawah
    akan crash 500 begitu barber yang disasar punya foto tersimpan -- murni
    bug pre-existing, tidak terkait R2, tapi jadi kelihatan sekarang karena
    baru diuji end-to-end dengan foto sungguhan). Field biner/internal
    dibuang di sini SEBELUM dikembalikan ke client -- frontend sudah selalu
    memakai `foto_url` (dari /api/public/booking/barbers), tidak pernah
    membaca foto_data/foto_r2_key langsung dari respons endpoint ini."""
    barber = db.get_barber(barber_id)
    if barber:
        barber.pop("foto_data", None)
        barber.pop("foto_r2_key", None)
    return barber


def _pastikan_barber_tenant_sama(user: dict, barber_id: int):
    """FONDASI Multi-Tenant Phase 1: fetch-then-authorize -- SEBELUMNYA
    keempat endpoint di bawah ini menerima barber_id APA ADANYA tanpa
    verifikasi kepemilikan sama sekali, artinya Owner Tenant A bisa
    mengubah status/urutan/foto barber milik Tenant B hanya dengan menebak
    ID-nya. 404 dipakai supaya tidak membocorkan bahwa barber_id itu
    sebenarnya ada, milik tenant lain."""
    barber = db.get_barber(barber_id)
    if barber is None or barber.get("tenant_id") != user.get("tenant_id"):
        raise HTTPException(status_code=404, detail="Barber tidak ditemukan.")


@router.put("/barber/{barber_id}/status")
def ubah_status_barber(barber_id: int, body: BarberStatusBody, user: dict = Depends(require_permission("izin_booking_kelola"))):
    _pastikan_barber_tenant_sama(user, barber_id)
    try:
        booking_db.set_status_booking_barber(barber_id, body.status_booking)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _barber_publik(barber_id)


@router.put("/barber/{barber_id}/urutan")
def ubah_urutan_barber(barber_id: int, body: BarberUrutanBody, user: dict = Depends(require_permission("izin_booking_kelola"))):
    _pastikan_barber_tenant_sama(user, barber_id)
    try:
        booking_db.set_urutan_barber(barber_id, body.urutan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _barber_publik(barber_id)


@router.post("/barber/{barber_id}/foto")
async def upload_foto_barber(barber_id: int, file: UploadFile = File(...), user: dict = Depends(require_permission("izin_booking_kelola"))):
    _pastikan_barber_tenant_sama(user, barber_id)
    konten = await file.read()
    try:
        booking_db.simpan_foto_barber(barber_id, file.filename, konten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except r2_storage.R2Error as e:
        raise HTTPException(status_code=502, detail=str(e))
    return _barber_publik(barber_id)


@router.delete("/barber/{barber_id}/foto")
def hapus_foto_barber_endpoint(barber_id: int, user: dict = Depends(require_permission("izin_booking_kelola"))):
    _pastikan_barber_tenant_sama(user, barber_id)
    try:
        booking_db.hapus_foto_barber(barber_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _barber_publik(barber_id)


# ---- SERVICE: urutan (field TAMBAHAN modul Booking; nama/harga/durasi/dst
# tetap lewat /api/pengaturan/service yang sudah ada) ----

class ServiceUrutanBody(BaseModel):
    urutan: int


@router.put("/service/{service_id}/urutan")
def ubah_urutan_service(service_id: int, body: ServiceUrutanBody, user: dict = Depends(require_permission("izin_booking_kelola"))):
    service = db.get_service(service_id)
    if service is None or service.get("tenant_id") != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Layanan tidak ditemukan.")
    try:
        booking_db.set_urutan_service(service_id, body.urutan)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_service(service_id)


# =====================================================================
# BARBER -- hanya booking miliknya sendiri
# =====================================================================


@router.get("/mine")
def booking_saya(tahun: int = None, bulan: int = None, tanggal: str = None, dari_tanggal: str = None,
                  user: dict = Depends(require_barber)):
    # FITUR Booking "Hari Ini"/"Akan Datang" (tampilan kartu operasional,
    # lihat pages/booking.js): `tanggal` (persis satu hari) & `dari_tanggal`
    # (>= satu tanggal, tanpa batas atas) TIDAK mengubah perilaku lama sama
    # sekali kalau tidak dikirim (default None) -- tab "Semua Booking" tetap
    # memakai tahun/bulan seperti sebelumnya.
    barber_id = user.get("barber_id")
    if barber_id is None:
        raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber. Hubungi Owner.")
    return booking_db.get_booking_list(barber_id=barber_id, tahun=tahun, bulan=bulan, tanggal=tanggal,
                                        dari_tanggal=dari_tanggal, tenant_id=user["tenant_id"])
