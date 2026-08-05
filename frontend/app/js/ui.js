// ui.js — helper tampilan yang dipakai berulang di banyak halaman, supaya
// setiap halaman tidak menulis ulang logika format angka/tanggal atau
// notifikasi sendiri-sendiri.

const MugenUI = (() => {
  function formatRupiah(angka) {
    const n = Math.round(Number(angka) || 0);
    return "Rp " + n.toLocaleString("id-ID");
  }

  function formatTanggal(iso) {
    if (!iso) return "-";
    const [y, m, d] = iso.split("-");
    return `${d}-${m}-${y}`;
  }

  function namaBulan(bulan) {
    const nama = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
      "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
    return nama[bulan] || bulan;
  }

  // "21 Juli 2026" dari tanggal ISO -- dipakai membuat nama file PDF
  // otomatis (Perbaikan Alur Cetak PDF) supaya formatnya konsisten dengan
  // formatTanggal()/namaBulan() yang sudah ada, bukan angka bulan mentah.
  function namaTanggalIndo(iso) {
    if (!iso) return "-";
    const [y, m, d] = iso.split("-").map(Number);
    return `${d} ${namaBulan(m)} ${y}`;
  }

  // Bersihkan nama file dari karakter yang tidak didukung banyak sistem
  // operasi (Windows paling ketat: \ / : * ? " < > |) -- dipakai nama file
  // PDF yang dibuat otomatis dari filter aktif (Perbaikan Alur Cetak PDF),
  // supaya unduhan tidak pernah gagal gara-gara filter berisi nama
  // karyawan/kategori bebas apa saja.
  function namaFileAman(nama) {
    return String(nama)
      .replace(/[\\/:*?"<>|]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  // BOOKING UI/UX #1: Nomor Transaksi -- [SERVICE_INITIAL][DD][MM][HHMM]
  // [TENANT_INITIAL], SATU-SATUNYA implementasi (dipakai layar Appointment
  // Confirmed di book_public.js DAN menu Booking > List/Calendar di
  // booking.js) supaya keduanya selalu menampilkan angka yang sama persis
  // untuk booking yang sama. Murni tampilan, dihitung dari field yang
  // sudah ada di respons booking (daftar_service/tanggal/jam_mulai) --
  // tidak disimpan di database. Aturan inisial: 1 kata = 1 huruf pertama,
  // 2+ kata = huruf pertama dari 2 kata pertama, abaikan &/-/spasi, huruf
  // kapital -- sama untuk service maupun tenant (tenant SELALU 2 huruf,
  // kata tunggal dipotong 2 huruf pertama, supaya berlaku untuk tenant
  // mana pun, bukan daftar hardcode nama toko).
  function _kataInisial(teks) {
    return String(teks || "").replace(/[&/\-]/g, " ").split(/\s+/).filter(Boolean);
  }
  function inisialService(namaService) {
    const kata = _kataInisial(namaService);
    if (kata.length <= 1) return (kata[0] || "").charAt(0).toUpperCase();
    return kata.slice(0, 2).map((k) => k.charAt(0).toUpperCase()).join("");
  }
  function inisialTenant(namaTenant) {
    const kata = _kataInisial(namaTenant);
    if (kata.length >= 2) return kata.slice(0, 2).map((k) => k.charAt(0).toUpperCase()).join("");
    return (kata[0] || "").slice(0, 2).toUpperCase();
  }
  function buatNomorTransaksi(booking, namaTenant) {
    const daftarService = String(booking.daftar_service || "").split(",")[0].trim();
    const tgl = new Date(booking.tanggal + "T00:00:00");
    const dd = String(tgl.getDate()).padStart(2, "0");
    const mm = String(tgl.getMonth() + 1).padStart(2, "0");
    const [jamStr, menitStr] = String(booking.jam_mulai || "00:00").split(":");
    const hhmm = String(jamStr || "00").padStart(2, "0") + String(menitStr || "00").padStart(2, "0");
    return `${inisialService(daftarService)}${dd}${mm}${hhmm}${inisialTenant(namaTenant)}`;
  }

  // REVISI UI/UX: toast SUKSES/INFO dihilangkan total sesuai instruksi
  // ("Hilangkan seluruh toast/snackbar sukses. Toast hanya muncul jika
  // terjadi error") -- diubah SATU tempat ini (bukan menghapus tiap
  // pemanggilan toast(...,"success") satu-satu di puluhan file) supaya
  // perilakunya konsisten di mana pun toast() dipanggil, dan pemanggilan
  // yang sudah ada tidak perlu diubah/dihapus satu per satu (aman kalau
  // ada yang terlewat). Loading spinner + teks proses (lihat withLoading
  // di bawah) sudah cukup jadi umpan balik sukses -- perubahan langsung
  // terlihat di UI (list ter-refresh, dst) tanpa perlu snackbar tambahan.
  function toast(message, type = "info", { force = false } = {}) {
    // `force` (opsional, default false): SATU-SATUNYA cara melewati aturan
    // "toast sukses/info dihilangkan total" di atas -- dipakai SENGAJA
    // hanya oleh fitur yang secara eksplisit diminta menampilkan notifikasi
    // sukses (mis. Hapus Rekap Transaksi khusus Owner, atau aksi besar
    // seperti pembayaran/booking/export/import/pembuatan tenant/perubahan
    // langganan -- lihat REVISI UI/UX Premium). Pemanggilan toast(...) yang
    // SUDAH ADA di seluruh aplikasi TIDAK mengirim parameter ini, jadi
    // perilakunya 100% tidak berubah.
    if (type !== "error" && !force) return;
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.textContent = message;
    document.body.appendChild(el);
    // REVISI UI/UX Premium: animasi KELUAR sungguhan (sebelumnya .remove()
    // instan) -- .toast-out (style.css) memicu mugen-toast-out, dilepas
    // dari DOM setelah durasinya selesai (var(--dur-fast), lihat CSS).
    setTimeout(() => {
      el.classList.add("toast-out");
      setTimeout(() => el.remove(), 150);
    }, 3500);
  }

  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const child of [].concat(children)) {
      if (child == null) continue;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
  }

  // Kolom "Service" (daftar "Nama xN" dipisah ", ") -- kalau lebih dari
  // satu jenis service, tampilkan tiap jenis di baris/div terpisah (bukan
  // digabung koma dalam satu baris) supaya konsisten dengan tampilan PDF
  // (lihat laporan_pdf.py _sel_service()). Tinggi baris tabel otomatis
  // menyesuaikan sendiri (elemen block <div> normal, TANPA CSS khusus) --
  // TIDAK mengubah data `raw` sama sekali, murni cara menampilkannya.
  // Dipakai di seluruh tampilan Rekap yang punya kolom Service (Rekap
  // Transaksi, Dashboard Barber, dst).
  function serviceCell(raw) {
    if (!raw) return "-";
    const bagian = raw.split(", ").map((b) => b.trim()).filter(Boolean);
    if (bagian.length === 0) return "-";
    const diformat = bagian.map((b) => {
      const idx = b.lastIndexOf(" x");
      return idx > -1 && /^\d+$/.test(b.slice(idx + 2)) ? `${b.slice(0, idx)} ×${b.slice(idx + 2)}` : b;
    });
    if (diformat.length === 1) return diformat[0];
    const wrap = el("div");
    for (const teks of diformat) wrap.appendChild(el("div", {}, teks));
    return wrap;
  }

  // Kolom "Keterangan"/"Ket." (daftar info dipisah "; ", pola yang sama
  // dipakai database.py/reimburse_db.py/kasbon_db.py/data_non_barber_db.py
  // saat membangun field `keterangan`) -- kalau lebih dari satu informasi
  // (Catatan/Kasbon/Reimburse/Libur, dst), tampilkan tiap info di baris/div
  // terpisah (bukan digabung titik-koma dalam satu baris), prinsip sama
  // persis serviceCell() di atas. TIDAK mengubah data `raw` sama sekali,
  // murni cara menampilkannya -- dipakai di seluruh tampilan Rekap yang
  // punya kolom Keterangan (Rekap Transaksi, dst).
  function keteranganCell(raw) {
    if (!raw) return "-";
    const bagian = raw.split("; ").map((b) => b.trim()).filter(Boolean);
    if (bagian.length === 0) return "-";
    if (bagian.length === 1) return bagian[0];
    const wrap = el("div");
    for (const teks of bagian) wrap.appendChild(el("div", {}, teks));
    return wrap;
  }

  // Bangun <table class="data-table"> dari daftar kolom + baris data.
  // columns: [{ key, label, format?: fn }]
  function buildTable(columns, rows, { emptyText = "Belum ada data." } = {}) {
    const wrap = el("div", { class: "table-wrap" });
    const table = el("table", { class: "data-table" });
    const thead = el("thead", {}, el("tr", {}, columns.map((c) => el("th", {}, c.label))));
    const tbody = el("tbody");
    if (!rows || rows.length === 0) {
      tbody.appendChild(el("tr", {}, el("td", { colspan: String(columns.length) }, emptyText)));
    } else {
      for (const row of rows) {
        const tr = el("tr");
        for (const c of columns) {
          const raw = row[c.key];
          const val = c.format ? c.format(raw, row) : (raw ?? "-");
          if (val instanceof Node) tr.appendChild(el("td", {}, val));
          else tr.appendChild(el("td", {}, String(val)));
        }
        tbody.appendChild(tr);
      }
    }
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  // ======================= REVISI UI/UX Premium =======================
  // Fondasi motion terpusat: skeleton loading, refreshInto() (crossfade
  // tanpa "flash" kosong saat rebuild tabel/kartu -- menggantikan pola
  // container.innerHTML="Memuat...";...;container.innerHTML="" yang
  // dipakai puluhan halaman), withButtonLoading() (spinner inline di
  // tombol, TANPA overlay layar penuh -- pengganti withLoading() untuk
  // aksi CRUD/filter harian, lihat catatan withLoading() di bawah), tabs()
  // (SATU implementasi tabs dipakai ulang, menggantikan 3 versi manual di
  // booking.js/rekap.js/pengaturan.js), emptyState()/errorState() (satu
  // pola tampilan, bukan string ad hoc per halaman). ======================

  // Placeholder skeleton sebelum data asli datang -- bentuknya menyerupai
  // data asli (jumlah kolom/baris sama) supaya TIDAK ada layout shift saat
  // ditukar. `kind`: "table" ({cols, rows=4}), "card" ({lines=3}), atau
  // "line" (satu baris teks, opsional {width}).
  function skeleton(kind, opts = {}) {
    if (kind === "table") {
      const { cols = 4, rows = 4 } = opts;
      const wrap = el("div", { class: "table-wrap" });
      const table = el("table", { class: "data-table" });
      const tbody = el("tbody");
      for (let r = 0; r < rows; r++) {
        const tr = el("tr", { class: "skeleton-row" });
        for (let c = 0; c < cols; c++) {
          tr.appendChild(el("td", {}, el("div", { class: "skeleton-block" })));
        }
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      wrap.appendChild(table);
      return wrap;
    }
    if (kind === "card") {
      const { lines = 3 } = opts;
      const card = el("div", { class: "card" });
      for (let i = 0; i < lines; i++) card.appendChild(el("div", { class: "skeleton-card-block" }));
      return card;
    }
    return el("div", { class: "skeleton-line", style: opts.width ? `width:${opts.width};` : "" });
  }

  // Ganti isi `container` dengan hasil `asyncRenderFn()` (harus resolve ke
  // satu Node) lewat crossfade halus, TANPA jeda kosong/"flash" -- dipakai
  // MENGGANTIKAN pola container.innerHTML="Memuat...";...container.innerHTML=""
  // yang sebelumnya tersebar di puluhan halaman (filter berubah, refresh
  // setelah CRUD, dst). Pemuatan PERTAMA kali (container masih kosong)
  // menampilkan skeleton() (kalau `skeleton` diisi) SELAMA menunggu, bukan
  // fade seluruh container yang belum ada isinya. Pemuatan BERIKUTNYA
  // (container sudah ada isi lama) memudarkan isi lama sebentar sebelum
  // ditukar -- fade-out ini berjalan BERSAMAAN dengan fetch data (bukan
  // menunggunya), jadi tidak menambah jeda kalau fetch-nya sendiri sudah
  // lebih lama dari durasi fade.
  async function refreshInto(container, asyncRenderFn, { skeleton: bentukSkeleton } = {}) {
    const sudahAdaIsi = container.children.length > 0;
    if (sudahAdaIsi) {
      container.classList.add("mugen-refresh-fade-out");
    } else if (bentukSkeleton) {
      container.appendChild(skeleton(bentukSkeleton.kind || "table", bentukSkeleton));
    }
    const hasil = await asyncRenderFn();
    container.innerHTML = "";
    container.appendChild(hasil);
    container.classList.remove("mugen-refresh-fade-out");
    container.classList.add("mugen-refresh-fade-in");
    setTimeout(() => container.classList.remove("mugen-refresh-fade-in"), 220);
    return hasil;
  }

  // Bungkus SATU tombol aksi (submit/simpan/hapus/bayar) dengan spinner
  // inline KECIL di dalam tombol itu sendiri -- BUKAN overlay layar penuh
  // (bandingkan withLoading() di bawah, yang SEKARANG khusus proses yang
  // sungguh memblokir SELURUH aplikasi: boot, login, sign out, migrasi/
  // restore/backup besar). Tombol dinonaktifkan selama proses, label asli
  // dikembalikan apa adanya setelah selesai (sukses maupun gagal) --
  // TIDAK ada jeda buatan sama sekali, secepat respons server yang
  // sungguhan (REVISI UI/UX Premium: "Contextual Loading").
  async function withButtonLoading(button, asyncFn) {
    const labelAsli = button.textContent;
    const disabledAsli = button.disabled;
    button.disabled = true;
    button.innerHTML = "";
    button.appendChild(el("span", { class: "btn-inline-spinner" }));
    button.appendChild(document.createTextNode(labelAsli));
    try {
      return await asyncFn();
    } finally {
      button.disabled = disabledAsli;
      button.textContent = labelAsli;
    }
  }

  // Tabs dengan indikator aktif yang bergeser halus -- SATU implementasi
  // dipakai ulang (menggantikan tabBar/renderTabs manual yang sebelumnya
  // diduplikasi di booking.js/rekap.js/pengaturan.js). `items`:
  // [{key, label}]. Caller SENDIRI yang merender body tab lewat
  // `onChange(key)` (isi body tiap tab beda-beda per halaman, tidak bisa
  // digeneralisasi di sini) -- helper ini murni tab bar + indikatornya.
  // Caller WAJIB memanggil `moveIndicator()` lewat requestAnimationFrame
  // SETELAH `bar` di-attach ke DOM (offsetWidth/offsetLeft baru benar
  // setelah elemen benar-benar terpasang).
  function tabs(items, { initial, onChange } = {}) {
    let active = initial || (items[0] && items[0].key);
    const bar = el("div", { class: "mugen-tabs" });
    const indicator = el("div", { class: "mugen-tabs-indicator" });
    const tombol = {};
    for (const item of items) {
      const btn = el("button", { type: "button", class: item.key === active ? "active" : "" }, item.label);
      btn.addEventListener("click", () => setActive(item.key));
      tombol[item.key] = btn;
      bar.appendChild(btn);
    }
    bar.appendChild(indicator);
    function moveIndicator() {
      const btn = tombol[active];
      if (!btn) return;
      indicator.style.width = btn.offsetWidth + "px";
      indicator.style.transform = `translateX(${btn.offsetLeft}px)`;
    }
    function setActive(key) {
      if (key === active || !tombol[key]) return;
      tombol[active].classList.remove("active");
      active = key;
      tombol[active].classList.add("active");
      moveIndicator();
      if (onChange) onChange(active);
    }
    return { bar, setActive, moveIndicator, get active() { return active; } };
  }

  // Satu pola tampilan untuk state kosong/error -- menggantikan string ad
  // hoc ("Belum ada data.", pesan error berbeda-beda) per halaman, supaya
  // SEMUA state kosong/error terlihat & beranimasi sama persis.
  function emptyState(text) {
    return el("div", { class: "mugen-state" }, text);
  }
  function errorState(text) {
    return el("div", { class: "mugen-state mugen-state-error" }, text);
  }

  // Dialog konfirmasi modern (menggantikan confirm() bawaan browser yang
  // tidak bisa diberi styling) -- dipakai fitur yang butuh konfirmasi
  // bertingkat lebih jelas dari sekadar ya/tidak polos, mis. Hapus Rekap
  // Transaksi khusus Owner. `message` boleh string atau array string
  // (tiap elemen jadi satu baris paragraf terpisah). Return Promise<bool>
  // -- true kalau tombol konfirmasi diklik, false kalau Batal/klik di luar
  // kotak/tombol X. Dipanggil dengan `await`, TIDAK memblokir thread
  // seperti confirm() bawaan (async, tidak membekukan tab).
  function confirmModal({ title, message, confirmText = "Ya", cancelText = "Batal", danger = false } = {}) {
    return new Promise((resolve) => {
      const overlay = el("div", { class: "modal-overlay" });
      const box = el("div", { class: "modal-box" });
      if (title) box.appendChild(el("h3", {}, title));
      const baris = Array.isArray(message) ? message : [message];
      for (const teks of baris) box.appendChild(el("p", {}, teks));

      const btnBatal = el("button", { type: "button" }, cancelText);
      const btnKonfirmasi = el("button", { type: "button", class: danger ? "btn-danger" : "btn-primary" }, confirmText);
      box.appendChild(el("div", { class: "modal-actions" }, [btnBatal, btnKonfirmasi]));
      overlay.appendChild(box);
      document.body.appendChild(overlay);

      function tutup(hasil) {
        // REVISI UI/UX Premium: animasi KELUAR sungguhan (sebelumnya
        // .remove() instan) -- .closing (style.css) memicu
        // mugen-overlay-out/mugen-overlay-box-out, var(--dur-fast).
        overlay.classList.add("closing");
        setTimeout(() => { overlay.remove(); resolve(hasil); }, 120);
      }
      btnBatal.addEventListener("click", () => tutup(false));
      btnKonfirmasi.addEventListener("click", () => tutup(true));
      overlay.addEventListener("click", (e) => { if (e.target === overlay) tutup(false); });
    });
  }

  function offlineBanner(cachedAt) {
    const waktu = new Date(cachedAt).toLocaleString("id-ID");
    return el("div", { class: "offline-banner" },
      `Sedang offline — menampilkan data tersimpan terakhir (${waktu}).`);
  }

  // Diagram batang SVG sederhana, dibuat manual TANPA library eksternal --
  // sengaja begitu supaya PWA tetap bisa dipakai offline (kalau pakai
  // library dari CDN, chart akan gagal dimuat begitu tidak ada internet).
  // data: [{ value: number, ...apapun }]. `xLabel(d, i)` -> teks di bawah
  // tiap batang, `yFormat(value)` -> teks di tooltip (hover/tap batang).
  function barChart(data, { xLabel = (d, i) => String(i + 1), yFormat = String } = {}) {
    const svgNS = "http://www.w3.org/2000/svg";
    const barW = 26, gap = 6, height = 190;
    const padding = { top: 10, bottom: 32 };
    const width = Math.max(1, data.length) * (barW + gap) + gap;
    const chartH = height - padding.top - padding.bottom;
    const maxVal = Math.max(1, ...data.map((d) => Number(d.value) || 0));

    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

    if (!data.length) {
      const empty = el("div", { style: "color:var(--text-dim);padding:12px 0;" }, "Belum ada data.");
      return empty;
    }

    data.forEach((d, i) => {
      const nilai = Number(d.value) || 0;
      const barH = Math.max(0, (nilai / maxVal) * chartH);
      const x = gap + i * (barW + gap);
      const y = padding.top + (chartH - barH);

      const rect = document.createElementNS(svgNS, "rect");
      rect.setAttribute("x", String(x));
      rect.setAttribute("y", String(y));
      rect.setAttribute("width", String(barW));
      rect.setAttribute("height", String(barH));
      rect.setAttribute("rx", "3");
      rect.setAttribute("fill", "var(--accent)");
      const title = document.createElementNS(svgNS, "title");
      title.textContent = `${xLabel(d, i)}: ${yFormat(nilai)}`;
      rect.appendChild(title);
      svg.appendChild(rect);

      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", String(x + barW / 2));
      label.setAttribute("y", String(height - padding.bottom + 16));
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", "var(--text-dim)");
      label.textContent = xLabel(d, i);
      svg.appendChild(label);
    });

    return el("div", { style: "overflow-x:auto;" }, svg);
  }

  // Overlay loading global (spinner melingkar di tengah aplikasi). Pakai
  // hitungan referensi (bukan boolean) supaya kalau beberapa withLoading()
  // kebetulan tumpang tindih, overlay-nya baru hilang setelah SEMUANYA
  // selesai -- tidak berkedip hilang di tengah proses yang lain.
  // REVISI: showLoading(message) sekarang menerima teks OPSIONAL (mis.
  // "Sedang keluar dari aplikasi…" untuk Sign Out) -- kalau tidak diisi,
  // perilaku SAMA PERSIS seperti sebelumnya (spinner polos tanpa teks).
  let _loadingCount = 0;
  let _loadingEl = null;
  let _loadingMsgEl = null;

  function showLoading(message) {
    _loadingCount++;
    if (_loadingEl) {
      if (message) _loadingMsgEl.textContent = message;
      return;
    }
    _loadingMsgEl = el("div", { class: "loading-message" }, message || "");
    _loadingEl = el("div", { class: "loading-overlay" }, [el("div", { class: "loading-spinner" }), _loadingMsgEl]);
    document.body.appendChild(_loadingEl);
  }

  function hideLoading() {
    _loadingCount = Math.max(0, _loadingCount - 1);
    if (_loadingCount > 0 || !_loadingEl) return;
    _loadingEl.remove();
    _loadingEl = null;
    _loadingMsgEl = null;
  }

  // Bungkus SATU aksi yang memanggil server (klik tombol submit/simpan/
  // hapus/tambah, atau ganti filter bulan/tahun) supaya menampilkan
  // spinner di tengah aplikasi dengan jeda MINIMAL 1,5 detik -- kalau
  // server-nya kebetulan lebih cepat dari itu, tetap ditahan sampai 1,5
  // detik supaya transisinya terasa "penuh", bukan cuma kedip sekilas.
  // Kalau server lebih lambat dari 1,5 detik, spinner tetap tampil sampai
  // benar-benar selesai (tidak dipotong paksa di 1,5 detik).
  // REVISI: opts opsional -- { message, minMs } -- dipakai Sign Out untuk
  // teks kustom + jeda lebih pendek (800-1200ms, lihat nav.js). Tanpa opts
  // (semua pemanggilan lama), perilaku SAMA PERSIS seperti sebelumnya
  // (tanpa teks, jeda minimal 1500ms).
  async function withLoading(asyncFn, opts) {
    const { message = null, minMs = 1500 } = opts || {};
    showLoading(message);
    try {
      const [hasil] = await Promise.all([
        asyncFn(),
        new Promise((resolve) => setTimeout(resolve, minMs)),
      ]);
      return hasil;
    } finally {
      hideLoading();
    }
  }

  // REVISI UI/UX: switch Dark Mode dipakai di DUA tempat (Setting >
  // Tampilan untuk Owner/Admin, dan di atas tombol Keluar untuk user
  // lain -- lihat nav.js/pengaturan.js), satu builder di sini supaya
  // markup & perilakunya SAMA PERSIS di kedua tempat.
  function themeSwitch() {
    const input = el("input", { type: "checkbox" });
    input.checked = MugenTheme.current() === "gelap";
    const label = el("label", { class: "theme-switch" }, [
      input,
      el("span", { class: "theme-switch-track" }),
      el("span", { class: "theme-switch-thumb" }),
    ]);
    input.addEventListener("change", () => {
      MugenTheme.setTema(input.checked ? "gelap" : "terang");
    });
    return label;
  }

  return {
    formatRupiah, formatTanggal, namaBulan, namaTanggalIndo, namaFileAman, toast, el, buildTable,
    serviceCell, keteranganCell, offlineBanner, barChart, showLoading, hideLoading, withLoading,
    themeSwitch, confirmModal, buatNomorTransaksi,
    skeleton, refreshInto, withButtonLoading, tabs, emptyState, errorState,
  };
})();
