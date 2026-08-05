"""
email_auth_migrasi.py — Migrasi skema untuk Email, Verifikasi Email, dan
Lupa Kata Sandi
=============================================================================
File ini SENGAJA dipisah dari database.py/auth_db.py (pola yang sama
seperti karyawan_migrasi.py/tenant_migrasi.py di tahap-tahap sebelumnya).

Tiga kolom baru pada tabel `users` (TIDAK mengubah kolom yang sudah ada --
`username` TETAP satu-satunya identitas login, kolom di bawah ini murni
TAMBAHAN untuk fitur email):

1. `email` (TEXT, nullable) -- alamat email akun ini, TERPISAH dari
   `username` (yang untuk akun hasil Registrasi mandiri KEBETULAN sama
   dengan email, tapi untuk akun lama/karyawan yang dibuat Owner lewat
   Pengaturan > User belum tentu berupa email sama sekali). NULL = akun
   ini belum punya email terdaftar (kondisi NORMAL untuk tenant lama/
   karyawan -- lihat item 5, TIDAK memblokir apa pun).
2. `email_verified` (INTEGER, default 0) -- 1 kalau email di atas sudah
   diklik link verifikasinya.
3. `blokir_sampai_verifikasi` (INTEGER, default 0) -- HANYA diset TRUE
   oleh alur Registrasi mandiri BARU (routers/tenant_registration.py) saat
   akun dibuat. Baris LAMA (dan email yang ditambahkan belakangan lewat
   Pengaturan > Profil untuk tenant lama) TIDAK PERNAH diset ini, sehingga
   TIDAK PERNAH diblokir login walau email-nya belum diverifikasi -- SESUAI
   permintaan eksplisit "Jangan memblokir tenant lama hanya karena email
   belum diverifikasi". Dicek di routers/auth_router.py::login().

Dua tabel baru (token sekali pakai, kedaluwarsa otomatis lewat
`expires_at`, TIDAK PERNAH dipakai untuk resolusi tenant/otorisasi APAPUN
di luar tujuannya sendiri -- terpisah total dari mekanisme token sesi
login di auth.py, yang TIDAK disentuh sama sekali oleh migrasi ini):

- `email_verification_tokens`: satu baris per permintaan verifikasi/kirim
  ulang -- token LAMA milik user yang sama TIDAK dihapus saat token baru
  dibuat (kirim ulang), tapi hanya token yang BELUM kedaluwarsa yang
  diterima verify_email() (lihat email_auth_db.py) -- link lama otomatis
  jadi tidak valid begitu masa berlakunya habis, bukan karena dihapus.
- `password_reset_tokens`: sama seperti di atas, PLUS kolom `used_at`
  (sekali pakai -- token yang sudah dipakai untuk mengubah password tidak
  bisa dipakai ulang walau belum kedaluwarsa).

Idempotent (aman dipanggil berulang kali), TIDAK PERNAH menghapus/
menimpa data yang sudah ada.
"""

from database import get_conn


def migrasi_email_auth():
    with get_conn() as conn:
        _migrasi_kolom_users(conn)
        _migrasi_tabel_verifikasi(conn)
        _migrasi_tabel_reset_password(conn)


def _migrasi_kolom_users(conn):
    kolom = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "email" not in kolom:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "email_verified" not in kolom:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
    if "blokir_sampai_verifikasi" not in kolom:
        conn.execute("ALTER TABLE users ADD COLUMN blokir_sampai_verifikasi INTEGER NOT NULL DEFAULT 0")


def _migrasi_tabel_verifikasi(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_verification_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            token       TEXT NOT NULL UNIQUE,
            expires_at  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)


def _migrasi_tabel_reset_password(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            token       TEXT NOT NULL UNIQUE,
            expires_at  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            used_at     TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
