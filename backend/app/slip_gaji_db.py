"""
slip_gaji_db.py — Modul Karyawan: Slip Gaji Otomatis
=============================================================================
Fase 1 dari permintaan besar "Modul Karyawan/Keuangan/Pembayaran" (lihat
riwayat komit terkait) -- HANYA Slip Gaji yang dibangun di fase ini. Kasbon,
Reimburse, audit Komisi, Izin & Cuti, dsb SENGAJA belum ada.

Slip Gaji = Gaji Pokok (field baru per-barber, opsional, default 0) + Komisi
+ Tips + Uang Harian + Bonus Customer (SEMUA diambil apa adanya lewat
database.get_ringkasan_barber_bulan() yang SUDAH ADA -- file ini TIDAK
menghitung ulang satu angka pun sendiri, sama seperti prinsip laporan_pdf.py)
dikurangi Potongan Kasbon (SELALU 0/manual di fase ini -- modul Kasbon belum
ada, field-nya sudah disiapkan supaya PR Kasbon nanti tinggal mengisi tanpa
migrasi skema lagi) dan Potongan Lain (nominal + catatan, diisi manual saat
generate) = Total Diterima.

Satu slip per barber per bulan (UNIQUE(barber_id, tahun, bulan)). Slip yang
sudah berstatus 'sudah_dibayar' TERKUNCI -- tidak bisa di-generate ulang
(supaya angka slip yang sudah dibayar tidak diam-diam berubah kalau ada
koreksi transaksi belakangan) -- harus dibatalkan statusnya dulu lewat
tandai_status().

Tabel baru murni milik modul ini (pola yang sama seperti booking_db.py
punya init_booking_db() sendiri, TIDAK lewat database.py init_db()) --
dipanggil dari main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel
yang SAMA dibuat di postgres_schema.py (create_all() TIDAK memanggil fungsi
ini sama sekali di jalur itu).
"""

from datetime import datetime

import kasbon_db
from database import get_conn, get_barber, get_ringkasan_barber_bulan

STATUS_VALID = {"belum_dibayar", "sudah_dibayar"}


def init_slip_gaji_db():
    """CREATE TABLE IF NOT EXISTS slip_gaji + ALTER TABLE barbers ADD COLUMN
    gaji_pokok (idempotent, SQLite -- PRAGMA table_info dulu karena SQLite
    tidak punya ADD COLUMN IF NOT EXISTS)."""
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(barbers)").fetchall()]
        if "gaji_pokok" not in kolom:
            conn.execute("ALTER TABLE barbers ADD COLUMN gaji_pokok INTEGER NOT NULL DEFAULT 0")

        kolom_slip = [r["name"] for r in conn.execute("PRAGMA table_info(slip_gaji)").fetchall()]
        if kolom_slip and "penyesuaian_komisi" not in kolom_slip:
            # Modul Karyawan Fase 3 (Komisi): kolom baru untuk instalasi yang
            # tabel slip_gaji-nya sudah ada -- CREATE TABLE IF NOT EXISTS di
            # bawah jadi no-op untuknya, sama seperti pola gaji_pokok di atas.
            conn.execute("ALTER TABLE slip_gaji ADD COLUMN penyesuaian_komisi INTEGER NOT NULL DEFAULT 0")
        if kolom_slip and "reimburse" not in kolom_slip:
            # Modul Karyawan Fase 4 (Reimburse): kolom baru, pola sama.
            conn.execute("ALTER TABLE slip_gaji ADD COLUMN reimburse INTEGER NOT NULL DEFAULT 0")
        if kolom_slip and "jumlah_hari_masuk" not in kolom_slip:
            # Karyawan Non-Barber (Kasir/OB/Kru): Gaji dihitung dari Jumlah
            # Hari Masuk x barbers.gaji_per_hari (disimpan ke kolom
            # gaji_pokok slip ini apa adanya, TIDAK ke barbers.gaji_pokok --
            # itu tetap eksklusif Barber). NULL untuk slip Barber (tidak
            # relevan, tetap pakai Gaji Pokok bulanan flat).
            conn.execute("ALTER TABLE slip_gaji ADD COLUMN jumlah_hari_masuk INTEGER")
        if kolom_slip and "bonus_manual" not in kolom_slip:
            # Bonus manual (SEMUA jabatan) -- field terpisah dari Potongan
            # Lain (yang sifatnya pengurang), MENAMBAH Total Diterima.
            conn.execute("ALTER TABLE slip_gaji ADD COLUMN bonus_manual INTEGER NOT NULL DEFAULT 0")

        if kolom_slip and "tanggal_mulai" not in kolom_slip:
            # Tahap 13: Periode rentang tanggal bebas untuk Kasir/OB/Kru
            # (gaji mereka TIDAK dibayar bulanan seperti Barber, bisa >1
            # slip dalam bulan kalender yang sama) -- constraint lama
            # UNIQUE(barber_id, tahun, bulan) HANYA cocok untuk Barber (1
            # slip/bulan). SQLite tidak bisa DROP CONSTRAINT, jadi tabel
            # di-REBUILD (rename+create ulang+copy data), pola sama seperti
            # migrasi tabel `transaksi` di database.py. Constraint lama
            # diganti index UNIQUE PARSIAL (WHERE tanggal_mulai IS
            # NULL/NOT NULL) di bawah -- barber (tanggal_mulai NULL) tetap
            # 1 slip/bulan seperti sekarang, non-barber diidentifikasi
            # lewat rentang tanggalnya sendiri, bukan tahun/bulan lagi.
            conn.execute("ALTER TABLE slip_gaji RENAME TO slip_gaji_migrasi_lama")
            conn.execute("""
                CREATE TABLE slip_gaji (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    barber_id         INTEGER NOT NULL,
                    tahun             INTEGER NOT NULL,
                    bulan             INTEGER NOT NULL,
                    gaji_pokok        INTEGER NOT NULL DEFAULT 0,
                    komisi            INTEGER NOT NULL DEFAULT 0,
                    tips              INTEGER NOT NULL DEFAULT 0,
                    uang_harian       INTEGER NOT NULL DEFAULT 0,
                    bonus_customer    INTEGER NOT NULL DEFAULT 0,
                    potongan_kasbon   INTEGER NOT NULL DEFAULT 0,
                    potongan_lain     INTEGER NOT NULL DEFAULT 0,
                    penyesuaian_komisi INTEGER NOT NULL DEFAULT 0,
                    reimburse         INTEGER NOT NULL DEFAULT 0,
                    jumlah_hari_masuk INTEGER,
                    bonus_manual      INTEGER NOT NULL DEFAULT 0,
                    tanggal_mulai     TEXT,
                    tanggal_selesai   TEXT,
                    catatan_potongan  TEXT,
                    total_diterima    INTEGER NOT NULL DEFAULT 0,
                    status            TEXT NOT NULL DEFAULT 'belum_dibayar',
                    tanggal_dibayar   TEXT,
                    dibuat_oleh       TEXT,
                    created_at        TEXT NOT NULL,
                    updated_at        TEXT,
                    FOREIGN KEY (barber_id) REFERENCES barbers(id)
                )
            """)
            conn.execute("""
                INSERT INTO slip_gaji (id, barber_id, tahun, bulan, gaji_pokok, komisi, tips, uang_harian,
                                        bonus_customer, potongan_kasbon, potongan_lain, penyesuaian_komisi,
                                        reimburse, jumlah_hari_masuk, bonus_manual, catatan_potongan,
                                        total_diterima, status, tanggal_dibayar, dibuat_oleh, created_at, updated_at)
                SELECT id, barber_id, tahun, bulan, gaji_pokok, komisi, tips, uang_harian,
                       bonus_customer, potongan_kasbon, potongan_lain, penyesuaian_komisi,
                       reimburse, jumlah_hari_masuk, bonus_manual, catatan_potongan,
                       total_diterima, status, tanggal_dibayar, dibuat_oleh, created_at, updated_at
                FROM slip_gaji_migrasi_lama
            """)
            conn.execute("DROP TABLE slip_gaji_migrasi_lama")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS slip_gaji (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id         INTEGER NOT NULL,
                tahun             INTEGER NOT NULL,
                bulan             INTEGER NOT NULL,
                gaji_pokok        INTEGER NOT NULL DEFAULT 0,
                komisi            INTEGER NOT NULL DEFAULT 0,
                tips              INTEGER NOT NULL DEFAULT 0,
                uang_harian       INTEGER NOT NULL DEFAULT 0,
                bonus_customer    INTEGER NOT NULL DEFAULT 0,
                potongan_kasbon   INTEGER NOT NULL DEFAULT 0,
                potongan_lain     INTEGER NOT NULL DEFAULT 0,
                penyesuaian_komisi INTEGER NOT NULL DEFAULT 0,
                reimburse         INTEGER NOT NULL DEFAULT 0,
                jumlah_hari_masuk INTEGER,
                bonus_manual      INTEGER NOT NULL DEFAULT 0,
                tanggal_mulai     TEXT,
                tanggal_selesai   TEXT,
                catatan_potongan  TEXT,
                total_diterima    INTEGER NOT NULL DEFAULT 0,
                status            TEXT NOT NULL DEFAULT 'belum_dibayar',
                tanggal_dibayar   TEXT,
                dibuat_oleh       TEXT,
                created_at        TEXT NOT NULL,
                updated_at        TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)

        # Tahap 13: pengganti UNIQUE(barber_id, tahun, bulan) yang lama --
        # index parsial, aman idempotent dijalankan tiap startup (jalur
        # rebuild DI ATAS maupun jalur instalasi baru sama-sama berakhir di
        # sini dengan tabel yang sudah punya kolom tanggal_mulai).
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_slip_gaji_bulanan
            ON slip_gaji(barber_id, tahun, bulan) WHERE tanggal_mulai IS NULL
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_slip_gaji_rentang
            ON slip_gaji(barber_id, tanggal_mulai, tanggal_selesai) WHERE tanggal_mulai IS NOT NULL
        """)


def _lengkapi(row: dict) -> dict:
    barber = get_barber(row["barber_id"])
    row["nama_barber"] = barber["nama"] if barber else "(karyawan terhapus)"
    row["jabatan"] = barber["jabatan"] if barber else "barber"
    return row


def get_slip_gaji_by_periode(barber_id: int, tahun: int, bulan: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM slip_gaji WHERE barber_id = ? AND tahun = ? AND bulan = ?",
            (barber_id, tahun, bulan),
        ).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_slip_gaji_by_rentang(barber_id: int, tanggal_mulai: str, tanggal_selesai: str):
    """Analog get_slip_gaji_by_periode(), tapi untuk Kasir/OB/Kru (periode
    rentang tanggal bebas) -- exact-match rentang, dipakai supaya generate
    ulang dengan rentang PERSIS sama meng-UPDATE slip yang sama (bukan bikin
    duplikat), sama seperti perilaku generate ulang Barber per bulan."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM slip_gaji WHERE barber_id = ? AND tanggal_mulai = ? AND tanggal_selesai = ?",
            (barber_id, tanggal_mulai, tanggal_selesai),
        ).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_slip_gaji(slip_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM slip_gaji WHERE id = ?", (slip_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_slip_gaji_list(tahun: int = None, bulan: int = None, barber_id: int = None) -> list:
    q = "SELECT * FROM slip_gaji WHERE 1=1"
    params = []
    if tahun is not None:
        q += " AND tahun = ?"; params.append(tahun)
    if bulan is not None:
        q += " AND bulan = ?"; params.append(bulan)
    if barber_id is not None:
        q += " AND barber_id = ?"; params.append(barber_id)
    q += " ORDER BY tahun DESC, bulan DESC, id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def buat_slip_gaji(barber_id: int, tahun: int = None, bulan: int = None, gaji_pokok: int = None,
                    potongan_kasbon: int = 0, potongan_lain: int = 0, penyesuaian_komisi: int = 0,
                    reimburse: int = 0, catatan_potongan: str = "", dibuat_oleh: str = "",
                    jumlah_hari_masuk: int = None, bonus_manual: int = 0,
                    tanggal_mulai: str = None, tanggal_selesai: str = None) -> dict:
    """Generate (atau hitung ulang, kalau belum berstatus Sudah Dibayar) slip
    gaji satu karyawan. Komponen income (komisi/tips/uang harian/bonus)
    SELALU dihitung ULANG dari get_ringkasan_barber_bulan() apa adanya --
    hanya potongan yang manual/diisi Owner. Untuk karyawan non-barber
    (Kasir/OB/Kru) fungsi ini otomatis bernilai 0 untuk keempat komponen itu
    (tidak ada transaksi jasa potong rambut), murni Gaji + Reimburse +
    Bonus Manual - Potongan.

    Periode: Barber tetap satu slip per BULAN KALENDER (tahun+bulan wajib
    diisi, TIDAK dibayar bulanan bukan berarti barber -- itu tetap
    tahun/bulan seperti sekarang). Kasir/OB/Kru TIDAK dibayar bulanan --
    periode berupa RENTANG TANGGAL BEBAS (tanggal_mulai/tanggal_selesai
    wajib diisi), boleh lebih dari satu slip dalam bulan kalender yang
    sama (mis. dibayar 2x sebulan) -- tahun/bulan tetap DIDERIVE dari
    tanggal_mulai murni untuk filter/tampilan daftar yang sudah ada, BUKAN
    lagi kunci keunikan slip untuk jabatan ini (lihat idx_slip_gaji_rentang
    di init_slip_gaji_db()).

    gaji_pokok: HANYA berlaku jabatan='barber' -- kalau diisi (bukan None),
    NILAI INI DISIMPAN PERMANEN ke barbers.gaji_pokok (bukan cuma dipakai
    sekali untuk slip ini), form Generate Slip Gaji SEKALIAN jadi tempat
    mengatur/mengubahnya. Kalau None, pakai nilai yang sudah tersimpan di
    barbers.gaji_pokok apa adanya.

    jumlah_hari_masuk: WAJIB diisi untuk jabatan NON-barber (Kasir/OB/Kru)
    -- komponen Gaji = jumlah_hari_masuk x barbers.gaji_per_hari, disimpan
    ke kolom gaji_pokok SLIP INI apa adanya (BUKAN ke barbers.gaji_pokok,
    yang tetap eksklusif Barber)."""
    barber = get_barber(barber_id)
    if barber is None:
        raise ValueError("Karyawan tidak ditemukan.")

    jabatan = barber.get("jabatan") or "barber"
    if jabatan == "barber":
        if tahun is None or bulan is None:
            raise ValueError("Bulan dan Tahun wajib diisi untuk Barber.")
        if not (1 <= bulan <= 12):
            raise ValueError("Bulan tidak valid.")
        existing = get_slip_gaji_by_periode(barber_id, tahun, bulan)
    else:
        if not tanggal_mulai or not tanggal_selesai:
            raise ValueError("Tanggal Mulai dan Tanggal Selesai wajib diisi untuk karyawan non-Barber.")
        datetime.strptime(tanggal_mulai, "%Y-%m-%d")  # raise ValueError kalau format salah
        datetime.strptime(tanggal_selesai, "%Y-%m-%d")
        if tanggal_selesai < tanggal_mulai:
            raise ValueError("Tanggal Selesai tidak boleh sebelum Tanggal Mulai.")
        tahun = int(tanggal_mulai[:4])
        bulan = int(tanggal_mulai[5:7])
        existing = get_slip_gaji_by_rentang(barber_id, tanggal_mulai, tanggal_selesai)

    if existing and existing["status"] == "sudah_dibayar":
        raise ValueError(
            "Slip Gaji periode ini sudah berstatus Sudah Dibayar dan terkunci -- "
            "batalkan statusnya dulu kalau perlu generate ulang."
        )

    if jabatan == "barber":
        if gaji_pokok is not None:
            gaji_pokok = int(gaji_pokok)
            if gaji_pokok < 0:
                raise ValueError("Gaji Pokok tidak boleh negatif.")
            with get_conn() as conn:
                conn.execute("UPDATE barbers SET gaji_pokok = ? WHERE id = ?", (gaji_pokok, barber_id))
        else:
            gaji_pokok = int(barber.get("gaji_pokok") or 0)
        jumlah_hari_masuk = None
    else:
        if jumlah_hari_masuk is None or int(jumlah_hari_masuk) < 0:
            raise ValueError("Jumlah Hari Masuk harus diisi (0 atau lebih) untuk karyawan non-Barber.")
        jumlah_hari_masuk = int(jumlah_hari_masuk)
        gaji_pokok = jumlah_hari_masuk * int(barber.get("gaji_per_hari") or 0)

    ringkasan = get_ringkasan_barber_bulan(barber_id, tahun, bulan)
    komisi = ringkasan["komisi"]
    tips = ringkasan["tips"]
    uang_harian = ringkasan["uang_harian"]
    bonus_customer = ringkasan["bonus_customer"]
    potongan_kasbon = int(potongan_kasbon or 0)
    potongan_lain = int(potongan_lain or 0)
    penyesuaian_komisi = int(penyesuaian_komisi or 0)  # signed -- bonus (+) atau potongan (-), lihat komisi_penyesuaian_db.py
    reimburse = int(reimburse or 0)  # selalu >= 0, lihat reimburse_db.py
    bonus_manual = int(bonus_manual or 0)  # selalu >= 0, semua jabatan
    if potongan_kasbon < 0 or potongan_lain < 0:
        raise ValueError("Potongan tidak boleh negatif.")
    if reimburse < 0:
        raise ValueError("Reimburse tidak boleh negatif.")
    if bonus_manual < 0:
        raise ValueError("Bonus Manual tidak boleh negatif.")
    total_diterima = (gaji_pokok + komisi + tips + uang_harian + bonus_customer + penyesuaian_komisi + reimburse
                       + bonus_manual - potongan_kasbon - potongan_lain)

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        if existing:
            conn.execute(
                """UPDATE slip_gaji SET gaji_pokok = ?, komisi = ?, tips = ?, uang_harian = ?,
                       bonus_customer = ?, potongan_kasbon = ?, potongan_lain = ?, penyesuaian_komisi = ?,
                       reimburse = ?, jumlah_hari_masuk = ?, bonus_manual = ?, catatan_potongan = ?,
                       total_diterima = ?, dibuat_oleh = ?, updated_at = ?
                   WHERE id = ?""",
                (gaji_pokok, komisi, tips, uang_harian, bonus_customer, potongan_kasbon, potongan_lain,
                 penyesuaian_komisi, reimburse, jumlah_hari_masuk, bonus_manual, catatan_potongan,
                 total_diterima, dibuat_oleh, now, existing["id"]),
            )
            slip_id = existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO slip_gaji
                       (barber_id, tahun, bulan, gaji_pokok, komisi, tips, uang_harian, bonus_customer,
                        potongan_kasbon, potongan_lain, penyesuaian_komisi, reimburse, jumlah_hari_masuk,
                        bonus_manual, tanggal_mulai, tanggal_selesai, catatan_potongan, total_diterima,
                        status, dibuat_oleh, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'belum_dibayar', ?, ?)""",
                (barber_id, tahun, bulan, gaji_pokok, komisi, tips, uang_harian, bonus_customer,
                 potongan_kasbon, potongan_lain, penyesuaian_komisi, reimburse, jumlah_hari_masuk,
                 bonus_manual, tanggal_mulai, tanggal_selesai, catatan_potongan, total_diterima, dibuat_oleh, now),
            )
            slip_id = cur.lastrowid
    return get_slip_gaji(slip_id)


def tandai_status(slip_id: int, status: str) -> dict:
    """REVISI (Fase 2, Kasbon): status_lama dicatat SEBELUM update supaya
    integrasi kasbon di bawah hanya bereaksi pada TRANSISI status (bukan
    tiap kali endpoint dipanggil dengan status yang sama) -- ini yang
    membuat pemanggilan berulang idempotent (toggle status ke nilai yang
    sama tidak memicu apply/reverse potongan kasbon lagi).

    -> 'sudah_dibayar' (dari status lain): kalau slip.potongan_kasbon > 0,
       potongan itu BARU sekarang benar-benar diterapkan ke saldo kasbon
       barber (lihat kasbon_db.terapkan_potongan_slip_gaji(), distribusi
       FIFO) -- BUKAN saat slip digenerate/dihitung ulang.
    -> 'belum_dibayar' (dari 'sudah_dibayar'): potongan yang sempat
       diterapkan di atas DIBATALKAN (kasbon_db.batalkan_potongan_slip_gaji()),
       saldo kasbon terkait dikembalikan seperti semula."""
    if status not in STATUS_VALID:
        raise ValueError(f"Status tidak dikenal: {status}")
    existing = get_slip_gaji(slip_id)
    if existing is None:
        raise ValueError("Slip Gaji tidak ditemukan.")
    status_lama = existing["status"]
    now = datetime.now().isoformat(timespec="seconds")
    tanggal_dibayar = now[:10] if status == "sudah_dibayar" else None
    with get_conn() as conn:
        conn.execute(
            "UPDATE slip_gaji SET status = ?, tanggal_dibayar = ?, updated_at = ? WHERE id = ?",
            (status, tanggal_dibayar, now, slip_id),
        )

    if status == "sudah_dibayar" and status_lama != "sudah_dibayar" and existing["potongan_kasbon"] > 0:
        kasbon_db.terapkan_potongan_slip_gaji(existing["barber_id"], slip_id, existing["potongan_kasbon"])
    elif status == "belum_dibayar" and status_lama == "sudah_dibayar":
        kasbon_db.batalkan_potongan_slip_gaji(slip_id)

    return get_slip_gaji(slip_id)


def hapus_slip_gaji(slip_id: int):
    existing = get_slip_gaji(slip_id)
    if existing is None:
        raise ValueError("Slip Gaji tidak ditemukan.")
    if existing["status"] == "sudah_dibayar":
        raise ValueError("Slip Gaji yang sudah berstatus Sudah Dibayar tidak bisa dihapus.")
    with get_conn() as conn:
        conn.execute("DELETE FROM slip_gaji WHERE id = ?", (slip_id,))
