"""test_slip_gaji_kasbon_race.py — tandai_status() Slip Gaji vs potongan Kasbon
=============================================================================
PERBAIKAN Owner (audit "celah atau hal yang tidak wajar"): slip_gaji_db.py::
tandai_status() membaca status_lama, baru kemudian UPDATE + menerapkan
potongan kasbon -- TANPA lock, dua pemanggilan nyaris bersamaan untuk SLIP
YANG SAMA (dua tab Admin, atau double-klik sebelum tombol frontend
terdisable) bisa KEDUANYA lolos kondisi transisi 'belum_dibayar' ->
'sudah_dibayar' dan KEDUANYA memotong saldo kasbon barber -- dobel.
Diperbaiki dengan lock in-process per slip_id (_kunci_slip()), pola SAMA
dengan _kunci_per_kasbon (kasbon_db.py) yang sudah ada untuk celah serupa
di bayar_kasbon()."""

import threading
import time

import database as db
import kasbon_db
import slip_gaji_db


def test_tandai_status_terkunci_per_slip_tidak_potong_kasbon_dobel(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Slip Lock", tenant_id=tenant_id)
    kasbon = kasbon_db.buat_kasbon(barber_id, "2026-01-01", 100000, tenant_id=tenant_id)
    slip = slip_gaji_db.buat_slip_gaji(barber_id, tahun=2026, bulan=1, potongan_kasbon=50000,
                                        tenant_id=tenant_id)
    slip_id = slip["id"]

    # Pegang lock slip ini secara manual (meniru request LAIN yang sudah
    # masuk lebih dulu ke tandai_status() untuk slip yang SAMA), lalu
    # panggil tandai_status() di thread terpisah -- HARUS menunggu sampai
    # lock dilepas, membuktikan tandai_status() benar-benar memakai lock
    # yang sama (bukan cuma dideklarasikan tapi tidak dipakai).
    kunci = slip_gaji_db._kunci_slip(slip_id)
    kunci.acquire()
    try:
        hasil = {}

        def _panggil():
            hasil["slip"] = slip_gaji_db.tandai_status(slip_id, "sudah_dibayar")

        t = threading.Thread(target=_panggil)
        t.start()
        time.sleep(0.2)
        # Thread masih terblokir menunggu lock -- potongan kasbon BELUM diterapkan.
        assert t.is_alive()
        assert kasbon_db.get_kasbon(kasbon["id"])["sisa"] == 100000
    finally:
        kunci.release()

    t.join(timeout=5)
    assert not t.is_alive()
    assert hasil["slip"]["status"] == "sudah_dibayar"
    assert kasbon_db.get_kasbon(kasbon["id"])["sisa"] == 50000  # terpotong TEPAT SEKALI


def test_tandai_status_dua_kali_sama_tidak_dobel_potong_kasbon(single_tenant):
    """Pemanggilan BERULANG (sequential, bukan race) ke status yang SAMA
    tetap harus idempotent -- perilaku lama ini TIDAK boleh berubah oleh
    penambahan lock."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = db.add_barber("Barber Slip Idempoten", tenant_id=tenant_id)
    kasbon = kasbon_db.buat_kasbon(barber_id, "2026-01-01", 100000, tenant_id=tenant_id)
    slip = slip_gaji_db.buat_slip_gaji(barber_id, tahun=2026, bulan=1, potongan_kasbon=50000,
                                        tenant_id=tenant_id)
    slip_gaji_db.tandai_status(slip["id"], "sudah_dibayar")
    slip_gaji_db.tandai_status(slip["id"], "sudah_dibayar")  # diulang, status sama
    assert kasbon_db.get_kasbon(kasbon["id"])["sisa"] == 50000
