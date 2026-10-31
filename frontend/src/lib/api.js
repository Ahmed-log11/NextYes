// Thin client for the NextYes API. The base URL comes from VITE_API_URL (see .env.example).
const BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function call(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("json") ? res.json() : res.text();
}

export const api = {
  base: BASE,
  health: () => call("/api/health"),
  businesses: () => call("/api/businesses"),
  policies: () => call("/api/policies"),
  evaluation: () => call("/api/evaluation"),
  plannerEvaluation: () => call("/api/planner-evaluation"),
  start: (business_id, level = "realistic", policy_id = "commercial_bank_sme") =>
    call("/api/journeys", { method: "POST", body: JSON.stringify({ business_id, level, policy_id }) }),
  journey: (id) => call(`/api/journeys/${id}`),
  act: (id, action) => call(`/api/journeys/${id}/actions`, { method: "POST", body: JSON.stringify(action) }),
  documents: (id) => call(`/api/journeys/${id}/documents`),
  bank: (id) => call(`/api/journeys/${id}/bank`),
  documentUrl: (id, name) => `${BASE}/api/journeys/${id}/documents/${name}`,
};
