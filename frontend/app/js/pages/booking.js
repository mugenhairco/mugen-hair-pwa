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
  // METODE_LABEL: "cash" SENGAJA dipertahankan di sini walau metode ini
  // sudah dihapus total dari sistem (lihat METODE_AKTIF_OPTIONS di bawah) --
  // murni supaya booking LAMA yang metode_pembayaran-nya masih "cash"
  // (data historis, tidak pernah diubah retroaktif) tetap tampil dengan
  // label yang benar di kolom "Metode" Booking List (lihat pemakaian
  // METODE_LABEL[v] di bawah), bukan string mentah "cash".
  const METODE_LABEL = { cash: "Cash", transfer: "Transfer Bank", qris: "QRIS", gateway: "Payment Gateway" };
  // Metode yang BENAR-BENAR bisa dipilih Owner (Payment Settings) & customer
  // (halaman booking) sekarang -- Cash sudah dihapus total dari flow booking.
  const METODE_AKTIF_OPTIONS = ["transfer", "qris", "gateway"];

  // Vocabulary status Payment Gateway (7 state) -- HANYA dipakai untuk booking
  // dengan metode_pembayaran === "gateway". Status ini SELALU berasal dari
  // gateway_status yang diperkaya backend (booking_db.py::_perkaya_status_gateway
  // / get_booking_list()) dari booking_payment_transactions, TIDAK PERNAH dari
  // status_pembayaran 2-state lama -- konsisten dengan riwayat_transaksi.js.
  const STATUS_GATEWAY_LABEL = {
    menunggu_pembayaran: "Menunggu Pembayaran",
    diproses: "Sedang Diproses",
    berhasil: "Berhasil",
    gagal: "Gagal",
    kedaluwarsa: "Kedaluwarsa",
    dibatalkan: "Dibatalkan",
    refund: "Refund",
  };
  const STATUS_GATEWAY_BADGE = {
    menunggu_pembayaran: "badge-libur",
    diproses: "badge-libur",
    berhasil: "badge-success",
    gagal: "badge-danger",
    kedaluwarsa: "badge-danger",
    dibatalkan: "badge-danger",
    refund: "badge-warning",
  };

  function waktuLengkapGateway(iso) {
    if (!iso) return "-";
    const [tanggal, jam] = iso.split("T");
    return `${MugenUI.formatTanggal(tanggal)} ${(jam || "").slice(0, 8)}`.trim();
  }

  // AUDIT (Implementasi Payment Gateway & Riwayat Transaksi Multi-Tenant --
  // perbaikan pasca-audit kesiapan): sama seperti riwayat_transaksi.js --
  // status YANG BELUM FINAL saja boleh dicek ulang manual ke provider,
  // KHUSUS untuk transaksi yang macet karena webhook TIDAK PERNAH sampai
  // sama sekali (server yang memanggil ulang provider, staff TIDAK PERNAH
  // bisa mengklaim status sendiri -- lihat routers/booking.py::
  // cek_ulang_transaksi_gateway()).
  const STATUS_GATEWAY_BOLEH_CEK_ULANG = new Set(["menunggu_pembayaran", "diproses"]);

  function bukaDetailGateway(transaksi) {
    const body = [
      MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Status"),
          MugenUI.el("span", { class: "badge" + (STATUS_GATEWAY_BADGE[transaksi.status_pembayaran] ? " " + STATUS_GATEWAY_BADGE[transaksi.status_pembayaran] : "") },
            STATUS_GATEWAY_LABEL[transaksi.status_pembayaran] || transaksi.status_pembayaran)]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Nominal"), MugenUI.el("div", {}, MugenUI.formatRupiah(transaksi.nominal))]),
      ]),
      MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:16px;margin-bottom:10px;" }, [
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Metode"), MugenUI.el("div", {}, transaksi.metode_pembayaran || "-")]),
        MugenUI.el("div", {}, [MugenUI.el("div", { class: "subtitle" }, "Channel"), MugenUI.el("div", {}, transaksi.channel_pembayaran || "-")]),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Waktu Dibuat"), MugenUI.el("div", {}, waktuLengkapGateway(transaksi.created_at)),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Waktu Dibayar"), MugenUI.el("div", {}, waktuLengkapGateway(transaksi.paid_at)),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Transaction ID (Provider)"), MugenUI.el("div", {}, transaksi.transaction_id_provider || "-"),
      ]),
      MugenUI.el("div", { style: "margin-bottom:10px;" }, [
        MugenUI.el("div", { class: "subtitle" }, "Reference ID (Provider)"), MugenUI.el("div", {}, transaksi.reference_id_provider || "-"),
      ]),
      MugenUI.el("h3", { style: "margin-top:16px;" }, "Riwayat Perubahan Status"),
      MugenUI.buildTable(
        [
          { key: "waktu", label: "Waktu", format: waktuLengkapGateway },
          { key: "status_lama", label: "Dari", format: (v) => STATUS_GATEWAY_LABEL[v] || v || "-" },
          { key: "status_baru", label: "Ke", format: (v) => STATUS_GATEWAY_LABEL[v] || v },
        ],
        transaksi.status_log || [],
        { emptyText: "Belum ada perubahan status." },
      ),
    ];

    let modal;
    if (STATUS_GATEWAY_BOLEH_CEK_ULANG.has(transaksi.status_pembayaran)) {
      const btnCekUlang = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:16px;" },
        "Cek Ulang ke Provider");
      btnCekUlang.addEventListener("click", async () => {
        try {
          const updated = await MugenUI.withButtonLoading(btnCekUlang,
            () => MugenApi.post(`/api/booking/transactions/${transaksi.id}/cek-ulang`));
          modal.close();
          MugenUI.toast("Status berhasil diperbarui dari provider.", "success", { force: true });
          bukaDetailGateway(updated);
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
      body.push(btnCekUlang);
      body.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:6px;" },
        "Pakai ini HANYA kalau status di sini tidak kunjung berubah walau customer sudah membayar -- server akan menanyakan ulang status LANGSUNG ke provider."));
    }
    modal = MugenUI.infoModal({ title: `Detail Transaksi — ${transaksi.nomor_transaksi}`, body });
  }

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
    const tabItems = [
      { key: "Booking List", label: "Booking List" },
      { key: "Calendar", label: "Calendar" },
      { key: "Operating Hours", label: "Operating Hours" },
      { key: "Barber Holiday", label: "Barber Holiday" },
      { key: "Closed Slot", label: "Closed Slot" },
      { key: "Payment Settings", label: "Payment Settings" },
      { key: "Booking Settings", label: "Booking Settings" },
      ...(isOwner ? [{ key: "Website Content", label: "Website Content" }] : []),
    ];
    const body = MugenUI.el("div");

    let barbers = [];
    try { barbers = await MugenApi.get("/api/input-data/barbers", { useCache: true }); } catch (e) { /* opsional */ }

    async function renderBody(activeTab) {
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

    // REVISI UI/UX Premium: MugenUI.tabs() (indikator geser halus otomatis)
    // menggantikan tabBar/renderTabs manual.
    const tabsCtl = MugenUI.tabs(tabItems, { onChange: renderBody });
    root.appendChild(tabsCtl.bar);
    root.appendChild(body);
    requestAnimationFrame(tabsCtl.moveIndicator);

    renderBody(tabsCtl.active);
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

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...", filter
    // tanpa overlay layar penuh -- lihat catatan di ui.js.
    async function load() {
      card.innerHTML = "";
      card.appendChild(MugenUI.skeleton("table", { cols: 9, rows: 4 }));
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
        card.appendChild(MugenUI.errorState(e.message));
      }
    }
    selBulan.addEventListener("change", load);
    selTahun.addEventListener("change", load);
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
        // Booking metode "gateway": status pembayaran HANYA boleh berubah lewat
        // webhook resmi provider (lihat routers/booking.py::verifikasi_booking()),
        // jadi tampilkan vocabulary 7-state gateway_status (diperkaya backend)
        // -- bukan status_pembayaran 2-state lama yang berhenti di "menunggu_verifikasi"
        // sampai webhook benar-benar mengonfirmasi.
        key: "status_pembayaran", label: "Status Bayar",
        format: (v, r) => {
          if (r.metode_pembayaran === "gateway") {
            const gs = r.gateway_status || "menunggu_pembayaran";
            return MugenUI.el("span", { class: "badge" + (STATUS_GATEWAY_BADGE[gs] ? " " + STATUS_GATEWAY_BADGE[gs] : "") }, STATUS_GATEWAY_LABEL[gs] || gs);
          }
          return MugenUI.el("span", { class: "badge" + (v === "terverifikasi" ? " badge-success" : " badge-libur") }, STATUS_BAYAR_LABEL[v] || v);
        },
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
          // Booking gateway TIDAK PERNAH bisa diverifikasi manual (backend
          // menolak 422 -- lihat routers/booking.py::verifikasi_booking()),
          // jadi tombol "Verifikasi" disembunyikan untuk metode ini.
          if (onVerifikasi && r.metode_pembayaran !== "gateway" && r.status_pembayaran !== "terverifikasi" && r.status_booking === "aktif") {
            const btn = MugenUI.el("button", {}, "Verifikasi");
            btn.addEventListener("click", async () => {
              btn.disabled = true;
              try { await onVerifikasi(r); } finally { btn.disabled = false; }
            });
            wrap.appendChild(btn);
          }
          if (r.metode_pembayaran === "gateway" && r.gateway_transaksi_id) {
            const btn = MugenUI.el("button", {}, "Detail");
            btn.addEventListener("click", async () => {
              try {
                const detail = await MugenUI.withButtonLoading(btn, () => MugenApi.get(`/api/booking/transactions/${r.gateway_transaksi_id}`));
                bukaDetailGateway(detail);
              } catch (e) {
                MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
              }
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

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...", filter
    // tanpa overlay layar penuh, verifikasi/batalkan booking (bookingTable
    // sudah menonaktifkan tombolnya sendiri selama proses berjalan, lihat
    // bookingTable() di atas) TANPA overlay layar penuh -- lihat catatan
    // withLoading() di ui.js.
    async function load() {
      tableWrap.innerHTML = "";
      tableWrap.appendChild(MugenUI.skeleton("table", { cols: 10, rows: 4 }));
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
              await MugenApi.post(`/api/booking/${r.id}/verifikasi`);
              // REVISI UI/UX Premium: aksi besar/konfirmasi penting (verifikasi
              // pembayaran booking) SENGAJA memakai force:true -- satu dari
              // sedikit titik toast sukses yang tetap ditampilkan di seluruh
              // aplikasi (lihat daftar whitelist di ui.js::toast()).
              MugenUI.toast("Pembayaran diverifikasi.", "success", { force: true });
              load();
              MugenBookingNotif.refreshNow(); // REVISI: badge langsung update, tidak menunggu poll berikutnya
            } catch (e) { MugenUI.toast(e.message, "error"); }
          },
          onBatalkan: async (r) => {
            if (!confirm(`Batalkan booking ${r.customer_nama} (${r.tanggal} ${r.jam_mulai})?`)) return;
            try {
              await MugenApi.post(`/api/booking/${r.id}/batalkan`);
              MugenUI.toast("Booking dibatalkan.", "success");
              load();
              MugenBookingNotif.refreshNow(); // REVISI: badge langsung update, tidak menunggu poll berikutnya
            } catch (e) { MugenUI.toast(e.message, "error"); }
          },
        }));
      } catch (e) {
        tableWrap.innerHTML = "";
        tableWrap.appendChild(MugenUI.errorState(e.message));
      }
    }
    selBulan.addEventListener("change", load);
    selTahun.addEventListener("change", load);
    selBarber.addEventListener("change", load);
    selStatus.addEventListener("change", load);
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

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...".
    async function load() {
      calBox.innerHTML = "";
      calBox.appendChild(MugenUI.skeleton("card", { lines: 4 }));
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
        calBox.appendChild(MugenUI.errorState(e.message));
      }
    }

    function renderGrid() {
      calBox.innerHTML = "";
      const y = shown.getFullYear(), m = shown.getMonth();
      const nav = MugenUI.el("div", { class: "book-calendar-nav" });
      const btnPrev = MugenUI.el("button", { type: "button" }, "‹");
      const btnNext = MugenUI.el("button", { type: "button" }, "›");
      btnPrev.addEventListener("click", () => { shown = new Date(y, m - 1, 1); load(); });
      btnNext.addEventListener("click", () => { shown = new Date(y, m + 1, 1); load(); });
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

    selBarber.addEventListener("change", load);
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpan,
          () => MugenApi.put("/api/booking/pengaturan", { jam_buka: inBuka.value, jam_tutup: inTutup.value, hari_operasional }));
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

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...".
    async function loadLiburToko() {
      liburListBody.innerHTML = "";
      liburListBody.appendChild(MugenUI.skeleton("table", { cols: 3, rows: 3 }));
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
                    await MugenUI.withButtonLoading(btn, () => MugenApi.del(`/api/booking/toko-libur/${r.id}`));
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
        liburListBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    btnTambahLibur.addEventListener("click", async () => {
      liburError.textContent = "";
      if (!inLiburTanggal.value) { liburError.textContent = "Pilih tanggal dulu."; return; }
      try {
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnTambahLibur, () => MugenApi.post("/api/booking/toko-libur", {
          tanggal: inLiburTanggal.value, keterangan: inLiburKeterangan.value.trim() || null,
        }));
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

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...".
    async function loadList() {
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.skeleton("table", { cols: 2, rows: 3 }));
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
        listBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
    btnTandai.addEventListener("click", async () => {
      errorBox.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnTandai,
          () => MugenApi.post("/api/input-data/libur", { barber_id: Number(selBarber.value), tanggal: inputTanggal.value }));
        MugenUI.toast("Ditandai libur.", "success");
        loadList();
      } catch (e) { errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnBatalkan.addEventListener("click", async () => {
      errorBox.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnBatalkan,
          () => MugenApi.del("/api/input-data/libur", { barber_id: Number(selBarber.value), tanggal: inputTanggal.value }));
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

    // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...".
    async function loadList() {
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 3 }));
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
                    await MugenUI.withButtonLoading(btn, () => MugenApi.del(`/api/booking/closed-slot/${r.id}`));
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
        listBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
    btnSimpan.addEventListener("click", async () => {
      errorBox.textContent = "";
      if (!inputJamMulai.value || !inputJamSelesai.value) { errorBox.textContent = "Isi jam mulai dan jam selesai."; return; }
      try {
        await MugenUI.withButtonLoading(btnSimpan, () => MugenApi.post("/api/booking/closed-slot", {
          barber_id: Number(selBarber.value), tanggal: inputTanggal.value,
          jam_mulai: inputJamMulai.value, jam_selesai: inputJamSelesai.value,
          keterangan: inputKeterangan.value || null,
        }));
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
    for (const key of METODE_AKTIF_OPTIONS) {
      const label = METODE_LABEL[key];
      const cb = MugenUI.el("input", { type: "checkbox" });
      cb.checked = s.metode_aktif.includes(key);
      checkboxes[key] = cb;
      card.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:8px;" }, [cb, label]));
    }

    const errorBox1 = MugenUI.el("div", { class: "login-error" });
    const btnSimpanMetode = MugenUI.el("button", { class: "btn-primary" }, "Simpan Metode Aktif");
    card.appendChild(errorBox1);
    card.appendChild(MugenUI.el("div", { style: "margin:12px 0;" }, btnSimpanMetode));
    btnSimpanMetode.addEventListener("click", async () => {
      errorBox1.textContent = "";
      const metode_aktif = Object.entries(checkboxes).filter(([, cb]) => cb.checked).map(([k]) => k);
      try {
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanMetode, () => MugenApi.put("/api/booking/payment-settings", { metode_aktif }));
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
    for (const key of METODE_AKTIF_OPTIONS) {
      const label = METODE_LABEL[key];
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
      for (const key of METODE_AKTIF_OPTIONS) {
        if (inNama[key].value.trim()) metode_nama[key] = inNama[key].value.trim();
        if (inInstruksi[key].value.trim()) metode_instruksi[key] = inInstruksi[key].value.trim();
      }
      try {
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanLabel,
          () => MugenApi.put("/api/booking/payment-settings", { metode_nama, metode_instruksi }));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanBank, () => MugenApi.put("/api/booking/payment-settings", {
          bank_nama: inBankNama.value, bank_nomor_rekening: inBankRek.value, bank_nama_pemilik: inBankAtasNama.value,
        }));
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

    // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading()
    // untuk kedua tombol QRIS (upload/ganti butuh progress upload file yang
    // bisa memakan waktu, hapus adalah aksi tunggal cepat -- keduanya cukup
    // spinner inline, tanpa overlay layar penuh).
    btnUploadQris.addEventListener("click", async () => {
      errorBox3.textContent = "";
      try {
        await MugenUI.withButtonLoading(btnUploadQris, async () => {
          if (inMerchant.value !== (s.qris_merchant_nama || "")) {
            await MugenApi.put("/api/booking/payment-settings", { qris_merchant_nama: inMerchant.value });
          }
          if (inQrisFile.files && inQrisFile.files[0]) {
            const hasil = await MugenApi.uploadFile("/api/booking/qris", inQrisFile.files[0]);
            qrisPreview.src = MUGEN_API_BASE + hasil.qris_url + "&t=" + Date.now();
            qrisPreview.style.display = "";
          }
        });
        MugenUI.toast("QRIS disimpan.", "success");
      } catch (e) { errorBox3.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnHapusQris.addEventListener("click", async () => {
      if (!confirm("Hapus QRIS yang sedang aktif?")) return;
      try {
        await MugenUI.withButtonLoading(btnHapusQris, () => MugenApi.del("/api/booking/qris"));
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
    linkCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Setiap toko punya alamat booking publik sendiri (subdomain) -- bagikan ke customer, atau ubah bagian depannya di bawah."));

    // FITUR URL Booking Publik per Tenant: Link Booking SEKARANG dibentuk
    // backend dari booking_slug tenant (subdomain <booking_slug>.<domain>/
    // app/#/book, lihat routers/booking.py::ambil_booking_slug()/
    // tenant_db.py::get_booking_url()) -- BUKAN lagi window.location.origin
    // polos (link lama itu TETAP berfungsi apa adanya sebagai jalur akses
    // internal, tidak dihapus/diubah -- ini murni link yang DITAMPILKAN &
    // disalin di sini, supaya benar dari device MANA PUN, bukan cuma dari
    // domain yang kebetulan sedang dibuka Owner saat itu). Selalu ikut
    // booking_slug TERKINI (dibaca ulang dari server, tidak ada state lokal
    // yang bisa basi) -- begitu diubah lewat form di bawah, link ini ikut
    // berubah otomatis tanpa reload halaman.
    const inLink = MugenUI.el("input", { type: "text", value: "", readOnly: true });
    const btnSalinLink = MugenUI.el("button", {}, "Salin Link");
    const btnBukaLink = MugenUI.el(
      "a", { href: "#", target: "_blank", rel: "noopener noreferrer", class: "btn-primary" }, "Buka",
    );
    linkCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;" }, [inLink, btnSalinLink, btnBukaLink]));
    btnSalinLink.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(inLink.value);
        MugenUI.toast("Link booking disalin.", "success");
      } catch (e) {
        inLink.select();
        MugenUI.toast("Gagal menyalin otomatis -- link sudah disorot, salin manual (Ctrl+C).", "error");
      }
    });

    const inSlug = MugenUI.el("input", { type: "text", placeholder: "mis. mugenhairco" });
    const errorBoxSlug = MugenUI.el("div", { class: "login-error" });
    const btnSimpanSlug = MugenUI.el("button", { class: "btn-primary" }, "Simpan Alamat Booking");
    linkCard.appendChild(MugenUI.el("label", { style: "margin-top:12px;" },
      "Ubah Alamat Booking (huruf kecil & angka saja, tanpa spasi/karakter khusus)"));
    linkCard.appendChild(inSlug);
    linkCard.appendChild(errorBoxSlug);
    linkCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanSlug));

    function terapkanBookingSlug(hasil) {
      inLink.value = hasil.booking_url || "";
      btnBukaLink.href = hasil.booking_url || "#";
      inSlug.value = hasil.booking_slug || "";
    }

    try {
      terapkanBookingSlug(await MugenApi.get("/api/booking/booking-slug"));
    } catch (e) {
      errorBoxSlug.textContent = e.message;
    }

    btnSimpanSlug.addEventListener("click", async () => {
      errorBoxSlug.textContent = "";
      try {
        const hasil = await MugenUI.withButtonLoading(btnSimpanSlug, () => MugenApi.put(
          "/api/booking/booking-slug", { booking_slug: inSlug.value.trim().toLowerCase() },
        ));
        terapkanBookingSlug(hasil);
        MugenUI.toast("Alamat booking disimpan.", "success");
      } catch (e) { errorBoxSlug.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });

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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpan, () => MugenApi.put("/api/booking/pengaturan", {
          interval_menit: Number(inInterval.value), maksimal_hari_kedepan: Number(inMaksHari.value),
        }));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanPesan, () => MugenApi.put("/api/booking/pengaturan", {
          pesan_penutup: inPenutup.value.trim(),
          pesan_nama_kosong: inNamaKosong.value.trim(),
          pesan_whatsapp_invalid: inWaInvalid.value.trim(),
        }));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        const hasil = await MugenUI.withButtonLoading(btnUploadHeroImage,
          () => MugenApi.uploadFile("/api/website/hero-image", inHeroImageFile.files[0]));
        content.hero_image_url = hasil.hero_image_url;
        heroImagePreview.src = MUGEN_API_BASE + hasil.hero_image_url + "&t=" + Date.now();
        heroImagePreview.style.display = "";
        MugenUI.toast("Hero Image disimpan.", "success");
      } catch (e) { errorHeroImage.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnHapusHeroImage.addEventListener("click", async () => {
      if (!confirm("Hapus Hero Image yang sedang aktif?")) return;
      try {
        await MugenUI.withButtonLoading(btnHapusHeroImage, () => MugenApi.del("/api/website/hero-image"));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        const hasil = await MugenUI.withButtonLoading(btnUploadHeroVideo,
          () => MugenApi.uploadFile("/api/website/hero-video", inHeroVideoFile.files[0]));
        content.hero_video_url = hasil.hero_video_url;
        heroVideoPreview.src = MUGEN_API_BASE + hasil.hero_video_url + "&t=" + Date.now();
        heroVideoPreview.style.display = "block";
        MugenUI.toast("Hero Video disimpan.", "success");
      } catch (e) { errorHeroVideo.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnHapusHeroVideo.addEventListener("click", async () => {
      if (!confirm("Hapus Hero Video yang sedang aktif?")) return;
      try {
        await MugenUI.withButtonLoading(btnHapusHeroVideo, () => MugenApi.del("/api/website/hero-video"));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanHero, () => simpanContent({
          hero_tipe: selHeroTipe.value, tagline: inTagline.value.trim(),
        }));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        const hasil = await MugenUI.withButtonLoading(btnUploadAboutFoto,
          () => MugenApi.uploadFile("/api/website/about-foto", inAboutFotoFile.files[0]));
        aboutFotoPreview.src = MUGEN_API_BASE + hasil.about_foto_url + "&t=" + Date.now();
        aboutFotoPreview.style.display = "";
        MugenUI.toast("Foto About disimpan.", "success");
      } catch (e) { errorAboutFoto.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
    btnHapusAboutFoto.addEventListener("click", async () => {
      if (!confirm("Hapus Foto About yang sedang aktif?")) return;
      try {
        await MugenUI.withButtonLoading(btnHapusAboutFoto, () => MugenApi.del("/api/website/about-foto"));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanAbout,
          () => simpanContent({ about_judul: inAboutJudul.value.trim(), about_deskripsi: inAboutDeskripsi.value.trim() }));
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

    // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
    // -- dipicu drag-drop ATAU tombol ↑/↓ per item (tidak ada satu tombol
    // tunggal untuk withButtonLoading), grid yang re-render ulang begitu
    // selesai sudah jadi feedback yang cukup untuk aksi reorder ini.
    async function simpanUrutanGallery(disusun) {
      try {
        gallery = await MugenApi.put("/api/website/gallery/reorder", { ordered_ids: disusun.map((f) => f.id) });
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
            // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
            gallery = await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/website/gallery/${foto.id}`));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnUploadGallery, async () => {
          for (const file of inGalleryFiles.files) {
            gallery = await MugenApi.uploadFile("/api/website/gallery", file);
          }
        });
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanVisit, () => simpanContent({
          alamat: inAlamat.value.trim(), visit_maps_embed_url: inMapsEmbed.value.trim(), visit_maps_link: inMapsLink.value.trim(),
        }));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanSocial, () => simpanContent({
          instagram: inInstagram.value.trim(), tiktok: inTiktok.value.trim(), whatsapp: inWhatsapp.value.trim(),
        }));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanContact, () => simpanContent({ telepon: inTelepon.value.trim() }));
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
        // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
        await MugenUI.withButtonLoading(btnSimpanCta, () => simpanContent({
          booking_cta_judul: inCtaJudul.value.trim(), booking_cta_subjudul: inCtaSubjudul.value.trim(),
          booking_cta_tombol_teks: inCtaTombolTeks.value.trim(),
        }));
        MugenUI.toast("Book Appointment disimpan.", "success");
      } catch (e) { errorCta.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message; }
    });
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageBooking begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageBooking = PageBooking;
