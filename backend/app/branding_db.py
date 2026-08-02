"""
branding_db.py — FONDASI Multi-Tenant Phase 2.2: Tenant Branding & Platform Branding
=============================================================================
Modul FASADE, bukan sumber penyimpanan baru untuk field yang SUDAH ADA --
mengumpulkan (bukan menduplikasi) identitas yang selama ini tersebar di dua
modul:
- nama_barbershop, email, logo  -> pengaturan_identitas.py (TIDAK diubah)
- tagline, alamat, whatsapp     -> website_content.py (TIDAK diubah, field
  ini TETAP dipakai apa adanya oleh halaman publik /book, lihat modul itu)

Field BENAR-BENAR BARU dari Phase 2.2 dimiliki LANGSUNG oleh modul ini:
- favicon (slot file_asset, pola identik logo)
- primary_color, secondary_color, website_url (baris `settings` baru,
  TIDAK butuh ALTER TABLE apa pun -- `settings` sudah generik key-value
  sejak awal, lihat database.py::_kunci_tenant()).

Endpoint publik GET /api/tenant/branding (routers/branding.py) memakai
get_branding() di sini sebagai satu-satunya sumber; endpoint tulis Setting >
Branding (routers/pengaturan.py) memakai update_branding()/simpan_favicon().

ZERO DATA LOSS: modul ini TIDAK membuat tabel baru, TIDAK mengubah skema
tabel yang sudah ada -- murni baris baru di tabel `settings`/`file_asset`
yang generik, persis pola pengaturan_identitas.py/website_content.py."""

import database as db
import file_asset_db
import pengaturan_identitas
import r2_storage
import website_content

# Favicon jauh lebih kecil dari foto/logo biasa (ICO/PNG kecil) -- cap
# sendiri yang jauh lebih ketat dari MAKS_UKURAN_GAMBAR_BYTES (10MB, dipakai
# Logo/Hero/dst) supaya tidak ada yang tidak sengaja upload gambar besar ke
# slot yang seharusnya cuma ikon kecil.
MAKS_UKURAN_FAVICON_BYTES = 1 * 1024 * 1024  # 1MB

FAVICON_EXT_KE_CONTENT_TYPE = {
    "ico": "image/x-icon",
    "png": "image/png",
}

# Field milik LANGSUNG modul ini (bukan delegasi) -- baris settings baru,
# generik seperti IDENTITAS_KEYS/WEBSITE_CONTENT_KEYS.
BRANDING_KEYS = ["primary_color", "secondary_color", "website_url"]

_HEX_WARNA = frozenset("0123456789abcdefABCDEF")


def _validasi_warna_hex(nilai: str, label: str) -> str:
    """Format `#RRGGBB` saja (dipakai langsung sebagai nilai CSS custom
    property di frontend, lihat brand.js) -- validasi ketat di sini
    mencegah nilai yang bisa menyuntik CSS/JS aneh-aneh tersimpan."""
    nilai = (nilai or "").strip()
    if not nilai:
        return ""
    if len(nilai) != 7 or nilai[0] != "#" or any(c not in _HEX_WARNA for c in nilai[1:]):
        raise ValueError(f"{label} harus format warna heksadesimal, contoh: #334155.")
    return nilai.upper()


def get_branding(tenant_id: int = None) -> dict:
    """Satu objek gabungan -- lihat docstring modul untuk sumber tiap
    field. Dipakai baik oleh endpoint publik (GET /api/tenant/branding)
    maupun Setting > Branding (mengisi form saat dibuka)."""
    identitas = pengaturan_identitas.get_identitas(tenant_id=tenant_id)
    konten = website_content.get_content(tenant_id=tenant_id)
    favicon_filename = file_asset_db.ambil_meta("favicon", tenant_id=tenant_id)
    return {
        "nama_barbershop": identitas["nama_barbershop"],
        "email": identitas["email"],
        "logo_url": identitas["logo_url"],
        "favicon_url": f"/api/pengaturan/favicon?v={favicon_filename}" if favicon_filename else None,
        "tagline": konten.get("tagline", ""),
        "alamat": konten.get("alamat", ""),
        "whatsapp": konten.get("whatsapp", ""),
        "primary_color": db.get_setting("primary_color", "", tenant_id=tenant_id),
        "secondary_color": db.get_setting("secondary_color", "", tenant_id=tenant_id),
        "website_url": db.get_setting("website_url", "", tenant_id=tenant_id),
    }


def update_branding(data: dict, tenant_id: int = None):
    """Pisahkan field yang dikirim ke modul pemiliknya masing-masing --
    supaya SATU form Setting > Branding bisa menyimpan seluruh field
    sekaligus tanpa Setting > Website Content perlu tahu apa pun tentang
    keberadaan tab Branding ini (arah ketergantungan satu arah)."""
    identitas_data = {k: v for k, v in data.items() if k in pengaturan_identitas.IDENTITAS_KEYS}
    if identitas_data:
        pengaturan_identitas.update_identitas(identitas_data, tenant_id=tenant_id)

    konten_data = {k: v for k, v in data.items() if k in ("tagline", "alamat", "whatsapp")}
    if konten_data:
        website_content.update_content(konten_data, tenant_id=tenant_id)

    branding_data = {}
    if "primary_color" in data:
        branding_data["primary_color"] = _validasi_warna_hex(data["primary_color"], "Primary Color")
    if "secondary_color" in data:
        branding_data["secondary_color"] = _validasi_warna_hex(data["secondary_color"], "Secondary Color")
    if "website_url" in data:
        branding_data["website_url"] = (data["website_url"] or "").strip()
    if branding_data:
        db.set_settings_bulk(branding_data, tenant_id=tenant_id)


def simpan_favicon(filename_asli: str, konten: bytes, tenant_id: int = None) -> str:
    return file_asset_db.simpan("favicon", filename_asli, konten, FAVICON_EXT_KE_CONTENT_TYPE, "Favicon",
                                 maks_ukuran_bytes=MAKS_UKURAN_FAVICON_BYTES, tenant_id=tenant_id)


def get_favicon_data(tenant_id: int = None):
    """Return (data, content_type) kalau tenant ini SUDAH punya favicon
    sendiri, atau (None, None) -- pemanggil (routers/branding.py) yang
    memutuskan fallback ke favicon platform, BUKAN di sini (modul ini
    murni akses data tenant, tidak tahu apa-apa soal branding platform)."""
    return file_asset_db.ambil("favicon", tenant_id=tenant_id)


def hapus_favicon(tenant_id: int = None):
    file_asset_db.hapus("favicon", tenant_id=tenant_id)
