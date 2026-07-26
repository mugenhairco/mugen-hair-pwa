"""
db_compat.py — Lapisan kompatibilitas SQLite <-> PostgreSQL (migrasi Neon)
=============================================================================
Dialek database aktif ditentukan SEKALI saat modul ini pertama kali diimpor,
dari environment variable DATABASE_URL:
- KOSONG/tidak diisi -> SQLite. Modul ini praktis tidak melakukan apa-apa
  (IS_POSTGRES=False, IntegrityError=sqlite3.IntegrityError) -- get_conn() di
  database.py/auth_db.py tetap 100% jalur SQLite asli, byte-identik dengan
  sebelum file ini ada. psycopg2 TIDAK PERNAH diimpor sama sekali di jalur ini,
  jadi tidak perlu terpasang untuk menjalankan aplikasi secara lokal/SQLite.
- Diisi (connection string Neon/Postgres lain) -> IS_POSTGRES=True. get_conn()
  di sini dipakai (didelegasikan dari database.py/auth_db.py) lewat connection
  pool (psycopg2 ThreadedConnectionPool) + wrapper cursor yang menerjemahkan
  placeholder '?' -> '%s' dan meng-emulasi `cursor.lastrowid` (lewat otomatis
  menambahkan "RETURNING id" pada setiap statement INSERT tanpa RETURNING
  eksplisit -- SELURUH tabel di postgres_schema.py memakai kolom 'id' sebagai
  primary key, jadi ini berlaku universal) -- supaya seluruh call-site yang
  sudah ada di database.py/auth_db.py/dst TIDAK PERLU tahu dialek mana yang
  sedang aktif ataupun diubah satu baris pun.

BUKAN cakupan modul ini: beberapa query yang sintaksnya BERBEDA total antar
dialek (strftime(), PRAGMA table_info, COLLATE NOCASE, LIKE case-sensitivity)
tidak bisa diterjemahkan otomatis lewat regex placeholder saja -- itu ditulis
ulang langsung di file pemanggilnya masing-masing (lihat README bagian
Migrasi PostgreSQL untuk daftar lengkap lokasinya).
"""

import os
import re
import sqlite3
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = bool(DATABASE_URL)

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool

    IntegrityError = psycopg2.IntegrityError
else:
    IntegrityError = sqlite3.IntegrityError


_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        minconn = int(os.environ.get("PG_POOL_MIN", "1"))
        maxconn = int(os.environ.get("PG_POOL_MAX", "10"))
        _pool = psycopg2.pool.ThreadedConnectionPool(minconn, maxconn, dsn=DATABASE_URL)
    return _pool


# Ganti '?' -> '%s' di LUAR string literal SQL (diapit kutip satu, termasuk
# kutip satu yang di-escape lewat '' ganda) -- supaya kalau suatu saat ada
# literal '?' di dalam teks SQL, tidak ikut tertukar jadi placeholder.
_TOKEN_RE = re.compile(r"'(?:[^']|'')*'|\?")
_INSERT_RE = re.compile(r"^\s*INSERT\b", re.IGNORECASE)
_RETURNING_RE = re.compile(r"\bRETURNING\b", re.IGNORECASE)


def _translate(query: str) -> str:
    return _TOKEN_RE.sub(lambda m: "%s" if m.group(0) == "?" else m.group(0), query)


class _PGCursor:
    """Menyediakan `.lastrowid` (tidak ada secara native di psycopg2) supaya
    seluruh call-site `cur = conn.execute(...); x = cur.lastrowid` yang sudah
    ada tetap berfungsi tanpa perubahan."""

    __slots__ = ("_cur", "lastrowid")

    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None

    def execute(self, query, params=()):
        is_insert = bool(_INSERT_RE.match(query)) and not _RETURNING_RE.search(query)
        # "RETURNING *" (bukan "RETURNING id") -- beberapa tabel (settings,
        # sync_meta) pakai 'key' sebagai primary key, tidak punya kolom 'id'
        # sama sekali, jadi "RETURNING id" akan gagal UndefinedColumn untuk
        # tabel itu. Ambil 'id' dari hasil HANYA kalau kolom itu memang ada.
        sql = _translate(query) + (" RETURNING *" if is_insert else "")
        self._cur.execute(sql, params)
        self.lastrowid = None
        if is_insert:
            # Statement macam "ON CONFLICT DO NOTHING" yang kena konflik (batal
            # menyisipkan baris apa pun) tidak menghasilkan baris RETURNING --
            # lastrowid tetap None, sama seperti tidak ada baris yang dibaca.
            row = self._cur.fetchone()
            if row is not None:
                self.lastrowid = row.get("id")
        return self

    def executemany(self, query, seq_of_params):
        self._cur.executemany(_translate(query), seq_of_params)
        return self

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _PGConn:
    __slots__ = ("_conn",)

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=()):
        return _PGCursor(self._conn.cursor()).execute(query, params)

    def executemany(self, query, seq_of_params):
        return _PGCursor(self._conn.cursor()).executemany(query, seq_of_params)

    def cursor(self):
        return _PGCursor(self._conn.cursor())

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def get_conn():
    pool = _get_pool()
    raw = pool.getconn()
    raw.cursor_factory = psycopg2.extras.RealDictCursor
    try:
        yield _PGConn(raw)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        pool.putconn(raw)
