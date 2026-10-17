"""
whatsapp_bot_db.py — FITUR WA Bot (Input Data & Rekap via WhatsApp, WhatsApp
Cloud API Meta)
=============================================================================
PERMINTAAN OWNER: barber/Owner bisa kirim pesan WhatsApp berisi input data
harian (mis. "Romen Dry Cut 3, Tips 30rb, Mifta libur...") atau minta rekap,
diproses otomatis jadi transaksi/libur di Rivoir -- lihat routers/
whatsapp_bot.py untuk webhook penerima pesannya.

ARSITEKTUR (keputusan Owner setelah diskusi panjang): SATU Meta App/WABA
("Rivoir") dipakai BERSAMA oleh SELURUH tenant -- BUKAN satu akun terpisah
per tenant (itu kendala khusus Twilio Sandbox yang cuma kasih 1 nomor per
akun; WhatsApp Cloud API produksi Meta MENDUKUNG banyak nomor telepon di
BAWAH SATU WABA/App yang sama, jadi tidak perlu akun terpisah-pisah).
Kredensial yang BENAR-BENAR platform-wide (Access Token System User,
Verify Token webhook) disimpan sebagai environment variable
(WHATSAPP_BOT_ACCESS_TOKEN/WHATSAPP_BOT_VERIFY_TOKEN, pola SAMA seperti
CRON_REMINDER_SECRET di routers/cron_reminder.py) -- TIDAK PERNAH disimpan
di database. Yang BEDA per tenant HANYA `phone_number_id` (nomor WA mana
yang dipakai tenant itu) + status aktif/nonaktif + kuota bulanan -- SEMUA
ini dikelola EKSKLUSIF oleh Superadmin (permintaan eksplisit Owner: "yang
memiliki hak untuk mengaktifkan atau mengatur Twilio/WA bot hanya
superadmin"), lihat routers/whatsapp_bot.py bagian endpoint
/api/superadmin/whatsapp-bot/*.

Webhook POST dari Meta MEMBAWA `phone_number_id` di payload (metadata) --
dari situ kita tahu pesan ini MILIK TENANT MANA (get_config_by_phone_number_id()
di bawah), tanpa Owner/Admin perlu setting URL unik per tenant sama sekali.

Kuota: SATU jatah pesan/bulan per tenant (kuota_pesan_bulanan, default 50,
Superadmin-editable per tenant) -- dihitung LIVE dari whatsapp_bot_pesan_log
bulan berjalan (pola SAMA seperti kuota_libur_db.py/izin_cuti_db.py: TIDAK
ADA kolom "sisa kuota" tersimpan/reset terjadwal, selalu dihitung ulang)."""

from datetime import datetime

from database import get_conn

DEFAULT_KUOTA_PESAN_BULANAN = 50


def init_whatsapp_bot_db():
    """JALUR SQLITE SAJA (dipanggil main.py on_startup(), idempotent) --
    jalur PostgreSQL: tabel yang SAMA dibuat di postgres_schema.py."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_bot_config (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id               INTEGER NOT NULL UNIQUE,
                phone_number_id         TEXT NOT NULL UNIQUE,
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
    milik tenant mana -- HANYA return config yang `aktif` (tenant yang
    dinonaktifkan Superadmin dianggap tidak ditemukan, pesan diabaikan)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM whatsapp_bot_config WHERE phone_number_id = ? AND aktif = 1",
            (phone_number_id,),
        ).fetchone()
    return _row_ke_dict(row) if row else None


def upsert_config(tenant_id: int, phone_number_id: str, nama_nomor: str = None,
                   kuota_pesan_bulanan: int = None, diatur_oleh: str = "") -> dict:
    """Superadmin daftarkan/ubah nomor WA Bot milik satu tenant. `aktif`
    SENGAJA TIDAK diisi di sini -- tenant baru SELALU mulai nonaktif,
    Superadmin menyalakannya eksplisit lewat set_aktif() (mencegah pesan
    masuk diproses sebelum Superadmin benar-benar siap)."""
    phone_number_id = (phone_number_id or "").strip()
    if not phone_number_id:
        raise ValueError("Phone Number ID wajib diisi.")
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
                   SET phone_number_id = ?, nama_nomor = ?, kuota_pesan_bulanan = ?,
                       diatur_oleh = ?, updated_at = ?
                   WHERE tenant_id = ?""",
                (phone_number_id, nama_nomor, kuota, diatur_oleh, now, tenant_id),
            )
        else:
            conn.execute(
                """INSERT INTO whatsapp_bot_config
                   (tenant_id, phone_number_id, nama_nomor, aktif, kuota_pesan_bulanan,
                    diatur_oleh, created_at, updated_at)
                   VALUES (?, ?, ?, 0, ?, ?, ?, ?)""",
                (tenant_id, phone_number_id, nama_nomor, kuota, diatur_oleh, now, now),
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
