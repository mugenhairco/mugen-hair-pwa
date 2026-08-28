"""test_booking_durasi_overlap.py — Regresi Requirement Owner (Durasi
Service Terintegrasi dengan Booking + Validasi Jam Operasional + Validasi
Waktu yang Sudah Terpakai): TIDAK ADA perubahan logika di booking_db.py --
hitung_slot()/_validasi_slot_tersedia() SUDAH benar (kandidat waktu dicek
span PENUH terhadap jam tutup DAN overlap booking lain, bukan cuma titik
mulai). Test-test ini mengunci contoh PERSIS dari requirement Owner supaya
kebenaran ini terbukti, bukan cuma diklaim."""

from datetime import timedelta

import booking_db
import database as db
from booking_db import _hari_ini_wib


def _siapkan(tenant_id, username="durasi1"):
    booking_db.update_payment_settings(metode_aktif=["transfer"], tenant_id=tenant_id)
    barber_id = db.add_barber(f"Barber {username}", tenant_id=tenant_id)
    return barber_id


def _besok(offset=1):
    return (_hari_ini_wib() + timedelta(days=offset)).isoformat()


def test_hitung_slot_service_2_jam_tumpang_tindih_booking_1_jam_pertama(single_tenant):
    """Persis contoh Owner: Dry Cut 11:00-12:00 sudah terbooking. Perm (2
    jam) yang dimulai 10:00 (span 10:00-12:00) ATAU 11:00 (span 11:00-13:00)
    keduanya HARUS "booked" -- overlap dicek span PENUH, bukan cuma jam
    mulai."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _siapkan(tenant_id)
    dry_cut = db.add_service("Dry Cut Overlap", 30000, tenant_id=tenant_id)
    perm = db.add_service("Perm Overlap", 100000, tenant_id=tenant_id)
    import pengaturan_service
    pengaturan_service.update_service_lengkap(perm, durasi_menit=120)
    tanggal = _besok()

    booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="11:00", service_ids=[dry_cut],
                             customer_nama="Customer A", customer_whatsapp="081234567890",
                             metode_pembayaran="transfer", tenant_id=tenant_id)

    hasil = booking_db.hitung_slot(barber_id, tanggal, [perm], tenant_id=tenant_id)
    status_per_jam = {s["jam"]: s["status"] for s in hasil["slots"]}
    assert status_per_jam.get("10:00") == "booked"
    assert status_per_jam.get("11:00") == "booked"


def test_hitung_slot_durasi_service_melebihi_jam_tutup_tidak_tersedia(single_tenant):
    """Persis contoh Owner: jam operasional 10:00-20:00, Perm 2 jam. 17:00
    boleh (selesai 19:00), 18:00 boleh (selesai 20:00), 19:00 TIDAK boleh
    (selesai 21:00, lewat jam tutup) -- kandidat 19:00 tidak boleh muncul
    berstatus "available"."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _siapkan(tenant_id)
    perm = db.add_service("Perm", 100000, tenant_id=tenant_id)
    import pengaturan_service
    pengaturan_service.update_service_lengkap(perm, durasi_menit=120)
    booking_db.update_booking_settings(jam_buka="10:00", jam_tutup="20:00", interval_menit=60, tenant_id=tenant_id)
    tanggal = _besok()

    hasil = booking_db.hitung_slot(barber_id, tanggal, [perm], tenant_id=tenant_id)
    status_per_jam = {s["jam"]: s["status"] for s in hasil["slots"]}
    assert status_per_jam.get("17:00") == "available"
    assert status_per_jam.get("18:00") == "available"
    assert "19:00" not in status_per_jam


def test_hitung_slot_durasi_ganjil_tidak_kelipatan_interval(single_tenant):
    """Interval 30 menit + servis 90 menit (bukan kelipatan interval jam
    penuh) -- overlap & batas jam tutup tetap harus benar."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _siapkan(tenant_id)
    service_90 = db.add_service("Coloring", 150000, tenant_id=tenant_id)
    import pengaturan_service
    pengaturan_service.update_service_lengkap(service_90, durasi_menit=90)
    booking_db.update_booking_settings(jam_buka="10:00", jam_tutup="20:00", interval_menit=30, tenant_id=tenant_id)
    tanggal = _besok()

    # Booking lain 13:00-14:00 (durasi default 60 menit lewat service beda).
    service_60 = db.add_service("Dry Cut Ganjil", 30000, tenant_id=tenant_id)
    booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="13:00", service_ids=[service_60],
                             customer_nama="Customer B", customer_whatsapp="081234567890",
                             metode_pembayaran="transfer", tenant_id=tenant_id)

    hasil = booking_db.hitung_slot(barber_id, tanggal, [service_90], tenant_id=tenant_id)
    status_per_jam = {s["jam"]: s["status"] for s in hasil["slots"]}
    # 12:30 -> span 12:30-14:00, overlap dengan 13:00-14:00 -> booked.
    assert status_per_jam.get("12:30") == "booked"
    # 11:00 -> span 11:00-12:30, TIDAK overlap -> available.
    assert status_per_jam.get("11:00") == "available"
    # kandidat terakhir yang muat sebelum 20:00 dengan durasi 90 menit: 18:30 (selesai 20:00).
    assert status_per_jam.get("18:30") == "available"
    assert "19:00" not in status_per_jam


def test_validasi_slot_tersedia_menolak_span_penuh_bukan_hanya_jam_mulai(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _siapkan(tenant_id)
    dry_cut = db.add_service("Dry Cut Validasi", 30000, tenant_id=tenant_id)
    tanggal = _besok()
    booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="11:00", service_ids=[dry_cut],
                             customer_nama="Customer C", customer_whatsapp="081234567890",
                             metode_pembayaran="transfer", tenant_id=tenant_id)

    import pytest
    # Jam mulai 10:00 TIDAK sama persis dengan booking yang ada (11:00),
    # tapi span 10:00-12:00 (durasi 120 menit) overlap -- harus ditolak.
    with pytest.raises(ValueError):
        booking_db._validasi_slot_tersedia(barber_id, tanggal, "10:00", 120, tenant_id=tenant_id)


def test_hitung_slot_beberapa_booking_tumpang_tindih_kandidat_yang_sama(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _siapkan(tenant_id)
    dry_cut = db.add_service("Dry Cut Multi", 30000, tenant_id=tenant_id)
    perm = db.add_service("Perm Multi", 100000, tenant_id=tenant_id)
    import pengaturan_service
    pengaturan_service.update_service_lengkap(perm, durasi_menit=180)
    tanggal = _besok()

    booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="11:00", service_ids=[dry_cut],
                             customer_nama="Customer D", customer_whatsapp="081234567890",
                             metode_pembayaran="transfer", tenant_id=tenant_id)
    booking_db.buat_booking(barber_id=barber_id, tanggal=tanggal, jam_mulai="13:00", service_ids=[dry_cut],
                             customer_nama="Customer E", customer_whatsapp="081234567890",
                             metode_pembayaran="transfer", tenant_id=tenant_id)

    # Perm 3 jam mulai 10:00 (span 10:00-13:00) overlap KEDUA booking di atas.
    hasil = booking_db.hitung_slot(barber_id, tanggal, [perm], tenant_id=tenant_id)
    status_per_jam = {s["jam"]: s["status"] for s in hasil["slots"]}
    assert status_per_jam.get("10:00") == "booked"
