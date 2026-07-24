"""sync_helper.py — TAHAP 12: Sinkronisasi Google Sheets & status cloud sync.

Sebelum tahap ini, sync_async() adalah no-op (lihat riwayat git) -- dipanggil
di titik yang SAMA PERSIS di routers/input_data.py, routers/pengeluaran.py,
dan routers/produk.py sejak tahap-tahap itu ditulis, justru supaya begitu
sinkron sungguhan diisi di sini, TIDAK ADA satu pun router yang perlu
diubah. Tahap 12 mengisi fungsi itu, murni menambah "sinkron ke cloud
setelah data tersimpan", TIDAK mengubah apa yang disimpan atau bagaimana
data itu dihitung (komisi/bonus/dll tetap 100% di database.py, tidak
disentuh sama sekali di sini).

Alur tiap kali sync_async() dipanggil (SETELAH data sudah tersimpan lokal
di SQLite oleh caller -- simpan lokal SELALU berhasil duluan, terlepas dari
apa pun yang terjadi di bawah ini):
1. Tandai ada 1 perubahan baru (write_counter++) -- cepat, murni lokal,
   supaya status "jumlah belum sinkron" langsung akurat walau proses upload
   di bawah belum/gagal jalan.
2. Coba kirim snapshot terbaru semua tabel yang disinkronkan ke Google
   Sheets, di BACKGROUND THREAD supaya request API pemanggil tidak ikut
   menunggu proses upload (bisa lambat / timeout kalau internet lambat).
   Kalau gagal (offline, belum dikonfigurasi, quota, dll) -- dicatat sebagai
   status "gagal", TIDAK PERNAH dilempar sebagai exception ke pemanggil.

"Sinkronkan Sekarang" (tombol di halaman Status Sinkronisasi) dan retry
otomatis berkala sama-sama memanggil sync_now() -- versi blocking dari
proses yang sama, supaya hasilnya (berhasil/gagal) bisa langsung
ditampilkan ke user."""

import threading
import time
import traceback
from datetime import datetime, timezone

import database as db
import pengeluaran_db
import sync_meta_db as meta
import google_sheets_client as sheets

_lock = threading.Lock()

ENTITAS_DISINKRONKAN = ["transaksi", "absensi_libur", "pengeluaran", "produk", "produk_mutasi"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _snapshot_semua_entitas() -> dict:
    """Baca ulang data TERBARU lewat fungsi baca yang SUDAH ADA (database.py /
    pengeluaran_db.py) -- read-only, tidak mengubah satu baris pun, dan tidak
    menduplikasi logika hitung apa pun (nilai yang dikirim ke Sheets persis
    yang sudah tersimpan/dihitung di SQLite)."""
    # get_transaksi_list() sudah menyertakan 'daftar_service' (ringkasan teks
    # siap-baca) selain 'items' (list of dict mentah) -- untuk snapshot ke
    # Sheets cukup ringkasannya saja, list mentahnya dibuang di sini supaya
    # setiap baris di tab "transaksi" tetap satu baris flat.
    transaksi = db.get_transaksi_list()
    for t in transaksi:
        t.pop("items", None)
    return {
        "transaksi": transaksi,
        "absensi_libur": db.get_libur_list(),
        "pengeluaran": pengeluaran_db.get_pengeluaran_list(),
        "produk": db.get_produk_list(hanya_aktif=False),
        "produk_mutasi": db.get_mutasi_produk_list(),
    }


def get_status() -> dict:
    write_counter = meta.get_meta_int("write_counter", 0)
    synced_counter = meta.get_meta_int("synced_counter", 0)
    return {
        "dikonfigurasi": sheets.is_configured(),
        "jumlah_belum_sinkron": max(0, write_counter - synced_counter),
        "last_sync_at": meta.get_meta("last_sync_at"),
        "last_attempt_at": meta.get_meta("last_attempt_at"),
        "last_sync_status": meta.get_meta("last_sync_status", "belum_pernah"),
        "last_sync_message": meta.get_meta("last_sync_message", ""),
    }


def sync_now() -> dict:
    """Sinkron SEKARANG, blocking -- dipakai tombol 'Sinkronkan Sekarang' dan
    retry otomatis berkala. Aman dipanggil kapan saja: tidak pernah melempar
    exception ke pemanggil, hanya mencatat status berhasil/gagal."""
    with _lock:
        percobaan_pada = _now_iso()
        meta.set_meta("last_attempt_at", percobaan_pada)

        if not sheets.is_configured():
            meta.set_meta("last_sync_status", "gagal")
            meta.set_meta(
                "last_sync_message",
                "Google Sheets belum dikonfigurasi (GOOGLE_SHEET_ID / kredensial "
                "service account belum diisi) -- data tetap aman di database lokal.",
            )
            return get_status()

        # Nilai write_counter DIBACA SEBELUM snapshot diambil: kalau ada
        # perubahan baru masuk SELAGI proses upload berjalan, perubahan itu
        # akan tetap tercatat "belum sinkron" dan diambil di percobaan
        # berikutnya (bukan ikut ditandai sinkron secara keliru).
        counter_saat_ini = meta.get_meta_int("write_counter", 0)
        try:
            snapshot = _snapshot_semua_entitas()
            for entitas in ENTITAS_DISINKRONKAN:
                sheets.push_snapshot(entitas, snapshot[entitas])
        except Exception as e:  # noqa: BLE001 - sengaja tangkap semua, sinkron tidak boleh menjatuhkan aplikasi
            meta.set_meta("last_sync_status", "gagal")
            meta.set_meta("last_sync_message", str(e) or e.__class__.__name__)
            return get_status()

        meta.set_meta("synced_counter", str(counter_saat_ini))
        meta.set_meta("last_sync_at", percobaan_pada)
        meta.set_meta("last_sync_status", "berhasil")
        meta.set_meta("last_sync_message", "")
        return get_status()


def _coba_sync_diam_diam() -> None:
    try:
        sync_now()
    except Exception:  # noqa: BLE001 - thread background, tidak boleh sampai crash diam-diam tanpa jejak
        traceback.print_exc()


def sync_async() -> None:
    """Dipanggil persis di titik yang sama seperti sebelum Tahap 12 (setelah
    setiap simpan/koreksi/hapus di Input Data, Pengeluaran, Produk). Data
    sudah tersimpan lokal duluan oleh caller sebelum baris ini dijalankan --
    fungsi ini murni soal sinkron ke cloud, apa pun hasilnya tidak pernah
    membuat simpan lokal dianggap gagal."""
    try:
        meta.increment_write_counter()
    except Exception:  # noqa: BLE001 - statistik sinkron tidak boleh ikut menggagalkan simpan data
        traceback.print_exc()
        return
    threading.Thread(target=_coba_sync_diam_diam, daemon=True).start()


def _retry_loop(interval_detik: int) -> None:
    while True:
        time.sleep(interval_detik)
        try:
            if get_status()["jumlah_belum_sinkron"] > 0:
                sync_now()
        except Exception:  # noqa: BLE001 - loop latar belakang, jangan sampai berhenti karena satu error
            traceback.print_exc()


def start_background_retry_loop() -> None:
    """Dipanggil sekali saat startup (main.py). Ini yang memenuhi "saat
    koneksi kembali normal, data yang belum tersinkron dikirim otomatis" --
    dicoba ulang berkala tanpa perlu user membuka halaman Sinkronisasi atau
    menekan tombol apa pun."""
    import os
    interval = int(os.environ.get("SYNC_RETRY_INTERVAL_DETIK", "60"))
    threading.Thread(target=_retry_loop, args=(interval,), daemon=True).start()
