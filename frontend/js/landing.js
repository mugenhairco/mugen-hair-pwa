// js/landing.js — Landing Page publik (Phase 5). Vanilla JS TANPA framework
// (mengikuti konvensi proyek: tidak ada proses build) -- SATU file, mandiri
// dari app/js/* (Landing Page adalah situs statis TERPISAH, lihat plan
// Phase 5: "SPA app dipindah ke /app/, Landing Page baru di root").

(function () {
  "use strict";

  // BUGFIX: navigasi Back/Forward browser (termasuk PWA standalone yang
  // di-resume dari background) SECARA DEFAULT me-restore posisi scroll
  // TERAKHIR sebelum pengguna meninggalkan halaman -- sehingga "memasuki"
  // Landing Page ini (mis. lewat tombol Back dari /app/#/register) bisa
  // mendarat di TENGAH halaman, bukan di atas. history.scrollRestoration
  // "manual" menonaktifkan restorasi otomatis itu supaya Landing Page ini
  // SELALU mulai dari atas.
  if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }
  // REVISI KEDUA (feedback Owner): baris ini SEBELUMNYA hanya dijalankan
  // kalau location.hash KOSONG -- tapi scrollToHash() di bawah selalu
  // memanggil history.pushState(hash) setiap kali menu diklik, jadi URL
  // address bar tetap membawa hash terakhir yang pernah diklik. Kalau
  // pengunjung me-refresh atau membuka ulang halaman ini persis dengan
  // hash lama itu masih di URL, browser melakukan native anchor-jump
  // (INSTAN, tanpa kompensasi offset navbar, terjadi SEBELUM skrip ini
  // sempat jalan) -- persis gejala "mendarat di tengah halaman" yang
  // dikeluhkan. Sekarang SELALU dipaksa ke atas dulu tanpa syarat; kalau
  // memang ada hash di URL (mis. deep link dibagikan), baru diarahkan
  // ULANG ke situ dengan animasi scroll halus milik Landing Page sendiri
  // (bukan native jump), lihat pemanggilan scrollToHash() di dalam
  // DOMContentLoaded paling bawah file ini.
  window.scrollTo(0, 0);

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

  // ============================= Detail Modal (Fitur & Pricing) =============
  // Overlay generik dipakai kedua slider (Fitur & Pricing) saat kartu di
  // tengah "dipilih" (lihat js/lp-slider.js onSelect) -- HANYA satu instance
  // pada satu waktu (openDetailModal menutup yang lama dulu kalau ada).

  let _modalKeydownHandler = null;

  function closeDetailModal() {
    const overlay = document.getElementById("lp-detail-modal");
    if (!overlay) return;
    overlay.remove();
    document.body.classList.remove("lp-modal-open");
    if (_modalKeydownHandler) {
      document.removeEventListener("keydown", _modalKeydownHandler);
      _modalKeydownHandler = null;
    }
  }

  function openDetailModal({ icon, title, body, footer }) {
    closeDetailModal();
    const closeBtn = el("button", { type: "button", class: "lp-modal-close", "aria-label": "Tutup" }, "×");
    closeBtn.addEventListener("click", closeDetailModal);

    const box = el("div", { class: "lp-modal-box" }, [
      closeBtn,
      ...(icon ? [el("div", { class: "lp-modal-icon" }, icon)] : []),
      el("h3", { class: "lp-modal-title" }, title),
      el("div", { class: "lp-modal-body" }, body),
      ...(footer ? [el("div", { class: "lp-modal-footer" }, footer)] : []),
    ]);

    const overlay = el("div", { class: "lp-modal-overlay", id: "lp-detail-modal", role: "dialog", "aria-modal": "true" }, box);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closeDetailModal(); });
    document.body.appendChild(overlay);
    document.body.classList.add("lp-modal-open");

    _modalKeydownHandler = (e) => { if (e.key === "Escape") closeDetailModal(); };
    document.addEventListener("keydown", _modalKeydownHandler);
    closeBtn.focus();
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

  // ==================== Animasi konten mockup dashboard ==================
  // FITUR (feedback Owner): mockup Dashboard di Hero DAN kartu Dashboard
  // Owner/Aplikasi Barber/Notifikasi WhatsApp/Absensi Karyawan di section
  // "Kenapa Rivoir" sebelumnya statis -- angka & isi mockup di dalamnya
  // sekarang "hidup" (angka berjalan, grafik/bar tumbuh, tangan melambai,
  // chat mengetik, radius mengecil + pin jatuh) supaya terasa lebih
  // menarik. Murni dekoratif, data dummy, TIDAK terhubung ke API apa pun.
  // Dimatikan total untuk prefers-reduced-motion (angka/teks yang terus
  // berubah tetap dianggap motion, bukan cuma transform/opacity CSS).
  function _formatJt(nilaiJutaan) {
    return "Rp " + nilaiJutaan.toFixed(1).replace(".", ",") + "jt";
  }
  // Format "pintar" untuk counter yang bergerak per kelipatan 0,5jt (lihat
  // _initSteppedCounter di bawah) -- BEDA dari _formatJt (selalu 1 desimal)
  // karena di sini nilai BOLAK-BALIK antara bulat & setengahan (mis. 20,5
  // lalu 21 lalu 21,5), jadi angka bulat SENGAJA tidak dipaksa ",0" di
  // belakangnya (feedback Owner: "20,5 21 21,5", bukan "21,0").
  function _formatJtSmart(nilaiJutaan) {
    const dibulatkan = Math.round(nilaiJutaan * 100) / 100;
    let s = dibulatkan.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    return "Rp " + s.replace(".", ",") + "jt";
  }

  // Loop generik dipakai bareng oleh beberapa animasi mockup di bawah:
  // frameFn(t) dipanggil tiap frame dari t=0->1 (durationMs, easing
  // _scrollEase), tahan sebentar di t=1 (holdMs), reset ke t=0, jeda
  // (pauseMs), ulang terus -- satu sumber pola timing, tidak diduplikasi
  // tiap fungsi.
  function _growHoldResetLoop(frameFn, durationMs, holdMs, pauseMs) {
    function cycle() {
      const start = performance.now();
      function tick(now) {
        const t = Math.min(1, (now - start) / durationMs);
        frameFn(_scrollEase(t));
        if (t < 1) { requestAnimationFrame(tick); return; }
        setTimeout(() => { frameFn(0); setTimeout(cycle, pauseMs); }, holdMs);
      }
      requestAnimationFrame(tick);
    }
    cycle();
  }

  // Counter "berjalan per step" generik (angka bulat ATAU kelipatan uang
  // tetap, mis. 0,5jt) -- dipakai SEMUA counter bertipe ini di halaman
  // (Booking Hari Ini x2, Pelanggan Baru, Pendapatan Dashboard Owner,
  // Barber Aktif) lewat SATU konstanta interval yang sama (STEP_TICK_MS)
  // supaya kecepatan pergerakan angkanya konsisten di semua tempat
  // (feedback Owner: "kecepatan pergerakan angka harus sama semua").
  // min ditampilkan dulu (cocok dengan nilai statis di HTML sebagai
  // fallback sebelum JS jalan), lalu naik per `step` tiap tick sampai
  // max, balik ke min, ulang terus.
  const STEP_TICK_MS = 180;
  function _initSteppedCounter(elId, min, max, step, formatFn) {
    const el = document.getElementById(elId);
    if (!el) return;
    let value = min;
    setInterval(() => {
      value = value >= max - 1e-9 ? min : Math.min(max, value + step);
      el.textContent = formatFn(value);
    }, STEP_TICK_MS);
  }

  // Grafik batang mockup Dashboard di Hero: tinggi tiap batang tumbuh dari
  // kecil ke tinggi aslinya (data-target, disimpan di HTML) lalu reset,
  // berulang -- SEMUA batang jalan bareng (progress sama).
  function initHeroChart() {
    const chart = document.getElementById("lp-hero-chart");
    if (!chart) return;
    const bars = Array.from(chart.querySelectorAll("span"));
    if (!bars.length) return;
    const targets = bars.map((b) => parseFloat(b.dataset.target) || 0);
    const MIN_PCT = 10;
    _growHoldResetLoop((e) => {
      bars.forEach((bar, i) => { bar.style.height = (MIN_PCT + (targets[i] - MIN_PCT) * e) + "%"; });
    }, 1400, 500, 300);
  }

  // Bar Dimas & Yoga: lebar + nominal tumbuh dari kecil ke target (cepat),
  // lalu reset ke kecil dan ulang -- keduanya jalan bareng (progress sama).
  // REVISI (feedback Owner): Dimas pendapatannya lebih tinggi dari Yoga,
  // jadi bar-nya harus konsisten lebih PENUH juga (maxPct beda, bukan
  // sama-sama mentok 3/4) -- proporsional dengan rasio nominal keduanya
  // (12,4jt : 9,1jt) supaya lebar bar selalu mencerminkan besar-kecil
  // pendapatan sungguhan di setiap titik animasi, bukan cuma di akhir.
  function initDashboardBars() {
    const barDimas = document.getElementById("lp-diff-bar-dimas");
    const valDimas = document.getElementById("lp-diff-val-dimas");
    const barYoga = document.getElementById("lp-diff-bar-yoga");
    const valYoga = document.getElementById("lp-diff-val-yoga");
    if (!barDimas || !valDimas || !barYoga || !valYoga) return;
    const DIMAS = { minPct: 24, maxPct: 80, minVal: 3.8, maxVal: 12.4 };
    const YOGA = { minPct: 16, maxPct: 58, minVal: 2.2, maxVal: 9.1 };
    _growHoldResetLoop((e) => {
      barDimas.style.width = (DIMAS.minPct + (DIMAS.maxPct - DIMAS.minPct) * e) + "%";
      valDimas.textContent = _formatJt(DIMAS.minVal + (DIMAS.maxVal - DIMAS.minVal) * e);
      barYoga.style.width = (YOGA.minPct + (YOGA.maxPct - YOGA.minPct) * e) + "%";
      valYoga.textContent = _formatJt(YOGA.minVal + (YOGA.maxVal - YOGA.minVal) * e);
    }, 1400, 500, 300);
  }

  // Aplikasi Barber: Pendapatan Bulan Ini & Komisi Saya naik terus dari
  // nilai minimum ke maksimum (REVISI feedback Owner -- SEBELUMNYA turun
  // besar->kecil, sekarang dibalik kecil->besar), lalu reset ke minimum
  // dan ulang.
  function initBarberCounters() {
    const pendapatanEl = document.getElementById("lp-diff-pendapatan-barber");
    const komisiEl = document.getElementById("lp-diff-komisi-barber");
    if (!pendapatanEl || !komisiEl) return;
    const PENDAPATAN = { min: 5.0, max: 12.4 };
    const KOMISI = { min: 2.0, max: 4.9 };
    _growHoldResetLoop((e) => {
      pendapatanEl.textContent = _formatJt(PENDAPATAN.min + (PENDAPATAN.max - PENDAPATAN.min) * e);
      komisiEl.textContent = _formatJt(KOMISI.min + (KOMISI.max - KOMISI.min) * e);
    }, 2200, 500, 300);
  }

  // Notifikasi WhatsApp: 2 bubble chat diketik satu per satu (efek
  // typewriter), lalu jeda, kosongkan lagi, ulang dari awal terus-menerus.
  // Teks disimpan di data-text dengan penanda "|...|" untuk bagian yang
  // harus tebal (mis. nominal) -- dipisah per segmen supaya <b> tetap utuh
  // sambil tetap "diketik" karakter demi karakter.
  function _typeIntoBubble(el, speedMs) {
    return new Promise((resolve) => {
      const raw = el.dataset.text || "";
      const parts = raw.split("|");
      el.textContent = "";
      let partIndex = 0;
      let charIndex = 0;
      let boldNode = null;
      function step() {
        if (partIndex >= parts.length) { resolve(); return; }
        const part = parts[partIndex];
        if (charIndex >= part.length) {
          partIndex++; charIndex = 0; boldNode = null;
          step();
          return;
        }
        const isBold = partIndex % 2 === 1;
        const ch = part[charIndex];
        if (isBold) {
          if (!boldNode) { boldNode = document.createElement("b"); el.appendChild(boldNode); }
          boldNode.appendChild(document.createTextNode(ch));
        } else {
          el.appendChild(document.createTextNode(ch));
        }
        charIndex++;
        setTimeout(step, speedMs);
      }
      step();
    });
  }
  function initWhatsAppTyping() {
    const bubble1 = document.getElementById("lp-diff-wa-bubble-1");
    const bubble2 = document.getElementById("lp-diff-wa-bubble-2");
    if (!bubble1 || !bubble2) return;
    const TYPE_SPEED_MS = 28;
    const GAP_MS = 500;
    const HOLD_MS = 1800;
    const RESTART_MS = 700;
    function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
    async function cycle() {
      bubble1.style.opacity = "0"; bubble1.textContent = "";
      bubble2.style.opacity = "0"; bubble2.textContent = "";
      await sleep(RESTART_MS);
      bubble1.style.opacity = "1";
      await _typeIntoBubble(bubble1, TYPE_SPEED_MS);
      await sleep(GAP_MS);
      bubble2.style.opacity = "1";
      await _typeIntoBubble(bubble2, TYPE_SPEED_MS);
      await sleep(HOLD_MS);
      cycle();
    }
    cycle();
  }

  // Absensi Karyawan: lingkaran radius mengecil terus, begitu sampai
  // kecil pin jatuh dari atas, "Jarak dari Toko" turun 70m->10m mengikuti
  // progress radius yang SAMA PERSIS (satu sumber kebenaran), lalu reset
  // dan ulang.
  function initAbsensiAnimation() {
    const radiusEl = document.getElementById("lp-diff-absensi-radius");
    const pinEl = document.getElementById("lp-diff-absensi-pin");
    const jarakEl = document.getElementById("lp-diff-absensi-jarak");
    if (!radiusEl || !pinEl || !jarakEl) return;
    const SHRINK_MS = 2400;
    const HOLD_MS = 900;
    const PAUSE_MS = 400;
    const MIN_SCALE = 0.32;
    const JARAK_MAX = 70;
    const JARAK_MIN = 10;
    function frame(t) {
      const e = _scrollEase(t);
      radiusEl.style.transform = `scale(${1 - (1 - MIN_SCALE) * e})`;
      jarakEl.textContent = Math.round(JARAK_MAX - (JARAK_MAX - JARAK_MIN) * e) + " meter";
    }
    function dropPin() {
      pinEl.classList.remove("lp-diff-pin-drop");
      pinEl.classList.add("lp-diff-pin-reset");
      // Paksa reflow supaya animasi bisa diputar ulang dari awal tiap siklus
      // (menambah class yang sama tanpa reflow tidak akan restart animasi).
      void pinEl.offsetWidth;
      pinEl.classList.remove("lp-diff-pin-reset");
      pinEl.classList.add("lp-diff-pin-drop");
    }
    function cycle() {
      radiusEl.style.transform = "";
      pinEl.classList.remove("lp-diff-pin-drop");
      pinEl.classList.add("lp-diff-pin-reset");
      const start = performance.now();
      function tick(now) {
        const t = Math.min(1, (now - start) / SHRINK_MS);
        frame(t);
        if (t < 1) { requestAnimationFrame(tick); return; }
        dropPin();
        setTimeout(() => setTimeout(cycle, PAUSE_MS), HOLD_MS);
      }
      requestAnimationFrame(tick);
    }
    cycle();
  }

  function initDiffMockupAnimations() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // Mockup Dashboard di Hero (BUKAN kartu fitur unggulan section "Kenapa
    // Rivoir" -- dua mockup dashboard berbeda, dua elemen terpisah). Semua
    // counter di sini pakai _initSteppedCounter (STEP_TICK_MS yang sama)
    // supaya kecepatan pergerakan angkanya konsisten satu sama lain.
    _initSteppedCounter("lp-hero-booking-count", 18, 50, 1, (v) => String(v));
    _initSteppedCounter("lp-hero-pendapatan", 4.85, 20, 0.5, _formatJtSmart);
    _initSteppedCounter("lp-hero-pelanggan-baru", 11, 50, 1, (v) => String(v));
    initHeroChart();
    // Kartu fitur unggulan (section "Kenapa Rivoir").
    _initSteppedCounter("lp-diff-booking-count", 18, 50, 1, (v) => String(v));
    _initSteppedCounter("lp-diff-pendapatan-owner", 20.5, 50, 0.5, _formatJtSmart);
    _initSteppedCounter("lp-diff-barber-aktif", 5, 15, 1, (v) => String(v));
    initDashboardBars();
    initBarberCounters();
    initWhatsAppTyping();
    initAbsensiAnimation();
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

  // ======================= Smooth Scroll & Scroll-Spy =======================
  // REVISI: `html { scroll-behavior: smooth }` bawaan browser (landing.css)
  // terasa kaku -- kurva animasinya linear/sama rata untuk jarak dekat
  // maupun jauh, dan link menu tidak pernah menandai section mana yang
  // sedang aktif. Diganti animasi scroll custom (durasi mengikuti jarak,
  // easing kustom) + scroll-spy (link menu otomatis menyala saat section-nya
  // terlihat, bukan cuma saat diklik). Berlaku untuk SEMUA link "#id" di
  // halaman (navbar, footer, tombol CTA "Lihat Paket") lewat event
  // delegation di document, bukan cuma navbar.
  //
  // REVISI KEDUA (feedback Owner): kurva awal (--ease/cubic-bezier(0.16,1,
  // 0.3,1), sama dengan transisi hover cepat di halaman ini) ternyata
  // TERLALU "meledak" di awal -- >90% jarak sudah ditempuh sebelum 30%
  // durasi berlalu, sisanya nyaris diam, jadi terasa tersentak berhenti
  // BUKAN melambat halus. Diganti easeOutCubic (0.33,1,0.68,1, KHUSUS untuk
  // scroll, SENGAJA beda dari --ease yang tetap dipakai transisi hover
  // pendek) -- perlambatan tersebar merata sepanjang durasi, mendekati
  // tujuan terasa jelas melambat, bukan berhenti tiba-tiba. Durasi juga
  // dinaikkan (600-1300ms, dari 450-900ms) supaya fase perlambatan itu
  // sungguh-sungguh punya waktu untuk dirasakan.
  //
  // REVISI KETIGA (feedback Owner): durasi masih terasa terlalu cepat --
  // dilipatgandakan 2x (1200-2600ms, dari 600-1300ms) supaya scroll ke
  // menu yang diklik terasa jauh lebih santai/mewah.

  // Evaluator cubic-bezier(x1,y1,x2,y2) generik (Newton-Raphson, pola sama
  // seperti implementasi referensi spesifikasi CSS Easing).
  function makeBezierEase(x1, y1, x2, y2) {
    function A(a1, a2) { return 1 - 3 * a2 + 3 * a1; }
    function B(a1, a2) { return 3 * a2 - 6 * a1; }
    function C(a1) { return 3 * a1; }
    function calc(t, a1, a2) { return ((A(a1, a2) * t + B(a1, a2)) * t + C(a1)) * t; }
    function slope(t, a1, a2) { return 3 * A(a1, a2) * t * t + 2 * B(a1, a2) * t + C(a1); }
    function tForX(x) {
      let t = x;
      for (let i = 0; i < 6; i++) {
        const s = slope(t, x1, x2);
        if (s === 0) return t;
        t -= (calc(t, x1, x2) - x) / s;
      }
      return t;
    }
    return (x) => (x <= 0 ? 0 : x >= 1 ? 1 : calc(tForX(x), y1, y2));
  }
  const _scrollEase = makeBezierEase(0.33, 1, 0.68, 1); // easeOutCubic, khusus scroll

  function _navbarOffset() {
    const navbar = document.getElementById("lp-navbar");
    return (navbar ? navbar.offsetHeight : 64) + 12; // +12px jarak napas
  }

  function _targetScrollY(el) {
    const y = el.getBoundingClientRect().top + window.scrollY - _navbarOffset();
    const maxY = document.documentElement.scrollHeight - window.innerHeight;
    return Math.max(0, Math.min(y, maxY));
  }

  // Durasi mengikuti jarak (klik menu section tetangga terasa lebih cepat
  // daripada section jauh) -- ciri khas landing page premium, BUKAN durasi
  // tetap seperti scroll-behavior:smooth bawaan browser.
  function smoothScrollTo(targetY) {
    return new Promise((resolve) => {
      const startY = window.scrollY;
      const diff = targetY - startY;
      if (Math.abs(diff) < 1) { resolve(); return; }
      const duration = Math.min(2600, Math.max(1200, Math.abs(diff) * 1.7));
      // scroll-behavior:smooth bawaan browser HARUS dimatikan sementara --
      // kalau tidak, window.scrollTo() tiap frame di bawah akan dianimasikan
      // ULANG oleh browser (smoothing dobel, hasilnya malah tersendat).
      const htmlEl = document.documentElement;
      const prevBehavior = htmlEl.style.scrollBehavior;
      htmlEl.style.scrollBehavior = "auto";
      const startTime = performance.now();
      function step(now) {
        const t = Math.min(1, (now - startTime) / duration);
        window.scrollTo(0, startY + diff * _scrollEase(t));
        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          htmlEl.style.scrollBehavior = prevBehavior;
          resolve();
        }
      }
      requestAnimationFrame(step);
    });
  }

  function scrollToHash(hash) {
    const el = document.querySelector(hash);
    if (!el) return;
    const targetY = _targetScrollY(el);
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const done = reduceMotion ? (window.scrollTo(0, targetY), Promise.resolve()) : smoothScrollTo(targetY);
    done.then(() => { if (history.pushState) history.pushState(null, "", hash); });
  }

  function initSmoothAnchors() {
    document.addEventListener("click", (e) => {
      const a = e.target.closest('a[href^="#"]');
      if (!a) return;
      const hash = a.getAttribute("href");
      if (!hash || hash.length < 2) return;
      if (!document.querySelector(hash)) return; // biarkan default kalau target tidak ada
      e.preventDefault();
      scrollToHash(hash);
    });
  }

  // Link menu navbar menyala otomatis mengikuti section yang SEDANG
  // terlihat saat pengunjung scroll manual -- bukan cuma saat diklik.
  function initScrollSpy() {
    const navLinks = Array.from(document.querySelectorAll('#lp-nav-links a[href^="#"]'));
    if (!navLinks.length || !("IntersectionObserver" in window)) return;
    const targetToLink = new Map();
    navLinks.forEach((a) => {
      const el = document.querySelector(a.getAttribute("href"));
      if (el) targetToLink.set(el, a);
    });
    if (!targetToLink.size) return;
    const band = _navbarOffset();
    const spy = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const active = targetToLink.get(entry.target);
        if (!active) return;
        navLinks.forEach((l) => l.classList.remove("lp-nav-active"));
        active.classList.add("lp-nav-active");
      });
    }, { rootMargin: `-${band}px 0px -65% 0px`, threshold: 0 });
    targetToLink.forEach((_a, el) => spy.observe(el));
  }

  // ============================= Features (contoh statis, lihat spesifikasi
  // Phase 5 -- HANYA Pricing & FAQ yang wajib dari database) =============

  // FITUR Detail Modal: tiap item punya `detail` (ringkasan lebih panjang +
  // poin-poin manfaat) yang ditampilkan saat kartu di tengah slider diklik
  // LAGI ("dipilih", lihat renderFeatures()/openFeatureDetail() di bawah).
  const FEATURES = [
    { icon: "📅", title: "Online Booking", desc: "Pelanggan booking sendiri lewat halaman publik toko Anda, 24 jam.", detail: {
      ringkasan: "Setiap toko punya halaman booking publik sendiri yang bisa dibagikan lewat media sosial atau WhatsApp -- pelanggan pilih layanan, barber, dan jam sendiri tanpa perlu menelepon.",
      poin: [
        "Halaman booking publik unik per toko, tinggal bagikan link-nya",
        "Pelanggan pilih barber, layanan, dan jam yang tersedia sendiri",
        "Konfirmasi booking otomatis, admin tidak perlu angkat telepon",
        "Slot terkunci real-time sehingga tidak ada double booking",
      ],
    } },
    { icon: "💬", title: "WhatsApp Notification", desc: "Pesan WhatsApp otomatis ke pelanggan dari nomor toko sendiri, tanpa admin ketik manual.", detail: {
      ringkasan: "Pelanggan otomatis menerima pesan WhatsApp dari nomor toko Anda sendiri -- saat memilih pembayaran QRIS, saat pembayaran diverifikasi (manual maupun otomatis lewat Payment Gateway), dan saat booking dibatalkan. Admin tidak perlu chat satu-satu lagi, dan isi pesannya bisa diatur sesuai gaya toko sendiri.",
      poin: [
        "Reminder otomatis \"segera bayar\" saat pelanggan pilih QRIS",
        "Konfirmasi otomatis begitu pembayaran diverifikasi",
        "Notifikasi pembatalan otomatis kalau booking tidak dibayar tepat waktu",
        "Dikirim dari nomor WhatsApp toko sendiri, isi pesan bisa diatur bebas",
      ],
    } },
    { icon: "📍", title: "Employee Attendance", desc: "Barber Check In/Out sendiri lewat Aplikasi Barber, jarak ke toko diverifikasi otomatis.", detail: {
      ringkasan: "Barber Check In/Check Out sendiri lewat Aplikasi Barber -- lokasi GPS & jarak ke toko diverifikasi otomatis di backend, bukan sekadar klaim dari HP. Owner bisa pantau kehadiran, keterlambatan, sampai barber yang lupa Check In/Out dari satu dashboard.",
      poin: [
        "Barber Check In/Out sendiri lewat Aplikasi Barber, tanpa alat fingerprint",
        "Jarak ke toko dihitung & diverifikasi otomatis (radius bisa diatur)",
        "Status Tepat Waktu/Terlambat/Tidak Check In-Out otomatis terdeteksi",
        "Dashboard kehadiran seluruh barber real-time untuk Owner",
      ],
    } },
    { icon: "🗓️", title: "Calendar", desc: "Jadwal barber & slot tersedia terlihat jelas dalam satu kalender.", detail: {
      ringkasan: "Satu tampilan kalender menampilkan jadwal seluruh barber sekaligus, sehingga admin bisa memantau kepadatan toko dan menambah booking manual dengan cepat.",
      poin: [
        "Tampilan kalender harian/mingguan untuk seluruh barber sekaligus",
        "Slot kosong dan terisi terlihat jelas dengan warna berbeda",
        "Admin bisa tambah booking manual langsung dari kalender",
        "Memudahkan pantau jam-jam sibuk toko",
      ],
    } },
    { icon: "✂️", title: "Barber Schedule", desc: "Atur jadwal & hari libur tiap barber tanpa bentrok booking.", detail: {
      ringkasan: "Jam kerja dan hari libur tiap barber diatur masing-masing -- sistem otomatis menutup slot booking saat barber tidak tersedia, jadi tidak ada jadwal yang bentrok.",
      poin: [
        "Atur jam kerja & hari libur masing-masing barber",
        "Slot booking otomatis tertutup saat barber libur/cuti",
        "Tiap barber bisa punya jadwal berbeda tiap hari",
        "Mencegah booking pelanggan bentrok dengan jadwal barber",
      ],
    } },
    { icon: "👥", title: "Customer Management", desc: "Riwayat pelanggan tersimpan rapi untuk layanan yang lebih personal.", detail: {
      ringkasan: "Riwayat kunjungan dan layanan tiap pelanggan tersimpan otomatis, membantu barber memberikan layanan yang lebih personal dan membangun pelanggan yang loyal.",
      poin: [
        "Riwayat kunjungan & layanan tiap pelanggan tersimpan otomatis",
        "Barber bisa lihat preferensi/model favorit pelanggan",
        "Data kontak pelanggan tersentralisasi & mudah dicari",
        "Membantu membangun hubungan pelanggan yang lebih personal",
      ],
    } },
    { icon: "💳", title: "Payment Gateway", desc: "Pembayaran online terintegrasi Payment Gateway, aman & terpercaya.", detail: {
      ringkasan: "Pembayaran online terintegrasi langsung dengan Payment Gateway resmi -- status transaksi ter-update otomatis begitu pelanggan membayar, tanpa konfirmasi manual.",
      poin: [
        "Terintegrasi Payment Gateway resmi & aman",
        "Mendukung berbagai metode pembayaran dalam satu sistem",
        "Status pembayaran ter-update otomatis, tanpa konfirmasi manual",
        "Mengurangi risiko kesalahan pencatatan transaksi tunai",
      ],
    } },
    { icon: "📱", title: "QRIS", desc: "Terima pembayaran QRIS langsung dari pelanggan.", detail: {
      ringkasan: "Terima pembayaran QRIS dari semua e-wallet dan bank pendukung -- kode QR dibuat otomatis tiap transaksi, dan status langsung berubah \"Lunas\" begitu berhasil.",
      poin: [
        "Terima pembayaran QRIS dari semua e-wallet & bank pendukung",
        "Kode QR dibuat otomatis untuk tiap transaksi",
        "Status \"Lunas\" langsung ter-update begitu pembayaran berhasil",
        "Praktis untuk transaksi cepat di kasir maupun booking online",
      ],
    } },
    { icon: "🏦", title: "Virtual Account", desc: "Dukungan transfer Virtual Account dari berbagai bank.", detail: {
      ringkasan: "Nomor Virtual Account unik dibuat otomatis untuk tiap transaksi, mendukung transfer dari berbagai bank besar di Indonesia dengan verifikasi otomatis.",
      poin: [
        "Nomor Virtual Account unik dibuat otomatis tiap transaksi",
        "Mendukung transfer dari berbagai bank besar di Indonesia",
        "Verifikasi pembayaran otomatis, tanpa cek mutasi manual",
        "Cocok untuk pelanggan yang lebih nyaman transfer bank",
      ],
    } },
    { icon: "📊", title: "Reports", desc: "Laporan transaksi, komisi, dan pengeluaran otomatis.", detail: {
      ringkasan: "Laporan transaksi, komisi barber, dan pengeluaran/kasbon tercatat rapi dan bisa diunduh dalam format PDF kapan saja untuk kebutuhan administrasi.",
      poin: [
        "Laporan transaksi harian, mingguan, hingga bulanan otomatis",
        "Perhitungan komisi barber otomatis sesuai aturan toko",
        "Pengeluaran & kasbon tercatat rapi dalam satu laporan",
        "Bisa diunduh dalam format PDF untuk arsip/administrasi",
      ],
    } },
    { icon: "📈", title: "Analytics", desc: "Pantau performa toko dengan data yang mudah dibaca.", detail: {
      ringkasan: "Grafik pendapatan dan jumlah booking membantu owner memahami performa toko sekilas, membandingkan antar periode, dan mengambil keputusan berbasis data.",
      poin: [
        "Grafik pendapatan & jumlah booking mudah dipahami sekilas",
        "Bandingkan performa antar periode (harian/bulanan)",
        "Lihat layanan & barber paling laris",
        "Membantu ambil keputusan bisnis berbasis data, bukan tebakan",
      ],
    } },
    { icon: "🧑‍🤝‍🧑", title: "Multi Barber", desc: "Kelola banyak barber dalam satu toko tanpa batas.", detail: {
      ringkasan: "Tidak ada batas jumlah barber yang bisa didaftarkan -- tiap barber punya akun & jadwal masing-masing, dan booking otomatis terbagi sesuai jam yang tersedia.",
      poin: [
        "Tidak ada batas jumlah barber yang bisa didaftarkan",
        "Tiap barber punya akun & jadwal masing-masing",
        "Booking otomatis terbagi sesuai barber & jam yang tersedia",
        "Cocok untuk barbershop kecil maupun yang terus berkembang",
      ],
    } },
    { icon: "🏬", title: "Multi Tenant", desc: "Setiap toko punya data & pengaturan yang terisolasi penuh.", detail: {
      ringkasan: "Data tiap toko (tenant) terpisah total dan tidak tercampur satu sama lain -- cocok untuk pemilik yang punya lebih dari satu cabang atau brand barbershop.",
      poin: [
        "Data tiap toko (tenant) terpisah total, tidak tercampur",
        "Pengaturan, harga, dan brand bisa berbeda per toko",
        "Cocok untuk pemilik dengan lebih dari satu cabang/brand",
        "Keamanan data terjamin antar tenant",
      ],
    } },
    { icon: "📲", title: "PWA", desc: "Instal seperti aplikasi native di HP atau desktop.", detail: {
      ringkasan: "Bisa diinstal langsung dari browser tanpa lewat App Store/Play Store -- tampilan dan pengalamannya seperti aplikasi native, tapi tetap ringan.",
      poin: [
        "Bisa diinstal langsung dari browser, tanpa App Store/Play Store",
        "Tampilan & pengalaman seperti aplikasi native",
        "Tetap ringan karena tidak perlu instalasi besar",
        "Bisa diakses cepat dari layar utama HP atau desktop",
      ],
    } },
    { icon: "🔔", title: "Notification", desc: "Notifikasi booking & aktivitas penting secara real-time.", detail: {
      ringkasan: "Notifikasi booking baru dan aktivitas penting muncul secara real-time, membantu barber & admin merespons pelanggan lebih cepat tanpa harus cek manual.",
      poin: [
        "Notifikasi booking baru muncul secara real-time",
        "Barber & admin selalu update tanpa harus cek manual",
        "Mengurangi risiko booking terlewat",
        "Membantu respons lebih cepat ke pelanggan",
      ],
    } },
    { icon: "🖥️", title: "Dashboard", desc: "Satu dashboard untuk mengelola seluruh operasional toko.", detail: {
      ringkasan: "Semua fitur -- booking, barber, laporan, dan lainnya -- tersedia dalam satu dashboard dengan ringkasan performa toko yang langsung terlihat saat login.",
      poin: [
        "Semua fitur (booking, barber, laporan, dst) dalam satu tempat",
        "Ringkasan performa toko langsung terlihat saat login",
        "Navigasi simpel, tidak perlu berpindah-pindah sistem",
        "Cocok untuk owner yang ingin kontrol penuh dari satu layar",
      ],
    } },
  ];

  // Modal detail Fitur -- dipicu js/lp-slider.js onSelect (lihat renderFeatures()).
  function openFeatureDetail(f) {
    const body = [el("p", { class: "lp-modal-desc" }, f.detail ? f.detail.ringkasan : f.desc)];
    if (f.detail && f.detail.poin && f.detail.poin.length) {
      body.push(el("ul", { class: "lp-modal-list lp-modal-list-check" }, f.detail.poin.map((t) => el("li", {}, t))));
    }
    openDetailModal({ icon: f.icon, title: f.title, body });
  }

  function renderFeatures() {
    const container = document.getElementById("lp-features-slider");
    const track = container.querySelector(".lp-slider-track");
    track.innerHTML = "";
    FEATURES.forEach((f) => {
      track.appendChild(el("div", { class: "lp-slider-slide" }, [
        el("div", { class: "lp-feature-card" }, [
          el("div", { class: "lp-feature-icon" }, f.icon),
          el("h3", {}, f.title),
          el("p", {}, f.desc),
          el("span", { class: "lp-slide-detail-hint" }, "Lihat detail →"),
        ]),
      ]));
    });
    // onSelect: kartu di tengah diklik LAGI ("dipilih") -> buka modal detail.
    window.LpSlider.init(container, { onSelect: (i) => openFeatureDetail(FEATURES[i]) });
  }

  // ============================= Pricing (WAJIB dari database) =============================

  // FITUR Landing Page & Pricing (paket 6 bulan): siklus aktif disimpan di
  // luar renderPricing() supaya toggle Bulanan/6 Bulan bisa render ULANG
  // grid yang SAMA (packages sudah di-fetch sekali) tanpa fetch API lagi.
  let _siklusAktif = "bulanan";
  let _packagesTerkini = [];
  // Instance LpSlider Pricing yang sedang aktif -- disimpan di modul supaya
  // initCycleToggle() bisa destroy()-nya sebelum render ulang (cegah
  // listener menumpuk) sekaligus baca getActiveIndex() supaya toggle
  // Bulanan/6 Bulan tidak "melompat" balik ke paket pertama.
  let _pricingSlider = null;

  async function loadPackages() {
    const container = document.getElementById("lp-pricing-slider");
    try {
      const packages = await apiGet("/api/public/landing/packages");
      _packagesTerkini = packages;
      renderPricing(container, packages, _siklusAktif);
      initCycleToggle();
    } catch (e) {
      const track = container.querySelector(".lp-slider-track");
      track.innerHTML = "";
      track.appendChild(el("p", { class: "lp-loading" }, "Paket belum tersedia saat ini."));
      console.error(e);
    }
  }

  // FITUR Landing Page & Pricing (Enterprise Exclusive): benefit "Custom
  // Feature Request" HANYA untuk paket kode "enterprise" -- murni tampilan
  // (tidak ada toggle/fitur baru di subscription_features, lihat
  // spesifikasi item 5: pengajuan fitur khusus melalui proses evaluasi
  // TERPISAH dari sistem, bukan sesuatu yang di-otomasi di aplikasi ini).
  function benefitEnterprise() {
    return el("div", { class: "lp-enterprise-benefit" }, [
      el("span", { class: "lp-pricing-badge lp-pricing-badge-enterprise", style: "position:static;transform:none;display:inline-block;margin-bottom:8px;" }, "Enterprise Exclusive"),
      el("div", {}, [
        el("strong", {}, "Custom Feature Request — "),
        "ajukan pengembangan fitur khusus sesuai kebutuhan bisnis Anda. Setiap permintaan melalui proses evaluasi (tidak otomatis disetujui), dan permintaan yang disetujui diprioritaskan untuk pelanggan Enterprise.",
      ]),
    ]);
  }

  // Ingat paket (+ siklus) yang dipilih lewat sessionStorage (sama origin
  // dengan /app/, jadi tetap terbawa lintas navigasi) -- register.js/
  // billing.js membaca ini untuk menyorot paket & siklus yang sama begitu
  // Owner sampai di halaman Billing, supaya pilihan di Landing Page tidak
  // hilang begitu saja saat harus Register dulu. Dipakai BERSAMA oleh
  // tombol "Select Package" di kartu Pricing maupun di modal detail-nya.
  function buatTombolPilihPaket(kode, siklus, kelas) {
    const btn = el("a", { href: "/app/#/register", class: kelas || "lp-btn lp-btn-primary" }, "Select Package");
    btn.addEventListener("click", () => {
      try {
        sessionStorage.setItem("mugen_pending_package_kode", kode);
        sessionStorage.setItem("mugen_pending_package_siklus", siklus);
      } catch (e) { /* abaikan (mis. private mode) */ }
    });
    return btn;
  }

  // Modal detail Pricing -- dipicu js/lp-slider.js onSelect (lihat
  // renderPricing()). Isinya cermin dari kartu (harga sesuai siklus aktif,
  // deskripsi, benefit Enterprise, daftar fitur) PLUS tombol "Select
  // Package" sendiri di dalam modal supaya bisa langsung lanjut dari sana.
  function openPricingDetail(p, siklus) {
    const pakai6 = siklus === "6bulan" && p.harga > 0 && p.harga_6bulan;
    // FITUR Landing Page & Pricing (paket Tahunan, diminta Owner): pola SAMA
    // PERSIS pakai6 di atas -- HANYA aktif kalau toggle "tahunan" DAN paket
    // ini punya harga_tahunan (paket Free/harga 0, atau belum diisi Super
    // Admin, tetap menampilkan harga bulanan apa adanya).
    const pakaiTahunan = siklus === "tahunan" && p.harga > 0 && p.harga_tahunan;
    const hargaTampil = pakai6 ? p.harga_6bulan : pakaiTahunan ? p.harga_tahunan : p.harga;
    const labelDurasi = p.harga > 0 ? (pakai6 ? " / 6 bulan" : pakaiTahunan ? " / tahun" : ` / ${p.durasi_hari} hari`) : "";
    const hematRupiah = pakai6 ? (p.harga * 6 - p.harga_6bulan) : 0;
    // "Setara Rp X/bulan" -- dihitung langsung dari harga_tahunan/12 (TIDAK
    // ADA kolom terpisah untuk ini, konsisten dengan pola hematRupiah di
    // atas yang juga dihitung, bukan disimpan).
    const efektifBulananTahunan = pakaiTahunan ? Math.round(p.harga_tahunan / 12) : 0;
    const fitur = (p.fitur || []).map((f) => el("li", {}, f.nama));

    const body = [
      el("div", { class: "lp-modal-price" }, [
        hargaTampil > 0 ? formatRupiah(hargaTampil) : "Gratis",
        el("small", {}, labelDurasi),
      ]),
    ];
    if (pakai6 && hematRupiah > 0) {
      body.push(el("div", { class: "lp-pricing-save-note" }, `Hemat ${formatRupiah(hematRupiah)} dibanding bulanan`));
    }
    if (pakaiTahunan) {
      body.push(el("div", { class: "lp-pricing-save-note" }, `Setara ${formatRupiah(efektifBulananTahunan)}/bulan`));
      body.push(el("div", { class: "lp-pricing-save-note" }, "Hemat dengan pembayaran tahunan"));
    }
    body.push(el("p", { class: "lp-modal-desc" }, p.deskripsi || ""));
    if (p.kode === "enterprise") body.push(benefitEnterprise());
    body.push(el("ul", { class: "lp-modal-list lp-modal-list-check" }, fitur.length ? fitur : [el("li", {}, "-")]));

    openDetailModal({ title: p.nama, body, footer: buatTombolPilihPaket(p.kode, siklus, "lp-btn lp-btn-primary lp-btn-lg") });
  }

  function renderPricing(container, packages, siklus, activeIndex) {
    const track = container.querySelector(".lp-slider-track");
    track.innerHTML = "";
    packages.forEach((p) => {
      const fitur = (p.fitur || []).map((f) => el("li", {}, f.nama));
      const btnPilih = buatTombolPilihPaket(p.kode, siklus);

      // pakai6: paket ini BENAR-BENAR menampilkan harga 6 bulan sekarang --
      // hanya kalau toggle aktif "6bulan" DAN paket ini punya harga_6bulan
      // (paket Free/harga 0, atau paket yang belum diisi Super Admin, tetap
      // menampilkan harga bulanan apa adanya, TIDAK ada tampilan kosong/rusak).
      const pakai6 = siklus === "6bulan" && p.harga > 0 && p.harga_6bulan;
      // FITUR Landing Page & Pricing (paket Tahunan, diminta Owner): pola
      // SAMA PERSIS pakai6 di atas. pakai6/pakaiTahunan SALING EKSKLUSIF
      // (siklus toggle hanya satu nilai aktif), jadi urutan pengecekan di
      // bawah tidak masalah.
      const pakaiTahunan = siklus === "tahunan" && p.harga > 0 && p.harga_tahunan;
      const hargaTampil = pakai6 ? p.harga_6bulan : pakaiTahunan ? p.harga_tahunan : p.harga;
      const labelDurasi = p.harga > 0 ? (pakai6 ? " / 6 bulan" : pakaiTahunan ? " / tahun" : ` / ${p.durasi_hari} hari`) : "";
      const hematRupiah = pakai6 ? (p.harga * 6 - p.harga_6bulan) : 0;
      // "Setara Rp X/bulan" -- dihitung langsung dari harga_tahunan/12
      // (TIDAK ADA kolom terpisah untuk ini di database, angkanya PERSIS
      // hasil bagi harga_tahunan yang sama dipakai checkout).
      const efektifBulananTahunan = pakaiTahunan ? Math.round(p.harga_tahunan / 12) : 0;

      const card = el("div", {
        class: "lp-pricing-card" + (p.kode === "enterprise" ? " lp-pricing-card-featured" : ""),
      });
      // Badge ribbon kartu: "⭐ Paling Hemat" KHUSUS mode Tahunan (TIDAK
      // PERNAH memakai teks "Hemat Lebih Banyak", itu badge toggle tab --
      // lihat index.html), mode 6 Bulan TETAP "Paling Hemat" seperti
      // sebelumnya (TIDAK diubah sama sekali).
      if (pakaiTahunan) {
        card.appendChild(el("span", { class: "lp-pricing-badge lp-pricing-badge-save" }, "⭐ Paling Hemat"));
      } else if (pakai6 && hematRupiah > 0) {
        card.appendChild(el("span", { class: "lp-pricing-badge lp-pricing-badge-save" }, "Paling Hemat"));
      } else if (p.kode === "enterprise") {
        card.appendChild(el("span", { class: "lp-pricing-badge lp-pricing-badge-popular lp-pulse" }, "★ Paling Populer"));
      }
      card.appendChild(el("h3", {}, p.nama));
      card.appendChild(el("div", { class: "lp-pricing-price" }, [
        hargaTampil > 0 ? formatRupiah(hargaTampil) : "Gratis",
        el("small", {}, labelDurasi),
      ]));
      if (pakai6 && hematRupiah > 0) {
        card.appendChild(el("div", { class: "lp-pricing-save-note" }, `Hemat ${formatRupiah(hematRupiah)} dibanding bulanan`));
      }
      if (pakaiTahunan) {
        card.appendChild(el("div", { class: "lp-pricing-save-note" }, `Setara ${formatRupiah(efektifBulananTahunan)}/bulan`));
        card.appendChild(el("div", { class: "lp-pricing-save-note" }, "Hemat dengan pembayaran tahunan"));
      }
      card.appendChild(el("p", { class: "lp-pricing-desc" }, p.deskripsi || ""));
      if (p.kode === "enterprise") card.appendChild(benefitEnterprise());
      card.appendChild(el("ul", { class: "lp-pricing-features" }, fitur.length ? fitur : [el("li", {}, "-")]));
      card.appendChild(el("span", { class: "lp-slide-detail-hint" }, "Lihat detail paket →"));
      card.appendChild(btnPilih);
      track.appendChild(el("div", { class: "lp-slider-slide" }, [card]));
    });
    if (_pricingSlider) _pricingSlider.destroy();
    // onSelect: kartu di tengah diklik LAGI ("dipilih", di luar tombol
    // "Select Package" yang tetap berfungsi normal) -> buka modal detail
    // paket itu, dihitung ulang dari `packages`+`siklus` saat ini (BUKAN
    // dari _packagesTerkini/_siklusAktif modul supaya tetap benar kalau
    // suatu saat dipanggil dengan data yang belum "commit" ke variabel modul).
    _pricingSlider = window.LpSlider.init(container, { onSelect: (i) => openPricingDetail(packages[i], siklus) });
    if (_pricingSlider && typeof activeIndex === "number") {
      _pricingSlider.goTo(activeIndex, { instant: true });
    }
  }

  // FITUR Landing Page & Pricing (paket 6 bulan): toggle Bulanan/6 Bulan di
  // atas grid Pricing -- render ULANG slider yang sama (packages sudah di
  // memory) dengan siklus baru, TANPA fetch API lagi. Posisi (paket yang
  // sedang di tengah) dipertahankan lewat getActiveIndex()/goTo() supaya
  // toggle tidak "melompat" balik ke paket pertama. addEventListener
  // dipasang HANYA SEKALI (guard lewat dataset) karena loadPackages() bisa
  // saja dipanggil ulang di masa depan.
  function initCycleToggle() {
    const toggle = document.getElementById("lp-cycle-toggle");
    if (!toggle || toggle.dataset.wired === "1") return;
    toggle.dataset.wired = "1";
    toggle.querySelectorAll(".lp-cycle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        _siklusAktif = btn.dataset.siklus;
        toggle.querySelectorAll(".lp-cycle-btn").forEach((b) => {
          b.classList.toggle("lp-cycle-active", b === btn);
          b.setAttribute("aria-selected", b === btn ? "true" : "false");
        });
        const activeIndex = _pricingSlider ? _pricingSlider.getActiveIndex() : 0;
        renderPricing(document.getElementById("lp-pricing-slider"), _packagesTerkini, _siklusAktif, activeIndex);
      });
    });
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
  // FITUR Hubungi Kami Dinamis: HANYA dua field (Email & WhatsApp, lihat
  // landing_db.py::_CONTACT_KEYS) -- masing-masing dirender sebagai link
  // yang bisa langsung diklik (mailto:/wa.me), BUKAN teks statis. Field
  // yang kosong TIDAK ditampilkan sama sekali (bukan baris kosong).

  // wa.me butuh format internasional TANPA "+"/spasi/tanda hubung, dan
  // nomor Indonesia yang diketik dengan awalan "0" (kebiasaan lokal) perlu
  // diganti "62" (kode negara) -- SEKEDAR normalisasi tampilan link, TIDAK
  // mengubah/menyimpan ulang nilai yang tersimpan di database.
  function nomorWaMe(nomor) {
    let digit = String(nomor || "").replace(/\D/g, "");
    if (digit.startsWith("0")) digit = "62" + digit.slice(1);
    else if (!digit.startsWith("62")) digit = "62" + digit;
    return digit;
  }

  // Ikon Email/WhatsApp (BARU) -- SVG inline monoline, mengikuti gaya ikon
  // checkmark yang sudah dipakai di Hero (index.html .lp-hero-note svg),
  // BUKAN logo merek WhatsApp asli (murni ikon "pesan" generik + label teks
  // "WhatsApp" di sampingnya sudah cukup jelas, tanpa perlu meniru bentuk
  // logo resmi).
  const IKON_KONTAK = {
    email: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"></rect><polyline points="22,6 12,13 2,6"></polyline></svg>',
    whatsapp: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>',
  };

  async function loadContact() {
    const grid = document.getElementById("lp-contact-grid");
    try {
      const c = await apiGet("/api/public/landing/contact");
      grid.innerHTML = "";
      const items = [];
      if (c.platform_contact_email) {
        items.push(el("a", { href: `mailto:${c.platform_contact_email}`, class: "lp-contact-item lp-reveal" }, [
          el("div", { class: "lp-contact-icon", html: IKON_KONTAK.email }),
          el("div", { class: "lp-contact-label" }, "Email"),
          el("div", { class: "lp-contact-value" }, c.platform_contact_email),
        ]));
      }
      if (c.platform_contact_whatsapp) {
        items.push(el("a", {
          href: `https://wa.me/${nomorWaMe(c.platform_contact_whatsapp)}`, target: "_blank", rel: "noopener", class: "lp-contact-item lp-reveal",
        }, [
          el("div", { class: "lp-contact-icon", html: IKON_KONTAK.whatsapp }),
          el("div", { class: "lp-contact-label" }, "WhatsApp"),
          el("div", { class: "lp-contact-value" }, c.platform_contact_whatsapp),
        ]));
      }
      if (!items.length) {
        grid.appendChild(el("p", { class: "lp-loading" }, "Kontak belum diatur."));
        return;
      }
      items.forEach((item) => grid.appendChild(item));
      revealObserve(grid.querySelectorAll(".lp-reveal"));
    } catch (e) {
      grid.innerHTML = "";
      grid.appendChild(el("p", { class: "lp-loading" }, "Kontak belum tersedia."));
      console.error(e);
    }
  }

  // ============================= Footer (tagline dari Super Admin) =============================
  // HANYA tagline yang dinamis -- kolom link navigasi & teks copyright
  // TETAP hardcode di index.html (di luar cakupan permintaan). Tagline
  // hardcode yang sudah ada di index.html dibiarkan apa adanya kalau
  // Super Admin belum pernah mengisi (bukan kosong/rusak).

  async function loadFooter() {
    const taglineEl = document.getElementById("lp-footer-tagline");
    if (!taglineEl) return;
    try {
      const f = await apiGet("/api/public/landing/footer");
      if (f.platform_footer_tagline) taglineEl.textContent = f.platform_footer_tagline;
    } catch (e) {
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
    initSmoothAnchors();
    initScrollSpy();
    initDiffMockupAnimations();
    renderFeatures();
    loadPackages();
    loadFaq();
    loadContact();
    loadFooter();
    registerServiceWorker();
    // Elemen ".lp-reveal" statis (sudah ada di HTML sejak awal, mis. judul
    // section/timeline/screenshot mockup) -- yang ditambahkan dinamis lewat
    // render di atas (Pricing/FAQ/Contact) sudah diobservasi masing-masing
    // lewat revealObserve() di fungsi render-nya sendiri.
    initScrollReveal();
    // Deep link (URL sudah membawa hash, mis. dibagikan atau hasil klik
    // menu sebelum refresh): halaman sudah dipaksa ke atas duluan di atas,
    // sekarang baru diarahkan ke section itu dengan animasi scroll halus
    // milik sendiri -- BUKAN native anchor-jump instan bawaan browser.
    // Ditunda sampai event "load" (BUKAN langsung di sini/DOMContentLoaded)
    // supaya gambar (logo, ilustrasi HP, dst) sudah selesai dimuat dan
    // ukurannya sudah pasti -- kalau dihitung lebih awal, gambar yang baru
    // selesai dimuat belakangan bisa menggeser tinggi halaman DI ATAS
    // section tujuan pas animasi sedang berjalan, hasilnya tetap sedikit
    // meleset dari section yang benar.
    if (location.hash && document.querySelector(location.hash)) {
      window.addEventListener("load", () => scrollToHash(location.hash), { once: true });
    }
  });
})();
