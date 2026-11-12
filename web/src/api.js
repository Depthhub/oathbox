export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

/* The founder's server session (from a wallet-signed message). Per-browser convenience only. */
const TOKEN_KEY = "oathbox.session.v1";
let memToken = null;

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || memToken;
  } catch {
    return memToken;
  }
}

export function setToken(token) {
  memToken = token || null;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the session lasts until the tab closes */
  }
}

async function request(path, { method = "GET", json, form } = {}) {
  const init = { method, headers: {} };
  const token = getToken();
  if (token) init.headers.Authorization = `Bearer ${token}`;
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Can't reach the Oathbox backend. Is it running on port 8000?", 0, null);
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    // A changed room or an unapproved server is an expected answer, not a crash.
    if (res.status === 409 && (data?.status === "room_changed" || data?.status === "server_not_approved")) return data;
    const detail = typeof data?.detail === "string" ? data.detail : `Request failed (HTTP ${res.status})`;
    throw new ApiError(detail, res.status, data);
  }
  return data;
}

export const api = {
  config: () => request("/api/config"),
  challenge: () => request("/api/auth/challenge"),
  verifyWallet: (body) => request("/api/auth/verify", { method: "POST", json: body }),
  me: () => request("/api/auth/me"),
  confirm: (id) => request(`/api/rooms/${encodeURIComponent(id)}/confirm`, { method: "POST" }),
  rooms: () => request("/api/rooms"),
  room: (id) => request(`/api/rooms/${encodeURIComponent(id)}`),
  commit: (id) => request(`/api/rooms/${encodeURIComponent(id)}/commit`, { method: "POST" }),
  upload: (form) => request("/api/rooms", { method: "POST", form }),
  ask: (id, question) => request(`/api/rooms/${encodeURIComponent(id)}/ask`, { method: "POST", json: { question } }),
  receipts: (id) => request(`/api/rooms/${encodeURIComponent(id)}/receipts`),
  verify: (receiptId, bundle) => request("/api/verify", { method: "POST", json: { receipt_id: receiptId, bundle: bundle || null } }),
  tamper: (on) => request("/api/demo/tamper", { method: "POST", json: { on } }),
};

/* The investor's own copies of receipt bundles, kept in this browser only. */
const KEY = "oathbox.exchanges.v1";

export function loadExchanges() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveExchanges(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, 50)));
  } catch {
    /* storage blocked: the page still works for this session */
  }
}

export function bundleFor(receiptId) {
  return loadExchanges().find((e) => e.receiptId === receiptId && e.bundle)?.bundle || null;
}

export function downloadBundle(bundle) {
  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `oathbox-receipt-${bundle.receipt_id}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function nsToDate(ns) {
  try {
    return new Date(Number(BigInt(ns) / 1000000n));
  } catch {
    return null;
  }
}
