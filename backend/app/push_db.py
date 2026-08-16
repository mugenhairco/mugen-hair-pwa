"""
push_db.py — FITUR Notifikasi Push (Web Push, termasuk iPhone lewat PWA
"Add to Home Screen" sejak iOS 16.4)
=============================================================================
Modul MANDIRI (berdiri sendiri, pola sama seperti kasbon_db.py/izin_cuti_db.py)
-- HANYA menyimpan/mengambil "Push Subscription" (endpoint + kunci enkripsi
p256dh/auth yang diberikan browser lewat PushManager.subscribe()) per akun
(users.id), TIDAK PERNAH menyimpan isi notifikasi itu sendiri (itu dikirim
langsung saat terjadi, lihat push_service.py).

SATU akun bisa punya BANYAK subscription sekaligus (mis. HP + laptop, atau
uninstall-install ulang PWA menghasilkan endpoint baru) -- UNIQUE di kolom
`endpoint` sendiri (bukan per-user) supaya subscribe ulang dari endpoint yang
SAMA otomatis meng-update kunci (kalau browser rotate key) tanpa duplikat.
"""

from datetime import datetime

from database import get_conn


def init_push_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                tenant_id  INTEGER,
                endpoint   TEXT NOT NULL,
                p256dh     TEXT NOT NULL,
                auth       TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(endpoint)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id ON push_subscriptions(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_push_subscriptions_tenant_id ON push_subscriptions(tenant_id)")


def simpan_subscription(user_id: int, tenant_id, endpoint: str, p256dh: str, auth: str) -> None:
    """Upsert lewat UNIQUE(endpoint) -- subscribe ulang dari endpoint yang
    sama (mis. browser refresh subscription-nya sendiri secara periodik,
    perilaku normal Push API) memperbarui kunci & user_id (kalau akun login
    berbeda di perangkat yang sama) tanpa membuat baris duplikat."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO push_subscriptions (user_id, tenant_id, endpoint, p256dh, auth, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (endpoint) DO UPDATE SET
                   user_id = excluded.user_id, tenant_id = excluded.tenant_id,
                   p256dh = excluded.p256dh, auth = excluded.auth""",
            (user_id, tenant_id, endpoint, p256dh, auth, now),
        )


def hapus_subscription(endpoint: str) -> None:
    """Dipanggil DUA jalur: (1) pengguna sendiri menekan "Nonaktifkan
    Notifikasi", (2) push_service.py otomatis begitu provider push balas
    410 Gone/404 (subscription kedaluwarsa/dicabut browser -- endpoint lama
    percuma disimpan terus, akan gagal setiap kali dipakai)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))


def get_subscriptions_untuk_user(user_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_subscriptions_untuk_barber(barber_id: int) -> list:
    """Subscription MILIK akun login barber ini (users.barber_id = barber_id,
    role='barber') -- lihat push_service.py::kirim_ke_barber(), dipakai
    notifikasi status Izin/Cuti (disetujui/ditolak) yang HANYA relevan buat
    barber ybs, bukan role admin/staff. Kosong (bukan error) kalau barber
    ini belum punya akun login sendiri sama sekali (mis. hanya dikelola
    lewat Setting > Barber tanpa akun terpisah)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ps.* FROM push_subscriptions ps
               JOIN users u ON u.id = ps.user_id
               WHERE u.barber_id = ? AND u.role = 'barber' AND u.aktif = 1""",
            (barber_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_subscriptions_untuk_role(tenant_id: int, roles: list) -> list:
    """Subscription MILIK SEMUA akun tenant ini yang role-nya termasuk
    `roles` (mis. ["admin", "staff"] utk notifikasi Booking Baru/Pengajuan
    Izin -- lihat push_service.py::kirim_ke_role())."""
    if not roles:
        return []
    placeholder = ", ".join("?" for _ in roles)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT ps.* FROM push_subscriptions ps
                JOIN users u ON u.id = ps.user_id
                WHERE u.tenant_id = ? AND u.aktif = 1 AND u.role IN ({placeholder})""",
            (tenant_id, *roles),
        ).fetchall()
        return [dict(r) for r in rows]
