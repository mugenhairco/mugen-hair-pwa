"""
r2_storage.py — Klien penyimpanan Cloudflare R2 (S3-compatible, lewat boto3)
=============================================================================
Lapisan penyimpanan file EKSTERNAL yang menggantikan BLOB-di-database
(file_asset_db.py/website_gallery.data/barbers.foto_data/reimburse.bukti_data
-- lihat README bagian "Migrasi Cloudflare R2 (Storage File)"), supaya
database (Neon) hanya menyimpan METADATA (nama file, tipe, KEY objek R2),
bukan lagi isi byte file itu sendiri.

Dialek storage aktif ditentukan SEKALI saat modul ini pertama kali diimpor,
dari environment variable R2_* (pola SAMA seperti db_compat.py menentukan
SQLite vs PostgreSQL dari DATABASE_URL):
- Environment variable R2_* TIDAK LENGKAP -> IS_ENABLED=False. Modul ini
  praktis tidak melakukan apa-apa -- pemanggil (file_asset_db.py dkk) TETAP
  memakai jalur BLOB-di-database lama apa adanya. Ini SENGAJA supaya
  development lokal (tanpa kredensial R2) tetap berfungsi penuh tanpa
  konfigurasi tambahan apa pun.
- Environment variable R2_* LENGKAP -> IS_ENABLED=True. Upload/baca/hapus
  file lewat R2 (S3-compatible API Cloudflare), boto3 dipakai sebagai
  client S3 generik yang di-arahkan ke endpoint R2 (bukan AWS).

Arsitektur: bucket R2 TETAP PRIVATE (tidak perlu akses publik/custom domain)
-- backend TETAP menjadi satu-satunya gerbang akses file, PERSIS seperti
alur BLOB-di-database sebelumnya (endpoint GET yang sudah ada di setiap
router membaca bytes lalu `Response(content=..., media_type=...)`, hanya
sumber bytes-nya sekarang R2 lewat get_bytes() alih-alih SELECT ... BLOB).
Ini KEPUTUSAN SADAR (bukan default R2) supaya TIDAK PERLU mengubah satu pun
endpoint API atau kode frontend -- diaudit langsung: seluruh frontend
(js/pages/booking.js, book_public.js, pengaturan.js, brand.js) memakai pola
`MUGEN_API_BASE + data.xxx_url` di puluhan tempat, yang mengasumsikan
`xxx_url` adalah PATH RELATIF ke backend yang sama, BUKAN URL absolut ke
domain lain -- kalau field itu diisi URL R2 langsung, hasilnya jadi string
gabungan yang rusak (mis. "https://mugen-hair-api.onrender.comhttps://pub-
xxxx.r2.dev/..."). `R2_PUBLIC_URL` tetap disediakan sebagai konfigurasi
opsional (dibaca, disimpan) untuk kemungkinan pemakaian CDN langsung di
masa depan, tapi TIDAK dipakai di jalur kode manapun saat ini.
"""

import logging
import os
import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("mugen.r2")

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "").strip()
# R2_ENDPOINT_URL biasanya https://<account_id>.r2.cloudflarestorage.com --
# boleh diisi eksplisit (didahulukan), atau diturunkan otomatis dari
# R2_ACCOUNT_ID kalau endpoint tidak diisi terpisah.
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL", "").strip().rstrip("/") or (
    f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else ""
)
# Disimpan untuk kemungkinan pemakaian CDN publik di masa depan -- TIDAK
# dipakai jalur kode manapun sekarang (lihat catatan arsitektur di atas).
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "").strip().rstrip("/")

IS_ENABLED = bool(R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME and R2_ENDPOINT_URL)

# Batas ukuran default untuk upload gambar/dokumen (Logo, Hero Image, Foto
# About, Background, QRIS, Foto Barber, Gallery foto, Bukti Reimburse) --
# TIDAK ADA batas ukuran sama sekali sebelum migrasi R2 ini (audit kode
# lama), jadi ini murni PENGERASAN baru (item validasi wajib), bukan
# pengetatan dari batas yang sudah ada. Video (Hero Video/Gallery video)
# TETAP pakai batas 50MB tersendiri yang sudah ada di website_content.py,
# tidak berubah.
MAKS_UKURAN_GAMBAR_BYTES = 10 * 1024 * 1024   # 10MB
MAKS_UKURAN_DOKUMEN_BYTES = 10 * 1024 * 1024  # 10MB -- Bukti Reimburse (gambar ATAU PDF)

_MAX_RETRIES = 3
_CONNECT_TIMEOUT_DETIK = 10
_READ_TIMEOUT_DETIK = 30

_client = None


class R2Error(RuntimeError):
    """Dilempar kalau upload/baca/hapus ke R2 gagal (setelah retry bawaan
    boto3 habis) -- router pemanggil menerjemahkannya jadi HTTP 502 dengan
    pesan jelas ke client, BUKAN dibiarkan jadi traceback 500 mentah."""


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": _MAX_RETRIES, "mode": "standard"},
                connect_timeout=_CONNECT_TIMEOUT_DETIK,
                read_timeout=_READ_TIMEOUT_DETIK,
            ),
            region_name="auto",
        )
    return _client


def validasi_dan_beri_nama(filename_asli: str, konten: bytes, ext_map: dict, label: str,
                            maks_ukuran_bytes: int | None = None) -> tuple:
    """Validasi ekstensi/isi/ukuran (aturan SAMA seperti yang sudah dipakai
    tiap modul sebelum migrasi R2 -- lihat pemanggil masing-masing untuk
    ext_map & batas ukurannya), lalu hasilkan NAMA FILE UNIK (uuid4 hex,
    supaya tidak ada tabrakan key di bucket walau nama file asli sama persis
    -- juga otomatis jadi cache-buster baru di `?v=` yang sudah dipakai
    setiap endpoint GET, tidak berubah).
    Return (nama_file_unik, content_type)."""
    ext = filename_asli.rsplit(".", 1)[-1].lower() if "." in filename_asli else ""
    if ext not in ext_map:
        raise ValueError(f"Format {label} tidak didukung.")
    if not konten:
        raise ValueError(f"File {label} kosong.")
    if maks_ukuran_bytes and len(konten) > maks_ukuran_bytes:
        raise ValueError(f"Ukuran {label} maksimal {maks_ukuran_bytes // (1024 * 1024)}MB.")
    nama_file = f"{uuid.uuid4().hex}.{ext}"
    return nama_file, ext_map[ext]


def upload(prefix: str, nama_file: str, konten: bytes, content_type: str) -> str:
    """Upload ke R2 di bawah folder `prefix/` (mis. "logos", "barbers",
    "gallery", "payments", "assets") -- return OBJECT KEY LENGKAP (disimpan
    di kolom `*_r2_key` di database, BUKAN bytes-nya). Retry otomatis lewat
    konfigurasi boto3 di atas (3x, exponential backoff bawaan botocore)
    untuk kegagalan transient (timeout/network/5xx) -- kegagalan yang
    menetap dilempar sebagai R2Error setelah retry habis."""
    if not IS_ENABLED:
        raise R2Error("Storage R2 belum dikonfigurasi (environment variable R2_* belum lengkap).")
    object_key = f"{prefix.strip('/')}/{nama_file}"
    try:
        _get_client().put_object(
            Bucket=R2_BUCKET_NAME, Key=object_key, Body=konten, ContentType=content_type,
        )
    except (BotoCoreError, ClientError) as e:
        logger.error("R2 upload gagal (key=%s): %s", object_key, e)
        raise R2Error(f"Upload file ke storage gagal, silakan coba lagi. ({e})") from e
    return object_key


def get_bytes(object_key: str):
    """Return (bytes, content_type) kalau ada, atau (None, None) kalau
    object_key kosong/belum pernah diupload/gagal dibaca -- SENGAJA tidak
    melempar exception di jalur baca (endpoint GET pemanggil sudah punya
    pola `if data is None: raise HTTPException(404, ...)` yang sama persis
    dipakai untuk "belum pernah upload" -- kegagalan baca R2 diperlakukan
    setara "tidak ada", supaya UI tidak pernah pecah gara-gara error 500,
    cukup menampilkan gambar kosong seperti sebelum file diupload)."""
    if not IS_ENABLED or not object_key:
        return None, None
    try:
        obj = _get_client().get_object(Bucket=R2_BUCKET_NAME, Key=object_key)
        return obj["Body"].read(), obj.get("ContentType") or "application/octet-stream"
    except ClientError as e:
        kode = e.response.get("Error", {}).get("Code", "")
        if kode not in ("NoSuchKey", "404"):
            logger.error("R2 get_object gagal (key=%s): %s", object_key, e)
        return None, None
    except BotoCoreError as e:
        logger.error("R2 get_object gagal (key=%s): %s", object_key, e)
        return None, None


def delete(object_key: str):
    """Hapus object di R2 -- best-effort & idempotent (TIDAK PERNAH melempar
    error ke pemanggil, sama seperti file_asset_db.hapus() lama): dipanggil
    tiap kali file diganti/dihapus supaya tidak jadi file sampah menumpuk di
    bucket, tapi kegagalan hapus (mis. network sempat putus) tidak boleh
    membatalkan operasi utama (ganti/hapus data) yang sedang berjalan --
    cukup dicatat di log sebagai sisa yang bisa dibersihkan manual nanti."""
    if not IS_ENABLED or not object_key:
        return
    try:
        _get_client().delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
    except (BotoCoreError, ClientError) as e:
        logger.warning("R2 delete gagal (key=%s, dibiarkan sebagai sisa -- lihat log ini kalau perlu dibersihkan manual): %s", object_key, e)
