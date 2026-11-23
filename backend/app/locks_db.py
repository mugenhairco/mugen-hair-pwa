"""locks_db.py — Factory kecil untuk lock in-process per-key
=============================================================================
BUGFIX (code-review audit menyeluruh babak 2, catatan minor #2):
kuota_libur_db.py dan rekap_gabungan_db.py masing-masing mendefinisikan
sendiri pola `defaultdict(threading.Lock)` + fungsi pembungkus untuk
mengunci per (barber_id, tanggal) -- identik satu sama lain. Ditarik ke
SATU factory di sini supaya kalau strategi locking-nya nanti perlu
diubah (mis. ditambah eviction supaya dict tidak membesar tanpa batas
selama proses hidup lama), cukup diubah di SATU tempat, tidak dua (atau
lebih, kalau ada modul baru lagi ke depannya) secara terpisah dan rawan
kelewat salah satu.

TIDAK mengubah modul `kasbon_db.py`/`slip_gaji_db.py` yang sudah ada --
keduanya mengunci per SATU id (bukan tuple komposit) dan sudah berjalan
lama tanpa masalah; di luar cakupan code-review yang memicu perubahan
ini (yang hanya menyoroti DUA modul yang BARU ditambahkan dalam audit
yang sama)."""

import threading
from collections import defaultdict
from typing import Callable


def buat_pengambil_kunci() -> Callable[..., threading.Lock]:
    """Return fungsi `ambil(*key_parts) -> threading.Lock` yang selalu
    mengembalikan objek Lock YANG SAMA untuk kombinasi `key_parts` yang
    sama (key boleh satu nilai atau beberapa -- digabung jadi tuple).
    Satu `defaultdict` terpisah dibuat per PEMANGGIL factory ini (bukan
    dibagi global) supaya lock satu modul tidak pernah bertabrakan
    dengan lock modul lain walau kebetulan key-nya sama."""
    kunci_per_key: dict[tuple, threading.Lock] = defaultdict(threading.Lock)

    def ambil(*key_parts) -> threading.Lock:
        return kunci_per_key[key_parts]

    return ambil
