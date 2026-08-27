# Bank RAG Bot

Chatbot agentico per il sito di una banca: risponde usando sia i contenuti
pubblici del sito sia documenti interni caricati dai dipendenti, con
guardrail di grounding e RBAC sui dati indicizzati.

Vedi [ARCHITECTURE.md](ARCHITECTURE.md) per il razionale delle scelte
architetturali e cosa manca ancora per la produzione.

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
