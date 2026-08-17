"""
error_log_db.py — Pencatatan Error Frontend & Backend (DIY, tanpa Sentry)
=============================================================================
Sebelum modul ini ada, error yang terjadi di production TIDAK PERNAH
tercatat di tempat yang bisa dilihat siapa pun -- backend hanya menulis ke
stdout (ditangkap Render sebagai log platform, tapi tidak ada yang otomatis
memberi tahu), frontend malah tidak mencatat apa pun sama sekali (error JS
di HP customer/barber hilang begitu saja di console browser mereka).
Satu-satunya cara tahu ada masalah adalah user melapor duluan.

Modul MANDIRI (pola sama seperti push_db.py/kasbon_db.py) ini memberi
tempat sederhana: SATU tabel yang menerima catatan error dari kedua sisi
(lihat routers/error_log.py untuk POST dari frontend, main.py::
_tangani_exception_global() untuk auto-capture crash backend), dilihat
Owner lewat Setting > Log Error.

Sengaja BUKAN pengganti layanan pihak ketiga (Sentry dkk) -- tidak ada
grouping/alert otomatis/dashboard canggih, murni "tercatat & bisa dilihat"
tanpa biaya berlangganan apa pun."""

from datetime import datetime

from database import get_conn

# Baris tertua dihapus begitu tabel melewati batas ini -- error yang
# berulang tanpa henti (mis. bug yang memicu render loop di frontend) tidak
# boleh membuat tabel ini tumbuh tanpa batas.
BATAS_BARIS = 2000


def init_error_log_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id  INTEGER,
                sumber     TEXT NOT NULL,
                pesan      TEXT NOT NULL,
                detail     TEXT,
                url        TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_logs_tenant_id ON error_logs(tenant_id)")


def _pangkas(conn):
    conn.execute(
        "DELETE FROM error_logs WHERE id NOT IN (SELECT id FROM error_logs ORDER BY id DESC LIMIT ?)",
        (BATAS_BARIS,),
    )


def catat_error(sumber: str, pesan: str, detail: str = None, url: str = None,
                 user_agent: str = None, tenant_id: int = None) -> None:
    """Dipanggil dari dua tempat: routers/error_log.py (POST dari frontend,
    tenant_id best-effort lewat auth.resolve_tenant_untuk_branding -- bisa
    None kalau benar-benar tidak diketahui, mis. error di halaman Login
    sebelum tenant sempat diketahui) dan main.py::_tangani_exception_global()
    (auto-capture crash backend, tenant_id SELALU None karena exception
    handler global tidak tahu request itu punya sesi tenant yang mana).

    SENGAJA TIDAK melempar exception ke pemanggil kalau INSERT gagal --
    pemanggil (kedua-duanya) yang membungkus try/except di sisinya sendiri
    (lihat catatan di routers/error_log.py), fungsi ini murni operasi
    database biasa supaya test bisa memverifikasi kegagalan penyimpanan
    sungguhan kalau perlu."""
    pesan = (pesan or "(tanpa pesan)").strip()[:2000]
    detail = (detail or "").strip()[:8000] or None
    url = (url or "").strip()[:500] or None
    user_agent = (user_agent or "").strip()[:500] or None
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO error_logs (tenant_id, sumber, pesan, detail, url, user_agent, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, sumber, pesan, detail, url, user_agent, now),
        )
        _pangkas(conn)


def get_error_log_list(tenant_id: int, sumber: str = None, limit: int = 200) -> list:
    """KHUSUS baris milik tenant ini -- error dengan tenant_id NULL (tidak
    diketahui tenant-nya, lihat catat_error()) SENGAJA TIDAK PERNAH muncul
    di sini, tidak ada tampilan lintas-tenant untuk Owner biasa (bukan
    superadmin)."""
    q = "SELECT * FROM error_logs WHERE tenant_id = ?"
    params = [tenant_id]
    if sumber is not None:
        q += " AND sumber = ?"
        params.append(sumber)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]
