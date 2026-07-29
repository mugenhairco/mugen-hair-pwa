// pages/uang_kas.js — Modul Keuangan (pengganti Transfer Kas/Bank): Uang Kas.
// Struktur mengikuti pola pages/pemasukan.js -- KHUSUS role admin/staff
// (barber tidak melihat menunya di nav.js, DAN router.js melempar barber
// keluar dari halaman ini kalau nekat buka lewat URL langsung). Backend
// (routers/uang_kas.py) juga menolak semua request dari barber lewat
// dependency require_owner_or_staff.
//
// BEDA dari Pemasukan/Pengeluaran: bukan daftar transaksi individual,
// tapi SATU Saldo Kas Awal (bisa diubah kapan pun) + ledger penyesuaian
// manual (tambah/kurang) -- Saldo Saat Ini = Saldo Kas Awal + seluruh
// penyesuaian, dihitung backend (uang_kas_db.get_saldo_kas()).

const PageUangKas = (() => {
  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  async function render(root) {
    const today = new Date();
    let editingId = null;

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Uang Kas"));

    const saldoCard = MugenUI.el("div", { class: "card" });
    const formCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(saldoCard);
    root.appendChild(formCard);
    root.appendChild(filterCard);
    root.appendChild(listCard);

    // ================= SALDO KAS AWAL + SALDO SAAT INI =================
    saldoCard.appendChild(MugenUI.el("h2", {}, "Saldo Kas"));
    const saldoSaatIniText = MugenUI.el("div", { style: "font-size:1.4em;font-weight:600;" }, "Memuat...");
    saldoCard.appendChild(MugenUI.el("div", { class: "subtitle" }, "Saldo Kas Saat Ini"));
    saldoCard.appendChild(saldoSaatIniText);

    const inputSaldoAwal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const btnSimpanSaldoAwal = MugenUI.el("button", {}, "Simpan Saldo Kas Awal");
    const saldoAwalError = MugenUI.el("div", { class: "login-error" });
    const saldoAwalInfo = MugenUI.el("div", { class: "subtitle" }, "");
    saldoCard.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Saldo Kas Awal (Rp)"));
    saldoCard.appendChild(inputSaldoAwal);
    saldoCard.appendChild(saldoAwalError);
    saldoCard.appendChild(saldoAwalInfo);
    saldoCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnSimpanSaldoAwal));

    async function muatSaldo() {
      try {
        const [awal, saatIni] = await Promise.all([
          MugenApi.get("/api/uang-kas/saldo-awal"),
          MugenApi.get("/api/uang-kas/saldo"),
        ]);
        inputSaldoAwal.value = String(awal.saldo || 0);
        saldoAwalInfo.textContent = awal.diubah_oleh ? `Terakhir diubah oleh ${awal.diubah_oleh} (${awal.updated_at || "-"})` : "";
        saldoSaatIniText.textContent = MugenUI.formatRupiah(saatIni.saldo);
      } catch (e) {
        saldoSaatIniText.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    }

    btnSimpanSaldoAwal.addEventListener("click", async () => {
      saldoAwalError.textContent = "";
      const saldo = Number(inputSaldoAwal.value);
      if (Number.isNaN(saldo) || saldo < 0) { saldoAwalError.textContent = "Saldo Kas Awal tidak valid."; return; }
      btnSimpanSaldoAwal.disabled = true;
      try {
        await MugenUI.withLoading(() => MugenApi.put("/api/uang-kas/saldo-awal", { saldo }), { message: "Menyimpan…" });
        MugenUI.toast("Saldo Kas Awal disimpan.", "success");
        muatSaldo();
      } catch (e) {
        saldoAwalError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSimpanSaldoAwal.disabled = false;
      }
    });

    // ================= FORM TAMBAH / EDIT PENYESUAIAN =================
    const formTitle = MugenUI.el("h2", {}, "Tambah Penyesuaian Kas");
    const inputTanggal = MugenUI.el("input", { type: "date", value: todayIso(), max: todayIso() });
    const selJenis = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "tambah" }, "Tambah"),
      MugenUI.el("option", { value: "kurang" }, "Kurang"),
    ]);
    const inputJumlah = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "mis. Koreksi selisih hitung fisik" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(MugenUI.el("label", {}, "Jenis"));
    formCard.appendChild(selJenis);
    formCard.appendChild(MugenUI.el("label", {}, "Jumlah (Rp)"));
    formCard.appendChild(inputJumlah);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Tambah Penyesuaian Kas";
      btnSubmit.textContent = "Simpan";
      btnBatal.style.display = "none";
      inputTanggal.value = todayIso();
      selJenis.value = "tambah";
      inputJumlah.value = "0";
      inputKeterangan.value = "";
      formError.textContent = "";
    }
    btnBatal.addEventListener("click", resetForm);

    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      if (!inputJumlah.value || Number(inputJumlah.value) <= 0) { formError.textContent = "Jumlah harus lebih dari 0."; return; }
      btnSubmit.disabled = true;
      try {
        const body = {
          tanggal: inputTanggal.value, jenis: selJenis.value,
          jumlah: Number(inputJumlah.value) || 0, keterangan: inputKeterangan.value.trim(),
        };
        if (editingId) {
          await MugenUI.withLoading(() => MugenApi.put(`/api/uang-kas/${editingId}`, body), { message: "Menyimpan…" });
          MugenUI.toast("Penyesuaian kas diperbarui.", "success");
        } else {
          await MugenUI.withLoading(() => MugenApi.post("/api/uang-kas", body), { message: "Menyimpan…" });
          MugenUI.toast("Penyesuaian kas disimpan.", "success");
        }
        resetForm();
        muatSaldo();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
      }
    });

    // ================= FILTER + DOWNLOAD PDF =================
    filterCard.appendChild(MugenUI.el("h2", {}, "Filter"));
    const selBulan = MugenUI.el("select");
    selBulan.appendChild(MugenUI.el("option", { value: "" }, "Semua Bulan"));
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    const selTahun = MugenUI.el("select");
    selTahun.appendChild(MugenUI.el("option", { value: "" }, "Semua Tahun"));
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun]));

    const btnDownloadPdf = MugenUI.el("button", {}, "Download PDF");
    btnDownloadPdf.addEventListener("click", async () => {
      try {
        await MugenUI.withLoading(() => {
          const qs = new URLSearchParams();
          if (selBulan.value) qs.set("bulan", selBulan.value);
          if (selTahun.value) qs.set("tahun", selTahun.value);
          return MugenApi.downloadFile(`/api/uang-kas/pdf?${qs}`, "laporan_uang_kas.pdf");
        }, { message: "Menyiapkan PDF…" });
      } catch (e) {
        MugenUI.toast(e.message, "error");
      }
    });
    filterCard.appendChild(btnDownloadPdf);

    // ================= DAFTAR PENYESUAIAN =================
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Penyesuaian Kas"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadList() {
      listBody.innerHTML = "Memuat...";
      try {
        const qs = new URLSearchParams();
        if (selBulan.value) qs.set("bulan", selBulan.value);
        if (selTahun.value) qs.set("tahun", selTahun.value);
        const data = await MugenApi.get(`/api/uang-kas?${qs}`);
        const rows = Array.isArray(data) ? data : [];
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            {
              key: "jenis", label: "Jenis",
              format: (v) => MugenUI.el("span", { class: "badge" + (v === "tambah" ? "" : " badge-libur") }, v === "tambah" ? "Tambah" : "Kurang"),
            },
            { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
            { key: "keterangan", label: "Keterangan", format: (v) => v || "-" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Edit");
                btnEdit.addEventListener("click", () => {
                  editingId = r.id;
                  formTitle.textContent = `Edit Penyesuaian #${r.id}`;
                  btnSubmit.textContent = "Simpan Perubahan";
                  btnBatal.style.display = "";
                  inputTanggal.value = r.tanggal;
                  selJenis.value = r.jenis;
                  inputJumlah.value = String(r.jumlah);
                  inputKeterangan.value = r.keterangan || "";
                  formError.textContent = "";
                  formCard.scrollIntoView({ behavior: "smooth" });
                });
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus penyesuaian kas tanggal ${r.tanggal}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/uang-kas/${r.id}`), { message: "Menghapus…" });
                    MugenUI.toast("Penyesuaian kas dihapus.", "success");
                    muatSaldo();
                    loadList();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnEdit);
                wrap.appendChild(btnHapus);
                return wrap;
              },
            },
          ],
          rows,
          { emptyText: "Belum ada penyesuaian kas." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
      }
    }

    selBulan.addEventListener("change", loadList);
    selTahun.addEventListener("change", loadList);

    resetForm();
    muatSaldo();
    loadList();
  }

  return { render };
})();
