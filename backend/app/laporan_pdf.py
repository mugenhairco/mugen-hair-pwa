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
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
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
import data_non_barber_db
import rekap_ringkasan

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


_LABEL_JABATAN_RINGKASAN = {"kasir": "Kasir", "ob": "OB", "kru": "Kru"}


def _label_jabatan(jabatan: str) -> str:
    """Label role untuk baris ringkasan 'Total Gaji {role}' -- 3 role baku
    (Kasir/OB/Kru) pakai label singkatan yang sudah dikenal, role kustom
    (ditulis bebas Owner lewat Setting > Karyawan) ditampilkan apa adanya
    (Title Case) supaya tetap terbaca rapi tanpa perlu daftar label baru
    tiap kali Owner membuat role baru."""
    return _LABEL_JABATAN_RINGKASAN.get(jabatan, (jabatan or "Lainnya").title())


def _sel_service(daftar_service: str) -> Paragraph:
    """Kolom Service (Rekap Transaksi): kalau lebih dari satu jenis service,
    tampilkan SATU BARIS BARU per jenis (bukan digabung koma dalam satu
    baris) -- murni kosmetik render PDF lewat tag <br/> yang didukung
    Paragraph reportlab, TIDAK mengubah `daftar_service` sumbernya sama
    sekali (field yang sama dipakai tampilan layar & Input Data apa adanya,
    lihat database.py). Baris tabel otomatis melebar tingginya sendiri
    (Platypus Table menyesuaikan ke flowable tertinggi di barisnya) --
    tidak perlu logika tambahan untuk itu. "Nama xN" diganti "Nama ×N"
    (tanda kali) supaya lebih mudah dibaca saat sudah per baris."""
    if not daftar_service:
        return _sel("-")
    bagian = [b.strip() for b in daftar_service.split(", ") if b.strip()]
    diformat = []
    for b in bagian:
        if " x" in b:
            nama, jumlah = b.rsplit(" x", 1)
            diformat.append(f"{nama} ×{jumlah}")
        else:
            diformat.append(b)
    return Paragraph("<br/>".join(diformat), _SEL_STYLE)


def _sel_keterangan(nilai) -> Paragraph:
    """Kolom Keterangan/Ket (Rekap Transaksi Detail & Ringkasan): kalau
    berisi LEBIH DARI SATU informasi (Catatan/Kasbon/Reimburse/Libur, dst),
    tampilkan SATU BARIS BARU per informasi -- BUKAN digabung koma/titik-
    koma jadi satu baris, prinsipnya sama persis _sel_service() di atas.
    Menerima LIST (baris sudah dipisah per info, dipakai rekap_ringkasan.py
    lewat field keterangan_list) ATAU string gabungan "; " (pola lama,
    dipakai r["keterangan"] baris Rekap Detail dari database.py/
    reimburse_db.py/kasbon_db.py/data_non_barber_db.py -- lihat _tempel()
    di bawah). TIDAK mengubah data sumbernya, murni cara menampilkannya."""
    if isinstance(nilai, list):
        bagian = [str(b).strip() for b in nilai if str(b or "").strip()]
    else:
        bagian = [b.strip() for b in (nilai or "").split("; ") if b.strip()]
    if not bagian:
        return _sel("-")
    return Paragraph("<br/>".join(bagian), _SEL_STYLE)


# Header kolom tabel -- BEDA dari _SEL_STYLE (isi sel biasa): tebal + putih
# (menyamai TEXTCOLOR/FONTNAME row header di _gaya_tabel()), supaya bisa
# dibungkus Paragraph juga (lihat _kepala() di bawah). PENTING: TableStyle
# (BACKGROUND/TEXTCOLOR/FONTNAME) TIDAK berlaku untuk isi sel berupa
# Paragraph/flowable (hanya berlaku untuk teks mentah) -- makanya warna/tebal
# header harus diatur di ParagraphStyle ini sendiri, bukan cukup lewat
# TableStyle seperti sebelum kolom header dibungkus Paragraph.
_HEADER_STYLE = ParagraphStyle("header-laporan", fontName="Helvetica-Bold", fontSize=8, leading=10,
                                textColor=colors.white)


def _kepala(nilai) -> Paragraph:
    """Bungkus label header kolom jadi Paragraph supaya BISA MELIPAT KE
    BARIS BARU kalau lebih lebar dari kolomnya -- sebelumnya header dikirim
    sebagai string mentah ke Table, yang TIDAK melipat teks sama sekali
    (beda dari isi sel biasa yang sudah lewat _sel()/Paragraph), sehingga
    header kolom sempit (mis. "Jml Service", "Kasbon Dibayar") tumpang
    tindih ke kolom sebelahnya alih-alih melipat rapi ke baris kedua."""
    return Paragraph(str(nilai), _HEADER_STYLE)


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


def _header_footer_factory(judul: str, periode: str, dicetak_oleh: str, tenant_id: int | None = None):
    """FONDASI Multi-Tenant Phase 2.2 (Tenant Branding): `tenant_id` SEBELUMNYA
    tidak pernah diteruskan sampai ke sini -- identitas/logo yang tercetak di
    SETIAP laporan PDF (apa pun tenant-nya) selalu diambil TANPA tenant_id,
    yaitu key `settings`/`file_asset` GLOBAL/tanpa-prefix (nilai lama dari
    sebelum Phase 1, beku sejak migrasi) -- bug nyata: PDF Tenant B akan
    tercetak dengan nama & logo Tenant A (tenant default) di kop suratnya,
    bukan milik tenant itu sendiri. Sekarang WAJIB diteruskan dari seluruh
    fungsi buat_pdf_*() di bawah (semuanya sudah menerima tenant_id untuk
    scoping data sejak Phase 1.1, tinggal diteruskan satu langkah lagi)."""
    identitas = pengaturan_identitas.get_identitas(tenant_id=tenant_id)
    nama_barbershop = identitas.get("nama_barbershop") or "Rivoir"
    logo_data, _ = pengaturan_identitas.get_logo_data(tenant_id=tenant_id)
    tanggal_cetak = datetime.now().strftime("%d/%m/%Y %H:%M")

    def _on_page(canvas, doc):
        canvas.saveState()
        # REVISI (Rapikan PDF Rekap Periode Ringkasan): baca dari doc.pagesize
        # (BUKAN konstanta A4 langsung) supaya header/footer tetap benar
        # posisinya kalau dokumennya landscape (lihat _bangun_pdf() param
        # `landscape`) -- untuk seluruh laporan lain yang tetap portrait,
        # doc.pagesize == A4 apa adanya, jadi tidak ada perubahan tampilan
        # sama sekali.
        width, height = doc.pagesize
        y = height - 15 * mm

        if logo_data:
            try:
                canvas.drawImage(ImageReader(BytesIO(logo_data)), 15 * mm, y - 10 * mm, width=14 * mm, height=14 * mm,
                                  preserveAspectRatio=True, mask="auto")
            except Exception:
                pass  # logo korup/format tidak didukung reportlab -- laporan tetap dicetak tanpa logo

        text_x = 32 * mm if logo_data else 15 * mm
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
                 col_widths: list | None = None, ringkasan_tambahan: list | None = None,
                 landscape_page: bool = False, extra_style: list | None = None,
                 tenant_id: int | None = None) -> bytes:
    """`landscape_page`/`extra_style` (REVISI Rapikan PDF Rekap Periode
    Ringkasan): KHUSUS dipakai laporan yang kolomnya terlalu banyak untuk
    muat rapi di lebar A4 potret (Rekap Periode Ringkasan) -- default TETAP
    False/None untuk SEMUA laporan lain di file ini, jadi tidak ada laporan
    lain yang tata letaknya berubah sama sekali. `extra_style` = daftar
    command TableStyle TAMBAHAN (mis. ALIGN per kolom), diterapkan SETELAH
    _gaya_tabel() supaya bisa menimpa/melengkapi tanpa mengubah gaya dasar
    yang dipakai laporan lain."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4) if landscape_page else A4,
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
        data_tabel = [[_kepala(h) for h in header_kolom]] + baris
        tabel = Table(data_tabel, colWidths=col_widths, repeatRows=1)
        gaya = _gaya_tabel()
        if extra_style:
            for command in extra_style:
                gaya.add(*command)
        tabel.setStyle(gaya)
        elemen.append(tabel)

        if ringkasan_tambahan:
            elemen.append(Spacer(1, 4 * mm))
            for baris_ringkasan in ringkasan_tambahan:
                elemen.append(Paragraph(baris_ringkasan, _RINGKASAN_STYLE))

    on_page = _header_footer_factory(judul, periode, dicetak_oleh, tenant_id=tenant_id)
    doc.build(elemen, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# Judul sub-bagian dalam PDF multi-tabel (lihat _bangun_pdf_sections()) --
# HANYA dipakai halaman Komisi yang punya dua tabel (Riwayat Komisi Dasar +
# Daftar Penyesuaian) dalam satu PDF, supaya keduanya jelas beda bagian.
_SUBJUDUL_STYLE = ParagraphStyle("subjudul-laporan", fontName="Helvetica-Bold", fontSize=10, leading=13)


def _bangun_pdf_sections(judul: str, periode: str, dicetak_oleh: str, sections: list,
                          ringkasan_tambahan: list | None = None, tenant_id: int | None = None) -> bytes:
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
            data_tabel = [[_kepala(h) for h in sec["header"]]] + baris
            tabel = Table(data_tabel, colWidths=sec.get("col_widths"), repeatRows=1)
            tabel.setStyle(_gaya_tabel())
            elemen.append(tabel)
        elemen.append(Spacer(1, 4 * mm))

    if ringkasan_tambahan:
        for baris_ringkasan in ringkasan_tambahan:
            elemen.append(Paragraph(baris_ringkasan, _RINGKASAN_STYLE))

    on_page = _header_footer_factory(judul, periode, dicetak_oleh, tenant_id=tenant_id)
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
                        dicetak_oleh: str, periode: str, tenant_id: int | None = None):
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
    data = db.get_laporan_transaksi_rekap(tanggal_mulai, tanggal_selesai, barber_id=barber_id, tenant_id=tenant_id)
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
    rincian_service = db.get_rincian_service_rentang(tanggal_mulai, tanggal_selesai, barber_id=barber_id,
                                                       tenant_id=tenant_id)
    ringkasan_tambahan = [f"<b>Total Semua Pendapatan: {_rupiah(total_pendapatan)}</b>"]
    if rincian_service:
        ringkasan_tambahan.append("<b>Total Jumlah per Service:</b>")
        ringkasan_tambahan.append(", ".join(f"{s['nama_service']}: {s['jumlah']}" for s in rincian_service))

    return header, baris, ringkasan_tambahan


def _laporan_pengeluaran(tanggal_mulai: str, tanggal_selesai: str, dicetak_oleh: str, tenant_id: int = None):
    data = pengeluaran_db.get_pengeluaran_list(tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
                                                tenant_id=tenant_id)
    header = ["Tanggal", "Kategori", "Keterangan", "Barber", "Jumlah"]
    baris = [[p["tanggal"], p.get("kategori") or "-", p["keterangan"], p.get("nama_barber") or "-",
              _rupiah(p["jumlah"])] for p in data]
    return header, baris


def _laporan_pemasukan(tanggal_mulai: str, tanggal_selesai: str, dicetak_oleh: str, tenant_id: int | None = None):
    data = pemasukan_db.get_pemasukan_list(tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
                                            tenant_id=tenant_id)
    header = ["Tanggal", "Kategori", "Keterangan", "Barber", "Jumlah"]
    baris = [[p["tanggal"], p.get("kategori") or "-", p["keterangan"], p.get("nama_barber") or "-",
              _rupiah(p["jumlah"])] for p in data]
    return header, baris


def _laporan_kasbon(tanggal_mulai: str, tanggal_selesai: str, barber_id: int | None, dicetak_oleh: str,
                     tenant_id: int | None = None):
    """Memenuhi kebutuhan Kasbon "masuk laporan keuangan" -- data APA ADANYA
    lewat kasbon_db.get_kasbon_list() (rentang tanggal bebas, sama seperti
    Laporan Transaksi/Pengeluaran), TIDAK menghitung ulang satu angka pun."""
    data = kasbon_db.get_kasbon_list(barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                      tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
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


def _laporan_rekap_bulanan(tahun: int, bulan: int, barber_id: int | None, dicetak_oleh: str,
                            tenant_id: int | None = None):
    data = db.get_rekap_bulanan_list(tahun, bulan, barber_id=barber_id, tenant_id=tenant_id)
    header = ["Barber", "Jumlah Service", "Komisi", "Tips", "Uang Harian", "Bonus Customer", "Total Pendapatan"]
    baris = [[r["nama_barber"], str(r["jumlah_service"]), _rupiah(r["total_komisi"]), _rupiah(r["tips"]),
              _rupiah(r["uang_harian"]), _rupiah(r["bonus_customer"]), _rupiah(r["total_pendapatan"])]
             for r in data]
    return header, baris


def _laporan_komisi(tahun: int, bulan: int, barber_id: int | None, dicetak_oleh: str,
                     tenant_id: int | None = None):
    """Penyesuaian komisi (bonus/potongan manual) satu bulan kalender --
    data APA ADANYA lewat komisi_penyesuaian_db.get_penyesuaian_list(),
    TIDAK menghitung ulang satu angka pun. Net (Total Bonus - Total
    Potongan) match persis dengan komisi_penyesuaian_db.get_saldo_periode()
    yang dipakai auto-fill Slip Gaji, jadi laporan ini otomatis konsisten
    dengan apa yang sudah tercermin di payroll."""
    data = komisi_penyesuaian_db.get_penyesuaian_list(barber_id=barber_id, tahun=tahun, bulan=bulan,
                                                        tenant_id=tenant_id)
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


def _laporan_reimburse(tanggal_mulai: str, tanggal_selesai: str, barber_id: int | None, dicetak_oleh: str,
                        tenant_id: int | None = None):
    """Klaim reimburse rentang tanggal bebas -- data APA ADANYA lewat
    reimburse_db.get_reimburse_list(), TIDAK menghitung ulang satu angka
    pun. Total Disetujui-lah yang benar-benar berdampak finansial
    (satu-satunya status yang bisa masuk auto-fill Slip Gaji, lihat
    reimburse_db.get_saldo_periode())."""
    data = reimburse_db.get_reimburse_list(barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                            tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
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
    # MAINTENANCE #1: PDF dinamis -- komponen yang nilainya 0/kosong TIDAK
    # ditampilkan sama sekali (bukan "Rp 0"), formula/field Total Diterima
    # itu sendiri TIDAK berubah (tetap seluruh komponen di bawah, lihat
    # slip_gaji_db.buat_slip_gaji() -- hanya TAMPILANNYA yang jadi dinamis).
    baris_dinamis = [
        (slip["gaji_pokok"], [_sel(label_gaji), _rupiah(slip["gaji_pokok"])]),
        (slip["komisi"], [_sel("Komisi"), _rupiah(slip["komisi"])]),
        (slip["tips"], [_sel("Tips"), _rupiah(slip["tips"])]),
        (slip["uang_harian"], [_sel("Uang Harian"), _rupiah(slip["uang_harian"])]),
        (slip["bonus_customer"], [_sel("Bonus Customer"), _rupiah(slip["bonus_customer"])]),
        (penyesuaian_komisi, [_sel("Penyesuaian Komisi"), f"{tanda_penyesuaian} {_rupiah(abs(penyesuaian_komisi))}"]),
        (slip.get("reimburse") or 0, [_sel("Reimburse"), _rupiah(slip.get("reimburse") or 0)]),
        (slip.get("bonus_manual") or 0, [_sel("Bonus Manual"), _rupiah(slip.get("bonus_manual") or 0)]),
        (slip["potongan_kasbon"], [_sel("Potongan Kasbon"), f"- {_rupiah(slip['potongan_kasbon'])}"]),
        (slip["potongan_lain"], [_sel(label_potongan_lain), f"- {_rupiah(slip['potongan_lain'])}"]),
    ]
    baris = [baris_item for nilai, baris_item in baris_dinamis if nilai]
    status_label = "Sudah Dibayar" if slip["status"] == "sudah_dibayar" else "Belum Dibayar"
    ringkasan_tambahan = [
        f"<b>Total Diterima: {_rupiah(slip['total_diterima'])}</b>",
        f"Status: {status_label}",
    ]
    if slip.get("tanggal_dibayar"):
        ringkasan_tambahan.append(f"Tanggal Dibayar: {slip['tanggal_dibayar']}")
    dicetak_oleh = slip.get("dibuat_oleh") or "-"
    return _bangun_pdf("Slip Gaji", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_SLIP_GAJI, ringkasan_tambahan=ringkasan_tambahan,
                        tenant_id=slip.get("tenant_id"))


def buat_laporan(jenis: str, barber_id: int | None, dicetak_oleh: str,
                  tanggal_mulai: str | None = None, tanggal_selesai: str | None = None,
                  tahun: int | None = None, bulan: int | None = None, tenant_id: int | None = None):
    """Return (bytes_pdf, nama_file). Raise ValueError kalau jenis tidak dikenal
    atau parameter wajib tidak diisi.

    Rekap Bulanan Barber & Komisi dipilih lewat Tahun+Bulan (lihat
    JENIS_TAHUN_BULAN) -- Rekap Bulanan karena perhitungan komisi/bonus/
    uang harian bertumpu pada batas bulan kalender (database.py
    get_ringkasan_barber_bulan()), Komisi karena baris komisi_penyesuaian
    tidak punya kolom tanggal harian sama sekali (terikat tahun+bulan
    saja). Jenis lain (termasuk Reimburse) dipilih lewat rentang tanggal
    bebas (tanggal_mulai/tanggal_selesai) supaya Periode di PDF menunjukkan
    rentang tanggal sebenarnya, bukan cuma Bulan/Tahun.

    FONDASI Multi-Tenant Phase 1.1: `tenant_id` sekarang diteruskan ke
    SELURUH jenis laporan tanpa kecuali (kasbon/reimburse/komisi/pemasukan
    -- lihat _laporan_kasbon/_laporan_reimburse/_laporan_komisi/
    _laporan_pemasukan)."""
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis laporan tidak dikenal: {jenis}")

    col_widths = None
    ringkasan_tambahan = None
    if jenis in JENIS_TAHUN_BULAN:
        if not tahun or not bulan:
            raise ValueError(f"Tahun dan Bulan wajib diisi untuk {_judul(jenis)}.")
        if jenis == "komisi":
            header, baris, ringkasan_tambahan = _laporan_komisi(tahun, bulan, barber_id, dicetak_oleh,
                                                                  tenant_id=tenant_id)
            col_widths = _LEBAR_KOLOM_KOMISI
        else:
            header, baris = _laporan_rekap_bulanan(tahun, bulan, barber_id, dicetak_oleh, tenant_id=tenant_id)
        periode = _periode_text(tahun, bulan)
    else:
        if not tanggal_mulai or not tanggal_selesai:
            raise ValueError("Tanggal Dari dan Tanggal Sampai wajib diisi.")
        if tanggal_mulai > tanggal_selesai:
            raise ValueError("Tanggal Dari tidak boleh setelah Tanggal Sampai.")
        periode = _periode_text_rentang(tanggal_mulai, tanggal_selesai)
        if jenis == "transaksi":
            header, baris, ringkasan_tambahan = _laporan_transaksi(
                tanggal_mulai, tanggal_selesai, barber_id, dicetak_oleh, periode, tenant_id=tenant_id,
            )
            col_widths = _LEBAR_KOLOM_TRANSAKSI
        elif jenis == "kasbon":
            header, baris, ringkasan_tambahan = _laporan_kasbon(
                tanggal_mulai, tanggal_selesai, barber_id, dicetak_oleh, tenant_id=tenant_id,
            )
            col_widths = _LEBAR_KOLOM_KASBON
        elif jenis == "reimburse":
            header, baris, ringkasan_tambahan = _laporan_reimburse(
                tanggal_mulai, tanggal_selesai, barber_id, dicetak_oleh, tenant_id=tenant_id,
            )
            col_widths = _LEBAR_KOLOM_REIMBURSE
        elif jenis == "pemasukan":
            header, baris = _laporan_pemasukan(tanggal_mulai, tanggal_selesai, dicetak_oleh, tenant_id=tenant_id)
        else:
            header, baris = _laporan_pengeluaran(tanggal_mulai, tanggal_selesai, dicetak_oleh, tenant_id=tenant_id)

    judul = _judul(jenis)
    konten = _bangun_pdf(judul, periode, dicetak_oleh, header, baris, col_widths, ringkasan_tambahan, tenant_id=tenant_id)
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
# Jml Service/Uang Harian/Tips/Pendapatan(/Reimburse/Kasbon Dibayar kalau
# ada)/Ket, mengikuti kolom tabel pages/rekap.js tab Transaksi APA ADANYA
# untuk kolom dasar -- Reimburse & Kasbon Dibayar KHUSUS PDF (lihat
# _gabung_reimburse_kasbon_kolom()), tidak ada di tampilan layar.
_LEBAR_KOLOM_REKAP_TRANSAKSI = {
    (False, False): [20 * mm, 26 * mm, 40 * mm, 16 * mm, 22 * mm, 20 * mm, 22 * mm, 28 * mm],
    (True, False):  [20 * mm, 26 * mm, 34 * mm, 16 * mm, 20 * mm, 18 * mm, 20 * mm, 18 * mm, 22 * mm],
    (False, True):  [20 * mm, 26 * mm, 34 * mm, 16 * mm, 20 * mm, 18 * mm, 20 * mm, 18 * mm, 22 * mm],
    (True, True):   [20 * mm, 24 * mm, 28 * mm, 14 * mm, 18 * mm, 16 * mm, 18 * mm, 16 * mm, 16 * mm, 24 * mm],
}


def _gabung_reimburse_kasbon_kolom(data: list, tahun: int = None, bulan: int = None, barber_id: int = None,
                                    tanggal_mulai: str = None, tanggal_selesai: str = None,
                                    tenant_id: int = None):
    """REVISI (khusus PDF Rekap Transaksi, BEDA dari tampilan layar yang
    tetap pakai reimburse_db.py/kasbon_db.py gabung_ke_rekap_transaksi()
    apa adanya -- baris terpisah): Reimburse & Kasbon Dibayar TIDAK jadi
    baris sendiri, tapi digabung sebagai KOLOM tambahan ke baris yang
    SUDAH ADA di tanggal+barber yang sama (satu tanggal = satu baris) --
    kalau tidak ada baris transaksi/libur di tanggal itu, baru dibuat baris
    baru minimal. Return (data, ada_reimburse, ada_kasbon) -- 2 flag
    terakhir dipakai buat_pdf_rekap_transaksi() untuk MENYEMBUNYIKAN TOTAL
    kolom (bukan cuma mengosongkan nilainya) kalau memang tidak ada
    satupun Reimburse/Kasbon di SELURUH data yang dicetak (baik filter
    satu karyawan maupun semua karyawan)."""
    for r in data:
        r["reimburse"] = 0
        r["kasbon_dibayar"] = 0

    # Baris PERTAMA yang cocok per (barber_id, tanggal) -- jarang ada lebih
    # dari satu transaksi barber yang sama di tanggal yang sama, tapi kalau
    # ada, Reimburse/Kasbon tanggal itu ditempelkan ke satu baris saja
    # (tidak pernah dobel) supaya total tetap benar.
    index = {}
    for r in data:
        index.setdefault((r["barber_id"], r["tanggal"]), r)

    def _tempel(key, jumlah, kolom, catatan, nama_barber):
        row = index.get(key)
        if row is None:
            row = {
                "tipe": "gabungan", "tanggal": key[1], "barber_id": key[0], "nama_barber": nama_barber,
                "daftar_service": "", "jumlah_service": 0, "tips": 0, "uang_harian": 0, "pendapatan": 0,
                "keterangan": "", "reimburse": 0, "kasbon_dibayar": 0,
            }
            index[key] = row
            data.append(row)
        row[kolom] += jumlah
        row["keterangan"] = "; ".join(x for x in [row["keterangan"], catatan] if x)

    for rb in reimburse_db.get_reimburse_list_disetujui(tahun=tahun, bulan=bulan, barber_id=barber_id,
                                                          tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
                                                          tenant_id=tenant_id):
        _tempel((rb["barber_id"], rb["tanggal_approval"]), rb["nominal"], "reimburse",
                f"Reimburse: {rb['kategori']} {_rupiah(rb['nominal'])}", rb["nama_barber"])

    for kb in kasbon_db.get_pembayaran_list_periode(tahun=tahun, bulan=bulan, barber_id=barber_id,
                                                     tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
                                                     tenant_id=tenant_id):
        catatan = f"Kasbon: {_rupiah(kb['jumlah'])} ({kb['keterangan']})" if kb.get("keterangan") else f"Kasbon: {_rupiah(kb['jumlah'])}"
        _tempel((kb["barber_id"], kb["tanggal"]), kb["jumlah"], "kasbon_dibayar", catatan, kb["nama_barber"])

    data.sort(key=lambda r: r["nama_barber"])
    data.sort(key=lambda r: r["tanggal"], reverse=True)
    ada_reimburse = any(r["reimburse"] for r in data)
    ada_kasbon = any(r["kasbon_dibayar"] for r in data)
    return data, ada_reimburse, ada_kasbon


def buat_pdf_rekap_transaksi(tahun: int | None, bulan: int | None, barber_id: int | None, dicetak_oleh: str,
                              tanggal_mulai: str | None = None, tanggal_selesai: str | None = None,
                              tenant_id: int | None = None) -> bytes:
    """tanggal_mulai/tanggal_selesai (opsional, dikirim dari input Periode
    PDF di halaman Rekap Transaksi) MENGGANTIKAN tahun/bulan sebagai
    periode kalau diisi -- filter tampilan layar (Bulan+Tahun) sendiri
    tidak berubah, ini murni opsi tambahan saat cetak PDF.

    FONDASI Multi-Tenant Phase 1.1: `tenant_id` diteruskan ke SELURUH query
    di bawah, termasuk data_non_barber_db/reimburse_db/kasbon_db yang
    digabung (lihat _gabung_reimburse_kasbon_kolom()) -- Phase 1 sempat
    tidak meneruskannya ke ketiga modul itu, sudah diperbaiki di sini."""
    if tanggal_mulai and tanggal_selesai:
        data = db.get_rekap_transaksi_list(barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                            tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
        # Dukungan Barber + Non-Barber: baris Gaji Non-Barber digabung SEBELUM
        # _gabung_reimburse_kasbon_kolom() supaya Reimburse/Kasbon yang
        # kebetulan jatuh di tanggal yang sama ikut tertempel ke baris itu
        # juga (fungsi itu generik, bekerja untuk baris tipe apapun).
        data = data_non_barber_db.gabung_ke_rekap_transaksi(
            data, barber_id=barber_id, tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
            tenant_id=tenant_id)
        data, ada_reimburse, ada_kasbon = _gabung_reimburse_kasbon_kolom(
            data, barber_id=barber_id, tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
            tenant_id=tenant_id)
        rincian_service = db.get_rincian_service_periode(barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                                          tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
        periode = _periode_text_rentang(tanggal_mulai, tanggal_selesai)
    else:
        data = db.get_rekap_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id, tenant_id=tenant_id)
        data = data_non_barber_db.gabung_ke_rekap_transaksi(data, tahun=tahun, bulan=bulan, barber_id=barber_id,
                                                             tenant_id=tenant_id)
        data, ada_reimburse, ada_kasbon = _gabung_reimburse_kasbon_kolom(
            data, tahun=tahun, bulan=bulan, barber_id=barber_id, tenant_id=tenant_id)
        rincian_service = db.get_rincian_service_periode(tahun=tahun, bulan=bulan, barber_id=barber_id,
                                                          tenant_id=tenant_id)
        periode = _periode_text_opsional(tahun, bulan)

    header = ["Tanggal", "Nama", "Service", "Jml Service", "Uang Harian", "Tips", "Pendapatan"]
    if ada_reimburse:
        header.append("Reimburse")
    if ada_kasbon:
        header.append("Kasbon Dibayar")
    header.append("Ket")

    baris = []
    for r in data:
        sel = [
            _sel(r["tanggal"]), _sel(r["nama_barber"]), _sel_service(r["daftar_service"]),
            _sel(str(r["jumlah_service"])), _sel(_rupiah(r["uang_harian"])), _sel(_rupiah(r["tips"])),
            _sel(_rupiah(r["pendapatan"])),
        ]
        if ada_reimburse:
            sel.append(_sel(_rupiah(r["reimburse"]) if r["reimburse"] else "-"))
        if ada_kasbon:
            sel.append(_sel(f"-{_rupiah(r['kasbon_dibayar'])}" if r["kasbon_dibayar"] else "-"))
        sel.append(_sel_keterangan(r["keterangan"]))
        baris.append(sel)

    # MAINTENANCE #1 (bugfix): Ringkasan di bawah tabel SEBELUMNYA menjumlah
    # "Total Pendapatan Barber" dari get_pendapatan_transaksi() = total_komisi
    # + tips SAJA (lihat database.py) -- Uang Harian ditampilkan per-baris di
    # tabel TAPI TIDAK PERNAH ikut dijumlahkan ke total manapun di bawahnya,
    # jadi "Total Keseluruhan" secara diam-diam kurang sebesar total Uang
    # Harian periode itu. Diperbaiki dengan menjumlahkan Komisi/Uang Harian/
    # Tips SEBAGAI TIGA ANGKA TERPISAH (Uang Harian di-dedup per (barber,
    # tanggal) -- SATU baris per hari itu di tabel bisa terwakili lebih dari
    # satu baris transaksi kalau barber itu dicatat lebih dari sekali hari
    # yang sama, dan tiap baris membawa nilai Uang Harian hari itu yang SAMA
    # apa adanya, lihat get_rekap_transaksi_list() -- menjumlah apa adanya
    # per-baris akan melipatgandakannya).
    #
    # Susunan & tampilan dinamis (MAINTENANCE #1): Komisi/Uang Harian/Tips/
    # Gaji Non-Barber per role/Reimburse/Kasbon HANYA ditampilkan kalau
    # nilainya bukan nol -- baris yang nilainya 0 TIDAK ditampilkan sama
    # sekali (bukan ditampilkan sebagai "Rp0"), lalu Rincian Service (HANYA
    # service yang jumlahnya > 0 -- get_rincian_service_periode() sudah
    # begitu dari awal), diakhiri "Total Diterima" (dulu "Total Keseluruhan").
    komisi_total = sum(r["pendapatan"] - r["tips"] for r in data if r.get("tipe") != "non_barber")
    tips_total = sum(r["tips"] for r in data if r.get("tipe") != "non_barber")
    uang_harian_per_hari = {}
    for r in data:
        if r.get("tipe") == "transaksi":
            uang_harian_per_hari[(r["barber_id"], r["tanggal"])] = r["uang_harian"]
    uang_harian_total = sum(uang_harian_per_hari.values())
    reimburse_total = sum(r["reimburse"] for r in data)
    kasbon_total = sum(r["kasbon_dibayar"] for r in data)

    non_barber_per_role = {}
    for r in data:
        if r.get("tipe") != "non_barber":
            continue
        role = r.get("jabatan") or "lainnya"
        non_barber_per_role[role] = non_barber_per_role.get(role, 0) + r["pendapatan"]
    gaji_non_barber_total = sum(non_barber_per_role.values())

    ringkasan_tambahan = []
    if komisi_total:
        ringkasan_tambahan.append(f"<b>Komisi: {_rupiah(komisi_total)}</b>")
    if uang_harian_total:
        ringkasan_tambahan.append(f"<b>Uang Harian: {_rupiah(uang_harian_total)}</b>")
    if tips_total:
        ringkasan_tambahan.append(f"<b>Tips: {_rupiah(tips_total)}</b>")
    for role, total in non_barber_per_role.items():
        if not total:
            continue
        ringkasan_tambahan.append(f"<b>Total Gaji {_label_jabatan(role)}: {_rupiah(total)}</b>")
    if ada_reimburse:
        ringkasan_tambahan.append(f"<b>Reimburse: {_rupiah(reimburse_total)}</b>")
    if ada_kasbon:
        ringkasan_tambahan.append(f"<b>Kasbon: -{_rupiah(kasbon_total)}</b>")
    if rincian_service:
        ringkasan_tambahan.append("<b>Service</b>")
        for s in rincian_service:
            ringkasan_tambahan.append(f"{s['nama_service']}: {s['jumlah']}")
    total_diterima = komisi_total + uang_harian_total + tips_total + gaji_non_barber_total + reimburse_total - kasbon_total
    ringkasan_tambahan.append(f"<b>Total Diterima: {_rupiah(total_diterima)}</b>")
    return _bangun_pdf("Rekap Transaksi", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_REKAP_TRANSAKSI[(ada_reimburse, ada_kasbon)],
                        ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


# REVISI (Rapikan tampilan PDF Rekap Periode Ringkasan): laporan ini bisa
# sampai 13 kolom (Reimburse/Kasbon Dibayar/Gaji Non-Barber dinamis, sama
# seperti Rekap Detail) -- TIDAK muat rapi di lebar A4 potret (194mm) tanpa
# memaksa kolom nominal jadi sempit dan angkanya terpotong ke baris kedua.
# Laporan ini SEKARANG dicetak LANDSCAPE (lihat buat_pdf_rekap_transaksi_
# ringkasan() -> landscape_page=True), memberi ~281mm lebar tercetak --
# HANYA laporan ini, seluruh laporan lain di file ini TETAP potret A4 apa
# adanya (_bangun_pdf() default landscape_page=False).
#
# Lebar kolom nominal (Uang Harian/Tips/Pendapatan/Reimburse/Kasbon Dibayar/
# Gaji Non-Barber/Total) dihitung dari lebar teks Rupiah TERBESAR yang
# realistis ("Rp 99.999.999", 8pt Helvetica) + padding sel, supaya angka
# WAJIB muat satu baris -- lihat komentar tiap nilai di bawah kalau nilai
# ini perlu disesuaikan lagi nanti.
_LEBAR_HALAMAN_RINGKASAN = 281 * mm  # A4 landscape (297mm) dikurangi margin kiri+kanan 8mm+8mm

_LEBAR_TETAP_RINGKASAN = {
    "Nama": 30 * mm,           # nama karyawan, dilebihkan supaya nama panjang tetap satu baris
    "Jml Service": 16 * mm,
    "Hari Libur": 16 * mm,
    "Uang Harian": 23 * mm,    # cukup untuk "Rp 99.999.999" tanpa terpotong
    "Tips": 23 * mm,
    "Pendapatan": 24 * mm,
    "Reimburse": 23 * mm,
    "Kasbon Dibayar": 24 * mm,  # ada prefix "-" tambahan ("-Rp ...")
    "Gaji Non-Barber": 24 * mm,
    "Total": 24 * mm,          # bisa negatif ("Rp -...") kalau kasbon lebih besar dari pendapatan
}


def _lebar_kolom_ringkasan(kolom: list) -> list:
    """Kolom "Service" & "Keterangan" (satu-satunya yang isinya wajar untuk
    melipat ke banyak baris, lihat _sel_service()/_sel_keterangan())
    berbagi SISA lebar setelah seluruh kolom tetap di atas -- supaya jumlah
    kolom yang tampil (dinamis) tidak perlu tabel lebar per kombinasi.
    Kolom nominal TIDAK PERNAH mengambil dari sisa ini (lebarnya SELALU
    tetap dari _LEBAR_TETAP_RINGKASAN), jadi tidak mungkin ikut menyempit
    walau kolom lain bertambah banyak."""
    sisa = _LEBAR_HALAMAN_RINGKASAN - sum(_LEBAR_TETAP_RINGKASAN[k] for k in kolom if k not in ("Service", "Keterangan"))
    # Keterangan biasanya menampung lebih banyak baris sekaligus (Catatan +
    # Kasbon + Reimburse + tiap hari Libur) dibanding Service (cuma daftar
    # jenis service), jadi kebagian porsi lebih besar dari sisa lebar.
    lebar_service = sisa * 0.38
    lebar_keterangan = sisa - lebar_service
    hasil = []
    for k in kolom:
        if k == "Service":
            hasil.append(lebar_service)
        elif k == "Keterangan":
            hasil.append(lebar_keterangan)
        else:
            hasil.append(_LEBAR_TETAP_RINGKASAN[k])
    return hasil


# Kolom yang isinya TEKS BEBAS (rata kiri wajar) -- selain ini, seluruh
# kolom Rekap Periode Ringkasan berisi angka/nominal, dirapikan rata kanan
# supaya digit-digitnya sejajar antar baris (lebih mudah dibaca/dibandingkan
# dibanding rata kiri untuk kolom angka).
_KOLOM_TEKS_RINGKASAN = {"Nama", "Service", "Keterangan"}


def _gaya_kolom_ringkasan(kolom: list) -> list:
    """Command TableStyle TAMBAHAN khusus Rekap Periode Ringkasan (dipakai
    lewat parameter extra_style _bangun_pdf(), TIDAK menyentuh _gaya_tabel()
    dasar yang dipakai laporan lain): header selalu center (rapi terlepas
    dari isi kolom), padding sel eksplisit & seragam (bukan cuma default
    reportlab), kolom angka rata kanan, kolom teks rata kiri."""
    commands = [
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, k in enumerate(kolom):
        align = "LEFT" if k in _KOLOM_TEKS_RINGKASAN else "RIGHT"
        commands.append(("ALIGN", (i, 1), (i, -1), align))
    return commands


def buat_pdf_rekap_transaksi_ringkasan(tahun: int | None, bulan: int | None, barber_id: int | None,
                                        dicetak_oleh: str, tanggal_mulai: str | None = None,
                                        tanggal_selesai: str | None = None, tenant_id: int | None = None) -> bytes:
    """"Rekap Periode (Ringkasan)" -- jenis laporan BARU di menu Rekap
    Transaksi (Perbaikan Alur Cetak PDF), satu baris per karyawan untuk
    SELURUH periode (BEDA dari buat_pdf_rekap_transaksi() / "Rekap Detail"
    yang satu baris per transaksi/hari, TIDAK diubah sama sekali). Data
    sumber & rumus grand total SAMA PERSIS dengan Rekap Detail (dibangun
    dari baris gabungan yang sama), hanya ditampilkan diringkas per
    karyawan lewat rekap_ringkasan.ringkas_per_karyawan() -- murni
    penjumlahan, tidak menghitung ulang satu angka pun."""
    if tanggal_mulai and tanggal_selesai:
        data = db.get_rekap_transaksi_list(barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                            tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
        data = reimburse_db.gabung_ke_rekap_transaksi(data, barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                                       tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
        data = kasbon_db.gabung_ke_rekap_transaksi(data, barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                                    tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
        data = data_non_barber_db.gabung_ke_rekap_transaksi(data, barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                                             tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
        rincian_service = db.get_rincian_service_periode(barber_id=barber_id, tanggal_mulai=tanggal_mulai,
                                                          tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
        periode = _periode_text_rentang(tanggal_mulai, tanggal_selesai)
    else:
        data = db.get_rekap_transaksi_list(tahun=tahun, bulan=bulan, barber_id=barber_id, tenant_id=tenant_id)
        data = reimburse_db.gabung_ke_rekap_transaksi(data, tahun=tahun, bulan=bulan, barber_id=barber_id,
                                                       tenant_id=tenant_id)
        data = kasbon_db.gabung_ke_rekap_transaksi(data, tahun=tahun, bulan=bulan, barber_id=barber_id,
                                                    tenant_id=tenant_id)
        data = data_non_barber_db.gabung_ke_rekap_transaksi(data, tahun=tahun, bulan=bulan, barber_id=barber_id,
                                                             tenant_id=tenant_id)
        rincian_service = db.get_rincian_service_periode(tahun=tahun, bulan=bulan, barber_id=barber_id,
                                                          tenant_id=tenant_id)
        periode = _periode_text_opsional(tahun, bulan)

    ringkas = rekap_ringkasan.ringkas_per_karyawan(data)
    ada_reimburse = any(r["reimburse"] for r in ringkas)
    ada_kasbon = any(r["kasbon_dibayar"] for r in ringkas)
    ada_non_barber = any(r["gaji_non_barber"] for r in ringkas)

    header = ["Nama", "Jml Service", "Service", "Hari Libur", "Uang Harian", "Tips", "Pendapatan"]
    if ada_reimburse:
        header.append("Reimburse")
    if ada_kasbon:
        header.append("Kasbon Dibayar")
    if ada_non_barber:
        header.append("Gaji Non-Barber")
    header.append("Total")
    header.append("Keterangan")

    baris = []
    for r in ringkas:
        sel = [
            _sel(r["nama_barber"]), _sel(str(r["jumlah_service"])),
            _sel_service(r["daftar_service"]), _sel(str(r["hari_libur"])), _sel(_rupiah(r["uang_harian"])),
            _sel(_rupiah(r["tips"])), _sel(_rupiah(r["pendapatan"])),
        ]
        if ada_reimburse:
            sel.append(_sel(_rupiah(r["reimburse"]) if r["reimburse"] else "-"))
        if ada_kasbon:
            sel.append(_sel(f"-{_rupiah(r['kasbon_dibayar'])}" if r["kasbon_dibayar"] else "-"))
        if ada_non_barber:
            sel.append(_sel(_rupiah(r["gaji_non_barber"]) if r["gaji_non_barber"] else "-"))
        sel.append(_sel(_rupiah(r["total"])))
        sel.append(_sel_keterangan(r["keterangan_list"]))
        baris.append(sel)

    # MAINTENANCE #1 (bugfix): ringkasan bawah SEBELUMNYA "SAMA PERSIS
    # rumusnya dengan Rekap Detail" apa adanya -- termasuk BUG-nya (Uang
    # Harian tidak ikut dijumlahkan ke total mana pun, lihat catatan bugfix
    # di buat_pdf_rekap_transaksi() di atas). `ringkas` (dari
    # rekap_ringkasan.ringkas_per_karyawan(), sudah diperbaiki juga) SUDAH
    # men-dedup Uang Harian per (barber, tanggal) per karyawan, jadi
    # menjumlahkannya lintas karyawan di sini aman (tidak perlu dedup lagi).
    komisi_total = sum(r["pendapatan"] - r["tips"] for r in ringkas)
    tips_total = sum(r["tips"] for r in ringkas)
    uang_harian_total = sum(r["uang_harian"] for r in ringkas)
    reimburse_total = sum(r["reimburse"] for r in ringkas)
    kasbon_total = sum(r["kasbon_dibayar"] for r in ringkas)
    non_barber_per_role = {}
    for r in ringkas:
        if not r["gaji_non_barber"]:
            continue
        role = r.get("jabatan") or "lainnya"
        non_barber_per_role[role] = non_barber_per_role.get(role, 0) + r["gaji_non_barber"]
    gaji_non_barber_total = sum(non_barber_per_role.values())

    # Susunan & tampilan dinamis (MAINTENANCE #1): SAMA PERSIS
    # buat_pdf_rekap_transaksi() -- lihat catatan lengkap di sana.
    ringkasan_tambahan = []
    if komisi_total:
        ringkasan_tambahan.append(f"<b>Komisi: {_rupiah(komisi_total)}</b>")
    if uang_harian_total:
        ringkasan_tambahan.append(f"<b>Uang Harian: {_rupiah(uang_harian_total)}</b>")
    if tips_total:
        ringkasan_tambahan.append(f"<b>Tips: {_rupiah(tips_total)}</b>")
    for role, total in non_barber_per_role.items():
        ringkasan_tambahan.append(f"<b>Total Gaji {_label_jabatan(role)}: {_rupiah(total)}</b>")
    if ada_reimburse:
        ringkasan_tambahan.append(f"<b>Reimburse: {_rupiah(reimburse_total)}</b>")
    if ada_kasbon:
        ringkasan_tambahan.append(f"<b>Kasbon: -{_rupiah(kasbon_total)}</b>")
    if rincian_service:
        ringkasan_tambahan.append("<b>Service</b>")
        for s in rincian_service:
            ringkasan_tambahan.append(f"{s['nama_service']}: {s['jumlah']}")
    total_diterima = komisi_total + uang_harian_total + tips_total + gaji_non_barber_total + reimburse_total - kasbon_total
    ringkasan_tambahan.append(f"<b>Total Diterima: {_rupiah(total_diterima)}</b>")

    return _bangun_pdf("Rekap Periode (Ringkasan)", periode, dicetak_oleh, header, baris,
                        col_widths=_lebar_kolom_ringkasan(header), ringkasan_tambahan=ringkasan_tambahan,
                        landscape_page=True, extra_style=_gaya_kolom_ringkasan(header), tenant_id=tenant_id)


# Lebar kolom Rekap Bulanan Barber (mm), total 194mm -- BEDA dari
# _LEBAR_KOLOM di _laporan_rekap_bulanan (dipakai Setting > Backup, kolom
# lebih sedikit): varian halaman ini menyertakan Hari Libur & Target Bonus
# persis seperti tabel pages/rekap.js tab Bulanan. Kolom Reimburse (Tahap
# 12) & Kasbon Dibayar (Tahap 17) ditambahkan sebelum Total.
_LEBAR_KOLOM_REKAP_BULANAN_HALAMAN = [28 * mm, 18 * mm, 16 * mm, 14 * mm, 18 * mm, 12 * mm, 14 * mm, 14 * mm, 20 * mm, 16 * mm, 24 * mm]


def buat_pdf_rekap_bulanan(tahun: int, bulan: int, barber_id: int | None, dicetak_oleh: str,
                            tenant_id: int | None = None) -> bytes:
    data = db.get_rekap_bulanan_list(tahun, bulan, barber_id=barber_id, tenant_id=tenant_id)
    header = ["Barber", "Jml Service", "Komisi", "Tips", "Uang Harian", "Hari Libur", "Target Bonus", "Bonus Cust.", "Reimburse", "Kasbon Dibayar", "Total"]
    # Tahap 17: BUGFIX -- Reimburse sebelumnya ditampilkan sebagai kolom
    # terpisah TAPI tidak ikut dijumlah ke Total. Sekarang Total per baris
    # (dan grand total di ringkasan) diperbaiki: + Reimburse - Kasbon
    # Dibayar (kasbon = pinjaman yang dikembalikan, MENGURANGI, bukan
    # pendapatan seperti Reimburse -- lihat kasbon_db.py).
    baris = []
    total_pendapatan = 0
    for r in data:
        reimburse = reimburse_db.get_saldo_periode(r["barber_id"], tahun, bulan)
        kasbon_dibayar = kasbon_db.get_total_dibayar_periode(r["barber_id"], tahun, bulan)
        total_baris = r["total_pendapatan"] + reimburse - kasbon_dibayar
        total_pendapatan += total_baris
        baris.append([
            _sel(r["nama_barber"]), _sel(str(r["jumlah_service"])), _sel(_rupiah(r["total_komisi"])),
            _sel(_rupiah(r["tips"])), _sel(_rupiah(r["uang_harian"])), _sel(str(r["hari_libur"])),
            _sel("Tercapai" if r["target_tercapai"] else "Belum"), _sel(_rupiah(r["bonus_customer"])),
            _sel(_rupiah(reimburse)), _sel(_rupiah(kasbon_dibayar)), _sel(_rupiah(total_baris)),
        ])
    ringkasan_tambahan = [f"<b>Total Pendapatan: {_rupiah(total_pendapatan)}</b>"]
    periode = _periode_text(tahun, bulan)
    return _bangun_pdf("Rekap Bulanan Barber", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_REKAP_BULANAN_HALAMAN, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


# Lebar kolom Rekap Pengeluaran & Laporan Pemasukan/Pengeluaran (mm), total
# 194mm -- Tanggal/Kategori/Keterangan/Barber/Nominal(/Status).
_LEBAR_KOLOM_PENGELUARAN_TAB_REKAP = [22 * mm, 30 * mm, 94 * mm, 28 * mm, 20 * mm]


def buat_pdf_rekap_pengeluaran(tahun: int | None, bulan: int | None, dicetak_oleh: str,
                                tenant_id: int = None) -> bytes:
    data = pengeluaran_db.get_pengeluaran_list(tahun=tahun, bulan=bulan, tenant_id=tenant_id)
    header = ["Tanggal", "Kategori", "Keterangan", "Barber", "Jumlah"]
    baris = [[
        _sel(p["tanggal"]), _sel(p.get("kategori") or "-"), _sel(p["keterangan"]),
        _sel(p.get("nama_barber") or "-"), _sel(_rupiah(p["jumlah"])),
    ] for p in data]
    total = sum(p["jumlah"] for p in data)
    ringkasan_tambahan = [f"<b>Total Pengeluaran: {_rupiah(total)}</b>"]
    periode = _periode_text_opsional(tahun, bulan)
    return _bangun_pdf("Rekap Pengeluaran", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_PENGELUARAN_TAB_REKAP, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


# Lebar kolom Daftar Slip Gaji (mm), total 194mm -- Periode/Barber/
# Reimburse/Total Diterima/Status, mengikuti kolom tabel pages/slip_gaji.js
# apa adanya (kolom Reimburse ditambahkan Tahap 12).
_LEBAR_KOLOM_SLIP_GAJI_LIST = [26 * mm, 44 * mm, 30 * mm, 34 * mm, 60 * mm]


def buat_pdf_slip_gaji_list(tahun: int | None, bulan: int | None, barber_id: int | None, dicetak_oleh: str,
                             tenant_id: int | None = None) -> bytes:
    data = slip_gaji_db.get_slip_gaji_list(tahun=tahun, bulan=bulan, barber_id=barber_id, tenant_id=tenant_id)
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
                        col_widths=_LEBAR_KOLOM_SLIP_GAJI_LIST, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


def buat_pdf_kasbon_list(barber_id: int | None, status: str | None, tahun: int | None, bulan: int | None,
                          dicetak_oleh: str, tenant_id: int | None = None) -> bytes:
    """Sama seperti _laporan_kasbon() (Setting > Backup), tapi filter
    tahun/bulan+status persis filter halaman Kasbon (BUKAN rentang tanggal
    bebas)."""
    data = kasbon_db.get_kasbon_list(barber_id=barber_id, status=status, tahun=tahun, bulan=bulan,
                                      tenant_id=tenant_id)
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
                        col_widths=_LEBAR_KOLOM_KASBON, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


# Lebar kolom Riwayat Komisi (Dasar) dalam PDF Laporan Komisi (mm), total
# 194mm -- Barber/Jml Service/Komisi Dasar/Tips/Uang Harian/Bonus Cust./
# Total Pendapatan, mengikuti tabel tampilkanRiwayatKomisi() di komisi.js.
_LEBAR_KOLOM_RIWAYAT_KOMISI_DASAR = [54 * mm, 20 * mm, 24 * mm, 20 * mm, 24 * mm, 24 * mm, 28 * mm]


def buat_pdf_komisi_list(barber_id: int | None, jenis: str | None, tahun: int, bulan: int, dicetak_oleh: str,
                          tenant_id: int | None = None) -> bytes:
    """PDF dua bagian, PERSIS apa yang tampil di halaman Komisi untuk
    filter Barber/Bulan/Tahun yang sama: Riwayat Komisi (Dasar) (reuse
    db.get_rekap_bulanan_list() apa adanya, TIDAK menghitung ulang) +
    Daftar Penyesuaian Komisi (dengan filter Jenis tambahan yang tidak ada
    di _laporan_komisi() versi Setting > Backup)."""
    riwayat = db.get_rekap_bulanan_list(tahun, bulan, barber_id=barber_id, tenant_id=tenant_id)
    header_riwayat = ["Barber", "Jml Service", "Komisi Dasar", "Tips", "Uang Harian", "Bonus Cust.", "Total Pendapatan"]
    baris_riwayat = [[
        _sel(r["nama_barber"]), _sel(str(r["jumlah_service"])), _sel(_rupiah(r["total_komisi"])),
        _sel(_rupiah(r["tips"])), _sel(_rupiah(r["uang_harian"])), _sel(_rupiah(r["bonus_customer"])),
        _sel(_rupiah(r["total_pendapatan"])),
    ] for r in riwayat]

    data = komisi_penyesuaian_db.get_penyesuaian_list(barber_id=barber_id, tahun=tahun, bulan=bulan, jenis=jenis,
                                                        tenant_id=tenant_id)
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
                                 ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


def buat_pdf_reimburse_list(barber_id: int | None, status: str | None, tahun: int | None, bulan: int | None,
                             dicetak_oleh: str, tenant_id: int | None = None) -> bytes:
    """Sama seperti _laporan_reimburse() (Setting > Backup), tapi filter
    tahun/bulan+status persis filter halaman Reimburse (BUKAN rentang
    tanggal bebas)."""
    data = reimburse_db.get_reimburse_list(barber_id=barber_id, status=status, tahun=tahun, bulan=bulan,
                                            tenant_id=tenant_id)
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
                        col_widths=_LEBAR_KOLOM_REIMBURSE, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


# Lebar kolom Laporan Izin & Cuti (mm), total 194mm -- Barber/Jenis/Mulai/
# Selesai/Alasan/Status, mengikuti tabel pages/izin_cuti.js apa adanya.
_LEBAR_KOLOM_IZIN_CUTI = [30 * mm, 16 * mm, 20 * mm, 20 * mm, 84 * mm, 24 * mm]


def buat_pdf_izin_cuti_list(barber_id: int | None, jenis: str | None, status: str | None, dicetak_oleh: str,
                             tenant_id: int | None = None) -> bytes:
    """Halaman Izin & Cuti TIDAK punya filter tanggal/bulan/tahun sama
    sekali (lihat pages/izin_cuti.js) -- Periode selalu "Semua Periode"."""
    data = izin_cuti_db.get_pengajuan_list(barber_id=barber_id, status=status, jenis=jenis, tenant_id=tenant_id)
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
                        col_widths=_LEBAR_KOLOM_IZIN_CUTI, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


# Lebar kolom Laporan Pemasukan/Pengeluaran (mm), total 194mm -- Tanggal/
# Kategori/Keterangan/Barber/Nominal/Status, mengikuti tabel pages/
# pemasukan.js & pages/pengeluaran.js apa adanya (BEDA dari
# _LEBAR_KOLOM_PENGELUARAN_TAB_REKAP di atas yang tidak punya kolom Status).
_LEBAR_KOLOM_PEMASUKAN_PENGELUARAN_HALAMAN = [20 * mm, 26 * mm, 70 * mm, 26 * mm, 24 * mm, 28 * mm]


def buat_pdf_pemasukan_list(tahun: int, bulan: int, kategori: str | None, cari: str | None, dicetak_oleh: str,
                             tenant_id: int | None = None) -> bytes:
    data = pemasukan_db.get_pemasukan_list(tahun=tahun, bulan=bulan, kategori=kategori, cari=cari,
                                            tenant_id=tenant_id)
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
                        col_widths=_LEBAR_KOLOM_PEMASUKAN_PENGELUARAN_HALAMAN, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


def buat_pdf_pengeluaran_list(tahun: int, bulan: int, kategori: str | None, cari: str | None, dicetak_oleh: str,
                               tenant_id: int = None) -> bytes:
    data = pengeluaran_db.get_pengeluaran_list(tahun=tahun, bulan=bulan, kategori=kategori, cari=cari,
                                                tenant_id=tenant_id)
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
                        col_widths=_LEBAR_KOLOM_PEMASUKAN_PENGELUARAN_HALAMAN, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


# Lebar kolom Laporan Uang Kas (mm), total 194mm -- Tanggal/Jenis/Jumlah/
# Keterangan/Saldo Berjalan.
_LEBAR_KOLOM_UANG_KAS = [24 * mm, 20 * mm, 28 * mm, 82 * mm, 40 * mm]


def buat_pdf_uang_kas_list(tahun: int | None, bulan: int | None, dicetak_oleh: str,
                            tenant_id: int | None = None) -> bytes:
    """Saldo Berjalan dihitung di PYTHON (bukan SQL) saat iterasi baris
    SECARA KRONOLOGIS (tertua dulu, kebalikan dari get_penyesuaian_list()
    yang defaultnya terbaru dulu -- ledger yang menunjukkan saldo berjalan
    HARUS dibaca kronologis), mulai dari Saldo Kas Awal -- konsisten
    dengan uang_kas_db.get_saldo_kas()."""
    data = list(reversed(uang_kas_db.get_penyesuaian_list(tahun=tahun, bulan=bulan, tenant_id=tenant_id)))
    saldo_awal = uang_kas_db.get_saldo_awal(tenant_id)["saldo"]
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
                        col_widths=_LEBAR_KOLOM_UANG_KAS, ringkasan_tambahan=ringkasan_tambahan, tenant_id=tenant_id)


# Lebar kolom Riwayat Mutasi Produk (mm), total 194mm -- Tanggal/Produk/
# Tipe/Jumlah/Sisa Stok/Catatan (SAMA PERSIS kolom yang tampil di layar,
# lihat produk.js loadRiwayat()).
_LEBAR_KOLOM_MUTASI_PRODUK = [22 * mm, 40 * mm, 20 * mm, 20 * mm, 22 * mm, 70 * mm]
_MUTASI_TIPE_LABEL = {"restock": "Restock", "jual": "Jual", "tester": "Tester"}


def buat_pdf_mutasi_produk(produk_id: int | None, tipe: str | None, tahun: int | None, bulan: int | None,
                            dicetak_oleh: str, tenant_id: int | None = None) -> bytes:
    """Cetak PDF Riwayat Mutasi Produk -- kolom dan datanya SENGAJA sumbernya
    SAMA PERSIS dengan tabel di layar (db.get_mutasi_produk_list(), lihat
    docstring-nya untuk arti kolom `sisa_stok`), memakai filter yang sama
    (produk/tipe/tahun/bulan, tahun/bulan OPSIONAL -- sama seperti
    GET /mutasi -- meski tombol Cetak PDF di produk.js selalu mengisi
    keduanya) supaya PDF yang dicetak selalu identik dengan apa yang sedang
    tampil di halaman Produk saat tombol itu ditekan."""
    data = db.get_mutasi_produk_list(produk_id=produk_id, tipe=tipe, tahun=tahun, bulan=bulan, tenant_id=tenant_id)
    header = ["Tanggal", "Produk", "Tipe", "Jumlah", "Sisa Stok", "Catatan"]
    baris = [[
        _sel(m["tanggal"]), _sel(m["nama_produk"]), _sel(_MUTASI_TIPE_LABEL.get(m["tipe"], m["tipe"])),
        _sel(m["jumlah"]), _sel(m["sisa_stok"]), _sel(m.get("catatan") or "-"),
    ] for m in data]
    periode = _periode_text_opsional(tahun, bulan)
    return _bangun_pdf("Riwayat Mutasi Produk", periode, dicetak_oleh, header, baris,
                        col_widths=_LEBAR_KOLOM_MUTASI_PRODUK, tenant_id=tenant_id)
