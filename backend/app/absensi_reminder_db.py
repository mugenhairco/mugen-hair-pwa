"""absensi_reminder_db.py — FITUR Reminder Absensi via WhatsApp
=============================================================================
PERMINTAAN Owner: barber yang lupa Check In/Check Out diingatkan otomatis
lewat WhatsApp (nomor TOKO, token Fonnte yang sama dengan Notifikasi WhatsApp
Booking -- lihat whatsapp_service.py) -- dikirim KE nomor WhatsApp PRIBADI
barber (barbers.nomor_whatsapp, lihat karyawan_migrasi.py), BUKAN sebaliknya.

TRIGGER WAKTU (bukan event user) -- BEDA dari pola event-driven lain di
aplikasi ini (push notifikasi booking dkk): "jam operasional toko sudah
mulai tapi barber belum Check In" dan "sudah 1 jam lewat jam tutup tapi
barber belum Check Out" TIDAK bisa diketahui dari reaksi atas suatu aksi,
HARUS dicek berbasis waktu. Mengikuti keputusan eksplisit Owner (TIDAK ada
proses berjalan terus-menerus di server/background scheduler, lihat
riwayat penghapusan auto_libur_db.py), pengecekan ini TIDAK dijalankan oleh
proses di dalam aplikasi sendiri -- jalankan_pengecekan() di bawah HANYA
dipanggil dari endpoint HTTP (lihat routers/cron_reminder.py) yang dipicu
layanan penjadwal GRATIS dari LUAR (mis. cron-job.org) setiap beberapa
menit. Server TETAP bisa tidur seperti biasa di luar jadwal itu -- setiap
panggilan hanya query singkat + kirim WA, tidak ada state yang disimpan di
memori proses.

IDEMPOTEN: tabel absensi_reminder_log mencatat SATU baris per (barber,
tanggal, jenis) -- walau endpoint pemicu dipanggil berkali-kali dalam
jendela waktu yang sama, SATU barber HANYA menerima SATU pesan per jenis
per hari (lihat _sudah_diingatkan()/_catat_pengingat()).

DIKECUALIKAN dari pengingat (PERMINTAAN Owner): barber yang sedang
Libur/Cuti/Izin pada tanggal itu (lihat _barber_sedang_libur_cuti_izin()),
dan barber yang belum mengisi nomor WhatsApp pribadinya sama sekali.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import attendance_db
import booking_db
import database as db
import feature_access
import pengaturan_identitas
import tenant_db
import whatsapp_service
from database import get_conn

WIB = ZoneInfo("Asia/Jakarta")

SETTING_AKTIF_KEY = "absensi_reminder_aktif"
TEMPLATE_SETTING_KEYS = {
    "checkin": "absensi_reminder_template_checkin",
    "checkout": "absensi_reminder_template_checkout",
}

# (jenis, label, deskripsi) -- dipakai frontend (menu WhatsApp > tab
# Reminder Absensi) menyusun textarea per jenis pesan, pola SAMA PERSIS
# whatsapp_templates.JENIS_PESAN (TIDAK memakai modul itu langsung --
# bentuk pesannya beda total, lihat catatan modul).
JENIS_PESAN = [
    ("checkin", "Pengingat Check In",
     "Dikirim SEKALI saat jam operasional toko sudah mulai tapi barber belum Check In hari itu."),
    ("checkout", "Pengingat Check Out",
     "Dikirim SEKALI saat sudah 1 jam lewat dari jam tutup toko tapi barber belum Check Out hari itu."),
]

PLACEHOLDER_INFO = [
    ("{nama_barber}", "Nama barber"),
    ("{toko}", "Nama barbershop"),
    ("{jam_buka}", "Jam buka toko"),
    ("{jam_tutup}", "Jam tutup toko"),
    ("{tanggal}", "Tanggal hari ini"),
]

DEFAULT_TEMPLATES = {
    "checkin": (
        "Halo {nama_barber}, jam operasional *{toko}* sudah dimulai sejak pukul {jam_buka} tapi Anda belum "
        "Check In. Mohon segera Check In lewat aplikasi."
    ),
    "checkout": (
        "Halo {nama_barber}, *{toko}* sudah tutup sejak pukul {jam_tutup} tapi Anda belum Check Out. "
        "Mohon segera Check Out lewat aplikasi."
    ),
}


def _sekarang_wib() -> datetime:
    return datetime.now(WIB)


def _hari_ini_wib() -> str:
    return _sekarang_wib().strftime("%Y-%m-%d")


def _gabung_jam(tanggal: str, jam_hhmm: str) -> datetime:
    jam, menit = (jam_hhmm or "00:00").split(":")[:2]
    tahun, bulan, hari = (int(x) for x in tanggal.split("-"))
    return datetime(tahun, bulan, hari, int(jam), int(menit), tzinfo=WIB)


def init_absensi_reminder_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS absensi_reminder_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id   INTEGER NOT NULL,
                barber_id   INTEGER NOT NULL,
                tanggal     TEXT NOT NULL,
                jenis       TEXT NOT NULL,
                dikirim_at  TEXT NOT NULL,
                UNIQUE(barber_id, tanggal, jenis)
            )
        """)


# ---------------------------------------------------------------------------
# Pengaturan per tenant (aktif/nonaktif + isi pesan) -- pola SAMA PERSIS
# whatsapp_service.py (settings generik lewat database.py), modul TERPISAH
# sengaja (lihat catatan atas file).
# ---------------------------------------------------------------------------

def get_aktif(tenant_id: int) -> bool:
    return db.get_setting(SETTING_AKTIF_KEY, "0", tenant_id=tenant_id) == "1"


def set_aktif(aktif: bool, tenant_id: int):
    db.set_setting(SETTING_AKTIF_KEY, "1" if aktif else "0", tenant_id=tenant_id)


def get_templates(tenant_id: int) -> dict:
    return {jenis: (db.get_setting(key, "", tenant_id=tenant_id) or "")
            for jenis, key in TEMPLATE_SETTING_KEYS.items()}


def set_templates(templates: dict, tenant_id: int):
    tidak_dikenal = set(templates.keys()) - set(TEMPLATE_SETTING_KEYS.keys())
    if tidak_dikenal:
        raise ValueError(f"Jenis pesan tidak dikenal: {', '.join(sorted(tidak_dikenal))}")
    for jenis, teks in templates.items():
        db.set_setting(TEMPLATE_SETTING_KEYS[jenis], (teks or "").strip(), tenant_id=tenant_id)


def render(jenis: str, nilai: dict, template_text: str = None) -> str:
    """Substitusi lewat str.replace() manual (BUKAN str.format()), pola SAMA
    whatsapp_templates.render() -- teks custom Owner yang kebetulan berisi
    kurung kurawal liar/typo placeholder TIDAK PERNAH menggagalkan
    pengiriman."""
    teks = (template_text or "").strip() or DEFAULT_TEMPLATES[jenis]
    for key, val in nilai.items():
        teks = teks.replace("{" + key + "}", str(val))
    return teks


# ---------------------------------------------------------------------------
# Idempotensi: SATU baris per (barber, tanggal, jenis)
# ---------------------------------------------------------------------------

def _sudah_diingatkan(barber_id: int, tanggal: str, jenis: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM absensi_reminder_log WHERE barber_id = ? AND tanggal = ? AND jenis = ?",
            (barber_id, tanggal, jenis),
        ).fetchone()
        return row is not None


def _catat_pengingat(tenant_id: int, barber_id: int, tanggal: str, jenis: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO absensi_reminder_log (tenant_id, barber_id, tanggal, jenis, dikirim_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(barber_id, tanggal, jenis) DO NOTHING",
            (tenant_id, barber_id, tanggal, jenis, _sekarang_wib().isoformat()),
        )


def _barber_sedang_libur_cuti_izin(barber_id: int, tanggal: str) -> bool:
    """PERMINTAAN Owner: barber Libur (Tandai Libur manual/mingguan, lihat
    booking_db.is_barber_libur() -- SUDAH menangani override "sudah Check
    In" untuk shift tukar dadakan) ATAU sedang Cuti/Izin yang DISETUJUI
    (tabel izin_cuti, terpisah dari absensi_libur -- lihat izin_cuti_db.py)
    pada tanggal ini DIKECUALIKAN total dari pengingat."""
    if booking_db.is_barber_libur(barber_id, tanggal):
        return True
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM izin_cuti WHERE barber_id = ? AND status = 'disetujui' "
            "AND jenis IN ('izin', 'cuti') AND tanggal_mulai <= ? AND tanggal_selesai >= ?",
            (barber_id, tanggal, tanggal),
        ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Pemicu utama -- dipanggil endpoint cron eksternal (routers/cron_reminder.py)
# ---------------------------------------------------------------------------

def jalankan_pengecekan() -> dict:
    """Loop SELURUH tenant AKTIF yang mengaktifkan fitur ini, kirim
    pengingat WA Check In (begitu jam buka toko lewat) / Check Out (begitu
    1 jam lewat jam tutup toko) ke barber yang belum melakukannya HARI INI
    -- lihat catatan modul untuk aturan pengecualian & idempotensi.
    Mengembalikan ringkasan jumlah (untuk log/debug endpoint pemicu)."""
    sekarang = _sekarang_wib()
    tanggal = sekarang.strftime("%Y-%m-%d")
    hari_ini_nama = booking_db.HARI_LIST[sekarang.weekday()]
    ringkasan = {"tenant_diperiksa": 0, "checkin_terkirim": 0, "checkout_terkirim": 0}

    for tenant in tenant_db.list_tenants():
        tenant_id = tenant["id"]
        if tenant.get("status") != "aktif":
            continue
        if not feature_access.tenant_has_feature(tenant_id, "absensi"):
            continue
        if not get_aktif(tenant_id):
            continue

        pengaturan = booking_db.get_booking_settings(tenant_id=tenant_id)
        if hari_ini_nama not in pengaturan["hari_operasional"]:
            continue
        jam_buka, jam_tutup = pengaturan["jam_buka"], pengaturan["jam_tutup"]

        lewat_jam_buka = sekarang >= _gabung_jam(tanggal, jam_buka)
        batas_checkout = _gabung_jam(tanggal, jam_tutup) + timedelta(hours=1)
        lewat_batas_checkout = sekarang >= batas_checkout
        if not lewat_jam_buka and not lewat_batas_checkout:
            continue

        ringkasan["tenant_diperiksa"] += 1
        nama_toko = pengaturan_identitas.get_identitas(tenant_id=tenant_id).get("nama_barbershop") or "Kami"
        templates = get_templates(tenant_id)
        nilai_placeholder = {"toko": nama_toko, "jam_buka": jam_buka, "jam_tutup": jam_tutup, "tanggal": tanggal}

        for b in db.get_barbers(hanya_aktif=True, tenant_id=tenant_id):
            nomor = (b.get("nomor_whatsapp") or "").strip()
            if not nomor:
                continue
            if _barber_sedang_libur_cuti_izin(b["id"], tanggal):
                continue
            log = attendance_db.get_log_hari_ini(b["id"], tenant_id=tenant_id)
            nilai = {**nilai_placeholder, "nama_barber": b["nama"]}

            if (lewat_jam_buka and (log is None or not log.get("check_in_at"))
                    and not _sudah_diingatkan(b["id"], tanggal, "checkin")):
                pesan = render("checkin", nilai, templates.get("checkin"))
                if whatsapp_service.kirim_whatsapp(nomor, pesan, tenant_id=tenant_id):
                    _catat_pengingat(tenant_id, b["id"], tanggal, "checkin")
                    ringkasan["checkin_terkirim"] += 1

            if (lewat_batas_checkout and log is not None and log.get("check_in_at") and not log.get("check_out_at")
                    and not _sudah_diingatkan(b["id"], tanggal, "checkout")):
                pesan = render("checkout", nilai, templates.get("checkout"))
                if whatsapp_service.kirim_whatsapp(nomor, pesan, tenant_id=tenant_id):
                    _catat_pengingat(tenant_id, b["id"], tanggal, "checkout")
                    ringkasan["checkout_terkirim"] += 1

    return ringkasan
