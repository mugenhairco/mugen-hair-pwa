"""routers/input_data.py — /api/input-data/*
Dipakai halaman Input Data. REVISI: seluruh endpoint di sini sekarang
KHUSUS Owner ('admin') dan Admin ('staff', akses PENUH sama persis seperti
Owner -- lihat REVISI Hak Akses Admin, menu ini tidak memakai sistem izin
sama sekali) -- Barber TIDAK LAGI punya akses ke Input Data sama sekali
(hak akses Barber sekarang hanya Dashboard + Rekap). Sebelumnya Barber
boleh input/koreksi/hapus transaksi miliknya sendiri; logika
`_resolve_barber_id`/`_pastikan_pemilik` di bawah masih punya cabang untuk
role 'barber' (kode itu sengaja TIDAK dihapus supaya diff seminimal
mungkin) tapi sudah tidak pernah tereksekusi lagi karena
`require_owner_or_staff` menolak permintaan barber sebelum mencapai kode
itu."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

import database as db
from auth import require_owner_or_staff

router = APIRouter(prefix="/api/input-data", tags=["input-data"])


class ItemBody(BaseModel):
    service_id: int
    jumlah: int


class TransaksiBody(BaseModel):
    tanggal: str
    barber_id: int | None = None  # diabaikan untuk role barber, wajib untuk role admin
    items: list[ItemBody]
    tips: int = 0
    catatan: str | None = None


class KoreksiBody(BaseModel):
    tanggal: str | None = None
    barber_id: int | None = None
    items: list[ItemBody] | None = None
    tips: int | None = None
    catatan: str | None = None


class PreviewBody(BaseModel):
    items: list[ItemBody]


class LiburBody(BaseModel):
    barber_id: int | None = None
    tanggal: str


def _resolve_barber_id(user: dict, barber_id_diminta: int | None) -> int:
    """Owner boleh pilih barber_id bebas (wajib diisi). Barber dipaksa ke
    barber_id akunnya sendiri, apapun yang dikirim dari frontend."""
    if user["role"] == "barber":
        if user.get("barber_id") is None:
            raise HTTPException(status_code=400, detail="Akun ini belum dikaitkan ke data Barber.")
        return user["barber_id"]
    # role admin
    if barber_id_diminta is None:
        raise HTTPException(status_code=422, detail="barber_id wajib diisi.")
    return barber_id_diminta


def _pastikan_pemilik(user: dict, transaksi_id: int) -> dict:
    """Untuk role barber: pastikan transaksi yang mau dikoreksi/dihapus benar
    memang miliknya sendiri, bukan milik barber lain."""
    transaksi = db.get_transaksi(transaksi_id)
    if transaksi is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")
    if user["role"] == "barber" and transaksi["barber_id"] != user.get("barber_id"):
        raise HTTPException(status_code=403, detail="Bukan transaksi milik Anda.")
    return transaksi


@router.get("/services")
def services(user: dict = Depends(require_owner_or_staff)):
    return db.get_services()


@router.get("/barbers")
def barbers(user: dict = Depends(require_owner_or_staff)):
    """Untuk dropdown pilih barber di form Input Data (Owner). Barber tidak
    butuh ini (barber_id-nya sudah otomatis dari akun), tapi tidak dilarang
    memanggilnya juga (hanya daftar nama, bukan data sensitif). HANYA
    jabatan='barber' (lihat database.py::get_barbers()) -- Input Data
    murni transaksi jasa potong rambut, Kasir/OB/Kru tidak relevan di sini."""
    return db.get_barbers()


@router.get("/karyawan")
def karyawan(user: dict = Depends(require_owner_or_staff)):
    """Untuk dropdown yang harus menampilkan SEMUA karyawan (Barber +
    Kasir/OB/Kru) -- Slip Gaji, Kasbon, Reimburse, Izin & Cuti, filter
    Rekap Transaksi. BEDA dari /barbers di atas yang khusus jabatan='barber'."""
    return db.get_karyawan()


@router.post("/preview")
def preview(body: PreviewBody, user: dict = Depends(require_owner_or_staff)):
    return db.hitung_preview_items([it.model_dump() for it in body.items])


@router.get("/transaksi")
def list_transaksi(tahun: int = None, bulan: int = None, tanggal: str = None,
                    user: dict = Depends(require_owner_or_staff)):
    barber_id = user.get("barber_id") if user["role"] == "barber" else None
    return db.get_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id, tanggal=tanggal)


@router.post("/transaksi")
def tambah_transaksi(body: TransaksiBody, user: dict = Depends(require_owner_or_staff)):
    barber_id = _resolve_barber_id(user, body.barber_id)
    try:
        transaksi_id = db.tambah_transaksi(
            tanggal=body.tanggal, barber_id=barber_id,
            items=[it.model_dump() for it in body.items],
            tips=body.tips, catatan=body.catatan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_transaksi(transaksi_id)


@router.put("/transaksi/{transaksi_id}")
def koreksi_transaksi(transaksi_id: int, body: KoreksiBody, user: dict = Depends(require_owner_or_staff)):
    _pastikan_pemilik(user, transaksi_id)
    barber_id = body.barber_id
    if user["role"] == "barber":
        barber_id = None  # barber tidak boleh memindahkan transaksinya ke barber lain
    try:
        db.koreksi_transaksi(
            transaksi_id, tanggal=body.tanggal, barber_id=barber_id,
            items=[it.model_dump() for it in body.items] if body.items is not None else None,
            tips=body.tips, catatan=body.catatan,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return db.get_transaksi(transaksi_id)


@router.delete("/transaksi/{transaksi_id}")
def hapus_transaksi(transaksi_id: int, user: dict = Depends(require_owner_or_staff)):
    _pastikan_pemilik(user, transaksi_id)
    db.hapus_transaksi(transaksi_id)
    return {"ok": True}


@router.get("/libur")
def list_libur(tahun: int = None, bulan: int = None, user: dict = Depends(require_owner_or_staff)):
    barber_id = user.get("barber_id") if user["role"] == "barber" else None
    return db.get_libur_list(barber_id=barber_id, tahun=tahun, bulan=bulan)


@router.post("/libur")
def tandai_libur(body: LiburBody, user: dict = Depends(require_owner_or_staff)):
    barber_id = _resolve_barber_id(user, body.barber_id)
    db.tandai_libur(barber_id, body.tanggal)
    return {"ok": True}


@router.delete("/libur")
def batalkan_libur(body: LiburBody, user: dict = Depends(require_owner_or_staff)):
    barber_id = _resolve_barber_id(user, body.barber_id)
    db.batalkan_libur(barber_id, body.tanggal)
    return {"ok": True}
