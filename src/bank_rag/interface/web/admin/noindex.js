import { api } from "./api-client.js";
import { escapeHtml } from "./dom-utils.js";

export async function refreshRulesList(containerEl) {
  containerEl.innerHTML = "<p class='muted'>Caricamento...</p>";
  try {
    const rules = await api.listNoIndexRules();
    if (rules.length === 0) {
      containerEl.innerHTML = "<p class='muted'>Nessuna regola no-index attiva.</p>";
      return;
    }
    containerEl.innerHTML = `
      <table>
        <thead>
          <tr><th>Pattern</th><th>Tipo</th><th>Ambito esclusione</th><th>Motivo</th><th>Da</th><th></th></tr>
        </thead>
        <tbody>
          ${rules
            .map(
              (r) => `
            <tr>
              <td class="mono">${escapeHtml(r.pattern)}</td>
              <td>${escapeHtml(r.rule_type)}</td>
              <td>${
                r.locator_kind
                  ? `${escapeHtml(r.locator_kind)}: <span class="mono">${escapeHtml(r.locator_pattern)}</span>`
                  : "intero documento"
              }</td>
              <td>${escapeHtml(r.reason)}</td>
              <td>${escapeHtml(r.created_by)}</td>
              <td><button class="btn-remove" type="button" data-pattern="${escapeHtml(r.pattern)}">Rimuovi</button></td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;

    containerEl.querySelectorAll(".btn-remove").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm(`Rimuovere la regola su "${btn.dataset.pattern}"?`)) return;
        await api.removeNoIndexRule(btn.dataset.pattern);
        refreshRulesList(containerEl);
      });
    });
  } catch (err) {
    containerEl.innerHTML = `<p class="error">Errore: ${escapeHtml(err.message)}</p>`;
  }
}

export function wireRuleForm(formEl, onDone) {
  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const statusEl = formEl.querySelector("[data-status]");
    statusEl.textContent = "Applicazione della regola in corso...";
    statusEl.className = "status";
    const payload = {
      pattern: formEl.pattern.value,
      rule_type: formEl.rule_type.value,
      reason: formEl.reason.value,
      locator_kind: formEl.locator_kind.value || null,
      locator_pattern: formEl.locator_pattern.value || null,
    };
    try {
      const result = await api.addNoIndexRule(payload);
      const purgedKey = Object.keys(result).find((k) => k.endsWith("_purged"));
      const purgedCount = purgedKey ? result[purgedKey] : 0;
      const unit = payload.locator_kind ? "chunk purgati" : "documenti purgati";
      statusEl.textContent = `Regola aggiunta. ${purgedCount} ${unit}.`;
      statusEl.className = "status status-ok";
      formEl.reset();
      onDone?.();
    } catch (err) {
      statusEl.textContent = `Errore: ${err.message}`;
      statusEl.className = "status status-error";
    }
  });
}
