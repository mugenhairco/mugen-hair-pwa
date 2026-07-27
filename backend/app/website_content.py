"""
website_content.py — CMS "Website Content" untuk halaman publik /book
=======================================================================
Owner-only (lihat routers/website.py: require_admin di semua endpoint tulis,
BUKAN lewat sistem izin permissions.py -- staff tidak pernah bisa diberi
akses ke sini). Mengikuti pola pengaturan_identitas.py:
- Field skalar (teks/link) -> tabel `settings` key-value yang sudah ada.
- Field gambar/video tunggal -> helper generik simpan/hapus/get-path.

REVISI STRUKTUR WEBSITE CONTENT: SATU-SATUNYA tempat pengaturan tampilan
halaman publik /book -- Tagline, Deskripsi, Alamat, Nomor WhatsApp,
Instagram, dan Hero Image DIPINDAHKAN ke sini dari pengaturan_identitas.py
(BUKAN diduplikasi -- sudah dihapus total dari sana). Header/Footer/Pesan
Pembuka lama (booking_db.py) juga sudah dihapus, digantikan Hero di sini.

Field yang TETAP di luar modul ini (supaya tidak ada pengaturan duplikat):
- Nama Barbershop, Email, Logo (pengaturan_identitas.py) -- identitas inti
  yang dipakai di LUAR /book juga (sidebar, Login, judul tab browser).
- Opening Hours / hari libur (booking_db.py, tab Operating Hours) -- SATU
  sumber kebenaran yang sama dipakai untuk slot booking maupun tampilan
  Opening Hours di website, supaya tidak mungkin saling tidak sinkron.
- Pesan konfirmasi & validasi form booking (booking_db.py, tab Booking
  Settings) -- pesan TRANSAKSIONAL alur booking, bukan konten tampilan.

Fitur SEO/Branding (warna/Favicon/Splash Screen)/Booking CTA sebagai link
eksternal/Footer legal (Privacy Policy/Terms) yang SEMPAT ada di iterasi
sebelumnya SUDAH DIHAPUS TOTAL sesuai instruksi revisi -- tidak ada
pengaturan untuk fitur-fitur itu lagi.

Gallery (daftar foto) memakai tabel `website_gallery` (lihat
init_website_db() untuk jalur SQLite, postgres_schema.py untuk jalur
PostgreSQL -- KEDUANYA harus diubah bersamaan kalau skema ini berubah lagi)."""

import os
import uuid
from datetime import datetime

import database as db
from database import get_conn

WEBSITE_CONTENT_KEYS = [
    # Hero
    "hero_tipe",              # "image" | "video" -- yang ditampilkan hanya salah satu
    "tagline",                 # dipindahkan dari Identitas
    # About
    "about_judul", "about_deskripsi",
    # Visit Us
    "alamat",                  # dipindahkan dari Identitas
    "visit_maps_embed_url",    # src iframe Google Maps (bukan raw HTML embed, hindari XSS)
    "visit_maps_link",         # link "Buka di Google Maps"
    # Social Media -- HANYA Instagram/TikTok/WhatsApp (lihat instruksi #8)
    "instagram", "tiktok", "whatsapp",  # instagram & whatsapp dipindahkan dari Identitas
    # Contact
    "telepon",
    # Background Website
    "background_tipe",         # "image" | "light" | "dark"
    "background_opacity",      # "0".."100", HANYA relevan kalau background_tipe == "image"
    # Book Appointment (CTA satu-satunya di halaman, lihat instruksi #7)
    "booking_cta_judul", "booking_cta_subjudul", "booking_cta_tombol_teks",
]

DEFAULT_VALUES = {
    "hero_tipe": "image",
    "background_tipe": "light",
    "background_opacity": "20",
    "booking_cta_judul": "Ready for your next cut?",
    "booking_cta_tombol_teks": "Book Appointment",
}

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
HERO_IMAGE_DIR = os.path.join(STATIC_DIR, "hero_image")
HERO_VIDEO_DIR = os.path.join(STATIC_DIR, "hero_video")
ABOUT_FOTO_DIR = os.path.join(STATIC_DIR, "about")
GALLERY_DIR = os.path.join(STATIC_DIR, "gallery")
BACKGROUND_DIR = os.path.join(STATIC_DIR, "background")

EXT_KE_CONTENT_TYPE_GAMBAR = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
}
# Instruksi: "Format video dibuat fleksibel selama didukung browser modern
# (MP4, MOV, WebM, dan format umum lainnya)" -- daftar di bawah ini sengaja
# mencakup format umum yang didukung SETIDAKNYA satu browser modern utama
# (Chrome/Safari/Firefox/Edge); MOV/QuickTime terutama dari upload iPhone.
EXT_KE_CONTENT_TYPE_VIDEO = {
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
    "m4v": "video/x-m4v", "ogv": "video/ogg", "ogg": "video/ogg",
}
# Cap ukuran video supaya Persistent Disk Render (kapasitas terbatas) tidak
# habis oleh satu file -- validasi baru yang wajar, bukan perubahan fitur lain.
MAKS_UKURAN_VIDEO_BYTES = 50 * 1024 * 1024  # 50MB


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
    data["background_opacity"] = int(data["background_opacity"] or 20)
    hero_image_filename = db.get_setting("hero_image_filename", "")
    data["hero_image_url"] = f"/api/website/hero-image?v={hero_image_filename}" if hero_image_filename else None
    hero_video_filename = db.get_setting("hero_video_filename", "")
    data["hero_video_url"] = f"/api/website/hero-video?v={hero_video_filename}" if hero_video_filename else None
    about_foto_filename = db.get_setting("about_foto_filename", "")
    data["about_foto_url"] = f"/api/website/about-foto?v={about_foto_filename}" if about_foto_filename else None
    background_image_filename = db.get_setting("background_image_filename", "")
    data["background_image_url"] = f"/api/website/background-image?v={background_image_filename}" if background_image_filename else None
    return data


def update_content(data: dict):
    bersih = {k: (v if v is not None else "") for k, v in data.items() if k in WEBSITE_CONTENT_KEYS}
    for k in bersih:
        if isinstance(bersih[k], str):
            bersih[k] = bersih[k].strip()
    if "hero_tipe" in bersih and bersih["hero_tipe"] not in ("image", "video"):
        raise ValueError("hero_tipe harus 'image' atau 'video'.")
    if "background_tipe" in bersih and bersih["background_tipe"] not in ("image", "light", "dark"):
        raise ValueError("background_tipe harus 'image', 'light', atau 'dark'.")
    if "background_opacity" in bersih:
        try:
            opasitas = int(bersih["background_opacity"])
        except (TypeError, ValueError):
            raise ValueError("background_opacity harus angka 0-100.")
        if not (0 <= opasitas <= 100):
            raise ValueError("background_opacity harus antara 0-100.")
        bersih["background_opacity"] = str(opasitas)
    if not bersih:
        return
    db.set_settings_bulk(bersih)


# ---------------------------------------------------------------------------
# Aset gambar/video slot tunggal -- pola generik sama seperti
# _simpan_gambar()/_get_gambar_file_path() di pengaturan_identitas.py.
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


def simpan_hero_image(filename_asli: str, konten: bytes) -> str:
    return _simpan_aset(HERO_IMAGE_DIR, "hero_image", "hero_image_filename", filename_asli, konten,
                         EXT_KE_CONTENT_TYPE_GAMBAR, "Hero Image")


def get_hero_image_path():
    return _get_aset_path(HERO_IMAGE_DIR, "hero_image_filename", EXT_KE_CONTENT_TYPE_GAMBAR)


def hapus_hero_image():
    _hapus_aset(HERO_IMAGE_DIR, "hero_image_filename")


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


def simpan_background_image(filename_asli: str, konten: bytes) -> str:
    return _simpan_aset(BACKGROUND_DIR, "background", "background_image_filename", filename_asli, konten,
                         EXT_KE_CONTENT_TYPE_GAMBAR, "Background Website")


def get_background_image_path():
    return _get_aset_path(BACKGROUND_DIR, "background_image_filename", EXT_KE_CONTENT_TYPE_GAMBAR)


def hapus_background_image():
    _hapus_aset(BACKGROUND_DIR, "background_image_filename")


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
