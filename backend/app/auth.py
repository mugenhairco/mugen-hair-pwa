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

from fastapi import Depends, HTTPException, Request, status
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
    # BUGFIX: sebelumnya hanya mengecek `tenant_id is not None` -- secara
    # PRAKTIK tetap benar untuk superadmin yang dibuat lewat jalur normal
    # (tambah_user() MEWAJIBKAN tenant_id=None untuk role ini), tapi
    # bergantung diam-diam pada invarian itu, bukan pengecekan role
    # eksplisit. Superadmin adalah akun PLATFORM (pengelola SELURUH tenant,
    # lihat require_superadmin() di bawah) -- TIDAK BOLEH pernah diblokir
    # oleh status tenant mana pun, jadi role dicek LANGSUNG di sini supaya
    # tidak bergantung pada invarian data.
    if user["role"] != "superadmin" and user.get("tenant_id") is not None:
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


def require_superadmin(user: dict = Depends(get_current_user)) -> dict:
    """FONDASI Multi-Tenant Phase 2.1: Super Admin Dashboard -- akun
    `role='superadmin'` (selalu `tenant_id=None`, lihat auth_db.tambah_user())
    mengelola SELURUH tenant. get_current_user() di atas TIDAK menjalankan
    pengecekan tenant aktif untuk akun ini (tenant_id None), dan
    get_current_tenant_id() menolak akun ini dari SEMUA endpoint ber-scope
    tenant biasa -- dua sifat itu bersama-sama memastikan superadmin dan
    akun tenant biasa saling eksklusif dari sisi endpoint yang bisa diakses."""
    if user["role"] != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Khusus Super Admin.")
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


def resolve_tenant_hibrid(request: Request, credentials: HTTPAuthorizationCredentials = Depends(_bearer),
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
    return resolve_tenant_publik(request, tenant)


def resolve_tenant_publik(request: Request, tenant: str | None = None) -> int:
    """FONDASI Multi-Tenant Phase 1: dependency resolusi tenant untuk SELURUH
    endpoint PUBLIC (tanpa sesi login -- halaman Login/booking /book) yang
    perlu tahu tenant mana yang aktif. Lihat tenant_db.cari_tenant_publik()
    untuk penjelasan lengkap kenapa mekanisme ini (query string
    `?tenant=<slug>`, BUKAN subdomain/custom domain -- custom domain
    eksplisit di luar cakupan Phase 1) dipilih. Query string kosong =
    tenant default, SATU-SATUNYA tenant yang ada di deployment single-tenant
    SEKARANG -- frontend yang belum dimodifikasi TIDAK PERNAH mengirim
    parameter ini, jadi perilakunya 100% sama seperti sebelum Phase 1.

    FONDASI Multi-Tenant Phase 2.0: kalau `tenant` (query string, prioritas
    utama -- tidak berubah) kosong, fallback ke
    `request.state.requested_tenant_slug` yang sudah di-resolve
    TenantResolutionMiddleware dari header `X-Tenant-Slug` atau subdomain
    (lihat tenant_middleware.py) -- deployment yang belum memakai keduanya
    (termasuk deployment produksi saat ini) selalu dapat None dari situ,
    jadi perilakunya tetap identik sebelum Phase 2.0."""
    import tenant_db  # import lokal: hindari import siklik (tenant_db.py -> database.py)
    slug = tenant or getattr(request.state, "requested_tenant_slug", None)
    t = tenant_db.cari_tenant_publik(slug)
    if t is None or t["status"] != "aktif":
        raise HTTPException(status_code=404, detail="Barbershop tidak ditemukan.")
    return t["id"]


def resolve_tenant_untuk_branding(request: Request, credentials: HTTPAuthorizationCredentials = Depends(_bearer),
                                   tenant: str | None = None) -> int | None:
    """FONDASI Multi-Tenant Phase 2.2 (Tenant Branding & Platform Branding):
    dependency KHUSUS endpoint publik GET /api/tenant/branding -- BEDA
    dengan resolve_tenant_hibrid()/resolve_tenant_publik() di atas (dipakai
    endpoint LAIN, TIDAK diubah sama sekali di sini, supaya tidak ada
    breaking change) dalam SATU hal penting: kalau tidak ada sinyal tenant
    APA PUN, fungsi ini return None (artinya "pakai branding platform") --
    BUKAN diam-diam jatuh ke tenant default pertama seperti
    resolve_tenant_publik() (perilaku ITU sengaja dipertahankan apa adanya
    untuk halaman publik /book dkk, supaya kompatibilitas mundur terjaga).

    Prioritas:
    1. Sesi login valid (token benar, akun aktif) -> `user["tenant_id"]`
       APA ADANYA -- integer untuk Owner/Admin/Barber biasa (branding toko
       sendiri, TIDAK BISA disuntik lewat query string manapun), atau None
       untuk superadmin (branding platform, sesuai spesifikasi "Super Admin
       tetap branding platform, bukan branding tenant tertentu") -- role
       'superadmin' SELALU dipetakan ke None secara EKSPLISIT di sini
       (BUKAN cuma mengandalkan `user["tenant_id"]` yang kebetulan NULL),
       supaya branding platform tetap benar walau baris user di database
       ternyata korup/tidak konsisten dengan invarian "superadmin tidak
       terikat tenant" (mis. tenant_id ter-isi lewat jalur lain di luar
       auth_db.tambah_user(), yang seharusnya menolak kombinasi itu -- lihat
       BUGFIX Branding Super Admin di frontend/js/brand.js untuk gejala
       yang PERSIS ditimbulkan bug data semacam ini).
    2. Tidak ada sesi valid (pengunjung anonim / halaman Login belum
       submit) -> `tenant` (query string eksplisit, TERMASUK slug yang
       "diingat" browser dari login sebelumnya -- lihat frontend/js/
       brand.js, murni untuk TAMPILAN, bukan otorisasi apa pun jadi aman
       dikirim proaktif) -> fallback slug dari middleware (header
       X-Tenant-Slug/subdomain, lihat tenant_middleware.py) -> None
       (branding platform) kalau semuanya kosong/tidak ditemukan/nonaktif."""
    if credentials is not None:
        try:
            user_id = _decode_token(credentials.credentials)
            user = auth_db.get_user(user_id)
            if user is not None and user.get("aktif"):
                if user.get("role") == "superadmin":
                    return None
                return user.get("tenant_id")
        except HTTPException:
            pass
    import tenant_db  # import lokal: hindari import siklik (tenant_db.py -> database.py)
    slug = tenant or getattr(request.state, "requested_tenant_slug", None)
    if not slug:
        return None
    # FITUR URL Booking Publik per Tenant: fallback ke booking_slug kalau
    # `slug` (dashboard/staff) tidak ketemu -- SATU-SATUNYA perubahan di
    # sini, supaya Logo/Nama Bisnis/dst tetap tampil benar begitu customer
    # membuka subdomain booking_slug (lihat tenant_guard.js, memakai
    # endpoint ini untuk memutuskan "Tenant Tidak Ditemukan" atau tidak).
    t = tenant_db.get_tenant_by_slug_atau_booking_slug(slug)
    if t is None or t["status"] != "aktif":
        return None
    return t["id"]


def require_feature(kode: str):
    """Dependency factory: FONDASI Multi-Tenant Phase 4 lanjutan (Feature
    Gating per Paket) -- BEDA SUMBU dari require_permission() di bawah
    (izin_* = peran DALAM satu tenant, ini = fitur yang TERMASUK di paket
    TENANT itu sendiri). Superadmin (akun platform, tidak terikat tenant
    mana pun) SELALU lolos tanpa syarat -- lihat feature_access.py untuk
    penjelasan lengkap & daftar kode fitur yang sungguhan ditegakkan.

    Dipasang sebagai dependency TAMBAHAN (bukan pengganti) di endpoint yang
    sudah ada -- signature endpoint tetap punya `user: dict = Depends(...)`
    aslinya (get_current_user/require_owner_or_staff/dst, TIDAK diubah,
    supaya pembatasan role yang sudah ada tidak ikut berubah), ditambah satu
    parameter baru `Depends(require_feature("kode_fitur"))` yang HANYA
    menegakkan gate fitur, dipanggil sama seperti require_permission()."""
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] == "superadmin":
            return user
        import feature_access  # import lokal: hindari import siklik (feature_access.py -> database.py)
        tenant_id = user.get("tenant_id")
        if tenant_id is None or not feature_access.tenant_has_feature(tenant_id, kode):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
                "message": "Fitur ini tidak tersedia di paket Anda saat ini. Upgrade paket untuk menggunakannya.",
                "feature": kode,
                "upgrade_required": True,
            })
        return user
    return _dep


def require_permission(key: str):
    """Dependency factory: Owner ('admin') SELALU lolos tanpa syarat (akses
    penuh, sesuai spesifikasi -- tidak pernah dibatasi hak akses apa pun).
    'staff' hanya lolos kalau Owner sudah mengaktifkan permission `key` ini
    lewat Setting > Hak Akses User. 'barber' selalu ditolak (permission
    Admin tidak berlaku untuk akun Barber).

    FITUR Role Custom: `user.get("custom_role_id")` (kolom baru di tabel
    `users`, lihat user_roles_db.py) diteruskan apa adanya ke
    permissions.has() -- None (staff belum ditempelkan ke role custom
    mana pun, termasuk SEMUA staff yang sudah ada sebelum fitur ini) tetap
    memakai set izin default tenant PERSIS seperti sebelumnya, 100%
    kompatibel mundur."""
    def _dep(user: dict = Depends(require_owner_or_staff)) -> dict:
        if user["role"] == "admin":
            return user
        import permissions  # import lokal: hindari import siklik (permissions.py -> database.py)
        if not permissions.has(key, tenant_id=user.get("tenant_id"), role_id=user.get("custom_role_id")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                 detail="Admin tidak punya izin untuk aksi ini. Hubungi Owner.")
        return user
    return _dep
