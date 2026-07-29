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


def buat_slip_gaji_pdf(slip: dict) -> bytes:
    """Slip Gaji satu barber satu bulan -- MEMAKAI ULANG tata letak
    _bangun_pdf() yang sama persis dengan Laporan PDF lain di file ini
    (tabel Komponen|Nominal + baris ringkasan Total Diterima di bawahnya),
    TIDAK menghitung ulang satu angka pun sendiri -- seluruh angka `slip`
    sudah final dari slip_gaji_db.buat_slip_gaji()/get_slip_gaji()."""
    periode = f"{_NAMA_BULAN[slip['bulan']]} {slip['tahun']} -- {slip['nama_barber']}"
    label_potongan_lain = "Potongan Lain"
    if slip.get("catatan_potongan"):
        label_potongan_lain += f" ({slip['catatan_potongan']})"
    penyesuaian_komisi = int(slip.get("penyesuaian_komisi") or 0)
    tanda_penyesuaian = "+" if penyesuaian_komisi >= 0 else "-"
    header = ["Komponen", "Nominal"]
    baris = [
        [_sel("Gaji Pokok"), _rupiah(slip["gaji_pokok"])],
        [_sel("Komisi"), _rupiah(slip["komisi"])],
        [_sel("Tips"), _rupiah(slip["tips"])],
        [_sel("Uang Harian"), _rupiah(slip["uang_harian"])],
        [_sel("Bonus Customer"), _rupiah(slip["bonus_customer"])],
        [_sel("Penyesuaian Komisi"), f"{tanda_penyesuaian} {_rupiah(abs(penyesuaian_komisi))}"],
        [_sel("Reimburse"), _rupiah(slip.get("reimburse") or 0)],
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
