"""rate_limit_db.py — Rate limit sederhana IN-MEMORY untuk endpoint publik
=============================================================================
BUGFIX (audit "susuri menyeluruh" -- "tidak ada rate limit di endpoint
publik booking/cek-status"): tiga endpoint publik TANPA login (POST
/api/public/booking, /cek-status, /snap-cek-ulang/{ref}) sebelumnya bisa
dipanggil tanpa batas oleh siapa pun -- risikonya beda-beda per endpoint
(spam booking memenuhi slot, scraping data customer lewat nomor WA, memicu
panggilan keluar ke Faspay berkali-kali) tapi solusinya sama: batasi laju
panggilan per IP (dan per target spesifik untuk snap-cek-ulang).

SENGAJA in-memory murni (dict + lock, TIDAK ada tabel/migrasi baru) --
deployment ini SATU proses uvicorn tanpa --workers (lihat render.yaml),
jadi tidak perlu state terbagi lintas proses/Redis. Sliding window kasar
(bukan token bucket presisi) -- cukup untuk tujuannya (jaring pengaman
kasar, BUKAN kontrol kuota yang presisi), dan SENGAJA lebih longgar dari
batas yang benar-benar dibutuhkan (false positive memblokir customer asli
jauh lebih mahal daripada false negative melewatkan sedikit penyalahgunaan).

TIDAK membedakan tenant -- limit per (scope, key) MURNI berdasarkan
scope+key yang dioper caller (biasanya IP, kadang digabung dengan
identifier lain seperti payment_reference), lihat masing-masing
pemanggil di routers/booking.py."""

import threading
import time

_kunci = threading.Lock()
_hits: dict[tuple, list] = {}

# Jaga-jaga memori tidak membesar tanpa batas selama proses hidup lama --
# dibersihkan OPORTUNISTIK (tiap panggilan cek_dan_catat(), tidak perlu
# cron/background thread terpisah) kalau entry sudah tidak dipakai lebih
# dari ini.
_MAKS_UMUR_ENTRY_DETIK = 3600


def cek_dan_catat(scope: str, key: str, maks_percobaan: int, jendela_detik: int) -> bool:
    """Return True kalau request ini MASIH dalam batas (dan langsung
    dicatat sebagai satu percobaan), False kalau sudah melebihi
    `maks_percobaan` dalam `jendela_detik` detik terakhir -- caller yang
    memutuskan mau diapakan (biasanya HTTP 429). `scope` membedakan jenis
    limiter (mis. "booking_buat", "cek_status", "snap_cek_ulang") supaya
    `key` yang sama (mis. IP yang sama) tidak berbagi kuota antar endpoint
    yang beda risikonya."""
    sekarang = time.monotonic()
    pintu = (scope, key)
    with _kunci:
        # Beres-beres oportunistik: buang entry LAIN yang sudah lama tidak
        # disentuh sama sekali (bukan entry ini) -- murah karena hanya
        # iterasi dict yang biasanya kecil (jumlah IP aktif, bukan jumlah
        # request).
        kadaluwarsa = [k for k, v in _hits.items() if not v or sekarang - v[-1] > _MAKS_UMUR_ENTRY_DETIK]
        for k in kadaluwarsa:
            del _hits[k]

        riwayat = _hits.setdefault(pintu, [])
        batas_bawah = sekarang - jendela_detik
        riwayat[:] = [t for t in riwayat if t > batas_bawah]
        if len(riwayat) >= maks_percobaan:
            return False
        riwayat.append(sekarang)
        return True


def ambil_ip_client(request) -> str:
    """Pola SAMA PERSIS routers/attendance.py::_ekstrak_metadata() --
    X-Forwarded-For didahulukan (Render/reverse proxy lain selalu di depan
    aplikasi ini, request.client.host akan selalu berisi IP proxy
    internal, BUKAN IP asli pengunjung, kalau header itu tidak dicek
    dulu). Return "unknown" (BUKAN None) kalau benar-benar tidak ada info
    apa pun -- supaya tetap ada satu kunci yang konsisten dipakai limiter,
    bukan melempar error."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
