"""
reimburse_db.py — Modul Karyawan: Reimburse (Fase 4)
=============================================================================
Fase 4 dari permintaan besar "Modul Karyawan/Keuangan/Pembayaran" (Fase 1:
slip_gaji_db.py, Fase 2: kasbon_db.py, Fase 3: komisi_penyesuaian_db.py).
Reimburse = klaim penggantian biaya yang DIAJUKAN barber sendiri (kategori,
nominal, bukti foto/dokumen), disetujui/ditolak Owner/Admin (`status`
'pending'/'disetujui'/'ditolak', `catatan_approval`). BEDA dari Kasbon/
Komisi: langsung bisa dibuat oleh akun Barber sendiri (self-service), bukan
hanya Owner/Admin.

Integrasi dengan Slip Gaji: field `slip_gaji.reimburse` (SELALU >= 0, lihat
slip_gaji_db.py) hanya nilai auto-fill di frontend saat Generate (dari
get_saldo_periode() di bawah -- total klaim BERSTATUS DISETUJUI barber+
periode itu), disalin ke slip. Sama seperti Komisi (bukan seperti Kasbon):
tidak ada hook dua-arah/FIFO, cukup dikunci begitu Slip Gaji periode itu
'sudah_dibayar' -- dicek LIVE ke tabel slip_gaji (_slip_terkunci()), bukan
flag tersimpan. BEDA dari Komisi: mengedit/menghapus/mengubah status klaim
YANG SUDAH DIBUAT untuk periode terkunci ditolak, TAPI membuat klaim BARU
tetap diizinkan (klaim reimburse yang telat diajukan untuk bulan yang sudah
digajikan adalah kasus wajar -- cukup tidak otomatis masuk ke slip yang
sudah terlanjur dibayar itu).

File bukti disimpan di database (kolom BLOB `bukti_data`, satu baris PER
KLAIM bukan per-barber -- nama file `reimburse-{id}.{ext}`, bukan
`barber-{barber_id}.{ext}`) -- disk lokal Render Free tier TIDAK
persisten, lihat README.

Tabel baru murni milik modul ini -- init_reimburse_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA dibuat
di postgres_schema.py.
"""

from datetime import datetime

from database import get_conn, get_barber

STATUS_VALID = {"pending", "disetujui", "ditolak"}
BUKTI_EXT_KE_CONTENT_TYPE = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "pdf": "application/pdf",
}

KATEGORI_DEFAULT = ["Transportasi", "Alat/Perlengkapan", "Makan", "Lainnya"]


def init_reimburse_db():
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(reimburse)").fetchall()]
        if kolom and "bukti_data" not in kolom:
            conn.execute("ALTER TABLE reimburse ADD COLUMN bukti_data BLOB")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reimburse (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id          INTEGER NOT NULL,
                tanggal            TEXT NOT NULL,
                kategori           TEXT NOT NULL,
                keterangan         TEXT,
                nominal            INTEGER NOT NULL,
                bukti_filename     TEXT,
                bukti_data         BLOB,
                status             TEXT NOT NULL DEFAULT 'pending',
                catatan_approval   TEXT,
                diajukan_oleh      TEXT,
                disetujui_oleh     TEXT,
                tanggal_approval   TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)


def _lengkapi(row: dict) -> dict:
    barber = get_barber(row["barber_id"])
    row["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    row["terkunci"] = _slip_terkunci(row["barber_id"], row["tanggal"])
    return row


def _slip_terkunci(barber_id: int, tanggal: str) -> bool:
    """True kalau ada Slip Gaji barber ini yang meliputi `tanggal` (tanggal
    klaim reimburse ini) dan sudah berstatus 'sudah_dibayar' -- query
    LANGSUNG ke tabel slip_gaji (bukan import slip_gaji_db), sama seperti
    pola komisi_penyesuaian_db.py.

    Barber: periode SELALU satu bulan kalender penuh (tanggal_mulai NULL di
    slip_gaji) -- cek tahun/bulan seperti sebelumnya. Kasir/OB/Kru: periode
    rentang tanggal bebas, bisa >1 slip per bulan kalender -- cek apakah
    `tanggal` jatuh DI DALAM rentang [tanggal_mulai, tanggal_selesai] slip
    manapun milik barber ini (Tahap 13: Slip Gaji periode rentang tanggal)."""
    barber = get_barber(barber_id)
    jabatan = (barber or {}).get("jabatan") or "barber"
    with get_conn() as conn:
        if jabatan == "barber":
            tahun, bulan = int(tanggal[:4]), int(tanggal[5:7])
            row = conn.execute(
                "SELECT status FROM slip_gaji WHERE barber_id = ? AND tahun = ? AND bulan = ? "
                "AND tanggal_mulai IS NULL",
                (barber_id, tahun, bulan),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT status FROM slip_gaji WHERE barber_id = ? AND tanggal_mulai IS NOT NULL "
                "AND tanggal_mulai <= ? AND tanggal_selesai >= ? AND status = 'sudah_dibayar' LIMIT 1",
                (barber_id, tanggal, tanggal),
            ).fetchone()
    return row is not None and row["status"] == "sudah_dibayar"


def get_reimburse(reimburse_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reimburse WHERE id = ?", (reimburse_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_reimburse_list(barber_id: int = None, status: str = None, tahun: int = None,
                        bulan: int = None, kategori: str = None,
                        tanggal_mulai: str = None, tanggal_selesai: str = None) -> list:
    """tanggal_mulai/tanggal_selesai (inklusif di kedua ujung) dipakai
    Laporan Reimburse (rentang tanggal bebas) -- BEDA dari tahun/bulan
    (satu bulan/tahun penuh, dipakai filter halaman Reimburse), pola sama
    persis kasbon_db.get_kasbon_list()."""
    q = "SELECT * FROM reimburse WHERE 1=1"
    params = []
    if barber_id is not None:
        q += " AND barber_id = ?"; params.append(barber_id)
    if status is not None:
        q += " AND status = ?"; params.append(status)
    if tahun is not None:
        q += " AND tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if kategori:
        q += " AND kategori = ?"; params.append(kategori)
    if tanggal_mulai is not None:
        q += " AND tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND tanggal <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY tanggal DESC, id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def get_reimburse_list_disetujui(tahun: int = None, bulan: int = None, barber_id: int = None,
                                  tanggal_mulai: str = None, tanggal_selesai: str = None) -> list:
    """Klaim BERSTATUS DISETUJUI, difilter lewat `tanggal_approval` (BUKAN
    `tanggal` klaim seperti get_reimburse_list()) -- dipakai
    gabung_ke_rekap_transaksi() di bawah (Tahap 14: baris reimburse
    otomatis muncul di Rekap Transaksi bertanggal SESUAI TANGGAL
    DISETUJUI, bukan tanggal klaim diajukan)."""
    q = "SELECT * FROM reimburse WHERE status = 'disetujui' AND tanggal_approval IS NOT NULL"
    params = []
    if barber_id is not None:
        q += " AND barber_id = ?"; params.append(barber_id)
    if tahun is not None:
        q += " AND tanggal_approval LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND tanggal_approval LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal_mulai is not None:
        q += " AND tanggal_approval >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND tanggal_approval <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY tanggal_approval DESC, id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def gabung_ke_rekap_transaksi(baris: list, tahun: int = None, bulan: int = None, barber_id: int = None,
                               tanggal_mulai: str = None, tanggal_selesai: str = None) -> list:
    """Menggabungkan `baris` (hasil database.get_rekap_transaksi_list(), satu
    baris = satu transaksi/hari libur) dengan baris klaim Reimburse
    BERSTATUS DISETUJUI pada periode yang sama -- dipanggil dari layer
    pemanggil (routers/rekap.py & laporan_pdf.py), BUKAN dari database.py
    sendiri (circular import: reimburse_db.py mengimpor database.py).

    Pola baris SAMA seperti baris tipe='libur' yang sudah ada di
    get_rekap_transaksi_list() -- tanggal = tanggal DISETUJUI (bukan
    tanggal klaim diajukan), Pendapatan = nominal reimburse (otomatis ikut
    Total Pendapatan di ringkasan PDF karena baris ini murni ditambahkan ke
    `baris` yang sama), Ket = "Reimburse (kategori)". Berlaku untuk SEMUA
    jabatan (barber/kasir/ob/kru), sama seperti tab Transaksi yang sudah
    generik untuk seluruh karyawan."""
    klaim = get_reimburse_list_disetujui(tahun=tahun, bulan=bulan, barber_id=barber_id,
                                          tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai)
    for k in klaim:
        baris.append({
            "tipe": "reimburse",
            "tanggal": k["tanggal_approval"],
            "barber_id": k["barber_id"],
            "nama_barber": k["nama_barber"],
            "daftar_service": "",
            "jumlah_service": 0,
            "tips": 0,
            "uang_harian": 0,
            "pendapatan": k["nominal"],
            "keterangan": f"Reimburse ({k['kategori']})",
        })
    baris.sort(key=lambda r: r["nama_barber"])
    baris.sort(key=lambda r: r["tanggal"], reverse=True)
    return baris


def get_kategori_list() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT kategori FROM reimburse WHERE kategori IS NOT NULL AND kategori != '' ORDER BY kategori"
        ).fetchall()
    dinamis = [r["kategori"] for r in rows]
    return list(dict.fromkeys(KATEGORI_DEFAULT + dinamis))


def buat_reimburse(barber_id: int, tanggal: str, kategori: str, nominal: int,
                    keterangan: str = "", diajukan_oleh: str = "") -> dict:
    barber = get_barber(barber_id)
    if barber is None:
        raise ValueError("Barber tidak ditemukan.")
    kategori = (kategori or "").strip()
    if not kategori:
        raise ValueError("Kategori tidak boleh kosong.")
    nominal = int(nominal or 0)
    if nominal <= 0:
        raise ValueError("Nominal harus lebih dari 0.")
    datetime.strptime(tanggal, "%Y-%m-%d")  # raise ValueError kalau format salah
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO reimburse (barber_id, tanggal, kategori, keterangan, nominal, status,
                                       diajukan_oleh, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (barber_id, tanggal, kategori, (keterangan or "").strip(), nominal, diajukan_oleh, now),
        )
        reimburse_id = cur.lastrowid
    return get_reimburse(reimburse_id)


def edit_reimburse(reimburse_id: int, tanggal: str = None, kategori: str = None,
                    nominal: int = None, keterangan: str = None) -> dict:
    existing = get_reimburse(reimburse_id)
    if existing is None:
        raise ValueError("Reimburse tidak ditemukan.")
    if existing["status"] != "pending":
        raise ValueError("Klaim yang sudah diproses (Disetujui/Ditolak) tidak bisa diedit lagi.")
    if existing["terkunci"]:
        raise ValueError(
            "Slip Gaji periode ini sudah berstatus Sudah Dibayar dan terkunci -- "
            "batalkan statusnya dulu kalau perlu mengubah klaim ini."
        )
    tanggal_baru = tanggal if tanggal is not None else existing["tanggal"]
    if tanggal is not None:
        datetime.strptime(tanggal_baru, "%Y-%m-%d")
    kategori_baru = kategori.strip() if kategori is not None else existing["kategori"]
    if kategori is not None and not kategori_baru:
        raise ValueError("Kategori tidak boleh kosong.")
    nominal_baru = int(nominal) if nominal is not None else existing["nominal"]
    if nominal is not None and nominal_baru <= 0:
        raise ValueError("Nominal harus lebih dari 0.")
    keterangan_baru = keterangan.strip() if keterangan is not None else existing["keterangan"]
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE reimburse SET tanggal = ?, kategori = ?, nominal = ?, keterangan = ?, updated_at = ?
               WHERE id = ?""",
            (tanggal_baru, kategori_baru, nominal_baru, keterangan_baru, now, reimburse_id),
        )
    return get_reimburse(reimburse_id)


def hapus_reimburse(reimburse_id: int):
    existing = get_reimburse(reimburse_id)
    if existing is None:
        raise ValueError("Reimburse tidak ditemukan.")
    if existing["status"] != "pending":
        raise ValueError("Klaim yang sudah diproses (Disetujui/Ditolak) tidak bisa dihapus lagi.")
    if existing["terkunci"]:
        raise ValueError(
            "Slip Gaji periode ini sudah berstatus Sudah Dibayar dan terkunci -- "
            "batalkan statusnya dulu kalau perlu menghapus klaim ini."
        )
    with get_conn() as conn:
        conn.execute("DELETE FROM reimburse WHERE id = ?", (reimburse_id,))


def set_status_reimburse(reimburse_id: int, status: str, catatan_approval: str = "",
                          disetujui_oleh: str = "") -> dict:
    if status not in {"disetujui", "ditolak"}:
        raise ValueError(f"Status tidak dikenal: {status}")
    existing = get_reimburse(reimburse_id)
    if existing is None:
        raise ValueError("Reimburse tidak ditemukan.")
    if existing["terkunci"]:
        raise ValueError(
            "Slip Gaji periode ini sudah berstatus Sudah Dibayar dan terkunci -- "
            "batalkan statusnya dulu kalau perlu mengubah status klaim ini."
        )
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE reimburse SET status = ?, catatan_approval = ?, disetujui_oleh = ?,
                   tanggal_approval = ?, updated_at = ? WHERE id = ?""",
            (status, (catatan_approval or "").strip(), disetujui_oleh, now[:10], now, reimburse_id),
        )
    return get_reimburse(reimburse_id)


def simpan_bukti_reimburse(reimburse_id: int, filename_asli: str, konten: bytes) -> str:
    existing = get_reimburse(reimburse_id)
    if existing is None:
        raise ValueError("Reimburse tidak ditemukan.")
    ext = filename_asli.rsplit(".", 1)[-1].lower() if "." in filename_asli else ""
    if ext not in BUKTI_EXT_KE_CONTENT_TYPE:
        raise ValueError("Format bukti harus JPG, PNG, WEBP, atau PDF.")
    if not konten:
        raise ValueError("File bukti kosong.")
    nama_file = f"reimburse-{reimburse_id}.{ext}"
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute("UPDATE reimburse SET bukti_filename = ?, bukti_data = ?, updated_at = ? WHERE id = ?",
                      (nama_file, konten, now, reimburse_id))
    return nama_file


def get_bukti_data(reimburse_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT bukti_filename, bukti_data FROM reimburse WHERE id = ?",
                            (reimburse_id,)).fetchone()
    if row is None or not row["bukti_filename"] or row["bukti_data"] is None:
        return None, None
    ext = row["bukti_filename"].rsplit(".", 1)[-1].lower()
    return bytes(row["bukti_data"]), BUKTI_EXT_KE_CONTENT_TYPE.get(ext, "application/octet-stream")


def buat_reimburse_sistem(barber_id: int, tanggal: str, kategori: str, nominal: int,
                           keterangan: str = "", dibuat_oleh: str = "") -> dict:
    """Sama seperti buat_reimburse(), TAPI untuk klaim yang lahir otomatis
    dari Pengeluaran (sumber_dana='karyawan') -- diinput Owner/Admin sendiri
    lewat pencatatan pengeluaran toko, jadi langsung disetujui (status
    'disetujui', bukan 'pending' menunggu approval terpisah)."""
    barber = get_barber(barber_id)
    if barber is None:
        raise ValueError("Karyawan tidak ditemukan.")
    kategori = (kategori or "").strip()
    if not kategori:
        raise ValueError("Kategori tidak boleh kosong.")
    nominal = int(nominal or 0)
    if nominal <= 0:
        raise ValueError("Nominal harus lebih dari 0.")
    datetime.strptime(tanggal, "%Y-%m-%d")  # raise ValueError kalau format salah
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO reimburse (barber_id, tanggal, kategori, keterangan, nominal, status,
                                       diajukan_oleh, disetujui_oleh, tanggal_approval, created_at)
               VALUES (?, ?, ?, ?, ?, 'disetujui', ?, ?, ?, ?)""",
            (barber_id, tanggal, kategori, (keterangan or "").strip(), nominal,
             dibuat_oleh, dibuat_oleh, now[:10], now),
        )
        reimburse_id = cur.lastrowid
    return get_reimburse(reimburse_id)


def edit_reimburse_sistem(reimburse_id: int, tanggal: str = None, kategori: str = None,
                           nominal: int = None, keterangan: str = None) -> dict:
    """Sama seperti edit_reimburse(), TAPI khusus klaim sistem (dari
    Pengeluaran) -- HANYA ditolak kalau terkunci (slip sudah dibayar), TIDAK
    ada pembatasan status='pending' karena klaim sistem memang selalu
    'disetujui' sejak dibuat."""
    existing = get_reimburse(reimburse_id)
    if existing is None:
        raise ValueError("Reimburse tidak ditemukan.")
    if existing["terkunci"]:
        raise ValueError(
            "Pengeluaran ini terkait Reimburse yang periodenya sudah dibayar lewat Slip Gaji "
            "dan tidak bisa diubah."
        )
    tanggal_baru = tanggal if tanggal is not None else existing["tanggal"]
    if tanggal is not None:
        datetime.strptime(tanggal_baru, "%Y-%m-%d")
    kategori_baru = kategori.strip() if kategori is not None else existing["kategori"]
    if kategori is not None and not kategori_baru:
        raise ValueError("Kategori tidak boleh kosong.")
    nominal_baru = int(nominal) if nominal is not None else existing["nominal"]
    if nominal is not None and nominal_baru <= 0:
        raise ValueError("Nominal harus lebih dari 0.")
    keterangan_baru = keterangan.strip() if keterangan is not None else existing["keterangan"]
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE reimburse SET tanggal = ?, kategori = ?, nominal = ?, keterangan = ?, updated_at = ?
               WHERE id = ?""",
            (tanggal_baru, kategori_baru, nominal_baru, keterangan_baru, now, reimburse_id),
        )
    return get_reimburse(reimburse_id)


def hapus_reimburse_sistem(reimburse_id: int):
    """Sama seperti hapus_reimburse(), TAPI khusus klaim sistem (dari
    Pengeluaran) -- HANYA ditolak kalau terkunci, TIDAK ada pembatasan
    status='pending'."""
    existing = get_reimburse(reimburse_id)
    if existing is None:
        raise ValueError("Reimburse tidak ditemukan.")
    if existing["terkunci"]:
        raise ValueError(
            "Pengeluaran ini terkait Reimburse yang periodenya sudah dibayar lewat Slip Gaji "
            "dan tidak bisa dihapus."
        )
    with get_conn() as conn:
        conn.execute("DELETE FROM reimburse WHERE id = ?", (reimburse_id,))


def get_saldo_periode(barber_id: int, tahun: int, bulan: int) -> int:
    """Total klaim BERSTATUS DISETUJUI milik barber ini pada periode
    (tahun+bulan, dari kolom `tanggal`) -- dipakai auto-fill 'Reimburse' di
    form Generate Slip Gaji (nilai ini HANYA saran awal, tetap bisa diedit
    manual). Berbeda dari Komisi (net bonus-potongan bisa negatif), nilai
    ini SELALU >= 0 karena reimburse murni penambahan."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(nominal), 0) AS total FROM reimburse
               WHERE barber_id = ? AND status = 'disetujui' AND tanggal LIKE ?""",
            (barber_id, f"{tahun:04d}-{bulan:02d}-%"),
        ).fetchone()
    return int(row["total"] or 0)


def get_saldo_rentang(barber_id: int, tanggal_mulai: str, tanggal_selesai: str) -> int:
    """Analog get_saldo_periode(), tapi untuk Kasir/OB/Kru (periode Slip
    Gaji rentang tanggal bebas, Tahap 13) -- total klaim BERSTATUS DISETUJUI
    milik barber ini yang tanggalnya jatuh DI DALAM [tanggal_mulai,
    tanggal_selesai] (inklusif di kedua ujung), dipakai auto-fill
    'Reimburse' di form Generate Slip Gaji untuk jabatan non-Barber."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(nominal), 0) AS total FROM reimburse
               WHERE barber_id = ? AND status = 'disetujui' AND tanggal >= ? AND tanggal <= ?""",
            (barber_id, tanggal_mulai, tanggal_selesai),
        ).fetchone()
    return int(row["total"] or 0)
