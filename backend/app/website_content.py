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

Gallery (daftar foto/video) memakai tabel `website_gallery` (lihat
init_website_db() untuk jalur SQLite, postgres_schema.py untuk jalur
PostgreSQL -- KEDUANYA harus diubah bersamaan kalau skema ini berubah lagi)."""

import uuid
from datetime import datetime

import database as db
import file_asset_db
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
# Cap ukuran video (Hero Video maupun Gallery) supaya kuota database (BLOB,
# lihat file_asset_db.py/tabel website_gallery) tidak habis oleh satu file.
MAKS_UKURAN_VIDEO_BYTES = 50 * 1024 * 1024  # 50MB


def init_website_db():
    """CREATE TABLE IF NOT EXISTS -- idempotent, jalur SQLite (dipanggil dari
    main.py on_startup()). Jalur PostgreSQL: tabel yang SAMA dibuat di
    postgres_schema.py (create_all() TIDAK memanggil fungsi ini sama
    sekali di jalur itu)."""
    with get_conn() as conn:
        kolom = [r["name"] for r in conn.execute("PRAGMA table_info(website_gallery)").fetchall()]
        if kolom and "data" not in kolom:
            conn.execute("ALTER TABLE website_gallery ADD COLUMN data BLOB")
        if kolom and "tipe" not in kolom:
            # Gallery bisa diisi video (format apa saja yang didukung
            # browser, sama seperti Hero Video) selain foto -- baris lama
            # otomatis 'foto' (DEFAULT), tidak perlu migrasi data.
            conn.execute("ALTER TABLE website_gallery ADD COLUMN tipe TEXT NOT NULL DEFAULT 'foto'")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS website_gallery (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT NOT NULL,
                data        BLOB,
                tipe        TEXT NOT NULL DEFAULT 'foto',
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
    hero_image_filename = file_asset_db.ambil_meta("hero_image")
    data["hero_image_url"] = f"/api/website/hero-image?v={hero_image_filename}" if hero_image_filename else None
    hero_video_filename = file_asset_db.ambil_meta("hero_video")
    data["hero_video_url"] = f"/api/website/hero-video?v={hero_video_filename}" if hero_video_filename else None
    about_foto_filename = file_asset_db.ambil_meta("about_foto")
    data["about_foto_url"] = f"/api/website/about-foto?v={about_foto_filename}" if about_foto_filename else None
    background_image_filename = file_asset_db.ambil_meta("background_image")
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

def simpan_hero_image(filename_asli: str, konten: bytes) -> str:
    return file_asset_db.simpan("hero_image", filename_asli, konten, EXT_KE_CONTENT_TYPE_GAMBAR, "Hero Image")


def get_hero_image_data():
    return file_asset_db.ambil("hero_image")


def hapus_hero_image():
    file_asset_db.hapus("hero_image")


def simpan_hero_video(filename_asli: str, konten: bytes) -> str:
    if len(konten) > MAKS_UKURAN_VIDEO_BYTES:
        raise ValueError(f"Ukuran video Hero maksimal {MAKS_UKURAN_VIDEO_BYTES // (1024 * 1024)}MB.")
    return file_asset_db.simpan("hero_video", filename_asli, konten, EXT_KE_CONTENT_TYPE_VIDEO, "Hero Video")


def get_hero_video_data():
    return file_asset_db.ambil("hero_video")


def hapus_hero_video():
    file_asset_db.hapus("hero_video")


def simpan_about_foto(filename_asli: str, konten: bytes) -> str:
    return file_asset_db.simpan("about_foto", filename_asli, konten, EXT_KE_CONTENT_TYPE_GAMBAR, "Foto About")


def get_about_foto_data():
    return file_asset_db.ambil("about_foto")


def hapus_about_foto():
    file_asset_db.hapus("about_foto")


def simpan_background_image(filename_asli: str, konten: bytes) -> str:
    return file_asset_db.simpan("background_image", filename_asli, konten, EXT_KE_CONTENT_TYPE_GAMBAR, "Background Website")


def get_background_image_data():
    return file_asset_db.ambil("background_image")


def hapus_background_image():
    file_asset_db.hapus("background_image")


# ---------------------------------------------------------------------------
# GALLERY -- daftar foto/video (BEDA dari slot tunggal di atas: bisa banyak
# sekaligus, jadi nama file unik per item + tabel `website_gallery`, bukan
# satu slot yang ditimpa). Video Gallery format fleksibel sama seperti Hero
# Video (EXT_KE_CONTENT_TYPE_VIDEO di atas), dengan cap ukuran yang sama.
# ---------------------------------------------------------------------------

def get_gallery() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM website_gallery ORDER BY urutan ASC, id ASC").fetchall()
        return [
            {
                "id": r["id"],
                "foto_url": f"/api/website/gallery/{r['id']}/foto?v={r['filename']}",
                "tipe": r["tipe"],
                "urutan": r["urutan"],
            }
            for r in rows
        ]


def tambah_gallery_foto(filename_asli: str, konten: bytes) -> int:
    ext = filename_asli.rsplit(".", 1)[-1].lower() if "." in filename_asli else ""
    if ext in EXT_KE_CONTENT_TYPE_GAMBAR:
        tipe = "foto"
    elif ext in EXT_KE_CONTENT_TYPE_VIDEO:
        tipe = "video"
    else:
        raise ValueError("Format Gallery harus JPG/PNG/WEBP (foto) atau MP4/MOV/WEBM/dst (video).")
    if not konten:
        raise ValueError("File kosong.")
    if tipe == "video" and len(konten) > MAKS_UKURAN_VIDEO_BYTES:
        raise ValueError(f"Ukuran video Gallery maksimal {MAKS_UKURAN_VIDEO_BYTES // (1024 * 1024)}MB.")
    nama_file = f"{uuid.uuid4().hex}.{ext}"
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        urutan_maks = conn.execute("SELECT COALESCE(MAX(urutan), -1) AS m FROM website_gallery").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO website_gallery (filename, data, tipe, urutan, created_at) VALUES (?, ?, ?, ?, ?)",
            (nama_file, konten, tipe, urutan_maks + 1, now),
        )
        return cur.lastrowid


def get_gallery_foto_data(foto_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT filename, data FROM website_gallery WHERE id = ?", (foto_id,)).fetchone()
    if row is None or row["data"] is None:
        return None, None
    ext = row["filename"].rsplit(".", 1)[-1].lower()
    if ext in EXT_KE_CONTENT_TYPE_VIDEO:
        return bytes(row["data"]), EXT_KE_CONTENT_TYPE_VIDEO[ext]
    return bytes(row["data"]), EXT_KE_CONTENT_TYPE_GAMBAR.get(ext, "application/octet-stream")


def hapus_gallery_foto(foto_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM website_gallery WHERE id = ?", (foto_id,)).fetchone()
        if row is None:
            raise ValueError("Foto tidak ditemukan.")
        conn.execute("DELETE FROM website_gallery WHERE id = ?", (foto_id,))


def reorder_gallery(ordered_ids: list):
    with get_conn() as conn:
        existing_ids = {r["id"] for r in conn.execute("SELECT id FROM website_gallery").fetchall()}
        if set(ordered_ids) != existing_ids:
            raise ValueError("Daftar urutan tidak cocok dengan foto Gallery yang ada.")
        for urutan, foto_id in enumerate(ordered_ids):
            conn.execute("UPDATE website_gallery SET urutan = ? WHERE id = ?", (urutan, foto_id))
