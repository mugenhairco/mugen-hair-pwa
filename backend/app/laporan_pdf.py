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
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

import database as db
import pengeluaran_db
import pengaturan_identitas

_NAMA_BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
               "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

JENIS_VALID = {"transaksi", "pengeluaran", "rekap_bulanan"}

# Dipakai HANYA untuk kolom Laporan Transaksi yang bisa berisi teks panjang
# (Ket, gabungan beberapa catatan) -- sel string biasa di reportlab Table
# TIDAK auto-wrap (bisa meluber ke luar lebar kolom/halaman), jadi dibungkus
# Paragraph supaya ikut membungkus baris. Header tabel TETAP string biasa
# (judul kolom selalu pendek, dan supaya style bold+putih dari TableStyle di
# _bangun_pdf() tetap berlaku apa adanya -- TableStyle tidak bisa menimpa
# style internal sebuah Paragraph).
_SEL_STYLE = ParagraphStyle("sel-laporan", fontName="Helvetica", fontSize=8, leading=10)

# Baris ringkasan di BAWAH tabel (Laporan Transaksi: Total Semua Pendapatan +
# Total Jumlah per Service) -- font sedikit lebih besar dari sel tabel (9pt)
# supaya terlihat sebagai ringkasan, bukan bagian dari tabel. Boleh berisi
# tag <b> (Paragraph reportlab mendukung mini-HTML dasar) untuk baris yang
# perlu ditebalkan.
_RINGKASAN_STYLE = ParagraphStyle("ringkasan-laporan", fontName="Helvetica", fontSize=9, leading=13)


def _sel(nilai) -> Paragraph:
    return Paragraph(str(nilai), _SEL_STYLE)


def _rupiah(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def _periode_text(tahun: int, bulan: int | None) -> str:
    return f"{_NAMA_BULAN[bulan]} {tahun}" if bulan else f"Tahun {tahun}"


def _tgl(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%d")


def _tgl_pendek(iso: str) -> str:
    """Format 'DD/MM' -- dipakai sebagai label tanggal di kolom Ket (Laporan
    Transaksi), yang isinya sudah dirangkum per barber untuk SELURUH periode
    (bukan per hari lagi), supaya setiap catatan tetap jelas tanggalnya."""
    d = _tgl(iso)
    return f"{d.day}/{d.month}"


def _periode_text_rentang(tanggal_mulai: str, tanggal_selesai: str) -> str:
    """Rentang tanggal bebas (Laporan Transaksi/Pengeluaran) -- BEDA dari
    _periode_text() di atas yang khusus Rekap Bulanan (selalu satu bulan/
    tahun penuh). Nama bulan/tahun tidak diulang kalau sama di kedua ujung,
    contoh: '3 - 25 Juli 2026' atau '20 Juni - 5 Juli 2026'."""
    d1, d2 = _tgl(tanggal_mulai), _tgl(tanggal_selesai)
    if d1.year == d2.year and d1.month == d2.month:
        if d1.day == d2.day:
            return f"{d1.day} {_NAMA_BULAN[d1.month]} {d1.year}"
        return f"{d1.day} - {d2.day} {_NAMA_BULAN[d2.month]} {d2.year}"
    if d1.year == d2.year:
        return f"{d1.day} {_NAMA_BULAN[d1.month]} - {d2.day} {_NAMA_BULAN[d2.month]} {d2.year}"
    return f"{d1.day} {_NAMA_BULAN[d1.month]} {d1.year} - {d2.day} {_NAMA_BULAN[d2.month]} {d2.year}"


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


def _bangun_pdf(judul: str, periode: str, dicetak_oleh: str, header_kolom: list, baris: list,
                 col_widths: list | None = None, ringkasan_tambahan: list | None = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        # Margin kiri-kanan dibuat SEKECIL MUNGKIN (bukan atas-bawah, yang
        # tetap dipakai untuk area header/nomor halaman) supaya tabel
        # tampil "full" selebar mungkin -- 8mm masih menyisakan sedikit
        # ruang aman cetak (kebanyakan printer tidak bisa benar-benar cetak
        # sampai tepi kertas 0mm).
        topMargin=32 * mm, bottomMargin=18 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
        title=judul,
    )
    styles = getSampleStyleSheet()
    elemen = [Spacer(1, 2 * mm)]

    if not baris:
        elemen.append(Paragraph("Tidak ada data pada periode ini.", styles["Normal"]))
    else:
        data_tabel = [header_kolom] + baris
        tabel = Table(data_tabel, colWidths=col_widths, repeatRows=1)
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

        if ringkasan_tambahan:
            elemen.append(Spacer(1, 4 * mm))
            for baris_ringkasan in ringkasan_tambahan:
                elemen.append(Paragraph(baris_ringkasan, _RINGKASAN_STYLE))

    on_page = _header_footer_factory(judul, periode, dicetak_oleh)
    doc.build(elemen, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# Lebar kolom Laporan Transaksi (mm), total 194mm = lebar A4 dikurangi
# margin kiri+kanan 8mm masing-masing (lihat _bangun_pdf topMargin/dst) --
# kelebihan lebar dari revisi "tabel full" dialokasikan ke kolom Ket (yang
# isinya paling mungkin panjang), kolom lain tetap sama seperti sebelumnya.
_LEBAR_KOLOM_TRANSAKSI = [26 * mm, 22 * mm, 24 * mm, 22 * mm, 13 * mm, 24 * mm, 63 * mm]


def _laporan_transaksi(tanggal_mulai: str, tanggal_selesai: str, barber_id: int | None,
                        dicetak_oleh: str, periode: str):
    """Laporan Transaksi = REKAP per barber untuk seluruh rentang tanggal
    (BUKAN daftar per kunjungan customer lagi) -- kolom Libur (hari) & Ket
    (gabungan catatan manual dari Input Data, masing-masing berlabel
    tanggal) ditambahkan supaya satu baris per barber tetap informatif walau
    sudah dirangkum. Kolom Tanggal berisi teks periode yang SAMA di setiap
    baris (rentang yang dipilih), bukan tanggal per baris seperti dulu.

    Return (header, baris, ringkasan_tambahan) -- 3-tuple KHUSUS jenis ini
    (beda dari _laporan_pengeluaran/_laporan_rekap_bulanan yang tetap
    2-tuple) karena ada baris ringkasan di bawah tabel: Total Semua
    Pendapatan (jumlah kolom Total seluruh baris di atas) dan Total Jumlah
    per Service (lintas barber yang tampil, hormat filter barber_id yang
    sama dengan tabelnya)."""
    data = db.get_laporan_transaksi_rekap(tanggal_mulai, tanggal_selesai, barber_id=barber_id)
    header = ["Tanggal", "Barber", "Uang Harian", "Komisi", "Libur", "Total", "Ket"]
    baris = []
    for r in data:
        keterangan = "; ".join(f"{_tgl_pendek(c['tanggal'])}: {c['catatan']}" for c in r["catatan_list"])
        baris.append([
            _sel(periode), _sel(r["nama_barber"]), _sel(_rupiah(r["uang_harian"])),
            _sel(_rupiah(r["komisi"])), _sel(str(r["hari_libur"])), _sel(_rupiah(r["total"])),
            _sel(keterangan),
        ])

    total_pendapatan = sum(r["total"] for r in data)
    rincian_service = db.get_rincian_service_rentang(tanggal_mulai, tanggal_selesai, barber_id=barber_id)
    ringkasan_tambahan = [f"<b>Total Semua Pendapatan: {_rupiah(total_pendapatan)}</b>"]
    if rincian_service:
        ringkasan_tambahan.append("<b>Total Jumlah per Service:</b>")
        ringkasan_tambahan.append(", ".join(f"{s['nama_service']}: {s['jumlah']}" for s in rincian_service))

    return header, baris, ringkasan_tambahan


def _laporan_pengeluaran(tanggal_mulai: str, tanggal_selesai: str, dicetak_oleh: str):
    data = pengeluaran_db.get_pengeluaran_list(tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
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


def buat_laporan(jenis: str, barber_id: int | None, dicetak_oleh: str,
                  tanggal_mulai: str | None = None, tanggal_selesai: str | None = None,
                  tahun: int | None = None, bulan: int | None = None):
    """Return (bytes_pdf, nama_file). Raise ValueError kalau jenis tidak dikenal
    atau parameter wajib tidak diisi.

    Rekap Bulanan Barber TETAP dipilih lewat Tahun+Bulan (wajib satu bulan
    penuh -- perhitungan komisi/bonus/uang harian bertumpu pada batas bulan
    kalender, lihat database.py get_ringkasan_barber_bulan(), BUKAN sesuatu
    yang bisa dipotong ke rentang tanggal bebas tanpa mengubah logika hitung
    itu sendiri). Laporan Transaksi & Pengeluaran dipilih lewat rentang
    tanggal bebas (tanggal_mulai/tanggal_selesai) supaya Periode di PDF
    menunjukkan rentang tanggal sebenarnya, bukan cuma Bulan/Tahun."""
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis laporan tidak dikenal: {jenis}")

    col_widths = None
    ringkasan_tambahan = None
    if jenis == "rekap_bulanan":
        if not tahun or not bulan:
            raise ValueError("Tahun dan Bulan wajib diisi untuk Rekap Bulanan Barber.")
        header, baris = _laporan_rekap_bulanan(tahun, bulan, barber_id, dicetak_oleh)
        periode = _periode_text(tahun, bulan)
    else:
        if not tanggal_mulai or not tanggal_selesai:
            raise ValueError("Tanggal Dari dan Tanggal Sampai wajib diisi.")
        if tanggal_mulai > tanggal_selesai:
            raise ValueError("Tanggal Dari tidak boleh setelah Tanggal Sampai.")
        periode = _periode_text_rentang(tanggal_mulai, tanggal_selesai)
        if jenis == "transaksi":
            header, baris, ringkasan_tambahan = _laporan_transaksi(
                tanggal_mulai, tanggal_selesai, barber_id, dicetak_oleh, periode,
            )
            col_widths = _LEBAR_KOLOM_TRANSAKSI
        else:
            header, baris = _laporan_pengeluaran(tanggal_mulai, tanggal_selesai, dicetak_oleh)

    judul = _judul(jenis)
    konten = _bangun_pdf(judul, periode, dicetak_oleh, header, baris, col_widths, ringkasan_tambahan)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"laporan_{jenis}_{stamp}.pdf"
    return konten, filename
