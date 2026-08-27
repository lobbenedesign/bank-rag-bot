// Thin fetch wrapper around the existing JSON API (see interface/api/routers/).
// Zero business logic here — every call maps 1:1 to a REST endpoint that
// already exists for the API itself; this file is presentation-layer glue,
// not a second implementation of anything.

const TOKEN_KEY = "bank_rag_admin_token";

// sessionStorage, not localStorage: cleared when the tab closes, so a JWT
// left in the browser doesn't outlive the employee's session on a shared
// workstation. Still readable by any script on this origin if XSS occurs —
// acceptable trade-off for an internal tool behind the bank's own network,
// not appropriate for the public-facing widget (which never stores a token).
export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(path, { ...options, headers });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // no JSON body on this error response — keep statusText
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  listDocuments: () => request("/admin/documents"),
  uploadDocument: (formData) => request("/admin/documents", { method: "POST", body: formData }),
  ingestUrl: (payload) =>
    request("/admin/urls", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listNoIndexRules: () => request("/admin/noindex"),
  addNoIndexRule: (payload) =>
    request("/admin/noindex", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  removeNoIndexRule: (pattern) => request(`/admin/noindex/${encodeURIComponent(pattern)}`, { method: "DELETE" }),
};
