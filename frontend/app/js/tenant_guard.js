// tenant_guard.js — FITUR Subdomain Otomatis per Tenant
// =============================================================================
// SATU-SATUNYA tempat yang tahu cara mendeteksi "apakah domain yang
// sedang dibuka ini BENTUK subdomain tenant" (mis. mugenhairco.rivoirsett.com)
// dan memverifikasinya ke backend SEBELUM aplikasi (router.js/Login/dst)
// sempat dirender sama sekali -- kalau slug-nya ternyata tidak dikenal
// (tenant dihapus/dinonaktifkan/salah ketik), pengguna melihat halaman
// "Tenant Tidak Ditemukan" (pages/tenant_not_found.js), BUKAN halaman
// Login toko yang salah/branding platform yang membingungkan.
//
// PENTING (performa): pengecekan sungguhan (fetch ke backend) HANYA
// terjadi kalau hostname-nya memang BERBENTUK subdomain tenant --
// deployment root (rivoirsett.com), www, atau label sistem (api/app/
// admin/dst) TIDAK PERNAH memicu fetch tambahan apa pun di sini, byte-
// identik dengan alur boot SEBELUM fitur ini ada.

const MugenTenantGuard = (() => {
  const BASE_DOMAIN = (window.MUGEN_TENANT_BASE_DOMAIN || "").trim().toLowerCase();
  // SAMA PERSIS dengan tenant_middleware.py::LABEL_BUKAN_TENANT (backend
  // TETAP satu-satunya sumber kebenaran otorisasi -- daftar di sini MURNI
  // supaya klien tidak perlu fetch ke backend untuk label yang SUDAH PASTI
  // bukan tenant, mis. admin.rivoirsett.com langsung dianggap "bukan mode
  // subdomain tenant" tanpa network round-trip).
  const LABEL_BUKAN_TENANT = new Set(["www", "api", "app", "admin", "mail", "ftp"]);

  function slugDariHostname() {
    if (!BASE_DOMAIN) return null;
    const host = location.hostname.toLowerCase();
    if (!host.endsWith("." + BASE_DOMAIN)) return null;
    const sisa = host.slice(0, -(BASE_DOMAIN.length + 1));
    if (!sisa || sisa.indexOf(".") !== -1 || LABEL_BUKAN_TENANT.has(sisa)) return null;
    return sisa;
  }

  // Return true kalau boot APLIKASI NORMAL boleh lanjut (bukan mode
  // subdomain tenant, ATAU slug-nya terbukti valid), false kalau halaman
  // "Tenant Tidak Ditemukan" SUDAH dirender ke `appRoot` dan pemanggil
  // WAJIB berhenti (jangan panggil MugenRouter.init() dkk lagi).
  async function cekLaluRender(appRoot) {
    const slug = slugDariHostname();
    if (!slug) return true;
    try {
      const data = await MugenApi.get("/api/tenant/branding");
      // `is_platform_default: true` di sini artinya backend TIDAK berhasil
      // me-resolve slug dari subdomain ini ke tenant aktif mana pun (lihat
      // auth.py::resolve_tenant_untuk_branding()) -- SATU-SATUNYA sinyal
      // yang dipakai, TIDAK ADA endpoint terpisah yang perlu dibuat.
      if (data && data.is_platform_default) {
        // FITUR URL Booking Publik per Tenant (item 9 spesifikasi): kalau
        // tujuan navigasi sekarang MEMANG halaman booking publik (#/book),
        // JANGAN tampilkan "Tenant Tidak Ditemukan" (Bahasa Indonesia, untuk
        // aplikasi INTERNAL) di sini -- biarkan boot lanjut normal supaya
        // PageBookPublic sendiri yang menampilkan "Booking page not found"
        // (Bahasa Inggris, SESUAI spesifikasi -- lihat book_public.js) begitu
        // endpoint publiknya sendiri gagal menemukan tenant lewat slug MAUPUN
        // booking_slug. Untuk hash APA PUN yang lain (termasuk kosong/default
        // -- akses Dashboard/Login lewat subdomain tenant), perilaku LAMA
        // TIDAK BERUBAH sama sekali.
        // FITUR Kompatibilitas URL Booking (Instagram Bio dkk): "/book" atau
        // "/app/book" (PATH ASLI, BUKAN hash) sekarang JUGA dianggap tujuan
        // navigasi halaman booking publik, sama seperti hash "#/book" di
        // atas -- lihat komentar pathAdalahHalamanBook() di router.js untuk
        // penjelasan lengkap kenapa duplikasi kecil ini ada di dua tempat.
        const hash = location.hash || "";
        const path = location.pathname;
        const pathAdalahHalamanBook = path === "/book" || path.startsWith("/book/") ||
          path === "/app/book" || path.startsWith("/app/book/");
        if (pathAdalahHalamanBook || hash === "#/book" || hash.startsWith("#/book/") || hash.startsWith("#/book?")) {
          return true;
        }
        appRoot.innerHTML = "";
        PageTenantNotFound.render(appRoot, slug);
        return false;
      }
    } catch (e) {
      // Gagal terhubung (offline dkk) -- JANGAN blokir akses ke seluruh
      // aplikasi hanya karena satu pengecekan ini gagal, biarkan alur boot
      // normal lanjut (halaman yang dituju akan menampilkan error jaringan
      // miliknya sendiri kalau memang bermasalah).
    }
    return true;
  }

  return { slugDariHostname, cekLaluRender };
})();
