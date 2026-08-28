import { api } from "./api-client.js";
import { escapeHtml } from "./dom-utils.js";

export async function refreshDocumentsList(containerEl) {
  containerEl.innerHTML = "<p class='muted'>Caricamento...</p>";
  try {
    const documents = await api.listDocuments();
    if (documents.length === 0) {
      containerEl.innerHTML = "<p class='muted'>Nessun documento indicizzato.</p>";
      return;
    }
    containerEl.innerHTML = `
      <table>
        <thead>
          <tr><th>Titolo</th><th>Source ID</th><th>Ambito</th><th>Versione</th><th>Aggiornato</th><th>Da</th></tr>
        </thead>
        <tbody>
          ${documents
            .map(
              (d) => `
            <tr>
              <td>${escapeHtml(d.title)}</td>
              <td class="mono">${escapeHtml(d.source_id)}</td>
              <td><span class="badge badge-${d.audience}">${escapeHtml(d.audience)}</span></td>
              <td>${d.version}</td>
              <td>${new Date(d.updated_at).toLocaleString("it-IT")}</td>
              <td>${escapeHtml(d.uploaded_by || "-")}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  } catch (err) {
    containerEl.innerHTML = `<p class="error">Errore: ${escapeHtml(err.message)}</p>`;
  }
}

export function wireUploadForm(formEl, onDone) {
  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const statusEl = formEl.querySelector("[data-status]");
    statusEl.textContent = "Caricamento in corso...";
    statusEl.className = "status";
    try {
      const formData = new FormData(formEl);
      // An empty date input still submits as "" via FormData, which the
      // backend's `date | None` field rejects (not a valid ISO date) —
      // omit it entirely so FastAPI's own default (None, "no expiry")
      // applies, instead of sending a value that fails validation.
      if (!formData.get("valid_until")) formData.delete("valid_until");
      const result = await api.uploadDocument(formData);
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
