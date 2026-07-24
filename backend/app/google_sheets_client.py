"""google_sheets_client.py — TAHAP 12
Klien tipis ke Google Sheets API lewat gspread + google-auth (kedua library
ini sudah ada di requirements.txt sejak Tahap 1, disiapkan untuk tahap ini).
Dipakai HANYA oleh sync_helper.py -- file ini tidak tahu apa-apa soal
transaksi/komisi/bonus/dll, hanya tahu cara mengirim daftar dict ke satu
tab (worksheet) Google Sheets.

Konfigurasi (dua-duanya wajib diisi saat deploy, TIDAK ikut git):
- Environment variable GOOGLE_SHEET_ID       -- ID spreadsheet tujuan
  (bagian di URL: https://docs.google.com/spreadsheets/d/<ID INI>/edit)
- Kredensial service account, SALAH SATU dari:
    - Environment variable GOOGLE_CREDENTIALS_JSON (isi mentah file JSON
      service account, cocok untuk deploy ke Render/dsb tanpa upload file)
    - File backend/app/credentials.json (sama seperti disebut README sejak
      Tahap 1 -- di-gitignore, harus di-copy manual saat deploy)

Kalau salah satu dari dua hal di atas belum diisi, is_configured() akan
False dan sync_helper TIDAK akan mencoba konek sama sekali (dianggap
"belum dikonfigurasi", diperlakukan sama seperti offline: data tetap aman
di SQLite lokal, status sinkron menandai belum tersinkron)."""

import json
import os

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID_ENV = "GOOGLE_SHEET_ID"
CREDENTIALS_ENV = "GOOGLE_CREDENTIALS_JSON"
CREDENTIALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def is_configured() -> bool:
    if not os.environ.get(SPREADSHEET_ID_ENV):
        return False
    return bool(os.environ.get(CREDENTIALS_ENV)) or os.path.exists(CREDENTIALS_PATH)


def _load_credentials_dict() -> dict:
    raw = os.environ.get(CREDENTIALS_ENV)
    if raw:
        return json.loads(raw)
    with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_client() -> gspread.Client:
    creds = Credentials.from_service_account_info(_load_credentials_dict(), scopes=_SCOPES)
    return gspread.authorize(creds)


def _sel(nilai):
    """Google Sheets cell hanya boleh diisi tipe primitif -- list/dict (mis.
    kolom 'items' pada snapshot transaksi) diserialisasi jadi teks JSON."""
    if isinstance(nilai, (dict, list)):
        return json.dumps(nilai, ensure_ascii=False)
    return nilai if nilai is not None else ""


def push_snapshot(entity: str, rows: list) -> None:
    """Timpa PENUH isi satu tab bernama `entity` dengan snapshot terbaru
    (list of dict) dari SQLite lokal. Overwrite penuh (bukan diff per baris)
    supaya baris yang sudah dihapus di lokal otomatis hilang juga dari
    Sheets, tanpa perlu logika hapus terpisah. Kalau spreadsheet/tab belum
    ada, dibuat otomatis (idempotent -- aman dipanggil berkali-kali)."""
    client = _get_client()
    spreadsheet = client.open_by_key(os.environ[SPREADSHEET_ID_ENV])
    try:
        worksheet = spreadsheet.worksheet(entity)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=entity, rows=max(len(rows) + 10, 100), cols=26)

    if not rows:
        worksheet.clear()
        return

    kolom = list(rows[0].keys())
    for r in rows:
        for k in r.keys():
            if k not in kolom:
                kolom.append(k)

    data = [kolom] + [[_sel(r.get(k)) for k in kolom] for r in rows]
    worksheet.clear()
    worksheet.update(range_name="A1", values=data, value_input_option="RAW")
