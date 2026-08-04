"""
landing_db.py — FONDASI Multi-Tenant Phase 5: Landing Page SaaS
=================================================================
CRUD untuk konten Landing Page publik yang dikelola Super Admin (BUKAN
hardcode, sesuai spesifikasi Phase 5): FAQ, Testimonial, info kontak
platform, dan statistik manual (Happy Customers/Uptime -- tidak ada
entitas datanya di database, lihat routers/landing.py::stats() untuk
statistik yang DIHITUNG LANGSUNG dari data asli seperti jumlah tenant aktif
dan jumlah booking).

Pola CRUD mengikuti subscription_packages/subscription_features di
billing_db.py. Info kontak platform + statistik manual memakai tabel
`settings` key-value yang SUDAH ADA (database.py::get_setting/set_setting)
dengan `tenant_id=None` DAN key baru yang jelas ber-prefix "platform_" --
SENGAJA TIDAK memakai nama key lama apa pun supaya tidak bentrok dengan
ruang key lama pra-multi-tenant (lihat catatan _kunci_tenant() di
database.py: tenant_id=None mengembalikan key APA ADANYA, ruang key yang
sama dipakai data legacy)."""

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


# ============================= Testimonial =============================


def list_testimonials(hanya_aktif: bool = False) -> list:
    with get_conn() as conn:
        if hanya_aktif:
            rows = conn.execute(
                "SELECT * FROM landing_testimonials WHERE aktif = 1 ORDER BY urutan ASC, id ASC"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM landing_testimonials ORDER BY urutan ASC, id ASC").fetchall()
        return [dict(r) for r in rows]


def get_testimonial(testimonial_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM landing_testimonials WHERE id = ?", (testimonial_id,)).fetchone()
        return dict(row) if row else None


def create_testimonial(nama: str, isi: str, jabatan_toko: str = "", foto_url: str = None, rating: int = 5) -> dict:
    nama = (nama or "").strip()
    isi = (isi or "").strip()
    if not nama:
        raise ValueError("Nama tidak boleh kosong.")
    if not isi:
        raise ValueError("Isi testimonial tidak boleh kosong.")
    if not (1 <= int(rating) <= 5):
        raise ValueError("Rating harus antara 1-5.")
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        urutan_maks = conn.execute(
            "SELECT COALESCE(MAX(urutan), -1) AS m FROM landing_testimonials"
        ).fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO landing_testimonials "
            "(nama, jabatan_toko, isi, foto_url, rating, urutan, aktif, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (nama, (jabatan_toko or "").strip(), isi, foto_url, int(rating), urutan_maks + 1, now, now),
        )
        testimonial_id = cur.lastrowid
    return get_testimonial(testimonial_id)


def update_testimonial(testimonial_id: int, **fields) -> dict:
    if get_testimonial(testimonial_id) is None:
        raise ValueError("Testimonial tidak ditemukan.")
    kolom_valid = {"nama", "jabatan_toko", "isi", "foto_url", "rating", "urutan", "aktif"}
    updates = {k: v for k, v in fields.items() if k in kolom_valid}
    if "nama" in updates and not str(updates["nama"]).strip():
        raise ValueError("Nama tidak boleh kosong.")
    if "isi" in updates and not str(updates["isi"]).strip():
        raise ValueError("Isi testimonial tidak boleh kosong.")
    if "rating" in updates and not (1 <= int(updates["rating"]) <= 5):
        raise ValueError("Rating harus antara 1-5.")
    if not updates:
        return get_testimonial(testimonial_id)
    updates["updated_at"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        conn.execute(f"UPDATE landing_testimonials SET {set_clause} WHERE id = ?", (*updates.values(), testimonial_id))
    return get_testimonial(testimonial_id)


def delete_testimonial(testimonial_id: int):
    if get_testimonial(testimonial_id) is None:
        raise ValueError("Testimonial tidak ditemukan.")
    with get_conn() as conn:
        conn.execute("DELETE FROM landing_testimonials WHERE id = ?", (testimonial_id,))


# ============================= Kontak Platform & Statistik Manual =============================

_CONTACT_KEYS = [
    "platform_contact_whatsapp", "platform_contact_email",
    "platform_contact_alamat", "platform_contact_maps_url",
    "platform_social_instagram", "platform_social_facebook", "platform_social_tiktok",
]
_STAT_KEYS = ["platform_stat_happy_customers", "platform_stat_uptime"]


def get_contact() -> dict:
    return {k: db.get_setting(k, "", tenant_id=None) for k in _CONTACT_KEYS}


def update_contact(data: dict):
    bersih = {k: (v or "").strip() for k, v in data.items() if k in _CONTACT_KEYS}
    if bersih:
        db.set_settings_bulk(bersih, tenant_id=None)


def get_manual_stats() -> dict:
    return {k: db.get_setting(k, "", tenant_id=None) for k in _STAT_KEYS}


def update_manual_stats(data: dict):
    bersih = {k: (v or "").strip() for k, v in data.items() if k in _STAT_KEYS}
    if bersih:
        db.set_settings_bulk(bersih, tenant_id=None)


def get_live_stats() -> dict:
    """Dihitung LANGSUNG dari data asli (bukan setting manual) -- keputusan
    cakupan Phase 5: "Active Tenants" & "Total Bookings" TIDAK dihardcode
    dan TIDAK bisa diedit Super Admin, murni cerminan data sungguhan supaya
    tidak pernah menampilkan angka yang menyesatkan."""
    with get_conn() as conn:
        active_tenants = conn.execute("SELECT COUNT(*) AS c FROM tenants WHERE status = 'aktif'").fetchone()["c"]
        total_bookings = conn.execute("SELECT COUNT(*) AS c FROM bookings").fetchone()["c"]
    return {"active_tenants": active_tenants, "total_bookings": total_bookings}
