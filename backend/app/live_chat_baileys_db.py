"""live_chat_baileys_db.py — FITUR Live Chat via Baileys (WhatsApp Web sendiri)
=============================================================================
PERMINTAAN Owner: pesan WA yang diketik manual dari HP toko (aplikasi
WhatsApp asli, BUKAN lewat kotak balas Live Chat) tidak pernah muncul di
Rivoir -- dipastikan ini keterbatasan Fonnte sendiri (webhook-nya HANYA
untuk pesan MASUK dari customer, tidak ada fitur melaporkan pesan keluar
manual, lihat screenshot dashboard Fonnte Owner: semua toggle Device/
Webhook eksplisit tertulis "incoming message"). Solusinya: tenant yang mau
bisa menyambungkan WhatsApp toko-nya LANGSUNG ke Rivoir lewat scan QR (pola
sama persis WhatsApp Web biasa, lewat service terpisah `baileys-service/`
yang menjalankan library Baileys, Node.js) -- begitu tersambung, SEMUA
pesan (masuk dari customer MAUPUN keluar yang diketik manual dari HP)
otomatis terlihat Rivoir, tidak cuma balasan lewat Live Chat.

BERDAMPINGAN dengan Fonnte, BUKAN ganti total -- HANYA tenant yang berhasil
scan QR (status 'tersambung' di sini) yang jalur kirim/terima Live Chat-nya
pindah ke Baileys (lihat kirim_terpasang() di bawah, dipakai
routers/live_chat.py::kirim_balasan() untuk memilih Fonnte vs Baileys).
Tenant yang belum/tidak pernah connect TIDAK terpengaruh sama sekali --
webhook Fonnte lama (routers/live_chat.py::terima_webhook()) tetap jalan
utuh untuk mereka. Reminder absensi/OTP/notifikasi booking otomatis TIDAK
ADA HUBUNGANNYA dengan modul ini -- semua itu tetap lewat
whatsapp_service.kirim_whatsapp() (Fonnte), sama sekali tidak diubah.

Modul ini TIDAK PERNAH bicara langsung ke service Baileys (lihat
routers/live_chat_baileys.py untuk itu) -- murni baca/tulis tabel
`live_chat_baileys_sesi`. `auth_state` (blob JSON kredensial+kunci sesi
WhatsApp milik Baileys) dititipkan DI SINI (bukan disimpan sendiri oleh
service Node.js-nya) supaya kredensial database tidak perlu ada di service
Node.js itu sama sekali -- service Baileys HANYA punya satu shared secret
(BAILEYS_INTERNAL_SECRET) untuk bicara ke backend Python ini."""

from datetime import datetime

from database import get_conn

STATUS_BELUM_TERHUBUNG = "belum_terhubung"
STATUS_MENUNGGU_SCAN = "menunggu_scan"
STATUS_TERSAMBUNG = "tersambung"
STATUS_TERPUTUS = "terputus"


def init_live_chat_baileys_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_chat_baileys_sesi (
                tenant_id         INTEGER PRIMARY KEY,
                auth_state        TEXT,
                status            TEXT NOT NULL DEFAULT 'belum_terhubung',
                qr_data           TEXT,
                nomor_tersambung  TEXT,
                updated_at        TEXT NOT NULL
            )
        """)
        # Migrasi kolom baru di live_chat_pesan (idempotent, pola SAMA
        # PERSIS booking_notif_dimatikan_migrasi.py) -- dipanggil di sini
        # (bukan file migrasi terpisah) karena satu-satunya pemakai kolom
        # ini adalah fitur Baileys. Jalur Postgres: ALTER TABLE ADD COLUMN
        # IF NOT EXISTS yang setara ada di postgres_schema.py.
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(live_chat_pesan)").fetchall()]
        if "baileys_msg_id" not in kolom:
            conn.execute("ALTER TABLE live_chat_pesan ADD COLUMN baileys_msg_id TEXT")


def _upsert(tenant_id: int, **kolom):
    """Helper internal -- INSERT baris baru (status default) kalau tenant
    ini belum pernah punya baris, lalu UPDATE kolom yang diberikan.
    SQLite/Postgres generik (pola get_conn() yang sudah dipakai modul lain
    di proyek ini)."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO live_chat_baileys_sesi (tenant_id, status, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (tenant_id) DO NOTHING",
            (tenant_id, STATUS_BELUM_TERHUBUNG, now),
        )
        if kolom:
            set_sql = ", ".join(f"{k} = ?" for k in kolom)
            conn.execute(
                f"UPDATE live_chat_baileys_sesi SET {set_sql}, updated_at = ? WHERE tenant_id = ?",
                (*kolom.values(), now, tenant_id),
            )


def get_status(tenant_id: int) -> dict:
    """Selalu mengembalikan baris (belum_terhubung kalau tenant belum pernah
    mulai connect sama sekali -- TIDAK ADA baris di tabel), supaya pemanggil
    (routers/live_chat_baileys.py) tidak perlu cek None secara terpisah."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, qr_data, nomor_tersambung FROM live_chat_baileys_sesi WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    if row is None:
        return {"status": STATUS_BELUM_TERHUBUNG, "qr_data": None, "nomor_tersambung": None}
    return {"status": row["status"], "qr_data": row["qr_data"], "nomor_tersambung": row["nomor_tersambung"]}


def kirim_terpasang(tenant_id: int) -> bool:
    """Dipakai routers/live_chat.py::kirim_balasan() memilih jalur kirim --
    True HANYA kalau tenant ini sudah tersambung Baileys (sesuai kesepakatan
    "berdampingan, bukan ganti total", lihat docstring modul)."""
    return get_status(tenant_id)["status"] == STATUS_TERSAMBUNG


def set_qr(tenant_id: int, qr_data: str):
    _upsert(tenant_id, status=STATUS_MENUNGGU_SCAN, qr_data=qr_data)


def set_tersambung(tenant_id: int, nomor_tersambung: str):
    _upsert(tenant_id, status=STATUS_TERSAMBUNG, qr_data=None, nomor_tersambung=nomor_tersambung)


def set_terputus(tenant_id: int):
    _upsert(tenant_id, status=STATUS_TERPUTUS, qr_data=None)


def get_auth_state(tenant_id: int) -> str | None:
    """Return blob JSON mentah (atau None kalau belum pernah ada sesi sama
    sekali) -- Baileys sendiri yang tahu cara parse isinya, modul ini murni
    penyimpanan buta (lihat routers/live_chat_baileys.py)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT auth_state FROM live_chat_baileys_sesi WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
    return row["auth_state"] if row else None


def set_auth_state(tenant_id: int, auth_state_json: str):
    _upsert(tenant_id, auth_state=auth_state_json)


def hapus_sesi(tenant_id: int):
    """Dipanggil saat tombol "Putuskan" diklik -- hapus TOTAL (bukan cuma
    set status terputus) supaya connect berikutnya mulai dari QR baru yang
    bersih, bukan mencoba pakai auth_state lama yang sudah sengaja dilepas."""
    with get_conn() as conn:
        conn.execute("DELETE FROM live_chat_baileys_sesi WHERE tenant_id = ?", (tenant_id,))
