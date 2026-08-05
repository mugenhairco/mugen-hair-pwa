"""email_templates.py — FITUR Email, Verifikasi Email, Lupa Kata Sandi:
template HTML branding Rivoir (platform SaaS), dikirim lewat email_service.py
=============================================================================
SENGAJA branding PLATFORM Rivoir (BUKAN branding tenant penerima) --
email-email ini (verifikasi akun, reset password) adalah komunikasi resmi
PLATFORM dari noreply@rivoirsett.com, konsisten dengan aturan branding
Super Admin/halaman Register yang sudah ditegakkan sebelumnya (lihat
brand.js::refreshPlatformOnly()) -- tenant TIDAK PERNAH melihat email yang
mengaku dari toko lain, dan Rivoir TIDAK PERNAH meniru identitas tenant
mana pun.

Warna aksen (#334155) SAMA PERSIS dengan --accent default (style.css,
tema Terang) supaya konsisten dengan tampilan web -- HTML email TIDAK bisa
membaca CSS custom property, jadi nilainya disalin manual di sini (satu
tempat, dipakai SEMUA template lewat _KERANGKA())."""

_AKSEN = "#334155"
_TEKS_DIM = "#64748b"
_BATAS = "#e2e8f0"


def _kerangka(judul: str, isi_html: str) -> str:
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;overflow:hidden;max-width:480px;width:100%;">
        <tr><td style="background:{_AKSEN};padding:24px 32px;">
          <span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:0.5px;">Rivoir</span>
        </td></tr>
        <tr><td style="padding:32px;">
          <h1 style="margin:0 0 16px;font-size:18px;color:#0f172a;">{judul}</h1>
          {isi_html}
        </td></tr>
        <tr><td style="padding:20px 32px;border-top:1px solid {_BATAS};">
          <p style="margin:0;font-size:12px;color:{_TEKS_DIM};">
            Email ini dikirim otomatis oleh Rivoir, platform manajemen barbershop.
            Jangan balas email ini -- kotak masuk noreply@rivoirsett.com tidak dipantau.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _tombol(teks: str, url: str) -> str:
    return (
        f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
        f'style="display:inline-block;background:{_AKSEN};color:#ffffff;text-decoration:none;'
        f'padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;margin:8px 0 16px;">'
        f'{teks}</a>'
    )


def template_verifikasi_email(nama_penerima: str, link_verifikasi: str, masa_berlaku_jam: int) -> str:
    isi = f"""
      <p style="margin:0 0 16px;font-size:14px;color:#334155;line-height:1.6;">
        Halo {nama_penerima},<br><br>
        Terima kasih telah mendaftar di Rivoir. Klik tombol di bawah ini untuk
        memverifikasi alamat email Anda dan mengaktifkan akun.
      </p>
      {_tombol("Verifikasi Email", link_verifikasi)}
      <p style="margin:0;font-size:13px;color:{_TEKS_DIM};line-height:1.6;">
        Link ini berlaku selama {masa_berlaku_jam} jam. Kalau tombol di atas
        tidak berfungsi, salin dan tempel URL berikut ke browser Anda:<br>
        <span style="word-break:break-all;color:{_AKSEN};">{link_verifikasi}</span>
      </p>
      <p style="margin:16px 0 0;font-size:13px;color:{_TEKS_DIM};">
        Bukan Anda yang mendaftar? Abaikan saja email ini.
      </p>"""
    return _kerangka("Verifikasi email Anda", isi)


def template_reset_password(nama_penerima: str, link_reset: str, masa_berlaku_jam: int) -> str:
    isi = f"""
      <p style="margin:0 0 16px;font-size:14px;color:#334155;line-height:1.6;">
        Halo {nama_penerima},<br><br>
        Kami menerima permintaan untuk mengatur ulang password akun Rivoir Anda.
        Klik tombol di bawah untuk membuat password baru.
      </p>
      {_tombol("Atur Ulang Password", link_reset)}
      <p style="margin:0;font-size:13px;color:{_TEKS_DIM};line-height:1.6;">
        Link ini berlaku selama {masa_berlaku_jam} jam. Kalau tombol di atas
        tidak berfungsi, salin dan tempel URL berikut ke browser Anda:<br>
        <span style="word-break:break-all;color:{_AKSEN};">{link_reset}</span>
      </p>
      <p style="margin:16px 0 0;font-size:13px;color:{_TEKS_DIM};">
        Bukan Anda yang meminta ini? Abaikan saja email ini -- password Anda
        tidak akan berubah.
      </p>"""
    return _kerangka("Atur ulang password Anda", isi)
