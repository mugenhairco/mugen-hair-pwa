"""
auth.py
=======
Login berbasis TOKEN untuk FastAPI (terpisah dari auth_db.py yang isinya
CRUD tabel `users` + hash password). File ini yang tahu soal HTTP:
membuat token saat login, dan menyediakan dependency FastAPI untuk
memvalidasi token + membatasi akses per role (admin / barber) di semua
router lain.

Token dibuat dengan itsdangerous.URLSafeTimedSerializer (bukan JWT) supaya
tidak perlu library tambahan selain yang sudah ada di requirements.txt.
Isinya cuma user_id, jadi kalau perlu dicabut cukup nonaktifkan user di
tabel `users` (auth_db.nonaktifkan_user) — token lama otomatis ditolak
karena get_current_user selalu re-check ke database, bukan cuma percaya isi token.
"""

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import auth_db

# SECRET_KEY WAJIB diisi lewat environment variable saat deploy (lihat render.yaml).
# Default di bawah ini HANYA untuk development lokal.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-jangan-dipakai-di-produksi")
TOKEN_MAX_AGE_DETIK = 60 * 60 * 24 * 14  # 14 hari

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="mugen-hair-auth")

_bearer = HTTPBearer(auto_error=False)


def buat_token(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id})


def _decode_token(token: str) -> int:
    try:
        data = _serializer.loads(token, max_age=TOKEN_MAX_AGE_DETIK)
    except SignatureExpired:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesi login sudah kedaluwarsa, silakan login lagi.")
    except BadSignature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tidak valid.")
    return data["user_id"]


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """Dependency dasar: wajib login (role apa saja). Selalu ambil data user
    TERBARU dari database (bukan dari isi token) supaya kalau user dinonaktifkan
    atau role-nya diubah, efeknya langsung terlihat tanpa harus tunggu token expired."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Belum login.")
    user_id = _decode_token(credentials.credentials)
    user = auth_db.get_user(user_id)
    if user is None or not user.get("aktif"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Akun tidak aktif atau tidak ditemukan.")
    user.pop("password_hash", None)
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khusus Owner (admin).")
    return user


def require_barber(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "barber":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khusus akun Barber.")
    return user


def require_owner_or_staff(user: dict = Depends(get_current_user)) -> dict:
    """'admin' (Owner, akses penuh) atau 'staff' (Admin, akses dibatasi hak
    akses yang diatur Owner lewat Setting > Hak Akses Admin -- lihat
    permissions.py). Dipakai sebagai dasar untuk require_permission() di
    bawah; endpoint yang butuh Owner MURNI (tanpa pengecualian apa pun,
    mis. menu Hak Akses Admin itu sendiri) tetap memakai require_admin di atas."""
    if user["role"] not in ("admin", "staff"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khusus Owner atau Admin.")
    return user


def require_permission(key: str):
    """Dependency factory: Owner ('admin') SELALU lolos tanpa syarat (akses
    penuh, sesuai spesifikasi -- tidak pernah dibatasi hak akses apa pun).
    'staff' hanya lolos kalau Owner sudah mengaktifkan permission `key` ini
    lewat Setting > Hak Akses Admin. 'barber' selalu ditolak (permission
    Admin tidak berlaku untuk akun Barber)."""
    def _dep(user: dict = Depends(require_owner_or_staff)) -> dict:
        if user["role"] == "admin":
            return user
        import permissions  # import lokal: hindari import siklik (permissions.py -> database.py)
        if not permissions.has(key):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                 detail="Admin tidak punya izin untuk aksi ini. Hubungi Owner.")
        return user
    return _dep
