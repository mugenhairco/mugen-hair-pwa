"""wa_otp_db.py — FITUR Lupa Kata Sandi Karyawan (Barber) via OTP WhatsApp
=============================================================================
PERMINTAAN OWNER: akun karyawan (role='barber') sebelumnya HANYA bisa minta
Owner mereset password-nya (lihat routers/auth_router.py::lupa_password(),
jalur email -- KHUSUS akun Owner/'admin'). Modul ini menambah jalur BARU,
KHUSUS barber, lewat OTP 6 digit yang dikirim ke WhatsApp PRIBADI barber itu
sendiri (barbers.nomor_whatsapp) dari WA toko (whatsapp_service.py, token
Fonnte milik tenant) -- TIDAK menyentuh/mengganti jalur email Owner yang
sudah ada sama sekali.

BEDA PRINSIP dari email_auth_db.py (token reset password Owner, acak
panjang `secrets.token_urlsafe(32)`, aman disimpan plaintext karena
entropinya sangat tinggi): OTP di sini sengaja PENDEK (6 digit, mudah
diketik manual dari WhatsApp) -- entropinya rendah (1 juta kemungkinan),
jadi dilindungi lapis TAMBAHAN yang token panjang tidak perlu:
1. Kadaluwarsa SANGAT PENDEK (lihat MASA_BERLAKU_OTP_MENIT).
2. Batas percobaan salah (lihat MAKS_PERCOBAAN_GAGAL) -- lewat batas itu,
   OTP (walau belum kadaluwarsa) dianggap tidak valid lagi, harus minta baru.
3. HANYA SATU OTP aktif per user kapan pun -- minta OTP baru otomatis
   membatalkan yang lama (buat_otp() di bawah), supaya tidak ada OTP lama
   yang "menumpuk" dan membingungkan mana yang masih berlaku.
4. Rate limit di level pemanggil (routers/auth_router.py, pakai
   rate_limit_db.py) -- membatasi SEBERAPA SERING OTP baru boleh diminta
   untuk satu username, di luar cakupan modul ini sendiri."""

import secrets
from datetime import datetime, timedelta

from auth_db import get_conn, hash_password

MASA_BERLAKU_OTP_MENIT = 5
MAKS_PERCOBAAN_GAGAL = 5

_PESAN_OTP_TIDAK_VALID = "Kode OTP tidak valid atau sudah kedaluwarsa. Silakan minta kode baru."


def init_wa_otp_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_otp_reset (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                kode            TEXT NOT NULL,
                percobaan_gagal INTEGER NOT NULL DEFAULT 0,
                expires_at      TEXT NOT NULL,
                used_at         TEXT,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def _sekarang_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _kadaluwarsa_iso() -> str:
    return (datetime.now() + timedelta(minutes=MASA_BERLAKU_OTP_MENIT)).isoformat(timespec="seconds")


def buat_otp(user_id: int) -> str:
    """Generate kode OTP 6 digit BARU untuk user ini. Menghapus dulu SEMUA
    OTP lama milik user ini yang masih berpotensi berlaku (belum dipakai --
    kadaluwarsa atau tidak, sekalian dibuang supaya tabel ini tidak
    menumpuk baris basi) -- SELALU hanya SATU OTP yang sah di satu waktu
    per user, pola sama tujuannya dengan SATU sesi login aktif
    (current_session_hash di auth_db.py), walau mekanismenya beda."""
    kode = f"{secrets.randbelow(900000) + 100000}"
    with get_conn() as conn:
        conn.execute("DELETE FROM wa_otp_reset WHERE user_id = ? AND used_at IS NULL", (user_id,))
        conn.execute(
            "INSERT INTO wa_otp_reset (user_id, kode, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (user_id, kode, _kadaluwarsa_iso(), _sekarang_iso()),
        )
    return kode


def verifikasi_dan_pakai_otp(user_id: int, kode: str, password_baru: str) -> None:
    """Raise ValueError (pesan SAMA PERSIS, `_PESAN_OTP_TIDAK_VALID`) untuk
    SEMUA kasus "OTP tidak bisa dipakai" -- tidak ada OTP aktif sama
    sekali, sudah kedaluwarsa, sudah lewat batas percobaan gagal -- supaya
    pengguna tidak mendapat sinyal tambahan yang membedakan kasus-kasus
    itu. Kode yang SALAH (tapi OTP-nya sendiri masih berlaku & belum lewat
    batas percobaan) dapat pesan "Kode OTP salah." TERSENDIRI -- ini AMAN
    beda karena pengguna di titik ini SUDAH terbukti tahu username+nomor
    WA yang benar (lolos lupa_password_wa() di routers/auth_router.py
    sebelum OTP ini dikirim), jadi membedakan "kode salah" di sini bukan
    celah enumerasi akun baru, cuma membantu mengetik ulang.

    Mengganti password + mencabut sesi aktif (current_session_hash=NULL)
    DALAM TRANSAKSI YANG SAMA dengan menandai OTP dipakai -- pola identik
    email_auth_db.py::pakai_token_reset() (lihat catatan keamanan lengkap
    di sana: jalur lupa password adalah skenario akun DIDUGA dibajak,
    sesi lama WAJIB ikut dicabut, bukan dibiarkan valid sampai basi
    sendiri)."""
    # BUGFIX (ditemukan lewat smoke test, SEBELUM pernah di-commit/push):
    # get_conn() HANYA conn.commit() kalau block `with` ini keluar TANPA
    # exception (lihat database.py::get_conn()) -- raise ValueError() di
    # DALAM block yang sama dengan UPDATE percobaan_gagal di atas akan
    # ikut me-rollback UPDATE itu, jadi counter-nya TIDAK PERNAH benar2
    # tersimpan (percobaan_gagal diam-diam selalu balik ke nilai sebelum
    # panggilan ini, celah ini membuat batas 5x salah coba TIDAK PERNAH
    # benar2 berlaku). Diperbaiki: tulis dulu (kalau perlu) sampai block
    # INI selesai NORMAL (biar ter-commit), baru raise di LUAR block-nya.
    kode = (kode or "").strip()
    cocok = False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM wa_otp_reset WHERE user_id = ? AND used_at IS NULL AND expires_at > ? "
            "ORDER BY id DESC LIMIT 1",
            (user_id, _sekarang_iso()),
        ).fetchone()
        if row is None:
            tidak_ada_otp_aktif = True
        else:
            row = dict(row)
            tidak_ada_otp_aktif = row["percobaan_gagal"] >= MAKS_PERCOBAAN_GAGAL
            if not tidak_ada_otp_aktif:
                cocok = bool(kode) and secrets.compare_digest(kode, row["kode"])
                if not cocok:
                    conn.execute(
                        "UPDATE wa_otp_reset SET percobaan_gagal = percobaan_gagal + 1 WHERE id = ?",
                        (row["id"],),
                    )
    if row is None or tidak_ada_otp_aktif:
        raise ValueError(_PESAN_OTP_TIDAK_VALID)
    if not cocok:
        raise ValueError("Kode OTP salah.")
    if not password_baru or len(password_baru) < 4:
        raise ValueError("Password minimal 4 karakter.")
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, current_session_hash = NULL WHERE id = ?",
            (hash_password(password_baru), user_id),
        )
        conn.execute("UPDATE wa_otp_reset SET used_at = ? WHERE id = ?", (_sekarang_iso(), row["id"]))
