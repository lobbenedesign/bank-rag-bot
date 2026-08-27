.PHONY: setup up down test bootstrap run

setup:   ## Guided first-time setup: checks Docker, creates .env, starts services, provisions Qdrant
	./scripts/setup.sh

up:      ## Start infrastructure containers (Qdrant, OpenSearch, Redis, Postgres)
	docker compose up -d qdrant opensearch redis postgres

down:    ## Stop infrastructure containers
	docker compose down

bootstrap: ## (Re-)provision the Qdrant collection schema
	PYTHONPATH=src python3 -m bank_rag.infrastructure.vector_stores.qdrant_bootstrap

test:    ## Run the unit test suite (no external services required)
	PYTHONPATH=src pytest tests/unit -v

run:     ## Start the API with auto-reload
	uvicorn bank_rag.interface.api.main:app --reload --app-dir src
