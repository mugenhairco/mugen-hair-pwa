// pages/rekap.js

const PageRekap = (() => {
  // PERMINTAAN OWNER: pola SAMA seperti dashboard_owner.js::_cacheTerakhir
  // -- simpan hasil fetch TERAKHIR tiap tab (Transaksi/Bulanan/Pengeluaran,
  // key dibedakan lewat `tab` di bawah) di LUAR render() (modul-level) supaya
  // bertahan lintas navigasi menu. Kalau Rekap dibuka lagi TANPA ada
  // simpan/edit/hapus apa pun sejak terakhir kali TAB itu berhasil dimuat
  // (lihat state.js::halamanPerluRefresh("rekap")) DAN filter (url) yang
  // aktif sama persis, tampilkan ulang data ini TANPA fetch/skeleton.
  let _cacheTerakhir = {}; // { [tab]: { userId, url, data } }

  function _ambilDariCache(tab, userId, url) {
    const c = _cacheTerakhir[tab];
    if (!c || c.userId !== userId || c.url !== url) return null;
    return c.data;
  }

  function _simpanKeCache(tab, userId, url, data) {
    _cacheTerakhir[tab] = { userId, url, data };
  }

  // FITUR "Rekap tidak refresh, cuma tambah baris diam-diam" (PERMINTAAN
  // Owner, pola sama Transaksi Hari Ini POS/Booking Mandiri): dipanggil
  // pages/input_data.js SETELAH simpan transaksi sukses. HANYA mengubah
  // cache tab "Transaksi" (kalau PERNAH dimuat sesi ini & filter tahun/
  // bulan/barber yang di-cache cocok dengan baris baru ini) -- TIDAK PERNAH
  // memicu fetch/re-render DOM apa pun di sini. Ini SENGAJA cukup: SPA satu-
  // halaman-aktif-sekaligus (hash router), jadi kalau Rekap sedang tidak
  // dilihat (yang hampir selalu benar -- pemicu datang dari menu Input Data
  // yang berbeda), baris baru ini otomatis "sudah ada" begitu user pindah
  // ke Rekap berikutnya (cache hit, TANPA skeleton/fetch) -- tujuan "tidak
  // refresh sama sekali" tercapai tanpa perlu menyentuh DOM yang sedang
  // tidak tampil.
  function suntikBarisTransaksi(baris) {
    const c = _cacheTerakhir["transaksi"];
    if (!c || !baris || !Array.isArray(c.data)) return;
    if (c.userId !== MugenState.getUser().id) return;
    const params = new URLSearchParams((c.url.split("?")[1] || ""));
    const tahunCache = Number(params.get("tahun"));
    const bulanCache = Number(params.get("bulan"));
    const barberCache = params.get("barber_id");
    const [tahunBaris, bulanBaris] = String(baris.tanggal || "").split("-").map(Number);
    if (tahunBaris !== tahunCache || bulanBaris !== bulanCache) return; // filter bulan/tahun tidak cocok
    if (barberCache && String(baris.barber_id) !== barberCache) return; // filter barber tidak cocok
    // Upsert (bukan skip-kalau-sudah-ada) -- "Koreksi" transaksi yang SUDAH
    // tampil di cache juga lewat jalur ini (id-nya sama, nilainya beda),
    // baris lama WAJIB diganti, bukan dibiarkan basi sampai refresh manual.
    //
    // Baris sumber="pos"/"booking"/"manual_customer" dibangun ULANG (hapus
    // baris lama + tambah baris baru) setiap kali sinkronisasi jalan --
    // id-nya TIDAK stabil antar rebuild, beda dengan Koreksi manual (PUT
    // in-place, id tetap). Untuk sumber otomatis itu, cocokkan upsert lewat
    // (barber_id, tanggal, sumber) -- SELALU maksimal 1 baris per kombinasi
    // itu (invarian rebuild-nya), bukan lewat id yang bisa berubah-ubah.
    const idxLama = baris.sumber
      ? c.data.findIndex((r) => r.tipe === "transaksi" && r.barber_id === baris.barber_id
          && r.tanggal === baris.tanggal && r.sumber === baris.sumber)
      : c.data.findIndex((r) => r.tipe === "transaksi" && r.id === baris.id);
    if (idxLama >= 0) c.data[idxLama] = baris;
    else c.data.push(baris);
    // Urutan SAMA PERSIS get_rekap_transaksi_list() (database.py): nama_barber
    // ASC dulu (sort stabil), baru tanggal DESC -- hasil akhirnya "tanggal
    // terbaru dulu, nama_barber A-Z per tanggal yang sama".
    c.data.sort((a, b) => (a.nama_barber < b.nama_barber ? -1 : a.nama_barber > b.nama_barber ? 1 : 0));
    c.data.sort((a, b) => (a.tanggal < b.tanggal ? 1 : a.tanggal > b.tanggal ? -1 : 0));
    // BUGFIX "Rekap masih loading walau sudah disuntik" (PERMINTAAN Owner):
    // api.js menandai flag "rekap_transaksi" KOTOR untuk SETIAP mutasi di
    // seluruh aplikasi (termasuk mutasi POS/Booking yang BARUSAN memicu
    // suntik ini) -- tanpa baris ini, cache SUDAH akurat tapi flag-nya
    // tetap kotor, jadi load() di renderTransaksi() tetap fetch ulang +
    // skeleton begitu tab ini dibuka lagi. Dibersihkan HANYA di sini
    // (bukan "rekap" -- itu tetap punya Bulanan/Pengeluaran, keduanya
    // belum punya suntik jadi memang harus tetap fetch ulang).
    MugenState.tandaiHalamanBersih("rekap_transaksi");
  }

  // FITUR "+ Tambah Transaksi" REPLACE TOTAL (PERMINTAAN Owner): BEDA dari
  // suntikBarisTransaksi() di atas (upsert SATU baris per sumber) -- submit
  // "Tambah Transaksi" menghapus SELURUH baris transaksi barber+tanggal
  // ini di server APA PUN sumbernya (lihat database.py::
  // ganti_transaksi_barber_hari()), jadi cache di sini juga harus
  // membuang SEMUA baris lama untuk barber+tanggal itu (bukan cuma yang
  // sumbernya sama) sebelum memasukkan baris penggantinya -- supaya
  // tidak ada baris basi (mis. bekas sumber="pos") yang tertinggal di
  // cache padahal sudah tidak ada lagi di server. Return array data baru
  // (untuk dirender ULANG instan oleh pemanggil, lihat renderTransaksi())
  // kalau berhasil disuntik, atau null kalau tidak berlaku (filter tidak
  // cocok/cache belum ada) -- pemanggil fallback ke load() biasa.
  function gantiBarisTransaksi(baris) {
    const c = _cacheTerakhir["transaksi"];
    if (!c || !baris || !Array.isArray(c.data)) return null;
    if (c.userId !== MugenState.getUser().id) return null;
    const params = new URLSearchParams((c.url.split("?")[1] || ""));
    const tahunCache = Number(params.get("tahun"));
    const bulanCache = Number(params.get("bulan"));
    const barberCache = params.get("barber_id");
    const [tahunBaris, bulanBaris] = String(baris.tanggal || "").split("-").map(Number);
    if (tahunBaris !== tahunCache || bulanBaris !== bulanCache) return null;
    if (barberCache && String(baris.barber_id) !== barberCache) return null;
    c.data = c.data.filter((r) => !(r.tipe === "transaksi" && r.barber_id === baris.barber_id && r.tanggal === baris.tanggal));
    c.data.push(baris);
    c.data.sort((a, b) => (a.nama_barber < b.nama_barber ? -1 : a.nama_barber > b.nama_barber ? 1 : 0));
    c.data.sort((a, b) => (a.tanggal < b.tanggal ? 1 : a.tanggal > b.tanggal ? -1 : 0));
    MugenState.tandaiHalamanBersih("rekap_transaksi");
    return c.data;
  }

  // BUGFIX "Rekap masih loading walau cuma input Pengeluaran" (PERMINTAAN
  // Owner): tab Pengeluaran di Rekap SEBELUMNYA memang belum punya suntik
  // (lihat catatan di suntikBarisTransaksi() di atas: "Bulanan/Pengeluaran,
  // keduanya belum punya suntik jadi memang harus tetap fetch ulang") --
  // api.js menandai flag "rekap" KOTOR untuk SETIAP mutasi di aplikasi
  // (termasuk Tambah/Koreksi Pengeluaran yang BARUSAN memicu ini), jadi tab
  // ini SELALU fetch ulang (skeleton ~beberapa detik) begitu Rekap dibuka
  // lagi. Dipanggil pages/pengeluaran.js SETELAH simpan (Tambah/Koreksi)
  // sukses dengan baris HASIL simpan (response POST/PUT, sudah termasuk
  // nama_barber) -- upsert by id ke cache tab "Pengeluaran" (kalau PERNAH
  // dimuat sesi ini & filter tahun/bulan yang di-cache cocok dengan baris
  // ini), lalu bersihkan flag "rekap" supaya tab ini TIDAK fetch ulang.
  // AMAN membersihkan "rekap" (bukan cuma bagian "pengeluaran") karena tab
  // Bulanan tidak memuat data Pengeluaran sama sekali (murni rekap per-
  // barber: komisi/tips/uang harian/dst, lihat renderBulanan() di bawah).
  function suntikBarisPengeluaran(p) {
    const c = _cacheTerakhir["pengeluaran"];
    if (!c || !p || !c.data || !Array.isArray(c.data.daftar)) return;
    if (c.userId !== MugenState.getUser().id) return;
    const params = new URLSearchParams((c.url.split("?")[1] || ""));
    const tahunCache = Number(params.get("tahun"));
    const bulanCache = Number(params.get("bulan"));
    const [tahunBaris, bulanBaris] = String(p.tanggal || "").split("-").map(Number);
    if (tahunBaris !== tahunCache || bulanBaris !== bulanCache) return; // filter bulan/tahun tidak cocok (mis. Koreksi pindah bulan) -- biarkan flag tetap kotor, fetch ulang biasa yang akan memperbaikinya
    const idx = c.data.daftar.findIndex((r) => r.id === p.id);
    if (idx >= 0) {
      c.data.total += p.jumlah - c.data.daftar[idx].jumlah;
      c.data.daftar[idx] = p;
    } else {
      c.data.daftar.push(p);
      c.data.total += p.jumlah;
    }
    // Urutan SAMA PERSIS get_pengeluaran_list() (pengeluaran_db.py): tanggal DESC, id DESC.
    c.data.daftar.sort((a, b) => (a.tanggal < b.tanggal ? 1 : a.tanggal > b.tanggal ? -1 : b.id - a.id));
    MugenState.tandaiHalamanBersih("rekap");
  }

  // Pasangan suntikBarisPengeluaran() di atas untuk Hapus -- dipanggil
  // pages/pengeluaran.js SETELAH hapus sukses dengan id & tanggal baris
  // yang baru dihapus (tanggal dipakai utk cocokkan filter bulan/tahun
  // cache, SAMA seperti suntikBarisPengeluaran()).
  function hapusBarisPengeluaran(id, tanggal) {
    const c = _cacheTerakhir["pengeluaran"];
    if (!c || !c.data || !Array.isArray(c.data.daftar)) return;
    if (c.userId !== MugenState.getUser().id) return;
    const params = new URLSearchParams((c.url.split("?")[1] || ""));
    const tahunCache = Number(params.get("tahun"));
    const bulanCache = Number(params.get("bulan"));
    const [tahunBaris, bulanBaris] = String(tanggal || "").split("-").map(Number);
    if (tahunBaris !== tahunCache || bulanBaris !== bulanCache) return;
    const idx = c.data.daftar.findIndex((r) => r.id === id);
    if (idx < 0) return;
    c.data.total -= c.data.daftar[idx].jumlah;
    c.data.daftar.splice(idx, 1);
    MugenState.tandaiHalamanBersih("rekap");
  }

  // Perbaikan Alur Cetak PDF: tombol "Cetak PDF" TIDAK lagi langsung
  // mengunduh -- PDF dibuat lalu ditampilkan dulu lewat MugenPdfPreview
  // (Preview PDF di dalam aplikasi, dengan Zoom/Nomor Halaman/Download
  // PDF/Print/Kembali), unduhan sungguhan hanya terjadi kalau tombol
  // "Download PDF" DI DALAM preview itu yang ditekan. `computeOptions`
  // dipanggil ULANG setiap kali tombol diklik (bukan sekali di awal),
  // supaya filter yang aktif SAAT diklik yang dipakai -- return
  // { generate: () => Promise<Blob>, filename: string }.
  function tombolCetakPdf(computeOptions) {
    // Feature Gating "export_pdf": tanpa fitur ini di paket, tombolnya
    // diganti blok upgrade -- SATU titik keputusan untuk seluruh 3 pemanggil
    // tombolCetakPdf() di file ini (Rekap Detail/Ringkasan, Rekap Pengeluaran).
    if (typeof MugenFeature !== "undefined" && !MugenFeature.has("export_pdf")) {
      return MugenFeature.upgradeBlock("Export PDF");
    }
    // PERMINTAAN Owner ("tombol Cetak PDF ikutin warna yang sudah ada di
    // pengaturan aplikasi"): class "btn-primary" -- warna aksen yang SAMA
    // dipakai tombol utama lain di seluruh app (Simpan, dst), bukan warna
    // biru-ungu di gambar referensi (itu cuma contoh layout, bukan warna).
    const btn = MugenUI.el("button", { class: "btn-primary" }, "Cetak PDF");
    btn.addEventListener("click", () => {
      const { generate, filename } = computeOptions();
      MugenPdfPreview.open({ generate, filename });
    });
    return btn;
  }

  // Tombol aksi generik dipakai kolom "Aksi" Rekap Transaksi (Owner) --
  // satu pola untuk hapus transaksi/reimburse/Keterangan Libur dan
  // batalkan pembayaran kasbon, supaya konfirmasi/loading/toast/refresh-nya
  // konsisten. `onSelesai` (opsional) dipanggil setelah sukses menghapus/
  // membatalkan -- kalau TIDAK diisi (default, dipakai renderTransaksi()),
  // baris tabel ini sendiri yang dihapus dari DOM (btn.closest("tr")),
  // baris di bawahnya otomatis naik -- TIDAK memuat ulang seluruh tabel
  // (permintaan Owner: loading cukup di tombolnya sendiri, bukan reset
  // semua baris + skeleton lagi).
  // `hapusBody` (opsional): baris "libur" TIDAK punya `id` (dihapus lewat
  // kombinasi barber_id+tanggal di body, bukan lewat path param seperti
  // transaksi/reimburse/kasbon/non_barber -- lihat DELETE /api/input-data/libur,
  // pola SAMA seperti tombol "Batalkan Libur" yang sudah ada di Input Data).
  function tombolAksi({ label, title, confirmTitle, confirmMessage, hapusUrl, hapusBody, pesanSukses, onSelesai }) {
    const wrap = MugenUI.el("div", { class: "actions-cell" });
    const btn = MugenUI.el("button", { type: "button", class: "btn-danger", title }, label);
    btn.addEventListener("click", async () => {
      const ok = await MugenUI.confirmModal({
        title: confirmTitle,
        message: confirmMessage,
        confirmText: "Ya, Lanjutkan",
        cancelText: "Batal",
        danger: true,
      });
      if (!ok) return;
      try {
        // REVISI UI/UX Premium: spinner inline di tombol sendiri, bukan overlay layar penuh
        await MugenUI.withButtonLoading(btn, () => MugenApi.del(hapusUrl, hapusBody));
        MugenUI.toast(pesanSukses, "success", { force: true });
        if (onSelesai) {
          onSelesai();
        } else {
          const tr = btn.closest("tr");
          if (tr) tr.remove();
        }
      } catch (e) {
        MugenUI.toast(e.detail && e.detail.detail ? e.detail.detail : e.message, "error");
      }
    });
    wrap.appendChild(btn);
    return wrap;
  }

  // PENGHAPUSAN Input Data Barber: `services` dulu selalu ikut dimuat di
  // pages/input_data.js (form Tambah/Koreksi Transaksi) -- di sini HANYA
  // dibutuhkan kalau tombol "✏ Koreksi" (lihat bukaModalKoreksi() di bawah)
  // benar-benar diklik, jadi fetch-nya lazy (sekali saja, di-cache module-
  // level) alih-alih ikut membebani pemuatan awal Rekap yang jauh lebih
  // sering dibuka.
  let _servicesPromise = null;
  function _ambilServices() {
    if (!_servicesPromise) _servicesPromise = MugenApi.get("/api/input-data/services", { useCache: true });
    return _servicesPromise;
  }

  // PENGHAPUSAN Input Data Barber: modal Koreksi Transaksi -- pola overlay/
  // box/modal-actions SAMA PERSIS MugenUI.confirmModal()/infoModal() (lihat
  // ui.js), dibuat lokal di sini (bukan di ui.js) karena isinya FORM
  // (tanggal/barber/qty per service/tips/catatan), bukan cuma teks/tombol.
  // Field & alur SAMA PERSIS form Koreksi lama di input_data.js -- endpoint
  // backend (GET/PUT /api/input-data/transaksi/{id}) TIDAK berubah.
  async function bukaModalKoreksi(transaksiId, { karyawanPromise, onSelesai }) {
    const overlay = MugenUI.el("div", { class: "modal-overlay" });
    const box = MugenUI.el("div", { class: "modal-box" });
    box.appendChild(MugenUI.el("h3", {}, `Koreksi Transaksi #${transaksiId}`));
    const body = MugenUI.el("div", { style: "text-align:left;" }, MugenUI.skeleton("card", { lines: 4 }));
    box.appendChild(body);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    function tutup() {
      overlay.classList.add("closing");
      setTimeout(() => overlay.remove(), 120);
    }
    overlay.addEventListener("click", (e) => { if (e.target === overlay) tutup(); });

    let transaksi, services, barbersOnly;
    try {
      [transaksi, services, { barbersOnly }] = await Promise.all([
        MugenApi.get(`/api/input-data/transaksi/${transaksiId}`),
        _ambilServices(),
        karyawanPromise,
      ]);
    } catch (e) {
      body.innerHTML = "";
      body.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
      body.appendChild(MugenUI.el("div", { class: "modal-actions" },
        MugenUI.el("button", { type: "button", onclick: tutup }, "Tutup")));
      return;
    }

    body.innerHTML = "";
    const inputTanggal = MugenUI.el("input", { type: "date", value: transaksi.tanggal });
    const selBarber = MugenUI.el("select");
    for (const b of barbersOnly) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    selBarber.value = String(transaksi.barber_id);
    const itemInputs = {}; // service_id -> input jumlah
    const itemsAwal = {};
    for (const it of transaksi.items) itemsAwal[it.service_id] = it.jumlah;
    const serviceRows = services.map((s) => {
      const inp = MugenUI.el("input", {
        type: "number", min: "0", placeholder: "—", style: "max-width:90px;",
        value: itemsAwal[s.id] ? MugenUI.nilaiTampilAngka(itemsAwal[s.id]) : "",
      });
      // PERMINTAAN Owner: pakai keypad angka custom yang sudah ada
      // (MugenUI.attachNumericKeypad(), dipakai POS untuk Tips/Uang
      // Cash) -- di HP (touch) keyboard OS diganti keypad angka custom
      // milik aplikasi sendiri, konsisten dengan form lain. Jumlah per-
      // service BUKAN nominal Rupiah, jadi TANPA opts.rupiah (angka
      // polos, bukan "Rp ...").
      MugenUI.attachNumericKeypad(inp);
      itemInputs[s.id] = inp;
      // BUGFIX "form goyang-goyang/overflow horizontal di HP" (PERMINTAAN
      // Owner): `.row > * { min-width: 140px }` (style.css, dipakai filter
      // bar lain) ikut membebani KEDUA div ini (flex:2 & flex:0 0 100px
      // TIDAK cukup, min-width menang di atas flex-basis) -- baris 2
      // kolom (nama service panjang + input qty sempit) jadi butuh ruang
      // lebih lebar dari layar HP sempit. min-width:0 eksplisit di sini
      // (inline style menang atas class) mengembalikan lebar sesuai
      // flex-basis yang dimaksud.
      return MugenUI.el("div", { class: "row", style: "align-items:center;" }, [
        MugenUI.el("div", { style: "flex:2;min-width:0;" }, `${s.nama} (${MugenUI.formatRupiah(s.harga)})`),
        MugenUI.el("div", { style: "flex:0 0 90px;min-width:0;" }, inp),
      ]);
    });
    const inputTips = MugenUI.el("input", { type: "number", min: "0", placeholder: "—", value: MugenUI.nilaiTampilAngka(transaksi.tips) });
    MugenUI.attachNumericKeypad(inputTips, { rupiah: true });
    const inputCatatan = MugenUI.el("input", { type: "text", placeholder: "Opsional", value: transaksi.catatan || "" });
    const formError = MugenUI.el("div", { class: "login-error" });
    const btnSimpan = MugenUI.el("button", { type: "button", class: "btn-primary" }, "Simpan Koreksi");
    const btnBatal = MugenUI.el("button", { type: "button" }, "Batal");

    body.appendChild(MugenUI.el("label", {}, "Tanggal"));
    body.appendChild(inputTanggal);
    body.appendChild(MugenUI.el("label", {}, "Barber"));
    body.appendChild(MugenUI.selectIcon(MugenIcons.karyawan, selBarber));
    body.appendChild(MugenUI.el("label", {}, "Service & Jumlah"));
    for (const row of serviceRows) body.appendChild(row);
    body.appendChild(MugenUI.el("label", {}, "Tips (Rp)"));
    body.appendChild(inputTips);
    body.appendChild(MugenUI.el("label", {}, "Catatan"));
    body.appendChild(inputCatatan);
    body.appendChild(formError);
    box.appendChild(MugenUI.el("div", { class: "modal-actions" }, [btnBatal, btnSimpan]));

    btnBatal.addEventListener("click", tutup);
    btnSimpan.addEventListener("click", async () => {
      formError.textContent = "";
      const items = Object.entries(itemInputs)
        .map(([service_id, inp]) => ({ service_id: Number(service_id), jumlah: Number(inp.value) || 0 }))
        .filter((it) => it.jumlah > 0);
      if (items.length === 0) { formError.textContent = "Minimal satu service harus diisi jumlahnya."; return; }
      try {
        const hasil = await MugenUI.withButtonLoading(btnSimpan, () => MugenApi.put(`/api/input-data/transaksi/${transaksiId}`, {
          tanggal: inputTanggal.value, barber_id: Number(selBarber.value), items,
          // PERMINTAAN Owner (keypad angka custom): inputTips.value SEKARANG
          // berformat "Rp ..." (attachNumericKeypad({rupiah:true})) -- WAJIB
          // dibaca lewat MugenUI.parseAngka(), bukan Number() (akan selalu
          // NaN/0 kalau langsung Number() dipanggil pada string berformat).
          tips: MugenUI.parseAngka(inputTips.value) || 0, catatan: inputCatatan.value || null,
        }));
        MugenUI.toast("Transaksi dikoreksi.", "success");
        tutup();
        if (onSelesai) onSelesai(hasil);
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });
  }

  // FITUR "+ Tambah Transaksi" (PERMINTAAN Owner): untuk transaksi walk-in
  // yang beneran kelewat tidak diinput sama sekali di hari itu (BEDA dari
  // Koreksi di atas yang mengedit baris yang SUDAH ADA) -- bentuknya
  // SENGAJA dibuat mirip bukaModalKoreksi() di atas (field yang sama).
  // Dikirim dengan `susulan: true` supaya backend (routers/input_data.py::
  // tambah_transaksi()) tidak menolak walau tanggalnya sudah terpakai
  // mode POS/Manual Customer hari itu -- TAPI (REVISI PERMINTAAN Owner)
  // submit ini MENGGANTI TOTAL seluruh baris transaksi barber+tanggal
  // itu (apa pun sumbernya), BUKAN menambah di samping yang sudah ada --
  // lihat db.ganti_transaksi_barber_hari(). Supaya admin tidak tidak
  // sengaja menghapus data yang sudah benar, begitu Barber & Tanggal
  // SAMA-SAMA terisi, form ini PRE-FILL otomatis dari GET
  // /transaksi-gabungan (gabungan SEMUA baris yang sudah ada untuk
  // kombinasi itu) -- admin tinggal MENAMBAHKAN yang kelewat di form
  // yang SAMA, baris hasilnya ditandai sumber="manual_susulan", tetap
  // boleh di-Koreksi/Hapus seperti baris manual biasa (TIDAK masuk
  // SUMBER_TERKELOLA_OTOMATIS di bawah).
  async function bukaModalTambah({ karyawanPromise, onSelesai }) {
    const overlay = MugenUI.el("div", { class: "modal-overlay" });
    const box = MugenUI.el("div", { class: "modal-box" });
    box.appendChild(MugenUI.el("h3", {}, "Tambah Transaksi Susulan"));
    const body = MugenUI.el("div", { style: "text-align:left;" }, MugenUI.skeleton("card", { lines: 4 }));
    box.appendChild(body);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    function tutup() {
      overlay.classList.add("closing");
      setTimeout(() => overlay.remove(), 120);
    }
    overlay.addEventListener("click", (e) => { if (e.target === overlay) tutup(); });

    let services, barbersOnly;
    try {
      [services, { barbersOnly }] = await Promise.all([_ambilServices(), karyawanPromise]);
    } catch (e) {
      body.innerHTML = "";
      body.appendChild(MugenUI.errorState(e.detail && e.detail.detail ? e.detail.detail : e.message));
      body.appendChild(MugenUI.el("div", { class: "modal-actions" },
        MugenUI.el("button", { type: "button", onclick: tutup }, "Tutup")));
      return;
    }

    body.innerHTML = "";
    body.appendChild(MugenUI.el("div", { class: "subtitle", style: "margin-top:-4px;" },
      "Untuk transaksi walk-in yang kelewat tidak diinput sama sekali di hari itu. Simpan akan MENGGANTI TOTAL seluruh transaksi barber ini pada tanggal yang dipilih (bukan menambah di samping yang sudah ada) -- data yang sudah tercatat otomatis dimuat di bawah begitu Barber & Tanggal dipilih."));
    const inputTanggal = MugenUI.el("input", { type: "date", value: MugenUI.isoHariIniWib() });
    const selBarber = MugenUI.el("select", {}, MugenUI.el("option", { value: "" }, "-- Pilih Barber --"));
    for (const b of barbersOnly) selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
    const itemInputs = {}; // service_id -> input jumlah
    const serviceRows = services.map((s) => {
      const inp = MugenUI.el("input", { type: "number", min: "0", placeholder: "—", style: "max-width:90px;" });
      // PERMINTAAN Owner: pakai keypad angka custom yang sudah ada -- lihat
      // catatan lengkap di bukaModalKoreksi() (pola sama persis di sini).
      MugenUI.attachNumericKeypad(inp);
      itemInputs[s.id] = inp;
      // BUGFIX "form goyang-goyang/overflow horizontal di HP" -- lihat
      // catatan lengkap di bukaModalKoreksi() (pola sama persis di sini).
      return MugenUI.el("div", { class: "row", style: "align-items:center;" }, [
        MugenUI.el("div", { style: "flex:2;min-width:0;" }, `${s.nama} (${MugenUI.formatRupiah(s.harga)})`),
        MugenUI.el("div", { style: "flex:0 0 90px;min-width:0;" }, inp),
      ]);
    });
    const inputTips = MugenUI.el("input", { type: "number", min: "0", placeholder: "—" });
    MugenUI.attachNumericKeypad(inputTips, { rupiah: true });
    const inputCatatan = MugenUI.el("input", { type: "text", placeholder: "Opsional, mis. \"Susulan lupa input\"" });
    const statusPrefill = MugenUI.el("div", { class: "subtitle", style: "margin:4px 0 0;" });
    const formError = MugenUI.el("div", { class: "login-error" });
    const btnSimpan = MugenUI.el("button", { type: "button", class: "btn-primary" }, "Simpan");
    const btnBatal = MugenUI.el("button", { type: "button" }, "Batal");

    body.appendChild(MugenUI.el("label", {}, "Tanggal"));
    body.appendChild(inputTanggal);
    body.appendChild(MugenUI.el("label", {}, "Barber"));
    body.appendChild(MugenUI.selectIcon(MugenIcons.karyawan, selBarber));
    body.appendChild(statusPrefill);
    body.appendChild(MugenUI.el("label", {}, "Service & Jumlah"));
    for (const row of serviceRows) body.appendChild(row);
    body.appendChild(MugenUI.el("label", {}, "Tips (Rp)"));
    body.appendChild(inputTips);
    body.appendChild(MugenUI.el("label", {}, "Catatan"));
    body.appendChild(inputCatatan);
    body.appendChild(formError);
    box.appendChild(MugenUI.el("div", { class: "modal-actions" }, [btnBatal, btnSimpan]));

    // FITUR Pre-fill (PERMINTAAN Owner, "biar lebih aman" -- supaya admin
    // tidak tidak sengaja menghapus data yang sudah benar, karena Simpan
    // MENGGANTI TOTAL): begitu Barber & Tanggal SAMA-SAMA terisi, ambil
    // gabungan baris yang sudah ada untuk kombinasi itu lewat
    // GET /transaksi-gabungan, isi ulang form ini dengan hasilnya.
    // `prefillToken` menghindari race kalau barber/tanggal diganti lagi
    // SEBELUM fetch sebelumnya selesai (hasil fetch basi diabaikan).
    let prefillToken = 0;
    async function muatPrefill() {
      for (const inp of Object.values(itemInputs)) inp.value = "";
      inputTips.value = "";
      inputCatatan.value = "";
      statusPrefill.textContent = "";
      if (!selBarber.value || !inputTanggal.value) return;
      const token = ++prefillToken;
      statusPrefill.textContent = "Memuat data yang sudah ada...";
      try {
        const qs = new URLSearchParams({ barber_id: selBarber.value, tanggal: inputTanggal.value });
        const hasil = await MugenApi.get(`/api/input-data/transaksi-gabungan?${qs}`);
        if (token !== prefillToken) return;
        for (const it of hasil.items) {
          if (itemInputs[it.service_id]) itemInputs[it.service_id].value = MugenUI.nilaiTampilAngka(it.jumlah);
        }
        // PERMINTAAN Owner (keypad angka custom): inputTips SEKARANG
        // berformat "Rp ..." (attachNumericKeypad({rupiah:true})) --
        // set .value langsung TIDAK memicu listener "input" milik
        // keypad itu, jadi format Rupiah-nya diterapkan manual di sini.
        if (hasil.tips) inputTips.value = MugenUI.formatRupiah(hasil.tips);
        if (hasil.catatan) inputCatatan.value = hasil.catatan;
        statusPrefill.textContent = hasil.ada_data
          ? "Data yang sudah tercatat untuk Barber & Tanggal ini sudah dimuat di atas -- tambahkan yang kelewat, lalu Simpan."
          : "Belum ada transaksi tercatat untuk Barber & Tanggal ini.";
      } catch (e) {
        if (token !== prefillToken) return;
        statusPrefill.textContent = "";
        formError.textContent = "Gagal memuat data yang sudah ada: " + (e.detail && e.detail.detail ? e.detail.detail : e.message);
      }
    }
    selBarber.addEventListener("change", muatPrefill);
    inputTanggal.addEventListener("change", muatPrefill);

    btnBatal.addEventListener("click", tutup);
    btnSimpan.addEventListener("click", async () => {
      formError.textContent = "";
      if (!selBarber.value) { formError.textContent = "Barber wajib dipilih."; return; }
      const items = Object.entries(itemInputs)
        .map(([service_id, inp]) => ({ service_id: Number(service_id), jumlah: Number(inp.value) || 0 }))
        .filter((it) => it.jumlah > 0);
      if (items.length === 0) { formError.textContent = "Minimal satu service harus diisi jumlahnya."; return; }
      try {
        const hasil = await MugenUI.withButtonLoading(btnSimpan, () => MugenApi.post("/api/input-data/transaksi", {
          tanggal: inputTanggal.value, barber_id: Number(selBarber.value), items,
          // PERMINTAAN Owner (keypad angka custom): lihat catatan di
          // bukaModalKoreksi() -- inputTips.value berformat "Rp ...",
          // WAJIB dibaca lewat MugenUI.parseAngka().
          tips: MugenUI.parseAngka(inputTips.value) || 0, catatan: inputCatatan.value || null, susulan: true,
        }));
        MugenUI.toast("Transaksi barber ini pada tanggal tersebut diperbarui.", "success");
        tutup();
        // FITUR "Rekap tidak refresh, cuma diam-diam diperbarui" (PERMINTAAN
        // Owner, pola SAMA pos.js::suntikKeRekap()): `hasil` di atas baris
        // transaksi MENTAH (database.get_transaksi()), BUKAN bentuk baris
        // Rekap yang sudah dihitung (komisi/pendapatan/uang harian/dst) --
        // ambil dulu bentuk yang benar lewat endpoint yang sama dipakai
        // suntik POS, baru serahkan ke onSelesai (pemanggil di
        // renderTransaksi() yang tahu cara menyuntik+render ulang instan).
        if (onSelesai) {
          MugenApi.get(`/api/rekap/transaksi/baris/${hasil.id}`).then(onSelesai).catch(() => onSelesai(null));
        }
      } catch (e) {
        formError.textContent = e.detail && e.detail.detail ? e.detail.detail : e.message;
      }
    });
  }

  async function render(root) {
    const user = MugenState.getUser();
    const isAdmin = user.role === "admin" || user.role === "staff";
    const today = new Date();

    // REVISI Hak Akses Granular: kolom "Aksi" (Hapus Transaksi/Reimburse/
    // Keterangan Libur/Gaji Non-Barber, Batalkan Kasbon) di tab Rekap >
    // Transaksi DULU hanya tampil untuk Owner -- sekarang Staff yang
    // Role-nya diberi izin terkait JUGA bisa melihat tombolnya,
    // masing-masing jenis baris dicek lewat key izin yang SAMA PERSIS
    // dipakai endpoint backend-nya (lihat routers/input_data.py::
    // hapus_transaksi()/batalkan_libur() -- "izin_input_data_hapus",
    // routers/reimburse.py::hapus_reimburse_dari_rekap() -- "izin_reimburse_
    // hapus", routers/kasbon.py::batalkan_pembayaran() -- "izin_kasbon",
    // routers/data_non_barber.py::hapus_data_non_barber() -- "izin_data_
    // non_barber_hapus"). Kolom
    // itu sendiri TETAP tidak pernah tampil untuk Barber (!isAdmin) --
    // konsep "Aksi" administratif ini tidak relevan untuk mereka.
    const bolehHapusTransaksi = isAdmin && (await MugenMenuAccess.has("izin_input_data_hapus"));
    // PENGHAPUSAN Input Data Barber: tombol "✏ Koreksi" (dulu di menu Input
    // Data, mode "Input Data Barber", sekarang dihapus) dipindah ke sini --
    // izin SAMA PERSIS dipakai endpoint backend-nya (routers/input_data.py::
    // koreksi_transaksi(), "izin_input_data_kelola"), TERPISAH dari izin
    // Hapus di atas (kelola != hapus).
    const bolehKoreksiTransaksi = isAdmin && (await MugenMenuAccess.has("izin_input_data_kelola"));
    const bolehHapusReimburse = isAdmin && (await MugenMenuAccess.has("izin_reimburse_hapus"));
    const bolehBatalKasbon = isAdmin && (await MugenMenuAccess.has("izin_kasbon"));
    const bolehHapusNonBarber = isAdmin && (await MugenMenuAccess.has("izin_data_non_barber_hapus"));
    const bolehLihatKolomAksi = isAdmin;

    root.innerHTML = "";
    root.appendChild(MugenUI.pageTitle("Rekap", MugenIcons.rekap));

    // AUDIT Hak Akses Menu (permintaan Owner): "Tidak Ada Akses" -- HANYA
    // pesan kosong, tanpa tab/data apa pun (MugenMenuAccess.get() selalu
    // balas "write" untuk Owner & Barber, jadi gate ini efektifnya HANYA
    // berlaku untuk 'staff').
    if ((await MugenMenuAccess.get("rekap")) === "none") {
      root.appendChild(MugenUI.emptyState("Anda tidak memiliki akses ke menu ini."));
      return;
    }

    // REVISI UI/UX Premium: MugenUI.tabs() (indikator geser halus otomatis)
    // menggantikan tabBar/renderTabs manual.
    const tabItems = [
      { key: "Transaksi", label: "Transaksi" },
      { key: "Bulanan", label: "Bulanan" },
      ...(isAdmin ? [{ key: "Pengeluaran", label: "Pengeluaran" }] : []),
    ];
    const body = MugenUI.el("div");
    const tabsCtl = MugenUI.tabs(tabItems, { onChange: renderBody });
    root.appendChild(tabsCtl.bar);
    root.appendChild(body);
    requestAnimationFrame(tabsCtl.moveIndicator);

    // Rekap Bulanan murni perhitungan komisi/tips/uang harian jasa potong
    // rambut -- TETAP khusus Barber (barbersOnly). Rekap Transaksi
    // menampilkan/memfilter SELURUH karyawan (barbersOnly + Kasir/OB/Kru,
    // lewat karyawanAll) sesuai permintaan revisi Karyawan Non-Barber --
    // barber non-barber otomatis tidak akan pernah punya baris transaksi
    // (Input Data tidak pernah membiarkan itu dibuat untuk non-barber),
    // jadi filter itu valid, hanya hasilnya kosong.
    let barbersOnly = [];
    let karyawanAll = [];
    // PERBAIKAN PERFORMA (keluhan Owner: menu Rekap terasa ada jeda):
    // SEBELUMNYA fetch Barber+Karyawan ini di-await DULU di sini, SEBELUM
    // renderBody() (akhir fungsi ini) sempat dipanggil sama sekali --
    // artinya WALAU data tabel Transaksi/Bulanan/Pengeluaran-nya sendiri
    // sudah bisa tampil INSTAN dari cache (_cacheTerakhir/
    // halamanPerluRefresh di atas), halaman tetap menunggu SATU round-trip
    // jaringan tambahan (fetch dropdown filter ini) lebih dulu -- BERURUTAN
    // (serial) dengan fetch data tabel, padahal daftar ini TIDAK PERNAH jadi
    // prasyarat data tabel (filter default "Semua Barber/Karyawan" tidak
    // butuh daftar namanya sudah siap). Sekarang fetch-nya TIDAK di-await di
    // sini -- dibiarkan jalan di belakang layar (Promise disimpan di
    // `karyawanPromise`), renderBody() langsung dipanggil tanpa menunggu
    // (lihat akhir fungsi ini) -- begitu Promise ini selesai, opsi dropdown
    // yang SUDAH terlanjur dirender (lihat filterBar() di bawah) disisipi
    // opsi barunya DI TEMPAT (select yang sudah ada, tanpa render ulang).
    const karyawanPromise = isAdmin
      ? Promise.all([
          MugenApi.get("/api/input-data/barbers", { useCache: true }),
          MugenApi.get("/api/input-data/karyawan", { useCache: true }),
        ])
          .then(([b, k]) => {
            barbersOnly = b;
            karyawanAll = k;
            return { barbersOnly: b, karyawanAll: k };
          })
          .catch(() => ({ barbersOnly: [], karyawanAll: [] })) // filter tetap opsional kalau gagal dimuat
      : Promise.resolve({ barbersOnly: [], karyawanAll: [] });

    function filterBar({ withBarber = true, ambilDaftarDari = (hasil) => hasil.barbersOnly, labelSemua = "Semua Barber" } = {}) {
      const selBulan = MugenUI.el("select");
      for (let m = 1; m <= 12; m++) selBulan.appendChild(MugenUI.el("option", { value: String(m) }, MugenUI.namaBulan(m)));
      selBulan.value = String(today.getMonth() + 1);
      const selTahun = MugenUI.el("select");
      for (let y = today.getFullYear() - 2; y <= today.getFullYear() + 1; y++) selTahun.appendChild(MugenUI.el("option", { value: String(y) }, String(y)));
      selTahun.value = String(today.getFullYear());
      const selBarber = withBarber && isAdmin ? MugenUI.el("select") : null;
      if (selBarber) {
        selBarber.appendChild(MugenUI.el("option", { value: "" }, labelSemua));
        // Opsi barber/karyawan disisipi ASINKRON begitu karyawanPromise
        // selesai -- tabel di atas TIDAK PERNAH menunggu ini.
        karyawanPromise.then((hasil) => {
          for (const b of ambilDaftarDari(hasil)) {
            selBarber.appendChild(MugenUI.el("option", { value: String(b.id) }, b.nama));
          }
        });
      }
      const row = MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;" }, [
        MugenUI.selectIcon(MugenIcons.calendar, selBulan),
        MugenUI.selectIcon(MugenIcons.calendar, selTahun),
        ...(selBarber ? [MugenUI.selectIcon(MugenIcons.karyawan, selBarber)] : []),
      ]);
      return { row, selBulan, selTahun, selBarber };
    }

    async function renderBody() {
      body.innerHTML = "";
      if (tabsCtl.active === "Transaksi") await renderTransaksi();
      else if (tabsCtl.active === "Bulanan") await renderBulanan();
      else await renderPengeluaran();
    }

    async function renderTransaksi() {
      const { row, selBulan, selTahun, selBarber } = filterBar({ ambilDaftarDari: (hasil) => hasil.karyawanAll, labelSemua: "Semua Karyawan" });

      // Periode tanggal TAMBAHAN khusus untuk cetak PDF (filter Bulan+Tahun
      // di atas untuk tampilan layar TIDAK berubah) -- kalau diisi,
      // menggantikan Bulan+Tahun sebagai periode PDF supaya bisa cetak
      // rentang custom (mis. per 2 minggu), default kosong (pakai Bulan+
      // Tahun seperti biasa).
      const inputDariTanggal = MugenUI.el("input", { type: "date" });
      const inputSampaiTanggal = MugenUI.el("input", { type: "date" });
      // Jenis Laporan (Perbaikan Alur Cetak PDF): "Rekap Detail" = format
      // lama (satu baris per transaksi/hari, TIDAK berubah), "Rekap
      // Periode (Ringkasan)" = BARU, satu baris per karyawan untuk seluruh
      // periode -- lihat laporan_pdf.buat_pdf_rekap_transaksi_ringkasan().
      const selJenisLaporan = MugenUI.el("select", {}, [
        MugenUI.el("option", { value: "detail" }, "Rekap Detail"),
        MugenUI.el("option", { value: "ringkasan" }, "Rekap Periode (Ringkasan)"),
      ]);
      const pdfRow = MugenUI.el("div", { class: "row", style: "flex:none;margin-bottom:14px;align-items:center;flex-wrap:wrap;" }, [
        MugenUI.el("span", { class: "subtitle", style: "margin:0;" }, "Periode PDF (opsional):"),
        inputDariTanggal, inputSampaiTanggal,
        MugenUI.el("span", { class: "subtitle", style: "margin:0;" }, "Jenis Laporan:"),
        MugenUI.selectIcon(MugenIcons.filter, selJenisLaporan),
      ]);

      // Periode efektif yang dipakai NAMA FILE (murni tampilan nama file --
      // parameter yang DIKIRIM ke server tetap lewat qs di bawah, TIDAK
      // berubah): kalau Periode PDF custom diisi, pakai apa adanya; kalau
      // tidak, diturunkan dari Bulan+Tahun yang aktif (tanggal 1 s.d. hari
      // terakhir bulan itu).
      function periodeUntukNamaFile() {
        if (inputDariTanggal.value && inputSampaiTanggal.value) {
          return { mulai: inputDariTanggal.value, selesai: inputSampaiTanggal.value };
        }
        const tahun = Number(selTahun.value), bulan = Number(selBulan.value);
        const hariTerakhir = new Date(tahun, bulan, 0).getDate();
        const dua = (n) => String(n).padStart(2, "0");
        return {
          mulai: `${tahun}-${dua(bulan)}-01`,
          selesai: `${tahun}-${dua(bulan)}-${dua(hariTerakhir)}`,
        };
      }

      function namaFilePdf() {
        const jenisLabel = selJenisLaporan.value === "ringkasan" ? "Rekap Periode" : "Rekap Harian";
        const karyawan = selBarber && selBarber.value
          ? (karyawanAll.find((k) => String(k.id) === selBarber.value) || {}).nama || "Karyawan"
          : "Semua Karyawan";
        const { mulai, selesai } = periodeUntukNamaFile();
        const tanggalLabel = mulai === selesai
          ? MugenUI.namaTanggalIndo(mulai)
          : `${MugenUI.namaTanggalIndo(mulai)} - ${MugenUI.namaTanggalIndo(selesai)}`;
        return MugenUI.namaFileAman(`${jenisLabel} ${karyawan} ${tanggalLabel}.pdf`);
      }

      pdfRow.appendChild(tombolCetakPdf(() => {
        const qs = new URLSearchParams();
        if (inputDariTanggal.value && inputSampaiTanggal.value) {
          qs.set("tanggal_mulai", inputDariTanggal.value);
          qs.set("tanggal_selesai", inputSampaiTanggal.value);
        } else {
          qs.set("tahun", selTahun.value);
          qs.set("bulan", selBulan.value);
        }
        if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
        qs.set("jenis", selJenisLaporan.value);
        return {
          generate: () => MugenApi.fetchBlob(`/api/rekap/transaksi/pdf?${qs}`),
          filename: namaFilePdf(),
        };
      }));

      const tableWrap = MugenUI.el("div");
      body.appendChild(row);
      body.appendChild(pdfRow);
      body.appendChild(tableWrap);
      // FITUR "+ Tambah Transaksi" (PERMINTAAN Owner) -- izin SAMA PERSIS
      // tombol Koreksi (bolehKoreksiTransaksi, "izin_input_data_kelola"),
      // supaya Owner bisa kasih izin ini ke Kasir juga lewat Pengaturan
      // Izin tanpa perlu izin baru. Bentuknya link teks polos (gaya "Lupa
      // Kata Sandi?" di Login, TANPA simbol "+") -- BUKAN tombol penuh,
      // supaya tidak terlalu menonjol dibanding tombol-tombol utama
      // (Cetak PDF, dll) di atasnya. Elemennya dibuat SEKALI di sini
      // (bukan di renderDenganData() yang bisa dipanggil berkali-kali
      // tiap ganti filter/halaman, supaya listener klik tidak terpasang
      // dobel) -- lihat renderDenganData() di bawah untuk tempat node ini
      // SEBENARNYA dipasang (sejajar baris pagination "‹ 1 ... 20 21 ›",
      // PERMINTAAN Owner, bukan di bawah sendiri terpisah).
      let linkTambah = null;
      if (bolehKoreksiTransaksi) {
        linkTambah = MugenUI.el("button", { type: "button", class: "text-link-aksi" }, "Tambah Transaksi");
        linkTambah.addEventListener("click", () => bukaModalTambah({
          karyawanPromise,
          // PERMINTAAN Owner: tabel yang SEDANG terbuka ini ikut diperbarui
          // diam-diam (gantiBarisTransaksi() + render ULANG dari cache,
          // TANPA fetch/skeleton) -- fallback ke load() biasa kalau baris
          // hasilnya tidak cocok filter Bulan/Tahun/Barber yang sedang
          // aktif (mis. ditambahkan untuk bulan lain).
          onSelesai: (barisRekap) => {
            const dataBaru = barisRekap && gantiBarisTransaksi(barisRekap);
            if (dataBaru) renderDenganData(dataBaru);
            else load();
          },
        }));
      }

      function renderDenganData(data) {
        tableWrap.innerHTML = "";
        if (data.__offline) tableWrap.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        const rows = Array.isArray(data) ? data : [];
          // Ket.: baris "libur" MURNI tetap badge pil (persis seperti
          // sebelumnya, tidak berubah). Jenis lain (catatan Input Data,
          // Reimburse/Kasbon/Gaji Non-Barber) bisa berisi lebih dari satu
          // informasi sekaligus (dipisah "; ") -- ditampilkan satu baris per
          // informasi (MugenUI.keteranganCell()), bukan digabung jadi satu
          // baris. Dipakai KEDUA susunan kolom (Owner/Admin & Barber) di
          // bawah, jadi diekstrak supaya tidak dobel.
          const kolomKet = {
            key: "keterangan", label: "Ket.", format: (v, r) => {
              if (!v) return "-";
              if (r.tipe === "libur") {
                // PERMINTAAN OWNER: "Libur ⚠️" (diambil dari kuota Cuti/Izin
                // karena kuota Libur bulanan habis) / "Libur 🔴" (kuota
                // Libur DAN Izin/Cuti gabungan sama-sama habis) -- lihat
                // kuota_libur_db.py::tandai_rekap_transaksi_kuota().
                const title = v.includes("⚠️")
                  ? "Libur ini diambil dari kuota Cuti/Izin karena kuota Libur bulanan sudah habis -- BUKAN pengajuan Cuti/Izin asli dari barber."
                  : v.includes("🔴")
                    ? "Kuota Libur DAN kuota gabungan Izin/Cuti bulan ini sama-sama sudah habis."
                    : null;
                return MugenUI.el("span", { class: "badge badge-libur", ...(title ? { title } : {}) }, v);
              }
              return MugenUI.keteranganCell(v);
            },
          };
          // REVISI Rekap Transaksi (KHUSUS Barber, lihat !isAdmin di bawah):
          // susunan kolom Owner/Admin (isAdmin true, termasuk Staff)
          // DIBIARKAN PERSIS seperti sebelumnya, TIDAK disentuh sama sekali
          // -- permintaan eksplisit supaya perbaikan ini hanya berlaku untuk
          // akun ber-role Barber, bukan Tenant (Owner/Admin).
          const kolomAdmin = [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_barber", label: "Nama" },
            { key: "daftar_service", label: "Service", format: MugenUI.serviceCell },
            { key: "jumlah_service", label: "Jml Service" },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiahAtauStrip },
            { key: "pendapatan", label: "Pendapatan", format: MugenUI.formatRupiah },
            kolomKet,
          ];
          // Susunan BARU khusus Barber (BUG FIX): (1) kolom Komisi yang
          // sebelumnya tidak ada sama sekali (field "komisi" sudah dikirim
          // backend, lihat database.py::get_rekap_transaksi_list(), tinggal
          // ditampilkan); (2) Reimburse/Kasbon Dibayar jadi kolom sendiri
          // (sebelumnya nilainya "tersembunyi" di dalam Pendapatan tanpa
          // label jelas) -- "-" untuk baris yang bukan tipe itu; (3)
          // Pendapatan sekarang benar-benar TOTAL baris itu (Komisi + Uang
          // Harian + Tips untuk baris transaksi -- SEBELUMNYA Uang Harian
          // tidak ikut dihitung; baris Reimburse/Kasbon/Libur nilainya apa
          // adanya dari backend, sudah benar sejak awal, tidak perlu
          // dihitung ulang di sini).
          const kolomBarber = [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "nama_barber", label: "Nama" },
            { key: "daftar_service", label: "Service", format: MugenUI.serviceCell },
            { key: "jumlah_service", label: "Jml Service" },
            { key: "komisi", label: "Komisi", format: (v, r) => r.tipe === "transaksi" ? MugenUI.formatRupiah(v || 0) : "-" },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiahAtauStrip },
            { key: "pendapatan", label: "Reimburse", format: (v, r) => r.tipe === "reimburse" ? MugenUI.formatRupiah(v) : "-" },
            { key: "pendapatan", label: "Kasbon Dibayar", format: (v, r) => r.tipe === "kasbon" ? MugenUI.formatRupiah(-v) : "-" },
            {
              key: "pendapatan", label: "Pendapatan", format: (v, r) => MugenUI.formatRupiah(
                r.tipe === "transaksi" ? (r.komisi || 0) + (r.uang_harian || 0) + (r.tips || 0) : v
              ),
            },
            kolomKet,
          ];
          // Kolom Hapus -- Owner selalu lihat semua, Staff dicek per
          // jenis baris lewat bolehHapusTransaksi/bolehHapusReimburse/
          // bolehBatalKasbon/bolehHapusNonBarber (lihat deklarasinya di
          // atas). Lima jenis baris punya aksi berbeda: "transaksi"
          // (hapus transaksi asli), "reimburse" (hapus klaim yang sudah
          // disetujui, dengan peringatan lebih kuat karena ini uang yang
          // sudah cair), "kasbon" (batalkan SATU pembayaran manual saja
          // -- pembayaran hasil potong otomatis Slip Gaji, sumber=
          // "potong_gaji", sengaja TIDAK bisa dihapus dari sini supaya
          // tidak bentrok dengan status Slip Gaji terkait, harus lewat
          // pembatalan status Slip Gaji itu sendiri), "non_barber"
          // (hapus entri Gaji Non-Barber, Input Data Non-Barber),
          // "libur" (hapus Keterangan Libur -- REVISI: sebelumnya
          // SELALU dash karena baris ini tidak punya "id" sama sekali,
          // dicek TERPISAH dari baris lain SEBELUM gerbang `r.id == null`
          // di bawah supaya tidak ikut ke-skip; dihapus lewat kombinasi
          // barber_id+tanggal, bukan id, lihat tombolAksi()/DELETE
          // /api/input-data/libur).
          const kolomAksi = bolehLihatKolomAksi ? [{
                key: "aksi", label: "Aksi", format: (_, r) => {
                  if (r.tipe === "libur") {
                    if (!bolehHapusTransaksi) return "-";
                    // PERMINTAAN OWNER: baris "Libur ⚠️" (lihat kolomKet di
                    // atas) tidak punya apa pun di absensi_libur untuk
                    // dihapus (tersimpan di izin_cuti) -- tombol Hapus
                    // Keterangan Libur di sini TIDAK berlaku untuk baris ini.
                    if (r.dari_kuota_cuti_izin) return "-";
                    return tombolAksi({
                      label: "🗑 Hapus", title: "Hapus Keterangan Libur",
                      confirmTitle: "Hapus Keterangan Libur",
                      confirmMessage: [
                        `Apakah Anda yakin ingin menghapus keterangan libur ${r.nama_barber} pada ${MugenUI.formatTanggal(r.tanggal)}?`,
                        "Barber ini akan dianggap masuk kerja seperti biasa pada tanggal tersebut setelah dihapus.",
                      ],
                      hapusUrl: "/api/input-data/libur",
                      hapusBody: { barber_id: r.barber_id, tanggal: r.tanggal },
                      pesanSukses: "Keterangan libur berhasil dihapus.",
                    });
                  }
                  if (r.id == null) return "-";
                  if (r.tipe === "transaksi") {
                    // PENGHAPUSAN Input Data Barber: tombol "✏ Koreksi" HANYA
                    // untuk baris yang TIDAK dikelola jalur lain -- baris
                    // sumber="pos"/"manual_customer" dibangun ULANG otomatis
                    // oleh jalur masing-masing (reset_hari_pos()/
                    // _sinkronkan_transaksi_hari()/_rebuild_transaksi_
                    // booking_barber_hari()) begitu ada perubahan di sana,
                    // mengedit baris gabungannya langsung di sini berisiko
                    // tertimpa/hilang pada sinkronisasi berikutnya -- koreksi
                    // yang benar untuk baris itu lewat Point of Sale/Manual
                    // Customer/Booking sendiri. Baris lama (sumber kosong) &
                    // hasil WA Bot (sumber="wa_bot") TETAP boleh dikoreksi di
                    // sini, sama seperti sebelumnya.
                    const SUMBER_TERKELOLA_OTOMATIS = ["pos", "manual_customer", "booking"];
                    const bolehKoreksi = bolehKoreksiTransaksi && !SUMBER_TERKELOLA_OTOMATIS.includes(r.sumber);
                    if (!bolehHapusTransaksi && !bolehKoreksi) return "-";
                    const wrap = bolehHapusTransaksi
                      ? tombolAksi({
                          label: "🗑 Hapus", title: "Hapus Transaksi",
                          confirmTitle: "Hapus Transaksi",
                          confirmMessage: [
                            "Apakah Anda yakin ingin menghapus transaksi ini?",
                            "Data yang dihapus tidak dapat dikembalikan.",
                          ],
                          hapusUrl: `/api/input-data/transaksi/${r.id}`,
                          pesanSukses: "Transaksi berhasil dihapus.",
                        })
                      : MugenUI.el("div", { class: "actions-cell" });
                    if (bolehKoreksi) {
                      const btnKoreksi = MugenUI.el("button", { type: "button", title: "Koreksi Transaksi" }, "✏ Koreksi");
                      btnKoreksi.addEventListener("click", () => bukaModalKoreksi(r.id, {
                        karyawanPromise,
                        onSelesai: () => load(),
                      }));
                      wrap.insertBefore(btnKoreksi, wrap.firstChild);
                    }
                    return wrap;
                  }
                  if (r.tipe === "reimburse") {
                    if (!bolehHapusReimburse) return "-";
                    return tombolAksi({
                      label: "🗑 Hapus", title: "Hapus Klaim Reimburse",
                      confirmTitle: "Hapus Klaim Reimburse",
                      confirmMessage: [
                        "Apakah Anda yakin ingin menghapus klaim reimburse yang sudah disetujui ini?",
                        "Klaim ini sudah cair/tercatat sebagai pendapatan -- menghapusnya akan mengurangi Total Pendapatan pada rekap ini.",
                        "Data yang dihapus tidak dapat dikembalikan.",
                      ],
                      hapusUrl: `/api/reimburse/${r.id}/rekap`,
                      pesanSukses: "Klaim reimburse berhasil dihapus.",
                    });
                  }
                  if (r.tipe === "kasbon") {
                    if (r.sumber !== "manual") return "-"; // potong_gaji: lewat Slip Gaji
                    if (!bolehBatalKasbon) return "-";
                    return tombolAksi({
                      label: "↩ Batalkan", title: "Batalkan Pembayaran Kasbon",
                      confirmTitle: "Batalkan Pembayaran Kasbon",
                      confirmMessage: [
                        "Apakah Anda yakin ingin membatalkan pembayaran kasbon ini?",
                        "Sisa kasbon karyawan ini akan dikembalikan sejumlah pembayaran yang dibatalkan.",
                        "Data yang dihapus tidak dapat dikembalikan.",
                      ],
                      hapusUrl: `/api/kasbon/pembayaran/${r.id}`,
                      pesanSukses: "Pembayaran kasbon berhasil dibatalkan.",
                    });
                  }
                  if (r.tipe === "non_barber") {
                    if (!bolehHapusNonBarber) return "-";
                    return tombolAksi({
                      label: "🗑 Hapus", title: "Hapus Data Gaji Non-Barber",
                      confirmTitle: "Hapus Data Gaji Non-Barber",
                      confirmMessage: [
                        "Apakah Anda yakin ingin menghapus data gaji ini?",
                        "Data yang dihapus tidak dapat dikembalikan.",
                      ],
                      hapusUrl: `/api/data-non-barber/${r.id}`,
                      pesanSukses: "Data gaji Non-Barber berhasil dihapus.",
                    });
                  }
                  return "-";
                },
          }] : [];
          const columns = [...(isAdmin ? kolomAdmin : kolomBarber), ...kolomAksi];

          if (!isAdmin) {
            tableWrap.appendChild(MugenUI.buildTable(columns, rows));
            return;
          }

          // PERMINTAAN Owner (referensi gambar "Daftar Transaksi"): tampilan
          // LAYAR Rekap Transaksi (KHUSUS Owner/Admin -- Barber di atas TETAP
          // tabel polos seperti sebelumnya, tidak berubah) sekarang dikelompokkan
          // PER TANGGAL -- satu "slide" cuma baris-baris SATU tanggal, navigasi
          // pindah ke tanggal lain. Dropdown Bulan/Tahun/Karyawan, Periode PDF,
          // Jenis Laporan TETAP persis seperti sebelumnya (TIDAK diubah) --
          // cuma cara tabelnya ditampilkan di layar yang berubah. Tanggal
          // tanpa data sama sekali otomatis tidak pernah jadi slide (backend
          // hanya mengirim baris yang benar-benar ada, bukan representasi
          // 1-31 hari kalender).
          const baganTanggal = new Map();
          for (const r of rows) {
            if (!baganTanggal.has(r.tanggal)) baganTanggal.set(r.tanggal, []);
            baganTanggal.get(r.tanggal).push(r);
          }
          // Backend mengirim baris terurut TERBARU dulu (ORDER BY tanggal
          // DESC) -- dibalik di sini supaya Halaman 1 = tanggal PALING LAMA,
          // Halaman terakhir = tanggal PALING BARU (PERMINTAAN Owner: "kalau
          // dimundurin itu tanggal sebelumnya, kalau dimajuin itu tanggal
          // yang terbaru" -- bukan kebalik). Format "YYYY-MM-DD" ASC = urut
          // kronologis yang benar lewat sort string biasa.
          const tanggalUnik = [...baganTanggal.keys()].sort();

          const cardHeader = MugenUI.el("div", { class: "card-header-row" }, [
            MugenUI.el("h2", { style: "margin:0;" }, "Daftar Transaksi"),
            MugenUI.el("span", { class: "badge badge-period" }, `${rows.length} Data`),
          ]);
          const navRow = MugenUI.el("div", { class: "rekap-slide-nav" });
          // PERMINTAAN Owner ("posisi pagination jangan berpindah-pindah
          // naik turun kalau data 4 baris vs 5 baris"): min-height di
          // sini (lihat style.css::.rekap-slide-table) supaya tabel
          // dengan sedikit baris tetap menyisakan ruang kosong di bawahnya
          // -- pagination tetap di posisi yang sama -- baru ikut turun
          // kalau datanya benar-benar lebih banyak dari itu.
          const slideTableBox = MugenUI.el("div", { class: "rekap-slide-table" });
          tableWrap.appendChild(cardHeader);
          tableWrap.appendChild(slideTableBox);
          // PERMINTAAN Owner: pagination di BAWAH tabel, rata kanan (bukan
          // di atas tabel seperti sebelumnya) -- lihat .rekap-slide-nav.
          tableWrap.appendChild(navRow);

          // PERMINTAAN Owner ("default-nya harusnya tampilkan halaman
          // pagination yang TERAKHIR, bukan yang pertama"): tanggalUnik
          // terurut ASC (lama -> baru, lihat komentar di atas).
          //
          // BUGFIX (PERMINTAAN Owner, ditemukan setelah fitur Booking
          // advance ada): "index TERAKHIR" dulu SELALU sama dengan "hari
          // ini" karena transaksi tidak pernah bertanggal MASA DEPAN --
          // sekarang booking yang dibayar hari ini untuk layanan tanggal
          // NANTI bisa membuat baris transaksi bertanggal depan, jadi
          // "terakhir" bisa jadi tanggal depan itu, BUKAN hari ini. Cari
          // dulu index hari ini SECARA EKSPLISIT (WIB) -- kalau hari ini
          // belum punya transaksi sama sekali (wajar, mis. toko belum
          // buka), mundur ke tanggal TERAKHIR SEBELUM hari ini (BUKAN
          // tanggal depan manapun) supaya tidak "melompat" ke booking
          // advance.
          const _hariIni = MugenUI.isoHariIniWib();
          let slideIndex = tanggalUnik.indexOf(_hariIni);
          if (slideIndex === -1) {
            slideIndex = tanggalUnik.length - 1;
            while (slideIndex >= 0 && tanggalUnik[slideIndex] > _hariIni) slideIndex -= 1;
          }
          slideIndex = Math.max(slideIndex, 0);

          // PERMINTAAN Owner ("tombol sebelumnya/berikutnya jadi komponen
          // pagination, ada nomor 1 2 3 4 5 ... sampai nomor terakhir"):
          // daftar nomor halaman yang ditampilkan -- selalu halaman
          // pertama+terakhir, halaman aktif +/-1 tetangganya, sisanya
          // dipadatkan jadi "..." kalau jumlah tanggal terlalu banyak
          // (pola pagination standar, bukan menampilkan SEMUA nomor kalau
          // tanggalnya puluhan dalam satu bulan).
          function _daftarHalamanPaginasi(aktif, total) {
            const AMBANG = 7; // total tanggal <= ini -> tampilkan semua, tanpa "..."
            if (total <= AMBANG) return Array.from({ length: total }, (_, i) => i);
            // BUGFIX (PERMINTAAN Owner "selalu tampilkan 5 angka"): jendela
            // SEBELUMNYA (kiri/kanan di-clamp independen ke [1, total-2])
            // menciut jadi cuma 2-3 angka begitu halaman aktif dekat ujung
            // (mis. halaman 1 atau 2) karena satu sisi mentok tanpa
            // menggeser sisi lain untuk menutupinya. UKURAN_JENDELA (3
            // nomor tengah) sekarang digeser utuh saat mentok, supaya
            // total nomor yang tampil (1 awal + 3 tengah + 1 akhir) SELALU
            // 5, di posisi mana pun.
            const UKURAN_JENDELA = 3;
            let kiri = aktif - 1;
            let kanan = aktif + 1;
            if (kiri < 1) { kiri = 1; kanan = kiri + UKURAN_JENDELA - 1; }
            if (kanan > total - 2) { kanan = total - 2; kiri = kanan - UKURAN_JENDELA + 1; }
            kiri = Math.max(kiri, 1);
            kanan = Math.min(kanan, total - 2);
            const hasil = [0];
            if (kiri > 1) hasil.push("...");
            for (let i = kiri; i <= kanan; i++) hasil.push(i);
            if (kanan < total - 2) hasil.push("...");
            hasil.push(total - 1);
            return hasil;
          }

          function renderSlide() {
            navRow.innerHTML = "";
            slideTableBox.innerHTML = "";

            if (tanggalUnik.length === 0) {
              slideTableBox.appendChild(MugenUI.buildTable(columns, []));
              if (linkTambah) navRow.appendChild(linkTambah);
              return;
            }

            const totalHalaman = tanggalUnik.length;
            const tanggalAktif = tanggalUnik[slideIndex];

            const labelBox = MugenUI.el("div", { class: "rekap-slide-label" }, [
              MugenUI.el("strong", {}, MugenUI.namaTanggalIndo(tanggalAktif)),
              MugenUI.el("span", {}, `Tanggal ${slideIndex + 1} dari ${totalHalaman}`),
            ]);

            const pager = MugenUI.el("div", { class: "rekap-pagination" });

            const btnSebelumnya = MugenUI.el("button", { type: "button", class: "rekap-page-arrow", "aria-label": "Tanggal sebelumnya" }, "‹");
            btnSebelumnya.disabled = slideIndex <= 0;
            btnSebelumnya.addEventListener("click", () => { slideIndex -= 1; renderSlide(); });
            pager.appendChild(btnSebelumnya);

            for (const p of _daftarHalamanPaginasi(slideIndex, totalHalaman)) {
              if (p === "...") {
                pager.appendChild(MugenUI.el("span", { class: "rekap-page-ellipsis" }, "…"));
                continue;
              }
              const btnNomor = MugenUI.el("button", {
                type: "button",
                class: "rekap-page-num" + (p === slideIndex ? " active" : ""),
                "aria-label": `Tanggal ${MugenUI.namaTanggalIndo(tanggalUnik[p])}`,
                ...(p === slideIndex ? { "aria-current": "page" } : {}),
              }, String(p + 1));
              btnNomor.addEventListener("click", () => { slideIndex = p; renderSlide(); });
              pager.appendChild(btnNomor);
            }

            const btnBerikutnya = MugenUI.el("button", { type: "button", class: "rekap-page-arrow", "aria-label": "Tanggal berikutnya" }, "›");
            btnBerikutnya.disabled = slideIndex >= totalHalaman - 1;
            btnBerikutnya.addEventListener("click", () => { slideIndex += 1; renderSlide(); });
            pager.appendChild(btnBerikutnya);

            navRow.appendChild(labelBox);
            // PERMINTAAN Owner ("tombol Tambah Transaksi harusnya sejajar
            // dengan pagination, bukan di bawah sendiri"): dibungkus SATU
            // div bersama pager supaya keduanya SELALU berada di baris
            // yang sama (satu flex item dari sudut pandang navRow, jadi
            // tidak ikut membungkus terpisah walau labelBox di atas
            // ikut turun baris di layar sempit).
            const barisBawah = MugenUI.el("div", { class: "rekap-slide-nav-bawah" });
            if (linkTambah) barisBawah.appendChild(linkTambah);
            barisBawah.appendChild(pager);
            navRow.appendChild(barisBawah);

            slideTableBox.appendChild(MugenUI.buildTable(columns, baganTanggal.get(tanggalAktif)));
          }
          renderSlide();
      }

      async function load(opts = {}) {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
        const url = `/api/rekap/transaksi?${qs}`;

        // PERMINTAAN OWNER: pola SAMA seperti Dashboard (lihat
        // dashboard_owner.js) -- begitu tab Transaksi dibuka lagi (pindah
        // menu lalu balik) TANPA ada simpan/edit/hapus apa pun sejak
        // terakhir kali tab INI berhasil dimuat, DAN filter (url) yang
        // aktif sama persis, tampilkan ulang hasil fetch terakhir PERSIS
        // seperti itu -- instan, tanpa skeleton/fetch sama sekali. Hanya
        // dicek untuk pemuatan AWAL (opts.bisaDariCache, dipanggil SEKALI
        // di akhir renderTransaksi() di bawah) -- ganti filter manual oleh
        // user (event listener di bawah, TANPA opts) SELALU fetch ulang.
        //
        // BUGFIX "Rekap masih loading walau ada suntik diam-diam dari POS/
        // Booking/Tambah Transaksi" (PERMINTAAN Owner): flag ini SENGAJA
        // "rekap_transaksi" -- TERPISAH dari "rekap" yang dipakai tab
        // Bulanan/Pengeluaran di bawah. api.js menandai KEDUA flag ini
        // kotor untuk SETIAP mutasi di seluruh aplikasi (default aman,
        // tidak berubah) -- TAPI suntikBarisTransaksi()/gantiBarisTransaksi()
        // di atas membersihkan HANYA "rekap_transaksi" setelah berhasil
        // menyuntik satu baris, supaya tab INI tidak ikut fetch ulang
        // (sebelumnya: suntik berhasil mengubah cache, tapi flag "rekap"
        // bersama Bulanan/Pengeluaran tetap kotor dari mutasi POS itu
        // sendiri, jadi tab ini tetap fetch ulang + skeleton walau
        // datanya sudah akurat). Bulanan/Pengeluaran TIDAK disentuh --
        // keduanya memang belum punya suntik, tetap fetch ulang seperti
        // biasa (benar, karena totalnya memang perlu dihitung ulang server).
        if (opts.bisaDariCache && !MugenState.halamanPerluRefresh("rekap_transaksi")) {
          const cached = _ambilDariCache("transaksi", MugenState.getUser().id, url);
          if (cached) {
            renderDenganData(cached);
            return;
          }
        }

        // REVISI UI/UX Premium: skeleton (bentuk tabel) menggantikan teks "Memuat..."
        tableWrap.innerHTML = "";
        tableWrap.appendChild(MugenUI.skeleton("table", { cols: isAdmin ? 9 : 11, rows: 4 }));
        try {
          const data = await MugenApi.get(url, { useCache: true });
          if (!data.__offline) {
            // Cache offline (data.__offline) SENGAJA tidak disimpan ke sini --
            // bukan representasi data yang sebenarnya berhasil dimuat barusan.
            _simpanKeCache("transaksi", MugenState.getUser().id, url, data);
            MugenState.tandaiHalamanBersih("rekap_transaksi");
          }
          renderDenganData(data);
        } catch (e) {
          tableWrap.innerHTML = "";
          tableWrap.appendChild(MugenUI.errorState(e.message));
        }
      }
      // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
      // -- skeleton di dalam tableWrap sendiri (di atas) sudah jadi feedback yang cukup.
      selBulan.addEventListener("change", () => load());
      selTahun.addEventListener("change", () => load());
      if (selBarber) selBarber.addEventListener("change", () => load());
      load({ bisaDariCache: true });
    }

    async function renderBulanan() {
      const { row, selBulan, selTahun, selBarber } = filterBar();
      row.appendChild(tombolCetakPdf(() => {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
        const barberNama = selBarber && selBarber.value
          ? (barbersOnly.find((b) => String(b.id) === selBarber.value) || {}).nama || "Barber"
          : "Semua Barber";
        return {
          generate: () => MugenApi.fetchBlob(`/api/rekap/bulanan/pdf?${qs}`),
          filename: MugenUI.namaFileAman(`Rekap Bulanan ${barberNama} ${MugenUI.namaBulan(Number(selBulan.value))} ${selTahun.value}.pdf`),
        };
      }));
      const tableWrap = MugenUI.el("div");
      body.appendChild(row);
      body.appendChild(tableWrap);

      function renderDenganData(data) {
        tableWrap.innerHTML = "";
        if (data.__offline) tableWrap.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        const rows = Array.isArray(data) ? data : [];
        tableWrap.appendChild(MugenUI.buildTable(
          [
            { key: "nama_barber", label: "Barber" },
            { key: "jumlah_service", label: "Jml Service" },
            { key: "total_komisi", label: "Komisi", format: MugenUI.formatRupiah },
            { key: "tips", label: "Tips", format: MugenUI.formatRupiahAtauStrip },
            { key: "uang_harian", label: "Uang Harian", format: MugenUI.formatRupiah },
            // PERMINTAAN OWNER: stabilo merah kalau bulan ini ADA tanggal
            // yang Kuota Libur DAN kuota Izin&Cuti-nya sama-sama sudah
            // habis -- lihat routers/rekap.py (field `kuota_habis`).
            { key: "hari_libur", label: "Hari Libur", format: (v, row) => row.kuota_habis
              ? MugenUI.el("span", { class: "badge badge-danger",
                  title: "Kuota Libur & Izin/Cuti bulan ini sudah habis" }, String(v ?? "-"))
              : String(v ?? "-") },
            { key: "target_tercapai", label: "Target Bonus", format: (v) => v ? "Tercapai" : "Belum" },
            { key: "bonus_customer", label: "Bonus Cust.", format: MugenUI.formatRupiah },
            { key: "reimburse", label: "Reimburse", format: MugenUI.formatRupiah },
            { key: "kasbon_dibayar", label: "Kasbon Dibayar", format: MugenUI.formatRupiah },
            { key: "total_pendapatan", label: "Total", format: MugenUI.formatRupiah },
          ],
          rows,
        ));
      }

      async function load(opts = {}) {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        if (selBarber && selBarber.value) qs.set("barber_id", selBarber.value);
        const url = `/api/rekap/bulanan?${qs}`;

        // PERMINTAAN OWNER: lihat catatan panjang di load() renderTransaksi()
        // di atas -- pola SAMA PERSIS, cuma key cache beda ("bulanan").
        if (opts.bisaDariCache && !MugenState.halamanPerluRefresh("rekap")) {
          const cached = _ambilDariCache("bulanan", MugenState.getUser().id, url);
          if (cached) {
            renderDenganData(cached);
            return;
          }
        }

        // REVISI UI/UX Premium: skeleton (bentuk tabel) menggantikan teks "Memuat..."
        tableWrap.innerHTML = "";
        tableWrap.appendChild(MugenUI.skeleton("table", { cols: 11, rows: 4 }));
        try {
          const data = await MugenApi.get(url, { useCache: true });
          if (!data.__offline) {
            _simpanKeCache("bulanan", MugenState.getUser().id, url, data);
            MugenState.tandaiHalamanBersih("rekap");
          }
          renderDenganData(data);
        } catch (e) {
          tableWrap.innerHTML = "";
          tableWrap.appendChild(MugenUI.errorState(e.message));
        }
      }
      // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
      // -- skeleton di dalam tableWrap sendiri (di atas) sudah jadi feedback yang cukup.
      selBulan.addEventListener("change", () => load());
      selTahun.addEventListener("change", () => load());
      if (selBarber) selBarber.addEventListener("change", () => load());
      load({ bisaDariCache: true });
    }

    async function renderPengeluaran() {
      const { row, selBulan, selTahun } = filterBar({ withBarber: false });
      row.appendChild(tombolCetakPdf(() => {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        return {
          generate: () => MugenApi.fetchBlob(`/api/rekap/pengeluaran/pdf?${qs}`),
          filename: MugenUI.namaFileAman(`Rekap Pengeluaran ${MugenUI.namaBulan(Number(selBulan.value))} ${selTahun.value}.pdf`),
        };
      }));
      const totalBox = MugenUI.el("div", { class: "card" });
      const tableWrap = MugenUI.el("div");
      body.appendChild(row);
      body.appendChild(totalBox);
      body.appendChild(tableWrap);

      function renderDenganData(data) {
        tableWrap.innerHTML = "";
        totalBox.innerHTML = "";
        if (data.__offline) tableWrap.appendChild(MugenUI.offlineBanner(data.__cachedAt));
        totalBox.appendChild(MugenUI.el("h2", {}, "Total Pengeluaran Bulan Ini"));
        totalBox.appendChild(MugenUI.el("div", { class: "big-number" }, MugenUI.formatRupiah(data.total)));
        tableWrap.appendChild(MugenUI.buildTable(
          [
            { key: "tanggal", label: "Tanggal", format: MugenUI.formatTanggal },
            { key: "kategori", label: "Kategori", format: (v) => v || "-" },
            { key: "keterangan", label: "Keterangan" },
            { key: "nama_barber", label: "Barber", format: (v) => v || "-" },
            { key: "jumlah", label: "Jumlah", format: MugenUI.formatRupiah },
          ],
          data.daftar,
        ));
      }

      async function load(opts = {}) {
        const qs = new URLSearchParams({ tahun: selTahun.value, bulan: selBulan.value });
        const url = `/api/rekap/pengeluaran?${qs}`;

        // PERMINTAAN OWNER: lihat catatan panjang di load() renderTransaksi()
        // di atas -- pola SAMA PERSIS, cuma key cache beda ("pengeluaran").
        if (opts.bisaDariCache && !MugenState.halamanPerluRefresh("rekap")) {
          const cached = _ambilDariCache("pengeluaran", MugenState.getUser().id, url);
          if (cached) {
            renderDenganData(cached);
            return;
          }
        }

        // REVISI UI/UX Premium: skeleton (bentuk tabel) menggantikan teks "Memuat..."
        tableWrap.innerHTML = "";
        tableWrap.appendChild(MugenUI.skeleton("table", { cols: 5, rows: 4 }));
        try {
          const data = await MugenApi.get(url, { useCache: true });
          if (!data.__offline) {
            _simpanKeCache("pengeluaran", MugenState.getUser().id, url, data);
            MugenState.tandaiHalamanBersih("rekap");
          }
          renderDenganData(data);
        } catch (e) {
          tableWrap.innerHTML = "";
          tableWrap.appendChild(MugenUI.errorState(e.message));
        }
      }
      // REVISI UI/UX Premium (Contextual Loading): tanpa overlay layar penuh
      // -- skeleton di dalam tableWrap sendiri (di atas) sudah jadi feedback yang cukup.
      selBulan.addEventListener("change", () => load());
      selTahun.addEventListener("change", () => load());
      load({ bisaDariCache: true });
    }

    renderBody();
  }

  return { render, suntikBarisTransaksi, suntikBarisPengeluaran, hapusBarisPengeluaran };
})();

// PERBAIKAN PERFORMA: modul ini dimuat DINAMIS oleh page_loader.js
// (bukan <script> biasa lagi, lihat index.html/router.js) -- top-level
// "const" TIDAK menempel ke objek window di browser (beda dari "var"),
// jadi page_loader.js TIDAK BISA mendeteksi lewat window.PageRekap begitu saja
// setelah script ini selesai dimuat. Baris di bawah ini SATU-SATUNYA
// perubahan di file ini untuk mendukung lazy-load -- expose eksplisit ke
// window supaya page_loader.js bisa memverifikasi modul benar-benar
// berhasil dimuat sebelum memanggil render()-nya.
window.PageRekap = PageRekap;
