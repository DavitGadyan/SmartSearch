.DEFAULT_GOAL := help
SHELL := /bin/bash

PY := cd backend && PYTHONPATH=. uv run
WEB := cd frontend && npm

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------- infrastructure ----------
infra: ## Start Postgres (pgvector), Redis and MLflow in Docker
	docker compose up -d postgres redis mlflow

infra-down: ## Stop infrastructure containers
	docker compose down

up: ## Run the whole stack (infra + API + web) in Docker
	docker compose --profile app up --build

# ---------- install ----------
install: ## Install backend (uv) and frontend (npm) dependencies
	cd backend && uv sync
	$(WEB) install

# ---------- database ----------
migrate: ## Apply Alembic migrations
	$(PY) alembic upgrade head

revision: ## Autogenerate a migration: make revision m="message"
	$(PY) alembic revision --autogenerate -m "$(m)"

# ---------- data pipeline ----------
data: ## Download WANDS, build catalog, embed products
	$(PY) python scripts/download_wands.py
	$(PY) python scripts/build_catalog.py
	$(PY) python scripts/embed_catalog.py

retailrocket: ## Download + evaluate on Retailrocket (needs ~/.kaggle/kaggle.json)
	$(PY) python scripts/download_retailrocket.py
	$(PY) python scripts/eval_retailrocket.py

warmup: ## Warm-up simulation (days 0-6, control strategy) → behavioral features
	$(PY) python scripts/simulate.py --phase warmup --reset
	$(PY) python scripts/refresh_marts.py --only product_stats.sql

train: ## Train the LightGBM LambdaRank ranker and register it in MLflow
	$(PY) python scripts/train_ranker.py

experiments: ## Seed experiments and run the A/B simulation (days 7-27), then item-item similarity
	$(PY) python scripts/simulate.py --phase experiment --reset
	$(PY) python scripts/build_item_similarity.py

bandit: ## Train the contextual-bandit policy off-policy (IPS/SNIPS/DR report) and A/B test it in simulation days 28-34
	$(PY) python scripts/train_bandit.py
	$(PY) python scripts/simulate.py --phase bandit --reset

graph: ## Build the product knowledge graph (communities summarised with Claude when ANTHROPIC_API_KEY is set)
	$(PY) python scripts/build_graph.py

images: ## Generate product photos for the most-shown products with Higgsfield (HF_API_KEY_ID/SECRET; prompt-only without)
	$(PY) python scripts/generate_images.py $(ARGS)

photos: ## Representative photo for every product from the Amazon Berkeley Objects dataset (downloads ~3.3 GB once)
	$(PY) python scripts/fetch_product_photos.py $(ARGS)

decisions: ## Evaluate the relevance judge (Microsoft-Decision-1 or local fallback) against WANDS human grades
	$(PY) python scripts/eval_decision_judge.py

marts: ## Build / refresh analytics marts (materialized views)
	$(PY) python scripts/refresh_marts.py

eval: ## Offline ranking evaluation (NDCG/MRR/Recall) on held-out WANDS queries
	$(PY) python scripts/offline_eval.py

report: ## Export experiment report to docs/experiment-report.md
	$(PY) python scripts/export_report.py

setup: infra install migrate data warmup train experiments bandit graph marts eval decisions report ## Full bootstrap from a clean clone

# ---------- dev servers ----------
api: ## Run FastAPI with reload
	$(PY) uvicorn app.main:app --reload --port 8000

web: ## Run Next.js dev server
	$(WEB) run dev

# ---------- quality ----------
test: ## Backend tests
	$(PY) pytest -q

lint: ## Lint backend + frontend
	$(PY) ruff check . && $(PY) ruff format --check .
	$(WEB) run lint

.PHONY: help infra infra-down up install migrate revision data retailrocket warmup train experiments bandit graph decisions marts eval report setup api web test lint
