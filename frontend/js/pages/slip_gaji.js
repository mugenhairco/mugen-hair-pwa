// pages/slip_gaji.js — Modul Karyawan (Fase 1): Slip Gaji Otomatis.
// Satu halaman, dua sudut pandang (pola yang sama seperti pages/rekap.js):
// - Owner ('admin') selalu penuh; 'staff' (Admin) HANYA kalau diberi izin
//   izin_slip_gaji (Setting > Hak Akses Admin) -- lihat renderAdminView().
//   Backend (routers/slip_gaji.py) yang benar-benar menegakkan ini, frontend
//   di sini hanya menampilkan pesan error kalau ditolak server.
// - 'barber': hanya melihat riwayat Slip Gaji miliknya sendiri, read-only
//   (tidak ada tombol Generate/Status/Hapus) -- lihat renderBarberView().
//
// Slip Gaji = Gaji Pokok + Komisi + Tips + Uang Harian + Bonus Customer
// (SEMUA dihitung backend dari data yang sudah ada, TIDAK dihitung ulang di
// sini) dikurangi Potongan Kasbon + Potongan Lain (manual, diisi Owner/Admin
// saat generate). Satu slip per barber per bulan -- generate ulang sebelum
// berstatus Sudah Dibayar akan menghitung ulang komponen income-nya.

const PageSlipGaji = (() => {
  async function unduhPdf(id, namaBarber, tahun, bulan) {
    try {
      await MugenUI.withLoading(async () => {
        const token = MugenState.getToken();
        const res = await fetch(`${MUGEN_API_BASE}/api/slip-gaji/${id}/pdf`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
          let pesan = "Gagal mengunduh Slip Gaji.";
          try { pesan = (await res.json()).detail || pesan; } catch (e) { /* body bukan JSON */ }
          throw new Error(pesan);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `slip_gaji_${namaBarber}_${tahun}-${String(bulan).padStart(2, "0")}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }, { message: "Menyiapkan PDF…" });
    } catch (e) {
      MugenUI.toast(e.message, "error");
    }
  }

  async function loadListInto(listBody, params, isAdmin, onBerubah) {
    listBody.innerHTML = "Memuat...";
    try {
      const qs = new URLSearchParams(params);
      const data = await MugenApi.get(`/api/slip-gaji?${qs.toString()}`);
      listBody.innerHTML = "";
      const rows = Array.isArray(data) ? data : [];

      const kolom = [
        { key: "periode", label: "Periode", format: (_, r) => `${MugenUI.namaBulan(r.bulan)} ${r.tahun}` },
      ];
      if (isAdmin) kolom.push({ key: "nama_barber", label: "Barber" });
      kolom.push(
        { key: "total_diterima", label: "Total Diterima", format: MugenUI.formatRupiah },
        {
          key: "status", label: "Status",
          format: (v) => MugenUI.el("span", { class: "badge" + (v === "sudah_dibayar" ? "" : " badge-libur") },
            v === "sudah_dibayar" ? "Sudah Dibayar" : "Belum Dibayar"),
        },
        {
          key: "aksi", label: "Aksi", format: (_, r) => {
            const wrap = MugenUI.el("div", { class: "actions-cell" });
            const btnPdf = MugenUI.el("button", {}, "Unduh PDF");
            btnPdf.addEventListener("click", () => unduhPdf(r.id, r.nama_barber, r.tahun, r.bulan));
            wrap.appendChild(btnPdf);

            if (isAdmin) {
              const btnStatus = MugenUI.el("button", {},
                r.status === "sudah_dibayar" ? "Batalkan Status" : "Tandai Sudah Dibayar");
              btnStatus.addEventListener("click", async () => {
                const statusBaru = r.status === "sudah_dibayar" ? "belum_dibayar" : "sudah_dibayar";
                try {
                  await MugenUI.withLoading(() => MugenApi.put(`/api/slip-gaji/${r.id}/status`, { status: statusBaru }),
                    { message: "Menyimpan…" });
                  MugenUI.toast("Status Slip Gaji diperbarui.", "success");
                  onBerubah();
                } catch (e) {
                  MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                }
              });
              wrap.appendChild(btnStatus);

              if (r.status !== "sudah_dibayar") {
                const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Hapus");
                btnHapus.addEventListener("click", async () => {
                  if (!confirm(`Hapus Slip Gaji ${r.nama_barber} periode ${MugenUI.namaBulan(r.bulan)} ${r.tahun}?`)) return;
                  try {
                    await MugenUI.withLoading(() => MugenApi.del(`/api/slip-gaji/${r.id}`), { message: "Menghapus…" });
                    MugenUI.toast("Slip Gaji dihapus.", "success");
                    onBerubah();
                  } catch (e) {
                    MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                  }
                });
                wrap.appendChild(btnHapus);
              }
            }
            return wrap;
          },
        },
      );

      listBody.appendChild(MugenUI.buildTable(kolom, rows, { emptyText: "Belum ada Slip Gaji." }));
    } catch (e) {
      listBody.innerHTML = "";
      listBody.appendChild(MugenUI.el("div", {}, e.detail && e.detail.detail ? e.detail.detail : e.message));
    }
  }

  // ================= BARBER: riwayat milik sendiri, read-only =================
  async function renderBarberView(root) {
    root.appendChild(MugenUI.el("div", { class: "subtitle" }, "Riwayat Slip Gaji Anda."));
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(listCard);
    listCard.appendChild(MugenUI.el("h2", {}, "Riwayat"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);
    const muat = () => loadListInto(listBody, {}, false, muat);
    muat();
  }

  // ================= OWNER/ADMIN: generate + kelola semua barber =================
  async function renderAdminView(root) {
    const today = new Date();
    let barbers = [];
    try {
      barbers = await MugenApi.get("/api/input-data/barbers", { useCache: true });
    } catch (e) { /* opsional -- form Generate tetap tampil, dropdown Barber cuma kosong */ }

    const formCard = MugenUI.el("div", { class: "card" });
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(formCard);
    root.appendChild(filterCard);
    root.appendChild(listCard);

    // ---- Form Generate ----
    formCard.appendChild(MugenUI.el("h2", {}, "Generate Slip Gaji"));
    formCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Komisi/Tips/Uang Harian/Bonus Customer dihitung otomatis dari data yang sudah ada. Generate ulang sebelum " +
      "berstatus Sudah Dibayar akan menghitung ulang komponen ini (potongan tetap sesuai yang diisi terakhir)."));

    const selBarber = MugenUI.el("select");
    for (const b of barbers) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(today.getMonth() + 1);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(today.getFullYear());
    const inputGajiPokok = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputPotonganKasbon = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputPenyesuaianKomisi = MugenUI.el("input", { type: "number", value: "0" }); // boleh negatif -- tanpa atribut min
    const inputPotonganLain = MugenUI.el("input", { type: "number", min: "0", value: "0" });
    const inputCatatanPotongan = MugenUI.el("input", { type: "text", placeholder: "Opsional, mis. keterlambatan" });
    const btnGenerate = MugenUI.el("button", { class: "btn-primary" }, "Generate Slip Gaji");
    const formError = MugenUI.el("div", { class: "login-error" });

    // Belum ada tab tersendiri untuk atur Gaji Pokok per-barber (lihat
    // slip_gaji_db.py) -- form ini SEKALIAN jadi tempatnya, otomatis
    // terisi nilai yang tersimpan saat ini begitu Barber dipilih, dan
    // otomatis "nempel" (tersimpan permanen ke data barber) begitu di-Generate.
    function isiGajiPokokDariBarber() {
      const b = barbers.find((x) => String(x.id) === selBarber.value);
      inputGajiPokok.value = String((b && b.gaji_pokok) || 0);
    }
    // Modul Karyawan Fase 2 (Kasbon): Potongan Kasbon otomatis terisi dari
    // saldo kasbon belum lunas barber yang dipilih (GET /api/kasbon/saldo/
    // {barber_id}), TAPI tetap bebas diedit manual sebelum Generate -- nilai
    // ini HANYA saran awal, tidak disimpan ke mana pun sampai slip benar-
    // benar ditandai Sudah Dibayar (lihat slip_gaji_db.tandai_status()).
    async function isiPotonganKasbonDariBarber() {
      if (!selBarber.value) { inputPotonganKasbon.value = "0"; return; }
      try {
        const saldo = await MugenApi.get(`/api/kasbon/saldo/${selBarber.value}`);
        inputPotonganKasbon.value = String(saldo.saldo || 0);
      } catch (e) { /* opsional -- kalau gagal (mis. tidak ada izin), biarkan manual */ }
    }
    // Modul Karyawan Fase 3 (Komisi): Penyesuaian Komisi otomatis terisi dari
    // net bonus-potongan barber+PERIODE yang dipilih (GET /api/komisi/saldo/
    // {barber_id}?tahun=&bulan=) -- BEDA dari Potongan Kasbon yang cuma
    // bereaksi ke Barber (saldo berjalan, bukan per-periode), field ini
    // reaktif ke Barber DAN Bulan/Tahun sekaligus. Tetap bebas diedit manual
    // sebelum Generate, nilai ini HANYA saran awal.
    async function isiPenyesuaianKomisiDariPeriode() {
      if (!selBarber.value) { inputPenyesuaianKomisi.value = "0"; return; }
      try {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        const saldo = await MugenApi.get(`/api/komisi/saldo/${selBarber.value}?${qs.toString()}`);
        inputPenyesuaianKomisi.value = String(saldo.saldo || 0);
      } catch (e) { /* opsional -- kalau gagal (mis. tidak ada izin), biarkan manual */ }
    }
    selBarber.addEventListener("change", () => {
      isiGajiPokokDariBarber();
      isiPotonganKasbonDariBarber();
      isiPenyesuaianKomisiDariPeriode();
    });
    selBulan.addEventListener("change", isiPenyesuaianKomisiDariPeriode);
    selTahun.addEventListener("change", isiPenyesuaianKomisiDariPeriode);
    isiGajiPokokDariBarber();
    isiPotonganKasbonDariBarber();
    isiPenyesuaianKomisiDariPeriode();

    formCard.appendChild(MugenUI.el("label", {}, "Barber"));
    formCard.appendChild(selBarber);
    formCard.appendChild(MugenUI.el("label", {}, "Bulan"));
    formCard.appendChild(selBulan);
    formCard.appendChild(MugenUI.el("label", {}, "Tahun"));
    formCard.appendChild(selTahun);
    formCard.appendChild(MugenUI.el("label", {}, "Gaji Pokok (Rp, opsional)"));
    formCard.appendChild(inputGajiPokok);
    formCard.appendChild(MugenUI.el("label", {}, "Potongan Kasbon (Rp, opsional)"));
    formCard.appendChild(inputPotonganKasbon);
    formCard.appendChild(MugenUI.el("label", {}, "Penyesuaian Komisi (Rp, boleh negatif, opsional)"));
    formCard.appendChild(inputPenyesuaianKomisi);
    formCard.appendChild(MugenUI.el("label", {}, "Potongan Lain (Rp, opsional)"));
    formCard.appendChild(inputPotonganLain);
    formCard.appendChild(MugenUI.el("label", {}, "Catatan Potongan (opsional)"));
    formCard.appendChild(inputCatatanPotongan);
    formCard.appendChild(formError);
    formCard.appendChild(MugenUI.el("div", { style: "margin-top:12px;" }, btnGenerate));

    btnGenerate.addEventListener("click", async () => {
      formError.textContent = "";
      if (!selBarber.value) { formError.textContent = "Pilih barber dulu."; return; }
      btnGenerate.disabled = true;
      try {
        await MugenUI.withLoading(() => MugenApi.post("/api/slip-gaji", {
          barber_id: Number(selBarber.value), tahun: Number(selTahun.value), bulan: Number(selBulan.value),
          gaji_pokok: Number(inputGajiPokok.value) || 0,
          potongan_kasbon: Number(inputPotonganKasbon.value) || 0, potongan_lain: Number(inputPotonganLain.value) || 0,
          penyesuaian_komisi: Number(inputPenyesuaianKomisi.value) || 0,
          catatan_potongan: inputCatatanPotongan.value.trim(),
        }), { message: "Menghitung Slip Gaji…" });
        // Sinkronkan cache lokal supaya kalau barber yang sama dipilih lagi
        // tanpa reload halaman, Gaji Pokok yang tampil sudah yang terbaru.
        const b = barbers.find((x) => String(x.id) === selBarber.value);
        if (b) b.gaji_pokok = Number(inputGajiPokok.value) || 0;
        MugenUI.toast("Slip Gaji berhasil dibuat.", "success");
        loadList();
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      } finally {
        btnGenerate.disabled = false;
      }
    });

    // ---- Filter ----
    filterCard.appendChild(MugenUI.el("h2", {}, "Filter"));
    const filBarber = MugenUI.el("select");
    filBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
    for (const b of barbers) filBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const filBulan = MugenUI.el("select");
    filBulan.appendChild(MugenUI.el("option", { value: "" }, "Semua Bulan"));
    for (let m = 1; m <= 12; m++) filBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    const filTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) filTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    filTahun.value = String(today.getFullYear());
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [filBarber, filBulan, filTahun]));

    // ---- Daftar ----
    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Slip Gaji"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    function loadList() {
      const params = { tahun: filTahun.value };
      if (filBulan.value) params.bulan = filBulan.value;
      if (filBarber.value) params.barber_id = filBarber.value;
      loadListInto(listBody, params, true, loadList);
    }

    filBarber.addEventListener("change", loadList);
    filBulan.addEventListener("change", loadList);
    filTahun.addEventListener("change", loadList);

    loadList();
  }

  async function render(root) {
    const user = MugenState.getUser();
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Slip Gaji"));

    if (user.role === "barber") {
      await renderBarberView(root);
    } else {
      await renderAdminView(root);
    }
  }

  return { render };
})();
