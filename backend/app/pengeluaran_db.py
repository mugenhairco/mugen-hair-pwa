"""
pengeluaran_db.py — Logika CRUD Pengeluaran (TAHAP 9)
=======================================================
Dipisahkan dari database.py (sesuai instruksi Tahap 9: jangan mengubah
database.py kecuali benar-benar diperlukan). File ini beroperasi pada
tabel `pengeluaran` yang sama persis (dibuat di database.py Tahap 2),
dengan kolom tambahan (kategori, barber_id, aktif) yang ditambahkan lewat
pengeluaran_migrasi.py.

Fungsi tambah_pengeluaran/koreksi_pengeluaran/dst di database.py (versi
Tahap 2, tanpa kategori/barber/aktif) TIDAK diubah maupun dihapus — supaya
Tahap 1-8 tetap seperti semula. File ini menyediakan versi LENGKAP untuk
dipakai khusus oleh router Tahap 9 (routers/pengeluaran.py).
"""

from datetime import datetime

from database import get_conn

# Daftar kategori default yang selalu muncul di dropdown filter/formulir,
# supaya toko punya kategori standar sejak awal walau belum ada datanya.
# Kategori baru tetap bisa ditambahkan bebas lewat form (kategori = teks
# bebas, bukan enum tertutup) dan akan otomatis ikut muncul di daftar.
KATEGORI_DEFAULT = ["Operasional", "Sewa", "Listrik & Air", "Bahan/Chemical", "Gaji", "Lainnya"]


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


def tambah_pengeluaran(tanggal: str, kategori: str, keterangan: str, jumlah: int,
                        barber_id: int = None, aktif: bool = True) -> int:
    kategori, keterangan = _validasi_input(tanggal, kategori, keterangan, jumlah)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        _pastikan_barber_valid(conn, barber_id)
        cur = conn.execute(
            """INSERT INTO pengeluaran (tanggal, kategori, keterangan, jumlah, barber_id, aktif, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tanggal, kategori, keterangan, int(jumlah), barber_id, 1 if aktif else 0, now),
        )
        return cur.lastrowid


def koreksi_pengeluaran(pengeluaran_id: int, tanggal: str, kategori: str, keterangan: str,
                         jumlah: int, barber_id: int = None, aktif: bool = True):
    kategori, keterangan = _validasi_input(tanggal, kategori, keterangan, jumlah)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM pengeluaran WHERE id = ?", (pengeluaran_id,)).fetchone()
        if existing is None:
            raise ValueError("Data pengeluaran tidak ditemukan.")
        _pastikan_barber_valid(conn, barber_id)
        conn.execute(
            """UPDATE pengeluaran
               SET tanggal = ?, kategori = ?, keterangan = ?, jumlah = ?,
                   barber_id = ?, aktif = ?, updated_at = ?
               WHERE id = ?""",
            (tanggal, kategori, keterangan, int(jumlah), barber_id, 1 if aktif else 0, now, pengeluaran_id),
        )


def hapus_pengeluaran(pengeluaran_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM pengeluaran WHERE id = ?", (pengeluaran_id,))


def get_pengeluaran(pengeluaran_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.*, b.nama AS nama_barber
               FROM pengeluaran p LEFT JOIN barbers b ON b.id = p.barber_id
               WHERE p.id = ?""",
            (pengeluaran_id,),
        ).fetchone()
        return dict(row) if row else None


def get_pengeluaran_list(tahun: int = None, bulan: int = None, tanggal: str = None,
                          kategori: str = None, cari: str = None, hanya_aktif: bool = None) -> list:
    """Urutan: tanggal terbaru dulu. `cari` mencari di keterangan & kategori."""
    q = """SELECT p.*, b.nama AS nama_barber
           FROM pengeluaran p LEFT JOIN barbers b ON b.id = p.barber_id WHERE 1=1"""
    params = []
    if tahun is not None:
        q += " AND strftime('%Y', p.tanggal) = ?"; params.append(f"{tahun:04d}")
    if bulan is not None:
        q += " AND strftime('%m', p.tanggal) = ?"; params.append(f"{bulan:02d}")
    if tanggal is not None:
        q += " AND p.tanggal = ?"; params.append(tanggal)
    if kategori:
        q += " AND p.kategori = ?"; params.append(kategori)
    if cari:
        q += " AND (p.keterangan LIKE ? OR p.kategori LIKE ?)"
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
            "SELECT DISTINCT kategori FROM pengeluaran WHERE kategori IS NOT NULL AND kategori != '' ORDER BY kategori"
        ).fetchall()
    dinamis = [r["kategori"] for r in rows]
    gabungan = list(dict.fromkeys(KATEGORI_DEFAULT + dinamis))  # urutan dijaga, tanpa duplikat
    return gabungan
