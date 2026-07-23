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

Password disimpan sebagai HASH (bcrypt via passlib), tidak pernah plaintext.
"""

import sqlite3
from contextlib import contextmanager

from database import DB_PATH  # pakai path database yang SAMA dengan database.py (satu file .db yang sama)

try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    _pwd_context = None


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


def hash_password(password: str) -> str:
    if _pwd_context is None:
        raise RuntimeError("Library 'passlib' belum terinstall. Jalankan: pip install passlib bcrypt")
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if _pwd_context is None:
        raise RuntimeError("Library 'passlib' belum terinstall. Jalankan: pip install passlib bcrypt")
    return _pwd_context.verify(password, password_hash)


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
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? AND aktif = 1", (username,)).fetchone()
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
