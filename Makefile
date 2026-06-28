# Developer workflow — everything runs through Docker. `make help` lists targets.
#
# Usage:
#   make up      — start the dev stack (API + database)
#   make seed    — load the catalogs into the database
#   make test    — run the test suite
#   make down    — stop the stack
#
# The command targets (fetch / seed / test / lint) exec into the running
# api container, so run `make up` first.

DEV := docker compose -f docker-compose.dev.yml
# Run a command inside the running api container (no host toolchain required).
EXEC_API := docker exec payback_api

.DEFAULT_GOAL := help
.PHONY: help up down logs fetch seed embed eval demo test lint

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Build and start the dev stack (API + database)
	$(DEV) up -d --build

down: ## Stop the dev stack and remove volumes
	$(DEV) down -v

logs: ## Tail the API logs
	$(DEV) logs -f api

fetch: ## Refresh the Open Food Facts catalog snapshot (needs network)
	$(EXEC_API) python -m data.fetch_off

seed: ## Load the committed catalog snapshots into the database
	$(EXEC_API) python -m data.seed

embed: ## Compute embeddings for products (run after seed; idempotent)
	$(EXEC_API) python -m data.embed

eval: ## A/B-evaluate the filter × ranker strategies (nDCG/Recall/MRR; run after embed)
	$(EXEC_API) python -m data.eval

demo: ## Run the 5-query demo against the live assistant (needs an LLM key; run after embed)
	$(EXEC_API) python /demo/run_demo.py

test: ## Run the test suite
	$(EXEC_API) python -m pytest

lint: ## Lint the codebase
	$(EXEC_API) ruff check .
