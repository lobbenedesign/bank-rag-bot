const GREETING = "Ciao! Sono l'assistente virtuale della banca. Come posso aiutarti oggi?";
const ERROR_MESSAGE = "Si è verificato un problema. Riprova tra poco, oppure contatta un operatore.";

export class ChatUI {
  constructor({ client, container }) {
    this.client = client;
    this.container = container;
    this._greeted = false;
    this._render();
  }

  _render() {
    this.container.innerHTML = `
      <button class="brag-bubble" data-role="bubble" aria-label="Apri la chat" type="button">💬</button>
      <div class="brag-panel" data-role="panel" hidden>
        <header class="brag-header">
          <span>Assistente Banca</span>
          <button class="brag-close" data-role="close" aria-label="Chiudi" type="button">×</button>
        </header>
        <div class="brag-messages" data-role="messages" aria-live="polite"></div>
        <form class="brag-form" data-role="form">
          <input class="brag-input" data-role="input" type="text" placeholder="Scrivi un messaggio..." autocomplete="off">
          <button type="submit" class="brag-send" aria-label="Invia">➤</button>
        </form>
      </div>
    `;

    this.bubble = this.container.querySelector('[data-role="bubble"]');
    this.panel = this.container.querySelector('[data-role="panel"]');
    this.messagesEl = this.container.querySelector('[data-role="messages"]');
    this.form = this.container.querySelector('[data-role="form"]');
    this.input = this.container.querySelector('[data-role="input"]');

    this.bubble.addEventListener("click", () => this._open());
    this.container.querySelector('[data-role="close"]').addEventListener("click", () => this._close());
    this.form.addEventListener("submit", (event) => this._handleSubmit(event));
  }

  _open() {
    this.panel.hidden = false;
    this.bubble.hidden = true;
    if (!this._greeted) {
      this._addMessage("assistant", GREETING);
      this._greeted = true;
    }
    this.input.focus();
  }

  _close() {
    this.panel.hidden = true;
    this.bubble.hidden = false;
  }

  async _handleSubmit(event) {
    event.preventDefault();
    const text = this.input.value.trim();
    if (!text) return;
    this.input.value = "";
    this._addMessage("user", text);
    const typingEl = this._addMessage("assistant", "...", { typing: true });

    try {
      const answer = await this.client.sendMessage(text);
      typingEl.remove();
      this._addMessage("assistant", answer.answer, { citations: answer.citations });
    } catch {
      typingEl.remove();
      this._addMessage("assistant", ERROR_MESSAGE);
    }
  }

  _addMessage(role, text, { citations = [], typing = false } = {}) {
    const el = document.createElement("div");
    el.className = `brag-message brag-message-${role}${typing ? " brag-typing" : ""}`;
    el.textContent = text;
    if (citations.length) {
      const cites = document.createElement("div");
      cites.className = "brag-citations";
      cites.textContent = "Fonti: " + citations.map((c) => c.title).join(", ");
      el.appendChild(cites);
    }
    this.messagesEl.appendChild(el);
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    return el;
  }
}
