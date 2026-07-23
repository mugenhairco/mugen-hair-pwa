// pages/dashboard_owner.js

const PageDashboardOwner = (() => {
  function render(root) {
    const today = new Date();
    let tahun = today.getFullYear();
    let bulan = today.getMonth() + 1;

    root.innerHTML = "";
    const header = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
    header.appendChild(MugenUI.el("h1", {}, "Dashboard Owner"));

    const selBulan = MugenUI.el("select");
    for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
    selBulan.value = String(bulan);
    const selTahun = MugenUI.el("select");
    for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
    selTahun.value = String(tahun);
    const picker = MugenUI.el("div", { class: "row", style: "flex:none;" }, [selBulan, selTahun]);
    header.appendChild(picker);
    root.appendChild(header);

    const body = MugenUI.el("div");
    root.appendChild(body);

    async function load() {
      body.innerHTML = "Memuat...";
      try {
        const data = await MugenApi.get(`/api/dashboard/owner?tahun=${tahun}&bulan=${bulan}`, { useCache: true });
        body.innerHTML = "";
        if (data.__offline) body.appendChild(MugenUI.offlineBanner(data.__cachedAt));

        const t = data.total_toko;
        body.appendChild(MugenUI.el("div", { class: "grid-cards" }, [
          card("Total Pendapatan Barber", t.total_pendapatan),
          card("Nilai Service", t.nilai_service),
          card("Komisi", t.komisi),
          card("Tips", t.tips),
          card("Uang Harian", t.uang_harian),
          card("Bonus (Customer+Kehadiran)", t.bonus_customer + t.bonus_kehadiran),
          card("Pengeluaran Toko", data.total_pengeluaran),
          card("Laba Kotor Toko", data.laba_kotor),
        ]));

        body.appendChild(MugenUI.el("h2", {}, "Per Barber"));
        body.appendChild(MugenUI.buildTable(
          [
            { key: "barber", label: "Barber", format: (_, r) => r.barber.nama },
            { key: "jumlah_customer", label: "Customer" },
            { key: "komisi", label: "Komisi", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            { key: "bonus_customer", label: "Bonus Customer", format: MugenUI.formatRupiah },
            { key: "bonus_kehadiran", label: "Bonus Kehadiran", format: MugenUI.formatRupiah },
            { key: "total_pendapatan", label: "Total", format: MugenUI.formatRupiah },
          ],
          data.per_barber,
        ));
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.el("div", { class: "card" }, e.message));
      }
    }

    function card(label, value) {
      return MugenUI.el("div", { class: "card" }, [
        MugenUI.el("h2", {}, label),
        MugenUI.el("div", { class: "big-number" }, MugenUI.formatRupiah(value)),
      ]);
    }

    selBulan.addEventListener("change", () => { bulan = Number(selBulan.value); load(); });
    selTahun.addEventListener("change", () => { tahun = Number(selTahun.value); load(); });
    load();
  }

  return { render };
})();
