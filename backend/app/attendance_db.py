"""
attendance_db.py — Modul BARU: Absensi (Check In/Check Out GPS Geofencing)
=============================================================================
Modul MANDIRI (berdiri sendiri) -- SENGAJA TIDAK terhubung ke izin_cuti.py
maupun absensi_libur (Barber Holiday, dipakai Booking) sama sekali, sesuai
keputusan eksplisit Owner ("Absensi berdiri sendiri"). Barber yang sedang
cuti/libur dan tidak check-in tetap tercatat "Tidak Check In" -- Owner
yang perlu menyilangkan datanya sendiri kalau diperlukan.

Tiga tabel (id murni milik modul ini):
- attendance_settings: SATU baris PER TENANT (konvensi "id = tenant_id",
  identik kas_saldo_awal/uang_kas_db.py -- lihat _pastikan_baris_settings()).
  Jam Masuk, Toleransi Masuk, Jam Pulang, Radius Absensi, Lokasi Toko.
- attendance_logs: SATU baris per barber PER HARI (UNIQUE(barber_id,
  tanggal)), dibuat pertama kali saat Check In, di-UPDATE saat Check Out.
  Kolom `status` = status WORKFLOW hari itu (lihat hitung_status_hari_ini())
  -- selalu DIHITUNG ULANG dari waktu server (WIB), TIDAK PERNAH dipercaya
  dari cache/frontend. Kolom `check_in_status` (tepat_waktu/terlambat)
  adalah klasifikasi ketepatan waktu SEKALI SAAT check-in, permanen,
  terpisah dari status workflow (lihat komentar hitung_status_hari_ini()
  untuk penjelasan kenapa dua kolom terpisah).
- attendance_audit_logs: APPEND-ONLY, satu baris per PERCOBAAN check-in/out
  (berhasil MAUPUN gagal) -- untuk investigasi Owner (lihat bagian ANTI
  FAKE GPS di spesifikasi). TIDAK PERNAH diedit/dihapus lewat aplikasi.

ANTI MANIPULASI WAKTU: seluruh perhitungan tanggal/jam "sekarang" di modul
ini memakai zona waktu Asia/Jakarta (WIB) dari SERVER (_sekarang_wib() di
bawah), pola yang sama seperti booking_db.py -- TIDAK PERNAH memakai jam/
tanggal yang dikirim dari perangkat client.

ANTI FAKE GPS (keputusan Owner: prioritaskan kelancaran Barber, longgarkan
sedikit -- BUKAN heuristik agresif): validasi KERAS di backend HANYA untuk
kondisi yang eksplisit diminta spesifikasi (lihat validasi_checkin()/
validasi_checkout() di bawah) -- akurasi GPS yang lemah/sinyal aneh dicatat
ke attendance_audit_logs untuk ditinjau Owner, TIDAK memblokir Barber
kecuali akurasinya benar-benar sangat buruk (> AKURASI_MAKSIMAL_METER).

Tabel baru murni milik modul ini -- init_attendance_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database import get_conn, get_barber

WIB = ZoneInfo("Asia/Jakarta")

# Akurasi GPS dalam meter -- lebih besar dari ini dianggap terlalu tidak
# presisi untuk dipercaya (ditolak). Sengaja LONGGAR (bukan 50-100m seperti
# rekomendasi awal) sesuai keputusan Owner supaya Barber dengan GPS HP biasa
# (bukan pasti indikasi Fake GPS) tidak terkunci dari Absensi.
AKURASI_MAKSIMAL_METER = 150

RADIUS_VALID = {100, 250, 500, 750, 1000}
CHECK_IN_STATUS_VALID = {"tepat_waktu", "terlambat"}
STATUS_HARI_INI_VALID = {"belum_check_in", "sedang_bekerja", "sudah_check_out",
                          "tidak_check_in", "tidak_check_out"}

DEFAULT_SETTINGS = {
    "jam_masuk": "09:00",
    "toleransi_menit": 15,
    "jam_pulang": "20:00",
    "radius_meter": 500,
    "lokasi_nama": "",
    "lokasi_latitude": None,
    "lokasi_longitude": None,
}


def init_attendance_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance_settings (
                id                INTEGER PRIMARY KEY,
                jam_masuk         TEXT NOT NULL DEFAULT '09:00',
                toleransi_menit   INTEGER NOT NULL DEFAULT 15,
                jam_pulang        TEXT NOT NULL DEFAULT '20:00',
                radius_meter      INTEGER NOT NULL DEFAULT 500,
                lokasi_nama       TEXT,
                lokasi_latitude   REAL,
                lokasi_longitude  REAL,
                updated_at        TEXT,
                tenant_id         INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id            INTEGER NOT NULL,
                tanggal              TEXT NOT NULL,
                check_in_at          TEXT,
                check_in_latitude    REAL,
                check_in_longitude   REAL,
                check_in_accuracy    REAL,
                check_in_speed       REAL,
                check_in_heading     REAL,
                check_in_jarak_meter REAL,
                check_in_status      TEXT,
                check_in_browser     TEXT,
                check_in_device      TEXT,
                check_in_ip          TEXT,
                check_out_at         TEXT,
                check_out_latitude   REAL,
                check_out_longitude  REAL,
                check_out_accuracy   REAL,
                check_out_speed      REAL,
                check_out_heading    REAL,
                check_out_jarak_meter REAL,
                check_out_browser    TEXT,
                check_out_device     TEXT,
                check_out_ip         TEXT,
                durasi_kerja_menit   INTEGER,
                created_at           TEXT NOT NULL,
                updated_at           TEXT,
                tenant_id            INTEGER,
                UNIQUE(barber_id, tanggal)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance_audit_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id    INTEGER,
                aksi         TEXT NOT NULL,
                sukses       INTEGER NOT NULL,
                alasan_gagal TEXT,
                waktu_server TEXT NOT NULL,
                latitude     REAL,
                longitude    REAL,
                accuracy     REAL,
                browser      TEXT,
                device       TEXT,
                ip_address   TEXT,
                tenant_id    INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_logs_tenant_tanggal ON attendance_logs(tenant_id, tanggal)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_logs_barber_id ON attendance_logs(barber_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_audit_logs_tenant_id ON attendance_audit_logs(tenant_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_audit_logs_barber_id ON attendance_audit_logs(barber_id)")


def _sekarang_wib() -> datetime:
    return datetime.now(WIB)


def _hari_ini_wib() -> str:
    return _sekarang_wib().strftime("%Y-%m-%d")


def _gabung_jam(tanggal: str, jam_hhmm: str) -> datetime:
    """Gabungkan tanggal (YYYY-MM-DD) + jam (HH:MM) jadi datetime ber-zona WIB."""
    jam, menit = (int(x) for x in jam_hhmm.split(":"))
    tgl = datetime.strptime(tanggal, "%Y-%m-%d")
    return datetime(tgl.year, tgl.month, tgl.day, jam, menit, tzinfo=WIB)


def haversine_meter(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Jarak antara dua titik koordinat (meter) memakai Haversine Formula --
    WAJIB dihitung ULANG di backend (spesifikasi ANTI FAKE GPS), tidak
    pernah mempercayai jarak dari frontend."""
    R = 6371000.0  # radius Bumi (meter)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(min(1, math.sqrt(a)))


# ---------------------------------------------------------------------------
# Pengaturan Absensi ("id = tenant_id", pola SAMA PERSIS uang_kas_db.py)
# ---------------------------------------------------------------------------

def _pastikan_baris_settings(conn, tenant_id: int):
    conn.execute(
        """INSERT INTO attendance_settings (id, jam_masuk, toleransi_menit, jam_pulang, radius_meter, tenant_id)
           VALUES (?, '09:00', 15, '20:00', 500, ?) ON CONFLICT DO NOTHING""",
        (tenant_id, tenant_id),
    )


def get_settings(tenant_id: int) -> dict:
    with get_conn() as conn:
        _pastikan_baris_settings(conn, tenant_id)
        row = conn.execute("SELECT * FROM attendance_settings WHERE id = ?", (tenant_id,)).fetchone()
        return dict(row) if row else {"id": tenant_id, **DEFAULT_SETTINGS, "tenant_id": tenant_id}


def set_settings(tenant_id: int, jam_masuk: str = None, toleransi_menit: int = None,
                  jam_pulang: str = None, radius_meter: int = None, lokasi_nama: str = None,
                  lokasi_latitude: float = None, lokasi_longitude: float = None) -> dict:
    existing = get_settings(tenant_id)
    jam_masuk_baru = jam_masuk if jam_masuk is not None else existing["jam_masuk"]
    jam_pulang_baru = jam_pulang if jam_pulang is not None else existing["jam_pulang"]
    for label, nilai in (("Jam Masuk", jam_masuk_baru), ("Jam Pulang", jam_pulang_baru)):
        try:
            jam, menit = (int(x) for x in nilai.split(":"))
            if not (0 <= jam <= 23 and 0 <= menit <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError(f"Format {label} tidak valid (harus HH:MM).")
    toleransi_baru = toleransi_menit if toleransi_menit is not None else existing["toleransi_menit"]
    if toleransi_baru is None or toleransi_baru < 0:
        raise ValueError("Toleransi Masuk tidak boleh negatif.")
    radius_baru = radius_meter if radius_meter is not None else existing["radius_meter"]
    if radius_baru not in RADIUS_VALID:
        raise ValueError(f"Radius Absensi tidak valid, pilih salah satu: {sorted(RADIUS_VALID)} meter.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        _pastikan_baris_settings(conn, tenant_id)
        fields, values = ["jam_masuk = ?", "toleransi_menit = ?", "jam_pulang = ?", "radius_meter = ?",
                           "updated_at = ?"], [jam_masuk_baru, int(toleransi_baru), jam_pulang_baru,
                                                int(radius_baru), now]
        if lokasi_nama is not None:
            fields.append("lokasi_nama = ?"); values.append(lokasi_nama.strip())
        if lokasi_latitude is not None:
            fields.append("lokasi_latitude = ?"); values.append(float(lokasi_latitude))
        if lokasi_longitude is not None:
            fields.append("lokasi_longitude = ?"); values.append(float(lokasi_longitude))
        values.append(tenant_id)
        conn.execute(f"UPDATE attendance_settings SET {', '.join(fields)} WHERE id = ?", values)
    return get_settings(tenant_id)


# ---------------------------------------------------------------------------
# Status hari ini -- SELALU dihitung ulang dari waktu server, TIDAK PERNAH
# disimpan sebagai kebenaran statis (supaya "Tidak Check In"/"Tidak Check
# Out" otomatis muncul begitu jam pulang lewat, tanpa perlu job terjadwal).
#
# CATATAN DESAIN: spesifikasi menyebut 7 nilai status (Belum Check In, Tepat
# Waktu, Terlambat, Sedang Bekerja, Sudah Check Out, Tidak Check In, Tidak
# Check Out). Di implementasi ini nilainya dipecah jadi DUA kolom ortogonal
# supaya konsisten sepanjang waktu: `status` (5 nilai, WORKFLOW hari itu --
# STATUS_HARI_INI_VALID di atas) + `check_in_status` (2 nilai, klasifikasi
# ketepatan waktu PERMANEN sejak momen check-in -- tepat_waktu/terlambat).
# Gabungan keduanya tetap mencakup ke-7 nilai spesifikasi (mis. "Terlambat,
# Sedang Bekerja" ditampilkan bersamaan di UI), tapi tidak ada nilai yang
# hilang begitu waktu berjalan (kalau "Tepat Waktu"/"Terlambat" jadi SATU
# status workflow yang berdiri sendiri, ia akan langsung tertimpa "Sedang
# Bekerja" pada request berikutnya -- nyaris tidak pernah terlihat).
# ---------------------------------------------------------------------------

def hitung_status_hari_ini(log: dict | None, settings: dict, sekarang: datetime = None) -> str:
    sekarang = sekarang or _sekarang_wib()
    tanggal = sekarang.strftime("%Y-%m-%d")
    jam_pulang_dt = _gabung_jam(tanggal, settings["jam_pulang"])
    if log is None or not log.get("check_in_at"):
        return "belum_check_in" if sekarang < jam_pulang_dt else "tidak_check_in"
    if log.get("check_out_at"):
        return "sudah_check_out"
    return "sedang_bekerja" if sekarang < jam_pulang_dt else "tidak_check_out"


def get_log_hari_ini(barber_id: int, tenant_id: int = None) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM attendance_logs WHERE barber_id = ? AND tanggal = ?",
            (barber_id, _hari_ini_wib()),
        ).fetchone()
        log = dict(row) if row else None
    if log is not None and tenant_id is not None and log.get("tenant_id") != tenant_id:
        return None
    return log


def _lengkapi(row: dict, settings: dict = None) -> dict:
    barber = get_barber(row["barber_id"])
    row["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    row["tenant_id"] = row.get("tenant_id") if row.get("tenant_id") is not None else (
        barber["tenant_id"] if barber else None)
    if settings is None and row.get("tenant_id") is not None:
        settings = get_settings(row["tenant_id"])
    if settings is not None:
        row["status"] = hitung_status_hari_ini(row, settings)
    return row


def get_log(log_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM attendance_logs WHERE id = ?", (log_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_log_list(tenant_id: int, tanggal: str = None, tanggal_dari: str = None, tanggal_sampai: str = None,
                  barber_id: int = None, status: str = None) -> list:
    """Daftar log absensi milik tenant, PLUS baris "semu" (belum ada log)
    untuk barber yang belum check-in sama sekali hari itu -- supaya
    Dashboard/Laporan bisa menampilkan "Tidak Check In" walau belum pernah
    ada baris attendance_logs untuk barber itu. Hanya berlaku untuk query
    SATU tanggal (tanggal= atau default hari ini) -- rentang tanggal
    (Laporan mingguan/bulanan) hanya menampilkan baris yang SUNGGUHAN ada."""
    settings = get_settings(tenant_id)
    q = "SELECT l.* FROM attendance_logs l JOIN barbers b ON b.id = l.barber_id WHERE b.tenant_id = ?"
    params = [tenant_id]
    if tanggal is not None:
        q += " AND l.tanggal = ?"; params.append(tanggal)
    if tanggal_dari is not None:
        q += " AND l.tanggal >= ?"; params.append(tanggal_dari)
    if tanggal_sampai is not None:
        q += " AND l.tanggal <= ?"; params.append(tanggal_sampai)
    if barber_id is not None:
        q += " AND l.barber_id = ?"; params.append(barber_id)
    q += " ORDER BY l.tanggal DESC, l.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    hasil = [_lengkapi(r, settings) for r in rows]

    tanggal_tunggal = tanggal or (_hari_ini_wib() if tanggal_dari is None and tanggal_sampai is None else None)
    if tanggal_tunggal is not None and barber_id is None:
        sudah_ada = {r["barber_id"] for r in hasil}
        with get_conn() as conn:
            aktif = [dict(r) for r in conn.execute(
                "SELECT id, nama FROM barbers WHERE tenant_id = ? AND aktif = 1", (tenant_id,)
            ).fetchall()]
        for b in aktif:
            if b["id"] in sudah_ada:
                continue
            semu = {
                "id": None, "barber_id": b["id"], "nama_barber": b["nama"], "tanggal": tanggal_tunggal,
                "check_in_at": None, "check_out_at": None, "check_in_status": None,
                "durasi_kerja_menit": None, "tenant_id": tenant_id,
            }
            semu["status"] = hitung_status_hari_ini(None, settings)
            hasil.append(semu)

    if status is not None:
        hasil = [r for r in hasil if r["status"] == status]
    return hasil


def get_ringkasan_dashboard(tenant_id: int) -> dict:
    """Kartu ringkasan Dashboard Owner/Admin -- Total Barber, Hadir, Belum
    Hadir, Terlambat, Sedang Bekerja, Sudah Check Out, Tidak Check In,
    Tidak Check Out."""
    daftar = get_log_list(tenant_id)
    total = len(daftar)
    hadir = sum(1 for r in daftar if r.get("check_in_at"))
    return {
        "total_barber": total,
        "hadir": hadir,
        "belum_hadir": total - hadir,
        "terlambat": sum(1 for r in daftar if r.get("check_in_status") == "terlambat"),
        "sedang_bekerja": sum(1 for r in daftar if r["status"] == "sedang_bekerja"),
        "sudah_check_out": sum(1 for r in daftar if r["status"] == "sudah_check_out"),
        "tidak_check_in": sum(1 for r in daftar if r["status"] == "tidak_check_in"),
        "tidak_check_out": sum(1 for r in daftar if r["status"] == "tidak_check_out"),
    }


# ---------------------------------------------------------------------------
# Audit log (append-only)
# ---------------------------------------------------------------------------

def catat_audit(barber_id: int, aksi: str, sukses: bool, alasan_gagal: str = None,
                 latitude: float = None, longitude: float = None, accuracy: float = None,
                 browser: str = None, device: str = None, ip_address: str = None,
                 tenant_id: int = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO attendance_audit_logs
                   (barber_id, aksi, sukses, alasan_gagal, waktu_server, latitude, longitude, accuracy,
                    browser, device, ip_address, tenant_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (barber_id, aksi, 1 if sukses else 0, alasan_gagal, _sekarang_wib().isoformat(timespec="seconds"),
             latitude, longitude, accuracy, browser, device, ip_address, tenant_id),
        )


def get_audit_list(tenant_id: int, barber_id: int = None, tanggal_dari: str = None,
                    tanggal_sampai: str = None) -> list:
    q = "SELECT * FROM attendance_audit_logs WHERE tenant_id = ?"
    params = [tenant_id]
    if barber_id is not None:
        q += " AND barber_id = ?"; params.append(barber_id)
    if tanggal_dari is not None:
        q += " AND waktu_server >= ?"; params.append(tanggal_dari)
    if tanggal_sampai is not None:
        q += " AND waktu_server <= ?"; params.append(tanggal_sampai + "T23:59:59")
    q += " ORDER BY id DESC LIMIT 500"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    for r in rows:
        barber = get_barber(r["barber_id"]) if r["barber_id"] else None
        r["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    return rows


# ---------------------------------------------------------------------------
# Validasi (dipanggil dari routers/attendance.py, SEMUA logika di sini --
# "Semua validasi dilakukan di backend. Frontend hanya menampilkan hasil
# validasi.")
# ---------------------------------------------------------------------------

def _validasi_koordinat(latitude, longitude, accuracy):
    if latitude is None or longitude is None:
        raise ValueError("Data koordinat tidak lengkap. Pastikan GPS aktif dan izin lokasi diberikan.")
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise ValueError("Data koordinat tidak valid.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Data koordinat tidak valid.")
    if accuracy is not None and accuracy > AKURASI_MAKSIMAL_METER:
        raise ValueError("Lokasi tidak valid. Nonaktifkan Fake GPS atau Mock Location.")
    return latitude, longitude


def validasi_checkin(tenant_id: int, barber_id: int, latitude, longitude, accuracy=None):
    """Return (settings, jarak_meter, status_ketepatan) kalau valid, raise
    ValueError (pesan siap ditampilkan ke Barber) kalau tidak."""
    barber = get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber["tenant_id"] != tenant_id):
        raise ValueError("Barber tidak ditemukan.")
    settings = get_settings(tenant_id)
    if settings.get("lokasi_latitude") is None or settings.get("lokasi_longitude") is None:
        raise ValueError("Lokasi Toko belum diatur Owner. Hubungi Owner untuk mengatur Pengaturan Absensi.")
    latitude, longitude = _validasi_koordinat(latitude, longitude, accuracy)

    existing = get_log_hari_ini(barber_id, tenant_id)
    if existing is not None and existing.get("check_in_at"):
        raise ValueError("Anda sudah Check In hari ini.")

    sekarang = _sekarang_wib()
    tanggal = sekarang.strftime("%Y-%m-%d")
    jam_pulang_dt = _gabung_jam(tanggal, settings["jam_pulang"])
    if sekarang >= jam_pulang_dt:
        raise ValueError("Sudah melewati jam pulang. Tidak bisa Check In lagi hari ini.")

    jarak = haversine_meter(latitude, longitude, settings["lokasi_latitude"], settings["lokasi_longitude"])
    if jarak > settings["radius_meter"]:
        raise ValueError(f"Anda berada di luar radius absensi ({round(jarak)} meter dari toko, "
                          f"maksimal {settings['radius_meter']} meter).")

    batas_toleransi_dt = _gabung_jam(tanggal, settings["jam_masuk"]) + timedelta(minutes=settings["toleransi_menit"])
    status_ketepatan = "terlambat" if sekarang > batas_toleransi_dt else "tepat_waktu"
    return settings, jarak, status_ketepatan


def validasi_checkout(tenant_id: int, barber_id: int, latitude, longitude, accuracy=None):
    barber = get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber["tenant_id"] != tenant_id):
        raise ValueError("Barber tidak ditemukan.")
    settings = get_settings(tenant_id)
    latitude, longitude = _validasi_koordinat(latitude, longitude, accuracy)

    existing = get_log_hari_ini(barber_id, tenant_id)
    if existing is None or not existing.get("check_in_at"):
        raise ValueError("Anda belum Check In hari ini.")
    if existing.get("check_out_at"):
        raise ValueError("Anda sudah Check Out hari ini.")

    sekarang = _sekarang_wib()
    tanggal = sekarang.strftime("%Y-%m-%d")
    jam_pulang_dt = _gabung_jam(tanggal, settings["jam_pulang"])
    if sekarang < jam_pulang_dt:
        raise ValueError(f"Belum waktunya Check Out (jam pulang {settings['jam_pulang']}).")

    jarak = None
    if settings.get("lokasi_latitude") is not None and settings.get("lokasi_longitude") is not None:
        jarak = haversine_meter(latitude, longitude, settings["lokasi_latitude"], settings["lokasi_longitude"])
        if jarak > settings["radius_meter"]:
            raise ValueError(f"Anda berada di luar radius absensi ({round(jarak)} meter dari toko, "
                              f"maksimal {settings['radius_meter']} meter).")
    return settings, existing, jarak


def check_in(tenant_id: int, barber_id: int, latitude, longitude, accuracy=None, speed=None,
             heading=None, browser: str = None, device: str = None, ip_address: str = None) -> dict:
    settings, jarak, status_ketepatan = validasi_checkin(tenant_id, barber_id, latitude, longitude, accuracy)
    sekarang = _sekarang_wib()
    now_iso = sekarang.isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO attendance_logs
                   (barber_id, tanggal, check_in_at, check_in_latitude, check_in_longitude, check_in_accuracy,
                    check_in_speed, check_in_heading, check_in_jarak_meter, check_in_status, check_in_browser,
                    check_in_device, check_in_ip, created_at, tenant_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(barber_id, tanggal) DO UPDATE SET
                   check_in_at = excluded.check_in_at, check_in_latitude = excluded.check_in_latitude,
                   check_in_longitude = excluded.check_in_longitude, check_in_accuracy = excluded.check_in_accuracy,
                   check_in_speed = excluded.check_in_speed, check_in_heading = excluded.check_in_heading,
                   check_in_jarak_meter = excluded.check_in_jarak_meter, check_in_status = excluded.check_in_status,
                   check_in_browser = excluded.check_in_browser, check_in_device = excluded.check_in_device,
                   check_in_ip = excluded.check_in_ip""",
            (barber_id, sekarang.strftime("%Y-%m-%d"), now_iso, latitude, longitude, accuracy, speed, heading,
             jarak, status_ketepatan, browser, device, ip_address, now_iso, tenant_id),
        )
    catat_audit(barber_id, "check_in", True, latitude=latitude, longitude=longitude, accuracy=accuracy,
                browser=browser, device=device, ip_address=ip_address, tenant_id=tenant_id)
    return _lengkapi(get_log_hari_ini(barber_id, tenant_id), settings)


def check_out(tenant_id: int, barber_id: int, latitude, longitude, accuracy=None, speed=None,
              heading=None, browser: str = None, device: str = None, ip_address: str = None) -> dict:
    settings, existing, jarak = validasi_checkout(tenant_id, barber_id, latitude, longitude, accuracy)
    sekarang = _sekarang_wib()
    now_iso = sekarang.isoformat(timespec="seconds")
    check_in_at = datetime.fromisoformat(existing["check_in_at"])
    durasi_menit = int((sekarang - check_in_at).total_seconds() // 60)
    with get_conn() as conn:
        conn.execute(
            """UPDATE attendance_logs SET check_out_at = ?, check_out_latitude = ?, check_out_longitude = ?,
                   check_out_accuracy = ?, check_out_speed = ?, check_out_heading = ?, check_out_jarak_meter = ?,
                   check_out_browser = ?, check_out_device = ?, check_out_ip = ?, durasi_kerja_menit = ?,
                   updated_at = ? WHERE id = ?""",
            (now_iso, latitude, longitude, accuracy, speed, heading, jarak, browser, device, ip_address,
             durasi_menit, now_iso, existing["id"]),
        )
    catat_audit(barber_id, "check_out", True, latitude=latitude, longitude=longitude, accuracy=accuracy,
                browser=browser, device=device, ip_address=ip_address, tenant_id=tenant_id)
    return get_log(existing["id"])
