"""
laporan_pdf.py — Download Laporan PDF (Menu Backup, Owner + Admin dengan izin)
=============================================================================
Tiga jenis laporan (sesuai spesifikasi): Transaksi, Pengeluaran, Rekap
Bulanan Barber. Format WAJIB tiap laporan (semuanya lewat _header_footer()
di bawah, dipanggil otomatis reportlab di SETIAP halaman): Nama Barbershop,
Logo (kalau tersedia), Judul Laporan, Periode, Tanggal Cetak, Nomor
Halaman, Nama pengguna yang mencetak.

Data diambil APA ADANYA lewat fungsi baca yang sudah ada (database.py/
pengeluaran_db.py) -- file ini murni menyusun tata letak PDF, TIDAK
menghitung ulang satu angka pun sendiri.
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

import database as db
import pengeluaran_db
import pengaturan_identitas

_NAMA_BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
               "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

JENIS_VALID = {"transaksi", "pengeluaran", "rekap_bulanan"}


def _rupiah(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def _periode_text(tahun: int, bulan: int | None) -> str:
    return f"{_NAMA_BULAN[bulan]} {tahun}" if bulan else f"Tahun {tahun}"


def _judul(jenis: str) -> str:
    return {
        "transaksi": "Laporan Transaksi",
        "pengeluaran": "Laporan Pengeluaran",
        "rekap_bulanan": "Rekap Bulanan Barber",
    }[jenis]


def _header_footer_factory(judul: str, periode: str, dicetak_oleh: str):
    identitas = pengaturan_identitas.get_identitas()
    nama_barbershop = identitas.get("nama_barbershop") or "MUGEN Hair Co."
    logo_path, _ = pengaturan_identitas.get_logo_file_path()
    tanggal_cetak = datetime.now().strftime("%d/%m/%Y %H:%M")

    def _on_page(canvas, doc):
        canvas.saveState()
        width, height = A4
        y = height - 15 * mm

        if logo_path:
            try:
                canvas.drawImage(logo_path, 15 * mm, y - 10 * mm, width=14 * mm, height=14 * mm,
                                  preserveAspectRatio=True, mask="auto")
            except Exception:
                pass  # logo korup/format tidak didukung reportlab -- laporan tetap dicetak tanpa logo

        text_x = 32 * mm if logo_path else 15 * mm
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(text_x, y - 2 * mm, nama_barbershop)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(text_x, y - 8 * mm, judul)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(text_x, y - 13 * mm, f"Periode: {periode}")

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(width - 15 * mm, height - 10 * mm, f"Dicetak: {tanggal_cetak}")
        canvas.drawRightString(width - 15 * mm, height - 15 * mm, f"Oleh: {dicetak_oleh}")

        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(width / 2, 10 * mm, f"Halaman {doc.page}")
        canvas.setFillColor(colors.black)
        canvas.restoreState()

    return _on_page


def _bangun_pdf(judul: str, periode: str, dicetak_oleh: str, header_kolom: list, baris: list) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=32 * mm, bottomMargin=18 * mm, leftMargin=15 * mm, rightMargin=15 * mm,
        title=judul,
    )
    styles = getSampleStyleSheet()
    elemen = [Spacer(1, 2 * mm)]

    if not baris:
        elemen.append(Paragraph("Tidak ada data pada periode ini.", styles["Normal"]))
    else:
        data_tabel = [header_kolom] + baris
        tabel = Table(data_tabel, repeatRows=1)
        tabel.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elemen.append(tabel)

    on_page = _header_footer_factory(judul, periode, dicetak_oleh)
    doc.build(elemen, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def _laporan_transaksi(tahun: int, bulan: int | None, barber_id: int | None, dicetak_oleh: str):
    data = db.get_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id)
    header = ["Tanggal", "Barber", "Service", "Harga", "Komisi", "Tips"]
    baris = [[t["tanggal"], t["nama_barber"], t["daftar_service"],
              _rupiah(t["total_harga"]), _rupiah(t["total_komisi"]), _rupiah(t["tips"])] for t in data]
    return header, baris


def _laporan_pengeluaran(tahun: int, bulan: int | None, dicetak_oleh: str):
    data = pengeluaran_db.get_pengeluaran_list(tahun=tahun, bulan=bulan)
    header = ["Tanggal", "Kategori", "Keterangan", "Barber", "Jumlah"]
    baris = [[p["tanggal"], p.get("kategori") or "-", p["keterangan"], p.get("nama_barber") or "-",
              _rupiah(p["jumlah"])] for p in data]
    return header, baris


def _laporan_rekap_bulanan(tahun: int, bulan: int, barber_id: int | None, dicetak_oleh: str):
    data = db.get_rekap_bulanan_list(tahun, bulan, barber_id=barber_id)
    header = ["Barber", "Jumlah Service", "Komisi", "Tips", "Uang Harian", "Bonus Customer", "Total Pendapatan"]
    baris = [[r["nama_barber"], str(r["jumlah_service"]), _rupiah(r["total_komisi"]), _rupiah(r["tips"]),
              _rupiah(r["uang_harian"]), _rupiah(r["bonus_customer"]), _rupiah(r["total_pendapatan"])]
             for r in data]
    return header, baris


def buat_laporan(jenis: str, tahun: int, bulan: int | None, barber_id: int | None, dicetak_oleh: str):
    """Return (bytes_pdf, nama_file). Raise ValueError kalau jenis tidak dikenal
    atau parameter wajib (bulan untuk rekap_bulanan) tidak diisi."""
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis laporan tidak dikenal: {jenis}")
    if not tahun:
        raise ValueError("Tahun wajib diisi.")

    if jenis == "transaksi":
        header, baris = _laporan_transaksi(tahun, bulan, barber_id, dicetak_oleh)
    elif jenis == "pengeluaran":
        header, baris = _laporan_pengeluaran(tahun, bulan, dicetak_oleh)
    else:
        if not bulan:
            raise ValueError("Bulan wajib diisi untuk Rekap Bulanan Barber.")
        header, baris = _laporan_rekap_bulanan(tahun, bulan, barber_id, dicetak_oleh)

    judul = _judul(jenis)
    periode = _periode_text(tahun, bulan)
    konten = _bangun_pdf(judul, periode, dicetak_oleh, header, baris)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"laporan_{jenis}_{stamp}.pdf"
    return konten, filename
