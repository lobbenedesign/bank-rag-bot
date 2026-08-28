## Data governance sul vector DB, chunking bancario, Maker-Checker sui numeri (2026-08-28)

Confronto puntuale tra una risposta da colloquio (struttura in 3 pilastri:
ingestion / orchestrazione agentica / guardrail, più due follow-up su
governance dei metadati vettoriali e chunking di documenti legali) e questo
codice, file per file. La maggior parte dei suggerimenti risultava già
implementata (RBAC sui vettori, pre-filtering server-side, grounding
rigoroso, cache, memoria multi-turno) — quello che segue è la parte
genuinamente nuova, aggiunta in questa sessione.

**Bug reale trovato e corretto, non dal confronto ma installando per
davvero la dipendenza pinnata**: `qdrant_store.py` chiamava
`AsyncQdrantClient.search()`, rimosso da qdrant-client in una versione
compresa nel pin `>=1.10` di questo progetto (`pip install qdrant-client`
risolve oggi alla 1.19.0, dove `.search()` non esiste più). Nessun test di
questo repo importava mai il pacchetto reale (tutti mockano
`QdrantVectorStore`), quindi solo installare davvero la dipendenza e
ispezionarla ha fatto emergere il problema. Migrato a `.query_points()`.

**Isolamento pubblico/interno — verificato, non solo dichiarato**: il
pre-filtering server-side su `audience` (mai un `if` post-retrieval) era
già corretto architetturalmente; qui è stato per la prima volta verificato
con un test reale contro il backend `:memory:` di qdrant-client stesso
(non un mock) — vedi `tests/unit/test_qdrant_vector_store.py`. Una singola
collection con metadati (non collection separate per pubblico/interno) è
la scelta giusta per questo caso d'uso: non ci sono dati HR o di dominio
completamente estraneo da isolare fisicamente, solo FAQ pubbliche vs
documenti interni sullo stesso dominio prodotto.

**Scadenza tassi/offerte (`DocumentMetadata.valid_until`)**: un chunk con
scadenza passata è escluso server-side dalla query, sia su Qdrant
(`QdrantVectorStore`) sia su OpenSearch (`OpenSearchKeywordIndex` — la
fusione ibrida RRF significa che un'esclusione solo lato vettoriale non
basta, un match lessicale sull'altro indice potrebbe comunque far passare
un tasso scaduto). Design note: niente `is_null`/`exists` per "nessuna
scadenza impostata" — trovato per davvero, testando contro il backend
`:memory:`, che `FieldCondition(is_null=True)` in qdrant-client non
matchava nemmeno i punti con quel campo genuinamente assente dal payload.
Invece di un filtro dimostrato inaffidabile, ogni chunk porta sempre un
`valid_until_ts` concreto (un sentinel "anno 9999" quando non scade mai),
così la query è sempre una singola condizione di range, su entrambi gli
indici.

**Soglia di similarità sul retrieval** (`retrieval_score_threshold`,
default disattivata): un candidato sotto soglia non arriva nemmeno al
reranker — il reranker sceglie il meno peggio tra i candidati che riceve,
non riconosce "nessuno di questi è davvero pertinente".

**Context prepending nei chunk**: ogni chunk viene prefissato con
`[Documento: {titolo} | {sezione}]` prima di essere vettorializzato — un
fatto isolato ("la commissione è dell'1%") perde il soggetto una volta
estratto dal documento sorgente; l'embedding stesso ora porta l'identità
documento/sezione, non solo la frase.

**Tabelle PDF → Markdown reale, non prosa appiattita**: `pdf_segmenter.py`
ora rileva le tabelle (`pdfplumber.find_tables()`, righe/bordi reali, non
euristica) e le emette come chunk Markdown a sé stanti — un LLM legge una
tabella Markdown correttamente, mentre l'euristica a paragrafi esistente
appiattiva righe/colonne in prosa illeggibile ("Durata Tasso Fisso Tasso
Variabile 20 anni 3.25% 2.90%..."), perdendo l'allineamento tra durata e
tasso — esattamente il tipo di documento più comune in banca. Le righe di
testo dentro il riquadro di una tabella rilevata sono escluse dal
raggruppamento a paragrafi, per non duplicare/corrompere il contenuto.
Limite dichiarato: serve una griglia visibile nel PDF (bordi disegnati);
una tabella allineata solo con spazi non viene rilevata e passa come prima
per il percorso a paragrafi. Verificato con un PDF reale generato da
fpdf2 con bordi (non un fixture sintetico dei soli byte).

**Maker-Checker sui numeri (`NumericGroundingGuardrail`)**: il flag
`grounded` esistente prova solo che un tool ha fornito *qualche* base alla
risposta, non che il numero specifico scritto dal modello coincida con
quello nella fonte — un modello può leggere male "3,5%" come "3,05%"
credendo comunque di star citando fedelmente. Un secondo passaggio LLM,
a scopo ristretto (confronta cifre, non scrive prosa), verifica che ogni
numero nella risposta compaia identico nelle citazioni prima che la
risposta sia trattata come affidabile a valle. Fail-*chiuso*, stessa
logica di `SentimentEscalationGuardrail`. Costo dichiarato esplicitamente:
scatta solo se il testo contiene qualcosa di numerico (percentuali,
importi, TAN/TAEG) — la maggior parte dei turni non paga la chiamata
extra.

Limite onesto, non nascosto: se un tool ha già "groundato" un'iterazione
precedente dello stesso turno, `RouterAgent` rivela il testo dal vivo
token per token (`can_reveal_live`, comportamento deliberato e già
testato in `test_streaming_reveals_content_live_once_search_has_grounded_the_turn`).
Bloccare anche quella rivelazione live avrebbe richiesto bufferizzare
l'intera risposta finale prima di mostrare un solo carattere, in
contraddizione con quel test. Non toccato. Quello che questo guardrail
garantisce comunque: un numero non verificato non è mai il testo che
resta a schermo (il client sovrascrive sempre col testo dell'evento
`done` finale — vedi `chat-ui.js`), non viene mai messo in cache per
altri clienti anonimi, e non viene mai registrato nell'audit trail come
se fosse affidabile.

Verificato con: 94 unit test (78 preesistenti + 16 nuovi, tutti passano),
inclusi 5 test reali contro il backend `:memory:` di qdrant-client (non
mock) e un test PDF con tabella reale generata da fpdf2. `ruff check` pulito.
`mypy` non eseguibile in modo pulito in questo ambiente (fallisce su
`py.typed` mancante su tutto il progetto, preesistente, non causato da
queste modifiche) — non risolto in questa sessione, dichiarato invece di
ignorato in silenzio.

## Streaming, localizzatore filiali, voce — le 3 migliorie "vere" senza compromessi

Delle migliorie identificate nel confronto con i chatbot bancari reali, queste tre sono state implementate senza alcun mock: funzionano davvero, non solo architetturalmente.

**Streaming (SSE)**. `RouterAgent.handle_streaming()` è diventata l'unica implementazione reale — `handle()` (non-streaming) ora la drena e restituisce solo l'ultima risposta. Stessa cosa per `AnswerQuestion.execute_streaming()`/`execute()`. Scelta deliberata, non ottimizzazione: due implementazioni parallele sarebbero due posti in cui il guardrail di grounding, il corto-circuito di conferma, o il fallback per max-iterazioni potrebbero divergere silenziosamente. Un'unica implementazione garantisce che streaming e non-streaming si comportino sempre allo stesso modo.

Il punto delicato: il contenuto può essere rivelato in diretta al cliente **solo dopo che un tool ha già "grounded" il turno** (`used_tool=True`). Prima di quel momento il modello potrebbe rispondere senza chiamare alcun tool, e il guardrail esistente sostituisce quella risposta con `FALLBACK_TEXT` — se il testo fosse già stato mostrato token per token, la sostituzione arriverebbe troppo tardi. Verificato con due test dedicati (uno prova che zero testo grezzo raggiunge il cliente nel caso ungrounded, l'altro che lo streaming è realmente incrementale nel caso grounded).

**Bug reale trovato aggiungendo il localizzatore filiali**: la logica di grounding controllava `tool.name == "search_knowledge_base"` specificamente — quindi una risposta legittimamente basata su `get_account_balance` o sul nuovo `find_branches` veniva **scartata e sostituita da FALLBACK_TEXT**, nonostante fosse corretta. Bug preesistente, esposto solo aggiungendo un secondo tool non-search. Corretto generalizzando a "qualunque tool eseguito con successo garantisce il turno", con test di regressione dedicato.

**Localizzatore filiali**: `BranchLocatorTool` + `StaticBranchDirectory`, dati reali in `branches.json` (seed di esempio, sostituibile con l'elenco vero della banca) — nessun mock, se la banca fornisce coordinate/indirizzi reali il tool risponde correttamente per davvero.

**Voce (lato browser)**: `VoiceController` avvolge le Web Speech API native (`SpeechRecognition`/`SpeechSynthesis`) — zero dipendenze nuove, zero backend coinvolto. Feature-detected: microfono e toggle "leggi ad alta voce" restano nascosti se il browser non le supporta (Safari/Firefox hanno supporto parziale). L'input vocale riempie il campo di testo invece di inviare automaticamente — scelta di sicurezza: un misriconoscimento vocale non deve mai innescare un'azione (es. una conferma di blocco carta) senza che il cliente riveda il testo.

Suite completa: **78/78 test passano.**

## Smoke test end-to-end reale (server vero avviato, non solo unit test)

Prima di questo punto, ogni verifica in questo progetto era `py_compile` (sintassi), unit test con fake (`ToolRegistry([])`, client fittizi), o file statici serviti senza backend. Qui invece: `uvicorn` avviato per davvero, con l'app FastAPI reale, senza Qdrant/OpenSearch/Postgres/Redis in esecuzione (disco della macchina troppo pieno per Docker — vedi nota sotto), per vedere fin dove il sistema regge senza infrastruttura.

**Bug reale trovato e corretto**: `pyproject.toml` dichiarava `opensearch-py>=2.6`, ma `AsyncOpenSearch` non è nemmeno importabile da quel pacchetto senza l'extra `[async]` (che porta `aiohttp`) — senza quell'extra, l'intera app falliva all'avvio con `ImportError`. Corretto in `opensearch-py[async]>=2.6`. Un bug di dipendenze non catturabile da `py_compile` né dagli unit test (che mockano `OpenSearchKeywordIndex`, non lo importano mai per davvero) — solo un vero avvio lo trova.

**Cosa ho verificato per davvero, con richieste HTTP reali**:
- `create_app()` costruisce senza errori (tutti e 4 i router, entrambi i mount statici, `/health`).
- `GET /health` → 200 reale.
- `GET /admin-ui/`, `GET /widget/` → 200 reali, serviti dallo stesso processo FastAPI.
- `GET /admin/noindex` senza token → 403 reale (gate `is_employee` funziona).
- `GET /admin/documents` con un JWT vero (firmato con `PyJWT`, stesso secret dell'app) → autenticazione **superata**, la richiesta arriva fino al tentativo di connessione a Postgres, che fallisce con `ConnectionRefusedError` (Postgres non è in esecuzione) — non un errore di codice.
- `POST /chat` → stesso pattern: la richiesta arriva fino al rate limiter, che tenta la connessione a Redis e fallisce con `ConnectionRefusedError` — non un errore di codice.

In altre parole: **tutto il wiring — routing, dependency injection, autenticazione JWT, autorizzazione, rate limiting — è stato verificato con richieste HTTP reali**, non solo ragionato. L'unica cosa non verificata è il comportamento quando Qdrant/OpenSearch/Postgres/Redis rispondono davvero (serve Docker, che il disco pieno della macchina non permette in questo momento) e la generazione di una risposta LLM reale (serve una chiave OpenAI vera e valida, non usata qui).

Per l'avvio ho dovuto anche creare uno stub temporaneo, **non incluso nel repository**, per `sentence_transformers` (pacchetto che porta `torch`, troppo pesante per lo spazio disco disponibile) — il reranker cross-encoder non è stato quindi eseguito per davvero in questo test, solo importato come stub che solleva `NotImplementedError` se chiamato. Dichiarato esplicitamente, non nascosto.

## Confronto con progetti/bot bancari reali (ricerca esterna)

Ricerca su GitHub (progetti simili: [mlrun/demo-banking-agent](https://github.com/mlrun/demo-banking-agent), [frogcoder/llm-chatbot](https://github.com/frogcoder/llm-chatbot), [RasaHQ/financial-demo](https://github.com/RasaHQ/financial-demo)) e su chatbot bancari reali in produzione (Erica-BofA, Eno-Capital One, Ceba-Commonwealth Bank, NOMI-RBC). Nessuno di questi supera la nostra architettura sul lato hexagonal/testing; due gap concreti trovati e colmati:

| Gap trovato | Fonte | Come l'ho colmato |
|---|---|---|
| Nessun guardrail *strutturale* di topic-scope (solo istruzione nel system prompt) | mlrun/demo-banking-agent usa una classificazione dedicata "è una domanda bancaria?" prima di procedere | [topic_guardrail.py](src/bank_rag/agents/topic_guardrail.py): check separato, fail-open, eseguito prima del loop tool-calling in `AnswerQuestion.execute` |
| Nessuna feature di sicurezza immediata via chat | Blocco carta è la feature più citata in assoluto nei bot reali (Eno, Ceba, Erica) — "un cliente che blocca la carta in 15 secondi è più protetto di uno in attesa al telefono" | [lock_card_tool.py](src/bank_rag/agents/tools/lock_card_tool.py), stesso pattern di `AccountBalanceTool`; system prompt aggiornato con eccezione esplicita (azione di sicurezza, non transazione finanziaria) |

**Aggiornamento — escalation "emotion-aware" ora implementata**: [sentiment_escalation_guardrail.py](src/bank_rag/agents/sentiment_escalation_guardrail.py), stesso pattern del `TopicGuardrail` ma con fail-mode opposto e deliberato — `TopicGuardrail` fallisce *aperto* (in dubbio, lascia passare: bloccare per errore una domanda bancaria legittima è il costo peggiore), `SentimentEscalationGuardrail` fallisce *chiuso* (in dubbio, esclude subito: perdere un cliente davvero in difficoltà è il costo peggiore). Scope volutamente stretto: intercetta frustrazione/rabbia/richiesta esplicita di un operatore, non "urgenza" in generale — "la mia carta è stata rubata, bloccala" deve comunque raggiungere il tool `lock_card`, non l'escalation immediata.

Conferma positiva dalla ricerca: le fonti enterprise (Backbase) dicono esplicitamente che "i migliori chatbot bancari nel 2026 separano il layer di conversazione (LLM) dal layer di esecuzione (logica deterministica con audit trail completo)" — è esattamente il pattern `Tool`/`BankApiClient` già presente in questo progetto prima di questa ricerca, non una scoperta che ha richiesto modifiche architetturali.

## Ricerca UX/frontend (secondo giro) — cosa colmato, cosa dichiarato fuori scope

Ricerca su UX best practice 2026 per chatbot conversazionali e specificamente bancari, più linee guida WCAG per widget chat. Trovato: il 71% dell'abbandono di prodotti AI è causato da problemi di interfaccia, non dal modello — le quattro proprietà che contano: trasparenza sulle capacità, gestione degli errori, segnalazione dell'incertezza, accessibilità.

| Gap trovato | Fonte | Come l'ho colmato |
|---|---|---|
| Target di tocco sotto soglia WCAG 2.5.8 (pulsante invio 36×36px) | Standard 44×44px minimo | [widget.css](src/bank_rag/interface/web/widget/widget.css): pulsanti invio/chiudi portati a 44×44px, verificato via `getBoundingClientRect()` nel browser |
| Nessuna "capability transparency" — l'utente non sa cosa il bot sa fare finché non chiede | Quick-reply/domande suggerite riducono il carico cognitivo | [chat-ui.js](src/bank_rag/interface/web/widget/chat-ui.js): 3 domande suggerite dopo il saluto, cliccabili |
| Citazioni come testo piatto, non ispezionabili | Pattern 2026: source badge cliccabili/espandibili | `_renderCitations()` in chat-ui.js: chip cliccabile per fonte, espande lo snippet on-click |
| Nessun supporto dark mode / `prefers-reduced-motion` | Linee guida accessibilità 2026 | `@media (prefers-color-scheme: dark)` su entrambe le UI (widget e admin); l'indicatore di digitazione animato rispetta `prefers-reduced-motion` |
| Nessuna chiusura da tastiera (Escape) | WCAG operabilità da tastiera | Aggiunto, **con un bug trovato e corretto durante la verifica**: il listener era agganciato al pannello, ma dopo il click su un chip il focus va al `body` — l'evento non risaliva mai. Spostato il listener su `document`, riverificato nel browser (chiusura + ritorno del focus alla bolla confermati). |

**Aggiornamento — conferma esplicita prima di `lock_card` ora implementata**: non un alert lato client, ma uno stato reale nel dominio.

- `Conversation.pending_action: PendingAction | None` — quando l'LLM chiama un tool con `requires_confirmation = True` (oggi solo `lock_card`), `RouterAgent` **non esegue mai `.run()`**: interrompe il loop, restituisce un `Answer` con `pending_action` valorizzato e un testo che chiede conferma.
- `AnswerQuestion.execute()` controlla `conversation.pending_action` **prima di qualunque altro guardrail** (topic-scope, sentiment) — se il messaggio successivo del cliente è la risposta a una proposta in sospeso, non deve rischiare di essere scartato come "fuori tema" solo perché è un breve "sì".
- Un nuovo `ConfirmationGuardrail` (stesso pattern degli altri due, fail-*chiuso* come `SentimentEscalationGuardrail`: ambiguo → non confermato) decide se il messaggio è una conferma esplicita. Solo allora il tool viene eseguito per davvero.

**Un bug reale trovato mentre veniva collegato, non dal codice del flusso stesso**: `RedisConversationRepository._serialize`/`_deserialize` non includevano affatto `pending_action`. Nei unit test, dove la stessa istanza `Conversation` sopravvive in memoria tra due chiamate a `execute()`, il flusso funzionava perfettamente — ma in una vera richiesta HTTP, ogni richiesta deserializza una `Conversation` **nuova** da Redis: lo stato "azione in sospeso" sarebbe sparito silenziosamente tra la proposta e la conferma, rompendo il meccanismo proprio nell'unico scenario che conta (l'uso reale, non il test). Corretto, e aggiunto un test round-trip dedicato ([test_redis_conversation_repository.py](tests/unit/test_redis_conversation_repository.py)) proprio per questa classe di bug — non catturabile da un fake in memoria, solo esercitando la serializzazione vera.

**Ancora non implementato, dichiarato esplicitamente**:
- **Streaming token-by-token** — pattern 2026 standard (SSE, non richiede websocket), ma tocca sia il backend (porta `LLMClient`, adapter OpenAI, endpoint `/chat`) sia il frontend. Prossimo passo prioritario rimasto.
- Il testo di conferma (`_build_confirmation_text` in `orchestrator.py`) è generico per qualunque tool con `requires_confirmation`, non specializzato per `lock_card` — funziona ma non è raffinato linguisticamente; con più tool a rischio in futuro varrebbe la pena renderlo per-tool.

# Architettura

Hexagonal / clean architecture: il dominio e i casi d'uso non conoscono
FastAPI, OpenAI, Qdrant o Postgres. Ogni dipendenza esterna è dietro un
`Protocol` in `application/ports/`, implementato da un adapter in
`infrastructure/`. Un solo file, `di_container.py`, collega le due cose.

```
interface/        -> HTTP/FastAPI, non contiene logica di business
  api/
    routers/       endpoint sottili: parse request -> use case -> response
agents/            -> il layer "agentic": Router Agent + Tool Registry + Tools
application/
  use_cases/       -> AnswerQuestion, IngestDocument (entry point indipendenti dal trasporto)
  ports/           -> Protocol: VectorStore, KeywordIndex, Reranker, LLMClient, Cache, ...
domain/            -> entità pure (Chunk, Conversation, Answer, Intent...)
infrastructure/    -> adapter concreti (Qdrant, OpenSearch, OpenAI, Redis, SQL, core-banking)
ingestion/         -> pipeline separata dal request path: scraper + file loader + chunker
observability/     -> tracing OpenTelemetry + eval RAGAS offline
```

Regola di dipendenza: le frecce puntano sempre verso l'interno.
`infrastructure` implementa i port di `application`; `application` non
importa mai `infrastructure`. Questo è ciò che rende `agents/orchestrator.py`
testabile con un `FakeLLMClient` in 20 righe, senza mock di rete
(vedi `tests/unit/test_router_agent.py`).

## Perché queste scelte (rispetto a una risposta "da colloquio" generica)

| Decisione | Motivazione |
|---|---|
| Hybrid retrieval (vector + BM25, fusi con RRF) | Il vector-only fallisce su termini esatti (codici prodotto, "TAEG", IBAN) tipici di documenti bancari. |
| Reranker cross-encoder dopo il retrieval | Il retrieval iniziale è cheap ma impreciso; il rerank su un pool piccolo è ciò che davvero alza la qualità del grounding. |
| RouterAgent con loop ReAct limitato (`max_iterations`) | Vero comportamento "agentic": il modello decide se/quanti tool chiamare (es. due ricerche per un confronto tra prodotti), non una pipeline fissa retrieve->generate. |
| Grounding check esplicito (`grounded` flag, fallback a operatore umano) | Un system prompt da solo non basta a impedire allucinazioni: se il modello non ha usato un tool, la risposta non viene mai spacciata per fattuale. |
| Tool Registry filtrato per autenticazione | Un tool con side-effect (saldo conto) non esiste nemmeno nello schema OpenAI passato al modello se la conversazione non è autenticata — l'accesso è strutturale, non affidato al prompt. |
| Audience come filtro server-side nel vector/keyword store | Un chunk `INTERNAL` non lascia mai il database per una richiesta pubblica, indipendentemente da bug applicativi a valle. |
| Versioning documenti (`DocumentRepository` + purge su re-ingestion) | Evita che una nuova versione di un foglio informativo conviva nell'indice con la versione superata, producendo risposte contraddittorie. |
| Cache solo per risposte grounded e non autenticate | Le FAQ pubbliche ripetitive risparmiano LLM+retrieval; le risposte legate a un cliente specifico non vengono mai cacheate/condivise. |
| PII filter prima dell'LLM | Nessun dato sensibile del cliente lascia il perimetro verso un provider LLM esterno. |
| Eval offline con RAGAS (`observability/eval/ragas_eval.py`) | Un sistema agentico è non deterministico: senza un dataset golden e metriche (faithfulness, answer relevancy, context precision) non c'è modo oggettivo di sapere se una modifica ha peggiorato le risposte. |
| Ingestion come servizio separato (`ingestion-worker`) | La latenza di indicizzazione non deve mai bloccare o rallentare il path di risposta in chat. |

## Colmati (verificati con test, non solo dichiarati)

| Gap | Come è stato risolto | Dove |
|---|---|---|
| Auth placeholder | Verifica JWT reale (HS256, claim `sub`/`role`/`exp` obbligatori), 401 su token invalido/scaduto/firmato con secret sbagliato | [jwt_auth.py](src/bank_rag/infrastructure/security/jwt_auth.py), 6 test in `test_jwt_auth.py` |
| Nessun rate limiting | `RateLimiter` port + adapter Redis a finestra fissa, applicato via dependency FastAPI su `/chat` e `/admin/documents` con soglie separate | [redis_rate_limiter.py](src/bank_rag/infrastructure/security/redis_rate_limiter.py), `dependencies.py::rate_limit` |
| Prompt injection nei documenti | Sanitizer regex applicato in ingestion *prima* del chunking (rimuove pattern noti prima che entrino nell'indice) + regola esplicita nel system prompt del router ("tool output è dato, non istruzione") | [prompt_injection_sanitizer.py](src/bank_rag/infrastructure/security/prompt_injection_sanitizer.py), 4 test |
| Nessuna migrazione Postgres | Alembic configurato, migrazione iniziale per `document_metadata` con indice su `audience` | `alembic/versions/0001_initial.py` |
| Conversazioni in-memory | `ConversationRepository` port + adapter Redis con TTL, sostituisce il dict in `chat.py` | [redis_conversation_repository.py](src/bank_rag/infrastructure/persistence/redis_conversation_repository.py) |
| Nessuna CI | Workflow GitHub Actions: `ruff` + `pytest tests/unit` su ogni push/PR; job `rag-eval` separato che gira RAGAS solo se cambia `agents/` o `ingestion/chunking/` | [.github/workflows/ci.yml](.github/workflows/ci.yml) |

Totale test unitari: **18/18 passano** (eseguiti localmente, non solo scritti) — inclusi i 6 sul JWT e i 4 sul sanitizer aggiunti in questo giro.

## Audit trail, query rewriting, no-index (aggiunti dopo)

| Funzionalità | Design | Dove |
|---|---|---|
| Audit trail immutabile | `AuditLog` port espone solo `record` (nessun update/delete nel codice); l'adapter SQL aggiunge `REVOKE UPDATE, DELETE` sul ruolo applicativo nella migrazione — append-only anche a livello DB, non solo per disciplina applicativa. Ogni scambio in `AnswerQuestion.execute` viene registrato: domanda, domanda risolta, documenti recuperati, risposta, intent, grounded. | [sql_audit_log.py](src/bank_rag/infrastructure/persistence/sql_audit_log.py), [0002_audit_and_noindex.py](alembic/versions/0002_audit_and_noindex.py) |
| Query rewriting multi-turno | `QueryRewriter` risolve un follow-up ("e il bonifico?") in domanda standalone usando la history, **prima** che l'LLM veda l'ultimo turno — sovrascrive solo ciò che il modello riceve come contesto, non la trascrizione mostrata al cliente. Skip esplicito della chiamata LLM quando non c'è history (nessun costo extra sul primo messaggio). | [llm_query_rewriter.py](src/bank_rag/infrastructure/llm/llm_query_rewriter.py), `RouterAgent.handle(..., resolved_question=...)` |
| No-index / esclusione da ingestion | `NoIndexRule` (pattern glob su URL o source_id) via `ManageNoIndexRules`: aggiungere una regola **purga immediatamente** i contenuti già indicizzati che matchano (non solo blocca ingestion futura). `IngestDocument` rifiuta un source_id escluso con `DocumentExcludedError`. | [manage_noindex_rules.py](src/bank_rag/application/use_cases/manage_noindex_rules.py), endpoint `POST/DELETE/GET /admin/noindex` |

## No-index granulare: pagina/sezione/riga, per ogni formato

Estensione del no-index per escludere una **porzione** di un documento (non solo il documento intero), su tutti i formati richiesti: PDF, DOCX, MD, TXT, CSV, Excel, JSON, XML, e pagine HTML del sito.

| Formato | Unità indirizzabile (`ChunkLocator`) | Segmentatore |
|---|---|---|
| PDF | pagina:paragrafo (`kind="page_paragraph"`, es. `"7:3"`) | [pdf_segmenter.py](src/bank_rag/ingestion/segmentation/pdf_segmenter.py) (via `pdfplumber`, non `PyMuPDF` — vedi nota licenza sotto) |
| DOCX | sezione per heading, breadcrumb (`"Conti > Conto Base"`) | [docx_segmenter.py](src/bank_rag/ingestion/segmentation/docx_segmenter.py) |
| Markdown | sezione per heading `#`/`##`/... | [markdown_segmenter.py](src/bank_rag/ingestion/segmentation/markdown_segmenter.py) |
| TXT / MD senza heading | range di righe fisso | stesso file, `segment_plain_text` |
| CSV | range di righe (con header ripetuto come contesto) | [csv_segmenter.py](src/bank_rag/ingestion/segmentation/csv_segmenter.py) |
| Excel (xlsx/xlsm) | `Foglio!range-righe` | [xlsx_segmenter.py](src/bank_rag/ingestion/segmentation/xlsx_segmenter.py) |
| JSON | chiave top-level o indice elemento (`$.chiave`, `$[2]`) | [json_segmenter.py](src/bank_rag/ingestion/segmentation/json_segmenter.py) |
| XML | elemento figlio della root, XPath-like (`/root/item[3]`) | [xml_segmenter.py](src/bank_rag/ingestion/segmentation/xml_segmenter.py) (via `defusedxml`, non lo stdlib — protezione da XXE/entity-expansion) |
| Pagine HTML del sito | sezione per heading `h1`-`h3` | [html_segmenter.py](src/bank_rag/ingestion/segmentation/html_segmenter.py) |

**Come funziona end-to-end**: `FileLoader`/`WebScraper` producono `list[DocumentSegment]` invece di testo piatto; `IngestDocument` scarta i segmenti il cui locator matcha una regola no-index attiva **prima** del chunking (il resto del documento viene comunque indicizzato); `ManageNoIndexRules.exclude(..., locator_kind=, locator_pattern=)` aggiunge la regola e purga **solo** i chunk già indicizzati che matchano (`VectorStore.delete_by_locator`/`KeywordIndex.delete_by_locator`), non l'intero documento.

Esempio reale (dal caso discusso): escludere solo la sezione "Cookie di terze parti" di `https://www.example-bank.it/privacy`, lasciando indicizzato il resto della pagina:
```json
POST /admin/noindex
{"pattern": "https://www.example-bank.it/privacy", "rule_type": "url",
 "reason": "sezione cookie obsoleta", "locator_kind": "section", "locator_pattern": "*Cookie*"}
```

**Aggiornamento — PDF ora a granularità paragrafo**: sostituito `pypdf` con `pdfplumber` in [pdf_segmenter.py](src/bank_rag/ingestion/segmentation/pdf_segmenter.py). `pdfplumber` espone le coordinate di ogni riga (bounding box), il che permette di rilevare un'interruzione di paragrafo come un gap verticale anomalo tra righe consecutive (soglia: `1.6x` l'altezza mediana delle righe della pagina) — la stessa euristica che userebbe un umano scorrendo la pagina. Locator ora `"pagina:paragrafo"` (es. `"7:3"`), non solo `"7"`.

**Nota sulla licenza, non solo tecnica**: `PyMuPDF` (fitz) avrebbe dato risultati probabilmente più accurati su layout complessi, ma è **AGPL-3.0** (o richiede licenza commerciale a pagamento da Artifex per uso closed-source) — inaccettabile da incorporare nel backend proprietario di una banca senza aprire il codice o pagare una licenza. `pdfplumber` (MIT, basato su `pdfminer.six`) non ha questo vincolo. È una decisione di compliance legale, non solo di qualità dell'estrazione, e va documentata quanto un controllo di sicurezza.

**Test PDF ora reale, non più dichiarato assente**: `fpdf2` (MIT) aggiunto come dipendenza **solo di test** (`[project.optional-dependencies].dev`, mai importata da codice applicativo) per generare un PDF vero con paragrafi e pagine noti, e verificare che `segment_pdf` rilevi correttamente sia i confini di pagina sia quelli di paragrafo.

Segmentazione HTML basata su sibling piatti dell'heading, non traversal ricorsivo del sottoalbero — corretta su markup semplice, non garantita su layout con wrapper annidati (limite ancora aperto, non toccato in questo giro).

Totale test unitari ora: **44/44 passano**, eseguiti localmente — inclusi round-trip reali per DOCX (`python-docx`), XLSX (`openpyxl`) e ora anche PDF (`fpdf2`), tutti costruiti in memoria, non mock.

## Cosa resta comunque fuori scope (onestà residua)

- JWT HS256 con secret condiviso: sufficiente per un solo servizio backend; con più servizi che devono verificare token indipendentemente, va sostituito con RS256 + JWKS dell'IdP (il punto di estensione è lo stesso `decode_token`, la firma non cambia).
- Rate limiting a finestra fissa, non sliding window/token bucket: più semplice, sufficiente contro l'abuso grossolano, non perfettamente equo al bordo della finestra.
- Il sanitizer anti prompt-injection è basato su regex: blocca i pattern noti e a basso sforzo, non un attacco elaborato — è difesa in profondità, non l'unica linea di difesa (si somma alla regola esplicita nel system prompt).
- L'eval RAGAS in CI richiede `OPENAI_API_KEY` come secret di repository: senza quello il job passa comunque (skip esplicito, non un falso verde silenzioso).
