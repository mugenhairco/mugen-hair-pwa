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

    function cardNumber(label, value) {
      return MugenUI.el("div", { class: "card" }, [
        MugenUI.el("h2", {}, label),
        MugenUI.el("div", { class: "big-number" }, String(value)),
      ]);
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
          cardNumber("Total Customer", t.jumlah_customer),
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
