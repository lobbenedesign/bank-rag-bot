import { api } from "./api-client.js";

export function wireUrlForm(formEl, onDone) {
  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const statusEl = formEl.querySelector("[data-status]");
    statusEl.textContent = "Scaricamento e indicizzazione in corso...";
    statusEl.className = "status";
    const payload = {
      url: formEl.url.value,
      title: formEl.title.value || null,
      audience: formEl.audience.value,
    };
    try {
      const result = await api.ingestUrl(payload);
      statusEl.textContent = `Indicizzato: ${result.chunks_indexed} chunk da "${result.source_id}".`;
      statusEl.className = "status status-ok";
      formEl.reset();
      onDone?.();
    } catch (err) {
      statusEl.textContent = `Errore: ${err.message}`;
      statusEl.className = "status status-error";
    }
  });
}
