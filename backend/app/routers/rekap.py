"""routers/rekap.py — /api/rekap/*
- Rekap Transaksi & Rekap Bulanan: Owner ('admin') dan Admin ('staff', akses
  PENUH sama persis seperti Owner -- lihat REVISI Hak Akses Admin, menu ini
  tidak memakai sistem izin sama sekali) bisa lihat semua barber (atau
  filter satu barber), Barber otomatis dibatasi ke data miliknya sendiri saja.
- Rekap Pengeluaran: data operasional TOKO (bukan milik barber manapun),
  jadi khusus Owner/Admin (bukan Barber). TAHAP 9: diarahkan ke
  pengeluaran_db (sumber yang sama dipakai CRUD Pengeluaran) supaya rekap
  ini otomatis ikut kategori & nama barber, bukan lagi hanya baca kolom
  dasar dari database.py."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response

import database as db
import pengeluaran_db
import reimburse_db
import laporan_pdf
from auth import get_current_user, require_owner_or_staff

router = APIRouter(prefix="/api/rekap", tags=["rekap"])


def _pdf_response(konten: bytes, prefix: str) -> Response:
    filename = laporan_pdf.buat_nama_file(prefix)
    return Response(content=konten, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/transaksi")
def rekap_transaksi(tahun: int = None, bulan: int = None, barber_id: int = None,
                     tanggal: str = None, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    data = db.get_rekap_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id, tanggal=tanggal)
    # Tahap 14: baris Reimburse yang sudah DISETUJUI ikut digabung di sini
    # (bukan di database.py, circular import) -- tanggal barisnya tanggal
    # DISETUJUI, bukan tanggal klaim diajukan.
    data = reimburse_db.gabung_ke_rekap_transaksi(data, tahun=tahun, bulan=bulan, barber_id=barber_id)
    return data


@router.get("/transaksi/pdf")
def rekap_transaksi_pdf(tahun: int = None, bulan: int = None, barber_id: int = None,
                         tanggal_mulai: str = None, tanggal_selesai: str = None,
                         user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    konten = laporan_pdf.buat_pdf_rekap_transaksi(tahun, bulan, barber_id, user["username"],
                                                   tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
    return _pdf_response(konten, "rekap_transaksi")


@router.get("/bulanan")
def rekap_bulanan(tahun: int, bulan: int, barber_id: int = None, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    data = db.get_rekap_bulanan_list(tahun=tahun, bulan=bulan, barber_id=barber_id)
    # Tahap 12: kolom Reimburse -- dihitung di sini (bukan di database.py,
    # yang tidak boleh impor reimburse_db karena circular import).
    for r in data:
        r["reimburse"] = reimburse_db.get_saldo_periode(r["barber_id"], tahun, bulan)
    return data


@router.get("/bulanan/pdf")
def rekap_bulanan_pdf(tahun: int, bulan: int, barber_id: int = None, user: dict = Depends(get_current_user)):
    if user["role"] == "barber":
        barber_id = user.get("barber_id")
    konten = laporan_pdf.buat_pdf_rekap_bulanan(tahun, bulan, barber_id, user["username"])
    return _pdf_response(konten, "rekap_bulanan")


@router.get("/pengeluaran")
def rekap_pengeluaran(tahun: int = None, bulan: int = None, user: dict = Depends(require_owner_or_staff)):
    daftar = pengeluaran_db.get_pengeluaran_list(tahun=tahun, bulan=bulan)
    total = sum(p["jumlah"] for p in daftar)
    return {"daftar": daftar, "total": total}


@router.get("/pengeluaran/pdf")
def rekap_pengeluaran_pdf(tahun: int = None, bulan: int = None, user: dict = Depends(require_owner_or_staff)):
    konten = laporan_pdf.buat_pdf_rekap_pengeluaran(tahun, bulan, user["username"])
    return _pdf_response(konten, "rekap_pengeluaran")
