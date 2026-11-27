"""routers/live_chat_baileys.py — FITUR Live Chat via Baileys (WhatsApp Web sendiri)
=============================================================================
Lihat docstring live_chat_baileys_db.py untuk latar belakang & arsitektur
lengkap (kenapa ini ada, kenapa berdampingan dengan Fonnte bukan ganti
total). Dua router di sini:

1. `authed_router` (/api/live-chat/baileys, require_permission("izin_live_
   chat_lihat") -- SAMA PERSIS gerbang routers/live_chat.py): dipanggil
   FRONTEND (pages/live_chat.js) -- status koneksi, gambar QR, mulai
   connect, putuskan. Endpoint di sini MEMPROKSI ke service Node.js
   terpisah (BAILEYS_SERVICE_URL) lewat HTTP biasa (requests, SAMA pola
   whatsapp_service.py) -- backend Python TIDAK PERNAH bicara protokol
   WhatsApp sendiri, murni penerus perintah + penyimpan status/sesi.

2. `internal_router` (/api/internal/baileys, dilindungi header
   X-Baileys-Secret, pola SAMA PERSIS routers/cron_reminder.py): dipanggil
   SERVICE BAILEYS (bukan frontend, TIDAK ADA sesi login) -- ambil/simpan
   sesi login, lapor perubahan status, lapor pesan masuk/keluar.

Fail-CLOSED kalau BAILEYS_INTERNAL_SECRET belum diisi (pola sama
cron_reminder.py) -- endpoint internal menolak SEMUA permintaan, bukan
menyala tanpa proteksi. BAILEYS_SERVICE_URL kosong -> authed_router
mengembalikan status "belum_terhubung" apa adanya (fitur ini murni
opsional per tenant, TIDAK PERNAH menghalangi Live Chat jalur Fonnte yang
sudah ada kalau belum/tidak diisi)."""

import logging
import os

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import live_chat_baileys_db
import live_chat_db
import push_service
from auth import require_permission

logger = logging.getLogger("mugen.live_chat_baileys")

authed_router = APIRouter(prefix="/api/live-chat/baileys", tags=["live-chat-baileys"])
internal_router = APIRouter(prefix="/api/internal/baileys", tags=["live-chat-baileys-internal"])

_BAILEYS_SERVICE_URL = os.environ.get("BAILEYS_SERVICE_URL", "").strip().rstrip("/")
_INTERNAL_SECRET = os.environ.get("BAILEYS_INTERNAL_SECRET", "").strip()
_TIMEOUT_DETIK = 15


def _wajib_secret_internal(x_baileys_secret: str | None):
    if not _INTERNAL_SECRET or x_baileys_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Tidak diizinkan.")


def kirim_pesan_lewat_baileys(tenant_id: int, nomor_wa: str, pesan: str) -> str:
    """Dipanggil routers/live_chat.py::kirim_balasan() KHUSUS kalau tenant
    ini sudah berstatus 'tersambung' (live_chat_baileys_db.kirim_terpasang()
    -- dicek PEMANGGIL, bukan di sini). Return baileys_msg_id (dipakai
    mekanisme dedup, lihat docstring lapor_pesan() di bawah) -- melempar
    Exception kalau gagal, pemanggil yang menentukan pesan error ke user."""
    if not _BAILEYS_SERVICE_URL:
        raise RuntimeError("BAILEYS_SERVICE_URL belum dikonfigurasi.")
    resp = requests.post(
        f"{_BAILEYS_SERVICE_URL}/tenant/{tenant_id}/kirim", json={"nomor_wa": nomor_wa, "pesan": pesan},
        timeout=_TIMEOUT_DETIK,
    )
    resp.raise_for_status()
    hasil = resp.json()
    if not hasil.get("ok"):
        raise RuntimeError(f"Service Baileys menolak kirim: {hasil}")
    return hasil["baileys_msg_id"]


# ---------------------------------------------------------------------------
# authed_router -- dipanggil frontend (pages/live_chat.js)
# ---------------------------------------------------------------------------

@authed_router.get("/status")
def ambil_status(user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    return live_chat_baileys_db.get_status(user["tenant_id"])


@authed_router.post("/connect")
def mulai_connect(user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    if not _BAILEYS_SERVICE_URL:
        raise HTTPException(status_code=503, detail="Service Baileys belum dikonfigurasi.")
    try:
        resp = requests.post(
            f"{_BAILEYS_SERVICE_URL}/tenant/{user['tenant_id']}/connect", timeout=_TIMEOUT_DETIK)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Gagal memulai connect Baileys tenant_id=%s: %s: %s", user["tenant_id"], type(e).__name__, e)
        raise HTTPException(status_code=502, detail="Gagal menghubungi service Baileys.")
    return live_chat_baileys_db.get_status(user["tenant_id"])


@authed_router.post("/putuskan")
def putuskan(user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    if _BAILEYS_SERVICE_URL:
        try:
            requests.post(
                f"{_BAILEYS_SERVICE_URL}/tenant/{user['tenant_id']}/putuskan", timeout=_TIMEOUT_DETIK)
        except Exception as e:
            # Best-effort -- tetap hapus sesi di sisi kita walau service
            # Baileys sedang tidak bisa dihubungi (mis. sudah mati), supaya
            # Owner tidak "terjebak" tidak bisa memutuskan dari UI.
            logger.warning("Gagal memberi tahu service Baileys soal putuskan tenant_id=%s: %s",
                            user["tenant_id"], e)
    live_chat_baileys_db.hapus_sesi(user["tenant_id"])
    return {"ok": True}


@authed_router.get("/qr.png")
def ambil_qr_png(user: dict = Depends(require_permission("izin_live_chat_lihat"))):
    import io

    import qrcode
    from fastapi.responses import Response

    status = live_chat_baileys_db.get_status(user["tenant_id"])
    if status["status"] != live_chat_baileys_db.STATUS_MENUNGGU_SCAN or not status["qr_data"]:
        raise HTTPException(status_code=404, detail="Tidak ada kode QR aktif saat ini.")
    img = qrcode.make(status["qr_data"])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


# ---------------------------------------------------------------------------
# internal_router -- dipanggil service Baileys (Node.js), BUKAN frontend
# ---------------------------------------------------------------------------

class SesiBody(BaseModel):
    auth_state: str


class StatusBody(BaseModel):
    status: str
    qr_data: str | None = None
    nomor_tersambung: str | None = None


class PesanBody(BaseModel):
    arah: str  # 'masuk' / 'keluar'
    nomor_wa: str
    nama_kontak: str | None = None
    isi_teks: str
    baileys_msg_id: str


@internal_router.get("/tersambung")
def list_tersambung(x_baileys_secret: str | None = Header(default=None)):
    """Dipanggil index.js SEKALI saat proses baileys-service baru boot --
    lihat docstring live_chat_baileys_db.list_tenant_tersambung() untuk
    kenapa ini perlu (socket aktif cuma hidup di memori proses Node.js,
    hilang tiap restart/redeploy walau auth_state tersimpan aman)."""
    _wajib_secret_internal(x_baileys_secret)
    return {"tenant_id": live_chat_baileys_db.list_tenant_tersambung()}


@internal_router.get("/sesi/{tenant_id}")
def ambil_sesi(tenant_id: int, x_baileys_secret: str | None = Header(default=None)):
    _wajib_secret_internal(x_baileys_secret)
    return {"auth_state": live_chat_baileys_db.get_auth_state(tenant_id)}


@internal_router.put("/sesi/{tenant_id}")
def simpan_sesi(tenant_id: int, body: SesiBody, x_baileys_secret: str | None = Header(default=None)):
    _wajib_secret_internal(x_baileys_secret)
    live_chat_baileys_db.set_auth_state(tenant_id, body.auth_state)
    return {"ok": True}


@internal_router.post("/status/{tenant_id}")
def lapor_status(tenant_id: int, body: StatusBody, x_baileys_secret: str | None = Header(default=None)):
    _wajib_secret_internal(x_baileys_secret)
    if body.status == live_chat_baileys_db.STATUS_MENUNGGU_SCAN and body.qr_data:
        live_chat_baileys_db.set_qr(tenant_id, body.qr_data)
    elif body.status == live_chat_baileys_db.STATUS_TERSAMBUNG:
        live_chat_baileys_db.set_tersambung(tenant_id, body.nomor_tersambung or "")
    elif body.status == live_chat_baileys_db.STATUS_TERPUTUS:
        live_chat_baileys_db.set_terputus(tenant_id)
    return {"ok": True}


@internal_router.post("/pesan/{tenant_id}")
def lapor_pesan(tenant_id: int, body: PesanBody, x_baileys_secret: str | None = Header(default=None)):
    """SATU endpoint generik untuk SEMUA event pesan yang dilihat Baileys --
    baik pesan MASUK dari customer, maupun pesan KELUAR (baik yang dikirim
    lewat Rivoir sendiri atau diketik manual dari HP toko -- Baileys tidak
    bisa membedakan ASAL-nya, cuma kita yang tahu lewat baileys_msg_id,
    lihat docstring simpan_pesan_teks_keluar() di live_chat_db.py).

    PERBEDAAN dari public_router.webhook() (jalur Fonnte lama): di sini
    SUDAH dipastikan tenant_id ini sedang berstatus 'tersambung' Baileys
    SEBELUM dipanggil (dijaga service Baileys sendiri -- cuma mengirim
    event untuk socket yang memang sedang aktif), jadi tidak perlu cari
    tenant_id dari token seperti webhook Fonnte.

    Gambar BELUM didukung di endpoint ini (hanya jenis='teks') -- jalur
    gambar lewat Fonnte yang sudah ada tetap terpisah & utuh untuk tenant
    yang belum pakai Baileys. Ini keterbatasan YANG DIKETAHUI, bukan bug --
    didokumentasikan di README/plan untuk fase berikutnya kalau diperlukan."""
    _wajib_secret_internal(x_baileys_secret)

    if body.arah == "keluar":
        if live_chat_db.baileys_msg_id_sudah_tersimpan(body.baileys_msg_id):
            # Echo dari pesan yang baru saja dikirim LEWAT Rivoir sendiri
            # (routers/live_chat.py::kirim_balasan() sudah menyimpannya saat
            # kirim) -- abaikan, JANGAN disimpan dobel.
            return {"ok": True, "disimpan": False}
        live_chat_db.simpan_pesan_teks_keluar(tenant_id, body.nomor_wa, body.isi_teks, body.baileys_msg_id)
        # BUGFIX (laporan Owner: balasan manual dari HP toko sudah tersimpan
        # & muncul di Live Chat, TAPI baru muncul setelah pindah menu lalu
        # balik lagi -- tidak "disuntik" langsung ke tab yang sedang
        # terbuka): beda dari pesan MASUK (lihat di bawah), cabang ini
        # SEBELUMNYA tidak pernah memicu push sama sekali, padahal
        # app.js/live_chat.js::suntikPesanMasuk() (lihat pola "suntik diam-
        # diam" yang sudah ada) tidak peduli arah pesannya -- cukup
        # dikirimi push jenis="live_chat_masuk" supaya tab yang terbuka
        # langsung memuat ulang thread/kontak itu tanpa pindah menu.
        push_service.kirim_ke_role(
            tenant_id, ["admin", "staff"], "Live Chat",
            f"Pesan terkirim ke {body.nomor_wa} dari HP toko",
            url="#/live-chat", jenis="live_chat_masuk",
            data={"nomor_wa": body.nomor_wa, "nama_kontak": None, "jenis": "teks", "isi_teks": body.isi_teks},
        )
        return {"ok": True, "disimpan": True}

    # arah == 'masuk' -- SAMA seperti public_router.webhook() (Fonnte):
    # selalu simpan & picu notifikasi push "Live Chat -- {nama}".
    live_chat_db.simpan_pesan_teks_masuk(tenant_id, body.nomor_wa, body.nama_kontak, body.isi_teks)
    preview = body.isi_teks if len(body.isi_teks) <= 80 else body.isi_teks[:77] + "..."
    push_service.kirim_ke_role(
        tenant_id, ["admin", "staff"], f"Live Chat -- {body.nama_kontak or body.nomor_wa}",
        preview, url="#/live-chat", jenis="live_chat_masuk",
        data={"nomor_wa": body.nomor_wa, "nama_kontak": body.nama_kontak, "jenis": "teks", "isi_teks": body.isi_teks},
    )
    return {"ok": True, "disimpan": True}
