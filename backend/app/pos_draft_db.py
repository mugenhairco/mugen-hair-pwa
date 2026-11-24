"""pos_draft_db.py — Draft Transaksi POS (Kasir walk-in)
=============================================================================
FITUR BARU (diminta Owner): Kasir bisa menyiapkan transaksi LEBIH AWAL --
pilih Barber + ketik Nama Customer -- SEBELUM customer-nya benar-benar siap
bayar. Draft tersimpan di SERVER (bukan localStorage) supaya bertahan
lintas pindah menu/tutup-buka app DAN terlihat SAMA oleh semua
device/kasir yang login (bukan per-device) -- lihat pages/pos.js untuk UI
kartu draft + expand inline Tips/Service/Metode Bayar di tempat.

Draft TIDAK punya status/fase -- cuma 2 keadaan: ADA (menunggu dipakai/
dibatalkan) atau TIDAK ADA (dihapus begitu transaksinya berhasil dibuat
lewat endpoint checkout POS yang sudah ada, ATAU dibatalkan manual). Tidak
ada kolom status karena tidak ada state ketiga.

Modul TERSENDIRI (bukan ditambah ke pos_db.py) -- konsisten dengan pola
1-modul-per-konsep di app ini (lihat izin_cuti_db.py, kasbon_db.py, dkk).
`_jalankan_di_belakang()` di bawah adalah duplikat KECIL yang sama persis
seperti pos_db.py/booking_db.py/izin_cuti_db.py -- pola project: tiap
modul punya salinan sendiri, bukan diimpor lintas modul."""

import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import push_service
from database import get_conn

WIB = ZoneInfo("Asia/Jakarta")

_logger = logging.getLogger("mugen.pos_draft")


def init_pos_draft_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pos_draft (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id      INTEGER NOT NULL,
                barber_id      INTEGER NOT NULL,
                customer_nama  TEXT NOT NULL,
                dibuat_oleh    TEXT,
                created_at     TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_draft_tenant ON pos_draft(tenant_id)")


def list_draft(tenant_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT pd.*, b.nama AS nama_barber "
            "FROM pos_draft pd LEFT JOIN barbers b ON b.id = pd.barber_id "
            "WHERE pd.tenant_id = ? ORDER BY pd.created_at ASC",
            (tenant_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def _ambil_draft(tenant_id: int, draft_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT pd.*, b.nama AS nama_barber "
            "FROM pos_draft pd LEFT JOIN barbers b ON b.id = pd.barber_id "
            "WHERE pd.tenant_id = ? AND pd.id = ?",
            (tenant_id, draft_id),
        ).fetchone()
        return dict(row) if row else None


def buat_draft(tenant_id: int, barber_id: int, customer_nama: str, dibuat_oleh: str) -> dict:
    now = datetime.now(WIB).isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pos_draft (tenant_id, barber_id, customer_nama, dibuat_oleh, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (tenant_id, barber_id, customer_nama, dibuat_oleh, now),
        )
        draft_id = cur.lastrowid
    draft = _ambil_draft(tenant_id, draft_id)
    _jalankan_di_belakang(_kirim_notifikasi_push_draft_berubah, tenant_id)
    return draft


def hapus_draft(tenant_id: int, draft_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM pos_draft WHERE tenant_id = ? AND id = ?",
            (tenant_id, draft_id),
        )
    ok = cur.rowcount > 0
    if ok:
        _jalankan_di_belakang(_kirim_notifikasi_push_draft_berubah, tenant_id)
    return ok


def _jalankan_di_belakang(fn, *args):
    """PERBAIKAN PERFORMA -- pola SAMA PERSIS pos_db.py/booking_db.py/
    izin_cuti_db.py::_jalankan_di_belakang(): push (pywebpush) adalah
    panggilan HTTP KELUAR yang bisa lambat -- dipindah ke thread terpisah
    (daemon) supaya respons buat/hapus draft tidak menunggu push selesai."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _kirim_notifikasi_push_draft_berubah(tenant_id: int) -> None:
    """Sinkron kartu Draft antar device/kasir secara real-time -- pola SAMA
    PERSIS pos_db.py::_kirim_notifikasi_push_pos_lunas(). Payload membawa
    FULL list draft terbaru (list draft selalu kecil, lebih simpel daripada
    diff per-baris) -- frontend (pages/pos.js::suntikDraftBerubah()) tinggal
    mengganti cache & re-render seksi Draft, TANPA fetch ulang ke server.
    Best effort, TIDAK PERNAH melempar exception (lihat push_service.
    IS_ENABLED kalau VAPID belum dikonfigurasi)."""
    try:
        push_service.kirim_ke_role(
            tenant_id, ["admin", "staff"],
            title="Draft POS Berubah",
            body="Daftar draft kasir diperbarui.",
            url="/app/#/pos",
            jenis="pos_draft_berubah",
            data=list_draft(tenant_id),
        )
    except Exception as e:
        _logger.error("Notifikasi push draft POS (tenant %s) GAGAL disiapkan: %s: %s",
                       tenant_id, type(e).__name__, e)
