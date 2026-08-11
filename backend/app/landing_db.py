"""
landing_db.py — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
=================================================================
CRUD untuk konten Landing Page publik yang dikelola Super Admin (BUKAN
hardcode, sesuai spesifikasi Phase 5): FAQ + info kontak platform (Email &
WhatsApp).

REVISI Restrukturisasi Super Admin & Landing Page: fitur Testimonial dan
Statistik (manual + live) DIHAPUS TOTAL dari sini (bukan disembunyikan --
lihat riwayat commit untuk fitur lengkapnya kalau perlu dikembalikan) --
section Testimoni landing page sudah tidak diperlukan, dan section
Statistik sudah lebih dulu tidak tampil di halaman publik (digantikan
section Differentiator). Field kontak platform SEKARANG HANYA Email &
WhatsApp (dulu juga ada alamat/maps/social media yang TIDAK PERNAH dipakai
frontend -- dihapus sekalian sebagai bagian pembersihan kode mati).

Pola CRUD mengikuti subscription_packages/subscription_features di
billing_db.py. Info kontak platform memakai tabel `settings` key-value yang
SUDAH ADA (database.py::get_setting/set_setting) dengan `tenant_id=None`
DAN key baru yang jelas ber-prefix "platform_" -- SENGAJA TIDAK memakai
nama key lama apa pun supaya tidak bentrok dengan ruang key lama
pra-multi-tenant (lihat catatan _kunci_tenant() di database.py:
tenant_id=None mengembalikan key APA ADANYA, ruang key yang sama dipakai
data legacy)."""

from datetime import datetime

import database as db
from database import get_conn

# ============================= FAQ =============================


def list_faq(hanya_aktif: bool = False) -> list:
    with get_conn() as conn:
        if hanya_aktif:
            rows = conn.execute(
                "SELECT * FROM landing_faq WHERE aktif = 1 ORDER BY urutan ASC, id ASC"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM landing_faq ORDER BY urutan ASC, id ASC").fetchall()
        return [dict(r) for r in rows]


def get_faq(faq_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM landing_faq WHERE id = ?", (faq_id,)).fetchone()
        return dict(row) if row else None


def create_faq(pertanyaan: str, jawaban: str) -> dict:
    pertanyaan = (pertanyaan or "").strip()
    jawaban = (jawaban or "").strip()
    if not pertanyaan:
        raise ValueError("Pertanyaan tidak boleh kosong.")
    if not jawaban:
        raise ValueError("Jawaban tidak boleh kosong.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        urutan_maks = conn.execute("SELECT COALESCE(MAX(urutan), -1) AS m FROM landing_faq").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO landing_faq (pertanyaan, jawaban, urutan, aktif, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (pertanyaan, jawaban, urutan_maks + 1, now, now),
        )
        faq_id = cur.lastrowid
    return get_faq(faq_id)


def update_faq(faq_id: int, **fields) -> dict:
    if get_faq(faq_id) is None:
        raise ValueError("FAQ tidak ditemukan.")
    kolom_valid = {"pertanyaan", "jawaban", "urutan", "aktif"}
    updates = {k: v for k, v in fields.items() if k in kolom_valid}
    if "pertanyaan" in updates and not str(updates["pertanyaan"]).strip():
        raise ValueError("Pertanyaan tidak boleh kosong.")
    if "jawaban" in updates and not str(updates["jawaban"]).strip():
        raise ValueError("Jawaban tidak boleh kosong.")
    if not updates:
        return get_faq(faq_id)
    updates["updated_at"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        conn.execute(f"UPDATE landing_faq SET {set_clause} WHERE id = ?", (*updates.values(), faq_id))
    return get_faq(faq_id)


def delete_faq(faq_id: int):
    if get_faq(faq_id) is None:
        raise ValueError("FAQ tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("DELETE FROM landing_faq WHERE id = ?", (faq_id,))


# ============================= Kontak Platform =============================

_CONTACT_KEYS = ["platform_contact_whatsapp", "platform_contact_email"]


def get_contact() -> dict:
    return {k: db.get_setting(k, "", tenant_id=None) for k in _CONTACT_KEYS}


def update_contact(data: dict):
    bersih = {k: (v or "").strip() for k, v in data.items() if k in _CONTACT_KEYS}
    if bersih:
        db.set_settings_bulk(bersih, tenant_id=None)


# ============================= Footer =============================
# REVISI Restrukturisasi Super Admin & Landing Page: HANYA tagline singkat
# footer yang dinamis -- kolom link navigasi & teks copyright TETAP
# hardcode di index.html (di luar cakupan permintaan).

_FOOTER_KEYS = ["platform_footer_tagline"]


def get_footer() -> dict:
    return {k: db.get_setting(k, "", tenant_id=None) for k in _FOOTER_KEYS}


def update_footer(data: dict):
    bersih = {k: (v or "").strip() for k, v in data.items() if k in _FOOTER_KEYS}
    if bersih:
        db.set_settings_bulk(bersih, tenant_id=None)
