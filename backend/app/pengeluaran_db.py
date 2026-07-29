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

import db_compat
import reimburse_db
import uang_kas_db
from database import get_conn

# Daftar kategori default yang selalu muncul di dropdown filter/formulir,
# supaya toko punya kategori standar sejak awal walau belum ada datanya.
# Kategori baru tetap bisa ditambahkan bebas lewat form (kategori = teks
# bebas, bukan enum tertutup) dan akan otomatis ikut muncul di daftar.
KATEGORI_DEFAULT = ["Operasional", "Sewa", "Listrik & Air", "Bahan/Chemical", "Gaji", "Lainnya"]

SUMBER_DANA_VALID = {"kas", "karyawan"}


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


def _validasi_sumber_dana(sumber_dana: str, barber_id) -> str:
    sumber_dana = (sumber_dana or "kas").strip()
    if sumber_dana not in SUMBER_DANA_VALID:
        raise ValueError(f"Sumber dana tidak dikenal: {sumber_dana}")
    if sumber_dana == "karyawan" and barber_id is None:
        raise ValueError("Karyawan wajib dipilih kalau sumber dana adalah Uang Karyawan.")
    return sumber_dana


def _pastikan_barber_valid(conn, barber_id):
    if barber_id is None:
        return
    ada = conn.execute("SELECT 1 FROM barbers WHERE id = ?", (barber_id,)).fetchone()
    if not ada:
        raise ValueError("Karyawan yang dipilih tidak ditemukan.")


def _reimburse_terkunci(reimburse_id) -> bool:
    if not reimburse_id:
        return False
    row = reimburse_db.get_reimburse(reimburse_id)
    return bool(row and row["terkunci"])


def tambah_pengeluaran(tanggal: str, kategori: str, keterangan: str, jumlah: int,
                        barber_id: int = None, aktif: bool = True,
                        sumber_dana: str = "kas", dibuat_oleh: str = None) -> int:
    kategori, keterangan = _validasi_input(tanggal, kategori, keterangan, jumlah)
    sumber_dana = _validasi_sumber_dana(sumber_dana, barber_id)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        _pastikan_barber_valid(conn, barber_id)
        cur = conn.execute(
            """INSERT INTO pengeluaran (tanggal, kategori, keterangan, jumlah, barber_id, aktif,
                                         sumber_dana, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (tanggal, kategori, keterangan, int(jumlah), barber_id, 1 if aktif else 0, sumber_dana, now),
        )
        pengeluaran_id = cur.lastrowid

    if sumber_dana == "kas":
        kas_penyesuaian_id = uang_kas_db.tambah_penyesuaian(
            tanggal, "kurang", int(jumlah), keterangan=f"Pengeluaran: {keterangan}", dibuat_oleh=dibuat_oleh,
        )
        with get_conn() as conn:
            conn.execute("UPDATE pengeluaran SET kas_penyesuaian_id = ? WHERE id = ?",
                         (kas_penyesuaian_id, pengeluaran_id))
    else:
        reimburse = reimburse_db.buat_reimburse_sistem(
            barber_id, tanggal, kategori, int(jumlah), keterangan=keterangan, dibuat_oleh=dibuat_oleh,
        )
        with get_conn() as conn:
            conn.execute("UPDATE pengeluaran SET reimburse_id = ? WHERE id = ?",
                         (reimburse["id"], pengeluaran_id))

    return pengeluaran_id


def koreksi_pengeluaran(pengeluaran_id: int, tanggal: str, kategori: str, keterangan: str,
                         jumlah: int, barber_id: int = None, aktif: bool = True,
                         sumber_dana: str = "kas", dibuat_oleh: str = None):
    kategori, keterangan = _validasi_input(tanggal, kategori, keterangan, jumlah)
    sumber_dana = _validasi_sumber_dana(sumber_dana, barber_id)
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM pengeluaran WHERE id = ?", (pengeluaran_id,)).fetchone()
        if existing is None:
            raise ValueError("Data pengeluaran tidak ditemukan.")
        existing = dict(existing)
        _pastikan_barber_valid(conn, barber_id)

    if _reimburse_terkunci(existing["reimburse_id"]):
        raise ValueError(
            "Pengeluaran ini terkait Reimburse yang periodenya sudah dibayar lewat Slip Gaji "
            "dan tidak bisa diubah."
        )

    sumber_lama = existing["sumber_dana"]
    kas_id_lama = existing["kas_penyesuaian_id"]
    reimburse_id_lama = existing["reimburse_id"]
    barber_id_lama = existing["barber_id"]
    now = datetime.now().isoformat(timespec="seconds")

    # Kasus paling umum: sumber dana (dan karyawannya, kalau 'karyawan')
    # TIDAK berubah -- link kas_penyesuaian/reimburse yang sudah ada cukup
    # di-sync di tempat, tidak perlu dihapus/dibuat ulang.
    if sumber_dana == sumber_lama and (sumber_dana == "kas" or barber_id == barber_id_lama):
        with get_conn() as conn:
            conn.execute(
                """UPDATE pengeluaran
                   SET tanggal = ?, kategori = ?, keterangan = ?, jumlah = ?,
                       barber_id = ?, aktif = ?, sumber_dana = ?, updated_at = ?
                   WHERE id = ?""",
                (tanggal, kategori, keterangan, int(jumlah), barber_id, 1 if aktif else 0, sumber_dana,
                 now, pengeluaran_id),
            )
        if sumber_dana == "kas" and kas_id_lama:
            uang_kas_db.edit_penyesuaian(
                kas_id_lama, tanggal=tanggal, jumlah=int(jumlah), keterangan=f"Pengeluaran: {keterangan}",
            )
        elif sumber_dana == "karyawan" and reimburse_id_lama:
            reimburse_db.edit_reimburse_sistem(
                reimburse_id_lama, tanggal=tanggal, kategori=kategori, nominal=int(jumlah), keterangan=keterangan,
            )
        return

    # Sumber dana (atau karyawannya) berubah -- link lama harus diganti.
    # Kosongkan dulu referensi kas_penyesuaian_id/reimburse_id di baris
    # pengeluaran ini SEBELUM baris yang direferensikan itu dihapus --
    # dibalik urutannya akan kena "FOREIGN KEY constraint failed" karena
    # baris ini masih memegang FK ke baris yang mau dihapus.
    with get_conn() as conn:
        conn.execute(
            """UPDATE pengeluaran
               SET tanggal = ?, kategori = ?, keterangan = ?, jumlah = ?,
                   barber_id = ?, aktif = ?, sumber_dana = ?,
                   kas_penyesuaian_id = NULL, reimburse_id = NULL, updated_at = ?
               WHERE id = ?""",
            (tanggal, kategori, keterangan, int(jumlah), barber_id, 1 if aktif else 0, sumber_dana,
             now, pengeluaran_id),
        )

    if kas_id_lama:
        uang_kas_db.hapus_penyesuaian(kas_id_lama)
    if reimburse_id_lama:
        reimburse_db.hapus_reimburse_sistem(reimburse_id_lama)

    if sumber_dana == "kas":
        kas_penyesuaian_id_baru = uang_kas_db.tambah_penyesuaian(
            tanggal, "kurang", int(jumlah), keterangan=f"Pengeluaran: {keterangan}", dibuat_oleh=dibuat_oleh,
        )
        with get_conn() as conn:
            conn.execute("UPDATE pengeluaran SET kas_penyesuaian_id = ? WHERE id = ?",
                         (kas_penyesuaian_id_baru, pengeluaran_id))
    else:
        reimburse = reimburse_db.buat_reimburse_sistem(
            barber_id, tanggal, kategori, int(jumlah), keterangan=keterangan, dibuat_oleh=dibuat_oleh,
        )
        with get_conn() as conn:
            conn.execute("UPDATE pengeluaran SET reimburse_id = ? WHERE id = ?",
                         (reimburse["id"], pengeluaran_id))


def hapus_pengeluaran(pengeluaran_id: int):
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM pengeluaran WHERE id = ?", (pengeluaran_id,)).fetchone()
        if existing is None:
            return
        existing = dict(existing)

    if _reimburse_terkunci(existing["reimburse_id"]):
        raise ValueError(
            "Pengeluaran ini terkait Reimburse yang periodenya sudah dibayar lewat Slip Gaji "
            "dan tidak bisa dihapus."
        )

    # Hapus baris pengeluaran DULU -- baris ini masih memegang FK ke
    # kas_penyesuaian_id/reimburse_id, jadi baris yang di-reference itu
    # baru boleh dihapus SETELAH referensinya sendiri sudah tidak ada
    # (kalau dibalik, DELETE kas_penyesuaian/reimburse akan gagal dengan
    # FOREIGN KEY constraint failed selama baris pengeluaran ini masih ada).
    with get_conn() as conn:
        conn.execute("DELETE FROM pengeluaran WHERE id = ?", (pengeluaran_id,))

    if existing["kas_penyesuaian_id"]:
        uang_kas_db.hapus_penyesuaian(existing["kas_penyesuaian_id"])
    if existing["reimburse_id"]:
        reimburse_db.hapus_reimburse_sistem(existing["reimburse_id"])


def get_pengeluaran(pengeluaran_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.*, b.nama AS nama_barber
               FROM pengeluaran p LEFT JOIN barbers b ON b.id = p.barber_id
               WHERE p.id = ?""",
            (pengeluaran_id,),
        ).fetchone()
        if row is None:
            return None
        row = dict(row)
        row["terkunci"] = _reimburse_terkunci(row.get("reimburse_id"))
        return row


def get_pengeluaran_list(tahun: int = None, bulan: int = None, tanggal: str = None,
                          tanggal_mulai: str = None, tanggal_selesai: str = None,
                          kategori: str = None, cari: str = None, hanya_aktif: bool = None) -> list:
    """Urutan: tanggal terbaru dulu. `cari` mencari di keterangan & kategori.
    tanggal_mulai/tanggal_selesai (format 'YYYY-MM-DD', inklusif di kedua
    ujung) dipakai Laporan PDF untuk rentang tanggal bebas -- BEDA dari
    tahun/bulan (satu bulan/tahun penuh)."""
    q = """SELECT p.*, b.nama AS nama_barber
           FROM pengeluaran p LEFT JOIN barbers b ON b.id = p.barber_id WHERE 1=1"""
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
        # SQLite: LIKE tidak peka huruf besar/kecil secara default (ASCII).
        # PostgreSQL: LIKE PEKA huruf besar/kecil -- ILIKE dipakai supaya
        # perilaku pencarian identik di kedua dialek.
        operator = "ILIKE" if db_compat.IS_POSTGRES else "LIKE"
        q += f" AND (p.keterangan {operator} ? OR p.kategori {operator} ?)"
        like = f"%{cari}%"
        params.append(like)
        params.append(like)
    if hanya_aktif is not None:
        q += " AND p.aktif = ?"; params.append(1 if hanya_aktif else 0)
    q += " ORDER BY p.tanggal DESC, p.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    for r in rows:
        r["terkunci"] = _reimburse_terkunci(r.get("reimburse_id"))
    return rows


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
