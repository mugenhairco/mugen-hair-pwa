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
import r2_storage

IDENTITAS_KEYS = [
    "nama_barbershop", "email",
]

EXT_KE_CONTENT_TYPE = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def get_identitas(tenant_id: int = None) -> dict:
    data = {k: db.get_setting(k, "", tenant_id=tenant_id) for k in IDENTITAS_KEYS}
    logo_filename = file_asset_db.ambil_meta("logo", tenant_id=tenant_id)
    if logo_filename:
        # AUDIT 404 file media: <img src> yang memuat url ini tidak bisa
        # membawa Bearer token/Origin (lihat tenant_db.slug_untuk_url_media()
        # untuk penjelasan lengkap) -- slug disisipkan di sini supaya GET
        # /api/pengaturan/logo bisa resolve tenant-nya lewat query string.
        import tenant_db  # import lokal: hindari import siklik
        slug = tenant_db.slug_untuk_url_media(tenant_id)
        data["logo_url"] = f"/api/pengaturan/logo?v={logo_filename}" + (f"&tenant={slug}" if slug else "")
    else:
        data["logo_url"] = None
    return data


def update_identitas(data: dict, tenant_id: int = None):
    if "nama_barbershop" in data and not (data["nama_barbershop"] or "").strip():
        raise ValueError("Nama Barbershop tidak boleh kosong.")
    aman = {k: (v or "").strip() for k, v in data.items() if k in IDENTITAS_KEYS}
    if not aman:
        return
    db.set_settings_bulk(aman, tenant_id=tenant_id)


def simpan_logo(filename_asli: str, konten: bytes, tenant_id: int = None) -> str:
    return file_asset_db.simpan("logo", filename_asli, konten, EXT_KE_CONTENT_TYPE, "Logo",
                                 maks_ukuran_bytes=r2_storage.MAKS_UKURAN_GAMBAR_BYTES, tenant_id=tenant_id)


def get_logo_data(tenant_id: int = None):
    """Return (data, content_type) kalau logo ada, atau (None, None)."""
    return file_asset_db.ambil("logo", tenant_id=tenant_id)
