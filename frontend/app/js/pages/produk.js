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
    root.appendChild(MugenUI.el("h1", {}, "Produk"));

    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" -- HANYA
    // pesan kosong, tanpa form/data apa pun.
    const levelProduk = await MugenMenuAccess.get("produk");
    if (levelProduk === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const bolehEdit = levelProduk === "write";
    const user = MugenState.getUser();

    let produkList = [];
    let editingProdukId = null; // null = tambah baru, angka = ubah nama

    const produkPendingBanner = MugenUI.el("div", { style: "display:none;" });
    const produkFormCard = MugenUI.el("div", { class: "card" });
    const produkListCard = MugenUI.el("div", { class: "card" });
    const mutasiFormCard = MugenUI.el("div", { class: "card", style: "display:none;" });
    const riwayatCard = MugenUI.el("div", { class: "card" });
    // Hak Akses Menu: level "Baca" -- sembunyikan form Tambah/Ubah Produk &
    // form Mutasi (restock/jual/tester); daftar produk & riwayat tetap tampil.
    if (bolehEdit) root.appendChild(produkPendingBanner);
    if (bolehEdit) root.appendChild(produkFormCard);
    root.appendChild(produkListCard);
    if (bolehEdit) root.appendChild(mutasiFormCard);
    root.appendChild(riwayatCard);

    // PERMINTAAN OWNER: lihat catatan lengkap pola ini di
    // input_data.js::pendingList (Simpan Transaksi) -- di sini satu
    // antrian dipakai untuk DUA jenis aksi (produk & mutasi), dibedakan
    // lewat `entry.jenis`.
    let produkPendingList = bolehEdit ? bacaPendingProduk(user.id) : [];

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
    // 1. TAMBAH / UBAH PRODUK
    // ---------------------------------------------------------------
    const produkFormTitle = MugenUI.el("h2", {}, "Tambah Produk");
    const inputNamaProduk = MugenUI.el("input", { type: "text", placeholder: "Nama produk" });
    const inputHargaModal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputHargaJual = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const btnSimpanProduk = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatalUbahProduk = MugenUI.el("button", { style: "display:none;" }, "Batal");
    const produkFormError = MugenUI.el("div", { class: "login-error" });

    produkFormCard.appendChild(produkFormTitle);
    produkFormCard.appendChild(MugenUI.el("label", {}, "Nama Produk"));
    produkFormCard.appendChild(inputNamaProduk);
    produkFormCard.appendChild(MugenUI.el("label", {}, "Harga Modal (Rp)"));
    produkFormCard.appendChild(inputHargaModal);
    produkFormCard.appendChild(MugenUI.el("label", {}, "Harga Jual (Rp)"));
    produkFormCard.appendChild(inputHargaJual);
    produkFormCard.appendChild(produkFormError);
    produkFormCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" },
      [btnSimpanProduk, btnBatalUbahProduk]));

    function resetProdukForm() {
      editingProdukId = null;
      produkFormTitle.textContent = "Tambah Produk";
      btnSimpanProduk.textContent = "Simpan";
      btnBatalUbahProduk.style.display = "none";
      inputNamaProduk.value = "";
      inputHargaModal.value = "0";
      inputHargaJual.value = "0";
      produkFormError.textContent = "";
    }

    function isiFormUbahProduk(p) {
      editingProdukId = p.id;
      produkFormTitle.textContent = `Ubah Produk #${p.id}`;
      btnSimpanProduk.textContent = "Simpan Perubahan";
      btnBatalUbahProduk.style.display = "";
      inputNamaProduk.value = p.nama;
      inputHargaModal.value = String(p.harga_modal || 0);
      inputHargaJual.value = String(p.harga_jual || 0);
      produkFormError.textContent = "";
      produkFormCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatalUbahProduk.addEventListener("click", resetProdukForm);

    btnSimpanProduk.addEventListener("click", () => {
      produkFormError.textContent = "";
      const nama = inputNamaProduk.value.trim();
      const hargaModal = Number(inputHargaModal.value);
      const hargaJual = Number(inputHargaJual.value);
      if (!nama) {
        produkFormError.textContent = "Nama produk tidak boleh kosong.";
        return;
      }
      if (Number.isNaN(hargaModal) || hargaModal < 0 || Number.isNaN(hargaJual) || hargaJual < 0) {
        produkFormError.textContent = "Harga Modal/Harga Jual tidak valid.";
        return;
      }
      // PERMINTAAN OWNER: jangan tunggu server -- langsung tampil sukses,
      // kirim diam-diam di belakang (jaring pengaman localStorage di atas).
      const editId = editingProdukId;
      const entry = {
        tempId: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        jenis: "produk",
        editId,
        body: { nama, harga_modal: hargaModal, harga_jual: hargaJual },
        label: editId ? `Ubah Produk #${editId} -- ${nama}` : `Tambah Produk -- ${nama}`,
      };
      produkPendingList = [...produkPendingList, entry];
      tulisPendingProduk(user.id, produkPendingList);
      MugenUI.toast(editId ? "Produk diubah." : "Produk ditambahkan.", "success");
      resetProdukForm();
      kirimProdukPending(entry);
    });

    // ---------------------------------------------------------------
    // 2. DAFTAR PRODUK
    // ---------------------------------------------------------------
    produkListCard.appendChild(MugenUI.el("h2", {}, "Daftar Produk"));
    const produkListBody = MugenUI.el("div");
    produkListCard.appendChild(produkListBody);

    function renderDenganDataProduk(data) {
      produkList = Array.isArray(data) ? data : [];
      produkListBody.innerHTML = "";
      if (data.__offline) produkListBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
      produkListBody.appendChild(MugenUI.buildTable(
          [
            { key: "nama", label: "Nama Produk" },
            { key: "harga_modal", label: "Harga Modal", format: MugenUI.formatRupiah },
            { key: "harga_jual", label: "Harga Jual", format: MugenUI.formatRupiah },
            { key: "stok", label: "Sisa Stok" },
            {
              key: "aksi", label: "Aksi", format: (_, p) => {
                if (!bolehEdit) return MugenUI.el("span", {}, "-"); // Hak Akses Menu: level "Baca"
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnRestock = MugenUI.el("button", {}, "Restock");
                btnRestock.addEventListener("click", () => bukaFormMutasi(p, "restock"));
                const btnJual = MugenUI.el("button", {}, "Jual");
                btnJual.addEventListener("click", () => bukaFormMutasi(p, "jual"));
                const btnTester = MugenUI.el("button", {}, "Tester");
                btnTester.addEventListener("click", () => bukaFormMutasi(p, "tester"));
                const btnUbah = MugenUI.el("button", {}, "Ubah");
                btnUbah.addEventListener("click", () => isiFormUbahProduk(p));
                const btnNonaktif = MugenUI.el("button", { class: "btn-danger" }, "Nonaktifkan");
                btnNonaktif.addEventListener("click", async () => {
                  if (!confirm(`Nonaktifkan produk "${p.nama}"?`)) return;
                  try {
                    // REVISI UI/UX Premium: withButtonLoading() menggantikan withLoading().
                    await MugenUI.withButtonLoading(btnNonaktif, () => MugenApi.del(`/api/produk/${p.id}`));
                    MugenUI.toast("Produk dinonaktifkan.", "success");
                    loadProdukList();
                  } catch (e) {
                    MugenUI.toast(e.message, "error");
                  }
                });
                wrap.appendChild(btnRestock);
                wrap.appendChild(btnJual);
                wrap.appendChild(btnTester);
                wrap.appendChild(btnUbah);
                wrap.appendChild(btnNonaktif);
                return wrap;
              },
            },
          ],
          produkList,
          { emptyText: "Belum ada produk." },
        ));
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
    // 3. FORM RESTOCK / JUAL (per produk yang dipilih dari daftar)
    // ---------------------------------------------------------------
    let mutasiProdukAktif = null; // { id, nama }
    let mutasiTipeAktif = "restock";

    const mutasiFormTitle = MugenUI.el("h2", {}, "Restock / Jual");
    const inputMutasiTanggal = MugenUI.el("input", { type: "date", value: todayIso() });
    const inputMutasiJumlah = MugenUI.el("input", { type: "number", min: "1", value: "1" });
    const inputMutasiCatatan = MugenUI.el("input", { type: "text", placeholder: "Opsional" });
    const btnSimpanMutasi = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnTutupMutasi = MugenUI.el("button", {}, "Tutup");
    const mutasiFormError = MugenUI.el("div", { class: "login-error" });

    mutasiFormCard.appendChild(mutasiFormTitle);
    mutasiFormCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    mutasiFormCard.appendChild(inputMutasiTanggal);
    mutasiFormCard.appendChild(MugenUI.el("label", {}, "Jumlah"));
    mutasiFormCard.appendChild(inputMutasiJumlah);
    mutasiFormCard.appendChild(MugenUI.el("label", {}, "Catatan"));
    mutasiFormCard.appendChild(inputMutasiCatatan);
    mutasiFormCard.appendChild(mutasiFormError);
    mutasiFormCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" },
      [btnSimpanMutasi, btnTutupMutasi]));

    const MUTASI_TIPE_LABEL = { restock: "Restock", jual: "Jual", tester: "Tester" };

    function bukaFormMutasi(produk, tipe) {
      mutasiProdukAktif = produk;
      mutasiTipeAktif = tipe;
      mutasiFormTitle.textContent = `${MUTASI_TIPE_LABEL[tipe]} — ${produk.nama} (stok saat ini: ${produk.stok})`;
      inputMutasiTanggal.value = todayIso();
      inputMutasiJumlah.value = "1";
      inputMutasiCatatan.value = "";
      mutasiFormError.textContent = "";
      mutasiFormCard.style.display = "";
      mutasiFormCard.scrollIntoView({ behavior: "smooth" });
    }

    btnTutupMutasi.addEventListener("click", () => {
      mutasiFormCard.style.display = "none";
      mutasiProdukAktif = null;
    });

    btnSimpanMutasi.addEventListener("click", () => {
      mutasiFormError.textContent = "";
      if (!mutasiProdukAktif) return;
      const jumlah = Number(inputMutasiJumlah.value);
      if (!jumlah || jumlah <= 0) {
        mutasiFormError.textContent = "Jumlah harus lebih dari 0.";
        return;
      }
      const body = {
        tanggal: inputMutasiTanggal.value,
        jumlah,
        catatan: inputMutasiCatatan.value || null,
      };
      // PERMINTAAN OWNER: jangan tunggu server -- langsung tampil sukses,
      // kirim diam-diam di belakang (jaring pengaman localStorage di atas).
      const entry = {
        tempId: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        jenis: "mutasi",
        produkId: mutasiProdukAktif.id,
        tipe: mutasiTipeAktif,
        body,
        label: `${MUTASI_TIPE_LABEL[mutasiTipeAktif]} -- ${mutasiProdukAktif.nama} x${jumlah}`,
      };
      produkPendingList = [...produkPendingList, entry];
      tulisPendingProduk(user.id, produkPendingList);
      MugenUI.toast(`${MUTASI_TIPE_LABEL[mutasiTipeAktif]} disimpan.`, "success");
      mutasiFormCard.style.display = "none";
      mutasiProdukAktif = null;
      kirimProdukPending(entry);
    });

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
      [selProdukFilter, selTipeFilter, selBulanFilter, selTahunFilter]));

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
              key: "aksi", label: "Aksi", format: (_, m) => {
                if (!bolehEdit) return MugenUI.el("span", {}, "-"); // Hak Akses Menu: level "Baca"
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnKoreksi = MugenUI.el("button", {}, "Koreksi");
                btnKoreksi.addEventListener("click", () => isiFormKoreksiMutasi(btnKoreksi, m));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus data ${m.tipe} #${m.id} (${m.nama_produk}, ${m.jumlah})?`)) return;
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
                wrap.appendChild(btnKoreksi);
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

    resetProdukForm();
    if (bolehEdit) renderProdukPendingBanner();
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
