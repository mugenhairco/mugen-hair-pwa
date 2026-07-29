"""
pengaturan_identitas.py — Identitas Barbershop & Logo (TAHAP 10 + REVISI STRUKTUR WEBSITE CONTENT)
=====================================================================================================
Memakai tabel `settings` yang sudah ada (database.py, generik key-value) —
tidak ada tabel baru untuk identitas. File ini hanya membatasi key mana
yang boleh dibaca/ditulis lewat menu Setting > Identitas Barbershop, dan
mengurus penyimpanan file logo di disk (di luar tanggung jawab database.py).

REVISI STRUKTUR WEBSITE CONTENT: Alamat, Nomor WhatsApp, Jam Operasional,
Tagline, Deskripsi, Website, Instagram, dan Banner (Hero Image) DIPINDAHKAN
ke website_content.py (dikelola lewat Booking > Website Content) --
BUKAN diduplikasi. Modul ini sekarang HANYA menyisakan identitas inti yang
dipakai di LUAR halaman publik /book juga (sidebar, halaman Login, judul
tab browser): Nama Barbershop, Email, dan Logo."""

import database as db
import file_asset_db

IDENTITAS_KEYS = [
    "nama_barbershop", "email",
]

EXT_KE_CONTENT_TYPE = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def get_identitas() -> dict:
    data = {k: db.get_setting(k, "") for k in IDENTITAS_KEYS}
    logo_filename = file_asset_db.ambil_meta("logo")
    data["logo_url"] = f"/api/pengaturan/logo?v={logo_filename}" if logo_filename else None
    return data


def update_identitas(data: dict):
    if "nama_barbershop" in data and not (data["nama_barbershop"] or "").strip():
        raise ValueError("Nama Barbershop tidak boleh kosong.")
    aman = {k: (v or "").strip() for k, v in data.items() if k in IDENTITAS_KEYS}
    if not aman:
        return
    db.set_settings_bulk(aman)


def simpan_logo(filename_asli: str, konten: bytes) -> str:
    return file_asset_db.simpan("logo", filename_asli, konten, EXT_KE_CONTENT_TYPE, "Logo")


def get_logo_data():
    """Return (data, content_type) kalau logo ada, atau (None, None)."""
    return file_asset_db.ambil("logo")
