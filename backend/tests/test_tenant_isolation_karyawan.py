"""Regresi isolasi tenant Phase 1.1 -- modul Karyawan (Kasbon, Reimburse,
Komisi Penyesuaian, Izin & Cuti, Slip Gaji, Data Non-Barber). Sebelum
Phase 1.1, modul-modul ini di-scope TRANSITIF lewat JOIN ke
barbers.tenant_id, tapi TIDAK SATU PUN query-nya benar-benar memfilter
tenant -- Owner tenant A bisa melihat/mengubah/menghapus data tenant B
lewat endpoint by-id maupun daftar tanpa filter barber_id."""

import kasbon_db
import reimburse_db
import komisi_penyesuaian_db
import izin_cuti_db
import slip_gaji_db
import data_non_barber_db


def _dua_barber(two_tenants):
    import database

    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a = database.add_barber("Barber A", tenant_id=tenant_a)
    barber_b = database.add_barber("Barber B", tenant_id=tenant_b)
    return barber_a, barber_b


def test_kasbon_isolasi(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a, barber_b = _dua_barber(two_tenants)

    kasbon_a = kasbon_db.buat_kasbon(barber_a, "2026-07-01", 100000, tenant_id=tenant_a)
    assert kasbon_a["tenant_id"] == tenant_a

    import pytest
    with pytest.raises(ValueError):
        kasbon_db.buat_kasbon(barber_b, "2026-07-01", 100000, tenant_id=tenant_a)

    assert len(kasbon_db.get_kasbon_list(tenant_id=tenant_a)) == 1
    assert len(kasbon_db.get_kasbon_list(tenant_id=tenant_b)) == 0

    kasbon_db.bayar_kasbon(kasbon_a["id"], "2026-07-02", 50000, dibuat_oleh="ownerA")
    pembayaran_id = kasbon_db.get_riwayat_pembayaran(kasbon_a["id"])[0]["id"]
    assert kasbon_db.get_pembayaran_kasbon(pembayaran_id)["tenant_id"] == tenant_a

    client, headers_b = two_tenants["client"], two_tenants["headers_b"]
    assert client.get(f"/api/kasbon/{kasbon_a['id']}", headers=headers_b).status_code == 404
    assert client.delete(f"/api/kasbon/pembayaran/{pembayaran_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/kasbon/saldo/{barber_a}", headers=headers_b).status_code == 404


def test_reimburse_isolasi(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a, barber_b = _dua_barber(two_tenants)

    reimburse_a = reimburse_db.buat_reimburse(barber_a, "2026-07-01", "Transportasi", 20000,
                                               tenant_id=tenant_a)
    assert reimburse_a["tenant_id"] == tenant_a

    import pytest
    with pytest.raises(ValueError):
        reimburse_db.buat_reimburse(barber_b, "2026-07-01", "Transportasi", 20000, tenant_id=tenant_a)

    assert len(reimburse_db.get_reimburse_list(tenant_id=tenant_a)) == 1
    assert len(reimburse_db.get_reimburse_list(tenant_id=tenant_b)) == 0

    reimburse_db.set_status_reimburse(reimburse_a["id"], "disetujui", disetujui_oleh="ownerA")
    assert len(reimburse_db.get_reimburse_list_disetujui(tenant_id=tenant_a)) == 1
    assert len(reimburse_db.get_reimburse_list_disetujui(tenant_id=tenant_b)) == 0

    client, headers_b = two_tenants["client"], two_tenants["headers_b"]
    assert client.get(f"/api/reimburse/{reimburse_a['id']}", headers=headers_b).status_code == 404


def test_komisi_penyesuaian_isolasi(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a, barber_b = _dua_barber(two_tenants)

    penyesuaian_a = komisi_penyesuaian_db.buat_penyesuaian(
        barber_a, 2026, 7, "bonus", 10000, "bonus test", tenant_id=tenant_a)
    assert penyesuaian_a["tenant_id"] == tenant_a

    import pytest
    with pytest.raises(ValueError):
        komisi_penyesuaian_db.buat_penyesuaian(barber_b, 2026, 7, "bonus", 10000, "x", tenant_id=tenant_a)

    assert len(komisi_penyesuaian_db.get_penyesuaian_list(tenant_id=tenant_a)) == 1
    assert len(komisi_penyesuaian_db.get_penyesuaian_list(tenant_id=tenant_b)) == 0

    client, headers_b = two_tenants["client"], two_tenants["headers_b"]
    assert client.get(f"/api/komisi/penyesuaian/{penyesuaian_a['id']}", headers=headers_b).status_code == 404


def test_izin_cuti_isolasi(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a, barber_b = _dua_barber(two_tenants)

    pengajuan_a = izin_cuti_db.buat_pengajuan(
        barber_a, "cuti", "2026-07-01", "2026-07-03", "liburan", tenant_id=tenant_a)
    assert pengajuan_a["tenant_id"] == tenant_a

    import pytest
    with pytest.raises(ValueError):
        izin_cuti_db.buat_pengajuan(barber_b, "cuti", "2026-07-01", "2026-07-03", "x", tenant_id=tenant_a)

    assert len(izin_cuti_db.get_pengajuan_list(tenant_id=tenant_a)) == 1
    assert len(izin_cuti_db.get_pengajuan_list(tenant_id=tenant_b)) == 0
    assert izin_cuti_db.get_jumlah_pending(tenant_id=tenant_a) == 1
    assert izin_cuti_db.get_jumlah_pending(tenant_id=tenant_b) == 0

    client, headers_b = two_tenants["client"], two_tenants["headers_b"]
    assert client.get(f"/api/izin-cuti/{pengajuan_a['id']}", headers=headers_b).status_code == 404
    assert client.delete(f"/api/izin-cuti/{pengajuan_a['id']}", headers=headers_b).status_code == 404


def test_slip_gaji_isolasi(two_tenants):
    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    barber_a, barber_b = _dua_barber(two_tenants)

    slip_a = slip_gaji_db.buat_slip_gaji(barber_a, tahun=2026, bulan=7, gaji_pokok=1000000,
                                          tenant_id=tenant_a)
    assert slip_a["tenant_id"] == tenant_a

    import pytest
    with pytest.raises(ValueError):
        slip_gaji_db.buat_slip_gaji(barber_b, tahun=2026, bulan=7, gaji_pokok=1000000, tenant_id=tenant_a)

    assert len(slip_gaji_db.get_slip_gaji_list(tenant_id=tenant_a)) == 1
    assert len(slip_gaji_db.get_slip_gaji_list(tenant_id=tenant_b)) == 0

    client, headers_b = two_tenants["client"], two_tenants["headers_b"]
    assert client.get(f"/api/slip-gaji/{slip_a['id']}", headers=headers_b).status_code == 404


def test_data_non_barber_isolasi(two_tenants):
    import database

    tenant_a, tenant_b = two_tenants["tenant_a"], two_tenants["tenant_b"]
    kasir_a = database.add_barber("Kasir A", jabatan="kasir", gaji_per_hari=100000, tenant_id=tenant_a)
    barber_b = database.add_barber("Barber B", tenant_id=tenant_b)

    entry_a = data_non_barber_db.tambah_data_non_barber(
        kasir_a, "2026-07-01", "2026-07-15", 100000, 10, tenant_id=tenant_a)
    assert entry_a["tenant_id"] == tenant_a

    import pytest
    with pytest.raises(ValueError):
        data_non_barber_db.tambah_data_non_barber(
            barber_b, "2026-07-01", "2026-07-15", 100000, 10, tenant_id=tenant_a)

    assert len(data_non_barber_db.get_data_non_barber_list(tenant_id=tenant_a)) == 1
    assert len(data_non_barber_db.get_data_non_barber_list(tenant_id=tenant_b)) == 0

    client, headers_b = two_tenants["client"], two_tenants["headers_b"]
    assert client.delete(f"/api/data-non-barber/{entry_a['id']}", headers=headers_b).status_code == 404
