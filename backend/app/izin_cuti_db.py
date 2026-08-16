"""
izin_cuti_db.py — Modul Karyawan: Izin & Cuti (Fase 5)
=============================================================================
Fase 5 (terakhir dari Modul Karyawan) dari permintaan besar "Modul Karyawan/
Keuangan/Pembayaran". Izin & Cuti = pengajuan izin/cuti barber (jenis
'izin'/'cuti', rentang tanggal_mulai..tanggal_selesai, alasan), disetujui/
ditolak Owner/Admin (status 'pending'/'disetujui'/'ditolak',
catatan_approval) -- pola akses SAMA PERSIS seperti reimburse_db.py
(self-service: barber boleh mengajukan/mengedit/menghapus MILIKNYA sendiri
selama masih 'pending', approve/reject eksklusif Owner/Admin).

SENGAJA TIDAK terhubung ke apa pun di luar dirinya sendiri -- TIDAK
mengubah `barbers.status_booking`/logika ketersediaan booking (yang sudah
punya konsep 'cuti' sendiri, lihat booking_db.py STATUS_BOOKING_VALID),
TIDAK terhubung ke Slip Gaji. Murni sistem pengajuan+riwayat+notifikasi
berdiri sendiri, sesuai cakupan spesifikasi asli ("Pengajuan izin/cuti,
alasan, tanggal mulai/selesai, status, riwayat, notifikasi admin/owner").

Tabel baru murni milik modul ini -- init_izin_cuti_db() dipanggil dari
main.py on_startup() jalur SQLite. Jalur PostgreSQL: tabel yang SAMA
dibuat di postgres_schema.py.
"""

import logging
from datetime import datetime

import push_service
from database import get_conn, get_barber

logger = logging.getLogger("mugen.izin_cuti")

JENIS_VALID = {"izin", "cuti"}
STATUS_VALID = {"pending", "disetujui", "ditolak"}
_JENIS_LABEL = {"izin": "Izin", "cuti": "Cuti"}


def init_izin_cuti_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS izin_cuti (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id         INTEGER NOT NULL,
                jenis             TEXT NOT NULL,
                tanggal_mulai     TEXT NOT NULL,
                tanggal_selesai   TEXT NOT NULL,
                alasan            TEXT NOT NULL,
                status            TEXT NOT NULL DEFAULT 'pending',
                catatan_approval  TEXT,
                diajukan_oleh     TEXT,
                disetujui_oleh    TEXT,
                tanggal_approval  TEXT,
                created_at        TEXT NOT NULL,
                updated_at        TEXT,
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)


def _lengkapi(row: dict) -> dict:
    barber = get_barber(row["barber_id"])
    row["nama_barber"] = barber["nama"] if barber else "(barber terhapus)"
    # FONDASI Multi-Tenant Phase 1.1: izin_cuti TIDAK punya kolom tenant_id
    # sendiri (di-scope TRANSITIF lewat barbers.tenant_id, barber_id NOT
    # NULL) -- diselipkan di sini untuk fetch-then-authorize.
    row["tenant_id"] = barber["tenant_id"] if barber else None
    return row


def get_pengajuan(pengajuan_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM izin_cuti WHERE id = ?", (pengajuan_id,)).fetchone()
        return _lengkapi(dict(row)) if row else None


def get_pengajuan_list(barber_id: int = None, status: str = None, jenis: str = None,
                        tahun: int = None, bulan: int = None, tenant_id: int = None) -> list:
    """FONDASI Multi-Tenant Phase 1.1: `tenant_id` opsional, JOIN tambahan
    ke barbers HANYA ditambahkan kalau diisi (endpoint ber-login WAJIB
    mengisi ini)."""
    q = "SELECT i.* FROM izin_cuti i"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = i.barber_id"
    q += " WHERE 1=1"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    if barber_id is not None:
        q += " AND i.barber_id = ?"; params.append(barber_id)
    if status is not None:
        q += " AND i.status = ?"; params.append(status)
    if jenis is not None:
        q += " AND i.jenis = ?"; params.append(jenis)
    if tahun is not None:
        q += " AND i.tanggal_mulai LIKE ?"; params.append(f"{tahun:04d}-%")
    if bulan is not None:
        q += " AND i.tanggal_mulai LIKE ?"; params.append(f"%-{bulan:02d}-%")
    q += " ORDER BY i.tanggal_mulai DESC, i.id DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return [_lengkapi(r) for r in rows]


def get_jumlah_pending(tenant_id: int = None) -> int:
    """Dipakai badge notifikasi sidebar (Owner/Admin) -- lihat izin_notif.js."""
    q = "SELECT COUNT(*) AS jumlah FROM izin_cuti i"
    if tenant_id is not None:
        q += " JOIN barbers b ON b.id = i.barber_id"
    q += " WHERE i.status = 'pending'"
    params = []
    if tenant_id is not None:
        q += " AND b.tenant_id = ?"; params.append(tenant_id)
    with get_conn() as conn:
        row = conn.execute(q, params).fetchone()
    return int(row["jumlah"] or 0)


def _kirim_notifikasi_push_pengajuan_baru(pengajuan: dict):
    """FITUR Notifikasi Push: "best effort" -- TIDAK PERNAH melempar
    exception/menggagalkan pengajuan utamanya (pola sama persis
    booking_db.py::_kirim_notifikasi_push_booking_baru()). Ke role
    admin/staff (yang approve/reject) -- audiens SAMA seperti badge
    get_jumlah_pending() (izin_notif.js)."""
    try:
        push_service.kirim_ke_role(
            pengajuan.get("tenant_id"), ["admin", "staff"],
            title=f"Pengajuan {_JENIS_LABEL.get(pengajuan['jenis'], pengajuan['jenis'])} Baru",
            body=f"{pengajuan.get('nama_barber')} mengajukan {pengajuan['tanggal_mulai']} s/d {pengajuan['tanggal_selesai']}.",
            url="/app/#/izin-cuti",
        )
    except Exception as e:
        logger.error("Notifikasi push pengajuan #%s GAGAL disiapkan: %s: %s", pengajuan.get("id"), type(e).__name__, e)


def _kirim_notifikasi_push_status_pengajuan(pengajuan: dict):
    """Ke akun login barber ybs SAJA (bukan role admin/staff seperti
    fungsi di atas) -- status pengajuannya sendiri yang berubah."""
    try:
        status_label = "Disetujui" if pengajuan["status"] == "disetujui" else "Ditolak"
        push_service.kirim_ke_barber(
            pengajuan["barber_id"],
            title=f"Pengajuan {_JENIS_LABEL.get(pengajuan['jenis'], pengajuan['jenis'])} {status_label}",
            body=f"Pengajuan {pengajuan['tanggal_mulai']} s/d {pengajuan['tanggal_selesai']} Anda {status_label.lower()}.",
            url="/app/#/izin-cuti",
        )
    except Exception as e:
        logger.error("Notifikasi push status pengajuan #%s GAGAL disiapkan: %s: %s", pengajuan.get("id"), type(e).__name__, e)


def buat_pengajuan(barber_id: int, jenis: str, tanggal_mulai: str, tanggal_selesai: str,
                    alasan: str, diajukan_oleh: str = "", tenant_id: int = None) -> dict:
    barber = get_barber(barber_id)
    if barber is None or (tenant_id is not None and barber["tenant_id"] != tenant_id):
        raise ValueError("Barber tidak ditemukan.")
    if jenis not in JENIS_VALID:
        raise ValueError(f"Jenis tidak dikenal: {jenis}")
    datetime.strptime(tanggal_mulai, "%Y-%m-%d")
    datetime.strptime(tanggal_selesai, "%Y-%m-%d")
    if tanggal_mulai > tanggal_selesai:
        raise ValueError("Tanggal Mulai tidak boleh setelah Tanggal Selesai.")
    alasan = (alasan or "").strip()
    if not alasan:
        raise ValueError("Alasan wajib diisi.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO izin_cuti (barber_id, jenis, tanggal_mulai, tanggal_selesai, alasan, status,
                                       diajukan_oleh, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (barber_id, jenis, tanggal_mulai, tanggal_selesai, alasan, diajukan_oleh, now),
        )
        pengajuan_id = cur.lastrowid
    pengajuan_baru = get_pengajuan(pengajuan_id)
    _kirim_notifikasi_push_pengajuan_baru(pengajuan_baru)
    return pengajuan_baru


def edit_pengajuan(pengajuan_id: int, jenis: str = None, tanggal_mulai: str = None,
                    tanggal_selesai: str = None, alasan: str = None) -> dict:
    existing = get_pengajuan(pengajuan_id)
    if existing is None:
        raise ValueError("Pengajuan tidak ditemukan.")
    if existing["status"] != "pending":
        raise ValueError("Pengajuan yang sudah diproses (Disetujui/Ditolak) tidak bisa diedit lagi.")
    jenis_baru = jenis if jenis is not None else existing["jenis"]
    if jenis_baru not in JENIS_VALID:
        raise ValueError(f"Jenis tidak dikenal: {jenis_baru}")
    mulai_baru = tanggal_mulai if tanggal_mulai is not None else existing["tanggal_mulai"]
    selesai_baru = tanggal_selesai if tanggal_selesai is not None else existing["tanggal_selesai"]
    if tanggal_mulai is not None:
        datetime.strptime(mulai_baru, "%Y-%m-%d")
    if tanggal_selesai is not None:
        datetime.strptime(selesai_baru, "%Y-%m-%d")
    if mulai_baru > selesai_baru:
        raise ValueError("Tanggal Mulai tidak boleh setelah Tanggal Selesai.")
    alasan_baru = alasan.strip() if alasan is not None else existing["alasan"]
    if alasan is not None and not alasan_baru:
        raise ValueError("Alasan wajib diisi.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE izin_cuti SET jenis = ?, tanggal_mulai = ?, tanggal_selesai = ?, alasan = ?,
                   updated_at = ? WHERE id = ?""",
            (jenis_baru, mulai_baru, selesai_baru, alasan_baru, now, pengajuan_id),
        )
    return get_pengajuan(pengajuan_id)


def hapus_pengajuan(pengajuan_id: int):
    existing = get_pengajuan(pengajuan_id)
    if existing is None:
        raise ValueError("Pengajuan tidak ditemukan.")
    if existing["status"] != "pending":
        raise ValueError("Pengajuan yang sudah diproses (Disetujui/Ditolak) tidak bisa dihapus lagi.")
    with get_conn() as conn:
        conn.execute("DELETE FROM izin_cuti WHERE id = ?", (pengajuan_id,))


def set_status_pengajuan(pengajuan_id: int, status: str, catatan_approval: str = "",
                          disetujui_oleh: str = "") -> dict:
    if status not in {"disetujui", "ditolak"}:
        raise ValueError(f"Status tidak dikenal: {status}")
    existing = get_pengajuan(pengajuan_id)
    if existing is None:
        raise ValueError("Pengajuan tidak ditemukan.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """UPDATE izin_cuti SET status = ?, catatan_approval = ?, disetujui_oleh = ?,
                   tanggal_approval = ?, updated_at = ? WHERE id = ?""",
            (status, (catatan_approval or "").strip(), disetujui_oleh, now[:10], now, pengajuan_id),
        )
    pengajuan_baru = get_pengajuan(pengajuan_id)
    _kirim_notifikasi_push_status_pengajuan(pengajuan_baru)
    return pengajuan_baru
