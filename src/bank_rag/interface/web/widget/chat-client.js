// Talks to POST /chat — the same endpoint the JSON API exposes to any
// client. No token is stored anywhere by default: an anonymous visitor gets
// PUBLIC-audience answers only, exactly like an anonymous request to the
// API directly (see interface/api/dependencies.py::get_identity). If the
// widget is embedded inside the bank's own logged-in online banking area,
// the host page can pass a short-lived token via `token` — this class never
// persists it (no localStorage/sessionStorage), it only holds it in memory
// for the lifetime of the page.
export class ChatClient {
  constructor({ baseUrl = "", token = null } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
    this.conversationId = null;
  }

  async sendMessage(message) {
    const headers = { "Content-Type": "application/json" };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const response = await fetch(`${this.baseUrl}/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({ conversation_id: this.conversationId, message }),
    });

    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Errore ${response.status}`);
    }

    const data = await response.json();
    this.conversationId = data.conversation_id;
    return data;
  }
}
