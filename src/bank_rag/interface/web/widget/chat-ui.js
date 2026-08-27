import { VoiceController } from "./voice-controller.js";

const GREETING = "Ciao! Sono l'assistente virtuale della banca. Come posso aiutarti oggi?";
const ERROR_MESSAGE = "Si è verificato un problema. Riprova tra poco, oppure contatta un operatore.";

// Shown once, after the greeting: makes the bot's capabilities legible up
// front ("capability transparency" is one of the four properties production
// chatbot UX research repeatedly names as the difference between a bot
// people trust and one they abandon — most abandonment is an interface
// failure, not a model failure).
const SUGGESTED_QUESTIONS = [
  "Quanto costa il Conto Base?",
  "Come blocco una carta smarrita?",
  "Voglio parlare con un operatore",
];

export class ChatUI {
  constructor({ client, container }) {
    this.client = client;
    this.container = container;
    this._greeted = false;
    this._voice = new VoiceController();
    this._readAloud = false;
    this._render();
  }

  _render() {
    this.container.innerHTML = `
      <button class="brag-bubble" data-role="bubble" aria-label="Apri la chat" type="button">💬</button>
      <div class="brag-panel" data-role="panel" role="dialog" aria-modal="true" aria-label="Assistente Banca" hidden>
        <header class="brag-header">
          <span>Assistente Banca</span>
          <div class="brag-header-actions">
            <button class="brag-voice-toggle" data-role="voice-toggle" type="button"
                    aria-label="Leggi le risposte ad alta voce" aria-pressed="false" hidden>🔊</button>
            <button class="brag-close" data-role="close" aria-label="Chiudi la chat" type="button">×</button>
          </div>
        </header>
        <div class="brag-messages" data-role="messages" aria-live="polite" aria-atomic="false"></div>
        <form class="brag-form" data-role="form">
          <label class="brag-sr-only" for="brag-input">Scrivi un messaggio</label>
          <input id="brag-input" class="brag-input" data-role="input" type="text"
                 placeholder="Scrivi un messaggio..." autocomplete="off">
          <button type="button" class="brag-mic" data-role="mic" aria-label="Parla per scrivere" hidden>🎤</button>
          <button type="submit" class="brag-send" aria-label="Invia messaggio">➤</button>
        </form>
      </div>
    `;

    this.bubble = this.container.querySelector('[data-role="bubble"]');
    this.panel = this.container.querySelector('[data-role="panel"]');
    this.messagesEl = this.container.querySelector('[data-role="messages"]');
    this.form = this.container.querySelector('[data-role="form"]');
    this.input = this.container.querySelector('[data-role="input"]');
    this.micButton = this.container.querySelector('[data-role="mic"]');
    this.voiceToggle = this.container.querySelector('[data-role="voice-toggle"]');

    this.bubble.addEventListener("click", () => this._open());
    this.container.querySelector('[data-role="close"]').addEventListener("click", () => this._close());
    this.form.addEventListener("submit", (event) => this._handleSubmit(event));
    // Bound to `document`, not `this.panel`: a keydown only bubbles from
    // whatever element currently has focus, and focus is lost to <body>
    // after a button click removes itself from the DOM (e.g. a suggestion
    // chip) — a listener scoped to the panel would silently stop firing
    // in exactly that state.
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !this.panel.hidden) this._close();
    });

    this._wireVoiceControls();
  }

  _wireVoiceControls() {
    if (this._voice.canListen) {
      this.micButton.hidden = false;
      this.micButton.addEventListener("click", () => {
        this.micButton.classList.add("brag-mic-listening");
        this._voice.listen({
          onResult: (transcript) => {
            this.input.value = transcript;
            this.input.focus();
          },
          onEnd: () => this.micButton.classList.remove("brag-mic-listening"),
        });
      });
    }

    if (this._voice.canSpeak) {
      this.voiceToggle.hidden = false;
      this.voiceToggle.addEventListener("click", () => {
        this._readAloud = !this._readAloud;
        this.voiceToggle.setAttribute("aria-pressed", String(this._readAloud));
        this.voiceToggle.classList.toggle("brag-voice-toggle-active", this._readAloud);
        if (!this._readAloud) this._voice.stopSpeaking();
      });
    }
  }

  _open() {
    this.panel.hidden = false;
    this.bubble.hidden = true;
    if (!this._greeted) {
      this._addMessage("assistant", GREETING);
      this._addSuggestedQuestions();
      this._greeted = true;
    }
    this.input.focus();
  }

  _close() {
    this.panel.hidden = true;
    this.bubble.hidden = false;
    this._voice.stopSpeaking();
    this.bubble.focus(); // return focus to the trigger for keyboard/screen-reader users
  }

  _addSuggestedQuestions() {
    const wrap = document.createElement("div");
    wrap.className = "brag-suggestions";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", "Domande suggerite");
    for (const question of SUGGESTED_QUESTIONS) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "brag-suggestion";
      chip.textContent = question;
      chip.addEventListener("click", () => {
        wrap.remove();
        this._send(question);
      });
      wrap.appendChild(chip);
    }
    this.messagesEl.appendChild(wrap);
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
  }

  async _handleSubmit(event) {
    event.preventDefault();
    const text = this.input.value.trim();
    if (!text) return;
    this.input.value = "";
    this.container.querySelector(".brag-suggestions")?.remove();
    await this._send(text);
  }

  async _send(text) {
    this._addMessage("user", text);
    const typingEl = this._addTypingIndicator();
    let assistantEl = null;
    let accumulated = "";

    const revealAssistantBubble = () => {
      if (assistantEl) return;
      typingEl.remove();
      assistantEl = this._addMessage("assistant", "");
    };

    try {
      await this.client.sendMessageStreaming(text, {
        onDelta: (delta) => {
          revealAssistantBubble();
          accumulated += delta;
          assistantEl.querySelector(".brag-message-text").textContent = accumulated;
          this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
        },
        onDone: (event) => {
          revealAssistantBubble(); // covers the (rare) zero-delta case, e.g. a pending-action prompt
          const finalText = accumulated || event.answer;
          if (!accumulated) {
            assistantEl.querySelector(".brag-message-text").textContent = finalText;
          }
          if (event.citations && event.citations.length) {
            assistantEl.appendChild(this._renderCitations(event.citations));
          }
          if (this._readAloud) this._voice.speak(finalText);
        },
      });
    } catch {
      typingEl.remove();
      assistantEl?.remove();
      this._addMessage("assistant", ERROR_MESSAGE);
    }
  }

  _addTypingIndicator() {
    const el = document.createElement("div");
    el.className = "brag-message brag-message-assistant brag-typing";
    el.setAttribute("aria-label", "L'assistente sta scrivendo");
    el.innerHTML = '<span class="brag-dot"></span><span class="brag-dot"></span><span class="brag-dot"></span>';
    this.messagesEl.appendChild(el);
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    return el;
  }

  _addMessage(role, text, { citations = [] } = {}) {
    const el = document.createElement("div");
    el.className = `brag-message brag-message-${role}`;
    const textEl = document.createElement("span");
    textEl.className = "brag-message-text";
    textEl.textContent = text;
    el.appendChild(textEl);
    if (citations.length) {
      el.appendChild(this._renderCitations(citations));
    }
    this.messagesEl.appendChild(el);
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    return el;
  }

  _renderCitations(citations) {
    const wrap = document.createElement("div");
    wrap.className = "brag-citations";
    for (const citation of citations) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "brag-citation-chip";
      chip.textContent = citation.title;
      chip.setAttribute("aria-expanded", "false");

      const snippet = document.createElement("div");
      snippet.className = "brag-citation-snippet";
      snippet.textContent = citation.snippet || "";
      snippet.hidden = true;

      chip.addEventListener("click", () => {
        const isOpen = !snippet.hidden;
        snippet.hidden = isOpen;
        chip.setAttribute("aria-expanded", String(!isOpen));
      });

      const item = document.createElement("div");
      item.className = "brag-citation-item";
      item.appendChild(chip);
      item.appendChild(snippet);
      wrap.appendChild(item);
    }
    return wrap;
  }
}
