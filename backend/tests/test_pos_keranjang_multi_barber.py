"""test_pos_keranjang_multi_barber.py -- FITUR Keranjang Multi-Barber POS
=============================================================================
PERMINTAAN Owner: satu checkout/satu kali pembayaran Point of Sale sekarang
bisa mencakup BEBERAPA barber sekaligus (mis. anak cukur Barber A, bapak
cukur Barber B, bayar satu kali scan), DAN satu barber bisa dapat beberapa
customer dengan service yang sama dalam satu checkout (qty > 1 lewat
mengulang service_id yang sama). Tips sekarang manual diisi kasir PER
BARBER (bukan dihitung/dibagi otomatis sistem), ikut masuk total yang
ditagihkan. Lihat pos_db.py::buat_transaksi()/_lengkapi() untuk desain
lengkapnya."""

import database as db
import pos_db


def test_keranjang_lintas_barber_satu_pembayaran_rekap_tetap_1_baris_per_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber A", tenant_id=tenant_id)
    barber_b = db.add_barber("Barber B", tenant_id=tenant_id)
    svc_dry = db.add_service("Dry Cut Smoke", 50000, tenant_id=tenant_id)

    # KASUS 1: anak (Barber A) + bapak (Barber B), 1x pembayaran,
    # tips manual per barber (barber A dikasih tips, barber B tidak).
    pos = pos_db.buat_transaksi(
        tenant_id,
        jasa_items=[
            {"barber_id": barber_a, "service_ids": [svc_dry], "tips": 10000},
            {"barber_id": barber_b, "service_ids": [svc_dry], "tips": 0},
        ],
        produk_items=[], metode_pembayaran="qris", dibuat_oleh="smoke",
    )
    assert pos["total_harga"] == 50000 + 50000 + 10000
    pos = pos_db.verifikasi_manual(pos["id"], tenant_id)
    assert pos["status"] == "lunas"

    tanggal = pos["tanggal"]
    rekap_a = db.get_transaksi_list(tahun=int(tanggal[:4]), bulan=int(tanggal[5:7]), barber_id=barber_a, tenant_id=tenant_id)
    rekap_b = db.get_transaksi_list(tahun=int(tanggal[:4]), bulan=int(tanggal[5:7]), barber_id=barber_b, tenant_id=tenant_id)
    assert len(rekap_a) == 1
    assert len(rekap_b) == 1
    assert rekap_a[0]["tips"] == 10000
    assert rekap_b[0]["tips"] == 0

    # KASUS 2: anak + bapak SAMA-SAMA Barber A, service sama (2x Dry Cut),
    # 1x pembayaran -- Rekap Barber A harus TETAP 1 baris (digabung dengan
    # transaksi pertama), tips terakumulasi.
    pos2 = pos_db.buat_transaksi(
        tenant_id,
        jasa_items=[{"barber_id": barber_a, "service_ids": [svc_dry, svc_dry], "tips": 5000}],
        produk_items=[], metode_pembayaran="qris", dibuat_oleh="smoke",
    )
    assert pos2["total_harga"] == 50000 * 2 + 5000
    pos2 = pos_db.verifikasi_manual(pos2["id"], tenant_id)
    rekap_a2 = db.get_transaksi_list(tahun=int(tanggal[:4]), bulan=int(tanggal[5:7]), barber_id=barber_a, tenant_id=tenant_id)
    assert len(rekap_a2) == 1
    assert rekap_a2[0]["tips"] == 10000 + 5000

    hari_ini = pos_db.get_transaksi_hari_ini(tenant_id, tanggal)
    assert len(hari_ini["service"]) == 3  # pos1->A, pos1->B, pos2->A
    for item in hari_ini["service"]:
        assert "pos_id" in item


def test_hapus_transaksi_lunas_rebuild_rekap_dan_kembalikan_stok(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber C", tenant_id=tenant_id)
    svc_dry = db.add_service("Dry Cut Smoke 2", 50000, tenant_id=tenant_id)
    produk_id = db.tambah_produk("Pomade Smoke", 10000, 20000, tenant_id=tenant_id)
    db.restock_produk(produk_id, "2020-01-01", 50)

    stok_awal = db.get_stok_produk(produk_id)

    pos1 = pos_db.buat_transaksi(
        tenant_id, jasa_items=[{"barber_id": barber_a, "service_ids": [svc_dry], "tips": 10000}],
        produk_items=[], metode_pembayaran="qris", dibuat_oleh="smoke",
    )
    pos1 = pos_db.verifikasi_manual(pos1["id"], tenant_id)
    tanggal = pos1["tanggal"]

    pos2 = pos_db.buat_transaksi(
        tenant_id,
        jasa_items=[{"barber_id": barber_a, "service_ids": [svc_dry], "tips": 0}],
        produk_items=[{"produk_id": produk_id, "jumlah": 3}],
        metode_pembayaran="qris", dibuat_oleh="smoke",
    )
    pos2 = pos_db.verifikasi_manual(pos2["id"], tenant_id)
    assert db.get_stok_produk(produk_id) == stok_awal - 3

    # Hapus pos2 (yang ada produknya) -- stok harus kembali, Rekap Barber A
    # ter-rebuild tanpa transaksi pos2 (tips kembali ke 10000 saja).
    pos_db.hapus_transaksi_lunas(pos2["id"], tenant_id)
    assert db.get_stok_produk(produk_id) == stok_awal

    rekap_a = db.get_transaksi_list(tahun=int(tanggal[:4]), bulan=int(tanggal[5:7]), barber_id=barber_a, tenant_id=tenant_id)
    assert len(rekap_a) == 1
    assert rekap_a[0]["tips"] == 10000

    hari_ini = pos_db.get_transaksi_hari_ini(tenant_id, tanggal)
    assert len(hari_ini["service"]) == 1
    assert len(hari_ini["produk"]) == 0


def test_endpoint_batalkan_pos_antisipasi_kasir_salah_input(single_tenant):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber E", tenant_id=tenant_id)
    svc = db.add_service("Dry Cut Smoke 4", 50000, tenant_id=tenant_id)

    r_buat = client.post("/api/pos/transaksi", headers=headers, json={
        "jasa_items": [{"barber_id": barber_a, "service_ids": [svc], "tips": 0}],
        "produk_items": [], "metode_pembayaran": "qris",
    })
    assert r_buat.status_code == 200, r_buat.text
    pos_id = r_buat.json()["id"]
    assert r_buat.json()["status"] == "menunggu"

    r_batal = client.post(f"/api/pos/transaksi/{pos_id}/batalkan", headers=headers)
    assert r_batal.status_code == 200, r_batal.text
    assert r_batal.json()["status"] == "batal"

    # No-op kalau dipanggil lagi (sudah 'batal', bukan 'menunggu')
    r_batal2 = client.post(f"/api/pos/transaksi/{pos_id}/batalkan", headers=headers)
    assert r_batal2.status_code == 200, r_batal2.text
    assert r_batal2.json()["status"] == "batal"

    # Transaksi yang dibatalkan TIDAK PERNAH ikut Rekap sama sekali
    tanggal = r_buat.json()["tanggal"]
    rekap = db.get_transaksi_list(tahun=int(tanggal[:4]), bulan=int(tanggal[5:7]), barber_id=barber_a, tenant_id=tenant_id)
    assert len(rekap) == 0


def test_hapus_transaksi_lunas_tolak_yang_belum_lunas(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber D", tenant_id=tenant_id)
    svc_dry = db.add_service("Dry Cut Smoke 3", 50000, tenant_id=tenant_id)
    pos = pos_db.buat_transaksi(
        tenant_id, jasa_items=[{"barber_id": barber_a, "service_ids": [svc_dry]}],
        produk_items=[], metode_pembayaran="qris", dibuat_oleh="smoke",
    )
    assert pos["status"] == "menunggu"
    try:
        pos_db.hapus_transaksi_lunas(pos["id"], tenant_id)
        assert False, "harus ditolak -- transaksi belum lunas"
    except ValueError as e:
        assert "lunas" in str(e).lower()
