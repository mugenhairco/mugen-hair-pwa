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

  // REVISI: nomor WhatsApp customer di Menu Booking ditampilkan sebagai link
  // wa.me yang bisa langsung diklik admin (buka chat, tanpa pesan otomatis),
  // supaya admin tidak perlu copy-paste nomor manual. wa.me mewajibkan format
  // internasional tanpa "+"/spasi/tanda baca, jadi nomor lokal (awalan 0)
  // dikonversi ke 62 dulu di sini sebelum dipakai sebagai href.
  function nomorKeFormatInternasional(nomorMentah) {
    const digits = String(nomorMentah).replace(/[^\d+]/g, "");
    if (digits.startsWith("+62")) return digits.slice(1);
    if (digits.startsWith("62")) return digits;
    if (digits.startsWith("0")) return "62" + digits.slice(1);
    return digits.replace(/^\+/, "");
  }

  function waLinkCell(nomorMentah) {
    if (!nomorMentah) return "-";
    const intl = nomorKeFormatInternasional(nomorMentah);
    if (!intl) return String(nomorMentah);
    return MugenUI.el("a", {
      href: `https://wa.me/${intl}`,
      target: "_blank",
      rel: "noopener noreferrer",
    }, "+" + intl);
  }

  async function render(root) {
    const user = MugenState.getUser();
    const isAdmin = user.role === "admin" || user.role === "staff";
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Booking"));

    if (!isAdmin) {
      await renderBarberList(root);
      return;
    }

    // REVISI Website Content (PR 1): tab "Website Content" HANYA untuk Owner
    // ('admin'), TIDAK PERNAH untuk staff ('Admin') -- sama seperti pola tab
    // Owner-murni di pengaturan.js (Komisi/Bonus Service/Hak Akses Admin),
    // BUKAN lewat sistem izin permissions.py.
    const isOwner = user.role === "admin";
    const tabs = [
      "Booking List", "Calendar", "Operating Hours", "Barber Holiday", "Closed Slot", "Payment Settings", "Booking Settings",
      ...(isOwner ? ["Website Content"] : []),
    ];
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
      else if (activeTab === "Website Content") await renderWebsiteContent(body);
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
    // BOOKING UI/UX #1: No. Transaksi -- SATU-SATUNYA implementasi ada di
    // MugenUI.buatNomorTransaksi() (ui.js), dipakai di sini DAN di layar
    // Appointment Confirmed (book_public.js) supaya angkanya selalu sama
    // persis untuk booking yang sama.
    const namaBarbershop = MugenBrand.get().nama_barbershop;
    const columns = [
      { key: "no_transaksi", label: "No. Transaksi", format: (_, r) => MugenUI.buatNomorTransaksi(r, namaBarbershop) },
      { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
      { key: "jam_mulai", label: "Jam", format: (_, r) => `${r.jam_mulai}-${r.jam_selesai}` },
      ...(withBarber ? [{ key: "nama_barber", label: "Barber" }] : []),
      { key: "customer_nama", label: "Customer" },
      { key: "customer_whatsapp", label: "WhatsApp", format: (v) => waLinkCell(v) },
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

    // Feature Gating "qris": Owner yang paketnya tidak menyertakan fitur
    // ini TIDAK BISA upload/ganti/hapus QRIS baru (backend menggerbang
    // POST/DELETE /api/booking/qris sama persis, lihat routers/booking.py)
    // -- tapi gambar QRIS yang SUDAH terupload (qrisPreview di atas) TETAP
    // tampil apa adanya, read-only, TIDAK ikut disembunyikan/dihapus, cuma
    // kemampuan MENGUBAHNYA yang dikunci.
    if (typeof MugenFeature !== "undefined" && !MugenFeature.has("qris")) {
      inMerchant.disabled = true;
      inQrisFile.disabled = true;
      btnUploadQris.disabled = true;
      btnHapusQris.disabled = true;
      qrisCard.appendChild(MugenFeature.upgradeBlock("QRIS"));
    }

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
    const linkCard = MugenUI.el("div", { class: "card" });
    body.appendChild(linkCard);
    linkCard.appendChild(MugenUI.el("h2", {}, "Link Booking"));
    linkCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Link ini otomatis mengikuti domain aplikasi -- bagikan ke customer."));
    // Link Booking: SELALU mengikuti domain saat ini (window.location.origin),
    // bukan setting yang disimpan -- otomatis benar begitu domain berganti,
    // tidak perlu ubah kode apa pun (lihat klarifikasi #4 spesifikasi).
    // BUGFIX: sebelumnya hanya memakai origin ("https://domain"), tanpa
    // path -- benar SELAMA aplikasi ini di-serve dari root domain ("/").
    // Sejak FONDASI Multi-Tenant Phase 5 (Landing Page publik di "/",
    // Dashboard PWA INI di "/app/"), origin saja menghasilkan link SALAH
    // ("https://domain/#/book" -> mendarat di Landing Page yang tidak
    // punya router hash sama sekali, BUKAN halaman /book yang sebenarnya)
    // -- customer yang mengklik link lama/tersimpan mendarat di halaman
    // marketing kosong, bukan halaman booking. Path saat ini
    // (window.location.pathname, SELALU "/app/" karena file ini cuma
    // dimuat dari sana) diikutkan juga supaya link tetap benar di mana pun
    // aplikasi ini di-mount, otomatis, tanpa perlu ubah kode lagi kalau
    // base path berubah lagi nanti.
    const basePath = window.location.pathname.replace(/index\.html$/, "").replace(/\/+$/, "");
    const linkBooking = `${window.location.origin}${basePath}/#/book`;
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

    // --- Pesan Booking (transaksional -- BUKAN konten tampilan website,
    // lihat komentar di booking_db.py: Header/Footer/Pesan Pembuka
    // DIPINDAHKAN ke Booking > Website Content, field di bawah ini tetap
    // di sini karena murni pesan konfirmasi & validasi form) ---
    const pesanCard = MugenUI.el("div", { class: "card" });
    body.appendChild(pesanCard);
    pesanCard.appendChild(MugenUI.el("h2", {}, "Pesan Booking"));
    pesanCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Tampilan Hero/Footer halaman Website diatur di Booking → Website Content. Pesan di bawah ini khusus untuk konfirmasi & validasi form booking."));

    const inPenutup = MugenUI.el("textarea", {}, s.pesan_penutup || "");
    const inNamaKosong = MugenUI.el("input", { type: "text", value: s.pesan_nama_kosong || "" });
    const inWaInvalid = MugenUI.el("input", { type: "text", value: s.pesan_whatsapp_invalid || "" });
    const errorBoxPesan = MugenUI.el("div", { class: "login-error" });
    const btnSimpanPesan = MugenUI.el("button", { class: "btn-primary" }, "Simpan");

    pesanCard.appendChild(MugenUI.el("label", {}, "Pesan Penutup (tampil setelah booking berhasil)"));
    pesanCard.appendChild(inPenutup);
    pesanCard.appendChild(MugenUI.el("label", {}, "Pesan Validasi: Nama Kosong"));
    pesanCard.appendChild(inNamaKosong);
    pesanCard.appendChild(MugenUI.el("label", {}, "Pesan Validasi: WhatsApp Tidak Valid"));
    pesanCard.appendChild(inWaInvalid);
    pesanCard.appendChild(errorBoxPesan);
    pesanCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanPesan));

    btnSimpanPesan.addEventListener("click", async () => {
      errorBoxPesan.textContent = "";
      try {
        await MugenUI.withLoading(() => MugenApi.put("/api/booking/pengaturan", {
          pesan_penutup: inPenutup.value.trim(),
          pesan_nama_kosong: inNamaKosong.value.trim(),
          pesan_whatsapp_invalid: inWaInvalid.value.trim(),
        }), { message: "Menyimpan…" });
        MugenUI.toast("Pesan booking disimpan.", "success");
      } catch (e) { errorBoxPesan.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
  }

  // ================= TAB: WEBSITE CONTENT (Owner-only) =================
  // REVISI STRUKTUR WEBSITE CONTENT: SATU-SATUNYA tempat pengaturan
  // tampilan halaman publik /book -- Tagline, Deskripsi, Alamat, Nomor
  // WhatsApp, Instagram, dan Hero Image genuinely DIKELOLA DI SINI sekarang
  // (dipindah dari Identitas Barbershop, BUKAN dibaca read-only lagi).
  // Field yang TETAP di tab lain (Nama Barbershop/Email/Logo di Identitas;
  // jam & hari libur di Operating Hours; pesan konfirmasi/validasi di
  // Booking Settings) tetap hanya ditampilkan sebagai ringkasan + arahan.
  // SEO/Branding warna/Favicon/Splash Screen/link CTA eksternal/Footer
  // legal SUDAH DIHAPUS TOTAL -- tidak ada pengaturan untuk itu lagi.
  async function renderWebsiteContent(body) {
    let content, gallery;
    try {
      [content, gallery] = await Promise.all([
        MugenApi.get("/api/website/content"),
        MugenApi.get("/api/website/gallery"),
      ]);
    } catch (e) {
      body.appendChild(MugenUI.el("div", {}, e.message));
      return;
    }

    async function simpanContent(patch) {
      Object.assign(content, patch);
      await MugenApi.put("/api/website/content", {
        hero_tipe: content.hero_tipe, tagline: content.tagline,
        about_judul: content.about_judul, about_deskripsi: content.about_deskripsi,
        alamat: content.alamat, visit_maps_embed_url: content.visit_maps_embed_url, visit_maps_link: content.visit_maps_link,
        instagram: content.instagram, tiktok: content.tiktok, whatsapp: content.whatsapp,
        telepon: content.telepon,
        booking_cta_judul: content.booking_cta_judul, booking_cta_subjudul: content.booking_cta_subjudul,
        booking_cta_tombol_teks: content.booking_cta_tombol_teks,
      });
    }

    body.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Seluruh konten di sini tampil di halaman Website publik (/book), langsung tanpa perlu deploy ulang. Field yang bertanda \"dikelola di ...\" diedit dari tab/menu lain supaya tidak ada dua tempat berbeda untuk data yang sama."));

    // --- Hero ---
    const heroCard = MugenUI.el("div", { class: "card" });
    body.appendChild(heroCard);
    heroCard.appendChild(MugenUI.el("h2", {}, "Hero"));
    heroCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Nama Brand & Logo dikelola di Setting → Identitas Barbershop."));

    const selHeroTipe = MugenUI.el("select");
    selHeroTipe.appendChild(MugenUI.el("option", { value: "image" }, "Gambar (Hero Image di bawah)"));
    selHeroTipe.appendChild(MugenUI.el("option", { value: "video" }, "Video (Hero Video di bawah)"));
    selHeroTipe.value = content.hero_tipe || "image";
    heroCard.appendChild(MugenUI.el("label", {}, "Yang Ditampilkan di Hero"));
    heroCard.appendChild(selHeroTipe);

    // Hero Image
    const heroImagePreview = MugenUI.el("img", { class: "logo-preview", style: content.hero_image_url ? "" : "display:none;", alt: "Hero Image" });
    if (content.hero_image_url) heroImagePreview.src = MUGEN_API_BASE + content.hero_image_url;
    const inHeroImageFile = MugenUI.el("input", { type: "file", accept: "image/jpeg,image/png,image/webp" });
    const btnUploadHeroImage = MugenUI.el("button", { type: "button" }, "Upload / Ganti Hero Image");
    const btnHapusHeroImage = MugenUI.el("button", { type: "button", class: "btn-danger" }, "Hapus Hero Image");
    const errorHeroImage = MugenUI.el("div", { class: "login-error" });
    heroCard.appendChild(MugenUI.el("label", { style: "margin-top:10px;" }, "Hero Image (JPG/PNG/WEBP)"));
    heroCard.appendChild(heroImagePreview);
    heroCard.appendChild(inHeroImageFile);
    heroCard.appendChild(errorHeroImage);
    heroCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin:8px 0;" }, [btnUploadHeroImage, btnHapusHeroImage]));

    btnUploadHeroImage.addEventListener("click", async () => {
      errorHeroImage.textContent = "";
      if (!inHeroImageFile.files || !inHeroImageFile.files[0]) { errorHeroImage.textContent = "Pilih file gambar dulu."; return; }
      try {
        const hasil = await MugenUI.withLoading(() => MugenApi.uploadFile("/api/website/hero-image", inHeroImageFile.files[0]), { message: "Mengunggah…" });
        content.hero_image_url = hasil.hero_image_url;
        heroImagePreview.src = MUGEN_API_BASE + hasil.hero_image_url + "&t=" + Date.now();
        heroImagePreview.style.display = "";
        MugenUI.toast("Hero Image disimpan.", "success");
      } catch (e) { errorHeroImage.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnHapusHeroImage.addEventListener("click", async () => {
      if (!confirm("Hapus Hero Image yang sedang aktif?")) return;
      try {
        await MugenUI.withLoading(() => MugenApi.del("/api/website/hero-image"), { message: "Menghapus…" });
        content.hero_image_url = null;
        heroImagePreview.style.display = "none";
        MugenUI.toast("Hero Image dihapus.", "success");
      } catch (e) { MugenUI.toast(e.message, "error"); }
    });

    // Hero Video -- format fleksibel selama didukung browser modern
    const heroVideoPreview = MugenUI.el("video", {
      controls: "controls",
      style: content.hero_video_url ? "max-width:320px;display:block;margin:8px 0;border-radius:10px;" : "display:none;",
    });
    if (content.hero_video_url) heroVideoPreview.src = MUGEN_API_BASE + content.hero_video_url;
    const inHeroVideoFile = MugenUI.el("input", { type: "file", accept: "video/mp4,video/webm,video/quicktime,video/x-m4v,video/ogg,.mov" });
    const btnUploadHeroVideo = MugenUI.el("button", { type: "button" }, "Upload / Ganti Hero Video");
    const btnHapusHeroVideo = MugenUI.el("button", { type: "button", class: "btn-danger" }, "Hapus Hero Video");
    const errorHeroVideo = MugenUI.el("div", { class: "login-error" });
    heroCard.appendChild(MugenUI.el("label", { style: "margin-top:10px;" }, "Hero Video (MP4/MOV/WEBM/dst, maks 50MB)"));
    heroCard.appendChild(heroVideoPreview);
    heroCard.appendChild(inHeroVideoFile);
    heroCard.appendChild(errorHeroVideo);
    heroCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin:8px 0;" }, [btnUploadHeroVideo, btnHapusHeroVideo]));

    btnUploadHeroVideo.addEventListener("click", async () => {
      errorHeroVideo.textContent = "";
      if (!inHeroVideoFile.files || !inHeroVideoFile.files[0]) { errorHeroVideo.textContent = "Pilih file video dulu."; return; }
      try {
        const hasil = await MugenUI.withLoading(() => MugenApi.uploadFile("/api/website/hero-video", inHeroVideoFile.files[0]), { message: "Mengunggah…" });
        content.hero_video_url = hasil.hero_video_url;
        heroVideoPreview.src = MUGEN_API_BASE + hasil.hero_video_url + "&t=" + Date.now();
        heroVideoPreview.style.display = "block";
        MugenUI.toast("Hero Video disimpan.", "success");
      } catch (e) { errorHeroVideo.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnHapusHeroVideo.addEventListener("click", async () => {
      if (!confirm("Hapus Hero Video yang sedang aktif?")) return;
      try {
        await MugenUI.withLoading(() => MugenApi.del("/api/website/hero-video"), { message: "Menghapus…" });
        content.hero_video_url = null;
        heroVideoPreview.style.display = "none";
        MugenUI.toast("Hero Video dihapus.", "success");
      } catch (e) { MugenUI.toast(e.message, "error"); }
    });

    const inTagline = MugenUI.el("input", { type: "text", value: content.tagline || "", placeholder: "mis. We don't fix hair. We fix egos." });
    heroCard.appendChild(MugenUI.el("label", { style: "margin-top:10px;" }, "Tagline"));
    heroCard.appendChild(inTagline);

    const errorHero = MugenUI.el("div", { class: "login-error" });
    const btnSimpanHero = MugenUI.el("button", { class: "btn-primary" }, "Simpan Hero");
    heroCard.appendChild(errorHero);
    heroCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanHero));
    btnSimpanHero.addEventListener("click", async () => {
      errorHero.textContent = "";
      try {
        await MugenUI.withLoading(() => simpanContent({
          hero_tipe: selHeroTipe.value, tagline: inTagline.value.trim(),
        }), { message: "Menyimpan…" });
        MugenUI.toast("Hero disimpan.", "success");
      } catch (e) { errorHero.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Choose Barber (foto barber tampil di step "Pilih Barber" wizard
    // booking publik) -- foto dikelola di Setting > Karyawan supaya satu
    // tempat yang sama dipakai untuk data barber di seluruh aplikasi. ---
    const barberCard = MugenUI.el("div", { class: "card" });
    body.appendChild(barberCard);
    barberCard.appendChild(MugenUI.el("h2", {}, "Choose Barber (Foto Barber)"));
    barberCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Foto tiap barber yang tampil di step \"Pilih Barber\" halaman booking publik dikelola di Setting → Karyawan (tombol \"Foto\" pada tiap baris barber)."));

    // --- About ---
    const aboutCard = MugenUI.el("div", { class: "card" });
    body.appendChild(aboutCard);
    aboutCard.appendChild(MugenUI.el("h2", {}, "About"));
    const inAboutJudul = MugenUI.el("input", { type: "text", value: content.about_judul || "" });
    const inAboutDeskripsi = MugenUI.el("textarea", {}, content.about_deskripsi || "");
    aboutCard.appendChild(MugenUI.el("label", {}, "Judul"));
    aboutCard.appendChild(inAboutJudul);
    aboutCard.appendChild(MugenUI.el("label", {}, "Deskripsi"));
    aboutCard.appendChild(inAboutDeskripsi);

    const aboutFotoPreview = MugenUI.el("img", { class: "logo-preview", style: content.about_foto_url ? "" : "display:none;", alt: "Foto About" });
    if (content.about_foto_url) aboutFotoPreview.src = MUGEN_API_BASE + content.about_foto_url;
    const inAboutFotoFile = MugenUI.el("input", { type: "file", accept: "image/jpeg,image/png,image/webp" });
    const btnUploadAboutFoto = MugenUI.el("button", { type: "button" }, "Upload / Ganti Foto");
    const btnHapusAboutFoto = MugenUI.el("button", { type: "button", class: "btn-danger" }, "Hapus Foto");
    const errorAboutFoto = MugenUI.el("div", { class: "login-error" });
    aboutCard.appendChild(MugenUI.el("label", { style: "margin-top:10px;" }, "Foto About"));
    aboutCard.appendChild(aboutFotoPreview);
    aboutCard.appendChild(inAboutFotoFile);
    aboutCard.appendChild(errorAboutFoto);
    aboutCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin:8px 0;" }, [btnUploadAboutFoto, btnHapusAboutFoto]));

    btnUploadAboutFoto.addEventListener("click", async () => {
      errorAboutFoto.textContent = "";
      if (!inAboutFotoFile.files || !inAboutFotoFile.files[0]) { errorAboutFoto.textContent = "Pilih file foto dulu."; return; }
      try {
        const hasil = await MugenUI.withLoading(() => MugenApi.uploadFile("/api/website/about-foto", inAboutFotoFile.files[0]), { message: "Mengunggah…" });
        aboutFotoPreview.src = MUGEN_API_BASE + hasil.about_foto_url + "&t=" + Date.now();
        aboutFotoPreview.style.display = "";
        MugenUI.toast("Foto About disimpan.", "success");
      } catch (e) { errorAboutFoto.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnHapusAboutFoto.addEventListener("click", async () => {
      if (!confirm("Hapus Foto About yang sedang aktif?")) return;
      try {
        await MugenUI.withLoading(() => MugenApi.del("/api/website/about-foto"), { message: "Menghapus…" });
        aboutFotoPreview.style.display = "none";
        MugenUI.toast("Foto About dihapus.", "success");
      } catch (e) { MugenUI.toast(e.message, "error"); }
    });

    const errorAbout = MugenUI.el("div", { class: "login-error" });
    const btnSimpanAbout = MugenUI.el("button", { class: "btn-primary" }, "Simpan About");
    aboutCard.appendChild(errorAbout);
    aboutCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanAbout));
    btnSimpanAbout.addEventListener("click", async () => {
      errorAbout.textContent = "";
      try {
        await MugenUI.withLoading(() => simpanContent({ about_judul: inAboutJudul.value.trim(), about_deskripsi: inAboutDeskripsi.value.trim() }), { message: "Menyimpan…" });
        MugenUI.toast("About disimpan.", "success");
      } catch (e) { errorAbout.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Gallery ---
    const galleryCard = MugenUI.el("div", { class: "card" });
    body.appendChild(galleryCard);
    galleryCard.appendChild(MugenUI.el("h2", {}, "Gallery"));
    galleryCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Bisa foto maupun video (format apa saja yang didukung browser). Seret (drag) untuk mengubah urutan, atau pakai tombol ↑/↓ (lebih andal di layar sentuh)."));
    const galleryGrid = MugenUI.el("div", { class: "website-gallery-grid" });
    galleryCard.appendChild(galleryGrid);

    async function simpanUrutanGallery(disusun) {
      try {
        gallery = await MugenUI.withLoading(
          () => MugenApi.put("/api/website/gallery/reorder", { ordered_ids: disusun.map((f) => f.id) }),
          { message: "Menyimpan urutan…" },
        );
        renderGalleryGrid();
      } catch (e) { MugenUI.toast(e.message, "error"); }
    }

    function renderGalleryGrid() {
      galleryGrid.innerHTML = "";
      gallery.forEach((foto, idx) => {
        const item = MugenUI.el("div", { class: "website-gallery-item", draggable: "true" });
        item.appendChild(
          foto.tipe === "video"
            ? MugenUI.el("video", { src: MUGEN_API_BASE + foto.foto_url, controls: "controls", muted: "muted" })
            : MugenUI.el("img", { src: MUGEN_API_BASE + foto.foto_url, alt: "Gallery" }),
        );
        const btnNaik = MugenUI.el("button", { type: "button", title: "Naikkan urutan" }, "↑");
        if (idx === 0) btnNaik.disabled = true;
        btnNaik.addEventListener("click", () => {
          const disusun = gallery.slice();
          [disusun[idx - 1], disusun[idx]] = [disusun[idx], disusun[idx - 1]];
          simpanUrutanGallery(disusun);
        });
        const btnTurun = MugenUI.el("button", { type: "button", title: "Turunkan urutan" }, "↓");
        if (idx === gallery.length - 1) btnTurun.disabled = true;
        btnTurun.addEventListener("click", () => {
          const disusun = gallery.slice();
          [disusun[idx], disusun[idx + 1]] = [disusun[idx + 1], disusun[idx]];
          simpanUrutanGallery(disusun);
        });
        const btnHapus = MugenUI.el("button", { type: "button", class: "btn-danger", title: "Hapus item" }, "✕");
        btnHapus.addEventListener("click", async () => {
          if (!confirm("Hapus item ini dari Gallery?")) return;
          try {
            gallery = await MugenUI.withLoading(() => MugenApi.del(`/api/website/gallery/${foto.id}`), { message: "Menghapus…" });
            renderGalleryGrid();
            MugenUI.toast("Item Gallery dihapus.", "success");
          } catch (e) { MugenUI.toast(e.message, "error"); }
        });
        item.appendChild(MugenUI.el("div", { class: "website-gallery-item-aksi" }, [btnNaik, btnTurun, btnHapus]));

        item.addEventListener("dragstart", (e) => {
          e.dataTransfer.setData("text/plain", String(idx));
          e.dataTransfer.effectAllowed = "move";
        });
        item.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; });
        item.addEventListener("drop", (e) => {
          e.preventDefault();
          const dariIdx = Number(e.dataTransfer.getData("text/plain"));
          if (Number.isNaN(dariIdx) || dariIdx === idx) return;
          const disusun = gallery.slice();
          const [dipindah] = disusun.splice(dariIdx, 1);
          disusun.splice(idx, 0, dipindah);
          simpanUrutanGallery(disusun);
        });

        galleryGrid.appendChild(item);
      });
    }
    renderGalleryGrid();

    const inGalleryFiles = MugenUI.el("input", {
      type: "file",
      accept: "image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime,video/x-m4v,video/ogg,.mov",
      multiple: "multiple",
    });
    const btnUploadGallery = MugenUI.el("button", { class: "btn-primary" }, "Upload Foto/Video");
    const errorGallery = MugenUI.el("div", { class: "login-error" });
    galleryCard.appendChild(MugenUI.el("label", { style: "margin-top:10px;" }, "Tambah Foto/Video (bisa pilih banyak sekaligus, video maks 50MB)"));
    galleryCard.appendChild(inGalleryFiles);
    galleryCard.appendChild(errorGallery);
    galleryCard.appendChild(MugenUI.el("div", { style: "margin-top:8px;" }, btnUploadGallery));
    btnUploadGallery.addEventListener("click", async () => {
      errorGallery.textContent = "";
      if (!inGalleryFiles.files || !inGalleryFiles.files.length) { errorGallery.textContent = "Pilih minimal satu foto/video dulu."; return; }
      try {
        await MugenUI.withLoading(async () => {
          for (const file of inGalleryFiles.files) {
            gallery = await MugenApi.uploadFile("/api/website/gallery", file);
          }
        }, { message: "Mengunggah…" });
        inGalleryFiles.value = "";
        renderGalleryGrid();
        MugenUI.toast("Gallery ditambahkan.", "success");
      } catch (e) { errorGallery.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Visit Us ---
    const visitCard = MugenUI.el("div", { class: "card" });
    body.appendChild(visitCard);
    visitCard.appendChild(MugenUI.el("h2", {}, "Visit Us"));
    const inAlamat = MugenUI.el("textarea", {}, content.alamat || "");
    const inMapsEmbed = MugenUI.el("input", { type: "text", value: content.visit_maps_embed_url || "", placeholder: "URL src iframe Google Maps Embed" });
    const inMapsLink = MugenUI.el("input", { type: "text", value: content.visit_maps_link || "", placeholder: "Link “Buka di Google Maps”" });
    visitCard.appendChild(MugenUI.el("label", {}, "Alamat"));
    visitCard.appendChild(inAlamat);
    visitCard.appendChild(MugenUI.el("label", {}, "Google Maps Embed URL"));
    visitCard.appendChild(inMapsEmbed);
    visitCard.appendChild(MugenUI.el("label", {}, "Link Google Maps"));
    visitCard.appendChild(inMapsLink);
    const errorVisit = MugenUI.el("div", { class: "login-error" });
    const btnSimpanVisit = MugenUI.el("button", { class: "btn-primary" }, "Simpan Visit Us");
    visitCard.appendChild(errorVisit);
    visitCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanVisit));
    btnSimpanVisit.addEventListener("click", async () => {
      errorVisit.textContent = "";
      try {
        await MugenUI.withLoading(() => simpanContent({
          alamat: inAlamat.value.trim(), visit_maps_embed_url: inMapsEmbed.value.trim(), visit_maps_link: inMapsLink.value.trim(),
        }), { message: "Menyimpan…" });
        MugenUI.toast("Visit Us disimpan.", "success");
      } catch (e) { errorVisit.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Opening Hours (pointer -- edit tetap di tab Operating Hours,
    // SATU sumber kebenaran yang sama dipakai slot booking, tidak
    // diduplikasi jadi form kedua di sini) ---
    const hoursCard = MugenUI.el("div", { class: "card" });
    body.appendChild(hoursCard);
    hoursCard.appendChild(MugenUI.el("h2", {}, "Opening Hours"));
    hoursCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Jam & hari operasional (dipakai juga untuk ketersediaan slot booking) dikelola di tab Operating Hours di atas."));

    // --- Social Media ---
    const socialCard = MugenUI.el("div", { class: "card" });
    body.appendChild(socialCard);
    socialCard.appendChild(MugenUI.el("h2", {}, "Social Media"));
    socialCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Ikon hanya tampil di Website kalau link-nya diisi."));
    const inInstagram = MugenUI.el("input", { type: "text", value: content.instagram || "", placeholder: "https://instagram.com/..." });
    const inTiktok = MugenUI.el("input", { type: "text", value: content.tiktok || "", placeholder: "https://tiktok.com/@..." });
    const inWhatsapp = MugenUI.el("input", { type: "text", value: content.whatsapp || "", placeholder: "08xxxxxxxxxx" });
    socialCard.appendChild(MugenUI.el("label", {}, "Instagram"));
    socialCard.appendChild(inInstagram);
    socialCard.appendChild(MugenUI.el("label", {}, "TikTok"));
    socialCard.appendChild(inTiktok);
    socialCard.appendChild(MugenUI.el("label", {}, "WhatsApp"));
    socialCard.appendChild(inWhatsapp);
    const errorSocial = MugenUI.el("div", { class: "login-error" });
    const btnSimpanSocial = MugenUI.el("button", { class: "btn-primary" }, "Simpan Social Media");
    socialCard.appendChild(errorSocial);
    socialCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanSocial));
    btnSimpanSocial.addEventListener("click", async () => {
      errorSocial.textContent = "";
      try {
        await MugenUI.withLoading(() => simpanContent({
          instagram: inInstagram.value.trim(), tiktok: inTiktok.value.trim(), whatsapp: inWhatsapp.value.trim(),
        }), { message: "Menyimpan…" });
        MugenUI.toast("Social Media disimpan.", "success");
      } catch (e) { errorSocial.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Contact ---
    const contactCard = MugenUI.el("div", { class: "card" });
    body.appendChild(contactCard);
    contactCard.appendChild(MugenUI.el("h2", {}, "Contact"));
    contactCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Email dikelola di Setting → Identitas Barbershop."));
    const inTelepon = MugenUI.el("input", { type: "text", value: content.telepon || "" });
    contactCard.appendChild(MugenUI.el("label", {}, "Nomor Telepon"));
    contactCard.appendChild(inTelepon);
    const errorContact = MugenUI.el("div", { class: "login-error" });
    const btnSimpanContact = MugenUI.el("button", { class: "btn-primary" }, "Simpan Contact");
    contactCard.appendChild(errorContact);
    contactCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanContact));
    btnSimpanContact.addEventListener("click", async () => {
      errorContact.textContent = "";
      try {
        await MugenUI.withLoading(() => simpanContent({ telepon: inTelepon.value.trim() }), { message: "Menyimpan…" });
        MugenUI.toast("Contact disimpan.", "success");
      } catch (e) { errorContact.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

    // --- Book Appointment (satu-satunya tombol CTA di halaman, SELALU
    // mengarah ke form booking -- tidak ada pengaturan link, lihat
    // instruksi #7) ---
    const ctaCard = MugenUI.el("div", { class: "card" });
    body.appendChild(ctaCard);
    ctaCard.appendChild(MugenUI.el("h2", {}, "Book Appointment"));
    ctaCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Tombol ini selalu membuka form booking. Posisinya di bawah Opening Hours, di atas Connect With Us."));
    const inCtaJudul = MugenUI.el("input", { type: "text", value: content.booking_cta_judul || "", placeholder: "mis. Ready for your next cut?" });
    const inCtaSubjudul = MugenUI.el("input", { type: "text", value: content.booking_cta_subjudul || "" });
    const inCtaTombolTeks = MugenUI.el("input", { type: "text", value: content.booking_cta_tombol_teks || "", placeholder: "Book Appointment" });
    ctaCard.appendChild(MugenUI.el("label", {}, "Heading"));
    ctaCard.appendChild(inCtaJudul);
    ctaCard.appendChild(MugenUI.el("label", {}, "Subheading (opsional)"));
    ctaCard.appendChild(inCtaSubjudul);
    ctaCard.appendChild(MugenUI.el("label", {}, "Tulisan Tombol"));
    ctaCard.appendChild(inCtaTombolTeks);
    const errorCta = MugenUI.el("div", { class: "login-error" });
    const btnSimpanCta = MugenUI.el("button", { class: "btn-primary" }, "Simpan Book Appointment");
    ctaCard.appendChild(errorCta);
    ctaCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanCta));
    btnSimpanCta.addEventListener("click", async () => {
      errorCta.textContent = "";
      try {
        await MugenUI.withLoading(() => simpanContent({
          booking_cta_judul: inCtaJudul.value.trim(), booking_cta_subjudul: inCtaSubjudul.value.trim(),
          booking_cta_tombol_teks: inCtaTombolTeks.value.trim(),
        }), { message: "Menyimpan…" });
        MugenUI.toast("Book Appointment disimpan.", "success");
      } catch (e) { errorCta.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
  }

  return { render };
})();
