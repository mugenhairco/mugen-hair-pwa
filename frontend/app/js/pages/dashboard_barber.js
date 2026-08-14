// pages/dashboard_barber.js — HANYA menampilkan data barber yang login
// sendiri. Backend (routers/dashboard.py) yang memastikan ini, bukan
// frontend — jadi meskipun frontend dimodifikasi, seorang Barber tetap
// tidak bisa melihat data barber lain.

const PageDashboardBarber = (() => {
  function render(root) {
    const today = new Date();
    let tahun = today.getFullYear();
    let bulan = today.getMonth() + 1;

    root.innerHTML = "";
    const header = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
    header.appendChild(MugenUI.el("h1", {}, "Dashboard Saya"));

    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(bulan);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(tahun);
    header.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun]));
    root.appendChild(header);

    const body = MugenUI.el("div");
    root.appendChild(body);

    function card(label, value) {
      return MugenUI.el("div", { class: "card" }, [
        MugenUI.el("h2", {}, label),
        MugenUI.el("div", { class: "big-number" }, MugenUI.formatRupiah(value)),
      ]);
    }

    // REVISI: kartu "Jumlah Customer" diganti kartu "Jumlah Service" berisi
    // rincian per jenis service milik barber ini sendiri (mis. "Dry Cut" = 7,
    // "Cut & Wash" = 3, dst), service dengan jumlah 0 tidak ditampilkan
    // (backend sudah memfilternya lewat rincian_service).
    function cardJumlahService(rincian) {
      const children = [MugenUI.el("h2", {}, "Jumlah Service")];
      if (!rincian || rincian.length === 0) {
        children.push(MugenUI.el("div", { style: "color:var(--text-dim);" }, "Belum ada service bulan ini."));
      } else {
        for (const item of rincian) {
          children.push(MugenUI.el("div", { style: "display:flex;justify-content:space-between;padding:2px 0;" }, [
            MugenUI.el("span", {}, item.nama_service),
            MugenUI.el("span", { style: "font-weight:600;" }, String(item.jumlah)),
          ]));
        }
      }
      return MugenUI.el("div", { class: "card" }, children);
    }

    // Rekap Transaksi Bulanan (khusus halaman ini, akun Barber sendiri) --
    // dipisah dari kartu ringkasan di atas: tabel rinci per transaksi untuk
    // periode yang dipilih, PLUS tabel Kasbon dan Reimburse TERPISAH
    // (bukan digabung jadi kolom di tabel transaksi) yang HANYA muncul
    // kalau ada datanya periode itu. Sumbernya SAMA dengan endpoint yang
    // sudah dipakai halaman Rekap (/api/rekap/transaksi) -- backend sudah
    // otomatis membatasi hasil ke barber yang sedang login (lihat
    // routers/rekap.py::rekap_transaksi()), jadi tidak ada data baru yang
    // perlu dihitung di sini, murni menampilkan baris yang sudah ada
    // (tipe="transaksi"/"kasbon"/"reimburse", lihat database.py/
    // kasbon_db.py/reimburse_db.py) dengan susunan kolom yang berbeda.
    function tabelTransaksiBulanan(rows) {
      const transaksiRows = rows.filter((r) => r.tipe === "transaksi");
      return MugenUI.buildTable(
        [
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "nama_barber", label: "Nama" },
          { key: "daftar_service", label: "Service", format: MugenUI.serviceCell },
          { key: "jumlah_service", label: "Jml Service" },
          { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
          { key: "pendapatan", label: "Komisi", format: MugenUI.formatRupiah },
          // Total baris = Uang Harian + Komisi baris itu sendiri (Kasbon/
          // Reimburse TIDAK ikut di sini -- sudah punya tabelnya sendiri
          // di bawah, supaya tidak dihitung dua kali).
          { key: "pendapatan", label: "Total", format: (v, r) => MugenUI.formatRupiah((r.uang_harian || 0) + v) },
          {
            key: "keterangan", label: "Ket.", format: (v, r) => {
              if (!v) return "-";
              if (r.tipe === "libur") return MugenUI.el("span", { class: "badge badge-libur" }, v);
              return MugenUI.keteranganCell(v);
            },
          },
        ],
        transaksiRows,
      );
    }

    // Kasbon: nilai baris "pendapatan" NEGATIF (lihat kasbon_db.py) --
    // ditampilkan sebagai nominal positif di sini (kolom sudah berlabel
    // "Kasbon", tandanya tidak perlu diulang).
    function tabelKasbon(rows) {
      const kasbonRows = rows.filter((r) => r.tipe === "kasbon");
      if (kasbonRows.length === 0) return null;
      return MugenUI.buildTable(
        [
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "pendapatan", label: "Jumlah", format: (v) => MugenUI.formatRupiah(Math.abs(v)) },
          { key: "keterangan", label: "Keterangan" },
        ],
        kasbonRows,
      );
    }

    function tabelReimburse(rows) {
      const reimburseRows = rows.filter((r) => r.tipe === "reimburse");
      if (reimburseRows.length === 0) return null;
      return MugenUI.buildTable(
        [
          { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
          { key: "pendapatan", label: "Jumlah", format: MugenUI.formatRupiah },
          { key: "keterangan", label: "Keterangan" },
        ],
        reimburseRows,
      );
    }

    async function load() {
      // REVISI UI/UX Premium: skeleton menggantikan teks "Memuat..." --
      // kartu asli otomatis beranimasi masuk begitu ditambahkan (lihat
      // .card { animation: mugen-fade-slide-in }).
      body.innerHTML = "";
      body.appendChild(MugenUI.el("div", { class: "grid-cards" }, [
        MugenUI.skeleton("card", { lines: 2 }), MugenUI.skeleton("card", { lines: 2 }),
        MugenUI.skeleton("card", { lines: 2 }),
      ]));
      try {
        const [r, rekapRows] = await Promise.all([
          MugenApi.get(`/api/dashboard/barber?tahun=${tahun}&bulan=${bulan}`, { useCache: true }),
          MugenApi.get(`/api/rekap/transaksi?tahun=${tahun}&bulan=${bulan}`, { useCache: true }),
        ]);
        body.innerHTML = "";
        if (r.__offline) body.appendChild(MugenUI.offlineBanner(r.__cachedAt));

        // REVISI: kartu "Bonus Kehadiran" dihapus total (fitur dihapus);
        // kartu "Jumlah Customer" diganti kartu rincian "Jumlah Service".
        body.appendChild(MugenUI.el("div", { class: "grid-cards" }, [
          card("Total Pendapatan", r.total_pendapatan),
          card("Komisi", r.komisi),
          card("Tips", r.tips),
          card("Uang Harian", r.uang_harian),
          card("Bonus Customer", r.bonus_customer),
          cardJumlahService(r.rincian_service),
        ]));

        // REVISI: Target Bonus Service sekarang bertingkat (banyak tier,
        // diatur lewat Setting), DAN acuan service-nya sekarang dipilih
        // Owner sendiri lewat Setting > Bonus Service (bukan hardcode Dry
        // Cut + Cut & Wash lagi) -- progress ditampilkan menuju tier
        // berikutnya yang belum tercapai.
        // REVISI Struktur Setting: teks baris pertama TIDAK lagi menyebut
        // nama service acuan secara eksplisit (aturan sudah sepenuhnya bisa
        // dikonfigurasi Owner, tidak perlu diulang di sini).
        const bd = r.bonus_customer_detail;
        const progressLines = [
          MugenUI.el("div", {}, `${bd.jumlah_service} service memenuhi target bonus bulan ini.`),
        ];
        if (bd.tier_tercapai) {
          progressLines.push(MugenUI.el("div", {},
            `Tier tercapai: ${bd.tier_tercapai.target} service → Bonus ${MugenUI.formatRupiah(bd.tier_tercapai.bonus)}.`));
        }
        if (bd.tier_berikutnya) {
          progressLines.push(MugenUI.el("div", {},
            `${r.progress_target}% menuju tier berikutnya (${bd.tier_berikutnya.target} service → Bonus ${MugenUI.formatRupiah(bd.tier_berikutnya.bonus)}).`));
        } else if (bd.tier_tercapai) {
          progressLines.push(MugenUI.el("div", {}, "Sudah mencapai tier tertinggi."));
        } else if (!bd.tiers.length) {
          progressLines.push(MugenUI.el("div", {}, "Belum ada target bonus diatur oleh Owner."));
        }
        body.appendChild(MugenUI.el("div", { class: "card" }, [
          MugenUI.el("h2", {}, "Progress Target Service"),
          ...progressLines,
        ]));

        body.appendChild(MugenUI.el("h2", {}, "Service Bulan Ini"));
        body.appendChild(MugenUI.buildTable(
          [
            { key: "nama_service", label: "Service" },
            { key: "jumlah", label: "Jumlah" },
          ],
          r.rincian_service,
        ));

        const rows = Array.isArray(rekapRows) ? rekapRows : [];
        if (rekapRows.__offline) body.appendChild(MugenUI.offlineBanner(rekapRows.__cachedAt));

        body.appendChild(MugenUI.el("h2", {}, "Rekap Transaksi Bulanan"));
        body.appendChild(tabelTransaksiBulanan(rows));

        const kasbonTable = tabelKasbon(rows);
        if (kasbonTable) {
          body.appendChild(MugenUI.el("h2", {}, "Kasbon"));
          body.appendChild(kasbonTable);
        }

        const reimburseTable = tabelReimburse(rows);
        if (reimburseTable) {
          body.appendChild(MugenUI.el("h2", {}, "Reimburse"));
          body.appendChild(reimburseTable);
        }
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.el("div", { class: "card" }, MugenUI.errorState(e.message)));
      }
    }

    // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
    // -- skeleton di body sendiri (lihat load() di atas) sudah cukup.
    selBulan.addEventListener("change", () => { bulan = Number(selBulan.value); load(); });
    selTahun.addEventListener("change", () => { tahun = Number(selTahun.value); load(); });
    load();
  }

  return { render };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageDashboardBarber begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageDashboardBarber = PageDashboardBarber;
