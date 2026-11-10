// pages/dashboard_owner.js
// REVISI: kartu "Bonus Kehadiran" dihapus (fitur Bonus Kehadiran dihapus
// total); ditambah kartu "Total Customer", bagian "Progress Target
// Service", dan "Service Bulan Ini" (dengan dropdown pilihan barber).
// REVISI Hak Akses Admin:
// - Kartu "Total Pendapatan Barber" DIHAPUS (nilainya sama persis dengan
//   "Total Komisi Barber" -- dua kartu untuk satu angka yang sama).
// - REVISI ("hilangkan fitur untuk menyembunyikan nilai kartu"): fitur
//   collapse/expand per kartu (klik judul untuk sembunyikan nilainya,
//   status tersimpan di localStorage) DIHAPUS TOTAL -- nilai kartu SELALU
//   tampil, tidak ada lagi panah/klik untuk sembunyikan. Tombol "Collapse
//   All"/"Expand All" (pengatur semua kartu sekaligus) SUDAH LEBIH DULU
//   dihapus (permintaan Owner terpisah, "bagian atas berantakan").
// - Halaman ini SEKARANG JUGA dipakai untuk role 'staff' (Admin, lihat
//   router.js::resolveDashboardPage) -- backend (routers/dashboard.py)
//   sudah memfilter field yang tidak diizinkan Owner jadi `null` untuk
//   role ini, dan mengosongkan `per_barber` sama sekali. Kartu dengan
//   nilai `null` TIDAK dirender sama sekali (bukan ditampilkan sebagai
//   "Rp 0", supaya tidak menyesatkan), dan bagian "SERVICE BULAN INI"/
//   "Grafik Pendapatan" (di luar cakupan Dashboard Admin, lihat
//   spesifikasi) hanya dirender untuk role 'admin' (Owner).
// REVISI (PERMINTAAN Owner): tabel "Per Barber" (ringkasan Komisi/Tips/
//   Uang Harian/Bonus Customer/Total per baris barber) DIHAPUS PERMANEN --
//   lihat catatan lengkap di dekat bagian "SERVICE BULAN INI" di bawah.

const PageDashboardOwner = (() => {
  // PERMINTAAN OWNER: simpan hasil fetch TERAKHIR (in-memory, hilang kalau
  // app di-reload) supaya kalau Dashboard dibuka lagi tanpa ada data baru
  // (lihat MugenState.dashboardPerluRefresh()), halaman bisa langsung
  // dirender ulang dari sini TANPA fetch/skeleton sama sekali. Disimpan di
  // LUAR render() (modul-level) supaya bertahan lintas navigasi menu;
  // `userId` dicocokkan supaya tidak salah pakai cache akun lain kalau ada
  // logout+login user berbeda tanpa reload app.
  let _cacheTerakhir = null; // { userId, url, data } | null

  function _ambilDariCache(userId, url) {
    if (!_cacheTerakhir) return null;
    if (_cacheTerakhir.userId !== userId || _cacheTerakhir.url !== url) return null;
    return _cacheTerakhir.data;
  }

  // FITUR "Dashboard tidak perlu refresh semua, cukup data yang berubah
  // saja" (PERMINTAAN Owner): dipanggil dari halaman lain (booking.js/
  // input_data.js, lazy-loaded via page_loader.js -- guard typeof WAJIB di
  // pemanggil) begitu ada data baru yang memengaruhi angka Dashboard (booking
  // lunas, transaksi Input Data baru/dikoreksi). HANYA menyegarkan
  // _cacheTerakhir di LATAR BELAKANG (fetch ulang url yang SAMA terakhir
  // kali Dashboard dimuat) -- TIDAK PERNAH menyentuh DOM (Dashboard, kalau
  // sedang dilihat, PASTI bukan halaman yang memicu ini -- SPA satu-halaman-
  // aktif-sekaligus, trigger-nya datang dari menu LAIN). Begitu selesai,
  // ditandai "bersih" (MugenState.tandaiDashboardBersih()) supaya next
  // kali user BENAR-BENAR membuka Dashboard, cache-hit yang SUDAH ADA
  // (lihat load() di bawah) langsung menampilkan angka terbaru INSTAN
  // TANPA skeleton -- bukan skeleton+fetch penuh seperti sebelumnya begitu
  // ada data baru di tempat lain. Belum pernah dibuka sesi ini (_cacheTerakhir
  // null) -> no-op aman, tidak ada apa pun yang perlu disegarkan.
  async function refreshDiamDiam() {
    if (!_cacheTerakhir) return;
    try {
      const data = await MugenApi.get(_cacheTerakhir.url);
      if (data.__offline) return; // bukan data sungguhan, jangan timpa cache yang valid
      _cacheTerakhir = { userId: _cacheTerakhir.userId, url: _cacheTerakhir.url, data };
      MugenState.tandaiDashboardBersih();
    } catch (e) {
      // best-effort -- diam saja, Dashboard tetap benar begitu dibuka manual
      // (dirty flag TIDAK ditandai bersih kalau refresh diam-diam ini gagal).
    }
  }

  async function render(root) {
    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" ke menu
    // Dashboard -- tampilkan HANYA pesan kosong, tidak fetch/tampilkan
    // kartu apa pun. Kartu PER-FIELD (izin_dashboard_*) tetap jalan seperti
    // sebelumnya begitu level di atas "none" -- dua sistem izin berbeda,
    // level menu ini menggerbang SELURUH halaman, izin_dashboard_* di
    // bawahnya menggerbang kartu MANA yang tampil.
    if ((await MugenMenuAccess.get("dashboard")) === "none") {
      root.innerHTML = "";
      root.appendChild(MugenUI.pageTitle("Dashboard", MugenIcons.dashboard));
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const today = new Date();
    let tahun = today.getFullYear();
    let bulan = today.getMonth() + 1;
    const isOwner = MugenState.getUser().role === "admin";

    // FITUR BARU (diminta Owner): mode "Periode" -- rentang tanggal bebas
    // (mis. 1-10 Agustus), berdampingan dengan mode "Bulanan" yang sudah
    // ada (satu bulan kalender penuh, TIDAK diubah sama sekali).
    let mode = "bulanan"; // "bulanan" | "periode"
    let tanggalMulai = MugenUI.awalBulanWib(MugenUI.isoHariIniWib());
    let tanggalSelesai = MugenUI.isoHariIniWib();

    root.innerHTML = "";
    const header = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
    header.appendChild(MugenUI.pageTitle(isOwner ? "Dashboard Owner" : "Dashboard Admin", MugenIcons.dashboard));

    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(bulan);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(tahun);
    const pickerBulanan = MugenUI.el("div", { class: "row", style: "flex:none;" }, [
      MugenUI.selectIcon(MugenIcons.calendar, selBulan),
      MugenUI.selectIcon(MugenIcons.calendar, selTahun),
    ]);

    const inputTanggalMulai = MugenUI.el("input", { type: "date", value: tanggalMulai, style: "max-width:150px;" });
    const inputTanggalSelesai = MugenUI.el("input", { type: "date", value: tanggalSelesai, style: "max-width:150px;" });
    const pickerPeriode = MugenUI.el("div", { class: "row", style: "flex:none;display:none;align-items:center;gap:6px;" }, [
      inputTanggalMulai,
      MugenUI.el("span", {}, "s/d"),
      inputTanggalSelesai,
    ]);

    const modeTabs = MugenUI.tabs(
      [{ key: "bulanan", label: "Bulanan" }, { key: "periode", label: "Periode" }],
      {
        initial: mode,
        onChange: (key) => {
          mode = key;
          pickerBulanan.style.display = mode === "bulanan" ? "" : "none";
          pickerPeriode.style.display = mode === "periode" ? "" : "none";
          load();
        },
      },
    );

    const picker = MugenUI.el("div", { class: "row", style: "flex:none;align-items:center;gap:10px;flex-wrap:wrap;" }, [
      modeTabs.bar, pickerBulanan, pickerPeriode,
    ]);
    header.appendChild(picker);
    root.appendChild(header);
    modeTabs.moveIndicator();

    const body = MugenUI.el("div");
    root.appendChild(body);

    // REVISI ("hilangkan fitur untuk menyembunyikan nilai kartu"): nilai
    // kartu SELALU tampil, tidak ada lagi panah/klik collapse per kartu
    // (dulu di sini, lihat riwayat komentar/COLLAPSE_KEY).
    // PERMINTAAN Owner (referensi dashboard "navy sidebar + kartu pastel"):
    // kartu statistik kembali berwarna per kategori -- `warna` ("blue"/
    // "green"/"orange"/"purple") menentukan latar kartu (class "card--
    // <warna>") & warna chip ikon (class "icon-chip--<warna>2"), menggantikan
    // kartu "andalan" tunggal yang dipakai sebelumnya.
    function card(label, value, icon, warna) {
      if (value === null || value === undefined) return null; // staff tanpa izin untuk kartu ini
      const valueBox = MugenUI.el("div", { class: "big-number" }, MugenUI.formatRupiah(value));
      const titleChildren = [];
      if (icon) titleChildren.push(MugenUI.el("span", { class: "card-collapse-icon icon-chip--" + warna + "2", html: icon }));
      titleChildren.push(MugenUI.el("span", {}, label));
      const titleRow = MugenUI.el("h2", { class: "card-collapse-title" }, titleChildren);
      return MugenUI.el("div", { class: "card card--" + warna }, [titleRow, valueBox]);
    }

    // REVISI ("Jumlah Service tampilkan nilai total keseluruhan service
    // saja"): SEBELUMNYA kartu ini berisi rincian per jenis service (mis.
    // "Dry Cut" = 7, "Cut & Wash" = 3, dst) -- SEKARANG cuma satu angka
    // total (jumlah seluruh service digabung), sama gayanya seperti
    // card() di atas. Gabungan seluruh barber, sama seperti kartu lain di
    // baris ini yang semuanya total toko.
    function cardJumlahService(rincian, warna) {
      if (rincian === null || rincian === undefined) return null;
      const total = rincian.reduce((jumlah, item) => jumlah + item.jumlah, 0);
      const titleRow = MugenUI.el("h2", { class: "card-collapse-title" }, [
        MugenUI.el("span", { class: "card-collapse-icon icon-chip--" + warna + "2", html: MugenIcons.service }),
        MugenUI.el("span", {}, "Jumlah Service"),
      ]);
      const valueBox = MugenUI.el("div", { class: "big-number" }, String(total));
      return MugenUI.el("div", { class: "card card--" + warna }, [titleRow, valueBox]);
    }

    // PERMINTAAN Owner: "Grafik Pendapatan Harian" -- smooth gradient area
    // chart (ungu->biru), tanpa library eksternal (SVG + animasi CSS
    // murni, konsisten dengan filosofi app ini -- lihat icons.js), filter
    // 7/30 Hari, tooltip sentuh/hover, animasi reveal kiri->kanan saat
    // dimuat. Data dari GET /api/dashboard/owner/pendapatan-harian.
    function formatTanggalPendekGp(iso) {
      const [, m, d] = iso.split("-").map(Number);
      const bulan = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
      return `${d} ${bulan[m - 1]}`;
    }

    // Kurva halus lewat Catmull-Rom -> Bezier kubik (dikonversi per segmen)
    // -- pola umum utk smooth line chart tanpa library, titik kontrol
    // dihitung dari tetangga kiri/kanan tiap titik supaya transisinya mulus.
    function kurvaMulusGp(points) {
      let d = `M ${points[0].x} ${points[0].y}`;
      for (let i = 0; i < points.length - 1; i++) {
        const p0 = points[i - 1] || points[i];
        const p1 = points[i];
        const p2 = points[i + 1];
        const p3 = points[i + 2] || p2;
        const cp1x = p1.x + (p2.x - p0.x) / 6, cp1y = p1.y + (p2.y - p0.y) / 6;
        const cp2x = p2.x - (p3.x - p1.x) / 6, cp2y = p2.y - (p3.y - p1.y) / 6;
        d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
      }
      return d;
    }

    function renderGrafikPendapatan() {
      const section = MugenUI.el("div", { class: "grafik-pendapatan" });
      const btn7 = MugenUI.el("button", { type: "button", class: "gp-filter-btn active" }, "7 Hari");
      const btn30 = MugenUI.el("button", { type: "button", class: "gp-filter-btn" }, "30 Hari");
      section.appendChild(MugenUI.el("div", { class: "gp-head" }, [
        MugenUI.el("h2", {}, "Pendapatan Harian"),
        MugenUI.el("div", { class: "gp-filter" }, [btn7, btn30]),
      ]));
      const totalValue = MugenUI.el("span", { class: "gp-total-value" }, "Rp 0");
      const totalLabel = MugenUI.el("span", { class: "gp-total-label" }, "");
      section.appendChild(MugenUI.el("div", { class: "gp-total-row" }, [totalValue, totalLabel]));
      const chartWrap = MugenUI.el("div", { class: "gp-chart-wrap" });
      section.appendChild(chartWrap);

      function gambar(data, hari) {
        const total = data.reduce((s, d) => s + d.nilai, 0);
        totalValue.textContent = MugenUI.formatRupiah(total);
        totalLabel.textContent = `total ${hari} hari terakhir`;

        const W = 720, H = 220, padL = 10, padR = 10, padT = 18, padB = 28;
        const innerW = W - padL - padR, innerH = H - padT - padB;
        const maxVal = Math.max(...data.map((d) => d.nilai), 0) * 1.15 || 1;

        const points = data.map((d, i) => ({
          x: padL + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW),
          y: padT + innerH - (d.nilai / maxVal) * innerH,
          ...d,
        }));

        const linePath = kurvaMulusGp(points);
        const areaPath = `${linePath} L ${points[points.length - 1].x} ${padT + innerH} L ${points[0].x} ${padT + innerH} Z`;

        const everyNth = Math.max(1, Math.ceil(data.length / 7));
        const axisLabels = points
          .map((p, i) => (i % everyNth === 0 || i === points.length - 1)
            ? `<text class="gp-axis-label" x="${p.x}" y="${H - 6}" text-anchor="middle">${formatTanggalPendekGp(p.tanggal)}</text>`
            : "")
          .join("");
        const dots = points
          .map((p, i) => `<circle class="gp-dot" style="animation-delay:${1 + i * 0.03}s" cx="${p.x}" cy="${p.y}" r="3.2" fill="#ffffff" stroke="#7C5CFC" stroke-width="2"></circle>`)
          .join("");

        chartWrap.innerHTML = `
          <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="gp-svg">
            <defs>
              <linearGradient id="gpAreaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#8B5CF6" stop-opacity="0.38" />
                <stop offset="55%" stop-color="#6D7CF7" stop-opacity="0.16" />
                <stop offset="100%" stop-color="#3B82F6" stop-opacity="0" />
              </linearGradient>
              <linearGradient id="gpLineGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stop-color="#8B5CF6" />
                <stop offset="100%" stop-color="#3B82F6" />
              </linearGradient>
              <clipPath id="gpRevealClip"><rect x="0" y="0" width="${W}" height="${H}" /></clipPath>
            </defs>
            <g class="gp-reveal-clip"><rect x="0" y="0" width="${W}" height="${H}" fill="transparent" /></g>
            <g clip-path="url(#gpRevealClip)">
              <path d="${areaPath}" fill="url(#gpAreaGrad)"></path>
              <path class="gp-line-path" d="${linePath}" fill="none" stroke="url(#gpLineGrad)" stroke-width="3" stroke-linecap="round"></path>
              ${dots}
            </g>
            <line class="gp-guide-line" x1="0" y1="${padT}" x2="0" y2="${padT + innerH}"></line>
            ${axisLabels}
            <rect class="gp-hover-catcher" x="0" y="0" width="${W}" height="${H}" fill="transparent"></rect>
          </svg>
        `;

        const svg = chartWrap.querySelector(".gp-svg");
        const guide = chartWrap.querySelector(".gp-guide-line");
        const catcher = chartWrap.querySelector(".gp-hover-catcher");
        const tooltip = MugenUI.el("div", { class: "gp-tooltip" }, [
          MugenUI.el("div", { class: "gp-tt-date" }),
          MugenUI.el("div", { class: "gp-tt-val" }),
        ]);
        chartWrap.style.position = "relative";
        chartWrap.appendChild(tooltip);

        function tampilkanDi(clientX) {
          const rect = svg.getBoundingClientRect();
          const svgX = ((clientX - rect.left) / rect.width) * W;
          let nearest = points[0], jarakTerdekat = Infinity;
          for (const p of points) {
            const jarak = Math.abs(p.x - svgX);
            if (jarak < jarakTerdekat) { jarakTerdekat = jarak; nearest = p; }
          }
          const px = (nearest.x / W) * rect.width + rect.left;
          const py = (nearest.y / H) * rect.height + rect.top;
          const wrapRect = chartWrap.getBoundingClientRect();
          tooltip.style.left = (px - wrapRect.left) + "px";
          tooltip.style.top = (py - wrapRect.top) + "px";
          tooltip.querySelector(".gp-tt-date").textContent = `${formatTanggalPendekGp(nearest.tanggal)} ${nearest.tanggal.slice(0, 4)}`;
          tooltip.querySelector(".gp-tt-val").textContent = MugenUI.formatRupiah(nearest.nilai);
          tooltip.classList.add("show");
          guide.setAttribute("x1", nearest.x);
          guide.setAttribute("x2", nearest.x);
          guide.classList.add("show");
        }
        function sembunyikanGp() {
          tooltip.classList.remove("show");
          guide.classList.remove("show");
        }
        catcher.addEventListener("mousemove", (e) => tampilkanDi(e.clientX));
        catcher.addEventListener("mouseleave", sembunyikanGp);
        catcher.addEventListener("touchstart", (e) => { tampilkanDi(e.touches[0].clientX); e.preventDefault(); }, { passive: false });
        catcher.addEventListener("touchmove", (e) => { tampilkanDi(e.touches[0].clientX); e.preventDefault(); }, { passive: false });
        catcher.addEventListener("touchend", sembunyikanGp);
      }

      async function muatGp(hari) {
        chartWrap.innerHTML = "";
        chartWrap.appendChild(MugenUI.skeleton("card", { lines: 2 }));
        try {
          const data = await MugenApi.get(`/api/dashboard/owner/pendapatan-harian?hari=${hari}`, { useCache: true });
          gambar(data, hari);
        } catch (e) {
          chartWrap.innerHTML = "";
          chartWrap.appendChild(MugenUI.errorState(e.message));
        }
      }

      btn7.addEventListener("click", () => {
        btn7.classList.add("active"); btn30.classList.remove("active");
        muatGp(7);
      });
      btn30.addEventListener("click", () => {
        btn30.classList.add("active"); btn7.classList.remove("active");
        muatGp(30);
      });

      muatGp(7);
      return section;
    }

    // BUGFIX (audit, race condition): dulu tidak ada penjagaan urutan
    // request -- membalik bulan/tahun dengan cepat bisa membuat dua
    // fetch tumpang tindih selesai TIDAK berurutan, data bulan yang
    // LEBIH LAMA bisa mendarat setelah bulan yang lebih baru dan diam-diam
    // menimpa dashboard dengan angka bulan yang salah.
    let urutanTerkini = 0;

    async function load(opts = {}) {
      const url = mode === "periode"
        ? `/api/dashboard/owner/periode?tanggal_mulai=${tanggalMulai}&tanggal_selesai=${tanggalSelesai}`
        : `/api/dashboard/owner?tahun=${tahun}&bulan=${bulan}`;

      // PERMINTAAN OWNER: begitu Dashboard dibuka lagi (pindah menu lalu
      // balik) TANPA ada simpan/edit/hapus apa pun sejak terakhir kali
      // Dashboard INI berhasil dimuat, tampilkan ulang hasil fetch terakhir
      // PERSIS seperti itu -- instan, tanpa skeleton/fetch sama sekali.
      // Hanya dicek untuk pemuatan AWAL (opts.bisaDariCache, dipanggil
      // SEKALI dari akhir render() di bawah) -- ganti bulan/tahun/periode
      // manual oleh user (handler di bawah, TANPA opts) SELALU fetch ulang.
      if (opts.bisaDariCache && !MugenState.dashboardPerluRefresh()) {
        const cached = _ambilDariCache(MugenState.getUser().id, url);
        if (cached) {
          renderDenganData(cached);
          return;
        }
      }

      const urutanSaya = ++urutanTerkini;
      // REVISI UI/UX Premium: skeleton (bentuk kartu) menggantikan teks
      // "Memuat..." -- kartu asli otomatis beranimasi masuk begitu
      // ditambahkan (lihat .card { animation: mugen-fade-slide-in }),
      // jadi transisi skeleton -> data terasa satu alur, bukan dua lompatan.
      body.innerHTML = "";
      body.appendChild(MugenUI.el("div", { class: "grid-cards" }, [
        MugenUI.skeleton("card", { lines: 2 }), MugenUI.skeleton("card", { lines: 2 }),
        MugenUI.skeleton("card", { lines: 2 }),
      ]));
      try {
        const data = await MugenApi.get(url, { useCache: true });
        if (urutanSaya !== urutanTerkini) return; // respons basi, biarkan panggilan terbaru yang merender
        if (!data.__offline) {
          // Cache offline (data.__offline) SENGAJA tidak disimpan ke sini --
          // bukan representasi data yang sebenarnya berhasil dimuat barusan.
          _cacheTerakhir = { userId: MugenState.getUser().id, url, data };
          MugenState.tandaiDashboardBersih();
        }
        renderDenganData(data);
      } catch (e) {
        if (urutanSaya !== urutanTerkini) return; // respons basi, jangan timpa hasil yang lebih baru
        body.innerHTML = "";
        body.appendChild(MugenUI.el("div", { class: "card" }, MugenUI.errorState(e.message)));
      }
    }

    function renderDenganData(data) {
        body.innerHTML = "";
        if (data.__offline) body.appendChild(MugenUI.offlineBanner(data.__cachedAt));

        const t = data.total_toko;
        const kartu = [
          card("Nilai Service", t.nilai_service, MugenIcons.service, "blue"),
          card("Total Komisi Barber", t.komisi, MugenIcons.komisi, "green"),
          card("Total Tips", t.tips, MugenIcons.tips, "orange"),
          card("Uang Harian", t.uang_harian, MugenIcons.uangHarian, "purple"),
          cardJumlahService(data.rincian_service_semua_barber, "blue"),
          card("Pengeluaran Toko", data.total_pengeluaran, MugenIcons.pengeluaran, "green"),
          card("Penjualan Produk", data.penjualan_produk, MugenIcons.penjualanProduk, "orange"),
          card("Laba Kotor Toko", data.laba_kotor, MugenIcons.labaKotor, "purple"),
        ].filter((el) => el !== null);

        if (kartu.length === 0) {
          body.appendChild(MugenUI.el("div", { class: "card" },
            "Belum ada kartu Dashboard yang diizinkan untuk akun Admin ini. Hubungi Owner untuk mengatur hak akses lewat Setting > Hak Akses Admin."));
        } else {
          body.appendChild(MugenUI.el("div", { class: "grid-cards" }, kartu));
        }

        // ================= BAGIAN KHUSUS OWNER =================
        // SERVICE BULAN INI (rincian per barber) dan Grafik Pendapatan
        // BUKAN bagian dari Dashboard Admin (lihat spesifikasi Hak Akses
        // Admin -- hanya 4 kartu ringkasan toko yang bisa diizinkan Owner),
        // jadi tidak pernah dirender untuk role 'staff'.
        if (!isOwner) return;

        // ================= GRAFIK PENDAPATAN HARIAN =================
        // PERMINTAAN Owner (smooth gradient area chart, ungu->biru, card
        // lavender TANPA bingkai/shadow -- "menyatu" langsung dengan
        // halaman, lihat .grafik-pendapatan di style.css): filter 7/30
        // Hari, tooltip saat disentuh/hover, animasi reveal kiri->kanan
        // saat pertama dimuat. Data NYATA dari backend (GET
        // /api/dashboard/owner/pendapatan-harian, rumus sama persis
        // dengan kartu "Nilai Service" di atas) -- BUKAN data dummy.
        // Animasi/tooltip MURNI lokal (CSS/SVG) setelah data diambil,
        // TIDAK ada panggilan server berulang -- satu fetch per load
        // halaman atau per klik ganti filter 7/30 Hari.
        body.appendChild(renderGrafikPendapatan());

        // ================= SERVICE BULAN INI / PERIODE INI =================
        // PERMINTAAN Owner ("saya ingin dashboard data service bulan ini
        // dibuat seperti gambar yang saya kirim" -- referensi kartu "Service
        // Performance": badge periode, 2 kartu ringkasan Total Service/Best
        // Seller, daftar "Service Terpopuler" dengan progress bar per item,
        // ditutup baris total): menggantikan tabel 2-kolom polos sebelumnya.
        const serviceCard = MugenUI.el("div", { class: "card" });
        const serviceHeader = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
        serviceHeader.appendChild(MugenUI.el("h2", { style: "margin:0;" }, mode === "periode" ? "SERVICE PERIODE INI" : "SERVICE BULAN INI"));
        const periodeLabel = mode === "periode"
          ? `${MugenUI.formatTanggal(tanggalMulai)} s/d ${MugenUI.formatTanggal(tanggalSelesai)}`
          : `${MugenUI.namaBulan(bulan)} ${tahun}`;
        serviceHeader.appendChild(MugenUI.el("span", { class: "badge badge-period" }, periodeLabel));
        serviceCard.appendChild(serviceHeader);

        const selBarberFilter = MugenUI.el("select", { style: "max-width:220px;" });
        selBarberFilter.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
        for (const r of data.per_barber) {
          selBarberFilter.appendChild(MugenUI.el("option", { value: String(r.barber.id) }, r.barber.nama));
        }
        serviceCard.appendChild(MugenUI.el("div", { style: "display:flex;justify-content:flex-end;margin-top:8px;" },
          MugenUI.selectIcon(MugenIcons.karyawan, selBarberFilter)));

        const serviceBox = MugenUI.el("div", { class: "sp-wrap" });
        serviceCard.appendChild(serviceBox);
        body.appendChild(serviceCard);

        function renderRincianService() {
          const rincian = !selBarberFilter.value
            ? data.rincian_service_semua_barber
            : (data.per_barber.find((x) => String(x.barber.id) === selBarberFilter.value) || {}).rincian_service;

          serviceBox.innerHTML = "";
          if (!rincian || rincian.length === 0) {
            serviceBox.appendChild(MugenUI.emptyState("Belum ada service pada periode ini."));
            return;
          }

          const terurut = [...rincian].sort((a, b) => b.jumlah - a.jumlah);
          const totalTransaksi = terurut.reduce((jumlah, s) => jumlah + s.jumlah, 0);
          const terlaris = terurut[0];
          const maxJumlah = terlaris.jumlah || 1;
          const subPeriode = mode === "periode" ? "periode ini" : "bulan ini";

          const stats = MugenUI.el("div", { class: "sp-stats" }, [
            MugenUI.el("div", { class: "sp-stat-tile card--blue" }, [
              MugenUI.el("div", { class: "sp-stat-label" }, "Total Service"),
              MugenUI.el("div", { class: "sp-stat-value" }, String(totalTransaksi)),
              MugenUI.el("div", { class: "sp-stat-sub" }, `Transaksi ${subPeriode}`),
            ]),
            MugenUI.el("div", { class: "sp-stat-tile card--green" }, [
              MugenUI.el("div", { class: "sp-stat-label" }, "Best Seller"),
              MugenUI.el("div", { class: "sp-stat-value sp-stat-value--best" }, terlaris.nama_service),
              MugenUI.el("div", { class: "sp-stat-sub" }, `${terlaris.jumlah} transaksi`),
            ]),
          ]);
          serviceBox.appendChild(stats);

          serviceBox.appendChild(MugenUI.el("h3", { class: "sp-subtitle" }, "Service Terpopuler"));

          const list = MugenUI.el("div", { class: "sp-list" });
          terurut.forEach((s, i) => {
            const warnaBar = (i % 5) + 1;
            const persen = Math.max((s.jumlah / maxJumlah) * 100, 3);
            list.appendChild(MugenUI.el("div", { class: "sp-row" }, [
              MugenUI.el("div", { class: "sp-row-label" }, [
                MugenUI.el("span", {}, `${i + 1}. ${s.nama_service}`),
                MugenUI.el("span", { class: "sp-row-count" }, `${s.jumlah}x`),
              ]),
              MugenUI.el("div", { class: "sp-bar-track" }, [
                MugenUI.el("div", { class: "sp-bar-fill sp-bar--" + warnaBar, style: `width:${persen}%;` }),
              ]),
            ]));
          });
          serviceBox.appendChild(list);

          serviceBox.appendChild(MugenUI.el("div", { class: "sp-footer" }, [
            MugenUI.el("span", {}, "Total seluruh service"),
            MugenUI.el("strong", {}, `${totalTransaksi} transaksi`),
          ]));
        }
        selBarberFilter.addEventListener("change", renderRincianService);
        renderRincianService();
        // PERMINTAAN Owner: tabel "Per Barber" (ringkasan Komisi/Tips/Uang
        // Harian/Bonus Customer/Total per baris barber) DIHAPUS PERMANEN
        // dari sini -- bukan disembunyikan lewat CSS. `data.per_barber`
        // TETAP dikirim backend & TETAP dipakai di atas (dropdown filter +
        // rincian service per barber di kartu "Service Bulan Ini", SENGAJA
        // TIDAK ikut dihapus) dan untuk menghitung kartu ringkasan "Total
        // Komisi Barber"/"Total Tips"/dst di atas (lihat total_toko di
        // routers/dashboard.py) -- field-field itu TIDAK bisa dihapus dari
        // payload API tanpa merusak keduanya, hanya tabel ini yang dihapus.
    }

    // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
    // -- skeleton di dalam body sendiri (lihat load() di atas) sudah jadi
    // feedback yang cukup, ganti bulan/tahun terasa instan.
    selBulan.addEventListener("change", () => { bulan = Number(selBulan.value); load(); });
    selTahun.addEventListener("change", () => { tahun = Number(selTahun.value); load(); });
    inputTanggalMulai.addEventListener("change", () => { tanggalMulai = inputTanggalMulai.value; load(); });
    inputTanggalSelesai.addEventListener("change", () => { tanggalSelesai = inputTanggalSelesai.value; load(); });
    // bisaDariCache: true HANYA di pemuatan AWAL ini -- ganti bulan/tahun/
    // periode manual oleh user (keempat handler di atas) SELALU fetch ulang.
    load({ bisaDariCache: true });
  }

  return { render, refreshDiamDiam };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageDashboardOwner begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageDashboardOwner = PageDashboardOwner;
