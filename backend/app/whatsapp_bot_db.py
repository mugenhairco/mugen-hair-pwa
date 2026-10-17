"""
whatsapp_bot_db.py — FITUR WA Bot (Input Data & Rekap via WhatsApp, Fonnte)
=============================================================================
PERMINTAAN OWNER: barber/Owner bisa kirim pesan WhatsApp berisi input data
harian (mis. "Romen Dry Cut 3, Tips 30rb, Mifta libur...") atau minta rekap,
diproses otomatis jadi transaksi/libur di Rivoir -- lihat routers/
whatsapp_bot.py untuk webhook penerima pesannya.

ARSITEKTUR (GANTI PROVIDER -- awalnya dibangun di atas Meta WhatsApp Cloud
API, tapi proses Business Verification Meta terlalu berat untuk kebutuhan
internal sekecil ini (cuma segelintir barber input data/cek rekap, bukan
chat ke pelanggan umum), jadi Owner memutuskan pindah ke Fonnte -- provider
lokal Indonesia berbasis otomasi WhatsApp Web/QR-scan, setup jauh lebih
cepat, tanpa verifikasi bisnis). BEDA PENTING dari arsitektur Meta: Fonnte
TIDAK PUNYA konsep "satu token platform-wide untuk banyak nomor" --
SETIAP nomor/device Fonnte PUNYA token API SENDIRI-SENDIRI (dari dashboard
Fonnte, menu device). Jadi `device_token` DISIMPAN PER TENANT di database
(kolom di bawah), BUKAN sebagai environment variable platform-wide seperti
sebelumnya. Yang TETAP jadi environment variable platform-wide HANYA
`WHATSAPP_BOT_WEBHOOK_SECRET` (pola SAMA seperti CRON_REMINDER_SECRET di
routers/cron_reminder.py) -- dipakai memvalidasi bahwa POST ke webhook
memang berasal dari URL yang didaftarkan sendiri (Fonnte tidak punya
handshake verifikasi semacam punya Meta, cuma POST langsung ke URL yang
diisi di dashboard device->edit->webhook).

Kolom `phone_number_id` (nama kolom dipertahankan apa adanya dari versi
Meta supaya tidak perlu migrasi rename) sekarang BERISI nomor WA device
Fonnte itu sendiri (nomor bot-nya sendiri, BUKAN nomor pengirim) -- field
`device` di payload webhook Fonnte berisi nomor yang sama, dari situ kita
tahu pesan masuk ini MILIK TENANT MANA (get_config_by_phone_number_id() di
bawah), tanpa Owner/Admin perlu setting URL webhook unik per tenant.

Status aktif/nonaktif + kuota bulanan + device_token SEMUA dikelola
EKSKLUSIF oleh Superadmin (permintaan eksplisit Owner: "yang memiliki hak
untuk mengaktifkan atau mengatur WA bot hanya superadmin"), lihat
routers/whatsapp_bot.py bagian endpoint /api/superadmin/whatsapp-bot/*.

Kuota: SATU jatah pesan/bulan per tenant (kuota_pesan_bulanan, default 50,
Superadmin-editable per tenant) -- dihitung LIVE dari whatsapp_bot_pesan_log
bulan berjalan (pola SAMA seperti kuota_libur_db.py/izin_cuti_db.py: TIDAK
ADA kolom "sisa kuota" tersimpan/reset terjadwal, selalu dihitung ulang)."""

import json
from datetime import datetime, timedelta

from database import get_conn

DEFAULT_KUOTA_PESAN_BULANAN = 50

# Jendela anti-dobel (idempotency) -- webhook Fonnte yang terkirim ulang
# (retry jaringan dsb) untuk pesan yang PERSIS SAMA dari pengirim yang
# SAMA dalam rentang waktu ini dianggap duplikat, diabaikan (lihat
# pesan_duplikat() di bawah, dipanggil routers/whatsapp_bot.py SEBELUM
# whatsapp_bot_parser.proses_pesan()). Pola SAMA seperti idempotensi
# absensi_reminder_db.py, cuma di sini dicek dari whatsapp_bot_pesan_log
# yang sudah ada (tidak perlu tabel baru).
_JENDELA_DUPLIKAT_DETIK = 120

# Konfirmasi input (preview -> YA/BATAL) kedaluwarsa setelah ini -- pesan
# baru yang tidak nyambung ke pending lama (atau balasan YA/BATAL yang
# datang telat) tidak akan "nyangkut" ke konfirmasi basi.
_JENDELA_PENDING_DETIK = 600


def init_whatsapp_bot_db():
    """JALUR SQLITE SAJA (dipanggil main.py on_startup(), idempotent) --
    jalur PostgreSQL: tabel yang SAMA dibuat di postgres_schema.py."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_bot_config (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id               INTEGER NOT NULL UNIQUE,
                phone_number_id         TEXT NOT NULL UNIQUE,
                device_token            TEXT,
                nomor_owner_whatsapp    TEXT,
                nama_nomor              TEXT,
                aktif                   INTEGER NOT NULL DEFAULT 0,
                kuota_pesan_bulanan     INTEGER NOT NULL DEFAULT 50,
                diatur_oleh             TEXT,
                created_at              TEXT NOT NULL,
                updated_at              TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_bot_pesan_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       INTEGER NOT NULL,
                wa_id_pengirim  TEXT NOT NULL,
                isi_pesan       TEXT,
                status          TEXT NOT NULL,
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_bot_pesan_log_tenant_id "
                      "ON whatsapp_bot_pesan_log(tenant_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_bot_pending_input (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       INTEGER NOT NULL,
                wa_id_pengirim  TEXT NOT NULL,
                jenis           TEXT NOT NULL,
                payload         TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                UNIQUE(tenant_id, wa_id_pengirim)
            )
        """)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_ke_dict(row) -> dict:
    hasil = dict(row)
    hasil["aktif"] = bool(hasil["aktif"])
    return hasil


def list_config() -> list:
    """Dipakai Superadmin -- daftar config SEMUA tenant yang sudah pernah
    diatur (tenant yang belum pernah diatur TIDAK muncul di sini, lihat
    routers/whatsapp_bot.py yang menggabungnya dengan daftar tenant penuh)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM whatsapp_bot_config ORDER BY id").fetchall()
    return [_row_ke_dict(r) for r in rows]


def get_config(tenant_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM whatsapp_bot_config WHERE tenant_id = ?",
                            (tenant_id,)).fetchone()
    return _row_ke_dict(row) if row else None


def get_config_by_phone_number_id(phone_number_id: str) -> dict | None:
    """Dipakai webhook (routers/whatsapp_bot.py) untuk tahu pesan masuk ini
    milik tenant mana -- `phone_number_id` di sini adalah nomor device
    Fonnte (field `device` di payload webhook), BUKAN lagi Phone Number ID
    Meta. HANYA return config yang `aktif` (tenant yang dinonaktifkan
    Superadmin dianggap tidak ditemukan, pesan diabaikan)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM whatsapp_bot_config WHERE phone_number_id = ? AND aktif = 1",
            (phone_number_id,),
        ).fetchone()
    return _row_ke_dict(row) if row else None


def upsert_config(tenant_id: int, phone_number_id: str, device_token: str, nama_nomor: str = None,
                   kuota_pesan_bulanan: int = None, diatur_oleh: str = "",
                   nomor_owner_whatsapp: str = None) -> dict:
    """Superadmin daftarkan/ubah nomor+token WA Bot milik satu tenant.
    `device_token` WAJIB diisi (beda dari arsitektur Meta lama -- Fonnte
    tidak punya token platform-wide, setiap device token-nya sendiri,
    lihat docstring modul). `nomor_owner_whatsapp` OPSIONAL -- tenant bisa
    jalan tanpa ini diisi (artinya belum ada nomor yang setara akses Owner
    lewat WA, cuma barber yang bisa pakai command self-only), lihat
    whatsapp_bot_parser.py::resolve_role(). `aktif` SENGAJA TIDAK diisi di
    sini -- tenant baru SELALU mulai nonaktif, Superadmin menyalakannya
    eksplisit lewat set_aktif() (mencegah pesan masuk diproses sebelum
    Superadmin benar-benar siap)."""
    phone_number_id = (phone_number_id or "").strip()
    if not phone_number_id:
        raise ValueError("Nomor device Fonnte wajib diisi.")
    device_token = (device_token or "").strip()
    if not device_token:
        raise ValueError("Device Token Fonnte wajib diisi.")
    nomor_owner_whatsapp = (nomor_owner_whatsapp or "").strip() or None
    kuota = DEFAULT_KUOTA_PESAN_BULANAN if kuota_pesan_bulanan is None else int(kuota_pesan_bulanan)
    if kuota < 0:
        raise ValueError("Kuota pesan tidak boleh negatif.")
    now = _now_iso()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM whatsapp_bot_config WHERE tenant_id = ?",
                                 (tenant_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE whatsapp_bot_config
                   SET phone_number_id = ?, device_token = ?, nomor_owner_whatsapp = ?, nama_nomor = ?,
                       kuota_pesan_bulanan = ?, diatur_oleh = ?, updated_at = ?
                   WHERE tenant_id = ?""",
                (phone_number_id, device_token, nomor_owner_whatsapp, nama_nomor, kuota, diatur_oleh,
                 now, tenant_id),
            )
        else:
            conn.execute(
                """INSERT INTO whatsapp_bot_config
                   (tenant_id, phone_number_id, device_token, nomor_owner_whatsapp, nama_nomor, aktif,
                    kuota_pesan_bulanan, diatur_oleh, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
                (tenant_id, phone_number_id, device_token, nomor_owner_whatsapp, nama_nomor, kuota,
                 diatur_oleh, now, now),
            )
    return get_config(tenant_id)


def set_aktif(tenant_id: int, aktif: bool, diatur_oleh: str = "") -> dict:
    existing = get_config(tenant_id)
    if existing is None:
        raise ValueError("Tenant ini belum punya konfigurasi WA Bot -- daftarkan Phone Number ID dulu.")
    with get_conn() as conn:
        conn.execute(
            "UPDATE whatsapp_bot_config SET aktif = ?, diatur_oleh = ?, updated_at = ? WHERE tenant_id = ?",
            (1 if aktif else 0, diatur_oleh, _now_iso(), tenant_id),
        )
    return get_config(tenant_id)


def hapus_config(tenant_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM whatsapp_bot_config WHERE tenant_id = ?", (tenant_id,))


def catat_pesan(tenant_id: int, wa_id_pengirim: str, isi_pesan: str, status: str) -> None:
    """`status`: 'diproses' | 'ditolak_kuota' | 'ditolak_akses' | 'tidak_dikenali'
    -- murni log/audit trail, SEKALIGUS sumber hitung kuota bulan berjalan
    (lihat kuota_terpakai_bulan_ini() di bawah, pola SAMA seperti
    kuota_libur_db.py: tidak ada kolom counter terpisah, selalu dihitung
    ulang dari baris yang ada)."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO whatsapp_bot_pesan_log (tenant_id, wa_id_pengirim, isi_pesan, status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (tenant_id, wa_id_pengirim, isi_pesan, status, _now_iso()),
        )


def kuota_terpakai_bulan_ini(tenant_id: int) -> int:
    bulan_ini = datetime.now().strftime("%Y-%m")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM whatsapp_bot_pesan_log "
            "WHERE tenant_id = ? AND status = 'diproses' AND created_at LIKE ?",
            (tenant_id, f"{bulan_ini}%"),
        ).fetchone()
    return row["jumlah"]


def cek_kuota(tenant_id: int) -> dict:
    """Return {"kuota": int, "terpakai": int, "sisa": int, "habis": bool} --
    dipakai webhook SEBELUM memproses pesan masuk (lihat routers/
    whatsapp_bot.py)."""
    config = get_config(tenant_id)
    kuota = config["kuota_pesan_bulanan"] if config else DEFAULT_KUOTA_PESAN_BULANAN
    terpakai = kuota_terpakai_bulan_ini(tenant_id)
    sisa = max(0, kuota - terpakai)
    return {"kuota": kuota, "terpakai": terpakai, "sisa": sisa, "habis": terpakai >= kuota}


def pesan_duplikat(tenant_id: int, wa_id_pengirim: str, isi_pesan: str) -> bool:
    """True kalau pesan PERSIS SAMA (tenant+pengirim+isi) sudah tercatat di
    whatsapp_bot_pesan_log dalam _JENDELA_DUPLIKAT_DETIK terakhir --
    dipanggil routers/whatsapp_bot.py SEBELUM whatsapp_bot_parser.
    proses_pesan(), supaya webhook yang terkirim ulang (retry jaringan
    Fonnte dsb) tidak diproses dua kali (lihat catatan modul: ini
    SANGAT PENTING untuk command yang MENULIS data, bukan cuma baca)."""
    batas = (datetime.now() - timedelta(seconds=_JENDELA_DUPLIKAT_DETIK)).isoformat(timespec="seconds")
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS jumlah FROM whatsapp_bot_pesan_log
               WHERE tenant_id = ? AND wa_id_pengirim = ? AND isi_pesan = ? AND created_at >= ?""",
            (tenant_id, wa_id_pengirim, isi_pesan, batas),
        ).fetchone()
    return row["jumlah"] > 0


# ---------------------------------------------------------------------------
# Konfirmasi input tertunda (preview -> YA/BATAL, lihat whatsapp_bot_parser.py)
# -- SATU baris per (tenant_id, wa_id_pengirim), upsert (pesan input BARU
# dari pengirim yang sama otomatis MENIMPA/membatalkan pending lama -- tidak
# ada cara pending "nyangkut" ganda).
# ---------------------------------------------------------------------------

def simpan_pending(tenant_id: int, wa_id_pengirim: str, jenis: str, payload: dict) -> None:
    now = _now_iso()
    payload_json = json.dumps(payload, ensure_ascii=False)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM whatsapp_bot_pending_input WHERE tenant_id = ? AND wa_id_pengirim = ?",
            (tenant_id, wa_id_pengirim),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE whatsapp_bot_pending_input SET jenis = ?, payload = ?, created_at = ? WHERE id = ?",
                (jenis, payload_json, now, existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO whatsapp_bot_pending_input (tenant_id, wa_id_pengirim, jenis, payload, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (tenant_id, wa_id_pengirim, jenis, payload_json, now),
            )


def ambil_pending(tenant_id: int, wa_id_pengirim: str) -> dict | None:
    """Return {"jenis": str, "payload": dict} atau None kalau tidak ada
    atau sudah kedaluwarsa (> _JENDELA_PENDING_DETIK sejak disimpan) --
    pending yang sudah kedaluwarsa SEKALIGUS dihapus di sini (tidak perlu
    cron/job terpisah, cukup dibersihkan saat dibaca)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM whatsapp_bot_pending_input WHERE tenant_id = ? AND wa_id_pengirim = ?",
            (tenant_id, wa_id_pengirim),
        ).fetchone()
        if row is None:
            return None
        umur = (datetime.now() - datetime.fromisoformat(row["created_at"])).total_seconds()
        if umur > _JENDELA_PENDING_DETIK:
            conn.execute("DELETE FROM whatsapp_bot_pending_input WHERE id = ?", (row["id"],))
            return None
        return {"jenis": row["jenis"], "payload": json.loads(row["payload"])}


def hapus_pending(tenant_id: int, wa_id_pengirim: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM whatsapp_bot_pending_input WHERE tenant_id = ? AND wa_id_pengirim = ?",
            (tenant_id, wa_id_pengirim),
        )
