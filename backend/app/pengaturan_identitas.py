"""
pengaturan_identitas.py — Identitas Barbershop & Logo (TAHAP 10)
==================================================================
Memakai tabel `settings` yang sudah ada (database.py, generik key-value) —
tidak ada tabel baru untuk identitas. File ini hanya membatasi key mana
yang boleh dibaca/ditulis lewat menu Setting > Identitas Barbershop, dan
mengurus penyimpanan file logo di disk (di luar tanggung jawab database.py).
"""

import os

import database as db

IDENTITAS_KEYS = [
    "nama_barbershop", "alamat", "whatsapp", "email", "instagram", "jam_operasional",
]

LOGO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logo")
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


def simpan_logo(filename_asli: str, konten: bytes) -> str:
    """Simpan file logo baru, HAPUS file logo lama (ekstensi apapun) supaya
    tidak menumpuk file yatim. Return nama file baru yang disimpan."""
    ext = _ekstensi_valid(filename_asli)
    if ext is None:
        raise ValueError("Format logo harus JPG, PNG, atau WEBP.")
    if not konten:
        raise ValueError("File logo kosong.")

    os.makedirs(LOGO_DIR, exist_ok=True)
    # hapus logo lama (ekstensi berapapun) sebelum simpan yang baru
    for f in os.listdir(LOGO_DIR):
        if f.startswith("logo."):
            try:
                os.remove(os.path.join(LOGO_DIR, f))
            except OSError:
                pass

    nama_file = f"logo.{ext}"
    with open(os.path.join(LOGO_DIR, nama_file), "wb") as fh:
        fh.write(konten)

    db.set_setting("logo_filename", nama_file)
    return nama_file


def get_logo_file_path():
    """Return (path, content_type) kalau logo ada, atau (None, None)."""
    nama_file = db.get_setting("logo_filename", "")
    if not nama_file:
        return None, None
    path = os.path.join(LOGO_DIR, nama_file)
    if not os.path.isfile(path):
        return None, None
    ext = nama_file.rsplit(".", 1)[-1].lower()
    return path, EXT_KE_CONTENT_TYPE.get(ext, "application/octet-stream")
