"""
absen_mandiri_db.py — FITUR BARU: Absen Mandiri (Check In/Out TANPA LOGIN
untuk karyawan Non-Barber: Kasir/OB/Kru/dst)
=============================================================================
File ini SENGAJA dipisah dari database.py/attendance_db.py (pola yang sama
seperti karyawan_migrasi.py/pengeluaran_migrasi.py di tahap-tahap sebelumnya).

Latar belakang (disetujui Owner): Barber sudah bisa Check In/Out lewat akun
login sendiri (lihat attendance_db.py) -- karyawan Non-Barber (jabatan !=
'barber') TIDAK PERNAH punya akun login sama sekali (lihat karyawan_migrasi.py),
jadi sebelumnya TIDAK ADA cara sama sekali bagi mereka untuk Check In/Out.
Absen Mandiri menambah halaman PUBLIK (tanpa login, lihat routers/
absen_mandiri.py) yang menampilkan daftar nama karyawan Non-Barber aktif --
tap nama lalu ambil lokasi GPS seperti Barber biasa. Baris attendance_logs
yang dihasilkan 100% SAMA (tabel yang sama, lihat attendance_db.check_in()/
check_out()) -- otomatis tergabung ke Dashboard/Riwayat Absensi Owner yang
sudah ada, TIDAK memengaruhi perhitungan gaji Non-Barber sama sekali (gaji
Non-Barber tetap dihitung manual lewat data_non_barber_db.py, modul ini
murni menambah jejak waktu Check In/Out yang informatif).

Device-lock (keamanan anti "titip absen", keputusan Owner): karena halaman
ini TANPA LOGIN/PIN, device (browser) yang dipakai Check In PERTAMA seorang
karyawan diikat ke karyawan itu (kolom `barbers.device_id_terikat`, id acak
yang dibuat & disimpan client-side di localStorage, lihat pages/
absen_mandiri.js) -- percobaan Check In/Out BERIKUTNYA atas nama karyawan
itu dari device LAIN ditolak (lihat cek_device_lock()) sampai Owner/Admin
me-reset ikatannya (lihat reset_device()). Beberapa karyawan BOLEH berbagi
SATU device fisik yang sama (mis. satu tablet di meja kasir) -- masing-
masing mengikat device_id YANG SAMA itu ke dirinya sendiri secara independen
pada Check In pertamanya; yang dicegah murni "Check In atas nama orang lain
dari device terpisah milik orang itu", BUKAN tap bergantian di device yang
sama. Ini kontrol level browser-storage (localStorage dihapus = ikatan
device bisa "lepas" dari sisi client, tapi device_id lama otomatis ditolak
begitu device baru mencoba memakai nama yang sudah terikat ke device_id
lain) -- cukup untuk staf biasa, BUKAN klaim keamanan tingkat kriptografi.

Tanpa PIN, tanpa foto, tanpa batas jam operasional/limit keterlambatan-
pulang cepat untuk Non-Barber (lihat attendance_db.validasi_checkin()/
validasi_checkout()/_menit_pulang_awal_baris() -- SEMUA jendela waktu/limit
itu HANYA berlaku jabatan='barber', dicek di sana, BUKAN di file ini)."""

from datetime import datetime

from database import get_conn, get_barber


def migrasi_absen_mandiri():
    """JALUR SQLITE SAJA -- idempotent, pola sama persis karyawan_migrasi.py.
    Jalur PostgreSQL: kolom yang sama dibuat lewat `ALTER TABLE ... ADD
    COLUMN IF NOT EXISTS` di postgres_schema.py."""
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
        if "device_id_terikat" not in kolom:
            conn.execute("ALTER TABLE barbers ADD COLUMN device_id_terikat TEXT")
        if "device_label_terikat" not in kolom:
            conn.execute("ALTER TABLE barbers ADD COLUMN device_label_terikat TEXT")
        if "device_terikat_sejak" not in kolom:
            conn.execute("ALTER TABLE barbers ADD COLUMN device_terikat_sejak TEXT")


def get_daftar_karyawan_publik(tenant_id: int) -> list:
    """Daftar karyawan Non-Barber (jabatan != 'barber') AKTIF milik tenant --
    dipakai halaman publik Absen Mandiri untuk tombol pilih nama. HANYA
    id/nama/jabatan (tidak ada data sensitif seperti device terikat)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nama, jabatan FROM barbers WHERE tenant_id = ? AND aktif = 1 "
            "AND jabatan != 'barber' ORDER BY nama",
            (tenant_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def cek_device_lock(barber: dict, device_id: str | None):
    """Raise ValueError kalau device_id yang dipakai BUKAN device yang sudah
    terikat ke karyawan ini. Tidak melakukan apa-apa kalau karyawan ini
    belum pernah terikat device sama sekali (device_id_terikat kosong --
    percobaan INI SENDIRI yang akan mengikatnya, lihat ikat_device_jika_belum()
    di bawah, dipanggil SETELAH Check In berhasil)."""
    terikat = barber.get("device_id_terikat")
    if terikat and device_id and terikat != device_id:
        raise ValueError(
            f"Perangkat ini belum terdaftar untuk {barber.get('nama') or 'karyawan ini'}. "
            "Minta Admin/Owner reset perangkat di menu Absensi."
        )


def ikat_device_jika_belum(barber_id: int, device_id: str | None, device_label: str | None):
    """Dipanggil attendance_db.check_in() SETELAH Check In berhasil tersimpan
    -- mengikat device_id ke karyawan ini HANYA kalau belum pernah terikat
    device apa pun sebelumnya (sekali terikat, tetap terikat sampai di-reset
    Admin/Owner lewat reset_device())."""
    if not device_id:
        return
    with get_conn() as conn:
        row = conn.execute("SELECT device_id_terikat FROM barbers WHERE id = ?", (barber_id,)).fetchone()
        if row is None or row["device_id_terikat"]:
            return
        conn.execute(
            "UPDATE barbers SET device_id_terikat = ?, device_label_terikat = ?, device_terikat_sejak = ? "
            "WHERE id = ?",
            (device_id, device_label, datetime.now().isoformat(timespec="seconds"), barber_id),
        )


def get_daftar_device_terikat(tenant_id: int) -> list:
    """Panel Admin "Perangkat Terikat" (menu Absensi, kartu Pengaturan) --
    SEMUA karyawan Non-Barber tenant ini (aktif maupun tidak, supaya Admin
    tetap bisa reset karyawan yang baru dinonaktifkan), beserta status
    device terikatnya."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nama, jabatan, aktif, device_id_terikat, device_label_terikat, device_terikat_sejak "
            "FROM barbers WHERE tenant_id = ? AND jabatan != 'barber' ORDER BY nama",
            (tenant_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def reset_device(barber_id: int, tenant_id: int) -> dict:
    """Admin/Owner melepas ikatan device karyawan ini -- Check In/Out
    berikutnya (dari device MANA PUN) akan mengikat device BARU itu lagi
    (lihat ikat_device_jika_belum())."""
    barber = get_barber(barber_id)
    if barber is None or barber.get("tenant_id") != tenant_id:
        raise ValueError("Karyawan tidak ditemukan.")
    with get_conn() as conn:
        conn.execute(
            "UPDATE barbers SET device_id_terikat = NULL, device_label_terikat = NULL, "
            "device_terikat_sejak = NULL WHERE id = ?",
            (barber_id,),
        )
    return get_barber(barber_id)
