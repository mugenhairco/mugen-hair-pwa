// pages/izin_cuti.js — Modul Karyawan (Fase 5): Izin & Cuti.
// Pola akses SAMA PERSIS reimburse.js (self-service): barber boleh
// mengajukan/mengedit/menghapus pengajuan MILIKNYA SENDIRI selama masih
// Pending, tanpa perlu izin_cuti_karyawan (itu HANYA berlaku untuk staff
// mengelola pengajuan SEMUA barber + aksi Setujui/Tolak, lihat
// routers/izin_cuti.py). Badge notifikasi jumlah pending di sidebar
// (Owner/Admin) lewat izin_notif.js -- lihat nav.js.

const PageIzinCuti = (() => {
  function badgeStatus(status) {
    const label = status === "disetujui" ? "Disetujui" : status === "ditolak" ? "Ditolak" : "Pending";
    return MugenUI.el("span", { class: "badge" + (status === "disetujui" ? "" : " badge-libur") }, label);
  }

  function labelJenis(jenis) {
    return jenis === "cuti" ? "Cuti" : "Izin";
  }

  // Perbaikan Alur Cetak PDF: lihat catatan sama di pages/kasbon.js.
  function tombolDownloadPdf(getParams, computeFilename) {
    // Feature Gating "export_pdf": lihat catatan sama di pages/rekap.js.
    if (typeof MugenFeature !== "undefined" && !MugenFeature.has("export_pdf")) {
      return MugenFeature.upgradeBlock("Export PDF");
    }
    const btn = MugenUI.el("button", {}, "Cetak PDF");
    btn.addEventListener("click", () => {
      const qs = new URLSearchParams(getParams());
      const filename = computeFilename ? computeFilename() : "Laporan Izin Cuti.pdf";
      MugenPdfPreview.open({
        generate: () => MugenApi.fetchBlob(`/api/izin-cuti/pdf?${qs}`),
        filename: MugenUI.namaFileAman(filename),
      });
    });
    return btn;
  }

  // ================= BARBER: pengajuan milik sendiri =================
  async function renderBarberView(root) {
    const today = new Date().toISOString().slice(0, 10);
    const formCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(listCard);

    let editingId = null;
    const formTitle = MugenUI.el("h2", {}, "Ajukan Izin / Cuti");
    const selJenis = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "izin" }, "Izin"),
      MugenUI.el("option", { value: "cuti" }, "Cuti"),
    ]);
    const inputMulai = MugenUI.el("input", { type: "date", value: today });
    const inputSelesai = MugenUI.el("input", { type: "date", value: today });
    const inputAlasan = MugenUI.el("input", { type: "text", placeholder: "Wajib diisi" });
    const btnSubmit = MugenUI.el("button", { class: "btn-primary" }, "Ajukan");
    const btnBatal = MugenUI.el("button", { style: "display:none;" }, "Batal Edit");
    const formError = MugenUI.el("div", { class: "login-error" });

    formCard.appendChild(formTitle);
    formCard.appendChild(MugenUI.el("label", {}, "Jenis"));
    formCard.appendChild(selJenis);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal Mulai"));
    formCard.appendChild(inputMulai);
    formCard.appendChild(MugenUI.el("label", {}, "Tanggal Selesai"));
    formCard.appendChild(inputSelesai);
    formCard.appendChild(MugenUI.el("label", {}, "Alasan"));
    formCard.appendChild(inputAlasan);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [btnSubmit, btnBatal]));

    function resetForm() {
      editingId = null;
      formTitle.textContent = "Ajukan Izin / Cuti";
      btnSubmit.textContent = "Ajukan";
      btnBatal.style.display = "none";
      selJenis.value = "izin";
      inputMulai.value = today;
      inputSelesai.value = today;
      inputAlasan.value = "";
      formError.textContent = "";
    }

    function isiFormUntukEdit(r) {
      editingId = r.id;
      formTitle.textContent = `Edit Pengajuan #${r.id}`;
      btnSubmit.textContent = "Simpan Perubahan";
      btnBatal.style.display = "";
      selJenis.value = r.jenis;
      inputMulai.value = r.tanggal_mulai;
      inputSelesai.value = r.tanggal_selesai;
      inputAlasan.value = r.alasan;
      formError.textContent = "";
      formCard.scrollIntoView({ behavior: "smooth" });
    }

    btnBatal.addEventListener("click", resetForm);
    btnSubmit.addEventListener("click", async () => {
      formError.textContent = "";
      if (!inputAlasan.value.trim()) { formError.textContent = "Alasan wajib diisi."; return; }
      if (inputMulai.value > inputSelesai.value) { formError.textContent = "Tanggal Mulai tidak boleh setelah Tanggal Selesai."; return; }
      btnSubmit.disabled = true;
      try {
        const body = {
          jenis: selJenis.value, tanggal_mulai: inputMulai.value, tanggal_selesai: inputSelesai.value,
          alasan: inputAlasan.value.trim(),
        };
        // REVISI UI/UX Premium: withButtonLoading() (spinner inline di
        // tombol) menggantikan withLoading() (overlay layar penuh) untuk
        // aksi CRUD rutin -- lihat catatan di ui.js.
        if (editingId) {
          await MugenUI.withButtonLoading(btnSubmit, () => MugenApi.put(`/api/izin-cuti/${editingId}`, body));
          MugenUI.toast("Pengajuan diperbarui.", "success");
        } else {
          await MugenUI.withButtonLoading(btnSubmit, () => MugenApi.post("/api/izin-cuti", body));
          MugenUI.toast("Pengajuan berhasil dikirim.", "success");
        }
        resetForm();
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnSubmit.disabled = false;
      }
    });

    listCard.appendChild(MugenUI.el("h2", {}, "Riwayat Pengajuan Saya"));
    listCard.appendChild(tombolDownloadPdf(() => ({}), () => "Laporan Izin Cuti Saya.pdf"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function loadList() {
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.skeleton("table", { cols: 6, rows: 3 }));
      try {
        const data = await MugenApi.get("/api/izin-cuti");
        const rows = Array.isArray(data) ? data : [];
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.buildTable(
          [
            { key: "jenis", label: "Jenis", format: labelJenis },
            { key: "tanggal_mulai", label: "Mulai", format: MugenUI.formatTanggal },
            { key: "tanggal_selesai", label: "Selesai", format: MugenUI.formatTanggal },
            { key: "alasan", label: "Alasan" },
            { key: "status", label: "Status", format: badgeStatus },
            { key: "catatan_approval", label: "Catatan", format: (v) => v || "-" },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                if (r.status !== "pending") return MugenUI.el("span", { class: "subtitle" }, "-");
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnEdit = MugenUI.el("button", {}, "Edit");
                btnEdit.addEventListener("click", () => isiFormUntukEdit(r));
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Batalkan pengajuan ${labelJenis(r.jenis)} tanggal ${r.tanggal_mulai}?`)) return;
                  try {
                    await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/izin-cuti/${r.id}`));
                    MugenUI.toast("Pengajuan dibatalkan.", "success");
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
          { emptyText: "Belum ada pengajuan Izin/Cuti." },
        ));
      } catch (e) {
        listBody.innerHTML = "";
        listBody.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
      }
    }

    resetForm();
    loadList();

    // FITUR Notifikasi Push: kartu terpisah, gagal diam-diam/tidak
    // ditampilkan sama sekali kalau backend belum enabled (VAPID_* belum
    // diisi Owner) atau browser tidak mendukung -- lihat
    // push_notif.js::renderCard(). Barber ditawarkan di sini (bukan cuma
    // di Pengaturan yang khusus admin/staff) supaya bisa dapat notifikasi
    // status pengajuan Izin/Cuti-nya sendiri (disetujui/ditolak).
    if (typeof MugenPushNotif !== "undefined") await MugenPushNotif.renderCard(root);
  }

  // ================= OWNER/ADMIN: kelola & approve semua pengajuan =================
  async function renderAdminView(root) {
    let barbers = [];
    try {
      barbers = await MugenApi.get("/api/input-data/karyawan", { useCache: true });
    } catch (e) { /* opsional */ }

    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(filterCard);
    root.appendChild(listCard);

    filterCard.appendChild(MugenUI.el("h2", {}, "Filter"));
    const filBarber = MugenUI.el("select");
    filBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Karyawan"));
    for (const b of barbers) filBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const filJenis = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Semua Jenis"),
      MugenUI.el("option", { value: "izin" }, "Izin"),
      MugenUI.el("option", { value: "cuti" }, "Cuti"),
    ]);
    const filStatus = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Semua Status"),
      MugenUI.el("option", { value: "pending" }, "Pending"),
      MugenUI.el("option", { value: "disetujui" }, "Disetujui"),
      MugenUI.el("option", { value: "ditolak" }, "Ditolak"),
    ]);
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [filBarber, filJenis, filStatus]));
    filterCard.appendChild(tombolDownloadPdf(() => {
      const params = {};
      if (filBarber.value) params.barber_id = filBarber.value;
      if (filJenis.value) params.jenis = filJenis.value;
      if (filStatus.value) params.status = filStatus.value;
      return params;
    }, () => {
      const karyawan = filBarber.value ? (barbers.find((b) => String(b.id) === filBarber.value) || {}).nama || "Karyawan" : "Semua Karyawan";
      const jenis = filJenis.value ? labelJenis(filJenis.value) : "";
      const label = { pending: "Pending", disetujui: "Disetujui", ditolak: "Ditolak" };
      const status = label[filStatus.value] || "";
      return ["Laporan Izin Cuti", karyawan, jenis, status].filter(Boolean).join(" ") + ".pdf";
    }));

    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Pengajuan Izin & Cuti"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    async function ubahStatus(btn, id, status) {
      const catatan = prompt(status === "ditolak" ? "Alasan penolakan (opsional):" : "Catatan approval (opsional):") || "";
      try {
        // REVISI UI/UX Premium: withButtonLoading() (spinner inline di
        // tombol) menggantikan withLoading() (overlay layar penuh) untuk
        // aksi CRUD rutin -- lihat catatan di ui.js.
        await MugenUI.withButtonLoading(btn, () => MugenApi.put(`/api/izin-cuti/${id}/status`, { status, catatan_approval: catatan }));
        MugenUI.toast(`Pengajuan ${status === "disetujui" ? "disetujui" : "ditolak"}.`, "success");
        if (typeof MugenIzinNotif !== "undefined") MugenIzinNotif.refreshNow();
        loadList();
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    }

    // REVISI UI/UX Premium: refreshInto() (skeleton tabel + crossfade)
    // menggantikan pola innerHTML="Memuat..." manual -- lihat catatan di ui.js.
    async function loadList() {
      await MugenUI.refreshInto(listBody, async () => {
        const qs = new URLSearchParams();
        if (filBarber.value) qs.set("barber_id", filBarber.value);
        if (filJenis.value) qs.set("jenis", filJenis.value);
        if (filStatus.value) qs.set("status", filStatus.value);
        let rows;
        try {
          const data = await MugenApi.get(`/api/izin-cuti?${qs.toString()}`);
          rows = Array.isArray(data) ? data : [];
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
        return MugenUI.buildTable(
          [
            { key: "nama_barber", label: "Karyawan" },
            { key: "jenis", label: "Jenis", format: labelJenis },
            { key: "tanggal_mulai", label: "Mulai", format: MugenUI.formatTanggal },
            { key: "tanggal_selesai", label: "Selesai", format: MugenUI.formatTanggal },
            { key: "alasan", label: "Alasan" },
            { key: "status", label: "Status", format: badgeStatus },
            {
              key: "aksi", label: "Aksi", format: (_, r) => {
                if (r.status !== "pending") {
                  return MugenUI.el("span", { class: "subtitle" }, r.catatan_approval ? `Catatan: ${r.catatan_approval}` : "-");
                }
                const wrap = MugenUI.el("div", { class: "actions-cell" });
                const btnSetujui = MugenUI.el("button", {}, "Setujui");
                btnSetujui.addEventListener("click", () => ubahStatus(btnSetujui, r.id, "disetujui"));
                const btnTolak = MugenUI.el("button", { class: "btn-danger" }, "Tolak");
                btnTolak.addEventListener("click", () => ubahStatus(btnTolak, r.id, "ditolak"));
                wrap.appendChild(btnSetujui);
                wrap.appendChild(btnTolak);
                return wrap;
              },
            },
          ],
          rows,
          { emptyText: "Belum ada pengajuan Izin/Cuti." },
        );
      }, { skeleton: { kind: "table", cols: 6, rows: 4 } });
    }

    filBarber.addEventListener("change", loadList);
    filJenis.addEventListener("change", loadList);
    filStatus.addEventListener("change", loadList);
    loadList();
  }

  async function render(root) {
    const user = MugenState.getUser();
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Izin & Cuti"));

    if (user.role === "barber") {
      await renderBarberView(root);
    } else {
      await renderAdminView(root);
    }
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageIzinCuti begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageIzinCuti = PageIzinCuti;
