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

import r2_storage
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
    # FONDASI Multi-Tenant Phase 1.1: reimburse TIDAK punya kolom tenant_id
    # sendiri (di-scope TRANSITIF lewat barbers.tenant_id, barber_id NOT
    # NULL) -- diselipkan di sini supaya router bisa fetch-then-authorize.
    row["tenant_id"] = barber["tenant_id"] if barber else None
    # `row` datang dari SELECT * -- kolom biner bukti_data (BLOB, sejak Fase
    # 4) TIDAK bisa di-serialize jadi JSON (bug laten yang ditemukan saat
    # audit migrasi R2 ini: endpoint upload/lihat bukti akan crash 500 begitu
    # bukti sungguhan tersimpan -- murni bug pre-existing, tidak terkait R2).
    # Dibuang di sini -- frontend (reimburse.js) hanya butuh `bukti_filename`
    # (untuk cek ada/tidaknya) dan membangun URL unduh sendiri dari `id`,
    # tidak pernah membaca bukti_data/bukti_r2_key dari respons ini.
    row.pop("bukti_data", None)
    row.pop("bukti_r2_key", None)
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
                        tanggal_mulai: str = None, tanggal_selesai: str = None,
                        tenant_id: int = None) -> list:
    """tanggal_mulai/tanggal_selesai (inklusif di kedua ujung) dipakai
    Laporan Reimburse (rentang tanggal bebas) -- BEDA dari tahun/bulan
    (satu bulan/tahun penuh, dipakai filter halaman Reimburse), pola sama
    persis kasbon_db.get_kasbon_list().

    FONDASI Multi-Tenant Phase 1.1: `tenant_id` opsional, JOIN tambahan ke
    barbers HANYA ditambahkan kalau diisi (endpoint ber-login WAJIB
    mengisi ini)."""
    q = "SELECT r.* FROM reimburse r"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = r.barber_id"
    q += " WHERE 1=1"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND r.barber_id = ?"; params.append(barber_id)
    if status is not None:
        q += " AND r.status = ?"; params.append(status)
    if tahun is not None:
        q += " AND r.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND r.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if kategori:
        q += " AND r.kategori = ?"; params.append(kategori)
    if tanggal_mulai is not None:
        q += " AND r.tanggal >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND r.tanggal <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY r.tanggal DESC, r.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def get_reimburse_list_disetujui(tahun: int = None, bulan: int = None, barber_id: int = None,
                                  tanggal_mulai: str = None, tanggal_selesai: str = None,
                                  tenant_id: int = None) -> list:
    """Klaim BERSTATUS DISETUJUI, difilter lewat `tanggal_approval` (BUKAN
    `tanggal` klaim seperti get_reimburse_list()) -- dipakai
    gabung_ke_rekap_transaksi() di bawah (Tahap 14: baris reimburse
    otomatis muncul di Rekap Transaksi bertanggal SESUAI TANGGAL
    DISETUJUI, bukan tanggal klaim diajukan).

    FONDASI Multi-Tenant Phase 1.1: `tenant_id` opsional, sama seperti
    get_reimburse_list()."""
    q = "SELECT r.* FROM reimburse r"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = r.barber_id"
    q += " WHERE r.status = 'disetujui' AND r.tanggal_approval IS NOT NULL"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND r.barber_id = ?"; params.append(barber_id)
    if tahun is not None:
        q += " AND r.tanggal_approval LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND r.tanggal_approval LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal_mulai is not None:
        q += " AND r.tanggal_approval >= ?"; params.append(tanggal_mulai)
    if tanggal_selesai is not None:
        q += " AND r.tanggal_approval <= ?"; params.append(tanggal_selesai)
    q += " ORDER BY r.tanggal_approval DESC, r.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def gabung_ke_rekap_transaksi(baris: list, tahun: int = None, bulan: int = None, barber_id: int = None,
                               tanggal_mulai: str = None, tanggal_selesai: str = None,
                               tenant_id: int = None) -> list:
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
                                          tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
                                          tenant_id=tenant_id)
    for k in klaim:
        baris.append({
            "tipe": "reimburse",
            "id": k["id"],  # dipakai tombol Hapus (Owner) di Rekap Transaksi
            "tanggal": k["tanggal_approval"],
            "barber_id": k["barber_id"],
            "nama_barber": k["nama_barber"],
            "daftar_service": "",
            "jumlah_service": 0,
            "tips": 0,
            "uang_harian": 0,
            "pendapatan": k["nominal"],
            "keterangan": f"Reimburse ({k['kategori']})",
            "kategori": k["kategori"],  # field mentah -- dipakai rekap_ringkasan.py supaya tidak perlu parsing teks "keterangan"
        })
    baris.sort(key=lambda r: r["nama_barber"])
    baris.sort(key=lambda r: r["tanggal"], reverse=True)
    return baris


def get_kategori_list(tenant_id: int = None) -> list:
    q = "SELECT DISTINCT r.kategori FROM reimburse r"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = r.barber_id"
    q += " WHERE r.kategori IS NOT NULL AND r.kategori != ''"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    q += " ORDER BY r.kategori"
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    dinamis = [r["kategori"] for r in rows]
    return list(dict.fromkeys(KATEGORI_DEFAULT + dinamis))


def buat_reimburse(barber_id: int, tanggal: str, kategori: str, nominal: int,
                    keterangan: str = "", diajukan_oleh: str = "", tenant_id: int = None) -> dict:
    barber = get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber["tenant_id"] != tenant_id):
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
    r2_key = _ambil_bukti_r2_key(reimburse_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM reimburse WHERE id = ?", (reimburse_id,))
    if r2_key:
        r2_storage.delete(r2_key)


def hapus_reimburse_disetujui(reimburse_id: int):
    """Hapus klaim reimburse yang SUDAH berstatus 'disetujui', sepenuhnya --
    dipakai KHUSUS oleh tombol Hapus di Rekap Transaksi (Owner/Admin dengan
    izin_reimburse), BEDA dari hapus_reimburse() di atas yang hanya
    mengizinkan status 'pending' (dipakai halaman Reimburse biasa). Tetap
    ditolak kalau terkunci (Slip Gaji periode ini sudah 'sudah_dibayar')
    supaya tidak membuat slip yang sudah terlanjur dibayar jadi tidak sinkron
    dengan klaim yang sempat masuk ke situ."""
    existing = get_reimburse(reimburse_id)
    if existing is None:
        raise ValueError("Reimburse tidak ditemukan.")
    if existing["status"] != "disetujui":
        raise ValueError("Hanya klaim berstatus Disetujui yang bisa dihapus lewat Rekap Transaksi.")
    if existing["terkunci"]:
        raise ValueError(
            "Slip Gaji periode ini sudah berstatus Sudah Dibayar dan terkunci -- "
            "batalkan statusnya dulu kalau perlu menghapus klaim ini."
        )
    r2_key = _ambil_bukti_r2_key(reimburse_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM reimburse WHERE id = ?", (reimburse_id,))
    if r2_key:
        r2_storage.delete(r2_key)


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
    nama_file, content_type = r2_storage.validasi_dan_beri_nama(
        filename_asli, konten, BUKTI_EXT_KE_CONTENT_TYPE, "bukti",
        maks_ukuran_bytes=r2_storage.MAKS_UKURAN_DOKUMEN_BYTES)
    now = datetime.now().isoformat(timespec="seconds")
    r2_key_lama = _ambil_bukti_r2_key(reimburse_id)

    if r2_storage.IS_ENABLED:
        r2_key_baru = r2_storage.upload("payments", nama_file, konten, content_type)
        data_kolom = None
    else:
        r2_key_baru = None
        data_kolom = konten

    with get_conn() as conn:
        conn.execute("UPDATE reimburse SET bukti_filename = ?, bukti_data = ?, bukti_r2_key = ?, updated_at = ? WHERE id = ?",
                      (nama_file, data_kolom, r2_key_baru, now, reimburse_id))

    if r2_key_lama and r2_key_lama != r2_key_baru:
        r2_storage.delete(r2_key_lama)
    return nama_file


def _ambil_bukti_r2_key(reimburse_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT bukti_r2_key FROM reimburse WHERE id = ?", (reimburse_id,)).fetchone()
    return row["bukti_r2_key"] if row else None


def get_bukti_data(reimburse_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT bukti_filename, bukti_data, bukti_r2_key FROM reimburse WHERE id = ?",
                            (reimburse_id,)).fetchone()
    if row is None or not row["bukti_filename"]:
        return None, None
    ext = row["bukti_filename"].rsplit(".", 1)[-1].lower()
    content_type = BUKTI_EXT_KE_CONTENT_TYPE.get(ext, "application/octet-stream")
    if row["bukti_r2_key"]:
        data, r2_content_type = r2_storage.get_bytes(row["bukti_r2_key"])
        if data is not None:
            return data, r2_content_type or content_type
    if row["bukti_data"] is not None:
        return bytes(row["bukti_data"]), content_type
    return None, None


def buat_reimburse_sistem(barber_id: int, tanggal: str, kategori: str, nominal: int,
                           keterangan: str = "", dibuat_oleh: str = "", tenant_id: int = None) -> dict:
    """Sama seperti buat_reimburse(), TAPI untuk klaim yang lahir otomatis
    dari Pengeluaran (sumber_dana='karyawan') -- diinput Owner/Admin sendiri
    lewat pencatatan pengeluaran toko, jadi langsung disetujui (status
    'disetujui', bukan 'pending' menunggu approval terpisah)."""
    barber = get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber["tenant_id"] != tenant_id):
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
    r2_key = _ambil_bukti_r2_key(reimburse_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM reimburse WHERE id = ?", (reimburse_id,))
    if r2_key:
        r2_storage.delete(r2_key)


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
