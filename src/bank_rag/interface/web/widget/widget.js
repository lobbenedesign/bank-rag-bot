// Bootstrap entry point — the ONE file a bank embeds on their site:
//   <script type="module" src="https://.../widget/widget.js"
//           data-bank-rag-widget data-api-base-url="https://.../">
//   </script>
//
// `document.currentScript` is always null for module scripts (per spec,
// module execution is deferred and detached from the triggering tag), so
// the script tag is located via its own data attribute instead.
import { ChatClient } from "./chat-client.js";
import { ChatUI } from "./chat-ui.js";

function findScriptTag() {
  return (
    document.querySelector("script[data-bank-rag-widget]") || document.querySelector('script[src*="widget.js"]')
  );
}

function injectStyles() {
  if (document.querySelector("#brag-widget-styles")) return;
  const link = document.createElement("link");
  link.id = "brag-widget-styles";
  link.rel = "stylesheet";
  link.href = new URL("widget.css", import.meta.url).href;
  document.head.appendChild(link);
}

function init() {
  const scriptTag = findScriptTag();
  const baseUrl = scriptTag?.dataset.apiBaseUrl || "";
  const token = scriptTag?.dataset.token || null;

  injectStyles();

  const container = document.createElement("div");
  container.id = "brag-widget-root";
  document.body.appendChild(container);

  const client = new ChatClient({ baseUrl, token });
  new ChatUI({ client, container });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
