"""
lokasi_user_migrasi.py — Migrasi skema untuk FITUR Izin Lokasi APK Android
=============================================================================
File ini SENGAJA dipisah dari auth_db.py (pola yang sama seperti
tampilan_migrasi.py/karyawan_migrasi.py di tahap-tahap sebelumnya).

Tiga kolom baru pada tabel `users` (boleh NULL, tidak ada default wajib):
lokasi_lat, lokasi_lng (REAL), lokasi_updated_at (TEXT, ISO 8601) --
"lokasi TERAKHIR diketahui" milik akun ybs, dikirim SEKALI oleh
android-app/ (Capacitor WebView) begitu izin lokasi diberikan pengguna
saat login pertama di APK (lihat frontend/app/js/native_app.js +
routers/auth_router.py::simpan_lokasi()). TIDAK ada hubungannya dengan
fitur Absensi GPS Check In/Out Geofencing (attendance_db.py) -- itu modul
terpisah yang mencatat lokasi PER CHECK-IN/CHECK-OUT, ini murni satu
"lokasi terakhir" per akun, best-effort (gagal kirim/izin ditolak TIDAK
PERNAH mengganggu apa pun, lihat native_app.js).

Idempotent (aman dipanggil berulang kali), TIDAK PERNAH menghapus/menimpa
data yang sudah ada.
"""

from auth_db import get_conn


def migrasi_lokasi_user():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "lokasi_lat" not in kolom:
            conn.execute("ALTER TABLE users ADD COLUMN lokasi_lat REAL")
        if "lokasi_lng" not in kolom:
            conn.execute("ALTER TABLE users ADD COLUMN lokasi_lng REAL")
        if "lokasi_updated_at" not in kolom:
            conn.execute("ALTER TABLE users ADD COLUMN lokasi_updated_at TEXT")
