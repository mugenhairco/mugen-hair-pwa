// pages/tenant_not_found.js — FITUR Subdomain Otomatis per Tenant
// =============================================================================
// Dirender oleh tenant_guard.js SEBELUM router.js/app.js lanjut boot sama
// sekali -- dipanggil langsung dengan `appRoot` (BUKAN lewat router.js::
// shell(), pola sama seperti PageLogin/PageRegister), jadi TIDAK ADA
// sidebar/menu apa pun yang mungkin bocor mengarah ke tenant lain.

const PageTenantNotFound = (() => {
  function render(root, slug) {
    root.innerHTML = "";
    const wrap = MugenUI.el("div", { class: "login-wrap" });
    const card = MugenUI.el("div", { class: "login-card", style: "text-align:center;" });

    // BUGFIX: class "brand-name" DIPAKAI brand.js (_terapkanKeDom()) untuk
    // menimpa textContent elemen apa pun yang memilikinya dengan nama
    // platform/tenant -- refreshPlatformOnly() di bawah akan langsung
    // menimpanya jadi "Rivoir" kalau dipakai di sini, MENGHILANGKAN judul
    // "Tenant Tidak Ditemukan" ini seketika. Wordmark "Rivoir" (elemen
    // TERPISAH, kecil) dipakai brand-name-nya, judul 404 di bawah POLOS.
    card.appendChild(MugenUI.el("div", {
      class: "brand-name", style: "font-size:14px;font-weight:600;color:var(--text-dim);margin-bottom:20px;",
    }, "Rivoir"));
    card.appendChild(MugenUI.el("div", {
      style: "font-size:56px;font-weight:800;color:var(--accent);line-height:1;margin-bottom:8px;",
    }, "404"));
    card.appendChild(MugenUI.el("h1", { style: "font-size:22px;margin:0;" }, "Tenant Tidak Ditemukan"));
    card.appendChild(MugenUI.el("p", { style: "font-size:14px;color:var(--text-dim);margin:12px 0 24px;" },
      `Toko dengan alamat "${slug}" tidak ditemukan, sudah tidak aktif, atau alamatnya salah ketik. ` +
      "Periksa kembali link yang Anda buka, atau hubungi pemilik toko untuk memastikan alamatnya."));

    const base = (window.MUGEN_TENANT_BASE_DOMAIN || "").trim();
    if (base) {
      const linkBeranda = MugenUI.el("a", {
        href: `https://${base}/`, class: "btn-primary",
        style: "display:block;width:100%;text-decoration:none;box-sizing:border-box;",
      }, "Ke Halaman Utama Rivoir");
      card.appendChild(linkBeranda);
      const linkDaftar = MugenUI.el("a", {
        href: `https://${base}/app/#/register`,
        style: "display:block;text-align:center;margin-top:16px;",
      }, "Daftarkan Barbershop Anda");
      card.appendChild(linkDaftar);
    }

    wrap.appendChild(card);
    root.appendChild(wrap);

    // Halaman ini PUBLIK murni & lintas-tenant secara desain (slug-nya
    // sendiri TIDAK dikenal) -- branding SELALU platform Rivoir, sama
    // seperti Register/Lupa Password/dst.
    if (typeof MugenBrand !== "undefined") MugenBrand.refreshPlatformOnly();
  }

  return { render };
})();
