"""whatsapp_templates.py — Isi pesan WhatsApp otomatis Booking (Fonnte, lihat
whatsapp_service.py).

REVISI: teks pesan sekarang BISA DIATUR SENDIRI oleh Owner lewat Setting >
WhatsApp (lihat whatsapp_service.get_templates()/set_templates(), routers/
pengaturan.py) -- DEFAULT_TEMPLATES di bawah ini HANYA dipakai kalau Owner
belum pernah mengubahnya sama sekali (sama seperti pola PERMISSION_DEFS di
permissions.py: default murni prasangka awal). Placeholder `{nama}`/`{toko}`/
`{nominal}`/`{layanan}`/`{tanggal}`/`{jam}` di teks (custom MAUPUN default)
diganti otomatis oleh render() -- SATU-SATUNYA tempat yang tahu cara mengisi
placeholder ini, dipanggil dari booking_db.py.

Substitusi lewat str.replace() manual (BUKAN str.format()) SENGAJA -- teks
custom dari Owner bisa berisi kurung kurawal liar/typo placeholder tanpa
membuat pengiriman pesan gagal (str.format() akan melempar KeyError/
IndexError untuk itu, whatsapp_service.kirim_whatsapp() harus tetap "best
effort" jalan terus).

WhatsApp TIDAK mendukung HTML -- teks polos dengan markup ringan Fonnte/
WhatsApp sendiri (*tebal*) boleh dipakai."""

from datetime import datetime

# (jenis, label, deskripsi) -- dipakai frontend (Setting > WhatsApp) untuk
# menyusun textarea per jenis pesan + label placeholder yang bisa dipakai.
JENIS_PESAN = [
    ("reminder_qris", "Reminder Bayar QRIS",
     "Dikirim saat customer booking metode QRIS, atau saat Admin menekan \"Verifikasi Booking\" untuk booking QRIS yang belum dibayar."),
    ("konfirmasi_pembayaran", "Konfirmasi Pembayaran",
     "Dikirim saat pembayaran diverifikasi (manual oleh Admin/Owner, atau otomatis lewat Payment Gateway)."),
    ("pembatalan", "Pembatalan Booking", "Dikirim saat booking dibatalkan karena belum dibayar."),
    # Pesan Otomatis Berdasarkan Jam Operasional Tenant: dikirim TAMBAHAN
    # (bukan pengganti) apa pun notifikasi lain yang sudah terkirim untuk
    # metode pembayarannya (mis. tetap dapat "Reminder Bayar QRIS" juga
    # kalau metodenya QRIS) -- pesan ini KHUSUS memberi tahu toko sedang
    # tutup, terlepas metode pembayaran apa pun.
    ("booking_luar_jam_operasional", "Booking di Luar Jam Operasional",
     "Dikirim otomatis begitu booking dibuat SAAT toko sedang di luar jam operasional (untuk SEMUA metode pembayaran)."),
]

PLACEHOLDER_INFO = [
    ("{nama}", "Nama customer"), ("{toko}", "Nama barbershop"), ("{nominal}", "Total harga (format Rupiah)"),
    ("{layanan}", "Daftar layanan yang dibooking"), ("{tanggal}", "Tanggal booking"), ("{jam}", "Jam booking"),
    ("{jam_buka}", "Jam buka toko berikutnya (khusus pesan Booking di Luar Jam Operasional)"),
]

DEFAULT_TEMPLATES = {
    "reminder_qris": (
        "Halo {nama}, terima kasih sudah booking di *{toko}*.\n\n"
        "Silakan selesaikan pembayaran sebesar *{nominal}* melalui QRIS yang tertera untuk booking:\n"
        "- Layanan: {layanan}\n"
        "- Tanggal: {tanggal}, {jam}\n\n"
        "Booking akan otomatis kami proses setelah pembayaran diverifikasi."
    ),
    "konfirmasi_pembayaran": (
        "Halo {nama}, pembayaran Anda sebesar *{nominal}* untuk booking di *{toko}* telah kami terima & "
        "verifikasi:\n"
        "- Layanan: {layanan}\n"
        "- Tanggal: {tanggal}, {jam}\n\n"
        "Sampai jumpa!"
    ),
    "pembatalan": (
        "Halo {nama}, mohon maaf booking Anda di *{toko}* berikut ini kami batalkan karena pembayaran belum "
        "kami terima:\n"
        "- Layanan: {layanan}\n"
        "- Tanggal: {tanggal}, {jam}\n\n"
        "Silakan booking ulang jika masih berminat."
    ),
    "booking_luar_jam_operasional": (
        "Booking Anda telah diterima. Saat ini *{toko}* sudah di luar jam operasional. Tim kami akan "
        "menghubungi Anda untuk konfirmasi pada jam operasional berikutnya, mulai pukul {jam_buka}."
    ),
}


def _rupiah(v) -> str:
    return "Rp " + f"{int(v):,}".replace(",", ".")


def _tanggal_indo(tanggal: str) -> str:
    _BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
              "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    try:
        d = datetime.strptime(tanggal, "%Y-%m-%d")
        return f"{d.day} {_BULAN[d.month]} {d.year}"
    except (ValueError, TypeError):
        return tanggal


def render(jenis: str, booking: dict, nama_toko: str, template_text: str = None) -> str:
    """`template_text` = teks custom milik tenant (kosong/None -> pakai
    DEFAULT_TEMPLATES[jenis])."""
    teks = (template_text or "").strip() or DEFAULT_TEMPLATES[jenis]
    nilai = {
        "nama": booking["customer_nama"],
        "toko": nama_toko,
        "nominal": _rupiah(booking["total_harga"]),
        "layanan": booking["daftar_service"],
        "tanggal": _tanggal_indo(booking["tanggal"]),
        "jam": booking["jam_mulai"],
        # Pesan Otomatis Berdasarkan Jam Operasional Tenant: HANYA terisi
        # untuk jenis "booking_luar_jam_operasional" (booking_db.py yang
        # menyisipkan field transien ini ke dict `booking` SEBELUM
        # memanggil render() -- lihat _kirim_notifikasi_wa_booking()) --
        # `.get()` supaya jenis lain yang tidak menyertakan placeholder ini
        # di templatenya tetap aman walau field-nya kosong.
        "jam_buka": booking.get("jam_buka", ""),
    }
    for key, val in nilai.items():
        teks = teks.replace("{" + key + "}", str(val))
    return teks
