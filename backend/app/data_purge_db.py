"""data_purge_db.py — FITUR Pembersihan Data Bulanan Otomatis
=============================================================================
Permintaan Owner: setiap tanggal 10, hapus PERMANEN seluruh data operasional
yang sudah lebih lama dari bulan berjalan (tanggal < tanggal 1 bulan ini) --
ATURAN SERAGAM, TIDAK dibedakan siklus pertama kali (catch-up seluruh
backlog lama) vs siklus bulanan biasa (hanya bulan lalu) -- keduanya memakai
cutoff yang SAMA, jadi tenant yang baru pertama kali diaktifkan fiturnya
otomatis "mengejar" seluruh riwayat lamanya di siklus pertama tanpa logika
spesial. Dipicu EKSTERNAL lewat routers/cron_purge_data.py (pola SAMA PERSIS
absensi_reminder_db.py/routers/cron_reminder.py) -- TIDAK ada proses latar
belakang di dalam aplikasi.

Tujuh kategori, DUA kelompok:

1. PERLU ARSIP PDF dulu (dikirim ke email tenant SEBELUM dihapus):
   - Rekap Transaksi Barber -- 1 PDF Detail PER barber (termasuk yang
     sudah nonaktif, lihat get_barbers(hanya_aktif=False)) + 1 PDF
     Ringkasan gabungan SEMUA barber.
   - Riwayat Absensi (attendance_logs) -- 1 PDF gabungan semua barber
     (pola SAMA seperti tombol "Cetak PDF" yang sudah ada di tab Daftar
     Absensi).
   - Riwayat Mutasi Produk (restock/jual/tester) -- 1 PDF gabungan semua
     produk (pola SAMA seperti tombol "Cetak PDF" yang sudah ada di menu
     Produk).
   KETIGANYA dikirim lewat SATU email (satu lampiran per PDF) -- supaya
   "sudah terkirim" berarti SATU keputusan all-or-nothing: kalau emailnya
   GAGAL terkirim (Resend belum dikonfigurasi/API error/tenant belum punya
   email terdaftar), KETIGA kategori ini TIDAK dihapus siklus ini --
   dicoba lagi bulan depan dengan cutoff yang lebih baru (backlog makin
   besar, bukan hilang). Prinsip: PDF adalah jaring pengaman, menghapus
   data tanpa jaring pengaman itu terkirim MELANGGAR tujuan fitur ini.

2. HAPUS LANGSUNG (tanpa PDF, tidak bergantung status email di atas):
   - Booking Customer (+ turunannya) -- pakai booking_db.hapus_riwayat_booking()
     yang SUDAH ADA (dulu dipakai tombol manual "Reset Riwayat Booking").
   - Log Audit & jejak mentah percobaan Check In/Out (attendance_audit_logs).
   - Riwayat Pengajuan Koreksi Absensi yang SUDAH diputuskan (status !=
     'pending' -- yang masih pending TIDAK PERNAH ikut terhapus).
   - Slip Gaji, BAIK 'belum_dibayar' MAUPUN 'sudah_dibayar' (permintaan
     eksplisit Owner, BEDA dari hapus_slip_gaji() manual yang menolak
     status 'sudah_dibayar') -- lihat slip_gaji_db.hapus_slip_gaji_sebelum()
     untuk penjelasan lengkap penanganan FK kasbon_pembayaran.

Riwayat Mutasi Produk PERLU langkah tambahan SEBELUM dihapus: saldo stok
dihitung ulang dari SELURUH riwayat produk_mutasi (TIDAK ada kolom stok
tersimpan) -- menghapus baris lama begitu saja akan membuat
get_stok_produk() menghitung dari titik nol lagi. database.py::
arsipkan_dan_hapus_mutasi_lama() membawa saldo bersihnya ke SATU baris
sintetis tipe='saldo_awal' SEBELUM baris lama benar-benar dihapus (lihat
docstring fungsi itu) -- dipanggil di sini PER produk.

TIDAK ADA tabel/pencatatan idempotensi terpisah -- pipeline ini aman
dipanggil berulang TANPA efek samping (idempotent "by construction"):
kalau sebuah tenant sudah dibersihkan sampai cutoff bulan ini, pemanggilan
kedua di hari yang sama tidak menemukan baris tersisa di rentang itu
(SEMUA fungsi hapus_*/arsipkan_* di atas sudah di-scope `tanggal < cutoff`)
-- jadi tidak ada apa pun untuk diarsipkan/dihapus lagi, dan tidak ada
email dobel terkirim. Penjaga TANGGAL_JALAN di bawah (hanya jalan tanggal
10) murni pengaman tambahan kalau cron eksternal salah dikonfigurasi
memanggil tiap hari."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import attendance_db
import booking_db
import database as db
import laporan_pdf
import slip_gaji_db
import tenant_db
from email_service import kirim_email

logger = logging.getLogger("mugen.data_purge")

WIB = ZoneInfo("Asia/Jakarta")

TANGGAL_JALAN = 10  # tanggal 10 setiap bulan -- lihat catatan modul

DICETAK_OLEH = "Sistem (Pembersihan Data Otomatis)"


def _sekarang_wib() -> datetime:
    return datetime.now(WIB)


def _cutoff_bulan_ini(sekarang: datetime) -> str:
    """Awal bulan berjalan ("YYYY-MM-01") -- SEMUA data bertanggal lebih
    lama dari ini dibersihkan, lihat catatan "ATURAN SERAGAM" di atas."""
    return sekarang.strftime("%Y-%m-01")


def _sehari_sebelum(tanggal: str) -> str:
    return (datetime.strptime(tanggal, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


def _tanggal_mulai_arsip(tenant: dict) -> str:
    """Batas awal rentang PDF arsip -- dipakai sebagai `tanggal_mulai` di
    SELURUH generator PDF di bawah. Sengaja TIDAK menghitung tanggal data
    paling lama yang sesungguhnya lewat query tambahan -- tanggal
    `created_at` tenant ini sudah PASTI sama atau lebih awal dari baris
    data apa pun miliknya (tidak ada data yang bisa tercatat sebelum
    tenant-nya sendiri dibuat), dan rentang tanggal yang lebih lebar dari
    yang sesungguhnya TIDAK mengubah data yang ikut ter-filter (query
    filter tanggal >= tanggal_mulai, kosong = tidak ada baris yang hilang/
    ekstra) -- jadi cukup dipakai apa adanya, tanpa query tambahan per
    kategori."""
    created_at = (tenant.get("created_at") or "")[:10]
    if len(created_at) == 10:
        return created_at
    return "2020-01-01"  # jaga-jaga kalau created_at kosong/tidak terbaca


def _kirim_arsip_dan_hapus_kategori_pdf(tenant: dict, cutoff: str) -> dict:
    """Kelompok 1 (lihat catatan modul): bangun PDF Rekap Transaksi
    (per barber + ringkasan)/Riwayat Absensi/Riwayat Mutasi Produk untuk
    rentang [tanggal_mulai_arsip, cutoff - 1 hari], kirim SATU email kalau
    ada isinya, LALU hapus ketiga kategori itu HANYA kalau email berhasil
    terkirim (lihat alasan lengkap di catatan modul). Mengembalikan
    ringkasan jumlah untuk log/respons endpoint."""
    tenant_id = tenant["id"]
    tanggal_mulai = _tanggal_mulai_arsip(tenant)
    tanggal_selesai = _sehari_sebelum(cutoff)
    hasil = {"email_terkirim": None, "transaksi_dihapus": 0, "absensi_dihapus": 0, "produk_diarsipkan": 0}

    lampiran = []

    barbers = db.get_barbers(hanya_aktif=False, tenant_id=tenant_id)
    ada_transaksi = False
    for barber in barbers:
        data_barber = db.get_rekap_transaksi_list(barber_id=barber["id"], tanggal_mulai=tanggal_mulai,
                                                    tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
        if not data_barber:
            continue
        ada_transaksi = True
        pdf_bytes = laporan_pdf.buat_pdf_rekap_transaksi(
            None, None, barber["id"], DICETAK_OLEH, tanggal_mulai=tanggal_mulai,
            tanggal_selesai=tanggal_selesai, tenant_id=tenant_id,
        )
        nama_file = f"Rekap-Transaksi-{barber['nama']}.pdf".replace(" ", "-")
        lampiran.append((nama_file, pdf_bytes))
    if ada_transaksi:
        ringkasan_bytes = laporan_pdf.buat_pdf_rekap_transaksi_ringkasan(
            None, None, None, DICETAK_OLEH, tanggal_mulai=tanggal_mulai,
            tanggal_selesai=tanggal_selesai, tenant_id=tenant_id,
        )
        lampiran.append(("Rekap-Transaksi-Ringkasan-Semua-Barber.pdf", ringkasan_bytes))

    data_absensi = attendance_db.get_log_list(tenant_id, tanggal_dari=tanggal_mulai, tanggal_sampai=tanggal_selesai)
    if data_absensi:
        pdf_bytes = laporan_pdf.buat_pdf_absensi_list(
            None, tanggal_mulai, tanggal_selesai, None, None, DICETAK_OLEH, tenant_id=tenant_id,
        )
        lampiran.append(("Riwayat-Absensi.pdf", pdf_bytes))

    data_produk = db.get_mutasi_produk_list(tenant_id=tenant_id, tanggal_mulai=tanggal_mulai,
                                              tanggal_selesai=tanggal_selesai)
    if data_produk:
        pdf_bytes = laporan_pdf.buat_pdf_mutasi_produk(
            None, None, None, None, DICETAK_OLEH, tenant_id=tenant_id,
            tanggal_mulai=tanggal_mulai, tanggal_selesai=tanggal_selesai,
        )
        lampiran.append(("Riwayat-Mutasi-Produk.pdf", pdf_bytes))

    if not lampiran:
        # Tidak ada data sama sekali di ketiga kategori ini pada rentang
        # itu -- tidak ada yang perlu diarsipkan MAUPUN dihapus, lewati
        # langsung (tidak terhitung gagal, cukup "tidak ada kerjaan").
        return hasil

    email_tenant = (tenant.get("email") or "").strip()
    if not email_tenant:
        logger.warning(
            "Pembersihan Data: tenant_id=%s TIDAK punya email terdaftar -- Rekap Transaksi/Absensi/"
            "Mutasi Produk TIDAK dihapus siklus ini (dicoba lagi bulan depan).", tenant_id,
        )
        hasil["email_terkirim"] = False
        return hasil

    nama_toko = tenant.get("nama_barbershop") or tenant.get("slug") or "Toko Anda"
    html = (
        f"<p>Halo,</p>"
        f"<p>Berikut arsip data operasional {nama_toko} periode "
        f"<b>{tanggal_mulai}</b> s/d <b>{tanggal_selesai}</b>, dikirim otomatis setiap tanggal {TANGGAL_JALAN} "
        f"sebagai bagian dari pengarsipan rutin sistem.</p>"
        f"<p>Arsip lengkap data tersebut terlampir dalam bentuk PDF.</p>"
        f"<p>Email ini dikirim otomatis, tidak perlu dibalas.</p>"
    )
    terkirim = kirim_email(email_tenant, f"Arsip Data Bulanan - {nama_toko}", html,
                            attachments=lampiran)
    hasil["email_terkirim"] = terkirim
    if not terkirim:
        logger.warning(
            "Pembersihan Data: tenant_id=%s GAGAL kirim email arsip -- Rekap Transaksi/Absensi/Mutasi "
            "Produk TIDAK dihapus siklus ini (dicoba lagi bulan depan).", tenant_id,
        )
        return hasil

    if ada_transaksi:
        hasil["transaksi_dihapus"] = db.hapus_riwayat_transaksi(tenant_id, cutoff)
    if data_absensi:
        hasil["absensi_dihapus"] = attendance_db.hapus_riwayat_absensi(tenant_id, sebelum_tanggal=cutoff)
    if data_produk:
        produk_list = db.get_produk_list(hanya_aktif=False, tenant_id=tenant_id)
        for produk in produk_list:
            if db.arsipkan_dan_hapus_mutasi_lama(produk["id"], cutoff) is not None:
                hasil["produk_diarsipkan"] += 1

    return hasil


def _hapus_kategori_tanpa_pdf(tenant_id: int, cutoff: str) -> dict:
    """Kelompok 2 (lihat catatan modul): Booking/Log Audit/Pengajuan
    Koreksi (yang sudah diputuskan)/Slip Gaji -- dihapus LANGSUNG, TIDAK
    bergantung sama sekali pada hasil email arsip kelompok 1."""
    return {
        "booking_dihapus": booking_db.hapus_riwayat_booking(tenant_id, sebelum_tanggal=cutoff),
        "audit_log_dihapus": attendance_db.hapus_audit_log_sebelum(tenant_id, cutoff),
        "koreksi_dihapus": attendance_db.hapus_koreksi_terputuskan_sebelum(tenant_id, cutoff),
        "slip_gaji_dihapus": slip_gaji_db.hapus_slip_gaji_sebelum(tenant_id, cutoff),
    }


def jalankan_pembersihan(paksa: bool = False) -> dict:
    """Loop SELURUH tenant (lihat catatan modul -- TIDAK disaring status
    'aktif', berbeda dari absensi_reminder_db.py, karena ini pembersihan
    data murni, bukan fitur berbayar, dan tenant suspended pun tetap
    menumpuk data yang perlu dibersihkan). Satu tenant gagal (exception
    apa pun) TIDAK menghentikan tenant lain -- dicatat log & dilanjutkan.

    `paksa` (dipakai Superadmin/debug, BUKAN jalur cron) -- True
    melewati penjagaan TANGGAL_JALAN, berguna untuk menjalankan ulang
    manual kalau cron sempat terlewat. Jalur cron EKSTERNAL (routers/
    cron_purge_data.py) SELALU memanggil tanpa `paksa` (default False)."""
    sekarang = _sekarang_wib()
    if not paksa and sekarang.day != TANGGAL_JALAN:
        return {"dijalankan": False, "alasan": f"bukan tanggal {TANGGAL_JALAN}"}

    cutoff = _cutoff_bulan_ini(sekarang)
    ringkasan = {"dijalankan": True, "cutoff": cutoff, "tenant_diperiksa": 0, "tenant_gagal": 0, "per_tenant": {}}

    for tenant in tenant_db.list_tenants():
        tenant_id = tenant["id"]
        ringkasan["tenant_diperiksa"] += 1
        try:
            hasil_pdf = _kirim_arsip_dan_hapus_kategori_pdf(tenant, cutoff)
            hasil_langsung = _hapus_kategori_tanpa_pdf(tenant_id, cutoff)
            ringkasan["per_tenant"][str(tenant_id)] = {**hasil_pdf, **hasil_langsung}
        except Exception as e:
            ringkasan["tenant_gagal"] += 1
            logger.error("Pembersihan Data GAGAL untuk tenant_id=%s: %s: %s", tenant_id, type(e).__name__, e)

    return ringkasan
