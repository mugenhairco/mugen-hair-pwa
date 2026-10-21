"""test_transaksi_idempotency.py — Input Data: cegah Transaksi dobel
=============================================================================
PERBAIKAN Owner (audit "Pastikan sekarang tidak bisa input data doubel"):
Input Data > Simpan Transaksi SENGAJA fire-and-forget (lihat catatan Owner
di frontend/app/js/pages/input_data.js) -- tombol "Kirim Ulang" di jaring
pengaman localStorage bisa mengirim ULANG entry yang SEBENARNYA sudah
berhasil tersimpan di server (hanya responsnya yang tidak sempat diterima
klien, mis. tab ditutup tepat saat itu). `idempotency_key` (tempId yang
dibuat klien per entry) membuat percobaan kedua jadi no-op aman -- server
mengembalikan transaksi yang SUDAH ADA, bukan membuat baris baru.

Cakupan: database.py::tambah_transaksi() level (key sama -> id sama, TIDAK
ada baris baru; key beda/None -> perilaku lama tidak berubah; key sama
tapi barber BEDA -> tetap baris terpisah, bukan dianggap dobel) + lewat
endpoint POST /api/input-data/transaksi (kirim body identik dua kali)."""

import database as db


def _setup(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Idempotensi", tenant_id=tenant_id)
    service_id = db.add_service("Potong Idempotensi", 30000, tenant_id=tenant_id)
    return tenant_id, barber_id, service_id


def test_key_sama_mengembalikan_transaksi_yang_sama_bukan_baris_baru(single_tenant):
    tenant_id, barber_id, service_id = _setup(single_tenant)
    items = [{"service_id": service_id, "jumlah": 1}]

    id_pertama = db.tambah_transaksi("2026-09-01", barber_id, items, tips=5000,
                                      idempotency_key="entry-abc")
    id_kedua = db.tambah_transaksi("2026-09-01", barber_id, items, tips=5000,
                                    idempotency_key="entry-abc")
    assert id_pertama == id_kedua

    daftar = db.get_transaksi_list(tahun=2026, bulan=9, barber_id=barber_id, tenant_id=tenant_id)
    assert len(daftar) == 1


def test_tanpa_key_perilaku_lama_tidak_berubah_boleh_dobel(single_tenant):
    tenant_id, barber_id, service_id = _setup(single_tenant)
    items = [{"service_id": service_id, "jumlah": 1}]

    id_pertama = db.tambah_transaksi("2026-09-02", barber_id, items, tips=0)
    id_kedua = db.tambah_transaksi("2026-09-02", barber_id, items, tips=0)
    assert id_pertama != id_kedua

    daftar = db.get_transaksi_list(tahun=2026, bulan=9, barber_id=barber_id, tenant_id=tenant_id)
    assert len(daftar) == 2


def test_key_beda_tetap_dua_transaksi_terpisah(single_tenant):
    tenant_id, barber_id, service_id = _setup(single_tenant)
    items = [{"service_id": service_id, "jumlah": 1}]

    id_pertama = db.tambah_transaksi("2026-09-03", barber_id, items, idempotency_key="entry-1")
    id_kedua = db.tambah_transaksi("2026-09-03", barber_id, items, idempotency_key="entry-2")
    assert id_pertama != id_kedua


def test_key_sama_tapi_barber_beda_tetap_dua_transaksi_terpisah(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_a = db.add_barber("Barber Idempotensi A", tenant_id=tenant_id)
    barber_b = db.add_barber("Barber Idempotensi B", tenant_id=tenant_id)
    service_id = db.add_service("Potong Idempotensi AB", 30000, tenant_id=tenant_id)
    items = [{"service_id": service_id, "jumlah": 1}]

    id_a = db.tambah_transaksi("2026-09-04", barber_a, items, idempotency_key="entry-sama")
    id_b = db.tambah_transaksi("2026-09-04", barber_b, items, idempotency_key="entry-sama")
    assert id_a != id_b


def test_lewat_endpoint_kirim_ulang_body_identik_tidak_dobel(single_tenant):
    client, headers = single_tenant["client"], single_tenant["headers"]
    tenant_id, barber_id, service_id = _setup(single_tenant)

    body = {
        "tanggal": "2026-09-05", "barber_id": barber_id,
        "items": [{"service_id": service_id, "jumlah": 1}],
        "tips": 10000, "catatan": None,
        "idempotency_key": "entry-endpoint-1",
    }
    r1 = client.post("/api/input-data/transaksi", json=body, headers=headers)
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/input-data/transaksi", json=body, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r1.json()["id"] == r2.json()["id"]

    r_list = client.get("/api/input-data/transaksi?tahun=2026&bulan=9", headers=headers)
    daftar = [t for t in r_list.json() if t["barber_id"] == barber_id]
    assert len(daftar) == 1
