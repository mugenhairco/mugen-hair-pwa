"""test_db_compat_koneksi_basi.py — BUGFIX: koneksi Postgres basi (Neon
auto-suspend) harus dibuang & diganti otomatis, bukan menggagalkan request
(500 Internal Server Error).

CATATAN TEKNIS (pola SAMA seperti test_backup_postgres.py): db_compat.
IS_POSTGRES ditentukan SEKALI saat modul diimpor dari DATABASE_URL env var
-- dijalankan di SUBPROCESS terpisah dengan DATABASE_URL (nilai PALSU/tidak
pernah benar-benar dipakai konek, lihat skrip di bawah -- pool-nya di-mock
total, psycopg2.pool.ThreadedConnectionPool TIDAK PERNAH dipanggil) di-set
SEBELUM import, supaya db_compat._ambil_koneksi_valid() (fungsi KHUSUS
jalur Postgres) bisa diuji TANPA butuh server Postgres sungguhan."""

import os
import subprocess
import sys
import textwrap

from conftest import APP_DIR

_SCRIPT = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {app_dir!r})
    os.environ["DATABASE_URL"] = "postgresql://fake:fake@localhost/fake"

    import db_compat
    import psycopg2
    from unittest.mock import MagicMock

    def _cursor_mock(error=None):
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        if error is not None:
            cur.execute.side_effect = error
        return cur

    def _conn_mock(error=None):
        conn = MagicMock()
        conn.cursor.return_value = _cursor_mock(error)
        return conn

    # Skenario 1: koneksi PERTAMA basi (OperationalError), KEDUA sehat --
    # yang basi harus DIBUANG (close=True), yang sehat yang dikembalikan.
    conn_basi = _conn_mock(psycopg2.OperationalError("SSL connection has been closed unexpectedly"))
    conn_sehat = _conn_mock()
    pool = MagicMock()
    pool.getconn.side_effect = [conn_basi, conn_sehat]

    hasil = db_compat._ambil_koneksi_valid(pool)
    assert hasil is conn_sehat, "harus mengembalikan koneksi yang SEHAT, bukan yang basi"
    pool.putconn.assert_called_once_with(conn_basi, close=True)
    print("skenario1 OK: koneksi basi dibuang, koneksi sehat dipakai")

    # Skenario 2: koneksi SEHAT di percobaan pertama -- TIDAK ADA yang dibuang sama sekali.
    conn_sehat2 = _conn_mock()
    pool2 = MagicMock()
    pool2.getconn.side_effect = [conn_sehat2]
    hasil2 = db_compat._ambil_koneksi_valid(pool2)
    assert hasil2 is conn_sehat2
    pool2.putconn.assert_not_called()
    print("skenario2 OK: koneksi sehat langsung dipakai, tidak ada yang dibuang")

    # Skenario 3: SEMUA percobaan basi (InterfaceError, "connection already
    # closed") -- exception ASLI harus tetap muncul di percobaan TERAKHIR
    # (bukan diam-diam ditelan selamanya), dan 4 koneksi basi sebelumnya
    # (dari _MAKSIMAL_PERCOBAAN_KONEKSI=5, percobaan terakhir TIDAK dibuang
    # karena errornya dibiarkan menyebar) sudah dibuang.
    pool3 = MagicMock()
    pool3.getconn.side_effect = [
        _conn_mock(psycopg2.InterfaceError("connection already closed")) for _ in range(5)
    ]
    try:
        db_compat._ambil_koneksi_valid(pool3)
        raise AssertionError("harusnya melempar psycopg2.InterfaceError, bukan berhasil diam-diam")
    except psycopg2.InterfaceError:
        pass
    assert pool3.putconn.call_count == 4, f"harusnya 4x dibuang, dapat {{pool3.putconn.call_count}}x"
    print("skenario3 OK: kegagalan Neon sungguhan tetap terlihat, bukan ditelan diam-diam")

    print("SEMUA SKENARIO LOLOS")
""")


def test_koneksi_basi_dibuang_dan_diganti_otomatis():
    env = dict(os.environ)
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT.format(app_dir=APP_DIR)],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "SEMUA SKENARIO LOLOS" in result.stdout
