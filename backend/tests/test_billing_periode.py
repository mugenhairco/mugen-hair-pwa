"""test_billing_periode.py -- Perbaikan Billing/Subscription (requirement
Owner poin 2): unit test murni untuk billing_periode.tambah_bulan_kalender()
-- TIDAK ADA DB/fixture, murni matematika kalender."""

from datetime import datetime

from billing_periode import tambah_bulan_kalender


def test_31_januari_tambah_1_bulan_clamp_ke_28_februari():
    assert tambah_bulan_kalender(datetime(2026, 1, 31), 1) == datetime(2026, 2, 28)


def test_31_januari_tambah_1_bulan_clamp_ke_29_februari_tahun_kabisat():
    assert tambah_bulan_kalender(datetime(2028, 1, 31), 1) == datetime(2028, 2, 29)


def test_30_agustus_tambah_1_bulan_jadi_30_september():
    """Contoh persis dari requirement Owner."""
    assert tambah_bulan_kalender(datetime(2026, 8, 30), 1) == datetime(2026, 9, 30)


def test_tambah_6_bulan_lintas_tahun():
    assert tambah_bulan_kalender(datetime(2026, 7, 15), 6) == datetime(2027, 1, 15)


def test_tambah_12_bulan_tahunan():
    assert tambah_bulan_kalender(datetime(2026, 3, 10), 12) == datetime(2027, 3, 10)


def test_tambah_12_bulan_31_januari_tidak_perlu_clamp():
    assert tambah_bulan_kalender(datetime(2026, 1, 31), 12) == datetime(2027, 1, 31)


def test_tanggal_tanpa_clamp_tetap_akurat():
    assert tambah_bulan_kalender(datetime(2026, 7, 15), 1) == datetime(2026, 8, 15)


def test_jam_menit_detik_dipertahankan():
    assert tambah_bulan_kalender(datetime(2026, 1, 31, 23, 59, 59), 1) == datetime(2026, 2, 28, 23, 59, 59)
