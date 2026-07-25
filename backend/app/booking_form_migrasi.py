"""
booking_form_migrasi.py — Migrasi skema untuk penyempurnaan Form Booking Customer
====================================================================================
Lanjutan dari booking_migrasi.py (Modul Booking awal) -- file migrasi BARU
terpisah (pola yang sama seperti pengeluaran_migrasi.py/pengaturan_migrasi.py/
sync_migrasi.py/revisi_bonus_migrasi.py/booking_migrasi.py: satu file
migrasi per "sesi" pekerjaan, bukan menumpuk semua di satu file raksasa).

Tiga migrasi idempotent di sini, aman dipanggil berulang kali, TIDAK PERNAH
menghapus/menimpa data yang sudah ada:

1. Kolom baru `barbers.status_booking` (ALTER TABLE, default 'aktif') --
   status KHUSUS untuk modul Booking (Active/On Vacation), TERPISAH dari
   kolom `aktif` yang SUDAH ADA (dipakai luas di seluruh aplikasi --
   Dashboard, Rekap, Input Data, dst -- TIDAK disentuh sama sekali di
   sini). "Non Active" pada 3 status yang diminta spek (Active/On
   Vacation/Non Active) dipetakan ke kolom `aktif` yang sudah ada
   (aktif=0), BUKAN nilai baru di status_booking -- supaya tidak ada dua
   mekanisme "nonaktifkan barber" yang bisa saling tidak sinkron. Barber
   libur SATU-DUA HARI tetap lewat absensi_libur (Barber Holiday) yang
   sudah ada sejak Modul Booking awal; status_booking='cuti' dipakai
   untuk cuti PANJANG/tidak tentu (barber tampil "On Vacation" di SEMUA
   tanggal sampai Owner ubah lagi).
2. Kolom baru `barbers.foto_filename` (ALTER TABLE, nullable) dan
   `barbers.urutan` (ALTER TABLE, default 0, di-backfill urut sesuai nama
   supaya urutan tampil di halaman booking TIDAK acak begitu kolom ini
   pertama kali dibuat -- Owner bebas mengubahnya lewat Setting > Barber
   sesudahnya).
3. Kolom baru `services.urutan` (ALTER TABLE, default 0, di-backfill
   sama seperti barber).

Tabel BARU `toko_libur` (hari libur TOKO, semua barber sekaligus --
mis. libur nasional/lebaran, BEDA dari Barber Holiday yang per-barber)
SENGAJA dibuat di booking_db.py sendiri (init_booking_db(), CREATE TABLE
IF NOT EXISTS), bukan di file migrasi ini -- tabel baru menumpang di
init function modul yang sama, mengikuti pola yang sudah dipakai
bookings/booking_items/closed_slot sebelumnya.
"""

from database import get_conn


def migrasi_booking_form():
    with get_conn() as conn:
        _migrasi_status_booking(conn)
        _migrasi_foto_dan_urutan_barber(conn)
        _migrasi_urutan_service(conn)


def _migrasi_status_booking(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
    if "status_booking" in kolom:
        return
    conn.execute("ALTER TABLE barbers ADD COLUMN status_booking TEXT NOT NULL DEFAULT 'aktif'")


def _migrasi_foto_dan_urutan_barber(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
    if "foto_filename" not in kolom:
        conn.execute("ALTER TABLE barbers ADD COLUMN foto_filename TEXT")
    if "urutan" not in kolom:
        conn.execute("ALTER TABLE barbers ADD COLUMN urutan INTEGER NOT NULL DEFAULT 0")
        for i, row in enumerate(conn.execute("SELECT id FROM barbers ORDER BY nama").fetchall()):
            conn.execute("UPDATE barbers SET urutan = ? WHERE id = ?", (i, row["id"]))


def _migrasi_urutan_service(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(services)").fetchall()]
    if "urutan" in kolom:
        return
    conn.execute("ALTER TABLE services ADD COLUMN urutan INTEGER NOT NULL DEFAULT 0")
    for i, row in enumerate(conn.execute("SELECT id FROM services ORDER BY nama").fetchall()):
        conn.execute("UPDATE services SET urutan = ? WHERE id = ?", (i, row["id"]))
