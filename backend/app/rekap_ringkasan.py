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

Kolom Keterangan (`keterangan`, REDESIGN Rapikan PDF -- contoh gambar
disetujui Owner): dikembalikan sebagai DICT terkelompok per kategori
({"catatan": [...], "kasbon": [...], "reimburse": [...], "libur": [...]})
-- BUKAN lagi list string pre-format satu baris per info. laporan_pdf.py
(lewat _sel_keterangan()) yang menentukan cara menampilkannya (label
kategori ditebalkan sekali, Kasbon/Reimburse digabung satu baris dipisah
koma, tanggal Libur SEBANYAK APA PUN digabung jadi satu baris ringkas) --
file ini murni mengumpulkan datanya per kategori, tidak tahu soal tata
letak PDF sama sekali. `libur` berisi tanggal ISO mentah (BUKAN sudah
diformat Indonesia) -- pemformatan tanggal jadi urusan laporan_pdf.py."""


def _rupiah(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


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
                "_tanggal_uang_harian_dihitung": set(),  # MAINTENANCE #1: lihat catatan di bawah
                # REDESIGN PDF Rekap Detail/Ringkasan (tabel Non-Barber
                # terpisah dari Barber, contoh gambar disetujui Owner):
                # dijumlah lintas periode Non-Barber (satu karyawan bisa
                # punya lebih dari satu baris data_non_barber dalam rentang
                # yang dipilih) -- laporan_pdf.py yang menampilkannya,
                # file ini murni menjumlahkan apa adanya.
                "nb_hari_masuk": 0,
                "nb_hari_libur": 0,
                "nb_bonus": 0,
                "nb_potongan": 0,
            }
            urutan.append(bid)
        acc = ringkas[bid]
        if r.get("jabatan") and not acc["jabatan"]:
            acc["jabatan"] = r["jabatan"]

        tipe = r["tipe"]
        if tipe == "transaksi":
            acc["jumlah_transaksi"] += 1
            acc["jumlah_service"] += r["jumlah_service"]
            # MAINTENANCE #1 (bugfix): Uang Harian adalah nominal PER HARI
            # (bukan per transaksi, lihat database.py::hitung_uang_harian_
            # per_hari()) -- get_rekap_transaksi_list() menempelkan nilai
            # HARI itu apa adanya ke SETIAP baris transaksi hari itu (kalau
            # barber dicatat lebih dari sekali di hari yang sama, semua baris
            # hari itu membawa angka yang SAMA). Menjumlahkannya per-baris
            # (perilaku SEBELUMNYA) melipatgandakan Uang Harian sebanyak
            # jumlah transaksi hari itu -- di-dedup per (barber, tanggal) di
            # sini supaya HANYA dihitung SEKALI per hari, apa pun jumlah
            # transaksinya hari itu.
            if r["tanggal"] not in acc["_tanggal_uang_harian_dihitung"]:
                acc["uang_harian"] += r["uang_harian"]
                acc["_tanggal_uang_harian_dihitung"].add(r["tanggal"])
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
            acc["nb_hari_masuk"] += r.get("nb_hari_masuk", 0)
            acc["nb_hari_libur"] += r.get("nb_hari_libur", 0)
            acc["nb_bonus"] += r.get("nb_bonus", 0)
            acc["nb_potongan"] += r.get("nb_potongan", 0)
            if (r.get("catatan") or "").strip():
                acc["catatan_list"].append(r["catatan"].strip())

    hasil = []
    for bid in urutan:
        acc = ringkas[bid]
        daftar_service = ", ".join(f"{nama} x{jml}" for nama, jml in acc["layanan"].items())
        # MAINTENANCE #1 (bugfix): "total" SEBELUMNYA tidak menyertakan
        # acc["uang_harian"] sama sekali -- kolom "Total" per baris di tabel
        # jadi diam-diam lebih kecil dari seharusnya kalau karyawan itu dapat
        # Uang Harian periode itu (uang_harian TETAP ditampilkan sebagai
        # kolomnya sendiri di tabel, jadi ketidaksesuaian ini terlihat kalau
        # dijumlah manual oleh pengguna).
        total = acc["pendapatan"] + acc["uang_harian"] + acc["gaji_non_barber"] + acc["reimburse"] - acc["kasbon_dibayar"]

        # Keterangan: dikelompokkan per kategori (dict) -- lihat docstring
        # modul di atas. Tanggal Libur dikirim MENTAH (ISO, urut) supaya
        # laporan_pdf.py bebas meringkasnya (mis. "3, 10, 12 November 2026")
        # tanpa file ini perlu tahu format tampilannya.
        keterangan = {
            "catatan": list(acc["catatan_list"]),
            "kasbon": [_rupiah(jumlah) for jumlah in acc["kasbon_ket_list"]],
            "reimburse": [
                f"{kategori} {_rupiah(jumlah)}".replace("  ", " ").strip()
                for kategori, jumlah in acc["reimburse_ket_list"]
            ],
            "libur": sorted(acc["libur_list"]),
        }

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
            "nb_hari_masuk": acc["nb_hari_masuk"],
            "nb_hari_libur": acc["nb_hari_libur"],
            "nb_bonus": acc["nb_bonus"],
            "nb_potongan": acc["nb_potongan"],
            "total": total,
            "keterangan": keterangan,
        })
    hasil.sort(key=lambda r: r["nama_barber"])
    return hasil
