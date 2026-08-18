"""routers/push.py — /api/push/* (FITUR Notifikasi Push, Web Push/VAPID)
=============================================================================
Boleh diakses SEMUA role yang sudah login (admin/staff/barber) -- setiap
akun mengatur notifikasi push MILIKNYA SENDIRI (subscribe/unsubscribe
perangkatnya sendiri), tidak ada endpoint di sini yang menyentuh akun lain."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import push_db
import push_service
from auth import get_current_user

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-public-key")
def vapid_public_key(user: dict = Depends(get_current_user)):
    """`enabled=False` (VAPID_* belum dikonfigurasi Owner di hosting) ->
    frontend TIDAK menampilkan tombol "Aktifkan Notifikasi" sama sekali,
    gagal diam-diam (fitur opsional, TIDAK boleh mengganggu halaman
    manapun -- pola sama seperti pengecekan Uang Harian Dinamis aktif)."""
    return {"enabled": push_service.IS_ENABLED, "public_key": push_service.VAPID_PUBLIC_KEY or None}


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeBody(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


@router.post("/subscribe")
def subscribe(body: SubscribeBody, user: dict = Depends(get_current_user)):
    push_db.simpan_subscription(user["id"], user["tenant_id"], body.endpoint, body.keys.p256dh, body.keys.auth)
    return {"ok": True}


class UnsubscribeBody(BaseModel):
    endpoint: str


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeBody, user: dict = Depends(get_current_user)):
    # BUGFIX (audit, IDOR): dulu memanggil push_db.hapus_subscription()
    # langsung -- fungsi itu menghapus HANYA berdasarkan endpoint, tanpa
    # cek kepemilikan sama sekali, jadi siapa pun yang login (dari tenant
    # mana pun) dan mengetahui string endpoint subscription push milik
    # ORANG LAIN bisa menghapusnya secara permanen. Sekarang di-scope ke
    # user["id"] yang sedang login.
    push_db.hapus_subscription_milik_user(user["id"], body.endpoint)
    return {"ok": True}
