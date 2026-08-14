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

  // Ilustrasi status hari ini (REVISI UI/UX Absensi Barber, feedback
  // Owner) -- SVG line-icon dibuat manual (TANPA aset gambar/library
  // eksternal, codebase ini memang sengaja tidak punya aset ikon sama
  // sekali, lihat nav.js) supaya PWA tetap ringan & bisa dipakai offline.
  // "sedang_bekerja" dapat cincin berdenyut (.mugen-pulse-ring, style.css)
  // supaya terasa "hidup"/real-time, status lain statis.
  const _ICON_SVG = {
    belum_check_in: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg>',
    sedang_bekerja: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M7 12h2.5l1.5-4 3 8 1.5-4H17"/></svg>',
    sudah_check_out: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>',
    tidak: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4.5l9 15.5H3z"/><path d="M12 10v4"/><circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none"/></svg>',
  };

  // Baris tabel fade-in bertahap (stagger) saat pertama dimuat -- REVISI
  // UI/UX Absensi Barber (feedback Owner), HANYA dipakai Riwayat Absensi
  // Saya (bukan diterapkan ke buildTable() secara global, supaya tabel
  // lain di aplikasi TIDAK ikut berubah). Delay dibatasi maksimal 8 baris
  // pertama (40ms/baris) supaya tabel panjang tidak terasa lambat.
  function beriAnimasiBaris(tableWrap) {
    tableWrap.querySelectorAll("tbody tr").forEach((tr, i) => {
      tr.classList.add("mugen-row-in");
      tr.style.animationDelay = `${Math.min(i, 8) * 40}ms`;
    });
    return tableWrap;
  }

  function statusIlustrasi(status) {
    const isTidak = status === "tidak_check_in" || status === "tidak_check_out";
    const svgKey = isTidak ? "tidak" : (_ICON_SVG[status] ? status : "belum_check_in");
    const tone = status === "sedang_bekerja" || status === "sudah_check_out" ? "tone-success" : isTidak ? "tone-danger" : "";
    const wrap = MugenUI.el("div", { class: `mugen-status-illus ${tone}`.trim(), html: _ICON_SVG[svgKey] });
    if (status === "sedang_bekerja") wrap.appendChild(MugenUI.el("div", { class: "mugen-pulse-ring" }));
    return wrap;
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

  // Keterangan yang terjadi SAAT limit bulanan sudah habis (teks dari
  // backend memuat suffix "... sudah habis", lihat hitung_ringkasan_bulan())
  // ditandai ikon warning + teks merah -- konsisten dengan formatSisaLimit().
  function keteranganText(list) {
    if (!list || !list.length) return "-";
    return MugenUI.el("div", {}, list.map((teks) => {
      const habis = teks.includes("sudah habis");
      return MugenUI.el("div", {
        class: habis ? "mugen-keterangan-alert" : "", style: habis ? "color:var(--danger);" : "",
      }, habis ? `⚠️ ${teks}` : teks);
    }));
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

  // Diagram lingkaran (progress ring) Sisa Limit -- REVISI UI/UX Absensi
  // Barber (feedback Owner), HANYA dipakai kartu "Sisa Limit Bulan Ini"
  // milik Barber sendiri (tabel Sisa Limit di sisi Owner/Admin, semua
  // barber sekaligus, TETAP format tabel biasa -- ring per-baris di tabel
  // besar tidak praktis). Ring menunjukkan sisa (bukan terpakai) supaya
  // penuh = anggaran masih utuh, mengosong = anggaran menipis/habis --
  // warna ikut ambang peringatan yang SAMA dengan formatSisaLimit().
  function ringLimit(judul, sisa, batas, ambang) {
    const pct = batas > 0 ? (sisa / batas) * 100 : 0;
    const habis = sisa <= (ambang ?? 40);
    const ring = MugenUI.progressRing(pct, { warna: habis ? "var(--danger)" : "var(--accent)", value: sisa, unit: "menit", ukuran: 108, tebal: 11 });
    return MugenUI.el("div", { style: "display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center;" }, [
      MugenUI.el("div", { class: "subtitle" }, judul),
      ring,
      habis ? MugenUI.el("div", { class: "badge badge-danger" }, "⚠️ Hampir/Sudah Habis") : null,
    ].filter(Boolean));
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

      body.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:24px;margin-bottom:16px;align-items:center;" }, [
        statusIlustrasi(status),
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

      const btnCheckIn = MugenUI.el("button", { class: "btn-primary" }, "Check In");
      const btnCheckOut = MugenUI.el("button", { class: "btn-primary" }, "Check Out");
      btnCheckIn.disabled = !!(log && log.check_in_at);
      btnCheckOut.disabled = !(log && log.check_in_at) || !!(log && log.check_out_at);
      body.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;gap:10px;" }, [btnCheckIn, btnCheckOut]));

      // REVISI UI/UX Absensi Barber (feedback Owner): modal konfirmasi
      // (box tengah layar, MugenUI.confirmModal() -- SUDAH ADA & dipakai
      // di banyak halaman lain, bukan komponen baru) SEBELUM lokasi
      // GPS diminta/dikirim, DAN modal (bukan lagi teks kecil merah)
      // untuk error apa pun (izin lokasi ditolak, validasi backend, dst).
      async function lakukanAksi(btn, endpoint, labelSukses, konfirmasi) {
        const ok = await MugenUI.confirmModal(konfirmasi);
        if (!ok) return;
        try {
          await MugenUI.withButtonLoading(btn, async () => {
            const coords = await ambilLokasi();
            await MugenApi.post(endpoint, {
              latitude: coords.latitude, longitude: coords.longitude,
              accuracy: coords.accuracy, speed: coords.speed, heading: coords.heading,
            });
          });
          MugenUI.toast(labelSukses, "success");
          load();
        } catch (e) {
          MugenUI.infoModal({ title: "Gagal", body: MugenUI.el("p", {}, (e.detail && e.detail.detail) ? e.detail.detail : e.message) });
        }
      }
      btnCheckIn.addEventListener("click", () => lakukanAksi(btnCheckIn, "/api/attendance/check-in", "Check In berhasil.", {
        title: "Konfirmasi Check In", message: "Anda akan Check In sekarang menggunakan lokasi perangkat ini. Lanjutkan?", confirmText: "Check In",
      }));
      btnCheckOut.addEventListener("click", () => lakukanAksi(btnCheckOut, "/api/attendance/check-out", "Check Out berhasil.", {
        title: "Konfirmasi Check Out", message: "Anda akan Check Out sekarang menggunakan lokasi perangkat ini. Lanjutkan?", confirmText: "Check Out",
      }));
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
        return beriAnimasiBaris(MugenUI.buildTable([
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "check_in_at", label: "Check In", format: jamDariIso },
          { key: "check_out_at", label: "Check Out", format: jamDariIso },
          { key: "status", label: "Status", format: (_, r) => badgeStatus(r) },
          { key: "durasi_kerja_menit", label: "Durasi Kerja", format: durasiText },
          { key: "keterangan", label: "Keterangan", format: keteranganText },
        ], rows, { emptyText: "Belum ada riwayat absensi." }));
      }, { skeleton: { kind: "table", cols: 6, rows: 4 } });
    }
    loadHistory();

    // ---- Sisa Limit Keterlambatan & Pulang Lebih Awal (bulan berjalan) ----
    const limitCard = MugenUI.el("div", { class: "card" });
    root.appendChild(limitCard);
    limitCard.appendChild(MugenUI.el("h2", {}, "Sisa Limit Bulan Ini"));
    const limitSubtitle = MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Keterlambatan & Pulang Lebih Awal masing-masing punya limit menit/bulan (diatur Owner/Admin), otomatis reset tiap tanggal 1. Limit habis TIDAK menghalangi Check In/Out, hanya tercatat di Keterangan.");
    limitCard.appendChild(limitSubtitle);
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
        limitSubtitle.textContent = `Limit Keterlambatan: ${r.batas_menit_terlambat} menit/bulan. Limit Pulang Lebih Awal: ${r.batas_menit_pulang_awal} menit/bulan. Diatur Owner/Admin di menu Absensi, otomatis reset tiap tanggal 1. Limit habis TIDAK menghalangi Check In/Out, hanya tercatat di Keterangan.`;
        return MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:32px;justify-content:center;" }, [
          ringLimit("Sisa Limit Terlambat", r.sisa_limit_terlambat, r.batas_menit_terlambat, r.ambang_peringatan_menit),
          ringLimit("Sisa Limit Pulang Lebih Awal", r.sisa_limit_pulang_awal, r.batas_menit_pulang_awal, r.ambang_peringatan_menit),
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
    koreksiCard.appendChild(MugenUI.el("label", {}, "Tanggal"));
    koreksiCard.appendChild(kTanggal);
    koreksiCard.appendChild(MugenUI.el("label", {}, "Jenis"));
    koreksiCard.appendChild(kJenis);
    koreksiCard.appendChild(MugenUI.el("label", {}, "Jam yang Seharusnya"));
    koreksiCard.appendChild(kJam);
    koreksiCard.appendChild(MugenUI.el("label", {}, "Alasan"));
    koreksiCard.appendChild(kAlasan);
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
      if (!kJam.value) {
        MugenUI.infoModal({ title: "Belum Lengkap", body: MugenUI.el("p", {}, "Jam yang seharusnya wajib diisi.") });
        return;
      }
      if (!kAlasan.value.trim()) {
        MugenUI.infoModal({ title: "Belum Lengkap", body: MugenUI.el("p", {}, "Alasan wajib diisi.") });
        return;
      }
      // REVISI UI/UX Absensi Barber (feedback Owner): modal konfirmasi
      // (box tengah layar) menampilkan RINGKASAN yang akan diajukan,
      // supaya barber sempat memeriksa ulang sebelum benar-benar
      // terkirim ke Admin/Owner.
      const ok = await MugenUI.confirmModal({
        title: "Konfirmasi Pengajuan Koreksi",
        message: [
          `Jenis: ${LABEL_JENIS_KOREKSI[kJenis.value] || kJenis.value}`,
          `Tanggal: ${MugenUI.formatTanggal(kTanggal.value)}`,
          `Jam yang Seharusnya: ${kJam.value}`,
          `Alasan: ${kAlasan.value.trim()}`,
          "Ajukan koreksi ini ke Admin/Owner?",
        ],
        confirmText: "Ajukan",
      });
      if (!ok) return;
      try {
        await MugenUI.withButtonLoading(kBtn, () => MugenApi.post("/api/attendance/koreksi", {
          tanggal: kTanggal.value, jenis: kJenis.value, waktu_diajukan: kJam.value, alasan: kAlasan.value.trim(),
        }));
        MugenUI.toast("Pengajuan koreksi berhasil dikirim.", "success");
        kJam.value = ""; kAlasan.value = "";
        loadKoreksiSaya();
      } catch (e) {
        MugenUI.infoModal({ title: "Gagal Mengajukan Koreksi", body: MugenUI.el("p", {}, (e.detail && e.detail.detail) ? e.detail.detail : e.message) });
      }
    });
  }

  // ---- Pengaturan Absensi (Jam Kerja, Radius, Limit, Lokasi Toko) --
  // REVISI (feedback Owner): sebelumnya tab terpisah di Setting > Absensi,
  // sekarang dipindahkan ke sini (menu utama Absensi) supaya semuanya jadi
  // satu tempat. Gate izin SAMA seperti sebelumnya (izin_absensi_pengaturan,
  // backend tetap menegakkan lewat require_permission() di PUT
  // /api/attendance/settings -- pemanggil hanya menyembunyikan/menampilkan
  // kartu ini, BUKAN satu-satunya lapis perlindungan).
  async function renderPengaturanAbsensi(root) {
    const card = MugenUI.el("div", { class: "card" });
    root.appendChild(card);
    card.appendChild(MugenUI.el("h2", {}, "Pengaturan Absensi"));
    card.appendChild(MugenUI.el("div", { class: "subtitle" },
      "Atur jam kerja & radius geofencing untuk Check In/Check Out Barber."));

    let settings;
    try {
      settings = await MugenApi.get("/api/attendance/settings");
    } catch (e) {
      card.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
      return;
    }

    const inputJamMasuk = MugenUI.el("input", { type: "time", value: settings.jam_masuk || "09:00" });
    const inputToleransi = MugenUI.el("input", { type: "number", min: "0", value: String(settings.toleransi_menit ?? 15) });
    const inputJamPulang = MugenUI.el("input", { type: "time", value: settings.jam_pulang || "20:00" });
    const selRadius = MugenUI.el("select", {}, [100, 250, 500, 750, 1000].map((r) =>
      MugenUI.el("option", { value: String(r) }, `${r} meter`)));
    selRadius.value = String(settings.radius_meter || 500);

    card.appendChild(MugenUI.el("label", {}, "Jam Masuk"));
    card.appendChild(inputJamMasuk);
    card.appendChild(MugenUI.el("label", {}, "Toleransi Masuk (menit)"));
    card.appendChild(inputToleransi);
    card.appendChild(MugenUI.el("label", {}, "Jam Pulang"));
    card.appendChild(inputJamPulang);
    card.appendChild(MugenUI.el("label", {}, "Radius Absensi"));
    card.appendChild(selRadius);

    card.appendChild(MugenUI.el("h3", { style: "margin-top:20px;" }, "Limit Keterlambatan & Pulang Lebih Awal"));
    card.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Setiap barber punya anggaran menit/bulan (otomatis reset tiap tanggal 1) untuk keterlambatan Check In dan untuk pulang lebih awal saat Check Out -- dua anggaran ini TERPISAH. Limit habis TIDAK memblokir Check In/Check Out, hanya dicatat di Keterangan (dengan tanda merah)."));
    const inputBatasTerlambat = MugenUI.el("input", { type: "number", min: "0", value: String(settings.batas_menit_terlambat ?? 120) });
    const inputBatasPulangAwal = MugenUI.el("input", { type: "number", min: "0", value: String(settings.batas_menit_pulang_awal ?? 120) });
    card.appendChild(MugenUI.el("label", {}, "Limit Keterlambatan (menit/bulan)"));
    card.appendChild(inputBatasTerlambat);
    card.appendChild(MugenUI.el("label", {}, "Limit Pulang Lebih Awal (menit/bulan)"));
    card.appendChild(inputBatasPulangAwal);

    card.appendChild(MugenUI.el("h3", { style: "margin-top:20px;" }, "Lokasi Toko"));
    const inputLokasiNama = MugenUI.el("input", { type: "text", value: settings.lokasi_nama || "", placeholder: "Contoh: Rivoir Barbershop Pusat" });
    const inputLat = MugenUI.el("input", { type: "text", value: settings.lokasi_latitude != null ? String(settings.lokasi_latitude) : "", placeholder: "Latitude", readonly: "" });
    const inputLng = MugenUI.el("input", { type: "text", value: settings.lokasi_longitude != null ? String(settings.lokasi_longitude) : "", placeholder: "Longitude", readonly: "" });
    const btnLokasiSaatIni = MugenUI.el("button", {}, "Gunakan Lokasi Saat Ini");
    const lokasiError = MugenUI.el("div", { class: "login-error" });

    card.appendChild(MugenUI.el("label", {}, "Nama Lokasi"));
    card.appendChild(inputLokasiNama);
    card.appendChild(MugenUI.el("label", {}, "Latitude"));
    card.appendChild(inputLat);
    card.appendChild(MugenUI.el("label", {}, "Longitude"));
    card.appendChild(inputLng);
    card.appendChild(lokasiError);
    card.appendChild(MugenUI.el("div", { style: "margin-top:8px;" }, btnLokasiSaatIni));

    btnLokasiSaatIni.addEventListener("click", () => {
      lokasiError.textContent = "";
      if (!navigator.geolocation) {
        lokasiError.textContent = "Perangkat/browser ini tidak mendukung Geolocation.";
        return;
      }
      btnLokasiSaatIni.disabled = true;
      btnLokasiSaatIni.textContent = "Mengambil lokasi…";
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          inputLat.value = String(pos.coords.latitude);
          inputLng.value = String(pos.coords.longitude);
          btnLokasiSaatIni.disabled = false;
          btnLokasiSaatIni.textContent = "Gunakan Lokasi Saat Ini";
        },
        (err) => {
          lokasiError.textContent = "Gagal mengambil lokasi: " + (err.message || "izin lokasi ditolak.");
          btnLokasiSaatIni.disabled = false;
          btnLokasiSaatIni.textContent = "Gunakan Lokasi Saat Ini";
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
      );
    });

    const errorBox = MugenUI.el("div", { class: "login-error" });
    const btnSimpan = MugenUI.el("button", { class: "btn-primary" }, "Simpan Pengaturan Absensi");
    card.appendChild(errorBox);
    card.appendChild(MugenUI.el("div", { style: "margin-top:16px;" }, btnSimpan));

    btnSimpan.addEventListener("click", async () => {
      errorBox.textContent = "";
      const body2 = {
        jam_masuk: inputJamMasuk.value, toleransi_menit: Number(inputToleransi.value),
        jam_pulang: inputJamPulang.value, radius_meter: Number(selRadius.value),
        lokasi_nama: inputLokasiNama.value.trim(),
        batas_menit_terlambat: Number(inputBatasTerlambat.value),
        batas_menit_pulang_awal: Number(inputBatasPulangAwal.value),
      };
      if (inputLat.value) body2.lokasi_latitude = Number(inputLat.value);
      if (inputLng.value) body2.lokasi_longitude = Number(inputLng.value);
      try {
        await MugenUI.withButtonLoading(btnSimpan, () => MugenApi.put("/api/attendance/settings", body2));
        MugenUI.toast("Pengaturan Absensi disimpan.", "success");
      } catch (e) {
        errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });
  }

  // ================= OWNER/ADMIN: Dashboard + Daftar + Laporan + Audit =================
  async function renderAdminView(root) {
    let barbers = [];
    try {
      barbers = await MugenApi.get("/api/input-data/karyawan", { useCache: true });
    } catch (e) { /* opsional */ }

    // ---- Pengaturan Absensi (lihat renderPengaturanAbsensi() di atas) ----
    // Owner selalu boleh; staff HANYA kalau diberi izin_absensi_pengaturan
    // lewat Setting > Hak Akses Admin (sama seperti sebelumnya saat ini
    // masih jadi tab Setting > Absensi).
    const userAktif = MugenState.getUser();
    const isOwnerAktif = userAktif.role === "admin";
    let bolehAturSettings = isOwnerAktif;
    if (!isOwnerAktif) {
      try {
        const izinAdmin = await MugenApi.get("/api/pengaturan/hak-akses-admin");
        bolehAturSettings = !!izinAdmin.izin_absensi_pengaturan;
      } catch (e) {
        bolehAturSettings = false;
      }
    }
    if (bolehAturSettings) {
      await renderPengaturanAbsensi(root);
    }

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
    const limitSubtitle = MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Keterlambatan & Pulang Lebih Awal masing-masing punya limit menit/bulan per barber (diatur Owner/Admin di kartu Pengaturan Absensi), otomatis reset tiap tanggal 1. Limit habis TIDAK menghalangi Check In/Out, hanya tercatat di Keterangan.");
    limitCard.appendChild(limitSubtitle);
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
        if (rows.length) {
          limitSubtitle.textContent = `Limit Keterlambatan: ${rows[0].batas_menit_terlambat} menit/bulan. Limit Pulang Lebih Awal: ${rows[0].batas_menit_pulang_awal} menit/bulan per barber. Diatur Owner/Admin di kartu Pengaturan Absensi, otomatis reset tiap tanggal 1. Limit habis TIDAK menghalangi Check In/Out, hanya tercatat di Keterangan.`;
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
    // Hapus PERMANEN (sampai ke database) -- KHUSUS Owner (backend
    // require_admin, TIDAK bisa didelegasikan ke staff lewat Hak Akses
    // Admin), karena log ini sendiri adalah bukti investigasi Fake GPS.
    if (isOwnerAktif) {
      const btnHapusAudit = MugenUI.el("button", { class: "btn-danger", style: "margin-bottom:10px;" }, "Hapus Semua Log Audit");
      btnHapusAudit.addEventListener("click", async () => {
        if (!confirm("Hapus SEMUA Log Audit Percobaan Check In/Out secara permanen? Tindakan ini TIDAK BISA dibatalkan (data terhapus sampai ke database).")) return;
        try {
          const hasil = await MugenUI.withButtonLoading(btnHapusAudit, () => MugenApi.del("/api/attendance/audit"));
          MugenUI.toast(`${hasil.jumlah_dihapus} baris Log Audit dihapus.`, "success");
          loadAudit();
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
      auditCard.appendChild(btnHapusAudit);
    }
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

    // ---- Reset Riwayat Absensi Karyawan (mengantisipasi data menumpuk) ----
    // BEDA dari Hapus Log Audit di atas: ini menghapus attendance_logs
    // (riwayat Check In/Out sungguhan), bukan sekadar log investigasi --
    // TAPI Owner ATAU Admin (staff) SAMA-SAMA boleh (backend
    // require_owner_or_staff, TANPA delegasi permission terpisah), sesuai
    // permintaan Owner.
    const resetCard = MugenUI.el("div", { class: "card" });
    root.appendChild(resetCard);
    resetCard.appendChild(MugenUI.el("h2", {}, "Reset Riwayat Absensi Karyawan"));
    resetCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:10px;" },
      "Hapus PERMANEN riwayat Check In/Out (Daftar Absensi, Sisa Limit, Keterangan) untuk mengantisipasi data yang menumpuk. Pilih satu barber, atau \"Semua Barber\" untuk menghapus riwayat SELURUH karyawan. Tindakan ini TIDAK BISA dibatalkan."));
    const selResetBarber = MugenUI.el("select");
    selResetBarber.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
    for (const b of barbers) selResetBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const btnResetRiwayat = MugenUI.el("button", { class: "btn-danger" }, "Hapus Riwayat Absensi");
    resetCard.appendChild(MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;flex:none;gap:10px;" },
      [selResetBarber, btnResetRiwayat]));

    btnResetRiwayat.addEventListener("click", async () => {
      const namaBarberDipilih = selResetBarber.value
        ? (barbers.find((b) => String(b.id) === selResetBarber.value) || {}).nama
        : "SEMUA barber";
      if (!confirm(`Hapus PERMANEN riwayat Check In/Out milik ${namaBarberDipilih}? Tindakan ini TIDAK BISA dibatalkan (data terhapus sampai ke database).`)) return;
      try {
        const qs = selResetBarber.value ? `?barber_id=${selResetBarber.value}` : "";
        const hasil = await MugenUI.withButtonLoading(btnResetRiwayat, () => MugenApi.del(`/api/attendance/riwayat${qs}`));
        MugenUI.toast(`${hasil.jumlah_dihapus} baris riwayat absensi dihapus.`, "success");
        loadDashboard();
        loadLimit();
        loadList();
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    });
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

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageAbsensi begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageAbsensi = PageAbsensi;
