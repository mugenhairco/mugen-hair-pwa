"""
pengaturan_bonus.py — Target Bonus Service bertingkat (REVISI)
=================================================================
`database.py` SUDAH punya get_bonus_customer_tiers()/set_bonus_customer_tiers()
(baca/tulis daftar tier + validasi dasar) — dipakai APA ADANYA di sini. File
ini HANYA menambah aturan tambah/ubah/hapus SATU tier lewat identitas
`target`-nya (tidak ada tabel dengan id sendiri untuk tier, jadi target-nya
itu sendiri yang dipakai sebagai identitas — sekaligus mencegah dua tier
dengan target yang sama), dengan pesan error yang jelas untuk menu Setting.
"""

import database as db


def tambah_tier(target: int, bonus: int) -> list:
    tiers = db.get_bonus_customer_tiers()
    if any(t["target"] == target for t in tiers):
        raise ValueError(f"Target {target} service sudah ada.")
    tiers.append({"target": target, "bonus": bonus})
    db.set_bonus_customer_tiers(tiers)
    return db.get_bonus_customer_tiers()


def ubah_tier(target_lama: int, target_baru: int, bonus: int) -> list:
    tiers = db.get_bonus_customer_tiers()
    if not any(t["target"] == target_lama for t in tiers):
        raise ValueError(f"Target {target_lama} service tidak ditemukan.")
    tiers = [t for t in tiers if t["target"] != target_lama]
    if any(t["target"] == target_baru for t in tiers):
        raise ValueError(f"Target {target_baru} service sudah dipakai tier lain.")
    tiers.append({"target": target_baru, "bonus": bonus})
    db.set_bonus_customer_tiers(tiers)
    return db.get_bonus_customer_tiers()


def hapus_tier(target: int) -> list:
    tiers = db.get_bonus_customer_tiers()
    baru = [t for t in tiers if t["target"] != target]
    if len(baru) == len(tiers):
        raise ValueError(f"Target {target} service tidak ditemukan.")
    db.set_bonus_customer_tiers(baru)
    return db.get_bonus_customer_tiers()
