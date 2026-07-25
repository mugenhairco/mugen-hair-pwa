"""
auth_db.py
==========
Tabel & fungsi untuk AUTENTIKASI saja (login admin/barber). SENGAJA dipisah
dari database.py supaya database.py (satu-satunya sumber logika bisnis,
disalin VERBATIM dari aplikasi Python Desktop) tetap 100% tidak tersentuh —
sesuai ATURAN MUTLAK: jangan ubah logika bisnis / hasil perhitungan.

Tabel 'users' terpisah dari tabel 'barbers' (di database.py) karena:
- 'barbers' murni data bisnis (dipakai transaksi, komisi, dst) — jangan diubah.
- 'users' murni data login (username, password hash, role, dan referensi ke
  barber_id kalau role-nya 'barber'). Satu baris barbers BOLEH tidak punya
  akun (belum dibuatkan login), dan sebaliknya.

Password disimpan sebagai HASH (bcrypt), tidak pernah plaintext.

BUGFIX startup lokal: sebelumnya hashing memakai passlib
(`passlib.context.CryptContext(schemes=["bcrypt"])`), yang TIDAK
kompatibel dengan bcrypt>=4.0 -- passlib 1.7.4 (sudah tidak dikembangkan
lagi) melakukan self-test versi bcrypt lewat atribut `bcrypt.__about__`
yang sudah dihapus dari bcrypt sejak versi 4.0, menyebabkan
`AttributeError: module 'bcrypt' has no attribute '__about__'` dan/atau
`ValueError: password cannot be longer than 72 bytes` (dari self-test lain
milik passlib, `detect_wrap_bug`, bukan dari password pengguna yang
sebenarnya) begitu fungsi hash/verify pertama kali dipanggil -- gagal
walau `bcrypt<4.0` sudah dikunci di requirements.txt, kalau environment
lokal kebetulan sudah lebih dulu punya bcrypt versi lebih baru terpasang.
Diperbaiki dengan memanggil library `bcrypt` LANGSUNG (tanpa passlib) --
algoritma & format hash yang dihasilkan identik (awalan `$2b$`), jadi hash
yang sudah tersimpan di database dari versi sebelumnya (dibuat lewat
passlib) tetap valid diverifikasi lewat kode ini tanpa perlu migrasi data
apa pun."""

import sqlite3
from contextlib import contextmanager

import bcrypt

from database import DB_PATH  # pakai path database yang SAMA dengan database.py (satu file .db yang sama)

# Batas bawaan algoritma bcrypt itu sendiri: byte setelah yang ke-72 pada
# password diabaikan. bcrypt versi lama memotongnya diam-diam; versi >=4.0
# melempar ValueError kalau tidak dipotong duluan -- dipotong manual di
# sini (simetris di hash & verify) supaya perilakunya konsisten di semua
# versi bcrypt, sesuai saran pesan error resminya sendiri.
_BCRYPT_MAX_BYTES = 72


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_auth_db():
    """CREATE TABLE IF NOT EXISTS — aman dipanggil berkali-kali, tidak akan
    pernah menimpa/menghapus data yang sudah ada (tabel & data 'barbers',
    'transaksi', dst di database.py TIDAK disentuh sama sekali)."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL,   -- 'admin' atau 'barber'
                barber_id     INTEGER,         -- HANYA diisi kalau role = 'barber'
                                                -- (referensi ke barbers.id di database.py)
                aktif         INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)


def _pesan_diagnosa_bcrypt(exc: Exception) -> str:
    """Kode ini (auth_db.py) sudah TIDAK memanggil passlib sama sekali sejak
    bugfix sebelumnya -- diverifikasi lewat reproduksi persis kombinasi
    paket yang dilaporkan (bcrypt 5.0.0 + passlib 1.7.4 terpasang
    berdampingan) dan backend tetap start normal. Kalau error semacam ini
    masih muncul, penyebab paling mungkin BUKAN kode ini, melainkan
    instalasi paket `bcrypt` yang rusak/tidak bersih di virtual environment
    lokal (paling sering di Windows: file ekstensi native `.pyd` versi lama
    gagal terhapus/tertimpa saat `pip install --upgrade`, karena Windows
    mengunci file yang sedang dipakai proses lain). Pesan ini mengubah
    traceback kriptis dari dalam library `bcrypt` menjadi langkah perbaikan
    yang jelas."""
    return (
        f"Gagal memanggil library 'bcrypt' ({exc.__class__.__name__}: {exc}). "
        "Kode aplikasi ini TIDAK memakai passlib lagi, jadi kemungkinan besar "
        "virtual environment lokal Anda punya sisa instalasi 'bcrypt' yang "
        "rusak/tidak bersih (sering terjadi di Windows saat upgrade paket "
        "berekstensi native). Perbaikan: HAPUS TOTAL folder virtual "
        "environment lama (mis. .venv/venv/env), buat baru "
        "('python -m venv .venv'), lalu 'pip install -r requirements.txt' "
        "dari kosong -- jangan install di atas venv lama. Lihat bagian "
        "'Instalasi' / 'Troubleshooting Windows' di README.md."
    )


def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")
    except Exception as e:
        raise RuntimeError(_pesan_diagnosa_bcrypt(e)) from e


def verify_password(password: str, password_hash: str) -> bool:
    pw_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))
    except Exception as e:
        raise RuntimeError(_pesan_diagnosa_bcrypt(e)) from e


def tambah_user(username: str, password: str, role: str, barber_id: int = None) -> int:
    from datetime import datetime
    username = (username or "").strip()
    if not username:
        raise ValueError("Username tidak boleh kosong.")
    if role not in ("admin", "barber"):
        raise ValueError("Role harus 'admin' atau 'barber'.")
    if role == "barber" and barber_id is None:
        raise ValueError("User dengan role 'barber' wajib dikaitkan ke barber_id.")
    if not password or len(password) < 4:
        raise ValueError("Password minimal 4 karakter.")

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, role, barber_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, hash_password(password), role, barber_id, now),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' sudah dipakai.")
        return cur.lastrowid


def get_user_by_username(username: str):
    """BUGFIX (login 'kadang' gagal dengan kredensial benar): pencocokan
    username sekarang case-INSENSITIVE (COLLATE NOCASE). Sebelumnya exact
    match case-sensitive -- kalau keyboard HP user kebetulan meng-kapital-
    kan huruf pertama (perilaku default autocapitalize banyak browser
    mobile, lihat juga perbaikan di frontend/js/pages/login.js), lookup ini
    tidak menemukan usernya sama sekali dan login ditolak walau password
    benar. `ORDER BY (username = ?) DESC` memprioritaskan exact match kalau
    kebetulan ada dua username yang hanya beda huruf besar/kecil (username
    tetap disimpan case-sensitive & unique persis seperti diketik saat
    dibuat -- ini HANYA mengubah cara mencari/mencocokkan saat login)."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM users
               WHERE username = ? COLLATE NOCASE AND aktif = 1
               ORDER BY (username = ?) DESC
               LIMIT 1""",
            (username, username),
        ).fetchone()
        return dict(row) if row else None


def get_user(user_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_list():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY role, username").fetchall()
        return [dict(r) for r in rows]


def nonaktifkan_user(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET aktif = 0 WHERE id = ?", (user_id,))


def ganti_password(user_id: int, password_baru: str):
    if not password_baru or len(password_baru) < 4:
        raise ValueError("Password minimal 4 karakter.")
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(password_baru), user_id))


def reset_atau_buat_admin_darurat(username: str, password: str) -> str:
    """'Break-glass' pemulihan akses admin -- dipanggil HANYA lewat
    main.py._reset_admin_darurat(), yang sendiri hanya berjalan kalau dua
    environment variable (ADMIN_RESET_USERNAME/ADMIN_RESET_PASSWORD) diisi
    eksplisit oleh operator (mis. lewat dashboard Render), tidak pernah
    otomatis/diam-diam. Beda dengan _bootstrap_admin_pertama() yang HANYA
    jalan kalau tabel users benar-benar kosong (instalasi baru), fungsi ini
    dipakai untuk server yang SUDAH berjalan tapi admin-nya lupa kredensial.

    - Kalau `username` itu SUDAH ada (aktif ataupun sudah dinonaktifkan):
      password-nya di-reset, dipaksa role='admin' & aktif=1 (jadi juga
      memulihkan akun yang kebetulan sempat dinonaktifkan).
    - Kalau `username` itu BELUM ada: dibuat baru sebagai admin.

    Baris user LAIN, dan seluruh tabel bisnis lain (barbers/transaksi/
    produk/pengeluaran/settings/dst di database.py), TIDAK disentuh sama
    sekali -- hanya SATU baris di tabel `users` yang diubah/ditambah.
    Return "direset" atau "dibuat" (bukan password) untuk keperluan log."""
    from datetime import datetime

    username = (username or "").strip()
    if not username:
        raise ValueError("Username untuk reset admin tidak boleh kosong.")
    if not password or len(password) < 4:
        raise ValueError("Password untuk reset admin minimal 4 karakter.")

    pw_hash = hash_password(password)
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO users (username, password_hash, role, barber_id, aktif, created_at) "
                "VALUES (?, ?, 'admin', NULL, 1, ?)",
                (username, pw_hash, now),
            )
            return "dibuat"
        conn.execute(
            "UPDATE users SET password_hash = ?, role = 'admin', barber_id = NULL, aktif = 1 WHERE id = ?",
            (pw_hash, row["id"]),
        )
        return "direset"


def autentikasi(username: str, password: str):
    """Return dict user (tanpa password_hash) kalau username+password benar, None kalau salah."""
    user = get_user_by_username(username)
    if user is None:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    user = dict(user)
    user.pop("password_hash")
    return user
