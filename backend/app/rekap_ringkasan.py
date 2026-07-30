"""
rekap_ringkasan.py — "Rekap Periode (Ringkasan)" untuk PDF Rekap Transaksi
=============================================================================
Jenis laporan BARU di menu Rekap Transaksi (Perbaikan Alur Cetak PDF):
- "Rekap Detail" (format lama, TIDAK diubah sama sekali) -- satu baris per
  transaksi/hari, lihat laporan_pdf.buat_pdf_rekap_transaksi().
- "Rekap Periode (Ringkasan)" (BARU, file ini) -- satu baris per karyawan
  untuk SELURUH periode yang dipilih, seluruh service/pelanggan/tips/uang
  harian/pendapatan/kasbon/reimburse/gaji Non-Barber diakumulasi jadi satu
  hasil akhir per karyawan.

PENTING: file ini TIDAK menghitung ulang satu angka pun sendiri -- murni
MENJUMLAHKAN baris yang SUDAH ADA (hasil database.get_rekap_transaksi_list()
+ reimburse_db/kasbon_db/data_non_barber_db.gabung_ke_rekap_transaksi(),
persis apa yang dipakai tampilan layar & Rekap Detail apa adanya), supaya
logika perhitungan Barber/Non-Barber yang sudah ada tidak tersentuh sama
sekali (sesuai permintaan).

Kolom Keterangan (`keterangan_list`, REVISI): dikembalikan sebagai LIST
baris teks TERPISAH (bukan satu string gabungan) -- satu baris per info
(Catatan/Kasbon/Reimburse/Libur), urut per kategori lalu tanggal, supaya
tampilan (laporan_pdf.py, lewat _sel_keterangan()) bisa menaruh tiap info
di baris terpisah, TIDAK digabung koma/titik-koma jadi satu baris."""

_NAMA_BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
               "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def _rupiah(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


def _tanggal_indo(iso: str) -> str:
    tahun, bulan, hari = iso.split("-")
    return f"{int(hari)} {_NAMA_BULAN[int(bulan)]} {int(tahun)}"


def ringkas_per_karyawan(baris: list) -> list:
    """`baris` = hasil gabungan lengkap (tipe: transaksi/libur/reimburse/
    kasbon/non_barber, lihat database.py & masing-masing modul
    gabung_ke_rekap_transaksi()). Return satu baris per barber_id, urut nama."""
    ringkas = {}
    urutan = []
    for r in baris:
        bid = r["barber_id"]
        if bid not in ringkas:
            ringkas[bid] = {
                "barber_id": bid,
                "nama_barber": r["nama_barber"],
                "jabatan": r.get("jabatan"),
                "jumlah_transaksi": 0,
                "jumlah_service": 0,
                "layanan": {},  # nama_service -> total qty (dari string "Nama xN" yang sudah ada)
                "hari_libur": 0,
                "uang_harian": 0,
                "tips": 0,
                "pendapatan": 0,
                "reimburse": 0,
                "kasbon_dibayar": 0,
                "gaji_non_barber": 0,
                "catatan_list": [],     # teks catatan Input Data (transaksi & Non-Barber)
                "kasbon_ket_list": [],  # jumlah tiap pembayaran kasbon (int)
                "reimburse_ket_list": [],  # (kategori, jumlah) tiap klaim
                "libur_list": [],       # tanggal ISO tiap hari libur
            }
            urutan.append(bid)
        acc = ringkas[bid]
        if r.get("jabatan") and not acc["jabatan"]:
            acc["jabatan"] = r["jabatan"]

        tipe = r["tipe"]
        if tipe == "transaksi":
            acc["jumlah_transaksi"] += 1
            acc["jumlah_service"] += r["jumlah_service"]
            acc["uang_harian"] += r["uang_harian"]
            acc["tips"] += r["tips"]
            acc["pendapatan"] += r["pendapatan"]
            for bagian in (r.get("daftar_service") or "").split(", "):
                bagian = bagian.strip()
                if not bagian or " x" not in bagian:
                    continue
                nama, jml = bagian.rsplit(" x", 1)
                try:
                    jml = int(jml)
                except ValueError:
                    continue
                acc["layanan"][nama] = acc["layanan"].get(nama, 0) + jml
            # Catatan transaksi -- keterangan baris "transaksi" berisi
            # catatan APA ADANYA, KECUALI kebetulan sama harinya dengan
            # libur ("Libur" ikut ditempel di situ, lihat database.py) --
            # dipisah lagi di sini supaya "Libur" tidak dobel dengan baris
            # tipe="libur" yang sudah menghasilkan baris Keterangan sendiri.
            catatan_mentah = (r.get("keterangan") or "").strip()
            for bagian in catatan_mentah.split("; "):
                bagian = bagian.strip()
                if bagian and bagian != "Libur":
                    acc["catatan_list"].append(bagian)
        elif tipe == "libur":
            acc["hari_libur"] += 1
            acc["libur_list"].append(r["tanggal"])
        elif tipe == "reimburse":
            acc["reimburse"] += r["pendapatan"]
            acc["reimburse_ket_list"].append((r.get("kategori") or "", r["pendapatan"]))
        elif tipe == "kasbon":
            jumlah = -r["pendapatan"]  # baris kasbon: pendapatan SUDAH negatif
            acc["kasbon_dibayar"] += jumlah
            acc["kasbon_ket_list"].append(jumlah)
        elif tipe == "non_barber":
            acc["gaji_non_barber"] += r["pendapatan"]
            if (r.get("catatan") or "").strip():
                acc["catatan_list"].append(r["catatan"].strip())

    hasil = []
    for bid in urutan:
        acc = ringkas[bid]
        daftar_service = ", ".join(f"{nama} x{jml}" for nama, jml in acc["layanan"].items())
        total = acc["pendapatan"] + acc["gaji_non_barber"] + acc["reimburse"] - acc["kasbon_dibayar"]

        # Keterangan: satu baris teks PER INFORMASI (bukan digabung jadi
        # satu baris) -- urut kategori: Catatan, lalu Kasbon, lalu
        # Reimburse, lalu Libur (tiap hari libur baris SENDIRI-SENDIRI,
        # urut tanggal), sesuai contoh yang diminta.
        keterangan_list = []
        for c in acc["catatan_list"]:
            keterangan_list.append(f"Catatan: {c}")
        for jumlah in acc["kasbon_ket_list"]:
            keterangan_list.append(f"Kasbon: {_rupiah(jumlah)}")
        for kategori, jumlah in acc["reimburse_ket_list"]:
            label = f"Reimburse: {kategori} {_rupiah(jumlah)}".replace("  ", " ").strip()
            keterangan_list.append(label)
        for tanggal in sorted(acc["libur_list"]):
            keterangan_list.append(f"Libur: {_tanggal_indo(tanggal)}")

        hasil.append({
            "barber_id": acc["barber_id"],
            "nama_barber": acc["nama_barber"],
            "jabatan": acc["jabatan"],
            "jumlah_transaksi": acc["jumlah_transaksi"],
            "jumlah_service": acc["jumlah_service"],
            "daftar_service": daftar_service,
            "hari_libur": acc["hari_libur"],
            "uang_harian": acc["uang_harian"],
            "tips": acc["tips"],
            "pendapatan": acc["pendapatan"],
            "reimburse": acc["reimburse"],
            "kasbon_dibayar": acc["kasbon_dibayar"],
            "gaji_non_barber": acc["gaji_non_barber"],
            "total": total,
            "keterangan_list": keterangan_list,
        })
    hasil.sort(key=lambda r: r["nama_barber"])
    return hasil
