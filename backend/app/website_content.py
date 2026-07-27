"""
website_content.py — CMS "Website Content" untuk halaman publik /book (PR 1)
=============================================================================
Owner-only (lihat routers/website.py: require_admin di semua endpoint tulis,
BUKAN lewat sistem izin permissions.py -- staff tidak pernah bisa diberi
akses ke sini, sama seperti tab Komisi/Bonus Service/Hak Akses Admin di
Setting). Mengikuti pola pengaturan_identitas.py PERSIS:
- Field skalar (teks/link) -> tabel `settings` key-value yang sudah ada.
- Field gambar/video tunggal (Hero Video, Foto About) -> helper generik
  simpan/hapus/get-path, pola sama seperti _simpan_gambar() di
  pengaturan_identitas.py (direplikasi di sini, bukan di-import silang,
  konsisten dengan gaya modul lain yang tidak saling pakai helper privat).

Field yang SUDAH ADA sengaja TIDAK diduplikasi di sini, langsung dipakai
lewat pengaturan_identitas.get_identitas() / booking_db.get_booking_settings()
oleh routers/website.py saat menyusun payload gabungan GET /api/website/content:
- Logo Header, Hero Image, Nama Brand, Tagline, Alamat, Instagram, WhatsApp
  (pengaturan_identitas.py)
- Opening Hours / hari libur (booking_db.py) -- SATU sumber kebenaran yang
  sama dipakai untuk slot booking maupun tampilan jam operasional di
  website, supaya tidak mungkin saling tidak sinkron.

Gallery (daftar foto, BEDA dari slot tunggal di atas -- bisa banyak foto
sekaligus) memakai tabel baru `website_gallery` (lihat init_website_db()
untuk jalur SQLite, postgres_schema.py untuk jalur PostgreSQL -- KEDUANYA
harus diubah bersamaan kalau skema tabel ini berubah lagi nanti).

PR 3 menambahkan: SEO (judul/deskripsi/keywords/OG Image), Footer legal
(Privacy Policy/Terms and Conditions -- teks panjang, Bahasa Indonesia
diperbolehkan di sini), dan Branding (Warna Primer/Sekunder -- HANYA
berlaku di halaman publik /book, lihat book_public.js; Favicon & Splash
Screen -- lihat catatan jujur di routers/website.py soal keterbatasan PWA
yang SUDAH ter-install)."""

import os
import re
import uuid
from datetime import datetime

import database as db
from database import get_conn

WEBSITE_CONTENT_KEYS = [
    # Hero
    "hero_tipe",              # "image" | "video" -- yang ditampilkan hanya salah satu
    "hero_cta_teks", "hero_cta_link",
    # About
    "about_judul", "about_deskripsi",
    # Visit Us
    "visit_maps_embed_url",   # src iframe Google Maps (bukan raw HTML embed, hindari XSS)
    "visit_maps_link",        # link "Buka di Google Maps"
    # Social (tambahan di luar instagram/whatsapp yang sudah ada di Identitas)
    "tiktok", "facebook", "youtube",
    # Footer
    "footer_copyright", "footer_pesan",
    # Booking CTA (closing section)
    "booking_cta_judul", "booking_cta_subjudul", "booking_cta_tombol_teks", "booking_cta_tombol_link",
    # Contact tambahan
    "telepon",
    # PR 3: Footer -- halaman legal (teks panjang sederhana, Bahasa
    # Indonesia diperbolehkan di sini sesuai instruksi -- BEDA dari
    # aturan "seluruh tampilan Bahasa Inggris" yang khusus untuk UI wizard).
    "footer_privacy_policy", "footer_terms",
    # PR 3: SEO -- di-inject ke <head> saat landing page render. CATATAN:
    # karena halaman ini SPA client-rendered, crawler yang TIDAK
    # menjalankan JavaScript tidak akan melihat meta ini -- tetap
    # dikerjakan sesuai permintaan, tapi bukan solusi SEO teknis penuh.
    "seo_title", "seo_deskripsi", "seo_keywords",
    # PR 3: Branding -- warna HANYA berlaku di halaman publik /book (lihat
    # book_public.js: CSS custom property di-set di root landing/wizard,
    # BUKAN global), tidak menyentuh tema aplikasi admin internal.
    "branding_warna_primer", "branding_warna_sekunder",
]

DEFAULT_VALUES = {
    "hero_tipe": "image",
    "hero_cta_teks": "Book Appointment",
    "booking_cta_tombol_teks": "Book Appointment",
}

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
HERO_VIDEO_DIR = os.path.join(STATIC_DIR, "hero_video")
ABOUT_FOTO_DIR = os.path.join(STATIC_DIR, "about")
GALLERY_DIR = os.path.join(STATIC_DIR, "gallery")
OG_IMAGE_DIR = os.path.join(STATIC_DIR, "seo")
FAVICON_DIR = os.path.join(STATIC_DIR, "favicon")
SPLASH_DIR = os.path.join(STATIC_DIR, "splash")

EXT_KE_CONTENT_TYPE_GAMBAR = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
}
EXT_KE_CONTENT_TYPE_VIDEO = {
    "mp4": "video/mp4", "webm": "video/webm",
}
# Cap ukuran video supaya Persistent Disk Render (kapasitas terbatas) tidak
# habis oleh satu file -- validasi baru yang wajar, bukan perubahan fitur lain.
MAKS_UKURAN_VIDEO_BYTES = 25 * 1024 * 1024  # 25MB


def init_website_db():
    """CREATE TABLE IF NOT EXISTS -- idempotent, jalur SQLite (dipanggil dari
    main.py on_startup()). Jalur PostgreSQL: tabel yang SAMA dibuat di
    postgres_schema.py (create_all() TIDAK memanggil fungsi ini sama
    sekali di jalur itu)."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS website_gallery (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT NOT NULL,
                urutan      INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
        """)


# ---------------------------------------------------------------------------
# Konten skalar (settings key-value)
# ---------------------------------------------------------------------------

def get_content() -> dict:
    data = {k: db.get_setting(k, DEFAULT_VALUES.get(k, "")) for k in WEBSITE_CONTENT_KEYS}
    hero_video_filename = db.get_setting("hero_video_filename", "")
    data["hero_video_url"] = f"/api/website/hero-video?v={hero_video_filename}" if hero_video_filename else None
    about_foto_filename = db.get_setting("about_foto_filename", "")
    data["about_foto_url"] = f"/api/website/about-foto?v={about_foto_filename}" if about_foto_filename else None
    og_image_filename = db.get_setting("og_image_filename", "")
    data["seo_og_image_url"] = f"/api/website/og-image?v={og_image_filename}" if og_image_filename else None
    favicon_filename = db.get_setting("favicon_filename", "")
    data["branding_favicon_url"] = f"/api/website/favicon?v={favicon_filename}" if favicon_filename else None
    splash_filename = db.get_setting("splash_filename", "")
    data["branding_splash_url"] = f"/api/website/splash?v={splash_filename}" if splash_filename else None
    return data


_HEX_WARNA_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def update_content(data: dict):
    bersih = {k: (v or "").strip() for k, v in data.items() if k in WEBSITE_CONTENT_KEYS}
    if "hero_tipe" in bersih and bersih["hero_tipe"] not in ("image", "video"):
        raise ValueError("hero_tipe harus 'image' atau 'video'.")
    for key in ("branding_warna_primer", "branding_warna_sekunder"):
        if bersih.get(key) and not _HEX_WARNA_RE.match(bersih[key]):
            raise ValueError(f"{key} harus format warna hex, contoh: #334155.")
    if not bersih:
        return
    db.set_settings_bulk(bersih)


# ---------------------------------------------------------------------------
# Aset gambar/video slot tunggal (Hero Video, Foto About) -- pola generik
# sama seperti _simpan_gambar()/_get_gambar_file_path() di
# pengaturan_identitas.py.
# ---------------------------------------------------------------------------

def _ekstensi_valid(filename: str, mapping: dict):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in mapping else None


def _simpan_aset(direktori: str, prefix: str, setting_key: str, filename_asli: str, konten: bytes,
                  mapping: dict, label: str) -> str:
    ext = _ekstensi_valid(filename_asli, mapping)
    if ext is None:
        raise ValueError(f"Format {label} tidak didukung.")
    if not konten:
        raise ValueError(f"File {label} kosong.")
    os.makedirs(direktori, exist_ok=True)
    for f in os.listdir(direktori):
        if f.startswith(f"{prefix}."):
            try:
                os.remove(os.path.join(direktori, f))
            except OSError:
                pass
    nama_file = f"{prefix}.{ext}"
    with open(os.path.join(direktori, nama_file), "wb") as fh:
        fh.write(konten)
    db.set_setting(setting_key, nama_file)
    return nama_file


def _get_aset_path(direktori: str, setting_key: str, mapping: dict):
    nama_file = db.get_setting(setting_key, "")
    if not nama_file:
        return None, None
    path = os.path.join(direktori, nama_file)
    if not os.path.isfile(path):
        return None, None
    ext = nama_file.rsplit(".", 1)[-1].lower()
    return path, mapping.get(ext, "application/octet-stream")


def _hapus_aset(direktori: str, setting_key: str):
    nama_file = db.get_setting(setting_key, "")
    if nama_file:
        path = os.path.join(direktori, nama_file)
        if os.path.isfile(path):
            os.remove(path)
    db.set_setting(setting_key, "")


def simpan_hero_video(filename_asli: str, konten: bytes) -> str:
    if len(konten) > MAKS_UKURAN_VIDEO_BYTES:
        raise ValueError(f"Ukuran video Hero maksimal {MAKS_UKURAN_VIDEO_BYTES // (1024 * 1024)}MB.")
    return _simpan_aset(HERO_VIDEO_DIR, "hero_video", "hero_video_filename", filename_asli, konten,
                         EXT_KE_CONTENT_TYPE_VIDEO, "Hero Video")


def get_hero_video_path():
    return _get_aset_path(HERO_VIDEO_DIR, "hero_video_filename", EXT_KE_CONTENT_TYPE_VIDEO)


def hapus_hero_video():
    _hapus_aset(HERO_VIDEO_DIR, "hero_video_filename")


def simpan_about_foto(filename_asli: str, konten: bytes) -> str:
    return _simpan_aset(ABOUT_FOTO_DIR, "about", "about_foto_filename", filename_asli, konten,
                         EXT_KE_CONTENT_TYPE_GAMBAR, "Foto About")


def get_about_foto_path():
    return _get_aset_path(ABOUT_FOTO_DIR, "about_foto_filename", EXT_KE_CONTENT_TYPE_GAMBAR)


def hapus_about_foto():
    _hapus_aset(ABOUT_FOTO_DIR, "about_foto_filename")


# PR 3: SEO Open Graph Image, Branding Favicon & Splash Screen -- pola
# generik yang SAMA seperti Hero Video/Foto About di atas.
def simpan_og_image(filename_asli: str, konten: bytes) -> str:
    return _simpan_aset(OG_IMAGE_DIR, "og_image", "og_image_filename", filename_asli, konten,
                         EXT_KE_CONTENT_TYPE_GAMBAR, "Open Graph Image")


def get_og_image_path():
    return _get_aset_path(OG_IMAGE_DIR, "og_image_filename", EXT_KE_CONTENT_TYPE_GAMBAR)


def hapus_og_image():
    _hapus_aset(OG_IMAGE_DIR, "og_image_filename")


def simpan_favicon(filename_asli: str, konten: bytes) -> str:
    return _simpan_aset(FAVICON_DIR, "favicon", "favicon_filename", filename_asli, konten,
                         EXT_KE_CONTENT_TYPE_GAMBAR, "Favicon")


def get_favicon_path():
    return _get_aset_path(FAVICON_DIR, "favicon_filename", EXT_KE_CONTENT_TYPE_GAMBAR)


def hapus_favicon():
    _hapus_aset(FAVICON_DIR, "favicon_filename")


def simpan_splash(filename_asli: str, konten: bytes) -> str:
    return _simpan_aset(SPLASH_DIR, "splash", "splash_filename", filename_asli, konten,
                         EXT_KE_CONTENT_TYPE_GAMBAR, "Splash Screen")


def get_splash_path():
    return _get_aset_path(SPLASH_DIR, "splash_filename", EXT_KE_CONTENT_TYPE_GAMBAR)


def hapus_splash():
    _hapus_aset(SPLASH_DIR, "splash_filename")


# ---------------------------------------------------------------------------
# GALLERY -- daftar foto (BEDA dari slot tunggal di atas: bisa banyak
# sekaligus, jadi nama file unik per foto + tabel `website_gallery`, bukan
# satu slot yang ditimpa).
# ---------------------------------------------------------------------------

def get_gallery() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM website_gallery ORDER BY urutan ASC, id ASC").fetchall()
        return [
            {"id": r["id"], "foto_url": f"/api/website/gallery/{r['id']}/foto?v={r['filename']}", "urutan": r["urutan"]}
            for r in rows
        ]


def tambah_gallery_foto(filename_asli: str, konten: bytes) -> int:
    ext = _ekstensi_valid(filename_asli, EXT_KE_CONTENT_TYPE_GAMBAR)
    if ext is None:
        raise ValueError("Format foto Gallery harus JPG, PNG, atau WEBP.")
    if not konten:
        raise ValueError("File foto kosong.")
    os.makedirs(GALLERY_DIR, exist_ok=True)
    nama_file = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(GALLERY_DIR, nama_file), "wb") as fh:
        fh.write(konten)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        urutan_maks = conn.execute("SELECT COALESCE(MAX(urutan), -1) AS m FROM website_gallery").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO website_gallery (filename, urutan, created_at) VALUES (?, ?, ?)",
            (nama_file, urutan_maks + 1, now),
        )
        return cur.lastrowid


def get_gallery_foto_path(foto_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT filename FROM website_gallery WHERE id = ?", (foto_id,)).fetchone()
    if row is None:
        return None, None
    path = os.path.join(GALLERY_DIR, row["filename"])
    if not os.path.isfile(path):
        return None, None
    ext = row["filename"].rsplit(".", 1)[-1].lower()
    return path, EXT_KE_CONTENT_TYPE_GAMBAR.get(ext, "application/octet-stream")


def hapus_gallery_foto(foto_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT filename FROM website_gallery WHERE id = ?", (foto_id,)).fetchone()
        if row is None:
            raise ValueError("Foto tidak ditemukan.")
        conn.execute("DELETE FROM website_gallery WHERE id = ?", (foto_id,))
    path = os.path.join(GALLERY_DIR, row["filename"])
    if os.path.isfile(path):
        os.remove(path)


def reorder_gallery(ordered_ids: list):
    with get_conn() as conn:
        existing_ids = {r["id"] for r in conn.execute("SELECT id FROM website_gallery").fetchall()}
        if set(ordered_ids) != existing_ids:
            raise ValueError("Daftar urutan tidak cocok dengan foto Gallery yang ada.")
        for urutan, foto_id in enumerate(ordered_ids):
            conn.execute("UPDATE website_gallery SET urutan = ? WHERE id = ?", (urutan, foto_id))
