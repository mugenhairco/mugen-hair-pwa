"""
test_produk_pdf.py — Booking UI/UX #1 lanjutan (Branding Rivoir): Cetak PDF Produk
=============================================================================
Cakupan:
1. get_mutasi_produk_list() menyertakan kolom `sisa_stok` (stok TERKINI
   produk itu, bukan saldo berjalan -- sama seperti kolom "Sisa Stok" di
   get_produk_list(), lihat docstring-nya).
2. GET /api/produk/mutasi/pdf menghasilkan PDF dengan kolom Tanggal/Produk/
   Tipe/Jumlah/Sisa Stok/Catatan, isinya SAMA PERSIS dengan data tabel
   (diverifikasi dengan membaca teks PDF asli, pola sama seperti
   test_maintenance_pdf_dan_urutan.py)."""

import io

import database as db


def _teks_pdf(konten: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(konten))
    return "\n".join(p.extract_text() for p in reader.pages)


def test_mutasi_produk_list_sisa_stok_stok_terkini(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    produk_id = db.tambah_produk("MT Sampo", 10000, 20000, tenant_id=tenant_id)

    db.restock_produk(produk_id, "2026-07-01", 50, None)
    db.jual_produk(produk_id, "2026-07-05", 10, "Jual eceran")

    mutasi = db.get_mutasi_produk_list(produk_id=produk_id, tenant_id=tenant_id)
    stok_terkini = db.get_stok_produk(produk_id)
    assert stok_terkini == 40
    # SEMUA baris (restock maupun jual) menampilkan stok TERKINI yang sama,
    # bukan saldo berjalan pada tanggal masing-masing baris.
    assert all(m["sisa_stok"] == stok_terkini for m in mutasi)


def test_mutasi_produk_list_sisa_stok_per_produk_terpisah(single_tenant):
    """Dua produk berbeda tidak boleh saling memengaruhi sisa_stok satu
    sama lain (cache per produk_id di get_mutasi_produk_list())."""
    tenant_id = single_tenant["tenant_id"]
    id_a = db.tambah_produk("MT Sampo A", 10000, 20000, tenant_id=tenant_id)
    id_b = db.tambah_produk("MT Sampo B", 10000, 20000, tenant_id=tenant_id)
    db.restock_produk(id_a, "2026-07-01", 30, None)
    db.restock_produk(id_b, "2026-07-01", 99, None)

    mutasi = db.get_mutasi_produk_list(tenant_id=tenant_id)
    sisa = {m["produk_id"]: m["sisa_stok"] for m in mutasi}
    assert sisa[id_a] == 30
    assert sisa[id_b] == 99


def test_pdf_mutasi_produk_kolom_dan_data_sama_dengan_tabel(single_tenant):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    # Feature Gating "export_pdf" (FONDASI Multi-Tenant Phase 4 lanjutan):
    # endpoint PDF di bawah SEKARANG digerbang require_feature("export_pdf")
    # -- single_tenant sengaja TIDAK punya baris tenant_subscriptions (lihat
    # conftest.py), jadi tanpa baris ini akan 403. Tenant SUNGGUHAN selalu
    # dapat baris ini otomatis (routers/superadmin.py::buat_tenant()).
    import subscription_db
    subscription_db.create_default_subscription(tenant_id)
    produk_id = db.tambah_produk("MT Pomade", 15000, 35000, tenant_id=tenant_id)
    db.restock_produk(produk_id, "2026-07-02", 20, "Restock awal")
    db.jual_produk(produk_id, "2026-07-10", 3, "Jual ke pelanggan")
    db.tester_produk(produk_id, "2026-07-11", 1, None)

    # Data tabel (endpoint yang sama dipakai layar).
    tabel = client.get("/api/produk/mutasi?tahun=2026&bulan=7", headers=headers).json()
    assert len(tabel) == 3
    stok_terkini = db.get_stok_produk(produk_id)
    assert stok_terkini == 16  # 20 - 3 - 1

    r = client.get("/api/produk/mutasi/pdf?tahun=2026&bulan=7", headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    teks = _teks_pdf(r.content)

    assert "Riwayat Mutasi Produk" in teks
    assert "Tanggal" in teks and "Produk" in teks and "Tipe" in teks
    assert "Jumlah" in teks and "Sisa Stok" in teks and "Catatan" in teks

    assert "MT Pomade" in teks
    assert "Restock" in teks
    assert "Jual" in teks
    assert "Tester" in teks
    assert "Restock awal" in teks
    assert "Jual ke pelanggan" in teks
    # Sisa Stok yang dicetak (stok terkini) harus sama dengan yang dipakai layar.
    assert str(stok_terkini) in teks


def test_pdf_mutasi_produk_filter_tipe_dan_produk(single_tenant):
    """PDF mengikuti filter produk_id/tipe yang sama seperti tabel -- hanya
    baris yang lolos filter yang boleh muncul."""
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    # Feature Gating "export_pdf": lihat catatan sama di test di atas.
    import subscription_db
    subscription_db.create_default_subscription(tenant_id)
    id_a = db.tambah_produk("MT Shampoo Only", 10000, 20000, tenant_id=tenant_id)
    id_b = db.tambah_produk("MT Wax Excluded", 10000, 20000, tenant_id=tenant_id)
    db.restock_produk(id_a, "2026-07-01", 10, None)
    db.restock_produk(id_b, "2026-07-01", 10, None)
    db.jual_produk(id_a, "2026-07-02", 2, None)

    r = client.get(f"/api/produk/mutasi/pdf?tahun=2026&bulan=7&produk_id={id_a}&tipe=jual", headers=headers)
    assert r.status_code == 200, r.text
    teks = _teks_pdf(r.content)
    assert "MT Shampoo Only" in teks
    assert "MT Wax Excluded" not in teks
    assert "Restock" not in teks
    assert "Jual" in teks
