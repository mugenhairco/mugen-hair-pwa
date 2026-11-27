// backend-client.js — jembatan HTTP ke backend Python (SATU-SATUNYA tempat
// di service ini yang bicara ke backend Rivoir, lihat docstring index.js
// untuk kenapa service ini TIDAK PERNAH connect ke Neon langsung).
//
// Dilindungi shared secret (BAILEYS_INTERNAL_SECRET, SAMA PERSIS nilai yang
// diisi di backend Python -- pola header X-Cron-Secret/CRON_REMINDER_SECRET
// yang sudah dipakai routers/cron_reminder.py), dikirim lewat header
// "X-Baileys-Secret" (lihat routers/live_chat_baileys.py::_wajib_secret_
// internal() di backend).

const BACKEND_URL = (process.env.BACKEND_URL || "").replace(/\/$/, "");
const SECRET = process.env.BAILEYS_INTERNAL_SECRET || "";

function _headers(extra = {}) {
  return { "X-Baileys-Secret": SECRET, "Content-Type": "application/json", ...extra };
}

async function ambilTenantTersambung() {
  const r = await fetch(`${BACKEND_URL}/api/internal/baileys/tersambung`, { headers: _headers() });
  if (!r.ok) throw new Error(`ambilTenantTersambung gagal (HTTP ${r.status})`);
  const data = await r.json();
  return data.tenant_id; // array of number
}

async function ambilSesi(tenantId) {
  const r = await fetch(`${BACKEND_URL}/api/internal/baileys/sesi/${tenantId}`, { headers: _headers() });
  if (!r.ok) throw new Error(`ambilSesi gagal (HTTP ${r.status})`);
  return r.json(); // { auth_state: string|null }
}

async function simpanSesi(tenantId, authStateJson) {
  const r = await fetch(`${BACKEND_URL}/api/internal/baileys/sesi/${tenantId}`, {
    method: "PUT",
    headers: _headers(),
    body: JSON.stringify({ auth_state: authStateJson }),
  });
  if (!r.ok) throw new Error(`simpanSesi gagal (HTTP ${r.status})`);
}

async function laporStatus(tenantId, status, extra = {}) {
  const r = await fetch(`${BACKEND_URL}/api/internal/baileys/status/${tenantId}`, {
    method: "POST",
    headers: _headers(),
    body: JSON.stringify({ status, ...extra }),
  });
  if (!r.ok) throw new Error(`laporStatus gagal (HTTP ${r.status})`);
}

async function laporPesan(tenantId, body) {
  const r = await fetch(`${BACKEND_URL}/api/internal/baileys/pesan/${tenantId}`, {
    method: "POST",
    headers: _headers(),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`laporPesan gagal (HTTP ${r.status})`);
}

module.exports = { ambilTenantTersambung, ambilSesi, simpanSesi, laporStatus, laporPesan };
