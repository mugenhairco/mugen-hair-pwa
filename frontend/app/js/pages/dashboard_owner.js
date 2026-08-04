// pages/dashboard_owner.js
// REVISI: kartu "Bonus Kehadiran" dihapus (fitur Bonus Kehadiran dihapus
// total); ditambah kartu "Total Customer", bagian "Progress Target
// Service", dan "Service Bulan Ini" (dengan dropdown pilihan barber).
// REVISI Hak Akses Admin:
// - Kartu "Total Pendapatan Barber" DIHAPUS (nilainya sama persis dengan
//   "Total Komisi Barber" -- dua kartu untuk satu angka yang sama).
// - Setiap kartu sekarang bisa di-collapse/expand (klik judulnya), status
//   collapse/expand per kartu TERSIMPAN di localStorage (bertahan lintas
//   refresh/login ulang) -- lihat COLLAPSE_KEY/_loadCollapseState di bawah.
//   Tombol "Collapse All"/"Expand All" mengatur semua kartu sekaligus.
// - Halaman ini SEKARANG JUGA dipakai untuk role 'staff' (Admin, lihat
//   router.js::resolveDashboardPage) -- backend (routers/dashboard.py)
//   sudah memfilter field yang tidak diizinkan Owner jadi `null` untuk
//   role ini, dan mengosongkan `per_barber` sama sekali. Kartu dengan
//   nilai `null` TIDAK dirender sama sekali (bukan ditampilkan sebagai
//   "Rp 0", supaya tidak menyesatkan), dan bagian "SERVICE BULAN INI"/
//   "Per Barber"/"Grafik Pendapatan" (di luar cakupan Dashboard Admin,
//   lihat spesifikasi) hanya dirender untuk role 'admin' (Owner).

const PageDashboardOwner = (() => {
  const COLLAPSE_KEY = "mugen_dashboard_owner_collapse_v1";

  function _loadCollapseState() {
    try {
      return JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "{}");
    } catch (e) {
      return {};
    }
  }

  function _saveCollapseState(state) {
    try {
      localStorage.setItem(COLLAPSE_KEY, JSON.stringify(state));
    } catch (e) {
      // localStorage penuh/tidak tersedia -- status collapse memang best-effort,
      // tidak menghalangi tampilan kartu itu sendiri.
    }
  }

  function render(root) {
    const today = new Date();
    let tahun = today.getFullYear();
    let bulan = today.getMonth() + 1;
    const isOwner = MugenState.getUser().role === "admin";
    const collapseState = _loadCollapseState();
    const cardKeys = []; // diisi ulang tiap render() body -- dipakai tombol Collapse/Expand All

    root.innerHTML = "";
    const header = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
    header.appendChild(MugenUI.el("h1", {}, isOwner ? "Dashboard Owner" : "Dashboard Admin"));

    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(bulan);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(tahun);
    const picker = MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun]);
    header.appendChild(picker);
    root.appendChild(header);

    const toolbar = MugenUI.el("div", { class: "row", style: "flex:none;margin:10px 0;gap:8px;" });
    const btnCollapseAll = MugenUI.el("button", {}, "Collapse All");
    const btnExpandAll = MugenUI.el("button", {}, "Expand All");
    toolbar.appendChild(btnCollapseAll);
    toolbar.appendChild(btnExpandAll);
    root.appendChild(toolbar);

    const body = MugenUI.el("div");
    root.appendChild(body);

    const cardToggleFns = {}; // key -> function(collapsed) untuk dipanggil tombol Collapse/Expand All

    function card(key, label, value) {
      if (value === null || value === undefined) return null; // staff tanpa izin untuk kartu ini
      cardKeys.push(key);
      const collapsed = collapseState[key] === true;
      const valueBox = MugenUI.el("div", { class: "big-number", style: collapsed ? "display:none;" : "" }, MugenUI.formatRupiah(value));
      const arrow = MugenUI.el("span", { class: "card-collapse-arrow" }, collapsed ? "▸" : "▾");
      const titleRow = MugenUI.el("h2", { class: "card-collapse-title" }, [
        MugenUI.el("span", {}, label),
        arrow,
      ]);
      function setCollapsed(next) {
        collapseState[key] = next;
        valueBox.style.display = next ? "none" : "";
        arrow.textContent = next ? "▸" : "▾";
      }
      titleRow.addEventListener("click", () => {
        setCollapsed(!collapseState[key]);
        _saveCollapseState(collapseState);
      });
      cardToggleFns[key] = setCollapsed;
      return MugenUI.el("div", { class: "card" }, [titleRow, valueBox]);
    }

    // REVISI: kartu "Total Customer" diganti kartu "Jumlah Service" berisi
    // rincian per jenis service (mis. "Dry Cut" = 7, "Cut & Wash" = 3, dst),
    // service dengan jumlah 0 tidak ditampilkan (backend sudah memfilternya
    // lewat rincian_service_semua_barber). Gabungan seluruh barber, sama
    // seperti kartu lain di baris ini yang semuanya total toko.
    function cardJumlahService(key, rincian) {
      if (rincian === null || rincian === undefined) return null;
      cardKeys.push(key);
      const collapsed = collapseState[key] === true;
      const listBox = MugenUI.el("div", { style: collapsed ? "display:none;" : "" });
      if (!rincian || rincian.length === 0) {
        listBox.appendChild(MugenUI.el("div", { style: "color:var(--text-dim);" }, "Belum ada service bulan ini."));
      } else {
        for (const item of rincian) {
          listBox.appendChild(MugenUI.el("div", { style: "display:flex;justify-content:space-between;padding:2px 0;" }, [
            MugenUI.el("span", {}, item.nama_service),
            MugenUI.el("span", { style: "font-weight:600;" }, String(item.jumlah)),
          ]));
        }
      }
      const arrow = MugenUI.el("span", { class: "card-collapse-arrow" }, collapsed ? "▸" : "▾");
      const titleRow = MugenUI.el("h2", { class: "card-collapse-title" }, [
        MugenUI.el("span", {}, "Jumlah Service"),
        arrow,
      ]);
      function setCollapsed(next) {
        collapseState[key] = next;
        listBox.style.display = next ? "none" : "";
        arrow.textContent = next ? "▸" : "▾";
      }
      titleRow.addEventListener("click", () => {
        setCollapsed(!collapseState[key]);
        _saveCollapseState(collapseState);
      });
      cardToggleFns[key] = setCollapsed;
      return MugenUI.el("div", { class: "card" }, [titleRow, listBox]);
    }

    async function load() {
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
        const data = await MugenApi.get(`/api/dashboard/owner?tahun=${tahun}&bulan=${bulan}`, { useCache: true });
        body.innerHTML = "";
        if (data.__offline) body.appendChild(MugenUI.offlineBanner(data.__cachedAt));

        cardKeys.length = 0;
        const t = data.total_toko;
        const kartu = [
          card("nilai_service", "Nilai Service", t.nilai_service),
          card("total_komisi", "Total Komisi Barber", t.komisi),
          card("total_tips", "Total Tips", t.tips),
          card("uang_harian", "Uang Harian", t.uang_harian),
          card("bonus_customer", "Bonus Customer", t.bonus_customer),
          cardJumlahService("jumlah_service", data.rincian_service_semua_barber),
          card("pengeluaran_toko", "Pengeluaran Toko", data.total_pengeluaran),
          card("penjualan_produk", "Penjualan Produk", data.penjualan_produk),
          card("laba_kotor", "Laba Kotor Toko", data.laba_kotor),
        ].filter((el) => el !== null);

        if (kartu.length === 0) {
          body.appendChild(MugenUI.el("div", { class: "card" },
            "Belum ada kartu Dashboard yang diizinkan untuk akun Admin ini. Hubungi Owner untuk mengatur hak akses lewat Setting > Hak Akses Admin."));
        } else {
          body.appendChild(MugenUI.el("div", { class: "grid-cards" }, kartu));
        }

        // ================= BAGIAN KHUSUS OWNER =================
        // SERVICE BULAN INI (rincian per barber), Per Barber, dan Grafik
        // Pendapatan BUKAN bagian dari Dashboard Admin (lihat spesifikasi
        // Hak Akses Admin -- hanya 4 kartu ringkasan toko yang bisa
        // diizinkan Owner), jadi tidak pernah dirender untuk role 'staff'.
        if (!isOwner) return;

        // ================= SERVICE BULAN INI =================
        const serviceCard = MugenUI.el("div", { class: "card" });
        const serviceHeader = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
        serviceHeader.appendChild(MugenUI.el("h2", { style: "margin:0;" }, "SERVICE BULAN INI"));
        const selBarberFilter = MugenUI.el("select", { style: "max-width:220px;" });
        selBarberFilter.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
        for (const r of data.per_barber) {
          selBarberFilter.appendChild(MugenUI.el("option", { value: String(r.barber.id) }, r.barber.nama));
        }
        serviceHeader.appendChild(selBarberFilter);
        serviceCard.appendChild(serviceHeader);

        const serviceTableBox = MugenUI.el("div");
        serviceCard.appendChild(serviceTableBox);
        body.appendChild(serviceCard);

        function renderRincianService() {
          serviceTableBox.innerHTML = "";
          if (!selBarberFilter.value) {
            serviceTableBox.appendChild(MugenUI.buildTable(
              [
                { key: "nama_service", label: "Service" },
                { key: "jumlah", label: "Jumlah" },
              ],
              data.rincian_service_semua_barber,
              { emptyText: "Belum ada service bulan ini." },
            ));
          } else {
            const r = data.per_barber.find((x) => String(x.barber.id) === selBarberFilter.value);
            if (!r) return;
            serviceTableBox.appendChild(MugenUI.buildTable(
              [
                { key: "nama_service", label: "Service" },
                { key: "jumlah", label: "Jumlah" },
              ],
              r.rincian_service,
              { emptyText: "Belum ada service bulan ini." },
            ));
          }
        }
        selBarberFilter.addEventListener("change", renderRincianService);
        renderRincianService();

        body.appendChild(MugenUI.el("h2", {}, "Per Barber"));
        body.appendChild(MugenUI.buildTable(
          [
            { key: "barber", label: "Barber", format: (_, r) => r.barber.nama },
            { key: "jumlah_customer", label: "Service" },
            { key: "komisi", label: "Komisi", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            { key: "bonus_customer", label: "Bonus Customer", format: MugenUI.formatRupiah },
            { key: "total_pendapatan", label: "Total", format: MugenUI.formatRupiah },
          ],
          data.per_barber,
        ));

        // ================= GRAFIK PENDAPATAN (khusus Dashboard Owner) =================
        const grafikCard = MugenUI.el("div", { class: "card" });
        const grafikHeader = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
        grafikHeader.appendChild(MugenUI.el("h2", { style: "margin:0;" }, "Grafik Pendapatan"));
        const selBarberGrafik = MugenUI.el("select", { style: "max-width:220px;" });
        selBarberGrafik.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
        for (const r of data.per_barber) {
          selBarberGrafik.appendChild(MugenUI.el("option", { value: String(r.barber.id) }, r.barber.nama));
        }
        grafikHeader.appendChild(selBarberGrafik);
        grafikCard.appendChild(grafikHeader);

        grafikCard.appendChild(MugenUI.el("h3", { style: "margin-bottom:4px;" },
          `Harian — ${MugenUI.namaBulan(bulan)} ${tahun}`));
        grafikCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:6px;" },
          "Komisi + Tips + Uang Harian per tanggal. Bonus Customer tidak diikutkan di sini karena itu " +
          "perhitungan bulanan, bukan harian (lihat grafik Bulanan di bawah)."));
        const grafikHarianBox = MugenUI.el("div");
        grafikCard.appendChild(grafikHarianBox);

        grafikCard.appendChild(MugenUI.el("h3", { style: "margin-bottom:4px;margin-top:20px;" }, `Bulanan — ${tahun}`));
        grafikCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:6px;" },
          "Total Pendapatan penuh (Komisi + Tips + Uang Harian + Bonus Customer) per bulan."));
        const grafikBulananBox = MugenUI.el("div");
        grafikCard.appendChild(grafikBulananBox);

        body.appendChild(grafikCard);

        async function renderGrafik() {
          // REVISI UI/UX Premium: skeleton menggantikan "Memuat..." --
          // lihat catatan sama di load() di atas.
          grafikHarianBox.innerHTML = "";
          grafikHarianBox.appendChild(MugenUI.skeleton("line", { width: "90%" }));
          grafikBulananBox.innerHTML = "";
          grafikBulananBox.appendChild(MugenUI.skeleton("line", { width: "90%" }));
          const barberIdGrafik = selBarberGrafik.value;
          const qsBarber = barberIdGrafik ? `&barber_id=${barberIdGrafik}` : "";
          try {
            const [harian, bulananData] = await Promise.all([
              MugenApi.get(`/api/dashboard/owner/grafik-harian?tahun=${tahun}&bulan=${bulan}${qsBarber}`, { useCache: true }),
              MugenApi.get(`/api/dashboard/owner/grafik-bulanan?tahun=${tahun}${qsBarber}`, { useCache: true }),
            ]);
            grafikHarianBox.innerHTML = "";
            if (harian.__offline) grafikHarianBox.appendChild(MugenUI.offlineBanner(harian.__cachedAt));
            grafikHarianBox.appendChild(MugenUI.barChart(
              harian.map((h) => ({ value: h.pendapatan, tanggal: h.tanggal })),
              { xLabel: (d) => String(d.tanggal), yFormat: MugenUI.formatRupiah },
            ));
            grafikBulananBox.innerHTML = "";
            if (bulananData.__offline) grafikBulananBox.appendChild(MugenUI.offlineBanner(bulananData.__cachedAt));
            grafikBulananBox.appendChild(MugenUI.barChart(
              bulananData.map((b) => ({ value: b.pendapatan, bulan: b.bulan })),
              { xLabel: (d) => MugenUI.namaBulan(d.bulan).slice(0, 3), yFormat: MugenUI.formatRupiah },
            ));
          } catch (e) {
            grafikHarianBox.innerHTML = "";
            grafikBulananBox.innerHTML = "";
            grafikHarianBox.appendChild(MugenUI.errorState(e.message));
          }
        }
        // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar
        // penuh -- skeleton di dalam grafikHarianBox/grafikBulananBox
        // sendiri (di atas) sudah jadi feedback yang cukup.
        selBarberGrafik.addEventListener("change", renderGrafik);
        renderGrafik();
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.el("div", { class: "card" }, MugenUI.errorState(e.message)));
      }
    }

    btnCollapseAll.addEventListener("click", () => {
      for (const key of cardKeys) { collapseState[key] = true; cardToggleFns[key] && cardToggleFns[key](true); }
      _saveCollapseState(collapseState);
    });
    btnExpandAll.addEventListener("click", () => {
      for (const key of cardKeys) { collapseState[key] = false; cardToggleFns[key] && cardToggleFns[key](false); }
      _saveCollapseState(collapseState);
    });

    // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
    // -- skeleton di dalam body sendiri (lihat load() di atas) sudah jadi
    // feedback yang cukup, ganti bulan/tahun terasa instan.
    selBulan.addEventListener("change", () => { bulan = Number(selBulan.value); load(); });
    selTahun.addEventListener("change", () => { tahun = Number(selTahun.value); load(); });
    load();
  }

  return { render };
})();
