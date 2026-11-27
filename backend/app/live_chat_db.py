"""live_chat_db.py — FITUR BARU "Live Chat": Inbox WhatsApp customer terintegrasi
=============================================================================
BEDA dari whatsapp_service.py (token Fonnte tenant dipakai KHUSUS untuk
KIRIM pesan keluar -- reminder/konfirmasi booking) dan dari WA Bot yang
sudah DIHAPUS TOTAL (nomor terpisah, dikelola Superadmin, khusus perintah
Owner/Barber): modul ini memakai TOKEN FONNTE YANG SAMA milik tenant
(whatsapp_service.TOKEN_SETTING_KEY, diisi Owner lewat Setting > WhatsApp)
untuk fitur DUA ARAH dengan CUSTOMER -- pesan masuk dari customer otomatis
tersimpan di sini & memicu notifikasi push, Owner/Admin bisa membalas lewat
Rivoir (dikirim lewat whatsapp_service.kirim_whatsapp() yang sudah ada,
TIDAK ada jalur kirim baru).

Fonnte mengirim webhook pesan masuk ke URL yang Owner SENDIRI pasang di
dashboard Fonnte miliknya (self-service, Rivoir tidak bisa mengatur webhook
tenant dari jarak jauh) -- URL itu membawa SATU token acak PER TENANT
(`live_chat_config.webhook_token`, lihat get_or_create_webhook_token())
supaya endpoint publiknya (routers/live_chat.py) bisa mencari tenant_id
dari token tanpa perlu sesi login Rivoir, pola mirip webhook WA Bot lama
TAPI token di sini per-tenant (bukan satu secret global) karena Owner
sendiri yang mendaftarkan webhook-nya, bukan Superadmin terpusat.

Retensi otomatis (PERMINTAAN Owner, lihat routers/cron_live_chat_purge.py):
pesan TIDAK PERNAH dihapus selama belum pernah dibuka di Rivoir
(`dibuka_di_rivoir_at IS NULL`) -- begitu Owner/Admin membuka thread
kontak itu (tandai_dibuka()), SEMUA pesan di thread itu yang belum pernah
dibuka ditandai waktunya, lalu hapus_kedaluwarsa() yang dipanggil cron
terjadwal akan menghapus baris gambar >24 jam dan baris teks >7 hari
SEJAK waktu itu (BUKAN sejak pesan dibuat) -- "dibaca di aplikasi WhatsApp
asli" TIDAK dipakai sebagai pemicu (lihat diskusi fitur ini: dokumentasi
Fonnte mewajibkan autoread aktif supaya webhook jalan sama sekali, jadi
status "dibaca" di akun WhatsApp sudah tidak bisa dibedakan dari "pesan
baru masuk" -- sinyal itu tidak andal, sengaja tidak dipakai).

Tabel baru murni milik modul ini -- init_live_chat_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py."""

import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import r2_storage
from database import get_conn

# BUGFIX (laporan Owner: jam pesan di Live Chat ikut jam server, bukan jam
# lokal Indonesia): SEBELUMNYA modul ini pakai datetime.now() polos (naive,
# ikut jam sistem container Render yang UTC) -- frontend (pages/live_chat.js
# ::_formatWaktu()) mem-parsing string TANPA offset itu seolah SUDAH jam
# lokal browser (standar parsing JS Date), jadi tampil mundur ~7 jam dari WIB
# sungguhan. Pola yang BENAR (dipakai konsisten modul lain: attendance_db.py/
# booking_db.py/pos_db.py/dkk, lihat _sekarang_wib()): datetime SADAR ZONA
# (aware, bawa offset "+07:00" di isoformat()-nya) -- begitu offset itu ada,
# JS Date mem-parsingnya dengan BENAR sebagai instant absolut, baru dirender
# ke zona lokal browser lewat toLocaleTimeString().
WIB = ZoneInfo("Asia/Jakarta")


def _sekarang_wib() -> datetime:
    return datetime.now(WIB)


GAMBAR_EXT_KE_CONTENT_TYPE = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
}
MAKS_UKURAN_GAMBAR_BYTES = 10 * 1024 * 1024  # 10MB -- generos, WA sendiri kompres sebelum kirim

# PERMINTAAN Owner: gambar dihapus 24 jam, teks dihapus 7 hari -- SEJAK
# dibuka_di_rivoir_at (bukan sejak pesan dibuat), lihat docstring modul.
RETENSI_GAMBAR_JAM = 24
RETENSI_TEKS_HARI = 7


def init_live_chat_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_chat_config (
                tenant_id       INTEGER PRIMARY KEY,
                webhook_token   TEXT NOT NULL UNIQUE,
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_chat_pesan (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id            INTEGER NOT NULL,
                arah                 TEXT NOT NULL,   -- 'masuk' (dari customer) / 'keluar' (balasan Owner/Admin)
                nomor_wa             TEXT NOT NULL,
                nama_kontak          TEXT,
                jenis                TEXT NOT NULL,   -- 'teks' / 'gambar'
                isi_teks             TEXT,
                gambar_filename      TEXT,
                gambar_data          BLOB,
                gambar_r2_key        TEXT,
                gambar_content_type  TEXT,
                waktu                TEXT NOT NULL,
                dibuka_di_rivoir_at  TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_live_chat_pesan_tenant_waktu ON live_chat_pesan(tenant_id, waktu)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_live_chat_pesan_tenant_nomor ON live_chat_pesan(tenant_id, nomor_wa, waktu)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_live_chat_pesan_dibuka ON live_chat_pesan(dibuka_di_rivoir_at)")


# ---------------------------------------------------------------------------
# Webhook token (per tenant)
# ---------------------------------------------------------------------------

def get_or_create_webhook_token(tenant_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT webhook_token FROM live_chat_config WHERE tenant_id = ?", (tenant_id,)).fetchone()
        if row:
            return row["webhook_token"]
        token = secrets.token_urlsafe(24)
        conn.execute(
            "INSERT INTO live_chat_config (tenant_id, webhook_token, created_at) VALUES (?, ?, ?)",
            (tenant_id, token, _sekarang_wib().isoformat(timespec="seconds")),
        )
        return token


def regenerate_webhook_token(tenant_id: int) -> str:
    """Owner curiga URL webhook-nya bocor -- token lama otomatis berhenti
    berfungsi (get_tenant_by_webhook_token() tidak akan menemukannya lagi),
    Owner tinggal pasang ulang URL baru di dashboard Fonnte-nya."""
    token = secrets.token_urlsafe(24)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO live_chat_config (tenant_id, webhook_token, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(tenant_id) DO UPDATE SET webhook_token = excluded.webhook_token",
            (tenant_id, token, _sekarang_wib().isoformat(timespec="seconds")),
        )
    return token


def get_tenant_by_webhook_token(token: str):
    if not token:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT tenant_id FROM live_chat_config WHERE webhook_token = ?", (token,)).fetchone()
    return row["tenant_id"] if row else None


# ---------------------------------------------------------------------------
# Pesan
# ---------------------------------------------------------------------------

def simpan_pesan_teks_masuk(tenant_id: int, nomor_wa: str, nama_kontak: str, isi_teks: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO live_chat_pesan (tenant_id, arah, nomor_wa, nama_kontak, jenis, isi_teks, waktu) "
            "VALUES (?, 'masuk', ?, ?, 'teks', ?, ?)",
            (tenant_id, nomor_wa, nama_kontak, isi_teks, _sekarang_wib().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def simpan_pesan_gambar_masuk(tenant_id: int, nomor_wa: str, nama_kontak: str,
                               filename_asli: str, konten: bytes) -> int:
    nama_file, content_type = r2_storage.validasi_dan_beri_nama(
        filename_asli, konten, GAMBAR_EXT_KE_CONTENT_TYPE, "gambar",
        maks_ukuran_bytes=MAKS_UKURAN_GAMBAR_BYTES)
    if r2_storage.IS_ENABLED:
        r2_key = r2_storage.upload("live-chat", nama_file, konten, content_type)
        data_kolom = None
    else:
        r2_key = None
        data_kolom = konten
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO live_chat_pesan (tenant_id, arah, nomor_wa, nama_kontak, jenis, "
            "gambar_filename, gambar_data, gambar_r2_key, gambar_content_type, waktu) "
            "VALUES (?, 'masuk', ?, ?, 'gambar', ?, ?, ?, ?, ?)",
            (tenant_id, nomor_wa, nama_kontak, nama_file, data_kolom, r2_key, content_type,
             _sekarang_wib().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def simpan_pesan_teks_keluar(tenant_id: int, nomor_wa: str, isi_teks: str, baileys_msg_id: str = None) -> int:
    """`baileys_msg_id` HANYA diisi kalau pesan ini dikirim lewat jalur
    Baileys (lihat live_chat_baileys_db.py) -- dipakai routers/live_chat_
    baileys.py mencocokkan event "pesan keluar" yang dilaporkan BALIK oleh
    Baileys (Baileys melihat SEMUA pesan keluar, termasuk yang baru saja
    dikirim lewat sini sendiri) supaya tidak tersimpan dobel."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO live_chat_pesan (tenant_id, arah, nomor_wa, jenis, isi_teks, waktu, baileys_msg_id) "
            "VALUES (?, 'keluar', ?, 'teks', ?, ?, ?)",
            (tenant_id, nomor_wa, isi_teks, _sekarang_wib().isoformat(timespec="seconds"), baileys_msg_id),
        )
        return cur.lastrowid


def baileys_msg_id_sudah_tersimpan(baileys_msg_id: str) -> bool:
    """Dipakai routers/live_chat_baileys.py -- lihat catatan dedup di
    docstring simpan_pesan_teks_keluar() di atas."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 AS ada FROM live_chat_pesan WHERE baileys_msg_id = ? LIMIT 1", (baileys_msg_id,)
        ).fetchone()
    return row is not None


def list_kontak(tenant_id: int) -> list:
    """Satu baris per nomor_wa unik, diurutkan dari pesan TERBARU -- preview
    pesan terakhir (teks apa adanya, atau label "📷 Gambar" untuk jenis
    gambar) + jumlah pesan MASUK yang belum pernah dibuka di Rivoir (badge
    unread, lihat tandai_dibuka())."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT nomor_wa, nama_kontak, jenis, isi_teks, waktu
               FROM live_chat_pesan p
               WHERE tenant_id = ? AND waktu = (
                   SELECT MAX(waktu) FROM live_chat_pesan WHERE tenant_id = p.tenant_id AND nomor_wa = p.nomor_wa
               )
               ORDER BY waktu DESC""",
            (tenant_id,),
        ).fetchall()
        hasil = []
        for r in rows:
            belum_dibuka = conn.execute(
                "SELECT COUNT(*) AS n FROM live_chat_pesan "
                "WHERE tenant_id = ? AND nomor_wa = ? AND arah = 'masuk' AND dibuka_di_rivoir_at IS NULL",
                (tenant_id, r["nomor_wa"]),
            ).fetchone()["n"]
            hasil.append({
                "nomor_wa": r["nomor_wa"],
                "nama_kontak": r["nama_kontak"],
                "preview": "📷 Gambar" if r["jenis"] == "gambar" else (r["isi_teks"] or ""),
                "waktu_terakhir": r["waktu"],
                "belum_dibuka": belum_dibuka,
            })
        return hasil


def list_pesan_thread(tenant_id: int, nomor_wa: str, limit: int = 200) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, arah, jenis, isi_teks, gambar_filename, gambar_content_type, waktu "
            "FROM live_chat_pesan WHERE tenant_id = ? AND nomor_wa = ? ORDER BY waktu ASC, id ASC LIMIT ?",
            (tenant_id, nomor_wa, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def tandai_dibuka(tenant_id: int, nomor_wa: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE live_chat_pesan SET dibuka_di_rivoir_at = ? "
            "WHERE tenant_id = ? AND nomor_wa = ? AND dibuka_di_rivoir_at IS NULL",
            (_sekarang_wib().isoformat(timespec="seconds"), tenant_id, nomor_wa),
        )


def get_gambar(tenant_id: int, pesan_id: int):
    """Return (bytes, content_type) -- None, None kalau pesan tidak ada/
    bukan milik tenant ini/bukan jenis gambar (isolasi tenant DICEK DI SINI,
    bukan cuma di endpoint, supaya satu-satunya jalur baca gambar aman
    dipanggil dari mana pun)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT gambar_filename, gambar_data, gambar_r2_key, gambar_content_type "
            "FROM live_chat_pesan WHERE id = ? AND tenant_id = ? AND jenis = 'gambar'",
            (pesan_id, tenant_id),
        ).fetchone()
    if row is None or not row["gambar_filename"]:
        return None, None
    if row["gambar_r2_key"]:
        data, r2_content_type = r2_storage.get_bytes(row["gambar_r2_key"])
        if data is not None:
            return data, r2_content_type or row["gambar_content_type"]
    if row["gambar_data"] is not None:
        return bytes(row["gambar_data"]), row["gambar_content_type"]
    return None, None


def hapus_kedaluwarsa() -> dict:
    """Dipanggil cron terjadwal (lihat routers/cron_live_chat_purge.py) --
    SELALU di-scan lintas SEMUA tenant sekaligus (pola sama data_purge_db.py),
    bukan per-tenant, karena dipanggil layanan penjadwal eksternal tanpa
    konteks tenant. Baris dengan dibuka_di_rivoir_at IS NULL TIDAK PERNAH
    ikut tersentuh di sini sama sekali (lihat WHERE di bawah)."""
    batas_gambar = (_sekarang_wib() - timedelta(hours=RETENSI_GAMBAR_JAM)).isoformat(timespec="seconds")
    batas_teks = (_sekarang_wib() - timedelta(days=RETENSI_TEKS_HARI)).isoformat(timespec="seconds")
    with get_conn() as conn:
        baris_gambar = conn.execute(
            "SELECT id, gambar_r2_key FROM live_chat_pesan "
            "WHERE jenis = 'gambar' AND dibuka_di_rivoir_at IS NOT NULL AND dibuka_di_rivoir_at <= ?",
            (batas_gambar,),
        ).fetchall()
        for b in baris_gambar:
            if b["gambar_r2_key"]:
                r2_storage.delete(b["gambar_r2_key"])
        conn.execute(
            "DELETE FROM live_chat_pesan WHERE jenis = 'gambar' AND dibuka_di_rivoir_at IS NOT NULL AND dibuka_di_rivoir_at <= ?",
            (batas_gambar,),
        )
        jumlah_teks = conn.execute(
            "SELECT COUNT(*) AS n FROM live_chat_pesan "
            "WHERE jenis = 'teks' AND dibuka_di_rivoir_at IS NOT NULL AND dibuka_di_rivoir_at <= ?",
            (batas_teks,),
        ).fetchone()["n"]
        conn.execute(
            "DELETE FROM live_chat_pesan WHERE jenis = 'teks' AND dibuka_di_rivoir_at IS NOT NULL AND dibuka_di_rivoir_at <= ?",
            (batas_teks,),
        )
    return {"gambar_dihapus": len(baris_gambar), "teks_dihapus": jumlah_teks}
