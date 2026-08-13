// js/lp-slider.js — Landing Page publik: komponen carousel generik "center
// focus + peek" (satu slide besar di tengah, tetangga kiri/kanan mengintip
// mengecil/pudar) -- dipakai section Fitur & Pricing (lihat landing.js).
// Vanilla JS TANPA framework/library, konsisten dengan seluruh proyek ini
// (lihat catatan header landing.js). File ini TIDAK tahu apa pun soal
// konten/data section mana pun -- MURNI mekanika slider generik, supaya bisa
// dipakai ulang tanpa duplikasi (pemanggil yang membangun DOM slide-nya).
//
// Kontrak DOM yang diharapkan di dalam `container` (elemen `.lp-slider`):
//   .lp-slider-track            -- wajib, scrollable (overflow-x:auto,
//                                   scroll-snap-type:x mandatory di CSS),
//                                   berisi HANYA elemen `.lp-slider-slide`
//                                   (init() sendiri yang menambahkan spacer
//                                   kiri/kanan supaya slide pertama/terakhir
//                                   tetap bisa sampai ke tengah).
//   .lp-slider-arrow-prev/-next -- opsional, tombol <button> yang sudah ada.
//   .lp-slider-dots             -- opsional, container kosong (diisi satu
//                                   `.lp-slider-dot` per slide oleh init()).
//
// init(container, opts) menerima opts.onSelect(index, slideEl) opsional --
// dipanggil saat slide yang SUDAH aktif/di tengah diklik LAGI (atau
// Enter/Space saat track fokus), yaitu momen "planet dipilih" (lihat video
// referensi: klik pertama pada slide pinggir cuma menggeser ke tengah,
// klik/pilih LAGI baru "membuka menu"-nya) -- pemanggil yang memutuskan apa
// artinya "dipilih" itu (mis. buka modal detail), file ini TIDAK tahu.
//
// Native CSS scroll-snap dipakai sebagai mekanisme geser utama (drag/swipe
// touch & trackpad GRATIS dari browser, jauh lebih robust daripada
// reimplementasi drag-pointer manual) -- JS di sini HANYA menambahkan: efek
// scale/opacity berdasar jarak ke tengah, tombol panah/dot/keyboard, DAN
// drag mouse (pointerType "mouse" SAJA -- touch/pen dibiarkan native, lihat
// _pasangDragMouse() supaya tidak dobel-tangani gesture yang sama).

(function () {
  "use strict";

  const KURANGI_GERAK = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function scrollBehavior() {
    return KURANGI_GERAK ? "auto" : "smooth";
  }

  // opts.onSelect(index, slideEl) -- opsional, dipanggil saat slide yang
  // SUDAH aktif/di tengah diklik lagi (atau Enter/Space saat track fokus)
  // -- "memilih planet" itu sendiri, BEDA dari sekadar menggeser ke tengah.
  // Elemen interaktif di dalam slide (link/tombol/dst) TIDAK memicu ini,
  // supaya klik ke tombol seperti "Select Package" tetap berfungsi normal
  // (lihat onSlideClick di bawah).
  function init(container, opts) {
    const track = container.querySelector(".lp-slider-track");
    if (!track) return null;
    const onSelect = opts && opts.onSelect;

    // Spacer kiri/kanan (lebar dinamis, ikut CSS var --slide-w yang sama
    // dipakai slide) -- TANPA ini, scroll-snap-align:center pada slide
    // pertama/terakhir tidak akan pernah benar-benar sampai ke tengah
    // viewport (browser membatasi scroll sampai konten habis, bukan
    // sampai slide terakhir center).
    const spacerKiri = document.createElement("div");
    spacerKiri.className = "lp-slider-spacer";
    spacerKiri.setAttribute("aria-hidden", "true");
    const spacerKanan = spacerKiri.cloneNode();
    track.insertBefore(spacerKiri, track.firstChild);
    track.appendChild(spacerKanan);

    let slides = Array.from(track.querySelectorAll(".lp-slider-slide"));
    const arrowPrev = container.querySelector(".lp-slider-arrow-prev");
    const arrowNext = container.querySelector(".lp-slider-arrow-next");
    const dotsWrap = container.querySelector(".lp-slider-dots");

    let indexAktif = 0;
    let rafId = null;
    let hancurkan = false;

    function buatDots() {
      if (!dotsWrap) return;
      dotsWrap.innerHTML = "";
      slides.forEach((_, i) => {
        const dot = document.createElement("button");
        dot.type = "button";
        dot.className = "lp-slider-dot";
        dot.setAttribute("aria-label", `Slide ${i + 1} dari ${slides.length}`);
        dot.addEventListener("click", () => goTo(i));
        dotsWrap.appendChild(dot);
      });
    }

    function tandaiAktif(i) {
      indexAktif = i;
      slides.forEach((s, idx) => s.classList.toggle("lp-slide-active", idx === i));
      if (dotsWrap) {
        Array.from(dotsWrap.children).forEach((dot, idx) => dot.classList.toggle("lp-slider-dot-active", idx === i));
      }
      if (arrowPrev) arrowPrev.disabled = i === 0;
      if (arrowNext) arrowNext.disabled = i === slides.length - 1;
    }

    // Efek scale/opacity proporsional jarak tiap slide ke titik tengah
    // track -- dipanggil tiap event scroll (throttle lewat requestAnimationFrame
    // supaya tidak membebani main thread saat drag/swipe cepat).
    function perbaruiEfekJarak() {
      rafId = null;
      if (hancurkan || !slides.length) return;
      const trackRect = track.getBoundingClientRect();
      const tengahTrack = trackRect.left + trackRect.width / 2;
      let idxTerdekat = 0;
      let jarakTerkecil = Infinity;
      slides.forEach((slide, i) => {
        const r = slide.getBoundingClientRect();
        const tengahSlide = r.left + r.width / 2;
        const jarak = Math.abs(tengahTrack - tengahSlide);
        if (jarak < jarakTerkecil) { jarakTerkecil = jarak; idxTerdekat = i; }
        // Normalisasi jarak terhadap setengah lebar track -- 0 di tengah
        // persis, 1 begitu sudah sejauh setengah lebar track (kira-kira
        // posisi slide tetangga), dibatasi supaya tidak minus/lebih dari 1.
        const t = Math.min(1, jarak / (trackRect.width / 2 || 1));
        const scale = 1 - t * 0.18; // 1 -> 0.82
        const opacity = 1 - t * 0.5; // 1 -> 0.5
        slide.style.transform = `scale(${scale.toFixed(3)})`;
        slide.style.opacity = opacity.toFixed(3);
      });
      if (idxTerdekat !== indexAktif || !slides[indexAktif].classList.contains("lp-slide-active")) {
        tandaiAktif(idxTerdekat);
      }
    }

    function onScroll() {
      if (rafId != null) return;
      rafId = requestAnimationFrame(perbaruiEfekJarak);
    }
    track.addEventListener("scroll", onScroll, { passive: true });

    // BUGFIX kritis: scrollIntoView() menelusuri SEMUA ancestor yang bisa
    // discroll -- termasuk document/window itu sendiri, BUKAN cuma track
    // ini. Karena slider ini letaknya di bawah lipatan (section Fitur/
    // Pricing), goTo(0, {instant:true}) yang dipanggil saat init() (di
    // bawah, sebelum pengunjung sempat menggeser apa pun) ikut men-scroll
    // SELURUH HALAMAN ke bawah supaya slide pertama "terlihat" -- gejala
    // "pengunjung mendarat di tengah halaman, bukan di atas". Diganti
    // hitungan scroll horizontal MURNI di dalam track ini sendiri lewat
    // track.scrollTo() -- TIDAK PERNAH menyentuh scroll vertikal
    // document/window sama sekali, apa pun posisi slider di halaman.
    function goTo(i, opts) {
      const target = slides[Math.max(0, Math.min(slides.length - 1, i))];
      if (!target) return;
      const trackRect = track.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const selisihKeTengah = (targetRect.left + targetRect.width / 2) - (trackRect.left + trackRect.width / 2);
      track.scrollTo({
        left: track.scrollLeft + selisihKeTengah,
        behavior: (opts && opts.instant) ? "auto" : scrollBehavior(),
      });
    }

    if (arrowPrev) arrowPrev.addEventListener("click", () => goTo(indexAktif - 1));
    if (arrowNext) arrowNext.addEventListener("click", () => goTo(indexAktif + 1));

    // Keyboard: track sendiri yang fokus (tabindex diset di markup oleh
    // pemanggil) -- panah kiri/kanan pindah SATU slide, konsisten dengan
    // ekspektasi carousel pada umumnya.
    function onKeydown(e) {
      if (e.key === "ArrowLeft") { e.preventDefault(); goTo(indexAktif - 1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); goTo(indexAktif + 1); }
      else if ((e.key === "Enter" || e.key === " ") && onSelect) {
        // HANYA kalau fokus persis di track (bukan di link/tombol anak yang
        // ikut fokus lewat Tab) -- kalau tidak, Enter di tombol "Select
        // Package" akan ikut membuka detail alih-alih menjalankan tombolnya.
        if (e.target !== track) return;
        e.preventDefault();
        onSelect(indexAktif, slides[indexAktif]);
      }
    }
    track.addEventListener("keydown", onKeydown);

    // Klik pada slide yang sedang "mengintip" (bukan slide aktif) --
    // pindahkan ke tengah dulu, meniru interaksi klik planet di pinggir
    // pada referensi video (klik pertama = pilih mana yang mau dilihat,
    // BUKAN langsung membuka detail). Klik LAGI pada slide yang SUDAH aktif
    // (di tengah) baru memicu onSelect ("membuka menu/detail"-nya) --
    // KECUALI kliknya kena elemen interaktif (link/tombol/dst di
    // dalamnya, mis. "Select Package"), yang harus tetap berfungsi normal.
    function onSlideClick(e) {
      const slide = e.target.closest(".lp-slider-slide");
      if (!slide) return;
      const i = slides.indexOf(slide);
      if (i === -1) return;
      if (!slide.classList.contains("lp-slide-active")) {
        e.preventDefault();
        goTo(i);
        return;
      }
      if (!onSelect || e.target.closest("a, button, input, select, textarea, label")) return;
      onSelect(i, slide);
    }
    track.addEventListener("click", onSlideClick, true);

    // Drag mouse desktop -- HANYA pointerType "mouse" (touch/pen dibiarkan
    // scroll native bawaan browser, supaya gesture yang sama tidak ditangani
    // dua kali/saling tabrak). PENTING: drag (setPointerCapture, matikan
    // scroll-snap) HANYA diaktifkan setelah pointer bergerak melewati
    // AMBANG_DRAG px -- BUKAN langsung di pointerdown. Kalau langsung di
    // pointerdown, setPointerCapture akan membajak SEMUA klik mouse di
    // dalam track (termasuk klik tombol "Select Package"/link di slide
    // aktif) karena browser mengarahkan ulang urutan event mouseup/click
    // ke elemen yang meng-capture, bukan ke target aslinya -- klik biasa
    // (tanpa gerakan berarti) jadi HARUS dibiarkan lewat native supaya
    // tombol/link di dalam slide tetap berfungsi.
    const AMBANG_DRAG = 6;
    let siapDrag = false;
    let sedangDrag = false;
    let mulaiX = 0;
    let mulaiScrollLeft = 0;
    let pointerIdAktif = null;
    function onPointerDown(e) {
      if (e.pointerType !== "mouse") return;
      siapDrag = true;
      sedangDrag = false;
      mulaiX = e.clientX;
      mulaiScrollLeft = track.scrollLeft;
      pointerIdAktif = e.pointerId;
    }
    function onPointerMove(e) {
      if (!siapDrag || e.pointerId !== pointerIdAktif) return;
      if (!sedangDrag) {
        if (Math.abs(e.clientX - mulaiX) < AMBANG_DRAG) return;
        sedangDrag = true;
        track.style.scrollSnapType = "none";
        track.classList.add("lp-slider-dragging");
        track.setPointerCapture(pointerIdAktif);
      }
      track.scrollLeft = mulaiScrollLeft - (e.clientX - mulaiX);
    }
    function onPointerUp(e) {
      if (!siapDrag || e.pointerId !== pointerIdAktif) return;
      siapDrag = false;
      if (sedangDrag) {
        sedangDrag = false;
        track.classList.remove("lp-slider-dragging");
        track.style.scrollSnapType = "";
        try { track.releasePointerCapture(pointerIdAktif); } catch (err) { /* abaikan */ }
        goTo(indexAktif); // snap presisi ke slide terdekat setelah drag manual
      }
      pointerIdAktif = null;
    }
    track.addEventListener("pointerdown", onPointerDown);
    track.addEventListener("pointermove", onPointerMove);
    track.addEventListener("pointerup", onPointerUp);
    track.addEventListener("pointercancel", onPointerUp);

    buatDots();
    // Posisi awal (slide pertama di tengah) + hitungan efek jarak pertama
    // kali -- goTo() sendiri memicu event "scroll" yang memanggil
    // perbaruiEfekJarak(), tapi dipanggil eksplisit juga di sini supaya
    // status awal (tombol panah/dot aktif) benar SEBELUM user berinteraksi
    // sama sekali (kalau slide pertama kebetulan sudah center secara alami).
    goTo(0, { instant: true });
    perbaruiEfekJarak();

    function destroy() {
      hancurkan = true;
      if (rafId != null) cancelAnimationFrame(rafId);
      track.removeEventListener("scroll", onScroll);
      track.removeEventListener("keydown", onKeydown);
      track.removeEventListener("click", onSlideClick, true);
      track.removeEventListener("pointerdown", onPointerDown);
      track.removeEventListener("pointermove", onPointerMove);
      track.removeEventListener("pointerup", onPointerUp);
      track.removeEventListener("pointercancel", onPointerUp);
    }

    return {
      goTo,
      getActiveIndex: () => indexAktif,
      destroy,
    };
  }

  window.LpSlider = { init };
})();
