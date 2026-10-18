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

REVISI (WA biasa, bukan Business): menu/command TETAP teks biasa (bukan
tombol/list interaktif WhatsApp Business) -- Owner memakai nomor WA biasa
untuk device Fonnte, belum dipastikan kompatibel dengan fitur interaktif
semacam itu."""

import re
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
    ditemukan di `teks` (format '11 oktober 2026' / '11 oktober', tahun
    opsional = tahun ini), atau None kalau tidak ada pola tanggal valid."""
    pola = r"(\d{1,2})\s+(" + "|".join(_BULAN_ID.keys()) + r")(?:\s+(\d{4}))?"
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
    supaya 0812.../+62812.../62812... semua dianggap nomor yang sama)."""
    nomor_owner = (config.get("nomor_owner_whatsapp") or "").strip() if config else ""
    nomor_pengirim = _normalisasi_nomor(wa_id_pengirim)
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

def proses_pesan(tenant_id: int, config: dict, wa_id_pengirim: str, isi_pesan: str) -> str | None:
    """Return teks balasan, atau None kalau TIDAK BOLEH membalas apa pun
    (nomor pengirim tidak dikenali sama sekali -- bukan Owner, bukan
    barber manapun di tenant ini)."""
    role, barber_self = resolve_role(tenant_id, config, wa_id_pengirim)
    if role is None:
        return None

    teks = (isi_pesan or "").strip()
    if not teks:
        return _menu_teks(role)

    atas = teks.upper()
    if atas in ("YA", "BATAL"):
        pending = whatsapp_bot_db.ambil_pending(tenant_id, wa_id_pengirim)
        if pending is not None:
            return _proses_konfirmasi(tenant_id, wa_id_pengirim, pending, atas)
        return _menu_teks(role)

    teks_lower = teks.lower().strip()
    kata = teks_lower.split()
    kata0 = kata[0] if kata else ""

    if teks_lower in ("menu", "help", "bantuan"):
        return _menu_teks(role)

    if teks_lower == "daftar produk":
        if role != "owner":
            return _menu_teks(role)
        return _cmd_daftar_produk(tenant_id)

    if teks_lower.startswith("rekap produk"):
        if role != "owner":
            return "Maaf, command ini khusus Owner."
        return _cmd_rekap_produk(tenant_id, teks[len("rekap produk"):].strip())

    if kata0 == "produk":
        if role != "owner":
            return "Maaf, input produk cuma bisa dilakukan dari nomor Owner."
        return _cmd_input_produk(tenant_id, wa_id_pengirim, teks[len("produk"):].strip())

    if kata0 == "rekap":
        return _cmd_rekap(tenant_id, role, barber_self, teks[len("rekap"):].strip())

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

    # Sisanya (Input Service / Tandai Libur) -- EKSKLUSIF Owner, dikenali
    # dari baris pertama yang cocok ke nama barber tenant ini.
    if role == "owner":
        hasil = _coba_input_service_atau_libur(tenant_id, wa_id_pengirim, teks)
        if hasil is not None:
            return hasil

    return _menu_teks(role)


def _menu_teks(role: str) -> str:
    if role == "owner":
        return (
            "*Menu WA Bot (Owner)*\n\n"
            '*Input data:* "<nama barber> [tanggal]" lalu baris kode+jumlah, diakhiri "Tips <nominal>"\n'
            '*Tandai libur:* "<nama barber> libur [tanggal]"\n'
            '*Input produk:* "Produk [tanggal]" lalu baris kode/nomor+jumlah\n'
            '*Daftar Produk*\n'
            '*Rekap* <tanggal/periode> [nama barber]\n'
            '*Rekap Produk* <bulan>\n'
            '*Absensi* <tanggal> / *Absen hari ini*\n'
            '*Cuti* <bulan>\n'
            '*Booking* hari ini / besok / <tanggal>\n'
            '*Kuota Libur* [nama]\n'
            '*Keterlambatan* [nama]'
        )
    return (
        "*Menu WA Bot*\n\n"
        '*Rekap* <tanggal/periode> -- data kamu sendiri\n'
        '*Absensi* <tanggal> / *Absen hari ini* -- data kamu sendiri\n'
        '*Cuti* <bulan> -- semua barber\n'
        '*Booking* hari ini / besok / <tanggal> -- punya kamu sendiri (hari ini & ke depan saja)\n'
        '*Kuota Libur* -- punya kamu sendiri\n'
        '*Keterlambatan* -- punya kamu sendiri'
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
        db.tambah_transaksi(p["tanggal"], p["barber_id"], p["items"], tips=p["tips"], sumber=SUMBER_WA_BOT)
        return f"✅ Data {p['nama_barber']} ({_format_tanggal_id(p['tanggal'])}) berhasil disimpan."

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

    return "❌ Konfirmasi tidak dikenali."


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

    payload = {"barber_id": barber["id"], "nama_barber": barber["nama"], "tanggal": tanggal,
               "items": items_simpan, "tips": tips}
    whatsapp_bot_db.simpan_pending(tenant_id, wa_id_pengirim, "input_service", payload)
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
    for i, p in enumerate(produk_list, start=1):
        lines.append(f"{i}. {p['nama']} - {_rupiah(p['harga_jual'])}")
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

def _cmd_rekap(tenant_id: int, role: str, barber_self: dict, sisa_teks: str) -> str:
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

    blok = [judul, ""]
    for b in barbers_target:
        blok.append(_rekap_satu_barber(tenant_id, b, tanggal_mulai, tanggal_selesai))
        blok.append("")
    return "\n".join(blok).rstrip()


def _rekap_satu_barber(tenant_id: int, barber: dict, tanggal_mulai: str, tanggal_selesai: str) -> str:
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
            uh = uang_harian_dinamis_db.breakdown_hari(barber, tanggal_mulai)
            uang_harian_total = uh.get("uang_harian_final", 0)
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
            uang_harian_total = db.hitung_uang_harian_rentang(barber, tanggal_mulai, tanggal_selesai)
        lines.append(f"Uang Harian: {_rupiah(uang_harian_total)}")
    except Exception:
        pass

    if jumlah_libur:
        lines.append(f"Total Hari Libur: {jumlah_libur} hari")

    grand_total = total_komisi + total_tips + uang_harian_total
    lines.append(f"*Grand Total: {_rupiah(grand_total)}*")
    return "\n".join(lines)


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
    for b in barbers_target:
        ringkasan = attendance_db.hitung_ringkasan_bulan(b["id"], tenant_id)
        catatan = ringkasan["keterangan_per_tanggal"].values()
        telat = sum(1 for notes in catatan if any("Terlambat" in n for n in notes))
        pulang_awal = sum(1 for notes in catatan if any("Pulang lebih awal" in n for n in notes))
        lines.append(f"{b['nama']}: Telat {telat}x, Pulang Cepat {pulang_awal}x")
    return "\n".join(lines)
