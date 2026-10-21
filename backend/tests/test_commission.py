"""Regresi bug Phase 1.1: hitung_komisi_service() sebelumnya selalu
membaca persentase_komisi milik tenant DEFAULT, bukan tenant transaksi
yang sedang dihitung -- lihat database.py::hitung_komisi_service()."""


def test_komisi_tenant_terpisah(two_tenants):
    import database

    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]

    database.set_setting("persentase_komisi", "40", tenant_id=tenant_a)
    database.set_setting("persentase_komisi", "55", tenant_id=tenant_b)

    barber_a = database.add_barber("Barber A", tenant_id=tenant_a)
    barber_b = database.add_barber("Barber B", tenant_id=tenant_b)
    service_a = database.add_service("Potong A", 100000, tenant_id=tenant_a)
    service_b = database.add_service("Potong B", 100000, tenant_id=tenant_b)

    assert database.hitung_komisi_service(100000, 0, tenant_id=tenant_a) == 40000
    assert database.hitung_komisi_service(100000, 0, tenant_id=tenant_b) == 55000

    tx_a = database.tambah_transaksi("2026-07-01", barber_a, [{"service_id": service_a, "jumlah": 1}])
    tx_b = database.tambah_transaksi("2026-07-01", barber_b, [{"service_id": service_b, "jumlah": 1}])

    assert database.get_transaksi(tx_a)["total_komisi"] == 40000
    assert database.get_transaksi(tx_b)["total_komisi"] == 55000

    # Batch path (get_transaksi_list -> _lengkapi_transaksi_batch) harus
    # menghasilkan angka yang SAMA dengan single-row path di atas.
    assert database.get_transaksi_list(tenant_id=tenant_a)[0]["total_komisi"] == 40000
    assert database.get_transaksi_list(tenant_id=tenant_b)[0]["total_komisi"] == 55000

    preview_a = database.hitung_preview_items([{"service_id": service_a, "jumlah": 1}], tenant_id=tenant_a)
    preview_b = database.hitung_preview_items([{"service_id": service_b, "jumlah": 1}], tenant_id=tenant_b)
    assert preview_a["total_komisi"] == 40000
    assert preview_b["total_komisi"] == 55000


def test_preview_menolak_service_tenant_lain(two_tenants):
    import database

    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    service_b = database.add_service("Potong B", 100000, tenant_id=tenant_b)

    preview = database.hitung_preview_items([{"service_id": service_b, "jumlah": 1}], tenant_id=tenant_a)
    assert preview["rincian"] == []
    assert preview["total_harga"] == 0


# ---------------------------------------------------------------------------
# PERBAIKAN Owner (audit "komisi berubah kalau harga diubah kemudian hari"):
# `modal` (Harga Modal) sekarang disnapshot di transaksi_detail SAAT
# transaksi dibuat/dikoreksi -- PERSIS SAMA seperti `harga` sudah lebih
# dulu disnapshot. Komisi transaksi LAMA harus TETAP sama persis walau
# Harga Modal service-nya diedit belakangan.
# ---------------------------------------------------------------------------

def test_komisi_transaksi_lama_tidak_berubah_meski_modal_service_diedit(single_tenant):
    import database

    tenant_id = single_tenant["tenant_id"]
    database.set_setting("persentase_komisi", "50", tenant_id=tenant_id)
    barber_id = database.add_barber("Barber Modal", tenant_id=tenant_id)
    service_id = database.add_service("Potong Modal", 100000, tenant_id=tenant_id)
    with database.get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (20000, service_id))

    tx_id = database.tambah_transaksi("2026-01-05", barber_id, [{"service_id": service_id, "jumlah": 1}])
    assert database.get_transaksi(tx_id)["total_komisi"] == 40000  # (100000-20000)*50%

    # Owner menaikkan Harga Modal service ini BELAKANGAN (Juni) -- komisi
    # transaksi Januari yang SUDAH tercatat TIDAK BOLEH ikut berubah.
    with database.get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (50000, service_id))

    assert database.get_transaksi(tx_id)["total_komisi"] == 40000  # TETAP, bukan (100000-50000)*50%=25000
    assert database.get_transaksi_list(tenant_id=tenant_id)[0]["total_komisi"] == 40000  # batch path juga


def test_komisi_baris_lama_tanpa_snapshot_modal_tetap_pakai_modal_live(single_tenant):
    """Baris transaksi_detail dari SEBELUM migrasi (modal NULL, belum
    pernah disnapshot) -- satu-satunya nilai yang tersedia tetap modal
    SAAT INI (perilaku lama, TIDAK berubah untuk baris itu)."""
    import database

    tenant_id = single_tenant["tenant_id"]
    database.set_setting("persentase_komisi", "50", tenant_id=tenant_id)
    barber_id = database.add_barber("Barber Modal Lama", tenant_id=tenant_id)
    service_id = database.add_service("Potong Modal Lama", 100000, tenant_id=tenant_id)
    with database.get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (20000, service_id))

    tx_id = database.tambah_transaksi("2026-01-06", barber_id, [{"service_id": service_id, "jumlah": 1}])
    # Simulasikan baris LAMA (sebelum kolom `modal` ada) dengan mengosongkan
    # snapshot-nya langsung.
    with database.get_conn() as conn:
        conn.execute("UPDATE transaksi_detail SET modal = NULL WHERE transaksi_id = ?", (tx_id,))

    assert database.get_transaksi(tx_id)["total_komisi"] == 40000  # fallback ke modal live (20000)

    with database.get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (50000, service_id))
    assert database.get_transaksi(tx_id)["total_komisi"] == 25000  # ikut berubah (TIDAK ada snapshot)


def test_koreksi_transaksi_snapshot_modal_baru_saat_koreksi(single_tenant):
    """Koreksi mengganti SELURUH baris item -- modal yang disnapshot ulang
    adalah modal SAAT KOREKSI (bukan modal asli saat transaksi dibuat),
    konsisten dengan `harga` yang juga dibaca ulang SAAT koreksi."""
    import database

    tenant_id = single_tenant["tenant_id"]
    database.set_setting("persentase_komisi", "50", tenant_id=tenant_id)
    barber_id = database.add_barber("Barber Koreksi Modal", tenant_id=tenant_id)
    service_id = database.add_service("Potong Koreksi Modal", 100000, tenant_id=tenant_id)
    with database.get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (20000, service_id))

    tx_id = database.tambah_transaksi("2026-01-07", barber_id, [{"service_id": service_id, "jumlah": 1}])
    assert database.get_transaksi(tx_id)["total_komisi"] == 40000

    with database.get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (30000, service_id))
    database.koreksi_transaksi(tx_id, items=[{"service_id": service_id, "jumlah": 1}])
    assert database.get_transaksi(tx_id)["total_komisi"] == 35000  # (100000-30000)*50%

    # Setelah dikoreksi, modal BERIKUTNYA diedit lagi TIDAK boleh ikut
    # mengubah hasil koreksi ini (snapshot baru sudah terkunci).
    with database.get_conn() as conn:
        conn.execute("UPDATE services SET modal = ? WHERE id = ?", (99999, service_id))
    assert database.get_transaksi(tx_id)["total_komisi"] == 35000
