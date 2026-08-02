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
// Background Website (Light/Dark preset atau Image+Opacity) DITERAPKAN lewat
// terapkanBackground() di bawah, scoped ke root .book-public saja (teknik
// custom-property inline style yang sama dipakai PR 3 untuk warna branding,
// sekarang dipakai untuk ini).
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

  // Preset warna Background Website "Light"/"Dark" -- SAMA PERSIS dengan
  // palet Light/Dark yang sudah dipakai aplikasi admin (:root & :root[data-
  // theme="dark"] di style.css), supaya kontras teks/ikon/tombol/kartu tetap
  // terjamin baik tanpa perlu palet baru terpisah. Diterapkan sebagai inline
  // custom property di elemen root (page) -- SCOPED ke subtree halaman
  // publik ini saja (teknik yang sama dipakai PR 3 untuk Primary/Secondary
  // Color, yang sekarang sudah dihapus), tidak pernah menjalar ke tema
  // aplikasi admin internal.
  const BG_PRESET = {
    light: {
      "--bg": "#F5F7FA", "--bg-card": "#FFFFFF", "--bg-input": "#F8FAFC", "--border": "#E2E8F0",
      "--text": "#0F172A", "--text-dim": "#64748B", "--accent": "#334155", "--accent-hover": "#1E293B",
      "--accent-pressed": "#0F172A",
      "--shadow-card": "0 1px 2px rgba(15,23,42,0.04), 0 1px 3px rgba(15,23,42,0.06)",
      "--shadow-elevated": "0 8px 24px rgba(15,23,42,0.10)",
    },
    dark: {
      "--bg": "#0F172A", "--bg-card": "#1E293B", "--bg-input": "#0F172A", "--border": "#334155",
      "--text": "#F1F5F9", "--text-dim": "#94A3B8", "--accent": "#475569", "--accent-hover": "#64748B",
      "--accent-pressed": "#334155",
      "--shadow-card": "0 1px 2px rgba(0,0,0,0.20), 0 1px 3px rgba(0,0,0,0.24)",
      "--shadow-elevated": "0 8px 24px rgba(0,0,0,0.40)",
    },
  };

  // Background Website: "light"/"dark" (preset polos) ATAU "image" (foto
  // Owner + slider opacity, memakai preset Light sebagai dasar kontras teks
  // -- pilihan Light/Dark TIDAK dipakai lagi kalau tipe-nya "image", sesuai
  // instruksi). Layer gambar ditaruh sebagai elemen ANAK PERTAMA rootEl,
  // position:absolute + z-index:-1 -- tetap di BELAKANG seluruh konten
  // halaman (dan tetap di ATAS dev-watermark-bg, karena #app sendiri sudah
  // z-index:1 lebih tinggi, lihat style.css) tanpa perlu z-index tinggi.
  function terapkanBackground(rootEl, content) {
    const preset = content.background_tipe === "dark" ? BG_PRESET.dark : BG_PRESET.light;
    for (const [prop, nilai] of Object.entries(preset)) rootEl.style.setProperty(prop, nilai);

    const layerLama = rootEl.querySelector(":scope > .book-bg-layer");
    if (layerLama) layerLama.remove();
    rootEl.classList.remove("book-bg-image");

    if (content.background_tipe === "image" && content.background_image_url) {
      rootEl.classList.add("book-bg-image");
      const layer = MugenUI.el("div", { class: "book-bg-layer", "aria-hidden": "true" });
      layer.style.backgroundImage = `url("${MUGEN_API_BASE}${content.background_image_url}")`;
      layer.style.opacity = String(Math.max(0, Math.min(100, content.background_opacity ?? 20)) / 100);
      rootEl.insertBefore(layer, rootEl.firstChild);
    }
  }

  function render(root) {
    root.innerHTML = "";
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
    terapkanBackground(page, content);

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
      const about = MugenUI.el("section", { class: "book-section book-about" });
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
      const gallerySec = MugenUI.el("section", { class: "book-section book-gallery" });
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
      const visit = MugenUI.el("section", { class: "book-section book-visit" });
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
      const hours = MugenUI.el("section", { class: "book-section book-hours" });
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
    const bookCta = MugenUI.el("section", { class: "book-section book-cta" });
    if (content.booking_cta_judul) bookCta.appendChild(MugenUI.el("h2", {}, content.booking_cta_judul));
    if (content.booking_cta_subjudul) bookCta.appendChild(MugenUI.el("div", { class: "subtitle" }, content.booking_cta_subjudul));
    const btnCta = MugenUI.el("button", { class: "btn-primary book-cta-btn", type: "button" },
      content.booking_cta_tombol_teks || "Book Appointment");
    btnCta.addEventListener("click", bukaWizard);
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
      const connect = MugenUI.el("section", { class: "book-section book-connect" });
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
    terapkanBackground(page, websiteContent);

    // Header wizard SENGAJA ringkas (logo/nama kecil + link kembali ke
    // Beranda) -- Hero besar sudah ditampilkan di landing page, tidak perlu
    // diulang di sini.
    wizardHeader.innerHTML = "";
    const wizardBrandRow = MugenUI.el("div", { class: "book-wizard-brand" });
    if (identitas.logo_url) {
      wizardBrandRow.appendChild(gambarAman(MUGEN_API_BASE + identitas.logo_url, { alt: "Logo", class: "book-wizard-logo" }));
    }
    wizardBrandRow.appendChild(MugenUI.el("span", {}, identitas.nama_barbershop || "Developer"));
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

      // Review Booking: satu blok per info (label + value SAJA, tanpa tombol
      // Change per-field lagi -- REVISI: diganti satu link "< Back" tunggal
      // di bawah halaman, lihat renderFasePilihMetode()).
      function seksiInfo(label, value) {
        return MugenUI.el("div", { class: "book-summary-field" }, [
          MugenUI.el("div", { class: "book-summary-label" }, label),
          MugenUI.el("div", { class: "book-summary-value" }, value),
        ]);
      }

      function renderFasePilihMetode() {
        body.appendChild(MugenUI.el("h2", {}, "Booking Summary"));
        body.appendChild(MugenUI.el("div", { class: "card book-summary-card" }, [
          seksiInfo("Barber", state.barberNama),
          seksiInfo("Service", dipilih.map((s) => s.nama).join(", ")),
          seksiInfo("Date", MugenUI.formatTanggal(state.tanggal)),
          seksiInfo("Time", state.jam),
          seksiInfo("Details", `${state.nama} • ${state.whatsapp}`),
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

        // REVISI: satu link "< Back" di bagian bawah halaman, tepat di atas
        // indikator lingkaran (bukan tombol Change per-field di dalam card
        // lagi) -- font/warna SAMA PERSIS dengan link "Change X" di step
        // lain (reuse .book-nav-row button), TAPI TANPA kelas "row" supaya
        // tidak ikut melebar+center seperti link Change lama (.row > *
        // { flex:1 } membuat tombol satu-satunya di situ melebar penuh,
        // teksnya jadi center bukan rata kiri) -- di sini SENGAJA rata kiri
        // sesuai spesifikasi. Mengembalikan ke step sebelumnya (5 -- Your
        // Details) sesuai alur booking.
        body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
          MugenUI.el("button", { type: "button", onclick: () => goto(5) }, "< Back"),
        ]));
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
        fieldRow("Transaction Number", MugenUI.buatNomorTransaksi(r, identitas.nama_barbershop)),
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
    }

    pushHistoryStep(1);
    renderAll();
  }

  return { render };
})();
