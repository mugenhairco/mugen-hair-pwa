// pages/dashboard_owner.js
// REVISI: kartu "Bonus Kehadiran" dihapus (fitur Bonus Kehadiran dihapus
// total); ditambah kartu "Total Customer", bagian "Progress Target
// Service", dan "Service Bulan Ini" (dengan dropdown pilihan barber).
// REVISI Hak Akses Admin:
// - Kartu "Total Pendapatan Barber" DIHAPUS (nilainya sama persis dengan
//   "Total Komisi Barber" -- dua kartu untuk satu angka yang sama).
// - REVISI ("hilangkan fitur untuk menyembunyikan nilai kartu"): fitur
//   collapse/expand per kartu (klik judul untuk sembunyikan nilainya,
//   status tersimpan di localStorage) DIHAPUS TOTAL -- nilai kartu SELALU
//   tampil, tidak ada lagi panah/klik untuk sembunyikan. Tombol "Collapse
//   All"/"Expand All" (pengatur semua kartu sekaligus) SUDAH LEBIH DULU
//   dihapus (permintaan Owner terpisah, "bagian atas berantakan").
// - Halaman ini SEKARANG JUGA dipakai untuk role 'staff' (Admin, lihat
//   router.js::resolveDashboardPage) -- backend (routers/dashboard.py)
//   sudah memfilter field yang tidak diizinkan Owner jadi `null` untuk
//   role ini, dan mengosongkan `per_barber` sama sekali. Kartu dengan
//   nilai `null` TIDAK dirender sama sekali (bukan ditampilkan sebagai
//   "Rp 0", supaya tidak menyesatkan), dan bagian "SERVICE BULAN INI"/
//   "Grafik Pendapatan" (di luar cakupan Dashboard Admin, lihat
//   spesifikasi) hanya dirender untuk role 'admin' (Owner).
// REVISI (PERMINTAAN Owner): tabel "Per Barber" (ringkasan Komisi/Tips/
//   Uang Harian/Bonus Customer/Total per baris barber) DIHAPUS PERMANEN --
//   lihat catatan lengkap di dekat bagian "SERVICE BULAN INI" di bawah.

const PageDashboardOwner = (() => {
  // PERMINTAAN OWNER: simpan hasil fetch TERAKHIR (in-memory, hilang kalau
  // app di-reload) supaya kalau Dashboard dibuka lagi tanpa ada data baru
  // (lihat MugenState.dashboardPerluRefresh()), halaman bisa langsung
  // dirender ulang dari sini TANPA fetch/skeleton sama sekali. Disimpan di
  // LUAR render() (modul-level) supaya bertahan lintas navigasi menu;
  // `userId` dicocokkan supaya tidak salah pakai cache akun lain kalau ada
  // logout+login user berbeda tanpa reload app.
  let _cacheTerakhir = null; // { userId, url, data } | null

  function _ambilDariCache(userId, url) {
    if (!_cacheTerakhir) return null;
    if (_cacheTerakhir.userId !== userId || _cacheTerakhir.url !== url) return null;
    return _cacheTerakhir.data;
  }

  // FITUR "Dashboard tidak perlu refresh semua, cukup data yang berubah
  // saja" (PERMINTAAN Owner): dipanggil dari halaman lain (booking.js/
  // input_data.js, lazy-loaded via page_loader.js -- guard typeof WAJIB di
  // pemanggil) begitu ada data baru yang memengaruhi angka Dashboard (booking
  // lunas, transaksi Input Data baru/dikoreksi). HANYA menyegarkan
  // _cacheTerakhir di LATAR BELAKANG (fetch ulang url yang SAMA terakhir
  // kali Dashboard dimuat) -- TIDAK PERNAH menyentuh DOM (Dashboard, kalau
  // sedang dilihat, PASTI bukan halaman yang memicu ini -- SPA satu-halaman-
  // aktif-sekaligus, trigger-nya datang dari menu LAIN). Begitu selesai,
  // ditandai "bersih" (MugenState.tandaiDashboardBersih()) supaya next
  // kali user BENAR-BENAR membuka Dashboard, cache-hit yang SUDAH ADA
  // (lihat load() di bawah) langsung menampilkan angka terbaru INSTAN
  // TANPA skeleton -- bukan skeleton+fetch penuh seperti sebelumnya begitu
  // ada data baru di tempat lain. Belum pernah dibuka sesi ini (_cacheTerakhir
  // null) -> no-op aman, tidak ada apa pun yang perlu disegarkan.
  async function refreshDiamDiam() {
    if (!_cacheTerakhir) return;
    try {
      const data = await MugenApi.get(_cacheTerakhir.url);
      if (data.__offline) return; // bukan data sungguhan, jangan timpa cache yang valid
      _cacheTerakhir = { userId: _cacheTerakhir.userId, url: _cacheTerakhir.url, data };
      MugenState.tandaiDashboardBersih();
    } catch (e) {
      // best-effort -- diam saja, Dashboard tetap benar begitu dibuka manual
      // (dirty flag TIDAK ditandai bersih kalau refresh diam-diam ini gagal).
    }
  }

  async function render(root) {
    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" ke menu
    // Dashboard -- tampilkan HANYA pesan kosong, tidak fetch/tampilkan
    // kartu apa pun. Kartu PER-FIELD (izin_dashboard_*) tetap jalan seperti
    // sebelumnya begitu level di atas "none" -- dua sistem izin berbeda,
    // level menu ini menggerbang SELURUH halaman, izin_dashboard_* di
    // bawahnya menggerbang kartu MANA yang tampil.
    if ((await MugenMenuAccess.get("dashboard")) === "none") {
      root.innerHTML = "";
      root.appendChild(MugenUI.pageTitle("Dashboard", MugenIcons.dashboard));
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const today = new Date();
    let tahun = today.getFullYear();
    let bulan = today.getMonth() + 1;
    const isOwner = MugenState.getUser().role === "admin";

    // FITUR BARU (diminta Owner): mode "Periode" -- rentang tanggal bebas
    // (mis. 1-10 Agustus), berdampingan dengan mode "Bulanan" yang sudah
    // ada (satu bulan kalender penuh, TIDAK diubah sama sekali).
    let mode = "bulanan"; // "bulanan" | "periode"
    let tanggalMulai = MugenUI.awalBulanWib(MugenUI.isoHariIniWib());
    let tanggalSelesai = MugenUI.isoHariIniWib();

    root.innerHTML = "";
    const header = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
    header.appendChild(MugenUI.pageTitle(isOwner ? "Dashboard Owner" : "Dashboard Admin", MugenIcons.dashboard));

    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(bulan);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(tahun);
    const pickerBulanan = MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun]);

    const inputTanggalMulai = MugenUI.el("input", { type: "date", value: tanggalMulai, style: "max-width:150px;" });
    const inputTanggalSelesai = MugenUI.el("input", { type: "date", value: tanggalSelesai, style: "max-width:150px;" });
    const pickerPeriode = MugenUI.el("div", { class: "row", style: "flex:none;display:none;align-items:center;gap:6px;" }, [
      inputTanggalMulai,
      MugenUI.el("span", {}, "s/d"),
      inputTanggalSelesai,
    ]);

    const modeTabs = MugenUI.tabs(
      [{ key: "bulanan", label: "Bulanan" }, { key: "periode", label: "Periode" }],
      {
        initial: mode,
        onChange: (key) => {
          mode = key;
          pickerBulanan.style.display = mode === "bulanan" ? "" : "none";
          pickerPeriode.style.display = mode === "periode" ? "" : "none";
          load();
        },
      },
    );

    const picker = MugenUI.el("div", { class: "row", style: "flex:none;align-items:center;gap:10px;flex-wrap:wrap;" }, [
      modeTabs.bar, pickerBulanan, pickerPeriode,
    ]);
    header.appendChild(picker);
    root.appendChild(header);
    modeTabs.moveIndicator();

    const body = MugenUI.el("div");
    root.appendChild(body);

    // REVISI ("hilangkan fitur untuk menyembunyikan nilai kartu"): nilai
    // kartu SELALU tampil, tidak ada lagi panah/klik collapse per kartu
    // (dulu di sini, lihat riwayat komentar/COLLAPSE_KEY).
    // PERMINTAAN Owner (referensi dashboard "navy sidebar + kartu pastel"):
    // kartu statistik kembali berwarna per kategori -- `warna` ("blue"/
    // "green"/"orange"/"purple") menentukan latar kartu (class "card--
    // <warna>") & warna chip ikon (class "icon-chip--<warna>2"), menggantikan
    // kartu "andalan" tunggal yang dipakai sebelumnya.
    function card(label, value, icon, warna) {
      if (value === null || value === undefined) return null; // staff tanpa izin untuk kartu ini
      const valueBox = MugenUI.el("div", { class: "big-number" }, MugenUI.formatRupiah(value));
      const titleChildren = [];
      if (icon) titleChildren.push(MugenUI.el("span", { class: "card-collapse-icon icon-chip--" + warna + "2", html: icon }));
      titleChildren.push(MugenUI.el("span", {}, label));
      const titleRow = MugenUI.el("h2", { class: "card-collapse-title" }, titleChildren);
      return MugenUI.el("div", { class: "card card--" + warna }, [titleRow, valueBox]);
    }

    // REVISI ("Jumlah Service tampilkan nilai total keseluruhan service
    // saja"): SEBELUMNYA kartu ini berisi rincian per jenis service (mis.
    // "Dry Cut" = 7, "Cut & Wash" = 3, dst) -- SEKARANG cuma satu angka
    // total (jumlah seluruh service digabung), sama gayanya seperti
    // card() di atas. Gabungan seluruh barber, sama seperti kartu lain di
    // baris ini yang semuanya total toko.
    function cardJumlahService(rincian, warna) {
      if (rincian === null || rincian === undefined) return null;
      const total = rincian.reduce((jumlah, item) => jumlah + item.jumlah, 0);
      const titleRow = MugenUI.el("h2", { class: "card-collapse-title" }, [
        MugenUI.el("span", { class: "card-collapse-icon icon-chip--" + warna + "2", html: MugenIcons.service }),
        MugenUI.el("span", {}, "Jumlah Service"),
      ]);
      const valueBox = MugenUI.el("div", { class: "big-number" }, String(total));
      return MugenUI.el("div", { class: "card card--" + warna }, [titleRow, valueBox]);
    }

    // BUGFIX (audit, race condition): dulu tidak ada penjagaan urutan
    // request -- membalik bulan/tahun dengan cepat bisa membuat dua
    // fetch tumpang tindih selesai TIDAK berurutan, data bulan yang
    // LEBIH LAMA bisa mendarat setelah bulan yang lebih baru dan diam-diam
    // menimpa dashboard dengan angka bulan yang salah.
    let urutanTerkini = 0;

    async function load(opts = {}) {
      const url = mode === "periode"
        ? `/api/dashboard/owner/periode?tanggal_mulai=${tanggalMulai}&tanggal_selesai=${tanggalSelesai}`
        : `/api/dashboard/owner?tahun=${tahun}&bulan=${bulan}`;

      // PERMINTAAN OWNER: begitu Dashboard dibuka lagi (pindah menu lalu
      // balik) TANPA ada simpan/edit/hapus apa pun sejak terakhir kali
      // Dashboard INI berhasil dimuat, tampilkan ulang hasil fetch terakhir
      // PERSIS seperti itu -- instan, tanpa skeleton/fetch sama sekali.
      // Hanya dicek untuk pemuatan AWAL (opts.bisaDariCache, dipanggil
      // SEKALI dari akhir render() di bawah) -- ganti bulan/tahun/periode
      // manual oleh user (handler di bawah, TANPA opts) SELALU fetch ulang.
      if (opts.bisaDariCache && !MugenState.dashboardPerluRefresh()) {
        const cached = _ambilDariCache(MugenState.getUser().id, url);
        if (cached) {
          renderDenganData(cached);
          return;
        }
      }

      const urutanSaya = ++urutanTerkini;
      // REVISI UI/UX Premium: skeleton (bentuk kartu) menggantikan teks
      // "Memuat..." -- kartu asli otomatis beranimasi masuk begitu
      // ditambahkan (lihat .card { animation: mugen-fade-slide-in }),
      // jadi transisi skeleton -> data terasa satu alur, bukan dua lompatan.
      body.innerHTML = "";
      body.appendChild(MugenUI.el("div", { class: "grid-cards" }, [
        MugenUI.skeleton("card", { lines: 2 }), MugenUI.skeleton("card", { lines: 2 }),
        MugenUI.skeleton("card", { lines: 2 }),
      ]));
      try {
        const data = await MugenApi.get(url, { useCache: true });
        if (urutanSaya !== urutanTerkini) return; // respons basi, biarkan panggilan terbaru yang merender
        if (!data.__offline) {
          // Cache offline (data.__offline) SENGAJA tidak disimpan ke sini --
          // bukan representasi data yang sebenarnya berhasil dimuat barusan.
          _cacheTerakhir = { userId: MugenState.getUser().id, url, data };
          MugenState.tandaiDashboardBersih();
        }
        renderDenganData(data);
      } catch (e) {
        if (urutanSaya !== urutanTerkini) return; // respons basi, jangan timpa hasil yang lebih baru
        body.innerHTML = "";
        body.appendChild(MugenUI.el("div", { class: "card" }, MugenUI.errorState(e.message)));
      }
    }

    function renderDenganData(data) {
        body.innerHTML = "";
        if (data.__offline) body.appendChild(MugenUI.offlineBanner(data.__cachedAt));

        const t = data.total_toko;
        const kartu = [
          card("Nilai Service", t.nilai_service, MugenIcons.service, "blue"),
          card("Total Komisi Barber", t.komisi, MugenIcons.komisi, "green"),
          card("Total Tips", t.tips, MugenIcons.tips, "orange"),
          card("Uang Harian", t.uang_harian, MugenIcons.uangHarian, "purple"),
          cardJumlahService(data.rincian_service_semua_barber, "blue"),
          card("Pengeluaran Toko", data.total_pengeluaran, MugenIcons.pengeluaran, "green"),
          card("Penjualan Produk", data.penjualan_produk, MugenIcons.penjualanProduk, "orange"),
          card("Laba Kotor Toko", data.laba_kotor, MugenIcons.labaKotor, "purple"),
        ].filter((el) => el !== null);

        if (kartu.length === 0) {
          body.appendChild(MugenUI.el("div", { class: "card" },
            "Belum ada kartu Dashboard yang diizinkan untuk akun Admin ini. Hubungi Owner untuk mengatur hak akses lewat Setting > Hak Akses Admin."));
        } else {
          body.appendChild(MugenUI.el("div", { class: "grid-cards" }, kartu));
        }

        // ================= BAGIAN KHUSUS OWNER =================
        // SERVICE BULAN INI (rincian per barber) dan Grafik Pendapatan
        // BUKAN bagian dari Dashboard Admin (lihat spesifikasi Hak Akses
        // Admin -- hanya 4 kartu ringkasan toko yang bisa diizinkan Owner),
        // jadi tidak pernah dirender untuk role 'staff'.
        if (!isOwner) return;

        // ================= SERVICE BULAN INI / PERIODE INI =================
        const serviceCard = MugenUI.el("div", { class: "card" });
        const serviceHeader = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
        serviceHeader.appendChild(MugenUI.el("h2", { style: "margin:0;" }, mode === "periode" ? "SERVICE PERIODE INI" : "SERVICE BULAN INI"));
        const selBarberFilter = MugenUI.el("select", { style: "max-width:220px;" });
        selBarberFilter.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
        for (const r of data.per_barber) {
          selBarberFilter.appendChild(MugenUI.el("option", { value: String(r.barber.id) }, r.barber.nama));
        }
        serviceHeader.appendChild(selBarberFilter);
        serviceCard.appendChild(serviceHeader);

        const serviceTableBox = MugenUI.el("div");
        serviceCard.appendChild(serviceTableBox);
        body.appendChild(serviceCard);

        function renderRincianService() {
          serviceTableBox.innerHTML = "";
          if (!selBarberFilter.value) {
            serviceTableBox.appendChild(MugenUI.buildTable(
              [
                { key: "nama_service", label: "Service" },
                { key: "jumlah", label: "Jumlah" },
              ],
              data.rincian_service_semua_barber,
              { emptyText: "Belum ada service pada periode ini." },
            ));
          } else {
            const r = data.per_barber.find((x) => String(x.barber.id) === selBarberFilter.value);
            if (!r) return;
            serviceTableBox.appendChild(MugenUI.buildTable(
              [
                { key: "nama_service", label: "Service" },
                { key: "jumlah", label: "Jumlah" },
              ],
              r.rincian_service,
              { emptyText: "Belum ada service pada periode ini." },
            ));
          }
        }
        selBarberFilter.addEventListener("change", renderRincianService);
        renderRincianService();
        // PERMINTAAN Owner: tabel "Per Barber" (ringkasan Komisi/Tips/Uang
        // Harian/Bonus Customer/Total per baris barber) DIHAPUS PERMANEN
        // dari sini -- bukan disembunyikan lewat CSS. `data.per_barber`
        // TETAP dikirim backend & TETAP dipakai di atas (dropdown filter +
        // rincian service per barber di kartu "Service Bulan Ini", SENGAJA
        // TIDAK ikut dihapus) dan untuk menghitung kartu ringkasan "Total
        // Komisi Barber"/"Total Tips"/dst di atas (lihat total_toko di
        // routers/dashboard.py) -- field-field itu TIDAK bisa dihapus dari
        // payload API tanpa merusak keduanya, hanya tabel ini yang dihapus.
    }

    // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
    // -- skeleton di dalam body sendiri (lihat load() di atas) sudah jadi
    // feedback yang cukup, ganti bulan/tahun terasa instan.
    selBulan.addEventListener("change", () => { bulan = Number(selBulan.value); load(); });
    selTahun.addEventListener("change", () => { tahun = Number(selTahun.value); load(); });
    inputTanggalMulai.addEventListener("change", () => { tanggalMulai = inputTanggalMulai.value; load(); });
    inputTanggalSelesai.addEventListener("change", () => { tanggalSelesai = inputTanggalSelesai.value; load(); });
    // bisaDariCache: true HANYA di pemuatan AWAL ini -- ganti bulan/tahun/
    // periode manual oleh user (keempat handler di atas) SELALU fetch ulang.
    load({ bisaDariCache: true });
  }

  return { render, refreshDiamDiam };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageDashboardOwner begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageDashboardOwner = PageDashboardOwner;
