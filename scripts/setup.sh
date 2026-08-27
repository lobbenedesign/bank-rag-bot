#!/usr/bin/env bash
# Guided first-time setup: checks prerequisites, creates .env interactively,
# starts the infrastructure containers, waits for them to be healthy, then
# provisions the Qdrant collection. Idempotent — safe to re-run.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== 1/5: checking prerequisites =="
command -v docker >/dev/null 2>&1 || { echo "Docker non trovato. Installa Docker Desktop e riprova: https://docs.docker.com/get-docker/"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose non trovato (serve Docker Desktop >= 4.x, o il plugin 'docker compose')."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 non trovato. Installalo e riprova."; exit 1; }

echo "== 2/5: configurazione .env =="
if [ -f .env ]; then
  echo ".env già presente, non lo sovrascrivo."
else
  cp .env.example .env
  read -rp "OPENAI_API_KEY (sk-...): " openai_key
  read -rp "CORE_BANKING_BASE_URL [https://core-banking.internal]: " banking_url
  banking_url=${banking_url:-https://core-banking.internal}
  read -rp "CORE_BANKING_SERVICE_TOKEN [change-me]: " banking_token
  banking_token=${banking_token:-change-me}

  # portable in-place edit (works on both GNU and BSD/macOS sed)
  tmp_env="$(mktemp)"
  sed \
    -e "s#^OPENAI_API_KEY=.*#OPENAI_API_KEY=${openai_key}#" \
    -e "s#^CORE_BANKING_BASE_URL=.*#CORE_BANKING_BASE_URL=${banking_url}#" \
    -e "s#^CORE_BANKING_SERVICE_TOKEN=.*#CORE_BANKING_SERVICE_TOKEN=${banking_token}#" \
    .env > "$tmp_env"
  mv "$tmp_env" .env
  echo ".env creato."
fi

echo "== 3/5: avvio Qdrant, OpenSearch, Redis, Postgres =="
docker compose up -d qdrant opensearch redis postgres

echo "== 4/5: attesa che i servizi siano pronti =="
wait_for() {
  local name="$1" url="$2" tries=30
  until curl -sf "$url" >/dev/null 2>&1; do
    tries=$((tries - 1))
    if [ "$tries" -le 0 ]; then echo "Timeout attendendo $name ($url)"; exit 1; fi
    sleep 2
  done
  echo "$name pronto."
}
wait_for "Qdrant" "http://localhost:6333/readyz"
wait_for "OpenSearch" "http://localhost:9200"

echo "== 5/5: provisioning della collection Qdrant =="
python3 -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[dev]"
PYTHONPATH="$ROOT_DIR/src" python3 -m bank_rag.infrastructure.vector_stores.qdrant_bootstrap

echo ""
echo "Setup completato. Avvia l'API con:"
echo "  source .venv/bin/activate && uvicorn bank_rag.interface.api.main:app --reload"
