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
    atau role-nya diubah, efeknya langsung terlihat tanpa harus tunggu token expired.

    FONDASI Multi-Tenant Phase 1: `user["tenant_id"]` ikut terbawa dari baris
    yang sama (SELECT * di auth_db.get_user(), tidak perlu query tambahan)
    -- inilah SATU-SATUNYA titik di seluruh aplikasi tempat tenant aktif
    di-resolve untuk endpoint ber-login, lihat get_current_tenant_id() di
    bawah. Tenant yang di-nonaktifkan (lihat tenant_db.py, kolom `status`)
    langsung menolak SEMUA request user-nya di sini, sama seperti akun user
    yang di-nonaktifkan -- efeknya konsisten & langsung terlihat tanpa
    tunggu token expired, pola yang sama dengan pengecekan `user.aktif`."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Belum login.")
    user_id = _decode_token(credentials.credentials)
    user = auth_db.get_user(user_id)
    if user is None or not user.get("aktif"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Akun tidak aktif atau tidak ditemukan.")
    if user.get("tenant_id") is not None:
        import tenant_db  # import lokal: hindari import siklik (tenant_db.py -> database.py)
        tenant = tenant_db.get_tenant(user["tenant_id"])
        if tenant is None or tenant["status"] != "aktif":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                 detail="Akun barbershop ini sedang tidak aktif. Hubungi penyedia layanan.")
    user.pop("password_hash", None)
    return user


def get_current_tenant_id(user: dict = Depends(get_current_user)) -> int:
    """Dependency tenant-resolution UTAMA untuk seluruh Dashboard PWA (§4
    rancangan audit) -- tenant SELALU diturunkan dari sesi login yang
    sedang aktif, TIDAK PERNAH dari parameter/header yang bisa disuntik
    client. Endpoint yang butuh menyaring data per-tenant memakai dependency
    ini (bukan membaca user["tenant_id"] manual di tiap endpoint) supaya ada
    SATU titik yang menolak tegas kalau suatu saat ada akun tanpa tenant_id
    (seharusnya tidak pernah terjadi lewat alur normal aplikasi)."""
    if user.get("tenant_id") is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="Akun ini belum dikaitkan ke barbershop mana pun.")
    return user["tenant_id"]


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


def resolve_tenant_hibrid(credentials: HTTPAuthorizationCredentials = Depends(_bearer),
                           tenant: str | None = None) -> int:
    """Dipakai endpoint yang PUBLIC tapi JUGA dipanggil dari sisi SUDAH LOGIN
    lewat endpoint yang SAMA PERSIS -- mis. GET /pengaturan/identitas,
    /pengaturan/logo, /website/content/*, /website/gallery* dipakai baik
    oleh halaman Login/booking publik (belum ada token) MAUPUN oleh menu
    Setting/Website Content setelah login (SUDAH ada token, tapi frontend-
    nya tidak dan tidak perlu tahu slug tenant-nya sendiri untuk membaca
    data miliknya sendiri).

    Kalau ada token valid, tenant diambil dari SESI LOGIN (prioritas --
    kalau tidak, Setting Tenant B akan diam-diam menampilkan data Tenant
    default, bug nyata yang ditemukan lewat pengujian dua-tenant Phase 1).
    Kalau tidak ada token (pengunjung publik sungguhan), fallback ke
    resolve_tenant_publik() (query string `?tenant=<slug>` / tenant
    default) -- endpoint TETAP bisa diakses tanpa login sama sekali,
    perilaku publik tidak berubah."""
    if credentials is not None:
        try:
            user_id = _decode_token(credentials.credentials)
            user = auth_db.get_user(user_id)
            if user is not None and user.get("aktif") and user.get("tenant_id") is not None:
                return user["tenant_id"]
        except HTTPException:
            pass
    return resolve_tenant_publik(tenant)


def resolve_tenant_publik(tenant: str | None = None) -> int:
    """FONDASI Multi-Tenant Phase 1: dependency resolusi tenant untuk SELURUH
    endpoint PUBLIC (tanpa sesi login -- halaman Login/booking /book) yang
    perlu tahu tenant mana yang aktif. Lihat tenant_db.cari_tenant_publik()
    untuk penjelasan lengkap kenapa mekanisme ini (query string
    `?tenant=<slug>`, BUKAN subdomain/custom domain -- custom domain
    eksplisit di luar cakupan Phase 1) dipilih. Query string kosong =
    tenant default, SATU-SATUNYA tenant yang ada di deployment single-tenant
    SEKARANG -- frontend yang belum dimodifikasi TIDAK PERNAH mengirim
    parameter ini, jadi perilakunya 100% sama seperti sebelum Phase 1."""
    import tenant_db  # import lokal: hindari import siklik (tenant_db.py -> database.py)
    t = tenant_db.cari_tenant_publik(tenant)
    if t is None or t["status"] != "aktif":
        raise HTTPException(status_code=404, detail="Barbershop tidak ditemukan.")
    return t["id"]


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
        if not permissions.has(key, tenant_id=user.get("tenant_id")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                 detail="Admin tidak punya izin untuk aksi ini. Hubungi Owner.")
        return user
    return _dep
