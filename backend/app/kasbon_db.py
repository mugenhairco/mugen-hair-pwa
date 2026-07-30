"""
kasbon_db.py — Modul Karyawan: Kasbon Karyawan (Fase 2)
=============================================================================
Fase 2 dari permintaan besar "Modul Karyawan/Keuangan/Pembayaran" (Fase 1:
lihat slip_gaji_db.py). Kasbon = uang muka/pinjaman yang diberikan ke
barber, dicatat per pengajuan (tabel `kasbon`, status belum_lunas/lunas,
`sisa` = sisa yang belum dibayar) dan riwayat pelunasannya (tabel
`kasbon_pembayaran`, satu baris per pembayaran, `sumber` manual/potong_gaji).

Integrasi dengan Slip Gaji: field `slip_gaji.potongan_kasbon` HANYA benar-
benar mengurangi saldo kasbon (dan membuat baris kasbon_pembayaran) saat
slip yang bersangkutan ditandai 'sudah_dibayar' -- lihat
slip_gaji_db.tandai_status() yang memanggil terapkan_potongan_slip_gaji()/
batalkan_potongan_slip_gaji() di bawah. Distribusi memakai urutan FIFO
(kasbon yang tanggalnya paling lama dipotong duluan) kalau barber punya
lebih dari satu kasbon belum lunas sekaligus, dan otomatis di-cap ke total
saldo outstanding riil (tidak pernah membuat `sisa` negatif).

Tabel baru murni milik modul ini (pola sama seperti slip_gaji_db.py) --
init_kasbon_db() dipanggil dari main.py on_startup() jalur SQLite. Jalur
PostgreSQL: tabel yang SAMA dibuat di postgres_schema.py.

Integrasi dengan Rekap Transaksi/Bulanan: BEDA dari Reimburse (murni
pendapatan, MENAMBAH Total), Kasbon adalah PINJAMAN yang harus
dikembalikan -- yang "masuk" ke Rekap adalah jumlah yang SUDAH DIBAYAR
(kasbon_pembayaran, sumber manual maupun potong_gaji), bukan jumlah yang
diajukan/dicairkan, dan nilainya MENGURANGI Total (lihat
gabung_ke_rekap_transaksi()/get_total_dibayar_periode() di bawah,
dipanggil dari routers/rekap.py -- pola sama seperti reimburse_db.py,
sengaja di sini bukan di database.py supaya tidak circular import)."""

from datetime import datetime

from database import get_conn, get_barber

STATUS_VALID = {"belum_lunas", "lunas"}
SUMBER_VALID = {"manual", "potong_gaji"}


def init_kasbon_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kasbon (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id    INTEGER NOT NULL,
                tanggal      TEXT NOT NULL,
                jumlah       INTEGER NOT NULL,
                keterangan   TEXT,
                status       TEXT NOT NULL DEFAULT 'belum_lunas',
                sisa         INTEGER NOT NULL,
                dibuat_oleh  TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kasbon_pembayaran (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                kasbon_id     INTEGER NOT NULL,
                tanggal       TEXT NOT NULL,
                jumlah        INTEGER NOT NULL,
                sumber        TEXT NOT NULL DEFAULT 'manual',
                slip_gaji_id  INTEGER,
                keterangan    TEXT,
                dibuat_oleh   TEXT,
                created_at    TEXT NOT NULL,
                FOREIGN KEY (kasbon_id) REFERENCES kasbon(id),
                FOREIGN KEY (slip_gaji_id) REFERENCES slip_gaji(id)
            )
        """)


def _lengkapi(row: dict) -> dict:
    barber = get_barber(row["barber_id"])
    row["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    return row


def get_kasbon(kasbon_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM kasbon WHERE id = ?", (kasbon_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_kasbon_list(barber_id: int = None, status: str = None, tahun: int = None, bulan: int = None,
                     tanggal_mulai: str = None, tanggal_selesai: str = None) -> list:
    """tanggal_mulai/tanggal_selesai (inklusif di kedua ujung) dipakai
    Laporan Kasbon (rentang tanggal bebas) -- BEDA dari tahun/bulan (satu
    bulan/tahun penuh, dipakai filter halaman Kasbon)."""
    q = "SELECT * FROM kasbon WHERE 1=1"
    params = []
    if barber_id is not None:
        q += " AND barber_id = ?"; params.append(barber_id)
    if status is not None:
        q += " AND status = ?"; params.append(status)
    if tahun is not None:
        q += " AND tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal_mulai is not None:
        q += " AND tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND tanggal <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY tanggal DESC, id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def _hitung_sudah_dibayar(conn, kasbon_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(jumlah), 0) AS total FROM kasbon_pembayaran WHERE kasbon_id = ?",
        (kasbon_id,),
    ).fetchone()
    return int(row["total"] or 0)


def buat_kasbon(barber_id: int, tanggal: str, jumlah: int, keterangan: str = "", dibuat_oleh: str = "") -> dict:
    barber = get_barber(barber_id)
    if barber is None:
        raise ValueError("Barber tidak ditemukan.")
    jumlah = int(jumlah or 0)
    if jumlah <= 0:
        raise ValueError("Jumlah kasbon harus lebih dari 0.")
    datetime.strptime(tanggal, "%Y-%m-%d")  # raise ValueError kalau format salah
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO kasbon (barber_id, tanggal, jumlah, keterangan, status, sisa, dibuat_oleh, created_at)
               VALUES (?, ?, ?, ?, 'belum_lunas', ?, ?, ?)""",
            (barber_id, tanggal, jumlah, (keterangan or "").strip(), jumlah, dibuat_oleh, now),
        )
        kasbon_id = cur.lastrowid
    return get_kasbon(kasbon_id)


def edit_kasbon(kasbon_id: int, tanggal: str = None, jumlah: int = None, keterangan: str = None) -> dict:
    existing = get_kasbon(kasbon_id)
    if existing is None:
        raise ValueError("Kasbon tidak ditemukan.")
    with get_conn() as conn:
        sudah_dibayar = _hitung_sudah_dibayar(conn, kasbon_id)
        if sudah_dibayar > 0 and (tanggal is not None or jumlah is not None):
            raise ValueError(
                "Kasbon ini sudah punya riwayat pembayaran -- Tanggal dan Jumlah tidak bisa diubah lagi "
                "(hanya Keterangan yang masih bisa diedit)."
            )
        tanggal_baru = tanggal if tanggal is not None else existing["tanggal"]
        jumlah_baru = int(jumlah) if jumlah is not None else existing["jumlah"]
        if jumlah is not None and jumlah_baru <= 0:
            raise ValueError("Jumlah kasbon harus lebih dari 0.")
        if tanggal is not None:
            datetime.strptime(tanggal_baru, "%Y-%m-%d")
        keterangan_baru = keterangan.strip() if keterangan is not None else existing["keterangan"]
        sisa_baru = jumlah_baru - sudah_dibayar
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """UPDATE kasbon SET tanggal = ?, jumlah = ?, keterangan = ?, sisa = ?, updated_at = ?
               WHERE id = ?""",
            (tanggal_baru, jumlah_baru, keterangan_baru, sisa_baru, now, kasbon_id),
        )
    return get_kasbon(kasbon_id)


def hapus_kasbon(kasbon_id: int):
    existing = get_kasbon(kasbon_id)
    if existing is None:
        raise ValueError("Kasbon tidak ditemukan.")
    with get_conn() as conn:
        ada_pembayaran = conn.execute(
            "SELECT 1 FROM kasbon_pembayaran WHERE kasbon_id = ? LIMIT 1", (kasbon_id,)
        ).fetchone()
        if ada_pembayaran:
            raise ValueError("Kasbon yang sudah punya riwayat pembayaran tidak bisa dihapus.")
        conn.execute("DELETE FROM kasbon WHERE id = ?", (kasbon_id,))


def get_riwayat_pembayaran(kasbon_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM kasbon_pembayaran WHERE kasbon_id = ? ORDER BY tanggal DESC, id DESC",
            (kasbon_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def bayar_kasbon(kasbon_id: int, tanggal: str, jumlah: int, keterangan: str = "", dibuat_oleh: str = "",
                  sumber: str = "manual", slip_gaji_id: int = None) -> dict:
    if sumber not in SUMBER_VALID:
        raise ValueError(f"Sumber pembayaran tidak dikenal: {sumber}")
    jumlah = int(jumlah or 0)
    if jumlah <= 0:
        raise ValueError("Jumlah pembayaran harus lebih dari 0.")
    datetime.strptime(tanggal, "%Y-%m-%d")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        kasbon = conn.execute("SELECT * FROM kasbon WHERE id = ?", (kasbon_id,)).fetchone()
        if kasbon is None:
            raise ValueError("Kasbon tidak ditemukan.")
        kasbon = dict(kasbon)
        if jumlah > kasbon["sisa"]:
            raise ValueError(f"Jumlah pembayaran ({jumlah}) melebihi sisa kasbon ({kasbon['sisa']}).")
        conn.execute(
            """INSERT INTO kasbon_pembayaran (kasbon_id, tanggal, jumlah, sumber, slip_gaji_id, keterangan,
                                               dibuat_oleh, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (kasbon_id, tanggal, jumlah, sumber, slip_gaji_id, (keterangan or "").strip(), dibuat_oleh, now),
        )
        sisa_baru = kasbon["sisa"] - jumlah
        status_baru = "lunas" if sisa_baru <= 0 else "belum_lunas"
        conn.execute(
            "UPDATE kasbon SET sisa = ?, status = ?, updated_at = ? WHERE id = ?",
            (sisa_baru, status_baru, now, kasbon_id),
        )
    return get_kasbon(kasbon_id)


def get_saldo_barber(barber_id: int) -> int:
    """Total sisa seluruh kasbon 'belum_lunas' milik satu barber -- dipakai
    (a) tampilan saldo di halaman Kasbon dan (b) auto-fill 'Potongan Kasbon'
    di form Generate Slip Gaji (nilai ini HANYA saran awal, tetap bisa
    diedit manual sebelum slip disimpan)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(sisa), 0) AS total FROM kasbon WHERE barber_id = ? AND status = 'belum_lunas'",
            (barber_id,),
        ).fetchone()
    return int(row["total"] or 0)


def terapkan_potongan_slip_gaji(barber_id: int, slip_gaji_id: int, jumlah: int) -> int:
    """Dipanggil HANYA dari slip_gaji_db.tandai_status() saat transisi ke
    'sudah_dibayar'. Distribusi FIFO: kasbon belum lunas milik barber ini,
    diurutkan tanggal paling lama dulu, masing-masing dipotong
    min(sisa_kasbon, sisa_jumlah) sampai `jumlah` habis atau kasbon habis --
    otomatis ter-cap ke total saldo outstanding riil (tidak mungkin membuat
    sisa negatif). Return total yang benar-benar diterapkan (bisa < jumlah
    kalau saldo outstanding lebih kecil dari potongan yang diminta)."""
    jumlah = int(jumlah or 0)
    if jumlah <= 0:
        return 0
    with get_conn() as conn:
        outstanding = [dict(r) for r in conn.execute(
            "SELECT id, sisa FROM kasbon WHERE barber_id = ? AND status = 'belum_lunas' ORDER BY tanggal ASC, id ASC",
            (barber_id,),
        ).fetchall()]

    sisa_potongan = jumlah
    total_diterapkan = 0
    tanggal_hari_ini = datetime.now().strftime("%Y-%m-%d")
    for row in outstanding:
        if sisa_potongan <= 0:
            break
        potong = min(row["sisa"], sisa_potongan)
        if potong <= 0:
            continue
        bayar_kasbon(row["id"], tanggal_hari_ini, potong,
                     keterangan="Potong otomatis dari Slip Gaji", dibuat_oleh="sistem",
                     sumber="potong_gaji", slip_gaji_id=slip_gaji_id)
        sisa_potongan -= potong
        total_diterapkan += potong
    return total_diterapkan


def batalkan_potongan_slip_gaji(slip_gaji_id: int):
    """Kebalikan dari terapkan_potongan_slip_gaji() -- dipanggil saat status
    Slip Gaji dibatalkan kembali ke 'belum_dibayar'. Kembalikan `sisa` tiap
    kasbon yang sempat dipotong lewat slip ini, set status balik ke
    'belum_lunas', lalu hapus baris kasbon_pembayaran terkait."""
    with get_conn() as conn:
        baris = [dict(r) for r in conn.execute(
            "SELECT * FROM kasbon_pembayaran WHERE slip_gaji_id = ? AND sumber = 'potong_gaji'",
            (slip_gaji_id,),
        ).fetchall()]
        now = datetime.now().isoformat(timespec="seconds")
        for p in baris:
            kasbon = conn.execute("SELECT * FROM kasbon WHERE id = ?", (p["kasbon_id"],)).fetchone()
            if kasbon is None:
                conn.execute("DELETE FROM kasbon_pembayaran WHERE id = ?", (p["id"],))
                continue
            sisa_baru = kasbon["sisa"] + p["jumlah"]
            conn.execute(
                "UPDATE kasbon SET sisa = ?, status = 'belum_lunas', updated_at = ? WHERE id = ?",
                (sisa_baru, now, p["kasbon_id"]),
            )
            conn.execute("DELETE FROM kasbon_pembayaran WHERE id = ?", (p["id"],))


def batalkan_pembayaran_kasbon(pembayaran_id: int):
    """Batalkan SATU baris pembayaran kasbon (kembalikan `sisa` kasbon
    terkait, balik `status` ke 'belum_lunas' kalau sempat 'lunas', lalu
    hapus baris kasbon_pembayaran itu) -- dipakai tombol Batalkan di Rekap
    Transaksi (Owner/Admin dengan izin_kasbon). HANYA untuk pembayaran
    sumber='manual' -- pembayaran hasil potong otomatis Slip Gaji harus
    dibatalkan lewat status Slip Gaji terkait (batalkan_potongan_slip_gaji()
    di atas), supaya tidak membuat slip yang sudah terlanjur dibayar jadi
    tidak sinkron dengan riwayat potongan kasbonnya."""
    with get_conn() as conn:
        p = conn.execute("SELECT * FROM kasbon_pembayaran WHERE id = ?", (pembayaran_id,)).fetchone()
        if p is None:
            raise ValueError("Riwayat pembayaran kasbon tidak ditemukan.")
        p = dict(p)
        if p["sumber"] != "manual":
            raise ValueError(
                "Pembayaran ini berasal dari potongan otomatis Slip Gaji -- batalkan lewat "
                "status Slip Gaji terkait, bukan dari sini."
            )
        kasbon = conn.execute("SELECT * FROM kasbon WHERE id = ?", (p["kasbon_id"],)).fetchone()
        if kasbon is None:
            raise ValueError("Kasbon terkait tidak ditemukan.")
        now = datetime.now().isoformat(timespec="seconds")
        sisa_baru = kasbon["sisa"] + p["jumlah"]
        conn.execute(
            "UPDATE kasbon SET sisa = ?, status = 'belum_lunas', updated_at = ? WHERE id = ?",
            (sisa_baru, now, p["kasbon_id"]),
        )
        conn.execute("DELETE FROM kasbon_pembayaran WHERE id = ?", (pembayaran_id,))


# ---------------------------------------------------------------------------
# Integrasi Rekap Transaksi/Bulanan -- lihat catatan di docstring modul ini
# kenapa yang dipakai adalah kasbon_pembayaran (jumlah DIBAYAR), bukan
# tabel kasbon (jumlah diajukan/dicairkan), dan kenapa nilainya MENGURANGI
# Total (bukan menambah seperti Reimburse).
# ---------------------------------------------------------------------------

def get_pembayaran_list_periode(tahun: int = None, bulan: int = None, barber_id: int = None,
                                 tanggal_mulai: str = None, tanggal_selesai: str = None) -> list:
    """Semua baris kasbon_pembayaran (SEMUA sumber -- manual maupun
    potong_gaji) pada periode ini (berdasarkan TANGGAL PEMBAYARAN, bukan
    tanggal kasbon diajukan), lintas kasbon manapun milik barber terkait.
    tanggal_mulai/tanggal_selesai dipakai periode PDF rentang tanggal bebas
    -- BEDA dari tahun/bulan yang dipakai tampilan layar (pola sama seperti
    reimburse_db.get_reimburse_list_disetujui())."""
    q = """SELECT p.*, k.barber_id AS barber_id FROM kasbon_pembayaran p
           JOIN kasbon k ON k.id = p.kasbon_id WHERE 1=1"""
    params = []
    if barber_id is not None:
        q += " AND k.barber_id = ?"; params.append(barber_id)
    if tahun is not None:
        q += " AND p.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND p.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal_mulai is not None:
        q += " AND p.tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND p.tanggal <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY p.tanggal DESC, p.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    barber_cache = {}
    for r in rows:
        bid = r["barber_id"]
        if bid not in barber_cache:
            barber_cache[bid] = get_barber(bid)
        barber = barber_cache[bid]
        r["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    return rows


def get_total_dibayar_periode(barber_id: int, tahun: int, bulan: int) -> int:
    """Total SEMUA pembayaran kasbon (manual + potong_gaji) barber ini pada
    bulan ini -- dipakai kolom 'Kasbon Dibayar' Rekap Bulanan, MENGURANGI
    Total Pendapatan (kasbon adalah pinjaman, bukan pendapatan)."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(p.jumlah), 0) AS total FROM kasbon_pembayaran p
               JOIN kasbon k ON k.id = p.kasbon_id
               WHERE k.barber_id = ? AND p.tanggal LIKE ?""",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%"),
        ).fetchone()
    return int(row["total"] or 0)


def gabung_ke_rekap_transaksi(baris: list, tahun: int = None, bulan: int = None, barber_id: int = None,
                               tanggal_mulai: str = None, tanggal_selesai: str = None) -> list:
    """Menggabungkan `baris` (hasil database.get_rekap_transaksi_list(),
    biasanya SUDAH digabung dengan baris Reimburse lewat reimburse_db) dengan
    baris pembayaran Kasbon pada periode yang sama -- dipanggil dari layer
    pemanggil (routers/rekap.py & laporan_pdf.py), BUKAN dari database.py
    sendiri (circular import: kasbon_db.py mengimpor database.py).

    BEDA dari baris Reimburse: 'pendapatan' di sini NEGATIF (mengurangi
    Total, bukan menambah) karena kasbon adalah pinjaman yang dikembalikan,
    bukan pendapatan -- tanggal = tanggal PEMBAYARAN (bukan tanggal kasbon
    diajukan)."""
    pembayaran = get_pembayaran_list_periode(tahun=tahun, bulan=bulan, barber_id=barber_id,
                                              tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
    for p in pembayaran:
        baris.append({
            "tipe": "kasbon",
            "id": p["id"],  # dipakai tombol Batalkan (Owner) di Rekap Transaksi
            "sumber": p["sumber"],  # 'manual' saja yang boleh dibatalkan dari sini
            "tanggal": p["tanggal"],
            "barber_id": p["barber_id"],
            "nama_barber": p["nama_barber"],
            "daftar_service": "",
            "jumlah_service": 0,
            "tips": 0,
            "uang_harian": 0,
            "pendapatan": -p["jumlah"],
            "keterangan": "Kasbon Dibayar" + (f" ({p['keterangan']})" if p.get("keterangan") else ""),
        })
    baris.sort(key=lambda r: r["nama_barber"])
    baris.sort(key=lambda r: r["tanggal"], reverse=True)
    return baris
