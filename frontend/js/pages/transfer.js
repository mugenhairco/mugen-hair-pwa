// pages/transfer.js — Modul Keuangan (Fase 2): CRUD Transfer Kas/Bank.
// Struktur mengikuti pola pages/pemasukan.js/pengeluaran.js -- KHUSUS
// role admin/staff (barber tidak melihat menunya di nav.js, DAN router.js
// melempar barber keluar dari halaman ini kalau nekat buka lewat URL
// langsung). Backend (routers/transfer.py) juga menolak semua request
// dari barber lewat dependency require_owner_or_staff.
//
// Murni catatan pemindahan dana antar akun toko sendiri (mis. Kas Tunai ->
// Bank) -- TIDAK memengaruhi laba/rugi atau kartu Dashboard mana pun,
// sengaja tidak dihubungkan ke perhitungan finansial lain.

const PageTransfer = (() => {
  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  async function render(root) {
    const today = new Date();
    let editingId = null;
    let akunOptions = [];

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Transfer Kas/Bank"));

    const formCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(filterCard);
    root.appendChild(listCard);

    try {
      akunOptions = await MugenApi.get("/api/transfer/akun", { useCache: true });
    } catch (e) {
      formCard.appendChild(MugenUI.el("div", {}, e.message));
      return;
    }

    // --- DATALIST akun (input teks bebas + saran) ---
    const akunListId = "transfer-akun-list";
    const datalist = MugenUI.el("datalist", { id: akunListId });
    for (const a of akunOptions) datalist.appendChild(MugenUI.el("option", { value: a }));
    root.appendChild(datalist);

    // ================= FORM TAMBAH / EDIT =================
    const formTitle = MugenUI.el("h2", {}, "Catat Transfer");
    const inputTanggal = MugenUI.el("input", { type: "date", value: todayIso() });
    const inputDariAkun = MugenUI.el("input", { type: "text", list: akunListId, placeholder: "mis. Kas Tunai" });
    const inputKeAkun = MugenUI.el("input", { type: "text", list: akunListId, placeholder: "mis. Bank" });
    const inputNominal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "Opsional" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(MugenUI.el("label", {}, "Dari Akun"));
    formCard.appendChild(inputDariAkun);
    formCard.appendChild(MugenUI.el("label", {}, "Ke Akun"));
    formCard.appendChild(inputKeAkun);
    formCard.appendChild(MugenUI.el("label", {}, "Nominal (Rp)"));
    formCard.appendChild(inputNominal);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Catat Transfer";
      btnSubmit.textContent = "Simpan";
      btnBatal.style.display = "none";
      inputTanggal.value = todayIso();
      inputDariAkun.value = "";
      inputKeAkun.value = "";
      inputNominal.value = "0";
      inputKeterangan.value = "";
      formError.textContent = "";
    }

    function isiFormUntukEdit(t) {
      editingId = t.id;
      formTitle.textContent = `Edit Transfer #${t.id}`;
      btnSubmit.textContent = "Simpan Perubahan";
      btnBatal.style.display = "";
      inputTanggal.value = t.tanggal;
      inputDariAkun.value = t.dari_akun;
      inputKeAkun.value = t.ke_akun;
      inputNominal.value = String(t.jumlah);
      inputKeterangan.value = t.keterangan || "";
      formError.textContent = "";
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatal.addEventListener("click", resetForm);

    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      const body = {
        tanggal: inputTanggal.value,
        dari_akun: inputDariAkun.value.trim(),
        ke_akun: inputKeAkun.value.trim(),
        jumlah: Number(inputNominal.value) || 0,
        keterangan: inputKeterangan.value.trim(),
      };
      if (!body.dari_akun || !body.ke_akun) { formError.textContent = "Akun Asal dan Akun Tujuan wajib diisi."; return; }
      if (body.dari_akun === body.ke_akun) { formError.textContent = "Akun Asal dan Akun Tujuan tidak boleh sama."; return; }
      if (!body.jumlah || body.jumlah <= 0) { formError.textContent = "Nominal harus lebih dari 0."; return; }

      btnSubmit.disabled = true;
      try {
        await MugenUI.withLoading(async () => {
          if (editingId) {
            await MugenApi.put(`/api/transfer/${editingId}`, body);
            MugenUI.toast("Transfer diperbarui.", "success");
          } else {
            await MugenApi.post("/api/transfer", body);
            MugenUI.toast("Transfer disimpan.", "success");
          }
        }, { message: "Menyimpan…" });
        for (const akun of [body.dari_akun, body.ke_akun]) {
          if (!akunOptions.includes(akun)) {
            akunOptions.push(akun);
            datalist.appendChild(MugenUI.el("option", { value: akun }));
          }
        }
        resetForm();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
      }
    });

    // ================= FILTER =================
    filterCard.appendChild(MugenUI.el("h2", {}, "Cari & Filter"));
    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(today.getMonth() + 1);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(today.getFullYear());
    const inputCari = MugenUI.el("input", { type: "text", placeholder: "Cari akun/keterangan..." });

    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun, inputCari]));
    const btnDownloadPdf = MugenUI.el("button", {}, "Download PDF");
    btnDownloadPdf.addEventListener("click", async () => {
      try {
        await MugenUI.withLoading(() => {
          const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
          if (inputCari.value.trim()) qs.set("cari", inputCari.value.trim());
          return MugenApi.downloadFile(`/api/transfer/pdf?${qs}`, "laporan_transfer.pdf");
        }, { message: "Menyiapkan PDF…" });
      } catch (e) {
        MugenUI.toast(e.message, "error");
      }
    });
    filterCard.appendChild(btnDownloadPdf);

    // ================= DAFTAR TRANSFER =================
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Transfer"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    let debounceTimer = null;
    function loadListDebounced() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(loadList, 300);
    }

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      try {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        if (inputCari.value.trim()) qs.set("cari", inputCari.value.trim());
        const data = await MugenApi.get(`/api/transfer?${qs}`, { useCache: true });
        listBody.innerHTML = "";
        if (data.__offline) listBody.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        const rows = Array.isArray(data) ? data : [];
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "dari_akun", label: "Dari Akun" },
            { key: "ke_akun", label: "Ke Akun" },
            { key: "jumlah", label: "Nominal", format: MugenUI.formatRupiah },
            { key: "keterangan", label: "Keterangan", format: (v) => v || "-" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Edit");
                btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus transfer ${r.dari_akun} -> ${r.ke_akun} tanggal ${r.tanggal}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/transfer/${r.id}`), { message: "Menghapus…" });
                    MugenUI.toast("Transfer dihapus.", "success");
                    loadList();
                  } catch (e) {
                    MugenUI.toast(e.message, "error");
                  }
                });
                wrap.appendChild(btnEdit);
                wrap.appendChild(btnHapus);
                return wrap;
              },
            },
          ],
          rows,
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.message));
      }
    }

    selBulan.addEventListener("change", () => MugenUI.withLoading(loadList));
    selTahun.addEventListener("change", () => MugenUI.withLoading(loadList));
    inputCari.addEventListener("input", loadListDebounced);

    resetForm();
    loadList();
  }

  return { render };
})();
