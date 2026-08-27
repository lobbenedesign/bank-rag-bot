// Wraps the browser's native Web Speech API — SpeechRecognition for
// speech-to-text, SpeechSynthesis for text-to-speech. Real capabilities,
// not simulated: no backend involvement, no new dependency, just what the
// browser already ships. Both are feature-detected — support varies a lot
// across browsers (Chrome/Edge: full; Safari: partial; Firefox: synthesis
// only, no recognition at the time of writing) — callers must check
// `.canListen`/`.canSpeak` and hide the corresponding UI entirely when
// unsupported, rather than showing a control that silently does nothing.
export class VoiceController {
  constructor({ lang = document.documentElement.lang || "it-IT" } = {}) {
    this.lang = lang;
    const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.canListen = Boolean(RecognitionCtor);
    this.canSpeak = "speechSynthesis" in window;
    this._recognition = this.canListen ? new RecognitionCtor() : null;
    if (this._recognition) {
      this._recognition.lang = this.lang;
      this._recognition.interimResults = false;
      this._recognition.maxAlternatives = 1;
    }
  }

  // `onEnd` fires whether recognition succeeded, failed, or was cancelled —
  // callers use it to reset "listening" UI state (e.g. a pulsing mic icon)
  // regardless of outcome.
  listen({ onResult, onError, onEnd }) {
    if (!this.canListen) return;
    this._recognition.onresult = (event) => onResult(event.results[0][0].transcript);
    this._recognition.onerror = (event) => onError?.(event.error);
    this._recognition.onend = () => onEnd?.();
    this._recognition.start();
  }

  speak(text) {
    if (!this.canSpeak || !text) return;
    window.speechSynthesis.cancel(); // don't queue overlapping utterances
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = this.lang;
    window.speechSynthesis.speak(utterance);
  }

  stopSpeaking() {
    if (this.canSpeak) window.speechSynthesis.cancel();
  }
}
