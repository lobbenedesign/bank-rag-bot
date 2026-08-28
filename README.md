# Bank RAG Bot

Chatbot agentico per il sito di una banca: risponde usando sia i contenuti
pubblici del sito sia documenti interni caricati dai dipendenti, con
guardrail di grounding e RBAC sui dati indicizzati.

Vedi [ARCHITECTURE.md](ARCHITECTURE.md) per il razionale delle scelte
architetturali e cosa manca ancora per la produzione.

## Screenshot

Catturati con Chrome headless contro le UI statiche reali di questo repository — non mockup grafici. Il widget usa dati di risposta di esempio (dichiarati come tali: il backend richiede Qdrant/OpenSearch/Postgres/Redis/OpenAI in esecuzione, non attivi in questa cattura), la UI admin usa dati di esempio per la tabella (backend Postgres non in esecuzione). Il markup, il CSS e la logica JS sono quelli reali, non modificati per lo screenshot.

### Widget cliente

| Chiuso | Aperto (domande suggerite) | Conversazione (citazione espansa) |
|---|---|---|
| ![Widget chiuso](docs/screenshots/widget-closed.png) | ![Widget aperto](docs/screenshots/widget-open.png) | ![Conversazione](docs/screenshots/widget-conversation.png) |

Streaming reale della risposta (SSE), citazioni cliccabili con snippet, domande suggerite, microfono/lettura vocale via Web Speech API nativa del browser (visibili solo se il browser le supporta).

### Pannello admin — ingestion

| Accesso (token JWT) | Gestione documenti | Esclusioni granulari (no-index) |
|---|---|---|
| ![Login](docs/screenshots/admin-login.png) | ![Documenti](docs/screenshots/admin-documents.png) | ![No-index](docs/screenshots/admin-noindex.png) |

Upload di 8 formati (PDF/DOCX/MD/TXT/CSV/XLSX/JSON/XML), indicizzazione URL on-demand, ed esclusione dall'indicizzazione sia per intero documento sia per porzione specifica (pagina, sezione, riga — vedi la riga `page_paragraph: 4:*` nello screenshot, che esclude solo un paragrafo di una pagina di un PDF senza toccare il resto).

## Quickstart

**Setup guidato** (consigliato — controlla Docker, crea `.env` chiedendo le chiavi, alza i container, aspetta che siano pronti, provisiona Qdrant):

```bash
make setup
```

**Setup manuale**, passo per passo:

```bash
cp .env.example .env   # valorizza OPENAI_API_KEY, CORE_BANKING_*
docker compose up -d qdrant opensearch redis postgres   # = make up
python -m bank_rag.infrastructure.vector_stores.qdrant_bootstrap   # = make bootstrap
pip install -e ".[dev]"
uvicorn bank_rag.interface.api.main:app --reload   # = make run
```

Qdrant, OpenSearch, Redis e Postgres sono interamente containerizzati: nessuna
installazione manuale sul sistema, solo Docker. OpenAI resta l'unica eccezione
perché è un'API esterna a pagamento, non software auto-ospitabile — per un
setup completamente locale/gratuito, sostituire `OpenAiChatClient`/`OpenAiEmbedder`
con un adapter Ollama dietro le stesse porte `LLMClient`/`Embedder`.

## Test

```bash
pytest
```

## Endpoint principali

- `POST /chat` — messaggio utente (autenticato o anonimo) -> risposta grounded + citazioni.
- `POST /admin/documents` — upload file (PDF/DOCX/MD/TXT/CSV/XLSX/JSON/XML) da parte di un dipendente (richiede token employee).
- `GET /admin/documents` — elenco documenti indicizzati.
- `POST /admin/urls` — indicizza una singola pagina del sito su richiesta (oltre alla sincronizzazione periodica in `ingestion/pipeline.py`).
- `GET/POST/DELETE /admin/noindex` — regole di esclusione dall'indicizzazione, per intero documento o per porzione (pagina/sezione/riga — vedi ARCHITECTURE.md).
- `GET /health`

## Interfacce web

Due UI statiche (HTML/CSS/JS puro, nessun framework, nessuna build), servite dalla stessa app FastAPI come layer di presentazione sopra l'API JSON — zero logica di business duplicata:

- **`/admin-ui/`** — pannello per i dipendenti: upload file, indicizzazione URL on-demand, gestione regole no-index (incluse quelle granulari per pagina/sezione). Richiede un token JWT employee, inserito manualmente e tenuto solo in `sessionStorage` (mai persistito).
- **`/widget/`** — widget chat per i clienti, incorporabile nel sito della banca con un solo `<script type="module">`. `/widget/index.html` è una pagina dimostrativa che mostra l'integrazione reale.

## Architettura del RAG, onesta

**Pipeline di retrieval**: vector search (Qdrant) + BM25 lessicale (OpenSearch), fusi con Reciprocal Rank Fusion, poi ridotti con un reranker cross-encoder ai `top_k` finali — non solo similarità vettoriale, perché quest'ultima da sola perde termini esatti (codici prodotto, percentuali) tipici di documenti bancari. Dettagli e motivazioni in [ARCHITECTURE.md](ARCHITECTURE.md).

**Guardrail, non solo istruzioni nel prompt**: filtro di ambito (rifiuta domande non bancarie prima di spendere un ciclo dell'agente), escalation su frustrazione del cliente, conferma esplicita prima di eseguire azioni ad alto rischio (blocco carta), RBAC sui vettori applicato server-side (mai a livello di prompt), sanitizer anti prompt-injection sui documenti caricati, audit trail append-only.

**Cosa è verificato per davvero, non solo scritto**: 78 unit test (fake in memoria, zero rete), più uno smoke test con `uvicorn` avviato realmente e richieste HTTP vere (routing, JWT, rate limiting) — vedi la sezione "Smoke test end-to-end" in ARCHITECTURE.md per l'esito esatto e i due bug reali trovati così (non nei test).

**Cosa NON è mai stato verificato contro servizi reali**: una vera risposta con Qdrant/OpenSearch/Postgres/Redis/OpenAI tutti in esecuzione insieme — non fatto in questa sessione per limiti di spazio disco della macchina di sviluppo, dichiarato esplicitamente, non nascosto.

**Cosa resta fuori scope, elencato senza giri di parole**: bonifici/pagamenti via chat (esclusi di proposito, non per dimenticanza — vedi il system prompt del RouterAgent), storico transazioni e budgeting (richiederebbero un vero core banking dietro `BankApiClient`, che qui è un client HTTP verso un sistema che non esiste), multi-canale WhatsApp/SMS (richiede account business reali che non ho). Elenco completo con motivazioni in ARCHITECTURE.md.

## Struttura

```
src/bank_rag/
  domain/            entità pure, nessuna dipendenza esterna
  application/
    ports/            interfacce (Protocol) verso ogni sistema esterno
    use_cases/         AnswerQuestion, IngestDocument, ManageNoIndexRules
  agents/              RouterAgent + ToolRegistry + Tools (il layer "agentic")
  infrastructure/      adapter concreti: Qdrant, OpenSearch, OpenAI, Redis, SQL, core-banking
  ingestion/           pipeline + segmentatori per formato (segmentation/)
  interface/
    api/               FastAPI: routers sottili, nessuna logica di business
    web/               le due UI statiche (admin/, widget/)
  observability/       tracing OpenTelemetry + eval offline RAGAS
  config/              Settings (pydantic-settings, da env/.env)
  di_container.py       unico punto che collega port -> adapter
```
