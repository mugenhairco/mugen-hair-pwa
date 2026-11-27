// index.js — FITUR Live Chat via Baileys (WhatsApp Web sendiri)
// =============================================================================
// Lihat docstring backend/app/live_chat_baileys_db.py untuk latar belakang &
// arsitektur lengkap (kenapa service terpisah ini ada, kenapa berdampingan
// dengan Fonnte bukan ganti total). Ringkasan:
//
// - Multi-tenant SEJAK AWAL (konsisten pola seluruh codebase Rivoir): SATU
//   proses Node.js ini memegang BANYAK socket Baileys sekaligus, satu per
//   tenant_id yang sedang aktif/tersambung (lihat `sockets` Map di bawah).
// - TIDAK connect ke Neon/database apa pun sama sekali -- semua penyimpanan
//   (termasuk sesi login WhatsApp-nya sendiri) dititipkan ke backend Python
//   lewat HTTP (lihat backend-client.js), dilindungi satu shared secret
//   (BAILEYS_INTERNAL_SECRET) -- service ini TIDAK PERNAH memegang
//   kredensial database.
// - Endpoint yang diekspos di sini (dipanggil backend Python, lihat
//   routers/live_chat_baileys.py): POST /tenant/:tenantId/connect, kirim,
//   putuskan.
//
// CATATAN PENTING (belum diuji end-to-end sungguhan): kode ini sudah
// diverifikasi `node --check` + `npm install` berhasil di sandbox
// pengembangan, TAPI belum pernah dites scan QR sungguhan + kirim/terima
// pesan WhatsApp asli (sandbox ini tidak punya HP/nomor WhatsApp untuk
// dites) -- WAJIB diuji manual oleh Owner di nomor UJI COBA (bukan nomor
// toko aktif) sebelum dipakai sungguhan, sesuai kesepakatan di plan.

const express = require("express");
const makeWASocket = require("@whiskeysockets/baileys").default;
const { DisconnectReason, Browsers, fetchLatestBaileysVersion } = require("@whiskeysockets/baileys");

const backend = require("./backend-client");
const { useDbAuthState } = require("./auth-state");

const PORT = process.env.PORT || 3000;

// tenant_id (number) -> socket Baileys aktif. Satu-satunya "sumber
// kebenaran" soal tenant mana yang sedang tersambung di PROSES ini --
// status TERSIMPAN (live_chat_baileys_sesi.status di backend Python) bisa
// saja mengatakan 'tersambung' dari sesi sebelumnya walau proses ini baru
// saja restart (Map ini kosong lagi) -- connect() dipanggil ulang
// otomatis saat reconnect (lihat connection.update di bawah) MEMAKAI
// auth_state tersimpan, jadi tidak perlu scan QR ulang.
const sockets = new Map();

function _nomorDariJid(jid) {
  return (jid || "").split("@")[0];
}

async function mulaiSocket(tenantId) {
  if (sockets.has(tenantId)) return sockets.get(tenantId);

  const { state, saveCreds } = await useDbAuthState(tenantId);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    browser: Browsers.ubuntu("Rivoir Live Chat"),
    printQRInTerminal: false,
  });
  sockets.set(tenantId, sock);

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;
    try {
      if (qr) {
        await backend.laporStatus(tenantId, "menunggu_scan", { qr_data: qr });
      }
      if (connection === "open") {
        const nomor = _nomorDariJid(sock.user && sock.user.id);
        await backend.laporStatus(tenantId, "tersambung", { nomor_tersambung: nomor });
      }
      if (connection === "close") {
        sockets.delete(tenantId);
        await backend.laporStatus(tenantId, "terputus");
        const kodeAlasan = lastDisconnect && lastDisconnect.error && lastDisconnect.error.output
          && lastDisconnect.error.output.statusCode;
        // Logout EKSPLISIT (tombol "Putuskan", lihat /tenant/:id/putuskan di
        // bawah) -- JANGAN coba sambung ulang otomatis. Sebab lain (jaringan
        // putus sebentar, dst) -- coba sambung ulang, auth_state tersimpan
        // dipakai lagi, TIDAK perlu scan QR ulang.
        if (kodeAlasan !== DisconnectReason.loggedOut) {
          setTimeout(() => { mulaiSocket(tenantId).catch(() => {}); }, 5000);
        }
      }
    } catch (e) {
      console.error(`[tenant ${tenantId}] gagal lapor status:`, e.message);
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      await _teruskanPesan(tenantId, msg);
    }
  });

  return sock;
}

async function _teruskanPesan(tenantId, msg) {
  if (!msg.message || !msg.key) return; // bukan pesan konten (reaksi/status, dst)
  const jid = msg.key.remoteJid || "";
  if (jid.endsWith("@g.us") || jid === "status@broadcast") return; // Live Chat khusus chat pribadi, bukan grup

  // Jenis gambar BELUM didukung di sini (lihat catatan rencana) -- hanya
  // pesan teks biasa (conversation/extendedTextMessage) yang diteruskan.
  const teks = msg.message.conversation || (msg.message.extendedTextMessage && msg.message.extendedTextMessage.text);
  if (!teks) return;

  try {
    await backend.laporPesan(tenantId, {
      arah: msg.key.fromMe ? "keluar" : "masuk",
      nomor_wa: _nomorDariJid(jid),
      nama_kontak: msg.pushName || null,
      isi_teks: teks,
      baileys_msg_id: msg.key.id,
    });
  } catch (e) {
    console.error(`[tenant ${tenantId}] gagal lapor pesan:`, e.message);
  }
}

const app = express();
app.use(express.json());

app.get("/health", (req, res) => res.json({ ok: true }));

app.post("/tenant/:tenantId/connect", async (req, res) => {
  const tenantId = Number(req.params.tenantId);
  try {
    await mulaiSocket(tenantId);
    res.json({ ok: true });
  } catch (e) {
    console.error(`[tenant ${tenantId}] gagal connect:`, e);
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

app.post("/tenant/:tenantId/kirim", async (req, res) => {
  const tenantId = Number(req.params.tenantId);
  const sock = sockets.get(tenantId);
  if (!sock) {
    return res.status(409).json({ ok: false, error: "Belum tersambung ke WhatsApp." });
  }
  const { nomor_wa, pesan } = req.body || {};
  if (!nomor_wa || !pesan) {
    return res.status(422).json({ ok: false, error: "nomor_wa dan pesan wajib diisi." });
  }
  try {
    const hasil = await sock.sendMessage(`${nomor_wa}@s.whatsapp.net`, { text: pesan });
    res.json({ ok: true, baileys_msg_id: hasil.key.id });
  } catch (e) {
    console.error(`[tenant ${tenantId}] gagal kirim:`, e);
    res.status(502).json({ ok: false, error: String(e.message || e) });
  }
});

app.post("/tenant/:tenantId/putuskan", async (req, res) => {
  const tenantId = Number(req.params.tenantId);
  const sock = sockets.get(tenantId);
  if (sock) {
    try { await sock.logout(); } catch (e) { /* abaikan -- tetap lanjut hapus dari Map */ }
    sockets.delete(tenantId);
  }
  res.json({ ok: true });
});

app.listen(PORT, () => {
  console.log(`baileys-service jalan di port ${PORT}`);
});
