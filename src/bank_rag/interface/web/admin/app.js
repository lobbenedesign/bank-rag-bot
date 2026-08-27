import { getToken, setToken, clearToken } from "./api-client.js";
import { refreshDocumentsList, wireUploadForm } from "./documents.js";
import { wireUrlForm } from "./urls.js";
import { refreshRulesList, wireRuleForm } from "./noindex.js";

const tokenInput = document.querySelector("#token-input");
const tokenForm = document.querySelector("#token-form");
const tokenStatus = document.querySelector("#token-status");
const tokenSection = document.querySelector("#token-section");
const appEl = document.querySelector("#app");

function updateTokenUi() {
  const hasToken = Boolean(getToken());
  appEl.hidden = !hasToken;
  tokenSection.hidden = hasToken;
  tokenStatus.textContent = hasToken
    ? "Token impostato per questa sessione del browser."
    : "Inserisci il tuo token employee per continuare.";
}

function refreshAll() {
  refreshDocumentsList(document.querySelector("#documents-table"));
  refreshRulesList(document.querySelector("#rules-table"));
}

tokenForm.addEventListener("submit", (event) => {
  event.preventDefault();
  setToken(tokenInput.value.trim());
  tokenInput.value = "";
  updateTokenUi();
  refreshAll();
});

document.querySelector("#logout-button").addEventListener("click", () => {
  clearToken();
  updateTokenUi();
});

wireUploadForm(document.querySelector("#upload-form"), refreshAll);
wireUrlForm(document.querySelector("#url-form"), refreshAll);
wireRuleForm(document.querySelector("#rule-form"), refreshAll);

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#${button.dataset.tab}`).classList.add("active");
  });
});

updateTokenUi();
if (getToken()) refreshAll();
