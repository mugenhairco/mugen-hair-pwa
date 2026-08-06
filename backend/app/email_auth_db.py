"""email_auth_db.py — FITUR Email, Verifikasi Email, Lupa Kata Sandi: akses
tabel `email_verification_tokens`/`password_reset_tokens` + kolom email
baru di `users` (skema lihat email_auth_migrasi.py/postgres_schema.py)
=============================================================================
Modul TIPIS, murni CRUD -- SENGAJA tidak memanggil email_service.py sama
sekali (pola sama seperti tenant_db.py yang tidak memanggil apa pun di
luar CRUD-nya sendiri) -- pemanggil (routers/tenant_registration.py,
routers/email_auth.py) yang merangkai "buat token" + "kirim email" +
tangani kegagalan pengiriman, supaya modul ini tetap murni & mudah
diuji terpisah dari jaringan.

Token dibuat dengan `secrets.token_urlsafe` (acak kriptografis, TIDAK
terkait/tidak menyentuh mekanisme token SESI LOGIN di auth.py sama
sekali) -- SATU KALI PAKAI untuk verifikasi email MAUPUN reset password
(kolom `used_at` di kedua tabel), dan kedaluwarsa lewat `expires_at`
untuk keduanya."""

import secrets
from datetime import datetime, timedelta

from auth_db import get_conn, hash_password

MASA_BERLAKU_VERIFIKASI_JAM = 24
MASA_BERLAKU_RESET_JAM = 1


def _sekarang_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _kadaluwarsa_iso(jam: int) -> str:
    return (datetime.now() + timedelta(hours=jam)).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# EMAIL akun (kolom users.email/email_verified/blokir_sampai_verifikasi)
# ---------------------------------------------------------------------------

def get_user_by_email(email: str):
    """Pencarian GLOBAL lintas tenant (case-insensitive) -- SESUAI kebutuhan
    Lupa Kata Sandi (pengguna hanya tahu emailnya, belum tentu tahu/ingat
    slug tenant/toko mana). Hanya user AKTIF yang dikembalikan (user
    dinonaktifkan Owner tidak boleh bisa reset password lewat jalur ini)."""
    email = (email or "").strip()
    if not email:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = LOWER(?) AND aktif = 1", (email,)
        ).fetchone()
        return dict(row) if row else None


def set_email_user(user_id: int, email: str):
    """Set/ubah email akun -- SELALU mereset email_verified ke 0 (email
    BARU wajib diverifikasi ulang, walau email SEBELUMNYA sudah
    terverifikasi) -- TIDAK PERNAH mengubah blokir_sampai_verifikasi
    (HANYA diset oleh alur Registrasi mandiri saat akun dibuat, lihat
    email_auth_migrasi.py) -- akun lama yang menambah email lewat
    Pengaturan > Profil TIDAK PERNAH diblokir login karenanya."""
    email = (email or "").strip()
    if not email:
        raise ValueError("Email tidak boleh kosong.")
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET email = ?, email_verified = 0 WHERE id = ?", (email, user_id)
        )


def tandai_blokir_sampai_verifikasi(user_id: int):
    """HANYA dipanggil routers/tenant_registration.py::register() -- lihat
    catatan blokir_sampai_verifikasi di email_auth_migrasi.py."""
    with get_conn() as conn:
        conn.execute("UPDATE users SET blokir_sampai_verifikasi = 1 WHERE id = ?", (user_id,))


# ---------------------------------------------------------------------------
# VERIFIKASI EMAIL
# ---------------------------------------------------------------------------

def buat_token_verifikasi(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO email_verification_tokens (user_id, token, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (user_id, token, _kadaluwarsa_iso(MASA_BERLAKU_VERIFIKASI_JAM), _sekarang_iso()),
        )
    return token


def verifikasi_email_dengan_token(token: str) -> dict:
    """Sekali pakai (kolom `used_at`, SAMA seperti token reset password) --
    return {"status": ..., "user": dict|None}, TIGA kemungkinan status:
    - "berhasil": token valid & belum kedaluwarsa/dipakai -- ditandai
      used_at DALAM transaksi yang sama, email_verified=1 &
      blokir_sampai_verifikasi dilepas.
    - "sudah_dipakai": token itu SAH tapi SUDAH pernah dipakai sebelumnya
      -- BUKAN dianggap error ke pengguna (lihat routers/auth_router.py),
      cukup pesan "sudah diverifikasi sebelumnya" -- kasus nyata: klik
      ulang link yang sama (dua tab, email client yang me-render ulang).
    - "tidak_valid": token tidak ada sama sekali ATAU sudah kedaluwarsa.
    Pengecekan ulang di DALAM fungsi ini (bukan mengandalkan pemanggil
    sudah tahu token valid) mencegah race condition token yang SAMA
    dipakai dua kali nyaris bersamaan, pola sama seperti pakai_token_reset()."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM email_verification_tokens WHERE token = ? AND expires_at > ?",
            (token, _sekarang_iso()),
        ).fetchone()
        if row is None:
            return {"status": "tidak_valid", "user": None}
        if row["used_at"] is not None:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
            return {"status": "sudah_dipakai", "user": dict(user) if user else None}
        conn.execute(
            "UPDATE email_verification_tokens SET used_at = ? WHERE token = ?", (_sekarang_iso(), token)
        )
        conn.execute(
            "UPDATE users SET email_verified = 1, blokir_sampai_verifikasi = 0 WHERE id = ?",
            (row["user_id"],),
        )
        user = conn.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        return {"status": "berhasil", "user": dict(user) if user else None}


# ---------------------------------------------------------------------------
# LUPA KATA SANDI
# ---------------------------------------------------------------------------

def buat_token_reset(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO password_reset_tokens (user_id, token, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (user_id, token, _kadaluwarsa_iso(MASA_BERLAKU_RESET_JAM), _sekarang_iso()),
        )
    return token


def ambil_reset_token_valid(token: str):
    """dict {user_id, ...} kalau token ADA, belum kedaluwarsa, DAN belum
    pernah dipakai (used_at IS NULL) -- None kalau salah satu syarat itu
    tidak terpenuhi (TIDAK membedakan alasannya ke pemanggil, sesuai
    prinsip pesan generik yang sama dipakai lupa_password())."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token = ? AND expires_at > ? AND used_at IS NULL",
            (token, _sekarang_iso()),
        ).fetchone()
        return dict(row) if row else None


def pakai_token_reset(token: str, password_baru: str):
    """Tandai token SEKALI PAKAI (used_at) + ganti password dalam SATU
    transaksi -- raise ValueError kalau token sudah tidak valid (dicek
    ulang di sini, BUKAN cuma mengandalkan pemanggil sudah memvalidasi
    lewat ambil_reset_token_valid() -- mencegah race condition token yang
    SAMA dipakai dua kali nyaris bersamaan)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token = ? AND expires_at > ? AND used_at IS NULL",
            (token, _sekarang_iso()),
        ).fetchone()
        if row is None:
            raise ValueError("Link reset password ini tidak valid atau sudah kedaluwarsa.")
        if not password_baru or len(password_baru) < 4:
            raise ValueError("Password minimal 4 karakter.")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password_baru), row["user_id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE token = ?", (_sekarang_iso(), token)
        )
