"""test_pos_cash_dan_rincian.py -- FITUR Cash di POS + Rincian per Metode
=============================================================================
PERMINTAAN Owner: metode "Cash" sekarang ditawarkan juga di Point of Sale
(kasir input nominal uang diterima, sistem hitung kembalian -- lihat
pos_db.bayar_cash()), dan tab "Transaksi Hari Ini" menampilkan rincian
total per metode pembayaran (Payment Gateway/QRIS manual/Cash, termasuk
tips & produk) + total keseluruhan -- lihat pos_db.get_transaksi_hari_ini()."""

import database as db
import pos_db


def test_bayar_cash_hitung_kembalian_dan_rekap_tetap_benar(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber Cash A", tenant_id=tenant_id)
    svc = db.add_service("Dry Cut Cash 1", 50000, tenant_id=tenant_id)

    pos = pos_db.buat_transaksi(
        tenant_id, jasa_items=[{"barber_id": barber_a, "service_ids": [svc], "tips": 5000}],
        produk_items=[], metode_pembayaran="cash", dibuat_oleh="smoke",
    )
    assert pos["status"] == "menunggu"
    assert pos["total_harga"] == 55000

    try:
        pos_db.bayar_cash(pos["id"], tenant_id, 50000)
        assert False, "harus ditolak -- uang diterima kurang dari total"
    except ValueError as e:
        assert "kurang" in str(e).lower()

    pos = pos_db.bayar_cash(pos["id"], tenant_id, 100000)
    assert pos["status"] == "lunas"
    assert pos["uang_diterima"] == 100000
    assert pos["kembalian"] == 45000

    tanggal = pos["tanggal"]
    rekap = db.get_transaksi_list(tahun=int(tanggal[:4]), bulan=int(tanggal[5:7]), barber_id=barber_a, tenant_id=tenant_id)
    assert len(rekap) == 1
    assert rekap[0]["tips"] == 5000


def test_bayar_cash_tolak_metode_bukan_cash_dan_sudah_lunas(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber Cash B", tenant_id=tenant_id)
    svc = db.add_service("Dry Cut Cash 2", 50000, tenant_id=tenant_id)

    pos_qris = pos_db.buat_transaksi(
        tenant_id, jasa_items=[{"barber_id": barber_a, "service_ids": [svc]}],
        produk_items=[], metode_pembayaran="qris", dibuat_oleh="smoke",
    )
    try:
        pos_db.bayar_cash(pos_qris["id"], tenant_id, 50000)
        assert False, "harus ditolak -- bukan metode cash"
    except ValueError as e:
        assert "cash" in str(e).lower()

    pos_cash = pos_db.buat_transaksi(
        tenant_id, jasa_items=[{"barber_id": barber_a, "service_ids": [svc]}],
        produk_items=[], metode_pembayaran="cash", dibuat_oleh="smoke",
    )
    pos_cash = pos_db.bayar_cash(pos_cash["id"], tenant_id, 50000)
    assert pos_cash["status"] == "lunas"
    try:
        pos_db.bayar_cash(pos_cash["id"], tenant_id, 50000)
        assert False, "harus ditolak -- sudah diproses sebelumnya"
    except ValueError as e:
        assert "sebelumnya" in str(e).lower()


def test_rincian_metode_dan_total_keseluruhan_transaksi_hari_ini(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber Cash C", tenant_id=tenant_id)
    svc = db.add_service("Dry Cut Cash 3", 50000, tenant_id=tenant_id)
    produk_id = db.tambah_produk("Pomade Cash", 10000, 20000, tenant_id=tenant_id)
    db.restock_produk(produk_id, "2020-01-01", 10)

    pos_qris = pos_db.buat_transaksi(
        tenant_id, jasa_items=[{"barber_id": barber_a, "service_ids": [svc], "tips": 5000}],
        produk_items=[{"produk_id": produk_id, "jumlah": 1}],
        metode_pembayaran="qris", dibuat_oleh="smoke",
    )
    pos_qris = pos_db.verifikasi_manual(pos_qris["id"], tenant_id)
    assert pos_qris["total_harga"] == 50000 + 5000 + 20000

    pos_cash = pos_db.buat_transaksi(
        tenant_id, jasa_items=[{"barber_id": barber_a, "service_ids": [svc]}],
        produk_items=[], metode_pembayaran="cash", dibuat_oleh="smoke",
    )
    pos_cash = pos_db.bayar_cash(pos_cash["id"], tenant_id, 50000)

    tanggal = pos_qris["tanggal"]
    hasil = pos_db.get_transaksi_hari_ini(tenant_id, tanggal)
    assert hasil["rincian_metode"]["qris"] == pos_qris["total_harga"]
    assert hasil["rincian_metode"]["cash"] == pos_cash["total_harga"]
    assert hasil["rincian_metode"]["gateway"] == 0
    assert hasil["total_keseluruhan"] == pos_qris["total_harga"] + pos_cash["total_harga"]


def test_endpoint_bayar_cash_pos(single_tenant):
    client, headers, tenant_id = single_tenant["client"], single_tenant["headers"], single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber Cash D", tenant_id=tenant_id)
    svc = db.add_service("Dry Cut Cash 4", 50000, tenant_id=tenant_id)

    r_buat = client.post("/api/pos/transaksi", headers=headers, json={
        "jasa_items": [{"barber_id": barber_a, "service_ids": [svc], "tips": 0}],
        "produk_items": [], "metode_pembayaran": "cash",
    })
    assert r_buat.status_code == 200, r_buat.text
    pos_id = r_buat.json()["id"]

    r_kurang = client.post(f"/api/pos/transaksi/{pos_id}/bayar-cash", headers=headers, json={"uang_diterima": 10000})
    assert r_kurang.status_code == 422, r_kurang.text

    r_bayar = client.post(f"/api/pos/transaksi/{pos_id}/bayar-cash", headers=headers, json={"uang_diterima": 60000})
    assert r_bayar.status_code == 200, r_bayar.text
    assert r_bayar.json()["status"] == "lunas"
    assert r_bayar.json()["kembalian"] == 10000
