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
        _normalisasi_urutan_service_kolisi(conn)
        _normalisasi_urutan_barber_kolisi(conn)


def _migrasi_status_booking(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
    if "status_booking" in kolom:
        return
    conn.execute("ALTER TABLE barbers ADD COLUMN status_booking TEXT NOT NULL DEFAULT 'aktif'")


def _migrasi_foto_dan_urutan_barber(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
    if "foto_filename" not in kolom:
        conn.execute("ALTER TABLE barbers ADD COLUMN foto_filename TEXT")
    if "foto_data" not in kolom:
        # Tahap 16: isi foto (BLOB) pindah dari disk lokal ke database --
        # disk lokal Render Free tier TIDAK persisten, lihat README.
        conn.execute("ALTER TABLE barbers ADD COLUMN foto_data BLOB")
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


def _normalisasi_urutan_service_kolisi(conn):
    """MAINTENANCE #1 (bugfix): SEBELUM diperbaiki, database.add_service()
    tidak pernah mengisi `urutan` (selalu memakai default kolom, 0) --
    SETIAP layanan yang ditambahkan setelah migrasi di atas (termasuk
    layanan di tenant baru mana pun yang dibuat lewat Super Admin
    Dashboard) berbagi urutan=0, membuat tombol ↑/↓ Setting > Layanan
    (menukar nilai urutan dua baris bersebelahan) tidak berpengaruh
    (menukar 0 dengan 0). Sudah diperbaiki PERMANEN di add_service() --
    fungsi ini HANYA membereskan data yang SUDAH TERLANJUR tidak konsisten
    sebelum perbaikan itu ada, per tenant, dan HANYA kalau memang
    terdeteksi ada tabrakan (dua layanan tenant yang sama dengan urutan
    yang SAMA PERSIS). Urutan RELATIF yang sudah ada (urutan lalu nama
    sebagai pemisah dasi) TETAP DIPERTAHANKAN, hanya angkanya dirapikan
    jadi 0,1,2,... berurutan -- Owner yang SUDAH mengatur urutan lewat
    tombol ↑/↓ (jadi urutan-nya sudah unik) TIDAK akan melihat urutan
    layanannya berubah sama sekali akibat migrasi ini. Aman dipanggil
    berkali-kali (no-op begitu tidak ada tabrakan tersisa).

    BUGFIX urutan startup: fungsi ini dipanggil dari migrasi_booking_form(),
    yang jalan SEBELUM migrasi_tenant() (lihat main.py::on_startup()) --
    pada boot PERTAMA KALI sebuah instalasi baru, kolom `tenant_id` di
    `services` BELUM ADA sama sekali di titik ini. Keluar lebih awal kalau
    begitu (aman -- instalasi baru tidak mungkin sudah punya tabrakan
    urutan, dan boot BERIKUTNYA setelah migrasi_tenant() selesai akan
    otomatis menormalisasi kalau memang perlu)."""
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(services)").fetchall()]
    if "tenant_id" not in kolom:
        return
    tenant_ids = [r["tenant_id"] for r in conn.execute("SELECT DISTINCT tenant_id FROM services").fetchall()]
    for tenant_id in tenant_ids:
        if tenant_id is None:
            rows = conn.execute("SELECT id, urutan FROM services WHERE tenant_id IS NULL ORDER BY urutan, nama").fetchall()
        else:
            rows = conn.execute("SELECT id, urutan FROM services WHERE tenant_id = ? ORDER BY urutan, nama",
                                 (tenant_id,)).fetchall()
        urutan_terpakai = [r["urutan"] for r in rows]
        if len(set(urutan_terpakai)) == len(urutan_terpakai):
            continue  # tidak ada tabrakan untuk tenant ini, tidak perlu apa-apa
        for i, row in enumerate(rows):
            if row["urutan"] != i:
                conn.execute("UPDATE services SET urutan = ? WHERE id = ?", (i, row["id"]))


def _normalisasi_urutan_barber_kolisi(conn):
    """BOOKING UI/UX #1 (bugfix): PERSIS pola _normalisasi_urutan_service_kolisi()
    di atas, tapi untuk `barbers` -- SEBELUM diperbaiki, database.add_barber()
    tidak pernah mengisi `urutan` (selalu default kolom, 0), jadi tombol ↑/↓
    Settings > Karyawan tidak berpengaruh untuk karyawan yang ditambahkan
    setelah migrasi _migrasi_foto_dan_urutan_barber() di atas. Sudah
    diperbaiki PERMANEN di add_barber() -- fungsi ini HANYA membereskan data
    yang SUDAH TERLANJUR tidak konsisten, per tenant, HANYA kalau memang ada
    tabrakan. Urutan RELATIF yang sudah ada tetap dipertahankan (Owner yang
    sudah pernah pakai ↑/↓, jadi urutannya sudah unik, tidak akan melihat
    perubahan apa pun). Aman dipanggil berkali-kali."""
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
    if "tenant_id" not in kolom:
        return
    tenant_ids = [r["tenant_id"] for r in conn.execute("SELECT DISTINCT tenant_id FROM barbers").fetchall()]
    for tenant_id in tenant_ids:
        if tenant_id is None:
            rows = conn.execute("SELECT id, urutan FROM barbers WHERE tenant_id IS NULL ORDER BY urutan, nama").fetchall()
        else:
            rows = conn.execute("SELECT id, urutan FROM barbers WHERE tenant_id = ? ORDER BY urutan, nama",
                                 (tenant_id,)).fetchall()
        urutan_terpakai = [r["urutan"] for r in rows]
        if len(set(urutan_terpakai)) == len(urutan_terpakai):
            continue  # tidak ada tabrakan untuk tenant ini, tidak perlu apa-apa
        for i, row in enumerate(rows):
            if row["urutan"] != i:
                conn.execute("UPDATE barbers SET urutan = ? WHERE id = ?", (i, row["id"]))
