"""billing_periode.py -- Kalkulasi periode kalender (bulan/tahun) untuk
perpanjangan langganan SaaS.
=============================================================================
Requirement Owner (Billing/Subscription overhaul, poin 2): perpanjangan
bulanan/6-bulanan/tahunan HARUS mengikuti kalender sungguhan (31 Jan + 1
bulan -> 28/29 Feb), BUKAN hitungan hari tetap (30/180/360 hari, cara lama
di billing_webhook.py). Kalau tanggal akhir bulan target lebih pendek dari
tanggal asal, di-clamp ke tanggal terakhir bulan itu (aturan umum
"anniversary date" kalender bisnis).

Modul murni (tanpa akses DB) supaya bisa diimpor billing_webhook.py tanpa
risiko import cycle."""

import calendar
from datetime import datetime


def tambah_bulan_kalender(tanggal: datetime, jumlah_bulan: int) -> datetime:
    bulan_index = tanggal.month - 1 + jumlah_bulan
    tahun_baru = tanggal.year + bulan_index // 12
    bulan_baru = bulan_index % 12 + 1
    hari_terakhir = calendar.monthrange(tahun_baru, bulan_baru)[1]
    hari_baru = min(tanggal.day, hari_terakhir)
    return tanggal.replace(year=tahun_baru, month=bulan_baru, day=hari_baru)
