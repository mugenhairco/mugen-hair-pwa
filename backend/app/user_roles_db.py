"""user_roles_db.py — Role Custom per Tenant (FITUR Role User Custom, diminta Owner)
=============================================================================
Lanjutan dari permissions.py (katalog izin_* yang sudah ada) -- SEBELUMNYA
HANYA ada SATU set izin per tenant, berlaku untuk SEMUA akun ber-role
'staff' sekaligus ("Hak Akses Admin"). Owner sekarang bisa membuat role
BERNAMA sendiri (mis. "Kasir", "Supervisor"), masing-masing dengan
kombinasi izin_* berbeda (checklist yang SAMA PERSIS, dari katalog
permissions.PERMISSION_DEFS -- TIDAK ADA sistem izin baru), lalu
menempelkan akun 'staff' tertentu ke role itu.

KOMPATIBEL MUNDUR TOTAL: akun 'staff' yang `custom_role_id`-nya NULL
(termasuk SEMUA akun staff yang sudah ada sebelum fitur ini) TETAP
memakai satu set izin tenant-wide lama ("Hak Akses User" default, disimpan
di tabel `settings` lewat permissions.py, TIDAK disentuh modul ini sama
sekali) -- role custom murni OPSIONAL/TAMBAHAN, bukan migrasi paksa. Lihat
permissions.py::get_all()/has() untuk titik gabungnya (parameter `role_id`
opsional -- diisi = pakai role custom, None = perilaku lama).

BEDA dari role custom TANPA centang apa pun: role BARU (belum pernah
diatur Owner) mulai KOSONG (fail-CLOSED, semua izin False) -- BEDA dari
default tenant-wide (banyak yang True by design, lihat permissions.py) --
karena tidak ada "staff yang sudah pakai" untuk digrandfather di role yang
baru saja dibuat Owner sendiri."""

from datetime import datetime

from database import get_conn


def init_user_roles_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id    INTEGER,
                nama         TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        # role_id BOLEH pakai FK (tabel ini BARU, dibuat sekaligus dengan
        # PRIMARY KEY yang benar sejak awal -- BUKAN tabel produksi lama
        # yang jadi sumber insiden FK di postgres_schema.py, pola sama
        # seperti subscription_package_features di billing_db.py) --
        # ON DELETE CASCADE otomatis membersihkan checklist izin begitu
        # role-nya dihapus.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_role_permissions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id      INTEGER NOT NULL,
                izin_key     TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                UNIQUE(role_id, izin_key),
                FOREIGN KEY (role_id) REFERENCES user_roles(id) ON DELETE CASCADE
            )
        """)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def list_roles(tenant_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM user_roles WHERE tenant_id = ? ORDER BY nama, id", (tenant_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_role(role_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_roles WHERE id = ?", (role_id,)).fetchone()
        return dict(row) if row else None


def create_role(tenant_id: int, nama: str) -> dict:
    nama = (nama or "").strip()
    if not nama:
        raise ValueError("Nama role tidak boleh kosong.")
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO user_roles (tenant_id, nama, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (tenant_id, nama, now, now),
        )
        role_id = cur.lastrowid
    return get_role(role_id)


def rename_role(role_id: int, nama: str) -> dict:
    if get_role(role_id) is None:
        raise ValueError("Role tidak ditemukan.")
    nama = (nama or "").strip()
    if not nama:
        raise ValueError("Nama role tidak boleh kosong.")
    with get_conn() as conn:
        conn.execute("UPDATE user_roles SET nama = ?, updated_at = ? WHERE id = ?", (nama, _now(), role_id))
    return get_role(role_id)


def delete_role(role_id: int):
    """Hapus PERMANEN -- ON DELETE CASCADE melepas checklist izin role ini
    (user_role_permissions). Akun 'staff' yang masih `custom_role_id`-nya
    menunjuk ke sini DISENGAJA TIDAK diurus di sini (butuh akses ke tabel
    `users`, milik auth_db.py) -- pemanggil (routers/pengaturan.py) WAJIB
    memanggil auth_db.lepas_custom_role_dari_semua_user() SEBELUM ini,
    supaya staff yang terkena otomatis balik ke Hak Akses User default
    (TIDAK PERNAH macet/terkunci karena role-nya tiba-tiba hilang -- lihat
    keputusan eksplisit Owner)."""
    if get_role(role_id) is None:
        raise ValueError("Role tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("DELETE FROM user_roles WHERE id = ?", (role_id,))


def get_role_permission_keys(role_id: int) -> set:
    """Set kode izin_* yang AKTIF (True) untuk role ini -- kode yang TIDAK
    ada di sini dianggap False (fail-CLOSED, lihat catatan modul di atas).
    Dipanggil permissions.py::get_all(role_id=...) untuk mengisi dict
    lengkap {key: bool} dari katalog PERMISSION_DEFS."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT izin_key FROM user_role_permissions WHERE role_id = ?", (role_id,)
        ).fetchall()
        return {r["izin_key"] for r in rows}


def set_role_permission_keys(role_id: int, keys: set):
    """GANTI TOTAL daftar izin aktif role ini jadi `keys` -- pola sama
    seperti billing_db.set_package_features() (hapus semua baris lama,
    insert ulang yang baru, dalam satu fungsi supaya tidak ada baris usang
    tersisa kalau Owner mencabut sebuah izin)."""
    if get_role(role_id) is None:
        raise ValueError("Role tidak ditemukan.")
    now = _now()
    with get_conn() as conn:
        conn.execute("DELETE FROM user_role_permissions WHERE role_id = ?", (role_id,))
        for key in keys:
            conn.execute(
                "INSERT INTO user_role_permissions (role_id, izin_key, created_at) VALUES (?, ?, ?)",
                (role_id, key, now),
            )
