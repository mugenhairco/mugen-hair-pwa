"""
booking_db.py — Modul BOOKING: tabel & logika inti
=====================================================
Pola yang sama seperti auth_db.py (Tahap 1): file terpisah dengan
init_xxx_db() sendiri, TIDAK menambah apa pun ke database.py (yang tetap
salinan verbatim logika bisnis aplikasi Desktop). Booking adalah modul
BARU yang tidak ada di aplikasi Desktop, jadi wajar hidup di modulnya
sendiri, terpisah dari transaksi/komisi/dst.

Tabel yang dipakai:
- `bookings` / `booking_items` (baru di sini, lihat init_booking_db()).
- `closed_slot` (baru di sini) — jam yang ditutup manual oleh Owner/Admin.
- `absensi_libur` (SUDAH ADA di database.py, dipakai APA ADANYA lewat
  db.get_conn() -- SENGAJA TIDAK membuat tabel "barber holiday" baru.
  absensi_libur sudah persis merepresentasikan "barber ini libur pada
  tanggal ini", dipakai juga oleh hitung_bonus_customer() untuk kehadiran.
  Kalau Booking punya tabel holiday sendiri yang terpisah, akan ada dua
  sumber kebenaran yang bisa saling tidak sinkron -- mis. Owner menutup
  booking barber tapi lupa tandai di sistem lain, jadi bonus kehadirannya
  tetap dihitung seperti masuk kerja. Menu "Barber Holiday" di Booking
  memakai fungsi db.tandai_libur/batalkan_libur/get_libur_list yang
  SUDAH ADA, lewat endpoint /api/input-data/libur yang SUDAH ADA juga.

Prioritas pengecekan ketersediaan slot (SESUAI SPEK, urutan ini harus
selalu dipakai dan tidak boleh dibalik):
  1. Barber Holiday (absensi_libur)
  2. Closed Slot (closed_slot)
  3. Sudah dibooking (bookings + booking_items, status_booking='aktif')
  4. Available
"""

import json
import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import booking_gateway_db
import database as db
import file_asset_db
import pengaturan_identitas
import push_service
import r2_storage
import whatsapp_service
import whatsapp_templates
from database import get_conn

# PENYEMPURNAAN: "hari ini"/"jam sekarang" untuk keperluan slot booking HARUS
# selalu dihitung memakai zona waktu Asia/Jakarta (WIB) -- BUKAN zona waktu
# jam sistem server (yang di Render defaultnya UTC), dan BUKAN jam perangkat
# customer. Sebelumnya kode ini memakai date.today()/datetime.now() polos,
# yang diam-diam mengikuti zona waktu server -- karena Render biasanya UTC
# (7 jam di belakang WIB), ini bisa salah tanggal (dekat tengah malam WIB)
# maupun salah menentukan jam yang "sudah lewat".
WIB = ZoneInfo("Asia/Jakarta")

logger = logging.getLogger("mugen.booking")


def _sekarang_wib() -> datetime:
    return datetime.now(WIB)


def _hari_ini_wib() -> date:
    return _sekarang_wib().date()

BOOKING_SETTINGS_KEYS = [
    "booking_jam_buka", "booking_jam_tutup", "booking_interval_menit",
    "booking_maksimal_hari_kedepan",
]
PAYMENT_SETTINGS_KEYS = [
    "booking_metode_aktif", "booking_qris_merchant_nama",
    "booking_bank_nama", "booking_bank_nomor_rekening", "booking_bank_nama_pemilik",
]
METODE_VALID = {"transfer", "qris", "gateway"}

# PENYEMPURNAAN FORM BOOKING: hari dalam seminggu (index Python-style,
# senin=0 .. minggu=6, sama seperti datetime.weekday()) yang toko buka.
# Default SEMUA hari aktif (7 hari) supaya migrasi tidak diam-diam menutup
# toko di hari yang sebelumnya bisa dibooking -- Owner yang mempersempit
# sendiri lewat Setting kalau memang ada hari libur rutin.
HARI_LIST = ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"]
_DEFAULT_HARI_OPERASIONAL = json.dumps(HARI_LIST)
_DEFAULT_METODE_NAMA = json.dumps({})
_DEFAULT_METODE_INSTRUKSI = json.dumps({})


def init_booking_db():
    """CREATE TABLE IF NOT EXISTS — aman dipanggil berkali-kali, tidak pernah
    menimpa/menghapus data yang sudah ada."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id           INTEGER NOT NULL,
                tanggal             TEXT NOT NULL,
                jam_mulai           TEXT NOT NULL,
                jam_selesai         TEXT NOT NULL,
                customer_nama       TEXT NOT NULL,
                customer_whatsapp   TEXT NOT NULL,
                total_harga         INTEGER NOT NULL,
                total_durasi_menit  INTEGER NOT NULL,
                metode_pembayaran   TEXT NOT NULL,
                status_pembayaran   TEXT NOT NULL DEFAULT 'menunggu_verifikasi',
                status_booking      TEXT NOT NULL DEFAULT 'aktif',
                catatan             TEXT,
                created_at          TEXT NOT NULL,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_items (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id    INTEGER NOT NULL,
                service_id    INTEGER NOT NULL,
                nama_service  TEXT NOT NULL,
                harga         INTEGER NOT NULL,
                durasi_menit  INTEGER NOT NULL,
                FOREIGN KEY (booking_id) REFERENCES bookings(id),
                FOREIGN KEY (service_id) REFERENCES services(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS closed_slot (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id   INTEGER NOT NULL,
                tanggal     TEXT NOT NULL,
                jam_mulai   TEXT NOT NULL,
                jam_selesai TEXT NOT NULL,
                keterangan  TEXT,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)
        # PENYEMPURNAAN FORM BOOKING: hari libur TOKO (semua barber sekaligus,
        # mis. libur nasional/lebaran) -- BEDA dari closed_slot (per-barber,
        # per-jam) dan absensi_libur/Barber Holiday (per-barber, per-hari).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS toko_libur (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal     TEXT NOT NULL UNIQUE,
                keterangan  TEXT,
                created_at  TEXT NOT NULL
            )
        """)


# ---------------------------------------------------------------------------
# Helper waktu (murni fungsi, tidak sentuh database)
# ---------------------------------------------------------------------------

def _ke_menit(jam_hhmm: str) -> int:
    h, m = jam_hhmm.split(":")
    return int(h) * 60 + int(m)


def _ke_hhmm(menit: int) -> str:
    h, m = divmod(menit, 60)
    return f"{h:02d}:{m:02d}"


def _tumpang_tindih(a_mulai, a_selesai, b_mulai, b_selesai) -> bool:
    return a_mulai < b_selesai and b_mulai < a_selesai


def _validasi_tanggal(tanggal: str):
    datetime.strptime(tanggal, "%Y-%m-%d")


def _validasi_jam(jam: str):
    if len(jam) != 5 or jam[2] != ":":
        raise ValueError("Format jam harus HH:MM.")
    h, m = int(jam[:2]), int(jam[3:])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Jam tidak valid.")


_WHATSAPP_RE = re.compile(r"^\+?[0-9]{8,15}$")


def _whatsapp_valid(nomor: str) -> bool:
    """Validasi longgar (nomor Indonesia bisa diawali 08/+62/62) -- hanya
    memastikan formatnya masuk akal (digit + tanda + di depan, 8-15
    digit), bukan verifikasi nomor itu benar-benar aktif."""
    nomor = (nomor or "").strip().replace(" ", "").replace("-", "")
    return bool(_WHATSAPP_RE.match(nomor))


# ---------------------------------------------------------------------------
# SETTING BOOKING (jam operasional, interval, maks. hari ke depan)
# ---------------------------------------------------------------------------

def get_booking_settings(tenant_id: int = None) -> dict:
    """FONDASI Multi-Tenant Phase 1: tenant BARU (dibuat lewat
    tenant_db.buat_tenant(), belum pernah membuka Setting > Booking Settings
    sama sekali) belum punya baris `settings` apa pun -- default di bawah
    (10:00-20:00, interval 60 menit, maks 30 hari ke depan) mencegah 500
    (dulu int(None) meledak) sampai Owner tenant itu mengaturnya sendiri,
    SAMA PERSIS dengan DEFAULT_BOOKING_SETTINGS di booking_migrasi.py/
    postgres_schema.py yang otomatis di-seed untuk instalasi satu-tenant."""
    s = {k: db.get_setting(k, tenant_id=tenant_id) for k in BOOKING_SETTINGS_KEYS}
    try:
        hari_operasional = json.loads(db.get_setting("booking_hari_operasional", _DEFAULT_HARI_OPERASIONAL,
                                                       tenant_id=tenant_id))
    except (TypeError, ValueError):
        hari_operasional = list(HARI_LIST)
    return {
        "jam_buka": s["booking_jam_buka"] or "10:00",
        "jam_tutup": s["booking_jam_tutup"] or "20:00",
        "interval_menit": int(s["booking_interval_menit"] or 60),
        "maksimal_hari_kedepan": int(s["booking_maksimal_hari_kedepan"] or 30),
        "hari_operasional": hari_operasional,
        # REVISI STRUKTUR WEBSITE CONTENT: header_judul/header_subtitle/
        # header_footer/pesan_pembuka (teks tampilan halaman /book) DIHAPUS
        # dari sini -- digantikan Hero/Footer di Booking > Website Content.
        # Pesan di bawah ini TETAP di sini karena bukan "konten tampilan
        # website", melainkan pesan transaksional alur booking (konfirmasi
        # sukses & validasi form), beda kategori.
        "pesan_penutup": db.get_setting(
            "booking_pesan_penutup",
            "Terima kasih! Kami akan segera menghubungi Anda lewat WhatsApp untuk konfirmasi.",
            tenant_id=tenant_id,
        ),
        "pesan_nama_kosong": db.get_setting("booking_pesan_nama_kosong", "Nama tidak boleh kosong.",
                                             tenant_id=tenant_id),
        "pesan_whatsapp_invalid": db.get_setting("booking_pesan_whatsapp_invalid", "Nomor WhatsApp tidak valid.",
                                                  tenant_id=tenant_id),
    }


def update_booking_settings(jam_buka: str = None, jam_tutup: str = None,
                             interval_menit: int = None, maksimal_hari_kedepan: int = None,
                             hari_operasional: list = None,
                             pesan_penutup: str = None,
                             pesan_nama_kosong: str = None, pesan_whatsapp_invalid: str = None,
                             tenant_id: int = None):
    if jam_buka is not None:
        _validasi_jam(jam_buka)
    if jam_tutup is not None:
        _validasi_jam(jam_tutup)
    if jam_buka is not None and jam_tutup is not None and _ke_menit(jam_buka) >= _ke_menit(jam_tutup):
        raise ValueError("Jam buka harus lebih awal dari jam tutup.")
    if interval_menit is not None and interval_menit <= 0:
        raise ValueError("Interval slot harus lebih dari 0 menit.")
    if maksimal_hari_kedepan is not None and maksimal_hari_kedepan <= 0:
        raise ValueError("Maksimal hari booking ke depan harus lebih dari 0.")
    if hari_operasional is not None:
        tidak_valid = [h for h in hari_operasional if h not in HARI_LIST]
        if tidak_valid:
            raise ValueError(f"Hari tidak dikenal: {', '.join(tidak_valid)}.")

    data = {}
    if jam_buka is not None: data["booking_jam_buka"] = jam_buka
    if jam_tutup is not None: data["booking_jam_tutup"] = jam_tutup
    if interval_menit is not None: data["booking_interval_menit"] = str(int(interval_menit))
    if maksimal_hari_kedepan is not None: data["booking_maksimal_hari_kedepan"] = str(int(maksimal_hari_kedepan))
    if hari_operasional is not None: data["booking_hari_operasional"] = json.dumps(hari_operasional)
    if pesan_penutup is not None: data["booking_pesan_penutup"] = pesan_penutup.strip()
    if pesan_nama_kosong is not None: data["booking_pesan_nama_kosong"] = pesan_nama_kosong.strip()
    if pesan_whatsapp_invalid is not None: data["booking_pesan_whatsapp_invalid"] = pesan_whatsapp_invalid.strip()
    if data:
        db.set_settings_bulk(data, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# PAYMENT SETTINGS (metode aktif, QRIS, transfer bank)
# ---------------------------------------------------------------------------

# PENYEMPURNAAN FORM BOOKING: label & teks instruksi bawaan per metode
# pembayaran -- dipakai kalau Owner belum menimpanya lewat Setting (nilai
# ini SAMA PERSIS dengan teks yang sebelumnya hardcode di frontend, supaya
# tampilan tidak berubah sampai Owner sengaja menggantinya).
DEFAULT_METODE_NAMA = {
    "transfer": "Transfer Bank", "qris": "QRIS", "gateway": "Payment Gateway",
}
DEFAULT_METODE_INSTRUKSI = {
    "transfer": "Booking akan berstatus \"Menunggu Verifikasi\" sampai staff mengonfirmasi transfer Anda.",
    "qris": "Booking akan berstatus \"Menunggu Verifikasi\" sampai staff mengonfirmasi pembayaran Anda.",
    "gateway": "Selesaikan pembayaran lewat channel yang Anda pilih. Booking otomatis terkonfirmasi begitu pembayaran berhasil.",
}


def get_payment_settings(tenant_id: int = None) -> dict:
    s = {k: db.get_setting(k, tenant_id=tenant_id) for k in PAYMENT_SETTINGS_KEYS}
    try:
        metode_aktif = json.loads(s["booking_metode_aktif"] or "[]")
    except (TypeError, ValueError):
        metode_aktif = []
    try:
        metode_nama_custom = json.loads(db.get_setting("booking_metode_nama", _DEFAULT_METODE_NAMA,
                                                         tenant_id=tenant_id))
    except (TypeError, ValueError):
        metode_nama_custom = {}
    try:
        metode_instruksi_custom = json.loads(db.get_setting("booking_metode_instruksi", _DEFAULT_METODE_INSTRUKSI,
                                                              tenant_id=tenant_id))
    except (TypeError, ValueError):
        metode_instruksi_custom = {}
    qris_filename = file_asset_db.ambil_meta("qris", tenant_id=tenant_id)
    qris_url = None
    if qris_filename:
        # AUDIT 404 file media: <img src> QRIS TIDAK BISA membawa Bearer
        # token/Origin (lihat tenant_db.slug_untuk_url_media() untuk
        # penjelasan lengkap -- bug yang sama dengan logo/favicon).
        import tenant_db  # import lokal: hindari import siklik
        slug = tenant_db.slug_untuk_url_media(tenant_id)
        qris_url = f"/api/public/booking/qris?v={qris_filename}" + (f"&tenant={slug}" if slug else "")
    return {
        "metode_aktif": metode_aktif,
        "metode_nama": {**DEFAULT_METODE_NAMA, **metode_nama_custom},
        "metode_instruksi": {**DEFAULT_METODE_INSTRUKSI, **metode_instruksi_custom},
        "qris_merchant_nama": s["booking_qris_merchant_nama"],
        "qris_url": qris_url,
        "bank_nama": s["booking_bank_nama"],
        "bank_nomor_rekening": s["booking_bank_nomor_rekening"],
        "bank_nama_pemilik": s["booking_bank_nama_pemilik"],
    }


def update_payment_settings(metode_aktif: list = None, qris_merchant_nama: str = None,
                             bank_nama: str = None, bank_nomor_rekening: str = None,
                             bank_nama_pemilik: str = None, metode_nama: dict = None,
                             metode_instruksi: dict = None, tenant_id: int = None):
    data = {}
    if metode_aktif is not None:
        tidak_valid = [m for m in metode_aktif if m not in METODE_VALID]
        if tidak_valid:
            raise ValueError(f"Metode pembayaran tidak dikenal: {', '.join(tidak_valid)}.")
        data["booking_metode_aktif"] = json.dumps(metode_aktif)
    if qris_merchant_nama is not None:
        data["booking_qris_merchant_nama"] = qris_merchant_nama.strip()
    if bank_nama is not None:
        data["booking_bank_nama"] = bank_nama.strip()
    if bank_nomor_rekening is not None:
        data["booking_bank_nomor_rekening"] = bank_nomor_rekening.strip()
    if bank_nama_pemilik is not None:
        data["booking_bank_nama_pemilik"] = bank_nama_pemilik.strip()
    if metode_nama is not None:
        tidak_valid = [m for m in metode_nama if m not in METODE_VALID]
        if tidak_valid:
            raise ValueError(f"Metode pembayaran tidak dikenal: {', '.join(tidak_valid)}.")
        # Gabung dengan yang sudah tersimpan (bukan timpa penuh) supaya
        # menyimpan SATU label tidak menghapus label metode lain yang
        # sudah pernah diatur Owner sebelumnya.
        existing = json.loads(db.get_setting("booking_metode_nama", _DEFAULT_METODE_NAMA, tenant_id=tenant_id))
        existing.update({k: v.strip() for k, v in metode_nama.items()})
        data["booking_metode_nama"] = json.dumps(existing)
    if metode_instruksi is not None:
        tidak_valid = [m for m in metode_instruksi if m not in METODE_VALID]
        if tidak_valid:
            raise ValueError(f"Metode pembayaran tidak dikenal: {', '.join(tidak_valid)}.")
        existing = json.loads(db.get_setting("booking_metode_instruksi", _DEFAULT_METODE_INSTRUKSI,
                                              tenant_id=tenant_id))
        existing.update({k: v.strip() for k, v in metode_instruksi.items()})
        data["booking_metode_instruksi"] = json.dumps(existing)
    if data:
        db.set_settings_bulk(data, tenant_id=tenant_id)


# QRIS image upload — pola SAMA PERSIS seperti pengaturan_identitas.py punya
# untuk logo barbershop (slot tunggal, lihat file_asset_db.py).
EXT_KE_CONTENT_TYPE = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def simpan_qris(filename_asli: str, konten: bytes, tenant_id: int = None) -> str:
    return file_asset_db.simpan("qris", filename_asli, konten, EXT_KE_CONTENT_TYPE, "QRIS",
                                 maks_ukuran_bytes=r2_storage.MAKS_UKURAN_GAMBAR_BYTES, tenant_id=tenant_id)


def hapus_qris(tenant_id: int = None):
    file_asset_db.hapus("qris", tenant_id=tenant_id)


def get_qris_data(tenant_id: int = None):
    return file_asset_db.ambil("qris", tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# CLOSED SLOT
# ---------------------------------------------------------------------------

def tambah_closed_slot(barber_id: int, tanggal: str, jam_mulai: str, jam_selesai: str,
                        keterangan: str = None, tenant_id: int = None) -> int:
    _validasi_tanggal(tanggal)
    _validasi_jam(jam_mulai)
    _validasi_jam(jam_selesai)
    if _ke_menit(jam_mulai) >= _ke_menit(jam_selesai):
        raise ValueError("Jam mulai harus lebih awal dari jam selesai.")
    barber = db.get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber.get("tenant_id") != tenant_id):
        raise ValueError("Barber tidak ditemukan.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO closed_slot (barber_id, tanggal, jam_mulai, jam_selesai, keterangan, created_at, tenant_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (barber_id, tanggal, jam_mulai, jam_selesai, (keterangan or "").strip() or None, now, tenant_id),
        )
        return cur.lastrowid


def hapus_closed_slot(closed_slot_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM closed_slot WHERE id = ?", (closed_slot_id,))


def get_closed_slot(closed_slot_id: int):
    """FONDASI Multi-Tenant Phase 1: dipakai router untuk fetch-then-authorize
    sebelum hapus_closed_slot() (yang sendiri tetap tidak menerima parameter
    tenant_id baru, sama seperti pola get_barber()/get_service())."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM closed_slot WHERE id = ?", (closed_slot_id,)).fetchone()
        return dict(row) if row else None


def get_closed_slot_list(barber_id: int = None, tahun: int = None, bulan: int = None,
                          tenant_id: int = None) -> list:
    q = """SELECT cs.*, b.nama AS nama_barber FROM closed_slot cs
           JOIN barbers b ON b.id = cs.barber_id WHERE 1=1"""
    params = []
    if barber_id is not None:
        q += " AND cs.barber_id = ?"; params.append(barber_id)
    if tenant_id is not None:
        q += " AND cs.tenant_id = ?"; params.append(tenant_id)
    if tahun is not None:
        q += " AND cs.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND cs.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    q += " ORDER BY cs.tanggal DESC, cs.jam_mulai"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def _get_closed_slots_tanggal(conn, barber_id: int, tanggal: str) -> list:
    rows = conn.execute(
        "SELECT jam_mulai, jam_selesai FROM closed_slot WHERE barber_id = ? AND tanggal = ?",
        (barber_id, tanggal),
    ).fetchall()
    return [(_ke_menit(r["jam_mulai"]), _ke_menit(r["jam_selesai"])) for r in rows]


# ---------------------------------------------------------------------------
# BARBER HOLIDAY -- pakai absensi_libur yang SUDAH ADA (database.py), lewat
# get_conn() query langsung (bukan lewat fungsi baru di database.py, supaya
# database.py benar-benar tidak tersentuh sama sekali untuk modul ini).
# ---------------------------------------------------------------------------

def is_barber_libur(barber_id: int, tanggal: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM absensi_libur WHERE barber_id = ? AND tanggal = ?",
            (barber_id, tanggal),
        ).fetchone()
        return row is not None


def is_barber_cuti(barber_id: int) -> bool:
    """Status 'cuti' (On Vacation) di kolom barbers.status_booking -- cuti
    PANJANG/tidak tentu (barber tidak bisa dibooking di SEMUA tanggal
    sampai Owner mengembalikan status-nya ke 'aktif'). BEDA dari
    is_barber_libur() di atas yang per-TANGGAL (Barber Holiday)."""
    barber = db.get_barber(barber_id)
    return barber is not None and barber.get("status_booking") == "cuti"


# ---------------------------------------------------------------------------
# TOKO LIBUR -- hari libur TOKO (SEMUA barber sekaligus), BEDA dari
# Barber Holiday (absensi_libur, per-barber) dan Closed Slot (closed_slot,
# per-barber per-jam). Tabel dibuat di init_booking_db() di atas.
# ---------------------------------------------------------------------------

def is_toko_libur(tanggal: str, tenant_id: int = None) -> bool:
    with get_conn() as conn:
        if tenant_id is not None:
            row = conn.execute("SELECT 1 FROM toko_libur WHERE tanggal = ? AND tenant_id = ?",
                                (tanggal, tenant_id)).fetchone()
        else:
            row = conn.execute("SELECT 1 FROM toko_libur WHERE tanggal = ?", (tanggal,)).fetchone()
        return row is not None


def is_hari_operasional(tanggal: str, tenant_id: int = None) -> bool:
    """Cek pola hari operasional mingguan (mis. toko tidak buka hari Minggu).
    `tanggal.weekday()`: Senin=0 .. Minggu=6, sama urutan dengan HARI_LIST."""
    hari_aktif = get_booking_settings(tenant_id=tenant_id)["hari_operasional"]
    hari_ini = HARI_LIST[datetime.strptime(tanggal, "%Y-%m-%d").weekday()]
    return hari_ini in hari_aktif


def tambah_toko_libur(tanggal: str, keterangan: str = None, tenant_id: int = None) -> int:
    _validasi_tanggal(tanggal)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        if tenant_id is not None:
            existing = conn.execute("SELECT id FROM toko_libur WHERE tanggal = ? AND tenant_id = ?",
                                     (tanggal, tenant_id)).fetchone()
        else:
            existing = conn.execute("SELECT id FROM toko_libur WHERE tanggal = ?", (tanggal,)).fetchone()
        if existing is not None:
            raise ValueError(f"Tanggal {tanggal} sudah ditandai libur toko.")
        cur = conn.execute(
            "INSERT INTO toko_libur (tanggal, keterangan, created_at, tenant_id) VALUES (?, ?, ?, ?)",
            (tanggal, (keterangan or "").strip() or None, now, tenant_id),
        )
        return cur.lastrowid


def hapus_toko_libur(toko_libur_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM toko_libur WHERE id = ?", (toko_libur_id,))


def get_toko_libur(toko_libur_id: int):
    """FONDASI Multi-Tenant Phase 1: dipakai router untuk fetch-then-authorize
    sebelum hapus_toko_libur()."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM toko_libur WHERE id = ?", (toko_libur_id,)).fetchone()
        return dict(row) if row else None


def get_toko_libur_list(tahun: int = None, bulan: int = None, tenant_id: int = None) -> list:
    q = "SELECT * FROM toko_libur WHERE 1=1"
    params = []
    if tenant_id is not None:
        q += " AND tenant_id = ?"; params.append(tenant_id)
    if tahun is not None:
        q += " AND tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    q += " ORDER BY tanggal DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


# ---------------------------------------------------------------------------
# BOOKING -- daftar terpakai (untuk cek tumpang tindih) & CRUD
# ---------------------------------------------------------------------------

def _get_booking_aktif_tanggal(conn, barber_id: int, tanggal: str) -> list:
    rows = conn.execute(
        "SELECT jam_mulai, jam_selesai FROM bookings "
        "WHERE barber_id = ? AND tanggal = ? AND status_booking = 'aktif'",
        (barber_id, tanggal),
    ).fetchall()
    return [(_ke_menit(r["jam_mulai"]), _ke_menit(r["jam_selesai"])) for r in rows]


def hitung_slot(barber_id: int, tanggal: str, service_ids: list = None, tenant_id: int = None) -> dict:
    """Return status ketersediaan untuk SEMUA kandidat jam mulai pada satu
    tanggal, plus info barber libur/tidak. `service_ids` kosong = cek per
    SATU interval (dipakai tampilan awal pilih jam, sebelum service
    dipilih); diisi = cek span PENUH sesuai total durasi service yang
    dipilih (dipakai validasi ulang setelah Pilih Service, dan sekali lagi
    saat submit booking).

    PENYEMPURNAAN FORM BOOKING: prioritas pengecekan sekarang, urutan ini
    harus selalu dipakai dan tidak boleh dibalik:
      0. Toko Libur / di luar Hari Operasional (SEMUA barber tutup)
      1. Barber Holiday (per-tanggal) ATAU status_booking='cuti' (jangka
         panjang) -- keduanya sama-sama berarti barber itu tidak bisa
         dibooking
      2. Closed Slot
      3. Sudah dibooking
      4. Available"""
    _validasi_tanggal(tanggal)
    barber = db.get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber.get("tenant_id") != tenant_id):
        raise ValueError("Barber tidak ditemukan.")

    pengaturan = get_booking_settings(tenant_id=tenant_id)
    interval = pengaturan["interval_menit"]
    jam_buka_menit = _ke_menit(pengaturan["jam_buka"])
    jam_tutup_menit = _ke_menit(pengaturan["jam_tutup"])

    if service_ids:
        durasi = _hitung_total_durasi(service_ids)
    else:
        durasi = interval

    toko_tutup = is_toko_libur(tanggal, tenant_id=tenant_id) or not is_hari_operasional(tanggal, tenant_id=tenant_id)
    barber_libur = is_barber_libur(barber_id, tanggal) or barber.get("status_booking") == "cuti"

    with get_conn() as conn:
        closed = _get_closed_slots_tanggal(conn, barber_id, tanggal)
        booked = _get_booking_aktif_tanggal(conn, barber_id, tanggal)

    sekarang_menit = None
    if tanggal == _hari_ini_wib().isoformat():
        now = _sekarang_wib()
        sekarang_menit = now.hour * 60 + now.minute

    slots = []
    t = jam_buka_menit
    while t < jam_tutup_menit:
        akhir = t + durasi
        if akhir > jam_tutup_menit:
            break  # durasi service tidak muat lagi sebelum tutup, kandidat berikutnya juga pasti tidak muat
        if toko_tutup or barber_libur:
            status = "closed"
        elif sekarang_menit is not None and t < sekarang_menit:
            status = "closed"  # jam yang sudah lewat hari ini, bukan slot yang benar-benar "ditutup" Owner
        elif any(_tumpang_tindih(t, akhir, b_mulai, b_akhir) for b_mulai, b_akhir in closed):
            status = "closed"
        elif any(_tumpang_tindih(t, akhir, b_mulai, b_akhir) for b_mulai, b_akhir in booked):
            status = "booked"
        else:
            status = "available"
        slots.append({"jam": _ke_hhmm(t), "status": status})
        t += interval

    return {
        "toko_libur": toko_tutup,
        "barber_libur": barber_libur,
        "durasi_menit": durasi,
        **pengaturan,
        "slots": slots,
    }


def _hitung_total_durasi(service_ids: list) -> int:
    total = 0
    for sid in service_ids:
        s = db.get_service(sid)
        if s is None:
            raise ValueError(f"Service #{sid} tidak ditemukan.")
        total += int(s.get("durasi_menit") or 60)
    return total


def _validasi_slot_tersedia(barber_id: int, tanggal: str, jam_mulai: str, durasi_menit: int,
                             tenant_id: int = None):
    """Validasi FINAL (dipanggil sekali lagi tepat sebelum booking benar-benar
    disimpan, terlepas dari apa pun yang sudah dicek di frontend) -- jaga-jaga
    dua customer booking slot yang sama nyaris bersamaan. Urutan pengecekan
    mengikuti prioritas: Toko Libur/Hari Operasional -> Barber Holiday/Cuti
    -> Closed Slot -> Sudah dibooking -> Available."""
    if is_toko_libur(tanggal, tenant_id=tenant_id):
        raise ValueError("Toko sedang libur pada tanggal ini.")
    if not is_hari_operasional(tanggal, tenant_id=tenant_id):
        raise ValueError("Toko tidak buka pada hari ini.")
    barber = db.get_barber(barber_id)
    if barber is not None and barber.get("status_booking") == "cuti":
        raise ValueError("Barber sedang cuti/On Vacation.")
    if is_barber_libur(barber_id, tanggal):
        raise ValueError("Barber sedang libur pada tanggal ini.")

    pengaturan = get_booking_settings(tenant_id=tenant_id)
    jam_buka_menit = _ke_menit(pengaturan["jam_buka"])
    jam_tutup_menit = _ke_menit(pengaturan["jam_tutup"])
    mulai = _ke_menit(jam_mulai)
    akhir = mulai + durasi_menit
    if mulai < jam_buka_menit or akhir > jam_tutup_menit:
        raise ValueError("Jam booking di luar jam operasional.")
    if tanggal == _hari_ini_wib().isoformat():
        now = _sekarang_wib()
        if mulai < now.hour * 60 + now.minute:
            raise ValueError("Jam yang dipilih sudah lewat.")

    maks_hari = pengaturan["maksimal_hari_kedepan"]
    batas = _hari_ini_wib() + timedelta(days=maks_hari)
    if datetime.strptime(tanggal, "%Y-%m-%d").date() > batas:
        raise ValueError(f"Booking hanya bisa dilakukan maksimal {maks_hari} hari ke depan.")

    with get_conn() as conn:
        closed = _get_closed_slots_tanggal(conn, barber_id, tanggal)
        if any(_tumpang_tindih(mulai, akhir, b_mulai, b_akhir) for b_mulai, b_akhir in closed):
            raise ValueError("Jam yang dipilih sudah ditutup untuk booking.")
        booked = _get_booking_aktif_tanggal(conn, barber_id, tanggal)
        if any(_tumpang_tindih(mulai, akhir, b_mulai, b_akhir) for b_mulai, b_akhir in booked):
            raise ValueError("Jam yang dipilih sudah dibooking, silakan pilih jam lain.")


def _kirim_notifikasi_wa_booking(booking: dict, jenis: str):
    """FITUR Notifikasi WhatsApp Otomatis Booking: dipanggil dari
    buat_booking()/verifikasi_pembayaran()/batalkan_booking() di bawah --
    "best effort", TIDAK PERNAH melempar exception maupun menggagalkan
    operasi booking utamanya kalau pengiriman WhatsApp gagal/token belum
    diisi (lihat whatsapp_service.kirim_whatsapp()). `booking` WAJIB sudah
    lengkap (hasil get_booking(), punya daftar_service/total_harga/dst).
    `jenis` = salah satu whatsapp_service.TEMPLATE_SETTING_KEYS -- teks
    pesan diambil dari template CUSTOM milik tenant kalau Owner sudah
    mengaturnya lewat Setting > WhatsApp, kalau belum fallback ke
    whatsapp_templates.DEFAULT_TEMPLATES (lihat render()).

    Feature Gating "whatsapp_reminder" (AUDIT "fitur hardcode di
    Superadmin"): SATU pengecualian sengaja dari aturan "business logic
    tidak tahu apa-apa soal billing" (feature_access.py/auth.py::
    require_feature() biasanya dipasang di lapisan router) -- titik pemicu
    notifikasi ini MURNI di dalam booking_db.py sendiri (dipanggil dari
    tengah buat_booking()/verifikasi_pembayaran()/batalkan_booking(), bukan
    endpoint router tunggal), tidak ada satu titik router yang bisa
    menggerbang di granularitas yang sama tanpa mengubah alur booking utama.
    Dicek di sini SEBELUM try/except best-effort di bawah (bukan di
    dalamnya) supaya tenant tanpa fitur ini TIDAK tercatat sebagai
    "percobaan gagal" di mana pun -- murni tidak pernah mencoba sama sekali,
    sama seperti token Fonnte kosong."""
    tenant_id = booking.get("tenant_id")
    import feature_access  # import lokal: hindari import siklik (feature_access.py -> database.py)
    if tenant_id is None or not feature_access.tenant_has_feature(tenant_id, "whatsapp_reminder"):
        return
    try:
        nama_toko = pengaturan_identitas.get_identitas(tenant_id=tenant_id).get("nama_barbershop") or "Kami"
        template_text = whatsapp_service.get_templates(tenant_id=tenant_id).get(jenis)
        pesan = whatsapp_templates.render(jenis, booking, nama_toko, template_text)
        whatsapp_service.kirim_whatsapp(booking["customer_whatsapp"], pesan, tenant_id=tenant_id)
    except Exception as e:
        logger.error("Notifikasi WhatsApp booking #%s GAGAL disiapkan: %s: %s", booking.get("id"), type(e).__name__, e)


def _kirim_notifikasi_push_booking_baru(booking: dict):
    """FITUR Notifikasi Push: dipanggil dari buat_booking() di bawah --
    "best effort" sama persis _kirim_notifikasi_wa_booking() di atas, TIDAK
    PERNAH melempar exception maupun menggagalkan booking utamanya kalau
    push gagal/belum dikonfigurasi Owner (lihat push_service.IS_ENABLED).
    Dikirim ke role admin/staff (yang mengelola menu Booking) -- audiens
    SAMA seperti badge/suara "Booking Baru" yang sudah ada (booking_notif.js)."""
    try:
        tenant_id = booking.get("tenant_id")
        push_service.kirim_ke_role(
            tenant_id, ["admin", "staff"],
            title="Booking Baru",
            body=f"{booking.get('customer_nama') or 'Customer'} booking {booking.get('tanggal')} {booking.get('jam_mulai')}.",
            url="/app/#/booking",
        )
    except Exception as e:
        logger.error("Notifikasi push booking #%s GAGAL disiapkan: %s: %s", booking.get("id"), type(e).__name__, e)


def buat_booking(barber_id: int, tanggal: str, jam_mulai: str, service_ids: list,
                  customer_nama: str, customer_whatsapp: str, metode_pembayaran: str,
                  catatan: str = None, tenant_id: int = None) -> dict:
    """FONDASI Multi-Tenant Phase 1: `tenant_id` (resolusi tenant publik,
    lihat routers/booking.py::resolve_tenant_publik()) diverifikasi TEGAS
    terhadap barber_id/service_ids yang dikirim customer -- SATU-SATUNYA
    cara memastikan "customer TIDAK PERNAH bisa booking ke barber/service
    milik toko lain" (persyaratan eksplisit Phase 1), bukan cuma dipercaya
    dari parameter. Baris `bookings` yang tersimpan ikut membawa tenant_id
    ini (kolom langsung, lihat tenant_migrasi.py)."""
    pesan = get_booking_settings(tenant_id=tenant_id)
    if not service_ids:
        raise ValueError("Pilih minimal satu service.")
    if not (customer_nama or "").strip():
        raise ValueError(pesan["pesan_nama_kosong"])
    if not _whatsapp_valid(customer_whatsapp):
        raise ValueError(pesan["pesan_whatsapp_invalid"])
    if metode_pembayaran not in METODE_VALID:
        raise ValueError("Metode pembayaran tidak dikenal.")
    metode_aktif = get_payment_settings(tenant_id=tenant_id)["metode_aktif"]
    if metode_pembayaran not in metode_aktif:
        raise ValueError("Metode pembayaran itu sedang tidak aktif.")
    _validasi_tanggal(tanggal)
    _validasi_jam(jam_mulai)

    barber = db.get_barber(barber_id)
    if barber is None or not barber.get("aktif") or (tenant_id is not None and barber.get("tenant_id") != tenant_id):
        raise ValueError("Barber tidak ditemukan atau tidak aktif.")

    items = []
    total_harga = 0
    total_durasi = 0
    for sid in service_ids:
        s = db.get_service(sid)
        if s is None or not s.get("aktif") or (tenant_id is not None and s.get("tenant_id") != tenant_id):
            raise ValueError(f"Service #{sid} tidak ditemukan atau tidak aktif.")
        items.append(s)
        total_harga += int(s["harga"])
        total_durasi += int(s.get("durasi_menit") or 60)

    _validasi_slot_tersedia(barber_id, tanggal, jam_mulai, total_durasi, tenant_id=tenant_id)

    jam_selesai = _ke_hhmm(_ke_menit(jam_mulai) + total_durasi)
    now = datetime.now().isoformat(timespec="seconds")
    # Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant: SEMUA
    # metode (termasuk "gateway") SEKARANG mulai 'menunggu_verifikasi' --
    # SEBELUMNYA "gateway" langsung dianggap 'terverifikasi' begitu wizard
    # publik melapor sendiri (self-report, TANPA verifikasi pembayaran
    # nyata sama sekali). Status pembayaran booking "gateway" HANYA boleh
    # berubah jadi 'terverifikasi' lewat booking_gateway_webhook.py
    # (webhook resmi provider tervalidasi signature), TIDAK PERNAH dari
    # klaim customer/frontend -- lihat routers/booking.py::public_buat_booking()
    # untuk alur checkout gateway (buat transaksi provider SETELAH baris
    # ini dibuat).
    status_pembayaran_awal = "menunggu_verifikasi"
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO bookings (barber_id, tanggal, jam_mulai, jam_selesai, customer_nama, "
            "customer_whatsapp, total_harga, total_durasi_menit, metode_pembayaran, "
            "status_pembayaran, status_booking, catatan, created_at, tenant_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aktif', ?, ?, ?)",
            (barber_id, tanggal, jam_mulai, jam_selesai, customer_nama.strip(),
             customer_whatsapp.strip(), total_harga, total_durasi, metode_pembayaran,
             status_pembayaran_awal, (catatan or "").strip() or None, now, tenant_id),
        )
        booking_id = cur.lastrowid
        for s in items:
            conn.execute(
                "INSERT INTO booking_items (booking_id, service_id, nama_service, harga, durasi_menit) "
                "VALUES (?, ?, ?, ?, ?)",
                (booking_id, s["id"], s["nama"], s["harga"], int(s.get("durasi_menit") or 60)),
            )
    booking_baru = get_booking(booking_id)
    # FITUR Notifikasi WhatsApp Otomatis Booking: HANYA metode "qris" (QRIS
    # offline yang di-upload Owner, customer scan sendiri) yang butuh
    # reminder segera bayar -- metode lain (cash/transfer dibayar langsung
    # di tempat/rekening, "gateway" dapat pesan sendiri lewat
    # verifikasi_pembayaran() begitu Faspay konfirmasi sukses).
    if metode_pembayaran == "qris":
        _kirim_notifikasi_wa_booking(booking_baru, "reminder_qris")
    _kirim_notifikasi_push_booking_baru(booking_baru)
    return booking_baru


def _perkaya_status_gateway(booking: dict):
    """Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant:
    tambahkan field gateway_status/gateway_channel/gateway_transaction_id/
    gateway_reference_id/gateway_paid_at dari transaksi Payment Gateway
    TERBARU milik booking ini (null kalau bukan booking metode "gateway",
    atau belum ada percobaan checkout sama sekali) -- TIDAK mengubah kolom
    bookings.status_pembayaran yang sudah ada, murni field TAMBAHAN untuk
    tampilan status 7-state yang lebih rinci (Daftar/Detail Booking)."""
    booking["gateway_transaksi_id"] = None
    booking["gateway_status"] = None
    booking["gateway_channel"] = None
    booking["gateway_transaction_id"] = None
    booking["gateway_reference_id"] = None
    booking["gateway_paid_at"] = None
    if booking.get("metode_pembayaran") != "gateway":
        return
    transaksi = booking_gateway_db.get_transaksi_terkini_untuk_booking(booking["id"])
    if transaksi is None:
        return
    booking["gateway_transaksi_id"] = transaksi["id"]
    booking["gateway_status"] = transaksi["status_pembayaran"]
    booking["gateway_channel"] = transaksi["channel_pembayaran"]
    booking["gateway_transaction_id"] = transaksi["transaction_id_provider"]
    booking["gateway_reference_id"] = transaksi["reference_id_provider"]
    booking["gateway_paid_at"] = transaksi["paid_at"]


def get_booking(booking_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT bk.*, b.nama AS nama_barber FROM bookings bk "
            "JOIN barbers b ON b.id = bk.barber_id WHERE bk.id = ?",
            (booking_id,),
        ).fetchone()
        if row is None:
            return None
        booking = dict(row)
        items = conn.execute(
            "SELECT service_id, nama_service, harga, durasi_menit FROM booking_items WHERE booking_id = ?",
            (booking_id,),
        ).fetchall()
        booking["items"] = [dict(i) for i in items]
        booking["daftar_service"] = ", ".join(i["nama_service"] for i in items)
        _perkaya_status_gateway(booking)
        return booking


def get_booking_list(barber_id: int = None, tahun: int = None, bulan: int = None,
                      tanggal: str = None, dari_tanggal: str = None,
                      status_booking: str = None, tenant_id: int = None) -> list:
    q = """SELECT bk.*, b.nama AS nama_barber FROM bookings bk
           JOIN barbers b ON b.id = bk.barber_id WHERE 1=1"""
    params = []
    if barber_id is not None:
        q += " AND bk.barber_id = ?"; params.append(barber_id)
    if tenant_id is not None:
        q += " AND bk.tenant_id = ?"; params.append(tenant_id)
    if tahun is not None:
        q += " AND bk.tanggal LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND bk.tanggal LIKE ?"; params.append(f"%-{bulan:02d}-%")
    if tanggal is not None:
        q += " AND bk.tanggal = ?"; params.append(tanggal)
    # FITUR Booking "Akan Datang" (tampilan kartu operasional Barber, lihat
    # pages/booking.js): tanpa batas atas -- jumlah booking per barber wajar
    # untuk query terbuka ke depan, TIDAK butuh paginasi di tahap ini.
    if dari_tanggal is not None:
        q += " AND bk.tanggal >= ?"; params.append(dari_tanggal)
    if status_booking is not None:
        q += " AND bk.status_booking = ?"; params.append(status_booking)
    q += " ORDER BY bk.tanggal DESC, bk.jam_mulai DESC"
    with get_conn() as conn:
        headers = [dict(r) for r in conn.execute(q, params).fetchall()]
        if not headers:
            return []
        ids = [h["id"] for h in headers]
        placeholder = ", ".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT booking_id, nama_service FROM booking_items WHERE booking_id IN ({placeholder})",
            ids,
        ).fetchall()
        per_booking = {}
        for r in rows:
            per_booking.setdefault(r["booking_id"], []).append(r["nama_service"])
        transaksi_per_booking = booking_gateway_db.get_transaksi_terkini_untuk_booking_batch(ids)
        for h in headers:
            h["daftar_service"] = ", ".join(per_booking.get(h["id"], []))
            h["gateway_transaksi_id"] = None
            h["gateway_status"] = None
            h["gateway_channel"] = None
            h["gateway_transaction_id"] = None
            h["gateway_reference_id"] = None
            h["gateway_paid_at"] = None
            if h.get("metode_pembayaran") == "gateway":
                transaksi = transaksi_per_booking.get(h["id"])
                if transaksi is not None:
                    h["gateway_transaksi_id"] = transaksi["id"]
                    h["gateway_status"] = transaksi["status_pembayaran"]
                    h["gateway_channel"] = transaksi["channel_pembayaran"]
                    h["gateway_transaction_id"] = transaksi["transaction_id_provider"]
                    h["gateway_reference_id"] = transaksi["reference_id_provider"]
                    h["gateway_paid_at"] = transaksi["paid_at"]
        return headers


def hitung_booking_belum_dikonfirmasi(tenant_id: int = None) -> int:
    """REVISI: Notifikasi Booking Baru -- jumlah booking yang masih
    'menunggu_verifikasi' DAN belum dibatalkan (status_booking='aktif').
    Dipakai badge menu Booking + polling notifikasi suara di sisi Admin
    (Depends(require_admin) di router, HANYA Admin yang bisa
    verifikasi/batalkan booking -- lihat routers/booking.py)."""
    q = "SELECT COUNT(*) AS jumlah FROM bookings WHERE status_pembayaran = 'menunggu_verifikasi' AND status_booking = 'aktif'"
    params = []
    if tenant_id is not None:
        q += " AND tenant_id = ?"; params.append(tenant_id)
    with get_conn() as conn:
        row = conn.execute(q, params).fetchone()
        return row["jumlah"]


def batalkan_booking(booking_id: int):
    booking = get_booking(booking_id)
    if booking is None:
        raise ValueError("Booking tidak ditemukan.")
    # FITUR Notifikasi WhatsApp Otomatis Booking: cek status SEBELUM update
    # supaya panggilan berulang (klik dobel Admin, retry webhook Faspay
    # lewat _terapkan_status() di booking_gateway_webhook.py) TIDAK kirim
    # pesan pembatalan berkali-kali -- idempoten, pola sama seperti guard
    # transaksi_setelah["status_pembayaran"] != status_baru di sana.
    sudah_dibatalkan = booking["status_booking"] == "dibatalkan"
    with get_conn() as conn:
        conn.execute("UPDATE bookings SET status_booking = 'dibatalkan' WHERE id = ?", (booking_id,))
    if not sudah_dibatalkan:
        _kirim_notifikasi_wa_booking(get_booking(booking_id), "pembatalan")


def verifikasi_pembayaran(booking_id: int):
    booking = get_booking(booking_id)
    if booking is None:
        raise ValueError("Booking tidak ditemukan.")
    if booking["status_booking"] != "aktif":
        raise ValueError("Booking ini sudah dibatalkan.")
    # FITUR Notifikasi WhatsApp Otomatis Booking: pesan konfirmasi ini
    # SATU-SATUNYA yang mewakili DUA pemicu sekaligus -- Admin/Owner klik
    # "Verifikasi" manual (QRIS offline) MAUPUN webhook Faspay otomatis
    # (metode "gateway", lihat booking_gateway_webhook.py::_terapkan_status())
    # -- keduanya memanggil fungsi yang SAMA PERSIS ini. Guard idempoten
    # sama seperti batalkan_booking() di atas.
    sudah_terverifikasi = booking["status_pembayaran"] == "terverifikasi"
    with get_conn() as conn:
        conn.execute("UPDATE bookings SET status_pembayaran = 'terverifikasi' WHERE id = ?", (booking_id,))
    if not sudah_terverifikasi:
        _kirim_notifikasi_wa_booking(get_booking(booking_id), "konfirmasi_pembayaran")


def hapus_riwayat_booking(tenant_id: int, sebelum_tanggal: str = None) -> int:
    """FITUR Reset Riwayat Booking (mengantisipasi data menumpuk -- pola
    SAMA PERSIS seperti attendance_db.py::hapus_riwayat_absensi(), lihat
    routers/booking.py::hapus_riwayat()). HAPUS PERMANEN booking milik
    tenant ini beserta seluruh data turunannya (booking_items, riwayat
    transaksi Payment Gateway) -- TIDAK BISA dibatalkan.

    `sebelum_tanggal` opsional (format "YYYY-MM-DD"): kalau diisi, HANYA
    booking dengan tanggal < nilai itu yang dihapus (bersihkan riwayat
    lama, booking hari ini/mendatang tetap aman) -- kosong (None) = hapus
    SEMUA booking tenant ini tanpa terkecuali, sama seperti barber_id=None
    di hapus_riwayat_absensi().

    Urutan hapus WAJIB anak sebelum induk (booking_payment_status_log ->
    booking_payment_transactions -> booking_items -> bookings) supaya
    tidak ada baris yatim tersisa -- booking_payment_status_log TIDAK
    punya booking_id langsung (lihat postgres_schema.py), jadi dihapus
    lewat subquery transaction_id."""
    with get_conn() as conn:
        params = [tenant_id]
        filter_tanggal = ""
        if sebelum_tanggal is not None:
            filter_tanggal = " AND tanggal < ?"
            params.append(sebelum_tanggal)

        ids = [r["id"] for r in conn.execute(
            f"SELECT id FROM bookings WHERE tenant_id = ?{filter_tanggal}", params,
        ).fetchall()]
        if not ids:
            return 0
        placeholder = ", ".join("?" for _ in ids)

        conn.execute(
            f"DELETE FROM booking_payment_status_log WHERE transaction_id IN "
            f"(SELECT id FROM booking_payment_transactions WHERE booking_id IN ({placeholder}))",
            ids,
        )
        conn.execute(f"DELETE FROM booking_payment_transactions WHERE booking_id IN ({placeholder})", ids)
        conn.execute(f"DELETE FROM booking_items WHERE booking_id IN ({placeholder})", ids)
        conn.execute(f"DELETE FROM bookings WHERE id IN ({placeholder})", ids)
        return len(ids)


# ---------------------------------------------------------------------------
# BARBER & SERVICE -- field TAMBAHAN khusus tampilan Booking (status
# Active/On Vacation, foto, urutan). Kolom `nama`/`harga`/`aktif`/dst di
# tabel barbers/services TETAP dikelola lewat db.update_barber/
# update_service & pengaturan_barber.py/pengaturan_service.py yang SUDAH
# ADA -- fungsi di bawah ini HANYA menyentuh kolom baru milik modul
# Booking, lewat UPDATE langsung (pola sama seperti pengaturan_service.py
# set_modal()/set_durasi()), supaya tidak menduplikasi validasi yang
# sudah ada di db.update_barber/update_service.
# ---------------------------------------------------------------------------

STATUS_BOOKING_VALID = {"aktif", "cuti"}
FOTO_EXT_KE_CONTENT_TYPE = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def set_status_booking_barber(barber_id: int, status_booking: str):
    if db.get_barber(barber_id) is None:
        raise ValueError("Barber tidak ditemukan.")
    if status_booking not in STATUS_BOOKING_VALID:
        raise ValueError("Status tidak dikenal.")
    with get_conn() as conn:
        conn.execute("UPDATE barbers SET status_booking = ? WHERE id = ?", (status_booking, barber_id))


def set_urutan_barber(barber_id: int, urutan: int):
    if db.get_barber(barber_id) is None:
        raise ValueError("Barber tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("UPDATE barbers SET urutan = ? WHERE id = ?", (int(urutan), barber_id))


def simpan_foto_barber(barber_id: int, filename_asli: str, konten: bytes) -> str:
    if db.get_barber(barber_id) is None:
        raise ValueError("Barber tidak ditemukan.")
    nama_file, content_type = r2_storage.validasi_dan_beri_nama(
        filename_asli, konten, FOTO_EXT_KE_CONTENT_TYPE, "foto",
        maks_ukuran_bytes=r2_storage.MAKS_UKURAN_GAMBAR_BYTES)
    r2_key_lama = _ambil_foto_r2_key(barber_id)

    if r2_storage.IS_ENABLED:
        r2_key_baru = r2_storage.upload("barbers", nama_file, konten, content_type)
        data_kolom = None
    else:
        r2_key_baru = None
        data_kolom = konten

    with get_conn() as conn:
        conn.execute("UPDATE barbers SET foto_filename = ?, foto_data = ?, foto_r2_key = ? WHERE id = ?",
                      (nama_file, data_kolom, r2_key_baru, barber_id))

    if r2_key_lama and r2_key_lama != r2_key_baru:
        r2_storage.delete(r2_key_lama)
    return nama_file


def _ambil_foto_r2_key(barber_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT foto_r2_key FROM barbers WHERE id = ?", (barber_id,)).fetchone()
    return row["foto_r2_key"] if row else None


def hapus_foto_barber(barber_id: int):
    barber = db.get_barber(barber_id)
    if barber is None:
        raise ValueError("Barber tidak ditemukan.")
    r2_key = _ambil_foto_r2_key(barber_id)
    with get_conn() as conn:
        conn.execute("UPDATE barbers SET foto_filename = NULL, foto_data = NULL, foto_r2_key = NULL WHERE id = ?", (barber_id,))
    if r2_key:
        r2_storage.delete(r2_key)


def get_foto_barber_data(barber_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT foto_filename, foto_data, foto_r2_key FROM barbers WHERE id = ?", (barber_id,)).fetchone()
    if row is None or not row["foto_filename"]:
        return None, None
    ext = row["foto_filename"].rsplit(".", 1)[-1].lower()
    content_type = FOTO_EXT_KE_CONTENT_TYPE.get(ext, "application/octet-stream")
    if row["foto_r2_key"]:
        data, r2_content_type = r2_storage.get_bytes(row["foto_r2_key"])
        if data is not None:
            return data, r2_content_type or content_type
    if row["foto_data"] is not None:
        return bytes(row["foto_data"]), content_type
    return None, None


def set_urutan_service(service_id: int, urutan: int):
    if db.get_service(service_id) is None:
        raise ValueError("Layanan tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("UPDATE services SET urutan = ? WHERE id = ?", (int(urutan), service_id))
