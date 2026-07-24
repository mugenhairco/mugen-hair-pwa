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

    async function load() {
      body.innerHTML = "Memuat...";
      try {
        const r = await MugenApi.get(`/api/dashboard/barber?tahun=${tahun}&bulan=${bulan}`, { useCache: true });
        body.innerHTML = "";
        if (r.__offline) body.appendChild(MugenUI.offlineBanner(r.__cachedAt));

        // REVISI: kartu "Bonus Kehadiran" dan "Jumlah Service" dihapus dari
        // Dashboard Barber (fitur Bonus Kehadiran dihapus total; Jumlah
        // Service masih ada rinciannya di tabel "Service Bulan Ini" di bawah,
        // hanya kartu ringkasan totalnya yang dihapus).
        body.appendChild(MugenUI.el("div", { class: "grid-cards" }, [
          card("Total Pendapatan", r.total_pendapatan),
          card("Komisi", r.komisi),
          card("Tips", r.tips),
          card("Uang Harian", r.uang_harian),
          card("Bonus Customer", r.bonus_customer),
          card("Jumlah Customer", r.jumlah_customer),
        ]));

        // REVISI: Target Bonus Service sekarang bertingkat (banyak tier,
        // diatur lewat Setting) -- progress ditampilkan menuju tier
        // berikutnya yang belum tercapai (dari Dry Cut + Cut & Wash saja).
        const bd = r.bonus_customer_detail;
        const progressLines = [
          MugenUI.el("div", {}, `${bd.jumlah_service} service (Dry Cut + Cut & Wash) bulan ini.`),
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

        body.appendChild(MugenUI.el("h2", {}, "Transaksi Terakhir"));
        body.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "daftar_service", label: "Service" },
            { key: "total_harga", label: "Nilai", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
          ],
          r.transaksi_terakhir,
        ));
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.el("div", { class: "card" }, e.message));
      }
    }

    selBulan.addEventListener("change", () => { bulan = Number(selBulan.value); load(); });
    selTahun.addEventListener("change", () => { tahun = Number(selTahun.value); load(); });
    load();
  }

  return { render };
})();
