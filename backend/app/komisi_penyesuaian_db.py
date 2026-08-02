"""
komisi_penyesuaian_db.py — Modul Karyawan: Komisi (Audit & Penyesuaian, Fase 3)
=============================================================================
Fase 3 dari permintaan besar "Modul Karyawan/Keuangan/Pembayaran" (Fase 1:
slip_gaji_db.py, Fase 2: kasbon_db.py). Perhitungan komisi DASAR
(database.get_ringkasan_barber_bulan()/hitung_komisi_service()) TIDAK
disentuh sama sekali di sini -- itu batasan keras dari spesifikasi asli
("Jangan mengubah sistem komisi yang sudah ada"). Modul ini murni lapisan
ADDITIF terpisah: penyesuaian manual (bonus tambahan / potongan komisi) per
barber per periode (tahun+bulan), langsung berlaku begitu dibuat (TIDAK ada
alur approval), dicatat sebagai audit trail (siapa/kapan/kenapa/berapa lewat
`keterangan` yang WAJIB diisi).

Integrasi dengan Slip Gaji: field `slip_gaji.penyesuaian_komisi` (signed,
lihat slip_gaji_db.py) HANYA sebuah nilai yang di-auto-fill di frontend saat
Generate (dari get_saldo_periode() di bawah) dan disalin ke slip -- TIDAK
ada hook dua-arah seperti Kasbon (tidak perlu FIFO/reversal, karena setiap
baris penyesuaian sudah terikat ke SATU periode tertentu, bukan representasi
saldo utang berjalan). Satu-satunya penjagaan: begitu Slip Gaji periode itu
berstatus 'sudah_dibayar', baris penyesuaian_komisi periode itu TERKUNCI
(tidak bisa dibuat/diubah/dihapus) -- dicek LIVE ke tabel slip_gaji tiap
panggilan (_slip_terkunci()), bukan flag tersimpan, jadi otomatis terbuka
lagi begitu status slip dibatalkan.

Tabel baru murni milik modul ini (pola sama seperti kasbon_db.py) --
init_komisi_penyesuaian_db() dipanggil dari main.py on_startup() jalur
SQLite. Jalur PostgreSQL: tabel yang SAMA dibuat di postgres_schema.py.
"""

from datetime import datetime

from database import get_conn, get_barber

JENIS_VALID = {"bonus", "potongan"}


def init_komisi_penyesuaian_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS komisi_penyesuaian (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id    INTEGER NOT NULL,
                tahun        INTEGER NOT NULL,
                bulan        INTEGER NOT NULL,
                jenis        TEXT NOT NULL,
                jumlah       INTEGER NOT NULL,
                keterangan   TEXT NOT NULL,
                dibuat_oleh  TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)


def _lengkapi(row: dict) -> dict:
    barber = get_barber(row["barber_id"])
    row["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    row["terkunci"] = _slip_terkunci(row["barber_id"], row["tahun"], row["bulan"])
    # FONDASI Multi-Tenant Phase 1.1: komisi_penyesuaian TIDAK punya kolom
    # tenant_id sendiri (di-scope TRANSITIF lewat barbers.tenant_id,
    # barber_id NOT NULL) -- diselipkan di sini untuk fetch-then-authorize.
    row["tenant_id"] = barber["tenant_id"] if barber else None
    return row


def _slip_terkunci(barber_id: int, tahun: int, bulan: int) -> bool:
    """True kalau Slip Gaji barber+periode ini sudah berstatus
    'sudah_dibayar' -- query LANGSUNG ke tabel slip_gaji (bukan import
    slip_gaji_db) supaya tidak ada dependency antar modul sama sekali."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM slip_gaji WHERE barber_id = ? AND tahun = ? AND bulan = ?",
            (barber_id, tahun, bulan),
        ).fetchone()
    return row is not None and row["status"] == "sudah_dibayar"


def get_penyesuaian(penyesuaian_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM komisi_penyesuaian WHERE id = ?", (penyesuaian_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_penyesuaian_list(barber_id: int = None, tahun: int = None, bulan: int = None, jenis: str = None,
                          tenant_id: int = None) -> list:
    """FONDASI Multi-Tenant Phase 1.1: `tenant_id` opsional, JOIN tambahan
    ke barbers HANYA ditambahkan kalau diisi (endpoint ber-login WAJIB
    mengisi ini)."""
    q = "SELECT k.* FROM komisi_penyesuaian k"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = k.barber_id"
    q += " WHERE 1=1"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND k.barber_id = ?"; params.append(barber_id)
    if tahun is not None:
        q += " AND k.tahun = ?"; params.append(tahun)
    if bulan is not None:
        q += " AND k.bulan = ?"; params.append(bulan)
    if jenis is not None:
        q += " AND k.jenis = ?"; params.append(jenis)
    q += " ORDER BY k.tahun DESC, k.bulan DESC, k.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def buat_penyesuaian(barber_id: int, tahun: int, bulan: int, jenis: str, jumlah: int,
                      keterangan: str, dibuat_oleh: str = "", tenant_id: int = None) -> dict:
    barber = get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber["tenant_id"] != tenant_id):
        raise ValueError("Barber tidak ditemukan.")
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis penyesuaian tidak dikenal: {jenis}")
    if not (1 <= bulan <= 12):
        raise ValueError("Bulan tidak valid.")
    jumlah = int(jumlah or 0)
    if jumlah <= 0:
        raise ValueError("Jumlah harus lebih dari 0.")
    keterangan = (keterangan or "").strip()
    if not keterangan:
        raise ValueError("Keterangan wajib diisi (alasan penyesuaian, untuk audit trail).")
    if _slip_terkunci(barber_id, tahun, bulan):
        raise ValueError(
            "Slip Gaji periode ini sudah berstatus Sudah Dibayar dan terkunci -- "
            "batalkan statusnya dulu kalau perlu menambah penyesuaian komisi."
        )
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO komisi_penyesuaian (barber_id, tahun, bulan, jenis, jumlah, keterangan,
                                                dibuat_oleh, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (barber_id, tahun, bulan, jenis, jumlah, keterangan, dibuat_oleh, now),
        )
        penyesuaian_id = cur.lastrowid
    return get_penyesuaian(penyesuaian_id)


def edit_penyesuaian(penyesuaian_id: int, jenis: str = None, jumlah: int = None, keterangan: str = None) -> dict:
    existing = get_penyesuaian(penyesuaian_id)
    if existing is None:
        raise ValueError("Penyesuaian komisi tidak ditemukan.")
    if existing["terkunci"]:
        raise ValueError(
            "Slip Gaji periode ini sudah berstatus Sudah Dibayar dan terkunci -- "
            "batalkan statusnya dulu kalau perlu mengubah penyesuaian komisi."
        )
    jenis_baru = jenis if jenis is not None else existing["jenis"]
    if jenis_baru not in JENIS_VALID:
        raise ValueError(f"Jenis penyesuaian tidak dikenal: {jenis_baru}")
    jumlah_baru = int(jumlah) if jumlah is not None else existing["jumlah"]
    if jumlah is not None and jumlah_baru <= 0:
        raise ValueError("Jumlah harus lebih dari 0.")
    keterangan_baru = keterangan.strip() if keterangan is not None else existing["keterangan"]
    if keterangan is not None and not keterangan_baru:
        raise ValueError("Keterangan wajib diisi (alasan penyesuaian, untuk audit trail).")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE komisi_penyesuaian SET jenis = ?, jumlah = ?, keterangan = ?, updated_at = ?
               WHERE id = ?""",
            (jenis_baru, jumlah_baru, keterangan_baru, now, penyesuaian_id),
        )
    return get_penyesuaian(penyesuaian_id)


def hapus_penyesuaian(penyesuaian_id: int):
    existing = get_penyesuaian(penyesuaian_id)
    if existing is None:
        raise ValueError("Penyesuaian komisi tidak ditemukan.")
    if existing["terkunci"]:
        raise ValueError(
            "Slip Gaji periode ini sudah berstatus Sudah Dibayar dan terkunci -- "
            "batalkan statusnya dulu kalau perlu menghapus penyesuaian komisi."
        )
    with get_conn() as conn:
        conn.execute("DELETE FROM komisi_penyesuaian WHERE id = ?", (penyesuaian_id,))


def get_saldo_periode(barber_id: int, tahun: int, bulan: int) -> int:
    """Net signed total (bonus dikurangi potongan) untuk satu barber di satu
    periode -- dipakai (a) tampilan net di halaman Komisi dan (b) auto-fill
    'Penyesuaian Komisi' di form Generate Slip Gaji (nilai ini HANYA saran
    awal, tetap bisa diedit manual sebelum slip disimpan)."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT
                   COALESCE(SUM(CASE WHEN jenis = 'bonus' THEN jumlah ELSE 0 END), 0) AS total_bonus,
                   COALESCE(SUM(CASE WHEN jenis = 'potongan' THEN jumlah ELSE 0 END), 0) AS total_potongan
               FROM komisi_penyesuaian WHERE barber_id = ? AND tahun = ? AND bulan = ?""",
            (barber_id, tahun, bulan),
        ).fetchone()
    return int(row["total_bonus"] or 0) - int(row["total_potongan"] or 0)
