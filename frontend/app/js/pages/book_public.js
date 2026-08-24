// pages/book_public.js — Halaman PUBLIK "/book" (hash #/book), TANPA LOGIN.
// Dirender LANGSUNG ke #app (bukan lewat MugenRouter.shell()) -- tidak ada
// sidebar/menu, karena ini bukan bagian dari aplikasi internal.
//
// REVISI STRUKTUR WEBSITE CONTENT: halaman ini SEKARANG mengikuti urutan
// section tetap Hero / About / Gallery / Visit Us / Opening Hours / Book
// Appointment / Connect With Us / Footer (watermark developer saja -- lihat
// index.html), dikonsumsi dari /api/website/content (SATU-SATUNYA sumber
// tampilan, lihat website_content.py) + /api/pengaturan/identitas (lewat
// brand.js, HANYA nama/email/logo -- identitas inti) + /api/public/booking/
// pengaturan (Opening Hours -- REUSE data yang sama dipakai slot booking,
// BUKAN sistem jam kedua). SEO meta/Favicon/Branding warna/Splash Screen/
// Footer legal (Privacy Policy/Terms)/CTA sebagai link eksternal SUDAH
// DIHAPUS TOTAL sesuai instruksi -- tidak ada penggantinya di halaman ini.
// REVISI Branding Rivoir: fitur "Background Website" (preset Light/Dark
// custom, upload gambar+opacity) SUDAH DIHAPUS TOTAL -- halaman ini
// sekarang selalu memakai satu background default (Light) yang sama
// seperti sebelumnya, tanpa opsi ganti apa pun (lihat :root[data-
// theme="dark"] .book-public di style.css, yang sudah memaksa palet Light
// terlepas dari tema akun -- itu SATU-SATUNYA sumber warna latar di sini
// sekarang, tidak ada override JS lagi).
//
// Setiap section WAJIB dinamis -- section/elemen yang datanya kosong TIDAK
// PERNAH dirender sama sekali (bukan disembunyikan lewat CSS), supaya tidak
// pernah ada kotak/jarak kosong tersisa di halaman. HANYA tombol Book
// Appointment (satu-satunya di seluruh halaman, di bawah Opening Hours, di
// atas Connect With Us) yang selalu tampil apa pun isi Heading/Subheading-nya.
//
// Wizard booking yang sudah ada (renderWizard) HANYA muncul setelah tombol
// Book Appointment ditekan -- urutan step-nya English, Service SEBELUM
// Date/Time (duration-aware sejak awal). Teks yang datang dari database
// (pesan custom Owner) SENGAJA TIDAK diterjemahkan otomatis.
//
// Data toko yang sensitif (Rating Google, Review pelanggan, Profil barber)
// SENGAJA tidak ditampilkan di landing page, sesuai instruksi -- barber baru
// muncul di dalam wizard booking.
//
// FASPAY SNAP -- Return/Landing Page UNIVERSAL "/book/return" (audit
// lanjutan #5): SATU URL yang sama untuk SELURUH tenant (https://<domain
// frontend>/book/return, TANPA tenant/parameter apa pun) yang didaftarkan
// ke Faspay sebagai Return/Landing Page SNAP Direct Debit/E-Wallet --
// customer diarahkan balik ke sini oleh Faspay/PJP (OVO/DANA/dst) SETELAH
// pembayaran selesai. SENGAJA murni tampilan statis, TIDAK memanggil API
// apa pun (aman dibuka tanpa parameter transaksi/tenant sama sekali,
// TIDAK bergantung bill_no/partnerReferenceNo/query string apa pun) --
// status pembayaran SUNGGUHAN TETAP HANYA ditentukan oleh Payment
// Notification Faspay (https://api.rivoirsett.com, lihat
// routers/snap_advance.py), BUKAN oleh kunjungan ke halaman ini. Route-nya
// SENDIRI sudah tercakup gratis oleh rewrite `/book/*` yang ada di
// render.yaml (destinasi app/index.html) + pathAdalahHalamanBook() di
// router.js (sudah mencocokkan path apa pun di bawah "/book/") -- TIDAK
// ada perubahan render.yaml/router.js yang diperlukan, murni cabang baru
// di dalam render() di bawah. Lihat renderPembayaranKembali().

const PageBookPublic = (() => {
  // Payment Gateway booking (Implementasi Payment Gateway & Riwayat Transaksi
  // Multi-Tenant): script checkout hosted provider dimuat DINAMIS persis
  // begitu customer pilih metode "gateway" -- pola SAMA PERSIS dengan
  // muatSnapJs() di pages/billing.js (checkout SaaS Owner), scope module
  // (bukan per-render) supaya tidak dimuat ulang kalau customer bolak-balik
  // fase dalam satu kunjungan wizard yang sama.
  let _pgwScriptLoadPromise = null;
  function muatPgwCheckoutScript(src, clientKey) {
    if (window.snap) return Promise.resolve();
    if (_pgwScriptLoadPromise) return _pgwScriptLoadPromise;
    _pgwScriptLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.setAttribute("data-client-key", clientKey);
      script.onload = () => resolve();
      script.onerror = () => {
        _pgwScriptLoadPromise = null;
        reject(new Error("Gagal memuat modul pembayaran."));
      };
      document.head.appendChild(script);
    });
    return _pgwScriptLoadPromise;
  }

  // Nama hari/bulan Bahasa Inggris KHUSUS untuk halaman publik ini -- TIDAK
  // mengubah MugenUI.namaBulan/dst (dipakai aplikasi admin internal, tetap
  // Bahasa Indonesia). HARI_KEY tetap kunci Indonesia (kontrak dengan
  // backend, lihat booking_db.py HARI_LIST) -- hanya label tampilannya
  // (LABEL_HARI_EN) yang Inggris.
  const HARI = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const HARI_KEY = ["minggu", "senin", "selasa", "rabu", "kamis", "jumat", "sabtu"]; // index = Date.getDay()
  const URUTAN_HARI_TAMPIL = ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"]; // Mon..Sun untuk Opening Hours
  const LABEL_HARI_EN = {
    senin: "Monday", selasa: "Tuesday", rabu: "Wednesday", kamis: "Thursday",
    jumat: "Friday", sabtu: "Saturday", minggu: "Sunday",
  };
  const BULAN = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];

  function todayIso() {
    // BUGFIX (audit): lihat catatan lengkap di MugenUI.isoHariIniWib().
    return MugenUI.isoHariIniWib();
  }

  function tambahHari(iso, n) {
    // BUGFIX (audit): pola lama (new Date(iso+"T00:00:00") lalu
    // toISOString()) mengonversi balik ke UTC -- untuk browser di zona
    // waktu POSITIF (termasuk WIB, UTC+7, audiens utama halaman booking
    // publik ini), tengah malam lokal jatuh ke SORE HARI SEBELUMNYA dalam
    // UTC, jadi tanggal hasilnya mundur satu hari. MugenUI.tambahHariWib()
    // murni aritmatika kalender lokal, tidak konversi UTC sama sekali.
    return MugenUI.tambahHariWib(iso, n);
  }

  function fieldRow(label, value, tebal) {
    return MugenUI.el("div", { class: "book-field-row" + (tebal ? " book-field-row-total" : "") }, [
      MugenUI.el("span", { class: "book-field-label" }, label),
      MugenUI.el("span", { class: "book-field-colon" }, ":"),
      MugenUI.el("span", { class: "book-field-value" }, value),
    ]);
  }

  // Konversi nomor WhatsApp ke format internasional untuk link wa.me --
  // duplikasi kecil dari pola yang sama di booking.js (module berbeda,
  // konsisten dengan gaya codebase: helper kecil per-modul, bukan
  // cross-import lintas closure).
  function nomorKeFormatInternasional(nomorMentah) {
    const digits = String(nomorMentah || "").replace(/[^\d+]/g, "");
    if (digits.startsWith("+62")) return digits.slice(1);
    if (digits.startsWith("62")) return digits;
    if (digits.startsWith("0")) return "62" + digits.slice(1);
    return digits.replace(/^\+/, "");
  }

  // REVISI UI/UX Premium: step tracker (dot + garis penghubung berselang-
  // seling dalam SATU baris flex, TANPA positioning absolut) menggantikan
  // pagination dots polos -- dot yang SUDAH dilewati tampil "completed"
  // (centang kecil), dot AKTIF berdenyut (glow ring), garis di antara dot
  // yang sudah dilewati ikut terisi warna aksen. Signature/nama fungsi
  // TIDAK berubah (dipanggil persis sama di semua step), murni presentasi.
  function paginationDots(langkahAktif, totalLangkah) {
    const wrap = MugenUI.el("div", { class: "book-step-track" });
    for (let i = 1; i <= totalLangkah; i++) {
      const status = i < langkahAktif ? " completed" : i === langkahAktif ? " active" : "";
      wrap.appendChild(MugenUI.el("span", { class: "book-dot-page" + status }));
      if (i < totalLangkah) {
        wrap.appendChild(MugenUI.el("span", { class: "book-step-line" + (i < langkahAktif ? " filled" : "") }));
      }
    }
    return wrap;
  }

  // REVISI UI/UX Premium: empty state ringan (ikon bulat + teks + aksi
  // opsional) -- menggantikan `<div class="subtitle">` polos untuk kondisi
  // "belum ada data" (barber/slot/metode pembayaran/channel kosong), TANPA
  // mengubah KAPAN kondisi ini muncul (logika pengecekan tetap sama persis
  // di masing-masing pemanggil, ini murni tampilannya).
  function kosongState(ikon, teks, tombolAksi) {
    const el = MugenUI.el("div", { class: "book-empty" }, [
      MugenUI.el("div", { class: "book-empty-icon" }, ikon),
      MugenUI.el("div", {}, teks),
    ]);
    if (tombolAksi) el.appendChild(MugenUI.el("div", { class: "book-empty-action" }, tombolAksi));
    return el;
  }

  // REVISI UI/UX Premium: kartu error ringkas + tombol "Try Again" yang
  // memanggil ULANG fungsi render yang sama persis (retry murni re-render,
  // TIDAK ADA endpoint/logika baru) -- dipakai di ketiga titik try/catch
  // yang sebelumnya hanya menampilkan errorState() tanpa cara memulihkan
  // diri selain refresh manual browser.
  function errorStateRetry(pesan, onRetry) {
    const btn = MugenUI.el("button", { class: "btn-primary", type: "button", style: "margin-top:14px;" }, "Try Again");
    btn.addEventListener("click", onRetry);
    return MugenUI.el("div", { class: "card", style: "text-align:center;" }, [
      MugenUI.errorState(pesan),
      btn,
    ]);
  }

  // REVISI UI/UX Premium: reveal-on-scroll ringan (IntersectionObserver,
  // sekali per elemen, satu observer dipakai bersama) -- pola yang SAMA
  // dipakai Landing Page SaaS (lp-reveal), versi book-scoped di sini murni
  // presentasi, TIDAK menyentuh urutan/isi section yang sudah ditentukan
  // dinamis oleh data (lihat renderLanding()).
  let bookRevealObserver = null;
  function bookRevealObserve(elements) {
    if (!elements.length) return;
    if (!("IntersectionObserver" in window)) {
      elements.forEach((el) => el.classList.add("book-in-view"));
      return;
    }
    if (!bookRevealObserver) {
      bookRevealObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("book-in-view");
          bookRevealObserver.unobserve(entry.target);
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -30px 0px" });
    }
    elements.forEach((el) => bookRevealObserver.observe(el));
  }

  // REVISI UI/UX Premium: kalender .ics (RFC 5545) dibuat MURNI di sisi
  // klien dari data booking yang SUDAH ada di layar (tanggal/jam_mulai/
  // jam_selesai/nama_barber/daftar_service) -- TIDAK ADA endpoint/field
  // baru dari backend. Tombol "Add to Calendar" pada layar Appointment
  // Confirmed mengunduh file ini lewat pola blob yang sama seperti
  // unduhGambar() di atas.
  function buatIcs(r, namaBarbershop) {
    const pad = (n) => String(n).padStart(2, "0");
    const [th, bl, tg] = [r.tanggal.slice(0, 4), r.tanggal.slice(5, 7), r.tanggal.slice(8, 10)];
    const [jm, mm] = r.jam_mulai.split(":");
    const [js, ms] = (r.jam_selesai || r.jam_mulai).split(":");
    const dtStart = `${th}${bl}${tg}T${pad(jm)}${pad(mm)}00`;
    const dtEnd = `${th}${bl}${tg}T${pad(js)}${pad(ms)}00`;
    const stamp = new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
    const esc = (s) => String(s || "").replace(/[\\;,]/g, (m) => "\\" + m).replace(/\n/g, "\\n");
    const lines = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Rivoir//Booking//EN",
      "BEGIN:VEVENT",
      `UID:booking-${r.id || Date.now()}@rivoir`,
      `DTSTAMP:${stamp}`,
      `DTSTART:${dtStart}`,
      `DTEND:${dtEnd}`,
      `SUMMARY:${esc((namaBarbershop || "Rivoir") + " — " + (r.daftar_service || "Appointment"))}`,
      `DESCRIPTION:${esc(`Barber: ${r.nama_barber || "-"}\\nService: ${r.daftar_service || "-"}`)}`,
      "END:VEVENT", "END:VCALENDAR",
    ];
    return lines.join("\r\n");
  }

  function unduhIcs(r, namaBarbershop) {
    const blob = new Blob([buatIcs(r, namaBarbershop)], { type: "text/calendar;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (namaBarbershop || "Rivoir").replace(/[^a-zA-Z0-9]+/g, "-") + "-Appointment.ics";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // REVISI: tombol "Download QRIS" -- ambil EKSTENSI file asli dari query
  // string "?v=" pada qris_url (lihat booking_db.py: qris_url selalu
  // berformat "/api/public/booking/qris?v=<nama_file_asli>"), lalu susun
  // nama file unduhan yang rapi berbasis nama barbershop (BUKAN hardcode
  // "MUGEN Hair Co." di source -- lihat brand.js/Tahap 10 -- supaya tetap
  // benar walau nama barbershop diganti lewat Setting), contoh hasil:
  // "MUGEN-Hair-Co-QRIS.png".
  function namaFileQris(qrisUrl, namaBarbershop) {
    const q = (qrisUrl || "").split("?")[1] || "";
    const namaAsli = new URLSearchParams(q).get("v") || "qris.png";
    const ext = (namaAsli.split(".").pop() || "png").toLowerCase();
    const dasar = (namaBarbershop || "QRIS").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "QRIS";
    return `${dasar}-QRIS.${ext}`;
  }

  // Ikon download (SVG inline, tanpa dependency CDN) untuk tombol Download QRIS.
  const IKON_DOWNLOAD_SVG =
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12"/>' +
    '<path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>';

  // Ikon Connect With Us (SVG inline monokrom, ikut warna teks/aksen lewat
  // currentColor -- tidak butuh file/CDN apa pun, konsisten dengan ikon
  // Download QRIS di atas). Instagram/TikTok/WhatsApp SAJA sesuai instruksi.
  const IKON_INSTAGRAM_SVG =
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5"/>' +
    '<circle cx="12" cy="12" r="4"/><circle cx="17.4" cy="6.6" r="0.9" fill="currentColor" stroke="none"/></svg>';
  const IKON_TIKTOK_SVG =
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16.6 5.82c-.9-.98-1.4-2.24-1.4-3.57h-3.02v13.44a3.03 3.03 0 1 1-2.14-2.9V9.68a6.04 6.04 0 1 0 5.16 5.98V9.4a8.7 8.7 0 0 0 5.1 1.63V8.02a5.6 5.6 0 0 1-3.7-2.2Z"/></svg>';
  const IKON_WHATSAPP_SVG =
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.39 1.26 4.81L2 22l5.42-1.35a9.87 9.87 0 0 0 4.62 1.16h.01c5.46 0 9.91-4.45 9.91-9.91C21.96 6.45 17.5 2 12.04 2Zm5.63 14.02c-.24.67-1.4 1.28-1.93 1.35-.5.07-1.12.1-1.8-.11-.42-.13-.96-.31-1.65-.6-2.9-1.25-4.79-4.16-4.94-4.35-.14-.19-1.18-1.57-1.18-3 0-1.43.75-2.13 1.02-2.42.27-.29.58-.36.78-.36.2 0 .39 0 .56.01.18.01.42-.07.65.5.24.58.82 2 .89 2.14.07.14.11.31.02.5-.09.19-.14.31-.28.48-.14.17-.29.37-.42.5-.14.14-.28.29-.12.57.16.28.71 1.17 1.53 1.9 1.05.94 1.94 1.23 2.22 1.37.28.14.44.12.6-.07.16-.19.68-.79.86-1.06.18-.27.36-.22.6-.13.24.09 1.52.72 1.78.85.26.13.43.2.5.31.07.11.07.63-.17 1.3Z"/></svg>';

  // Efek ripple ringan (murni CSS animasi + JS posisi klik) saat tombol
  // Download QRIS ditekan, supaya terasa modern tanpa perlu library apa pun.
  function tambahkanEfekRipple(tombol) {
    tombol.addEventListener("click", (e) => {
      const rect = tombol.getBoundingClientRect();
      const ukuran = Math.max(rect.width, rect.height);
      const ripple = document.createElement("span");
      ripple.className = "book-ripple";
      ripple.style.width = ripple.style.height = ukuran + "px";
      const x = (e.clientX || rect.left + rect.width / 2) - rect.left - ukuran / 2;
      const y = (e.clientY || rect.top + rect.height / 2) - rect.top - ukuran / 2;
      ripple.style.left = x + "px";
      ripple.style.top = y + "px";
      tombol.appendChild(ripple);
      ripple.addEventListener("animationend", () => ripple.remove());
    });
  }

  // Unduh gambar lewat fetch->blob->anchor[download] supaya file benar-benar
  // TERSIMPAN (bukan cuma membuka gambar di tab baru) walau URL-nya beda
  // origin (frontend Render static vs backend Render API) -- atribut
  // download pada <a> TIDAK dihormati browser untuk URL cross-origin
  // langsung, tapi SELALU dihormati untuk blob: URL (dianggap same-origin).
  // Kalau fetch/blob gagal (offline, browser lawas, dsb.), fallback buka
  // gambar di tab baru supaya customer tetap bisa simpan manual (tekan lama
  // di HP / klik kanan "Simpan Gambar" di desktop).
  async function unduhGambar(url, namaFile) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("gagal mengambil gambar");
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = namaFile;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch (e) {
      window.open(url, "_blank");
    }
  }

  // Gambar dengan pola "sembunyikan sampai terbukti berhasil dimuat" (lihat
  // brand.js) -- dipakai berulang di landing page (Hero/About/Gallery),
  // supaya tidak pernah tampil sebagai ikon broken-image.
  function gambarAman(url, attrs) {
    const img = MugenUI.el("img", { ...attrs, style: (attrs.style || "") + "display:none;" });
    img.onload = () => { img.style.display = ""; };
    img.onerror = () => { img.style.display = "none"; img.removeAttribute("src"); };
    img.src = url;
    return img;
  }

  // FASPAY SNAP -- deteksi Return/Landing Page universal "/book/return"
  // (lihat catatan modul di atas). Cocok path ASLI ("/book/return",
  // "/app/book/return", boleh diikuti "/" atau query string apa pun) MAUPUN
  // varian hash ("#/book/return") -- SENGAJA startsWith, BUKAN exact match,
  // supaya trailing slash atau parameter apa pun yang mungkin ditambahkan
  // Faspay/PJP saat redirect TIDAK PERNAH membuat halaman ini gagal cocok
  // (instruksi eksplisit: halaman ini WAJIB aman dibuka tanpa parameter
  // transaksi apa pun, TIDAK boleh bergantung satu pun dari parameter itu).
  function isHalamanReturnPembayaran() {
    const p = location.pathname;
    if (p === "/book/return" || p.startsWith("/book/return/") || p.startsWith("/book/return?") ||
        p === "/app/book/return" || p.startsWith("/app/book/return/") || p.startsWith("/app/book/return?")) {
      return true;
    }
    const h = location.hash || "";
    return h === "#/book/return" || h.startsWith("#/book/return/") || h.startsWith("#/book/return?");
  }

  // FASPAY SNAP -- Return/Landing Page universal (lihat catatan modul).
  // MURNI statis, TIDAK ADA panggilan API sama sekali -- SENGAJA, supaya
  // halaman ini 100% aman dibuka tanpa identifier transaksi/tenant apa pun
  // (instruksi eksplisit #8), dan supaya visitnya sendiri TIDAK PERNAH bisa
  // disalahartikan sebagai penentu status pembayaran (yang TETAP HANYA
  // datang dari Payment Notification Faspay -- lihat snap_webhook.py).
  // TIDAK menyentuh flow subscription SaaS (scope KHUSUS booking tenant,
  // instruksi eksplisit #11) -- billing.js tidak diubah/disentuh di sini.
  function renderPembayaranKembali(root) {
    if (typeof MugenTheme !== "undefined") MugenTheme.forceLight();
    document.body.classList.add("book-public-active");
    const page = MugenUI.el("div", { class: "book-public book-landing" });
    root.appendChild(page);
    const hero = MugenUI.el("section", { class: "book-hero" });
    const heroContent = MugenUI.el("div", { class: "book-hero-content" });
    heroContent.appendChild(MugenUI.el("h1", {}, "Pembayaran Sedang Diproses"));
    heroContent.appendChild(MugenUI.el("div", { class: "book-hero-tagline" },
      "Kami sedang memverifikasi pembayaran Anda. Status booking akan diperbarui secara otomatis begitu pembayaran dikonfirmasi -- Anda tidak perlu melakukan apa pun lagi di halaman ini."));
    hero.appendChild(heroContent);
    page.appendChild(hero);
  }

  async function render(root) {
    root.innerHTML = "";
    if (isHalamanReturnPembayaran()) { renderPembayaranKembali(root); return; }
    // REVISI UI/UX (Dark Mode): lapis pertahanan KEDUA di sisi JS -- router.js
    // sudah memanggil MugenTheme.forceLight() sebelum PageBookPublic.render()
    // dipanggil, tapi dipanggil ulang di sini juga supaya halaman ini tetap
    // benar walau suatu saat dipanggil dari jalur lain.
    if (typeof MugenTheme !== "undefined") MugenTheme.forceLight();
    // REVISI STRUKTUR WEBSITE CONTENT: watermark developer BESAR (dev-
    // watermark-bg) disembunyikan KHUSUS selama di /book -- lapis
    // pertahanan KEDUA yang sama seperti forceLight() di atas (router.js
    // sudah menandai body.book-public-active lebih dulu). Watermark KECIL
    // footer (dev-watermark-footer) TIDAK disentuh sama sekali di mana pun.
    document.body.classList.add("book-public-active");

    // FONDASI Multi-Tenant Phase 3: dicek PALING AWAL, SEBELUM endpoint
    // publik lain mana pun (yang JUSTRU akan ditolak 403 oleh
    // resolve_tenant_publik_aktif kalau statusnya diblokir, lihat
    // routers/booking.py) -- supaya customer langsung melihat halaman
    // "tidak tersedia" yang rapi, bukan error mentah dari Promise.all()
    // gagal di renderLanding(). Endpoint ini SENDIRI selalu bisa diakses
    // (resolve_tenant_publik polos, bukan varian _aktif).
    try {
      const { tersedia } = await MugenApi.get("/api/public/booking/subscription-status");
      if (!tersedia) {
        renderTidakTersedia(root);
        return;
      }
    } catch (e) {
      // FITUR URL Booking Publik per Tenant (item 9 spesifikasi): 404 di
      // sini SATU-SATUNYA berarti resolve_tenant_publik() (auth.py) gagal
      // total menemukan tenant apa pun (slug MAUPUN booking_slug tidak
      // cocok) -- tampilkan halaman ramah "Booking page not found"
      // (Bahasa Inggris, SESUAI teks spesifikasi persis), BUKAN error
      // server mentah. Status LAIN (0/offline, 5xx, dst): lanjut ke
      // renderLanding() seperti biasa -- endpoint publik lain di sana
      // sudah punya penanganan error sendiri (lihat catch block
      // renderLanding()), jangan blokir halaman hanya karena SATU
      // pengecekan awal gagal karena network, bukan karena memang tidak
      // ditemukan/diblokir Super Admin.
      if (e && e.status === 404) {
        renderBookingPageNotFound(root);
        return;
      }
    }
    renderLanding(root);
  }

  // FITUR URL Booking Publik per Tenant (item 9 spesifikasi): halaman
  // "Booking page not found" -- dipakai KHUSUS saat tenant/booking_slug-nya
  // sendiri tidak ditemukan (404), BEDA dari renderTidakTersedia() (tenant
  // DITEMUKAN tapi subscription-nya tidak aktif -- pesan & penyebabnya
  // beda total). Teks Bahasa Inggris SESUAI spesifikasi persis, konsisten
  // dengan halaman ini yang sudah sepenuhnya Bahasa Inggris.
  function renderBookingPageNotFound(root) {
    const page = MugenUI.el("div", { class: "book-public book-landing" });
    root.appendChild(page);
    const hero = MugenUI.el("section", { class: "book-hero" });
    const heroContent = MugenUI.el("div", { class: "book-hero-content" });
    heroContent.appendChild(MugenUI.el("h1", {}, "Booking page not found"));
    heroContent.appendChild(MugenUI.el("div", { class: "book-hero-tagline" },
      "This booking link is invalid or no longer available."));
    hero.appendChild(heroContent);
    page.appendChild(hero);
  }

  // FONDASI Multi-Tenant Phase 3: halaman "tidak tersedia" saat subscription
  // tenant Expired/Suspended/Cancelled -- TIDAK memanggil endpoint publik
  // lain mana pun (semuanya akan ditolak 403), murni tampilan statis.
  function renderTidakTersedia(root) {
    const page = MugenUI.el("div", { class: "book-public book-landing" });
    root.appendChild(page);
    const hero = MugenUI.el("section", { class: "book-hero" });
    const heroContent = MugenUI.el("div", { class: "book-hero-content" });
    heroContent.appendChild(MugenUI.el("h1", {}, "Booking Tidak Tersedia"));
    heroContent.appendChild(MugenUI.el("div", { class: "book-hero-tagline" },
      "Halaman booking toko ini sedang tidak tersedia. Hubungi pemilik toko untuk informasi lebih lanjut."));
    hero.appendChild(heroContent);
    page.appendChild(hero);
  }

  // ================= LANDING PAGE (website resmi) =================
  async function renderLanding(root) {
    const page = MugenUI.el("div", { class: "book-public book-landing" });
    root.appendChild(page);
    page.appendChild(MugenUI.skeleton("card", { lines: 3 })); // skeleton selagi konten landing dimuat

    let content, gallery, pengaturan, identitas;
    try {
      [content, gallery, pengaturan] = await Promise.all([
        MugenApi.get("/api/website/content"),
        MugenApi.get("/api/website/gallery"),
        MugenApi.get("/api/public/booking/pengaturan"),
        MugenBrand.refresh(),
      ]);
      identitas = MugenBrand.get();
    } catch (e) {
      page.innerHTML = "";
      page.appendChild(errorStateRetry("Failed to load this page: " + e.message, () => { root.innerHTML = ""; renderLanding(root); }));
      return;
    }
    page.innerHTML = "";

    function bukaWizard() {
      root.innerHTML = "";
      renderWizard(root);
    }

    // ---- Hero -- hanya salah satu (Gambar ATAU Video) sesuai hero_tipe,
    // area media disembunyikan total kalau yang dipilih belum diisi. Tidak
    // ada lagi tombol CTA di sini -- SATU-SATUNYA tombol Book Appointment
    // ada di section tersendiri di bawah (lihat instruksi #7). ----
    const hero = MugenUI.el("section", { class: "book-hero" });
    let heroMediaEl = null;
    if (content.hero_tipe === "video" && content.hero_video_url) {
      heroMediaEl = MugenUI.el("video", {
        src: MUGEN_API_BASE + content.hero_video_url,
        autoplay: "autoplay", muted: "muted", loop: "loop", playsinline: "playsinline",
      });
    } else if (content.hero_tipe === "image" && content.hero_image_url) {
      heroMediaEl = gambarAman(MUGEN_API_BASE + content.hero_image_url, { alt: "Hero", class: "book-hero-img" });
    }
    if (heroMediaEl) hero.appendChild(MugenUI.el("div", { class: "book-hero-media" }, heroMediaEl));
    const heroContent = MugenUI.el("div", { class: "book-hero-content" });
    if (identitas.logo_url) {
      heroContent.appendChild(gambarAman(MUGEN_API_BASE + identitas.logo_url, { alt: "Logo", class: "book-hero-logo" }));
    }
    if (identitas.nama_barbershop) heroContent.appendChild(MugenUI.el("h1", {}, identitas.nama_barbershop));
    if (content.tagline) heroContent.appendChild(MugenUI.el("div", { class: "book-hero-tagline" }, content.tagline));
    if (heroContent.children.length) hero.appendChild(heroContent);
    if (heroMediaEl || heroContent.children.length) page.appendChild(hero);

    // ---- About -- section (dan judulnya) hanya tampil kalau ADA isinya. ----
    if (content.about_judul || content.about_deskripsi || content.about_foto_url) {
      const about = MugenUI.el("section", { class: "book-section book-about book-reveal" });
      if (content.about_foto_url) {
        about.appendChild(gambarAman(MUGEN_API_BASE + content.about_foto_url, { alt: "About", class: "book-about-foto" }));
      }
      const aboutText = MugenUI.el("div", { class: "book-about-text" });
      if (content.about_judul) aboutText.appendChild(MugenUI.el("h2", {}, content.about_judul));
      if (content.about_deskripsi) aboutText.appendChild(MugenUI.el("p", {}, content.about_deskripsi));
      if (aboutText.children.length) about.appendChild(aboutText);
      page.appendChild(about);
    }

    // ---- Gallery ----
    if (gallery.length) {
      const gallerySec = MugenUI.el("section", { class: "book-section book-gallery book-reveal" });
      gallerySec.appendChild(MugenUI.el("h2", {}, "Our Work"));
      const slider = MugenUI.el("div", { class: "book-gallery-slider" });
      for (const foto of gallery) {
        slider.appendChild(
          foto.tipe === "video"
            ? MugenUI.el("video", {
                src: MUGEN_API_BASE + foto.foto_url, class: "book-gallery-slide",
                autoplay: "autoplay", muted: "muted", loop: "loop", playsinline: "playsinline",
              })
            : MugenUI.el("img", {
                src: MUGEN_API_BASE + foto.foto_url, alt: "Gallery", loading: "lazy", class: "book-gallery-slide",
              }),
        );
      }
      gallerySec.appendChild(slider);
      page.appendChild(gallerySec);
    }

    // ---- Visit Us -- HANYA peta/alamat/link (Opening Hours sekarang
    // section tersendiri di bawah, TIDAK lagi digabung ke sini). ----
    if (content.visit_maps_embed_url || content.alamat || content.visit_maps_link) {
      const visit = MugenUI.el("section", { class: "book-section book-visit book-reveal" });
      visit.appendChild(MugenUI.el("h2", {}, "Visit Us"));
      if (content.visit_maps_embed_url) {
        visit.appendChild(MugenUI.el("iframe", {
          src: content.visit_maps_embed_url, class: "book-maps-embed", loading: "lazy",
          referrerpolicy: "no-referrer-when-downgrade", allowfullscreen: "allowfullscreen",
        }));
      }
      if (content.alamat) visit.appendChild(MugenUI.el("div", { class: "book-visit-alamat" }, content.alamat));
      if (content.visit_maps_link) {
        visit.appendChild(MugenUI.el("a", {
          href: content.visit_maps_link, target: "_blank", rel: "noopener noreferrer", class: "book-maps-link",
        }, "Open in Google Maps"));
      }
      page.appendChild(visit);
    }

    // ---- Opening Hours -- section tersendiri (bukan lagi bagian dari
    // Visit Us), tetap SATU sumber data yang sama dengan slot booking
    // (booking_db.py, tab Operating Hours) -- tidak ada input terpisah. ----
    const hariAktif = pengaturan.hari_operasional || [];
    if (hariAktif.length) {
      const aktifTerurut = URUTAN_HARI_TAMPIL.filter((h) => hariAktif.includes(h));
      const liburTerurut = URUTAN_HARI_TAMPIL.filter((h) => !hariAktif.includes(h));
      const hours = MugenUI.el("section", { class: "book-section book-hours book-reveal" });
      hours.appendChild(MugenUI.el("h2", {}, "Opening Hours"));
      hours.appendChild(MugenUI.el("div", {},
        `${aktifTerurut.map((h) => LABEL_HARI_EN[h]).join(", ")}: ${pengaturan.jam_buka} – ${pengaturan.jam_tutup}`));
      if (liburTerurut.length) {
        hours.appendChild(MugenUI.el("div", { class: "subtitle" },
          `Closed: ${liburTerurut.map((h) => LABEL_HARI_EN[h]).join(", ")}`));
      }
      page.appendChild(hours);
    }

    // ---- Book Appointment -- SATU-SATUNYA tombol booking di seluruh
    // halaman, di bawah Opening Hours & di atas Connect With Us. Heading/
    // Subheading boleh kosong (layout menyesuaikan tanpa jarak kosong),
    // TAPI tombolnya SELALU tampil apa pun isinya, dan SELALU menuju
        // halaman booking (bukan link yang bisa diatur Owner). ----
    const bookCta = MugenUI.el("section", { class: "book-section book-cta book-reveal" });
    if (content.booking_cta_judul) bookCta.appendChild(MugenUI.el("h2", {}, content.booking_cta_judul));
    if (content.booking_cta_subjudul) bookCta.appendChild(MugenUI.el("div", { class: "subtitle" }, content.booking_cta_subjudul));
    const btnCta = MugenUI.el("button", { class: "btn-primary book-cta-btn", type: "button" },
      content.booking_cta_tombol_teks || "Book Appointment");
    btnCta.addEventListener("click", bukaWizard);
    tambahkanEfekRipple(btnCta);
    bookCta.appendChild(btnCta);
    page.appendChild(bookCta);

    // ---- Connect With Us -- section kecil (heading lebih kecil, layout
    // horizontal), HANYA Instagram/TikTok/WhatsApp, ikon HANYA tampil kalau
    // link-nya terisi, section-nya sendiri disembunyikan total kalau
    // semuanya kosong. ----
    const social = [];
    if (content.instagram) social.push({ label: "Instagram", href: content.instagram, svg: IKON_INSTAGRAM_SVG });
    if (content.tiktok) social.push({ label: "TikTok", href: content.tiktok, svg: IKON_TIKTOK_SVG });
    if (content.whatsapp) social.push({ label: "WhatsApp", href: `https://wa.me/${nomorKeFormatInternasional(content.whatsapp)}`, svg: IKON_WHATSAPP_SVG });
    if (social.length) {
      const connect = MugenUI.el("section", { class: "book-section book-connect book-reveal" });
      connect.appendChild(MugenUI.el("h2", {}, "Connect With Us"));
      const row = MugenUI.el("div", { class: "book-connect-row" });
      for (const s of social) {
        row.appendChild(MugenUI.el("a", {
          href: s.href, target: "_blank", rel: "noopener noreferrer", class: "book-connect-link",
          "aria-label": s.label, title: s.label, html: s.svg,
        }));
      }
      connect.appendChild(row);
      page.appendChild(connect);
    }

    // ---- Footer -- TIDAK ada lagi konten CMS (copyright/pesan/Privacy
    // Policy/Terms, semua sudah dihapus total sesuai instruksi). Kredit
    // developer sudah ditangani GLOBAL lewat .dev-watermark-footer
    // (index.html, tampil di semua halaman termasuk ini) -- tidak perlu
    // elemen footer tambahan apa pun di sini.

    // REVISI UI/UX Premium: reveal-on-scroll untuk section landing di atas
    // (About/Gallery/Visit/Hours/Book Appointment/Connect) -- dipanggil
    // TERAKHIR, setelah SEMUA section (yang datanya ada) sudah ter-append,
    // supaya observer melihat posisi akhir elemen yang sebenarnya.
    bookRevealObserve(page.querySelectorAll(".book-reveal"));
  }

  // ================= WIZARD BOOKING =================
  async function renderWizard(root) {
    if (typeof MugenTheme !== "undefined") MugenTheme.forceLight();
    document.body.classList.add("book-public-active");
    const page = MugenUI.el("div", { class: "book-public book-wizard-enter" });
    root.appendChild(page);

    const wizardHeader = MugenUI.el("div", { class: "book-wizard-header" });
    page.appendChild(wizardHeader);

    const bodyViewport = MugenUI.el("div", { class: "book-body-viewport" });
    let body = MugenUI.el("div", { class: "book-body" });
    bodyViewport.appendChild(body);
    page.appendChild(bodyViewport);
    body.appendChild(MugenUI.skeleton("card", { lines: 3 })); // skeleton selagi barbers/services/pengaturan dimuat

    // ---- state ----
    let step = 1;
    const TOTAL_STEP = 6; // Choose Barber, Choose Service, Select Date, Select Time, Your Details, Payment
    let pengaturan = null, barbers = [], services = [];
    let calendarShown = new Date(); // bulan yang lagi ditampilkan di kalender
    const state = {
      barberId: null, barberNama: "",
      tanggal: null,
      jam: null,
      serviceIds: [],
      nama: "", whatsapp: "",
      metode: null,
      // Migrasi Faspay SNAP Advance: sub-pilihan channel ("va"/"qris") saat
      // metode "gateway" dipilih -- lihat renderFaseMetode()/buatPayloadBooking().
      channel: null,
    };

    try {
      [pengaturan, barbers, services] = await Promise.all([
        MugenApi.get("/api/public/booking/pengaturan"),
        MugenApi.get("/api/public/booking/barbers"),
        MugenApi.get("/api/public/booking/services"),
        MugenBrand.refresh(),
      ]);
    } catch (e) {
      body.innerHTML = ""; // buang skeleton sebelum tampilkan error
      body.appendChild(errorStateRetry("Failed to load the booking form: " + e.message, () => { root.innerHTML = ""; renderWizard(root); }));
      return;
    }

    // Feature Gating "booking_online": paket tenant ini tidak menyertakan
    // fitur ini -- endpoint /pengaturan sengaja membalas payload PENDEK
    // {"booking_online": false} (lihat routers/booking.py::public_pengaturan),
    // tampilkan pesan ramah alih-alih lanjut ke Step 1 (Choose Barber) yang
    // datanya sendiri sudah tidak lengkap (barbers/services tetap
    // dipanggil di Promise.all di atas, tapi hasilnya tidak dipakai lagi).
    if (pengaturan.booking_online === false) {
      body.innerHTML = ""; // buang skeleton sebelum tampilkan pesan
      body.appendChild(MugenUI.el("div", { class: "card" }, "Booking online belum tersedia untuk toko ini."));
      return;
    }

    const identitas = MugenBrand.get();

    // Header wizard SENGAJA ringkas (logo/nama kecil + link kembali ke
    // Beranda) -- Hero besar sudah ditampilkan di landing page, tidak perlu
    // diulang di sini.
    wizardHeader.innerHTML = "";
    const wizardBrandRow = MugenUI.el("div", { class: "book-wizard-brand" });
    if (identitas.logo_url) {
      wizardBrandRow.appendChild(gambarAman(MUGEN_API_BASE + identitas.logo_url, { alt: "Logo", class: "book-wizard-logo" }));
    }
    wizardBrandRow.appendChild(MugenUI.el("span", {}, identitas.nama_barbershop || "Rivoir"));
    wizardHeader.appendChild(wizardBrandRow);

    // ---- animasi perpindahan step: SAMA PERSIS dengan transisi antar menu
    // aplikasi (fade-in opacity murni, 300ms, lihat mugen-content-fade-in di
    // style.css) -- bukan animasi baru. router.js memicu animasi itu dengan
    // selalu membuat <main class="content"> BARU tiap navigasi (shell()),
    // jadi di sini dipakai teknik yang SAMA: `body` dibuat ulang (bukan
    // innerHTML="") tiap ganti step supaya kelas .book-step-fade-in
    // ter-trigger otomatis oleh browser. transitioning=true selama animasi
    // berjalan supaya klik ganda/step lain tidak nyelonong di tengah jalan.
    let transitioning = false;
    const ANIM_MS = 300;

    function prefersReducedMotion() {
      return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }

    // ---- riwayat browser: tiap masuk step 1-6 (SEBELUM booking benar-benar
    // dikirim ke server, lihat renderPayment()) push satu history state,
    // supaya tombol Back Android/Swipe Back iPhone/Browser Back bisa mundur
    // SATU step demi step (transisi sama seperti tombol Change di layar,
    // TIDAK reload/rerender halaman, state booking tetap tersimpan) sampai
    // akhirnya keluar wizard kembali ke landing page. SENGAJA TIDAK push
    // state untuk step 7/fase pembayaran -- booking sudah terkirim ke server
    // di titik itu, jadi Back dari sana cukup kembali ke Ringkasan Booking
    // (step 6) tanpa mengubah alur pengiriman booking itu sendiri.
    function pushHistoryStep(n) {
      history.pushState({ mugenBookStep: n }, "");
    }

    function onPopState(e) {
      // SENGAJA TIDAK menjaga `transitioning` di sini (beda dari goto(),
      // yang memang menjaganya untuk debounce klik ganda pada tombol di
      // layar) -- tombol Back Android/Swipe Back iPhone/Browser Back adalah
      // aksi OS yang browser SUDAH memprosesnya (history sudah berpindah),
      // jadi event ini TIDAK BOLEH diabaikan sekalipun sedang di tengah
      // animasi step sebelumnya (kalau diabaikan, tombol Back terasa
      // "tidak berfungsi" sampai ditekan lagi) -- renderAll()/
      // gantiBodyDenganFade() aman dipanggil susulan begitu (murni ganti
      // elemen `body`, tidak ada state yang rusak kalau dipanggil dua kali
      // berdekatan).
      const st = e.state;
      if (st && typeof st.mugenBookStep === "number") {
        if (st.mugenBookStep === step) return;
        step = st.mugenBookStep;
        renderAll("mundur");
      } else {
        window.removeEventListener("popstate", onPopState);
        root.innerHTML = "";
        render(root);
      }
    }
    window.addEventListener("popstate", onPopState);

    function goto(n) {
      if (transitioning || n === step) return;
      const arah = n > step ? "maju" : "mundur";
      step = n;
      if (n <= 6) pushHistoryStep(n);
      renderAll(arah);
    }

    function renderStepBody() {
      if (step === 1) renderChooseBarber();
      else if (step === 2) renderChooseService();
      else if (step === 3) renderSelectDate();
      else if (step === 4) renderSelectTime();
      else if (step === 5) renderYourDetails();
      else if (step === 6) renderPayment();
      else if (step === 7) renderConfirmed();
    }

    function renderAll(arah) {
      if (!arah || prefersReducedMotion()) {
        body.innerHTML = "";
        renderStepBody();
      } else {
        gantiBodyDenganFade();
      }
      window.scrollTo(0, 0);
    }

    // Body DIBUAT ULANG (bukan innerHTML="") -- elemen baru otomatis
    // ter-fade-in oleh CSS (persis mekanisme .content di router.js), body
    // lama langsung dilepas (BUKAN menunggu animasi keluar) supaya tidak ada
    // flash putih/kedip: background page & card sudah konsisten di kedua step.
    function gantiBodyDenganFade() {
      transitioning = true;
      page.classList.add("book-nav-disabled");
      const bodyLama = body;
      body = MugenUI.el("div", { class: "book-body book-step-fade-in" });
      bodyViewport.appendChild(body);
      renderStepBody();
      bodyLama.remove();
      setTimeout(() => {
        transitioning = false;
        page.classList.remove("book-nav-disabled");
      }, ANIM_MS);
    }

    // ================= STEP 1: CHOOSE BARBER =================
    function renderChooseBarber() {
      body.appendChild(MugenUI.el("h2", {}, "Choose Barber"));
      const grid = MugenUI.el("div", { class: "book-barber-grid" });
      for (const b of barbers) {
        const card = MugenUI.el("button", {
          class: "book-barber-card" + (b.libur_hari_ini ? " disabled" : ""),
          type: "button",
        }, [
          b.foto_url
            ? MugenUI.el("img", { src: MUGEN_API_BASE + b.foto_url, class: "book-barber-foto", alt: b.nama })
            : MugenUI.el("div", { class: "book-barber-foto book-barber-foto-kosong" }, b.nama.charAt(0).toUpperCase()),
          MugenUI.el("div", { class: "book-barber-nama" }, b.nama),
          b.libur_hari_ini ? MugenUI.el("div", { class: "book-barber-status" }, "On Vacation") : null,
        ]);
        if (!b.libur_hari_ini) {
          card.addEventListener("click", () => {
            state.barberId = b.id;
            state.barberNama = b.nama;
            goto(2);
          });
        } else {
          card.disabled = true;
        }
        grid.appendChild(card);
      }
      if (barbers.length) {
        body.appendChild(grid);
      } else {
        body.appendChild(kosongState("✂️", "No barbers available for booking right now."));
      }
      body.appendChild(paginationDots(1, TOTAL_STEP));
    }

    // ================= STEP 2: CHOOSE SERVICE (boleh lebih dari satu) =================
    // REVISI: dipindah dari posisi 4 (setelah Date/Time) ke posisi 2 --
    // dengan service sudah diketahui SEBELUM Date/Time dipilih, Step 4
    // (Select Time) bisa langsung menghitung slot yang duration-aware sejak
    // awal, jadi tidak perlu lagi re-validasi jam terpakai SETELAH memilih
    // service seperti alur lama (lihat renderSelectTime()).
    function renderChooseService() {
      body.appendChild(MugenUI.el("h2", {}, "Choose Service"));
      const listBox = MugenUI.el("div", { class: "book-service-list" });
      const totalBox = MugenUI.el("div", { class: "book-service-total" });
      const errorBox = MugenUI.el("div", { class: "login-error" });

      function updateTotal() {
        const dipilih = services.filter((s) => state.serviceIds.includes(s.id));
        const totalHarga = dipilih.reduce((a, s) => a + s.harga, 0);
        const totalDurasi = dipilih.reduce((a, s) => a + s.durasi_menit, 0);
        totalBox.innerHTML = "";
        if (dipilih.length) {
          totalBox.appendChild(MugenUI.el("div", {}, `${dipilih.length} service(s) selected — Total ${MugenUI.formatRupiah(totalHarga)} (± ${totalDurasi} min)`));
        }
      }

      for (const s of services) {
        const checkbox = MugenUI.el("input", { type: "checkbox" });
        checkbox.checked = state.serviceIds.includes(s.id);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) state.serviceIds.push(s.id);
          else state.serviceIds = state.serviceIds.filter((id) => id !== s.id);
          updateTotal();
        });
        const row = MugenUI.el("label", { class: "book-service-row" }, [
          checkbox,
          MugenUI.el("div", { class: "book-service-info" }, [
            MugenUI.el("div", {}, s.nama),
            MugenUI.el("div", { class: "subtitle" }, `${MugenUI.formatRupiah(s.harga)} · ${s.durasi_menit} min`),
          ]),
        ]);
        listBox.appendChild(row);
      }
      body.appendChild(listBox);
      updateTotal();
      body.appendChild(totalBox);
      body.appendChild(errorBox);
      // REVISI: link "‹ Change Barber" di atas step diganti "< Back" tunggal
      // di bawah, tepat di atas indikator lingkaran, rata kiri -- sama
      // seperti Booking Summary (lihat renderFasePilihMetode()).
      body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(1) }, "< Back"),
      ]));
      body.appendChild(paginationDots(2, TOTAL_STEP));

      const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;" }, "Continue");
      tambahkanEfekRipple(btnLanjut);
      btnLanjut.addEventListener("click", () => {
        errorBox.textContent = "";
        if (!state.serviceIds.length) {
          errorBox.textContent = "Please select at least one service.";
          return;
        }
        goto(3);
      });
      body.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnLanjut));
    }

    // ================= STEP 3: SELECT DATE (kalender visual) =================
    function renderSelectDate() {
      body.appendChild(MugenUI.el("h2", {}, `Select Date — ${state.barberNama}`));
      const minDate = todayIso();
      const maxDate = tambahHari(todayIso(), pengaturan.maksimal_hari_kedepan);
      const hariOperasional = pengaturan.hari_operasional || HARI_KEY;
      const tokoLiburSet = new Set(pengaturan.toko_libur_tanggal || []);

      const calCard = MugenUI.el("div", { class: "book-calendar" });
      body.appendChild(calCard);

      function renderKalender() {
        calCard.innerHTML = "";
        const y = calendarShown.getFullYear();
        const m = calendarShown.getMonth(); // 0-11

        const nav = MugenUI.el("div", { class: "book-calendar-nav" });
        const btnPrev = MugenUI.el("button", { type: "button" }, "‹");
        const btnNext = MugenUI.el("button", { type: "button" }, "›");
        btnPrev.addEventListener("click", () => {
          calendarShown = new Date(y, m - 1, 1);
          renderKalender();
        });
        btnNext.addEventListener("click", () => {
          calendarShown = new Date(y, m + 1, 1);
          renderKalender();
        });
        nav.appendChild(btnPrev);
        nav.appendChild(MugenUI.el("div", {}, `${BULAN[m]} ${y}`));
        nav.appendChild(btnNext);
        calCard.appendChild(nav);

        const grid = MugenUI.el("div", { class: "book-calendar-grid" });
        for (const h of HARI) grid.appendChild(MugenUI.el("div", { class: "book-calendar-dow" }, h));

        const firstDay = new Date(y, m, 1);
        const startOffset = firstDay.getDay(); // 0=Sun
        const jumlahHari = new Date(y, m + 1, 0).getDate();
        for (let i = 0; i < startOffset; i++) grid.appendChild(MugenUI.el("div", { class: "book-calendar-cell empty" }));
        for (let d = 1; d <= jumlahHari; d++) {
          const iso = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
          const diluarRentang = iso < minDate || iso > maxDate;
          const hariIni = HARI_KEY[new Date(y, m, d).getDay()];
          const bukanHariOperasional = !hariOperasional.includes(hariIni);
          const tokoLibur = tokoLiburSet.has(iso);
          const nonaktif = diluarRentang || bukanHariOperasional || tokoLibur;
          const cell = MugenUI.el("button", {
            type: "button",
            class: "book-calendar-cell" + (nonaktif ? " disabled" : "") + (iso === state.tanggal ? " selected" : ""),
            title: tokoLibur ? "Closed for the day" : (bukanHariOperasional ? "Outside opening days" : ""),
          }, String(d));
          if (nonaktif) {
            cell.disabled = true;
          } else {
            cell.addEventListener("click", () => {
              state.tanggal = iso;
              state.jam = null;
              goto(4);
            });
          }
          grid.appendChild(cell);
        }
        calCard.appendChild(grid);
      }
      renderKalender();
      body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(2) }, "< Back"),
      ]));
      body.appendChild(paginationDots(3, TOTAL_STEP));
    }

    // ================= STEP 4: SELECT TIME =================
    // REVISI: service_ids SUDAH diketahui sejak Step 2 -- slot yang
    // ditampilkan di sini langsung duration-aware sejak awal (dulu baru
    // duration-aware setelah re-validasi di step Pilih Service yang lama).
    async function renderSelectTime() {
      body.appendChild(MugenUI.el("h2", {}, `Select Time — ${MugenUI.formatTanggal(state.tanggal)}`));
      const slotBox = MugenUI.el("div");
      body.appendChild(slotBox);
      slotBox.appendChild(MugenUI.skeleton("line", { width: "80%" })); // skeleton selagi slot waktu dimuat

      let data;
      try {
        data = await MugenApi.get(
          `/api/public/booking/slot?barber_id=${state.barberId}&tanggal=${state.tanggal}&service_ids=${state.serviceIds.join(",")}`,
        );
      } catch (e) {
        slotBox.innerHTML = "";
        slotBox.appendChild(errorStateRetry(e.detail && e.detail.detail ? e.detail.detail : e.message, () => {
          body.innerHTML = "";
          renderSelectTime();
        }));
        return;
      }
      slotBox.innerHTML = "";

      const btnPilihTanggalLain = MugenUI.el("button", { type: "button" }, "Choose another date");
      btnPilihTanggalLain.addEventListener("click", () => goto(3));

      if (data.barber_libur) {
        slotBox.appendChild(kosongState("🌴", `${state.barberNama} is on leave on this date. Please choose another date or barber.`, btnPilihTanggalLain));
      } else {
        const grid = MugenUI.el("div", { class: "book-slot-grid" });
        for (const s of data.slots) {
          const btn = MugenUI.el("button", {
            type: "button",
            class: "book-slot-btn book-slot-" + s.status + (s.jam === state.jam ? " selected" : ""),
          }, s.jam);
          if (s.status === "available") {
            btn.addEventListener("click", () => {
              state.jam = s.jam;
              goto(5);
            });
          } else {
            btn.disabled = true;
          }
          grid.appendChild(btn);
        }
        slotBox.appendChild(grid);
        slotBox.appendChild(MugenUI.el("div", { class: "book-legend" }, [
          MugenUI.el("span", { class: "book-legend-item" }, [MugenUI.el("span", { class: "book-dot book-slot-available" }), " Available"]),
          MugenUI.el("span", { class: "book-legend-item" }, [MugenUI.el("span", { class: "book-dot book-slot-booked" }), " Booked"]),
          MugenUI.el("span", { class: "book-legend-item" }, [MugenUI.el("span", { class: "book-dot book-slot-closed" }), " Closed"]),
        ]));
        if (!data.slots.some((s) => s.status === "available")) {
          const btnTanggalLain2 = MugenUI.el("button", { type: "button", style: "width:100%;margin-top:10px;" }, "Choose another date");
          btnTanggalLain2.addEventListener("click", () => goto(3));
          slotBox.appendChild(MugenUI.el("div", { class: "book-warning" }, "No time slots available on this date. Please choose another date."));
          slotBox.appendChild(btnTanggalLain2);
        }
      }
      body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(3) }, "< Back"),
      ]));
      body.appendChild(paginationDots(4, TOTAL_STEP));
    }

    // ================= STEP 5: YOUR DETAILS (Nama + WhatsApp) =================
    function renderYourDetails() {
      body.appendChild(MugenUI.el("h2", {}, "Your Details"));
      const inputNama = MugenUI.el("input", { type: "text", placeholder: "Full name", value: state.nama });
      const inputWa = MugenUI.el("input", { type: "tel", placeholder: "+62 8xx-xxxx-xxxx", value: state.whatsapp });
      const errorBox = MugenUI.el("div", { class: "login-error" });

      body.appendChild(MugenUI.el("label", {}, "Name"));
      body.appendChild(inputNama);
      body.appendChild(MugenUI.el("label", {}, "WhatsApp Number"));
      body.appendChild(inputWa);
      body.appendChild(errorBox);
      body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(4) }, "< Back"),
      ]));
      body.appendChild(paginationDots(5, TOTAL_STEP));

      const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;" }, "Continue");
      tambahkanEfekRipple(btnLanjut);
      btnLanjut.addEventListener("click", () => {
        errorBox.textContent = "";
        const nomorBersih = inputWa.value.trim().replace(/[\s-]/g, "");
        if (!inputNama.value.trim()) { errorBox.textContent = pengaturan.pesan_nama_kosong; return; }
        if (!/^\+?[0-9]{8,15}$/.test(nomorBersih)) { errorBox.textContent = pengaturan.pesan_whatsapp_invalid; return; }
        state.nama = inputNama.value.trim();
        state.whatsapp = inputWa.value.trim();
        goto(6);
      });
      body.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnLanjut));
    }

    // ================= STEP 6: PAYMENT =================
    // Fase (TANPA menambah step/goto baru -- pagination dots tetap di titik
    // ke-6 dari 6 selama semua fase ini): checkout -> metode -> lalu
    // bercabang dua --
    //   Transfer/QRIS: -> bayar (booking SUDAH dikirim ke server di titik
    //     Confirm, halaman ini murni instruksi).
    //   Payment Gateway: -> waiting (poll status) -> berhasil (goto(7),
    //     reuse renderConfirmed()) / gagal / kedaluwarsa.
    // Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant:
    // booking Payment Gateway SEKARANG SUNGGUHAN (bukan simulasi) -- Confirm
    // di fase "metode" langsung POST /api/public/booking untuk KEDUA jalur
    // (Transfer/QRIS MAUPUN Gateway, SAMA PERSIS), backend (routers/booking.py)
    // yang membuat transaksi checkout ke provider & mengembalikan
    // checkout_token/checkout_redirect_url. TIDAK ADA tombol/aksi frontend
    // mana pun yang menandai pembayaran "berhasil" sendiri -- status HANYA
    // pernah berubah lewat booking_gateway_webhook.py (notifikasi resmi
    // provider tervalidasi signature), fase "waiting" di sini murni POLL
    // GET /api/public/booking/gateway-status/{order_id} (read-only) untuk
    // tahu kapan webhook sudah mengonfirmasi.
    function renderPayment() {
      let fase = "checkout";
      const dipilih = services.filter((s) => state.serviceIds.includes(s.id));
      const totalHarga = dipilih.reduce((a, s) => a + s.harga, 0);
      const totalDurasi = dipilih.reduce((a, s) => a + s.durasi_menit, 0);
      const metodeNama = pengaturan.metode_nama || {};
      const metodeInstruksi = pengaturan.metode_instruksi || {};
      const metodeAktif = pengaturan.metode_aktif || [];
      const POLLING_INTERVAL_MS = 3000;
      const DURASI_ESTIMASI_MS = 15 * 60 * 1000;

      function baris(label, value, tebal) {
        return MugenUI.el("div", { style: "display:flex;justify-content:space-between;padding:4px 0;" + (tebal ? "font-weight:700;" : "") }, [
          MugenUI.el("span", { style: "color:var(--text-dim);" }, label),
          MugenUI.el("span", {}, value),
        ]);
      }

      function buatPayloadBooking(metode) {
        return {
          barber_id: state.barberId, tanggal: state.tanggal, jam_mulai: state.jam,
          service_ids: state.serviceIds, customer_nama: state.nama, customer_whatsapp: state.whatsapp,
          metode_pembayaran: metode,
          // Migrasi Faspay SNAP Advance: "gateway" sekarang butuh channel
          // (VA/QRIS) dipilih di muka -- SNAP tidak punya halaman hosted
          // seperti Xpress v4 dulu yang menawarkan semua channel sekaligus.
          channel: metode === "gateway" ? state.channel : undefined,
        };
      }

      function isiKontenMetode() {
        const items = [];
        if (state.metode === "transfer") {
          items.push(
            MugenUI.el("div", {}, `Bank: ${pengaturan.bank_nama || "-"}`),
            MugenUI.el("div", {}, `Account No.: ${pengaturan.bank_nomor_rekening || "-"}`),
            MugenUI.el("div", {}, `Account Name: ${pengaturan.bank_nama_pemilik || "-"}`),
            MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" }, metodeInstruksi.transfer || ""),
          );
        } else if (state.metode === "qris") {
          if (pengaturan.qris_url) {
            const qrisFullUrl = MUGEN_API_BASE + pengaturan.qris_url;
            items.push(MugenUI.el("img", { src: qrisFullUrl, class: "book-qris-img", alt: "QRIS" }));
            const btnDownload = MugenUI.el("button", {
              type: "button",
              class: "book-download-qris-btn",
            }, [
              MugenUI.el("span", { class: "book-download-qris-icon", html: IKON_DOWNLOAD_SVG }),
              "Download QRIS",
            ]);
            tambahkanEfekRipple(btnDownload);
            btnDownload.addEventListener("click", () => unduhGambar(qrisFullUrl, namaFileQris(pengaturan.qris_url, identitas.nama_barbershop)));
            items.push(btnDownload);
          }
          items.push(MugenUI.el("div", { style: "margin-top:8px;" }, pengaturan.qris_merchant_nama || ""));
          items.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" }, metodeInstruksi.qris || ""));
        }
        return items;
      }

      // Review Booking: satu blok per info (label + value SAJA, tanpa tombol
      // Change per-field lagi -- satu link "< Back" tunggal di bawah
      // halaman, lihat renderFaseCheckout()/renderFaseMetode()).
      function seksiInfo(label, value) {
        return MugenUI.el("div", { class: "book-summary-field" }, [
          MugenUI.el("div", { class: "book-summary-label" }, label),
          MugenUI.el("div", { class: "book-summary-value" }, value),
        ]);
      }

      // ---- fase "checkout": Booking Summary murni (Checkout) ----
      function renderFaseCheckout() {
        body.appendChild(MugenUI.el("h2", {}, "Booking Summary"));
        body.appendChild(MugenUI.el("div", { class: "card book-summary-card" }, [
          seksiInfo("Barber", state.barberNama),
          seksiInfo("Service", dipilih.map((s) => s.nama).join(", ")),
          seksiInfo("Date", MugenUI.formatTanggal(state.tanggal)),
          seksiInfo("Time", state.jam),
          seksiInfo("Duration", `± ${totalDurasi} min`),
          seksiInfo("Details", `${state.nama} • ${state.whatsapp}`),
          MugenUI.el("hr"),
          baris("Total Payment", MugenUI.formatRupiah(totalHarga), true),
        ]));
        body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
          MugenUI.el("button", { type: "button", onclick: () => goto(5) }, "< Back"),
        ]));
        body.appendChild(paginationDots(6, TOTAL_STEP));
        const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" }, "Lanjut ke Pembayaran");
        tambahkanEfekRipple(btnLanjut);
        btnLanjut.addEventListener("click", () => { fase = "metode"; gantiFase(); });
        body.appendChild(btnLanjut);
      }

      // ---- fase "metode": daftar metode pembayaran aktif ----
      function renderFaseMetode() {
        body.appendChild(MugenUI.el("h2", {}, "Payment Method"));
        const metodeBox = MugenUI.el("div", { class: "book-metode-list" });
        body.appendChild(metodeBox);
        // Migrasi Faspay SNAP Advance: metode "gateway" sekarang butuh
        // sub-pilihan channel (VA/QRIS) -- ditampilkan HANYA kalau
        // "gateway" sedang terpilih, sumbernya pengaturan.snap_channel_aktif
        // (dikonfigurasi Super Admin, lihat routers/booking.py::public_pengaturan()).
        const channelBox = MugenUI.el("div", { class: "book-metode-list", style: "margin-top:8px;" });
        const snapChannelLabel = { va: pengaturan.snap_va_label ? `Virtual Account (${pengaturan.snap_va_label})` : "Virtual Account", qris: "QRIS" };
        function renderChannelBox() {
          channelBox.innerHTML = "";
          if (state.metode !== "gateway") return;
          const channelAktif = pengaturan.snap_channel_aktif || [];
          for (const c of channelAktif) {
            const btn = MugenUI.el("button", {
              type: "button",
              class: "book-metode-btn" + (state.channel === c ? " selected" : ""),
            }, snapChannelLabel[c] || c);
            btn.addEventListener("click", () => {
              state.channel = c;
              for (const el of channelBox.children) el.classList.remove("selected");
              btn.classList.add("selected");
            });
            channelBox.appendChild(btn);
          }
          if (channelAktif.length === 1) state.channel = channelAktif[0];
        }
        const errorBox = MugenUI.el("div", { class: "login-error" });

        if (!metodeAktif.length) {
          metodeBox.appendChild(kosongState("💳", "No payment method is active yet. Please contact the barbershop."));
        } else if (metodeAktif.length === 1) {
          state.metode = metodeAktif[0];
          metodeBox.appendChild(MugenUI.el("button", {
            type: "button",
            class: "book-metode-btn selected",
            disabled: "disabled",
          }, metodeNama[state.metode] || state.metode));
          renderChannelBox();
        } else {
          for (const m of metodeAktif) {
            const btn = MugenUI.el("button", {
              type: "button",
              class: "book-metode-btn" + (state.metode === m ? " selected" : ""),
            }, metodeNama[m] || m);
            btn.addEventListener("click", () => {
              state.metode = m;
              state.channel = null;
              for (const el of metodeBox.children) el.classList.remove("selected");
              btn.classList.add("selected");
              renderChannelBox();
            });
            metodeBox.appendChild(btn);
          }
          renderChannelBox();
        }
        body.appendChild(channelBox);
        body.appendChild(errorBox);

        body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
          MugenUI.el("button", { type: "button", onclick: () => { fase = "checkout"; gantiFase(); } }, "< Back"),
        ]));
        body.appendChild(paginationDots(6, TOTAL_STEP));

        const btnKonfirmasi = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" }, "Confirm");
        tambahkanEfekRipple(btnKonfirmasi);
        btnKonfirmasi.addEventListener("click", async () => {
          errorBox.textContent = "";
          if (!state.metode) { errorBox.textContent = "Please select a payment method first."; return; }
          if (state.metode === "gateway" && !state.channel) { errorBox.textContent = "Please select VA/QRIS first."; return; }
          try {
            // REVISI: pakai withButtonLoading (spinner kecil di tombol) alih-alih
            // withLoading (overlay pesan penuh) -- tombol sendiri yang mengelola
            // disabled/enabled + label selama request berjalan. Booking SUNGGUHAN
            // dikirim di sini untuk SEMUA metode termasuk "gateway" -- backend
            // (routers/booking.py::public_buat_booking()) yang membuat transaksi
            // checkout ke provider & mengembalikan checkout_token/redirect_url
            // kalau metodenya "gateway".
            const hasil = await MugenUI.withButtonLoading(btnKonfirmasi, () => MugenApi.post("/api/public/booking", buatPayloadBooking(state.metode)));
            state.bookingResult = hasil;
            if (state.metode === "gateway") {
              fase = "waiting";
              gantiFase();
              return;
            }
            MugenUI.toast("Booking berhasil dikonfirmasi.", "success", { force: true }); // toast konfirmasi tambahan, fase "bayar" tetap tampil seperti biasa
            fase = "bayar";
            gantiFase();
          } catch (e) {
            errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
          }
        });
        body.appendChild(btnKonfirmasi);
      }

      function renderFasePembayaran() {
        // Booking SUDAH tersimpan di server pada titik ini (dibuat saat
        // tombol Confirm di fase sebelumnya ditekan) -- halaman ini murni
        // menampilkan instruksi/QRIS untuk diselesaikan pembayarannya,
        // TIDAK mengirim apa pun lagi ke server. HANYA dicapai lewat
        // Transfer/QRIS -- Payment Gateway punya fase "waiting" sendiri.
        const judul = state.metode === "qris" ? "QRIS Payment" : "Payment";
        body.appendChild(MugenUI.el("h2", {}, judul));
        body.appendChild(MugenUI.el("div", { class: "card" }, [
          baris("Total Payment", MugenUI.formatRupiah(totalHarga), true),
          MugenUI.el("hr"),
          ...isiKontenMetode(),
        ]));

        const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" }, "Continue");
        tambahkanEfekRipple(btnLanjut);
        btnLanjut.addEventListener("click", () => goto(7));
        body.appendChild(btnLanjut);
      }

      function salinTeks(teks, btn) {
        try {
          navigator.clipboard.writeText(teks);
          MugenUI.toast("Disalin.", "success");
        } catch (e) {
          MugenUI.toast("Gagal menyalin -- salin manual.", "error");
        }
      }

      // Migrasi Faspay SNAP Advance: VA/QRIS TIDAK PUNYA halaman hosted
      // seperti Xpress v4 dulu (window.snap.pay()/window.open(redirect_url))
      // -- nomor VA / kode QR ditampilkan LANGSUNG di halaman ini, customer
      // menyelesaikan pembayaran lewat app bank/e-wallet miliknya sendiri.
      // Status SUNGGUHAN tetap 100% dari polling di bawah (webhook Faspay),
      // TIDAK PERNAH dari aksi customer di halaman ini.
      function isiKontenSnapWaiting() {
        const r = state.bookingResult;
        const items = [];
        if (r.channel === "va") {
          items.push(MugenUI.el("div", { class: "subtitle" }, pengaturan.snap_va_label || "Virtual Account"));
          const nomorRow = MugenUI.el("div", { style: "display:flex;align-items:center;gap:8px;justify-content:center;margin-top:4px;" }, [
            MugenUI.el("div", { style: "font-size:22px;font-weight:700;letter-spacing:1px;" }, r.va_number || "-"),
          ]);
          const btnSalin = MugenUI.el("button", { type: "button", class: "book-download-qris-btn" }, "Salin Nomor");
          tambahkanEfekRipple(btnSalin);
          btnSalin.addEventListener("click", () => salinTeks(r.va_number || "", btnSalin));
          nomorRow.appendChild(btnSalin);
          items.push(nomorRow);
          items.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
            "Transfer PERSIS sejumlah Total Payment di bawah ke nomor Virtual Account ini lewat m-banking/ATM."));
        } else if (r.channel === "qris") {
          if (r.qr_url) {
            items.push(MugenUI.el("img", { src: r.qr_url, class: "book-qris-img", alt: "QRIS" }));
          }
          items.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" },
            "Scan kode QR di atas lewat app e-wallet/m-banking mana pun yang mendukung QRIS."));
        }
        return items;
      }

      // ---- fase "waiting": Menunggu konfirmasi Payment Gateway (poll) ----
      function renderFaseWaiting() {
        // Format Baru Nomor Transaksi Booking: booking BARU sudah punya
        // nomor_transaksi dari server (booking_db.buat_booking()) --
        // fallback ke rumus lama HANYA untuk booking lama (seharusnya
        // tidak terjadi di fase ini, booking baru saja dibuat, tapi tetap
        // dijaga konsisten dengan pemanggil lain).
        const invoiceRef = state.bookingResult.nomor_transaksi || MugenUI.buatNomorTransaksi(
          { daftar_service: dipilih.map((s) => s.nama).join(", "), tanggal: state.tanggal, jam_mulai: state.jam },
          identitas.nama_barbershop,
        );
        const paymentReference = state.bookingResult.payment_reference;
        body.appendChild(MugenUI.el("h2", {}, "Menunggu Konfirmasi Pembayaran"));
        const statusLabelEl = MugenUI.el("div", { class: "subtitle" }, "Selesaikan pembayaran memakai info di bawah.");
        const countdownEl = MugenUI.el("div", { class: "book-countdown" }, "15:00");
        body.appendChild(MugenUI.el("div", { class: "card" }, [
          MugenUI.el("div", { style: "text-align:center;" }, [
            statusLabelEl,
            countdownEl,
          ]),
          MugenUI.el("hr"),
          MugenUI.el("div", { style: "text-align:center;" }, isiKontenSnapWaiting()),
          MugenUI.el("hr"),
          seksiInfo("No. Invoice", invoiceRef),
          seksiInfo("Nama Customer", state.nama),
          seksiInfo("Barber", state.barberNama),
          seksiInfo("Layanan", dipilih.map((s) => s.nama).join(", ")),
          MugenUI.el("hr"),
          baris("Total Payment", MugenUI.formatRupiah(totalHarga), true),
        ]));
        body.appendChild(MugenUI.el("div", { class: "subtitle", style: "text-align:center;margin-bottom:8px;" },
          "Status di halaman ini otomatis diperbarui begitu pembayaran Anda dikonfirmasi resmi oleh provider -- tidak perlu refresh manual."));

        // Polling + countdown SAMA-SAMA self-clear begitu elemen ini sudah
        // tidak ada di DOM lagi (user pindah fase/keluar wizard lewat cara
        // APA PUN) -- pola guard yang sama seperti timer lain di file ini.
        const pollTimer = setInterval(async () => {
          if (!document.body.contains(countdownEl)) { clearInterval(pollTimer); return; }
          let status;
          try {
            status = await MugenApi.get(`/api/public/booking/snap-status/${paymentReference}`);
          } catch (e) {
            return; // hiccup jaringan sesaat -- coba lagi di tick berikutnya
          }
          if (status.status === "PAID") {
            clearInterval(pollTimer);
            MugenUI.toast("Pembayaran berhasil.", "success", { force: true });
            goto(7);
          } else if (["FAILED", "CANCELLED"].includes(status.status)) {
            clearInterval(pollTimer);
            fase = "gagal";
            gantiFase();
          } else if (status.status === "EXPIRED") {
            clearInterval(pollTimer);
            fase = "kedaluwarsa";
            gantiFase();
          } else if (status.status === "PENDING") {
            statusLabelEl.textContent = "Pembayaran sedang diproses provider…";
          }
        }, POLLING_INTERVAL_MS);

        // Countdown MURNI tampilan (estimasi batas waktu umum provider) --
        // TIDAK PERNAH mengubah fase sendiri begitu habis (status
        // "kedaluwarsa" sungguhan hanya datang dari polling di atas/webhook).
        const deadline = Date.now() + DURASI_ESTIMASI_MS;
        const countdownTimer = setInterval(() => {
          if (!document.body.contains(countdownEl)) { clearInterval(countdownTimer); return; }
          const sisaMs = deadline - Date.now();
          if (sisaMs <= 0) {
            clearInterval(countdownTimer);
            countdownEl.textContent = "00:00";
            return;
          }
          const sisaDetik = Math.floor(sisaMs / 1000);
          const mm = String(Math.floor(sisaDetik / 60)).padStart(2, "0");
          const ss = String(sisaDetik % 60).padStart(2, "0");
          countdownEl.textContent = `${mm}:${ss}`;
          countdownEl.classList.toggle("book-countdown-urgent", sisaDetik < 60);
        }, 1000);
      }

      // ---- fase "gagal": Payment Failed/Cancelled ----
      function renderFaseGagal() {
        body.appendChild(MugenUI.el("div", { class: "card book-selesai" }, [
          MugenUI.el("div", { class: "book-selesai-icon book-selesai-icon-gagal" }, "✕"),
          MugenUI.el("h2", {}, "Payment Failed"),
          MugenUI.el("div", { class: "subtitle" }, "Pembayaran gagal atau dibatalkan. Silakan buat pemesanan baru untuk mencoba lagi."),
        ]));
        const btnUlang = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" }, "Coba Lagi");
        tambahkanEfekRipple(btnUlang);
        btnUlang.addEventListener("click", () => { fase = "metode"; gantiFase(); });
        body.appendChild(btnUlang);
      }

      // ---- fase "kedaluwarsa": Payment Expired ----
      function renderFaseKedaluwarsa() {
        body.appendChild(MugenUI.el("div", { class: "card book-selesai" }, [
          MugenUI.el("div", { class: "book-selesai-icon book-selesai-icon-gagal" }, "⏱"),
          MugenUI.el("h2", {}, "Payment Expired"),
          MugenUI.el("div", { class: "subtitle" }, "Batas waktu pembayaran sudah lewat. Silakan buat pembayaran baru."),
        ]));
        const btnBaru = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" }, "Buat Pembayaran Baru");
        tambahkanEfekRipple(btnBaru);
        btnBaru.addEventListener("click", () => { fase = "metode"; gantiFase(); });
        body.appendChild(btnBaru);
      }

      function gantiFase() {
        body.innerHTML = "";
        if (fase === "bayar") renderFasePembayaran();
        else if (fase === "metode") renderFaseMetode();
        else if (fase === "waiting") renderFaseWaiting();
        else if (fase === "gagal") renderFaseGagal();
        else if (fase === "kedaluwarsa") renderFaseKedaluwarsa();
        else renderFaseCheckout();
      }

      gantiFase();
    }

    // Pesan Otomatis Berdasarkan Jam Operasional Tenant (permintaan Owner):
    // `r.dibuat_di_luar_jam_operasional` dihitung SERVER-SIDE saat booking
    // ini dibuat (booking_db.buat_booking(), pakai waktu WIB AKTUAL saat
    // customer menekan Confirm -- BUKAN jam appointment yang dipilih,
    // BUKAN jam browser customer) -- field TRANSIEN, hanya ada di respons
    // booking BARU SAJA dibuat (state.bookingResult), TIDAK pernah
    // ditanyakan ulang setelah layar ini. Di dalam jam operasional: teks
    // pesan_penutup Owner TETAP APA ADANYA (tidak diubah sama sekali) --
    // di luar jam operasional: SELALU ganti dengan pesan yang menjelaskan
    // toko sedang tutup + jam buka berikutnya (dari pengaturan.jam_buka
    // ASLI milik tenant, TIDAK PERNAH hardcode 10:00/20:00).
    function pesanPenutupFinal(r) {
      if (r.dibuat_di_luar_jam_operasional) {
        return `Booking Anda telah diterima. Saat ini ${identitas.nama_barbershop} sudah di luar jam operasional. `
          + `Tim kami akan menghubungi Anda untuk konfirmasi pada jam operasional berikutnya, mulai pukul ${pengaturan.jam_buka}.`;
      }
      return pengaturan.pesan_penutup || "Thank you! We'll reach out to you on WhatsApp shortly to confirm.";
    }

    // ================= STEP 7: APPOINTMENT CONFIRMED =================
    function renderConfirmed() {
      const r = state.bookingResult;
      const detail = MugenUI.el("div", { class: "book-selesai-detail" }, [
        fieldRow("Transaction Number", r.nomor_transaksi || MugenUI.buatNomorTransaksi(r, identitas.nama_barbershop)),
        fieldRow("Barber", r.nama_barber),
        fieldRow("Date", MugenUI.formatTanggal(r.tanggal)),
        fieldRow("Time", r.jam_mulai),
        fieldRow("Service", r.daftar_service),
        MugenUI.el("hr"),
        fieldRow("Total", MugenUI.formatRupiah(r.total_harga), true),
      ]);
      body.appendChild(MugenUI.el("div", { class: "card book-selesai" }, [
        MugenUI.el("div", { class: "book-selesai-icon" }, "✓"),
        MugenUI.el("h2", {}, "Appointment Confirmed!"),
        detail,
        MugenUI.el("div", { class: "subtitle", style: "margin-top:12px;" }, pesanPenutupFinal(r)),
      ]));

      const actions = MugenUI.el("div", { class: "book-selesai-actions" });

      // REVISI UI/UX Premium: "Add to Calendar" -- file .ics dibuat MURNI di
      // klien dari data booking yang sudah tampil di layar (lihat buatIcs()),
      // TIDAK memanggil endpoint apa pun.
      const btnKalender = MugenUI.el("button", { type: "button" }, "📅 Add to Calendar");
      tambahkanEfekRipple(btnKalender);
      btnKalender.addEventListener("click", () => unduhIcs(r, identitas.nama_barbershop));
      actions.appendChild(btnKalender);

      const btnBaru = MugenUI.el("button", { class: "btn-primary", type: "button" }, "Book Another Appointment");
      tambahkanEfekRipple(btnBaru);
      btnBaru.addEventListener("click", () => {
        state.barberId = null; state.barberNama = ""; state.tanggal = null; state.jam = null;
        state.serviceIds = []; state.nama = ""; state.whatsapp = ""; state.metode = null;
        goto(1);
      });
      actions.appendChild(btnBaru);

      // "Back to Home" -- kembali ke Landing Page (renderLanding), reuse
      // fungsi render() yang sama persis dipanggil router.js saat #/book
      // pertama dibuka (bukan endpoint/logika baru).
      const btnBeranda = MugenUI.el("button", { type: "button" }, "Back to Home");
      tambahkanEfekRipple(btnBeranda);
      btnBeranda.addEventListener("click", () => {
        window.removeEventListener("popstate", onPopState);
        root.innerHTML = "";
        render(root);
      });
      actions.appendChild(btnBeranda);

      body.appendChild(actions);
    }

    pushHistoryStep(1);
    renderAll();
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageBookPublic begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageBookPublic = PageBookPublic;
