// js/landing.js — Landing Page publik (Phase 5). Vanilla JS TANPA framework
// (mengikuti konvensi proyek: tidak ada proses build) -- SATU file, mandiri
// dari app/js/* (Landing Page adalah situs statis TERPISAH, lihat plan
// Phase 5: "SPA app dipindah ke /app/, Landing Page baru di root").

(function () {
  "use strict";

  function apiBase() {
    if (window.MUGEN_API_BASE) return window.MUGEN_API_BASE;
    if (["localhost", "127.0.0.1"].includes(location.hostname)) return "http://localhost:8000";
    return "";
  }

  async function apiGet(path) {
    const res = await fetch(apiBase() + path);
    if (!res.ok) throw new Error(`GET ${path} gagal: HTTP ${res.status}`);
    return res.json();
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else node.setAttribute(k, v);
    });
    (Array.isArray(children) ? children : children != null ? [children] : []).forEach((c) => {
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function formatRupiah(n) {
    return "Rp " + Number(n || 0).toLocaleString("id-ID");
  }

  // ============================= Scroll reveal =============================
  // Fade+slide sekali per elemen (BUKAN animasi berulang tiap scroll) --
  // satu IntersectionObserver dipakai bersama untuk SEMUA elemen ".lp-reveal"
  // (baik yang sudah ada di HTML sejak awal maupun yang baru ditambahkan
  // lewat render dinamis Pricing/FAQ/Testimonial/Contact di bawah), supaya
  // ringan (satu observer, bukan satu per elemen) dan otomatis tidak
  // menganimasikan apa pun untuk pengguna dengan prefers-reduced-motion
  // (CSS-nya sendiri yang menonaktifkan transition, lihat landing.css).
  let revealObserver = null;
  function revealObserve(elements) {
    if (!("IntersectionObserver" in window)) {
      elements.forEach((node) => node.classList.add("lp-in-view"));
      return;
    }
    if (!revealObserver) {
      revealObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("lp-in-view");
          revealObserver.unobserve(entry.target);
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    }
    elements.forEach((node) => revealObserver.observe(node));
  }
  function initScrollReveal() {
    revealObserve(document.querySelectorAll(".lp-reveal"));
  }

  // ============================= Navbar =============================

  function initNavbar() {
    const navbar = document.getElementById("lp-navbar");
    const hamburger = document.getElementById("lp-hamburger");
    const links = document.getElementById("lp-nav-links");

    function onScroll() {
      navbar.classList.toggle("lp-solid", window.scrollY > 12);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });

    hamburger.addEventListener("click", () => links.classList.toggle("lp-open"));
    links.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => links.classList.remove("lp-open")));
  }

  // ============================= Animated counters =============================

  function animateCounter(node, target, suffix) {
    const start = 0;
    const duration = 1200;
    const startTime = performance.now();
    function tick(now) {
      const progress = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const value = Math.round(start + (target - start) * eased);
      node.textContent = value.toLocaleString("id-ID") + (suffix || "");
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  async function loadStats() {
    try {
      const stats = await apiGet("/api/public/landing/stats");
      const section = document.getElementById("lp-stats");
      const nums = section.querySelectorAll(".lp-stat-num");
      nums[0].dataset.target = stats.active_tenants || 0;
      nums[1].dataset.target = stats.total_bookings || 0;
      nums[2].dataset.target = Number(stats.platform_stat_happy_customers) || 0;
      const uptimeNode = section.querySelector(".lp-stat-num-text");
      uptimeNode.textContent = stats.platform_stat_uptime || "-";
    } catch (e) {
      // Statistik gagal dimuat BUKAN alasan menyembunyikan seluruh Landing
      // Page -- biarkan angka 0 tampil apa adanya, bagian lain tetap jalan.
      console.error(e);
    }
  }

  // BUGFIX: sebelumnya initCounters() (IntersectionObserver) dan loadStats()
  // (fetch async) dipanggil terpisah/paralel di boot -- kalau section Trusted
  // KEBETULAN sudah masuk viewport SEBELUM fetch selesai (umum terjadi kalau
  // section itu ada di atas layar/viewport pendek), observer langsung
  // menganimasikan ke nilai default "0" di HTML (data-target belum sempat
  // diisi loadStats()), lalu MENGUNCI diri (sudahJalan=true, observer
  // disconnect) -- update data-target yang datang belakangan dari loadStats()
  // TIDAK PERNAH memicu animasi ulang, counter diam permanen di 0 padahal
  // datanya sebenarnya sudah ada. initStatsSection() memastikan urutannya:
  // TUNGGU loadStats() selesai (data-target sudah benar) SEBELUM observer
  // mulai memantau sama sekali.
  async function initStatsSection() {
    await loadStats();
    const section = document.getElementById("lp-stats");
    const nums = section.querySelectorAll(".lp-stat-num");
    let sudahJalan = false;
    const observer = new IntersectionObserver((entries) => {
      if (sudahJalan || !entries.some((e) => e.isIntersecting)) return;
      sudahJalan = true;
      nums.forEach((node) => animateCounter(node, Number(node.dataset.target) || 0));
      observer.disconnect();
    }, { threshold: 0.3 });
    observer.observe(section);
  }

  // ============================= Features (contoh statis, lihat spesifikasi
  // Phase 5 -- HANYA Pricing & FAQ yang wajib dari database) =============

  const FEATURES = [
    { icon: "📅", title: "Online Booking", desc: "Pelanggan booking sendiri lewat halaman publik toko Anda, 24 jam." },
    { icon: "🗓️", title: "Calendar", desc: "Jadwal barber & slot tersedia terlihat jelas dalam satu kalender." },
    { icon: "✂️", title: "Barber Schedule", desc: "Atur jadwal & hari libur tiap barber tanpa bentrok booking." },
    { icon: "👥", title: "Customer Management", desc: "Riwayat pelanggan tersimpan rapi untuk layanan yang lebih personal." },
    { icon: "💳", title: "Midtrans", desc: "Pembayaran online terintegrasi Midtrans, aman & terpercaya." },
    { icon: "📱", title: "QRIS", desc: "Terima pembayaran QRIS langsung dari pelanggan." },
    { icon: "🏦", title: "Virtual Account", desc: "Dukungan transfer Virtual Account dari berbagai bank." },
    { icon: "📊", title: "Reports", desc: "Laporan transaksi, komisi, dan pengeluaran otomatis." },
    { icon: "📈", title: "Analytics", desc: "Pantau performa toko dengan data yang mudah dibaca." },
    { icon: "🧑‍🤝‍🧑", title: "Multi Barber", desc: "Kelola banyak barber dalam satu toko tanpa batas." },
    { icon: "🏬", title: "Multi Tenant", desc: "Setiap toko punya data & pengaturan yang terisolasi penuh." },
    { icon: "📲", title: "PWA", desc: "Instal seperti aplikasi native di HP atau desktop." },
    { icon: "🔔", title: "Notification", desc: "Notifikasi booking & aktivitas penting secara real-time." },
    { icon: "🖥️", title: "Dashboard", desc: "Satu dashboard untuk mengelola seluruh operasional toko." },
  ];

  function renderFeatures() {
    const grid = document.getElementById("lp-features-grid");
    grid.innerHTML = "";
    FEATURES.forEach((f, i) => {
      grid.appendChild(el("div", { class: `lp-feature-card lp-reveal lp-reveal-${(i % 3) + 1}` }, [
        el("div", { class: "lp-feature-icon" }, f.icon),
        el("h3", {}, f.title),
        el("p", {}, f.desc),
      ]));
    });
    revealObserve(grid.querySelectorAll(".lp-reveal"));
  }

  // ============================= Pricing + Comparison (WAJIB dari database) =============================

  async function loadPackages() {
    const grid = document.getElementById("lp-pricing-grid");
    const table = document.getElementById("lp-compare-table");
    try {
      const packages = await apiGet("/api/public/landing/packages");
      renderPricing(grid, packages);
      renderCompareTable(table, packages);
    } catch (e) {
      grid.innerHTML = "";
      grid.appendChild(el("p", { class: "lp-loading" }, "Paket belum tersedia saat ini."));
      table.innerHTML = "";
      console.error(e);
    }
  }

  function renderPricing(grid, packages) {
    grid.innerHTML = "";
    packages.forEach((p, i) => {
      const fitur = (p.fitur || []).map((f) => el("li", {}, f.nama));
      const btnPilih = el("a", { href: "/app/#/register", class: "lp-btn lp-btn-primary" }, "Select Package");
      // Ingat paket yang diklik lewat sessionStorage (sama origin dengan
      // /app/, jadi tetap terbawa lintas navigasi) -- register.js/billing.js
      // membaca ini untuk menyorot paket yang sama begitu Owner sampai di
      // halaman Billing, supaya pilihan di Landing Page tidak hilang begitu
      // saja saat harus Register dulu.
      btnPilih.addEventListener("click", () => {
        try { sessionStorage.setItem("mugen_pending_package_kode", p.kode); } catch (e) { /* abaikan (mis. private mode) */ }
      });
      grid.appendChild(el("div", { class: `lp-pricing-card lp-reveal lp-reveal-${(i % 3) + 1}` }, [
        el("h3", {}, p.nama),
        el("div", { class: "lp-pricing-price" }, [
          p.harga > 0 ? formatRupiah(p.harga) : "Gratis",
          el("small", {}, p.harga > 0 ? ` / ${p.durasi_hari} hari` : ""),
        ]),
        el("p", { class: "lp-pricing-desc" }, p.deskripsi || ""),
        el("ul", { class: "lp-pricing-features" }, fitur.length ? fitur : [el("li", {}, "-")]),
        btnPilih,
      ]));
    });
    revealObserve(grid.querySelectorAll(".lp-reveal"));
  }

  function renderCompareTable(table, packages) {
    table.innerHTML = "";
    const semuaFitur = [];
    const kodeTerlihat = new Set();
    packages.forEach((p) => (p.fitur || []).forEach((f) => {
      if (!kodeTerlihat.has(f.kode)) { kodeTerlihat.add(f.kode); semuaFitur.push(f); }
    }));

    const thead = el("thead", {}, el("tr", {}, [
      el("th", {}, "Fitur"),
      ...packages.map((p) => el("th", {}, p.nama)),
    ]));

    const rows = [];
    rows.push(el("tr", {}, [
      el("td", {}, "Harga"),
      ...packages.map((p) => el("td", {}, p.harga > 0 ? formatRupiah(p.harga) : "Gratis")),
    ]));
    rows.push(el("tr", {}, [
      el("td", {}, "Max Barber"),
      ...packages.map((p) => el("td", {}, p.max_barber == null ? "Unlimited" : String(p.max_barber))),
    ]));
    rows.push(el("tr", {}, [
      el("td", {}, "Booking / bulan"),
      ...packages.map((p) => el("td", {}, p.max_booking == null ? "Unlimited" : String(p.max_booking))),
    ]));
    semuaFitur.forEach((f) => {
      rows.push(el("tr", {}, [
        el("td", {}, f.nama),
        ...packages.map((p) => {
          const punya = (p.fitur || []).some((pf) => pf.kode === f.kode);
          return el("td", {}, punya ? "✓" : "—");
        }),
      ]));
    });

    const tbody = el("tbody", {}, rows);
    table.appendChild(thead);
    table.appendChild(tbody);
  }

  // ============================= Testimonials (WAJIB dari database) =============================

  function inisial(nama) {
    return (nama || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  }

  async function loadTestimonials() {
    const wrap = document.getElementById("lp-testimonials");
    try {
      const list = await apiGet("/api/public/landing/testimonials");
      wrap.innerHTML = "";
      if (!list.length) {
        wrap.appendChild(el("p", { class: "lp-loading" }, "Belum ada testimonial."));
        return;
      }
      const track = el("div", { class: "lp-carousel-track" });
      list.forEach((t, i) => {
        track.appendChild(el("div", { class: `lp-testimonial-card lp-reveal lp-reveal-${(i % 3) + 1}` }, [
          el("div", { class: "lp-testimonial-rating" }, "★".repeat(t.rating) + "☆".repeat(5 - t.rating)),
          el("p", { class: "lp-testimonial-isi" }, `"${t.isi}"`),
          el("div", { class: "lp-testimonial-foot" }, [
            el("div", { class: "lp-testimonial-avatar" }, inisial(t.nama)),
            el("div", {}, [
              el("div", { class: "lp-testimonial-nama" }, t.nama),
              t.jabatan_toko ? el("div", { class: "lp-testimonial-jabatan" }, t.jabatan_toko) : null,
            ].filter(Boolean)),
          ]),
        ]));
      });
      wrap.appendChild(track);
      revealObserve(track.querySelectorAll(".lp-reveal"));
    } catch (e) {
      wrap.innerHTML = "";
      wrap.appendChild(el("p", { class: "lp-loading" }, "Testimonial belum tersedia."));
      console.error(e);
    }
  }

  // ============================= FAQ (WAJIB dari database) =============================

  async function loadFaq() {
    const wrap = document.getElementById("lp-faq-list");
    try {
      const list = await apiGet("/api/public/landing/faq");
      wrap.innerHTML = "";
      if (!list.length) {
        wrap.appendChild(el("p", { class: "lp-loading" }, "Belum ada FAQ."));
        return;
      }
      list.forEach((f) => {
        const answer = el("div", { class: "lp-faq-answer" }, el("div", { class: "lp-faq-answer-inner" }, f.jawaban));
        const item = el("div", { class: "lp-faq-item lp-reveal" }, [
          el("button", { type: "button", class: "lp-faq-question" }, [
            el("span", {}, f.pertanyaan),
            el("span", { class: "lp-faq-icon" }, "+"),
          ]),
          answer,
        ]);
        item.querySelector(".lp-faq-question").addEventListener("click", () => {
          const buka = item.classList.toggle("lp-open");
          answer.style.maxHeight = buka ? answer.scrollHeight + "px" : "0";
        });
        wrap.appendChild(item);
      });
      revealObserve(wrap.querySelectorAll(".lp-reveal"));
    } catch (e) {
      wrap.innerHTML = "";
      wrap.appendChild(el("p", { class: "lp-loading" }, "FAQ belum tersedia."));
      console.error(e);
    }
  }

  // ============================= Contact (dari Super Admin) =============================

  async function loadContact() {
    const grid = document.getElementById("lp-contact-grid");
    try {
      const c = await apiGet("/api/public/landing/contact");
      grid.innerHTML = "";
      const items = [
        ["WhatsApp", c.platform_contact_whatsapp],
        ["Email", c.platform_contact_email],
        ["Alamat", c.platform_contact_alamat],
      ].filter(([, v]) => v);
      if (!items.length) {
        grid.appendChild(el("p", { class: "lp-loading" }, "Kontak belum diatur."));
        return;
      }
      items.forEach(([label, value]) => {
        grid.appendChild(el("div", { class: "lp-contact-item lp-reveal" }, [
          el("div", { class: "lp-contact-label" }, label),
          el("div", { class: "lp-contact-value" }, value),
        ]));
      });
      if (c.platform_contact_maps_url) {
        grid.appendChild(el("a", { href: c.platform_contact_maps_url, target: "_blank", rel: "noopener", class: "lp-contact-item lp-reveal" }, [
          el("div", { class: "lp-contact-label" }, "Lokasi"),
          el("div", { class: "lp-contact-value" }, "Buka di Google Maps"),
        ]));
      }
      revealObserve(grid.querySelectorAll(".lp-reveal"));
    } catch (e) {
      grid.innerHTML = "";
      grid.appendChild(el("p", { class: "lp-loading" }, "Kontak belum tersedia."));
      console.error(e);
    }
  }

  // ============================= Boot =============================

  function registerServiceWorker() {
    // Scope default "/" (folder tempat file ini didaftarkan) -- lihat
    // service-worker.js untuk kenapa ini TIDAK bentrok dengan SW /app/.
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("service-worker.js", { updateViaCache: "none" }).catch(() => {});
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("lp-year").textContent = new Date().getFullYear();
    initNavbar();
    renderFeatures();
    initStatsSection();
    loadPackages();
    loadTestimonials();
    loadFaq();
    loadContact();
    registerServiceWorker();
    // Elemen ".lp-reveal" statis (sudah ada di HTML sejak awal, mis. judul
    // section/timeline/screenshot mockup) -- yang ditambahkan dinamis lewat
    // render di atas (Pricing/FAQ/Testimonial/Contact) sudah diobservasi
    // masing-masing lewat revealObserve() di fungsi render-nya sendiri.
    initScrollReveal();
  });
})();
