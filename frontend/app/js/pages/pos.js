// pages/pos.js — Menu BARU "Point of Sale" (Kasir walk-in).
// Dua tab: "Kasir" (alur Barber/Produk -> Service -> Payment -> Pembayaran
// Berhasil, pilihan Barber/Service/Produk INSTAN tanpa loading -- seluruh
// data pengaturan di-fetch SEKALI di awal, pola SAMA PERSIS wizard booking
// publik di book_public.js) dan "Transaksi Hari Ini" (gabungan booking
// online yang sudah lunas + transaksi Kasir hari itu, lihat routers/pos.py::
// transaksi_hari_ini()). Metode pembayaran (QRIS manual/Payment Gateway/
// Cash) reuse TOTAL konfigurasi yang sama dipakai booking publik (lihat
// booking_db.get_payment_settings()) -- SATU toggle metode_aktif dibagi
// bersama Booking & POS, lihat routers/pos.py::METODE_POS_VALID. Kalau
// cuma SATU metode yang aktif, Kasir TIDAK dipaksa memilih (langsung
// dipakai, lihat renderPayment()).
//
// PERMINTAAN Owner: KEDUA tab TIDAK PERNAH loading lagi setelah pemuatan
// PERTAMA di satu sesi -- lihat cache module-level (_cachePengaturan/
// _cacheTransaksiHariIni) & _suntikTransaksiBaru() di bawah ini untuk
// arsitektur lengkapnya (Transaksi Hari Ini diupdate LANGSUNG begitu satu
// transaksi POS lunas, TANPA fetch ulang ke server sama sekali).

const PagePos = (() => {
  // PERMINTAAN Owner: tab "Kasir" & "Transaksi Hari Ini" TIDAK boleh
  // menunggu loading tiap dibuka/pindah tab -- cache di LUAR render()
  // (module-level, bertahan lintas pindah tab/menu SELAMA SPA tidak
  // reload, pola SAMA seperti produk.js/rekap.js::_cacheTerakhir).
  //
  // "pos_kasir" (pengaturan: barber/service/produk/payment settings) pakai
  // flag "halamanKotor" (lihat state.js) HANYA secara LOKAL di sini --
  // SENGAJA TIDAK didaftarkan di hook mutasi generik api.js (endpoint POS
  // sendiri -- buat transaksi/bayar/batalkan -- JUGA mutasi; kalau ikut
  // terdaftar di sana, SATU checkout akan langsung menandai cache ini
  // kotor lagi & memaksa loading di checkout berikutnya, menggagalkan
  // tujuan "tidak ada loading" untuk pemakaian paling umum). Praktisnya:
  // dimuat SEKALI per sesi (default "kotor" sebelum pernah dimuat, lalu
  // ditandai "bersih" & TIDAK PERNAH kotor lagi sampai SPA reload total).
  //
  // "pos_transaksi" (Transaksi Hari Ini) TIDAK pakai flag "kotor" sama
  // sekali -- daftar ini berubah TIAP SATU transaksi POS lunas (jalur
  // paling sering dipakai di menu ini), begitu lunas barisnya langsung
  // DISUNTIKKAN ke cache ini (_suntikTransaksiBaru(), optimistic update,
  // TANPA fetch ulang apa pun) -- kalau tab ini belum pernah dibuka sesi
  // ini (cache masih null), tidak ada yang perlu disuntik (nanti fetch
  // fresh begitu pertama kali dibuka, otomatis sudah termasuk transaksi
  // barunya). Hapus baris (kolomAksi()) TETAP fetch ulang penuh (butuh
  // angka stok/Rekap yang benar-benar baru dari server, tidak bisa
  // dihitung sendiri di frontend).
  let _cachePengaturan = null; // { userId, data }
  let _cacheTransaksiHariIni = null; // { userId, tanggal, data }

  function _suntikTransaksiBaru(pos) {
    if (!_cacheTransaksiHariIni || !pos) return;
    if (pos.tanggal !== _cacheTransaksiHariIni.tanggal) return; // beda tanggal (jaga2 lewat tengah malam) -- biarkan, nanti fetch fresh saat tab dibuka utk tanggal itu
    const data = _cacheTransaksiHariIni.data;
    for (const b of pos.daftar_barber || []) {
      if (!b.daftar_service || !b.daftar_service.length) continue;
      data.service.push({
        sumber: "pos", pos_id: pos.id, jam: pos.jam, nama_barber: b.nama,
        daftar_service: b.daftar_service.map((s) => s.nama).join(", "),
        nominal: b.daftar_service.reduce((sum, s) => sum + s.harga, 0),
      });
    }
    for (const p of pos.daftar_produk || []) {
      data.produk.push({
        sumber: "pos", pos_id: pos.id, jam: pos.jam, nama_produk: p.nama,
        jumlah: p.jumlah, nominal: p.harga_satuan * p.jumlah,
      });
    }
    data.service.sort((a, c) => (a.jam < c.jam ? -1 : a.jam > c.jam ? 1 : 0));
    data.produk.sort((a, c) => (a.jam < c.jam ? -1 : a.jam > c.jam ? 1 : 0));
    data.rincian_metode = data.rincian_metode || {};
    data.rincian_metode[pos.metode_pembayaran] = (data.rincian_metode[pos.metode_pembayaran] || 0) + pos.total_harga;
    data.total_keseluruhan = (data.total_keseluruhan || 0) + pos.total_harga;
  }

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
    const userId = MugenState.getUser().id;
    if (_cachePengaturan && _cachePengaturan.userId === userId && !MugenState.halamanPerluRefresh("pos_kasir")) {
      jalankanWizardKasir(body, _cachePengaturan.data);
      return;
    }
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
    _cachePengaturan = { userId, data: pengaturan };
    MugenState.tandaiHalamanBersih("pos_kasir");
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
    // FITUR Keranjang Multi-Barber (PERMINTAAN Owner -- "anak cukur Barber
    // A, bapak cukur Barber B, mau 1 kali scan" & "tips manual per
    // barber"): `keranjang` = baris yang SUDAH ditambahkan lewat "+ Tambah
    // ke Keranjang" ({barberId, serviceIds: Set, tips}), `form*` = entri
    // yang SEDANG diisi tapi BELUM ditambahkan -- supaya kasus paling
    // umum (1 customer saja) tetap secepat alur lama: langsung "Lanjut ke
    // Payment" TANPA klik "Tambah ke Keranjang" dulu (form yang masih
    // terisi otomatis dianggap baris terakhir, lihat kumpulkanJasaItems()).
    const state = {
      keranjang: [], formBarberId: null, formServiceIds: new Set(), formTips: 0,
      produk: {},
      metode: null, channel: null, bankCode: null, transaksi: null,
    };
    let fase = "pilih";

    function formTerisi() {
      return state.formBarberId !== null && state.formServiceIds.size > 0;
    }

    // Keranjang + (form yang masih terisi, kalau ada) -- INI yang akan
    // benar-benar dikirim/ditagihkan kalau "Lanjut ke Payment" diklik
    // sekarang.
    function kumpulkanJasaItems() {
      const items = state.keranjang.map((k) => ({
        barberId: k.barberId, serviceIds: Array.from(k.serviceIds), tips: k.tips,
      }));
      if (formTerisi()) {
        items.push({ barberId: state.formBarberId, serviceIds: Array.from(state.formServiceIds), tips: state.formTips });
      }
      return items;
    }

    function totalHarga() {
      let total = 0;
      for (const item of kumpulkanJasaItems()) {
        for (const sid of item.serviceIds) {
          const s = pengaturan.services.find((x) => x.id === sid);
          if (s) total += s.harga;
        }
        total += item.tips || 0;
      }
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
      state.keranjang = []; state.formBarberId = null; state.formServiceIds = new Set(); state.formTips = 0;
      state.produk = {};
      state.metode = null; state.channel = null; state.bankCode = null; state.transaksi = null;
      fase = "pilih";
    }

    function gantiFase() {
      body.innerHTML = "";
      if (fase === "pilih") renderPilih();
      else if (fase === "payment") renderPayment();
      else if (fase === "menunggu_manual") renderMenungguManual();
      else if (fase === "waiting") renderWaitingGateway();
      else if (fase === "bayar_cash") renderBayarCash();
      else renderSelesai();
    }

    // ---- fase "pilih": Keranjang multi-barber (Barber+Service+Tips per
    // entri) + Produk (tetap tenant-wide, TIDAK terikat barber manapun,
    // satu checkout bisa mencampur Service + Produk -- PERMINTAAN Owner
    // "satu kali scan untuk Service + Produk") ----
    function renderPilih() {
      body.appendChild(MugenUI.el("h2", {}, "Pilih Barber, Service & Produk"));
      const errorBox = MugenUI.el("div", { class: "login-error" });

      // --- Keranjang (baris yang sudah ditambahkan) ---
      const keranjangBox = MugenUI.el("div");
      body.appendChild(keranjangBox);
      function renderKeranjang() {
        keranjangBox.innerHTML = "";
        if (!state.keranjang.length) return;
        keranjangBox.appendChild(MugenUI.el("label", {}, "Keranjang"));
        for (let i = 0; i < state.keranjang.length; i++) {
          const k = state.keranjang[i];
          const barber = pengaturan.barbers.find((b) => b.id === k.barberId);
          const namaService = Array.from(k.serviceIds)
            .map((sid) => pengaturan.services.find((s) => s.id === sid))
            .filter(Boolean).map((s) => s.nama).join(", ");
          const btnHapus = MugenUI.el("button", { type: "button" }, "Hapus");
          btnHapus.addEventListener("click", () => {
            state.keranjang.splice(i, 1);
            renderKeranjang(); renderTotal();
          });
          keranjangBox.appendChild(MugenUI.el("div", {
            class: "card", style: "display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;",
          }, [
            MugenUI.el("div", {}, [
              MugenUI.el("div", { style: "font-weight:700;" }, barber ? barber.nama : "(barber terhapus)"),
              MugenUI.el("div", { class: "subtitle" }, namaService + (k.tips > 0 ? ` — Tips ${MugenUI.formatRupiah(k.tips)}` : "")),
            ]),
            btnHapus,
          ]));
        }
      }
      renderKeranjang();

      // --- Form entri (barber+service+tips yang SEDANG diisi) ---
      // PERMINTAAN Owner: Barber jadi dropdown modern (MugenUI.
      // dropdownSelect(), lihat ui.js), Service jadi card yang bisa
      // diklik seluruh areanya (menggantikan checkbox kecil).
      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Barber"));
      const barberOpsi = pengaturan.barbers.map((b) => ({ value: b.id, label: b.nama }));
      const dropdownBarber = MugenUI.dropdownSelect(barberOpsi, {
        value: state.formBarberId, placeholder: "-- Pilih Barber --",
        onChange: (v) => { state.formBarberId = v; renderTotal(); },
      });
      body.appendChild(dropdownBarber.el);

      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Service"));
      const serviceGrid = MugenUI.el("div", { class: "pos-service-grid" });
      for (const s of pengaturan.services) {
        const card = MugenUI.el("button", {
          type: "button", class: "pos-service-card" + (state.formServiceIds.has(s.id) ? " selected" : ""),
        }, [
          MugenUI.el("div", { class: "pos-service-card-nama" }, s.nama),
          MugenUI.el("div", { class: "pos-service-card-harga" }, MugenUI.formatRupiah(s.harga)),
          MugenUI.el("div", { class: "pos-service-card-check" }, "✓"),
        ]);
        card.addEventListener("click", () => {
          if (state.formServiceIds.has(s.id)) state.formServiceIds.delete(s.id);
          else state.formServiceIds.add(s.id);
          card.classList.toggle("selected");
          renderTotal();
        });
        serviceGrid.appendChild(card);
      }
      body.appendChild(serviceGrid);
      if (!pengaturan.services.length) body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada service aktif."));

      // Tips: manual oleh kasir, PER BARBER (PERMINTAAN Owner -- kasir
      // yang isi sendiri, BUKAN dihitung/dibagi otomatis sistem).
      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Tips untuk barber ini (opsional)"));
      const inputTips = MugenUI.el("input", { type: "number", min: "0", value: String(state.formTips || 0), style: "max-width:160px;" });
      inputTips.addEventListener("input", () => {
        state.formTips = Math.max(0, parseInt(inputTips.value, 10) || 0);
        renderTotal();
      });
      MugenUI.attachNumericKeypad(inputTips);
      body.appendChild(inputTips);

      const btnTambah = MugenUI.el("button", { type: "button", style: "margin-top:12px;" }, "+ Tambah ke Keranjang");
      btnTambah.addEventListener("click", () => {
        errorBox.textContent = "";
        if (!state.formBarberId) { errorBox.textContent = "Pilih Barber terlebih dahulu."; return; }
        if (!state.formServiceIds.size) { errorBox.textContent = "Pilih minimal satu Service terlebih dahulu."; return; }
        state.keranjang.push({ barberId: state.formBarberId, serviceIds: new Set(state.formServiceIds), tips: state.formTips });
        state.formBarberId = null; state.formServiceIds = new Set(); state.formTips = 0;
        fase = "pilih"; gantiFase(); // render ulang penuh -- form & select perlu kembali kosong
      });
      body.appendChild(btnTambah);

      // --- Produk (terpisah, tenant-wide, TIDAK terikat barber manapun) ---
      // PERMINTAAN Owner: dropdown pencarian multi-pilih (bukan daftar qty
      // satu-satu) -- tombol +/- di dalamnya mengatur kuantitas TANPA
      // memicu keyboard apa pun, dropdown TIDAK tertutup tiap satu produk
      // dipilih (tutup hanya lewat klik luar/tombol Tutup). Ringkasan
      // produk yang sudah terpilih tetap tampil di luar dropdown supaya
      // kasir bisa lihat/ubah qty tanpa membuka dropdown lagi.
      body.appendChild(MugenUI.el("label", { style: "margin-top:20px;" }, "Produk"));

      function buatQtyStepper(p) {
        const qty = state.produk[p.id] || 0;
        const btnMinus = MugenUI.el("button", { type: "button", class: "pos-qty-btn" }, "−");
        const nilai = MugenUI.el("span", { class: "pos-qty-value" }, String(qty));
        const btnPlus = MugenUI.el("button", { type: "button", class: "pos-qty-btn" }, "+");
        btnMinus.disabled = qty <= 0;
        btnPlus.disabled = qty >= p.stok;
        btnMinus.addEventListener("click", (e) => { e.stopPropagation(); ubahQtyProduk(p, -1); });
        btnPlus.addEventListener("click", (e) => { e.stopPropagation(); ubahQtyProduk(p, 1); });
        return MugenUI.el("div", { class: "pos-qty-stepper" }, [btnMinus, nilai, btnPlus]);
      }

      const produkTerpilihBox = MugenUI.el("div", { class: "pos-produk-terpilih", style: "margin-top:8px;" });
      function renderProdukTerpilih() {
        produkTerpilihBox.innerHTML = "";
        const idsTerpilih = Object.keys(state.produk).map(Number).filter((id) => state.produk[id] > 0);
        for (const pid of idsTerpilih) {
          const p = pengaturan.produk.find((x) => x.id === pid);
          if (!p) continue;
          produkTerpilihBox.appendChild(MugenUI.el("div", { class: "pos-produk-terpilih-row" }, [
            MugenUI.el("div", {}, [
              MugenUI.el("div", { class: "pos-produk-terpilih-nama" }, p.nama),
              MugenUI.el("div", { class: "pos-produk-terpilih-harga" }, `${MugenUI.formatRupiah(p.harga_jual)}/pcs`),
            ]),
            buatQtyStepper(p),
          ]));
        }
      }

      const produkListEl = MugenUI.el("div");
      function renderDaftarProdukDropdown(query) {
        produkListEl.innerHTML = "";
        const q = (query || "").trim().toLowerCase();
        // Pencarian substring fleksibel -- cocok di MANA PUN dalam nama
        // (bukan cuma awalan), tidak peka huruf besar/kecil.
        const hasil = pengaturan.produk.filter((p) => !q || p.nama.toLowerCase().includes(q));
        if (!hasil.length) {
          produkListEl.appendChild(MugenUI.el("div", { class: "mugen-dropdown-empty" }, "Produk tidak ditemukan."));
          return;
        }
        for (const p of hasil) {
          const terpilih = (state.produk[p.id] || 0) > 0;
          const row = MugenUI.el("div", { class: "pos-produk-option" + (terpilih ? " selected" : "") }, [
            MugenUI.el("div", { class: "pos-produk-option-check" }, "✓"),
            MugenUI.el("div", { class: "pos-produk-option-info" }, [
              MugenUI.el("div", { class: "pos-produk-option-nama" }, p.nama),
              MugenUI.el("div", { class: "pos-produk-option-meta" }, `${MugenUI.formatRupiah(p.harga_jual)}/pcs · stok ${p.stok}`),
            ]),
            buatQtyStepper(p),
          ]);
          row.addEventListener("click", (e) => {
            if (e.target.closest(".pos-qty-btn")) return; // tombol +/- menangani sendiri
            if (p.stok <= 0) return;
            ubahQtyProduk(p, 1); // klik baris = tambah 1 (pilih baru ATAU tambah qty kalau sudah terpilih)
            renderDaftarProdukDropdown(searchProdukInput.value);
          });
          produkListEl.appendChild(row);
        }
      }

      function ubahQtyProduk(p, delta) {
        const qtyBaru = Math.max(0, Math.min(p.stok, (state.produk[p.id] || 0) + delta));
        if (qtyBaru > 0) state.produk[p.id] = qtyBaru; else delete state.produk[p.id];
        renderProdukTerpilih();
        if (dropdownProdukWrap.classList.contains("open")) renderDaftarProdukDropdown(searchProdukInput.value);
        renderTotal();
      }

      const searchProdukInput = MugenUI.el("input", {
        type: "text", class: "mugen-dropdown-search", placeholder: "Cari produk…",
      });
      searchProdukInput.addEventListener("input", () => renderDaftarProdukDropdown(searchProdukInput.value));
      const btnTutupDropdownProduk = MugenUI.el("button", { type: "button", class: "mugen-dropdown-close" }, "Tutup");
      const panelProduk = MugenUI.el("div", { class: "mugen-dropdown-panel" }, [
        MugenUI.el("div", { class: "mugen-dropdown-search-wrap" }, [searchProdukInput]),
        produkListEl,
        btnTutupDropdownProduk,
      ]);
      const triggerProduk = MugenUI.el("button", { type: "button", class: "mugen-dropdown-trigger" }, [
        MugenUI.el("span", { class: "mugen-dropdown-trigger-label" }, "+ Tambah Produk"),
        MugenUI.el("span", { class: "mugen-dropdown-chevron" }, "⌄"),
      ]);
      const dropdownProdukWrap = MugenUI.el("div", { class: "mugen-dropdown", style: "margin-top:10px;" }, [triggerProduk, panelProduk]);

      let pointerdownLuarProduk = null;
      function bukaDropdownProduk() {
        if (dropdownProdukWrap.classList.contains("open")) return;
        dropdownProdukWrap.classList.add("open");
        searchProdukInput.value = "";
        renderDaftarProdukDropdown("");
        pointerdownLuarProduk = (e) => { if (!dropdownProdukWrap.contains(e.target)) tutupDropdownProduk(); };
        setTimeout(() => document.addEventListener("pointerdown", pointerdownLuarProduk, true), 0);
      }
      function tutupDropdownProduk() {
        if (!dropdownProdukWrap.classList.contains("open")) return;
        dropdownProdukWrap.classList.remove("open");
        if (pointerdownLuarProduk) document.removeEventListener("pointerdown", pointerdownLuarProduk, true);
        pointerdownLuarProduk = null;
      }
      triggerProduk.addEventListener("click", () => (
        dropdownProdukWrap.classList.contains("open") ? tutupDropdownProduk() : bukaDropdownProduk()
      ));
      btnTutupDropdownProduk.addEventListener("click", tutupDropdownProduk);

      if (pengaturan.produk.length) {
        body.appendChild(dropdownProdukWrap);
        body.appendChild(produkTerpilihBox);
        renderProdukTerpilih();
      } else {
        body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada produk aktif."));
      }

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
        const jasaItems = kumpulkanJasaItems();
        if (!jasaItems.length && !Object.keys(state.produk).length) {
          errorBox.textContent = "Pilih minimal satu Service atau Produk."; return;
        }
        // Form terisi SEBAGIAN (barber tanpa service, atau sebaliknya) --
        // bukan baris lengkap untuk diikutkan otomatis, tapi juga bukan
        // niat kosong -- minta kasir selesaikan/hapus dulu supaya tidak
        // diam-diam terlewat dari pembayaran.
        if ((state.formBarberId && !state.formServiceIds.size) || (!state.formBarberId && state.formServiceIds.size)) {
          errorBox.textContent = "Lengkapi dulu Barber & Service yang sedang diisi (atau kosongkan keduanya)."; return;
        }
        state.jasaItemsFinal = jasaItems;
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
      // PERMINTAAN Owner: kalau cuma SATU opsi pembayaran yang tersedia
      // (satu-satunya metode aktif, dengan paling banyak satu channel),
      // JANGAN paksa Kasir memilih -- langsung pakai opsi itu, tampilkan
      // sebagai info saja (tombol Back masih bisa kembali ke "pilih").
      const satuOpsi = opsi.length === 1;
      if (!opsi.length) {
        body.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:12px;" },
          "Belum ada metode pembayaran aktif untuk Point of Sale. Hubungi Superadmin."));
      } else if (satuOpsi) {
        state.metode = opsi[0].metode; state.channel = opsi[0].channel;
        metodeBox.appendChild(MugenUI.el("div", { class: "subtitle" }, `Metode pembayaran: ${opsi[0].label}`));
        renderBankBox();
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
            jasa_items: (state.jasaItemsFinal || []).map((it) => ({
              barber_id: it.barberId, service_ids: it.serviceIds, tips: it.tips || 0,
            })),
            produk_items: Object.keys(state.produk).map((pid) => ({ produk_id: Number(pid), jumlah: state.produk[pid] })),
            metode_pembayaran: state.metode,
            channel: state.metode === "gateway" ? state.channel : undefined,
            bank_code: state.metode === "gateway" && state.channel === "va" ? state.bankCode : undefined,
          };
          const hasil = await MugenUI.withButtonLoading(btnBuat, () => MugenApi.post("/api/pos/transaksi", payload));
          state.transaksi = hasil;
          fase = state.metode === "gateway" ? "waiting" : (state.metode === "cash" ? "bayar_cash" : "menunggu_manual");
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
          const hasil = await MugenUI.withButtonLoading(btnTerima, () => MugenApi.post(`/api/pos/transaksi/${state.transaksi.id}/verifikasi`));
          state.transaksi = hasil;
          _suntikTransaksiBaru(hasil);
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
      // PERMINTAAN Owner (antisipasi Kasir salah input sebelum customer
      // sempat scan & bayar): tombol Batalkan -- TIDAK ada di booking
      // publik (customer bisa ditinggal, ada countdown 15 menit terpisah),
      // tapi di Kasir kasusnya beda: kasir berdiri di situ, kalau sadar
      // salah input harus bisa langsung batalkan tanpa menunggu kedaluwarsa.
      const btnBatalkan = MugenUI.el("button", { type: "button", style: "margin-top:12px;margin-left:8px;" }, "Batalkan");
      body.appendChild(MugenUI.el("div", { class: "card" }, [
        MugenUI.el("div", { style: "text-align:center;" }, [statusLabelEl, MugenUI.el("div", {}, [btnSudahBayar, btnBatalkan])]),
        MugenUI.el("hr"),
        MugenUI.el("div", { style: "text-align:center;" }, items),
        MugenUI.el("hr"),
        barisTotal(),
      ]));

      function terapkanStatus(status) {
        if (status.status === "PAID") {
          clearInterval(pollTimer);
          _suntikTransaksiBaru(r);
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

      btnBatalkan.addEventListener("click", async () => {
        if (!document.body.contains(statusLabelEl)) return;
        if (!confirm("Batalkan transaksi ini? Kalau customer terlanjur membayar, pembayaran TETAP akan terdeteksi lunas, TIDAK akan ikut terbatalkan.")) return;
        try {
          const hasil = await MugenUI.withButtonLoading(btnBatalkan,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/batalkan`));
          clearInterval(pollTimer);
          if (hasil.status === "lunas") {
            // Race jarang: customer sempat bayar tepat sebelum Kasir klik
            // Batalkan -- pembayaran TETAP sah, TIDAK dibatalkan.
            MugenUI.toast("Pembayaran ternyata sudah diterima -- transaksi TIDAK dibatalkan.", "error", { force: true });
            state.transaksi = hasil;
            _suntikTransaksiBaru(hasil);
            fase = "selesai"; gantiFase();
            return;
          }
          MugenUI.toast("Transaksi dibatalkan.", "success", { force: true });
          // Keranjang/Produk SENGAJA TIDAK direset (BUKAN resetState()) --
          // kasir biasanya mau LANGSUNG memperbaiki input yang salah lalu
          // coba bayar lagi, bukan mengetik ulang semuanya dari awal.
          state.transaksi = null; state.metode = null; state.channel = null; state.bankCode = null;
          fase = "pilih"; gantiFase();
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
    }

    // ---- fase "bayar_cash": Kasir input nominal uang diterima dari
    // customer, sistem hitung kembalian LIVE sambil mengetik -- transaksi
    // LANGSUNG lunas begitu "Selesaikan Transaksi" diklik (uang tunai
    // diterima di tempat SAAT itu juga, TIDAK ada status menunggu). ----
    function renderBayarCash() {
      const r = state.transaksi;
      body.appendChild(MugenUI.el("h2", {}, "Pembayaran Cash"));
      body.appendChild(MugenUI.el("div", { class: "card" }, [barisTotal()]));

      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Uang Diterima"));
      const inputUang = MugenUI.el("input", { type: "number", min: "0", style: "width:100%;font-size:18px;" });
      MugenUI.attachNumericKeypad(inputUang);
      body.appendChild(inputUang);

      const kembalianBox = MugenUI.el("div", { style: "margin-top:8px;font-weight:700;" });
      body.appendChild(kembalianBox);
      function renderKembalian() {
        const diterima = parseInt(inputUang.value, 10) || 0;
        const sisa = diterima - totalHarga();
        kembalianBox.className = sisa >= 0 ? "subtitle" : "login-error";
        kembalianBox.textContent = sisa >= 0
          ? `Kembalian: ${MugenUI.formatRupiah(sisa)}`
          : `Kurang ${MugenUI.formatRupiah(-sisa)}`;
      }
      inputUang.addEventListener("input", renderKembalian);
      renderKembalian();

      const errorBox = MugenUI.el("div", { class: "login-error" });
      body.appendChild(errorBox);

      const btnSelesai = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Selesaikan Transaksi");
      btnSelesai.addEventListener("click", async () => {
        errorBox.textContent = "";
        const diterima = parseInt(inputUang.value, 10) || 0;
        if (diterima < totalHarga()) { errorBox.textContent = "Uang diterima kurang dari total pembayaran."; return; }
        try {
          const hasil = await MugenUI.withButtonLoading(btnSelesai,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/bayar-cash`, { uang_diterima: diterima }));
          state.transaksi = hasil;
          _suntikTransaksiBaru(hasil);
          MugenUI.toast("Pembayaran Cash diterima.", "success", { force: true });
          fase = "selesai"; gantiFase();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      body.appendChild(btnSelesai);
    }

    // ---- fase "selesai" ----
    function renderSelesai() {
      const r = state.transaksi;
      const isi = [
        MugenUI.el("div", { class: "book-selesai-icon" }, "✓"),
        MugenUI.el("h2", {}, "Pembayaran Berhasil"),
        MugenUI.el("div", { class: "subtitle" }, `Total: ${MugenUI.formatRupiah(totalHarga())}`),
      ];
      if (r && r.metode_pembayaran === "cash") {
        isi.push(MugenUI.el("div", { class: "subtitle" }, `Uang Diterima: ${MugenUI.formatRupiah(r.uang_diterima || 0)}`));
        isi.push(MugenUI.el("div", { style: "font-weight:700;margin-top:4px;" }, `Kembalian: ${MugenUI.formatRupiah(r.kembalian || 0)}`));
      }
      body.appendChild(MugenUI.el("div", { class: "card book-selesai" }, isi));
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
    const userId = MugenState.getUser().id;
    const tanggalHariIni = MugenUI.isoHariIniWib();

    // Tombol Hapus (PERMINTAAN Owner: baris yang terlanjur salah input di
    // POS bisa langsung dihapus dari sini) -- HANYA untuk baris sumber
    // "pos" (booking online TIDAK dihapus dari sini sama sekali). Spinner
    // di tombolnya sendiri (MugenUI.withButtonLoading(), pola SAMA PERSIS
    // halaman lain), lalu muat ulang PAKSA (fetch fresh -- butuh angka
    // stok/Rekap yang benar-benar baru dari server, TIDAK bisa dihitung
    // sendiri di frontend seperti _suntikTransaksiBaru()).
    function kolomAksi(posId) {
      if (!posId) return "-";
      const btn = MugenUI.el("button", { type: "button" }, "Hapus");
      btn.addEventListener("click", async () => {
        if (!confirm("Hapus transaksi POS ini? Stok produk (kalau ada) dikembalikan & Rekap barber terkait dihitung ulang.")) return;
        try {
          await MugenUI.withButtonLoading(btn, () => MugenApi.del(`/api/pos/transaksi/${posId}`));
          MugenUI.toast("Transaksi dihapus.", "success", { force: true });
          await muatUlangPaksa();
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
      return btn;
    }

    function tampilkanData(hasil) {
      body.innerHTML = "";

      // Rincian total per metode pembayaran (PERMINTAAN Owner) --
      // termasuk tips & produk (dihitung dari total mentah tiap
      // transaksi di backend, lihat pos_db.get_transaksi_hari_ini()).
      const rincian = hasil.rincian_metode || {};
      function barisRincian(label, nominal, tebal) {
        return MugenUI.el("div", {
          style: `display:flex;justify-content:space-between;${tebal ? "font-weight:700;" : ""}`,
        }, [MugenUI.el("span", {}, label), MugenUI.el("span", {}, MugenUI.formatRupiah(nominal || 0))]);
      }
      body.appendChild(MugenUI.el("div", { class: "card", style: "margin-bottom:16px;" }, [
        MugenUI.el("div", { style: "font-weight:700;margin-bottom:8px;" }, "Rincian Pembayaran Hari Ini"),
        barisRincian("Payment Gateway", rincian.gateway),
        barisRincian("QRIS Manual", rincian.qris),
        barisRincian("Cash", rincian.cash),
        MugenUI.el("hr"),
        barisRincian("Total Keseluruhan", hasil.total_keseluruhan, true),
      ]));

      body.appendChild(MugenUI.el("h2", {}, "Service"));
      body.appendChild(MugenUI.buildTable(
        [
          { key: "jam", label: "Jam" },
          { key: "nama_barber", label: "Barber" },
          { key: "daftar_service", label: "Service" },
          { key: "nominal", label: "Nominal", format: (v) => MugenUI.formatRupiah(v) },
          { key: "sumber", label: "Sumber", format: (v) => (v === "pos" ? "Kasir" : "Booking Online") },
          { key: "pos_id", label: "Aksi", format: (v) => kolomAksi(v) },
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
          { key: "pos_id", label: "Aksi", format: (v) => kolomAksi(v) },
        ],
        hasil.produk,
        { emptyText: "Belum ada transaksi produk hari ini." },
      ));
    }

    async function muatUlangPaksa() {
      let hasil;
      try {
        hasil = await MugenApi.get("/api/pos/transaksi-hari-ini");
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
        return;
      }
      _cacheTransaksiHariIni = { userId, tanggal: tanggalHariIni, data: hasil };
      tampilkanData(hasil);
    }

    // PERMINTAAN Owner: tab ini TIDAK PERNAH loading kalau sudah pernah
    // dibuka sesi ini untuk tanggal yang sama -- baris baru masuk lewat
    // _suntikTransaksiBaru() (dipanggil begitu SATU transaksi POS lunas,
    // lihat jalankanWizardKasir()), BUKAN fetch ulang di sini.
    if (_cacheTransaksiHariIni && _cacheTransaksiHariIni.userId === userId && _cacheTransaksiHariIni.tanggal === tanggalHariIni) {
      tampilkanData(_cacheTransaksiHariIni.data);
      return;
    }
    body.appendChild(MugenUI.skeleton("table", { cols: 4, rows: 3 }));
    await muatUlangPaksa();
  }

  return { render };
})();

window.PagePos = PagePos;
