// pages/book_public.js — Halaman PUBLIK "/book" (hash #/book), TANPA LOGIN.
// Dirender LANGSUNG ke #app (bukan lewat MugenRouter.shell()) -- tidak ada
// sidebar/menu, karena ini bukan bagian dari aplikasi internal.
//
// PR 2 "Revisi Konsep Website Booking": halaman ini SEKARANG website resmi
// MUGEN Hair Co. (Hero/About/Gallery/Visit Us/Connect With Us/Closing),
// dikonsumsi dari /api/website/* (PR 1) + /api/pengaturan/identitas +
// /api/public/booking/pengaturan (Opening Hours -- REUSE data yang sama
// dipakai slot booking, BUKAN sistem jam kedua). Wizard booking yang sudah
// ada (renderWizard) HANYA muncul setelah tombol "Book Appointment"
// ditekan -- urutan step-nya diubah (Service sekarang SEBELUM Date/Time,
// supaya slot yang ditampilkan langsung duration-aware sejak awal) dan
// SELURUH teks UI diterjemahkan ke Bahasa Inggris. Teks yang datang dari
// database (pesan custom Owner lewat Setting/Booking Settings) SENGAJA
// TIDAK diterjemahkan otomatis -- tetap apa adanya sesuai yang Owner isi.
//
// Data diambil dari endpoint /api/public/booking/* & /api/website/* --
// endpoint itu sengaja hanya membocorkan info yang memang boleh dilihat
// siapa saja -- TIDAK ADA data toko yang sensitif (Rating Google, Review
// pelanggan, dan Profil barber SENGAJA tidak ditampilkan di halaman utama,
// sesuai instruksi -- barber baru muncul di dalam wizard booking).

const PageBookPublic = (() => {
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
    return new Date().toISOString().slice(0, 10);
  }

  function tambahHari(iso, n) {
    const d = new Date(iso + "T00:00:00");
    d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
  }

  function fieldRow(label, value, tebal) {
    return MugenUI.el("div", { class: "book-field-row" + (tebal ? " book-field-row-total" : "") }, [
      MugenUI.el("span", { class: "book-field-label" }, label),
      MugenUI.el("span", { class: "book-field-colon" }, ":"),
      MugenUI.el("span", { class: "book-field-value" }, value),
    ]);
  }

  function prefersReducedMotionGlobal() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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

  // Pagination dots (○ ○ ● ○ ○ ○) -- pengganti teks "Langkah X dari Y",
  // ditaruh di BAWAH konten step (tepat di atas tombol Next/Continue),
  // BUKAN di atas halaman seperti progress bar lama.
  function paginationDots(langkahAktif, totalLangkah) {
    const wrap = MugenUI.el("div", { class: "book-pagination-dots" });
    for (let i = 1; i <= totalLangkah; i++) {
      wrap.appendChild(MugenUI.el("span", { class: "book-dot-page" + (i === langkahAktif ? " active" : "") }));
    }
    return wrap;
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

  // PR 3: Primary/Secondary Color HANYA berlaku di halaman publik /book --
  // di-set sebagai inline style di elemen root landing/wizard (bukan
  // :root global), jadi otomatis ter-scope ke subtree ini saja dan TIDAK
  // pernah menjalar ke tema aplikasi admin internal.
  function terapkanWarnaBranding(rootEl, content) {
    if (content.branding_warna_primer) {
      rootEl.style.setProperty("--accent", content.branding_warna_primer);
      rootEl.style.setProperty("--accent-pressed", content.branding_warna_primer);
    }
    if (content.branding_warna_sekunder) {
      rootEl.style.setProperty("--accent-hover", content.branding_warna_sekunder);
    }
  }

  // PR 3: SEO -- di-inject ke <head> saat landing page dibuka. CATATAN
  // JUJUR: halaman ini SPA client-rendered, jadi crawler yang TIDAK
  // menjalankan JavaScript tidak akan melihat meta ini -- tetap berguna
  // untuk preview link (WhatsApp/Facebook/dst yang menjalankan JS atau
  // punya bot pembaca Open Graph).
  function terapkanSeoMeta(content, identitas) {
    function setMeta(attr, name, value) {
      if (!value) return;
      let el = document.head.querySelector(`meta[${attr}="${name}"]`);
      if (!el) {
        el = document.createElement("meta");
        el.setAttribute(attr, name);
        document.head.appendChild(el);
      }
      el.setAttribute("content", value);
    }
    const judul = content.seo_title || identitas.nama_barbershop;
    if (judul) document.title = judul;
    setMeta("name", "description", content.seo_deskripsi);
    setMeta("name", "keywords", content.seo_keywords);
    setMeta("property", "og:title", judul);
    setMeta("property", "og:description", content.seo_deskripsi);
    if (content.seo_og_image_url) setMeta("property", "og:image", MUGEN_API_BASE + content.seo_og_image_url);
  }

  // PR 3: Favicon -- berlaku untuk kunjungan/tab BARU. Perangkat yang
  // SUDAH meng-install PWA ini sebelumnya TIDAK akan otomatis memperbarui
  // ikon yang sudah terlanjur tersimpan di home screen mereka
  // (keterbatasan bawaan browser/OS, lihat juga catatan yang sama di
  // routers/website.py & booking.js).
  function terapkanFavicon(content) {
    if (!content.branding_favicon_url) return;
    const url = MUGEN_API_BASE + content.branding_favicon_url;
    document.querySelectorAll('link[rel="icon"]').forEach((el) => { el.href = url; });
  }

  // Overlay sederhana untuk menampilkan Privacy Policy / Terms and
  // Conditions (teks panjang dari CMS) -- tanpa perlu route/hash baru.
  function tampilkanTeksLegal(judul, teks) {
    const overlay = MugenUI.el("div", { class: "book-legal-overlay" });
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    const panel = MugenUI.el("div", { class: "book-legal-panel" });
    const btnClose = MugenUI.el("button", { type: "button", class: "book-legal-close" }, "✕");
    btnClose.addEventListener("click", () => overlay.remove());
    panel.appendChild(btnClose);
    panel.appendChild(MugenUI.el("h2", {}, judul));
    panel.appendChild(MugenUI.el("div", { class: "book-legal-text" }, teks));
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
  }

  function render(root) {
    root.innerHTML = "";
    // REVISI UI/UX (Dark Mode): lapis pertahanan KEDUA di sisi JS -- router.js
    // sudah memanggil MugenTheme.forceLight() sebelum PageBookPublic.render()
    // dipanggil, tapi dipanggil ulang di sini juga supaya halaman ini tetap
    // benar walau suatu saat dipanggil dari jalur lain.
    if (typeof MugenTheme !== "undefined") MugenTheme.forceLight();
    renderLanding(root);
  }

  // ================= LANDING PAGE (website resmi) =================
  async function renderLanding(root) {
    const page = MugenUI.el("div", { class: "book-public book-landing" });
    root.appendChild(page);
    page.appendChild(MugenUI.el("p", { class: "status-placeholder" }, "Loading…"));

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
      page.appendChild(MugenUI.el("div", { class: "card" }, "Failed to load this page: " + e.message));
      return;
    }
    page.innerHTML = "";
    terapkanWarnaBranding(page, content);
    terapkanSeoMeta(content, identitas);
    terapkanFavicon(content);

    function bukaBooking(link) {
      const nilai = (link || "").trim();
      if (!nilai) { root.innerHTML = ""; renderWizard(root); return; }
      window.location.href = nilai;
    }

    // ---- Hero ----
    const hero = MugenUI.el("section", { class: "book-hero" });
    const heroMedia = MugenUI.el("div", { class: "book-hero-media" });
    if (content.hero_tipe === "video" && content.hero_video_url) {
      heroMedia.appendChild(MugenUI.el("video", {
        src: MUGEN_API_BASE + content.hero_video_url,
        autoplay: "autoplay", muted: "muted", loop: "loop", playsinline: "playsinline",
      }));
    } else if (identitas.banner_url) {
      heroMedia.appendChild(gambarAman(MUGEN_API_BASE + identitas.banner_url, { alt: "Hero", class: "book-hero-img" }));
    }
    hero.appendChild(heroMedia);
    const heroContent = MugenUI.el("div", { class: "book-hero-content" });
    if (identitas.logo_url) {
      heroContent.appendChild(gambarAman(MUGEN_API_BASE + identitas.logo_url, { alt: "Logo", class: "book-hero-logo" }));
    }
    heroContent.appendChild(MugenUI.el("h1", {}, identitas.nama_barbershop || "MUGEN Hair Co."));
    heroContent.appendChild(MugenUI.el("div", { class: "book-hero-tagline" },
      identitas.tagline || "We don't fix hair. We fix egos."));
    const btnHeroCta = MugenUI.el("button", { class: "btn-primary book-hero-cta", type: "button" },
      content.hero_cta_teks || "Book Appointment");
    btnHeroCta.addEventListener("click", () => bukaBooking(content.hero_cta_link));
    heroContent.appendChild(btnHeroCta);
    hero.appendChild(heroContent);
    page.appendChild(hero);

    // ---- About ----
    if (content.about_judul || content.about_deskripsi || content.about_foto_url) {
      const about = MugenUI.el("section", { class: "book-section book-about" });
      if (content.about_foto_url) {
        about.appendChild(gambarAman(MUGEN_API_BASE + content.about_foto_url, { alt: "About", class: "book-about-foto" }));
      }
      const aboutText = MugenUI.el("div", { class: "book-about-text" });
      aboutText.appendChild(MugenUI.el("h2", {}, content.about_judul || "About Us"));
      if (content.about_deskripsi) aboutText.appendChild(MugenUI.el("p", {}, content.about_deskripsi));
      about.appendChild(aboutText);
      page.appendChild(about);
    }

    // ---- Gallery ----
    if (gallery.length) {
      const gallerySec = MugenUI.el("section", { class: "book-section book-gallery" });
      gallerySec.appendChild(MugenUI.el("h2", {}, "Gallery"));
      const slider = MugenUI.el("div", { class: "book-gallery-slider" });
      for (const foto of gallery) {
        slider.appendChild(MugenUI.el("img", {
          src: MUGEN_API_BASE + foto.foto_url, alt: "Gallery", loading: "lazy", class: "book-gallery-slide",
        }));
      }
      gallerySec.appendChild(slider);
      page.appendChild(gallerySec);
    }

    // ---- Visit Us ----
    const visit = MugenUI.el("section", { class: "book-section book-visit" });
    visit.appendChild(MugenUI.el("h2", {}, "Visit Us"));
    if (content.visit_maps_embed_url) {
      visit.appendChild(MugenUI.el("iframe", {
        src: content.visit_maps_embed_url, class: "book-maps-embed", loading: "lazy",
        referrerpolicy: "no-referrer-when-downgrade", allowfullscreen: "allowfullscreen",
      }));
    }
    if (identitas.alamat) visit.appendChild(MugenUI.el("div", { class: "book-visit-alamat" }, identitas.alamat));
    if (content.visit_maps_link) {
      visit.appendChild(MugenUI.el("a", {
        href: content.visit_maps_link, target: "_blank", rel: "noopener noreferrer", class: "book-maps-link",
      }, "Open in Google Maps"));
    }
    const hariAktif = pengaturan.hari_operasional || [];
    if (hariAktif.length) {
      const aktifTerurut = URUTAN_HARI_TAMPIL.filter((h) => hariAktif.includes(h));
      const liburTerurut = URUTAN_HARI_TAMPIL.filter((h) => !hariAktif.includes(h));
      const hoursBox = MugenUI.el("div", { class: "book-opening-hours" });
      hoursBox.appendChild(MugenUI.el("div", { class: "book-opening-hours-title" }, "Opening Hours"));
      hoursBox.appendChild(MugenUI.el("div", {},
        `${aktifTerurut.map((h) => LABEL_HARI_EN[h]).join(", ")}: ${pengaturan.jam_buka} – ${pengaturan.jam_tutup}`));
      if (liburTerurut.length) {
        hoursBox.appendChild(MugenUI.el("div", { class: "subtitle" },
          `Closed: ${liburTerurut.map((h) => LABEL_HARI_EN[h]).join(", ")}`));
      }
      visit.appendChild(hoursBox);
    }
    page.appendChild(visit);

    // ---- Connect With Us ----
    const social = [];
    if (identitas.instagram) social.push({ label: "Instagram", href: identitas.instagram });
    if (content.tiktok) social.push({ label: "TikTok", href: content.tiktok });
    if (identitas.whatsapp) social.push({ label: "WhatsApp", href: `https://wa.me/${nomorKeFormatInternasional(identitas.whatsapp)}` });
    if (content.facebook) social.push({ label: "Facebook", href: content.facebook });
    if (content.youtube) social.push({ label: "YouTube", href: content.youtube });
    if (social.length) {
      const connect = MugenUI.el("section", { class: "book-section book-connect" });
      connect.appendChild(MugenUI.el("h2", {}, "Connect With Us"));
      const row = MugenUI.el("div", { class: "book-connect-row" });
      for (const s of social) {
        row.appendChild(MugenUI.el("a", {
          href: s.href, target: "_blank", rel: "noopener noreferrer", class: "book-connect-link",
        }, s.label));
      }
      connect.appendChild(row);
      page.appendChild(connect);
    }

    // ---- Closing ----
    const closing = MugenUI.el("section", { class: "book-section book-closing" });
    closing.appendChild(MugenUI.el("h2", {}, content.booking_cta_judul || "Ready for a fresh look?"));
    if (content.booking_cta_subjudul) closing.appendChild(MugenUI.el("div", { class: "subtitle" }, content.booking_cta_subjudul));
    const btnClosingCta = MugenUI.el("button", { class: "btn-primary book-closing-cta", type: "button" },
      content.booking_cta_tombol_teks || "Book Appointment");
    btnClosingCta.addEventListener("click", () => bukaBooking(content.booking_cta_tombol_link));
    closing.appendChild(btnClosingCta);
    page.appendChild(closing);

    // ---- Footer ----
    if (content.footer_copyright || content.footer_pesan || content.footer_privacy_policy || content.footer_terms) {
      const footerSec = MugenUI.el("footer", { class: "book-landing-footer" });
      if (content.footer_pesan) footerSec.appendChild(MugenUI.el("div", {}, content.footer_pesan));
      const legalLinks = [];
      if (content.footer_privacy_policy) {
        const btn = MugenUI.el("button", { type: "button", class: "book-legal-link" }, "Privacy Policy");
        btn.addEventListener("click", () => tampilkanTeksLegal("Privacy Policy", content.footer_privacy_policy));
        legalLinks.push(btn);
      }
      if (content.footer_terms) {
        const btn = MugenUI.el("button", { type: "button", class: "book-legal-link" }, "Terms and Conditions");
        btn.addEventListener("click", () => tampilkanTeksLegal("Terms and Conditions", content.footer_terms));
        legalLinks.push(btn);
      }
      if (legalLinks.length) footerSec.appendChild(MugenUI.el("div", { class: "book-legal-links" }, legalLinks));
      if (content.footer_copyright) footerSec.appendChild(MugenUI.el("div", { class: "subtitle" }, content.footer_copyright));
      page.appendChild(footerSec);
    }
  }

  // ================= WIZARD BOOKING =================
  async function renderWizard(root) {
    if (typeof MugenTheme !== "undefined") MugenTheme.forceLight();
    const page = MugenUI.el("div", { class: "book-public book-wizard-enter" });
    root.appendChild(page);

    const wizardHeader = MugenUI.el("div", { class: "book-wizard-header" });
    page.appendChild(wizardHeader);

    const bodyViewport = MugenUI.el("div", { class: "book-body-viewport" });
    const body = MugenUI.el("div", { class: "book-body" });
    bodyViewport.appendChild(body);
    const footer = MugenUI.el("div", { class: "book-footer" });
    page.appendChild(bodyViewport);
    page.appendChild(footer);

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
    };

    let websiteContent = null;
    try {
      [pengaturan, barbers, services, websiteContent] = await Promise.all([
        MugenApi.get("/api/public/booking/pengaturan"),
        MugenApi.get("/api/public/booking/barbers"),
        MugenApi.get("/api/public/booking/services"),
        MugenApi.get("/api/website/content"),
        MugenBrand.refresh(),
      ]);
    } catch (e) {
      body.appendChild(MugenUI.el("div", { class: "card" }, "Failed to load the booking form: " + e.message));
      return;
    }

    const identitas = MugenBrand.get();
    terapkanWarnaBranding(page, websiteContent);

    // Header wizard SENGAJA ringkas (logo/nama kecil + link kembali ke
    // Beranda) -- Hero/Banner besar sudah ditampilkan di landing page,
    // tidak perlu diulang di sini. pesan_pembuka (Booking Settings, field
    // LAMA yang sudah ada) tetap ditampilkan di sini kalau diisi Owner.
    wizardHeader.innerHTML = "";
    const btnKembali = MugenUI.el("button", { type: "button", class: "book-back-home" }, "‹ Back to Home");
    btnKembali.addEventListener("click", () => { root.innerHTML = ""; render(root); });
    wizardHeader.appendChild(btnKembali);
    const wizardBrandRow = MugenUI.el("div", { class: "book-wizard-brand" });
    if (identitas.logo_url) {
      wizardBrandRow.appendChild(gambarAman(MUGEN_API_BASE + identitas.logo_url, { alt: "Logo", class: "book-wizard-logo" }));
    }
    wizardBrandRow.appendChild(MugenUI.el("span", {}, identitas.nama_barbershop || "MUGEN Hair Co."));
    wizardHeader.appendChild(wizardBrandRow);
    if (pengaturan.pesan_pembuka) {
      wizardHeader.appendChild(MugenUI.el("div", { class: "book-pesan-pembuka" }, pengaturan.pesan_pembuka));
    }

    footer.innerHTML = "";
    if (pengaturan.header_footer) {
      footer.appendChild(MugenUI.el("div", {}, pengaturan.header_footer));
    }

    // ---- animasi perpindahan step: slide + fade, 300ms, arah mengikuti
    // maju/mundurnya nomor step (goto ke step lebih besar = "Continue" =
    // slide dari kanan ke kiri, goto ke step lebih kecil = "Back" = slide
    // dari kiri ke kanan). Selama animasi berjalan, transitioning=true
    // membuat goto() lain diabaikan -- ini SATU-SATUNYA tempat penjagaan
    // double-klik perlu ditambahkan karena semua tombol navigasi step
    // memanggil goto().
    let transitioning = false;
    const ANIM_MS = 300;

    function prefersReducedMotion() {
      return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }

    function goto(n) {
      if (transitioning || n === step) return;
      const arah = n > step ? "maju" : "mundur";
      step = n;
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
        animasiTransisi(arah);
      }
      window.scrollTo(0, 0);
    }

    function animasiTransisi(arah) {
      transitioning = true;
      bodyViewport.classList.add("book-transitioning");
      page.classList.add("book-nav-disabled");

      const klonLama = body.cloneNode(true);
      klonLama.classList.add("book-step-outgoing", arah === "maju" ? "book-anim-out-maju" : "book-anim-out-mundur");
      bodyViewport.appendChild(klonLama);

      body.innerHTML = "";
      renderStepBody();
      body.classList.add(arah === "maju" ? "book-anim-in-maju" : "book-anim-in-mundur");

      let selesai = false;
      function bersihkan() {
        if (selesai) return;
        selesai = true;
        klonLama.remove();
        body.classList.remove("book-anim-in-maju", "book-anim-in-mundur");
        bodyViewport.classList.remove("book-transitioning");
        page.classList.remove("book-nav-disabled");
        transitioning = false;
      }
      klonLama.addEventListener("animationend", bersihkan);
      // jaga-jaga kalau animationend tidak pernah terpicu (mis. tab di background)
      setTimeout(bersihkan, ANIM_MS + 150);
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
      body.appendChild(grid);
      if (!barbers.length) {
        body.appendChild(MugenUI.el("div", { class: "subtitle" }, "No barbers available for booking right now."));
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
      body.appendChild(MugenUI.el("div", { class: "row book-nav-row", style: "margin-bottom:12px;" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(1) }, "‹ Change Barber"),
      ]));
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
      body.appendChild(paginationDots(2, TOTAL_STEP));

      const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;" }, "Continue");
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
      body.appendChild(MugenUI.el("div", { class: "row book-nav-row", style: "margin-bottom:12px;" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(2) }, "‹ Change Service"),
      ]));
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
      body.appendChild(paginationDots(3, TOTAL_STEP));
    }

    // ================= STEP 4: SELECT TIME =================
    // REVISI: service_ids SUDAH diketahui sejak Step 2 -- slot yang
    // ditampilkan di sini langsung duration-aware sejak awal (dulu baru
    // duration-aware setelah re-validasi di step Pilih Service yang lama).
    async function renderSelectTime() {
      body.appendChild(MugenUI.el("h2", {}, `Select Time — ${MugenUI.formatTanggal(state.tanggal)}`));
      body.appendChild(MugenUI.el("div", { class: "row book-nav-row", style: "margin-bottom:12px;" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(3) }, "‹ Change Date"),
      ]));
      const slotBox = MugenUI.el("div");
      body.appendChild(slotBox);
      slotBox.innerHTML = "Loading available times...";

      let data;
      try {
        data = await MugenApi.get(
          `/api/public/booking/slot?barber_id=${state.barberId}&tanggal=${state.tanggal}&service_ids=${state.serviceIds.join(",")}`,
        );
      } catch (e) {
        slotBox.innerHTML = "";
        slotBox.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
        return;
      }
      slotBox.innerHTML = "";

      if (data.barber_libur) {
        slotBox.appendChild(MugenUI.el("div", { class: "book-warning" },
          `${state.barberNama} is on leave on this date. Please choose another date or barber.`));
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
          slotBox.appendChild(MugenUI.el("div", { class: "book-warning" }, "No time slots available on this date. Please choose another date."));
        }
      }
      body.appendChild(paginationDots(4, TOTAL_STEP));
    }

    // ================= STEP 5: YOUR DETAILS (Nama + WhatsApp) =================
    function renderYourDetails() {
      body.appendChild(MugenUI.el("h2", {}, "Your Details"));
      body.appendChild(MugenUI.el("div", { class: "row book-nav-row", style: "margin-bottom:12px;" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(4) }, "‹ Change Time"),
      ]));
      const inputNama = MugenUI.el("input", { type: "text", placeholder: "Full name", value: state.nama });
      const inputWa = MugenUI.el("input", { type: "tel", placeholder: "+62 8xx-xxxx-xxxx", value: state.whatsapp });
      const errorBox = MugenUI.el("div", { class: "login-error" });

      body.appendChild(MugenUI.el("label", {}, "Name"));
      body.appendChild(inputNama);
      body.appendChild(MugenUI.el("label", {}, "WhatsApp Number"));
      body.appendChild(inputWa);
      body.appendChild(errorBox);
      body.appendChild(paginationDots(5, TOTAL_STEP));

      const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;" }, "Continue");
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
    // Dipecah jadi 2 fase TANPA menambah step/goto baru (pagination dots
    // tetap di titik ke-6 dari 6 selama fase ini) -- fase "pilih" (Ringkasan
    // + Metode Pembayaran + tombol Confirm, yang benar-benar mengirim
    // booking ke server) lalu fase "bayar" (Halaman Pembayaran sesuai
    // metode terpilih, termasuk Download QRIS) baru muncul SETELAH booking
    // berhasil dibuat.
    function renderPayment() {
      let fase = "pilih";
      const dipilih = services.filter((s) => state.serviceIds.includes(s.id));
      const totalHarga = dipilih.reduce((a, s) => a + s.harga, 0);
      const metodeNama = pengaturan.metode_nama || {};
      const metodeInstruksi = pengaturan.metode_instruksi || {};
      const metodeAktif = pengaturan.metode_aktif || [];

      function baris(label, value, tebal) {
        return MugenUI.el("div", { style: "display:flex;justify-content:space-between;padding:4px 0;" + (tebal ? "font-weight:700;" : "") }, [
          MugenUI.el("span", { style: "color:var(--text-dim);" }, label),
          MugenUI.el("span", {}, value),
        ]);
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
        } else if (state.metode === "cash") {
          items.push(MugenUI.el("div", {}, metodeInstruksi.cash || ""));
        } else if (state.metode === "gateway") {
          items.push(MugenUI.el("div", {}, metodeInstruksi.gateway || ""));
        }
        return items;
      }

      function renderFasePilihMetode() {
        body.appendChild(MugenUI.el("h2", {}, "Booking Summary"));
        body.appendChild(MugenUI.el("div", { class: "row book-nav-row", style: "margin-bottom:12px;" }, [
          MugenUI.el("button", { type: "button", onclick: () => goto(5) }, "‹ Change Details"),
        ]));
        body.appendChild(MugenUI.el("div", { class: "card" }, [
          baris("Barber", state.barberNama),
          baris("Date", MugenUI.formatTanggal(state.tanggal)),
          baris("Time", state.jam),
          baris("Service", dipilih.map((s) => s.nama).join(", ")),
          baris("Name", state.nama),
          baris("WhatsApp", state.whatsapp),
          MugenUI.el("hr"),
          baris("Total Payment", MugenUI.formatRupiah(totalHarga), true),
        ]));

        body.appendChild(MugenUI.el("h2", { style: "margin-top:24px;" }, "Payment Method"));
        const metodeBox = MugenUI.el("div", { class: "book-metode-list" });
        body.appendChild(metodeBox);
        const errorBox = MugenUI.el("div", { class: "login-error" });

        if (!metodeAktif.length) {
          metodeBox.appendChild(MugenUI.el("div", { class: "subtitle" }, "No payment method is active yet. Please contact the barbershop."));
        } else if (metodeAktif.length === 1) {
          state.metode = metodeAktif[0];
          metodeBox.appendChild(MugenUI.el("button", {
            type: "button",
            class: "book-metode-btn selected",
            disabled: "disabled",
          }, metodeNama[state.metode] || state.metode));
        } else {
          for (const m of metodeAktif) {
            const btn = MugenUI.el("button", {
              type: "button",
              class: "book-metode-btn" + (state.metode === m ? " selected" : ""),
            }, metodeNama[m] || m);
            btn.addEventListener("click", () => {
              state.metode = m;
              for (const el of metodeBox.children) el.classList.remove("selected");
              btn.classList.add("selected");
            });
            metodeBox.appendChild(btn);
          }
        }
        body.appendChild(errorBox);
        body.appendChild(paginationDots(6, TOTAL_STEP));

        const btnKonfirmasi = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" }, "Confirm");
        btnKonfirmasi.addEventListener("click", async () => {
          errorBox.textContent = "";
          if (!state.metode) { errorBox.textContent = "Please select a payment method first."; return; }
          if (state.metode === "gateway") { errorBox.textContent = "Payment Gateway is not available yet, please choose another method."; return; }
          btnKonfirmasi.disabled = true;
          try {
            const hasil = await MugenUI.withLoading(() => MugenApi.post("/api/public/booking", {
              barber_id: state.barberId, tanggal: state.tanggal, jam_mulai: state.jam,
              service_ids: state.serviceIds, customer_nama: state.nama, customer_whatsapp: state.whatsapp,
              metode_pembayaran: state.metode,
            }), { message: "Processing your booking…" });
            state.bookingResult = hasil;
            fase = "bayar";
            gantiFase();
          } catch (e) {
            errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
          } finally {
            btnKonfirmasi.disabled = false;
          }
        });
        body.appendChild(btnKonfirmasi);
      }

      function renderFasePembayaran() {
        // Booking SUDAH tersimpan di server pada titik ini (dibuat saat
        // tombol Confirm di fase sebelumnya ditekan) -- halaman ini murni
        // menampilkan instruksi/QRIS untuk diselesaikan pembayarannya,
        // TIDAK mengirim apa pun lagi ke server.
        const judul = state.metode === "qris" ? "QRIS Payment" : "Payment";
        body.appendChild(MugenUI.el("h2", {}, judul));
        body.appendChild(MugenUI.el("div", { class: "card" }, [
          baris("Total Payment", MugenUI.formatRupiah(totalHarga), true),
          MugenUI.el("hr"),
          ...isiKontenMetode(),
        ]));

        const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" }, "Continue");
        btnLanjut.addEventListener("click", () => goto(7));
        body.appendChild(btnLanjut);
      }

      function gantiFase() {
        body.innerHTML = "";
        if (fase === "bayar") renderFasePembayaran();
        else renderFasePilihMetode();
      }

      gantiFase();
    }

    // ================= STEP 7: APPOINTMENT CONFIRMED =================
    function renderConfirmed() {
      const r = state.bookingResult;
      const detail = MugenUI.el("div", { class: "book-selesai-detail" }, [
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
        MugenUI.el("div", { class: "subtitle", style: "margin-top:12px;" },
          pengaturan.pesan_penutup || "Thank you! We'll reach out to you on WhatsApp shortly to confirm."),
      ]));
      const btnBaru = MugenUI.el("button", { class: "btn-primary", type: "button", style: "margin-top:16px;" }, "Book Another Appointment");
      btnBaru.addEventListener("click", () => {
        state.barberId = null; state.barberNama = ""; state.tanggal = null; state.jam = null;
        state.serviceIds = []; state.nama = ""; state.whatsapp = ""; state.metode = null;
        goto(1);
      });
      body.appendChild(btnBaru);
      const btnHome = MugenUI.el("button", { type: "button", style: "margin-top:10px;margin-left:8px;" }, "Back to Home");
      btnHome.addEventListener("click", () => { root.innerHTML = ""; render(root); });
      body.appendChild(btnHome);
    }

    renderAll();
  }

  return { render };
})();
