"""
manual_customer_db.py — Input Data: Manual Customer (Waiting List / Booking)
=============================================================================
FITUR BARU (diminta Owner): metode input KEDUA untuk Input Data, alternatif
dari "Input Barber" (sistem lama, bulk qty per service TANPA nama customer,
lihat routers/input_data.py -- TIDAK diubah sama sekali). Manual Customer
mencatat customer SATU PER SATU (1 customer = 1 baris), dengan dua jenis:

- "waiting_list": customer masih menunggu, barber/service BOLEH belum
  diketahui saat baris dibuat (nullable) -- jam OTOMATIS dari waktu server
  (WIB) saat baris dibuat, TIDAK PERNAH bisa diedit setelahnya.
- "booking": customer sudah punya jadwal, barber+service WAJIB sudah
  diketahui -- jam WAJIB diisi manual oleh kasir (jam booking, BUKAN jam
  kasir menginput), juga TIDAK PERNAH bisa diedit setelahnya.

PENTING -- INTEGRASI KE REKAP: modul ini TIDAK PERNAH membuat formula
pendapatan/komisi/Uang Harian baru, dan TIDAK PERNAH menyentuh rekap.py/
get_rekap_transaksi_list() sama sekali. Begitu tenant menekan "Tutup &
Simpan Hari Ini" (tutup_hari() di bawah), setiap baris yang SUDAH punya
barber_id+minimal satu service diubah jadi baris `transaksi`/
`transaksi_detail` SUNGGUHAN lewat database.tambah_transaksi() -- fungsi
yang SAMA PERSIS dipakai Input Barber. Setelah itu Rekap melihatnya sebagai
transaksi biasa, TIDAK TAHU dan TIDAK PERLU TAHU baris itu berasal dari
Manual Customer -- nama customer/jam HANYA pernah ada di tabel-tabel modul
ini, TIDAK PERNAH masuk ke `transaksi`/Rekap sama sekali (sesuai permintaan
eksplisit "jangan tambahkan Nama Customer/Jam ke Rekap").

ATURAN "SATU TANGGAL SATU MODE" (mencegah double counting): tabel
`input_data_hari` menyimpan MODE ('barber' atau 'manual_customer') yang
sedang dipakai satu tenant untuk satu tanggal -- baris ini dibuat OTOMATIS
saat transaksi PERTAMA (jenis apa pun) dibuat untuk tanggal itu, dan
MENOLAK percobaan memakai mode lain untuk tanggal yang sama (lihat
pastikan_mode() di bawah, dipanggil modul ini SENDIRI untuk Manual Customer
DAN dari routers/input_data.py::tambah_transaksi() -- SATU-SATUNYA
perubahan yang disentuh di sistem Input Barber lama, murni pemanggilan
guard ini, tidak mengubah perilaku apa pun kalau tidak ada konflik mode).
Owner bisa mengganti mode kapan pun via reset_hari() (tombol "Reset Semua
Transaksi Hari Ini") -- menghapus SELURUH transaksi tanggal itu (kedua
mode) supaya mode bebas dipilih ulang.

CLOSING BUKAN PENGUNCIAN DATA (klarifikasi eksplisit Owner): status
'closed' pada input_data_hari murni PENANDA WORKFLOW ("hari ini sudah
ditutup") -- baris `transaksi` hasil konversi TETAP bisa diedit/dihapus
lewat endpoint Input Barber/Rekap yang sudah ada, SAMA PERSIS seperti
transaksi Input Barber biasa. Ini SENGAJA supaya tidak perlu membangun
mekanisme "buka kunci" terpisah.

Tabel baru murni milik modul ini -- init_manual_customer_db() dipanggil
dari main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from database import get_conn, get_barber, get_service, tambah_transaksi, hapus_transaksi

WIB = ZoneInfo("Asia/Jakarta")

JENIS_VALID = {"waiting_list", "booking"}
MODE_VALID = {"barber", "manual_customer"}
STATUS_HARI_VALID = {"open", "closed"}


def _sekarang_wib() -> datetime:
    return datetime.now(WIB)


def _hari_ini_wib() -> str:
    return _sekarang_wib().strftime("%Y-%m-%d")


def init_manual_customer_db():
    with get_conn() as conn:
        # SATU baris per (tenant_id, tanggal) -- "mode" mengunci tanggal itu
        # ke SATU metode input (lihat docstring modul), "status" hanya
        # relevan untuk mode='manual_customer' ('open' selamanya kalau
        # mode='barber', Closing tidak berlaku untuk Input Barber).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS input_data_hari (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id    INTEGER NOT NULL,
                tanggal      TEXT NOT NULL,
                mode         TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'open',
                ditutup_oleh TEXT,
                ditutup_at   TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT,
                UNIQUE(tenant_id, tanggal)
            )
        """)
        # barber_id/service dibiarkan NULLABLE (Waiting List boleh belum
        # tahu barber/service) -- layanan yang dipilih customer disimpan di
        # tabel anak manual_customer_transaksi_service (many-to-many, SATU
        # customer bisa ambil lebih dari satu service tanpa field "Jumlah
        # Service" -- setiap baris service = qty 1, lihat rule #5).
        # `jam` (HH:MM) dan `jenis` immutable setelah dibuat (lihat
        # docstring) -- TIDAK ADA fungsi update_jam di modul ini sama
        # sekali, sengaja tidak disediakan.
        #
        # HOTFIX DEPLOY: `barber_id`/`service_id` SENGAJA TANPA "FOREIGN KEY
        # ... REFERENCES barbers(id)/services(id)" (pola sama seperti
        # email_verification_tokens.user_id, lihat postgres_schema.py untuk
        # penjelasan lengkap) -- jalur SQLite sendiri TIDAK bermasalah (id
        # di sini selalu INTEGER PRIMARY KEY AUTOINCREMENT yang valid), tapi
        # FK ini tetap dihapus di jalur SQLite juga supaya definisi tabel
        # SIMETRIS dengan jalur PostgreSQL (yang WAJIB menghapusnya karena
        # tabel `barbers`/`services` produksi PostgreSQL ternyata tidak lagi
        # punya constraint UNIQUE/PRIMARY KEY murni pada `id`).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS manual_customer_transaksi (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id      INTEGER NOT NULL,
                tanggal        TEXT NOT NULL,
                nama_customer  TEXT NOT NULL,
                jenis          TEXT NOT NULL,
                jam            TEXT NOT NULL,
                barber_id      INTEGER,
                tips           INTEGER NOT NULL DEFAULT 0,
                catatan        TEXT,
                transaksi_id   INTEGER,
                dibuat_oleh    TEXT,
                created_at     TEXT NOT NULL,
                updated_at     TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS manual_customer_transaksi_service (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                manual_customer_transaksi_id INTEGER NOT NULL,
                service_id                  INTEGER NOT NULL,
                FOREIGN KEY (manual_customer_transaksi_id) REFERENCES manual_customer_transaksi(id) ON DELETE CASCADE
            )
        """)


# ---------------------------------------------------------------------------
# MODE HARIAN ("satu tanggal satu mode") -- lihat docstring modul
# ---------------------------------------------------------------------------

def get_status_hari(tenant_id: int, tanggal: str) -> dict:
    """Return {'mode': None, 'status': None} kalau tanggal ini belum pernah
    dipakai sama sekali (mode bebas dipilih)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT mode, status FROM input_data_hari WHERE tenant_id = ? AND tanggal = ?",
            (tenant_id, tanggal),
        ).fetchone()
    if row is None:
        return {"mode": None, "status": None}
    return {"mode": row["mode"], "status": row["status"]}


def pastikan_mode(tenant_id: int, tanggal: str, mode: str) -> None:
    """Dipanggil SEBELUM transaksi apa pun (Input Barber MAUPUN Manual
    Customer) dibuat untuk tenant_id+tanggal ini -- kalau tanggal itu belum
    punya mode, mode ini otomatis "diklaim" (baris input_data_hari dibuat).
    Kalau sudah punya mode LAIN, ValueError (pesan siap ditampilkan ke
    Owner). Kalau sudah 'closed' (hanya berlaku mode='manual_customer'),
    ValueError juga -- tidak boleh menambah entri baru pada hari yang sudah
    ditutup (lihat docstring modul: Closing BUKAN mengunci Rekap, tapi
    tetap menutup pintu penambahan ENTRI BARU di tanggal itu)."""
    if mode not in MODE_VALID:
        raise ValueError(f"Mode input tidak dikenal: {mode}")
    existing = get_status_hari(tenant_id, tanggal)
    if existing["mode"] is None:
        now = datetime.now().isoformat(timespec="seconds")
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO input_data_hari (tenant_id, tanggal, mode, status, created_at) "
                "VALUES (?, ?, ?, 'open', ?)",
                (tenant_id, tanggal, mode, now),
            )
        return
    if existing["mode"] != mode:
        label = {"barber": "Input Barber", "manual_customer": "Manual Customer"}
        raise ValueError(
            f"Tanggal {tanggal} sudah memakai metode \"{label.get(existing['mode'], existing['mode'])}\" -- "
            f"satu tanggal hanya boleh menggunakan satu metode input. Hapus/reset seluruh transaksi tanggal "
            f"ini dulu (tombol \"Reset Semua Transaksi Hari Ini\") kalau ingin mengganti metode."
        )
    if existing["status"] == "closed":
        raise ValueError(f"Tanggal {tanggal} sudah ditutup (Closing) -- tidak bisa menambah transaksi baru.")


def reset_hari(tenant_id: int, tanggal: str) -> None:
    """Tombol "Reset Semua Transaksi Hari Ini" -- menghapus SELURUH
    transaksi tanggal ini (kedua mode sekaligus, apa pun mode yang sedang
    aktif) supaya mode bebas dipilih ulang. Kalau mode='manual_customer',
    baris `transaksi` hasil Closing (kalau ada) ikut dihapus lewat
    database.hapus_transaksi() (cascade transaksi_detail otomatis, lihat
    database.py) -- dilacak PERSIS lewat manual_customer_transaksi.
    transaksi_id, BUKAN menghapus seluruh transaksi tanggal itu secara
    membabi buta (aman walau ada transaksi lain di tanggal sama yang
    entah bagaimana tercipta dari jalur lain)."""
    status = get_status_hari(tenant_id, tanggal)
    if status["mode"] is None:
        return  # tidak ada apa pun untuk direset
    if status["mode"] == "barber":
        with get_conn() as conn:
            baris = conn.execute(
                "SELECT t.id FROM transaksi t JOIN barbers b ON b.id = t.barber_id "
                "WHERE b.tenant_id = ? AND t.tanggal = ?",
                (tenant_id, tanggal),
            ).fetchall()
        for r in baris:
            hapus_transaksi(r["id"])
    else:
        entri = get_manual_customer_list(tenant_id, tanggal)
        for e in entri:
            if e.get("transaksi_id") is not None:
                hapus_transaksi(e["transaksi_id"])
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM manual_customer_transaksi WHERE tenant_id = ? AND tanggal = ?",
                (tenant_id, tanggal),
            )
    with get_conn() as conn:
        conn.execute("DELETE FROM input_data_hari WHERE tenant_id = ? AND tanggal = ?", (tenant_id, tanggal))


# ---------------------------------------------------------------------------
# CRUD manual_customer_transaksi
# ---------------------------------------------------------------------------

def _lengkapi(row: dict) -> dict:
    with get_conn() as conn:
        service_ids = [r["service_id"] for r in conn.execute(
            "SELECT service_id FROM manual_customer_transaksi_service "
            "WHERE manual_customer_transaksi_id = ? ORDER BY id ASC", (row["id"],),
        ).fetchall()]
    row["service_ids"] = service_ids
    row["daftar_service"] = []
    for sid in service_ids:
        s = get_service(sid)
        if s is not None:
            row["daftar_service"].append({"id": s["id"], "nama": s["nama"]})
    if row.get("barber_id") is not None:
        barber = get_barber(row["barber_id"])
        row["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    else:
        row["nama_barber"] = None
    return row


def get_manual_customer(entry_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM manual_customer_transaksi WHERE id = ?", (entry_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_manual_customer_list(tenant_id: int, tanggal: str) -> list:
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM manual_customer_transaksi WHERE tenant_id = ? AND tanggal = ? "
            "ORDER BY jam ASC, id ASC",
            (tenant_id, tanggal),
        ).fetchall()]
    return [_lengkapi(r) for r in rows]


def _pastikan_barber_tenant_sama(barber_id: int, tenant_id: int) -> None:
    barber = get_barber(barber_id)
    if barber is None or barber.get("tenant_id") != tenant_id:
        raise ValueError("Barber tidak ditemukan.")


def _pastikan_service_ids_valid(service_ids: list, tenant_id: int) -> list:
    bersih = []
    for sid in service_ids or []:
        s = get_service(sid)
        if s is None or (s.get("tenant_id") is not None and s.get("tenant_id") != tenant_id):
            raise ValueError(f"Service #{sid} tidak ditemukan.")
        bersih.append(int(sid))
    return bersih


def tambah_manual_customer(tenant_id: int, tanggal: str, nama_customer: str, jenis: str,
                            jam_booking: str = None, barber_id: int = None, service_ids: list = None,
                            tips: int = 0, catatan: str = None, dibuat_oleh: str = None) -> dict:
    """`jam_booking` HANYA dipakai (dan WAJIB diisi) untuk jenis='booking' --
    jam untuk jenis='waiting_list' SELALU dari jam server (WIB) saat ini,
    parameter jam_booking diabaikan kalau diisi untuk jenis ini (jangan
    sampai kasir bisa "menitipkan" jam manual lewat jalur Waiting List)."""
    datetime.strptime(tanggal, "%Y-%m-%d")  # ValueError kalau format salah
    nama_customer = (nama_customer or "").strip()
    if not nama_customer:
        raise ValueError("Nama Customer wajib diisi.")
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis customer tidak dikenal: {jenis}")

    pastikan_mode(tenant_id, tanggal, "manual_customer")

    if jenis == "waiting_list":
        jam = _sekarang_wib().strftime("%H:%M")
        if barber_id is not None:
            _pastikan_barber_tenant_sama(barber_id, tenant_id)
        service_ids_bersih = _pastikan_service_ids_valid(service_ids, tenant_id)
    else:  # booking
        jam = (jam_booking or "").strip()
        try:
            datetime.strptime(jam, "%H:%M")
        except ValueError:
            raise ValueError("Jam Booking wajib diisi (format JJ:MM).")
        if barber_id is None:
            raise ValueError("Barber wajib diisi untuk Booking.")
        _pastikan_barber_tenant_sama(barber_id, tenant_id)
        service_ids_bersih = _pastikan_service_ids_valid(service_ids, tenant_id)
        if not service_ids_bersih:
            raise ValueError("Service wajib diisi untuk Booking.")

    tips = int(tips or 0)
    if tips < 0:
        raise ValueError("Tips tidak boleh negatif.")

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO manual_customer_transaksi
                   (tenant_id, tanggal, nama_customer, jenis, jam, barber_id, tips, catatan,
                    dibuat_oleh, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, tanggal, nama_customer, jenis, jam, barber_id, tips,
             (catatan or "").strip() or None, dibuat_oleh, now),
        )
        entry_id = cur.lastrowid
        for sid in service_ids_bersih:
            conn.execute(
                "INSERT INTO manual_customer_transaksi_service (manual_customer_transaksi_id, service_id) "
                "VALUES (?, ?)",
                (entry_id, sid),
            )
    return get_manual_customer(entry_id)


def edit_manual_customer(entry_id: int, tenant_id: int, nama_customer: str = None, barber_id=None,
                          service_ids: list = None, tips: int = None, catatan: str = None) -> dict:
    """BOLEH diedit: nama_customer, barber_id, service_ids, tips, catatan.
    TIDAK PERNAH: jam, jenis, tanggal -- tidak ada parameter untuk itu sama
    sekali di sini (rule #14/#18: jam salah -> hapus, buat ulang).

    Kalau entri ini SUDAH diproses (transaksi_id terisi, lihat tutup_hari()),
    perubahan di sini ikut di-cascade ke baris `transaksi`/`transaksi_detail`
    terkait lewat database.koreksi_transaksi() supaya Rekap tetap sinkron
    (Closing tidak mengunci data, lihat docstring modul -- edit sesudah
    Closing tetap diizinkan Owner)."""
    from database import koreksi_transaksi  # import lokal: hindari siklik di modul level

    existing = get_manual_customer(entry_id)
    if existing is None or existing["tenant_id"] != tenant_id:
        raise ValueError("Data Manual Customer tidak ditemukan.")

    nama_baru = nama_customer.strip() if nama_customer is not None else existing["nama_customer"]
    if not nama_baru:
        raise ValueError("Nama Customer wajib diisi.")
    barber_baru = barber_id if barber_id is not None else existing["barber_id"]
    if barber_baru is not None:
        _pastikan_barber_tenant_sama(barber_baru, tenant_id)
    service_ids_baru = (
        _pastikan_service_ids_valid(service_ids, tenant_id) if service_ids is not None else existing["service_ids"]
    )
    if existing["jenis"] == "booking" and (barber_baru is None or not service_ids_baru):
        raise ValueError("Booking wajib memiliki Barber dan minimal satu Service.")
    tips_baru = int(tips) if tips is not None else existing["tips"]
    if tips_baru < 0:
        raise ValueError("Tips tidak boleh negatif.")
    catatan_baru = catatan.strip() if catatan is not None else existing["catatan"]

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "UPDATE manual_customer_transaksi SET nama_customer = ?, barber_id = ?, tips = ?, "
            "catatan = ?, updated_at = ? WHERE id = ?",
            (nama_baru, barber_baru, tips_baru, catatan_baru, now, entry_id),
        )
        if service_ids is not None:
            conn.execute(
                "DELETE FROM manual_customer_transaksi_service WHERE manual_customer_transaksi_id = ?",
                (entry_id,),
            )
            for sid in service_ids_baru:
                conn.execute(
                    "INSERT INTO manual_customer_transaksi_service (manual_customer_transaksi_id, service_id) "
                    "VALUES (?, ?)",
                    (entry_id, sid),
                )

    if existing.get("transaksi_id") is not None and barber_baru is not None and service_ids_baru:
        koreksi_transaksi(
            existing["transaksi_id"], barber_id=barber_baru,
            items=[{"service_id": sid, "jumlah": 1} for sid in service_ids_baru],
            tips=tips_baru,
        )
    return get_manual_customer(entry_id)


def hapus_manual_customer(entry_id: int, tenant_id: int) -> None:
    existing = get_manual_customer(entry_id)
    if existing is None or existing["tenant_id"] != tenant_id:
        raise ValueError("Data Manual Customer tidak ditemukan.")
    if existing.get("transaksi_id") is not None:
        hapus_transaksi(existing["transaksi_id"])
    with get_conn() as conn:
        conn.execute("DELETE FROM manual_customer_transaksi WHERE id = ?", (entry_id,))


# ---------------------------------------------------------------------------
# CLOSING ("Tutup & Simpan Hari Ini")
# ---------------------------------------------------------------------------

def tutup_hari(tenant_id: int, tanggal: str, ditutup_oleh: str = None) -> dict:
    """Rule #21/#22/#26: (1) HANYA baris yang SUDAH punya barber_id +
    minimal satu service yang diproses jadi transaksi Rekap SUNGGUHAN lewat
    database.tambah_transaksi() -- Waiting List yang belum dilengkapi tetap
    tersimpan sebagai histori TANPA menghasilkan pendapatan/service barber
    apa pun. (2) Idempoten TERHADAP DOUBLE CLOSING -- ValueError kalau
    tanggal ini sudah 'closed' (satu tenant+tanggal cuma boleh satu kali
    Closing, unique constraint tenant_id+tanggal di input_data_hari plus
    pengecekan status di sini). (3) Baris yang SUDAH diproses sebelumnya
    (transaksi_id sudah terisi -- mis. Closing dipanggil ulang setelah
    entri baru ditambah manual lewat jalur lain) TIDAK diproses ulang,
    mencegah baris `transaksi` duplikat."""
    status = get_status_hari(tenant_id, tanggal)
    if status["mode"] != "manual_customer":
        raise ValueError(f"Tanggal {tanggal} tidak memakai metode Manual Customer -- tidak ada yang perlu ditutup.")
    if status["status"] == "closed":
        raise ValueError(f"Tanggal {tanggal} sudah ditutup sebelumnya (Closing tidak bisa dilakukan dua kali).")

    entri = get_manual_customer_list(tenant_id, tanggal)
    diproses, dilewati = 0, 0
    for e in entri:
        if e.get("transaksi_id") is not None:
            continue  # sudah diproses Closing sebelumnya (seharusnya tidak terjadi, jaga-jaga)
        if e.get("barber_id") is None or not e.get("service_ids"):
            dilewati += 1  # Waiting List belum lengkap -- tetap histori, TIDAK masuk Rekap
            continue
        transaksi_id = tambah_transaksi(
            tanggal=tanggal, barber_id=e["barber_id"],
            items=[{"service_id": sid, "jumlah": 1} for sid in e["service_ids"]],
            tips=e.get("tips") or 0,
        )
        with get_conn() as conn:
            conn.execute(
                "UPDATE manual_customer_transaksi SET transaksi_id = ? WHERE id = ?",
                (transaksi_id, e["id"]),
            )
        diproses += 1

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "UPDATE input_data_hari SET status = 'closed', ditutup_oleh = ?, ditutup_at = ?, updated_at = ? "
            "WHERE tenant_id = ? AND tanggal = ?",
            (ditutup_oleh, now, now, tenant_id, tanggal),
        )
    return {"tanggal": tanggal, "diproses": diproses, "dilewati": dilewati}
