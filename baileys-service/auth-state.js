// auth-state.js — sesi login WhatsApp (auth_state) disimpan DI BACKEND
// PYTHON (lewat backend-client.js), BUKAN di file lokal seperti
// useMultiFileAuthState() bawaan Baileys -- supaya proses ini aman di-
// restart kapan saja (Render bisa mematikan/menghidupkan ulang service
// ini) tanpa kehilangan sesi & TANPA perlu disk persisten di service ini
// sama sekali. Polanya SAMA PERSIS useMultiFileAuthState() bawaan Baileys,
// cuma tempat baca/tulisnya diganti jadi satu blob JSON lewat HTTP.

const { proto, initAuthCreds, BufferJSON } = require("@whiskeysockets/baileys");
const backend = require("./backend-client");

async function useDbAuthState(tenantId) {
  const { auth_state } = await backend.ambilSesi(tenantId);
  let creds;
  let keysData = {};
  if (auth_state) {
    const parsed = JSON.parse(auth_state, BufferJSON.reviver);
    creds = parsed.creds;
    keysData = parsed.keys || {};
  } else {
    creds = initAuthCreds();
  }

  const simpan = async () => {
    const payload = JSON.stringify({ creds, keys: keysData }, BufferJSON.replacer);
    await backend.simpanSesi(tenantId, payload);
  };

  return {
    state: {
      creds,
      keys: {
        get: async (type, ids) => {
          const hasil = {};
          for (const id of ids) {
            let value = (keysData[type] || {})[id];
            if (value && type === "app-state-sync-key") {
              value = proto.Message.AppStateSyncKeyData.fromObject(value);
            }
            hasil[id] = value;
          }
          return hasil;
        },
        set: async (data) => {
          for (const kategori in data) {
            keysData[kategori] = keysData[kategori] || {};
            for (const id in data[kategori]) {
              const value = data[kategori][id];
              if (value) keysData[kategori][id] = value;
              else delete keysData[kategori][id];
            }
          }
          await simpan();
        },
      },
    },
    saveCreds: simpan,
  };
}

module.exports = { useDbAuthState };
