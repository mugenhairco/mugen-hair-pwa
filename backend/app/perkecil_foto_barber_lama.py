#!/usr/bin/env python3
"""
perkecil_foto_barber_lama.py — Backfill SATU KALI: perkecil & kompres foto
barber yang SUDAH ADA sebelum perbaikan performa di booking_db.py (lihat
_perkecil_foto_barber(), dipakai simpan_foto_barber() untuk upload BARU)
=========================================================================================
Foto barber yang diupload SEBELUM perbaikan itu tetap tersimpan MENTAH
ukuran asli upload (temuan log produksi: 11-14 detik/foto diunduh dari R2
untuk tampilan 92x92px, style.css::.book-barber-foto) -- perbaikan di
booking_db.py HANYA berlaku untuk upload BARU, TIDAK otomatis memperbaiki
baris yang sudah ada. Script ini membereskan baris lama itu SEKALI, dengan
fungsi perkecil yang SAMA PERSIS (booking_db._perkecil_foto_barber())
supaya hasilnya identik dengan upload baru, tidak ada logika terpisah yang
bisa berbeda/menyimpang.

Script MANUAL (dijalankan langsung lewat command line, TIDAK PERNAH
dipanggil otomatis dari main.py/on_startup ataupun proses lain mana pun),
mengikuti pola persis sama seperti migrate_blobs_to_r2.py (lihat file itu
untuk konteks arsitektur R2 lengkap).

ATURAN KESELAMATAN:
- HANYA menimpa ISI file foto (R2 object yang SAMA key-nya, atau kolom
  `barbers.foto_data`) dengan versi yang sudah diperkecil -- TIDAK PERNAH
  mengubah `foto_filename`/`foto_r2_key`/kolom lain. URL foto (yang
  menyertakan `?v=<foto_filename>`) tetap identik, jadi TIDAK ADA
  perubahan apa pun yang terlihat di frontend/API selain ukurannya.
- Baris yang hasil perkecilnya TIDAK lebih kecil dari aslinya (foto yang
  memang sudah kecil, atau gagal diproses -- lihat
  booking_db._perkecil_foto_barber()) dilewati (di-skip), bukan ditimpa.
- Idempotent & aman dijalankan berulang -- menjalankannya dua kali tidak
  memperkecil lagi (hasil kedua kali tidak akan lebih kecil dari hasil
  pertama, otomatis ter-skip sendiri lewat aturan di atas).
- --dry-run: hitung & tampilkan ukuran SEBELUM/SESUDAH tiap baris, TANPA
  menulis apa pun ke R2/database.
- Menolak berjalan sama sekali kalau DATABASE_URL tidak diisi (mencegah
  salah jalan ke SQLite lokal alih-alih Neon production).
- Baris yang foto-nya sudah di R2 (foto_r2_key terisi) TAPI environment
  variable R2_* belum lengkap di proses yang menjalankan script ini
  dilewati dengan peringatan jelas (TIDAK dihitung sebagai gagal diam-diam).

Cara pakai (manual, dari folder backend/app, DENGAN DATABASE_URL Neon DAN
env var R2_* lengkap diisi di environment yang menjalankan ini -- foto
barber produksi sudah dimigrasi ke R2):
    DATABASE_URL="postgresql://..." R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... \\
      R2_SECRET_ACCESS_KEY=... R2_BUCKET_NAME=... \\
      python perkecil_foto_barber_lama.py --dry-run   # lihat ukuran dulu, tidak menulis apa pun
    DATABASE_URL="postgresql://..." R2_ACCOUNT_ID=... ... python perkecil_foto_barber_lama.py  # jalankan sungguhan
"""

import argparse
import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import db_compat  # noqa: E402
import booking_db  # noqa: E402
import r2_storage  # noqa: E402
from database import get_conn  # noqa: E402


class MigrasiTidakDiizinkan(RuntimeError):
    """DATABASE_URL belum diisi -- tidak ada database production untuk
    diproses (lihat ATURAN KESELAMATAN di atas). Dipisah dari sys.exit()
    CLI supaya modul ini AMAN diimpor dari proses lain (lihat
    routers/migrasi_foto_barber.py -- endpoint sekali-pakai yang menjalankan
    jalankan_migrasi() di bawah DI DALAM proses backend yang sudah punya
    DATABASE_URL/R2_* production, tanpa modul ini sendiri pernah menyentuh
    kredensial apa pun secara langsung)."""


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""


def _baca_bytes_lama(row):
    """Return bytes foto SAAT INI (sebelum diperkecil), atau None kalau
    tidak bisa dibaca sama sekali (sumbernya bermasalah, bukan "sudah
    kecil" -- dibedakan di main() lewat pesan log yang berbeda)."""
    if row["foto_r2_key"]:
        if not r2_storage.IS_ENABLED:
            return None, "foto_r2_key ada tapi R2_* belum dikonfigurasi di proses ini"
        data, _ct = r2_storage.get_bytes(row["foto_r2_key"])
        if data is None:
            return None, f"gagal membaca {row['foto_r2_key']} dari R2"
        return data, None
    if row["foto_data"]:
        return bytes(row["foto_data"]), None
    return None, "tidak ada data foto sama sekali"


def _tulis_bytes_baru(row, hasil: bytes, ext: str):
    if row["foto_r2_key"]:
        prefix, nama_file = row["foto_r2_key"].rsplit("/", 1)
        content_type = booking_db.FOTO_EXT_KE_CONTENT_TYPE.get(ext, "application/octet-stream")
        r2_storage.upload(prefix, nama_file, hasil, content_type)
    else:
        with get_conn() as conn:
            conn.execute("UPDATE barbers SET foto_data = ? WHERE id = ?", (hasil, row["id"]))


def jalankan_migrasi(dry_run: bool) -> dict:
    """Inti migrasi, DIPAKAI BERSAMA oleh CLI (main() di bawah) dan endpoint
    sekali-pakai (routers/migrasi_foto_barber.py) -- SATU logika, bukan
    diduplikasi. Return dict ringkasan (lihat kunci di bawah) + "rincian"
    per-barber, supaya pemanggil (CLI mencetak, endpoint membalas JSON)
    bisa menyajikannya sesuai kebutuhan masing-masing tanpa mengulang
    perhitungan apa pun."""
    if not db_compat.IS_POSTGRES:
        raise MigrasiTidakDiizinkan(
            "DATABASE_URL belum diisi -- tidak ada database production untuk diproses.")

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, foto_filename, foto_data, foto_r2_key FROM barbers "
            "WHERE foto_filename IS NOT NULL "
            "AND (foto_r2_key IS NOT NULL OR (foto_data IS NOT NULL AND length(foto_data) > 0))"
        ).fetchall()

    diproses = 0
    dilewati = 0
    total_lama = 0
    total_baru = 0
    rincian = []
    for row in rows:
        data_lama, alasan_gagal = _baca_bytes_lama(row)
        if data_lama is None:
            dilewati += 1
            rincian.append({"barber_id": row["id"], "status": "skip", "alasan": alasan_gagal})
            continue

        ext = _ext(row["foto_filename"])
        hasil = booking_db._perkecil_foto_barber(data_lama, ext)
        if len(hasil) >= len(data_lama):
            dilewati += 1
            rincian.append({
                "barber_id": row["id"], "status": "skip",
                "alasan": f"sudah kecil/optimal ({len(data_lama)} bytes), tidak diubah",
            })
            continue

        if not dry_run:
            _tulis_bytes_baru(row, hasil, ext)

        diproses += 1
        total_lama += len(data_lama)
        total_baru += len(hasil)
        rincian.append({
            "barber_id": row["id"], "status": "ok",
            "ukuran_lama_bytes": len(data_lama), "ukuran_baru_bytes": len(hasil),
            "hemat_persen": round((1 - len(hasil) / len(data_lama)) * 100),
        })

    return {
        "dry_run": dry_run,
        "total_barber_punya_foto": len(rows),
        "diproses": diproses,
        "dilewati": dilewati,
        "total_ukuran_lama_bytes": total_lama,
        "total_ukuran_baru_bytes": total_baru,
        "hemat_persen_total": round((1 - total_baru / total_lama) * 100) if total_lama else 0,
        "rincian": rincian,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Hitung & tampilkan ukuran sebelum/sesudah saja, tidak menulis apa pun.")
    args = parser.parse_args()

    try:
        hasil = jalankan_migrasi(dry_run=args.dry_run)
    except MigrasiTidakDiizinkan as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"{hasil['total_barber_punya_foto']} barber punya foto. "
          f"({'DRY RUN -- tidak ada perubahan' if args.dry_run else 'JALAN SUNGGUHAN'})")
    print()
    for baris in hasil["rincian"]:
        if baris["status"] == "skip":
            print(f"  [SKIP] barber id={baris['barber_id']}: {baris['alasan']}.")
        else:
            print(f"  [OK] barber id={baris['barber_id']}: {baris['ukuran_lama_bytes']:,} -> "
                  f"{baris['ukuran_baru_bytes']:,} bytes (hemat {baris['hemat_persen']}%).")

    print()
    verb = "AKAN diperkecil" if args.dry_run else "berhasil diperkecil"
    if hasil["diproses"]:
        print(f"{hasil['diproses']} foto {verb}, {hasil['dilewati']} dilewati. "
              f"Total {hasil['total_ukuran_lama_bytes']:,} -> {hasil['total_ukuran_baru_bytes']:,} bytes "
              f"(hemat {hasil['hemat_persen_total']}%).")
    else:
        print(f"Tidak ada foto yang perlu diperkecil ({hasil['dilewati']} dilewati).")


if __name__ == "__main__":
    main()
