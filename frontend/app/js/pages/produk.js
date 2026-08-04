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
  function todayIso() {
    return new Date().toISOString().slice(0, 10);
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

    let produkList = [];
    let editingProdukId = null; // null = tambah baru, angka = ubah nama

    const produkFormCard = MugenUI.el("div", { class: "card" });
    const produkListCard = MugenUI.el("div", { class: "card" });
    const mutasiFormCard = MugenUI.el("div", { class: "card", style: "display:none;" });
    const riwayatCard = MugenUI.el("div", { class: "card" });
    root.appendChild(produkFormCard);
    root.appendChild(produkListCard);
    root.appendChild(mutasiFormCard);
    root.appendChild(riwayatCard);

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

    btnSimpanProduk.addEventListener("click", async () => {
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
      btnSimpanProduk.disabled = true;
      try {
        await MugenUI.withLoading(async () => {
          if (editingProdukId) {
            await MugenApi.put(`/api/produk/${editingProdukId}`, { nama, harga_modal: hargaModal, harga_jual: hargaJual });
            MugenUI.toast("Produk diubah.", "success");
          } else {
            await MugenApi.post("/api/produk", { nama, harga_modal: hargaModal, harga_jual: hargaJual });
            MugenUI.toast("Produk ditambahkan.", "success");
          }
        }, { message: "Menyimpan produk…" });
        resetProdukForm();
        await loadProdukList();
        // AUDIT SINKRONISASI: sebelumnya dropdown filter "Riwayat Mutasi"
        // TIDAK ikut di-refresh di sini (hanya diisi sekali saat halaman
        // pertama dibuka) -- produk yang BARU ditambahkan sudah benar
        // muncul di tabel Daftar Produk (loadProdukList di atas) tapi
        // belum muncul di dropdown filter riwayat sampai halaman dibuka
        // ulang. isiOpsiProdukFilter() aman dipanggil ulang (isi ulang
        // total dari produkList yang baru saja di-refresh di atas).
        isiOpsiProdukFilter();
      } catch (e) {
        produkFormError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSimpanProduk.disabled = false;
      }
    });

    // ---------------------------------------------------------------
    // 2. DAFTAR PRODUK
    // ---------------------------------------------------------------
    produkListCard.appendChild(MugenUI.el("h2", {}, "Daftar Produk"));
    const produkListBody = MugenUI.el("div");
    produkListCard.appendChild(produkListBody);

    async function loadProdukList() {
      produkListBody.innerHTML = "Memuat...";
      try {
        const data = await MugenApi.get("/api/produk?hanya_aktif=true", { useCache: true });
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
                    await MugenUI.withLoading(() => MugenApi.del(`/api/produk/${p.id}`), { message: "Menghapus…" });
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
      } catch (e) {
        produkListBody.innerHTML = "";
        produkListBody.appendChild(MugenUI.el("div", {}, e.message));
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

    btnSimpanMutasi.addEventListener("click", async () => {
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
      btnSimpanMutasi.disabled = true;
      try {
        await MugenUI.withLoading(() => MugenApi.post(`/api/produk/${mutasiProdukAktif.id}/${mutasiTipeAktif}`, body), { message: `Memproses ${MUTASI_TIPE_LABEL[mutasiTipeAktif]}…` });
        MugenUI.toast(`${MUTASI_TIPE_LABEL[mutasiTipeAktif]} disimpan.`, "success");
        mutasiFormCard.style.display = "none";
        mutasiProdukAktif = null;
        loadProdukList();
        loadRiwayat();
      } catch (e) {
        mutasiFormError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSimpanMutasi.disabled = false;
      }
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

    function isiFormKoreksiMutasi(m) {
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
          await MugenUI.withLoading(() => MugenApi.put(`/api/produk/mutasi/${m.id}`, {
            tanggal: tanggalBaru,
            jumlah: Number(jumlahBaru),
            catatan: catatanBaru || null,
          }), { message: "Memproses transaksi…" });
          MugenUI.toast("Mutasi dikoreksi.", "success");
          loadProdukList();
          loadRiwayat();
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      })();
    }

    async function loadRiwayat() {
      riwayatBody.innerHTML = "Memuat...";
      try {
        const qs = new URLSearchParams({ tahun: selTahunFilter.value, bulan: selBulanFilter.value });
        if (selProdukFilter.value) qs.set("produk_id", selProdukFilter.value);
        if (selTipeFilter.value) qs.set("tipe", selTipeFilter.value);
        const data = await MugenApi.get(`/api/produk/mutasi?${qs}`, { useCache: true });
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
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnKoreksi = MugenUI.el("button", {}, "Koreksi");
                btnKoreksi.addEventListener("click", () => isiFormKoreksiMutasi(m));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus data ${m.tipe} #${m.id} (${m.nama_produk}, ${m.jumlah})?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/produk/mutasi/${m.id}`), { message: "Menghapus…" });
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
      } catch (e) {
        riwayatBody.innerHTML = "";
        riwayatBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    selProdukFilter.addEventListener("change", () => MugenUI.withLoading(loadRiwayat));
    selTipeFilter.addEventListener("change", () => MugenUI.withLoading(loadRiwayat));
    selBulanFilter.addEventListener("change", () => MugenUI.withLoading(loadRiwayat));
    selTahunFilter.addEventListener("change", () => MugenUI.withLoading(loadRiwayat));

    resetProdukForm();
    await loadProdukList();
    isiOpsiProdukFilter();
    loadRiwayat();
  }

  return { render };
})();
