"""
test_maintenance_pdf_dan_urutan.py — FOUNDATION MAINTENANCE #1
=============================================================================
Cakupan:
1. Bugfix PDF: Uang Harian sebelumnya tidak pernah ikut dijumlahkan ke
   "Total Diterima" (Rekap Detail & Rekap Periode Ringkasan) walau
   ditampilkan per-baris -- diverifikasi dengan membaca ISI TEKS PDF asli
   (pypdf), bukan cuma "tidak error", persis pola test_branding.py.
2. Bugfix ganda-hitung: Uang Harian (nominal PER HARI) sebelumnya dijumlah
   PER BARIS TRANSAKSI di rekap_ringkasan.py -- barber dengan 2 transaksi
   di hari yang sama akan mendapat Uang Harian hari itu dihitung 2x.
3. PDF dinamis: baris/ringkasan bernilai 0 tidak ditampilkan sama sekali
   (Rekap Detail/Ringkasan/Slip Gaji).
4. Bugfix pengurutan Layanan: add_service() sekarang mengisi `urutan`
   berurutan (bukan selalu 0), get_services() diurutkan oleh `urutan`
   (bukan alfabetis) sehingga Input Data ikut urutan Setting > Layanan,
   dan migrasi normalisasi tabrakan urutan lama."""

import io

import database as db
import kasbon_db
import reimburse_db
import laporan_pdf
import rekap_ringkasan


def _siapkan_uang_harian(tenant_id, service_id, target=1):
    """Setiap transaksi qty>=target dari `service_id` (dijadikan acuan)
    membuat Uang Harian cair hari itu -- lihat database.py::
    hitung_uang_harian_bulan()."""
    db.set_uang_harian_acuan_ids([service_id], tenant_id=tenant_id)
    db.set_setting("uang_harian_target_service_harian", str(target), tenant_id=tenant_id)


def _teks_pdf(konten: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(konten))
    return "\n".join(p.extract_text() for p in reader.pages)


# ---------------------------------------------------------------------------
# 1 & 3: Rekap Detail (buat_pdf_rekap_transaksi)
# ---------------------------------------------------------------------------

def test_rekap_detail_total_diterima_termasuk_uang_harian(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Budi", uang_harian=50000, tenant_id=tenant_id)
    service_id = db.add_service("MT Dry Cut", 100000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, service_id)

    db.tambah_transaksi("2026-07-01", barber_id, [{"service_id": service_id, "jumlah": 1}], tips=10000)

    konten = laporan_pdf.buat_pdf_rekap_transaksi(2026, 7, None, "tester", tenant_id=tenant_id)
    teks = _teks_pdf(konten)

    komisi = 40000  # 40% dari 100000
    uang_harian = 50000
    tips = 10000
    total_diterima = komisi + uang_harian + tips

    assert f"Komisi: Rp {komisi:,}".replace(",", ".") in teks
    assert f"Uang Harian: Rp {uang_harian:,}".replace(",", ".") in teks
    assert f"Tips: Rp {tips:,}".replace(",", ".") in teks
    assert f"Total Diterima: Rp {total_diterima:,}".replace(",", ".") in teks
    # Dinamis: tidak ada Reimburse/Kasbon sama sekali -> baris itu TIDAK muncul.
    assert "Reimburse:" not in teks
    assert "Kasbon:" not in teks


def test_rekap_detail_dua_transaksi_hari_sama_uang_harian_tidak_dobel(single_tenant):
    """Root cause utama bug ini: Uang Harian adalah nominal PER HARI, bukan
    per transaksi -- barber dengan 2 transaksi di hari yang sama HARUS
    tetap dapat Uang Harian SATU KALI, bukan dua kali."""
    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Budi", uang_harian=50000, tenant_id=tenant_id)
    service_id = db.add_service("MT Dry Cut", 100000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, service_id)

    # DUA transaksi terpisah, tanggal SAMA.
    db.tambah_transaksi("2026-07-01", barber_id, [{"service_id": service_id, "jumlah": 1}])
    db.tambah_transaksi("2026-07-01", barber_id, [{"service_id": service_id, "jumlah": 1}])

    konten = laporan_pdf.buat_pdf_rekap_transaksi(2026, 7, None, "tester", tenant_id=tenant_id)
    teks = _teks_pdf(konten)
    # 2 transaksi -> komisi 40000 x 2 = 80000, TAPI Uang Harian TETAP 50000 (bukan 100000).
    assert "Uang Harian: Rp 50.000" in teks
    assert "Uang Harian: Rp 100.000" not in teks
    assert "Komisi: Rp 80.000" in teks
    assert "Total Diterima: Rp 130.000" in teks  # 80000 + 50000


def test_rekap_detail_dengan_kasbon_dan_reimburse(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Budi", tenant_id=tenant_id)
    service_id = db.add_service("MT Dry Cut", 100000, tenant_id=tenant_id)
    db.tambah_transaksi("2026-07-01", barber_id, [{"service_id": service_id, "jumlah": 1}])

    r = reimburse_db.buat_reimburse(barber_id, "2026-07-02", "Transport", 20000, tenant_id=tenant_id)
    reimburse_db.set_status_reimburse(r["id"], "disetujui")

    k = kasbon_db.buat_kasbon(barber_id, "2026-07-01", 15000, tenant_id=tenant_id)
    kasbon_db.bayar_kasbon(k["id"], "2026-07-03", 15000)

    # Rentang tanggal (bukan tahun/bulan) sengaja dipakai di sini -- get_
    # reimburse_list_disetujui() memfilter dari tanggal_approval (SELALU
    # "hari ini" sungguhan, diisi set_status_reimburse(), TIDAK BISA
    # ditentukan manual), jadi rentang lebar sampai jauh ke depan supaya
    # test ini tidak bergantung tanggal berapa sebenarnya dijalankan.
    konten = laporan_pdf.buat_pdf_rekap_transaksi(None, None, None, "tester",
                                                   tanggal_mulai="2026-07-01", tanggal_selesai="2030-12-31",
                                                   tenant_id=tenant_id)
    teks = _teks_pdf(konten)
    assert "Komisi: Rp 40.000" in teks
    assert "Reimburse: Rp 20.000" in teks
    assert "Kasbon: -Rp 15.000" in teks
    assert "Total Diterima: Rp 45.000" in teks  # 40000 + 20000 - 15000
    assert "Uang Harian:" not in teks  # tidak diatur -> 0 -> tidak tampil
    assert "Tips:" not in teks


def test_rekap_detail_hanya_dry_cut_tanpa_service_lain(single_tenant):
    """Daftar Service pada Rincian HANYA menampilkan service yang
    jumlahnya > 0 (get_rincian_service_periode() sudah begitu sejak awal)."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Budi", tenant_id=tenant_id)
    dry_cut = db.add_service("MT Dry Cut", 35000, tenant_id=tenant_id)
    db.add_service("MT Cut & Wash", 45000, tenant_id=tenant_id)  # tidak pernah dipakai
    db.tambah_transaksi("2026-07-01", barber_id, [{"service_id": dry_cut, "jumlah": 2}])

    konten = laporan_pdf.buat_pdf_rekap_transaksi(2026, 7, None, "tester", tenant_id=tenant_id)
    teks = _teks_pdf(konten)
    assert "MT Dry Cut: 2" in teks
    assert "MT Cut & Wash" not in teks


def test_rekap_detail_tanpa_data_sama_sekali_tidak_error(single_tenant):
    """Periode benar-benar kosong (tidak ada transaksi/libur/reimburse/
    kasbon apa pun) -- _bangun_pdf() (TIDAK diubah pekerjaan ini) menampilkan
    pesan "Tidak ada data" dan TIDAK merender ringkasan sama sekali (baris
    kosong = else branch tidak tereksekusi) -- perilaku pre-existing, bukan
    bagian dari perbaikan ini, cukup dipastikan tidak error/crash."""
    tenant_id = single_tenant["tenant_id"]
    konten = laporan_pdf.buat_pdf_rekap_transaksi(2026, 7, None, "tester", tenant_id=tenant_id)
    teks = _teks_pdf(konten)
    assert "Tidak ada data pada periode ini." in teks


# ---------------------------------------------------------------------------
# 1 & 2 & 3: Rekap Periode (Ringkasan) -- rekap_ringkasan.py + buat_pdf_rekap_transaksi_ringkasan
# ---------------------------------------------------------------------------

def test_rekap_ringkasan_total_diterima_termasuk_uang_harian(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Budi", uang_harian=50000, tenant_id=tenant_id)
    service_id = db.add_service("MT Dry Cut", 100000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, service_id)
    db.tambah_transaksi("2026-07-01", barber_id, [{"service_id": service_id, "jumlah": 1}], tips=5000)

    konten = laporan_pdf.buat_pdf_rekap_transaksi_ringkasan(2026, 7, None, "tester", tenant_id=tenant_id)
    teks = _teks_pdf(konten)
    assert "Uang Harian: Rp 50.000" in teks
    assert "Total Diterima: Rp 95.000" in teks  # 40000 komisi + 50000 uang harian + 5000 tips


def test_rekap_ringkasan_dua_transaksi_hari_sama_uang_harian_tidak_dobel(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Budi", uang_harian=50000, tenant_id=tenant_id)
    service_id = db.add_service("MT Dry Cut", 100000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, service_id)
    db.tambah_transaksi("2026-07-01", barber_id, [{"service_id": service_id, "jumlah": 1}])
    db.tambah_transaksi("2026-07-01", barber_id, [{"service_id": service_id, "jumlah": 1}])

    konten = laporan_pdf.buat_pdf_rekap_transaksi_ringkasan(2026, 7, None, "tester", tenant_id=tenant_id)
    teks = _teks_pdf(konten)
    assert "Rp 100.000" not in teks  # 50000 x 2 TIDAK boleh muncul di mana pun


def test_ringkas_per_karyawan_tidak_dobel_hitung_uang_harian_langsung():
    """Unit test langsung ke rekap_ringkasan.ringkas_per_karyawan() (tanpa
    lewat PDF) -- mengonfirmasi baris "Total" per baris tabel (bukan cuma
    ringkasan grand total di bawahnya) juga benar."""
    baris = [
        {"tipe": "transaksi", "barber_id": 1, "nama_barber": "Budi", "jabatan": "barber",
         "tanggal": "2026-07-01", "jumlah_service": 1, "uang_harian": 50000, "tips": 0,
         "pendapatan": 40000, "daftar_service": "Dry Cut x1", "keterangan": ""},
        {"tipe": "transaksi", "barber_id": 1, "nama_barber": "Budi", "jabatan": "barber",
         "tanggal": "2026-07-01", "jumlah_service": 1, "uang_harian": 50000, "tips": 0,
         "pendapatan": 40000, "daftar_service": "Dry Cut x1", "keterangan": ""},
    ]
    hasil = rekap_ringkasan.ringkas_per_karyawan(baris)
    assert len(hasil) == 1
    assert hasil[0]["uang_harian"] == 50000  # bukan 100000
    assert hasil[0]["pendapatan"] == 80000   # 40000 x 2, per-transaksi memang benar dijumlah
    assert hasil[0]["total"] == 130000       # 80000 pendapatan + 50000 uang harian (dulu hilang dari total)


# ---------------------------------------------------------------------------
# 3: Slip Gaji PDF -- baris bernilai 0 disembunyikan, formula TIDAK berubah
# ---------------------------------------------------------------------------

def _slip_dasar(**override):
    dasar = {
        "nama_barber": "Budi", "tahun": 2026, "bulan": 7, "jumlah_hari_masuk": None,
        "gaji_pokok": 0, "komisi": 100000, "tips": 0, "uang_harian": 0, "bonus_customer": 0,
        "penyesuaian_komisi": 0, "reimburse": 0, "bonus_manual": 0, "potongan_kasbon": 0,
        "potongan_lain": 0, "catatan_potongan": "", "total_diterima": 100000,
        "status": "belum_dibayar", "dibuat_oleh": "tester", "tanggal_dibayar": None,
    }
    dasar.update(override)
    return dasar


def test_slip_gaji_pdf_sembunyikan_komponen_nol():
    konten = laporan_pdf.buat_slip_gaji_pdf(_slip_dasar())
    teks = _teks_pdf(konten)
    assert "Komisi" in teks
    assert "Rp 100.000" in teks  # Komisi & Total Diterima sama-sama 100.000
    # "Gaji" SENGAJA tidak dicek di sini -- substring itu juga muncul di
    # judul dokumen "Slip Gaji" itu sendiri, jadi dicek label baris yang
    # lebih spesifik ("Gaji Pokok"/"Gaji (") di bawah.
    for label in ("Gaji Pokok", "Gaji (", "Tips", "Uang Harian", "Bonus Customer",
                  "Penyesuaian Komisi", "Reimburse", "Bonus Manual",
                  "Potongan Kasbon", "Potongan Lain"):
        assert label not in teks
    assert "Total Diterima: Rp 100.000" in teks  # ringkasan TETAP selalu tampil


def test_slip_gaji_pdf_tampilkan_semua_komponen_yang_terisi():
    slip = _slip_dasar(gaji_pokok=500000, tips=20000, uang_harian=50000, bonus_customer=100000,
                        penyesuaian_komisi=-5000, reimburse=30000, bonus_manual=10000,
                        potongan_kasbon=25000, potongan_lain=15000,
                        total_diterima=500000 + 100000 + 20000 + 50000 + 100000 - 5000 + 30000 + 10000 - 25000 - 15000)
    konten = laporan_pdf.buat_slip_gaji_pdf(slip)
    teks = _teks_pdf(konten)
    for label in ("Gaji Pokok", "Komisi", "Tips", "Uang Harian", "Bonus Customer",
                  "Penyesuaian Komisi", "Reimburse", "Bonus Manual",
                  "Potongan Kasbon", "Potongan Lain"):
        assert label in teks
    # Formula Slip Gaji SENGAJA TIDAK diubah (beda dari Rekap Transaksi) --
    # lihat konfirmasi eksplisit pengguna sebelum pekerjaan ini dimulai.
    assert f"Total Diterima: {laporan_pdf._rupiah(slip['total_diterima'])}" in teks


# ---------------------------------------------------------------------------
# 4: Pengurutan Layanan -- add_service()/get_services()/normalisasi migrasi
# ---------------------------------------------------------------------------

def test_add_service_urutan_berurutan_otomatis(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    id1 = db.add_service("MT Dry Cut", 35000, tenant_id=tenant_id)
    id2 = db.add_service("MT Cut & Wash", 45000, tenant_id=tenant_id)
    id3 = db.add_service("MT Hair Do", 60000, tenant_id=tenant_id)

    layanan = {s["id"]: s["urutan"] for s in db.get_services(hanya_aktif=False, tenant_id=tenant_id)}
    assert layanan[id1] == 0
    assert layanan[id2] == 1
    assert layanan[id3] == 2


def test_get_services_urut_berdasarkan_urutan_bukan_nama(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.add_service("MT Zzz Terakhir Alfabet", 10000, tenant_id=tenant_id)  # urutan=0 (ditambah duluan)
    db.add_service("MT Aaa Duluan Alfabet", 20000, tenant_id=tenant_id)    # urutan=1

    hasil = db.get_services(tenant_id=tenant_id)
    assert [s["nama"] for s in hasil] == ["MT Zzz Terakhir Alfabet", "MT Aaa Duluan Alfabet"]


def test_input_data_services_ikut_urutan_setting(single_tenant):
    """Endpoint /api/input-data/services (dipakai form Input Data) TIDAK
    menyortir ulang sendiri -- HARUS mengikuti urutan dari get_services()."""
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    db.add_service("MT Zzz Terakhir Alfabet", 10000, tenant_id=tenant_id)
    db.add_service("MT Aaa Duluan Alfabet", 20000, tenant_id=tenant_id)

    r = client.get("/api/input-data/services", headers=headers)
    assert r.status_code == 200, r.text
    assert [s["nama"] for s in r.json()] == ["MT Zzz Terakhir Alfabet", "MT Aaa Duluan Alfabet"]


def test_tombol_naik_turun_service_bertukar_urutan_via_http(single_tenant):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    id_a = db.add_service("MT Layanan A", 10000, tenant_id=tenant_id)
    id_b = db.add_service("MT Layanan B", 20000, tenant_id=tenant_id)
    assert [s["nama"] for s in db.get_services(tenant_id=tenant_id)] == ["MT Layanan A", "MT Layanan B"]

    # Simulasikan tombol "↑" pada Layanan B: tukar urutan A<->B (pola yang
    # sama persis dipakai frontend, lihat pages/pengaturan.js renderLayanan()).
    r1 = client.put(f"/api/booking/service/{id_b}/urutan", headers=headers, json={"urutan": 0})
    r2 = client.put(f"/api/booking/service/{id_a}/urutan", headers=headers, json={"urutan": 1})
    assert r1.status_code == 200 and r2.status_code == 200

    assert [s["nama"] for s in db.get_services(tenant_id=tenant_id)] == ["MT Layanan B", "MT Layanan A"]


def test_normalisasi_urutan_service_kolisi_merapikan_tanpa_mengubah_urutan_relatif(single_tenant):
    import booking_form_migrasi
    tenant_id = single_tenant["tenant_id"]

    # Simulasikan data lama (sebelum bugfix) -- beberapa layanan berbagi
    # urutan=0, ditambahkan lewat INSERT langsung (BUKAN add_service() yang
    # sekarang sudah benar) supaya tabrakannya sungguhan.
    with db.get_conn() as conn:
        conn.execute("INSERT INTO services (nama, harga, tenant_id, urutan) VALUES (?, ?, ?, 0)",
                     ("MT Beta", 10000, tenant_id))
        conn.execute("INSERT INTO services (nama, harga, tenant_id, urutan) VALUES (?, ?, ?, 0)",
                     ("MT Alpha", 20000, tenant_id))
        conn.execute("INSERT INTO services (nama, harga, tenant_id, urutan) VALUES (?, ?, ?, 0)",
                     ("MT Charlie", 30000, tenant_id))

    with db.get_conn() as conn:
        booking_form_migrasi._normalisasi_urutan_service_kolisi(conn)

    hasil = db.get_services(hanya_aktif=False, tenant_id=tenant_id)
    urutan_list = [s["urutan"] for s in hasil]
    assert urutan_list == sorted(urutan_list) == [0, 1, 2]
    # Urutan RELATIF dipertahankan (tie-break alfabetis, karena ketiganya
    # sama-sama urutan=0 sebelum dirapikan): Alpha, Beta, Charlie.
    assert [s["nama"] for s in hasil] == ["MT Alpha", "MT Beta", "MT Charlie"]


def test_normalisasi_urutan_service_tidak_menyentuh_yang_sudah_unik(single_tenant):
    """No-op total kalau urutan sudah unik -- Owner yang sudah mengatur
    lewat tombol ↑/↓ tidak boleh melihat urutannya berubah."""
    import booking_form_migrasi
    tenant_id = single_tenant["tenant_id"]
    id_a = db.add_service("MT Sudah Diatur A", 10000, tenant_id=tenant_id)
    id_b = db.add_service("MT Sudah Diatur B", 20000, tenant_id=tenant_id)
    with db.get_conn() as conn:
        conn.execute("UPDATE services SET urutan = 5 WHERE id = ?", (id_a,))
        conn.execute("UPDATE services SET urutan = 2 WHERE id = ?", (id_b,))

    with db.get_conn() as conn:
        booking_form_migrasi._normalisasi_urutan_service_kolisi(conn)

    hasil = {s["id"]: s["urutan"] for s in db.get_services(hanya_aktif=False, tenant_id=tenant_id)}
    assert hasil[id_a] == 5
    assert hasil[id_b] == 2
