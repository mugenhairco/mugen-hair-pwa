"""
whatsapp_bot_parser.py — FITUR WA Bot: parsing perintah & dispatch command
=============================================================================
Lapisan AKAL dari WA Bot -- routers/whatsapp_bot.py (webhook) cuma
memanggil proses_pesan() satu kali per pesan masuk yang sah (lolos cek
nomor terdaftar + kuota), modul ini yang menguraikan isi pesan jadi
command, menjalankannya, dan mengembalikan teks balasan.

ARSITEKTUR AKSES (ringkasan, lihat spesifikasi percakapan Owner panjang
yang mendasari modul ini): SETIAP tenant punya SATU nomor "Owner" (kolom
whatsapp_bot_config.nomor_owner_whatsapp, Superadmin-managed, OPSIONAL)
yang kalau mengirim pesan dianggap akses PENUH (input data siapa saja +
lihat rekap siapa saja) -- BEDA dari barbers.nomor_whatsapp (nomor pribadi
tiap barber, akses TERBATAS ke datanya sendiri, KECUALI command Cuti/Izin
yang SENGAJA dibuka untuk semua barber, permintaan eksplisit Owner).
Nomor yang tidak cocok ke keduanya -> resolve_role() return (None, None),
proses_pesan() TIDAK membalas apa pun (silent -- supaya nomor acak di luar
sistem tidak tahu nomor ini "terhubung" ke Rivoir sama sekali).

ALUR KONFIRMASI (Input Data/Tandai Libur/Input Produk -- SEMUA command
yang MENULIS data): command ini TIDAK LANGSUNG menyimpan -- selalu
menghasilkan PREVIEW (ringkasan apa yang AKAN disimpan) + menyimpan baris
"pending" (whatsapp_bot_db.simpan_pending()), menunggu balasan YA/BATAL
dari pengirim yang SAMA. Ini SATU-SATUNYA jalan data WA Bot benar-benar
masuk ke tabel transaksi/produk_mutasi/absensi_libur -- mencegah salah
ketik/salah cocok service langsung tersimpan tanpa kesempatan koreksi.
Pending kedaluwarsa otomatis (lihat whatsapp_bot_db._JENDELA_PENDING_DETIK)
dan OTOMATIS TERTIMPA kalau pengirim yang sama mengirim command input BARU
sebelum membalas YA/BATAL yang lama (simpan_pending() upsert per pengirim).

PENCOCOKAN KODE SERVICE/PRODUK (dipakai Input Data & Input Produk, lihat
_cocokkan()): rantai exact match (case-insensitive) -> cocok awalan
(minimal 3 huruf) -> akronim huruf depan tiap kata ("Dry Cut" -> "DC").
Kalau cocok ke 0 ATAU 2+ kandidat sekaligus, TIDAK PERNAH menebak --
selalu minta klarifikasi (daftar bernomor) dan GAGALKAN SELURUH input itu
(tidak memproses baris lain secara parsial), supaya Owner tidak kaget ada
baris yang "diam-diam" ditebak salah.

INPUT HARIAN (permintaan Owner, pengganti form kertas "List Customer
Harian" -- lihat docstring _cmd_input_harian()): SATU PENGECUALIAN dari
aturan "gagal total" di atas -- gabungan banyak barber + Libur + Produk
dalam satu pesan, jadi kalau langsung gagal total di baris pertama yang
keliru, Owner harus ketik ULANG SELURUH pesan panjang itu dari awal.
Sebagai gantinya, parsing BERHENTI SEMENTARA tepat di baris yang
bermasalah (bot tanya spesifik), lalu LANJUT dari situ begitu Owner balas
koreksinya -- lihat whatsapp_bot_db jenis pending "input_harian_draft" vs
"input_harian" (siap-YA/BATAL) di _lanjutkan_parsing_input_harian()/
_terapkan_koreksi_input_harian().

REVISI (WA biasa, bukan Business): menu/command TETAP teks biasa (bukan
tombol/list interaktif WhatsApp Business) -- Owner memakai nomor WA biasa
untuk device Fonnte, belum dipastikan kompatibel dengan fitur interaktif
semacam itu."""

import re
import uuid
from datetime import date, timedelta

import attendance_db
import booking_db
import database as db
import izin_cuti_db
import kuota_libur_db
import uang_harian_dinamis_db
import whatsapp_bot_db

SUMBER_WA_BOT = "wa_bot"

_BULAN_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    # Singkatan 3 huruf umum (feedback Owner: "Rekap 18 okt" harus tetap
    # dikenali, bukan cuma nama bulan lengkap) -- "agt" ditambah sebagai
    # varian "agu" karena dua-duanya sama umum dipakai untuk Agustus.
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "agu": 8, "agt": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}
_NAMA_BULAN = {v: k.capitalize() for k, v in _BULAN_ID.items()}
_NAMA_BULAN_SINGKAT = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
    7: "Jul", 8: "Agu", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des",
}

POLA_SERVICE = r"^([A-Za-z][A-Za-z\s\+]*?)\s*(\d+)$"
POLA_PRODUK = r"^(.+?)\s+(\d+)$"


# ---------------------------------------------------------------------------
# Util format & parsing dasar (tanggal Bahasa Indonesia, nominal "30rb", dll)
# ---------------------------------------------------------------------------

def _rupiah(n: int) -> str:
    return f"Rp{int(n):,}".replace(",", ".")


def _cari_tanggal(teks: str):
    """Return (start, end, iso) dari substring tanggal PERTAMA yang
    ditemukan di `teks` (format '11 oktober 2026' / '11 oktober' / '11 okt',
    tahun opsional = tahun ini), atau None kalau tidak ada pola tanggal
    valid.

    BUGFIX nama bulan: alternasi regex Python mencoba tiap pilihan BERURUT
    dari kiri dan berhenti di yang PERTAMA cocok (bukan yang terpanjang) --
    kalau "okt" dicoba sebelum "oktober" di input "11 oktober 2026", yang
    kecocok cuma "okt" dan sisa "ober" bikin grup tahun opsional gagal
    cocok (butuh spasi tepat setelahnya), jadi TAHUN DIAM-DIAM TERABAIKAN
    dan jatuh ke default tahun ini -- salah tanpa error apa pun. Diurutkan
    terpanjang dulu supaya nama bulan lengkap SELALU menang sebelum
    singkatannya dicoba."""
    nama_bulan_terurut = sorted(_BULAN_ID.keys(), key=len, reverse=True)
    pola = r"(\d{1,2})\s+(" + "|".join(nama_bulan_terurut) + r")(?:\s+(\d{4}))?"
    m = re.search(pola, teks, re.IGNORECASE)
    if not m:
        return None
    hari = int(m.group(1))
    bulan = _BULAN_ID[m.group(2).lower()]
    tahun = int(m.group(3)) if m.group(3) else date.today().year
    try:
        iso = date(tahun, bulan, hari).isoformat()
    except ValueError:
        return None
    return (m.start(), m.end(), iso)


def _parse_periode(teks: str):
    """'11 oktober - 15 oktober 2026' -> (mulai_iso, selesai_iso, sisa_teks)
    -- None kalau tidak ditemukan DUA tanggal dipisah '-' (berarti bukan
    periode, caller fallback ke tanggal tunggal).

    BUGFIX: `sisa_teks` HARUS menggabungkan teks SEBELUM tanggal pertama
    ("Romen" di "Romen 11 oktober - 16 oktober 2026") DAN teks SETELAH
    tanggal kedua ("jaka" di "11 oktober - 16 oktober 2026 jaka") --
    sebelumnya cuma teks setelah yang diambil, jadi nama barber yang
    ditulis SEBELUM rentang tanggal hilang begitu saja dan _cmd_rekap()
    jatuh ke default "semua barber"."""
    tm1 = _cari_tanggal(teks)
    if tm1 is None:
        return None
    sebelum = teks[:tm1[0]]
    sisa = teks[tm1[1]:]
    m_strip = re.match(r"\s*-\s*", sisa)
    if not m_strip:
        return None
    sisa = sisa[m_strip.end():]
    tm2 = _cari_tanggal(sisa)
    if tm2 is None:
        return None
    setelah = sisa[tm2[1]:]
    sisa_setelah = (sebelum + " " + setelah).strip()
    return (tm1[2], tm2[2], sisa_setelah)


def _format_tanggal_id(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {_NAMA_BULAN_SINGKAT[m]} {y}"


def _parse_nominal(teks: str) -> int:
    """'30rb' -> 30000, '1jt' -> 1000000, '30.000'/'30000' -> 30000.
    Tidak ada parser nominal shorthand yang sudah ada di codebase ini,
    jadi ditulis baru di sini -- khusus kebutuhan Tips/nominal via WA."""
    t = teks.strip().lower().replace(" ", "")
    t = re.sub(r"^rp\.?", "", t)
    m = re.match(r"^(\d+(?:[.,]\d+)?)(rb|ribu|k|jt|juta)?$", t)
    if not m:
        digits = re.sub(r"[^\d]", "", t)
        return int(digits) if digits else 0
    angka = float(m.group(1).replace(",", "."))
    suf = m.group(2)
    if suf in ("rb", "ribu", "k"):
        angka *= 1000
    elif suf in ("jt", "juta"):
        angka *= 1_000_000
    return int(angka)


def _bulan_sekarang() -> tuple[int, int]:
    today = date.today()
    return today.year, today.month


def _akhir_bulan(tahun: int, bulan: int) -> str:
    if bulan == 12:
        return date(tahun, 12, 31).isoformat()
    return (date(tahun, bulan + 1, 1) - timedelta(days=1)).isoformat()


def _bulan_dari_teks(teks: str):
    """'Oktober' / 'Oktober 2026' / 'bulan ini' / 'bulan depan' -> (tahun, bulan),
    None kalau tidak dikenali (caller fallback ke bulan berjalan)."""
    t = teks.strip().lower()
    if not t:
        return None
    if t == "bulan ini":
        return _bulan_sekarang()
    if t == "bulan depan":
        tahun, bulan = _bulan_sekarang()
        bulan += 1
        if bulan > 12:
            bulan = 1
            tahun += 1
        return tahun, bulan
    m = re.search(r"(" + "|".join(_BULAN_ID.keys()) + r")(?:\s+(\d{4}))?", t)
    if m:
        bulan = _BULAN_ID[m.group(1)]
        tahun = int(m.group(2)) if m.group(2) else date.today().year
        return tahun, bulan
    return None


# ---------------------------------------------------------------------------
# Pencocokan nama (service/produk/barber) -- lihat docstring modul
# ---------------------------------------------------------------------------

def _akronim(nama: str) -> str:
    kata = [w for w in re.split(r"[\s\+]+", nama) if w]
    return "".join(w[0].upper() for w in kata)


def _cocokkan(teks: str, kandidat: list, field: str = "nama") -> list:
    """Rantai exact -> awalan (min 3 huruf) -> akronim, dipakai Service &
    Produk (lihat docstring modul)."""
    t = teks.strip().lower()
    if not t:
        return []
    exact = [k for k in kandidat if k[field].strip().lower() == t]
    if exact:
        return exact
    if len(t) >= 3:
        prefix = [k for k in kandidat if k[field].strip().lower().startswith(t)]
        if prefix:
            return prefix
    return [k for k in kandidat if _akronim(k[field]) == t.upper()]


def _cocokkan_barber(teks: str, barbers: list) -> list:
    """Nama barber: exact -> awalan SAJA (TANPA akronim -- nama barber
    biasanya satu/dua kata pendek, akronim 1-2 huruf terlalu berisiko
    nabrak nama lain, beda dari service/produk yang namanya lebih panjang)."""
    t = teks.strip().lower()
    if not t:
        return []
    exact = [b for b in barbers if b["nama"].strip().lower() == t]
    if exact:
        return exact
    if len(t) >= 3:
        return [b for b in barbers if b["nama"].strip().lower().startswith(t)]
    return []


def _teks_ambigu_list(ketik: str, opsi: list, field: str = "nama") -> str:
    daftar = "\n".join(f"{i + 1}. {o[field]}" for i, o in enumerate(opsi))
    return f'"{ketik}" bisa jadi beberapa pilihan:\n{daftar}\n\nKetik ulang nama/kode yang lebih spesifik.'


def _hasil_barber_gagal(ketik: str, cocok: list) -> str:
    if not cocok:
        return f'Barber "{ketik}" tidak ditemukan.'
    return _teks_ambigu_list(ketik, cocok, "nama")


def _cocokkan_satu_service(kode: str, services: list):
    """Dipakai Input Data & Input Harian -- return (service_dict, None)
    kalau cocok PAS SATU, atau (None, pesan_error) kalau 0/2+ kandidat."""
    cocok = _cocokkan(kode, services, "nama")
    if len(cocok) == 0:
        return None, f'Service "{kode}" tidak dikenali. Cek penulisan atau ketik "Menu".'
    if len(cocok) > 1:
        return None, _teks_ambigu_list(kode, cocok, "nama")
    return cocok[0], None


def _cocokkan_satu_produk(kode: str, produk_list: list, produk_terurut: list):
    """Dipakai Input Produk/Restock/Tester/Input Harian -- SAMA PERSIS logika
    yang sebelumnya ada inline di _cmd_input_produk()/_parse_baris_produk_mutasi()
    (nomor urut Daftar Produk ATAU nama/akronim), diekstrak supaya bisa
    dipakai ULANG baris-per-baris oleh parser Input Harian (lihat
    _lanjutkan_parsing_input_harian()). Return (produk_dict, None) kalau
    cocok PAS SATU, atau (None, pesan_error)."""
    if kode.isdigit():
        idx = int(kode)
        if idx < 1 or idx > len(produk_terurut):
            return None, f'Nomor produk {idx} tidak ada di daftar. Kirim "Daftar Produk" untuk lihat nomornya.'
        return produk_terurut[idx - 1], None
    cocok = _cocokkan(kode, produk_list, "nama")
    if len(cocok) == 0:
        return None, f'Produk "{kode}" tidak dikenali.'
    if len(cocok) > 1:
        return None, _teks_ambigu_list(kode, cocok, "nama")
    return cocok[0], None


def _resolve_koreksi_kode_jumlah(balasan: str, jumlah_lama: int | None, pola: str):
    """Dipakai koreksi service_line/produk_line Input Harian -- balasan user
    ATAS pertanyaan koreksi bisa berupa baris LENGKAP ('<kode> <jumlah>',
    mis. kalau user keliru ketik ulang semuanya) ATAU cuma kode/nama
    penggantinya saja (umumnya, karena jumlahnya sendiri sudah benar dari
    baris asli) -- coba parse sebagai baris lengkap dulu, fallback pakai
    `jumlah_lama` (dari baris asli yang salah) kalau balasan cuma kode/nama
    tanpa angka. Return (kode, jumlah) atau (None, None) kalau jumlah_lama
    juga None (baris asli dulu TIDAK match pola sama sekali, jadi balasan
    WAJIB berupa baris lengkap)."""
    parsed = _parse_baris_kode_jumlah(balasan, pola)
    if parsed is not None:
        return parsed
    if jumlah_lama is not None:
        return balasan.strip(), jumlah_lama
    return None, None


def _parse_baris_kode_jumlah(baris: str, pola: str):
    m = re.match(pola, baris.strip())
    if not m:
        return None
    kode = m.group(1).strip()
    try:
        jumlah = int(m.group(2))
    except ValueError:
        return None
    if jumlah <= 0:
        return None
    return kode, jumlah


# ---------------------------------------------------------------------------
# Resolusi akses (Owner / Barber / tidak dikenal) -- lihat docstring modul
# ---------------------------------------------------------------------------

def _normalisasi_nomor(n: str) -> str:
    digit = re.sub(r"\D", "", n or "")
    if digit.startswith("0"):
        digit = "62" + digit[1:]
    return digit


def resolve_role(tenant_id: int, config: dict, wa_id_pengirim: str):
    """Return ('owner', None) | ('barber', barber_dict) | (None, None).
    Nomor dibandingkan SETELAH dinormalisasi (lihat _normalisasi_nomor,
    supaya 0812.../+62812.../62812... semua dianggap nomor yang sama).
    PERMINTAAN OWNER: maksimal 2 nomor setara akses Owner PENUH per tenant
    (nomor_owner_whatsapp + nomor_owner_whatsapp_2, keduanya opsional)."""
    nomor_pengirim = _normalisasi_nomor(wa_id_pengirim)
    nomor_owner_list = [config.get("nomor_owner_whatsapp"), config.get("nomor_owner_whatsapp_2")] if config else []
    for nomor_owner in nomor_owner_list:
        nomor_owner = (nomor_owner or "").strip()
        if nomor_owner and _normalisasi_nomor(nomor_owner) == nomor_pengirim:
            return "owner", None
    barbers = db.get_barbers(tenant_id=tenant_id, hanya_aktif=False)
    for b in barbers:
        if b.get("nomor_whatsapp") and _normalisasi_nomor(b["nomor_whatsapp"]) == nomor_pengirim:
            return "barber", b
    return None, None


# ---------------------------------------------------------------------------
# Status Libur/Cuti/Izin satu barber pada satu tanggal -- dipakai Rekap &
# Absensi (barber yang sedang Libur/Cuti/Izin TIDAK dianggap "tidak ada
# data"/"belum check-in", tapi ditampilkan status terjadwalnya).
# ---------------------------------------------------------------------------

def _status_libur_cuti_hari(barber_id: int, tanggal: str):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM absensi_libur WHERE barber_id = ? AND tanggal = ?", (barber_id, tanggal)
        ).fetchone()
    if row:
        return "LIBUR"
    aktif = izin_cuti_db.get_pengajuan_aktif_pada_tanggal(barber_id, tanggal)
    if aktif:
        return "CUTI" if aktif["jenis"] == "cuti" else "IZIN"
    return None


def _hitung_hari_libur_rentang(barber_id: int, tanggal_mulai: str, tanggal_selesai: str) -> int:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS jumlah FROM absensi_libur WHERE barber_id = ? AND tanggal >= ? AND tanggal <= ?",
            (barber_id, tanggal_mulai, tanggal_selesai),
        ).fetchone()
    return row["jumlah"]


# ---------------------------------------------------------------------------
# ENTRYPOINT -- dipanggil routers/whatsapp_bot.py SATU KALI per pesan masuk
# yang sudah lolos cek nomor device terdaftar + kuota belum habis.
# ---------------------------------------------------------------------------

def adalah_command_baca(isi_pesan: str) -> bool:
    """True kalau `isi_pesan` PASTI command baca-saja (Rekap/Absensi/Cuti/
    Booking/Kuota Libur/Keterlambatan/Menu/Daftar Produk/Rekap Produk) --
    dipanggil routers/whatsapp_bot.py SEBELUM memutuskan apakah proteksi
    anti-dobel (whatsapp_bot_db.pesan_duplikat()) perlu diterapkan.

    PERMINTAAN OWNER: proteksi anti-dobel (jendela 2 menit) awalnya
    berlaku utuh untuk SEMUA pesan -- efek sampingnya, Owner yang sengaja
    kirim ulang command BACA yang persis sama (mis. "Rekap 18 oktober"
    dua kali berturut-turut) jadi tidak dibalas apa pun di percobaan
    kedua, padahal command baca TIDAK PERNAH berisiko dobel data. Jadi
    dipersempit: HANYA command baca yang boleh lewati proteksi ini --
    cocok PERSIS pola yang sama dengan percabangan di proses_pesan() di
    bawah (bukan reimplementasi logika baru, murni klasifikasi teks).
    Default-nya SELALU False (tetap diproteksi) kalau ragu -- termasuk
    pesan kosong, "YA"/"BATAL", dan apa pun yang berpotensi Input
    Service/Tandai Libur/Input Produk (SEMUANYA command TULIS, salah
    klasifikasi di sini bisa bikin transaksi tercatat dobel)."""
    teks = (isi_pesan or "").strip()
    if not teks:
        return False
    if teks.upper() in ("YA", "BATAL"):
        return False
    teks_lower = teks.lower().strip()
    kata0 = teks_lower.split()[0] if teks_lower.split() else ""
    if teks_lower in ("menu", "help", "bantuan"):
        return True
    if teks_lower == "daftar produk":
        return True
    if teks_lower.startswith("rekap produk"):
        return True
    if kata0 == "produk":
        return False  # Input Produk -- TULIS
    if kata0 == "rekap":
        return True
    if kata0 == "absensi" or teks_lower.startswith("absen "):
        return True
    if kata0 in ("cuti", "izin"):
        return True
    if kata0 == "booking":
        return True
    if teks_lower == "kuota libur" or teks_lower.startswith("kuota libur "):
        return True
    if teks_lower == "keterlambatan" or teks_lower.startswith("keterlambatan "):
        return True
    return False  # sisanya berpotensi Input Service/Tandai Libur -- TULIS


def proses_pesan(tenant_id: int, config: dict, wa_id_pengirim: str, isi_pesan: str) -> str | None:
    """Return teks balasan, atau None kalau TIDAK BOLEH membalas apa pun
    (nomor pengirim tidak dikenali sama sekali -- bukan Owner, bukan
    barber manapun di tenant ini)."""
    role, barber_self = resolve_role(tenant_id, config, wa_id_pengirim)
    if role is None:
        return None

    teks = (isi_pesan or "").strip()
    if not teks:
        return _pesan_tidak_dikenali()

    atas = teks.upper()

    # PERMINTAAN OWNER (Input Harian): kalau ada draft Input Harian yang
    # masih menunggu koreksi SATU baris tertentu (lihat
    # _lanjutkan_parsing_input_harian()), balasan APA PUN dari pengirim
    # yang sama (selain BATAL) dianggap jawaban koreksi itu -- BUKAN
    # command baru. Dicek PALING AWAL (sebelum YA/BATAL generik di bawah)
    # supaya BATAL saat menunggu koreksi juga lewat jalur ini, bukan
    # _proses_konfirmasi() yang mengasumsikan pending sudah berupa preview
    # lengkap siap simpan.
    pending = whatsapp_bot_db.ambil_pending(tenant_id, wa_id_pengirim)
    if pending is not None and pending["jenis"] == "input_harian_draft":
        if atas == "BATAL":
            whatsapp_bot_db.hapus_pending(tenant_id, wa_id_pengirim)
            return "❌ Input Harian dibatalkan, tidak ada data tersimpan."
        return _terapkan_koreksi_input_harian(tenant_id, wa_id_pengirim, pending["payload"], teks)

    if atas in ("YA", "BATAL"):
        if pending is not None:
            return _proses_konfirmasi(tenant_id, wa_id_pengirim, pending, atas)
        return _pesan_tidak_dikenali()

    teks_lower = teks.lower().strip()
    kata = teks_lower.split()
    kata0 = kata[0] if kata else ""

    if teks_lower in ("menu", "help", "bantuan"):
        return _menu_teks(role)

    if teks_lower == "daftar produk":
        if role != "owner":
            return _pesan_tidak_dikenali()
        return _cmd_daftar_produk(tenant_id)

    if teks_lower.startswith("rekap produk"):
        if role != "owner":
            return "Maaf, command ini khusus Owner."
        return _cmd_rekap_produk(tenant_id, teks[len("rekap produk"):].strip())

    if kata0 == "produk":
        if role != "owner":
            return "Maaf, input produk cuma bisa dilakukan dari nomor Owner."
        return _cmd_input_produk(tenant_id, wa_id_pengirim, teks[len("produk"):].strip())

    if kata0 == "restock":
        if role != "owner":
            return "Maaf, restock produk cuma bisa dilakukan dari nomor Owner."
        return _cmd_restock_produk(tenant_id, wa_id_pengirim, teks[len("restock"):].strip())

    if kata0 == "tester":
        if role != "owner":
            return "Maaf, tester produk cuma bisa dilakukan dari nomor Owner."
        return _cmd_tester_produk(tenant_id, wa_id_pengirim, teks[len("tester"):].strip())

    if kata0 == "rekap":
        return _cmd_rekap(tenant_id, role, barber_self, teks[len("rekap"):].strip(),
                           config.get("tampilkan_potongan_keterlambatan", True))

    if kata0 == "absensi":
        return _cmd_absensi(tenant_id, role, barber_self, teks[len("absensi"):].strip())
    if teks_lower.startswith("absen "):
        return _cmd_absensi(tenant_id, role, barber_self, teks[len("absen"):].strip())

    if kata0 in ("cuti", "izin"):
        return _cmd_cuti(tenant_id, teks[len(kata0):].strip())

    if kata0 == "booking":
        return _cmd_booking(tenant_id, role, barber_self, teks[len("booking"):].strip())

    if teks_lower == "kuota libur" or teks_lower.startswith("kuota libur "):
        return _cmd_kuota_libur(tenant_id, role, barber_self, teks[len("kuota libur"):].strip())

    if teks_lower == "keterlambatan" or teks_lower.startswith("keterlambatan "):
        return _cmd_keterlambatan(tenant_id, role, barber_self, teks[len("keterlambatan"):].strip())

    if kata0 == "input" and len(kata) > 1 and kata[1] == "harian":
        if role != "owner":
            return "Maaf, Input Harian cuma bisa dilakukan dari nomor Owner."
        return _cmd_input_harian(tenant_id, wa_id_pengirim, teks[len("input harian"):].strip())

    # Sisanya (Input Service / Tandai Libur) -- EKSKLUSIF Owner, dikenali
    # dari baris pertama yang cocok ke nama barber tenant ini.
    if role == "owner":
        hasil = _coba_input_service_atau_libur(tenant_id, wa_id_pengirim, teks)
        if hasil is not None:
            return hasil

    return _pesan_tidak_dikenali()


def _pesan_tidak_dikenali() -> str:
    """REVISI (permintaan Owner): pesan yang TIDAK DIKENALI jangan langsung
    dibalas daftar Menu lengkap (dianggap mengagetkan/kepanjangan) -- cukup
    pesan singkat. REVISI LAGI (permintaan Owner): kata/saran "Menu" juga
    dihapus dari pesan singkat ini (sebelumnya "...Ketik Menu untuk lihat
    daftar perintah.") -- TAPI command "menu"/"help"/"bantuan" itu sendiri
    TETAP berfungsi kalau diketik manual (lihat _menu_teks()), cuma tidak
    lagi disarankan proaktif di sini."""
    return "Perintah tidak dikenali."


def _menu_teks(role: str) -> str:
    """REVISI (feedback Owner: menu versi sebelumnya pakai notasi
    placeholder ala command-line, "<nama barber> [tanggal]", susah dibaca)
    -- diganti CONTOH PESAN SUNGGUHAN yang tinggal ditiru, sama seperti
    contoh-contoh yang sudah disepakati waktu rancang fitur ini.

    REVISI (permintaan Owner): baris CONTOH dibuat miring (`_teks_`, satu-
    satunya opsi "penonjolan" yang didukung WhatsApp selain tebal --
    WhatsApp TIDAK mendukung warna font sama sekali) supaya kelihatan
    beda dari baris penjelasan di atasnya."""
    if role == "owner":
        return (
            "Input data service, contoh:\n"
            "_Romen 11 oktober 2026_\n"
            "_Dc 2_\n"
            "_Tips 30rb_\n\n"
            "Input harian (gabungan banyak barber + libur + produk sekaligus), contoh:\n"
            "_Input Harian 11 oktober 2026_\n"
            "_Romen_\n"
            "_Dc 2_\n"
            "_Tips 30rb_\n"
            "_Ozi_\n"
            "_Hw 1_\n"
            "_Tips 20rb_\n"
            "_Libur: Mifta_\n"
            "_Produk:_\n"
            "_Wax Pomade 1_\n\n"
            "Tandai libur, contoh:\n"
            "_Mifta libur_\n\n"
            "Input produk, contoh:\n"
            "_Produk 11 oktober 2026_\n"
            "_1 2_\n\n"
            "Restock produk, contoh:\n"
            "_Restock 11 oktober 2026_\n"
            "_1 10_\n\n"
            "Tester produk, contoh:\n"
            "_Tester 11 oktober 2026_\n"
            "_1 1_\n\n"
            "Lihat daftar produk (+ sisa stok): ketik *Daftar Produk*\n\n"
            "Lihat rekap, contoh:\n"
            "_Rekap 11 oktober 2026_\n"
            "_Rekap 11 oktober - 15 oktober 2026_\n"
            "_Rekap 11 oktober romen_\n\n"
            "Rekap penjualan produk, contoh:\n"
            "_Rekap Produk Oktober_\n\n"
            "Lihat absensi, contoh:\n"
            "_Absensi 11 oktober 2026_\n"
            "_Absen hari ini_\n\n"
            "Lihat cuti/izin, contoh:\n"
            "_Cuti Oktober_\n\n"
            "Lihat booking, contoh:\n"
            "_Booking hari ini_\n"
            "_Booking besok_\n"
            "_Booking 20 oktober_\n\n"
            "Sisa kuota libur: ketik *Kuota Libur* (atau *Kuota Libur Romen* untuk satu barber)\n\n"
            "Keterlambatan bulan ini: ketik *Keterlambatan* (atau *Keterlambatan Romen*)"
        )
    return (
        "Lihat rekap kamu, contoh:\n"
        "_Rekap 11 oktober 2026_\n"
        "_Rekap 11 oktober - 15 oktober 2026_\n\n"
        "Lihat absensi kamu, contoh:\n"
        "_Absensi 11 oktober 2026_\n"
        "_Absen hari ini_\n\n"
        "Lihat cuti/izin semua barber, contoh:\n"
        "_Cuti Oktober_\n\n"
        "Lihat booking kamu (hari ini & ke depan saja), contoh:\n"
        "_Booking hari ini_\n"
        "_Booking besok_\n\n"
        "Sisa kuota libur kamu: ketik *Kuota Libur*\n\n"
        "Keterlambatan kamu bulan ini: ketik *Keterlambatan*"
    )


# ---------------------------------------------------------------------------
# Konfirmasi (YA/BATAL) -- dispatch berdasar `jenis` pending yang tersimpan
# ---------------------------------------------------------------------------

def _proses_konfirmasi(tenant_id: int, wa_id_pengirim: str, pending: dict, jawaban: str) -> str:
    jenis = pending["jenis"]
    p = pending["payload"]

    if jawaban == "BATAL":
        whatsapp_bot_db.hapus_pending(tenant_id, wa_id_pengirim)
        return "❌ Input dibatalkan, tidak ada data tersimpan."

    whatsapp_bot_db.hapus_pending(tenant_id, wa_id_pengirim)

    if jenis == "input_service":
        db.tambah_transaksi(p["tanggal"], p["barber_id"], p["items"], tips=p["tips"], sumber=SUMBER_WA_BOT,
                             idempotency_key=p.get("idempotency_key"))
        return f"✅ Data {p['nama_barber']} ({_format_tanggal_id(p['tanggal'])}) berhasil disimpan."

    if jenis == "input_harian":
        return _simpan_input_harian(tenant_id, p)

    if jenis == "tandai_libur":
        try:
            jenis_hasil = kuota_libur_db.tandai_libur_dengan_kuota(p["barber_id"], tenant_id, p["tanggal"])
        except ValueError as e:
            return f"❌ {e}"
        label = {"libur": "LIBUR", "cuti": "CUTI (kuota libur bulan ini sudah habis)",
                 "kelebihan_kuota": "LIBUR (kuota Libur & Cuti sama-sama sudah habis)"}
        return (f"✅ {p['nama_barber']} ditandai {label.get(jenis_hasil, jenis_hasil)} "
                f"pada {_format_tanggal_id(p['tanggal'])}.")

    if jenis == "input_produk":
        gagal = []
        for it in p["items"]:
            try:
                db.jual_produk(it["produk_id"], p["tanggal"], it["jumlah"], sumber=SUMBER_WA_BOT)
            except ValueError as e:
                gagal.append(f"{it['nama']}: {e}")
        if gagal:
            return "⚠️ Sebagian produk GAGAL disimpan (stok tidak cukup):\n" + "\n".join(gagal)
        return f"✅ Penjualan produk ({_format_tanggal_id(p['tanggal'])}) berhasil disimpan."

    if jenis == "restock_produk":
        # restock_produk() SELALU aman (tidak mungkin saldo negatif, lihat
        # docstring database.py) -- tidak perlu try/except per item seperti
        # input_produk/tester_produk di atas/bawah.
        for it in p["items"]:
            db.restock_produk(it["produk_id"], p["tanggal"], it["jumlah"])
        return f"✅ Restock produk ({_format_tanggal_id(p['tanggal'])}) berhasil disimpan."

    if jenis == "tester_produk":
        gagal = []
        for it in p["items"]:
            try:
                db.tester_produk(it["produk_id"], p["tanggal"], it["jumlah"])
            except ValueError as e:
                gagal.append(f"{it['nama']}: {e}")
        if gagal:
            return "⚠️ Sebagian produk GAGAL disimpan (stok tidak cukup):\n" + "\n".join(gagal)
        return f"✅ Tester produk ({_format_tanggal_id(p['tanggal'])}) berhasil disimpan."

    return "❌ Konfirmasi tidak dikenali."


def _simpan_input_harian(tenant_id: int, p: dict) -> str:
    """YA pada "Konfirmasi Input Harian" -- simpan SEMUANYA: transaksi tiap
    barber, status Libur/Cuti tiap barber (lewat cascade kuota yang SAMA
    seperti command "<barber> libur" biasa, lihat kuota_libur_db.py --
    hasilnya BISA jadi Cuti/"kelebihan_kuota" kalau kuota Libur bulan itu
    sudah habis, PERMINTAAN OWNER supaya ini ditunjukkan apa adanya di sini,
    bukan diasumsikan selalu Libur murni), dan penjualan produk. SEBAGIAN
    gagal (stok produk tidak cukup / tanggal sudah tercakup Cuti/Izin lain)
    TIDAK menggagalkan bagian lain -- tiap bagian independen, dilaporkan
    per baris di hasil akhir (sama pola seperti input_produk/tester_produk
    di atas, bukan transaksi database tunggal)."""
    hasil = []

    for b in p["barbers"]:
        try:
            db.tambah_transaksi(p["tanggal"], b["barber_id"], b["items"], tips=b["tips"], sumber=SUMBER_WA_BOT,
                                 idempotency_key=b.get("idempotency_key"))
            hasil.append(f"✅ Data {b['nama_barber']} tersimpan.")
        except ValueError as e:
            hasil.append(f"❌ Data {b['nama_barber']} GAGAL: {e}")

    label_libur = {"libur": "LIBUR", "cuti": "CUTI (kuota libur bulan ini sudah habis)",
                   "kelebihan_kuota": "LIBUR (kuota Libur & Cuti sama-sama sudah habis)"}
    for l in p["libur"]:
        try:
            jenis_hasil = kuota_libur_db.tandai_libur_dengan_kuota(l["barber_id"], tenant_id, p["tanggal"])
            hasil.append(f"✅ {l['nama_barber']} ditandai {label_libur.get(jenis_hasil, jenis_hasil)}.")
        except ValueError as e:
            hasil.append(f"❌ {l['nama_barber']}: {e}")

    if p["produk"]:
        gagal_produk = []
        for it in p["produk"]:
            try:
                db.jual_produk(it["produk_id"], p["tanggal"], it["jumlah"], sumber=SUMBER_WA_BOT)
            except ValueError as e:
                gagal_produk.append(f"{it['nama']}: {e}")
        if gagal_produk:
            hasil.append("⚠️ Sebagian produk GAGAL disimpan (stok tidak cukup):\n" + "\n".join(gagal_produk))
        else:
            hasil.append("✅ Penjualan produk tersimpan.")

    return f"*Input Harian {_format_tanggal_id(p['tanggal'])} diproses:*\n\n" + "\n".join(hasil)


# ---------------------------------------------------------------------------
# INPUT SERVICE & TANDAI LIBUR (Owner only) -- dikenali dari baris pertama
# ---------------------------------------------------------------------------

def _coba_input_service_atau_libur(tenant_id: int, wa_id_pengirim: str, teks: str):
    """Return teks balasan kalau baris pertama cocok ke nama barber tenant
    ini (lanjut diproses sebagai Input Service atau Tandai Libur), atau
    None kalau baris pertama BUKAN nama barber dikenal sama sekali
    (berarti bukan command ini -- caller fallback ke Menu)."""
    baris = [l.strip() for l in teks.split("\n") if l.strip()]
    if not baris:
        return None
    baris0 = baris[0]
    tanggal_match = _cari_tanggal(baris0)
    if tanggal_match:
        sisa_baris0 = (baris0[:tanggal_match[0]] + baris0[tanggal_match[1]:]).strip()
        tanggal = tanggal_match[2]
    else:
        sisa_baris0 = baris0
        tanggal = date.today().isoformat()

    barbers = db.get_barbers(tenant_id=tenant_id)
    kata_sisa = sisa_baris0.split()

    # "<nama> libur [tanggal]" -- SATU baris (tidak ada baris service lain).
    if kata_sisa and kata_sisa[-1].lower() == "libur":
        nama_calon = " ".join(kata_sisa[:-1]).strip()
        cocok = _cocokkan_barber(nama_calon, barbers)
        if len(cocok) == 1:
            barber = cocok[0]
            payload = {"barber_id": barber["id"], "nama_barber": barber["nama"], "tanggal": tanggal}
            whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "tandai_libur", payload)
            return (f"*Konfirmasi Tandai Libur*\n\n{barber['nama']} - {_format_tanggal_id(tanggal)}\n\n"
                    "Balas *YA* untuk simpan, atau *BATAL* untuk batalkan.")
        if len(cocok) > 1:
            return _hasil_barber_gagal(nama_calon, cocok)
        return None  # bukan nama barber dikenal -> bukan command ini

    # Input Service -- baris0 (minus tanggal) HARUS persis nama satu barber.
    cocok = _cocokkan_barber(sisa_baris0, barbers)
    if len(cocok) != 1 or len(baris) < 2:
        return None
    return _parse_dan_preview_input_service(tenant_id, wa_id_pengirim, cocok[0], tanggal, baris[1:])


def _parse_dan_preview_input_service(tenant_id: int, wa_id_pengirim: str, barber: dict, tanggal: str,
                                      baris_list: list):
    services = db.get_services(tenant_id=tenant_id)
    items_preview, items_simpan = [], []
    tips = 0

    for baris in baris_list:
        if baris.lower().startswith("tips"):
            tips = _parse_nominal(baris[len("tips"):].strip())
            continue
        parsed = _parse_baris_kode_jumlah(baris, POLA_SERVICE)
        if parsed is None:
            return f'Baris tidak dikenali: "{baris}". Format: <kode service><jumlah>, mis. "Dc 2".'
        kode, jumlah = parsed
        cocok = _cocokkan(kode, services, "nama")
        if len(cocok) == 0:
            return f'Service "{kode}" tidak dikenali. Cek penulisan atau ketik "Menu".'
        if len(cocok) > 1:
            return _teks_ambigu_list(kode, cocok, "nama")
        s = cocok[0]
        komisi = db.hitung_komisi_service(s["harga"], s.get("modal", 0), tenant_id=tenant_id) * jumlah
        items_preview.append((s["nama"], jumlah, komisi))
        items_simpan.append({"service_id": s["id"], "jumlah": jumlah})

    if not items_simpan:
        return "Tidak ada service yang diisi -- minimal 1 baris service."

    total_komisi = sum(k for _, _, k in items_preview)
    lines = ["*Konfirmasi Input Data*", "", f"{barber['nama']} - {_format_tanggal_id(tanggal)}", ""]
    for nama, jumlah, komisi in items_preview:
        lines.append(f"{nama} x{jumlah} = Komisi {_rupiah(komisi)}")
    lines.append(f"Tips: {_rupiah(tips)}")
    lines.append("")
    lines.append(f"*Total: {_rupiah(total_komisi + tips)}*")
    lines.append("")
    lines.append("Balas *YA* untuk simpan, atau *BATAL* untuk batalkan.")

    # PERBAIKAN Owner (audit "tidak boleh input dobel"): idempotency_key
    # dibuat SEKALI di sini (bertahan sama lewat pending tersimpan, TIDAK
    # dibuat ulang tiap percobaan konfirmasi) -- lihat pemakaiannya di
    # _proses_konfirmasi() jenis "input_service" + database.py::
    # tambah_transaksi(). Menutup celah webhook Fonnte yang terkirim ULANG
    # tepat di luar jendela _JENDELA_DUPLIKAT_DETIK (whatsapp_bot_db.
    # pesan_duplikat()), atau dua request "YA" yang diproses BERSAMAAN
    # (race condition -- pesan_duplikat() sendiri rentan TOCTOU karena
    # baris log-nya baru tercatat SETELAH proses_pesan() selesai, lihat
    # routers/whatsapp_bot.py).
    payload = {"barber_id": barber["id"], "nama_barber": barber["nama"], "tanggal": tanggal,
               "items": items_simpan, "tips": tips, "idempotency_key": uuid.uuid4().hex}
    whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_service", payload)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# INPUT HARIAN (Owner only) -- gabungan SATU pesan utk seluruh hari: banyak
# barber (servis masing-masing + tips), siapa Libur, dan produk terjual.
# Permintaan Owner (pengganti form kertas "List Customer Harian"):
#
#   Input Harian 20 oktober 2026
#
#   Romen
#   Dc 3
#   Tips 60000
#
#   Ozi
#   Dc 2
#   Hw 2
#   Tips 55000
#
#   Libur: Mifta
#
#   Produk:
#   Wax Pomade 2
#
# KOREKSI INTERAKTIF (beda dari semua command lain di modul ini, yang
# gagal TOTAL kalau ada satu baris salah -- lihat docstring modul):
# begitu parsing mentok di SATU baris yang tidak dikenali/ambigu (nama
# barber/kode servis/nama produk), draft yang SUDAH berhasil diuraikan
# sejauh itu disimpan sebagai pending jenis "input_harian_draft"
# (whatsapp_bot_db.simpan_pending(), payload = state parser lengkap --
# lihat _lanjutkan_parsing_input_harian()), lalu bot tanya SPESIFIK baris
# mana yang bermasalah dan minta balasan SINGKAT penggantinya (bukan minta
# kirim ulang semuanya dari awal). proses_pesan() mengenali pending jenis
# ini PALING AWAL (sebelum YA/BATAL generik) dan mengarahkan balasan
# berikutnya ke _terapkan_koreksi_input_harian(), yang menempelkan
# koreksi itu ke draft lalu memanggil ULANG _lanjutkan_parsing_input_harian()
# utk melanjutkan sisa baris -- bisa berulang kalau ada beberapa baris
# bermasalah. Begitu SEMUA baris beres, baru ditampilkan SATU ringkasan
# lengkap (semua barber + servis + tips, siapa Libur, produk apa saja,
# total keseluruhan) dengan YA/BATAL seperti command lain -- disimpan
# sebagai pending jenis "input_harian" (lihat _proses_konfirmasi()).
# ---------------------------------------------------------------------------

def _cmd_input_harian(tenant_id: int, wa_id_pengirim: str, sisa_setelah_kata: str) -> str:
    baris = [l.strip() for l in sisa_setelah_kata.split("\n") if l.strip()]
    tanggal = date.today().isoformat()
    if baris:
        tm = _cari_tanggal(baris[0])
        if tm:
            tanggal = tm[2]
            sisa0 = (baris[0][:tm[0]] + baris[0][tm[1]:]).strip()
            if sisa0:
                baris[0] = sisa0
            else:
                baris = baris[1:]

    if not baris:
        return ('Format: "Input Harian [tanggal]" lalu per barber (nama lalu baris servis, '
                '"Tips <nominal>"), "Libur: <nama>, <nama>", dan "Produk:" + baris '
                '"<nama/nomor produk> <jumlah>". Ketik "Menu" untuk contoh lengkap.')

    draft = {
        "tanggal": tanggal,
        "baris": baris,
        "idx": 0,
        "section": None,  # None | "barber" | "produk"
        "barber_aktif": None,
        "barbers": [],
        "libur": [],
        "produk": [],
        "koreksi": None,
        "libur_tokens": None,
        "libur_idx": None,
    }
    return _lanjutkan_parsing_input_harian(tenant_id, wa_id_pengirim, draft)


def _lanjutkan_parsing_input_harian(tenant_id: int, wa_id_pengirim: str, draft: dict) -> str:
    """Lanjutkan parsing draft Input Harian dari posisi yang tersimpan di
    `draft` (idx/libur_idx) sampai SELESAI (tampilkan ringkasan final +
    YA/BATAL) atau MENTOK di satu baris yang perlu dikoreksi (simpan draft
    sbg pending "input_harian_draft" + kembalikan pertanyaan spesifik).
    Dipanggil dari _cmd_input_harian() (parsing awal) MAUPUN
    _terapkan_koreksi_input_harian() (lanjutan setelah satu koreksi
    diterapkan) -- murni fungsi lanjutan, tidak peduli dari mana asalnya."""
    barbers_tenant = db.get_barbers(tenant_id=tenant_id)
    services = db.get_services(tenant_id=tenant_id)
    produk_list = db.get_produk_list(tenant_id=tenant_id)
    produk_terurut = sorted(produk_list, key=lambda p: p["id"])

    # Tuntaskan dulu token Libur yang masih tersisa (kalau sedang di
    # tengah SATU baris "Libur: a, b, c" -- tiap nama divalidasi satu per
    # satu, bisa mentok di tengah tanpa mengulang nama yang sudah benar).
    if draft["libur_tokens"] is not None:
        while draft["libur_idx"] < len(draft["libur_tokens"]):
            nama = draft["libur_tokens"][draft["libur_idx"]].strip()
            cocok = _cocokkan_barber(nama, barbers_tenant)
            if len(cocok) != 1:
                draft["koreksi"] = {"tipe": "libur_nama"}
                whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
                pesan_gagal = _hasil_barber_gagal(nama, cocok)
                return f'Baris Libur -- {pesan_gagal}\n\nBalas nama penggantinya, atau *BATAL* untuk batalkan semua.'
            b = cocok[0]
            draft["libur"].append({"barber_id": b["id"], "nama_barber": b["nama"]})
            draft["libur_idx"] += 1
        draft["libur_tokens"] = None
        draft["libur_idx"] = None

    while draft["idx"] < len(draft["baris"]):
        baris = draft["baris"][draft["idx"]]
        baris_lower = baris.lower().strip()

        # --- Penanda bagian "Libur" ---
        if baris_lower == "libur" or baris_lower.startswith("libur:") or baris_lower.startswith("libur "):
            sisa = baris[len("libur"):].lstrip(": ").strip()
            draft["idx"] += 1
            # BUGFIX: tutup blok barber yg sedang berjalan (kalau ada) dengan
            # MENYIMPANNYA dulu ke draft["barbers"] -- sebelumnya langsung
            # di-None-kan di sini, diam-diam MEMBUANG servis+tips barber yang
            # baru selesai diketik kalau baris berikutnya langsung "Libur"/
            # "Produk" (bukan barber lain).
            if draft["barber_aktif"] is not None:
                draft["barbers"].append(draft["barber_aktif"])
                draft["barber_aktif"] = None
            draft["section"] = None
            tokens = [t.strip() for t in sisa.split(",") if t.strip()]
            if not tokens:
                continue  # baris "Libur" kosong -- lewati
            draft["libur_tokens"] = tokens
            draft["libur_idx"] = 0
            return _lanjutkan_parsing_input_harian(tenant_id, wa_id_pengirim, draft)

        # --- Penanda bagian "Produk" ---
        if baris_lower == "produk" or baris_lower.startswith("produk:"):
            draft["idx"] += 1
            if draft["barber_aktif"] is not None:  # lihat BUGFIX catatan di penanda "Libur" di atas
                draft["barbers"].append(draft["barber_aktif"])
                draft["barber_aktif"] = None
            draft["section"] = "produk"
            continue

        # --- Baris di dalam bagian Produk ---
        if draft["section"] == "produk":
            parsed = _parse_baris_kode_jumlah(baris, POLA_PRODUK)
            if parsed is None:
                draft["koreksi"] = {"tipe": "produk_line", "jumlah": None}
                whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
                return (f'Baris produk "{baris}" formatnya tidak saya kenali '
                        '(harus "<nama/nomor produk> <jumlah>").\n\n'
                        'Balas baris yang benar, atau *BATAL* untuk batalkan semua.')
            kode, jumlah = parsed
            produk, error = _cocokkan_satu_produk(kode, produk_list, produk_terurut)
            if error:
                draft["koreksi"] = {"tipe": "produk_line", "jumlah": jumlah}
                whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
                return f'Baris produk -- {error}\n\nBalas nama/nomor produk yang benar, atau *BATAL* untuk batalkan semua.'
            draft["produk"].append({"produk_id": produk["id"], "nama": produk["nama"], "jumlah": jumlah,
                                     "harga_jual": produk["harga_jual"]})
            draft["idx"] += 1
            continue

        # --- Baris "Tips <nominal>" di dalam blok barber ---
        if draft["section"] == "barber" and baris_lower.startswith("tips"):
            draft["barber_aktif"]["tips"] = _parse_nominal(baris[len("tips"):].strip())
            draft["idx"] += 1
            continue

        # --- Baris servis di dalam blok barber ---
        if draft["section"] == "barber":
            parsed = _parse_baris_kode_jumlah(baris, POLA_SERVICE)
            if parsed is not None:
                kode, jumlah = parsed
                service, error = _cocokkan_satu_service(kode, services)
                if error is None:
                    draft["barber_aktif"]["items"].append(
                        {"service_id": service["id"], "nama": service["nama"], "jumlah": jumlah,
                         "harga": service["harga"], "modal": service.get("modal", 0)})
                    draft["idx"] += 1
                    continue
                draft["koreksi"] = {"tipe": "service_line", "jumlah": jumlah,
                                     "barber_nama": draft["barber_aktif"]["nama_barber"]}
                whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
                return (f'Baris "{baris}" di bagian {draft["barber_aktif"]["nama_barber"]} -- {error}\n\n'
                        'Balas kode servis yang benar, atau *BATAL* untuk batalkan semua.')
            # baris TIDAK cocok pola servis sama sekali -- mungkin maksudnya
            # baris barber BARU (menutup blok ini) -- JANGAN maju idx dulu,
            # jatuhkan ke pengecekan nama barber di bawah.

        # --- Baris nama barber baru (menutup blok sebelumnya kalau ada) ---
        cocok = _cocokkan_barber(baris, barbers_tenant)
        if len(cocok) == 1:
            if draft["barber_aktif"] is not None:
                draft["barbers"].append(draft["barber_aktif"])
            b = cocok[0]
            draft["barber_aktif"] = {"barber_id": b["id"], "nama_barber": b["nama"], "items": [], "tips": 0}
            draft["section"] = "barber"
            draft["idx"] += 1
            continue

        draft["koreksi"] = {"tipe": "barber_block"}
        whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
        if cocok:
            pesan_gagal = _hasil_barber_gagal(baris, cocok)
        elif draft["section"] == "barber":
            pesan_gagal = (f'Baris "{baris}" tidak saya kenali (bukan format servis yang valid, '
                            'bukan juga nama barber lain, "Libur", atau "Produk").')
        else:
            pesan_gagal = f'Baris "{baris}" tidak saya kenali sebagai nama barber, "Libur", atau "Produk".'
        return f'{pesan_gagal}\n\nBalas nama barber yang benar untuk baris ini, atau *BATAL* untuk batalkan semua.'

    # --- Semua baris selesai -- tutup blok barber terakhir kalau masih terbuka ---
    if draft["barber_aktif"] is not None:
        draft["barbers"].append(draft["barber_aktif"])
        draft["barber_aktif"] = None

    if not draft["barbers"] and not draft["libur"] and not draft["produk"]:
        return "Tidak ada data yang diisi -- minimal satu barber/Libur/Produk."

    return _tampilkan_ringkasan_input_harian(tenant_id, wa_id_pengirim, draft)


def _terapkan_koreksi_input_harian(tenant_id: int, wa_id_pengirim: str, draft: dict, balasan: str) -> str:
    """Menerima balasan SINGKAT user atas pertanyaan koreksi yang tersimpan
    di draft['koreksi'], menerapkannya ke draft, lalu memanggil ULANG
    _lanjutkan_parsing_input_harian() utk melanjutkan sisa baris dari titik
    yang sama (idx TIDAK dimundurkan -- baris yang salah itu dianggap
    "terselesaikan" oleh balasan ini, bukan diulang)."""
    koreksi = draft["koreksi"]
    tipe = koreksi["tipe"]
    draft["koreksi"] = None
    balasan = balasan.strip()

    if tipe == "barber_block":
        barbers_tenant = db.get_barbers(tenant_id=tenant_id)
        cocok = _cocokkan_barber(balasan, barbers_tenant)
        if len(cocok) != 1:
            draft["koreksi"] = {"tipe": "barber_block"}
            whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
            pesan_gagal = _hasil_barber_gagal(balasan, cocok)
            return f'{pesan_gagal}\n\nBalas nama barber yang benar, atau *BATAL* untuk batalkan semua.'
        if draft["barber_aktif"] is not None:
            draft["barbers"].append(draft["barber_aktif"])
        b = cocok[0]
        draft["barber_aktif"] = {"barber_id": b["id"], "nama_barber": b["nama"], "items": [], "tips": 0}
        draft["section"] = "barber"
        draft["idx"] += 1
        return _lanjutkan_parsing_input_harian(tenant_id, wa_id_pengirim, draft)

    if tipe == "service_line":
        kode, jumlah = _resolve_koreksi_kode_jumlah(balasan, koreksi["jumlah"], POLA_SERVICE)
        if kode is None:
            draft["koreksi"] = koreksi
            whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
            return ('Format harus "<kode servis> <jumlah>", mis. "Dc 2".\n\n'
                     'Balas baris yang benar, atau *BATAL* untuk batalkan semua.')
        services = db.get_services(tenant_id=tenant_id)
        service, error = _cocokkan_satu_service(kode, services)
        if error:
            draft["koreksi"] = {"tipe": "service_line", "jumlah": jumlah, "barber_nama": koreksi["barber_nama"]}
            whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
            return f'{error}\n\nBalas kode servis yang benar, atau *BATAL* untuk batalkan semua.'
        draft["barber_aktif"]["items"].append(
            {"service_id": service["id"], "nama": service["nama"], "jumlah": jumlah,
             "harga": service["harga"], "modal": service.get("modal", 0)})
        draft["idx"] += 1
        return _lanjutkan_parsing_input_harian(tenant_id, wa_id_pengirim, draft)

    if tipe == "produk_line":
        kode, jumlah = _resolve_koreksi_kode_jumlah(balasan, koreksi["jumlah"], POLA_PRODUK)
        if kode is None:
            draft["koreksi"] = koreksi
            whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
            return ('Format harus "<nama/nomor produk> <jumlah>".\n\n'
                     'Balas baris yang benar, atau *BATAL* untuk batalkan semua.')
        produk_list = db.get_produk_list(tenant_id=tenant_id)
        produk_terurut = sorted(produk_list, key=lambda p: p["id"])
        produk, error = _cocokkan_satu_produk(kode, produk_list, produk_terurut)
        if error:
            draft["koreksi"] = {"tipe": "produk_line", "jumlah": jumlah}
            whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
            return f'{error}\n\nBalas nama/nomor produk yang benar, atau *BATAL* untuk batalkan semua.'
        draft["produk"].append({"produk_id": produk["id"], "nama": produk["nama"], "jumlah": jumlah,
                                 "harga_jual": produk["harga_jual"]})
        draft["idx"] += 1
        return _lanjutkan_parsing_input_harian(tenant_id, wa_id_pengirim, draft)

    if tipe == "libur_nama":
        barbers_tenant = db.get_barbers(tenant_id=tenant_id)
        cocok = _cocokkan_barber(balasan, barbers_tenant)
        if len(cocok) != 1:
            draft["koreksi"] = {"tipe": "libur_nama"}
            whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian_draft", draft)
            pesan_gagal = _hasil_barber_gagal(balasan, cocok)
            return f'{pesan_gagal}\n\nBalas nama penggantinya, atau *BATAL* untuk batalkan semua.'
        b = cocok[0]
        draft["libur"].append({"barber_id": b["id"], "nama_barber": b["nama"]})
        draft["libur_idx"] += 1
        return _lanjutkan_parsing_input_harian(tenant_id, wa_id_pengirim, draft)

    return "❌ Koreksi tidak dikenali."


def _tampilkan_ringkasan_input_harian(tenant_id: int, wa_id_pengirim: str, draft: dict) -> str:
    """Draft SUDAH lengkap tanpa baris bermasalah -- bangun SATU ringkasan
    lengkap (semua barber + servis + tips, siapa Libur, produk apa saja,
    total keseluruhan), simpan sbg pending jenis "input_harian" (lihat
    _proses_konfirmasi()), minta YA/BATAL seperti command lain."""
    lines = ["*Konfirmasi Input Harian*", _format_tanggal_id(draft["tanggal"]), ""]
    total_keseluruhan = 0

    for b in draft["barbers"]:
        lines.append(f"*{b['nama_barber']}*")
        komisi_barber = 0
        for it in b["items"]:
            komisi = db.hitung_komisi_service(it["harga"], it.get("modal", 0), tenant_id=tenant_id) * it["jumlah"]
            komisi_barber += komisi
            lines.append(f"{it['nama']} x{it['jumlah']} = Komisi {_rupiah(komisi)}")
        lines.append(f"Tips: {_rupiah(b['tips'])}")
        subtotal = komisi_barber + b["tips"]
        lines.append(f"Subtotal: {_rupiah(subtotal)}")
        lines.append("")
        total_keseluruhan += subtotal

    if draft["libur"]:
        lines.append("*Libur*")
        for l in draft["libur"]:
            lines.append(f"- {l['nama_barber']}")
        lines.append("")

    if draft["produk"]:
        lines.append("*Produk Terjual*")
        total_produk = 0
        for p in draft["produk"]:
            subtotal = p["harga_jual"] * p["jumlah"]
            total_produk += subtotal
            lines.append(f"{p['nama']} x{p['jumlah']} = {_rupiah(subtotal)}")
        lines.append(f"Total Produk: {_rupiah(total_produk)}")
        lines.append("")
        total_keseluruhan += total_produk

    lines.append(f"*Total Keseluruhan: {_rupiah(total_keseluruhan)}*")
    lines.append("")
    lines.append("Balas *YA* untuk simpan semua, atau *BATAL* untuk batalkan.")

    # PERBAIKAN Owner (audit "tidak boleh input dobel"): idempotency_key
    # PER BARBER dibuat SEKALI di sini (sama alasannya seperti catatan di
    # _parse_dan_preview_input_service() -- lihat pemakaiannya di
    # _simpan_input_harian()).
    payload = {
        "tanggal": draft["tanggal"],
        "barbers": [{"barber_id": b["barber_id"], "nama_barber": b["nama_barber"],
                     "items": [{"service_id": it["service_id"], "jumlah": it["jumlah"]} for it in b["items"]],
                     "tips": b["tips"], "idempotency_key": uuid.uuid4().hex} for b in draft["barbers"]],
        "libur": draft["libur"],
        "produk": [{"produk_id": p["produk_id"], "nama": p["nama"], "jumlah": p["jumlah"]} for p in draft["produk"]],
    }
    whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_harian", payload)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# INPUT PRODUK & DAFTAR PRODUK (Owner only, TIDAK terikat barber)
# ---------------------------------------------------------------------------

def _cmd_daftar_produk(tenant_id: int) -> str:
    produk_list = sorted(db.get_produk_list(tenant_id=tenant_id), key=lambda p: p["id"])
    lines = ["*Daftar Produk*", ""]
    if not produk_list:
        lines.append("Belum ada produk aktif.")
        return "\n".join(lines)
    # PERMINTAAN OWNER: tampilkan sisa stok -- get_produk_list() SUDAH
    # menyertakan field "stok" (hitung ulang live dari produk_mutasi, lihat
    # database.py::get_stok_produk()), jadi tinggal dipakai, tidak perlu
    # query tambahan sama sekali.
    for i, p in enumerate(produk_list, start=1):
        lines.append(f"{i}. {p['nama']} - {_rupiah(p['harga_jual'])} (Sisa: {p['stok']})")
    return "\n".join(lines)


def _cmd_input_produk(tenant_id: int, wa_id_pengirim: str, sisa_setelah_kata: str) -> str:
    """`sisa_setelah_kata` = teks SETELAH kata "Produk" pada baris pertama,
    bisa berisi tanggal (opsional) lalu baris-baris berikutnya."""
    baris = [l.strip() for l in sisa_setelah_kata.split("\n") if l.strip()]
    tanggal = date.today().isoformat()
    if baris:
        tm = _cari_tanggal(baris[0])
        if tm:
            tanggal = tm[2]
            sisa0 = (baris[0][:tm[0]] + baris[0][tm[1]:]).strip()
            if sisa0:
                baris[0] = sisa0
            else:
                baris = baris[1:]

    if not baris:
        return 'Format: "Produk [tanggal]" lalu baris kode/nomor+jumlah, mis. "Captain Clay 30 1".'

    produk_list = db.get_produk_list(tenant_id=tenant_id)
    produk_terurut = sorted(produk_list, key=lambda p: p["id"])

    items_preview, items_simpan = [], []
    for baris_item in baris:
        parsed = _parse_baris_kode_jumlah(baris_item, POLA_PRODUK)
        if parsed is None:
            return f'Baris tidak dikenali: "{baris_item}".'
        kode, jumlah = parsed
        if kode.isdigit():
            idx = int(kode)
            if idx < 1 or idx > len(produk_terurut):
                return f'Nomor produk {idx} tidak ada di daftar. Kirim "Daftar Produk" untuk lihat nomornya.'
            p = produk_terurut[idx - 1]
        else:
            cocok = _cocokkan(kode, produk_list, "nama")
            if len(cocok) == 0:
                return f'Produk "{kode}" tidak dikenali.'
            if len(cocok) > 1:
                return _teks_ambigu_list(kode, cocok, "nama")
            p = cocok[0]
        subtotal = p["harga_jual"] * jumlah
        items_preview.append((p["nama"], jumlah, subtotal))
        items_simpan.append({"produk_id": p["id"], "nama": p["nama"], "jumlah": jumlah})

    if not items_simpan:
        return "Tidak ada produk yang diisi."

    total = sum(s for _, _, s in items_preview)
    lines = ["*Konfirmasi Penjualan Produk*", _format_tanggal_id(tanggal), ""]
    for nama, jumlah, subtotal in items_preview:
        lines.append(f"{nama} x{jumlah} = {_rupiah(subtotal)}")
    lines.append("")
    lines.append(f"*Total: {_rupiah(total)}*")
    lines.append("")
    lines.append("Balas *YA* untuk simpan, atau *BATAL*.")

    payload = {"tanggal": tanggal, "items": items_simpan}
    whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_produk", payload)
    return "\n".join(lines)


def _parse_baris_produk_mutasi(tenant_id: int, sisa_setelah_kata: str, format_hint: str):
    """Dipakai BERSAMA oleh Restock & Tester (permintaan Owner) -- parsing
    tanggal+baris kode/nomor+jumlah PERSIS SAMA seperti _cmd_input_produk()
    di atas, TAPI tidak perlu subtotal rupiah (restock/tester tidak
    mengubah omzet) jadi dipisah sebagai helper sendiri alih-alih
    menumpangi _cmd_input_produk(). Return (tanggal, items, None) kalau
    valid, atau (None, None, pesan_error) kalau gagal -- `items` = list
    {"produk_id", "nama", "jumlah"}."""
    baris = [l.strip() for l in sisa_setelah_kata.split("\n") if l.strip()]
    tanggal = date.today().isoformat()
    if baris:
        tm = _cari_tanggal(baris[0])
        if tm:
            tanggal = tm[2]
            sisa0 = (baris[0][:tm[0]] + baris[0][tm[1]:]).strip()
            if sisa0:
                baris[0] = sisa0
            else:
                baris = baris[1:]

    if not baris:
        return None, None, f'Format: "{format_hint} [tanggal]" lalu baris kode/nomor+jumlah, mis. "Captain Clay 30 1".'

    produk_list = db.get_produk_list(tenant_id=tenant_id)
    produk_terurut = sorted(produk_list, key=lambda p: p["id"])

    items = []
    for baris_item in baris:
        parsed = _parse_baris_kode_jumlah(baris_item, POLA_PRODUK)
        if parsed is None:
            return None, None, f'Baris tidak dikenali: "{baris_item}".'
        kode, jumlah = parsed
        if kode.isdigit():
            idx = int(kode)
            if idx < 1 or idx > len(produk_terurut):
                return None, None, f'Nomor produk {idx} tidak ada di daftar. Kirim "Daftar Produk" untuk lihat nomornya.'
            p = produk_terurut[idx - 1]
        else:
            cocok = _cocokkan(kode, produk_list, "nama")
            if len(cocok) == 0:
                return None, None, f'Produk "{kode}" tidak dikenali.'
            if len(cocok) > 1:
                return None, None, _teks_ambigu_list(kode, cocok, "nama")
            p = cocok[0]
        items.append({"produk_id": p["id"], "nama": p["nama"], "jumlah": jumlah})

    if not items:
        return None, None, "Tidak ada produk yang diisi."
    return tanggal, items, None


def _cmd_restock_produk(tenant_id: int, wa_id_pengirim: str, sisa_setelah_kata: str) -> str:
    tanggal, items, error = _parse_baris_produk_mutasi(tenant_id, sisa_setelah_kata, "Restock")
    if error:
        return error

    lines = ["*Konfirmasi Restock Produk*", _format_tanggal_id(tanggal), ""]
    for it in items:
        lines.append(f"{it['nama']} +{it['jumlah']}")
    lines.append("")
    lines.append("Balas *YA* untuk simpan, atau *BATAL*.")

    payload = {"tanggal": tanggal, "items": items}
    whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "restock_produk", payload)
    return "\n".join(lines)


def _cmd_tester_produk(tenant_id: int, wa_id_pengirim: str, sisa_setelah_kata: str) -> str:
    tanggal, items, error = _parse_baris_produk_mutasi(tenant_id, sisa_setelah_kata, "Tester")
    if error:
        return error

    lines = ["*Konfirmasi Tester Produk*", _format_tanggal_id(tanggal), ""]
    for it in items:
        lines.append(f"{it['nama']} -{it['jumlah']} (tester, TIDAK dihitung omzet)")
    lines.append("")
    lines.append("Balas *YA* untuk simpan, atau *BATAL*.")

    payload = {"tanggal": tanggal, "items": items}
    whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "tester_produk", payload)
    return "\n".join(lines)


def _cmd_rekap_produk(tenant_id: int, sisa_teks: str) -> str:
    tahun, bulan = _bulan_dari_teks(sisa_teks) or _bulan_sekarang()
    rows = db.get_mutasi_produk_list(tipe="jual", tahun=tahun, bulan=bulan, tenant_id=tenant_id)
    agregat: dict[str, dict] = {}
    for r in rows:
        key = r["nama_produk"]
        a = agregat.setdefault(key, {"jumlah": 0, "omzet": 0})
        a["jumlah"] += r["jumlah"]
        a["omzet"] += r["jumlah"] * (r.get("harga_jual_saat_itu") or 0)

    lines = [f"*Rekap Produk - {_NAMA_BULAN[bulan]} {tahun}*", ""]
    if not agregat:
        lines.append("Tidak ada penjualan produk bulan ini.")
        return "\n".join(lines)
    total = 0
    for nama, data in agregat.items():
        lines.append(f"{nama}: {data['jumlah']} terjual = {_rupiah(data['omzet'])}")
        total += data["omzet"]
    lines.append("")
    lines.append(f"*Total Penjualan Produk: {_rupiah(total)}*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# REKAP (service/komisi/tips/uang harian) -- Owner semua barber, Barber diri
# sendiri saja.
# ---------------------------------------------------------------------------

# PERMINTAAN OWNER: rekap PERIODE (bukan satu hari) sampai 10 hari
# ditampilkan DETAIL PER HARI (lihat _rekap_satu_barber_per_hari()) --
# lebih dari itu (mis. rekap 1 bulan penuh) tetap format agregat lama
# (_rekap_satu_barber()) supaya pesan tidak kepanjangan.
_BATAS_HARI_REKAP_DETAIL = 10


def _cmd_rekap(tenant_id: int, role: str, barber_self: dict, sisa_teks: str,
                tampilkan_potongan_keterlambatan: bool = True) -> str:
    periode = _parse_periode(sisa_teks) if sisa_teks else None
    if periode:
        tanggal_mulai, tanggal_selesai, sisa_setelah = periode
    else:
        tm = _cari_tanggal(sisa_teks)
        if tm:
            tanggal_mulai = tanggal_selesai = tm[2]
            sisa_setelah = (sisa_teks[:tm[0]] + sisa_teks[tm[1]:]).strip()
        else:
            tanggal_mulai = tanggal_selesai = date.today().isoformat()
            sisa_setelah = sisa_teks.strip()

    nama_target = sisa_setelah.strip() or None

    if role == "barber":
        barbers_target = [barber_self]
    else:
        semua = db.get_barbers(tenant_id=tenant_id)
        if nama_target:
            cocok = _cocokkan_barber(nama_target, semua)
            if len(cocok) != 1:
                return _hasil_barber_gagal(nama_target, cocok)
            barbers_target = cocok
        else:
            barbers_target = semua

    if tanggal_mulai == tanggal_selesai:
        judul = f"*Rekap {_format_tanggal_id(tanggal_mulai)}*"
    else:
        judul = f"*Rekap Periode {_format_tanggal_id(tanggal_mulai)} - {_format_tanggal_id(tanggal_selesai)}*"

    jumlah_hari = (date.fromisoformat(tanggal_selesai) - date.fromisoformat(tanggal_mulai)).days + 1
    per_hari = tanggal_mulai != tanggal_selesai and jumlah_hari <= _BATAS_HARI_REKAP_DETAIL

    blok = [judul, ""]
    for b in barbers_target:
        if per_hari:
            blok.append(_rekap_satu_barber_per_hari(tenant_id, b, tanggal_mulai, tanggal_selesai,
                                                      tampilkan_potongan_keterlambatan))
        else:
            blok.append(_rekap_satu_barber(tenant_id, b, tanggal_mulai, tanggal_selesai,
                                            tampilkan_potongan_keterlambatan))
        blok.append("")
    return "\n".join(blok).rstrip()


def _uang_harian_tampilan_hari(tenant_id: int, barber: dict, tanggal: str,
                                tampilkan_potongan_keterlambatan: bool) -> int:
    """Uang Harian SATU hari untuk DITAMPILKAN di WA Bot -- sama persis
    db.hitung_uang_harian_per_hari() (termasuk percabangan opt-in Uang
    Harian Dinamis), KECUALI Superadmin menonaktifkan
    `tampilkan_potongan_keterlambatan` DAN tenant memang memakai Uang
    Harian Dinamis -- dalam kondisi itu potongan KHUSUS dari keterlambatan/
    pulang lebih awal diabaikan UNTUK TAMPILAN SAJA (potongan syarat
    minimal service TETAP berlaku apa adanya, termasuk Rp0 mutlak kalau
    syaratnya tidak terpenuhi). Angka SESUNGGUHNYA yang dibayarkan
    (Dashboard/Slip Gaji/Laporan PDF) TIDAK disentuh fungsi ini sama
    sekali -- murni lapisan tampilan pesan WA Bot."""
    if tampilkan_potongan_keterlambatan or not uang_harian_dinamis_db.get_config(tenant_id)["aktif"]:
        return db.hitung_uang_harian_per_hari(barber, tanggal)
    breakdown = uang_harian_dinamis_db.breakdown_hari(barber, tanggal)
    service = breakdown["service"]
    if service["mode"] == "SYARAT" and not service["terpenuhi"]:
        return breakdown["uang_harian_final"]
    # Toggle ini KHUSUS keterlambatan (permintaan Owner) -- potongan pulang
    # lebih awal dan syarat minimal service TETAP berlaku apa adanya, cuma
    # kontribusi "keterlambatan" yang diabaikan dari MAX (lihat
    # uang_harian_dinamis_db.evaluasi_hari(), section 11 & 13: potongan
    # digabung pakai MAX, bukan dijumlahkan).
    potongan_tanpa_keterlambatan = max(breakdown["pulang_awal"]["potongan_persen"], service["potongan_persen"])
    return round(breakdown["uang_harian_dasar"] * (100 - potongan_tanpa_keterlambatan) / 100)


def _uang_harian_tampilan_rentang(tenant_id: int, barber: dict, tanggal_mulai: str, tanggal_selesai: str,
                                   tampilkan_potongan_keterlambatan: bool) -> int:
    if tampilkan_potongan_keterlambatan or not uang_harian_dinamis_db.get_config(tenant_id)["aktif"]:
        return db.hitung_uang_harian_rentang(barber, tanggal_mulai, tanggal_selesai)
    total = 0
    cur = date.fromisoformat(tanggal_mulai)
    akhir = date.fromisoformat(tanggal_selesai)
    while cur <= akhir:
        total += _uang_harian_tampilan_hari(tenant_id, barber, cur.isoformat(), tampilkan_potongan_keterlambatan)
        cur += timedelta(days=1)
    return total


def _rekap_satu_barber(tenant_id: int, barber: dict, tanggal_mulai: str, tanggal_selesai: str,
                        tampilkan_potongan_keterlambatan: bool = True) -> str:
    lines = [f"*{barber['nama']}*"]
    transaksi_list = db.get_transaksi_list(barber_id=barber["id"], tanggal_mulai=tanggal_mulai,
                                            tanggal_selesai=tanggal_selesai, tenant_id=tenant_id)
    jumlah_libur = _hitung_hari_libur_rentang(barber["id"], tanggal_mulai, tanggal_selesai)

    if not transaksi_list:
        if tanggal_mulai == tanggal_selesai:
            status = _status_libur_cuti_hari(barber["id"], tanggal_mulai)
            if status:
                lines.append(status)
                return "\n".join(lines)
        lines.append("Tidak ada transaksi.")
        if jumlah_libur:
            lines.append(f"Total Hari Libur: {jumlah_libur} hari")
        return "\n".join(lines)

    agregat_service: dict[str, int] = {}
    total_komisi = 0
    total_tips = 0
    for t in transaksi_list:
        total_tips += t.get("tips", 0) or 0
        total_komisi += t.get("total_komisi", 0) or 0
        for it in t["items"]:
            agregat_service[it["nama_service"]] = agregat_service.get(it["nama_service"], 0) + it["jumlah"]

    for nama, jml in agregat_service.items():
        lines.append(f"{nama} x{jml}")
    lines.append(f"Total Komisi: {_rupiah(total_komisi)}")
    lines.append(f"Total Tips: {_rupiah(total_tips)}")

    uang_harian_total = 0
    try:
        if tanggal_mulai == tanggal_selesai:
            uang_harian_total = _uang_harian_tampilan_hari(tenant_id, barber, tanggal_mulai,
                                                             tampilkan_potongan_keterlambatan)
        else:
            # BUGFIX: sebelumnya Uang Harian cuma dihitung untuk rekap SATU
            # hari (breakdown_hari()) -- rekap PERIODE (rentang tanggal)
            # selalu dapat Rp0. Dipakai database.hitung_uang_harian_rentang()
            # (BUKAN uang_harian_dinamis_db.hitung_uang_harian_dinamis_rentang()
            # langsung) -- wrapper di database.py ini yang PUNYA percabangan
            # opt-in Uang Harian Dinamis (lihat _uang_harian_dinamis_aktif()):
            # tenant yang BELUM opt-in (mayoritas, termasuk default) tetap
            # pakai sistem lama berbasis jumlah service, SAMA seperti jalur
            # satu-hari (breakdown_hari() sudah menangani ini sendiri) --
            # manggil modul dinamis langsung TANPA percabangan ini bikin
            # Uang Harian SELALU Rp0 untuk tenant yang belum opt-in, karena
            # modul dinamis mensyaratkan data Absensi check-in+check-out
            # lengkap tiap tanggal, bukan sekadar jumlah service.
            uang_harian_total = _uang_harian_tampilan_rentang(tenant_id, barber, tanggal_mulai, tanggal_selesai,
                                                                tampilkan_potongan_keterlambatan)
        lines.append(f"Uang Harian: {_rupiah(uang_harian_total)}")
    except Exception:
        pass

    if jumlah_libur:
        lines.append(f"Total Hari Libur: {jumlah_libur} hari")

    grand_total = total_komisi + total_tips + uang_harian_total
    lines.append(f"*Grand Total: {_rupiah(grand_total)}*")
    return "\n".join(lines)


def _rekap_satu_barber_per_hari(tenant_id: int, barber: dict, tanggal_mulai: str, tanggal_selesai: str,
                                 tampilkan_potongan_keterlambatan: bool = True) -> str:
    """PERMINTAAN OWNER: rekap periode pendek (<= _BATAS_HARI_REKAP_DETAIL
    hari) dipecah per tanggal -- tiap hari tetap ditampilkan WALAU tidak
    ada transaksi (Libur/Cuti/Izin/Tanpa keterangan/Tidak ada transaksi),
    supaya kelihatan lengkap semua hari dalam periode, bukan cuma angka
    agregat keseluruhan."""
    lines = [f"*{barber['nama']}*", ""]
    tanggal_absen = {l["tanggal"] for l in attendance_db.get_log_list(
        tenant_id, tanggal_dari=tanggal_mulai, tanggal_sampai=tanggal_selesai, barber_id=barber["id"])}

    total_komisi = 0
    total_tips = 0
    total_uang_harian = 0
    jumlah_libur = 0

    cur = date.fromisoformat(tanggal_mulai)
    akhir = date.fromisoformat(tanggal_selesai)
    while cur <= akhir:
        tanggal = cur.isoformat()
        blok = [f"*{_format_tanggal_id(tanggal)}*"]
        status = _status_libur_cuti_hari(barber["id"], tanggal)
        if status == "LIBUR":
            blok.append("Libur")
            jumlah_libur += 1
        elif status == "CUTI":
            blok.append("Cuti")
        elif status == "IZIN":
            blok.append("Izin")
        else:
            transaksi_hari = db.get_transaksi_list(barber_id=barber["id"], tanggal_mulai=tanggal,
                                                     tanggal_selesai=tanggal, tenant_id=tenant_id)
            if not transaksi_hari:
                blok.append("Tidak ada transaksi." if tanggal in tanggal_absen else "Tanpa keterangan")
            else:
                agregat_service: dict[str, int] = {}
                komisi_hari = 0
                tips_hari = 0
                for t in transaksi_hari:
                    tips_hari += t.get("tips", 0) or 0
                    komisi_hari += t.get("total_komisi", 0) or 0
                    for it in t["items"]:
                        agregat_service[it["nama_service"]] = agregat_service.get(it["nama_service"], 0) + it["jumlah"]
                for nama, jml in agregat_service.items():
                    blok.append(f"{nama} x{jml}")
                try:
                    uang_harian_hari = _uang_harian_tampilan_hari(tenant_id, barber, tanggal,
                                                                    tampilkan_potongan_keterlambatan)
                except Exception:
                    uang_harian_hari = 0
                blok.append(f"Komisi: {_rupiah(komisi_hari)}")
                blok.append(f"Tips: {_rupiah(tips_hari)}")
                blok.append(f"Uang Harian: {_rupiah(uang_harian_hari)}")
                total_komisi += komisi_hari
                total_tips += tips_hari
                total_uang_harian += uang_harian_hari
        lines.append("\n".join(blok))
        lines.append("")
        cur += timedelta(days=1)

    grand_total = total_komisi + total_tips + total_uang_harian
    lines.append(f"Total Komisi: {_rupiah(total_komisi)}")
    lines.append(f"Total Tips: {_rupiah(total_tips)}")
    lines.append(f"Total Uang Harian: {_rupiah(total_uang_harian)}")
    if jumlah_libur:
        lines.append(f"Total Hari Libur: {jumlah_libur} hari")
    lines.append(f"*Grand Total: {_rupiah(grand_total)}*")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# ABSENSI -- Owner semua barber, Barber diri sendiri saja.
# ---------------------------------------------------------------------------

def _cmd_absensi(tenant_id: int, role: str, barber_self: dict, sisa_teks: str) -> str:
    tm = _cari_tanggal(sisa_teks)
    tanggal = tm[2] if tm else date.today().isoformat()

    barbers_target = [barber_self] if role == "barber" else db.get_barbers(tenant_id=tenant_id)
    logs = attendance_db.get_log_list(tenant_id, tanggal=tanggal)
    log_by_barber = {l["barber_id"]: l for l in logs}

    judul = "Absensi Saya" if role == "barber" else "Absensi"
    lines = [f"*{judul} {_format_tanggal_id(tanggal)}*", ""]
    for b in barbers_target:
        status = _status_libur_cuti_hari(b["id"], tanggal)
        if status:
            lines.append(f"{b['nama']}: {status}")
            continue
        log = log_by_barber.get(b["id"])
        if log is None or not log.get("check_in_at"):
            lines.append(f"{b['nama']}: Belum Check In")
        elif not log.get("check_out_at"):
            lines.append(f"{b['nama']}: Masuk {log['check_in_at'][11:16]}, belum Check Out")
        else:
            lines.append(f"{b['nama']}: Masuk {log['check_in_at'][11:16]}, Pulang {log['check_out_at'][11:16]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CUTI/IZIN -- dibuka untuk SEMUA barber (bukan self-only), permintaan
# eksplisit Owner: info jadwal cuti rekan kerja lebih berguna dibagikan
# terbuka dibanding data keuangan/komisi yang tetap self-only.
# ---------------------------------------------------------------------------

def _cmd_cuti(tenant_id: int, sisa_teks: str) -> str:
    tahun, bulan = _bulan_dari_teks(sisa_teks) or _bulan_sekarang()
    awal_bulan = date(tahun, bulan, 1).isoformat()
    akhir_bulan = _akhir_bulan(tahun, bulan)

    semua = izin_cuti_db.get_pengajuan_list(tenant_id=tenant_id)
    # Bersinggungan dengan bulan yang diminta (BUKAN cuma yang MULAI di
    # bulan itu) -- pengajuan yang melintasi batas bulan (mis. 30 Okt - 3
    # Nov) harus tetap muncul di query Oktober MAUPUN November.
    overlap = [p for p in semua if p["status"] != "ditolak"
               and p["tanggal_mulai"] <= akhir_bulan and p["tanggal_selesai"] >= awal_bulan]

    lines = [f"*Cuti/Izin - {_NAMA_BULAN[bulan]} {tahun}*", ""]
    if not overlap:
        lines.append("Tidak ada pengajuan Cuti/Izin bulan ini.")
        return "\n".join(lines)

    label_status = {"pending": "Menunggu Persetujuan", "disetujui": "Disetujui", "ditolak": "Ditolak"}
    overlap.sort(key=lambda p: p["tanggal_mulai"])
    for p in overlap:
        jenis_label = "Cuti" if p["jenis"] == "cuti" else "Izin"
        if p["tanggal_mulai"] == p["tanggal_selesai"]:
            rentang = _format_tanggal_id(p["tanggal_mulai"])
        else:
            rentang = f"{_format_tanggal_id(p['tanggal_mulai'])} - {_format_tanggal_id(p['tanggal_selesai'])}"
        lines.append(f"{p['nama_barber']}: {jenis_label} {rentang} ({label_status.get(p['status'], p['status'])})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BOOKING -- Owner semua barber (+ tanggal masa lalu boleh), Barber diri
# sendiri saja (hari ini & ke depan SAJA -- tanggal lewat ditolak eksplisit).
# ---------------------------------------------------------------------------

def _cmd_booking(tenant_id: int, role: str, barber_self: dict, sisa_teks: str) -> str:
    teks_lower = sisa_teks.lower().strip()
    mode_minggu = teks_lower == "minggu ini"
    tanggal = None  # None = mode rentang "dari_tanggal" (minggu ini / tanpa parameter eksplisit)

    if teks_lower in ("", "hari ini"):
        tanggal = date.today().isoformat()
    elif teks_lower == "besok":
        tanggal = (date.today() + timedelta(days=1)).isoformat()
    elif mode_minggu:
        tanggal = None
    else:
        tm = _cari_tanggal(sisa_teks)
        tanggal = tm[2] if tm else date.today().isoformat()

    hari_ini_iso = date.today().isoformat()
    if role == "barber" and tanggal is not None and tanggal < hari_ini_iso:
        return ("Booking tanggal yang sudah lewat tidak bisa diakses lewat WA. "
                "Hubungi Owner/Admin kalau butuh data booking lama.")

    barber_id_filter = barber_self["id"] if role == "barber" else None
    if mode_minggu:
        akhir = (date.today() + timedelta(days=7)).isoformat()
        daftar = booking_db.get_booking_list(barber_id=barber_id_filter, tenant_id=tenant_id,
                                              dari_tanggal=hari_ini_iso)
        daftar = [d for d in daftar if d["tanggal"] <= akhir]
    else:
        daftar = booking_db.get_booking_list(barber_id=barber_id_filter, tenant_id=tenant_id, tanggal=tanggal)

    judul_tanggal = "Minggu Ini" if mode_minggu else _format_tanggal_id(tanggal)
    judul = f"Booking Saya {judul_tanggal}" if role == "barber" else f"Booking {judul_tanggal}"
    lines = [f"*{judul}*", ""]
    if not daftar:
        lines.append("Tidak ada booking.")
        return "\n".join(lines)

    daftar = sorted(daftar, key=lambda d: (d["tanggal"], d["jam_mulai"]))
    for d in daftar:
        suffix = f" - Barber: {d['nama_barber']}" if role == "owner" else ""
        lines.append(f"{d['jam_mulai']} - {d['customer_nama']} ({d.get('daftar_service', '')}){suffix}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# KUOTA LIBUR & KETERLAMBATAN -- tanpa parameter periode (Kuota Libur =
# nilai saat ini, Keterlambatan = selalu bulan kalender berjalan),
# Owner semua barber (atau satu nama), Barber diri sendiri saja.
# ---------------------------------------------------------------------------

def _resolve_barbers_target(tenant_id: int, role: str, barber_self: dict, nama_target: str):
    """Return (list_barber, None) kalau sukses, atau (None, teks_error)
    kalau nama_target diisi tapi gagal cocok (0 atau 2+ kandidat)."""
    if role == "barber":
        return [barber_self], None
    semua = db.get_barbers(tenant_id=tenant_id)
    if not nama_target:
        return semua, None
    cocok = _cocokkan_barber(nama_target, semua)
    if len(cocok) != 1:
        return None, _hasil_barber_gagal(nama_target, cocok)
    return cocok, None


def _cmd_kuota_libur(tenant_id: int, role: str, barber_self: dict, sisa_teks: str) -> str:
    barbers_target, error = _resolve_barbers_target(tenant_id, role, barber_self, sisa_teks.strip())
    if error:
        return error
    lines = ["*Kuota Libur*", ""]
    for b in barbers_target:
        saldo = kuota_libur_db.get_sisa_kuota_libur_bulan_ini(b["id"], tenant_id)
        if not saldo["aktif"]:
            lines.append(f"{b['nama']}: Tidak dibatasi (kuota belum diatur Owner)")
        else:
            lines.append(f"{b['nama']}: Sisa {saldo['sisa']} hari")
    return "\n".join(lines)


def _cmd_keterlambatan(tenant_id: int, role: str, barber_self: dict, sisa_teks: str) -> str:
    barbers_target, error = _resolve_barbers_target(tenant_id, role, barber_self, sisa_teks.strip())
    if error:
        return error
    tahun, bulan = _bulan_sekarang()
    lines = ["*Keterlambatan & Pulang Cepat*", f"Bulan {_NAMA_BULAN[bulan]} {tahun} (berjalan)", ""]
    blok = []
    for b in barbers_target:
        ringkasan = attendance_db.hitung_ringkasan_bulan(b["id"], tenant_id, tahun, bulan)
        baris_telat = (f"Keterlambatan: {ringkasan['menit_terlambat_terpakai']}/"
                       f"{ringkasan['batas_menit_terlambat']} menit "
                       f"(sisa {ringkasan['sisa_limit_terlambat']} menit)")
        if ringkasan["sisa_limit_terlambat"] == 0:
            baris_telat += " — limit habis"
        baris_pulang = (f"Pulang Cepat: {ringkasan['menit_pulang_awal_terpakai']}/"
                        f"{ringkasan['batas_menit_pulang_awal']} menit "
                        f"(sisa {ringkasan['sisa_limit_pulang_awal']} menit)")
        if ringkasan["sisa_limit_pulang_awal"] == 0:
            baris_pulang += " — limit habis"
        blok.append(f"{b['nama']}\n{baris_telat}\n{baris_pulang}")
    lines.append("\n\n".join(blok))
    return "\n".join(lines)
