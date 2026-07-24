// pages/produk.js — TAHAP 8
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
    const btnSimpanProduk = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatalUbahProduk = MugenUI.el("button", { style: "display:none;" }, "Batal");
    const produkFormError = MugenUI.el("div", { class: "login-error" });

    produkFormCard.appendChild(produkFormTitle);
    produkFormCard.appendChild(MugenUI.el("label", {}, "Nama Produk"));
    produkFormCard.appendChild(inputNamaProduk);
    produkFormCard.appendChild(produkFormError);
    produkFormCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" },
      [btnSimpanProduk, btnBatalUbahProduk]));

    function resetProdukForm() {
      editingProdukId = null;
      produkFormTitle.textContent = "Tambah Produk";
      btnSimpanProduk.textContent = "Simpan";
      btnBatalUbahProduk.style.display = "none";
      inputNamaProduk.value = "";
      produkFormError.textContent = "";
    }

    function isiFormUbahProduk(p) {
      editingProdukId = p.id;
      produkFormTitle.textContent = `Ubah Nama Produk #${p.id}`;
      btnSimpanProduk.textContent = "Simpan Perubahan";
      btnBatalUbahProduk.style.display = "";
      inputNamaProduk.value = p.nama;
      produkFormError.textContent = "";
      produkFormCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatalUbahProduk.addEventListener("click", resetProdukForm);

    btnSimpanProduk.addEventListener("click", async () => {
      produkFormError.textContent = "";
      const nama = inputNamaProduk.value.trim();
      if (!nama) {
        produkFormError.textContent = "Nama produk tidak boleh kosong.";
        return;
      }
      btnSimpanProduk.disabled = true;
      try {
        if (editingProdukId) {
          await MugenApi.put(`/api/produk/${editingProdukId}`, { nama });
          MugenUI.toast("Nama produk diubah.", "success");
        } else {
          await MugenApi.post("/api/produk", { nama });
          MugenUI.toast("Produk ditambahkan.", "success");
        }
        resetProdukForm();
        loadProdukList();
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
            { key: "stok", label: "Sisa Stok" },
            {
              key: "aksi", label: "Aksi", format: (_, p) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnRestock = MugenUI.el("button", {}, "Restock");
                btnRestock.addEventListener("click", () => bukaFormMutasi(p, "restock"));
                const btnJual = MugenUI.el("button", {}, "Jual");
                btnJual.addEventListener("click", () => bukaFormMutasi(p, "jual"));
                const btnUbah = MugenUI.el("button", {}, "Ubah Nama");
                btnUbah.addEventListener("click", () => isiFormUbahProduk(p));
                const btnNonaktif = MugenUI.el("button", { class: "btn-danger" }, "Nonaktifkan");
                btnNonaktif.addEventListener("click", async () => {
                  if (!confirm(`Nonaktifkan produk "${p.nama}"?`)) return;
                  try {
                    await MugenApi.del(`/api/produk/${p.id}`);
                    MugenUI.toast("Produk dinonaktifkan.", "success");
                    loadProdukList();
                  } catch (e) {
                    MugenUI.toast(e.message, "error");
                  }
                });
                wrap.appendChild(btnRestock);
                wrap.appendChild(btnJual);
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

    function bukaFormMutasi(produk, tipe) {
      mutasiProdukAktif = produk;
      mutasiTipeAktif = tipe;
      mutasiFormTitle.textContent = tipe === "restock"
        ? `Restock — ${produk.nama} (stok saat ini: ${produk.stok})`
        : `Jual — ${produk.nama} (stok saat ini: ${produk.stok})`;
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
        await MugenApi.post(`/api/produk/${mutasiProdukAktif.id}/${mutasiTipeAktif}`, body);
        MugenUI.toast(mutasiTipeAktif === "restock" ? "Restock disimpan." : "Penjualan disimpan.", "success");
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
    const selBulanFilter = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulanFilter.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulanFilter.value = String(today.getMonth() + 1);
    const selTahunFilter = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahunFilter.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahunFilter.value = String(today.getFullYear());

    riwayatCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;" },
      [selProdukFilter, selTipeFilter, selBulanFilter, selTahunFilter]));

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
          await MugenApi.put(`/api/produk/mutasi/${m.id}`, {
            tanggal: tanggalBaru,
            jumlah: Number(jumlahBaru),
            catatan: catatanBaru || null,
          });
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
              format: (v) => MugenUI.el("span", { class: "badge" + (v === "restock" ? "" : " badge-libur") }, v === "restock" ? "Restock" : "Jual"),
            },
            { key: "jumlah", label: "Jumlah" },
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
                    await MugenApi.del(`/api/produk/mutasi/${m.id}`);
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

    selProdukFilter.addEventListener("change", loadRiwayat);
    selTipeFilter.addEventListener("change", loadRiwayat);
    selBulanFilter.addEventListener("change", loadRiwayat);
    selTahunFilter.addEventListener("change", loadRiwayat);

    resetProdukForm();
    await loadProdukList();
    isiOpsiProdukFilter();
    loadRiwayat();
  }

  return { render };
})();
