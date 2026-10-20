.DEFAULT_GOAL := help
.PHONY: help setup db backend ui dev mock stop reset test full

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'

setup: ## Create .env and install deps (safe to re-run; `dev` does this for you)
	@test -f .env || (cp .env.example .env && echo "Created .env: add your ANTHROPIC_API_KEY (or set LLM_MODE=mock)")
	cd backend && uv sync
	cd frontend && npm install

db: ## Start Postgres in Docker
	docker compose up -d --wait db

backend: db ## Run the backend on :8000 (starts Postgres first)
	cd backend && uv run uvicorn app.main:app --reload

ui: ## Run the web UI on :5173
	cd frontend && npm run dev

dev: setup db ## Set up (if needed) and run everything; Ctrl+C stops the app
	@$(MAKE) -j2 --no-print-directory backend ui

mock: setup db ## Like `make dev` but with canned dialogue, no API calls
	@LLM_MODE=mock $(MAKE) -j2 --no-print-directory backend ui

stop: ## Stop Postgres (data is kept)
	docker compose down

reset: ## Wipe containers and data, then run `make dev` for a fresh brewery
	docker compose --profile full down -v
	@$(MAKE) --no-print-directory dev

test: ## Run backend unit tests
	cd backend && uv run pytest -q

full: ## Run everything in containers instead of locally
	docker compose --profile full up --build
