// pages/book_public.js — Halaman PUBLIK "/book" (hash #/book), TANPA LOGIN.
// Dirender LANGSUNG ke #app (bukan lewat MugenRouter.shell()) -- tidak ada
// sidebar/menu, karena ini bukan bagian dari aplikasi internal. Semua data
// diambil dari endpoint /api/public/booking/* (lihat routers/booking.py) --
// endpoint itu sengaja hanya membocorkan info yang memang boleh dilihat
// siapa saja (nama barber, nama/harga/durasi service, jam operasional,
// ketersediaan slot, info pembayaran) -- TIDAK ADA data toko yang sensitif.

const PageBookPublic = (() => {
  const HARI = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
  const HARI_KEY = ["minggu", "senin", "selasa", "rabu", "kamis", "jumat", "sabtu"]; // index = Date.getDay()
  const BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember"];

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

  // REVISI: tombol "Download QRIS" -- ambil filename asli (dengan ekstensi
  // asli, sama seperti file yang diunggah admin lewat Setting) dari query
  // string "?v=" pada qris_url (lihat booking_db.py: qris_url selalu
  // berformat "/api/public/booking/qris?v=<nama_file_asli>").
  function namaFileDariUrl(qrisUrl) {
    const q = (qrisUrl || "").split("?")[1] || "";
    return new URLSearchParams(q).get("v") || "qris.png";
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

  // REVISI UI/UX: Halaman Awal Web Booking -- HANYA tombol besar "BOOKING"
  // (tanpa logo), kata "BOOKING" terbang cepat dari sudut layar ke tengah
  // lewat lintasan Z dengan motion blur (lihat @keyframes book-intro-fly di
  // style.css), lalu setelah ditekan baru wizard booking yang sudah ada
  // (renderWizard, TIDAK diubah logikanya) dimuat dengan Slide+Fade.
  function render(root) {
    root.innerHTML = "";
    // REVISI UI/UX (Dark Mode): lapis pertahanan KEDUA di sisi JS -- router.js
    // sudah memanggil MugenTheme.forceLight() sebelum PageBookPublic.render()
    // dipanggil, tapi dipanggil ulang di sini juga supaya halaman ini tetap
    // benar walau suatu saat dipanggil dari jalur lain.
    if (typeof MugenTheme !== "undefined") MugenTheme.forceLight();

    const intro = MugenUI.el("div", { class: "book-public book-intro" });
    root.appendChild(intro);

    const btnBooking = MugenUI.el("button", { class: "book-intro-btn", type: "button", disabled: true }, "BOOKING");
    intro.appendChild(btnBooking);

    const reduced = prefersReducedMotionGlobal();
    if (reduced) {
      btnBooking.disabled = false;
    } else {
      btnBooking.classList.add("book-intro-flying");
      const siap = () => {
        btnBooking.classList.add("book-intro-settled");
        btnBooking.disabled = false;
      };
      btnBooking.addEventListener("animationend", siap, { once: true });
      // jaga-jaga kalau animationend tidak pernah terpicu (mis. tab background)
      setTimeout(siap, 1100);
    }

    btnBooking.addEventListener("click", () => {
      if (btnBooking.disabled) return;
      intro.classList.add("book-intro-leaving");
      setTimeout(() => {
        intro.remove();
        renderWizard(root);
      }, reduced ? 0 : 220);
    });
  }

  async function renderWizard(root) {
    const page = MugenUI.el("div", { class: "book-public book-wizard-enter" });
    root.appendChild(page);

    const header = MugenUI.el("div", { class: "book-header" });
    page.appendChild(header);

    const progressBox = MugenUI.el("div", { class: "book-progress" });
    const bodyViewport = MugenUI.el("div", { class: "book-body-viewport" });
    const body = MugenUI.el("div", { class: "book-body" });
    bodyViewport.appendChild(body);
    const footer = MugenUI.el("div", { class: "book-footer" });
    page.appendChild(progressBox);
    page.appendChild(bodyViewport);
    page.appendChild(footer);

    // ---- state ----
    let step = 1;
    const TOTAL_STEP = 6; // Barber, Tanggal, Jam, Service, Data Diri, Ringkasan+Bayar
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

    try {
      [pengaturan, barbers, services] = await Promise.all([
        MugenApi.get("/api/public/booking/pengaturan"),
        MugenApi.get("/api/public/booking/barbers"),
        MugenApi.get("/api/public/booking/services"),
        MugenBrand.refresh(),
      ]);
    } catch (e) {
      body.appendChild(MugenUI.el("div", { class: "card" }, "Gagal memuat halaman booking: " + e.message));
      return;
    }

    const identitas = MugenBrand.get();

    header.innerHTML = "";
    if (identitas.banner_url) {
      // REVISI: sembunyikan dulu sampai TERBUKTI berhasil dimuat (onload),
      // dan tetap sembunyi (bukan ikon broken-image) kalau gagal (onerror) --
      // banner sudah di-preload lewat brand.js sejak identitas didapat, jadi
      // pada praktiknya ini biasanya langsung "onload" instan dari cache.
      const bannerImg = MugenUI.el("img", { class: "book-banner-img", style: "display:none;", alt: "Banner" });
      bannerImg.onload = () => { bannerImg.style.display = ""; };
      bannerImg.onerror = () => { bannerImg.style.display = "none"; bannerImg.removeAttribute("src"); };
      bannerImg.src = MUGEN_API_BASE + identitas.banner_url;
      header.appendChild(bannerImg);
    }
    header.appendChild(MugenUI.el("h1", {}, pengaturan.header_judul || identitas.nama_barbershop || "MUGEN Hair Co."));
    header.appendChild(MugenUI.el("div", { class: "subtitle" }, pengaturan.header_subtitle || identitas.tagline || "Booking Online"));
    if (pengaturan.pesan_pembuka) {
      header.appendChild(MugenUI.el("div", { class: "book-pesan-pembuka" }, pengaturan.pesan_pembuka));
    }

    footer.innerHTML = "";
    if (pengaturan.header_footer) {
      footer.appendChild(MugenUI.el("div", {}, pengaturan.header_footer));
    }

    function renderProgress() {
      progressBox.innerHTML = "";
      progressBox.appendChild(MugenUI.el("div", {}, `Langkah ${Math.min(step, TOTAL_STEP)} dari ${TOTAL_STEP}`));
    }

    // ---- animasi perpindahan step: slide + fade, ~300ms, arah mengikuti
    // maju/mundurnya nomor step (goto ke step lebih besar = "Lanjut" = slide
    // dari kanan, goto ke step lebih kecil = "Kembali" = slide dari kiri).
    // Selama animasi berjalan, transitioning=true membuat goto() lain
    // diabaikan -- ini SATU-SATUNYA tempat penjagaan double-klik perlu
    // ditambahkan karena semua tombol navigasi step memanggil goto().
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
      if (step === 1) renderPilihBarber();
      else if (step === 2) renderPilihTanggal();
      else if (step === 3) renderPilihJam();
      else if (step === 4) renderPilihService();
      else if (step === 5) renderDataDiri();
      else if (step === 6) renderRingkasanBayar();
      else if (step === 7) renderSelesai();
    }

    function renderAll(arah) {
      renderProgress();
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

    // ================= STEP 1: PILIH BARBER =================
    function renderPilihBarber() {
      body.appendChild(MugenUI.el("h2", {}, "Pilih Barber"));
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
        body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada barber yang bisa dibooking saat ini."));
      }
    }

    // ================= STEP 2: PILIH TANGGAL (kalender visual) =================
    function renderPilihTanggal() {
      body.appendChild(MugenUI.el("h2", {}, `Pilih Tanggal — ${state.barberNama}`));
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
        const startOffset = firstDay.getDay(); // 0=Min
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
            title: tokoLibur ? "Toko libur" : (bukanHariOperasional ? "Di luar hari operasional" : ""),
          }, String(d));
          if (nonaktif) {
            cell.disabled = true;
          } else {
            cell.addEventListener("click", () => {
              state.tanggal = iso;
              state.jam = null;
              goto(3);
            });
          }
          grid.appendChild(cell);
        }
        calCard.appendChild(grid);
      }
      renderKalender();

      body.appendChild(MugenUI.el("div", { class: "row book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(1) }, "‹ Ganti Barber"),
      ]));
    }

    // ================= STEP 3: PILIH JAM =================
    async function renderPilihJam() {
      body.appendChild(MugenUI.el("h2", {}, `Pilih Jam — ${MugenUI.formatTanggal(state.tanggal)}`));
      const slotBox = MugenUI.el("div");
      body.appendChild(slotBox);
      slotBox.innerHTML = "Memuat jam tersedia...";

      let data;
      try {
        data = await MugenApi.get(`/api/public/booking/slot?barber_id=${state.barberId}&tanggal=${state.tanggal}`);
      } catch (e) {
        slotBox.innerHTML = "";
        slotBox.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
        return;
      }
      slotBox.innerHTML = "";

      if (data.barber_libur) {
        slotBox.appendChild(MugenUI.el("div", { class: "book-warning" },
          `${state.barberNama} sedang libur pada tanggal ini. Silakan pilih tanggal lain atau ganti barber.`));
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
              goto(4);
            });
          } else {
            btn.disabled = true;
          }
          grid.appendChild(btn);
        }
        slotBox.appendChild(grid);
        slotBox.appendChild(MugenUI.el("div", { class: "book-legend" }, [
          MugenUI.el("span", { class: "book-legend-item" }, [MugenUI.el("span", { class: "book-dot book-slot-available" }), " Tersedia"]),
          MugenUI.el("span", { class: "book-legend-item" }, [MugenUI.el("span", { class: "book-dot book-slot-booked" }), " Sudah Dibooking"]),
          MugenUI.el("span", { class: "book-legend-item" }, [MugenUI.el("span", { class: "book-dot book-slot-closed" }), " Tutup"]),
        ]));
        if (!data.slots.some((s) => s.status === "available")) {
          slotBox.appendChild(MugenUI.el("div", { class: "book-warning" }, "Tidak ada jam tersedia pada tanggal ini. Silakan pilih tanggal lain."));
        }
      }

      body.appendChild(MugenUI.el("div", { class: "row book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(2) }, "‹ Ganti Tanggal"),
      ]));
    }

    // ================= STEP 4: PILIH SERVICE (boleh lebih dari satu) =================
    function renderPilihService() {
      body.appendChild(MugenUI.el("h2", {}, "Pilih Service"));
      const listBox = MugenUI.el("div", { class: "book-service-list" });
      const totalBox = MugenUI.el("div", { class: "book-service-total" });
      const errorBox = MugenUI.el("div", { class: "login-error" });

      function updateTotal() {
        const dipilih = services.filter((s) => state.serviceIds.includes(s.id));
        const totalHarga = dipilih.reduce((a, s) => a + s.harga, 0);
        const totalDurasi = dipilih.reduce((a, s) => a + s.durasi_menit, 0);
        totalBox.innerHTML = "";
        if (dipilih.length) {
          totalBox.appendChild(MugenUI.el("div", {}, `${dipilih.length} service dipilih — Total ${MugenUI.formatRupiah(totalHarga)} (± ${totalDurasi} menit)`));
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
            MugenUI.el("div", { class: "subtitle" }, `${MugenUI.formatRupiah(s.harga)} · ${s.durasi_menit} menit`),
          ]),
        ]);
        listBox.appendChild(row);
      }
      body.appendChild(listBox);
      updateTotal();
      body.appendChild(totalBox);
      body.appendChild(errorBox);

      const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button" }, "Lanjut");
      btnLanjut.addEventListener("click", async () => {
        errorBox.textContent = "";
        if (!state.serviceIds.length) {
          errorBox.textContent = "Pilih minimal satu service.";
          return;
        }
        // Validasi ulang: total durasi dari service yang dipilih mungkin butuh
        // lebih dari satu slot -- pastikan span PENUH dari jam yang sudah
        // dipilih di Step 3 masih benar-benar kosong semua.
        btnLanjut.disabled = true;
        try {
          const cek = await MugenUI.withLoading(() => MugenApi.get(
            `/api/public/booking/slot?barber_id=${state.barberId}&tanggal=${state.tanggal}&service_ids=${state.serviceIds.join(",")}`,
          ), { message: "Memeriksa ketersediaan jam…" });
          const slotJam = cek.slots.find((s) => s.jam === state.jam);
          if (!slotJam || slotJam.status !== "available") {
            errorBox.textContent = `Durasi total service ini (${cek.durasi_menit} menit) butuh jam yang sudah terpakai. Silakan pilih jam lain.`;
            return;
          }
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
          return;
        } finally {
          btnLanjut.disabled = false;
        }
        goto(5);
      });
      body.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnLanjut));

      body.appendChild(MugenUI.el("div", { class: "row book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(3) }, "‹ Ganti Jam"),
      ]));
    }

    // ================= STEP 5: DATA DIRI (Nama + WhatsApp) =================
    function renderDataDiri() {
      body.appendChild(MugenUI.el("h2", {}, "Data Diri"));
      const inputNama = MugenUI.el("input", { type: "text", placeholder: "Nama lengkap", value: state.nama });
      const inputWa = MugenUI.el("input", { type: "tel", placeholder: "08xxxxxxxxxx", value: state.whatsapp });
      const errorBox = MugenUI.el("div", { class: "login-error" });

      body.appendChild(MugenUI.el("label", {}, "Nama"));
      body.appendChild(inputNama);
      body.appendChild(MugenUI.el("label", {}, "Nomor WhatsApp"));
      body.appendChild(inputWa);
      body.appendChild(errorBox);

      const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button" }, "Lanjut");
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

      body.appendChild(MugenUI.el("div", { class: "row book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(4) }, "‹ Ganti Service"),
      ]));
    }

    // ================= STEP 6: RINGKASAN + FULL PAYMENT =================
    function renderRingkasanBayar() {
      body.appendChild(MugenUI.el("h2", {}, "Ringkasan Booking"));

      const dipilih = services.filter((s) => state.serviceIds.includes(s.id));
      const totalHarga = dipilih.reduce((a, s) => a + s.harga, 0);

      const ringkasan = MugenUI.el("div", { class: "card" }, [
        baris("Barber", state.barberNama),
        baris("Tanggal", MugenUI.formatTanggal(state.tanggal)),
        baris("Jam", state.jam),
        baris("Service", dipilih.map((s) => s.nama).join(", ")),
        baris("Nama", state.nama),
        baris("WhatsApp", state.whatsapp),
        MugenUI.el("hr"),
        baris("Total Pembayaran", MugenUI.formatRupiah(totalHarga), true),
      ]);
      body.appendChild(ringkasan);

      function baris(label, value, tebal) {
        return MugenUI.el("div", { style: "display:flex;justify-content:space-between;padding:4px 0;" + (tebal ? "font-weight:700;" : "") }, [
          MugenUI.el("span", { style: "color:var(--text-dim);" }, label),
          MugenUI.el("span", {}, value),
        ]);
      }

      body.appendChild(MugenUI.el("h2", { style: "margin-top:24px;" }, "Metode Pembayaran (Full Payment)"));
      const metodeBox = MugenUI.el("div", { class: "book-metode-list" });
      body.appendChild(metodeBox);
      const detailBox = MugenUI.el("div", { style: "margin-top:12px;" });
      body.appendChild(detailBox);
      const errorBox = MugenUI.el("div", { class: "login-error" });

      const metodeNama = pengaturan.metode_nama || {};
      const metodeInstruksi = pengaturan.metode_instruksi || {};

      function renderDetailMetode() {
        detailBox.innerHTML = "";
        if (state.metode === "transfer") {
          detailBox.appendChild(MugenUI.el("div", { class: "card" }, [
            MugenUI.el("div", {}, `Bank: ${pengaturan.bank_nama || "-"}`),
            MugenUI.el("div", {}, `No. Rekening: ${pengaturan.bank_nomor_rekening || "-"}`),
            MugenUI.el("div", {}, `A/N: ${pengaturan.bank_nama_pemilik || "-"}`),
            MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" }, metodeInstruksi.transfer || ""),
          ]));
        } else if (state.metode === "qris") {
          const items = [];
          if (pengaturan.qris_url) {
            const qrisFullUrl = MUGEN_API_BASE + pengaturan.qris_url;
            items.push(MugenUI.el("img", { src: qrisFullUrl, class: "book-qris-img", alt: "QRIS" }));
            const btnDownload = MugenUI.el("button", { type: "button", style: "display:block;margin:8px auto 0;" }, "Download QRIS");
            btnDownload.addEventListener("click", () => unduhGambar(qrisFullUrl, namaFileDariUrl(pengaturan.qris_url)));
            items.push(btnDownload);
          }
          items.push(MugenUI.el("div", {}, pengaturan.qris_merchant_nama || ""));
          items.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:8px;" }, metodeInstruksi.qris || ""));
          detailBox.appendChild(MugenUI.el("div", { class: "card" }, items));
        } else if (state.metode === "cash") {
          detailBox.appendChild(MugenUI.el("div", { class: "card" }, metodeInstruksi.cash || ""));
        } else if (state.metode === "gateway") {
          detailBox.appendChild(MugenUI.el("div", { class: "card" }, metodeInstruksi.gateway || ""));
        }
      }

      // REVISI: kalau hanya SATU metode pembayaran yang aktif, langsung
      // pakai itu tanpa customer perlu memilih -- selector metode (metodeBox)
      // hanya ditampilkan kalau ada 2+ metode aktif. Dengan 0 metode aktif,
      // perilaku lama (pesan "Belum ada metode aktif") dipertahankan persis.
      const metodeAktif = pengaturan.metode_aktif || [];
      if (!metodeAktif.length) {
        metodeBox.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada metode pembayaran aktif. Hubungi barbershop."));
      } else if (metodeAktif.length === 1) {
        state.metode = metodeAktif[0];
        renderDetailMetode();
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
            renderDetailMetode();
          });
          metodeBox.appendChild(btn);
        }
      }
      body.appendChild(errorBox);

      const btnKonfirmasi = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" }, "Konfirmasi Booking");
      btnKonfirmasi.addEventListener("click", async () => {
        errorBox.textContent = "";
        if (!state.metode) { errorBox.textContent = "Pilih metode pembayaran dulu."; return; }
        if (state.metode === "gateway") { errorBox.textContent = "Payment Gateway belum tersedia, pilih metode lain."; return; }
        btnKonfirmasi.disabled = true;
        try {
          const hasil = await MugenUI.withLoading(() => MugenApi.post("/api/public/booking", {
            barber_id: state.barberId, tanggal: state.tanggal, jam_mulai: state.jam,
            service_ids: state.serviceIds, customer_nama: state.nama, customer_whatsapp: state.whatsapp,
            metode_pembayaran: state.metode,
          }), { message: "Memproses booking…" });
          state.bookingResult = hasil;
          goto(7);
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        } finally {
          btnKonfirmasi.disabled = false;
        }
      });
      body.appendChild(btnKonfirmasi);

      body.appendChild(MugenUI.el("div", { class: "row book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => goto(5) }, "‹ Ganti Data Diri"),
      ]));
    }

    // ================= STEP 7: SELESAI =================
    function renderSelesai() {
      const r = state.bookingResult;
      const detail = MugenUI.el("div", { class: "book-selesai-detail" }, [
        fieldRow("Barber", r.nama_barber),
        fieldRow("Tanggal", MugenUI.formatTanggal(r.tanggal)),
        fieldRow("Jam", r.jam_mulai),
        fieldRow("Service", r.daftar_service),
        MugenUI.el("hr"),
        fieldRow("Total", MugenUI.formatRupiah(r.total_harga), true),
      ]);
      body.appendChild(MugenUI.el("div", { class: "card book-selesai" }, [
        MugenUI.el("div", { class: "book-selesai-icon" }, "✓"),
        MugenUI.el("h2", {}, "Booking Berhasil!"),
        detail,
        MugenUI.el("div", { class: "subtitle", style: "margin-top:12px;" },
          pengaturan.pesan_penutup || "Terima kasih! Kami akan segera menghubungi Anda lewat WhatsApp untuk konfirmasi."),
      ]));
      const btnBaru = MugenUI.el("button", { class: "btn-primary", type: "button", style: "margin-top:16px;" }, "Buat Booking Baru");
      btnBaru.addEventListener("click", () => {
        state.barberId = null; state.barberNama = ""; state.tanggal = null; state.jam = null;
        state.serviceIds = []; state.nama = ""; state.whatsapp = ""; state.metode = null;
        goto(1);
      });
      body.appendChild(btnBaru);
    }

    renderAll();
  }

  return { render };
})();
