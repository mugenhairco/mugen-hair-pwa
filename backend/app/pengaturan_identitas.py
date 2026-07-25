"""
pengaturan_identitas.py — Identitas Barbershop, Logo & Banner (TAHAP 10 + PENYEMPURNAAN FORM BOOKING)
========================================================================================================
Memakai tabel `settings` yang sudah ada (database.py, generik key-value) —
tidak ada tabel baru untuk identitas. File ini hanya membatasi key mana
yang boleh dibaca/ditulis lewat menu Setting > Identitas Barbershop, dan
mengurus penyimpanan file logo/banner di disk (di luar tanggung jawab
database.py).

PENYEMPURNAAN FORM BOOKING: menambah `tagline`, `deskripsi`, `website` ke
IDENTITAS_KEYS (field teks tambahan, dipakai halaman /book) dan Banner
(gambar, pola upload SAMA PERSIS seperti Logo) -- SEMUA field lama
(nama_barbershop/alamat/whatsapp/email/instagram/jam_operasional/logo)
TIDAK diubah sama sekali, murni penambahan.
"""

import os

import database as db

IDENTITAS_KEYS = [
    "nama_barbershop", "alamat", "whatsapp", "email", "instagram", "jam_operasional",
    "tagline", "deskripsi", "website",
]

LOGO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logo")
BANNER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "banner")
EXT_KE_CONTENT_TYPE = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def get_identitas() -> dict:
    data = {k: db.get_setting(k, "") for k in IDENTITAS_KEYS}
    logo_filename = db.get_setting("logo_filename", "")
    data["logo_url"] = f"/api/pengaturan/logo?v={logo_filename}" if logo_filename else None
    banner_filename = db.get_setting("banner_filename", "")
    data["banner_url"] = f"/api/pengaturan/banner?v={banner_filename}" if banner_filename else None
    return data


def update_identitas(data: dict):
    if "nama_barbershop" in data and not (data["nama_barbershop"] or "").strip():
        raise ValueError("Nama Barbershop tidak boleh kosong.")
    aman = {k: (v or "").strip() for k, v in data.items() if k in IDENTITAS_KEYS}
    if not aman:
        return
    db.set_settings_bulk(aman)


def _ekstensi_valid(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in EXT_KE_CONTENT_TYPE else None


def _simpan_gambar(direktori: str, prefix: str, setting_key: str, filename_asli: str, konten: bytes) -> str:
    """Helper generik dipakai simpan_logo() & simpan_banner() -- keduanya
    pola SAMA PERSIS (normalisasi nama file, hapus file lama dulu supaya
    tidak menumpuk, simpan nama file baru ke tabel settings)."""
    ext = _ekstensi_valid(filename_asli)
    if ext is None:
        raise ValueError(f"Format {prefix} harus JPG, PNG, atau WEBP.")
    if not konten:
        raise ValueError(f"File {prefix} kosong.")

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


def _get_gambar_file_path(direktori: str, setting_key: str):
    nama_file = db.get_setting(setting_key, "")
    if not nama_file:
        return None, None
    path = os.path.join(direktori, nama_file)
    if not os.path.isfile(path):
        return None, None
    ext = nama_file.rsplit(".", 1)[-1].lower()
    return path, EXT_KE_CONTENT_TYPE.get(ext, "application/octet-stream")


def simpan_logo(filename_asli: str, konten: bytes) -> str:
    """Simpan file logo baru, HAPUS file logo lama (ekstensi apapun) supaya
    tidak menumpuk file yatim. Return nama file baru yang disimpan."""
    return _simpan_gambar(LOGO_DIR, "logo", "logo_filename", filename_asli, konten)


def get_logo_file_path():
    """Return (path, content_type) kalau logo ada, atau (None, None)."""
    return _get_gambar_file_path(LOGO_DIR, "logo_filename")


def simpan_banner(filename_asli: str, konten: bytes) -> str:
    """Sama seperti simpan_logo(), untuk gambar Banner (dipakai header
    halaman booking publik /book)."""
    return _simpan_gambar(BANNER_DIR, "banner", "banner_filename", filename_asli, konten)


def get_banner_file_path():
    return _get_gambar_file_path(BANNER_DIR, "banner_filename")
