// pages/pos.js — Menu BARU "Point of Sale" (Kasir walk-in).
// Dua tab: "Kasir" (alur Barber/Produk -> Service -> Payment -> Pembayaran
// Berhasil, pilihan Barber/Service/Produk INSTAN tanpa loading -- seluruh
// data pengaturan di-fetch SEKALI di awal, pola SAMA PERSIS wizard booking
// publik di book_public.js) dan "Transaksi Hari Ini" (gabungan booking
// online yang sudah lunas + transaksi Kasir hari itu, lihat routers/pos.py::
// transaksi_hari_ini()). Metode pembayaran (QRIS manual/Payment Gateway/
// Cash) reuse TOTAL konfigurasi yang sama dipakai booking publik (lihat
// booking_db.get_payment_settings()) -- SATU toggle metode_aktif dibagi
// bersama Booking & POS, lihat routers/pos.py::METODE_POS_VALID. Kalau
// cuma SATU metode yang aktif, Kasir TIDAK dipaksa memilih (langsung
// dipakai, lihat renderPayment()).
//
// PERMINTAAN Owner: KEDUA tab TIDAK PERNAH loading lagi setelah pemuatan
// PERTAMA di satu sesi -- lihat cache module-level (_cachePengaturan/
// _cacheTransaksiHariIni) & _suntikTransaksiBaru() di bawah ini untuk
// arsitektur lengkapnya (Transaksi Hari Ini diupdate LANGSUNG begitu satu
// transaksi POS lunas, TANPA fetch ulang ke server sama sekali).

const PagePos = (() => {
  // PERMINTAAN Owner: tab "Kasir" & "Transaksi Hari Ini" TIDAK boleh
  // menunggu loading tiap dibuka/pindah tab -- cache di LUAR render()
  // (module-level, bertahan lintas pindah tab/menu SELAMA SPA tidak
  // reload, pola SAMA seperti produk.js/rekap.js::_cacheTerakhir).
  //
  // "pos_kasir" (pengaturan: barber/service/produk/payment settings) pakai
  // flag "halamanKotor" (lihat state.js) HANYA secara LOKAL di sini --
  // SENGAJA TIDAK didaftarkan di hook mutasi generik api.js (endpoint POS
  // sendiri -- buat transaksi/bayar/batalkan -- JUGA mutasi; kalau ikut
  // terdaftar di sana, SATU checkout akan langsung menandai cache ini
  // kotor lagi & memaksa loading di checkout berikutnya, menggagalkan
  // tujuan "tidak ada loading" untuk pemakaian paling umum). Praktisnya:
  // dimuat SEKALI per sesi (default "kotor" sebelum pernah dimuat, lalu
  // ditandai "bersih" & TIDAK PERNAH kotor lagi sampai SPA reload total).
  //
  // "pos_transaksi" (Transaksi Hari Ini): checkout/verifikasi/hapus booking
  // SESI INI SENDIRI tetap TIDAK pernah memicu loading ulang -- begitu
  // lunas, barisnya langsung DISUNTIKKAN ke cache ini (_suntikTransaksiBaru()/
  // suntikBookingLunas()/hapusBookingDariPos(), optimistic update, TANPA
  // fetch ulang), SEGERA diikuti tandaiHalamanBersih("pos_transaksi") supaya
  // flag kotor yang otomatis ditulis mutasi POS/Booking (default konservatif
  // di api.js, SEKARANG mendaftarkan "pos_transaksi") langsung dinetralkan
  // lagi. BUGFIX (dilaporkan Owner, "tidak menyuntik data diam-diam kalau
  // ada user LAIN yang input"): yang BENAR-BENAR berubah di sini -- "pos_
  // transaksi" SEKARANG ikut didaftarkan di FLAG_HALAMAN_SEMUA (api.js),
  // jadi mutasi dari mana pun SELAIN jalur suntik di atas (termasuk dari
  // device/sesi LAIN yang backend-nya sudah tahu, tapi dirty-flag di
  // localStorage sendiri cuma per-BROWSER, tidak lintas device real-time)
  // membuat render() berikutnya di DEVICE INI fetch ulang, bukan cache
  // selamanya seperti sebelumnya. Hapus baris (kolomAksi()) TETAP fetch
  // ulang penuh (butuh angka stok/Rekap yang benar-benar baru dari server,
  // tidak bisa dihitung sendiri di frontend).
  let _cachePengaturan = null; // { userId, data }
  let _cacheTransaksiHariIni = null; // { userId, tanggal, data }

  // FITUR BARU Draft POS (PERMINTAAN Owner): kasir siapkan Barber+Nama
  // Customer LEBIH AWAL, sebelum customer-nya benar-benar siap bayar --
  // lihat pos_draft_db.py untuk arsitektur backend lengkap. Cache array
  // draft, TERSENDIRI dari _cachePengaturan (yang SENGAJA tidak pernah
  // ditandai kotor, lihat catatan di atas) -- "pos_draft" didaftarkan di
  // FLAG_HALAMAN_SEMUA (api.js) persis seperti "pos_transaksi", supaya
  // draft yang dibuat/dihapus dari DEVICE LAIN saat tab Kasir di device
  // ini SEDANG TIDAK terbuka tetap ter-refresh begitu tab Kasir dibuka
  // lagi (push diam-diam HANYA sampai kalau #/pos sedang terbuka, lihat
  // app.js) -- bukan cuma mengandalkan push real-time semata.
  let _cacheDraftList = null; // array baris draft

  // Pointer suntik-diam-diam utk seksi Draft, pola SAMA PERSIS
  // _transaksiHariIniTampilUlang -- diisi saat seksi Draft tab Kasir
  // dirender, direset null di renderBody() begitu pindah tab/menu.
  let _draftTampilUlang = null;

  // Dipanggil app.js begitu push "pos_draft_berubah" masuk -- `daftarBaru`
  // SELALU full list draft terbaru tenant ini (lihat pos_draft_db.py::
  // _kirim_notifikasi_push_draft_berubah()), method PUBLIC (page lain
  // lazy-loaded, lihat page_loader.js).
  function suntikDraftBerubah(daftarBaru) {
    if (!daftarBaru) return;
    _cacheDraftList = daftarBaru;
    MugenState.tandaiHalamanBersih("pos_draft");
    if (typeof _draftTampilUlang === "function") _draftTampilUlang();
  }

  // FITUR Notifikasi Push "Transaksi POS Baru" -> suntik diam-diam REAL-
  // TIME (PERMINTAAN Owner, "kerjakan dengan teliti" -- lanjutan BUGFIX
  // "pos_transaksi" di atas, yang HANYA menjamin tab ini fetch ulang
  // begitu dibuka/dipindah-balik lagi, bukan real-time selama tab SEDANG
  // dilihat). Pola SAMA PERSIS pages/booking.js::_bookingSuntikBaris --
  // diisi renderTransaksiHariIniTab() HANYA saat tab itu yang sedang aktif
  // (null kalau tab aktif sekarang "Kasir"), dipanggil suntikTransaksiLunas()
  // di bawah supaya baris baru dari CHECKOUT DEVICE LAIN langsung tampil
  // di DOM yang SEDANG terlihat, bukan cuma diam-diam masuk ke cache untuk
  // ditampilkan "nanti" begitu tab-nya dibuka lagi.
  let _transaksiHariIniTampilUlang = null;

  // Dipanggil app.js begitu push "pos_transaksi_lunas" masuk (lihat
  // catatan push_service.py/pos_db.py::_kirim_notifikasi_push_pos_lunas())
  // -- `pos` baris POS lengkap (SAMA PERSIS bentuk yang sudah dipakai
  // _suntikTransaksiBaru() untuk checkout sesi sendiri), method PUBLIC
  // (page lain lazy-loaded, lihat page_loader.js).
  function suntikTransaksiLunas(pos) {
    _suntikTransaksiBaru(pos);
    if (typeof _transaksiHariIniTampilUlang === "function") _transaksiHariIniTampilUlang();
  }

  function _suntikTransaksiBaru(pos) {
    if (!_cacheTransaksiHariIni || !pos) return;
    if (pos.tanggal !== _cacheTransaksiHariIni.tanggal) return; // beda tanggal (jaga2 lewat tengah malam) -- biarkan, nanti fetch fresh saat tab dibuka utk tanggal itu
    // BUGFIX (lihat catatan "pos_transaksi" di api.js): checkout SESI INI
    // SENDIRI -- tandai "bersih" lagi SEGERA setelah suntik, supaya flag
    // kotor otomatis dari mutasi POST /api/pos/transaksi (default
    // konservatif, lihat api.js) tidak memicu loading ulang yang tidak
    // perlu untuk aksinya sendiri.
    MugenState.tandaiHalamanBersih("pos_transaksi");
    const data = _cacheTransaksiHariIni.data;
    for (const b of pos.daftar_barber || []) {
      if (!b.daftar_service || !b.daftar_service.length) continue;
      data.service.push({
        sumber: "pos", pos_id: pos.id, jam: pos.jam, barber_id: b.barber_id, nama_barber: b.nama,
        daftar_service: b.daftar_service.map((s) => s.nama).join(", "),
        nominal: b.daftar_service.reduce((sum, s) => sum + s.harga, 0),
        tips: b.tips,
      });
    }
    for (const p of pos.daftar_produk || []) {
      data.produk.push({
        sumber: "pos", pos_id: pos.id, jam: pos.jam, nama_produk: p.nama,
        jumlah: p.jumlah, nominal: p.harga_satuan * p.jumlah,
      });
    }
    data.service.sort((a, c) => (a.jam < c.jam ? -1 : a.jam > c.jam ? 1 : 0));
    data.produk.sort((a, c) => (a.jam < c.jam ? -1 : a.jam > c.jam ? 1 : 0));
    data.rincian_metode = data.rincian_metode || {};
    data.rincian_metode[pos.metode_pembayaran] = (data.rincian_metode[pos.metode_pembayaran] || 0) + pos.total_harga;
    data.total_keseluruhan = (data.total_keseluruhan || 0) + pos.total_harga;
  }

  // FITUR Booking Mandiri (PERMINTAAN Owner): booking (sumber apa pun --
  // Booking Mandiri MAUPUN List Booking yang sudah ada) yang baru jadi
  // LUNAS ikut disuntik ke cache ini, bentuk baris SAMA PERSIS yang
  // dihasilkan backend (pos_db.get_transaksi_hari_ini() -- UNION booking
  // "terverifikasi" + pos_transaksi "lunas", lihat catatan modul), supaya
  // tidak ada cabang render terpisah di tampilan untuk baris "sumber:
  // booking" yang disuntik vs yang datang dari fetch biasa. Dipanggil
  // pages/booking.js (BUKAN dari sini -- method PUBLIC, page lain lazy-
  // loaded lihat page_loader.js) begitu booking jadi lunas.
  function suntikBookingLunas(booking) {
    if (!_cacheTransaksiHariIni || !booking) return;
    if (booking.status_pembayaran !== "terverifikasi") return;
    // BUGFIX (lihat catatan "pos_transaksi" di api.js) -- sama seperti
    // _suntikTransaksiBaru() di atas.
    MugenState.tandaiHalamanBersih("pos_transaksi");
    const data = _cacheTransaksiHariIni.data;
    data.rincian_metode = data.rincian_metode || {};
    // FITUR Rekonsiliasi Pembayaran Booking (PERMINTAAN Owner): uang yang
    // diterima HARI INI (saat verifikasi/"Sudah Bayar" ini terjadi) SELALU
    // masuk Total Keseluruhan/Rincian Pembayaran hari ini, APA PUN tanggal
    // LAYANAN booking-nya (lihat catatan panjang di pos_db.
    // get_transaksi_hari_ini()) -- beda dari daftar Service (appointment
    // list) di bawah yang TETAP cuma tampil kalau tanggal layanannya
    // PERSIS hari ini.
    data.rincian_metode[booking.metode_pembayaran] = (data.rincian_metode[booking.metode_pembayaran] || 0) + booking.total_harga;
    data.total_keseluruhan = (data.total_keseluruhan || 0) + booking.total_harga;
    if (booking.tanggal !== _cacheTransaksiHariIni.tanggal) {
      // Dibayar hari ini, TAPI layanannya bukan hari ini -- tidak masuk
      // daftar Service (appointment list hari ini tetap murni tanggal
      // layanan), cukup baris penyesuaian "+" merah yang menjelaskan
      // kenapa Total Keseluruhan bertambah.
      data.penyesuaian = data.penyesuaian || [];
      data.penyesuaian.push({
        arah: "tambah", nominal: booking.total_harga, booking_id: booking.id,
        label: `${booking.customer_nama || booking.nama_barber} -- booking tanggal ${booking.tanggal}`,
      });
      return;
    }
    // Guard idempoten -- hindari baris dobel kalau (jarang) dipanggil 2x
    // untuk booking yang sama (mis. klik dobel tombol Verifikasi/Sudah Bayar).
    if (data.service.some((s) => s.sumber === "booking" && s.booking_id === booking.id)) return;
    data.service.push({
      sumber: "booking", booking_id: booking.id, jam: booking.jam_mulai,
      barber_id: booking.barber_id, nama_barber: booking.nama_barber,
      daftar_service: booking.daftar_service, nominal: booking.total_harga,
      nama_customer: booking.customer_nama,
    });
    data.service.sort((a, c) => (a.jam < c.jam ? -1 : a.jam > c.jam ? 1 : 0));
  }

  // BUGFIX "Transaksi Hari Ini POS tidak langsung update saat booking yang
  // SUDAH LUNAS dihapus dari List Booking" (PERMINTAAN Owner): kebalikan
  // suntikBookingLunas() di atas -- backend (booking_db.hapus_booking())
  // SUDAH benar membangun ulang baris transaksi barber+tanggal itu begitu
  // booking terverifikasi dihapus, tapi cache module-level ini (kalau tab
  // "Transaksi Hari Ini" sedang/pernah dibuka sesi ini) tidak pernah
  // diberitahu, jadi baris lama nyangkut sampai F5. Dipanggil
  // pages/booking.js SETELAH hapus booking sukses, dengan data booking
  // (baris tabel `r`, SUDAH berisi metode_pembayaran/total_harga/tanggal/
  // daftar_service -- lihat booking_db.get_booking_list()) SEBELUM baris
  // itu benar-benar dihapus dari server.
  function hapusBookingDariPos(booking) {
    if (!_cacheTransaksiHariIni || !booking) return;
    if (booking.status_pembayaran !== "terverifikasi") return; // belum lunas -- tidak pernah ikut disuntik, tidak ada yang perlu dibersihkan
    // BUGFIX (lihat catatan "pos_transaksi" di api.js) -- sama seperti
    // _suntikTransaksiBaru() di atas.
    MugenState.tandaiHalamanBersih("pos_transaksi");
    const data = _cacheTransaksiHariIni.data;
    data.rincian_metode = data.rincian_metode || {};
    data.rincian_metode[booking.metode_pembayaran] = (data.rincian_metode[booking.metode_pembayaran] || 0) - booking.total_harga;
    data.total_keseluruhan = (data.total_keseluruhan || 0) - booking.total_harga;
    if (booking.tanggal !== _cacheTransaksiHariIni.tanggal) {
      if (data.penyesuaian) {
        const idxPenyesuaian = data.penyesuaian.findIndex((p) => p.booking_id === booking.id);
        if (idxPenyesuaian >= 0) data.penyesuaian.splice(idxPenyesuaian, 1);
      }
      return;
    }
    const idxService = data.service.findIndex((s) => s.sumber === "booking" && s.booking_id === booking.id);
    if (idxService >= 0) data.service.splice(idxService, 1);
  }

  // FITUR "Rekap tidak refresh, cuma tambah baris diam-diam" (PERMINTAAN
  // Owner): dulu HANYA pernah disambungkan ke Input Data (lihat komentar
  // lama di routers/rekap.py::rekap_transaksi_baris(), yang bahkan
  // menyebut "pola sama Transaksi Hari Ini POS" padahal belum pernah
  // benar-benar dipakai POS) -- akibatnya menu Rekap SELALU skeleton
  // loading begitu dibuka setelah ada transaksi POS baru, walau sudah
  // terbuka sesi ini. `ids`: hasil.rekap_transaksi_ids dari respons
  // bayar-cash/verifikasi/status (PAID) -- lihat pos_db.py::
  // get_rekap_transaksi_ids(). Best-effort, gagal diam-diam (baris baru
  // TETAP kelihatan begitu Rekap dibuka/di-refresh biasa).
  function suntikKeRekap(ids) {
    if (!ids || !ids.length) return;
    if (typeof PageRekap === "undefined" || typeof PageRekap.suntikBarisTransaksi !== "function") return;
    for (const id of ids) {
      MugenApi.get(`/api/rekap/transaksi/baris/${id}`)
        .then((baris) => PageRekap.suntikBarisTransaksi(baris))
        .catch(() => {});
    }
  }

  async function render(root) {
    root.innerHTML = "";
    root.appendChild(MugenUI.pageTitle("Point of Sale", MugenIcons.pos));

    const levelPos = await MugenMenuAccess.get("pos");
    if (levelPos === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const user = MugenState.getUser();
    const isOwner = user.role === "admin";
    const TAB_IZIN = { "Kasir": "izin_pos_kelola", "Transaksi Hari Ini": "izin_pos_lihat" };
    const ALL_TABS = Object.keys(TAB_IZIN);
    let tabsLolos = ALL_TABS;
    if (!isOwner) {
      const hasilIzin = await Promise.all(ALL_TABS.map((t) => MugenMenuAccess.has(TAB_IZIN[t])));
      tabsLolos = ALL_TABS.filter((_, i) => hasilIzin[i]);
    }
    if (!tabsLolos.length) {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }
    const tabItems = tabsLolos.map((t) => ({ key: t, label: t }));
    const body = MugenUI.el("div");

    async function renderBody(activeTab) {
      body.innerHTML = "";
      // Reset diawal -- tab lama (kalau ada) tidak lagi aktif, lihat
      // catatan _transaksiHariIniTampilUlang di atas (pola sama
      // pages/booking.js::_bookingSuntikBaris).
      _transaksiHariIniTampilUlang = null;
      _draftTampilUlang = null;
      if (activeTab === "Kasir") await renderKasirTab(body);
      else await renderTransaksiHariIniTab(body);
    }

    const tabsCtl = MugenUI.tabs(tabItems, { onChange: renderBody });
    root.appendChild(tabsCtl.bar);
    root.appendChild(body);
    requestAnimationFrame(tabsCtl.moveIndicator);
    await renderBody(tabsCtl.active);
  }

  // ================= TAB: KASIR =================
  async function renderKasirTab(body) {
    const userId = MugenState.getUser().id;
    if (_cachePengaturan && _cachePengaturan.userId === userId && !MugenState.halamanPerluRefresh("pos_kasir")) {
      jalankanWizardKasir(body, _cachePengaturan.data);
      return;
    }
    body.appendChild(MugenUI.skeleton("card", { lines: 4 }));
    let pengaturan;
    try {
      pengaturan = await MugenApi.get("/api/pos/pengaturan");
    } catch (e) {
      body.innerHTML = "";
      body.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
      return;
    }
    body.innerHTML = "";
    _cachePengaturan = { userId, data: pengaturan };
    MugenState.tandaiHalamanBersih("pos_kasir");
    jalankanWizardKasir(body, pengaturan);
  }

  // Wizard Kasir -- SELURUH data (barber/service/produk/payment settings)
  // SUDAH ada di `pengaturan` sejak awal (satu fetch di renderKasirTab() di
  // atas) -- pindah antar fase di bawah ini TIDAK PERNAH menunggu network
  // lagi KECUALI saat benar-benar submit pembayaran (tombol "Buat
  // Transaksi"/"Payment Diterima"), pola SAMA PERSIS wizard booking publik.
  function jalankanWizardKasir(bodyOuter, pengaturan) {
    // FITUR BARU Draft POS: seksi "Draft" PERSISTEN di atas wizard biasa --
    // TIDAK ikut terhapus setiap gantiFase() (yang hanya membersihkan
    // wizardBox, bukan seluruh bodyOuter) supaya kartu draft tetap
    // kelihatan walau kasir sedang di fase manapun dari alur checkout
    // biasa (non-draft). `body` di-shadow ke wizardBox di bawah --
    // SELURUH renderPilih()/renderPayment()/dst TETAP memakai
    // `body.appendChild` apa adanya, tidak perlu disentuh satu per satu.
    const draftBox = MugenUI.el("div", { class: "pos-draft-section" });
    const wizardBox = MugenUI.el("div");
    bodyOuter.appendChild(draftBox);
    bodyOuter.appendChild(wizardBox);
    const body = wizardBox;
    renderDraftSection(draftBox, pengaturan);

    const metodeAktif = pengaturan.metode_aktif || [];
    const metodeNama = pengaturan.metode_nama || {};
    const metodeInstruksi = pengaturan.metode_instruksi || {};
    // FITUR Keranjang Multi-Barber (PERMINTAAN Owner -- "anak cukur Barber
    // A, bapak cukur Barber B, mau 1 kali scan" & "tips manual per
    // barber"): `keranjang` = baris yang SUDAH ditambahkan lewat "+ Tambah
    // ke Keranjang" ({barberId, serviceIds: Set, tips}), `form*` = entri
    // yang SEDANG diisi tapi BELUM ditambahkan -- supaya kasus paling
    // umum (1 customer saja) tetap secepat alur lama: langsung "Lanjut ke
    // Payment" TANPA klik "Tambah ke Keranjang" dulu (form yang masih
    // terisi otomatis dianggap baris terakhir, lihat kumpulkanJasaItems()).
    const state = {
      keranjang: [], formBarberId: null, formServiceIds: new Set(), formTips: 0,
      produk: {},
      metode: null, channel: null, bankCode: null, transaksi: null,
    };
    let fase = "pilih";

    function formTerisi() {
      return state.formBarberId !== null && state.formServiceIds.size > 0;
    }

    // Keranjang + (form yang masih terisi, kalau ada) -- INI yang akan
    // benar-benar dikirim/ditagihkan kalau "Lanjut ke Payment" diklik
    // sekarang.
    function kumpulkanJasaItems() {
      const items = state.keranjang.map((k) => ({
        barberId: k.barberId, serviceIds: Array.from(k.serviceIds), tips: k.tips,
      }));
      if (formTerisi()) {
        items.push({ barberId: state.formBarberId, serviceIds: Array.from(state.formServiceIds), tips: state.formTips });
      }
      return items;
    }

    function totalHarga() {
      let total = 0;
      for (const item of kumpulkanJasaItems()) {
        for (const sid of item.serviceIds) {
          const s = pengaturan.services.find((x) => x.id === sid);
          if (s) total += s.harga;
        }
        total += item.tips || 0;
      }
      for (const pid of Object.keys(state.produk)) {
        const qty = state.produk[pid];
        if (qty > 0) {
          const p = pengaturan.produk.find((x) => x.id === Number(pid));
          if (p) total += p.harga_jual * qty;
        }
      }
      return total;
    }

    function barisTotal() {
      return MugenUI.el("div", { style: "display:flex;justify-content:space-between;font-weight:700;" }, [
        MugenUI.el("span", {}, "Total Payment"), MugenUI.el("span", {}, MugenUI.formatRupiah(totalHarga())),
      ]);
    }

    // PERMINTAAN Owner: begitu "Lanjut ke Payment" diklik, tampilkan
    // rincian lengkap ala nota/struk -- per barber (nama + tiap service +
    // harganya + tips-nya), lalu produk -- TETAP lengkap walau barber
    // atau service-nya lebih dari 2 (tidak diringkas/dipotong).
    function buatRincianNota() {
      const baris = [];
      for (const item of (state.jasaItemsFinal || [])) {
        const barber = pengaturan.barbers.find((b) => b.id === item.barberId);
        const namaBarber = barber ? barber.nama : "(barber terhapus)";
        baris.push(MugenUI.el("div", { class: "pos-nota-barber" }, namaBarber));
        for (const sid of item.serviceIds) {
          const s = pengaturan.services.find((x) => x.id === sid);
          if (!s) continue;
          baris.push(MugenUI.el("div", { class: "pos-nota-row" }, [
            MugenUI.el("span", {}, s.nama), MugenUI.el("span", {}, MugenUI.formatRupiah(s.harga)),
          ]));
        }
        if (item.tips > 0) {
          baris.push(MugenUI.el("div", { class: "pos-nota-row pos-nota-tips" }, [
            MugenUI.el("span", {}, `Tips untuk ${namaBarber}`), MugenUI.el("span", {}, MugenUI.formatRupiah(item.tips)),
          ]));
        }
      }
      const idsProduk = Object.keys(state.produk).map(Number).filter((id) => state.produk[id] > 0);
      if (idsProduk.length) {
        baris.push(MugenUI.el("div", { class: "pos-nota-barber" }, "Produk"));
        for (const pid of idsProduk) {
          const p = pengaturan.produk.find((x) => x.id === pid);
          if (!p) continue;
          const qty = state.produk[pid];
          baris.push(MugenUI.el("div", { class: "pos-nota-row" }, [
            MugenUI.el("span", {}, `${p.nama} ×${qty}`), MugenUI.el("span", {}, MugenUI.formatRupiah(p.harga_jual * qty)),
          ]));
        }
      }
      if (!baris.length) return null;
      return MugenUI.el("div", { class: "pos-nota card" }, [
        MugenUI.el("div", { class: "pos-nota-judul" }, "Rincian Pesanan"),
        ...baris,
      ]);
    }

    function resetState() {
      state.keranjang = []; state.formBarberId = null; state.formServiceIds = new Set(); state.formTips = 0;
      state.produk = {};
      state.metode = null; state.channel = null; state.bankCode = null; state.transaksi = null;
      fase = "pilih";
    }

    function gantiFase() {
      body.innerHTML = "";
      if (fase === "pilih") renderPilih();
      else if (fase === "payment") renderPayment();
      else if (fase === "menunggu_manual") renderMenungguManual();
      else if (fase === "waiting") renderWaitingGateway();
      else if (fase === "bayar_cash") renderBayarCash();
      else renderSelesai();
    }

    // ---- fase "pilih": Keranjang multi-barber (Barber+Service+Tips per
    // entri) + Produk (tetap tenant-wide, TIDAK terikat barber manapun,
    // satu checkout bisa mencampur Service + Produk -- PERMINTAAN Owner
    // "satu kali scan untuk Service + Produk") ----
    function renderPilih() {
      body.appendChild(MugenUI.el("h2", {}, "Pilih Barber, Service & Produk"));
      const errorBox = MugenUI.el("div", { class: "login-error" });

      // --- Keranjang (baris yang sudah ditambahkan) ---
      const keranjangBox = MugenUI.el("div");
      body.appendChild(keranjangBox);
      function renderKeranjang() {
        keranjangBox.innerHTML = "";
        if (!state.keranjang.length) return;
        keranjangBox.appendChild(MugenUI.el("label", {}, "Keranjang"));
        for (let i = 0; i < state.keranjang.length; i++) {
          const k = state.keranjang[i];
          const barber = pengaturan.barbers.find((b) => b.id === k.barberId);
          const namaService = Array.from(k.serviceIds)
            .map((sid) => pengaturan.services.find((s) => s.id === sid))
            .filter(Boolean).map((s) => s.nama).join(", ");
          const btnHapus = MugenUI.el("button", { type: "button" }, "Hapus");
          btnHapus.addEventListener("click", () => {
            state.keranjang.splice(i, 1);
            renderKeranjang(); renderTotal();
          });
          keranjangBox.appendChild(MugenUI.el("div", {
            class: "card", style: "display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;",
          }, [
            MugenUI.el("div", {}, [
              MugenUI.el("div", { style: "font-weight:700;" }, barber ? barber.nama : "(barber terhapus)"),
              MugenUI.el("div", { class: "subtitle" }, namaService + (k.tips > 0 ? ` — Tips ${MugenUI.formatRupiah(k.tips)}` : "")),
            ]),
            btnHapus,
          ]));
        }
      }
      renderKeranjang();

      // --- Form entri (barber+service+tips yang SEDANG diisi) ---
      // PERMINTAAN Owner: Barber jadi dropdown modern (MugenUI.
      // dropdownSelect(), lihat ui.js), Service jadi card yang bisa
      // diklik seluruh areanya (menggantikan checkbox kecil).
      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Barber"));
      const barberOpsi = pengaturan.barbers.map((b) => ({ value: b.id, label: b.nama }));
      const dropdownBarber = MugenUI.dropdownSelect(barberOpsi, {
        value: state.formBarberId, placeholder: "-- Pilih Barber --",
        onChange: (v) => { state.formBarberId = v; renderTotal(); },
      });
      body.appendChild(dropdownBarber.el);

      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Service"));
      const serviceGrid = MugenUI.el("div", { class: "pos-service-grid" });
      for (const s of pengaturan.services) {
        const card = MugenUI.el("button", {
          type: "button", class: "pos-service-card" + (state.formServiceIds.has(s.id) ? " selected" : ""),
        }, [
          MugenUI.el("div", { class: "pos-service-card-nama" }, s.nama),
          MugenUI.el("div", { class: "pos-service-card-harga" }, MugenUI.formatRupiah(s.harga)),
          MugenUI.el("div", { class: "pos-service-card-check" }, "✓"),
        ]);
        card.addEventListener("click", () => {
          if (state.formServiceIds.has(s.id)) state.formServiceIds.delete(s.id);
          else state.formServiceIds.add(s.id);
          card.classList.toggle("selected");
          renderTotal();
        });
        serviceGrid.appendChild(card);
      }
      body.appendChild(serviceGrid);
      if (!pengaturan.services.length) body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada service aktif."));

      // Tips: manual oleh kasir, PER BARBER (PERMINTAAN Owner -- kasir
      // yang isi sendiri, BUKAN dihitung/dibagi otomatis sistem).
      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Tips untuk barber ini (opsional)"));
      const inputTips = MugenUI.el("input", { type: "text", value: MugenUI.nilaiTampilAngka(state.formTips), style: "max-width:160px;" });
      inputTips.addEventListener("input", () => {
        state.formTips = Math.max(0, MugenUI.parseAngka(inputTips.value));
        renderTotal();
      });
      MugenUI.attachNumericKeypad(inputTips, { rupiah: true });
      body.appendChild(inputTips);

      // PERMINTAAN Owner: tombol ini jadi ikon keranjang SAJA, tanpa teks
      // (lihat icons.js::MugenIcons.keranjang, style polos TANPA warna/fill
      // -- konvensi SAMA PERSIS tombol Download QRIS di book_public.js).
      const btnTambah = MugenUI.el("button", {
        type: "button", class: "pos-tambah-keranjang-btn", style: "margin-top:12px;",
        "aria-label": "Tambah ke Keranjang", title: "Tambah ke Keranjang",
      }, MugenUI.el("span", { html: MugenIcons.keranjang }));
      btnTambah.addEventListener("click", () => {
        errorBox.textContent = "";
        if (!state.formBarberId) { errorBox.textContent = "Pilih Barber terlebih dahulu."; return; }
        if (!state.formServiceIds.size) { errorBox.textContent = "Pilih minimal satu Service terlebih dahulu."; return; }
        state.keranjang.push({ barberId: state.formBarberId, serviceIds: new Set(state.formServiceIds), tips: state.formTips });
        state.formBarberId = null; state.formServiceIds = new Set(); state.formTips = 0;
        fase = "pilih"; gantiFase(); // render ulang penuh -- form & select perlu kembali kosong
      });
      body.appendChild(btnTambah);

      // --- Produk (terpisah, tenant-wide, TIDAK terikat barber manapun) ---
      // PERMINTAAN Owner: dropdown pencarian multi-pilih (bukan daftar qty
      // satu-satu) -- tombol +/- di dalamnya mengatur kuantitas TANPA
      // memicu keyboard apa pun, dropdown TIDAK tertutup tiap satu produk
      // dipilih (tutup hanya lewat klik luar/tombol Tutup). Ringkasan
      // produk yang sudah terpilih tetap tampil di luar dropdown supaya
      // kasir bisa lihat/ubah qty tanpa membuka dropdown lagi.
      body.appendChild(MugenUI.el("label", { style: "margin-top:20px;" }, "Produk"));

      function buatQtyStepper(p) {
        const qty = state.produk[p.id] || 0;
        const btnMinus = MugenUI.el("button", { type: "button", class: "pos-qty-btn" }, "−");
        const nilai = MugenUI.el("span", { class: "pos-qty-value" }, String(qty));
        const btnPlus = MugenUI.el("button", { type: "button", class: "pos-qty-btn" }, "+");
        btnMinus.disabled = qty <= 0;
        btnPlus.disabled = qty >= p.stok;
        btnMinus.addEventListener("click", (e) => { e.stopPropagation(); ubahQtyProduk(p, -1); });
        btnPlus.addEventListener("click", (e) => { e.stopPropagation(); ubahQtyProduk(p, 1); });
        return MugenUI.el("div", { class: "pos-qty-stepper" }, [btnMinus, nilai, btnPlus]);
      }

      const produkTerpilihBox = MugenUI.el("div", { class: "pos-produk-terpilih", style: "margin-top:8px;" });
      function renderProdukTerpilih() {
        produkTerpilihBox.innerHTML = "";
        const idsTerpilih = Object.keys(state.produk).map(Number).filter((id) => state.produk[id] > 0);
        for (const pid of idsTerpilih) {
          const p = pengaturan.produk.find((x) => x.id === pid);
          if (!p) continue;
          produkTerpilihBox.appendChild(MugenUI.el("div", { class: "pos-produk-terpilih-row" }, [
            MugenUI.el("div", {}, [
              MugenUI.el("div", { class: "pos-produk-terpilih-nama" }, p.nama),
              MugenUI.el("div", { class: "pos-produk-terpilih-harga" }, `${MugenUI.formatRupiah(p.harga_jual)}/pcs`),
            ]),
            buatQtyStepper(p),
          ]));
        }
      }

      const produkListEl = MugenUI.el("div");
      function renderDaftarProdukDropdown(query) {
        produkListEl.innerHTML = "";
        const q = (query || "").trim().toLowerCase();
        // Pencarian substring fleksibel -- cocok di MANA PUN dalam nama
        // (bukan cuma awalan), tidak peka huruf besar/kecil.
        const hasil = pengaturan.produk.filter((p) => !q || p.nama.toLowerCase().includes(q));
        if (!hasil.length) {
          produkListEl.appendChild(MugenUI.el("div", { class: "mugen-dropdown-empty" }, "Produk tidak ditemukan."));
          return;
        }
        for (const p of hasil) {
          const terpilih = (state.produk[p.id] || 0) > 0;
          const row = MugenUI.el("div", { class: "pos-produk-option" + (terpilih ? " selected" : "") }, [
            MugenUI.el("div", { class: "pos-produk-option-check" }, "✓"),
            MugenUI.el("div", { class: "pos-produk-option-info" }, [
              MugenUI.el("div", { class: "pos-produk-option-nama" }, p.nama),
              MugenUI.el("div", { class: "pos-produk-option-meta" }, `${MugenUI.formatRupiah(p.harga_jual)}/pcs · stok ${p.stok}`),
            ]),
            buatQtyStepper(p),
          ]);
          row.addEventListener("click", (e) => {
            if (e.target.closest(".pos-qty-btn")) return; // tombol +/- menangani sendiri
            if (p.stok <= 0) return;
            ubahQtyProduk(p, 1); // klik baris = tambah 1 (pilih baru ATAU tambah qty kalau sudah terpilih)
            renderDaftarProdukDropdown(searchProdukInput.value);
          });
          produkListEl.appendChild(row);
        }
      }

      function ubahQtyProduk(p, delta) {
        const qtyBaru = Math.max(0, Math.min(p.stok, (state.produk[p.id] || 0) + delta));
        if (qtyBaru > 0) state.produk[p.id] = qtyBaru; else delete state.produk[p.id];
        renderProdukTerpilih();
        if (modalOverlayProduk.classList.contains("open")) renderDaftarProdukDropdown(searchProdukInput.value);
        renderTotal();
      }

      const searchProdukInput = MugenUI.el("input", {
        type: "text", class: "mugen-dropdown-search", placeholder: "Cari produk…",
      });
      searchProdukInput.addEventListener("input", () => renderDaftarProdukDropdown(searchProdukInput.value));
      const triggerProduk = MugenUI.el("button", { type: "button", class: "mugen-dropdown-trigger", style: "margin-top:10px;" }, [
        MugenUI.el("span", { class: "mugen-dropdown-trigger-label" }, "+ Tambah Produk"),
        MugenUI.el("span", { class: "mugen-dropdown-chevron" }, "⌄"),
      ]);

      // PERMINTAAN Owner: dropdown yang nempel di bawah tombol terpotong
      // batas layar (ruang scroll terlalu sempit) -- ganti jadi modal
      // floating di TENGAH layar (tinggi ~70-80% viewport) supaya daftar
      // produk (bisa banyak) punya ruang scroll yang luas & nyaman di HP
      // maupun tablet/desktop. Nempel ke document.body (BUKAN di bawah
      // #app), pola SAMA dengan overlay keypad custom, supaya position:
      // fixed benar2 tidak terpengaruh ancestor manapun. Render ulang
      // "pilih" (lihat gantiFase()) membuat instance BARU setiap kali --
      // bersihkan instance lama dulu supaya tidak menumpuk di body.
      document.querySelectorAll(".pos-produk-modal-overlay").forEach((n) => n.remove());
      const btnTutupModalProduk = MugenUI.el("button", {
        type: "button", class: "pos-produk-modal-close", "aria-label": "Tutup",
      }, "✕");
      const modalBoxProduk = MugenUI.el("div", { class: "pos-produk-modal" }, [
        MugenUI.el("div", { class: "pos-produk-modal-header" }, [
          MugenUI.el("h3", {}, "Pilih Produk"),
          btnTutupModalProduk,
        ]),
        MugenUI.el("div", { class: "pos-produk-modal-search-wrap" }, [searchProdukInput]),
        MugenUI.el("div", { class: "pos-produk-modal-list" }, [produkListEl]),
      ]);
      const modalOverlayProduk = MugenUI.el("div", { class: "pos-produk-modal-overlay" }, [modalBoxProduk]);
      document.body.appendChild(modalOverlayProduk);

      // PERMINTAAN Owner (Animasi Morphing Form): modal ini box/overlay-nya
      // PERSISTEN (dibuat sekali per renderPilih(), dibuka/ditutup berkali-
      // kali lewat toggle class .open -- BUKAN instance baru tiap panggil
      // seperti confirmModal/infoModal) -- pakai morphDariTombol() SEKALI,
      // lalu panggil buka()/tutup() berkali-kali. Style inline yang
      // dipasang buka()/tutup() otomatis menang atas CSS transform/
      // transition `.pos-produk-modal`/`.open` di bawah (style inline pada
      // elemen selalu menang atas rule stylesheet apa pun utk elemen yang
      // sama) -- jadi tidak perlu CSS tambahan apa pun di sini. Kalau null
      // (prefers-reduced-motion / tombol pemicu tidak wajar), fallback diam
      // -diam ke animasi scale+slide class-toggle yang SUDAH ADA (tidak
      // berubah dari sebelumnya).
      // BUGFIX (ketemu lewat Playwright mid-transition sampling -- rect box
      // ternyata cuma ikut CSS scale(0.97) lama, FLIP tidak pernah jalan):
      // morphDariTombol() mensyaratkan asalEl.isConnected, TAPI baris ini
      // berjalan SEBELUM triggerProduk di-append ke DOM (lihat
      // `body.appendChild(triggerProduk)` jauh di bawah) -- dipanggil di
      // sini, asalEl.isConnected selalu false, morphDariTombol() selalu
      // balas null diam-diam. Inisialisasi LAZY di buka() pertama kali
      // (saat itu sudah pasti attached -- dipicu dari klik tombolnya
      // sendiri) supaya pengukuran rect valid.
      let morphProduk;

      function bukaModalProduk() {
        modalOverlayProduk.classList.add("open");
        searchProdukInput.value = "";
        renderDaftarProdukDropdown("");
        if (morphProduk === undefined) morphProduk = MugenUI.morphDariTombol(modalBoxProduk, triggerProduk);
        if (morphProduk) morphProduk.buka();
      }
      function tutupModalProduk() {
        modalOverlayProduk.classList.remove("open");
        if (morphProduk) morphProduk.tutup();
      }
      triggerProduk.addEventListener("click", bukaModalProduk);
      btnTutupModalProduk.addEventListener("click", tutupModalProduk);
      // Klik di overlay gelap (BUKAN di kotak modal-nya) = tutup juga --
      // perilaku standar modal, setara "klik luar" pada dropdown lama.
      modalOverlayProduk.addEventListener("pointerdown", (e) => {
        if (e.target === modalOverlayProduk) tutupModalProduk();
      });
      // Navigasi hash-router (ganti halaman) -- modal HARUS ikut hilang
      // walau nempel di body, bukan di bawah #app (pola sama dgn keypad).
      window.addEventListener("hashchange", () => modalOverlayProduk.remove(), { once: true });

      if (pengaturan.produk.length) {
        body.appendChild(triggerProduk);
        body.appendChild(produkTerpilihBox);
        renderProdukTerpilih();
      } else {
        body.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada produk aktif."));
      }

      const totalBox = MugenUI.el("div", { class: "card", style: "margin-top:12px;" });
      body.appendChild(totalBox);
      function renderTotal() {
        totalBox.innerHTML = "";
        totalBox.appendChild(barisTotal());
      }
      renderTotal();

      body.appendChild(errorBox);
      const btnLanjut = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Lanjut ke Payment");
      btnLanjut.addEventListener("click", () => {
        errorBox.textContent = "";
        const jasaItems = kumpulkanJasaItems();
        if (!jasaItems.length && !Object.keys(state.produk).length) {
          errorBox.textContent = "Pilih minimal satu Service atau Produk."; return;
        }
        // Form terisi SEBAGIAN (barber tanpa service, atau sebaliknya) --
        // bukan baris lengkap untuk diikutkan otomatis, tapi juga bukan
        // niat kosong -- minta kasir selesaikan/hapus dulu supaya tidak
        // diam-diam terlewat dari pembayaran.
        if ((state.formBarberId && !state.formServiceIds.size) || (!state.formBarberId && state.formServiceIds.size)) {
          errorBox.textContent = "Lengkapi dulu Barber & Service yang sedang diisi (atau kosongkan keduanya)."; return;
        }
        state.jasaItemsFinal = jasaItems;
        fase = "payment"; gantiFase();
      });
      body.appendChild(btnLanjut);
    }

    // ---- fase "payment": pilih metode (QRIS manual/Payment Gateway) ----
    function renderPayment() {
      body.appendChild(MugenUI.el("h2", {}, "Payment"));
      const nota = buatRincianNota();
      if (nota) body.appendChild(nota);
      body.appendChild(MugenUI.el("div", { class: "card" }, [barisTotal()]));

      const errorBox = MugenUI.el("div", { class: "login-error" });
      const metodeBox = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;margin-top:12px;" });
      const bankBox = MugenUI.el("div", { class: "bank-grid" });

      function renderBankBox() {
        bankBox.innerHTML = "";
        if (state.metode !== "gateway" || state.channel !== "va") return;
        const bankAktif = pengaturan.snap_va_bank_aktif || {};
        const kodeList = Object.keys(bankAktif);
        for (const kode of kodeList) {
          const card = MugenUI.el("button", {
            type: "button", class: "bank-card" + (state.bankCode === kode ? " selected" : ""),
          }, [MugenUI.bankLogoBadge(kode), MugenUI.el("span", {}, MugenUI.bankNamaLengkap(kode, bankAktif[kode]))]);
          card.addEventListener("click", () => {
            state.bankCode = kode;
            for (const el of bankBox.children) el.classList.remove("selected");
            card.classList.add("selected");
          });
          bankBox.appendChild(card);
        }
        if (kodeList.length === 1) state.bankCode = kodeList[0];
      }

      const opsi = [];
      for (const m of metodeAktif) {
        if (m === "gateway") {
          for (const c of (pengaturan.snap_channel_aktif || [])) {
            opsi.push({ metode: "gateway", channel: c, label: c === "va" ? "Virtual Account" : "QRIS" });
          }
        } else {
          opsi.push({ metode: m, channel: null, label: metodeNama[m] || m });
        }
      }
      // PERMINTAAN Owner: kalau cuma SATU opsi pembayaran yang tersedia
      // (satu-satunya metode aktif, dengan paling banyak satu channel),
      // JANGAN paksa Kasir memilih -- langsung pakai opsi itu, tampilkan
      // sebagai info saja (tombol Back masih bisa kembali ke "pilih").
      const satuOpsi = opsi.length === 1;
      if (!opsi.length) {
        body.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:12px;" },
          "Belum ada metode pembayaran aktif untuk Point of Sale. Hubungi Superadmin."));
      } else if (satuOpsi) {
        state.metode = opsi[0].metode; state.channel = opsi[0].channel;
        metodeBox.appendChild(MugenUI.el("div", { class: "subtitle" }, `Metode pembayaran: ${opsi[0].label}`));
        renderBankBox();
      } else {
        for (const o of opsi) {
          const dipilih = state.metode === o.metode && state.channel === o.channel;
          const btn = MugenUI.el("button", {
            type: "button", class: "book-metode-btn" + (dipilih ? " selected" : ""),
          }, o.label);
          btn.addEventListener("click", () => {
            state.metode = o.metode; state.channel = o.channel; state.bankCode = null;
            for (const el of metodeBox.children) el.classList.remove("selected");
            btn.classList.add("selected");
            renderBankBox();
          });
          metodeBox.appendChild(btn);
        }
      }
      body.appendChild(metodeBox);
      body.appendChild(bankBox);
      body.appendChild(errorBox);

      body.appendChild(MugenUI.el("div", { class: "book-nav-row" }, [
        MugenUI.el("button", { type: "button", onclick: () => { fase = "pilih"; gantiFase(); } }, "< Back"),
      ]));

      const btnBuat = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Buat Transaksi");
      btnBuat.addEventListener("click", async () => {
        errorBox.textContent = "";
        if (!state.metode) { errorBox.textContent = "Pilih metode pembayaran terlebih dahulu."; return; }
        if (state.metode === "gateway" && !state.channel) { errorBox.textContent = "Pilih VA/QRIS terlebih dahulu."; return; }
        if (state.metode === "gateway" && state.channel === "va" && !state.bankCode) {
          errorBox.textContent = "Pilih bank terlebih dahulu."; return;
        }
        try {
          const payload = {
            jasa_items: (state.jasaItemsFinal || []).map((it) => ({
              barber_id: it.barberId, service_ids: it.serviceIds, tips: it.tips || 0,
            })),
            produk_items: Object.keys(state.produk).map((pid) => ({ produk_id: Number(pid), jumlah: state.produk[pid] })),
            metode_pembayaran: state.metode,
            channel: state.metode === "gateway" ? state.channel : undefined,
            bank_code: state.metode === "gateway" && state.channel === "va" ? state.bankCode : undefined,
          };
          const hasil = await MugenUI.withButtonLoading(btnBuat, () => MugenApi.post("/api/pos/transaksi", payload));
          state.transaksi = hasil;
          fase = state.metode === "gateway" ? "waiting" : (state.metode === "cash" ? "bayar_cash" : "menunggu_manual");
          gantiFase();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      body.appendChild(btnBuat);
    }

    // ---- fase "menunggu_manual": QRIS foto (yang di-upload Superadmin) +
    // tombol "Payment Diterima" -- Kasir sendiri yang melihat notifikasi
    // pembayaran masuk ke rekening/HP toko, TIDAK ada verifikasi otomatis
    // untuk metode ini. ----
    function renderMenungguManual() {
      body.appendChild(MugenUI.el("h2", {}, "Menunggu Pembayaran (QRIS)"));
      const items = [];
      if (pengaturan.qris_url) {
        items.push(MugenUI.el("img", { src: MUGEN_API_BASE + pengaturan.qris_url, class: "book-qris-img", alt: "QRIS" }));
      } else {
        items.push(MugenUI.el("div", { class: "subtitle" }, "Foto QRIS belum diunggah Superadmin."));
      }
      items.push(MugenUI.el("div", { style: "margin-top:8px;" }, pengaturan.qris_merchant_nama || ""));
      items.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" }, metodeInstruksi.qris || ""));

      body.appendChild(MugenUI.el("div", { class: "card" }, [
        barisTotal(),
        MugenUI.el("hr"),
        MugenUI.el("div", { style: "text-align:center;" }, items),
      ]));

      const errorBox = MugenUI.el("div", { class: "login-error" });
      body.appendChild(errorBox);
      const btnTerima = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Payment Diterima");
      btnTerima.addEventListener("click", async () => {
        errorBox.textContent = "";
        try {
          const hasil = await MugenUI.withButtonLoading(btnTerima, () => MugenApi.post(`/api/pos/transaksi/${state.transaksi.id}/verifikasi`));
          state.transaksi = hasil;
          _suntikTransaksiBaru(hasil);
          suntikKeRekap(hasil.rekap_transaksi_ids);
          MugenUI.toast("Pembayaran dikonfirmasi.", "success", { force: true });
          fase = "selesai"; gantiFase();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      body.appendChild(btnTerima);
    }

    // ---- fase "waiting": Payment Gateway (QR/VA ditampilkan di layar
    // Kasir, customer scan di tempat) -- poll status + tombol "Saya Sudah
    // Bayar", TANPA countdown 15 menit (konsep itu khusus booking publik
    // yang bisa ditinggal customer; di Kasir, Kasir berdiri menyelesaikan
    // transaksi SAAT ITU JUGA). ----
    function renderWaitingGateway() {
      const r = state.transaksi;
      body.appendChild(MugenUI.el("h2", {}, "Menunggu Konfirmasi Pembayaran"));
      const statusLabelEl = MugenUI.el("div", { class: "subtitle" }, "Selesaikan pembayaran memakai info di bawah.");

      const items = [];
      if (r.channel === "va" || state.channel === "va") {
        items.push(MugenUI.el("div", { class: "subtitle" },
          r.channel_code ? `Virtual Account ${MugenUI.bankNamaLengkap(r.channel_code, null)}` : "Virtual Account"));
        items.push(MugenUI.el("div", { style: "font-size:22px;font-weight:700;letter-spacing:1px;text-align:center;margin-top:4px;" },
          r.va_number || "-"));
      } else if (r.qr_url) {
        items.push(MugenUI.el("img", { src: r.qr_url, class: "book-qris-img", alt: "QRIS" }));
      } else if (r.qr_content) {
        const btnBuka = MugenUI.el("button", { type: "button", class: "book-download-qris-btn" }, "Buka Halaman QRIS");
        btnBuka.addEventListener("click", () => window.open(r.qr_content, "_blank"));
        items.push(btnBuka);
      }

      const btnSudahBayar = MugenUI.el("button", { type: "button", style: "margin-top:12px;" }, "Saya Sudah Bayar");
      // PERMINTAAN Owner (antisipasi Kasir salah input sebelum customer
      // sempat scan & bayar): tombol Batalkan -- TIDAK ada di booking
      // publik (customer bisa ditinggal, ada countdown 15 menit terpisah),
      // tapi di Kasir kasusnya beda: kasir berdiri di situ, kalau sadar
      // salah input harus bisa langsung batalkan tanpa menunggu kedaluwarsa.
      const btnBatalkan = MugenUI.el("button", { type: "button", style: "margin-top:12px;margin-left:8px;" }, "Batalkan");
      body.appendChild(MugenUI.el("div", { class: "card" }, [
        MugenUI.el("div", { style: "text-align:center;" }, [statusLabelEl, MugenUI.el("div", {}, [btnSudahBayar, btnBatalkan])]),
        MugenUI.el("hr"),
        MugenUI.el("div", { style: "text-align:center;" }, items),
        MugenUI.el("hr"),
        barisTotal(),
      ]));

      function terapkanStatus(status) {
        if (status.status === "PAID") {
          clearInterval(pollTimer);
          _suntikTransaksiBaru(r);
          suntikKeRekap(status.rekap_transaksi_ids);
          MugenUI.toast("Pembayaran berhasil.", "success", { force: true });
          fase = "selesai"; gantiFase();
          return true;
        }
        if (["FAILED", "CANCELLED", "EXPIRED"].includes(status.status)) {
          clearInterval(pollTimer);
          MugenUI.toast("Pembayaran gagal/dibatalkan.", "error", { force: true });
          fase = "pilih"; gantiFase();
          return true;
        }
        return false;
      }

      const pollTimer = setInterval(async () => {
        if (!document.body.contains(statusLabelEl)) { clearInterval(pollTimer); return; }
        let status;
        try {
          status = await MugenApi.get(`/api/pos/transaksi/${r.id}/status`);
        } catch (e) {
          return; // hiccup jaringan sesaat -- coba lagi di tick berikutnya
        }
        if (!terapkanStatus(status) && status.status === "PENDING") {
          statusLabelEl.textContent = "Pembayaran sedang diproses provider…";
        }
      }, 3000);

      btnSudahBayar.addEventListener("click", async () => {
        if (!document.body.contains(statusLabelEl)) return;
        try {
          const status = await MugenUI.withButtonLoading(btnSudahBayar,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/cek-ulang`));
          if (!terapkanStatus(status)) {
            statusLabelEl.textContent = "Pembayaran belum terdeteksi -- coba lagi setelah selesai bayar.";
          }
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });

      btnBatalkan.addEventListener("click", async () => {
        if (!document.body.contains(statusLabelEl)) return;
        if (!(await MugenUI.confirmModal({ message: "Batalkan transaksi ini? Kalau customer terlanjur membayar, pembayaran TETAP akan terdeteksi lunas, TIDAK akan ikut terbatalkan.", danger: true }))) return;
        try {
          const hasil = await MugenUI.withButtonLoading(btnBatalkan,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/batalkan`));
          clearInterval(pollTimer);
          if (hasil.status === "lunas") {
            // Race jarang: customer sempat bayar tepat sebelum Kasir klik
            // Batalkan -- pembayaran TETAP sah, TIDAK dibatalkan.
            MugenUI.toast("Pembayaran ternyata sudah diterima -- transaksi TIDAK dibatalkan.", "error", { force: true });
            state.transaksi = hasil;
            _suntikTransaksiBaru(hasil);
            suntikKeRekap(hasil.rekap_transaksi_ids);
            fase = "selesai"; gantiFase();
            return;
          }
          MugenUI.toast("Transaksi dibatalkan.", "success", { force: true });
          // Keranjang/Produk SENGAJA TIDAK direset (BUKAN resetState()) --
          // kasir biasanya mau LANGSUNG memperbaiki input yang salah lalu
          // coba bayar lagi, bukan mengetik ulang semuanya dari awal.
          state.transaksi = null; state.metode = null; state.channel = null; state.bankCode = null;
          fase = "pilih"; gantiFase();
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
    }

    // ---- fase "bayar_cash": Kasir input nominal uang diterima dari
    // customer, sistem hitung kembalian LIVE sambil mengetik -- transaksi
    // LANGSUNG lunas begitu "Selesaikan Transaksi" diklik (uang tunai
    // diterima di tempat SAAT itu juga, TIDAK ada status menunggu). ----
    function renderBayarCash() {
      const r = state.transaksi;
      body.appendChild(MugenUI.el("h2", {}, "Pembayaran Cash"));
      body.appendChild(MugenUI.el("div", { class: "card" }, [barisTotal()]));

      body.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Uang Diterima"));
      const inputUang = MugenUI.el("input", { type: "text", style: "width:100%;font-size:18px;" });
      MugenUI.attachNumericKeypad(inputUang, { rupiah: true });
      body.appendChild(inputUang);

      const kembalianBox = MugenUI.el("div", { style: "margin-top:8px;font-weight:700;" });
      body.appendChild(kembalianBox);
      function renderKembalian() {
        const diterima = MugenUI.parseAngka(inputUang.value);
        const sisa = diterima - totalHarga();
        kembalianBox.className = sisa >= 0 ? "subtitle" : "login-error";
        kembalianBox.textContent = sisa >= 0
          ? `Kembalian: ${MugenUI.formatRupiah(sisa)}`
          : `Kurang ${MugenUI.formatRupiah(-sisa)}`;
      }
      inputUang.addEventListener("input", renderKembalian);
      renderKembalian();

      const errorBox = MugenUI.el("div", { class: "login-error" });
      body.appendChild(errorBox);

      const btnSelesai = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Selesaikan Transaksi");
      btnSelesai.addEventListener("click", async () => {
        errorBox.textContent = "";
        const diterima = MugenUI.parseAngka(inputUang.value);
        if (diterima < totalHarga()) { errorBox.textContent = "Uang diterima kurang dari total pembayaran."; return; }
        try {
          const hasil = await MugenUI.withButtonLoading(btnSelesai,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/bayar-cash`, { uang_diterima: diterima }));
          state.transaksi = hasil;
          _suntikTransaksiBaru(hasil);
          suntikKeRekap(hasil.rekap_transaksi_ids);
          MugenUI.toast("Pembayaran Cash diterima.", "success", { force: true });
          fase = "selesai"; gantiFase();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      body.appendChild(btnSelesai);
    }

    // ---- fase "selesai" ----
    // PERMINTAAN Owner (animasi lagi di app ini -- "checkout POS selesai"):
    // tambahan confetti/partikel di sekitar centang sukses, KHUSUS POS
    // (class .pos-selesai-icon baru, TERPISAH dari .book-selesai-icon
    // polos yang dipakai bersama di wizard booking publik -- supaya
    // perubahan ini tidak ikut memengaruhi layar sukses booking customer).
    function renderSelesai() {
      const r = state.transaksi;
      const iconBox = MugenUI.el("div", { class: "book-selesai-icon pos-selesai-icon" }, "✓");
      const isi = [
        iconBox,
        MugenUI.el("h2", {}, "Pembayaran Berhasil"),
        MugenUI.el("div", { class: "subtitle" }, `Total: ${MugenUI.formatRupiah(totalHarga())}`),
      ];
      if (r && r.metode_pembayaran === "cash") {
        isi.push(MugenUI.el("div", { class: "subtitle" }, `Uang Diterima: ${MugenUI.formatRupiah(r.uang_diterima || 0)}`));
        isi.push(MugenUI.el("div", { style: "font-weight:700;margin-top:4px;" }, `Kembalian: ${MugenUI.formatRupiah(r.kembalian || 0)}`));
      }
      body.appendChild(MugenUI.el("div", { class: "card book-selesai" }, isi));
      ledakanKonfetiPos(iconBox);
      const btnBaru = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Transaksi Baru");
      btnBaru.addEventListener("click", () => { resetState(); gantiFase(); });
      body.appendChild(btnBaru);
    }

    // Ledakan partikel kecil dari tengah centang -- murni CSS (translate
    // custom property per partikel), tidak ada library eksternal, otomatis
    // dilewati kalau browser/OS minta prefers-reduced-motion.
    function ledakanKonfetiPos(iconBox) {
      if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const warna = ["#8B5CF6", "#3B82F6", "#22C55E", "#F59E0B", "#EC4899"];
      const jumlah = 18;
      for (let i = 0; i < jumlah; i++) {
        const sudut = (Math.PI * 2 * i) / jumlah + (Math.random() * 0.5 - 0.25);
        const jarak = 55 + Math.random() * 45;
        const tx = Math.cos(sudut) * jarak;
        const ty = Math.sin(sudut) * jarak - 15; // bias sedikit ke atas
        const piece = MugenUI.el("span", { class: "pos-confetti-piece" });
        piece.style.setProperty("--tx", `${tx}px`);
        piece.style.setProperty("--ty", `${ty}px`);
        piece.style.setProperty("--rot", `${Math.round(Math.random() * 540 - 270)}deg`);
        piece.style.background = warna[i % warna.length];
        piece.style.animationDelay = `${Math.round(Math.random() * 80)}ms`;
        iconBox.appendChild(piece);
      }
      setTimeout(() => {
        iconBox.querySelectorAll(".pos-confetti-piece").forEach((p) => p.remove());
      }, 1100);
    }

    gantiFase();
  }

  // FITUR BARU Draft POS (PERMINTAAN Owner): "Draft Baru" -- tautan teks
  // biasa (BUKAN tombol, TANPA simbol "+", gaya SAMA PERSIS ".text-link-
  // aksi" yang sudah dipakai "Hapus" di tab Transaksi Hari Ini) yang
  // membuka form kecil Barber+Nama Customer. Draft yang sudah dibuat
  // tampil sebagai kartu persisten -- diklik -> expand INLINE di tempat
  // (Tips -> Service -> Metode Bayar -> Submit, lihat
  // jalankanDraftPembayaran() di bawah), TANPA pindah fase/halaman sama
  // sekali. Tersimpan di server (pos_draft_db.py) -- SAMA bagi semua
  // kasir/device tenant ini, lihat catatan _cacheDraftList/
  // suntikDraftBerubah() di atas untuk sinkronisasi real-time lintas
  // device.
  async function renderDraftSection(draftBox, pengaturan) {
    let expandedId = null; // hanya SATU kartu boleh expand pada satu waktu
    // Dipakai renderList() membedakan "baru saja expand" (morph HARUS
    // diputar) vs "render ulang sementara kartu ybs memang sudah terbuka"
    // (mis. refresh list dari push notif draft berubah di perangkat lain)
    // -- kalau tidak dibedakan, morph accordion akan terputar ULANG setiap
    // kali list di-refresh walau user tidak mengklik apa pun.
    let expandedIdSebelumnya = null;
    // BUGFIX (dilaporkan Owner: "jika user telah memilih service dan menutup
    // draf nya, pastikan service yg dipilih tidak hilang"): renderList() di
    // bawah membangun ULANG SELURUH kartu (termasuk instance
    // jalankanDraftPembayaran() milik kartu yang sedang expand) setiap kali
    // dipanggil -- tanpa ini, state (serviceIds/tips/metode/fase) jadi
    // OBJEK BARU tiap render, hilang begitu kartu di-collapse lalu di-
    // expand lagi. `_draftState[draftId]` di sini PERSISTEN selama seksi
    // Draft tab Kasir ini masih hidup (bertahan lintas collapse/expand,
    // direset hanya kalau draft itu sendiri selesai/dibatalkan atau Kasir
    // pindah tab/menu) -- jalankanDraftPembayaran() dibuat memakai OBJEK
    // yang SAMA (bukan bikin baru) lewat opsi `persisted` di bawah.
    const _draftState = {};

    draftBox.innerHTML = "";
    const linkDraftBaru = MugenUI.el("button", { type: "button", class: "text-link-aksi pos-draft-baru-link" }, "Draft Baru");
    const formBox = MugenUI.el("div", { style: "display:none;" });
    const listBox = MugenUI.el("div", { class: "pos-draft-list" });
    draftBox.appendChild(linkDraftBaru);
    draftBox.appendChild(formBox);
    draftBox.appendChild(listBox);

    function tutupForm() { formBox.style.display = "none"; formBox.innerHTML = ""; }

    function bukaForm() {
      formBox.innerHTML = "";
      formBox.style.display = "";
      const errorBox = MugenUI.el("div", { class: "login-error" });
      let barberIdForm = null;
      const barberOpsi = pengaturan.barbers.map((b) => ({ value: b.id, label: b.nama }));
      const dropdownBarber = MugenUI.dropdownSelect(barberOpsi, {
        placeholder: "-- Pilih Barber --",
        onChange: (v) => { barberIdForm = v; },
      });
      const inputNama = MugenUI.el("input", { type: "text", placeholder: "Nama Customer" });
      const btnSimpan = MugenUI.el("button", { class: "btn-primary", type: "button" }, "Simpan Draft");
      const btnBatalForm = MugenUI.el("button", { type: "button" }, "Batal");
      btnSimpan.addEventListener("click", async () => {
        errorBox.textContent = "";
        const nama = inputNama.value.trim();
        if (!barberIdForm) { errorBox.textContent = "Pilih Barber terlebih dahulu."; return; }
        if (!nama) { errorBox.textContent = "Nama Customer tidak boleh kosong."; return; }
        try {
          const draft = await MugenUI.withButtonLoading(btnSimpan, () =>
            MugenApi.post("/api/pos/draft", { barber_id: barberIdForm, customer_nama: nama }));
          _cacheDraftList = _cacheDraftList || [];
          _cacheDraftList.push(draft);
          MugenState.tandaiHalamanBersih("pos_draft");
          tutupForm();
          renderList();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      btnBatalForm.addEventListener("click", tutupForm);
      formBox.appendChild(MugenUI.el("div", { class: "card pos-draft-form", style: "margin:8px 0 12px;" }, [
        MugenUI.el("label", {}, "Barber"),
        dropdownBarber.el,
        MugenUI.el("label", { style: "margin-top:8px;" }, "Nama Customer"),
        inputNama,
        errorBox,
        MugenUI.el("div", { style: "margin-top:10px;display:flex;gap:8px;" }, [btnSimpan, btnBatalForm]),
      ]));
    }

    linkDraftBaru.addEventListener("click", () => {
      if (formBox.style.display === "none") bukaForm(); else tutupForm();
    });

    // REVISI UI/UX Premium (PERMINTAAN Owner -- "Animasi Morphing Form",
    // form Draft POS): accordion morph -- slot tumbuh dari max-height:0
    // menuju tinggi asli kontennya (diukur scrollHeight, SETELAH slot
    // ter-attach ke DOM -- makanya dipanggil lewat requestAnimationFrame
    // dari buatKartuDraft(), bukan sebelum di-append), dibarengi fade+
    // slide (konsisten dgn morph lain di app ini). max-height dikunci
    // balik ke "none" setelah transisi usai supaya perubahan konten
    // berikutnya (ganti fase Tips->Service->Metode Bayar) TIDAK ikut
    // kepotong/clip oleh nilai max-height lama yang sudah basi.
    function _animasiAccordionMasuk(slot) {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const tinggi = slot.scrollHeight;
      if (!tinggi) return;
      slot.style.overflow = "hidden";
      slot.style.transition = "none";
      slot.style.maxHeight = "0px";
      slot.style.opacity = "0";
      slot.style.transform = "translateY(8px)";
      void slot.offsetHeight; // paksa reflow -- state AWAL harus ter-apply dulu sebelum transisi dipasang di bawah (rAF)
      requestAnimationFrame(() => {
        slot.style.transition = "max-height 300ms var(--ease-standard), opacity 300ms var(--ease-standard), transform 300ms var(--ease-standard)";
        slot.style.maxHeight = tinggi + "px";
        slot.style.opacity = "1";
        slot.style.transform = "translateY(0)";
      });
      let selesai = false;
      const beres = (e) => {
        if (e.target !== slot || e.propertyName !== "max-height") return;
        if (selesai) return;
        selesai = true;
        slot.removeEventListener("transitionend", beres);
        slot.style.maxHeight = "none";
        slot.style.overflow = "";
        slot.style.transition = "";
      };
      slot.addEventListener("transitionend", beres);
      setTimeout(beres, 360); // jaring pengaman kalau transitionend tidak terpicu
    }

    function buatKartuDraft(d) {
      const expandSlot = MugenUI.el("div");
      const btnBatalDraft = MugenUI.el("button", { type: "button", class: "text-link-aksi" }, "Batal");
      btnBatalDraft.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!(await MugenUI.confirmModal({ message: `Batalkan draft ${d.customer_nama}?`, danger: true }))) return;
        try {
          await MugenUI.withButtonLoading(btnBatalDraft, () => MugenApi.del(`/api/pos/draft/${d.id}`));
          _cacheDraftList = (_cacheDraftList || []).filter((x) => x.id !== d.id);
          MugenState.tandaiHalamanBersih("pos_draft");
          delete _draftState[d.id];
          if (expandedId === d.id) expandedId = null;
          renderList();
        } catch (e2) {
          MugenUI.toast(e2.detail && e2.detail.detail ? e2.detail.detail : e2.message, "error");
        }
      });
      const header = MugenUI.el("div", { class: "pos-draft-card-header" }, [
        MugenUI.el("div", {}, [
          MugenUI.el("div", { style: "font-weight:700;" }, d.nama_barber || "(barber terhapus)"),
          MugenUI.el("div", { class: "subtitle" }, d.customer_nama),
        ]),
        btnBatalDraft,
      ]);
      header.addEventListener("click", (e) => {
        if (e.target.closest(".text-link-aksi")) return;
        expandedId = expandedId === d.id ? null : d.id;
        renderList();
      });
      const card = MugenUI.el("div", { class: "pos-draft-card" + (expandedId === d.id ? " expanded" : "") }, [header, expandSlot]);
      if (expandedId === d.id) {
        if (expandedId !== expandedIdSebelumnya) {
          requestAnimationFrame(() => _animasiAccordionMasuk(expandSlot));
        }
        jalankanDraftPembayaran(expandSlot, d, pengaturan, {
          persisted: _draftState[d.id] || (_draftState[d.id] = {}),
          onBatal: () => { expandedId = null; renderList(); },
          onSelesai: async () => {
            try {
              await MugenApi.del(`/api/pos/draft/${d.id}`);
            } catch (e3) {
              // Draft sudah terhapus/basi -- tidak fatal, transaksinya SENDIRI
              // sudah berhasil dibuat (lihat jalankanDraftPembayaran()).
            }
            _cacheDraftList = (_cacheDraftList || []).filter((x) => x.id !== d.id);
            MugenState.tandaiHalamanBersih("pos_draft");
            delete _draftState[d.id];
            expandedId = null;
            renderList();
          },
        });
      }
      return card;
    }

    function renderList() {
      listBox.innerHTML = "";
      for (const d of (_cacheDraftList || [])) {
        listBox.appendChild(buatKartuDraft(d));
      }
      expandedIdSebelumnya = expandedId; // dibaca buatKartuDraft() di ATAS (closure) -- diupdate SETELAH loop supaya seluruh kartu dalam render ini konsisten dibandingkan dgn nilai SEBELUM render ini mulai
    }

    // Pola SAMA PERSIS _transaksiHariIniTampilUlang -- berlaku utk KEDUA
    // jalur (cache hit MAUPUN fetch fresh) di bawah.
    _draftTampilUlang = renderList;

    if (_cacheDraftList === null || MugenState.halamanPerluRefresh("pos_draft")) {
      try {
        _cacheDraftList = await MugenApi.get("/api/pos/draft");
        MugenState.tandaiHalamanBersih("pos_draft");
      } catch (e) {
        _cacheDraftList = _cacheDraftList || [];
      }
    }
    renderList();
  }

  // Mini-wizard INLINE (Tips -> Service -> Metode Bayar -> Submit) utk
  // satu kartu Draft -- Barber+Nama Customer SUDAH terisi dari draft-nya
  // (`draft.barber_id`, dikunci, TIDAK bisa diubah di sini), TIDAK ada
  // Keranjang multi-barber/Produk sama sekali (draft SENGAJA 1 barber 1
  // customer, lihat spesifikasi Owner). Submit memakai endpoint checkout
  // SAMA PERSIS alur biasa (POST /api/pos/transaksi) -- fase pasca-submit
  // (QRIS manual/Payment Gateway/Cash) SENGAJA kode TERSENDIRI (bukan
  // reuse renderMenungguManual/renderWaitingGateway/renderBayarCash milik
  // jalankanWizardKasir() di atas) supaya alur checkout utama yang sudah
  // teruji TIDAK ikut tersentuh/berisiko regresi oleh perubahan ini --
  // logikanya sengaja dijaga identik (endpoint, validasi, polling
  // gateway, hitung kembalian cash).
  function jalankanDraftPembayaran(container, draft, pengaturan, { onBatal, onSelesai, persisted }) {
    const metodeAktif = pengaturan.metode_aktif || [];
    const metodeNama = pengaturan.metode_nama || {};
    const metodeInstruksi = pengaturan.metode_instruksi || {};
    // BUGFIX (lihat catatan _draftState di renderDraftSection()): `state`
    // dan `fase` di bawah DIAMBIL dari `persisted` (objek yang sama,
    // dipertahankan pemanggil lintas collapse/expand), BUKAN dibuat baru
    // tiap kartu ini di-render ulang -- supaya Service/Tips/Metode Bayar
    // yang sudah dipilih kasir TIDAK hilang kalau kartu di-collapse dulu
    // (mis. untuk lihat/expand draft lain) lalu dibuka lagi.
    if (!persisted.state) {
      persisted.state = { serviceIds: new Set(), tips: 0, produk: {}, metode: null, channel: null, bankCode: null, transaksi: null };
    }
    const state = persisted.state;
    let fase = persisted.fase || "isi";

    // PERMINTAAN Owner ("siapa tahu customer mau beli produk juga"):
    // totalHarga() ikut menjumlahkan Produk (state.produk, map produk_id
    // -> qty -- pola SAMA PERSIS wizard Kasir biasa), dipakai baik di
    // layar "isi" (renderTotal()) maupun ketiga layar pasca-submit
    // (barisTotalDraft() di bawah).
    function totalHarga() {
      let total = state.tips || 0;
      for (const sid of state.serviceIds) {
        const s = pengaturan.services.find((x) => x.id === sid);
        if (s) total += s.harga;
      }
      for (const pid of Object.keys(state.produk)) {
        const qty = state.produk[pid];
        if (qty > 0) {
          const p = pengaturan.produk.find((x) => x.id === Number(pid));
          if (p) total += p.harga_jual * qty;
        }
      }
      return total;
    }

    // PERMINTAAN Owner ("tampilkan total payment yg harus dibayarkan,
    // sama seperti Menunggu Pembayaran (QRIS) di POS bukan draft"):
    // baris Total Payment yang dipakai di KETIGA layar pasca-submit
    // (QRIS manual/Payment Gateway/Cash) -- pola SAMA PERSIS barisTotal()
    // milik jalankanWizardKasir() di atas.
    function barisTotalDraft() {
      return MugenUI.el("div", { style: "display:flex;justify-content:space-between;font-weight:700;" }, [
        MugenUI.el("span", {}, "Total Payment"), MugenUI.el("span", {}, MugenUI.formatRupiah(totalHarga())),
      ]);
    }

    function gantiFase() {
      persisted.fase = fase; // sinkron tiap kali fase berubah -- lihat catatan di atas
      container.innerHTML = "";
      if (fase === "menunggu_manual") renderMenungguManual();
      else if (fase === "waiting") renderWaitingGateway();
      else if (fase === "bayar_cash") renderBayarCash();
      else renderIsi();
    }

    function renderIsi() {
      const errorBox = MugenUI.el("div", { class: "login-error" });

      container.appendChild(MugenUI.el("label", {}, "Service"));
      const serviceGrid = MugenUI.el("div", { class: "pos-service-grid" });
      for (const s of pengaturan.services) {
        const card = MugenUI.el("button", {
          type: "button", class: "pos-service-card" + (state.serviceIds.has(s.id) ? " selected" : ""),
        }, [
          MugenUI.el("div", { class: "pos-service-card-nama" }, s.nama),
          MugenUI.el("div", { class: "pos-service-card-harga" }, MugenUI.formatRupiah(s.harga)),
          MugenUI.el("div", { class: "pos-service-card-check" }, "✓"),
        ]);
        card.addEventListener("click", () => {
          if (state.serviceIds.has(s.id)) state.serviceIds.delete(s.id); else state.serviceIds.add(s.id);
          card.classList.toggle("selected");
          renderTotal();
        });
        serviceGrid.appendChild(card);
      }
      container.appendChild(serviceGrid);
      if (!pengaturan.services.length) container.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada service aktif."));

      // PERMINTAAN Owner ("draft harusnya juga bisa menampilkan produk,
      // siapa tahu customer mau beli produk juga"): SENGAJA bukan modal
      // layar-penuh seperti renderPilih() milik jalankanWizardKasir() di
      // atas (yang nempel ke document.body -- draft bisa expand
      // BERSAMAAN dengan wizard Kasir biasa yang sedang dibuka di tab
      // yang sama, modal document.body akan BENTROK satu sama lain) --
      // daftar produk + qty stepper di sini murni INLINE di dalam kartu
      // draft itu sendiri, cukup ditoggle tampil/sembunyi oleh link
      // "+ Tambah Produk". Produk opsional -- boleh pilih Service saja,
      // Produk saja, atau keduanya (lihat validasi submit di bawah).
      container.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Produk (opsional)"));

      function buatQtyStepperDraft(p) {
        const qty = state.produk[p.id] || 0;
        const btnMinus = MugenUI.el("button", { type: "button", class: "pos-qty-btn" }, "−");
        const nilai = MugenUI.el("span", { class: "pos-qty-value" }, String(qty));
        const btnPlus = MugenUI.el("button", { type: "button", class: "pos-qty-btn" }, "+");
        btnMinus.disabled = qty <= 0;
        btnPlus.disabled = qty >= p.stok;
        btnMinus.addEventListener("click", (e) => { e.stopPropagation(); ubahQtyProdukDraft(p, -1); });
        btnPlus.addEventListener("click", (e) => { e.stopPropagation(); ubahQtyProdukDraft(p, 1); });
        return MugenUI.el("div", { class: "pos-qty-stepper" }, [btnMinus, nilai, btnPlus]);
      }

      const produkTerpilihBoxDraft = MugenUI.el("div", { class: "pos-produk-terpilih" });
      function renderProdukTerpilihDraft() {
        produkTerpilihBoxDraft.innerHTML = "";
        const idsTerpilih = Object.keys(state.produk).map(Number).filter((id) => state.produk[id] > 0);
        for (const pid of idsTerpilih) {
          const p = pengaturan.produk.find((x) => x.id === pid);
          if (!p) continue;
          produkTerpilihBoxDraft.appendChild(MugenUI.el("div", { class: "pos-produk-terpilih-row" }, [
            MugenUI.el("div", {}, [
              MugenUI.el("div", { class: "pos-produk-terpilih-nama" }, p.nama),
              MugenUI.el("div", { class: "pos-produk-terpilih-harga" }, `${MugenUI.formatRupiah(p.harga_jual)}/pcs`),
            ]),
            buatQtyStepperDraft(p),
          ]));
        }
      }

      const daftarProdukBoxDraft = MugenUI.el("div", {
        style: "display:none;max-height:220px;overflow-y:auto;border:1px solid var(--border);border-radius:8px;margin-top:8px;",
      });
      function renderDaftarProdukDraft(query) {
        daftarProdukBoxDraft.innerHTML = "";
        const q = (query || "").trim().toLowerCase();
        const hasil = pengaturan.produk.filter((p) => !q || p.nama.toLowerCase().includes(q));
        if (!hasil.length) {
          daftarProdukBoxDraft.appendChild(MugenUI.el("div", { class: "mugen-dropdown-empty" }, "Produk tidak ditemukan."));
          return;
        }
        for (const p of hasil) {
          const terpilih = (state.produk[p.id] || 0) > 0;
          const row = MugenUI.el("div", { class: "pos-produk-option" + (terpilih ? " selected" : "") }, [
            MugenUI.el("div", { class: "pos-produk-option-check" }, "✓"),
            MugenUI.el("div", { class: "pos-produk-option-info" }, [
              MugenUI.el("div", { class: "pos-produk-option-nama" }, p.nama),
              MugenUI.el("div", { class: "pos-produk-option-meta" }, `${MugenUI.formatRupiah(p.harga_jual)}/pcs · stok ${p.stok}`),
            ]),
            buatQtyStepperDraft(p),
          ]);
          row.addEventListener("click", (e) => {
            if (e.target.closest(".pos-qty-btn")) return;
            if (p.stok <= 0) return;
            ubahQtyProdukDraft(p, 1);
            renderDaftarProdukDraft(searchProdukInputDraft.value);
          });
          daftarProdukBoxDraft.appendChild(row);
        }
      }

      function ubahQtyProdukDraft(p, delta) {
        const qtyBaru = Math.max(0, Math.min(p.stok, (state.produk[p.id] || 0) + delta));
        if (qtyBaru > 0) state.produk[p.id] = qtyBaru; else delete state.produk[p.id];
        renderProdukTerpilihDraft();
        if (daftarProdukBoxDraft.style.display !== "none") renderDaftarProdukDraft(searchProdukInputDraft.value);
        renderTotal();
      }

      const searchProdukInputDraft = MugenUI.el("input", { type: "text", placeholder: "Cari produk…", style: "margin-top:8px;" });
      searchProdukInputDraft.addEventListener("input", () => renderDaftarProdukDraft(searchProdukInputDraft.value));

      const triggerProdukDraft = MugenUI.el("button", { type: "button", class: "text-link-aksi" }, "+ Tambah Produk");
      triggerProdukDraft.addEventListener("click", () => {
        const sedangTerbuka = daftarProdukBoxDraft.style.display !== "none";
        daftarProdukBoxDraft.style.display = sedangTerbuka ? "none" : "";
        if (!sedangTerbuka) { searchProdukInputDraft.value = ""; renderDaftarProdukDraft(""); }
      });

      if (pengaturan.produk.length) {
        container.appendChild(produkTerpilihBoxDraft);
        renderProdukTerpilihDraft();
        container.appendChild(triggerProdukDraft);
        container.appendChild(searchProdukInputDraft);
        container.appendChild(daftarProdukBoxDraft);
      } else {
        container.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada produk aktif."));
      }

      container.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Tips (opsional)"));
      const inputTips = MugenUI.el("input", { type: "text", value: MugenUI.nilaiTampilAngka(state.tips), style: "max-width:160px;" });
      inputTips.addEventListener("input", () => {
        state.tips = Math.max(0, MugenUI.parseAngka(inputTips.value));
        renderTotal();
      });
      MugenUI.attachNumericKeypad(inputTips, { rupiah: true });
      container.appendChild(inputTips);

      const metodeBox = MugenUI.el("div", { class: "row", style: "flex-wrap:wrap;gap:8px;margin-top:12px;" });
      const bankBox = MugenUI.el("div", { class: "bank-grid" });

      function renderBankBox() {
        bankBox.innerHTML = "";
        if (state.metode !== "gateway" || state.channel !== "va") return;
        const bankAktif = pengaturan.snap_va_bank_aktif || {};
        const kodeList = Object.keys(bankAktif);
        for (const kode of kodeList) {
          const card = MugenUI.el("button", {
            type: "button", class: "bank-card" + (state.bankCode === kode ? " selected" : ""),
          }, [MugenUI.bankLogoBadge(kode), MugenUI.el("span", {}, MugenUI.bankNamaLengkap(kode, bankAktif[kode]))]);
          card.addEventListener("click", () => {
            state.bankCode = kode;
            for (const el of bankBox.children) el.classList.remove("selected");
            card.classList.add("selected");
          });
          bankBox.appendChild(card);
        }
        if (kodeList.length === 1) state.bankCode = kodeList[0];
      }

      const opsi = [];
      for (const m of metodeAktif) {
        if (m === "gateway") {
          for (const c of (pengaturan.snap_channel_aktif || [])) {
            opsi.push({ metode: "gateway", channel: c, label: c === "va" ? "Virtual Account" : "QRIS" });
          }
        } else {
          opsi.push({ metode: m, channel: null, label: metodeNama[m] || m });
        }
      }
      container.appendChild(MugenUI.el("label", { style: "margin-top:12px;" }, "Metode Bayar"));
      const satuOpsi = opsi.length === 1;
      if (!opsi.length) {
        container.appendChild(MugenUI.el("div", { class: "subtitle" }, "Belum ada metode pembayaran aktif."));
      } else if (satuOpsi) {
        state.metode = opsi[0].metode; state.channel = opsi[0].channel;
        metodeBox.appendChild(MugenUI.el("div", { class: "subtitle" }, `Metode pembayaran: ${opsi[0].label}`));
        renderBankBox();
      } else {
        for (const o of opsi) {
          const dipilih = state.metode === o.metode && state.channel === o.channel;
          const btn = MugenUI.el("button", {
            type: "button", class: "book-metode-btn" + (dipilih ? " selected" : ""),
          }, o.label);
          btn.addEventListener("click", () => {
            state.metode = o.metode; state.channel = o.channel; state.bankCode = null;
            for (const el of metodeBox.children) el.classList.remove("selected");
            btn.classList.add("selected");
            renderBankBox();
          });
          metodeBox.appendChild(btn);
        }
      }
      container.appendChild(metodeBox);
      container.appendChild(bankBox);

      const totalBox = MugenUI.el("div", { class: "card", style: "margin-top:12px;" });
      container.appendChild(totalBox);
      function renderTotal() {
        totalBox.innerHTML = "";
        totalBox.appendChild(MugenUI.el("div", { style: "display:flex;justify-content:space-between;font-weight:700;" }, [
          MugenUI.el("span", {}, "Total Payment"), MugenUI.el("span", {}, MugenUI.formatRupiah(totalHarga())),
        ]));
      }
      renderTotal();

      container.appendChild(errorBox);

      const btnTutup = MugenUI.el("button", { type: "button" }, "Tutup");
      btnTutup.addEventListener("click", () => onBatal());

      const btnBuat = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Buat Transaksi");
      btnBuat.addEventListener("click", async () => {
        errorBox.textContent = "";
        if (!state.serviceIds.size && !Object.keys(state.produk).length) {
          errorBox.textContent = "Pilih minimal satu Service atau Produk."; return;
        }
        if (!state.metode) { errorBox.textContent = "Pilih metode pembayaran terlebih dahulu."; return; }
        if (state.metode === "gateway" && !state.channel) { errorBox.textContent = "Pilih VA/QRIS terlebih dahulu."; return; }
        if (state.metode === "gateway" && state.channel === "va" && !state.bankCode) {
          errorBox.textContent = "Pilih bank terlebih dahulu."; return;
        }
        try {
          const payload = {
            jasa_items: state.serviceIds.size
              ? [{ barber_id: draft.barber_id, service_ids: Array.from(state.serviceIds), tips: state.tips || 0 }]
              : [],
            produk_items: Object.keys(state.produk).map((pid) => ({ produk_id: Number(pid), jumlah: state.produk[pid] })),
            metode_pembayaran: state.metode,
            channel: state.metode === "gateway" ? state.channel : undefined,
            bank_code: state.metode === "gateway" && state.channel === "va" ? state.bankCode : undefined,
          };
          const hasil = await MugenUI.withButtonLoading(btnBuat, () => MugenApi.post("/api/pos/transaksi", payload));
          state.transaksi = hasil;
          fase = state.metode === "gateway" ? "waiting" : (state.metode === "cash" ? "bayar_cash" : "menunggu_manual");
          gantiFase();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      container.appendChild(MugenUI.el("div", { style: "display:flex;gap:8px;margin-top:12px;" }, [btnBuat, btnTutup]));
    }

    function renderMenungguManual() {
      container.appendChild(MugenUI.el("h3", {}, "Menunggu Pembayaran (QRIS)"));
      const items = [];
      if (pengaturan.qris_url) {
        // BUGFIX (dilaporkan Owner: "tampilan qris memenuhi full layar") --
        // .book-qris-img sengaja width:100% (lihat style.css), mengikuti
        // lebar kontainernya -- di kartu Draft yang kecil ini WAJIB
        // dibungkus .book-qris-wrap (max-width 240px, pola SAMA PERSIS
        // halaman Booking Publik) supaya ukurannya pas untuk kartu inline,
        // tidak melebar penuh.
        items.push(MugenUI.el("div", { class: "book-qris-wrap" },
          MugenUI.el("img", { src: MUGEN_API_BASE + pengaturan.qris_url, class: "book-qris-img", alt: "QRIS" })));
      } else {
        items.push(MugenUI.el("div", { class: "subtitle" }, "Foto QRIS belum diunggah Superadmin."));
      }
      items.push(MugenUI.el("div", { class: "subtitle", style: "margin-top:4px;" }, metodeInstruksi.qris || ""));
      container.appendChild(MugenUI.el("div", { class: "card" }, [
        barisTotalDraft(),
        MugenUI.el("hr"),
        MugenUI.el("div", { style: "text-align:center;" }, items),
      ]));
      const errorBox = MugenUI.el("div", { class: "login-error" });
      container.appendChild(errorBox);
      const btnTerima = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Payment Diterima");
      btnTerima.addEventListener("click", async () => {
        errorBox.textContent = "";
        try {
          const hasil = await MugenUI.withButtonLoading(btnTerima, () => MugenApi.post(`/api/pos/transaksi/${state.transaksi.id}/verifikasi`));
          _suntikTransaksiBaru(hasil);
          suntikKeRekap(hasil.rekap_transaksi_ids);
          MugenUI.toast("Pembayaran dikonfirmasi.", "success", { force: true });
          onSelesai();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      container.appendChild(btnTerima);
    }

    function renderWaitingGateway() {
      const r = state.transaksi;
      container.appendChild(MugenUI.el("h3", {}, "Menunggu Konfirmasi Pembayaran"));
      const statusLabelEl = MugenUI.el("div", { class: "subtitle" }, "Selesaikan pembayaran memakai info di bawah.");
      const items = [];
      if (r.channel === "va" || state.channel === "va") {
        items.push(MugenUI.el("div", { class: "subtitle" },
          r.channel_code ? `Virtual Account ${MugenUI.bankNamaLengkap(r.channel_code, null)}` : "Virtual Account"));
        items.push(MugenUI.el("div", { style: "font-size:20px;font-weight:700;letter-spacing:1px;text-align:center;margin-top:4px;" },
          r.va_number || "-"));
      } else if (r.qr_url) {
        // BUGFIX sama seperti renderMenungguManual() di atas -- bungkus
        // .book-qris-wrap supaya QR Payment Gateway juga tidak melebar
        // penuh di kartu Draft yang kecil ini.
        items.push(MugenUI.el("div", { class: "book-qris-wrap" },
          MugenUI.el("img", { src: r.qr_url, class: "book-qris-img", alt: "QRIS" })));
      } else if (r.qr_content) {
        const btnBuka = MugenUI.el("button", { type: "button", class: "book-download-qris-btn" }, "Buka Halaman QRIS");
        btnBuka.addEventListener("click", () => window.open(r.qr_content, "_blank"));
        items.push(btnBuka);
      }
      const btnSudahBayar = MugenUI.el("button", { type: "button", style: "margin-top:12px;" }, "Saya Sudah Bayar");
      const btnBatalkanTx = MugenUI.el("button", { type: "button", style: "margin-top:12px;margin-left:8px;" }, "Batalkan");
      container.appendChild(MugenUI.el("div", { class: "card" }, [
        MugenUI.el("div", { style: "text-align:center;" }, [statusLabelEl, MugenUI.el("div", {}, [btnSudahBayar, btnBatalkanTx])]),
        MugenUI.el("hr"),
        MugenUI.el("div", { style: "text-align:center;" }, items),
        MugenUI.el("hr"),
        barisTotalDraft(),
      ]));

      function terapkanStatus(status) {
        if (status.status === "PAID") {
          clearInterval(pollTimer);
          _suntikTransaksiBaru(r);
          suntikKeRekap(status.rekap_transaksi_ids);
          MugenUI.toast("Pembayaran berhasil.", "success", { force: true });
          onSelesai();
          return true;
        }
        if (["FAILED", "CANCELLED", "EXPIRED"].includes(status.status)) {
          clearInterval(pollTimer);
          MugenUI.toast("Pembayaran gagal/dibatalkan.", "error", { force: true });
          fase = "isi"; gantiFase();
          return true;
        }
        return false;
      }

      const pollTimer = setInterval(async () => {
        if (!document.body.contains(statusLabelEl)) { clearInterval(pollTimer); return; }
        let status;
        try {
          status = await MugenApi.get(`/api/pos/transaksi/${r.id}/status`);
        } catch (e) {
          return; // hiccup jaringan sesaat -- coba lagi di tick berikutnya
        }
        if (!terapkanStatus(status) && status.status === "PENDING") {
          statusLabelEl.textContent = "Pembayaran sedang diproses provider…";
        }
      }, 3000);

      btnSudahBayar.addEventListener("click", async () => {
        if (!document.body.contains(statusLabelEl)) return;
        try {
          const status = await MugenUI.withButtonLoading(btnSudahBayar,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/cek-ulang`));
          if (!terapkanStatus(status)) {
            statusLabelEl.textContent = "Pembayaran belum terdeteksi -- coba lagi setelah selesai bayar.";
          }
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });

      btnBatalkanTx.addEventListener("click", async () => {
        if (!document.body.contains(statusLabelEl)) return;
        if (!(await MugenUI.confirmModal({ message: "Batalkan transaksi ini? Kalau customer terlanjur membayar, pembayaran TETAP akan terdeteksi lunas, TIDAK akan ikut terbatalkan.", danger: true }))) return;
        try {
          const hasil = await MugenUI.withButtonLoading(btnBatalkanTx,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/batalkan`));
          clearInterval(pollTimer);
          if (hasil.status === "lunas") {
            MugenUI.toast("Pembayaran ternyata sudah diterima -- transaksi TIDAK dibatalkan.", "error", { force: true });
            state.transaksi = hasil;
            _suntikTransaksiBaru(hasil);
            suntikKeRekap(hasil.rekap_transaksi_ids);
            onSelesai();
            return;
          }
          MugenUI.toast("Transaksi dibatalkan.", "success", { force: true });
          state.transaksi = null; state.metode = null; state.channel = null; state.bankCode = null;
          fase = "isi"; gantiFase();
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
    }

    function renderBayarCash() {
      const r = state.transaksi;
      container.appendChild(MugenUI.el("h3", {}, "Pembayaran Cash"));
      container.appendChild(MugenUI.el("div", { class: "card" }, [barisTotalDraft()]));
      container.appendChild(MugenUI.el("label", { style: "margin-top:8px;" }, "Uang Diterima"));
      const inputUang = MugenUI.el("input", { type: "text", style: "width:100%;font-size:18px;" });
      MugenUI.attachNumericKeypad(inputUang, { rupiah: true });
      container.appendChild(inputUang);
      const kembalianBox = MugenUI.el("div", { style: "margin-top:8px;font-weight:700;" });
      container.appendChild(kembalianBox);
      function renderKembalian() {
        const diterima = MugenUI.parseAngka(inputUang.value);
        const sisa = diterima - totalHarga();
        kembalianBox.className = sisa >= 0 ? "subtitle" : "login-error";
        kembalianBox.textContent = sisa >= 0
          ? `Kembalian: ${MugenUI.formatRupiah(sisa)}`
          : `Kurang ${MugenUI.formatRupiah(-sisa)}`;
      }
      inputUang.addEventListener("input", renderKembalian);
      renderKembalian();
      const errorBox = MugenUI.el("div", { class: "login-error" });
      container.appendChild(errorBox);
      const btnSelesai = MugenUI.el("button", { class: "btn-primary", type: "button", style: "width:100%;margin-top:12px;" },
        "Selesaikan Transaksi");
      btnSelesai.addEventListener("click", async () => {
        errorBox.textContent = "";
        const diterima = MugenUI.parseAngka(inputUang.value);
        if (diterima < totalHarga()) { errorBox.textContent = "Uang diterima kurang dari total pembayaran."; return; }
        try {
          const hasil = await MugenUI.withButtonLoading(btnSelesai,
            () => MugenApi.post(`/api/pos/transaksi/${r.id}/bayar-cash`, { uang_diterima: diterima }));
          _suntikTransaksiBaru(hasil);
          suntikKeRekap(hasil.rekap_transaksi_ids);
          MugenUI.toast("Pembayaran Cash diterima.", "success", { force: true });
          onSelesai();
        } catch (e) {
          errorBox.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
        }
      });
      container.appendChild(btnSelesai);
    }

    gantiFase();
  }

  // ================= TAB: TRANSAKSI HARI INI =================
  // Gabungan booking online (sudah terverifikasi/lunas) + transaksi Kasir
  // (lunas) hari ini -- field ringkas saja (nama barber/service/produk,
  // nominal, jam), TANPA komisi/tips (PERMINTAAN Owner).
  async function renderTransaksiHariIniTab(body) {
    const userId = MugenState.getUser().id;
    const tanggalHariIni = MugenUI.isoHariIniWib();

    // Tombol Hapus (PERMINTAAN Owner: baris yang terlanjur salah input di
    // POS bisa langsung dihapus dari sini) -- HANYA untuk baris sumber
    // "pos" (booking online TIDAK dihapus dari sini sama sekali). Spinner
    // di tombolnya sendiri (MugenUI.withButtonLoading(), pola SAMA PERSIS
    // halaman lain), lalu muat ulang PAKSA (fetch fresh -- butuh angka
    // stok/Rekap yang benar-benar baru dari server, TIDAK bisa dihitung
    // sendiri di frontend seperti _suntikTransaksiBaru()).
    function kolomAksi(posId) {
      if (!posId) return "-";
      // PERMINTAAN Owner: link teks polos (gaya "Lupa Kata Sandi?" di
      // Login), BUKAN tombol -- supaya tinggi baris ini SAMA dengan baris
      // Booking Online (Aksi-nya cuma "-", teks polos juga).
      const btn = MugenUI.el("button", { type: "button", class: "text-link-aksi" }, "Hapus");
      btn.addEventListener("click", async () => {
        if (!(await MugenUI.confirmModal({ message: "Hapus transaksi POS ini? Stok produk (kalau ada) dikembalikan & Rekap barber terkait dihitung ulang.", danger: true }))) return;
        try {
          await MugenUI.withButtonLoading(btn, () => MugenApi.del(`/api/pos/transaksi/${posId}`));
          MugenUI.toast("Transaksi dihapus.", "success", { force: true });
          await muatUlangPaksa();
        } catch (e) {
          MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
        }
      });
      return btn;
    }

    function tampilkanData(hasil) {
      body.innerHTML = "";

      // Rincian total per metode pembayaran (PERMINTAAN Owner) --
      // termasuk tips & produk (dihitung dari total mentah tiap
      // transaksi di backend, lihat pos_db.get_transaksi_hari_ini()).
      const rincian = hasil.rincian_metode || {};
      function barisRincian(label, nominal, tebal) {
        return MugenUI.el("div", {
          style: `display:flex;justify-content:space-between;${tebal ? "font-weight:700;" : ""}`,
        }, [MugenUI.el("span", {}, label), MugenUI.el("span", {}, MugenUI.formatRupiah(nominal || 0))]);
      }
      // FITUR Rekonsiliasi Pembayaran Booking (PERMINTAAN Owner): "Total
      // Keseluruhan"/rincian metode di atas SEKARANG berdasarkan tanggal
      // PEMBAYARAN diterima (bukan tanggal layanan, lihat catatan
      // panjang di pos_db.get_transaksi_hari_ini()) -- baris "penyesuaian"
      // di bawah ini (warna merah) menjelaskan SECARA TRANSPARAN kenapa
      // totalnya segitu: "+" = booking yang dibayar HARI INI untuk
      // layanan di tanggal lain (uangnya ikut masuk total hari ini),
      // "-" = booking untuk LAYANAN hari ini yang sudah dibayar di
      // tanggal lain (uangnya TIDAK ikut dihitung di total hari ini,
      // sudah benar -- baris ini murni penjelasan, bukan pengurang
      // ulang).
      const barisPenyesuaian = (hasil.penyesuaian || []).map((p) => MugenUI.el("div", {
        style: "display:flex;justify-content:space-between;color:#dc2626;font-size:12.5px;margin-top:4px;",
      }, [
        MugenUI.el("span", {}, `${p.arah === "tambah" ? "+" : "-"} ${p.label}`),
        MugenUI.el("span", {}, `${p.arah === "tambah" ? "+" : "-"} ${MugenUI.formatRupiah(p.nominal)}`),
      ]));

      // FITUR "Detail Transaksi Hari Ini" (PERMINTAAN Owner): kartu
      // "Rincian Pembayaran Hari Ini" yang DULU tampil permanen di atas
      // halaman sekarang DIHAPUS -- isinya (Payment Gateway/QRIS/Cash/
      // Total/penyesuaian) pindah ke modal ini, DIGABUNG dengan rincian
      // service per-nama (dijumlahkan satu hari, lintas Kasir+Booking
      // Online -- lihat pos_db.get_transaksi_hari_ini()) + Total Tips +
      // Total Produk. Dipicu tombol link "Detail" di bawah tabel Service.
      function bukaDetailTransaksi() {
        const rincianService = hasil.rincian_service || [];
        MugenUI.infoModal({
          title: "Detail Transaksi Hari Ini",
          body: [
            MugenUI.el("div", { style: "font-weight:700;margin-bottom:8px;" },
              `Total Service: ${MugenUI.formatRupiah(hasil.total_service || 0)}`),
            MugenUI.el("div", { class: "subtitle", style: "margin-bottom:4px;" }, "Rincian Service"),
            ...(rincianService.length
              ? rincianService.map((s) => MugenUI.el("div", {
                  style: "display:flex;justify-content:space-between;",
                }, [
                  MugenUI.el("span", {}, `${s.nama} ${s.jumlah}×`),
                  MugenUI.el("span", {}, MugenUI.formatRupiah(s.nominal)),
                ]))
              : [MugenUI.el("div", { class: "subtitle" }, "Belum ada service hari ini.")]),
            MugenUI.el("hr"),
            barisRincian("Total Tips", hasil.total_tips),
            barisRincian("Total Produk", hasil.total_produk),
            MugenUI.el("hr"),
            MugenUI.el("div", { style: "font-weight:700;margin-bottom:4px;" }, "Metode Pembayaran"),
            barisRincian("Payment Gateway", rincian.gateway),
            barisRincian("QRIS Manual", rincian.qris),
            barisRincian("Cash", rincian.cash),
            MugenUI.el("hr"),
            barisRincian("Total Transaksi", hasil.total_keseluruhan, true),
            ...barisPenyesuaian,
          ],
        });
      }

      // Kolom "No" (PERMINTAAN Owner) -- nomor urut tampilan, dihitung ULANG
      // tiap render dari urutan baris SAAT INI (bukan disimpan permanen di
      // cache), supaya tetap benar walau baris baru masuk lewat suntik
      // diam-diam (_suntikTransaksiBaru/suntikBookingLunas) yang menyortir
      // ulang array-nya.
      const produkRows = (hasil.produk || []).map((r, i) => ({ ...r, no: i + 1 }));

      body.appendChild(MugenUI.el("h2", {}, "Service"));

      // FITUR Filter Barber (PERMINTAAN Owner) -- daftar opsi diambil dari
      // barber yang BENAR-BENAR punya transaksi hari ini (bukan semua
      // barber aktif), supaya tidak ada opsi kosong di dropdown. Filter
      // ini MURNI tampilan (client-side, data hari ini sudah lengkap di
      // memori) -- kartu "Detail Transaksi Hari Ini" (lihat bukaDetailTransaksi()
      // di atas) TETAP untuk SELURUH hari (tidak ikut terpotong oleh filter ini).
      const daftarBarberHariIni = [];
      const idBarberSudahAda = new Set();
      for (const r of hasil.service || []) {
        if (r.barber_id == null || idBarberSudahAda.has(r.barber_id)) continue;
        idBarberSudahAda.add(r.barber_id);
        daftarBarberHariIni.push({ id: r.barber_id, nama: r.nama_barber });
      }
      daftarBarberHariIni.sort((a, c) => a.nama.localeCompare(c.nama));

      const selFilterBarber = MugenUI.el("select", {}, [
        MugenUI.el("option", { value: "" }, "Semua Barber"),
        ...daftarBarberHariIni.map((b) => MugenUI.el("option", { value: String(b.id) }, b.nama)),
      ]);
      body.appendChild(MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;" }, [
        MugenUI.selectIcon(MugenIcons.karyawan, selFilterBarber),
      ]));

      const tabelServiceWrap = MugenUI.el("div");
      body.appendChild(tabelServiceWrap);

      function gambarTabelService() {
        tabelServiceWrap.innerHTML = "";
        const dipilih = selFilterBarber.value;
        const serviceTersaring = dipilih
          ? (hasil.service || []).filter((r) => String(r.barber_id) === dipilih)
          : (hasil.service || []);
        const serviceRows = serviceTersaring.map((r, i) => ({ ...r, no: i + 1 }));
        tabelServiceWrap.appendChild(MugenUI.buildTable(
          [
            { key: "no", label: "No" },
            { key: "jam", label: "Jam" },
            // PERMINTAAN Owner: nama customer -- HANYA terisi untuk baris
            // sumber="booking" (online maupun Booking Mandiri, lihat catatan
            // pos_db.py::get_transaksi_hari_ini()). Baris sumber="pos" (Kasir
            // walk-in) TIDAK PERNAH punya field ini (form checkout Kasir
            // tidak menanyakan nama customer sama sekali) -- tampil strip.
            { key: "nama_customer", label: "Nama Customer", format: (v) => v || "-" },
            { key: "nama_barber", label: "Barber" },
            { key: "daftar_service", label: "Service" },
            { key: "nominal", label: "Nominal", format: (v) => MugenUI.formatRupiah(v) },
            // FITUR Tampilkan Tips (PERMINTAAN Owner): HANYA terisi untuk
            // baris sumber="pos" -- Booking Online/Mandiri tidak punya
            // konsep tips sama sekali (lihat pos_db.get_transaksi_hari_ini()).
            { key: "tips", label: "Tips", format: (v) => (v ? MugenUI.formatRupiah(v) : "-") },
            {
              key: "sumber", label: "Sumber",
              // FITUR Rekonsiliasi Pembayaran Booking (PERMINTAAN Owner):
              // baris booking yang pembayarannya sudah diterima di
              // tanggal LAIN (dibayar di muka) ikut ditandai di sini,
              // supaya kasir langsung tahu "customer ini sudah bayar"
              // tanpa perlu buka Rincian Pembayaran di atas.
              format: (v, r) => (v === "pos" ? "Kasir" : "Booking Online")
                + (r.dibayar_tanggal_lain ? ` (dibayar ${r.dibayar_tanggal_lain})` : ""),
            },
            { key: "pos_id", label: "Aksi", format: (v) => kolomAksi(v) },
          ],
          serviceRows,
          {
            emptyText: dipilih ? "Belum ada transaksi service hari ini untuk barber ini." : "Belum ada transaksi service hari ini.",
            // PERMINTAAN Owner: baris customer yang SUDAH BAYAR (booking
            // dibayar di muka untuk layanan hari ini) font-nya merah,
            // supaya kasir gampang tahu customer mana yang tidak perlu
            // ditagih lagi.
            rowClass: (r) => (r.dibayar_tanggal_lain ? "pos-baris-sudah-bayar" : ""),
          },
        ));
      }
      selFilterBarber.addEventListener("change", gambarTabelService);
      gambarTabelService();

      // Tombol link "Detail" (PERMINTAAN Owner: posisi di bawah tabel
      // Service, rata kanan) -- gaya link polos, pola SAMA PERSIS tombol
      // "Hapus" (.text-link-aksi) di kolom Aksi tabel di atas.
      const btnDetail = MugenUI.el("button", { type: "button", class: "text-link-aksi" }, "Detail");
      btnDetail.addEventListener("click", bukaDetailTransaksi);
      body.appendChild(MugenUI.el("div", { style: "display:flex;justify-content:flex-end;margin:6px 0 4px;" }, [btnDetail]));

      body.appendChild(MugenUI.el("h2", { style: "margin-top:20px;" }, "Produk"));
      body.appendChild(MugenUI.buildTable(
        [
          { key: "no", label: "No" },
          { key: "jam", label: "Jam" },
          { key: "nama_produk", label: "Produk" },
          { key: "jumlah", label: "Jumlah" },
          { key: "nominal", label: "Nominal", format: (v) => MugenUI.formatRupiah(v) },
          { key: "pos_id", label: "Aksi", format: (v) => kolomAksi(v) },
        ],
        produkRows,
        { emptyText: "Belum ada transaksi produk hari ini." },
      ));
    }

    async function muatUlangPaksa() {
      let hasil;
      try {
        hasil = await MugenApi.get("/api/pos/transaksi-hari-ini");
      } catch (e) {
        body.innerHTML = "";
        body.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
        return;
      }
      _cacheTransaksiHariIni = { userId, tanggal: tanggalHariIni, data: hasil };
      MugenState.tandaiHalamanBersih("pos_transaksi");
      tampilkanData(hasil);
    }

    // PERMINTAAN Owner: tab ini TIDAK PERNAH loading kalau sudah pernah
    // dibuka sesi ini untuk tanggal yang sama -- baris baru masuk lewat
    // _suntikTransaksiBaru() (dipanggil begitu SATU transaksi POS lunas,
    // lihat jalankanWizardKasir()), BUKAN fetch ulang di sini.
    //
    // BUGFIX (dilaporkan Owner: "tidak menyuntik data diam-diam kalau ada
    // user LAIN yang input"): syarat TAMBAHAN di atas supaya tab ini TETAP
    // dianggap "bersih" HANYA kalau tidak ada mutasi yang relevan (termasuk
    // dari SESI/DEVICE LAIN -- tidak bisa dideteksi real-time, tapi paling
    // tidak fetch ulang penuh terjadi begitu Owner/Kasir di device INI
    // sendiri melakukan APA PUN yang lain lalu kembali ke tab ini, bukan
    // menunggu F5 selamanya) -- lihat catatan "pos_transaksi" di api.js.
    //
    // FITUR Notifikasi Push "Transaksi POS Baru" (PERMINTAAN Owner,
    // "kerjakan dengan teliti"): tab ini SELALU jadi target "tampil ulang"
    // live kalau tab ini yang sedang aktif -- diisi DI SINI (bukan di
    // dalam cabang if/muatUlangPaksa di bawah) supaya berlaku utk KEDUA
    // jalur (cache hit MAUPUN fetch fresh), persis seperti pola
    // pages/booking.js::_bookingSuntikBaris. suntikTransaksiLunas() (lihat
    // atas) memanggil ini setelah _suntikTransaksiBaru() menyisipkan baris
    // dari checkout DEVICE LAIN ke cache, supaya DOM yang SEDANG terlihat
    // ikut ter-update SEKETIKA, bukan cuma cache-nya saja (yang baru
    // kelihatan "nanti" begitu tab ini dibuka lagi).
    _transaksiHariIniTampilUlang = () => { if (_cacheTransaksiHariIni) tampilkanData(_cacheTransaksiHariIni.data); };
    if (_cacheTransaksiHariIni && _cacheTransaksiHariIni.userId === userId && _cacheTransaksiHariIni.tanggal === tanggalHariIni
        && !MugenState.halamanPerluRefresh("pos_transaksi")) {
      tampilkanData(_cacheTransaksiHariIni.data);
      return;
    }
    body.appendChild(MugenUI.skeleton("table", { cols: 4, rows: 3 }));
    await muatUlangPaksa();
  }

  return { render, suntikBookingLunas, hapusBookingDariPos, suntikTransaksiLunas, suntikDraftBerubah };
})();

window.PagePos = PagePos;
