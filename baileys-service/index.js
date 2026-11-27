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
// CATATAN PENTING (sudah diuji end-to-end sungguhan oleh Owner, 27 Nov
// 2026): scan QR + kirim/terima pesan WhatsApp asli BERHASIL. Ditemukan 2
// bug nyata dari pengujian itu (sudah diperbaiki di revisi ini):
// 1. Logger BAWAAN Baileys (default pino level "info") ternyata mencetak
//    OBJEK SESI ENKRIPSI MENTAH (kunci privat Signal Protocol!) ke log
//    Render tiap sesi dibuat/ditutup -- risiko keamanan nyata (siapa pun
//    yang bisa baca log Render bisa baca kunci privat itu). Diperbaiki:
//    logger khusus level "error" dipasang eksplisit (lihat `_logBaileys`
//    di bawah) -- log yang KITA tulis sendiri (console.log/error) TIDAK
//    ikut terpengaruh, tetap muncul seperti biasa.
// 2. Satu pesan masuk dari customer bisa membuat 2 baris di Live Chat
//    kalau Fonnte (webhook LAMA) masih terpasang DI SAMPING Baileys yang
//    baru -- keduanya "melihat" pesan yang sama secara independen, tidak
//    ada cara mencocokkan ID antara 2 sistem berbeda itu. Diperbaiki di
//    sisi backend (routers/live_chat.py::terima_webhook() sekarang skip
//    diam-diam kalau tenant itu sudah tersambung Baileys) -- TAPI Owner
//    tetap disarankan melepas/menghapus URL webhook lama dari dashboard
//    Fonnte-nya sendiri supaya Fonnte berhenti mencoba sama sekali.

const express = require("express");
const pino = require("pino");
const makeWASocket = require("@whiskeysockets/baileys").default;
const { DisconnectReason, Browsers, fetchLatestBaileysVersion } = require("@whiskeysockets/baileys");

const backend = require("./backend-client");

// Lihat catatan keamanan di atas -- "error" saja (bukan default "info"),
// supaya dump state internal Baileys (termasuk kunci sesi Signal Protocol)
// tidak ikut tercetak ke log Render. console.log/error KITA sendiri di
// bawah TIDAK lewat logger ini, jadi tetap muncul seperti biasa.
const _logBaileys = pino({ level: "error" });
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
    logger: _logBaileys,
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
    // BUGFIX (pertanyaan Owner: pesan yang masuk SAAT service ini tertidur
    // -- lihat catatan free-tier Render di atas -- apakah ikut masuk begitu
    // bangun lagi): dipastikan LANGSUNG dari source code Baileys terpasang
    // (node_modules/@whiskeysockets/baileys/lib/Socket/messages-recv.js,
    // upsertMessage(msg, node.attrs.offline ? 'append' : 'notify')) --
    // WhatsApp MEMANG tetap mengirim ulang pesan yang terlewat saat koneksi
    // putus begitu socket ini sambung lagi, TAPI diberi tipe event
    // "append" (bukan "notify" yang dipakai pesan real-time). SEBELUM fix
    // ini, baris di bawah cuma menerima "notify" -- pesan susulan itu
    // dibuang diam-diam, tidak pernah ikut tersimpan di Rivoir. "append"
    // juga dipakai Baileys untuk notifikasi non-teks (reaksi/revoke/dst,
    // lihat messages-recv.js lain) -- itu otomatis tersaring sendiri di
    // _teruskanPesan() lewat cek `if (!teks) return`, jadi aman diterima
    // di sini tanpa menyaring tipe secara eksplisit.
    if (type !== "notify" && type !== "append") return;
    for (const msg of messages) {
      await _teruskanPesan(tenantId, msg);
    }
  });

  return sock;
}

async function _teruskanPesan(tenantId, msg) {
  if (!msg.message || !msg.key) return; // bukan pesan konten (reaksi/status, dst)
  let jid = msg.key.remoteJid || "";
  if (jid.endsWith("@g.us") || jid === "status@broadcast") return; // Live Chat khusus chat pribadi, bukan grup

  // BUGFIX (laporan Owner: nomor kontak yang muncul aneh/bukan angka WA
  // biasa, 1 pesan jadi 2 baris beda nomor): WhatsApp sedang migrasi
  // sebagian kontak ke pengenal "@lid" (Linked ID, demi privasi) alih-alih
  // nomor HP asli ("@s.whatsapp.net") -- Baileys MENYEDIAKAN padanan nomor
  // HP asli lewat `key.remoteJidAlt` KHUSUS untuk kasus ini (lihat
  // node_modules/@whiskeysockets/baileys/lib/Types/Message.d.ts). Dipakai
  // di sini supaya nomor_wa yang tersimpan SELALU nomor HP asli yang bisa
  // dikenali Owner, bukan ID internal WhatsApp yang tidak berarti apa pun.
  if (jid.endsWith("@lid") && msg.key.remoteJidAlt) {
    jid = msg.key.remoteJidAlt;
  }

  // Jenis gambar BELUM didukung di sini (lihat catatan rencana) -- hanya
  // pesan teks biasa (conversation/extendedTextMessage) yang diteruskan.
  const teks = msg.message.conversation || (msg.message.extendedTextMessage && msg.message.extendedTextMessage.text);
  if (!teks) return;

  const nomorWa = _nomorDariJid(jid);
  const arah = msg.key.fromMe ? "keluar" : "masuk";
  // Log bersih (BUKAN lewat _logBaileys yang sengaja dibungkam, lihat
  // catatan keamanan di atas) -- supaya gampang dicek di log Render kalau
  // ada laporan pesan tidak muncul/salah nomor, tanpa perlu menebak lagi.
  console.log(`[tenant ${tenantId}] pesan ${arah} dari/ke ${nomorWa}: "${teks.slice(0, 50)}"`);

  try {
    await backend.laporPesan(tenantId, {
      arah,
      nomor_wa: nomorWa,
      // PERMINTAAN Owner: tampilkan nomor HP sebagai identitas kontak,
      // BUKAN nama profil WhatsApp (pushName) -- frontend sudah otomatis
      // menampilkan nomor_wa kalau nama_kontak kosong (lihat
      // pages/live_chat.js::_renderKontakList()), jadi cukup kirim null.
      nama_kontak: null,
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

// BUGFIX (laporan Owner setelah redeploy: kirim/terima pesan error "tidak
// bisa terhubung"): `sockets` Map di atas HANYA hidup di memori proses ini
// -- tiap kali proses restart (redeploy, crash, dst) Map-nya kosong lagi,
// padahal auth_state tiap tenant tersimpan AMAN di backend Python. Tanpa
// ini, tenant yang sebelumnya 'tersambung' diam saja (tidak ada socket
// aktif) sampai seseorang kebetulan buka halaman Live Chat & klik
// "Hubungkan" lagi. Dipanggil SEKALI saat proses baru boot -- pakai
// auth_state yang sudah ada, JADI TIDAK PERLU scan QR ulang.
(async () => {
  let tenantIds;
  try {
    tenantIds = await backend.ambilTenantTersambung();
  } catch (e) {
    console.error("Gagal ambil daftar tenant tersambung saat boot:", e.message);
    return;
  }
  for (const tenantId of tenantIds) {
    console.log(`[tenant ${tenantId}] menyambung ulang otomatis setelah restart...`);
    mulaiSocket(tenantId).catch((e) => {
      console.error(`[tenant ${tenantId}] gagal menyambung ulang otomatis:`, e.message);
    });
  }
})();
