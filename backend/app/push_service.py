"""
push_service.py — Kirim Notifikasi Push (Web Push Protocol/VAPID)
=============================================================================
Pola IS_ENABLED SAMA PERSIS email_service.py (lihat komentar di sana untuk
alasan lengkap): VAPID_PRIVATE_KEY/VAPID_PUBLIC_KEY kosong (default) ->
IS_ENABLED=False, kirim_ke_user()/kirim_ke_role() TIDAK PERNAH memanggil
jaringan sama sekali -- HANYA mencatat log & mengembalikan 0 (jumlah
terkirim), TIDAK PERNAH melempar exception. Pemanggil (booking_db.py,
izin_cuti_db.py) memanggil fungsi di sini SETELAH operasi utamanya (buat
booking/pengajuan izin) BERHASIL disimpan -- notifikasi push murni "best
effort", kegagalan kirim (kredensial salah, browser cabut izin, jaringan
turun, dst) TIDAK PERNAH boleh menggagalkan operasi bisnis yang memicunya.

VAPID key pair (SEKALI per deployment, BUKAN per tenant) dibuat lewat:
    python3 -c "from py_vapid import Vapid02; v = Vapid02(); v.generate_keys(); print(v.private_pem"
atau lebih mudah lewat `vapid --gen` (dari paket py-vapid, ikut terpasang
sebagai dependency pywebpush) -- isi hasilnya ke environment variable
VAPID_PRIVATE_KEY/VAPID_PUBLIC_KEY di dashboard hosting (pola sama seperti
SECRET_KEY/RESEND_API_KEY, TIDAK PERNAH ikut git).

Dependency `pywebpush` (lihat requirements.txt) HANYA diimpor kalau
IS_ENABLED -- instalasi yang belum mengisi VAPID_* tetap boot normal walau
(secara hipotetis) pywebpush belum terpasang, sama seperti pola
psycopg2-binary/boto3/R2 di modul lain.
"""

import json
import logging
import os

import push_db

logger = logging.getLogger("mugen.push")

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
# mailto:/https: subject WAJIB oleh spek VAPID (RFC 8292) -- identitas
# kontak pengirim, provider push (Apple/Google/Mozilla) memakainya kalau
# perlu menghubungi pemilik server (mis. dianggap spam).
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@rivoirsett.com").strip()

IS_ENABLED = bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


def _kirim_ke_satu_subscription(sub: dict, payload: dict) -> bool:
    """Return True kalau terkirim. Endpoint yang provider push balas 410
    Gone/404 Not Found (kedaluwarsa/dicabut pengguna lewat browser, BUKAN
    lewat tombol di aplikasi ini) otomatis dihapus dari push_subscriptions
    supaya tidak terus dicoba percuma tiap kali."""
    from pywebpush import WebPushException, webpush  # import lokal, lihat catatan IS_ENABLED di atas

    try:
        webpush(
            subscription_info={
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            },
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
            timeout=10,
        )
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            push_db.hapus_subscription(sub["endpoint"])
        else:
            logger.warning("Push ke user_id=%s gagal (HTTP %s): %s", sub.get("user_id"), status, e)
        return False
    except Exception as e:
        logger.error("Push ke user_id=%s gagal tak terduga: %s: %s", sub.get("user_id"), e.__class__.__name__, e)
        return False


def _kirim_ke_daftar_subscription(subs: list, title: str, body: str, url: str = None) -> int:
    if not IS_ENABLED:
        logger.info("Push '%s' TIDAK dikirim (%d subscription dilewati) -- VAPID_* belum dikonfigurasi.",
                     title, len(subs))
        return 0
    payload = {"title": title, "body": body, "url": url or "/app/"}
    terkirim = 0
    for sub in subs:
        if _kirim_ke_satu_subscription(sub, payload):
            terkirim += 1
    return terkirim


def kirim_ke_user(user_id: int, title: str, body: str, url: str = None) -> int:
    """Kirim ke SEMUA perangkat yang subscribe atas nama akun ini (bisa 0
    kalau belum pernah mengaktifkan notifikasi push sama sekali -- itu
    kondisi NORMAL, bukan error)."""
    return _kirim_ke_daftar_subscription(push_db.get_subscriptions_untuk_user(user_id), title, body, url)


def kirim_ke_barber(barber_id: int, title: str, body: str, url: str = None) -> int:
    """Kirim ke akun login barber ini SAJA (bukan tenant_id/roles seperti
    kirim_ke_role() -- lihat push_db.get_subscriptions_untuk_barber())."""
    return _kirim_ke_daftar_subscription(push_db.get_subscriptions_untuk_barber(barber_id), title, body, url)


def kirim_ke_role(tenant_id: int, roles: list, title: str, body: str, url: str = None) -> int:
    """Kirim ke SEMUA akun tenant ini yang role-nya termasuk `roles` (mis.
    Booking Baru/Pengajuan Izin -> ["admin", "staff"])."""
    return _kirim_ke_daftar_subscription(push_db.get_subscriptions_untuk_role(tenant_id, roles), title, body, url)
