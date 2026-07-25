// pages/dashboard_owner.js
// REVISI: kartu "Bonus Kehadiran" dihapus (fitur Bonus Kehadiran dihapus
// total); ditambah kartu "Total Customer", bagian "Progress Target
// Service", dan "Service Bulan Ini" (dengan dropdown pilihan barber).

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

    function card(label, value) {
      return MugenUI.el("div", { class: "card" }, [
        MugenUI.el("h2", {}, label),
        MugenUI.el("div", { class: "big-number" }, MugenUI.formatRupiah(value)),
      ]);
    }

    // REVISI: kartu "Total Customer" diganti kartu "Jumlah Service" berisi
    // rincian per jenis service (mis. "Dry Cut" = 7, "Cut & Wash" = 3, dst),
    // service dengan jumlah 0 tidak ditampilkan (backend sudah memfilternya
    // lewat rincian_service_semua_barber). Gabungan seluruh barber, sama
    // seperti kartu lain di baris ini yang semuanya total toko.
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
          card("Total Komisi Barber", t.komisi),
          card("Total Tips", t.tips),
          card("Uang Harian", t.uang_harian),
          card("Bonus Customer", t.bonus_customer),
          cardJumlahService(data.rincian_service_semua_barber),
          card("Pengeluaran Toko", data.total_pengeluaran),
          card("Laba Kotor Toko", data.laba_kotor),
        ]));

        // ================= PROGRESS TARGET SERVICE + SERVICE BULAN INI =================
        // Dropdown: "Semua Barber" (gabungan) atau satu barber tertentu.
        // Isi dropdown otomatis dari barber AKTIF yang sama seperti dipakai
        // untuk data di atas (data.per_barber) -- tidak ada barber di-hardcode.
        const serviceCard = MugenUI.el("div", { class: "card" });
        const serviceHeader = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
        serviceHeader.appendChild(MugenUI.el("h2", { style: "margin:0;" }, "Service Bulan Ini"));
        const selBarberFilter = MugenUI.el("select", { style: "max-width:220px;" });
        selBarberFilter.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
        for (const r of data.per_barber) {
          selBarberFilter.appendChild(MugenUI.el("option", { value: String(r.barber.id) }, r.barber.nama));
        }
        serviceHeader.appendChild(selBarberFilter);
        serviceCard.appendChild(serviceHeader);

        const progressBox = MugenUI.el("div", { style: "margin:12px 0;" });
        serviceCard.appendChild(progressBox);
        const serviceTableBox = MugenUI.el("div");
        serviceCard.appendChild(serviceTableBox);
        body.appendChild(serviceCard);

        function renderProgressDanRincian() {
          progressBox.innerHTML = "";
          serviceTableBox.innerHTML = "";

          if (!selBarberFilter.value) {
            // ---- Semua Barber: gabungan ----
            const totalServiceUtama = data.per_barber.reduce(
              (acc, r) => acc + r.bonus_customer_detail.jumlah_service, 0,
            );
            progressBox.appendChild(MugenUI.el("div", {},
              `Total ${totalServiceUtama} service (Dry Cut + Cut & Wash) — gabungan seluruh barber. ` +
              `Target Bonus Service dihitung per barber (lihat tabel "Per Barber" di bawah), pilih satu barber ` +
              `di dropdown untuk melihat progress target barber tersebut.`));
            serviceTableBox.appendChild(MugenUI.buildTable(
              [
                { key: "nama_service", label: "Service" },
                { key: "jumlah", label: "Jumlah" },
              ],
              data.rincian_service_semua_barber,
              { emptyText: "Belum ada service bulan ini." },
            ));
          } else {
            // ---- Satu barber tertentu ----
            const r = data.per_barber.find((x) => String(x.barber.id) === selBarberFilter.value);
            if (!r) return;
            const bd = r.bonus_customer_detail;
            const lines = [MugenUI.el("div", {}, `${bd.jumlah_service} service (Dry Cut + Cut & Wash) bulan ini.`)];
            if (bd.tier_tercapai) {
              lines.push(MugenUI.el("div", {},
                `Tier tercapai: ${bd.tier_tercapai.target} service → Bonus ${MugenUI.formatRupiah(bd.tier_tercapai.bonus)}.`));
            }
            if (bd.tier_berikutnya) {
              lines.push(MugenUI.el("div", {},
                `${r.progress_target}% menuju tier berikutnya (${bd.tier_berikutnya.target} service → Bonus ${MugenUI.formatRupiah(bd.tier_berikutnya.bonus)}).`));
            } else if (bd.tier_tercapai) {
              lines.push(MugenUI.el("div", {}, "Sudah mencapai tier tertinggi."));
            } else if (!bd.tiers.length) {
              lines.push(MugenUI.el("div", {}, "Belum ada target bonus diatur (Setting > Komisi & Bonus)."));
            }
            for (const l of lines) progressBox.appendChild(l);
            serviceTableBox.appendChild(MugenUI.buildTable(
              [
                { key: "nama_service", label: "Service" },
                { key: "jumlah", label: "Jumlah" },
              ],
              r.rincian_service,
              { emptyText: "Belum ada service bulan ini." },
            ));
          }
        }
        selBarberFilter.addEventListener("change", renderProgressDanRincian);
        renderProgressDanRincian();

        body.appendChild(MugenUI.el("h2", {}, "Per Barber"));
        body.appendChild(MugenUI.buildTable(
          [
            { key: "barber", label: "Barber", format: (_, r) => r.barber.nama },
            { key: "jumlah_customer", label: "Customer" },
            { key: "komisi", label: "Komisi", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiah },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            { key: "bonus_customer", label: "Bonus Customer", format: MugenUI.formatRupiah },
            { key: "total_pendapatan", label: "Total", format: MugenUI.formatRupiah },
          ],
          data.per_barber,
        ));

        // ================= GRAFIK PENDAPATAN (khusus Dashboard Owner) =================
        // Dua diagram batang: harian (mengikuti bulan/tahun yang sedang
        // dipilih di atas) dan bulanan (Jan-Des tahun yang sedang dipilih).
        // Dropdown "Semua Barber" (gabungan) / satu barber tertentu -- daftar
        // barber sama seperti dropdown "Service Bulan Ini" di atas (barber
        // aktif dari data.per_barber, tidak ada yang di-hardcode).
        const grafikCard = MugenUI.el("div", { class: "card" });
        const grafikHeader = MugenUI.el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" });
        grafikHeader.appendChild(MugenUI.el("h2", { style: "margin:0;" }, "Grafik Pendapatan"));
        const selBarberGrafik = MugenUI.el("select", { style: "max-width:220px;" });
        selBarberGrafik.appendChild(MugenUI.el("option", { value: "" }, "Semua Barber"));
        for (const r of data.per_barber) {
          selBarberGrafik.appendChild(MugenUI.el("option", { value: String(r.barber.id) }, r.barber.nama));
        }
        grafikHeader.appendChild(selBarberGrafik);
        grafikCard.appendChild(grafikHeader);

        grafikCard.appendChild(MugenUI.el("h3", { style: "margin-bottom:4px;" },
          `Harian — ${MugenUI.namaBulan(bulan)} ${tahun}`));
        grafikCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:6px;" },
          "Komisi + Tips + Uang Harian per tanggal. Bonus Customer tidak diikutkan di sini karena itu " +
          "perhitungan bulanan, bukan harian (lihat grafik Bulanan di bawah)."));
        const grafikHarianBox = MugenUI.el("div");
        grafikCard.appendChild(grafikHarianBox);

        grafikCard.appendChild(MugenUI.el("h3", { style: "margin-bottom:4px;margin-top:20px;" }, `Bulanan — ${tahun}`));
        grafikCard.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-bottom:6px;" },
          "Total Pendapatan penuh (Komisi + Tips + Uang Harian + Bonus Customer) per bulan."));
        const grafikBulananBox = MugenUI.el("div");
        grafikCard.appendChild(grafikBulananBox);

        body.appendChild(grafikCard);

        async function renderGrafik() {
          grafikHarianBox.innerHTML = "Memuat...";
          grafikBulananBox.innerHTML = "Memuat...";
          const barberIdGrafik = selBarberGrafik.value;
          const qsBarber = barberIdGrafik ? `&barber_id=${barberIdGrafik}` : "";
          try {
            const [harian, bulananData] = await Promise.all([
              MugenApi.get(`/api/dashboard/owner/grafik-harian?tahun=${tahun}&bulan=${bulan}${qsBarber}`, { useCache: true }),
              MugenApi.get(`/api/dashboard/owner/grafik-bulanan?tahun=${tahun}${qsBarber}`, { useCache: true }),
            ]);
            grafikHarianBox.innerHTML = "";
            grafikHarianBox.appendChild(MugenUI.barChart(
              harian.map((h) => ({ value: h.pendapatan, tanggal: h.tanggal })),
              { xLabel: (d) => String(d.tanggal), yFormat: MugenUI.formatRupiah },
            ));
            grafikBulananBox.innerHTML = "";
            grafikBulananBox.appendChild(MugenUI.barChart(
              bulananData.map((b) => ({ value: b.pendapatan, bulan: b.bulan })),
              { xLabel: (d) => MugenUI.namaBulan(d.bulan).slice(0, 3), yFormat: MugenUI.formatRupiah },
            ));
          } catch (e) {
            grafikHarianBox.innerHTML = "";
            grafikBulananBox.innerHTML = "";
            grafikHarianBox.appendChild(MugenUI.el("div", {}, e.message));
          }
        }
        selBarberGrafik.addEventListener("change", () => MugenUI.withLoading(renderGrafik));
        renderGrafik();
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.el("div", { class: "card" }, e.message));
      }
    }

    selBulan.addEventListener("change", () => { bulan = Number(selBulan.value); MugenUI.withLoading(load); });
    selTahun.addEventListener("change", () => { tahun = Number(selTahun.value); MugenUI.withLoading(load); });
    load();
  }

  return { render };
})();
