// pages/pemasukan.js — Modul Keuangan (Fase 1): CRUD Pemasukan.
// Cermin persis pages/pengeluaran.js -- halaman ini KHUSUS role admin/staff
// (barber tidak melihat menunya di nav.js, DAN router.js melempar barber
// keluar dari halaman ini kalau nekat buka lewat URL langsung). Backend
// (routers/pemasukan.py) juga menolak semua request dari barber lewat
// dependency require_owner_or_staff, jadi perlindungan ada di dua lapis,
// bukan cuma disembunyikan di frontend.

const PagePemasukan = (() => {
  function todayIso() {
    // BUGFIX (audit): lihat catatan lengkap di MugenUI.isoHariIniWib().
    return MugenUI.isoHariIniWib();
  }

  async function render(root) {
    const today = new Date();
    let editingId = null; // null = mode Tambah, angka = mode Edit
    let barbers = [];
    let kategoriOptions = [];

    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Pemasukan"));

    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" -- HANYA
    // pesan kosong, tanpa form/data apa pun.
    const levelPemasukan = await MugenMenuAccess.get("pemasukan");
    if (levelPemasukan === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const bolehEdit = levelPemasukan === "write";

    const formCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    // Hak Akses Menu: level "Baca" -- sembunyikan form Tambah/Edit Pemasukan.
    if (bolehEdit) root.appendChild(formCard);
    root.appendChild(filterCard);
    root.appendChild(listCard);

    try {
      [barbers, kategoriOptions] = await Promise.all([
        MugenApi.get("/api/input-data/barbers", { useCache: true }),
        MugenApi.get("/api/pemasukan/kategori", { useCache: true }),
      ]);
    } catch (e) {
      formCard.appendChild(MugenUI.errorState(e.message));
      return;
    }

    // --- DATALIST kategori (input teks bebas + saran) ---
    const kategoriListId = "pemasukan-kategori-list";
    const datalist = MugenUI.el("datalist", { id: kategoriListId });
    for (const k of kategoriOptions) datalist.appendChild(MugenUI.el("option", { value: k }));
    root.appendChild(datalist);

    // ================= FORM TAMBAH / EDIT =================
    const formTitle = MugenUI.el("h2", {}, "Tambah Pemasukan");
    const inputTanggal = MugenUI.el("input", { type: "date", value: todayIso() });
    const inputKategori = MugenUI.el("input", { type: "text", list: kategoriListId, placeholder: "mis. Modal Tambahan" });
    const inputKeterangan = MugenUI.el("input", { type: "text", placeholder: "Untuk apa pemasukan ini" });
    const inputNominal = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const selBarber = MugenUI.el("select");
    selBarber.appendChild(MugenUI.el("option", { value: "" }, "-- tidak terkait barber (opsional) --"));
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const inputAktif = MugenUI.el("input", { type: "checkbox", style: "width:auto;" });
    inputAktif.checked = true;

    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Simpan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    formCard.appendChild(inputTanggal);
    formCard.appendChild(MugenUI.el("label", {}, "Kategori"));
    formCard.appendChild(inputKategori);
    formCard.appendChild(MugenUI.el("label", {}, "Keterangan"));
    formCard.appendChild(inputKeterangan);
    formCard.appendChild(MugenUI.el("label", {}, "Nominal (Rp)"));
    formCard.appendChild(inputNominal);
    formCard.appendChild(MugenUI.el("label", {}, "Barber (opsional)"));
    formCard.appendChild(selBarber);
    formCard.appendChild(MugenUI.el("label", {}, [inputAktif, " Status Aktif"]));
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Tambah Pemasukan";
      btnSubmit.textContent = "Simpan";
      btnBatal.style.display = "none";
      inputTanggal.value = todayIso();
      inputKategori.value = "";
      inputKeterangan.value = "";
      inputNominal.value = "0";
      selBarber.value = "";
      inputAktif.checked = true;
      formError.textContent = "";
    }

    function isiFormUntukEdit(p) {
      editingId = p.id;
      formTitle.textContent = `Edit Pemasukan #${p.id}`;
      btnSubmit.textContent = "Simpan Perubahan";
      btnBatal.style.display = "";
      inputTanggal.value = p.tanggal;
      inputKategori.value = p.kategori || "";
      inputKeterangan.value = p.keterangan || "";
      inputNominal.value = String(p.jumlah);
      selBarber.value = p.barber_id ? String(p.barber_id) : "";
      inputAktif.checked = !!p.aktif;
      formError.textContent = "";
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatal.addEventListener("click", resetForm);

    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      const body = {
        tanggal: inputTanggal.value,
        kategori: inputKategori.value.trim(),
        keterangan: inputKeterangan.value.trim(),
        jumlah: Number(inputNominal.value) || 0,
        barber_id: selBarber.value ? Number(selBarber.value) : null,
        aktif: inputAktif.checked,
      };
      if (!body.kategori) { formError.textContent = "Kategori tidak boleh kosong."; return; }
      if (!body.keterangan) { formError.textContent = "Keterangan tidak boleh kosong."; return; }
      if (!body.jumlah || body.jumlah <= 0) { formError.textContent = "Nominal harus lebih dari 0."; return; }

      btnSubmit.disabled = true;
      try {
        // REVISI UI/UX Premium: spinner inline di tombol Simpan, bukan overlay layar penuh.
        await MugenUI.withButtonLoading(btnSubmit, async () => {
          if (editingId) {
            await MugenApi.put(`/api/pemasukan/${editingId}`, body);
            MugenUI.toast("Pemasukan diperbarui.", "success");
          } else {
            await MugenApi.post("/api/pemasukan", body);
            MugenUI.toast("Pemasukan disimpan.", "success");
          }
        });
        // Kategori baru yang baru saja diketik langsung ikut jadi saran berikutnya.
        if (!kategoriOptions.includes(body.kategori)) {
          kategoriOptions.push(body.kategori);
          datalist.appendChild(MugenUI.el("option", { value: body.kategori }));
          if (selKategori) selKategori.appendChild(MugenUI.el("option", { value: body.kategori }, body.kategori));
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
    const selKategori = MugenUI.el("select");
    selKategori.appendChild(MugenUI.el("option", { value: "" }, "Semua Kategori"));
    for (const k of kategoriOptions) selKategori.appendChild(MugenUI.el("option", { value: k }, k));
    const inputCari = MugenUI.el("input", { type: "text", placeholder: "Cari keterangan/kategori..." });

    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun, selKategori, inputCari]));
    // Perbaikan Alur Cetak PDF: Preview PDF dulu, TIDAK langsung mengunduh
    // -- lihat pdf_preview.js.
    const btnDownloadPdf = MugenUI.el("button", {}, "Cetak PDF");
    btnDownloadPdf.addEventListener("click", () => {
      const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
      if (selKategori.value) qs.set("kategori", selKategori.value);
      if (inputCari.value.trim()) qs.set("cari", inputCari.value.trim());
      const bagian = ["Laporan Pemasukan", selKategori.value || "", MugenUI.namaBulan(Number(selBulan.value)), selTahun.value];
      MugenPdfPreview.open({
        generate: () => MugenApi.fetchBlob(`/api/pemasukan/pdf?${qs}`),
        filename: MugenUI.namaFileAman(bagian.filter(Boolean).join(" ") + ".pdf"),
      });
    });
    // Feature Gating "export_pdf": lihat catatan sama di pages/rekap.js.
    filterCard.appendChild(
      typeof MugenFeature !== "undefined" && !MugenFeature.has("export_pdf")
        ? MugenFeature.upgradeBlock("Export PDF") : btnDownloadPdf);

    // ================= DAFTAR PEMASUKAN =================
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Pemasukan"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    let debounceTimer = null;
    function loadListDebounced() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(loadList, 300);
    }

    // BUGFIX (audit, race condition): lihat catatan lengkap di
    // pages/pengeluaran.js (pola sama persis) -- dua fetch tumpang tindih
    // (mengetik cepat di pencarian, klik ganda filter) bisa selesai TIDAK
    // berurutan, respons basi bisa menimpa hasil yang lebih baru.
    let urutanTerkini = 0;
    const _RESPON_BASI = Symbol("respon-basi");

    async function loadList() {
      const urutanSaya = ++urutanTerkini;
      // REVISI UI/UX Premium: skeleton tabel + crossfade lewat refreshInto(),
      // menggantikan teks "Memuat..." dan penggantian innerHTML manual.
      try {
        await MugenUI.refreshInto(listBody, async () => {
          const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
          if (selKategori.value) qs.set("kategori", selKategori.value);
          if (inputCari.value.trim()) qs.set("cari", inputCari.value.trim());
          const data = await MugenApi.get(`/api/pemasukan?${qs}`, { useCache: true });
          if (urutanSaya !== urutanTerkini) throw _RESPON_BASI;
          const rows = Array.isArray(data) ? data : [];
          const box = MugenUI.el("div");
          if (data.__offline) box.appendChild(MugenUI.offlineBanner(data.__cachedAt));
          box.appendChild(MugenUI.buildTable(
            [
              { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
              { key: "kategori", label: "Kategori" },
              { key: "keterangan", label: "Keterangan" },
              { key: "nama_barber", label: "Barber", format: (v) => v || "-" },
              { key: "jumlah", label: "Nominal", format: MugenUI.formatRupiah },
              {
                key: "aktif", label: "Status",
                format: (v) => MugenUI.el("span", { class: "badge" + (v ? "" : " badge-libur") }, v ? "Aktif" : "Nonaktif"),
              },
              {
                key: "aksi", label: "Aksi", format: (_, r) => {
                  if (!bolehEdit) return MugenUI.el("span", {}, "-"); // Hak Akses Menu: level "Baca"
                  const wrap = MugenUI.el("div", { class: "actions-cell" });
                  const btnEdit = MugenUI.el("button", {}, "Edit");
                  btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                  const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                  btnHapus.addEventListener("click", async () => {
                    if (!confirm(`Hapus pemasukan "${r.keterangan}" tanggal ${r.tanggal}?`)) return;
                    try {
                      // REVISI UI/UX Premium: spinner inline di tombol Hapus, bukan overlay layar penuh.
                      await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/pemasukan/${r.id}`));
                      MugenUI.toast("Pemasukan dihapus.", "success");
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
          return box;
        }, { skeleton: { kind: "table", cols: 7, rows: 4 } });
      } catch (e) {
        if (e === _RESPON_BASI) return;
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.errorState(e.message));
      }
    }

    // REVISI UI/UX Premium: MugenUI.withLoading(...) dihapus di sini --
    // skeleton tabel di dalam loadList()/refreshInto() (lihat atas) sudah
    // jadi feedback loading yang cukup untuk ganti filter.
    selBulan.addEventListener("change", loadList);
    selTahun.addEventListener("change", loadList);
    selKategori.addEventListener("change", loadList);
    inputCari.addEventListener("input", loadListDebounced);

    resetForm();
    loadList();
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PagePemasukan begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PagePemasukan = PagePemasukan;
