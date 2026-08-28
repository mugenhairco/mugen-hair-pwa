"""test_booking_libur_mingguan.py — Requirement Owner: Barber Holiday diganti
dari input tanggal manual jadi jadwal libur MINGGUAN rutin per barber.
Cakupan: set_hari_libur_mingguan() validasi, is_barber_libur() additive-OR
(tanggal manual absensi_libur TETAP mutlak, TIDAK berubah), override
Check In (barber yang benar-benar masuk di hari libur mingguannya sendiri
TIDAK dianggap libur), efek ke hitung_slot()."""

from datetime import timedelta

import booking_db
import database as db
from booking_db import _hari_ini_wib


def _barber(tenant_id, username="libur1"):
    return db.add_barber(f"Barber {username}", tenant_id=tenant_id)


def _tanggal_hari(nama_hari_target, offset_awal=0):
    """Cari tanggal terdekat (mulai offset_awal hari dari sekarang) yang
    jatuh pada nama_hari_target ("senin".."minggu")."""
    idx_target = booking_db.HARI_LIST.index(nama_hari_target)
    tanggal = _hari_ini_wib() + timedelta(days=offset_awal)
    while tanggal.weekday() != idx_target:
        tanggal += timedelta(days=1)
    return tanggal.isoformat()


def test_set_hari_libur_mingguan_menolak_hari_tidak_valid(single_tenant):
    import pytest
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    with pytest.raises(ValueError):
        booking_db.set_hari_libur_mingguan(barber_id, ["senin", "bukan_hari"])


def test_set_hari_libur_mingguan_barber_tidak_ditemukan(single_tenant):
    import pytest
    with pytest.raises(ValueError):
        booking_db.set_hari_libur_mingguan(999999, ["senin"])


def test_is_barber_libur_true_pada_hari_libur_mingguan_setiap_minggu(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    booking_db.set_hari_libur_mingguan(barber_id, ["selasa"])

    selasa_ini = _tanggal_hari("selasa", offset_awal=1)
    selasa_depan = _tanggal_hari("selasa", offset_awal=8)
    assert booking_db.is_barber_libur(barber_id, selasa_ini) is True
    assert booking_db.is_barber_libur(barber_id, selasa_depan) is True

    senin = _tanggal_hari("senin", offset_awal=1)
    assert booking_db.is_barber_libur(barber_id, senin) is False


def test_is_barber_libur_tetap_true_untuk_tanggal_manual_absensi_libur(single_tenant):
    """Regresi additive-OR: tanggal manual (Cuti & Izin, absensi_libur)
    TIDAK boleh berubah perilakunya sama sekali oleh fitur jadwal mingguan
    ini -- barber TANPA jadwal mingguan apa pun tetap libur di tanggal yang
    ditandai manual."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    tanggal = (_hari_ini_wib() + timedelta(days=3)).isoformat()
    db.tandai_libur(barber_id, tanggal)

    assert booking_db.is_barber_libur(barber_id, tanggal) is True


def test_is_barber_libur_false_jika_sudah_checkin_pada_hari_libur_mingguan(single_tenant):
    """Klarifikasi eksplisit Owner: barber yang Check In pada hari libur
    mingguannya sendiri (shift tukar dadakan) otomatis TIDAK dianggap libur
    hari itu -- baik untuk Booking maupun Auto-Libur payroll."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    booking_db.set_hari_libur_mingguan(barber_id, ["selasa"])
    selasa = _tanggal_hari("selasa", offset_awal=1)
    assert booking_db.is_barber_libur(barber_id, selasa) is True

    with booking_db.get_conn() as conn:
        conn.execute(
            "INSERT INTO attendance_logs (barber_id, tanggal, check_in_at, created_at, tenant_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (barber_id, selasa, "2026-01-01T09:00:00", "2026-01-01T09:00:00", tenant_id),
        )

    assert booking_db.is_barber_libur(barber_id, selasa) is False


def test_hitung_slot_semua_closed_pada_hari_libur_mingguan_barber(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    service_id = db.add_service("Cukur Libur Mingguan", 50000, tenant_id=tenant_id)
    booking_db.set_hari_libur_mingguan(barber_id, ["rabu"])
    rabu = _tanggal_hari("rabu", offset_awal=1)

    hasil = booking_db.hitung_slot(barber_id, rabu, [service_id], tenant_id=tenant_id)
    assert hasil["barber_libur"] is True
    assert all(s["status"] == "closed" for s in hasil["slots"])
