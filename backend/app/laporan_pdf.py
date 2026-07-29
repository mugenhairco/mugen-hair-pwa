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
import kasbon_db
import pemasukan_db
import komisi_penyesuaian_db
import reimburse_db
import slip_gaji_db
import izin_cuti_db
import uang_kas_db

_NAMA_BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
               "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

JENIS_VALID = {"transaksi", "pengeluaran", "rekap_bulanan", "kasbon", "pemasukan", "komisi", "reimburse"}
# Jenis yang dipilih lewat Tahun+Bulan (satu bulan kalender penuh), BUKAN
# rentang tanggal bebas -- Rekap Bulanan (perhitungan komisi/bonus/uang
# harian bertumpu pada batas bulan kalender) dan Komisi (baris
# komisi_penyesuaian tidak punya kolom tanggal harian, terikat tahun+bulan
# saja, lihat komisi_penyesuaian_db.py). Semua jenis LAIN pakai rentang
# tanggal bebas (tanggal_mulai/tanggal_selesai) -- lihat buat_laporan().
JENIS_TAHUN_BULAN = {"rekap_bulanan", "komisi"}

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


def _periode_text_opsional(tahun: int | None, bulan: int | None) -> str:
    """Sama seperti _periode_text(), tapi untuk laporan cetak-langsung-dari-
    menu yang tahun/bulan-nya OPSIONAL (mengikuti filter halaman aslinya,
    yang beberapa punya opsi "Semua Bulan"/"Semua Tahun") -- BEDA dari
    _periode_text() yang mengasumsikan tahun+bulan selalu terisi."""
    if tahun and bulan:
        return _periode_text(tahun, bulan)
    if tahun:
        return f"Tahun {tahun}"
    return "Semua Periode"


def _judul(jenis: str) -> str:
    return {
        "transaksi": "Laporan Transaksi",
        "pengeluaran": "Laporan Pengeluaran",
        "rekap_bulanan": "Rekap Bulanan Barber",
        "kasbon": "Laporan Kasbon",
        "pemasukan": "Laporan Pemasukan",
        "komisi": "Laporan Komisi",
        "reimburse": "Laporan Reimburse",
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


def _gaya_tabel() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])


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
        tabel.setStyle(_gaya_tabel())
        elemen.append(tabel)

        if ringkasan_tambahan:
            elemen.append(Spacer(1, 4 * mm))
            for baris_ringkasan in ringkasan_tambahan:
                elemen.append(Paragraph(baris_ringkasan, _RINGKASAN_STYLE))

    on_page = _header_footer_factory(judul, periode, dicetak_oleh)
    doc.build(elemen, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# Judul sub-bagian dalam PDF multi-tabel (lihat _bangun_pdf_sections()) --
# HANYA dipakai halaman Komisi yang punya dua tabel (Riwayat Komisi Dasar +
# Daftar Penyesuaian) dalam satu PDF, supaya keduanya jelas beda bagian.
_SUBJUDUL_STYLE = ParagraphStyle("subjudul-laporan", fontName="Helvetica-Bold", fontSize=10, leading=13)


def _bangun_pdf_sections(judul: str, periode: str, dicetak_oleh: str, sections: list,
                          ringkasan_tambahan: list | None = None) -> bytes:
    """Sama seperti _bangun_pdf(), tapi mendukung LEBIH DARI SATU tabel
    dalam satu PDF (masing-masing didahului sub-judul) -- dipakai halaman
    yang PDF cetak-langsungnya perlu menampilkan lebih dari satu tabel data
    yang sedang tampil di halaman itu (lihat buat_pdf_komisi_list()).
    sections = list of {"subjudul": str, "header": list, "baris": list,
    "col_widths": list|None}."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=32 * mm, bottomMargin=18 * mm, leftMargin=8 * mm, rightMargin=8 * mm,
        title=judul,
    )
    styles = getSampleStyleSheet()
    elemen = [Spacer(1, 2 * mm)]

    for sec in sections:
        elemen.append(Paragraph(sec["subjudul"], _SUBJUDUL_STYLE))
        baris = sec["baris"]
        if not baris:
            elemen.append(Paragraph("Tidak ada data pada periode ini.", styles["Normal"]))
        else:
            data_tabel = [sec["header"]] + baris
            tabel = Table(data_tabel, colWidths=sec.get("col_widths"), repeatRows=1)
            tabel.setStyle(_gaya_tabel())
            elemen.append(tabel)
        elemen.append(Spacer(1, 4 * mm))

    if ringkasan_tambahan:
        for baris_ringkasan in ringkasan_tambahan:
            elemen.append(Paragraph(baris_ringkasan, _RINGKASAN_STYLE))

    on_page = _header_footer_factory(judul, periode, dicetak_oleh)
    doc.build(elemen, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# Lebar kolom Laporan Transaksi (mm), total 194mm = lebar A4 dikurangi
# margin kiri+kanan 8mm masing-masing (lihat _bangun_pdf topMargin/dst) --
# Tanggal/Barber/UangHarian/Komisi/Tips/Libur/Total/Ket. Uang Harian/Komisi/
# Tips/Total disamakan 20mm (semuanya "Rp X.XXX.XXX", perlu lebar yang
# sama supaya tidak membungkus jadi 2 baris), Ket kebagian sisa lebar
# terbanyak (yang isinya paling mungkin panjang).
_LEBAR_KOLOM_TRANSAKSI = [24 * mm, 16 * mm, 20 * mm, 20 * mm, 20 * mm, 10 * mm, 20 * mm, 64 * mm]


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
    Pendapatan (jumlah kolom Total seluruh baris di atas, sudah termasuk
    Tips) dan Total Jumlah per Service (lintas barber yang tampil, hormat
    filter barber_id yang sama dengan tabelnya)."""
    data = db.get_laporan_transaksi_rekap(tanggal_mulai, tanggal_selesai, barber_id=barber_id)
    header = ["Tanggal", "Barber", "Uang Harian", "Komisi", "Tips", "Libur", "Total", "Ket"]
    baris = []
    for r in data:
        keterangan = "; ".join(f"{_tgl_pendek(c['tanggal'])}: {c['catatan']}" for c in r["catatan_list"])
        baris.append([
            _sel(periode), _sel(r["nama_barber"]), _sel(_rupiah(r["uang_harian"])),
            _sel(_rupiah(r["komisi"])), _sel(_rupiah(r["tips"])), _sel(str(r["hari_libur"])),
            _sel(_rupiah(r["total"])), _sel(keterangan),
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


def _laporan_pemasukan(tanggal_mulai: str, tanggal_selesai: str, dicetak_oleh: str):
    data = pemasukan_db.get_pemasukan_list(tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
    header = ["Tanggal", "Kategori", "Keterangan", "Barber", "Jumlah"]
    baris = [[p["tanggal"], p.get("kategori") or "-", p["keterangan"], p.get("nama_barber") or "-",
              _rupiah(p["jumlah"])] for p in data]
    return header, baris


def _laporan_kasbon(tanggal_mulai: str, tanggal_selesai: str, barber_id: int | None, dicetak_oleh: str):
    """Memenuhi kebutuhan Kasbon "masuk laporan keuangan" -- data APA ADANYA
    lewat kasbon_db.get_kasbon_list() (rentang tanggal bebas, sama seperti
    Laporan Transaksi/Pengeluaran), TIDAK menghitung ulang satu angka pun."""
    data = kasbon_db.get_kasbon_list(barber_id=barber_id, tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
    header = ["Tanggal", "Barber", "Jumlah Kasbon", "Sisa", "Status", "Keterangan"]
    baris = [[
        _sel(k["tanggal"]), _sel(k["nama_barber"]), _sel(_rupiah(k["jumlah"])), _sel(_rupiah(k["sisa"])),
        _sel("Lunas" if k["status"] == "lunas" else "Belum Lunas"), _sel(k.get("keterangan") or "-"),
    ] for k in data]

    total_diberikan = sum(k["jumlah"] for k in data)
    total_sisa = sum(k["sisa"] for k in data)
    ringkasan_tambahan = [
        f"<b>Total Kasbon Diberikan: {_rupiah(total_diberikan)}</b>",
        f"<b>Total Sisa Belum Lunas: {_rupiah(total_sisa)}</b>",
    ]
    return header, baris, ringkasan_tambahan


def _laporan_rekap_bulanan(tahun: int, bulan: int, barber_id: int | None, dicetak_oleh: str):
    data = db.get_rekap_bulanan_list(tahun, bulan, barber_id=barber_id)
    header = ["Barber", "Jumlah Service", "Komisi", "Tips", "Uang Harian", "Bonus Customer", "Total Pendapatan"]
    baris = [[r["nama_barber"], str(r["jumlah_service"]), _rupiah(r["total_komisi"]), _rupiah(r["tips"]),
              _rupiah(r["uang_harian"]), _rupiah(r["bonus_customer"]), _rupiah(r["total_pendapatan"])]
             for r in data]
    return header, baris


def _laporan_komisi(tahun: int, bulan: int, barber_id: int | None, dicetak_oleh: str):
    """Penyesuaian komisi (bonus/potongan manual) satu bulan kalender --
    data APA ADANYA lewat komisi_penyesuaian_db.get_penyesuaian_list(),
    TIDAK menghitung ulang satu angka pun. Net (Total Bonus - Total
    Potongan) match persis dengan komisi_penyesuaian_db.get_saldo_periode()
    yang dipakai auto-fill Slip Gaji, jadi laporan ini otomatis konsisten
    dengan apa yang sudah tercermin di payroll."""
    data = komisi_penyesuaian_db.get_penyesuaian_list(barber_id=barber_id, tahun=tahun, bulan=bulan)
    header = ["Barber", "Jenis", "Jumlah", "Keterangan"]
    baris = [[
        _sel(k["nama_barber"]), _sel("Bonus" if k["jenis"] == "bonus" else "Potongan"),
        _sel(_rupiah(k["jumlah"])), _sel(k.get("keterangan") or "-"),
    ] for k in data]

    total_bonus = sum(k["jumlah"] for k in data if k["jenis"] == "bonus")
    total_potongan = sum(k["jumlah"] for k in data if k["jenis"] == "potongan")
    ringkasan_tambahan = [
        f"<b>Total Bonus: {_rupiah(total_bonus)}</b>",
        f"<b>Total Potongan: {_rupiah(total_potongan)}</b>",
        f"<b>Net: {_rupiah(total_bonus - total_potongan)}</b>",
    ]
    return header, baris, ringkasan_tambahan


def _laporan_reimburse(tanggal_mulai: str, tanggal_selesai: str, barber_id: int | None, dicetak_oleh: str):
    """Klaim reimburse rentang tanggal bebas -- data APA ADANYA lewat
    reimburse_db.get_reimburse_list(), TIDAK menghitung ulang satu angka
    pun. Total Disetujui-lah yang benar-benar berdampak finansial
    (satu-satunya status yang bisa masuk auto-fill Slip Gaji, lihat
    reimburse_db.get_saldo_periode())."""
    data = reimburse_db.get_reimburse_list(barber_id=barber_id, tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
    label_status = {"pending": "Pending", "disetujui": "Disetujui", "ditolak": "Ditolak"}
    header = ["Tanggal", "Barber", "Kategori", "Nominal", "Status", "Keterangan"]
    baris = [[
        _sel(r["tanggal"]), _sel(r["nama_barber"]), _sel(r["kategori"]), _sel(_rupiah(r["nominal"])),
        _sel(label_status.get(r["status"], r["status"])), _sel(r.get("keterangan") or "-"),
    ] for r in data]

    total_disetujui = sum(r["nominal"] for r in data if r["status"] == "disetujui")
    total_pending = sum(r["nominal"] for r in data if r["status"] == "pending")
    total_ditolak = sum(r["nominal"] for r in data if r["status"] == "ditolak")
    ringkasan_tambahan = [
        f"<b>Total Disetujui: {_rupiah(total_disetujui)}</b>",
        f"Total Pending: {_rupiah(total_pending)}",
        f"Total Ditolak: {_rupiah(total_ditolak)}",
    ]
    return header, baris, ringkasan_tambahan


# Lebar kolom Slip Gaji (mm), total 194mm sama seperti tabel lain di file
# ini (lihat _LEBAR_KOLOM_TRANSAKSI) -- Komponen lebih lebar karena baris
# "Potongan Lain" bisa memuat catatan bebas dari Owner.
_LEBAR_KOLOM_SLIP_GAJI = [110 * mm, 84 * mm]

# Lebar kolom Laporan Kasbon (mm), total 194mm sama seperti tabel lain di
# file ini -- Tanggal/Barber/Jumlah Kasbon/Sisa/Status/Keterangan.
_LEBAR_KOLOM_KASBON = [22 * mm, 28 * mm, 28 * mm, 28 * mm, 24 * mm, 64 * mm]

# Lebar kolom Laporan Komisi (mm), total 194mm -- Barber/Jenis/Jumlah/Keterangan.
_LEBAR_KOLOM_KOMISI = [40 * mm, 24 * mm, 30 * mm, 100 * mm]

# Lebar kolom Laporan Reimburse (mm), total 194mm, proporsi sama persis
# Laporan Kasbon -- Tanggal/Barber/Kategori/Nominal/Status/Keterangan.
_LEBAR_KOLOM_REIMBURSE = [22 * mm, 28 * mm, 28 * mm, 28 * mm, 24 * mm, 64 * mm]


def _periode_text_slip_gaji(row: dict) -> str:
    """Barber: satu bulan kalender penuh (tahun/bulan). Kasir/OB/Kru (Tahap
    13: periode rentang tanggal bebas, row['tanggal_mulai'] terisi): pakai
    _periode_text_rentang() yang sudah ada, sama seperti Laporan Transaksi/
    Pengeluaran."""
    if row.get("tanggal_mulai"):
        return _periode_text_rentang(row["tanggal_mulai"], row["tanggal_selesai"])
    return _periode_text(row["tahun"], row["bulan"])


def buat_slip_gaji_pdf(slip: dict) -> bytes:
    """Slip Gaji satu barber satu periode -- MEMAKAI ULANG tata letak
    _bangun_pdf() yang sama persis dengan Laporan PDF lain di file ini
    (tabel Komponen|Nominal + baris ringkasan Total Diterima di bawahnya),
    TIDAK menghitung ulang satu angka pun sendiri -- seluruh angka `slip`
    sudah final dari slip_gaji_db.buat_slip_gaji()/get_slip_gaji()."""
    periode = f"{_periode_text_slip_gaji(slip)} -- {slip['nama_barber']}"
    label_potongan_lain = "Potongan Lain"
    if slip.get("catatan_potongan"):
        label_potongan_lain += f" ({slip['catatan_potongan']})"
    penyesuaian_komisi = int(slip.get("penyesuaian_komisi") or 0)
    tanda_penyesuaian = "+" if penyesuaian_komisi >= 0 else "-"
    # Karyawan Non-Barber (Kasir/OB/Kru): baris "Gaji Pokok" diganti label
    # yang menunjukkan rincian hari x rate (angka gaji_pokok slip TETAP
    # sama, cuma disimpan lewat jalur berbeda -- lihat slip_gaji_db.py).
    if slip.get("jumlah_hari_masuk") is not None:
        gaji_per_hari = int(slip["gaji_pokok"]) // int(slip["jumlah_hari_masuk"]) if slip["jumlah_hari_masuk"] else 0
        label_gaji = f"Gaji ({slip['jumlah_hari_masuk']} hari x {_rupiah(gaji_per_hari)}/hari)"
    else:
        label_gaji = "Gaji Pokok"
    header = ["Komponen", "Nominal"]
    baris = [
        [_sel(label_gaji), _rupiah(slip["gaji_pokok"])],
        [_sel("Komisi"), _rupiah(slip["komisi"])],
        [_sel("Tips"), _rupiah(slip["tips"])],
        [_sel("Uang Harian"), _rupiah(slip["uang_harian"])],
        [_sel("Bonus Customer"), _rupiah(slip["bonus_customer"])],
        [_sel("Penyesuaian Komisi"), f"{tanda_penyesuaian} {_rupiah(abs(penyesuaian_komisi))}"],
        [_sel("Reimburse"), _rupiah(slip.get("reimburse") or 0)],
        [_sel("Bonus Manual"), _rupiah(slip.get("bonus_manual") or 0)],
        [_sel("Potongan Kasbon"), f"- {_rupiah(slip['potongan_kasbon'])}"],
        [_sel(label_potongan_lain), f"- {_rupiah(slip['potongan_lain'])}"],
    ]
    status_label = "Sudah Dibayar" if slip["status"] == "sudah_dibayar" else "Belum Dibayar"
    ringkasan_tambahan = [
        f"<b>Total Diterima: {_rupiah(slip['total_diterima'])}</b>",
        f"Status: {status_label}",
    ]
    if slip.get("tanggal_dibayar"):
        ringkasan_tambahan.append(f"Tanggal Dibayar: {slip['tanggal_dibayar']}")
    dicetak_oleh = slip.get("dibuat_oleh") or "-"
    return _bangun_pdf("Slip Gaji", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_SLIP_GAJI, ringkasan_tambahan=ringkasan_tambahan)


def buat_laporan(jenis: str, barber_id: int | None, dicetak_oleh: str,
                  tanggal_mulai: str | None = None, tanggal_selesai: str | None = None,
                  tahun: int | None = None, bulan: int | None = None):
    """Return (bytes_pdf, nama_file). Raise ValueError kalau jenis tidak dikenal
    atau parameter wajib tidak diisi.

    Rekap Bulanan Barber & Komisi dipilih lewat Tahun+Bulan (lihat
    JENIS_TAHUN_BULAN) -- Rekap Bulanan karena perhitungan komisi/bonus/
    uang harian bertumpu pada batas bulan kalender (database.py
    get_ringkasan_barber_bulan()), Komisi karena baris komisi_penyesuaian
    tidak punya kolom tanggal harian sama sekali (terikat tahun+bulan
    saja). Jenis lain (termasuk Reimburse) dipilih lewat rentang tanggal
    bebas (tanggal_mulai/tanggal_selesai) supaya Periode di PDF menunjukkan
    rentang tanggal sebenarnya, bukan cuma Bulan/Tahun."""
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis laporan tidak dikenal: {jenis}")

    col_widths = None
    ringkasan_tambahan = None
    if jenis in JENIS_TAHUN_BULAN:
        if not tahun or not bulan:
            raise ValueError(f"Tahun dan Bulan wajib diisi untuk {_judul(jenis)}.")
        if jenis == "komisi":
            header, baris, ringkasan_tambahan = _laporan_komisi(tahun, bulan, barber_id, dicetak_oleh)
            col_widths = _LEBAR_KOLOM_KOMISI
        else:
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
        elif jenis == "kasbon":
            header, baris, ringkasan_tambahan = _laporan_kasbon(
                tanggal_mulai, tanggal_selesai, barber_id, dicetak_oleh,
            )
            col_widths = _LEBAR_KOLOM_KASBON
        elif jenis == "reimburse":
            header, baris, ringkasan_tambahan = _laporan_reimburse(
                tanggal_mulai, tanggal_selesai, barber_id, dicetak_oleh,
            )
            col_widths = _LEBAR_KOLOM_REIMBURSE
        elif jenis == "pemasukan":
            header, baris = _laporan_pemasukan(tanggal_mulai, tanggal_selesai, dicetak_oleh)
        else:
            header, baris = _laporan_pengeluaran(tanggal_mulai, tanggal_selesai, dicetak_oleh)

    judul = _judul(jenis)
    konten = _bangun_pdf(judul, periode, dicetak_oleh, header, baris, col_widths, ringkasan_tambahan)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"laporan_{jenis}_{stamp}.pdf"
    return konten, filename


# =============================================================================
# Cetak PDF LANGSUNG DARI MENU (Revisi Sistem Laporan & PDF)
# =============================================================================
# BEDA dari buat_laporan()/JENIS_VALID di atas (yang khusus dipakai Setting >
# Backup > Download Laporan PDF, dipilih lewat rentang tanggal bebas ATAU
# Tahun+Bulan generik): setiap fungsi buat_pdf_*() di bawah ini menerima
# PERSIS bentuk filter halaman aslinya masing-masing (barber/status/jenis/
# kategori/cari, dst -- bukan cuma tanggal), supaya tombol "Download PDF" di
# halaman itu mencerminkan filter yang SEDANG AKTIF di halaman, bukan filter
# generik. Data tetap diambil APA ADANYA lewat fungsi baca yang sudah ada,
# TIDAK ada satu angka pun dihitung ulang di sini -- murni tata letak PDF,
# sama seperti seluruh isi file ini.


def buat_nama_file(prefix: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}_{stamp}.pdf"


# Lebar kolom Rekap Transaksi (mm), total 194mm -- Tanggal/Barber/Service/
# Jml Service/Uang Harian/Tips/Pendapatan/Ket, mengikuti kolom tabel
# pages/rekap.js tab Transaksi apa adanya.
_LEBAR_KOLOM_REKAP_TRANSAKSI = [20 * mm, 26 * mm, 40 * mm, 16 * mm, 22 * mm, 20 * mm, 22 * mm, 28 * mm]


def buat_pdf_rekap_transaksi(tahun: int | None, bulan: int | None, barber_id: int | None, dicetak_oleh: str,
                              tanggal_mulai: str | None = None, tanggal_selesai: str | None = None) -> bytes:
    """tanggal_mulai/tanggal_selesai (opsional, dikirim dari input Periode
    PDF di halaman Rekap Transaksi) MENGGANTIKAN tahun/bulan sebagai
    periode kalau diisi -- filter tampilan layar (Bulan+Tahun) sendiri
    tidak berubah, ini murni opsi tambahan saat cetak PDF."""
    if tanggal_mulai and tanggal_selesai:
        data = db.get_rekap_transaksi_list(barber_id=barber_id, tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
        data = reimburse_db.gabung_ke_rekap_transaksi(data, barber_id=barber_id,
                                                        tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
        rincian_service = db.get_rincian_service_periode(barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                                          tanggal_selesai=tanggal_selesai)
        periode = _periode_text_rentang(tanggal_mulai, tanggal_selesai)
    else:
        data = db.get_rekap_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id)
        data = reimburse_db.gabung_ke_rekap_transaksi(data, tahun=tahun, bulan=bulan, barber_id=barber_id)
        rincian_service = db.get_rincian_service_periode(tahun=tahun, bulan=bulan, barber_id=barber_id)
        periode = _periode_text_opsional(tahun, bulan)
    header = ["Tanggal", "Nama", "Service", "Jml Service", "Uang Harian", "Tips", "Pendapatan", "Ket"]
    baris = [[
        _sel(r["tanggal"]), _sel(r["nama_barber"]), _sel(r["daftar_service"] or "-"),
        _sel(str(r["jumlah_service"])), _sel(_rupiah(r["uang_harian"])), _sel(_rupiah(r["tips"])),
        _sel(_rupiah(r["pendapatan"])), _sel(r["keterangan"] or "-"),
    ] for r in data]
    # Tahap 15: ringkasan di bawah tabel dipecah jadi Pendapatan (transaksi
    # murni, TIDAK termasuk Reimburse) + Rincian (jumlah per jenis service,
    # digabung SEMUA karyawan yang tercakup filter -- service yang jumlahnya
    # 0 otomatis tidak muncul) + Reimburse (terpisah) + TOTAL (Pendapatan +
    # Reimburse) -- sebelumnya Reimburse ikut tercampur ke "Total Pendapatan".
    pendapatan_total = sum(r["pendapatan"] for r in data if r.get("tipe") != "reimburse")
    reimburse_total = sum(r["pendapatan"] for r in data if r.get("tipe") == "reimburse")
    ringkasan_tambahan = [f"<b>Pendapatan: {_rupiah(pendapatan_total)}</b>"]
    if rincian_service:
        ringkasan_tambahan.append("<b>Rincian</b>")
        for s in rincian_service:
            ringkasan_tambahan.append(f"{s['nama_service']}: {s['jumlah']}")
    ringkasan_tambahan.append(f"<b>Reimburse: {_rupiah(reimburse_total)}</b>")
    ringkasan_tambahan.append(f"<b>TOTAL: {_rupiah(pendapatan_total + reimburse_total)}</b>")
    return _bangun_pdf("Rekap Transaksi", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_REKAP_TRANSAKSI, ringkasan_tambahan=ringkasan_tambahan)


# Lebar kolom Rekap Bulanan Barber (mm), total 194mm -- BEDA dari
# _LEBAR_KOLOM di _laporan_rekap_bulanan (dipakai Setting > Backup, kolom
# lebih sedikit): varian halaman ini menyertakan Hari Libur & Target Bonus
# persis seperti tabel pages/rekap.js tab Bulanan. Kolom Reimburse (Tahap
# 12) ditambahkan sebelum Total.
_LEBAR_KOLOM_REKAP_BULANAN_HALAMAN = [30 * mm, 16 * mm, 20 * mm, 18 * mm, 20 * mm, 14 * mm, 18 * mm, 16 * mm, 20 * mm, 22 * mm]


def buat_pdf_rekap_bulanan(tahun: int, bulan: int, barber_id: int | None, dicetak_oleh: str) -> bytes:
    data = db.get_rekap_bulanan_list(tahun, bulan, barber_id=barber_id)
    header = ["Barber", "Jml Service", "Komisi", "Tips", "Uang Harian", "Hari Libur", "Target Bonus", "Bonus Cust.", "Reimburse", "Total"]
    baris = [[
        _sel(r["nama_barber"]), _sel(str(r["jumlah_service"])), _sel(_rupiah(r["total_komisi"])),
        _sel(_rupiah(r["tips"])), _sel(_rupiah(r["uang_harian"])), _sel(str(r["hari_libur"])),
        _sel("Tercapai" if r["target_tercapai"] else "Belum"), _sel(_rupiah(r["bonus_customer"])),
        _sel(_rupiah(reimburse_db.get_saldo_periode(r["barber_id"], tahun, bulan))),
        _sel(_rupiah(r["total_pendapatan"])),
    ] for r in data]
    total_pendapatan = sum(r["total_pendapatan"] for r in data)
    ringkasan_tambahan = [f"<b>Total Pendapatan: {_rupiah(total_pendapatan)}</b>"]
    periode = _periode_text(tahun, bulan)
    return _bangun_pdf("Rekap Bulanan Barber", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_REKAP_BULANAN_HALAMAN, ringkasan_tambahan=ringkasan_tambahan)


# Lebar kolom Rekap Pengeluaran & Laporan Pemasukan/Pengeluaran (mm), total
# 194mm -- Tanggal/Kategori/Keterangan/Barber/Nominal(/Status).
_LEBAR_KOLOM_PENGELUARAN_TAB_REKAP = [22 * mm, 30 * mm, 94 * mm, 28 * mm, 20 * mm]


def buat_pdf_rekap_pengeluaran(tahun: int | None, bulan: int | None, dicetak_oleh: str) -> bytes:
    data = pengeluaran_db.get_pengeluaran_list(tahun=tahun, bulan=bulan)
    header = ["Tanggal", "Kategori", "Keterangan", "Barber", "Jumlah"]
    baris = [[
        _sel(p["tanggal"]), _sel(p.get("kategori") or "-"), _sel(p["keterangan"]),
        _sel(p.get("nama_barber") or "-"), _sel(_rupiah(p["jumlah"])),
    ] for p in data]
    total = sum(p["jumlah"] for p in data)
    ringkasan_tambahan = [f"<b>Total Pengeluaran: {_rupiah(total)}</b>"]
    periode = _periode_text_opsional(tahun, bulan)
    return _bangun_pdf("Rekap Pengeluaran", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_PENGELUARAN_TAB_REKAP, ringkasan_tambahan=ringkasan_tambahan)


# Lebar kolom Daftar Slip Gaji (mm), total 194mm -- Periode/Barber/
# Reimburse/Total Diterima/Status, mengikuti kolom tabel pages/slip_gaji.js
# apa adanya (kolom Reimburse ditambahkan Tahap 12).
_LEBAR_KOLOM_SLIP_GAJI_LIST = [26 * mm, 44 * mm, 30 * mm, 34 * mm, 60 * mm]


def buat_pdf_slip_gaji_list(tahun: int | None, bulan: int | None, barber_id: int | None, dicetak_oleh: str) -> bytes:
    data = slip_gaji_db.get_slip_gaji_list(tahun=tahun, bulan=bulan, barber_id=barber_id)
    header = ["Periode", "Barber", "Reimburse", "Total Diterima", "Status"]
    baris = [[
        _sel(_periode_text_slip_gaji(r)), _sel(r["nama_barber"]),
        _sel(_rupiah(r["reimburse"])),
        _sel(_rupiah(r["total_diterima"])),
        _sel("Sudah Dibayar" if r["status"] == "sudah_dibayar" else "Belum Dibayar"),
    ] for r in data]
    total = sum(r["total_diterima"] for r in data)
    ringkasan_tambahan = [f"<b>Total Diterima (semua baris): {_rupiah(total)}</b>"]
    periode = _periode_text_opsional(tahun, bulan)
    return _bangun_pdf("Daftar Slip Gaji", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_SLIP_GAJI_LIST, ringkasan_tambahan=ringkasan_tambahan)


def buat_pdf_kasbon_list(barber_id: int | None, status: str | None, tahun: int | None, bulan: int | None,
                          dicetak_oleh: str) -> bytes:
    """Sama seperti _laporan_kasbon() (Setting > Backup), tapi filter
    tahun/bulan+status persis filter halaman Kasbon (BUKAN rentang tanggal
    bebas)."""
    data = kasbon_db.get_kasbon_list(barber_id=barber_id, status=status, tahun=tahun, bulan=bulan)
    header = ["Tanggal", "Barber", "Jumlah Kasbon", "Sisa", "Status", "Keterangan"]
    baris = [[
        _sel(k["tanggal"]), _sel(k["nama_barber"]), _sel(_rupiah(k["jumlah"])), _sel(_rupiah(k["sisa"])),
        _sel("Lunas" if k["status"] == "lunas" else "Belum Lunas"), _sel(k.get("keterangan") or "-"),
    ] for k in data]
    total_diberikan = sum(k["jumlah"] for k in data)
    total_sisa = sum(k["sisa"] for k in data)
    ringkasan_tambahan = [
        f"<b>Total Kasbon Diberikan: {_rupiah(total_diberikan)}</b>",
        f"<b>Total Sisa Belum Lunas: {_rupiah(total_sisa)}</b>",
    ]
    periode = _periode_text_opsional(tahun, bulan)
    return _bangun_pdf("Laporan Kasbon", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_KASBON, ringkasan_tambahan=ringkasan_tambahan)


# Lebar kolom Riwayat Komisi (Dasar) dalam PDF Laporan Komisi (mm), total
# 194mm -- Barber/Jml Service/Komisi Dasar/Tips/Uang Harian/Bonus Cust./
# Total Pendapatan, mengikuti tabel tampilkanRiwayatKomisi() di komisi.js.
_LEBAR_KOLOM_RIWAYAT_KOMISI_DASAR = [54 * mm, 20 * mm, 24 * mm, 20 * mm, 24 * mm, 24 * mm, 28 * mm]


def buat_pdf_komisi_list(barber_id: int | None, jenis: str | None, tahun: int, bulan: int, dicetak_oleh: str) -> bytes:
    """PDF dua bagian, PERSIS apa yang tampil di halaman Komisi untuk
    filter Barber/Bulan/Tahun yang sama: Riwayat Komisi (Dasar) (reuse
    db.get_rekap_bulanan_list() apa adanya, TIDAK menghitung ulang) +
    Daftar Penyesuaian Komisi (dengan filter Jenis tambahan yang tidak ada
    di _laporan_komisi() versi Setting > Backup)."""
    riwayat = db.get_rekap_bulanan_list(tahun, bulan, barber_id=barber_id)
    header_riwayat = ["Barber", "Jml Service", "Komisi Dasar", "Tips", "Uang Harian", "Bonus Cust.", "Total Pendapatan"]
    baris_riwayat = [[
        _sel(r["nama_barber"]), _sel(str(r["jumlah_service"])), _sel(_rupiah(r["total_komisi"])),
        _sel(_rupiah(r["tips"])), _sel(_rupiah(r["uang_harian"])), _sel(_rupiah(r["bonus_customer"])),
        _sel(_rupiah(r["total_pendapatan"])),
    ] for r in riwayat]

    data = komisi_penyesuaian_db.get_penyesuaian_list(barber_id=barber_id, tahun=tahun, bulan=bulan, jenis=jenis)
    header_penyesuaian = ["Barber", "Jenis", "Jumlah", "Keterangan"]
    baris_penyesuaian = [[
        _sel(k["nama_barber"]), _sel("Bonus" if k["jenis"] == "bonus" else "Potongan"),
        _sel(_rupiah(k["jumlah"])), _sel(k.get("keterangan") or "-"),
    ] for k in data]

    total_bonus = sum(k["jumlah"] for k in data if k["jenis"] == "bonus")
    total_potongan = sum(k["jumlah"] for k in data if k["jenis"] == "potongan")
    ringkasan_tambahan = [
        f"<b>Total Bonus: {_rupiah(total_bonus)}</b>",
        f"<b>Total Potongan: {_rupiah(total_potongan)}</b>",
        f"<b>Net: {_rupiah(total_bonus - total_potongan)}</b>",
    ]
    periode = _periode_text(tahun, bulan)
    sections = [
        {"subjudul": "Riwayat Komisi (Dasar)", "header": header_riwayat, "baris": baris_riwayat,
         "col_widths": _LEBAR_KOLOM_RIWAYAT_KOMISI_DASAR},
        {"subjudul": "Daftar Penyesuaian Komisi", "header": header_penyesuaian, "baris": baris_penyesuaian,
         "col_widths": _LEBAR_KOLOM_KOMISI},
    ]
    return _bangun_pdf_sections("Laporan Komisi", periode, dicetak_oleh, sections,
                                 ringkasan_tambahan=ringkasan_tambahan)


def buat_pdf_reimburse_list(barber_id: int | None, status: str | None, tahun: int | None, bulan: int | None,
                             dicetak_oleh: str) -> bytes:
    """Sama seperti _laporan_reimburse() (Setting > Backup), tapi filter
    tahun/bulan+status persis filter halaman Reimburse (BUKAN rentang
    tanggal bebas)."""
    data = reimburse_db.get_reimburse_list(barber_id=barber_id, status=status, tahun=tahun, bulan=bulan)
    label_status = {"pending": "Pending", "disetujui": "Disetujui", "ditolak": "Ditolak"}
    header = ["Tanggal", "Barber", "Kategori", "Nominal", "Status", "Keterangan"]
    baris = [[
        _sel(r["tanggal"]), _sel(r["nama_barber"]), _sel(r["kategori"]), _sel(_rupiah(r["nominal"])),
        _sel(label_status.get(r["status"], r["status"])), _sel(r.get("keterangan") or "-"),
    ] for r in data]
    total_disetujui = sum(r["nominal"] for r in data if r["status"] == "disetujui")
    total_pending = sum(r["nominal"] for r in data if r["status"] == "pending")
    total_ditolak = sum(r["nominal"] for r in data if r["status"] == "ditolak")
    ringkasan_tambahan = [
        f"<b>Total Disetujui: {_rupiah(total_disetujui)}</b>",
        f"Total Pending: {_rupiah(total_pending)}",
        f"Total Ditolak: {_rupiah(total_ditolak)}",
    ]
    periode = _periode_text_opsional(tahun, bulan)
    return _bangun_pdf("Laporan Reimburse", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_REIMBURSE, ringkasan_tambahan=ringkasan_tambahan)


# Lebar kolom Laporan Izin & Cuti (mm), total 194mm -- Barber/Jenis/Mulai/
# Selesai/Alasan/Status, mengikuti tabel pages/izin_cuti.js apa adanya.
_LEBAR_KOLOM_IZIN_CUTI = [30 * mm, 16 * mm, 20 * mm, 20 * mm, 84 * mm, 24 * mm]


def buat_pdf_izin_cuti_list(barber_id: int | None, jenis: str | None, status: str | None, dicetak_oleh: str) -> bytes:
    """Halaman Izin & Cuti TIDAK punya filter tanggal/bulan/tahun sama
    sekali (lihat pages/izin_cuti.js) -- Periode selalu "Semua Periode"."""
    data = izin_cuti_db.get_pengajuan_list(barber_id=barber_id, status=status, jenis=jenis)
    label_status = {"pending": "Pending", "disetujui": "Disetujui", "ditolak": "Ditolak"}
    header = ["Barber", "Jenis", "Mulai", "Selesai", "Alasan", "Status"]
    baris = [[
        _sel(r["nama_barber"]), _sel("Cuti" if r["jenis"] == "cuti" else "Izin"),
        _sel(r["tanggal_mulai"]), _sel(r["tanggal_selesai"]), _sel(r["alasan"]),
        _sel(label_status.get(r["status"], r["status"])),
    ] for r in data]
    jumlah_disetujui = sum(1 for r in data if r["status"] == "disetujui")
    jumlah_pending = sum(1 for r in data if r["status"] == "pending")
    jumlah_ditolak = sum(1 for r in data if r["status"] == "ditolak")
    ringkasan_tambahan = [
        f"<b>Total Pengajuan: {len(data)}</b> "
        f"(Disetujui: {jumlah_disetujui}, Pending: {jumlah_pending}, Ditolak: {jumlah_ditolak})",
    ]
    return _bangun_pdf("Laporan Izin & Cuti", "Semua Periode", dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_IZIN_CUTI, ringkasan_tambahan=ringkasan_tambahan)


# Lebar kolom Laporan Pemasukan/Pengeluaran (mm), total 194mm -- Tanggal/
# Kategori/Keterangan/Barber/Nominal/Status, mengikuti tabel pages/
# pemasukan.js & pages/pengeluaran.js apa adanya (BEDA dari
# _LEBAR_KOLOM_PENGELUARAN_TAB_REKAP di atas yang tidak punya kolom Status).
_LEBAR_KOLOM_PEMASUKAN_PENGELUARAN_HALAMAN = [20 * mm, 26 * mm, 70 * mm, 26 * mm, 24 * mm, 28 * mm]


def buat_pdf_pemasukan_list(tahun: int, bulan: int, kategori: str | None, cari: str | None, dicetak_oleh: str) -> bytes:
    data = pemasukan_db.get_pemasukan_list(tahun=tahun, bulan=bulan, kategori=kategori, cari=cari)
    header = ["Tanggal", "Kategori", "Keterangan", "Barber", "Nominal", "Status"]
    baris = [[
        _sel(p["tanggal"]), _sel(p.get("kategori") or "-"), _sel(p["keterangan"]),
        _sel(p.get("nama_barber") or "-"), _sel(_rupiah(p["jumlah"])),
        _sel("Aktif" if p.get("aktif") else "Nonaktif"),
    ] for p in data]
    total = sum(p["jumlah"] for p in data)
    ringkasan_tambahan = [f"<b>Total Pemasukan: {_rupiah(total)}</b>"]
    periode = _periode_text(tahun, bulan)
    return _bangun_pdf("Laporan Pemasukan", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_PEMASUKAN_PENGELUARAN_HALAMAN, ringkasan_tambahan=ringkasan_tambahan)


def buat_pdf_pengeluaran_list(tahun: int, bulan: int, kategori: str | None, cari: str | None, dicetak_oleh: str) -> bytes:
    data = pengeluaran_db.get_pengeluaran_list(tahun=tahun, bulan=bulan, kategori=kategori, cari=cari)
    header = ["Tanggal", "Kategori", "Keterangan", "Barber", "Nominal", "Status"]
    baris = [[
        _sel(p["tanggal"]), _sel(p.get("kategori") or "-"), _sel(p["keterangan"]),
        _sel(p.get("nama_barber") or "-"), _sel(_rupiah(p["jumlah"])),
        _sel("Aktif" if p.get("aktif") else "Nonaktif"),
    ] for p in data]
    total = sum(p["jumlah"] for p in data)
    ringkasan_tambahan = [f"<b>Total Pengeluaran: {_rupiah(total)}</b>"]
    periode = _periode_text(tahun, bulan)
    return _bangun_pdf("Laporan Pengeluaran", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_PEMASUKAN_PENGELUARAN_HALAMAN, ringkasan_tambahan=ringkasan_tambahan)


# Lebar kolom Laporan Uang Kas (mm), total 194mm -- Tanggal/Jenis/Jumlah/
# Keterangan/Saldo Berjalan.
_LEBAR_KOLOM_UANG_KAS = [24 * mm, 20 * mm, 28 * mm, 82 * mm, 40 * mm]


def buat_pdf_uang_kas_list(tahun: int | None, bulan: int | None, dicetak_oleh: str) -> bytes:
    """Saldo Berjalan dihitung di PYTHON (bukan SQL) saat iterasi baris
    SECARA KRONOLOGIS (tertua dulu, kebalikan dari get_penyesuaian_list()
    yang defaultnya terbaru dulu -- ledger yang menunjukkan saldo berjalan
    HARUS dibaca kronologis), mulai dari Saldo Kas Awal -- konsisten
    dengan uang_kas_db.get_saldo_kas()."""
    data = list(reversed(uang_kas_db.get_penyesuaian_list(tahun=tahun, bulan=bulan)))
    saldo_awal = uang_kas_db.get_saldo_awal()["saldo"]
    header = ["Tanggal", "Jenis", "Jumlah", "Keterangan", "Saldo Berjalan"]
    baris = []
    saldo_berjalan = saldo_awal
    for k in data:
        if k["jenis"] == "tambah":
            saldo_berjalan += k["jumlah"]
        else:
            saldo_berjalan -= k["jumlah"]
        baris.append([
            _sel(k["tanggal"]), _sel("Tambah" if k["jenis"] == "tambah" else "Kurang"),
            _sel(_rupiah(k["jumlah"])), _sel(k.get("keterangan") or "-"), _sel(_rupiah(saldo_berjalan)),
        ])
    ringkasan_tambahan = [
        f"Saldo Kas Awal: {_rupiah(saldo_awal)}",
        f"<b>Saldo Akhir: {_rupiah(saldo_berjalan)}</b>",
    ]
    periode = _periode_text_opsional(tahun, bulan)
    return _bangun_pdf("Laporan Uang Kas", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_UANG_KAS, ringkasan_tambahan=ringkasan_tambahan)
