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

  function toast(message, type = "info") {
    const el = document.createElement("div");
    el.className = "toast" + (type !== "info" ? " " + type : "");
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
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
  let _loadingCount = 0;
  let _loadingEl = null;

  function showLoading() {
    _loadingCount++;
    if (_loadingEl) return;
    _loadingEl = el("div", { class: "loading-overlay" }, el("div", { class: "loading-spinner" }));
    document.body.appendChild(_loadingEl);
  }

  function hideLoading() {
    _loadingCount = Math.max(0, _loadingCount - 1);
    if (_loadingCount > 0 || !_loadingEl) return;
    _loadingEl.remove();
    _loadingEl = null;
  }

  // Bungkus SATU aksi yang memanggil server (klik tombol submit/simpan/
  // hapus/tambah, atau ganti filter bulan/tahun) supaya menampilkan
  // spinner di tengah aplikasi dengan jeda MINIMAL 1,5 detik -- kalau
  // server-nya kebetulan lebih cepat dari itu, tetap ditahan sampai 1,5
  // detik supaya transisinya terasa "penuh", bukan cuma kedip sekilas.
  // Kalau server lebih lambat dari 1,5 detik, spinner tetap tampil sampai
  // benar-benar selesai (tidak dipotong paksa di 1,5 detik).
  async function withLoading(asyncFn) {
    showLoading();
    try {
      const [hasil] = await Promise.all([
        asyncFn(),
        new Promise((resolve) => setTimeout(resolve, 1500)),
      ]);
      return hasil;
    } finally {
      hideLoading();
    }
  }

  return {
    formatRupiah, formatTanggal, namaBulan, toast, el, buildTable, offlineBanner, barChart,
    showLoading, hideLoading, withLoading,
  };
})();
