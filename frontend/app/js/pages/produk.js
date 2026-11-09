// pages/produk.js — ditulis di Tahap 10, dihubungkan ke router/nav di Tahap 11.
// Khusus Owner (admin), sama seperti backend routers/produk.py: data produk
// adalah persediaan barang dagang milik TOKO, bukan milik barber manapun.
//
// Tiga bagian di halaman ini:
// 1. Form Tambah/Ubah Produk + daftar produk (nama, sisa stok, aksi).
// 2. Form Restock / Jual untuk satu produk yang dipilih dari daftar.
// 3. Riwayat Mutasi (restock & jual) dengan filter, serta aksi Koreksi/Hapus
//    (mengikuti pesan error dari backend kalau saldo stok akan jadi negatif).

const PageProduk = (() => {
  // PERMINTAAN OWNER: pola SAMA seperti dashboard_owner.js/rekap.js --
  // simpan hasil fetch TERAKHIR (Daftar Produk & Riwayat Mutasi, key
  // dibedakan lewat `bagian` di bawah) di LUAR render() (modul-level)
  // supaya bertahan lintas navigasi menu. Kalau Produk dibuka lagi TANPA
  // ada simpan/edit/hapus apa pun sejak terakhir kali BAGIAN itu berhasil
  // dimuat (lihat state.js::halamanPerluRefresh("produk")) DAN filter
  // (url) yang aktif sama persis, tampilkan ulang data ini TANPA fetch/skeleton.
  let _cacheTerakhir = {}; // { [bagian]: { userId, url, data } }

  function _ambilDariCache(bagian, userId, url) {
    const c = _cacheTerakhir[bagian];
    if (!c || c.userId !== userId || c.url !== url) return null;
    return c.data;
  }

  function _simpanKeCache(bagian, userId, url, data) {
    _cacheTerakhir[bagian] = { userId, url, data };
  }

  function todayIso() {
    // BUGFIX (audit): lihat catatan lengkap di MugenUI.isoHariIniWib().
    return MugenUI.isoHariIniWib();
  }

  // PERMINTAAN OWNER: Tambah/Ubah Produk & Restock/Jual/Tester sama seperti
  // Simpan Transaksi di input_data.js -- jangan tunggu server, supaya tidak
  // "loading" tiap simpan. Jaring pengaman localStorage per-user (satu
  // antrian untuk KEDUA jenis aksi, dibedakan lewat `jenis` tiap entry --
  // lihat kirimProdukPending() di bawah). Koreksi Mutasi & Hapus/Nonaktifkan
  // TIDAK diubah (jarang dipakai, lewat prompt()/confirm() terpisah).
  function kunciPendingProduk(userId) {
    return `mugen_pending_produk_user_${userId}`;
  }
  function bacaPendingProduk(userId) {
    try {
      return JSON.parse(localStorage.getItem(kunciPendingProduk(userId)) || "[]");
    } catch (e) {
      return [];
    }
  }
  function tulisPendingProduk(userId, daftar) {
    try {
      localStorage.setItem(kunciPendingProduk(userId), JSON.stringify(daftar));
    } catch (e) {
      // localStorage penuh/diblokir -- biarkan, jaring pengamannya saja yang tidak aktif.
    }
  }

  // Cetak PDF: PDF ditampilkan dulu lewat MugenPdfPreview (Zoom/Nomor
  // Halaman/Download PDF/Print), TIDAK langsung mengunduh -- pola yang
  // sama dipakai rekap.js (duplikasi kecil per-modul, konsisten dengan
  // gaya codebase). `computeOptions` dipanggil ULANG tiap klik supaya
  // filter yang aktif SAAT diklik yang dipakai.
  function tombolCetakPdf(computeOptions) {
    // Feature Gating "export_pdf": lihat catatan sama di pages/rekap.js.
    if (typeof MugenFeature !== "undefined" && !MugenFeature.has("export_pdf")) {
      return MugenFeature.upgradeBlock("Export PDF");
    }
    const btn = MugenUI.el("button", {}, "Cetak PDF");
    btn.addEventListener("click", () => {
      const { generate, filename } = computeOptions();
      MugenPdfPreview.open({ generate, filename });
    });
    return btn;
  }

  async function render(root) {
    const today = new Date();
    root.innerHTML = "";
    root.appendChild(MugenUI.pageTitle("Produk", MugenIcons.produk));

    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" -- HANYA
    // pesan kosong, tanpa form/data apa pun.
    const levelProduk = await MugenMenuAccess.get("produk");
    if (levelProduk === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    // REVISI Hak Akses (sub-item terpisah, lihat permissions.py::
    // PERMISSION_TREE): Tambah/Kelola Produk (izin_produk_kelola) dan
    // Restock/Jual/Tester (izin_produk_mutasi) SEKARANG dua saklar
    // terpisah, BUKAN lagi satu level kasar.
    const bolehKelolaProduk = await MugenMenuAccess.has("izin_produk_kelola");
    const bolehMutasi = await MugenMenuAccess.has("izin_produk_mutasi");
    const bolehHapusProduk = await MugenMenuAccess.has("izin_produk_hapus");
    const user = MugenState.getUser();

    let produkList = [];

    const produkPendingBanner = MugenUI.el("div", { style: "display:none;" });
    const produkListCard = MugenUI.el("div", { class: "card" });
    const riwayatCard = MugenUI.el("div", { class: "card" });
    // Hak Akses: Tambah Produk (izin_produk_kelola) & aksi Mutasi (izin_
    // produk_mutasi) masing-masing punya saklar sendiri; daftar produk &
    // riwayat tetap tampil. PERMINTAAN Owner ("aksi per-baris jadi menu
    // titik tiga, langsung modal di tengah layar -- jangan perlu scroll",
    // lanjut "form Tambah Produk jadi tombol juga, taruh dekat Daftar
    // Produk"): Tambah/Ubah Produk & Restock/Jual/Tester SEKARANG semua
    // modal (bukaModalTambahProduk()/bukaModalUbahProduk()/bukaModalMutasi()
    // di bawah) -- TIDAK ADA LAGI form besar yang selalu terbuka di atas
    // halaman, tombolnya nempel di header card "Daftar Produk".
    if (bolehKelolaProduk) root.appendChild(produkPendingBanner);
    root.appendChild(produkListCard);
    root.appendChild(riwayatCard);

    // PERMINTAAN OWNER: lihat catatan lengkap pola ini di
    // input_data.js::pendingList (Simpan Transaksi) -- di sini satu
    // antrian dipakai untuk DUA jenis aksi (produk & mutasi), dibedakan
    // lewat `entry.jenis`.
    let produkPendingList = (bolehKelolaProduk || bolehMutasi) ? bacaPendingProduk(user.id) : [];

    function renderProdukPendingBanner() {
      produkPendingBanner.innerHTML = "";
      if (produkPendingList.length === 0) {
        produkPendingBanner.style.display = "none";
        return;
      }
      produkPendingBanner.style.display = "";
      const box = MugenUI.el("div", { class: "card", style: "border:1px solid var(--danger);" });
      box.appendChild(MugenUI.el("div", { style: "font-weight:600;margin-bottom:6px;" },
        `${produkPendingList.length} perubahan produk belum terkonfirmasi tersimpan di server.`));
      box.appendChild(MugenUI.el("div", { style: "margin-bottom:8px;color:var(--text-muted);" },
        'Cek dulu di "Daftar Produk"/"Riwayat Mutasi" di bawah -- kalau sudah muncul di sana, klik "Sudah Ada, Buang" (jangan Kirim Ulang supaya tidak dobel).'));
      for (const entry of produkPendingList) {
        const row = MugenUI.el("div", { class: "row", style: "align-items:center;margin-bottom:4px;flex-wrap:wrap;gap:8px;" });
        row.appendChild(MugenUI.el("div", { style: "flex:1;" }, entry.label));
        const btnKirim = MugenUI.el("button", {}, "Kirim Ulang");
        btnKirim.addEventListener("click", () => kirimProdukPending(entry, btnKirim));
        const btnBuang = MugenUI.el("button", { class: "btn-danger" }, "Sudah Ada, Buang");
        btnBuang.addEventListener("click", () => {
          produkPendingList = produkPendingList.filter((e) => e.tempId !== entry.tempId);
          tulisPendingProduk(user.id, produkPendingList);
          renderProdukPendingBanner();
        });
        row.appendChild(btnKirim);
        row.appendChild(btnBuang);
        box.appendChild(row);
      }
      produkPendingBanner.appendChild(box);
    }

    function kirimProdukPending(entry, btnEl) {
      const kirim = () => {
        if (entry.jenis === "produk") {
          return entry.editId
            ? MugenApi.put(`/api/produk/${entry.editId}`, entry.body)
            : MugenApi.post("/api/produk", entry.body);
        }
        return MugenApi.post(`/api/produk/${entry.produkId}/${entry.tipe}`, entry.body);
      };
      (btnEl ? MugenUI.withButtonLoading(btnEl, kirim) : kirim())
        .then(() => {
          produkPendingList = produkPendingList.filter((e) => e.tempId !== entry.tempId);
          tulisPendingProduk(user.id, produkPendingList);
          renderProdukPendingBanner();
          loadProdukList().then(() => {
            if (entry.jenis === "produk") isiOpsiProdukFilter();
          });
          if (entry.jenis === "mutasi") loadRiwayat();
        })
        .catch((e) => {
          renderProdukPendingBanner();
          MugenUI.toast(`${entry.label} gagal terkirim: ${e.detail && e.detail.detail ? e.detail.detail : e.message}`, "error", { force: true });
        });
    }

    // ---------------------------------------------------------------
    // 1. TAMBAH PRODUK -- PERMINTAAN Owner: tombol "+ Tambah Produk" di
    //    header card Daftar Produk, klik langsung buka modal (konsisten
    //    dengan bukaModalUbahProduk()/bukaModalMutasi() di bawah -- TIDAK
    //    ADA LAGI form besar yang selalu terbuka di atas halaman).
    // ---------------------------------------------------------------
    function bukaModalTambahProduk() {
      const inpNama = MugenUI.el("input", { type: "text", placeholder: "Nama produk" });
      const inpModal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const inpJual = MugenUI.el("input", { type: "number", min: "0", value: "0" });
      const err = MugenUI.el("div", { class: "login-error" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan");

      const modal = MugenUI.infoModal({
        title: "Tambah Produk",
        body: [
          MugenUI.el("label", {}, "Nama Produk"), inpNama,
          MugenUI.el("label", {}, "Harga Modal (Rp)"), inpModal,
          MugenUI.el("label", {}, "Harga Jual (Rp)"), inpJual,
          err,
          MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan),
        ],
      });

      btnSimpan.addEventListener("click", () => {
        err.textContent = "";
        const nama = inpNama.value.trim();
        const hargaModal = Number(inpModal.value);
        const hargaJual = Number(inpJual.value);
        if (!nama) {
          err.textContent = "Nama produk tidak boleh kosong.";
          return;
        }
        if (Number.isNaN(hargaModal) || hargaModal < 0 || Number.isNaN(hargaJual) || hargaJual < 0) {
          err.textContent = "Harga Modal/Harga Jual tidak valid.";
          return;
        }
        // PERMINTAAN OWNER: jangan tunggu server -- langsung tampil sukses,
        // kirim diam-diam di belakang (jaring pengaman localStorage di atas).
        const entry = {
          tempId: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          jenis: "produk",
          editId: null,
          body: { nama, harga_modal: hargaModal, harga_jual: hargaJual },
          label: `Tambah Produk -- ${nama}`,
        };
        produkPendingList = [...produkPendingList, entry];
        tulisPendingProduk(user.id, produkPendingList);
        MugenUI.toast("Produk ditambahkan.", "success");
        modal.close();
        kirimProdukPending(entry);
      });
    }

    // ---------------------------------------------------------------
    // 2. DAFTAR PRODUK
    // ---------------------------------------------------------------
    const produkListHeader = MugenUI.el("div", { class: "card-header-row" }, [
      MugenUI.el("h2", { style: "margin:0;" }, "Daftar Produk"),
    ]);
    if (bolehKelolaProduk) {
      const btnTambahProduk = MugenUI.el("button", {
        type: "button", class: "btn-primary", style: "display:inline-flex;align-items:center;gap:8px;",
      }, [
        MugenUI.el("span", { class: "btn-icon-inline", html: MugenIcons.plus }),
        "Tambah Produk",
      ]);
      btnTambahProduk.addEventListener("click", () => bukaModalTambahProduk());
      produkListHeader.appendChild(btnTambahProduk);
    }
    produkListCard.appendChild(produkListHeader);

    // PERMINTAAN Owner ("pencarian untuk produk, tampilannya pakai ikon"):
    // cari NAMA produk, client-side saja (daftar produk sudah penuh di
    // memori lewat produkList, tidak perlu round-trip API baru) -- ikon
    // kaca pembesar lewat MugenUI.selectIcon() (fungsinya generik, bukan
    // cuma untuk <select>, lihat catatan di style.css::.select-icon-wrap).
    let produkSearchQuery = "";
    const inputCariProduk = MugenUI.el("input", { type: "text", placeholder: "Cari produk..." });
    produkListCard.appendChild(MugenUI.el("div", { style: "max-width:320px;margin-bottom:14px;" },
      [MugenUI.selectIcon(MugenIcons.search, inputCariProduk)]));
    inputCariProduk.addEventListener("input", () => {
      produkSearchQuery = inputCariProduk.value;
      renderTabelProduk();
    });

    const produkListBody = MugenUI.el("div");
    produkListCard.appendChild(produkListBody);
    const produkTableBox = MugenUI.el("div");

    function kolomProduk() {
      return [
        { key: "nama", label: "Nama Produk" },
        { key: "harga_modal", label: "Harga Modal", format: MugenUI.formatRupiah },
        { key: "harga_jual", label: "Harga Jual", format: MugenUI.formatRupiah },
        { key: "stok", label: "Sisa Stok" },
        {
          // PERMINTAAN Owner ("daftar produk banyak, aksi jadi titik
          // tiga saja -- klik langsung modal di tengah, tidak perlu
          // scroll"): Restock/Jual/Tester/Ubah/Nonaktifkan sekarang
          // SATU tombol menu "⋮" per baris (MugenUI.bukaMenuAksi(),
          // helper generik di ui.js -- dipakai juga booking.js), ganti
          // 5 tombol sejajar. Hak akses per aksi (izin_produk_mutasi/
          // kelola/hapus) TETAP sama seperti sebelumnya -- cuma
          // menentukan item mana yang masuk daftar menu.
          key: "aksi", label: "Aksi", format: (_, p) => {
            const items = [];
            if (bolehMutasi) {
              items.push({ label: "Restock", onClick: () => bukaModalMutasi(p, "restock") });
              items.push({ label: "Jual", onClick: () => bukaModalMutasi(p, "jual") });
              items.push({ label: "Tester", onClick: () => bukaModalMutasi(p, "tester") });
            }
            if (bolehKelolaProduk) {
              items.push({ label: "Ubah", onClick: () => bukaModalUbahProduk(p) });
            }
            if (bolehHapusProduk) {
              items.push({ label: "Nonaktifkan", danger: true, onClick: () => nonaktifkanProduk(p) });
            }
            if (items.length === 0) return MugenUI.el("span", {}, "-");
            const btnAksi = MugenUI.el("button", {
              type: "button", class: "aksi-btn", "aria-label": "Aksi", html: MugenIcons.moreVertical,
            });
            btnAksi.addEventListener("click", (e) => {
              e.stopPropagation();
              MugenUI.bukaMenuAksi(btnAksi, items);
            });
            return btnAksi;
          },
        },
      ];
    }

    function renderTabelProduk() {
      produkTableBox.innerHTML = "";
      const q = produkSearchQuery.trim().toLowerCase();
      const rows = q ? produkList.filter((p) => p.nama.toLowerCase().includes(q)) : produkList;
      produkTableBox.appendChild(MugenUI.buildTable(kolomProduk(), rows, {
        emptyText: q ? "Tidak ada produk yang cocok." : "Belum ada produk.",
      }));
    }

    function renderDenganDataProduk(data) {
      produkList = Array.isArray(data) ? data : [];
      produkListBody.innerHTML = "";
      if (data.__offline) produkListBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
      produkListBody.appendChild(produkTableBox);
      renderTabelProduk();
    }

    async function loadProdukList(opts = {}) {
      const url = "/api/produk?hanya_aktif=true";

      // PERMINTAAN OWNER: pola SAMA seperti Dashboard/Rekap -- begitu menu
      // Produk dibuka lagi (pindah menu lalu balik) TANPA ada simpan/edit/
      // hapus apa pun sejak terakhir kali Daftar Produk berhasil dimuat,
      // tampilkan ulang hasil fetch terakhir PERSIS seperti itu -- instan,
      // tanpa skeleton/fetch sama sekali. Hanya dicek untuk pemuatan AWAL
      // (opts.bisaDariCache, dipanggil SEKALI di akhir render() di bawah)
      // -- refresh setelah simpan/hapus (call site lain di file ini, TANPA
      // opts) SELALU fetch ulang.
      if (opts.bisaDariCache && !MugenState.halamanPerluRefresh("produk")) {
        const cached = _ambilDariCache("daftar", MugenState.getUser().id, url);
        if (cached) {
          renderDenganDataProduk(cached);
          return;
        }
      }

      // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...".
      produkListBody.innerHTML = "";
      produkListBody.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 4 }));
      try {
        const data = await MugenApi.get(url, { useCache: true });
        if (!data.__offline) {
          _simpanKeCache("daftar", MugenState.getUser().id, url, data);
          MugenState.tandaiHalamanBersih("produk");
        }
        renderDenganDataProduk(data);
      } catch (e) {
        produkListBody.innerHTML = "";
        produkListBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    // ---------------------------------------------------------------
    // 3. MENU AKSI "⋮" + MODAL Restock/Jual/Tester/Ubah (per produk,
    //    dipicu dari Daftar Produk di atas) -- PERMINTAAN Owner: semua
    //    langsung modal di tengah layar, TIDAK PERNAH scroll ke bagian
    //    lain halaman.
    // ---------------------------------------------------------------
    const MUTASI_TIPE_LABEL = { restock: "Restock", jual: "Jual", tester: "Tester" };

    function bukaModalMutasi(produk, tipe) {
      const inpTanggal = MugenUI.el("input", { type: "date", value: todayIso() });
      const inpJumlah = MugenUI.el("input", { type: "number", min: "1", value: "1" });
      const inpCatatan = MugenUI.el("input", { type: "text", placeholder: "Opsional" });
      const err = MugenUI.el("div", { class: "login-error" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan");

      const modal = MugenUI.infoModal({
        title: `${MUTASI_TIPE_LABEL[tipe]} — ${produk.nama} (stok saat ini: ${produk.stok})`,
        body: [
          MugenUI.el("label", {}, "Tanggal"), inpTanggal,
          MugenUI.el("label", {}, "Jumlah"), inpJumlah,
          MugenUI.el("label", {}, "Catatan"), inpCatatan,
          err,
          MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan),
        ],
      });

      btnSimpan.addEventListener("click", () => {
        err.textContent = "";
        const jumlah = Number(inpJumlah.value);
        if (!jumlah || jumlah <= 0) {
          err.textContent = "Jumlah harus lebih dari 0.";
          return;
        }
        const body = { tanggal: inpTanggal.value, jumlah, catatan: inpCatatan.value || null };
        // PERMINTAAN OWNER: jangan tunggu server -- langsung tampil sukses,
        // kirim diam-diam di belakang (jaring pengaman localStorage di atas).
        const entry = {
          tempId: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          jenis: "mutasi",
          produkId: produk.id,
          tipe,
          body,
          label: `${MUTASI_TIPE_LABEL[tipe]} -- ${produk.nama} x${jumlah}`,
        };
        produkPendingList = [...produkPendingList, entry];
        tulisPendingProduk(user.id, produkPendingList);
        MugenUI.toast(`${MUTASI_TIPE_LABEL[tipe]} disimpan.`, "success");
        modal.close();
        kirimProdukPending(entry);
      });
    }

    function bukaModalUbahProduk(produk) {
      const inpNama = MugenUI.el("input", { type: "text", value: produk.nama });
      const inpModal = MugenUI.el("input", { type: "number", min: "0", value: String(produk.harga_modal || 0) });
      const inpJual = MugenUI.el("input", { type: "number", min: "0", value: String(produk.harga_jual || 0) });
      const err = MugenUI.el("div", { class: "login-error" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Perubahan");

      const modal = MugenUI.infoModal({
        title: `Ubah Produk — ${produk.nama}`,
        body: [
          MugenUI.el("label", {}, "Nama Produk"), inpNama,
          MugenUI.el("label", {}, "Harga Modal (Rp)"), inpModal,
          MugenUI.el("label", {}, "Harga Jual (Rp)"), inpJual,
          err,
          MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpan),
        ],
      });

      btnSimpan.addEventListener("click", () => {
        err.textContent = "";
        const nama = inpNama.value.trim();
        const hargaModal = Number(inpModal.value);
        const hargaJual = Number(inpJual.value);
        if (!nama) {
          err.textContent = "Nama produk tidak boleh kosong.";
          return;
        }
        if (Number.isNaN(hargaModal) || hargaModal < 0 || Number.isNaN(hargaJual) || hargaJual < 0) {
          err.textContent = "Harga Modal/Harga Jual tidak valid.";
          return;
        }
        // PERMINTAAN OWNER: jangan tunggu server -- langsung tampil sukses,
        // kirim diam-diam di belakang (jaring pengaman localStorage di atas).
        const entry = {
          tempId: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          jenis: "produk",
          editId: produk.id,
          body: { nama, harga_modal: hargaModal, harga_jual: hargaJual },
          label: `Ubah Produk #${produk.id} -- ${nama}`,
        };
        produkPendingList = [...produkPendingList, entry];
        tulisPendingProduk(user.id, produkPendingList);
        MugenUI.toast("Produk diubah.", "success");
        modal.close();
        kirimProdukPending(entry);
      });
    }

    async function nonaktifkanProduk(produk) {
      if (!(await MugenUI.confirmModal({ message: `Nonaktifkan produk "${produk.nama}"?`, danger: true }))) return;
      try {
        await MugenApi.del(`/api/produk/${produk.id}`);
        MugenUI.toast("Produk dinonaktifkan.", "success");
        loadProdukList();
      } catch (e) {
        MugenUI.toast(e.message, "error");
      }
    }

    // ---------------------------------------------------------------
    // 4. RIWAYAT MUTASI (dengan filter + koreksi/hapus)
    // ---------------------------------------------------------------
    riwayatCard.appendChild(MugenUI.el("h2", {}, "Riwayat Mutasi"));

    const selProdukFilter = MugenUI.el("select");
    const selTipeFilter = MugenUI.el("select");
    selTipeFilter.appendChild(MugenUI.el("option", { value: "" }, "Semua Tipe"));
    selTipeFilter.appendChild(MugenUI.el("option", { value: "restock" }, "Restock"));
    selTipeFilter.appendChild(MugenUI.el("option", { value: "jual" }, "Jual"));
    selTipeFilter.appendChild(MugenUI.el("option", { value: "tester" }, "Tester"));
    const selBulanFilter = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulanFilter.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulanFilter.value = String(today.getMonth() + 1);
    const selTahunFilter = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahunFilter.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahunFilter.value = String(today.getFullYear());

    riwayatCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;" },
      [MugenUI.selectIcon(MugenIcons.produk, selProdukFilter), MugenUI.selectIcon(MugenIcons.filter, selTipeFilter), MugenUI.selectIcon(MugenIcons.calendar, selBulanFilter), MugenUI.selectIcon(MugenIcons.calendar, selTahunFilter)]));

    // Cetak PDF: filter yang dipakai SAMA PERSIS dengan yang sedang aktif
    // di layar (produk/tipe/tahun/bulan) -- lihat laporan_pdf.py
    // buat_pdf_mutasi_produk(), sumber datanya SAMA (db.get_mutasi_produk_list())
    // dengan tabel di bawah supaya isi PDF selalu identik dengan tabel.
    riwayatCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;" }, [
      tombolCetakPdf(() => {
        const qs = new URLSearchParams({ tahun: selTahunFilter.value, bulan: selBulanFilter.value });
        if (selProdukFilter.value) qs.set("produk_id", selProdukFilter.value);
        if (selTipeFilter.value) qs.set("tipe", selTipeFilter.value);
        const namaProduk = selProdukFilter.value
          ? (produkList.find((p) => String(p.id) === selProdukFilter.value) || {}).nama || "Produk"
          : "Semua Produk";
        return {
          generate: () => MugenApi.fetchBlob(`/api/produk/mutasi/pdf?${qs}`),
          filename: MugenUI.namaFileAman(`Riwayat Mutasi Produk ${namaProduk} ${MugenUI.namaBulan(Number(selBulanFilter.value))} ${selTahunFilter.value}.pdf`),
        };
      }),
    ]));

    const riwayatBody = MugenUI.el("div");
    riwayatCard.appendChild(riwayatBody);

    function isiOpsiProdukFilter() {
      selProdukFilter.innerHTML = "";
      selProdukFilter.appendChild(MugenUI.el("option", { value: "" }, "Semua Produk"));
      for (const p of produkList) selProdukFilter.appendChild(MugenUI.el("option", { value: String(p.id) }, p.nama));
    }

    function isiFormKoreksiMutasi(btn, m) {
      // Koreksi tanggal/jumlah/catatan lewat prompt sederhana supaya tidak
      // perlu form/modal terpisah untuk aksi yang jarang dipakai ini.
      const tanggalBaru = prompt("Tanggal (YYYY-MM-DD):", m.tanggal);
      if (tanggalBaru === null) return;
      const jumlahBaru = prompt("Jumlah:", String(m.jumlah));
      if (jumlahBaru === null) return;
      const catatanBaru = prompt("Catatan (kosongkan jika tidak ada):", m.catatan || "");
      if (catatanBaru === null) return;
      (async () => {
        try {
          // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
          await MugenUI.withButtonLoading(btn, () => MugenApi.put(`/api/produk/mutasi/${m.id}`, {
            tanggal: tanggalBaru,
            jumlah: Number(jumlahBaru),
            catatan: catatanBaru || null,
          }));
          MugenUI.toast("Mutasi dikoreksi.", "success");
          loadProdukList();
          loadRiwayat();
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      })();
    }

    function renderDenganDataRiwayat(data) {
      riwayatBody.innerHTML = "";
      if (data.__offline) riwayatBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
      const rows = Array.isArray(data) ? data : [];
      riwayatBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_produk", label: "Produk" },
            {
              key: "tipe", label: "Tipe",
              format: (v) => MugenUI.el("span", {
                class: "badge" + (v === "restock" ? "" : v === "tester" ? " badge-tester" : " badge-libur"),
              }, MUTASI_TIPE_LABEL[v] || v),
            },
            { key: "jumlah", label: "Jumlah" },
            { key: "sisa_stok", label: "Sisa Stok" },
            { key: "catatan", label: "Catatan" },
            {
              // REVISI Hak Akses (sub-item terpisah): Koreksi (izin_produk_
              // mutasi) dan Hapus (izin_produk_hapus) punya gerbang sendiri.
              key: "aksi", label: "Aksi", format: (_, m) => {
                if (!bolehMutasi && !bolehHapusProduk) return MugenUI.el("span", {}, "-");
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                if (bolehMutasi) {
                  const btnKoreksi = MugenUI.el("button", {}, "Koreksi");
                  btnKoreksi.addEventListener("click", () => isiFormKoreksiMutasi(btnKoreksi, m));
                  wrap.appendChild(btnKoreksi);
                }
                if (!bolehHapusProduk) return wrap;
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!(await MugenUI.confirmModal({ message: `Hapus data ${m.tipe} #${m.id} (${m.nama_produk}, ${m.jumlah})?`, danger: true }))) return;
                  try {
                    // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
                    await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/produk/mutasi/${m.id}`));
                    MugenUI.toast("Data mutasi dihapus.", "success");
                    loadProdukList();
                    loadRiwayat();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnHapus);
                return wrap;
              },
            },
          ],
          rows,
          { emptyText: "Belum ada riwayat mutasi." },
        ));
    }

    async function loadRiwayat(opts = {}) {
      const qs = new URLSearchParams({ tahun: selTahunFilter.value, bulan: selBulanFilter.value });
      if (selProdukFilter.value) qs.set("produk_id", selProdukFilter.value);
      if (selTipeFilter.value) qs.set("tipe", selTipeFilter.value);
      const url = `/api/produk/mutasi?${qs}`;

      // PERMINTAAN OWNER: lihat catatan panjang di loadProdukList() di atas
      // -- pola SAMA PERSIS, cuma key cache beda ("riwayat").
      if (opts.bisaDariCache && !MugenState.halamanPerluRefresh("produk")) {
        const cached = _ambilDariCache("riwayat", MugenState.getUser().id, url);
        if (cached) {
          renderDenganDataRiwayat(cached);
          return;
        }
      }

      // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat...".
      riwayatBody.innerHTML = "";
      riwayatBody.appendChild(MugenUI.skeleton("table", { cols: 6, rows: 4 }));
      try {
        const data = await MugenApi.get(url, { useCache: true });
        if (!data.__offline) {
          _simpanKeCache("riwayat", MugenState.getUser().id, url, data);
          MugenState.tandaiHalamanBersih("produk");
        }
        renderDenganDataRiwayat(data);
      } catch (e) {
        riwayatBody.innerHTML = "";
        riwayatBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
    // -- skeleton di riwayatBody sendiri (di atas) sudah cukup.
    selProdukFilter.addEventListener("change", () => loadRiwayat());
    selTipeFilter.addEventListener("change", () => loadRiwayat());
    selBulanFilter.addEventListener("change", () => loadRiwayat());
    selTahunFilter.addEventListener("change", loadRiwayat);

    if (bolehKelolaProduk || bolehMutasi) renderProdukPendingBanner();
    await loadProdukList({ bisaDariCache: true });
    isiOpsiProdukFilter();
    loadRiwayat({ bisaDariCache: true });
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageProduk begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageProduk = PageProduk;
