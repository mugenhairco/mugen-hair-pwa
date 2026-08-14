// pages/absensi.js — Modul BARU: Absensi (GPS Check In/Out Geofencing).
// Berdiri sendiri -- TIDAK terhubung ke Izin & Cuti/Barber Holiday sama
// sekali (keputusan eksplisit Owner). Barber: self-service Check In/Out +
// riwayat sendiri (lihat renderBarberView). Owner/Admin: Dashboard + daftar
// semua barber + Laporan (Export PDF/Excel) + Log Audit (investigasi Fake
// GPS) -- lihat renderAdminView. Perlindungan sebenarnya tetap di backend
// (routers/attendance.py) -- "Semua validasi dilakukan di backend. Frontend
// hanya menampilkan hasil validasi."

const PageAbsensi = (() => {
  const LABEL_STATUS = {
    belum_check_in: "Belum Check In", sedang_bekerja: "Sedang Bekerja",
    sudah_check_out: "Sudah Check Out", tidak_check_in: "Tidak Check In",
    tidak_check_out: "Tidak Check Out",
  };
  const LABEL_KETEPATAN = { tepat_waktu: "Tepat Waktu", terlambat: "Terlambat" };

  function badgeStatus(row) {
    const status = row.status;
    let cls = "badge";
    if (status === "sedang_bekerja") cls += " badge-success";
    else if (status === "tidak_check_in" || status === "tidak_check_out") cls += " badge-danger";
    else if (status === "belum_check_in") cls += " badge-libur";
    let label = LABEL_STATUS[status] || status || "-";
    if (status === "sedang_bekerja" && row.check_in_status) label += ` (${LABEL_KETEPATAN[row.check_in_status] || row.check_in_status})`;
    return MugenUI.el("span", { class: cls }, label);
  }

  function jamDariIso(v) {
    if (!v) return "-";
    return v.length >= 16 ? v.slice(11, 16) : v;
  }

  function durasiText(menit) {
    if (menit === null || menit === undefined) return "-";
    const jam = Math.floor(menit / 60), sisa = menit % 60;
    return `${jam}j ${sisa}m`;
  }

  // FITUR Limit Keterlambatan & Pulang Lebih Awal (120 menit/bulan,
  // masing-masing) -- sisa limit <= ambang_peringatan_menit (dari API,
  // default 40) ditampilkan ikon warning + teks merah (badge-danger,
  // konsisten dengan status "Tidak Check In/Out").
  function formatSisaLimit(menit, ambang) {
    const teks = `${menit} menit`;
    if (menit <= (ambang ?? 40)) {
      return MugenUI.el("span", { class: "badge badge-danger" }, `⚠️ ${teks}`);
    }
    return MugenUI.el("span", {}, teks);
  }

  function keteranganText(list) {
    if (!list || !list.length) return "-";
    return MugenUI.el("div", {}, list.map((teks) =>
      MugenUI.el("div", { style: teks.includes("sudah habis") ? "color:var(--danger);" : "" }, teks)));
  }

  const LABEL_JENIS_KOREKSI = { check_in: "Check In", check_out: "Check Out" };
  function badgeStatusKoreksi(status) {
    const label = status === "disetujui" ? "Disetujui" : status === "ditolak" ? "Ditolak" : "Pending";
    return MugenUI.el("span", { class: "badge" + (status === "disetujui" ? "" : status === "ditolak" ? " badge-danger" : " badge-libur") }, label);
  }

  // Geolocation Promise-based, enableHighAccuracy + maximumAge:0 (ANTI FAKE
  // GPS: selalu ambil lokasi TERBARU dari perangkat, TIDAK PERNAH menerima
  // koordinat cache) -- backend TETAP memvalidasi ulang semuanya, ini murni
  // supaya frontend mengambil sinyal GPS sebaik mungkin sebelum dikirim.
  function ambilLokasi() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("Perangkat/browser ini tidak mendukung Geolocation."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(pos.coords),
        (err) => {
          let pesan = "Gagal mengambil lokasi.";
          if (err.code === err.PERMISSION_DENIED) pesan = "Izin lokasi ditolak. Aktifkan izin lokasi untuk Check In/Check Out.";
          else if (err.code === err.POSITION_UNAVAILABLE) pesan = "Lokasi tidak tersedia. Pastikan GPS aktif.";
          else if (err.code === err.TIMEOUT) pesan = "Waktu pengambilan lokasi habis. Coba lagi.";
          reject(new Error(pesan));
        },
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
      );
    });
  }

  function infoItem(label, value) {
    return MugenUI.el("div", {}, [
      MugenUI.el("div", { class: "subtitle" }, label),
      MugenUI.el("div", { style: "font-weight:600;font-size:16px;margin-top:2px;" }, value),
    ]);
  }

  // ================= BARBER: Check In/Out + Riwayat milik sendiri =================
  async function renderBarberView(root) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Absensi Hari Ini"));
    const body = MugenUI.el("div");
    card.appendChild(body);

    async function load() {
      body.innerHTML = "";
      body.appendChild(MugenUI.skeleton("card", { lines: 4 }));
      let data;
      try {
        data = await MugenApi.get("/api/attendance/today");
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
        return;
      }
      body.innerHTML = "";
      const log = data.log, status = data.status;

      body.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:24px;margin-bottom:16px;" }, [
        infoItem("Status Hari Ini", badgeStatus({ status, check_in_status: log && log.check_in_status })),
        infoItem("Jam Check In", jamDariIso(log && log.check_in_at)),
        infoItem("Jam Check Out", jamDariIso(log && log.check_out_at)),
      ]));

      const lokasiInfo = MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
        "Lokasi Saat Ini & Jarak dari toko akan diambil otomatis saat Anda menekan tombol Check In/Check Out.");
      body.appendChild(lokasiInfo);

      if (status === "tidak_check_in") {
        body.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:10px;" },
          "Anda tidak Check In hari ini."));
      } else if (status === "tidak_check_out") {
        body.appendChild(MugenUI.el("div", { class: "login-error", style: "margin-bottom:10px;" },
          "Anda tidak Check Out hari ini."));
      }

      const errBox = MugenUI.el("div", { class: "login-error" });
      const btnCheckIn = MugenUI.el("button", { class: "btn-primary" }, "Check In");
      const btnCheckOut = MugenUI.el("button", { class: "btn-primary" }, "Check Out");
      btnCheckIn.disabled = !!(log && log.check_in_at);
      btnCheckOut.disabled = !(log && log.check_in_at) || !!(log && log.check_out_at);
      body.appendChild(errBox);
      body.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;gap:10px;" }, [btnCheckIn, btnCheckOut]));

      async function lakukanAksi(btn, endpoint, labelSukses) {
        errBox.textContent = "";
        btn.disabled = true;
        try {
          const coords = await ambilLokasi();
          await MugenUI.withButtonLoading(btn, () => MugenApi.post(endpoint, {
            latitude: coords.latitude, longitude: coords.longitude,
            accuracy: coords.accuracy, speed: coords.speed, heading: coords.heading,
          }));
          MugenUI.toast(labelSukses, "success");
          load();
        } catch (e) {
          errBox.textContent = (e.detail && e.detail.detail) ? e.detail.detail : e.message;
          btn.disabled = false;
        }
      }
      btnCheckIn.addEventListener("click", () => lakukanAksi(btnCheckIn, "/api/attendance/check-in", "Check In berhasil."));
      btnCheckOut.addEventListener("click", () => lakukanAksi(btnCheckOut, "/api/attendance/check-out", "Check Out berhasil."));
    }
    load();

    const historyCard = MugenUI.el("div", { class: "card" });
    root.appendChild(historyCard);
    historyCard.appendChild(MugenUI.el("h2", {}, "Riwayat Absensi Saya"));
    const historyBody = MugenUI.el("div");
    historyCard.appendChild(historyBody);

    async function loadHistory() {
      await MugenUI.refreshInto(historyBody, async () => {
        let rows;
        try {
          rows = await MugenApi.get("/api/attendance/history");
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
        return MugenUI.buildTable([
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "check_in_at", label: "Check In", format: jamDariIso },
          { key: "check_out_at", label: "Check Out", format: jamDariIso },
          { key: "status", label: "Status", format: (_, r) => badgeStatus(r) },
          { key: "durasi_kerja_menit", label: "Durasi Kerja", format: durasiText },
          { key: "keterangan", label: "Keterangan", format: keteranganText },
        ], rows, { emptyText: "Belum ada riwayat absensi." });
      }, { skeleton: { kind: "table", cols: 6, rows: 4 } });
    }
    loadHistory();

    // ---- Sisa Limit Keterlambatan & Pulang Lebih Awal (bulan berjalan) ----
    const limitCard = MugenUI.el("div", { class: "card" });
    root.appendChild(limitCard);
    limitCard.appendChild(MugenUI.el("h2", {}, "Sisa Limit Bulan Ini"));
    limitCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Keterlambatan & Pulang Lebih Awal masing-masing punya limit 120 menit/bulan, otomatis reset tiap tanggal 1. Limit habis TIDAK menghalangi Check In/Out, hanya tercatat di Keterangan."));
    const limitBody = MugenUI.el("div");
    limitCard.appendChild(limitBody);
    async function loadLimitSaya() {
      await MugenUI.refreshInto(limitBody, async () => {
        let r;
        try {
          r = await MugenApi.get("/api/attendance/ringkasan-bulan");
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
        return MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:24px;" }, [
          infoItem("Sisa Limit Terlambat", formatSisaLimit(r.sisa_limit_terlambat, r.ambang_peringatan_menit)),
          infoItem("Sisa Limit Pulang Lebih Awal", formatSisaLimit(r.sisa_limit_pulang_awal, r.ambang_peringatan_menit)),
        ]);
      }, { skeleton: { kind: "card", lines: 1 } });
    }
    loadLimitSaya();

    // ---- Ajukan Koreksi (lupa Check In/Check Out) ----
    const koreksiCard = MugenUI.el("div", { class: "card" });
    root.appendChild(koreksiCard);
    koreksiCard.appendChild(MugenUI.el("h2", {}, "Ajukan Koreksi Absensi"));
    koreksiCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Lupa Check In atau Check Out? Ajukan koreksi jam yang seharusnya di sini -- akan diproses (disetujui/ditolak) oleh Admin/Owner."));
    const kTanggal = MugenUI.el("input", { type: "date", value: new Date().toISOString().slice(0, 10) });
    const kJenis = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "check_in" }, "Check In"),
      MugenUI.el("option", { value: "check_out" }, "Check Out"),
    ]);
    const kJam = MugenUI.el("input", { type: "time" });
    const kAlasan = MugenUI.el("input", { type: "text", placeholder: "Wajib diisi, mis. \"Lupa check-in, HP mati\"" });
    const kBtn = MugenUI.el("button", { class: "btn-primary" }, "Ajukan Koreksi");
    const kError = MugenUI.el("div", { class: "login-error" });
    koreksiCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    koreksiCard.appendChild(kTanggal);
    koreksiCard.appendChild(MugenUI.el("label", {}, "Jenis"));
    koreksiCard.appendChild(kJenis);
    koreksiCard.appendChild(MugenUI.el("label", {}, "Jam yang Seharusnya"));
    koreksiCard.appendChild(kJam);
    koreksiCard.appendChild(MugenUI.el("label", {}, "Alasan"));
    koreksiCard.appendChild(kAlasan);
    koreksiCard.appendChild(kError);
    koreksiCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-top:12px;" }, [kBtn]));

    const koreksiListBody = MugenUI.el("div");
    koreksiCard.appendChild(MugenUI.el("h2", { style: "margin-top:24px;" }, "Riwayat Koreksi Saya"));
    koreksiCard.appendChild(koreksiListBody);

    async function loadKoreksiSaya() {
      await MugenUI.refreshInto(koreksiListBody, async () => {
        let rows;
        try {
          rows = await MugenApi.get("/api/attendance/koreksi");
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
        return MugenUI.buildTable([
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "jenis", label: "Jenis", format: (v) => LABEL_JENIS_KOREKSI[v] || v },
          { key: "waktu_diajukan", label: "Jam Diajukan" },
          { key: "alasan", label: "Alasan" },
          { key: "status", label: "Status", format: (v) => badgeStatusKoreksi(v) },
          { key: "catatan_approval", label: "Catatan Admin/Owner", format: (v) => v || "-" },
          {
            key: "aksi", label: "Aksi", format: (_, r) => {
              if (r.status !== "pending") return MugenUI.el("span", { class: "subtitle" }, "-");
              const btnHapus = MugenUI.el("button", { class: "btn-danger" }, "Batalkan");
              btnHapus.addEventListener("click", async () => {
                if (!confirm(`Batalkan pengajuan koreksi ${LABEL_JENIS_KOREKSI[r.jenis] || r.jenis} tanggal ${r.tanggal}?`)) return;
                try {
                  await MugenUI.withButtonLoading(btnHapus, () => MugenApi.del(`/api/attendance/koreksi/${r.id}`));
                  MugenUI.toast("Pengajuan koreksi dibatalkan.", "success");
                  loadKoreksiSaya();
                } catch (e) {
                  MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
                }
              });
              return btnHapus;
            },
          },
        ], rows, { emptyText: "Belum ada pengajuan koreksi." });
      }, { skeleton: { kind: "table", cols: 7, rows: 3 } });
    }
    loadKoreksiSaya();

    kBtn.addEventListener("click", async () => {
      kError.textContent = "";
      if (!kJam.value) { kError.textContent = "Jam yang seharusnya wajib diisi."; return; }
      if (!kAlasan.value.trim()) { kError.textContent = "Alasan wajib diisi."; return; }
      try {
        await MugenUI.withButtonLoading(kBtn, () => MugenApi.post("/api/attendance/koreksi", {
          tanggal: kTanggal.value, jenis: kJenis.value, waktu_diajukan: kJam.value, alasan: kAlasan.value.trim(),
        }));
        MugenUI.toast("Pengajuan koreksi berhasil dikirim.", "success");
        kJam.value = ""; kAlasan.value = "";
        loadKoreksiSaya();
      } catch (e) {
        kError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });
  }

  // ================= OWNER/ADMIN: Dashboard + Daftar + Laporan + Audit =================
  async function renderAdminView(root) {
    let barbers = [];
    try {
      barbers = await MugenApi.get("/api/input-data/karyawan", { useCache: true });
    } catch (e) { /* opsional */ }

    // ---- Dashboard ringkasan ----
    const dashCard = MugenUI.el("div", { class: "card" });
    root.appendChild(dashCard);
    dashCard.appendChild(MugenUI.el("h2", {}, "Dashboard Absensi Hari Ini"));
    const dashGrid = MugenUI.el("div", { class: "grid-cards" });
    dashCard.appendChild(dashGrid);

    async function loadDashboard() {
      dashGrid.innerHTML = "";
      dashGrid.appendChild(MugenUI.skeleton("card", { lines: 1 }));
      let ringkasan;
      try {
        ringkasan = await MugenApi.get("/api/attendance/dashboard");
      } catch (e) {
        dashGrid.innerHTML = "";
        dashGrid.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
        return;
      }
      dashGrid.innerHTML = "";
      const KARTU = [
        ["total_barber", "Total Barber"], ["hadir", "Hadir"], ["belum_hadir", "Belum Hadir"],
        ["terlambat", "Terlambat"], ["sedang_bekerja", "Sedang Bekerja"], ["sudah_check_out", "Sudah Check Out"],
        ["tidak_check_in", "Tidak Check In"], ["tidak_check_out", "Tidak Check Out"],
      ];
      for (const [key, label] of KARTU) {
        dashGrid.appendChild(MugenUI.el("div", { class: "card" }, [
          MugenUI.el("h2", {}, label),
          MugenUI.el("div", { class: "big-number" }, String(ringkasan[key] ?? 0)),
        ]));
      }
    }
    loadDashboard();

    // ---- Sisa Limit Keterlambatan & Pulang Lebih Awal (bulan berjalan) ----
    const limitCard = MugenUI.el("div", { class: "card" });
    root.appendChild(limitCard);
    limitCard.appendChild(MugenUI.el("h2", {}, "Sisa Limit Bulan Ini"));
    limitCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Keterlambatan & Pulang Lebih Awal masing-masing punya limit 120 menit/bulan per barber, otomatis reset tiap tanggal 1. Limit habis TIDAK menghalangi Check In/Out, hanya tercatat di Keterangan."));
    const limitBody = MugenUI.el("div");
    limitCard.appendChild(limitBody);
    async function loadLimit() {
      await MugenUI.refreshInto(limitBody, async () => {
        let rows;
        try {
          rows = await MugenApi.get("/api/attendance/ringkasan-bulan");
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
        return MugenUI.buildTable([
          { key: "nama_barber", label: "Barber" },
          { key: "sisa_limit_terlambat", label: "Sisa Limit Terlambat", format: (v, r) => formatSisaLimit(v, r.ambang_peringatan_menit) },
          { key: "sisa_limit_pulang_awal", label: "Sisa Limit Pulang Lebih Awal", format: (v, r) => formatSisaLimit(v, r.ambang_peringatan_menit) },
        ], rows, { emptyText: "Belum ada barber aktif." });
      }, { skeleton: { kind: "table", cols: 3, rows: 3 } });
    }
    loadLimit();

    // ---- Filter & Daftar Absensi ----
    const filterCard = MugenUI.el("div", { class: "card" });
    const listCard = MugenUI.el("div", { class: "card" });
    root.appendChild(filterCard);
    root.appendChild(listCard);

    filterCard.appendChild(MugenUI.el("h2", {}, "Filter"));
    const filBarber = MugenUI.el("select");
    filBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
    for (const b of barbers) filBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const filStatus = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "" }, "Semua Status"),
      MugenUI.el("option", { value: "belum_check_in" }, "Belum Check In"),
      MugenUI.el("option", { value: "sedang_bekerja" }, "Sedang Bekerja"),
      MugenUI.el("option", { value: "sudah_check_out" }, "Sudah Check Out"),
      MugenUI.el("option", { value: "tidak_check_in" }, "Tidak Check In"),
      MugenUI.el("option", { value: "tidak_check_out" }, "Tidak Check Out"),
    ]);
    const filPeriode = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "hari" }, "Hari Ini"),
      MugenUI.el("option", { value: "minggu" }, "Minggu Ini"),
      MugenUI.el("option", { value: "bulan" }, "Bulan Ini"),
      MugenUI.el("option", { value: "rentang" }, "Rentang Tanggal"),
    ]);
    const today = new Date().toISOString().slice(0, 10);
    const inputDari = MugenUI.el("input", { type: "date", value: today, style: "display:none;" });
    const inputSampai = MugenUI.el("input", { type: "date", value: today, style: "display:none;" });
    filterCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;flex:none;gap:10px;" },
      [filBarber, filStatus, filPeriode, inputDari, inputSampai]));

    function rentangPeriode() {
      const d = new Date();
      if (filPeriode.value === "hari") return { tanggal: today };
      if (filPeriode.value === "minggu") {
        const mulai = new Date(d); mulai.setDate(d.getDate() - 6);
        return { tanggal_dari: mulai.toISOString().slice(0, 10), tanggal_sampai: today };
      }
      if (filPeriode.value === "bulan") {
        const mulai = new Date(d.getFullYear(), d.getMonth(), 1);
        return { tanggal_dari: mulai.toISOString().slice(0, 10), tanggal_sampai: today };
      }
      return { tanggal_dari: inputDari.value, tanggal_sampai: inputSampai.value };
    }

    filPeriode.addEventListener("change", () => {
      const rentang = filPeriode.value === "rentang";
      inputDari.style.display = rentang ? "" : "none";
      inputSampai.style.display = rentang ? "" : "none";
      loadList();
    });

    function paramsAktif() {
      const params = { ...rentangPeriode() };
      if (filBarber.value) params.barber_id = filBarber.value;
      if (filStatus.value) params.status = filStatus.value;
      return params;
    }

    // Feature Gating "export_pdf": lihat catatan sama di pages/rekap.js --
    // Export Excel memakai gate yang SAMA (lihat routers/attendance.py).
    function tombolExport() {
      const wrap = MugenUI.el("div", { class: "row", style: "flex:none;gap:10px;margin-top:10px;" });
      if (typeof MugenFeature !== "undefined" && !MugenFeature.has("export_pdf")) {
        wrap.appendChild(MugenFeature.upgradeBlock("Export PDF/Excel"));
        return wrap;
      }
      const btnPdf = MugenUI.el("button", {}, "Cetak PDF");
      btnPdf.addEventListener("click", () => {
        const qs = new URLSearchParams(paramsAktif());
        MugenPdfPreview.open({
          generate: () => MugenApi.fetchBlob(`/api/attendance/pdf?${qs}`),
          filename: MugenUI.namaFileAman("Laporan Absensi.pdf"),
        });
      });
      const btnExcel = MugenUI.el("button", {}, "Export Excel");
      btnExcel.addEventListener("click", async () => {
        try {
          const qs = new URLSearchParams(paramsAktif());
          const blob = await MugenUI.withButtonLoading(btnExcel, () => MugenApi.fetchBlob(`/api/attendance/excel?${qs}`));
          MugenApi.saveBlob(blob, MugenUI.namaFileAman("Laporan Absensi.xlsx"));
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
      wrap.appendChild(btnPdf);
      wrap.appendChild(btnExcel);
      return wrap;
    }
    filterCard.appendChild(tombolExport());

    listCard.appendChild(MugenUI.el("h2", {}, "Daftar Absensi"));
    const listBody = MugenUI.el("div");
    listCard.appendChild(listBody);

    function bukaDetail(r) {
      const baris = (label, value) => MugenUI.el("div", { style: "display:flex;justify-content:space-between;gap:16px;padding:6px 0;border-bottom:1px solid var(--border);" }, [
        MugenUI.el("span", { class: "subtitle" }, label), MugenUI.el("span", {}, value ?? "-"),
      ]);
      const body2 = MugenUI.el("div", {}, [
        baris("Barber", r.nama_barber),
        baris("Tanggal", r.tanggal),
        baris("Jam Check In", jamDariIso(r.check_in_at)),
        baris("Jam Check Out", jamDariIso(r.check_out_at)),
        baris("Durasi Kerja", durasiText(r.durasi_kerja_menit)),
        baris("Latitude Check In", r.check_in_latitude),
        baris("Longitude Check In", r.check_in_longitude),
        baris("Akurasi GPS Check In", r.check_in_accuracy != null ? `${Math.round(r.check_in_accuracy)} meter` : "-"),
        baris("Jarak dari Toko (Check In)", r.check_in_jarak_meter != null ? `${Math.round(r.check_in_jarak_meter)} meter` : "-"),
        baris("Latitude Check Out", r.check_out_latitude),
        baris("Longitude Check Out", r.check_out_longitude),
        baris("Jarak dari Toko (Check Out)", r.check_out_jarak_meter != null ? `${Math.round(r.check_out_jarak_meter)} meter` : "-"),
        baris("Browser", r.check_in_browser),
        baris("Device", r.check_in_device),
        baris("IP Address", r.check_in_ip),
      ]);
      MugenUI.infoModal({ title: `Detail Absensi -- ${r.nama_barber}`, body: body2 });
    }

    async function loadList() {
      await MugenUI.refreshInto(listBody, async () => {
        const qs = new URLSearchParams(paramsAktif());
        let rows;
        try {
          rows = await MugenApi.get(`/api/attendance?${qs.toString()}`);
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
        return MugenUI.buildTable([
          { key: "nama_barber", label: "Nama" },
          { key: "check_in_at", label: "Check In", format: jamDariIso },
          { key: "check_out_at", label: "Check Out", format: jamDariIso },
          { key: "status", label: "Status", format: (_, r) => badgeStatus(r) },
          { key: "durasi_kerja_menit", label: "Durasi Kerja", format: durasiText },
          { key: "keterangan", label: "Keterangan", format: keteranganText },
          {
            key: "aksi", label: "Detail", format: (_, r) => {
              if (!r.id) return MugenUI.el("span", { class: "subtitle" }, "-");
              const btn = MugenUI.el("button", {}, "Lihat Detail");
              btn.addEventListener("click", () => bukaDetail(r));
              return btn;
            },
          },
        ], rows, { emptyText: "Belum ada data absensi pada periode ini." });
      }, { skeleton: { kind: "table", cols: 7, rows: 4 } });
    }
    filBarber.addEventListener("change", loadList);
    filStatus.addEventListener("change", loadList);
    inputDari.addEventListener("change", loadList);
    inputSampai.addEventListener("change", loadList);
    loadList();

    // ---- Pengajuan Koreksi Absensi (barber lupa Check In/Check Out) ----
    const koreksiCard = MugenUI.el("div", { class: "card" });
    root.appendChild(koreksiCard);
    koreksiCard.appendChild(MugenUI.el("h2", {}, "Pengajuan Koreksi Absensi"));
    koreksiCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Koreksi diajukan barber saat lupa Check In/Check Out -- Setujui untuk menerapkan jam yang diajukan ke data Absensi, atau Tolak."));
    const kFilStatus = MugenUI.el("select", {}, [
      MugenUI.el("option", { value: "pending" }, "Pending"),
      MugenUI.el("option", { value: "" }, "Semua Status"),
      MugenUI.el("option", { value: "disetujui" }, "Disetujui"),
      MugenUI.el("option", { value: "ditolak" }, "Ditolak"),
    ]);
    koreksiCard.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:10px;" }, [kFilStatus]));
    const koreksiListBody = MugenUI.el("div");
    koreksiCard.appendChild(koreksiListBody);

    async function ubahStatusKoreksi(btn, id, status) {
      const catatan = prompt(status === "ditolak" ? "Alasan penolakan (opsional):" : "Catatan approval (opsional):") || "";
      try {
        await MugenUI.withButtonLoading(btn, () => MugenApi.put(`/api/attendance/koreksi/${id}/status`, { status, catatan_approval: catatan }));
        MugenUI.toast(`Koreksi ${status === "disetujui" ? "disetujui" : "ditolak"}.`, "success");
        loadKoreksi();
        loadList();
        loadLimit();
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    }

    async function loadKoreksi() {
      await MugenUI.refreshInto(koreksiListBody, async () => {
        const qs = new URLSearchParams();
        if (kFilStatus.value) qs.set("status", kFilStatus.value);
        let rows;
        try {
          rows = await MugenApi.get(`/api/attendance/koreksi?${qs.toString()}`);
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
        return MugenUI.buildTable([
          { key: "nama_barber", label: "Barber" },
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "jenis", label: "Jenis", format: (v) => LABEL_JENIS_KOREKSI[v] || v },
          { key: "waktu_diajukan", label: "Jam Diajukan" },
          { key: "alasan", label: "Alasan" },
          { key: "status", label: "Status", format: badgeStatusKoreksi },
          {
            key: "aksi", label: "Aksi", format: (_, r) => {
              if (r.status !== "pending") {
                return MugenUI.el("span", { class: "subtitle" }, r.catatan_approval ? `Catatan: ${r.catatan_approval}` : "-");
              }
              const wrap = MugenUI.el("div", { class: "actions-cell" });
              const btnSetujui = MugenUI.el("button", {}, "Setujui");
              btnSetujui.addEventListener("click", () => ubahStatusKoreksi(btnSetujui, r.id, "disetujui"));
              const btnTolak = MugenUI.el("button", { class: "btn-danger" }, "Tolak");
              btnTolak.addEventListener("click", () => ubahStatusKoreksi(btnTolak, r.id, "ditolak"));
              wrap.appendChild(btnSetujui);
              wrap.appendChild(btnTolak);
              return wrap;
            },
          },
        ], rows, { emptyText: "Belum ada pengajuan koreksi." });
      }, { skeleton: { kind: "table", cols: 7, rows: 3 } });
    }
    kFilStatus.addEventListener("change", loadKoreksi);
    loadKoreksi();

    // ---- Log Audit (investigasi Fake GPS/Mock Location) ----
    const auditCard = MugenUI.el("div", { class: "card" });
    root.appendChild(auditCard);
    auditCard.appendChild(MugenUI.el("h2", {}, "Log Audit Percobaan Check In/Out"));
    auditCard.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Rekam SEMUA percobaan Check In/Check Out (berhasil maupun gagal) untuk investigasi -- termasuk alasan penolakan, akurasi GPS, browser, device, dan IP Address."));
    const auditBody = MugenUI.el("div");
    auditCard.appendChild(auditBody);

    async function loadAudit() {
      await MugenUI.refreshInto(auditBody, async () => {
        let rows;
        try {
          rows = await MugenApi.get("/api/attendance/audit");
        } catch (e) {
          return MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message);
        }
        return MugenUI.buildTable([
          { key: "waktu_server", label: "Waktu Server" },
          { key: "nama_barber", label: "Barber" },
          { key: "aksi", label: "Aksi", format: (v) => (v === "check_in" ? "Check In" : "Check Out") },
          { key: "sukses", label: "Hasil", format: (v) => MugenUI.el("span", { class: "badge " + (v ? "badge-success" : "badge-danger") }, v ? "Berhasil" : "Gagal") },
          { key: "alasan_gagal", label: "Alasan Gagal", format: (v) => v || "-" },
          { key: "accuracy", label: "Akurasi GPS", format: (v) => (v != null ? `${Math.round(v)} m` : "-") },
          { key: "browser", label: "Browser" },
          { key: "device", label: "Device" },
          { key: "ip_address", label: "IP Address" },
        ], rows, { emptyText: "Belum ada percobaan Check In/Out." });
      }, { skeleton: { kind: "table", cols: 9, rows: 4 } });
    }
    loadAudit();
  }

  async function render(root) {
    const user = MugenState.getUser();
    root.innerHTML = "";
    root.appendChild(MugenUI.el("h1", {}, "Absensi"));

    if (user.role === "barber") {
      await renderBarberView(root);
    } else {
      await renderAdminView(root);
    }
  }

  return { render };
})();
