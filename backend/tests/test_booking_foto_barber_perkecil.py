"""test_booking_foto_barber_perkecil.py — BUGFIX (audit performa halaman
booking publik): foto barber sebelumnya disimpan MENTAH persis ukuran asli
upload (bisa beberapa MB dari kamera HP), padahal ditampilkan mungil
92x92px (style.css::.book-barber-foto) -- log produksi menunjukkan 11-14
detik/foto diunduh dari R2 akibat ini. booking_db.simpan_foto_barber()
sekarang memperkecil & mengompres foto SEKALI saat diupload lewat
_perkecil_foto_barber(). Dites di jalur SQLite (R2_* kosong di test suite,
lihat conftest.py -- r2_storage.IS_ENABLED=False, jadi bytes akhir
tersimpan di kolom foto_data, cukup untuk menguji logika resize-nya)."""

import io

from PIL import Image

import booking_db
import database as db


def _barber(tenant_id, username="fotobarber"):
    return db.add_barber(f"Barber {username}", tenant_id=tenant_id)


def _foto_jpeg_besar(sisi_px=2000):
    """Foto JPEG persegi tanpa detail rumit (jauh lebih besar dari tampilan
    92x92px, meniru foto asli kamera HP yang jadi sumber masalah)."""
    img = Image.new("RGB", (sisi_px, sisi_px), color=(120, 45, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_simpan_foto_barber_memperkecil_dimensi_dan_ukuran(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    konten_asli = _foto_jpeg_besar(2000)

    booking_db.simpan_foto_barber(barber_id, "foto.jpg", konten_asli)

    data, content_type = booking_db.get_foto_barber_data(barber_id)
    assert content_type == "image/jpeg"
    assert len(data) < len(konten_asli), "hasil tersimpan harus lebih kecil dari upload asli"

    img_hasil = Image.open(io.BytesIO(data))
    assert max(img_hasil.size) <= booking_db._FOTO_BARBER_MAKS_DIMENSI_PX


def test_simpan_foto_barber_tidak_memperbesar_foto_yang_sudah_kecil(single_tenant):
    """Foto yang SUDAH lebih kecil dari batas (mis. 50x50px) tidak boleh
    diperbesar atau malah membengkak ukurannya gara-gara re-encode."""
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    img = Image.new("RGB", (50, 50), color=(10, 200, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    konten_kecil = buf.getvalue()

    booking_db.simpan_foto_barber(barber_id, "kecil.jpg", konten_kecil)

    data, _ = booking_db.get_foto_barber_data(barber_id)
    img_hasil = Image.open(io.BytesIO(data))
    assert img_hasil.size == (50, 50)


def test_perkecil_foto_barber_fallback_kalau_bukan_gambar_valid():
    """File yang lolos validasi ekstensi (.jpg) tapi isinya bukan gambar
    valid TIDAK BOLEH membuat simpan_foto_barber() gagal -- fallback ke
    bytes asli (kegagalan optimasi bukan alasan menolak upload Owner)."""
    konten_rusak = b"bukan data gambar sama sekali"
    hasil = booking_db._perkecil_foto_barber(konten_rusak, "jpg")
    assert hasil == konten_rusak


def test_simpan_foto_barber_mempertahankan_format_png(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    barber_id = _barber(tenant_id)
    img = Image.new("RGBA", (1200, 900), color=(5, 5, 5, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    konten_png = buf.getvalue()

    booking_db.simpan_foto_barber(barber_id, "foto.png", konten_png)

    data, content_type = booking_db.get_foto_barber_data(barber_id)
    assert content_type == "image/png"
    img_hasil = Image.open(io.BytesIO(data))
    assert img_hasil.format == "PNG"
    assert max(img_hasil.size) <= booking_db._FOTO_BARBER_MAKS_DIMENSI_PX
