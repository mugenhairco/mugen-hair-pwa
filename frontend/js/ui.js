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

  return { formatRupiah, formatTanggal, namaBulan, toast, el, buildTable, offlineBanner };
})();
