"""
pemasukan_db.py — Modul Keuangan: Pemasukan (Fase 1)
=============================================================================
Fase 1 dari "Modul Keuangan" (B pada spesifikasi besar) -- pencatatan
pemasukan LAIN di luar pendapatan service/booking yang sudah tercatat lewat
tabel `transaksi` (mis. penjualan aset lama, suntikan modal, pendapatan
sewa, dsb). Struktur & pola akses SENGAJA MENCERMIN `pengeluaran_db.py`
persis -- sama-sama data finansial TOKO (bukan data payroll individu
seperti Kasbon/Komisi/Reimburse), jadi mengikuti pola akses Pengeluaran:
staff ('Admin') akses PENUH tanpa sistem izin, barber TIDAK punya akses
sama sekali (lihat routers/pemasukan.py).

Tabel baru murni milik modul ini -- init_pemasukan_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

from datetime import datetime

import db_compat
from database import get_conn

KATEGORI_DEFAULT = ["Penjualan Aset", "Modal Tambahan", "Sewa", "Lainnya"]


def init_pemasukan_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pemasukan (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal      TEXT NOT NULL,
                kategori     TEXT NOT NULL,
                keterangan   TEXT NOT NULL,
                jumlah       INTEGER NOT NULL,
                barber_id    INTEGER,
                aktif        INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT NOT NULL,
                updated_at   TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)


def _validasi_tanggal(tanggal: str):
    datetime.strptime(tanggal, "%Y-%m-%d")  # raise ValueError kalau format salah


def _validasi_input(tanggal: str, kategori: str, keterangan: str, jumlah: int):
    _validasi_tanggal(tanggal)
    kategori = (kategori or "").strip()
    if not kategori:
        raise ValueError("Kategori tidak boleh kosong.")
    keterangan = (keterangan or "").strip()
    if not keterangan:
        raise ValueError("Keterangan tidak boleh kosong.")
    if jumlah is None or jumlah <= 0:
        raise ValueError("Nominal harus diisi dan lebih dari 0.")
    return kategori, keterangan


def _pastikan_barber_valid(conn, barber_id):
    if barber_id is None:
        return
    ada = conn.execute("SELECT 1 FROM barbers WHERE id = ?", (barber_id,)).fetchone()
    if not ada:
        raise ValueError("Barber yang dipilih tidak ditemukan.")


def tambah_pemasukan(tanggal: str, kategori: str, keterangan: str, jumlah: int,
                      barber_id: int = None, aktif: bool = True) -> int:
    kategori, keterangan = _validasi_input(tanggal, kategori, keterangan, jumlah)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        _pastikan_barber_valid(conn, barber_id)
        cur = conn.execute(
            """INSERT INTO pemasukan (tanggal, kategori, keterangan, jumlah, barber_id, aktif, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tanggal, kategori, keterangan, int(jumlah), barber_id, 1 if aktif else 0, now),
        )
        return cur.lastrowid


def koreksi_pemasukan(pemasukan_id: int, tanggal: str, kategori: str, keterangan: str,
                       jumlah: int, barber_id: int = None, aktif: bool = True):
    kategori, keterangan = _validasi_input(tanggal, kategori, keterangan, jumlah)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM pemasukan WHERE id = ?", (pemasukan_id,)).fetchone()
        if existing is None:
            raise ValueError("Data pemasukan tidak ditemukan.")
        _pastikan_barber_valid(conn, barber_id)
        conn.execute(
            """UPDATE pemasukan
               SET tanggal = ?, kategori = ?, keterangan = ?, jumlah = ?,
                   barber_id = ?, aktif = ?, updated_at = ?
               WHERE id = ?""",
            (tanggal, kategori, keterangan, int(jumlah), barber_id, 1 if aktif else 0, now, pemasukan_id),
        )


def hapus_pemasukan(pemasukan_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM pemasukan WHERE id = ?", (pemasukan_id,))


def get_pemasukan(pemasukan_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.*, b.nama AS nama_barber
               FROM pemasukan p LEFT JOIN barbers b ON b.id = p.barber_id
               WHERE p.id = ?""",
            (pemasukan_id,),
        ).fetchone()
        return dict(row) if row else None


def get_pemasukan_list(tahun: int = None, bulan: int = None, tanggal: str = None,
                        tanggal_mulai: str = None, tanggal_selesai: str = None,
                        kategori: str = None, cari: str = None, hanya_aktif: bool = None) -> list:
    """Urutan: tanggal terbaru dulu. `cari` mencari di keterangan & kategori.
    tanggal_mulai/tanggal_selesai (format 'YYYY-MM-DD', inklusif di kedua
    ujung) dipakai Laporan PDF untuk rentang tanggal bebas -- BEDA dari
    tahun/bulan (satu bulan/tahun penuh)."""
    q = """SELECT p.*, b.nama AS nama_barber
           FROM pemasukan p LEFT JOIN barbers b ON b.id = p.barber_id WHERE 1=1"""
    params = []
    if tahun is not None:
        q += " AND p.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND p.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal is not None:
        q += " AND p.tanggal = ?"; params.append(tanggal)
    if tanggal_mulai is not None:
        q += " AND p.tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND p.tanggal <= ?"; params.append(tanggal_selesai)
    if kategori:
        q += " AND p.kategori = ?"; params.append(kategori)
    if cari:
        operator = "ILIKE" if db_compat.IS_POSTGRES else "LIKE"
        q += f" AND (p.keterangan {operator} ? OR p.kategori {operator} ?)"
        like = f"%{cari}%"
        params.append(like)
        params.append(like)
    if hanya_aktif is not None:
        q += " AND p.aktif = ?"; params.append(1 if hanya_aktif else 0)
    q += " ORDER BY p.tanggal DESC, p.id DESC"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]


def get_kategori_list() -> list:
    """Gabungan kategori default + kategori yang sudah pernah dipakai di data,
    supaya dropdown filter/form selalu lengkap tanpa perlu tabel kategori terpisah."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT kategori FROM pemasukan WHERE kategori IS NOT NULL AND kategori != '' ORDER BY kategori"
        ).fetchall()
    dinamis = [r["kategori"] for r in rows]
    return list(dict.fromkeys(KATEGORI_DEFAULT + dinamis))  # urutan dijaga, tanpa duplikat
