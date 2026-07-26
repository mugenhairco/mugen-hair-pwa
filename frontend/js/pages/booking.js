// pages/booking.js — Menu "Booking" internal (BUKAN halaman publik /book,
// lihat book_public.js untuk itu). Owner/Admin: full access lewat tab
// (Booking List, Calendar, Operating Hours, Barber Holiday, Closed Slot,
// Payment Settings, Booking Settings). Barber: HANYA daftar booking
// miliknya sendiri (tanpa tab, backend /api/booking/mine sudah membatasi
// lewat barber_id dari akun login -- bukan dari parameter apa pun yang
// dikirim, jadi frontend TIDAK BISA membocorkan booking barber lain
// meskipun dimodifikasi).
//
// Barber Holiday SENGAJA memakai endpoint /api/input-data/libur yang
// SUDAH ADA (lihat booking_db.py) -- bukan endpoint baru -- supaya "barber
// libur" tetap SATU sumber kebenaran yang sama dengan yang dipakai
// perhitungan Bonus Customer di Dashboard.

const PageBooking = (() => {
  const STATUS_BAYAR_LABEL = { menunggu_verifikasi: "Menunggu Verifikasi", terverifikasi: "Terverifikasi" };
  const STATUS_BOOKING_LABEL = { aktif: "Aktif", dibatalkan: "Dibatalkan" };
  const METODE_LABEL = { cash: "Cash", transfer: "Transfer Bank", qris: "QRIS", gateway: "Payment Gateway" };

  async function render(root) {
    const user = MugenState.getUser();
    const isAdmin = user.role === "admin" || user.role === "staff";
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Booking"));

    if (!isAdmin) {
      await renderBarberList(root);
      return;
    }

    const tabs = ["Booking List", "Calendar", "Operating Hours", "Barber Holiday", "Closed Slot", "Payment Settings", "Booking Settings"];
    let activeTab = tabs[0];
    const tabBar = MugenUI.el("div", { class: "tabs" });
    const body = MugenUI.el("div");
    root.appendChild(tabBar);
    root.appendChild(body);

    let barbers = [];
    try { barbers = await MugenApi.get("/api/input-data/barbers", { useCache: true }); } catch (e) { /* opsional */ }

    function renderTabs() {
      tabBar.innerHTML = "";
      for (const t of tabs) {
        const btn = MugenUI.el("button", { class: activeTab === t ? "active" : "" }, t);
        btn.addEventListener("click", () => { activeTab = t; renderTabs(); renderBody(); });
        tabBar.appendChild(btn);
      }
    }

    async function renderBody() {
      body.innerHTML = "";
      if (activeTab === "Booking List") await renderBookingList(body, barbers);
      else if (activeTab === "Calendar") await renderCalendar(body, barbers);
      else if (activeTab === "Operating Hours") await renderOperatingHours(body);
      else if (activeTab === "Barber Holiday") await renderBarberHoliday(body, barbers);
      else if (activeTab === "Closed Slot") await renderClosedSlot(body, barbers);
      else if (activeTab === "Payment Settings") await renderPaymentSettings(body);
      else if (activeTab === "Booking Settings") await renderBookingSettings(body);
    }

    renderTabs();
    renderBody();
  }

  // ================= Barber: hanya milik sendiri =================
  async function renderBarberList(root) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    const today = new Date();
    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(today.getMonth() + 1);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 1; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(today.getFullYear());
    root.insertBefore(MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;" }, [selBulan, selTahun]), card);

    async function load() {
      card.innerHTML = "Memuat...";
      try {
        const data = await MugenApi.get(`/api/booking/mine?tahun=${selTahun.value}&bulan=${selBulan.value}`, { useCache: true });
        card.innerHTML = "";
        // AUDIT SINKRONISASI: sebelumnya __offline TIDAK pernah dicek di
        // seluruh halaman ini walau semua fetch memakai useCache:true --
        // kalau jaringan sempat putus sesaat, halaman diam-diam menampilkan
        // data cache lokal LAMA tanpa tanda apa pun, persis gejala "kadang
        // sinkron kadang tidak" yang dilaporkan. Sekarang tiap fetch di
        // halaman ini menampilkan offlineBanner kalau datanya bukan dari
        // server yang baru saja dipanggil.
        if (data.__offline) card.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        card.appendChild(bookingTable(Array.isArray(data) ? data : [], { withBarber: false }));
      } catch (e) {
        card.innerHTML = "";
        card.appendChild(MugenUI.el("div", {}, e.message));
      }
    }
    selBulan.addEventListener("change", () => MugenUI.withLoading(load));
    selTahun.addEventListener("change", () => MugenUI.withLoading(load));
    load();
  }

  // ================= Helper: tabel booking (dipakai List & Calendar) =================
  function bookingTable(rows, { withBarber = true, onVerifikasi = null, onBatalkan = null } = {}) {
    const columns = [
      { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
      { key: "jam_mulai", label: "Jam", format: (_, r) => `${r.jam_mulai}-${r.jam_selesai}` },
      ...(withBarber ? [{ key: "nama_barber", label: "Barber" }] : []),
      { key: "customer_nama", label: "Customer" },
      { key: "customer_whatsapp", label: "WhatsApp" },
      { key: "daftar_service", label: "Service" },
      { key: "total_harga", label: "Total", format: MugenUI.formatRupiah },
      { key: "metode_pembayaran", label: "Metode", format: (v) => METODE_LABEL[v] || v },
      {
        key: "status_pembayaran", label: "Status Bayar",
        format: (v) => MugenUI.el("span", { class: "badge" + (v === "terverifikasi" ? " badge-success" : " badge-libur") }, STATUS_BAYAR_LABEL[v] || v),
      },
      {
        key: "status_booking", label: "Status",
        format: (v) => MugenUI.el("span", { class: "badge" + (v === "aktif" ? "" : " badge-danger") }, STATUS_BOOKING_LABEL[v] || v),
      },
    ];
    if (onVerifikasi || onBatalkan) {
      columns.push({
        key: "aksi", label: "Aksi", format: (_, r) => {
          const wrap = MugenUI.el("div", { class: "actions-cell" });
          if (onVerifikasi && r.status_pembayaran !== "terverifikasi" && r.status_booking === "aktif") {
            const btn = MugenUI.el("button", {}, "Verifikasi");
            btn.addEventListener("click", async () => {
              btn.disabled = true;
              try { await onVerifikasi(r); } finally { btn.disabled = false; }
            });
            wrap.appendChild(btn);
          }
          if (onBatalkan && r.status_booking === "aktif") {
            const btn = MugenUI.el("button", { class: "btn-danger" }, "Batalkan");
            btn.addEventListener("click", async () => {
              btn.disabled = true;
              try { await onBatalkan(r); } finally { btn.disabled = false; }
            });
            wrap.appendChild(btn);
          }
          return wrap;
        },
      });
    }
    return MugenUI.buildTable(columns, rows, { emptyText: "Belum ada booking." });
  }

  function barberFilterRow(barbers, today, { withStatus = true } = {}) {
    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(today.getMonth() + 1);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 1; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(today.getFullYear());
    const selBarber = MugenUI.el("select");
    selBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const selStatus = withStatus ? MugenUI.el("select") : null;
    if (selStatus) {
      selStatus.appendChild(MugenUI.el("option", { value: "" }, "Semua Status"));
      selStatus.appendChild(MugenUI.el("option", { value: "aktif" }, "Aktif"));
      selStatus.appendChild(MugenUI.el("option", { value: "dibatalkan" }, "Dibatalkan"));
    }
    const row = MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;flex-wrap:wrap;" },
      [selBulan, selTahun, selBarber, ...(selStatus ? [selStatus] : [])]);
    return { row, selBulan, selTahun, selBarber, selStatus };
  }

  // ================= TAB: BOOKING LIST =================
  async function renderBookingList(body, barbers) {
    const today = new Date();
    const { row, selBulan, selTahun, selBarber, selStatus } = barberFilterRow(barbers, today);
    const tableWrap = MugenUI.el("div");
    body.appendChild(row);
    body.appendChild(tableWrap);

    async function load() {
      tableWrap.innerHTML = "Memuat...";
      try {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        if (selBarber.value) qs.set("barber_id", selBarber.value);
        if (selStatus.value) qs.set("status_booking", selStatus.value);
        const data = await MugenApi.get(`/api/booking?${qs}`, { useCache: true });
        tableWrap.innerHTML = "";
        // AUDIT SINKRONISASI: lihat komentar di renderBarberList() di atas.
        if (data.__offline) tableWrap.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        const rows = Array.isArray(data) ? data : [];
        tableWrap.appendChild(bookingTable(rows, {
          onVerifikasi: async (r) => {
            try {
              await MugenUI.withLoading(() => MugenApi.post(`/api/booking/${r.id}/verifikasi`), { message: "Memverifikasi pembayaran…" });
              MugenUI.toast("Pembayaran diverifikasi.", "success");
              load();
              MugenBookingNotif.refreshNow(); // REVISI: badge langsung update, tidak menunggu poll berikutnya
            } catch (e) { MugenUI.toast(e.message, "error"); }
          },
          onBatalkan: async (r) => {
            if (!confirm(`Batalkan booking ${r.customer_nama} (${r.tanggal} ${r.jam_mulai})?`)) return;
            try {
              await MugenUI.withLoading(() => MugenApi.post(`/api/booking/${r.id}/batalkan`), { message: "Membatalkan booking…" });
              MugenUI.toast("Booking dibatalkan.", "success");
              load();
              MugenBookingNotif.refreshNow(); // REVISI: badge langsung update, tidak menunggu poll berikutnya
            } catch (e) { MugenUI.toast(e.message, "error"); }
          },
        }));
      } catch (e) {
        tableWrap.innerHTML = "";
        tableWrap.appendChild(MugenUI.el("div", {}, e.message));
      }
    }
    selBulan.addEventListener("change", () => MugenUI.withLoading(load));
    selTahun.addEventListener("change", () => MugenUI.withLoading(load));
    selBarber.addEventListener("change", () => MugenUI.withLoading(load));
    selStatus.addEventListener("change", () => MugenUI.withLoading(load));
    load();
  }

  // ================= TAB: CALENDAR =================
  async function renderCalendar(body, barbers) {
    const today = new Date();
    let shown = new Date(today.getFullYear(), today.getMonth(), 1);
    // Filter bulan/tahun TIDAK dipakai di sini (navigasi bulan sudah lewat
    // tombol ‹/› kalender sendiri) -- hanya filter barber yang relevan.
    const selBarber = MugenUI.el("select");
    selBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    body.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;" }, [selBarber]));

    const calOfflineBox = MugenUI.el("div"); // AUDIT SINKRONISASI: lihat komentar renderBarberList()
    const calBox = MugenUI.el("div", { class: "book-calendar", style: "max-width:520px;" });
    const detailBox = MugenUI.el("div", { style: "margin-top:16px;" });
    body.appendChild(calOfflineBox);
    body.appendChild(calBox);
    body.appendChild(detailBox);

    const HARI = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
    let bookingPerTanggal = {};
    let selectedTanggal = null;

    async function load() {
      calBox.innerHTML = "Memuat...";
      try {
        const qs = new URLSearchParams({ tahun: String(shown.getFullYear()), bulan: String(shown.getMonth() + 1) });
        if (selBarber.value) qs.set("barber_id", selBarber.value);
        const data = await MugenApi.get(`/api/booking?${qs}`, { useCache: true });
        calOfflineBox.innerHTML = "";
        if (data.__offline) calOfflineBox.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        bookingPerTanggal = {};
        for (const b of Array.isArray(data) ? data : []) {
          if (b.status_booking !== "aktif") continue;
          (bookingPerTanggal[b.tanggal] = bookingPerTanggal[b.tanggal] || []).push(b);
        }
        renderGrid();
      } catch (e) {
        calBox.innerHTML = "";
        calBox.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    function renderGrid() {
      calBox.innerHTML = "";
      const y = shown.getFullYear(), m = shown.getMonth();
      const nav = MugenUI.el("div", { class: "book-calendar-nav" });
      const btnPrev = MugenUI.el("button", { type: "button" }, "‹");
      const btnNext = MugenUI.el("button", { type: "button" }, "›");
      btnPrev.addEventListener("click", () => { shown = new Date(y, m - 1, 1); MugenUI.withLoading(load); });
      btnNext.addEventListener("click", () => { shown = new Date(y, m + 1, 1); MugenUI.withLoading(load); });
      nav.appendChild(btnPrev);
      nav.appendChild(MugenUI.el("div", {}, `${MugenUI.namaBulan(m + 1)} ${y}`));
      nav.appendChild(btnNext);
      calBox.appendChild(nav);

      const grid = MugenUI.el("div", { class: "book-calendar-grid" });
      for (const h of HARI) grid.appendChild(MugenUI.el("div", { class: "book-calendar-dow" }, h));
      const firstDay = new Date(y, m, 1);
      const jumlahHari = new Date(y, m + 1, 0).getDate();
      for (let i = 0; i < firstDay.getDay(); i++) grid.appendChild(MugenUI.el("div", { class: "book-calendar-cell empty" }));
      for (let d = 1; d <= jumlahHari; d++) {
        const iso = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        const jumlah = (bookingPerTanggal[iso] || []).length;
        const cell = MugenUI.el("button", {
          type: "button",
          class: "book-calendar-cell" + (iso === selectedTanggal ? " selected" : ""),
        }, [String(d), jumlah ? MugenUI.el("div", { style: "font-size:9px;" }, `${jumlah}`) : null]);
        cell.addEventListener("click", () => { selectedTanggal = iso; renderGrid(); renderDetail(); });
        grid.appendChild(cell);
      }
      calBox.appendChild(grid);
      renderDetail();
    }

    function renderDetail() {
      detailBox.innerHTML = "";
      if (!selectedTanggal) return;
      detailBox.appendChild(MugenUI.el("h2", {}, MugenUI.formatTanggal(selectedTanggal)));
      detailBox.appendChild(bookingTable(bookingPerTanggal[selectedTanggal] || [], { withBarber: true }));
    }

    selBarber.addEventListener("change", () => MugenUI.withLoading(load));
    load();
  }

  // ================= TAB: OPERATING HOURS =================
  const HARI_OPERASIONAL_LABEL = {
    senin: "Senin", selasa: "Selasa", rabu: "Rabu", kamis: "Kamis", jumat: "Jumat", sabtu: "Sabtu", minggu: "Minggu",
  };

  async function renderOperatingHours(body) {
    const card = MugenUI.el("div", { class: "card" });
    body.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Jam Operasional"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Semua slot booking mengikuti jam & hari ini."));

    let s;
    try { s = await MugenApi.get("/api/booking/pengaturan"); } catch (e) { card.appendChild(MugenUI.el("div", {}, e.message)); return; }

    const inBuka = MugenUI.el("input", { type: "time", value: s.jam_buka });
    const inTutup = MugenUI.el("input", { type: "time", value: s.jam_tutup });
    const hariAktif = new Set(s.hari_operasional || Object.keys(HARI_OPERASIONAL_LABEL));
    const hariChecks = {};
    const hariBox = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;flex:none;gap:14px;" });
    for (const [key, label] of Object.entries(HARI_OPERASIONAL_LABEL)) {
      const cb = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
      cb.checked = hariAktif.has(key);
      hariChecks[key] = cb;
      hariBox.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:6px;width:auto;" }, [cb, label]));
    }
    const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const errorBox = MugenUI.el("div", { class: "login-error" });

    card.appendChild(MugenUI.el("label", {}, "Jam Buka"));
    card.appendChild(inBuka);
    card.appendChild(MugenUI.el("label", {}, "Jam Tutup"));
    card.appendChild(inTutup);
    card.appendChild(MugenUI.el("label", {}, "Hari Operasional"));
    card.appendChild(hariBox);
    card.appendChild(errorBox);
    card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

    btnSimpan.addEventListener("click", async () => {
      errorBox.textContent = "";
      const hari_operasional = Object.entries(hariChecks).filter(([, cb]) => cb.checked).map(([k]) => k);
      if (!hari_operasional.length) { errorBox.textContent = "Pilih minimal satu hari operasional."; return; }
      try {
        await MugenUI.withLoading(() => MugenApi.put("/api/booking/pengaturan", { jam_buka: inBuka.value, jam_tutup: inTutup.value, hari_operasional }), { message: "Menyimpan…" });
        MugenUI.toast("Jam operasional disimpan.", "success");
      } catch (e) {
        errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });

    // --- Hari Libur Toko (kalender libur seluruh toko, semua barber sekaligus) ---
    const liburFormCard = MugenUI.el("div", { class: "card" });
    const liburListCard = MugenUI.el("div", { class: "card" });
    body.appendChild(liburFormCard);
    body.appendChild(liburListCard);

    liburFormCard.appendChild(MugenUI.el("h2", {}, "Hari Libur Toko"));
    liburFormCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Berbeda dengan Barber Holiday (per-barber): tanggal di sini menutup SELURUH barber sekaligus, mis. hari libur nasional."));
    const inLiburTanggal = MugenUI.el("input", { type: "date", value: new Date().toISOString().slice(0, 10) });
    const inLiburKeterangan = MugenUI.el("input", { type: "text", placeholder: "mis. Libur Lebaran, Tahun Baru" });
    const btnTambahLibur = MugenUI.el("button", { class: "btn-primary" }, "Tambah Libur Toko");
    const liburError = MugenUI.el("div", { class: "login-error" });

    liburFormCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    liburFormCard.appendChild(inLiburTanggal);
    liburFormCard.appendChild(MugenUI.el("label", {}, "Keterangan (opsional)"));
    liburFormCard.appendChild(inLiburKeterangan);
    liburFormCard.appendChild(liburError);
    liburFormCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnTambahLibur));

    liburListCard.appendChild(MugenUI.el("h2", {}, "Daftar Libur Toko"));
    const liburListBody = MugenUI.el("div");
    liburListCard.appendChild(liburListBody);

    async function loadLiburToko() {
      liburListBody.innerHTML = "Memuat...";
      try {
        const data = await MugenApi.get("/api/booking/toko-libur", { useCache: true });
        liburListBody.innerHTML = "";
        if (data.__offline) liburListBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        liburListBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "keterangan", label: "Keterangan", format: (v) => v || "-" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const btn = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btn.addEventListener("click", async () => {
                  if (!confirm(`Hapus libur toko ${r.tanggal}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/booking/toko-libur/${r.id}`), { message: "Menghapus…" });
                    MugenUI.toast("Libur toko dihapus.", "success");
                    loadLiburToko();
                  } catch (e) { MugenUI.toast(e.message, "error"); }
                });
                return btn;
              },
            },
          ],
          Array.isArray(data) ? data : [],
          { emptyText: "Belum ada libur toko yang dijadwalkan." },
        ));
      } catch (e) {
        liburListBody.innerHTML = "";
        liburListBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    btnTambahLibur.addEventListener("click", async () => {
      liburError.textContent = "";
      if (!inLiburTanggal.value) { liburError.textContent = "Pilih tanggal dulu."; return; }
      try {
        await MugenUI.withLoading(() => MugenApi.post("/api/booking/toko-libur", {
          tanggal: inLiburTanggal.value, keterangan: inLiburKeterangan.value.trim() || null,
        }), { message: "Menyimpan…" });
        MugenUI.toast("Libur toko ditambahkan.", "success");
        inLiburKeterangan.value = "";
        loadLiburToko();
      } catch (e) { liburError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    loadLiburToko();
  }

  // ================= TAB: BARBER HOLIDAY (pakai endpoint libur yg SUDAH ADA) =================
  async function renderBarberHoliday(body, barbers) {
    const formCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    body.appendChild(formCard);
    body.appendChild(listCard);

    formCard.appendChild(MugenUI.el("h2", {}, "Tandai Libur Barber"));
    formCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Barber yang libur otomatis tidak bisa dibooking pada tanggal itu (tetap tampil di halaman booking, abu-abu, status \"On Vacation\")."));
    const selBarber = MugenUI.el("select");
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const inputTanggal = MugenUI.el("input", { type: "date", value: new Date().toISOString().slice(0, 10) });
    const btnTandai = MugenUI.el("button", { class: "btn-primary" }, "Tandai Libur");
    const btnBatalkan = MugenUI.el("button", {}, "Batalkan Libur");
    const errorBox = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(MugenUI.el("label", {}, "Barber"));
    formCard.appendChild(selBarber);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(errorBox);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnTandai, btnBatalkan]));

    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Libur Bulan Ini"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      const today = new Date();
      try {
        const data = await MugenApi.get(`/api/input-data/libur?tahun=${today.getFullYear()}&bulan=${today.getMonth() + 1}`, { useCache: true });
        listBody.innerHTML = "";
        if (data.__offline) listBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_barber", label: "Barber" },
          ],
          Array.isArray(data) ? data : [],
          { emptyText: "Belum ada barber yang libur bulan ini." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    btnTandai.addEventListener("click", async () => {
      errorBox.textContent = "";
      try {
        await MugenUI.withLoading(() => MugenApi.post("/api/input-data/libur", { barber_id: Number(selBarber.value), tanggal: inputTanggal.value }), { message: "Menyimpan…" });
        MugenUI.toast("Ditandai libur.", "success");
        loadList();
      } catch (e) { errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnBatalkan.addEventListener("click", async () => {
      errorBox.textContent = "";
      try {
        await MugenUI.withLoading(() => MugenApi.del("/api/input-data/libur", { barber_id: Number(selBarber.value), tanggal: inputTanggal.value }), { message: "Menghapus…" });
        MugenUI.toast("Libur dibatalkan.", "success");
        loadList();
      } catch (e) { errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    loadList();
  }

  // ================= TAB: CLOSED SLOT =================
  async function renderClosedSlot(body, barbers) {
    const formCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    body.appendChild(formCard);
    body.appendChild(listCard);

    formCard.appendChild(MugenUI.el("h2", {}, "Tutup Slot"));
    formCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Untuk meeting, training, reservasi offline, istirahat, atau keperluan pribadi lain -- jam ini tidak bisa dibooking walau barber sedang masuk kerja."));
    const selBarber = MugenUI.el("select");
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const inputTanggal = MugenUI.el("input", { type: "date", value: new Date().toISOString().slice(0, 10) });
    const inputJamMulai = MugenUI.el("input", { type: "time" });
    const inputJamSelesai = MugenUI.el("input", { type: "time" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "mis. Meeting, Training, Istirahat" });
    const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Tutup Slot");
    const errorBox = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(MugenUI.el("label", {}, "Barber"));
    formCard.appendChild(selBarber);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(MugenUI.el("label", {}, "Jam Mulai"));
    formCard.appendChild(inputJamMulai);
    formCard.appendChild(MugenUI.el("label", {}, "Jam Selesai"));
    formCard.appendChild(inputJamSelesai);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan (opsional)"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(errorBox);
    formCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Slot Ditutup Bulan Ini"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      const today = new Date();
      try {
        const data = await MugenApi.get(`/api/booking/closed-slot?tahun=${today.getFullYear()}&bulan=${today.getMonth() + 1}`, { useCache: true });
        listBody.innerHTML = "";
        if (data.__offline) listBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_barber", label: "Barber" },
            { key: "jam_mulai", label: "Jam", format: (_, r) => `${r.jam_mulai}-${r.jam_selesai}` },
            { key: "keterangan", label: "Keterangan", format: (v) => v || "-" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const btn = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btn.addEventListener("click", async () => {
                  if (!confirm(`Hapus tutup slot ${r.tanggal} ${r.jam_mulai}-${r.jam_selesai}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/booking/closed-slot/${r.id}`), { message: "Menghapus…" });
                    MugenUI.toast("Slot dibuka kembali.", "success");
                    loadList();
                  } catch (e) { MugenUI.toast(e.message, "error"); }
                });
                return btn;
              },
            },
          ],
          Array.isArray(data) ? data : [],
          { emptyText: "Belum ada slot yang ditutup bulan ini." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    btnSimpan.addEventListener("click", async () => {
      errorBox.textContent = "";
      if (!inputJamMulai.value || !inputJamSelesai.value) { errorBox.textContent = "Isi jam mulai dan jam selesai."; return; }
      try {
        await MugenUI.withLoading(() => MugenApi.post("/api/booking/closed-slot", {
          barber_id: Number(selBarber.value), tanggal: inputTanggal.value,
          jam_mulai: inputJamMulai.value, jam_selesai: inputJamSelesai.value,
          keterangan: inputKeterangan.value || null,
        }), { message: "Menyimpan…" });
        MugenUI.toast("Slot ditutup.", "success");
        inputJamMulai.value = ""; inputJamSelesai.value = ""; inputKeterangan.value = "";
        loadList();
      } catch (e) { errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    loadList();
  }

  // ================= TAB: PAYMENT SETTINGS =================
  async function renderPaymentSettings(body) {
    const card = MugenUI.el("div", { class: "card" });
    body.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Metode Pembayaran"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" }, "Hanya metode yang aktif yang ditampilkan ke customer di halaman booking. Semua booking pakai Full Payment (tidak ada DP)."));

    let s;
    try { s = await MugenApi.get("/api/booking/payment-settings"); } catch (e) { card.appendChild(MugenUI.el("div", {}, e.message)); return; }

    const checkboxes = {};
    for (const [key, label] of Object.entries(METODE_LABEL)) {
      const cb = MugenUI.el("input", { type: "checkbox" });
      cb.checked = s.metode_aktif.includes(key);
      checkboxes[key] = cb;
      const catatan = key === "gateway" ? " (segera hadir -- customer belum bisa memilih metode ini walau diaktifkan)" : "";
      card.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:8px;" }, [cb, `${label}${catatan}`]));
    }

    const errorBox1 = MugenUI.el("div", { class: "login-error" });
    const btnSimpanMetode = MugenUI.el("button", { class: "btn-primary" }, "Simpan Metode Aktif");
    card.appendChild(errorBox1);
    card.appendChild(MugenUI.el("div", { style: "margin:12px 0;" }, btnSimpanMetode));
    btnSimpanMetode.addEventListener("click", async () => {
      errorBox1.textContent = "";
      const metode_aktif = Object.entries(checkboxes).filter(([, cb]) => cb.checked).map(([k]) => k);
      try {
        await MugenUI.withLoading(() => MugenApi.put("/api/booking/payment-settings", { metode_aktif }), { message: "Menyimpan…" });
        MugenUI.toast("Metode pembayaran disimpan.", "success");
      } catch (e) { errorBox1.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Label & Instruksi per Metode (tampil di halaman booking Step 6) ---
    const labelCard = MugenUI.el("div", { class: "card" });
    body.appendChild(labelCard);
    labelCard.appendChild(MugenUI.el("h2", {}, "Label & Instruksi Metode Pembayaran"));
    labelCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Nama tombol & pesan yang dilihat customer per metode di halaman booking. Kosongkan untuk pakai default."));
    const inNama = {}, inInstruksi = {};
    for (const [key, label] of Object.entries(METODE_LABEL)) {
      inNama[key] = MugenUI.el("input", { type: "text", value: (s.metode_nama && s.metode_nama[key]) || "" });
      inInstruksi[key] = MugenUI.el("textarea", {}, (s.metode_instruksi && s.metode_instruksi[key]) || "");
      labelCard.appendChild(MugenUI.el("label", {}, `Nama Tampilan — ${label}`));
      labelCard.appendChild(inNama[key]);
      labelCard.appendChild(MugenUI.el("label", {}, `Instruksi — ${label}`));
      labelCard.appendChild(inInstruksi[key]);
    }
    const errorBoxLabel = MugenUI.el("div", { class: "login-error" });
    const btnSimpanLabel = MugenUI.el("button", { class: "btn-primary" }, "Simpan Label & Instruksi");
    labelCard.appendChild(errorBoxLabel);
    labelCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanLabel));
    btnSimpanLabel.addEventListener("click", async () => {
      errorBoxLabel.textContent = "";
      const metode_nama = {}, metode_instruksi = {};
      for (const key of Object.keys(METODE_LABEL)) {
        if (inNama[key].value.trim()) metode_nama[key] = inNama[key].value.trim();
        if (inInstruksi[key].value.trim()) metode_instruksi[key] = inInstruksi[key].value.trim();
      }
      try {
        await MugenUI.withLoading(() => MugenApi.put("/api/booking/payment-settings", { metode_nama, metode_instruksi }), { message: "Menyimpan…" });
        MugenUI.toast("Label & instruksi metode pembayaran disimpan.", "success");
      } catch (e) { errorBoxLabel.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Transfer Bank ---
    const bankCard = MugenUI.el("div", { class: "card" });
    body.appendChild(bankCard);
    bankCard.appendChild(MugenUI.el("h2", {}, "Info Transfer Bank"));
    const inBankNama = MugenUI.el("input", { type: "text", value: s.bank_nama || "" });
    const inBankRek = MugenUI.el("input", { type: "text", value: s.bank_nomor_rekening || "" });
    const inBankAtasNama = MugenUI.el("input", { type: "text", value: s.bank_nama_pemilik || "" });
    bankCard.appendChild(MugenUI.el("label", {}, "Nama Bank"));
    bankCard.appendChild(inBankNama);
    bankCard.appendChild(MugenUI.el("label", {}, "Nomor Rekening"));
    bankCard.appendChild(inBankRek);
    bankCard.appendChild(MugenUI.el("label", {}, "Atas Nama"));
    bankCard.appendChild(inBankAtasNama);
    const errorBox2 = MugenUI.el("div", { class: "login-error" });
    const btnSimpanBank = MugenUI.el("button", { class: "btn-primary" }, "Simpan Info Bank");
    bankCard.appendChild(errorBox2);
    bankCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanBank));
    btnSimpanBank.addEventListener("click", async () => {
      errorBox2.textContent = "";
      try {
        await MugenUI.withLoading(() => MugenApi.put("/api/booking/payment-settings", {
          bank_nama: inBankNama.value, bank_nomor_rekening: inBankRek.value, bank_nama_pemilik: inBankAtasNama.value,
        }), { message: "Menyimpan…" });
        MugenUI.toast("Info transfer bank disimpan.", "success");
      } catch (e) { errorBox2.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- QRIS ---
    const qrisCard = MugenUI.el("div", { class: "card" });
    body.appendChild(qrisCard);
    qrisCard.appendChild(MugenUI.el("h2", {}, "QRIS"));
    qrisCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Upload gambar QRIS statis. Desain modular -- nanti mudah diganti ke QRIS Dynamic/API."));
    const qrisPreview = MugenUI.el("img", { class: "book-qris-img", style: s.qris_url ? "" : "display:none;", alt: "QRIS" });
    if (s.qris_url) qrisPreview.src = MUGEN_API_BASE + s.qris_url;
    const inQrisFile = MugenUI.el("input", { type: "file", accept: "image/jpeg,image/png,image/webp" });
    const inMerchant = MugenUI.el("input", { type: "text", value: s.qris_merchant_nama || "", placeholder: "Nama Merchant" });
    const btnUploadQris = MugenUI.el("button", {}, "Upload / Ganti QRIS");
    const btnHapusQris = MugenUI.el("button", { class: "btn-danger" }, "Hapus QRIS");
    const errorBox3 = MugenUI.el("div", { class: "login-error" });

    qrisCard.appendChild(qrisPreview);
    qrisCard.appendChild(MugenUI.el("label", {}, "Nama Merchant"));
    qrisCard.appendChild(inMerchant);
    qrisCard.appendChild(MugenUI.el("label", {}, "File QRIS (JPG/PNG/WEBP)"));
    qrisCard.appendChild(inQrisFile);
    qrisCard.appendChild(errorBox3);
    qrisCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnUploadQris, btnHapusQris]));

    btnUploadQris.addEventListener("click", async () => {
      errorBox3.textContent = "";
      try {
        await MugenUI.withLoading(async () => {
          if (inMerchant.value !== (s.qris_merchant_nama || "")) {
            await MugenApi.put("/api/booking/payment-settings", { qris_merchant_nama: inMerchant.value });
          }
          if (inQrisFile.files && inQrisFile.files[0]) {
            const hasil = await MugenApi.uploadFile("/api/booking/qris", inQrisFile.files[0]);
            qrisPreview.src = MUGEN_API_BASE + hasil.qris_url + "&t=" + Date.now();
            qrisPreview.style.display = "";
          }
        }, { message: "Mengunggah…" });
        MugenUI.toast("QRIS disimpan.", "success");
      } catch (e) { errorBox3.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnHapusQris.addEventListener("click", async () => {
      if (!confirm("Hapus QRIS yang sedang aktif?")) return;
      try {
        await MugenUI.withLoading(() => MugenApi.del("/api/booking/qris"), { message: "Menghapus…" });
        qrisPreview.style.display = "none";
        MugenUI.toast("QRIS dihapus.", "success");
      } catch (e) { MugenUI.toast(e.message, "error"); }
    });
  }

  // ================= TAB: BOOKING SETTINGS =================
  async function renderBookingSettings(body) {
    // Link Booking: SELALU mengikuti domain saat ini (window.location.origin),
    // bukan setting yang disimpan -- otomatis benar begitu domain berganti,
    // tidak perlu ubah kode apa pun (lihat klarifikasi #4 spesifikasi).
    const linkCard = MugenUI.el("div", { class: "card" });
    body.appendChild(linkCard);
    linkCard.appendChild(MugenUI.el("h2", {}, "Link Booking"));
    linkCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Link ini otomatis mengikuti domain aplikasi -- bagikan ke customer."));
    const linkBooking = `${window.location.origin}/#/book`;
    const inLink = MugenUI.el("input", { type: "text", value: linkBooking, readOnly: true });
    const btnSalinLink = MugenUI.el("button", {}, "Salin Link");
    btnSalinLink.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(linkBooking);
        MugenUI.toast("Link booking disalin.", "success");
      } catch (e) {
        inLink.select();
        MugenUI.toast("Gagal menyalin otomatis -- link sudah disorot, salin manual (Ctrl+C).", "error");
      }
    });
    linkCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;" }, [inLink, btnSalinLink]));

    const card = MugenUI.el("div", { class: "card" });
    body.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Pengaturan Booking"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Durasi per service diatur di menu Setting > Layanan (bukan di sini)."));

    let s;
    try { s = await MugenApi.get("/api/booking/pengaturan"); } catch (e) { card.appendChild(MugenUI.el("div", {}, e.message)); return; }

    const inInterval = MugenUI.el("input", { type: "number", min: "5", step: "5", value: String(s.interval_menit) });
    const inMaksHari = MugenUI.el("input", { type: "number", min: "1", value: String(s.maksimal_hari_kedepan) });
    const errorBox = MugenUI.el("div", { class: "login-error" });
    const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan");

    card.appendChild(MugenUI.el("label", {}, "Interval Slot (menit)"));
    card.appendChild(inInterval);
    card.appendChild(MugenUI.el("label", {}, "Maksimal Booking ke Depan (hari)"));
    card.appendChild(inMaksHari);
    card.appendChild(errorBox);
    card.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan));

    btnSimpan.addEventListener("click", async () => {
      errorBox.textContent = "";
      try {
        await MugenUI.withLoading(() => MugenApi.put("/api/booking/pengaturan", {
          interval_menit: Number(inInterval.value), maksimal_hari_kedepan: Number(inMaksHari.value),
        }), { message: "Menyimpan…" });
        MugenUI.toast("Pengaturan booking disimpan.", "success");
      } catch (e) { errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Header, Footer & Pesan Halaman Booking ---
    const headerCard = MugenUI.el("div", { class: "card" });
    body.appendChild(headerCard);
    headerCard.appendChild(MugenUI.el("h2", {}, "Header, Footer & Pesan Halaman Booking"));
    headerCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Banner tampilan header memakai Banner di Setting > Identitas Barbershop."));

    const inJudul = MugenUI.el("input", { type: "text", value: s.header_judul || "", placeholder: "mis. Nama Barbershop (default: Nama Barbershop)" });
    const inSubtitle = MugenUI.el("input", { type: "text", value: s.header_subtitle || "", placeholder: "mis. Booking Online" });
    const inFooter = MugenUI.el("input", { type: "text", value: s.header_footer || "" });
    const inPembuka = MugenUI.el("textarea", {}, s.pesan_pembuka || "");
    const inPenutup = MugenUI.el("textarea", {}, s.pesan_penutup || "");
    const inNamaKosong = MugenUI.el("input", { type: "text", value: s.pesan_nama_kosong || "" });
    const inWaInvalid = MugenUI.el("input", { type: "text", value: s.pesan_whatsapp_invalid || "" });
    const errorBoxHeader = MugenUI.el("div", { class: "login-error" });
    const btnSimpanHeader = MugenUI.el("button", { class: "btn-primary" }, "Simpan");

    headerCard.appendChild(MugenUI.el("label", {}, "Judul Header"));
    headerCard.appendChild(inJudul);
    headerCard.appendChild(MugenUI.el("label", {}, "Subtitle Header"));
    headerCard.appendChild(inSubtitle);
    headerCard.appendChild(MugenUI.el("label", {}, "Footer"));
    headerCard.appendChild(inFooter);
    headerCard.appendChild(MugenUI.el("label", {}, "Pesan Pembuka (tampil di bawah judul)"));
    headerCard.appendChild(inPembuka);
    headerCard.appendChild(MugenUI.el("label", {}, "Pesan Penutup (tampil setelah booking berhasil)"));
    headerCard.appendChild(inPenutup);
    headerCard.appendChild(MugenUI.el("label", {}, "Pesan Validasi: Nama Kosong"));
    headerCard.appendChild(inNamaKosong);
    headerCard.appendChild(MugenUI.el("label", {}, "Pesan Validasi: WhatsApp Tidak Valid"));
    headerCard.appendChild(inWaInvalid);
    headerCard.appendChild(errorBoxHeader);
    headerCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanHeader));

    btnSimpanHeader.addEventListener("click", async () => {
      errorBoxHeader.textContent = "";
      try {
        await MugenUI.withLoading(() => MugenApi.put("/api/booking/pengaturan", {
          header_judul: inJudul.value.trim(),
          header_subtitle: inSubtitle.value.trim(),
          header_footer: inFooter.value.trim(),
          pesan_pembuka: inPembuka.value.trim(),
          pesan_penutup: inPenutup.value.trim(),
          pesan_nama_kosong: inNamaKosong.value.trim(),
          pesan_whatsapp_invalid: inWaInvalid.value.trim(),
        }), { message: "Menyimpan…" });
        MugenUI.toast("Header, footer & pesan booking disimpan.", "success");
      } catch (e) { errorBoxHeader.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
  }

  return { render };
})();
