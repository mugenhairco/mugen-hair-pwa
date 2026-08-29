"""
auth_db.py
==========
Tabel & fungsi untuk AUTENTIKASI saja (login admin/barber). SENGAJA dipisah
dari database.py supaya database.py (satu-satunya sumber logika bisnis,
disalin VERBATIM dari aplikasi Python Desktop) tetap 100% tidak tersentuh —
sesuai ATURAN MUTLAK: jangan ubah logika bisnis / hasil perhitungan.

Tabel 'users' terpisah dari tabel 'barbers' (di database.py) karena:
- 'barbers' murni data bisnis (dipakai transaksi, komisi, dst) — jangan diubah.
- 'users' murni data login (username, password hash, role, dan referensi ke
  barber_id kalau role-nya 'barber'). Satu baris barbers BOLEH tidak punya
  akun (belum dibuatkan login), dan sebaliknya.

Password disimpan sebagai HASH (bcrypt), tidak pernah plaintext.

BUGFIX startup lokal: sebelumnya hashing memakai passlib
(`passlib.context.CryptContext(schemes=["bcrypt"])`), yang TIDAK
kompatibel dengan bcrypt>=4.0 -- passlib 1.7.4 (sudah tidak dikembangkan
lagi) melakukan self-test versi bcrypt lewat atribut `bcrypt.__about__`
yang sudah dihapus dari bcrypt sejak versi 4.0, menyebabkan
`AttributeError: module 'bcrypt' has no attribute '__about__'` dan/atau
`ValueError: password cannot be longer than 72 bytes` (dari self-test lain
milik passlib, `detect_wrap_bug`, bukan dari password pengguna yang
sebenarnya) begitu fungsi hash/verify pertama kali dipanggil -- gagal
walau `bcrypt<4.0` sudah dikunci di requirements.txt, kalau environment
lokal kebetulan sudah lebih dulu punya bcrypt versi lebih baru terpasang.
Diperbaiki dengan memanggil library `bcrypt` LANGSUNG (tanpa passlib) --
algoritma & format hash yang dihasilkan identik (awalan `$2b$`), jadi hash
yang sudah tersimpan di database dari versi sebelumnya (dibuat lewat
passlib) tetap valid diverifikasi lewat kode ini tanpa perlu migrasi data
apa pun."""

import secrets
import sqlite3
from contextlib import contextmanager

import bcrypt

import db_compat
from db_compat import IntegrityError
from database import DB_PATH  # pakai path database yang SAMA dengan database.py (satu file .db yang sama)

# Batas bawaan algoritma bcrypt itu sendiri: byte setelah yang ke-72 pada
# password diabaikan. bcrypt versi lama memotongnya diam-diam; versi >=4.0
# melempar ValueError kalau tidak dipotong duluan -- dipotong manual di
# sini (simetris di hash & verify) supaya perilakunya konsisten di semua
# versi bcrypt, sesuai saran pesan error resminya sendiri.
_BCRYPT_MAX_BYTES = 72


@contextmanager
def get_conn():
    # AUDIT SINKRONISASI: konsisten dengan get_conn() di database.py (file
    # .db yang sama) -- WAL mode + busy_timeout 30 detik supaya pembaca/
    # penulis dari device lain tidak saling memblokir/gagal "database is
    # locked" saat request bersamaan. Lihat komentar lengkap di database.py.
    # TAHAP migrasi Postgres: sama seperti get_conn() di database.py, kalau
    # DATABASE_URL diisi seluruh fungsi di file ini otomatis jalan di atas
    # PostgreSQL lewat db_compat.get_conn() -- lihat db_compat.py.
    if db_compat.IS_POSTGRES:
        with db_compat.get_conn() as conn:
            yield conn
        return
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_auth_db():
    """CREATE TABLE IF NOT EXISTS — aman dipanggil berkali-kali, tidak akan
    pernah menimpa/menghapus data yang sudah ada (tabel & data 'barbers',
    'transaksi', dst di database.py TIDAK disentuh sama sekali).

    FONDASI Multi-Tenant Phase 1: instalasi SQLite BARU (tabel belum pernah
    ada) langsung dibuat dengan `tenant_id` + `UNIQUE(tenant_id, username)`
    (bukan lagi `username` unik global) sejak awal. Instalasi SQLite LAMA
    (tabel sudah ada dari sebelum Phase 1) TIDAK ikut diubah constraint-nya
    di sini -- SQLite tidak bisa mengubah UNIQUE constraint tanpa membangun
    ulang tabel; kolom `tenant_id`-nya sendiri tetap ditambahkan lewat
    ALTER TABLE oleh tenant_migrasi.py (dipanggil terpisah, lihat main.py).
    Batasan ini HANYA berlaku jalur SQLite (development lokal) -- jalur
    PostgreSQL (produksi, lihat postgres_schema.py) sudah menangani
    perubahan constraint pada instalasi yang sudah berjalan lewat
    `DROP CONSTRAINT`/`CREATE UNIQUE INDEX`."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL,   -- 'admin' atau 'barber'
                barber_id     INTEGER,         -- HANYA diisi kalau role = 'barber'
                                                -- (referensi ke barbers.id di database.py)
                tenant_id     INTEGER,         -- referensi ke tenants.id (tenant_migrasi.py)
                aktif         INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL,
                UNIQUE(tenant_id, username),
                FOREIGN KEY (barber_id) REFERENCES barbers(id)
            )
        """)


def _pesan_diagnosa_bcrypt(exc: Exception) -> str:
    """Kode ini (auth_db.py) sudah TIDAK memanggil passlib sama sekali sejak
    bugfix sebelumnya -- diverifikasi lewat reproduksi persis kombinasi
    paket yang dilaporkan (bcrypt 5.0.0 + passlib 1.7.4 terpasang
    berdampingan) dan backend tetap start normal. Kalau error semacam ini
    masih muncul, penyebab paling mungkin BUKAN kode ini, melainkan
    instalasi paket `bcrypt` yang rusak/tidak bersih di virtual environment
    lokal (paling sering di Windows: file ekstensi native `.pyd` versi lama
    gagal terhapus/tertimpa saat `pip install --upgrade`, karena Windows
    mengunci file yang sedang dipakai proses lain). Pesan ini mengubah
    traceback kriptis dari dalam library `bcrypt` menjadi langkah perbaikan
    yang jelas."""
    return (
        f"Gagal memanggil library 'bcrypt' ({exc.__class__.__name__}: {exc}). "
        "Kode aplikasi ini TIDAK memakai passlib lagi, jadi kemungkinan besar "
        "virtual environment lokal Anda punya sisa instalasi 'bcrypt' yang "
        "rusak/tidak bersih (sering terjadi di Windows saat upgrade paket "
        "berekstensi native). Perbaikan: HAPUS TOTAL folder virtual "
        "environment lama (mis. .venv/venv/env), buat baru "
        "('python -m venv .venv'), lalu 'pip install -r requirements.txt' "
        "dari kosong -- jangan install di atas venv lama. Lihat bagian "
        "'Instalasi' / 'Troubleshooting Windows' di README.md."
    )


def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")
    except Exception as e:
        raise RuntimeError(_pesan_diagnosa_bcrypt(e)) from e


def verify_password(password: str, password_hash: str) -> bool:
    pw_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))
    except Exception as e:
        raise RuntimeError(_pesan_diagnosa_bcrypt(e)) from e


# Hash dummy untuk mitigasi timing side-channel di autentikasi() -- dibuat
# SEKALI per proses dari string acak yang TIDAK PERNAH jadi password
# siapa pun, jadi verify_password(apapun, hash ini) SELALU False.
_HASH_DUMMY_ANTI_TIMING = hash_password(secrets.token_hex(32))


def tambah_user(username: str, password: str, role: str, barber_id: int = None, tenant_id: int = None,
                 custom_role_id: int = None) -> int:
    """FONDASI Multi-Tenant Phase 1: `tenant_id` menandai user ini milik
    tenant mana -- WAJIB diisi pemanggil KECUALI jalur bootstrap instalasi
    yang benar-benar baru (lihat main.py::_bootstrap_admin_pertama(), yang
    sudah meresolusi tenant default sebelum memanggil ini). Constraint unik
    username berubah dari GLOBAL menjadi PER TENANT (lihat
    postgres_schema.py/tenant_migrasi.py) -- dua tenant boleh sama-sama
    punya username yang sama persis.

    FONDASI Multi-Tenant Phase 2.1 (Super Admin Dashboard): role 'superadmin'
    ditambahkan -- akun ini mengelola SELURUH tenant (bukan milik satu
    barbershop mana pun), jadi WAJIB `tenant_id=None` (get_current_user() di
    auth.py melewatkan pengecekan tenant aktif kalau tenant_id None, dan
    get_current_tenant_id() menolak akun ini dari endpoint ber-scope tenant
    -- lihat auth.py). Lihat main.py::_bootstrap_superadmin_pertama().

    FITUR Role Custom: `custom_role_id` OPSIONAL, HANYA relevan untuk role
    'staff' (lihat user_roles_db.py) -- None (default) berarti akun ini
    memakai set izin default tenant, PERSIS perilaku lama. Validasi bahwa
    role_id itu SUNGGUHAN ada & milik tenant yang sama adalah tanggung
    jawab pemanggil (routers/pengaturan.py, sama seperti barber_id di
    atas) -- modul ini (auth_db.py) TIDAK mengimpor user_roles_db.py sama
    sekali supaya tidak ada import silang antar modul murni penyimpanan."""
    from datetime import datetime
    username = (username or "").strip()
    if not username:
        raise ValueError("Username tidak boleh kosong.")
    if role not in ("admin", "staff", "barber", "superadmin"):
        raise ValueError("Role harus 'admin' (Owner), 'staff' (Admin), 'barber', atau 'superadmin'.")
    if role == "barber" and barber_id is None:
        raise ValueError("User dengan role 'barber' wajib dikaitkan ke barber_id.")
    if role == "superadmin" and tenant_id is not None:
        raise ValueError("User ber-role 'superadmin' tidak boleh dikaitkan ke tenant mana pun.")
    if not password or len(password) < 4:
        raise ValueError("Password minimal 4 karakter.")

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, role, barber_id, tenant_id, custom_role_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, hash_password(password), role, barber_id, tenant_id, custom_role_id, now),
            )
        except IntegrityError:
            raise ValueError(f"Username '{username}' sudah dipakai.")
        return cur.lastrowid


def set_custom_role(user_id: int, custom_role_id: int | None):
    """FITUR Role Custom: tempel/lepas akun 'staff' ke/dari role custom
    tertentu -- `custom_role_id=None` mengembalikannya ke set izin default
    tenant (validasi role='staff'/kepemilikan role_id adalah tanggung
    jawab pemanggil, lihat catatan tambah_user() di atas)."""
    if get_user(user_id) is None:
        raise ValueError("User tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("UPDATE users SET custom_role_id = ? WHERE id = ?", (custom_role_id, user_id))


def lepas_custom_role_dari_semua_user(custom_role_id: int):
    """FITUR Role Custom: dipanggil SEBELUM sebuah role dihapus
    (user_roles_db.delete_role()) -- SEMUA akun staff yang masih
    ditempelkan ke role itu otomatis balik ke set izin default tenant
    (custom_role_id = NULL), TIDAK PERNAH macet/terkunci karena role-nya
    tiba-tiba hilang (keputusan eksplisit Owner, lihat routers/
    pengaturan.py::hapus_user_role())."""
    with get_conn() as conn:
        conn.execute("UPDATE users SET custom_role_id = NULL WHERE custom_role_id = ?", (custom_role_id,))


def get_user_by_username(username: str, tenant_id: int = None):
    """BUGFIX (login 'kadang' gagal dengan kredensial benar): pencocokan
    username sekarang case-INSENSITIVE. Sebelumnya exact match case-sensitive
    -- kalau keyboard HP user kebetulan meng-kapitalkan huruf pertama
    (perilaku default autocapitalize banyak browser mobile, lihat juga
    perbaikan di frontend/js/pages/login.js), lookup ini tidak menemukan
    usernya sama sekali dan login ditolak walau password benar.
    `LOWER(username) = LOWER(?)` dipakai (bukan `COLLATE NOCASE`, kolasi
    khusus SQLite yang tidak dikenal PostgreSQL) supaya perbandingan case-
    insensitive-nya identik di kedua dialek database. `ORDER BY
    (username = ?) DESC` memprioritaskan exact match kalau kebetulan ada dua
    username yang hanya beda huruf besar/kecil (username tetap disimpan
    case-sensitive & unique persis seperti diketik saat dibuat -- ini HANYA
    mengubah cara mencari/mencocokkan saat login).

    FONDASI Multi-Tenant Phase 2.0: `tenant_id` opsional -- diisi untuk
    login dengan slug tenant eksplisit (pencarian di-scope KETAT ke tenant
    itu saja, lihat routers/auth_router.py). None (default) = perilaku
    LAMA, cari lintas tenant -- masih dipakai jalur darurat/bootstrap yang
    memang belum tahu tenant_id (lihat reset_atau_buat_admin_darurat())."""
    with get_conn() as conn:
        q = "SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND aktif = 1"
        params = [username]
        if tenant_id is not None:
            q += " AND tenant_id = ?"
            params.append(tenant_id)
        q += " ORDER BY (username = ?) DESC LIMIT 1"
        params.append(username)
        row = conn.execute(q, params).fetchone()
        return dict(row) if row else None


def cari_kandidat_login(username: str) -> list:
    """FONDASI Multi-Tenant Phase 2.0: SEMUA user aktif (lintas tenant)
    yang username-nya cocok (case-insensitive) -- dipakai login TANPA slug
    tenant eksplisit (lihat autentikasi() di bawah) untuk mendeteksi
    ambiguitas. Dua tenant BERBEDA boleh punya username yang sama persis
    (lihat UNIQUE(tenant_id, username) di init_auth_db()/postgres_schema.py,
    berubah dari UNIQUE(username) global sejak Phase 1) -- hasil fungsi ini
    NORMALNYA 0 atau 1 baris, >1 baris HANYA terjadi kalau memang ada
    tenant lain yang kebetulan memakai username yang sama."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND aktif = 1",
            (username,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_user(user_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_list(tenant_id: int = None):
    """FONDASI Multi-Tenant Phase 1: `tenant_id=None` (default) tetap
    mengembalikan SEMUA user lintas tenant -- perilaku LAMA, dipertahankan
    karena dipakai main.py::_bootstrap_admin_pertama() untuk cek "instalasi
    benar-benar baru" (harus lihat lintas tenant, bukan cuma satu tenant
    yang belum tentu ada). Endpoint API (routers/pengaturan.py) SELALU
    memanggil dengan tenant_id diisi eksplisit."""
    with get_conn() as conn:
        if tenant_id is not None:
            rows = conn.execute("SELECT * FROM users WHERE tenant_id = ? ORDER BY role, username", (tenant_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM users ORDER BY role, username").fetchall()
        return [dict(r) for r in rows]


def hitung_owner_aktif(tenant_id: int = None) -> int:
    """Jumlah akun Owner (role='admin') yang masih aktif -- dipakai untuk
    menegakkan aturan 'Owner terakhir tidak boleh dihapus atau diturunkan
    rolenya' (lihat pengaturan_user.py/routers/pengaturan.py).

    FONDASI Multi-Tenant Phase 1: `tenant_id` WAJIB diisi pemanggil di
    endpoint API -- tanpa ini, "Owner terakhir" akan terhitung LINTAS
    SELURUH tenant (bug: Tenant B tidak akan pernah bisa kehilangan Owner
    terakhirnya SENDIRI selama Tenant A manapun masih punya Owner aktif)."""
    with get_conn() as conn:
        if tenant_id is not None:
            row = conn.execute(
                "SELECT COUNT(*) AS jumlah FROM users WHERE role = 'admin' AND aktif = 1 AND tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS jumlah FROM users WHERE role = 'admin' AND aktif = 1"
            ).fetchone()
        return row["jumlah"]


def nonaktifkan_user(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET aktif = 0 WHERE id = ?", (user_id,))


def set_session_hash(user_id: int, session_hash: str | None):
    """Kontrol Sesi Login Satu-Device per Akun -- menulis hash token yang
    SEDANG aktif untuk akun ini (lihat auth.py::hash_token()). Dipanggil
    routers/auth_router.py::login() (setiap login menulis ULANG kolom ini,
    otomatis mencabut sesi/device sebelumnya) dan logout() (menulis None,
    supaya token yang di-logout manual juga benar-benar mati di backend)."""
    with get_conn() as conn:
        conn.execute("UPDATE users SET current_session_hash = ? WHERE id = ?", (session_hash, user_id))


def hapus_user(user_id: int):
    """Hapus PERMANEN (bukan Nonaktifkan) -- aman dilakukan kapan pun, tidak
    ada tabel lain yang menyimpan FK ke users.id (kolom 'dibuat_oleh'/
    'diajukan_oleh' dkk di seluruh modul murni TEXT username, bukan FK),
    jadi tidak ada risiko riwayat data hilang/rusak seperti pada Barber
    (yang diblokir kalau sudah punya transaksi/absensi)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# REVISI UI/UX: preferensi Dark/Light Mode disimpan PER AKUN (kolom
# users.tema, lihat tampilan_migrasi.py) -- setiap user (admin maupun
# barber) mengatur tema-nya sendiri, tidak memengaruhi user lain.
TEMA_VALID = {"terang", "gelap"}


def set_tema_user(user_id: int, tema: str):
    if tema not in TEMA_VALID:
        raise ValueError("Tema harus 'terang' atau 'gelap'.")
    with get_conn() as conn:
        conn.execute("UPDATE users SET tema = ? WHERE id = ?", (tema, user_id))


# FITUR Izin Lokasi APK Android (lihat lokasi_user_migrasi.py) -- "lokasi
# TERAKHIR diketahui" per akun, best-effort, dikirim SEKALI oleh
# android-app/ (native_app.js) begitu izin lokasi diberikan.
def set_lokasi_user(user_id: int, lat: float, lng: float):
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET lokasi_lat = ?, lokasi_lng = ?, lokasi_updated_at = ? WHERE id = ?",
            (lat, lng, now, user_id),
        )


def ganti_password(user_id: int, password_baru: str):
    if not password_baru or len(password_baru) < 4:
        raise ValueError("Password minimal 4 karakter.")
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(password_baru), user_id))


def reset_atau_buat_admin_darurat(username: str, password: str, tenant_id: int = None) -> str:
    """'Break-glass' pemulihan akses admin -- dipanggil HANYA lewat
    main.py._reset_admin_darurat(), yang sendiri hanya berjalan kalau dua
    environment variable (ADMIN_RESET_USERNAME/ADMIN_RESET_PASSWORD) diisi
    eksplisit oleh operator (mis. lewat dashboard Render), tidak pernah
    otomatis/diam-diam. Beda dengan _bootstrap_admin_pertama() yang HANYA
    jalan kalau tabel users benar-benar kosong (instalasi baru), fungsi ini
    dipakai untuk server yang SUDAH berjalan tapi admin-nya lupa kredensial.

    - Kalau `username` itu SUDAH ada (aktif ataupun sudah dinonaktifkan):
      password-nya di-reset, dipaksa role='admin' & aktif=1 (jadi juga
      memulihkan akun yang kebetulan sempat dinonaktifkan).
    - Kalau `username` itu BELUM ada: dibuat baru sebagai admin.

    `tenant_id` (BUGFIX audit, opsional lewat env var ADMIN_RESET_TENANT_ID
    di main.py) -- SEBELUMNYA pencarian username SAMA SEKALI tidak
    di-scope per tenant: (1) kalau username itu KEBETULAN ada di lebih
    dari satu tenant, fungsi lama diam-diam memilih salah satu tanpa
    operator sadar tenant mana yang sebenarnya ter-promosikan; (2) saat
    MEMBUAT admin darurat baru, baris yang di-INSERT tidak pernah mengisi
    tenant_id, menghasilkan admin dengan tenant_id=NULL -- melanggar
    invarian tambah_user() (hanya role='superadmin' yang boleh tenant_id
    NULL) dan admin itu langsung terkunci dari SEMUA endpoint tenant-scoped
    lewat get_current_tenant_id(). Sekarang: kalau `tenant_id` diisi,
    pencarian & pembuatan di-scope ketat ke tenant itu. Kalau TIDAK diisi
    (kompatibel mundur untuk deployment lama/single-tenant): username yang
    cocok di LEBIH DARI SATU tenant menolak dengan error eksplisit (minta
    operator mengisi ADMIN_RESET_TENANT_ID), dan MEMBUAT admin baru (belum
    ada baris sama sekali) WAJIB tenant_id eksplisit -- tidak lagi diam-diam
    membuat admin tanpa tenant.

    Baris user LAIN, dan seluruh tabel bisnis lain (barbers/transaksi/
    produk/pengeluaran/settings/dst di database.py), TIDAK disentuh sama
    sekali -- hanya SATU baris di tabel `users` yang diubah/ditambah.
    Return "direset" atau "dibuat" (bukan password) untuk keperluan log."""
    from datetime import datetime

    username = (username or "").strip()
    if not username:
        raise ValueError("Username untuk reset admin tidak boleh kosong.")
    if not password or len(password) < 4:
        raise ValueError("Password untuk reset admin minimal 4 karakter.")

    pw_hash = hash_password(password)
    with get_conn() as conn:
        if tenant_id is not None:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ? AND tenant_id = ?", (username, tenant_id)
            ).fetchone()
        else:
            kandidat = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchall()
            if len(kandidat) > 1:
                raise ValueError(
                    f"Username '{username}' ditemukan di lebih dari satu barbershop -- isi juga env var "
                    "ADMIN_RESET_TENANT_ID supaya jelas akun tenant mana yang dituju."
                )
            row = kandidat[0] if kandidat else None
        if row is None:
            if tenant_id is None:
                raise ValueError(
                    f"Username '{username}' belum ada di tenant manapun. Untuk MEMBUAT admin darurat baru, "
                    "isi juga env var ADMIN_RESET_TENANT_ID (admin baru wajib terkait ke satu barbershop)."
                )
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO users (username, password_hash, role, barber_id, aktif, tenant_id, created_at) "
                "VALUES (?, ?, 'admin', NULL, 1, ?, ?)",
                (username, pw_hash, tenant_id, now),
            )
            return "dibuat"
        conn.execute(
            "UPDATE users SET password_hash = ?, role = 'admin', barber_id = NULL, aktif = 1 WHERE id = ?",
            (pw_hash, row["id"]),
        )
        return "direset"


def autentikasi(username: str, password: str, tenant_id: int = None):
    """Return dict user (tanpa password_hash) kalau username+password benar
    untuk TEPAT SATU tenant, None kalau salah/tidak ditemukan.

    FONDASI Multi-Tenant Phase 2.0: `tenant_id` opsional.
    - Diisi (login dengan slug tenant eksplisit dari form Login): pencarian
      di-scope KETAT ke tenant itu saja lewat get_user_by_username().
    - None (default, login TANPA slug -- kasus paling umum, termasuk 100%
      instalasi yang cuma punya satu tenant): cari SEMUA kandidat lintas
      tenant lewat cari_kandidat_login(), lalu verifikasi password
      terhadap SETIAP kandidat (bukan cuma yang pertama ketemu seperti
      Phase 1). Kalau TEPAT SATU yang password-nya cocok, login berhasil
      seperti biasa. Kalau LEBIH DARI SATU yang password-nya SAMA-SAMA
      cocok (dua tenant BERBEDA kebetulan pakai username+password
      identik -- sangat jarang, tapi constraint database mengizinkan ini
      terjadi), return LIST kandidat (bukan dict/None) sebagai sinyal
      "ambigu, minta pengguna pilih tenant" ke pemanggil (lihat
      routers/auth_router.py::login()) -- PENTING: ambiguitas ini HANYA
      pernah terungkap ke pemanggil yang SUDAH membuktikan tahu password
      yang benar untuk kandidat-kandidat itu; percobaan dengan password
      salah tetap dapat None biasa, tidak pernah membocorkan bahwa ada
      lebih dari satu tenant dengan username itu."""
    if tenant_id is not None:
        user = get_user_by_username(username, tenant_id=tenant_id)
        if user is None or not verify_password(password, user["password_hash"]):
            return None
        user = dict(user)
        user.pop("password_hash")
        return user

    kandidat = cari_kandidat_login(username)
    cocok = [u for u in kandidat if verify_password(password, u["password_hash"])]
    # BUGFIX (audit, timing side-channel): dulu latensi total di sini
    # berbanding lurus dengan JUMLAH kandidat (tenant berbeda yang
    # kebetulan pakai username sama) -- secara teori bisa dipakai menebak
    # lewat pengukuran waktu apakah suatu username eksis di lebih dari
    # satu tenant. Kalau TEPAT SATU kandidat, tambahkan SATU verifikasi
    # dummy (terhadap hash yang TIDAK PERNAH bisa cocok dengan password
    # apa pun, dibuat sekali per proses) supaya waktunya tidak lagi mudah
    # dibedakan dari kasus dua kandidat -- dijaga sesempit ini (bukan
    # padding ke angka besar) supaya TIDAK menambah latensi login normal
    # (kasus 0 kandidat = username salah, sudah cepat & tetap begitu).
    if len(kandidat) == 1:
        verify_password(password, _HASH_DUMMY_ANTI_TIMING)
    if not cocok:
        return None
    if len(cocok) > 1:
        return cocok
    user = dict(cocok[0])
    user.pop("password_hash")
    return user
