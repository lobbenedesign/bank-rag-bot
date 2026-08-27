// Talks to POST /chat and POST /chat/stream — the same endpoints the JSON
// API exposes to any client. No token is stored anywhere by default: an
// anonymous visitor gets PUBLIC-audience answers only, exactly like an
// anonymous request to the API directly (see
// interface/api/dependencies.py::get_identity). If the widget is embedded
// inside the bank's own logged-in online banking area, the host page can
// pass a short-lived token via `token` — this class never persists it (no
// localStorage/sessionStorage), it only holds it in memory for the
// lifetime of the page.
export class ChatClient {
  constructor({ baseUrl = "", token = null } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
    this.conversationId = null;
  }

  async sendMessage(message) {
    const response = await fetch(`${this.baseUrl}/chat`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify({ conversation_id: this.conversationId, message }),
    });

    if (!response.ok) {
      throw new Error(await this._errorDetail(response));
    }

    const data = await response.json();
    this.conversationId = data.conversation_id;
    return data;
  }

  // Server-Sent Events over a plain POST body (EventSource can't send a
  // body, so the stream is parsed by hand from the fetch response's
  // ReadableStream — a standard pattern for POST-initiated SSE). Calls
  // `onDelta(text)` for each incremental chunk and `onDone(event)` once
  // with the final { answer, citations, grounded, conversation_id }.
  async sendMessageStreaming(message, { onDelta, onDone }) {
    const response = await fetch(`${this.baseUrl}/chat/stream`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify({ conversation_id: this.conversationId, message }),
    });

    if (!response.ok || !response.body) {
      throw new Error(await this._errorDetail(response));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data: "));
        if (!dataLine) continue;

        const event = JSON.parse(dataLine.slice(6));
        if (event.type === "delta") {
          onDelta(event.text);
        } else if (event.type === "done") {
          this.conversationId = event.conversation_id;
          onDone(event);
        }
      }
    }
  }

  _headers() {
    const headers = { "Content-Type": "application/json" };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    return headers;
  }

  async _errorDetail(response) {
    const body = await response.json().catch(() => ({}));
    return body.detail || `Errore ${response.status}`;
  }
}
