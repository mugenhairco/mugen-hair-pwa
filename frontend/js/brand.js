// brand.js — FONDASI Multi-Tenant Phase 2.2: Tenant Branding & Platform
// Branding (White Label). Satu-satunya tempat yang tahu cara membaca
// branding dari backend (/api/tenant/branding, endpoint publik -- tidak
// perlu login, karena halaman Login pun perlu menampilkannya) dan
// menerapkannya ke: <title>, elemen ".brand-name"/".brand-logo" di halaman
// manapun, favicon (<link rel="icon">/apple-touch-icon), dan warna
// Primary/Secondary (CSS custom properties --accent/--accent-hover/
// --accent-pressed/--accent-secondary di :root, lihat css/style.css --
// SELURUH komponen yang sudah memakai var(--accent) otomatis ikut berubah
// tanpa perlu sentuh CSS lain sama sekali).
//
// FONDASI Multi-Tenant Phase 2.2 (Platform Branding): kalau tenant belum
// dikenali sama sekali (browser baru, tidak ada sesi login, tidak ada
// slug yang diingat, tidak ada subdomain/query) backend mengembalikan
// branding PLATFORM ("Developer", lihat routers/branding.py) -- BUKAN
// tenant pertama yang kebetulan ada di database. DEFAULT di bawah ini
// (dipakai SEBELUM refresh() pertama selesai) sengaja disamakan supaya
// tidak ada "flash" nama tenant sebelum data platform yang benar termuat.
//
// Dipakai localStorage sebagai cache supaya nama/logo langsung tampil tanpa
// "flash ke default" setiap kali halaman dibuka, lalu di-refresh ke data
// terbaru di background. PERFORMA: refresh() (fetch ke server) HANYA
// dipanggil SEKALI per pemuatan aplikasi (app.js, saat DOMContentLoaded)
// dan SEKALI lagi tepat setelah login berhasil (tenant baru saja
// "diketahui" -- lihat login.js) -- navigasi antar halaman SETELAHNYA
// (router.js/nav.js) hanya memanggil applyToDom() dari cache, TIDAK
// pernah request ulang ke server tiap pindah menu.

const MugenBrand = (() => {
  const KEY = "mugen_identitas_cache";
  const DEFAULT = {
    nama_barbershop: "Developer",
    logo_url: null,
    favicon_url: null,
    primary_color: "",
    secondary_color: "",
    is_platform_default: true,
  };

  let current = DEFAULT;
  try {
    const cached = JSON.parse(localStorage.getItem(KEY));
    if (cached) current = cached;
  } catch (e) { /* cache rusak/tidak ada, pakai default */ }

  // REVISI: logo/banner sempat "tidak muncul/rusak" saat aplikasi pertama
  // dibuka -- warm up cache gambar milik browser sedini mungkin (begitu modul
  // ini dimuat, memakai data cache localStorage yang sudah ada) supaya saat
  // <img class="brand-logo"> nanti benar-benar butuh src ini, gambarnya
  // kemungkinan besar sudah ada di cache HTTP browser, bukan baru mulai
  // diunduh dari nol.
  function preload(url) {
    if (!url) return;
    const img = new Image();
    img.src = MUGEN_API_BASE + url;
  }
  preload(current.logo_url);

  function get() {
    return current;
  }

  // FONDASI Multi-Tenant Phase 2.2: favicon mengikuti tenant, fallback ke
  // favicon platform (file statis, sudah dipasang di index.html) kalau
  // tenant belum upload sendiri -- href ASLI (platform) direkam SEKALI di
  // sini saat modul ini pertama dimuat (sebelum override apa pun terjadi)
  // supaya bisa dikembalikan kalau tenant lain (di perangkat/tab yang
  // sama) TIDAK punya favicon custom.
  const FAVICON_LINKS = Array.from(document.querySelectorAll(
    'link[rel="icon"], link[rel="apple-touch-icon"]'
  )).map((el) => ({ el, hrefPlatform: el.getAttribute("href") }));

  function applyFavicon(url) {
    const href = url ? MUGEN_API_BASE + url : null;
    FAVICON_LINKS.forEach(({ el, hrefPlatform }) => {
      // BUGFIX kompatibilitas browser: mengganti `href` atribut yang SAMA
      // tidak selalu memicu browser membaca ulang favicon (banyak browser
      // meng-cache berdasar URL persis) -- me-remove lalu menambahkan
      // ULANG elemen <link> memaksa browser memperlakukannya sebagai
      // favicon BARU, jadi berubah tanpa perlu hard refresh manual.
      const baru = el.cloneNode(true);
      baru.setAttribute("href", href || hrefPlatform);
      el.replaceWith(baru);
      // Perbarui referensi elemen di array supaya panggilan applyFavicon()
      // BERIKUTNYA (mis. ganti tenant lain di tab yang sama) tetap bekerja.
      const idx = FAVICON_LINKS.findIndex((f) => f.el === el);
      if (idx !== -1) FAVICON_LINKS[idx].el = baru;
    });
  }

  // FONDASI Multi-Tenant Phase 2.2: Primary/Secondary Color -- diterapkan
  // sebagai CSS custom property di :root (inline style, prioritas TERTINGGI,
  // menang atas :root maupun :root[data-theme="dark"] di style.css) supaya
  // SATU warna tenant berlaku konsisten di kedua tema Terang/Gelap, sama
  // seperti pola var(--accent) yang sudah dipakai di puluhan tempat (lihat
  // komentar di style.css) -- TIDAK PERNAH menyentuh file CSS itu sendiri.
  function _shade(hex, persenGelap) {
    // Menggelapkan warna heksadesimal `hex` sebesar `persenGelap` (0..1)
    // -- dipakai turunan --accent-hover/--accent-pressed dari Primary
    // Color, konsisten dengan arah token bawaan (hover LEBIH GELAP dari
    // accent dasar, lihat --accent-hover/--accent-pressed di style.css).
    const n = parseInt(hex.slice(1), 16);
    const bagi = (shift) => Math.round(((n >> shift) & 0xff) * (1 - persenGelap));
    return "#" + [16, 8, 0].map((shift) => bagi(shift).toString(16).padStart(2, "0")).join("");
  }

  function applyTheme(primaryColor, secondaryColor) {
    const root = document.documentElement.style;
    if (primaryColor) {
      root.setProperty("--accent", primaryColor);
      root.setProperty("--accent-hover", _shade(primaryColor, 0.15));
      root.setProperty("--accent-pressed", _shade(primaryColor, 0.3));
    } else {
      root.removeProperty("--accent");
      root.removeProperty("--accent-hover");
      root.removeProperty("--accent-pressed");
    }
    if (secondaryColor) {
      root.setProperty("--accent-secondary", secondaryColor);
    } else {
      root.removeProperty("--accent-secondary");
    }
  }

  function applyToDom() {
    document.title = current.nama_barbershop || DEFAULT.nama_barbershop;
    document.querySelectorAll(".brand-name").forEach((el) => {
      el.textContent = current.nama_barbershop || DEFAULT.nama_barbershop;
    });
    document.querySelectorAll(".brand-logo").forEach((el) => {
      if (current.logo_url) {
        // REVISI: sembunyikan dulu elemen sampai gambar TERBUKTI berhasil
        // dimuat (onload), dan tetap sembunyikan (bukan ikon broken-image)
        // kalau ternyata gagal dimuat (onerror) -- sebelumnya display
        // langsung diset "tampil" bersamaan dengan src diisi, jadi kalau
        // gambar gagal/lambat dimuat yang terlihat pengguna adalah ikon
        // gambar rusak, bukan placeholder kosong.
        el.style.display = "none";
        el.onload = () => { el.style.display = ""; };
        el.onerror = () => { el.style.display = "none"; el.removeAttribute("src"); };
        el.src = MUGEN_API_BASE + current.logo_url;
      } else {
        el.onload = null;
        el.onerror = null;
        el.removeAttribute("src");
        el.style.display = "none";
      }
    });
    applyFavicon(current.favicon_url);
    applyTheme(current.primary_color, current.secondary_color);
  }

  async function refresh() {
    try {
      // FONDASI Multi-Tenant Phase 2.2: dua sumber "tenant yang diketahui"
      // untuk TAMPILAN branding SAJA (bukan otorisasi apa pun, endpoint ini
      // publik) -- backend TETAP memprioritaskan tenant sesi login yang
      // valid di atas keduanya (lihat auth.resolve_tenant_untuk_branding()):
      // 1. `?tenant=<slug>` di URL saat ini -- mekanisme tenant discovery
      //    yang SUDAH ADA sejak Phase 1 (dipakai /book dkk), dipakai di sini
      //    supaya link khusus per-toko (mis. dibagikan admin ke staf toko
      //    itu) langsung menampilkan branding tokonya sebelum sempat login.
      // 2. Slug yang "diingat" dari login sebelumnya (state.js, Phase 2.0)
      //    -- fallback kalau URL saat ini TIDAK membawa parameter tenant
      //    sama sekali, supaya pengguna yang belum login di perangkat yang
      //    sudah pernah dipakai tokonya sendiri tidak melihat branding
      //    platform dulu sesaat.
      const slugUrl = new URLSearchParams(location.search).get("tenant");
      const slugDiingat = typeof MugenState !== "undefined" ? MugenState.getTenantSlug() : "";
      const slug = slugUrl || slugDiingat;
      const path = "/api/tenant/branding" + (slug ? `?tenant=${encodeURIComponent(slug)}` : "");
      const data = await MugenApi.get(path);
      current = data;
      localStorage.setItem(KEY, JSON.stringify(data));
      preload(current.logo_url);
    } catch (e) {
      // offline / gagal -> tetap pakai cache/default yang sudah ada, jangan error-kan halaman
    }
    applyToDom();
    return current;
  }

  return { get, refresh, applyToDom };
})();
