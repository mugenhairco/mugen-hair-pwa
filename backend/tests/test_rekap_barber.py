"""
test_rekap_barber.py — BUGFIX Rekap Transaksi/Bulanan (KHUSUS tampilan Barber)
=============================================================================
Cakupan (lihat catatan lengkap di database.py::get_rekap_transaksi_list(),
routers/rekap.py, laporan_pdf.py::buat_pdf_rekap_transaksi(), dan
frontend/app/js/pages/rekap.js):
1. Field "komisi" baru pada baris tipe="transaksi" (get_rekap_transaksi_list) --
   TIDAK mengubah field "pendapatan" yang sudah ada sama sekali.
2. Endpoint /api/rekap/transaksi meneruskan field itu apa adanya.
3. buat_pdf_rekap_transaksi(is_barber=True) TIDAK error & menambah kolom
   Komisi + memindah Pendapatan jadi kolom terakhir sebelum Ket, SEDANGKAN
   is_barber=False (default, dipakai Owner/Admin) TIDAK berubah sama sekali
   dari sebelumnya (regresi)."""

import database as db
import laporan_pdf


def _siapkan_uang_harian(tenant_id, service_id, target=1):
    db.set_uang_harian_acuan_ids([service_id], tenant_id=tenant_id)
    db.set_setting("uang_harian_target_service_harian", str(target), tenant_id=tenant_id)


def test_get_rekap_transaksi_list_punya_field_komisi_terpisah_dari_pendapatan(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Romen", uang_harian=60000, tenant_id=tenant_id)
    service_id = db.add_service("RB Dry Cut", 35000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, service_id)

    db.tambah_transaksi("2026-08-04", barber_id, [{"service_id": service_id, "jumlah": 1}], tips=50000)

    rows = db.get_rekap_transaksi_list(tahun=2026, bulan=8, barber_id=barber_id, tenant_id=tenant_id)
    assert len(rows) == 1
    r = rows[0]
    assert r["tipe"] == "transaksi"
    # Komisi = 40% dari 35000 (modal 0) = 14000.
    assert r["komisi"] == 14000
    # "pendapatan" TETAP komisi+tips apa adanya (TIDAK diubah -- dipakai
    # Owner/Admin & PDF lama tanpa perubahan sama sekali).
    assert r["pendapatan"] == 14000 + 50000


def test_api_rekap_transaksi_sebagai_barber_meneruskan_field_komisi(single_tenant):
    client = single_tenant["client"]
    tenant_id = single_tenant["tenant_id"]
    import auth_db

    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Romen", uang_harian=60000, tenant_id=tenant_id)
    service_id = db.add_service("RB2 Dry Cut", 35000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, service_id)
    db.tambah_transaksi("2026-08-04", barber_id, [{"service_id": service_id, "jumlah": 1}], tips=0)

    auth_db.tambah_user("romen_login", "password123", role="barber", barber_id=barber_id, tenant_id=tenant_id)
    r = client.post("/api/auth/login", json={"username": "romen_login", "password": "password123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r2 = client.get("/api/rekap/transaksi?tahun=2026&bulan=8", headers=headers)
    assert r2.status_code == 200
    data = r2.json()
    assert len(data) == 1
    assert data[0]["komisi"] == 14000


def test_pdf_rekap_transaksi_is_barber_true_tidak_error_dan_landscape(single_tenant):
    """is_barber=True (dipakai routers/rekap.py saat role akun == 'barber')
    HARUS berhasil membangun PDF (tidak melempar reportlab LayoutError akibat
    kolom terlalu sempit) -- dicetak landscape (lebar > tinggi, lihat
    _LEBAR_KOLOM_REKAP_TRANSAKSI_BARBER)."""
    import re

    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Romen", uang_harian=60000, tenant_id=tenant_id)
    s1 = db.add_service("RB3 Dry Cut", 35000, tenant_id=tenant_id)
    s2 = db.add_service("RB3 Cut & Wash", 45000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, s1)
    db.tambah_transaksi("2026-08-04", barber_id,
                         [{"service_id": s1, "jumlah": 1}, {"service_id": s2, "jumlah": 3}], tips=50000)

    konten = laporan_pdf.buat_pdf_rekap_transaksi(2026, 8, None, "tester", tenant_id=tenant_id, is_barber=True)
    assert konten[:4] == b"%PDF"
    m = re.search(rb"/MediaBox\s*\[([^\]]+)\]", konten)
    assert m is not None
    lebar, tinggi = [float(x) for x in m.group(1).split()[2:4]]
    assert lebar > tinggi, "PDF Rekap Transaksi Barber harus landscape supaya header kolom tidak terpotong"


def test_pdf_rekap_transaksi_is_barber_false_default_tidak_berubah(single_tenant):
    """Regresi: PARAMETER is_barber default False -- pemanggil lama (Owner/
    Admin, tidak pernah mengisi parameter ini) HARUS tetap dapat PDF potret
    apa adanya, tidak ada perubahan sama sekali dari sebelum fitur ini ada."""
    import re

    tenant_id = single_tenant["tenant_id"]
    db.set_setting("persentase_komisi", "40", tenant_id=tenant_id)
    barber_id = db.add_barber("Romen", uang_harian=60000, tenant_id=tenant_id)
    service_id = db.add_service("RB4 Dry Cut", 35000, tenant_id=tenant_id)
    _siapkan_uang_harian(tenant_id, service_id)
    db.tambah_transaksi("2026-08-04", barber_id, [{"service_id": service_id, "jumlah": 1}], tips=0)

    konten = laporan_pdf.buat_pdf_rekap_transaksi(2026, 8, None, "tester", tenant_id=tenant_id)
    assert konten[:4] == b"%PDF"
    m = re.search(rb"/MediaBox\s*\[([^\]]+)\]", konten)
    lebar, tinggi = [float(x) for x in m.group(1).split()[2:4]]
    assert lebar < tinggi, "PDF Rekap Transaksi Owner/Admin (default) harus TETAP potret, tidak berubah"
