"""test_produk_idempotency.py — Produk: cegah Jual/Restock/Tester dobel
=============================================================================
PERBAIKAN Owner (audit "Pastikan sekarang tidak bisa input data doubel"):
sama alasannya persis seperti test_transaksi_idempotency.py -- WA Bot
(Jual/Restock/Tester Produk, termasuk bagian produk di Input Harian) bisa
memproses konfirmasi "YA" yang sama dua kali (race condition dua webhook
bersamaan, atau Fonnte mengirim ulang di luar jendela anti-dobel 2 menit).
`idempotency_key` per item (dibuat sekali saat preview, dipakai ulang saat
konfirmasi, lihat whatsapp_bot_parser.py) membuat percobaan kedua jadi
no-op aman -- mutasi yang SUDAH ADA dikembalikan, bukan baris baru.

Cakupan: database.py level (jual_produk/restock_produk/tester_produk)."""

import database as db


def _setup(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    produk_id = db.tambah_produk("Produk Idempotensi", harga_modal=10000, harga_jual=50000, tenant_id=tenant_id)
    db.restock_produk(produk_id, "2026-01-01", 100)
    return tenant_id, produk_id


def test_jual_produk_key_sama_mengembalikan_mutasi_yang_sama(single_tenant):
    tenant_id, produk_id = _setup(single_tenant)
    id1 = db.jual_produk(produk_id, "2026-09-01", 2, idempotency_key="jual-abc")
    id2 = db.jual_produk(produk_id, "2026-09-01", 2, idempotency_key="jual-abc")
    assert id1 == id2
    assert db.get_stok_produk(produk_id) == 98  # HANYA terpotong sekali


def test_jual_produk_tanpa_key_perilaku_lama_boleh_dobel(single_tenant):
    tenant_id, produk_id = _setup(single_tenant)
    id1 = db.jual_produk(produk_id, "2026-09-02", 2)
    id2 = db.jual_produk(produk_id, "2026-09-02", 2)
    assert id1 != id2
    assert db.get_stok_produk(produk_id) == 96  # dua kali terpotong


def test_jual_produk_key_sama_tapi_produk_beda_tetap_terpisah(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    produk_a = db.tambah_produk("Produk A", harga_modal=0, harga_jual=10000, tenant_id=tenant_id)
    produk_b = db.tambah_produk("Produk B", harga_modal=0, harga_jual=10000, tenant_id=tenant_id)
    db.restock_produk(produk_a, "2026-01-01", 10)
    db.restock_produk(produk_b, "2026-01-01", 10)
    id_a = db.jual_produk(produk_a, "2026-09-03", 1, idempotency_key="sama")
    id_b = db.jual_produk(produk_b, "2026-09-03", 1, idempotency_key="sama")
    assert id_a != id_b


def test_restock_produk_key_sama_tidak_dobel_stok(single_tenant):
    tenant_id, produk_id = _setup(single_tenant)
    stok_awal = db.get_stok_produk(produk_id)
    id1 = db.restock_produk(produk_id, "2026-09-04", 10, idempotency_key="restock-abc")
    id2 = db.restock_produk(produk_id, "2026-09-04", 10, idempotency_key="restock-abc")
    assert id1 == id2
    assert db.get_stok_produk(produk_id) == stok_awal + 10  # HANYA bertambah sekali


def test_tester_produk_key_sama_tidak_dobel_stok(single_tenant):
    tenant_id, produk_id = _setup(single_tenant)
    stok_awal = db.get_stok_produk(produk_id)
    id1 = db.tester_produk(produk_id, "2026-09-05", 3, idempotency_key="tester-abc")
    id2 = db.tester_produk(produk_id, "2026-09-05", 3, idempotency_key="tester-abc")
    assert id1 == id2
    assert db.get_stok_produk(produk_id) == stok_awal - 3  # HANYA terpotong sekali
