// pages/pos.js — Menu BARU "Point of Sale" (Kasir walk-in).
// Dua tab: "Kasir" (alur Barber/Produk -> Service -> Payment -> Pembayaran
// Berhasil, pilihan Barber/Service/Produk INSTAN tanpa loading -- seluruh
// data pengaturan di-fetch SEKALI di awal, pola SAMA PERSIS wizard booking
// publik di book_public.js) dan "Transaksi Hari Ini" (gabungan booking
// online yang sudah lunas + transaksi Kasir hari itu, lihat routers/pos.py::
// transaksi_hari_ini()). Metode pembayaran (QRIS manual/Payment Gateway)
// reuse TOTAL konfigurasi yang sama dipakai booking publik (lihat
// booking_db.get_payment_settings()) -- "Cash" TIDAK ditawarkan di sini
// (bukan skenario walk-in, lihat routers/pos.py::METODE_POS_VALID).

const PagePos = (() => {
  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Point of Sale"));

    const levelPos = await MugenMenuAccess.get("pos");
    if (levelPos === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const user = MugenState.getUser();
    const isOwner = user.role === "admin";
    const TAB_IZIN = { "Kasir": "izin_pos_kelola", "Transaksi Hari Ini": "izin_pos_lihat" };
    const ALL_TABS = Object.keys(TAB_IZIN);
    let tabsLolos = ALL_TABS;
    if (!isOwner) {
      const hasilIzin = await Promise.all(ALL_TABS.map((t) => MugenMenuAccess.has(TAB_IZIN[t])));
      tabsLolos = ALL_TABS.filter((_, i) => hasilIzin[i]);
    }
    if (!tabsLolos.length) {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const tabItems = tabsLolos.map((t) => ({ key: t, label: t }));
    const body = MugenUI.el("div");

    async function renderBody(activeTab) {
      body.innerHTML = "";
      if (activeTab === "Kasir") await renderKasirTab(body);
      else await renderTransaksiHariIniTab(body);
    }

    const tabsCtl = MugenUI.tabs(tabItems, { onChange: renderBody });
    root.appendChild(tabsCtl.bar);
    root.appendChild(body);
    requestAnimationFrame(tabsCtl.moveIndicator);
    await renderBody(tabsCtl.active);
  }

  // ================= TAB: KASIR =================
  async function renderKasirTab(body) {
    body.appendChild(MugenUI.skeleton("card", { lines: 4 }));
    let pengaturan;
    try {
      pengaturan = await MugenApi.get("/api/pos/pengaturan");
    } catch (e) {
      body.innerHTML = "";
      body.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
      return;
    }
    body.innerHTML = "";
    jalankanWizardKasir(body, pengaturan);
  }

  // Wizard Kasir -- SELURUH data (barber/service/produk/payment settings)
  // SUDAH ada di `pengaturan` sejak awal (satu fetch di renderKasirTab() di
  // atas) -- pindah antar fase di bawah ini TIDAK PERNAH menunggu network
  // lagi KECUALI saat benar-benar submit pembayaran (tombol "Buat
  // Transaksi"/"Payment Diterima"), pola SAMA PERSIS wizard booking publik.
  function jalankanWizardKasir(body, pengaturan) {
    const metodeAktif = pengaturan.metode_aktif || [];
    const metodeNama = pengaturan.metode_nama || {};
    const metodeInstruksi = pengaturan.metode_instruksi || {};
    const state = {
      barberId: null, serviceIds: new Set(), produk: {},
      metode: null, channel: null, bankCode: null, transaksi: null,
    };
    let fase = "pilih";

    function totalHarga() {
      let total = 0;
      for (const s of pengaturan.services) if (state.serviceIds.has(s.id)) total += s.harga;
      for (const pid of Object.keys(state.produk)) {
        const qty = state.produk[pid];
        if (qty > 0) {
          const p = pengaturan.produk.find((x) => x.id === Number(pid));
          if (p) total += p.harga_jual * qty;
        }
      }
      return total;
    }

    function barisTotal() {
      return MugenUI.el("div", { style: "display:flex;justify-content:space-between;font-weight:700;" }, [
        MugenUI.el("span", {}, "Total Payment"), MugenUI.el("span", {}, MugenUI.formatRupiah(totalHarga())),
      ]);
    }

    function resetState() {
      state.barberId = null; state.serviceIds = new Set(); state.produk = {};
      state.metode = null; state.channel = null; state.bankCode = null; state.transaksi = null;
      fase = "pilih";
    }

    function gantiFase() {
      body.innerHTML = "";
      if (fase === "pilih") renderPilih();
      else if (fase === "payment") renderPayment();
      else if (fase === "menunggu_manual") renderMenungguManual();
      else if (fase === "waiting") renderWaitingGateway();
      else renderSelesai();
    }

    // ---- fase "pilih": Barber + Service + Produk (satu checkout bisa
    // mencampur keduanya -- PERMINTAAN Owner "satu kali scan untuk Service
    // + Produk") ----
    function renderPilih() {
      body.appendChild(MugenUI.el("h2", {}, "Pilih Barber, Service & Produk"));
      const errorBox = MugenUI.el("div", { class: "login-error" });

      body.appendChild(MugenUI.el("label", {}, "Barber (wajib kalau memilih Service)"));
      const selBarber = MugenUI.el("select");
      selBarber.appendChild(MugenUI.el("option", { value: "" }, "-- Pilih Barber --"));
      for (const b of pengaturan.barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
      if (state.barberId) selBarber.value = String(state.barberId);
      selBarber.addEventListener("change", () => {
        state.barberId = selBarber.value ? Number(selBarber.value) : null;
      });
      body.appendChild(selBarber);

      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Service"));
      const serviceBox = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:12px;" });
      for (const s of pengaturan.services) {
        const cb = MugenUI.el("input", { type: "checkbox" });
        cb.checked = state.serviceIds.has(s.id);
        cb.addEventListener("change", () => {
          if (cb.checked) state.serviceIds.add(s.id); else state.serviceIds.delete(s.id);
          renderTotal();
        });
        serviceBox.appendChild(MugenUI.el("label", { style: "display:flex;align-items:center;gap:6px;" },
          [cb, `${s.nama} (${MugenUI.formatRupiah(s.harga)})`]));
      }
      body.appendChild(serviceBox);
      if (!pengaturan.services.length) body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada service aktif."));

      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Produk"));
      const produkBox = MugenUI.el("div", { style: "display:flex;flex-direction:column;gap:8px;" });
      for (const p of pengaturan.produk) {
        const inputQty = MugenUI.el("input", {
          type: "number", min: "0", max: String(p.stok),
          value: String(state.produk[p.id] || 0), style: "width:70px;",
        });
        inputQty.addEventListener("input", () => {
          const qty = Math.max(0, Math.min(p.stok, parseInt(inputQty.value, 10) || 0));
          if (qty > 0) state.produk[p.id] = qty; else delete state.produk[p.id];
          renderTotal();
        });
        produkBox.appendChild(MugenUI.el("div", { class: "row", style: "align-items:center;gap:10px;" }, [
          MugenUI.el("div", { style: "flex:1;" }, `${p.nama} (${MugenUI.formatRupiah(p.harga_jual)}/pcs, stok ${p.stok})`),
          inputQty,
        ]));
      }
      body.appendChild(produkBox);
      if (!pengaturan.produk.length) body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada produk aktif."));

      const totalBox = MugenUI.el("div", { class: "card", style: "margin-top:12px;" });
      body.appendChild(totalBox);
      function renderTotal() {
        totalBox.innerHTML = "";
        totalBox.appendChild(barisTotal());
      }
      renderTotal();

      body.appendChild(errorBox);
      const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Lanjut ke Payment");
      btnLanjut.addEventListener("click", () => {
        errorBox.textContent = "";
        if (!state.serviceIds.size && !Object.keys(state.produk).length) {
          errorBox.textContent = "Pilih minimal satu Service atau Produk."; return;
        }
        if (state.serviceIds.size && !state.barberId) {
          errorBox.textContent = "Barber wajib dipilih kalau ada Service yang dipilih."; return;
        }
        fase = "payment"; gantiFase();
      });
      body.appendChild(btnLanjut);
    }

    // ---- fase "payment": pilih metode (QRIS manual/Payment Gateway) ----
    function renderPayment() {
      body.appendChild(MugenUI.el("h2", {}, "Payment"));
      body.appendChild(MugenUI.el("div", { class: "card" }, [barisTotal()]));

      const errorBox = MugenUI.el("div", { class: "login-error" });
      const metodeBox = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;margin-top:12px;" });
      const bankBox = MugenUI.el("div", { class: "bank-grid" });

      function renderBankBox() {
        bankBox.innerHTML = "";
        if (state.metode !== "gateway" || state.channel !== "va") return;
        const bankAktif = pengaturan.snap_va_bank_aktif || {};
        const kodeList = Object.keys(bankAktif);
        for (const kode of kodeList) {
          const card = MugenUI.el("button", {
            type: "button", class: "bank-card" + (state.bankCode === kode ? " selected" : ""),
          }, [MugenUI.bankLogoBadge(kode), MugenUI.el("span", {}, MugenUI.bankNamaLengkap(kode, bankAktif[kode]))]);
          card.addEventListener("click", () => {
            state.bankCode = kode;
            for (const el of bankBox.children) el.classList.remove("selected");
            card.classList.add("selected");
          });
          bankBox.appendChild(card);
        }
        if (kodeList.length === 1) state.bankCode = kodeList[0];
      }

      const opsi = [];
      for (const m of metodeAktif) {
        if (m === "gateway") {
          for (const c of (pengaturan.snap_channel_aktif || [])) {
            opsi.push({ metode: "gateway", channel: c, label: c === "va" ? "Virtual Account" : "QRIS" });
          }
        } else {
          opsi.push({ metode: m, channel: null, label: metodeNama[m] || m });
        }
      }
      if (!opsi.length) {
        body.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:12px;" },
          "Belum ada metode pembayaran aktif untuk Point of Sale. Hubungi Superadmin."));
      } else {
        for (const o of opsi) {
          const dipilih = state.metode === o.metode && state.channel === o.channel;
          const btn = MugenUI.el("button", {
            type: "button", class: "book-metode-btn" + (dipilih ? " selected" : ""),
          }, o.label);
          btn.addEventListener("click", () => {
            state.metode = o.metode; state.channel = o.channel; state.bankCode = null;
            for (const el of metodeBox.children) el.classList.remove("selected");
            btn.classList.add("selected");
            renderBankBox();
          });
          metodeBox.appendChild(btn);
        }
      }
      body.appendChild(metodeBox);
      body.appendChild(bankBox);
      body.appendChild(errorBox);

      body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => { fase = "pilih"; gantiFase(); } }, "< Back"),
      ]));

      const btnBuat = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Buat Transaksi");
      btnBuat.addEventListener("click", async () => {
        errorBox.textContent = "";
        if (!state.metode) { errorBox.textContent = "Pilih metode pembayaran terlebih dahulu."; return; }
        if (state.metode === "gateway" && !state.channel) { errorBox.textContent = "Pilih VA/QRIS terlebih dahulu."; return; }
        if (state.metode === "gateway" && state.channel === "va" && !state.bankCode) {
          errorBox.textContent = "Pilih bank terlebih dahulu."; return;
        }
        try {
          const payload = {
            barber_id: state.barberId, service_ids: Array.from(state.serviceIds),
            produk_items: Object.keys(state.produk).map((pid) => ({ produk_id: Number(pid), jumlah: state.produk[pid] })),
            metode_pembayaran: state.metode,
            channel: state.metode === "gateway" ? state.channel : undefined,
            bank_code: state.metode === "gateway" && state.channel === "va" ? state.bankCode : undefined,
          };
          const hasil = await MugenUI.withButtonLoading(btnBuat, () => MugenApi.post("/api/pos/transaksi", payload));
          state.transaksi = hasil;
          fase = state.metode === "gateway" ? "waiting" : "menunggu_manual";
          gantiFase();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      body.appendChild(btnBuat);
    }

    // ---- fase "menunggu_manual": QRIS foto (yang di-upload Superadmin) +
    // tombol "Payment Diterima" -- Kasir sendiri yang melihat notifikasi
    // pembayaran masuk ke rekening/HP toko, TIDAK ada verifikasi otomatis
    // untuk metode ini. ----
    function renderMenungguManual() {
      body.appendChild(MugenUI.el("h2", {}, "Menunggu Pembayaran (QRIS)"));
      const items = [];
      if (pengaturan.qris_url) {
        items.push(MugenUI.el("img", { src: MUGEN_API_BASE + pengaturan.qris_url, class: "book-qris-img", alt: "QRIS" }));
      } else {
        items.push(MugenUI.el("div", { class: "subtitle" }, "Foto QRIS belum diunggah Superadmin."));
      }
      items.push(MugenUI.el("div", { style: "margin-top:8px;" }, pengaturan.qris_merchant_nama || ""));
      items.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" }, metodeInstruksi.qris || ""));

      body.appendChild(MugenUI.el("div", { class: "card" }, [
        barisTotal(),
        MugenUI.el("hr"),
        MugenUI.el("div", { style: "text-align:center;" }, items),
      ]));

      const errorBox = MugenUI.el("div", { class: "login-error" });
      body.appendChild(errorBox);
      const btnTerima = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Payment Diterima");
      btnTerima.addEventListener("click", async () => {
        errorBox.textContent = "";
        try {
          await MugenUI.withButtonLoading(btnTerima, () => MugenApi.post(`/api/pos/transaksi/${state.transaksi.id}/verifikasi`));
          MugenUI.toast("Pembayaran dikonfirmasi.", "success", { force: true });
          fase = "selesai"; gantiFase();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      body.appendChild(btnTerima);
    }

    // ---- fase "waiting": Payment Gateway (QR/VA ditampilkan di layar
    // Kasir, customer scan di tempat) -- poll status + tombol "Saya Sudah
    // Bayar", TANPA countdown 15 menit (konsep itu khusus booking publik
    // yang bisa ditinggal customer; di Kasir, Kasir berdiri menyelesaikan
    // transaksi SAAT ITU JUGA). ----
    function renderWaitingGateway() {
      const r = state.transaksi;
      body.appendChild(MugenUI.el("h2", {}, "Menunggu Konfirmasi Pembayaran"));
      const statusLabelEl = MugenUI.el("div", { class: "subtitle" }, "Selesaikan pembayaran memakai info di bawah.");

      const items = [];
      if (r.channel === "va" || state.channel === "va") {
        items.push(MugenUI.el("div", { class: "subtitle" },
          r.channel_code ? `Virtual Account ${MugenUI.bankNamaLengkap(r.channel_code, null)}` : "Virtual Account"));
        items.push(MugenUI.el("div", { style: "font-size:22px;font-weight:700;letter-spacing:1px;text-align:center;margin-top:4px;" },
          r.va_number || "-"));
      } else if (r.qr_url) {
        items.push(MugenUI.el("img", { src: r.qr_url, class: "book-qris-img", alt: "QRIS" }));
      } else if (r.qr_content) {
        const btnBuka = MugenUI.el("button", { type: "button", class: "book-download-qris-btn" }, "Buka Halaman QRIS");
        btnBuka.addEventListener("click", () => window.open(r.qr_content, "_blank"));
        items.push(btnBuka);
      }

      const btnSudahBayar = MugenUI.el("button", { type: "button", style: "margin-top:12px;" }, "Saya Sudah Bayar");
      body.appendChild(MugenUI.el("div", { class: "card" }, [
        MugenUI.el("div", { style: "text-align:center;" }, [statusLabelEl, MugenUI.el("div", {}, [btnSudahBayar])]),
        MugenUI.el("hr"),
        MugenUI.el("div", { style: "text-align:center;" }, items),
        MugenUI.el("hr"),
        barisTotal(),
      ]));

      function terapkanStatus(status) {
        if (status.status === "PAID") {
          clearInterval(pollTimer);
          MugenUI.toast("Pembayaran berhasil.", "success", { force: true });
          fase = "selesai"; gantiFase();
          return true;
        }
        if (["FAILED", "CANCELLED", "EXPIRED"].includes(status.status)) {
          clearInterval(pollTimer);
          MugenUI.toast("Pembayaran gagal/dibatalkan.", "error", { force: true });
          fase = "pilih"; gantiFase();
          return true;
        }
        return false;
      }

      const pollTimer = setInterval(async () => {
        if (!document.body.contains(statusLabelEl)) { clearInterval(pollTimer); return; }
        let status;
        try {
          status = await MugenApi.get(`/api/pos/transaksi/${r.id}/status`);
        } catch (e) {
          return; // hiccup jaringan sesaat -- coba lagi di tick berikutnya
        }
        if (!terapkanStatus(status) && status.status === "PENDING") {
          statusLabelEl.textContent = "Pembayaran sedang diproses provider…";
        }
      }, 3000);

      btnSudahBayar.addEventListener("click", async () => {
        if (!document.body.contains(statusLabelEl)) return;
        try {
          const status = await MugenUI.withButtonLoading(btnSudahBayar,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/cek-ulang`));
          if (!terapkanStatus(status)) {
            statusLabelEl.textContent = "Pembayaran belum terdeteksi -- coba lagi setelah selesai bayar.";
          }
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
    }

    // ---- fase "selesai" ----
    function renderSelesai() {
      body.appendChild(MugenUI.el("div", { class: "card book-selesai" }, [
        MugenUI.el("div", { class: "book-selesai-icon" }, "✓"),
        MugenUI.el("h2", {}, "Pembayaran Berhasil"),
        MugenUI.el("div", { class: "subtitle" }, `Total: ${MugenUI.formatRupiah(totalHarga())}`),
      ]));
      const btnBaru = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Transaksi Baru");
      btnBaru.addEventListener("click", () => { resetState(); gantiFase(); });
      body.appendChild(btnBaru);
    }

    gantiFase();
  }

  // ================= TAB: TRANSAKSI HARI INI =================
  // Gabungan booking online (sudah terverifikasi/lunas) + transaksi Kasir
  // (lunas) hari ini -- field ringkas saja (nama barber/service/produk,
  // nominal, jam), TANPA komisi/tips (PERMINTAAN Owner).
  async function renderTransaksiHariIniTab(body) {
    body.appendChild(MugenUI.skeleton("table", { cols: 4, rows: 3 }));
    let hasil;
    try {
      hasil = await MugenApi.get("/api/pos/transaksi-hari-ini");
    } catch (e) {
      body.innerHTML = "";
      body.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
      return;
    }
    body.innerHTML = "";

    body.appendChild(MugenUI.el("h2", {}, "Service"));
    body.appendChild(MugenUI.buildTable(
      [
        { key: "jam", label: "Jam" },
        { key: "nama_barber", label: "Barber" },
        { key: "daftar_service", label: "Service" },
        { key: "nominal", label: "Nominal", format: (v) => MugenUI.formatRupiah(v) },
        { key: "sumber", label: "Sumber", format: (v) => (v === "pos" ? "Kasir" : "Booking Online") },
      ],
      hasil.service,
      { emptyText: "Belum ada transaksi service hari ini." },
    ));

    body.appendChild(MugenUI.el("h2", { style: "margin-top:20px;" }, "Produk"));
    body.appendChild(MugenUI.buildTable(
      [
        { key: "jam", label: "Jam" },
        { key: "nama_produk", label: "Produk" },
        { key: "jumlah", label: "Jumlah" },
        { key: "nominal", label: "Nominal", format: (v) => MugenUI.formatRupiah(v) },
      ],
      hasil.produk,
      { emptyText: "Belum ada transaksi produk hari ini." },
    ));
  }

  return { render };
})();

window.PagePos = PagePos;
