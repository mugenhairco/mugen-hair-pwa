"""
transfer_db.py — Modul Keuangan: Transfer Kas/Bank (Fase 2)
=============================================================================
Fase 2 dari "Modul Keuangan" -- catatan mutasi dana ANTAR akun milik toko
sendiri (mis. setor tunai dari Kas ke Bank, tarik tunai dari Bank ke Kas).
MURNI catatan pemindahan, BUKAN pemasukan/pengeluaran riil -- sengaja TIDAK
dihubungkan ke perhitungan laba/rugi atau kartu Dashboard mana pun (uang
berpindah antar kantong sendiri, saldo bersih toko tidak berubah).

`dari_akun`/`ke_akun` teks bebas (pola sama seperti `kategori` di
pemasukan_db.py/pengeluaran_db.py -- datalist saran, bukan enum tertutup)
supaya toko bebas mendefinisikan nama akunnya sendiri (Kas Tunai, Bank BCA,
Bank Mandiri, dst) tanpa perlu tabel akun terpisah.

Pola akses SAMA seperti Pemasukan/Pengeluaran: data finansial TOKO, staff
akses penuh tanpa sistem izin, barber tidak ada akses sama sekali.

Tabel baru murni milik modul ini -- init_transfer_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

from datetime import datetime

import db_compat
from database import get_conn

AKUN_DEFAULT = ["Kas Tunai", "Bank"]


def init_transfer_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transfer_dana (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal      TEXT NOT NULL,
                dari_akun    TEXT NOT NULL,
                ke_akun      TEXT NOT NULL,
                jumlah       INTEGER NOT NULL,
                keterangan   TEXT,
                dibuat_oleh  TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT
            )
        """)


def _validasi_input(tanggal: str, dari_akun: str, ke_akun: str, jumlah: int):
    datetime.strptime(tanggal, "%Y-%m-%d")  # raise ValueError kalau format salah
    dari_akun = (dari_akun or "").strip()
    ke_akun = (ke_akun or "").strip()
    if not dari_akun or not ke_akun:
        raise ValueError("Akun Asal dan Akun Tujuan wajib diisi.")
    if dari_akun == ke_akun:
        raise ValueError("Akun Asal dan Akun Tujuan tidak boleh sama.")
    if jumlah is None or jumlah <= 0:
        raise ValueError("Nominal harus diisi dan lebih dari 0.")
    return dari_akun, ke_akun


def tambah_transfer(tanggal: str, dari_akun: str, ke_akun: str, jumlah: int,
                     keterangan: str = "", dibuat_oleh: str = "") -> int:
    dari_akun, ke_akun = _validasi_input(tanggal, dari_akun, ke_akun, jumlah)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO transfer_dana (tanggal, dari_akun, ke_akun, jumlah, keterangan, dibuat_oleh, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tanggal, dari_akun, ke_akun, int(jumlah), (keterangan or "").strip(), dibuat_oleh, now),
        )
        return cur.lastrowid


def koreksi_transfer(transfer_id: int, tanggal: str, dari_akun: str, ke_akun: str,
                      jumlah: int, keterangan: str = ""):
    dari_akun, ke_akun = _validasi_input(tanggal, dari_akun, ke_akun, jumlah)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM transfer_dana WHERE id = ?", (transfer_id,)).fetchone()
        if existing is None:
            raise ValueError("Data transfer tidak ditemukan.")
        conn.execute(
            """UPDATE transfer_dana SET tanggal = ?, dari_akun = ?, ke_akun = ?, jumlah = ?,
                   keterangan = ?, updated_at = ? WHERE id = ?""",
            (tanggal, dari_akun, ke_akun, int(jumlah), (keterangan or "").strip(), now, transfer_id),
        )


def hapus_transfer(transfer_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM transfer_dana WHERE id = ?", (transfer_id,))


def get_transfer(transfer_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM transfer_dana WHERE id = ?", (transfer_id,)).fetchone()
        return dict(row) if row else None


def get_transfer_list(tahun: int = None, bulan: int = None, tanggal_mulai: str = None,
                       tanggal_selesai: str = None, cari: str = None) -> list:
    q = "SELECT * FROM transfer_dana WHERE 1=1"
    params = []
    if tahun is not None:
        q += " AND tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal_mulai is not None:
        q += " AND tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND tanggal <= ?"; params.append(tanggal_selesai)
    if cari:
        operator = "ILIKE" if db_compat.IS_POSTGRES else "LIKE"
        q += f" AND (dari_akun {operator} ? OR ke_akun {operator} ? OR keterangan {operator} ?)"
        like = f"%{cari}%"
        params.extend([like, like, like])
    q += " ORDER BY tanggal DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]


def get_akun_list() -> list:
    """Gabungan akun default + akun yang sudah pernah dipakai (dari_akun
    ATAU ke_akun), sama seperti pola get_kategori_list() di
    pemasukan_db.py/pengeluaran_db.py."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT dari_akun AS akun FROM transfer_dana WHERE dari_akun IS NOT NULL AND dari_akun != ''
               UNION
               SELECT ke_akun AS akun FROM transfer_dana WHERE ke_akun IS NOT NULL AND ke_akun != ''
               ORDER BY akun"""
        ).fetchall()
    dinamis = [r["akun"] for r in rows]
    return list(dict.fromkeys(AKUN_DEFAULT + dinamis))
