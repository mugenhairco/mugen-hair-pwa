"""
uang_kas_db.py — Modul Keuangan: Uang Kas (pengganti Transfer Kas/Bank)
=============================================================================
Pengganti yang lebih sederhana dari Transfer Kas/Bank (dihapus) -- SATU
akun "Kas" (bukan transfer antar 2 akun): Owner/Admin mencatat Saldo Kas
Awal sekali, lalu penyesuaian manual (tambah/kurang) dari waktu ke waktu
(mis. koreksi selisih hitung fisik vs sistem). Pola akses SAMA PERSIS
Pemasukan/Pengeluaran: data operasional TOKO, staff ('Admin') akses PENUH
tanpa sistem izin, barber TIDAK punya akses sama sekali (lihat
routers/uang_kas.py).

Dua tabel:
- kas_saldo_awal: Saldo Kas Awal, bisa diubah Owner/Admin kapan pun (bukan
  riwayat -- nilai dasar perhitungan saldo berjalan). FONDASI Multi-Tenant
  Phase 1.1: SATU baris PER TENANT (bukan lagi satu baris global id=1) --
  kolom `id` (INTEGER PRIMARY KEY, bukan SERIAL/AUTOINCREMENT) dipakai
  LANGSUNG sebagai `tenant_id` (konvensi "id = tenant_id"), supaya tidak
  perlu mengubah tipe kolom itu dari skema lama. Baris dibuat LAZY (INSERT
  ... ON CONFLICT DO NOTHING, dialek-netral SQLite/PostgreSQL) begitu
  get_saldo_awal()/set_saldo_awal() pertama kali dipanggil untuk tenant
  itu -- tenant BARU (dibuat setelah migrasi Phase 1.1) tidak pernah
  di-seed lewat migrasi, jadi baris pertamanya selalu lahir dari sini.
- kas_penyesuaian: ledger tambah/kurang, pola CASE-WHEN identik
  komisi_penyesuaian_db.get_saldo_periode() untuk hitung saldo berjalan.
  Punya kolom tenant_id LANGSUNG juga (TIDAK PUNYA barber_id sama sekali,
  jadi tidak bisa di-scope transitif lewat JOIN ke barbers).

Tabel baru murni milik modul ini -- init_uang_kas_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

from datetime import datetime

from database import get_conn

JENIS_VALID = {"tambah", "kurang"}


def init_uang_kas_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kas_saldo_awal (
                id           INTEGER PRIMARY KEY,
                saldo        INTEGER NOT NULL DEFAULT 0,
                diubah_oleh  TEXT,
                updated_at   TEXT,
                tenant_id    INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kas_penyesuaian (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal      TEXT NOT NULL,
                jenis        TEXT NOT NULL,
                jumlah       INTEGER NOT NULL,
                keterangan   TEXT,
                dibuat_oleh  TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT,
                tenant_id    INTEGER
            )
        """)


def _validasi_tanggal(tanggal: str):
    datetime.strptime(tanggal, "%Y-%m-%d")  # raise ValueError kalau format salah


def _pastikan_baris_saldo_awal(conn, tenant_id: int):
    """Lazy-create baris kas_saldo_awal milik tenant ini (id = tenant_id)
    kalau belum ada -- lihat penjelasan skema di docstring modul."""
    conn.execute(
        "INSERT INTO kas_saldo_awal (id, saldo, tenant_id) VALUES (?, 0, ?) ON CONFLICT DO NOTHING",
        (tenant_id, tenant_id),
    )


def get_saldo_awal(tenant_id: int) -> dict:
    with get_conn() as conn:
        _pastikan_baris_saldo_awal(conn, tenant_id)
        row = conn.execute("SELECT * FROM kas_saldo_awal WHERE id = ?", (tenant_id,)).fetchone()
        return dict(row) if row else {"id": tenant_id, "saldo": 0, "diubah_oleh": None, "updated_at": None,
                                       "tenant_id": tenant_id}


def set_saldo_awal(saldo: int, diubah_oleh: str, tenant_id: int):
    if saldo < 0:
        raise ValueError("Saldo Kas Awal tidak boleh negatif.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        _pastikan_baris_saldo_awal(conn, tenant_id)
        conn.execute(
            "UPDATE kas_saldo_awal SET saldo = ?, diubah_oleh = ?, updated_at = ? WHERE id = ?",
            (int(saldo), diubah_oleh, now, tenant_id),
        )
    return get_saldo_awal(tenant_id)


def get_saldo_kas(tenant_id: int) -> int:
    """Saldo Kas Awal + total penyesuaian (tambah - kurang) sampai saat
    ini -- pola CASE-WHEN identik komisi_penyesuaian_db.get_saldo_periode()."""
    saldo_awal = get_saldo_awal(tenant_id)["saldo"]
    with get_conn() as conn:
        row = conn.execute(
            """SELECT
                   COALESCE(SUM(CASE WHEN jenis = 'tambah' THEN jumlah ELSE 0 END), 0) AS total_tambah,
                   COALESCE(SUM(CASE WHEN jenis = 'kurang' THEN jumlah ELSE 0 END), 0) AS total_kurang
               FROM kas_penyesuaian WHERE tenant_id = ?""",
            (tenant_id,),
        ).fetchone()
    return int(saldo_awal) + int(row["total_tambah"] or 0) - int(row["total_kurang"] or 0)


def _validasi_input(tanggal: str, jenis: str, jumlah: int, keterangan: str):
    _validasi_tanggal(tanggal)
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis penyesuaian tidak dikenal: {jenis}")
    if jumlah is None or jumlah <= 0:
        raise ValueError("Jumlah harus diisi dan lebih dari 0.")
    keterangan = (keterangan or "").strip()
    return keterangan


def tambah_penyesuaian(tanggal: str, jenis: str, jumlah: int, keterangan: str = "",
                        dibuat_oleh: str = None, tenant_id: int = None) -> int:
    keterangan = _validasi_input(tanggal, jenis, jumlah, keterangan)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO kas_penyesuaian (tanggal, jenis, jumlah, keterangan, dibuat_oleh, created_at,
                                             tenant_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tanggal, jenis, int(jumlah), keterangan, dibuat_oleh, now, tenant_id),
        )
        return cur.lastrowid


def edit_penyesuaian(penyesuaian_id: int, tanggal: str = None, jenis: str = None,
                      jumlah: int = None, keterangan: str = None):
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM kas_penyesuaian WHERE id = ?", (penyesuaian_id,)).fetchone()
        if existing is None:
            raise ValueError("Penyesuaian kas tidak ditemukan.")
        tanggal_final = tanggal if tanggal is not None else existing["tanggal"]
        jenis_final = jenis if jenis is not None else existing["jenis"]
        jumlah_final = jumlah if jumlah is not None else existing["jumlah"]
        _validasi_input(tanggal_final, jenis_final, jumlah_final, keterangan or "")
        now = datetime.now().isoformat(timespec="seconds")
        fields, values = ["updated_at = ?"], [now]
        if tanggal is not None:
            fields.append("tanggal = ?"); values.append(tanggal)
        if jenis is not None:
            fields.append("jenis = ?"); values.append(jenis)
        if jumlah is not None:
            fields.append("jumlah = ?"); values.append(int(jumlah))
        if keterangan is not None:
            fields.append("keterangan = ?"); values.append(keterangan.strip())
        values.append(penyesuaian_id)
        conn.execute(f"UPDATE kas_penyesuaian SET {', '.join(fields)} WHERE id = ?", values)


def hapus_penyesuaian(penyesuaian_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM kas_penyesuaian WHERE id = ?", (penyesuaian_id,))


def get_penyesuaian(penyesuaian_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM kas_penyesuaian WHERE id = ?", (penyesuaian_id,)).fetchone()
        return dict(row) if row else None


def get_penyesuaian_list(tahun: int = None, bulan: int = None, tenant_id: int = None) -> list:
    q = "SELECT * FROM kas_penyesuaian WHERE 1=1"
    params = []
    if tenant_id is not None:
        q += " AND tenant_id = ?"; params.append(tenant_id)
    if tahun is not None:
        q += " AND tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    q += " ORDER BY tanggal DESC, id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]
