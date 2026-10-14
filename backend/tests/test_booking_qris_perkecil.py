"""test_booking_qris_perkecil.py — PERBAIKAN PERFORMA (laporan Owner: foto
QRIS tampil pelan-pelan dari atas ke bawah di halaman booking publik,
gejala file besar/mentah). Screenshot QRIS dari HP/aplikasi bank/e-wallet
sebelumnya disimpan & dilayani APA ADANYA (bisa 1-3MB), tidak ada kompresi
sama sekali -- beda dari foto barber yang sudah lebih dulu diperbaiki
(lihat test_booking_foto_barber_perkecil.py, pola tes yang sama persis di
sini). booking_db.simpan_qris() sekarang memperkecil & mengompres lewat
_perkecil_qris() -- dimensi maksimal & kualitas SENGAJA lebih tinggi
daripada foto barber supaya tetap bisa di-scan kamera HP customer."""

import io

from PIL import Image

import booking_db


def _qris_jpeg_besar(sisi_px=2500):
    """Gambar JPEG persegi tanpa detail rumit (jauh lebih besar dari batas
    _QRIS_MAKS_DIMENSI_PX, meniru screenshot QRIS mentah dari HP)."""
    img = Image.new("RGB", (sisi_px, sisi_px), color=(30, 90, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_simpan_qris_memperkecil_dimensi_dan_ukuran(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    konten_asli = _qris_jpeg_besar(2500)

    booking_db.simpan_qris("qris.jpg", konten_asli, tenant_id=tenant_id)

    data, content_type = booking_db.get_qris_data(tenant_id=tenant_id)
    assert content_type == "image/jpeg"
    assert len(data) < len(konten_asli), "hasil tersimpan harus lebih kecil dari upload asli"

    img_hasil = Image.open(io.BytesIO(data))
    assert max(img_hasil.size) <= booking_db._QRIS_MAKS_DIMENSI_PX


def test_simpan_qris_tidak_memperbesar_qris_yang_sudah_kecil(single_tenant):
    """QRIS yang SUDAH lebih kecil dari batas (mis. 300x300px, umum untuk
    QRIS resmi) tidak boleh diperbesar atau malah membengkak ukurannya
    gara-gara re-encode."""
    tenant_id = single_tenant["tenant_id"]
    img = Image.new("RGB", (300, 300), color=(10, 200, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    konten_kecil = buf.getvalue()

    booking_db.simpan_qris("qris_kecil.jpg", konten_kecil, tenant_id=tenant_id)

    data, _ = booking_db.get_qris_data(tenant_id=tenant_id)
    img_hasil = Image.open(io.BytesIO(data))
    assert img_hasil.size == (300, 300)


def test_perkecil_qris_fallback_kalau_bukan_gambar_valid():
    """File yang lolos validasi ekstensi (.jpg) tapi isinya bukan gambar
    valid TIDAK BOLEH membuat simpan_qris() gagal -- fallback ke bytes asli
    (kegagalan optimasi bukan alasan menolak upload Owner)."""
    konten_rusak = b"bukan data gambar sama sekali"
    hasil = booking_db._perkecil_qris(konten_rusak, "jpg")
    assert hasil == konten_rusak


def test_simpan_qris_besar_mempertahankan_format_png(single_tenant):
    tenant_id = single_tenant["tenant_id"]
    img = Image.new("RGBA", (2000, 1500), color=(5, 5, 5, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    konten_png = buf.getvalue()

    booking_db.simpan_qris("qris.png", konten_png, tenant_id=tenant_id)

    data, content_type = booking_db.get_qris_data(tenant_id=tenant_id)
    assert content_type == "image/png"
    img_hasil = Image.open(io.BytesIO(data))
    assert img_hasil.format == "PNG"
    assert max(img_hasil.size) <= booking_db._QRIS_MAKS_DIMENSI_PX
