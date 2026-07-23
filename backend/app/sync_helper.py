"""sync_helper.py
================
BELUM diimplementasikan — placeholder sementara.

Poin #14/#16 di spesifikasi (sinkronisasi Google Sheets + credentials.json)
belum dikerjakan di tahap ini karena butuh sync.py (logika sinkronisasi
dari aplikasi Desktop) yang belum ada di repo ini sama sekali — belum ada
file itu untuk disalin. Supaya router Input Data / Produk / Pengeluaran
tetap bisa dipanggil sekarang tanpa error, sync_async() sengaja dibuat
no-op (tidak melakukan apa-apa) untuk sementara.

TODO (tahap sinkronisasi, menyusul):
- Salin sync.py VERBATIM dari aplikasi Desktop ke folder ini (sama seperti
  database.py), lalu panggil fungsi sync-nya di sini.
- Jalankan di background thread (bukan blocking response API) supaya user
  tidak menunggu proses upload ke Google Sheets setiap simpan data.
- credentials.json dibaca dari backend/app/credentials.json (tidak ikut
  git — lihat README, harus di-copy manual saat deploy) atau dari
  environment variable GOOGLE_CREDENTIALS_JSON di Render.
"""


def sync_async():
    """No-op untuk sementara. Dipanggil di titik yang sama persis dengan
    tempat sync.py nanti akan dipanggil, supaya saat sync.py sudah ada,
    tinggal isi fungsi ini tanpa perlu ubah router manapun."""
    pass
