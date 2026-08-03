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

from datetime import datetime

import database as db
import file_asset_db
import r2_storage
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
    # Book Appointment (CTA satu-satunya di halaman, lihat instruksi #7)
    "booking_cta_judul", "booking_cta_subjudul", "booking_cta_tombol_teks",
]

# REVISI Branding Rivoir: fitur "Background Website" (pilihan Light/Dark/
# Image+Opacity per tenant) DIHAPUS TOTAL -- Web Booking sekarang selalu
# memakai satu background default yang sama (lihat :root[data-theme="dark"]
# .book-public di style.css), tanpa opsi ganti apa pun.
DEFAULT_VALUES = {
    "hero_tipe": "image",
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

def get_content(tenant_id: int = None) -> dict:
    data = {k: db.get_setting(k, DEFAULT_VALUES.get(k, ""), tenant_id=tenant_id) for k in WEBSITE_CONTENT_KEYS}
    hero_image_filename = file_asset_db.ambil_meta("hero_image", tenant_id=tenant_id)
    data["hero_image_url"] = f"/api/website/hero-image?v={hero_image_filename}" if hero_image_filename else None
    hero_video_filename = file_asset_db.ambil_meta("hero_video", tenant_id=tenant_id)
    data["hero_video_url"] = f"/api/website/hero-video?v={hero_video_filename}" if hero_video_filename else None
    about_foto_filename = file_asset_db.ambil_meta("about_foto", tenant_id=tenant_id)
    data["about_foto_url"] = f"/api/website/about-foto?v={about_foto_filename}" if about_foto_filename else None
    return data


def update_content(data: dict, tenant_id: int = None):
    bersih = {k: (v if v is not None else "") for k, v in data.items() if k in WEBSITE_CONTENT_KEYS}
    for k in bersih:
        if isinstance(bersih[k], str):
            bersih[k] = bersih[k].strip()
    if "hero_tipe" in bersih and bersih["hero_tipe"] not in ("image", "video"):
        raise ValueError("hero_tipe harus 'image' atau 'video'.")
    if not bersih:
        return
    db.set_settings_bulk(bersih, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Aset gambar/video slot tunggal -- pola generik sama seperti
# _simpan_gambar()/_get_gambar_file_path() di pengaturan_identitas.py.
# ---------------------------------------------------------------------------

def simpan_hero_image(filename_asli: str, konten: bytes, tenant_id: int = None) -> str:
    return file_asset_db.simpan("hero_image", filename_asli, konten, EXT_KE_CONTENT_TYPE_GAMBAR, "Hero Image",
                                 maks_ukuran_bytes=r2_storage.MAKS_UKURAN_GAMBAR_BYTES, tenant_id=tenant_id)


def get_hero_image_data(tenant_id: int = None):
    return file_asset_db.ambil("hero_image", tenant_id=tenant_id)


def hapus_hero_image(tenant_id: int = None):
    file_asset_db.hapus("hero_image", tenant_id=tenant_id)


def simpan_hero_video(filename_asli: str, konten: bytes, tenant_id: int = None) -> str:
    if len(konten) > MAKS_UKURAN_VIDEO_BYTES:
        raise ValueError(f"Ukuran video Hero maksimal {MAKS_UKURAN_VIDEO_BYTES // (1024 * 1024)}MB.")
    return file_asset_db.simpan("hero_video", filename_asli, konten, EXT_KE_CONTENT_TYPE_VIDEO, "Hero Video",
                                 tenant_id=tenant_id)


def get_hero_video_data(tenant_id: int = None):
    return file_asset_db.ambil("hero_video", tenant_id=tenant_id)


def hapus_hero_video(tenant_id: int = None):
    file_asset_db.hapus("hero_video", tenant_id=tenant_id)


def simpan_about_foto(filename_asli: str, konten: bytes, tenant_id: int = None) -> str:
    return file_asset_db.simpan("about_foto", filename_asli, konten, EXT_KE_CONTENT_TYPE_GAMBAR, "Foto About",
                                 maks_ukuran_bytes=r2_storage.MAKS_UKURAN_GAMBAR_BYTES, tenant_id=tenant_id)


def get_about_foto_data(tenant_id: int = None):
    return file_asset_db.ambil("about_foto", tenant_id=tenant_id)


def hapus_about_foto(tenant_id: int = None):
    file_asset_db.hapus("about_foto", tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# GALLERY -- daftar foto/video (BEDA dari slot tunggal di atas: bisa banyak
# sekaligus, jadi nama file unik per item + tabel `website_gallery`, bukan
# satu slot yang ditimpa). Video Gallery format fleksibel sama seperti Hero
# Video (EXT_KE_CONTENT_TYPE_VIDEO di atas), dengan cap ukuran yang sama.
# ---------------------------------------------------------------------------

def get_gallery(tenant_id: int = None) -> list:
    with get_conn() as conn:
        if tenant_id is not None:
            rows = conn.execute("SELECT * FROM website_gallery WHERE tenant_id = ? ORDER BY urutan ASC, id ASC",
                                 (tenant_id,)).fetchall()
        else:
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


_EXT_KE_CONTENT_TYPE_GALLERY = {**EXT_KE_CONTENT_TYPE_GAMBAR, **EXT_KE_CONTENT_TYPE_VIDEO}


def tambah_gallery_foto(filename_asli: str, konten: bytes, tenant_id: int = None) -> int:
    ext = filename_asli.rsplit(".", 1)[-1].lower() if "." in filename_asli else ""
    if ext in EXT_KE_CONTENT_TYPE_GAMBAR:
        tipe = "foto"
    elif ext in EXT_KE_CONTENT_TYPE_VIDEO:
        tipe = "video"
    else:
        raise ValueError("Format Gallery harus JPG/PNG/WEBP (foto) atau MP4/MOV/WEBM/dst (video).")
    maks_ukuran = MAKS_UKURAN_VIDEO_BYTES if tipe == "video" else r2_storage.MAKS_UKURAN_GAMBAR_BYTES
    nama_file, content_type = r2_storage.validasi_dan_beri_nama(
        filename_asli, konten, _EXT_KE_CONTENT_TYPE_GALLERY, "Gallery", maks_ukuran_bytes=maks_ukuran)
    now = datetime.now().isoformat(timespec="seconds")

    if r2_storage.IS_ENABLED:
        r2_key = r2_storage.upload("gallery", nama_file, konten, content_type)
        data_kolom = None
    else:
        r2_key = None
        data_kolom = konten

    with get_conn() as conn:
        if tenant_id is not None:
            urutan_maks = conn.execute(
                "SELECT COALESCE(MAX(urutan), -1) AS m FROM website_gallery WHERE tenant_id = ?",
                (tenant_id,)).fetchone()["m"]
        else:
            urutan_maks = conn.execute("SELECT COALESCE(MAX(urutan), -1) AS m FROM website_gallery").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO website_gallery (filename, data, r2_key, tipe, urutan, created_at, tenant_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nama_file, data_kolom, r2_key, tipe, urutan_maks + 1, now, tenant_id),
        )
        return cur.lastrowid


def get_gallery_foto_data(foto_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT filename, data, r2_key FROM website_gallery WHERE id = ?", (foto_id,)).fetchone()
    if row is None:
        return None, None
    ext = row["filename"].rsplit(".", 1)[-1].lower()
    content_type = EXT_KE_CONTENT_TYPE_VIDEO.get(ext) or EXT_KE_CONTENT_TYPE_GAMBAR.get(ext, "application/octet-stream")
    if row["r2_key"]:
        data, r2_content_type = r2_storage.get_bytes(row["r2_key"])
        if data is not None:
            return data, r2_content_type or content_type
    if row["data"] is not None:
        return bytes(row["data"]), content_type
    return None, None


def get_gallery_foto_meta(foto_id: int):
    """FONDASI Multi-Tenant Phase 1: dipakai router untuk fetch-then-authorize
    (bandingkan tenant_id) SEBELUM memanggil get_gallery_foto_data()/
    hapus_gallery_foto() -- keduanya sendiri tetap menerima bare foto_id
    tanpa parameter tenant_id baru, sama seperti pola get_barber()/get_service()."""
    with get_conn() as conn:
        row = conn.execute("SELECT id, tenant_id FROM website_gallery WHERE id = ?", (foto_id,)).fetchone()
        return dict(row) if row else None


def hapus_gallery_foto(foto_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT id, r2_key FROM website_gallery WHERE id = ?", (foto_id,)).fetchone()
        if row is None:
            raise ValueError("Foto tidak ditemukan.")
        conn.execute("DELETE FROM website_gallery WHERE id = ?", (foto_id,))
    if row["r2_key"]:
        r2_storage.delete(row["r2_key"])


def reorder_gallery(ordered_ids: list, tenant_id: int = None):
    with get_conn() as conn:
        if tenant_id is not None:
            existing_ids = {r["id"] for r in conn.execute(
                "SELECT id FROM website_gallery WHERE tenant_id = ?", (tenant_id,)).fetchall()}
        else:
            existing_ids = {r["id"] for r in conn.execute("SELECT id FROM website_gallery").fetchall()}
        if set(ordered_ids) != existing_ids:
            raise ValueError("Daftar urutan tidak cocok dengan foto Gallery yang ada.")
        for urutan, foto_id in enumerate(ordered_ids):
            conn.execute("UPDATE website_gallery SET urutan = ? WHERE id = ?", (urutan, foto_id))
