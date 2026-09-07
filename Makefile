.DEFAULT_GOAL := help

PYTHON ?= python3
VENV_DIR ?= .venv
DBT_PYTHON ?= python3.12
DBT_VENV_DIR ?= .venv-dbt

.PHONY: install-dbt
.PHONY: dbt-build
dbt-build: ## Build all dbt models and run their data tests
	$(VENV_DIR)/bin/python scripts/run_dbt.py build

.PHONY: dbt-debug
.PHONY: dbt-sources
dbt-sources: ## List declared dbt source tables without querying PostgreSQL
	$(VENV_DIR)/bin/python scripts/run_dbt.py ls --resource-type source --output name

dbt-debug: ## Verify the local dbt project and PostgreSQL connection
	$(VENV_DIR)/bin/python scripts/run_dbt.py debug

install-dbt: ## Create the separate dbt environment and install locked dependencies
	$(DBT_PYTHON) -m venv $(DBT_VENV_DIR)
	$(DBT_VENV_DIR)/bin/python -m pip install -r requirements-dbt.txt

.PHONY: help bootstrap check check-config inspect-fixture check-python db-init db-tables check-db install-warehouse check-load

help: ## Show available development commands
	@awk 'BEGIN {FS = ":.*## "; printf "Available commands:\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Create the Python virtual environment and local .env file
	$(PYTHON) -m venv $(VENV_DIR)
	@test -f .env || cp .env.example .env
	@printf '%s\n' "Bootstrap complete. Activate with: source $(VENV_DIR)/bin/activate"

check-config: ## Validate committed pipeline and city configuration
	$(PYTHON) scripts/validate_config.py

inspect-fixture: ## Summarize and validate the saved Kyiv API fixture
	$(PYTHON) scripts/inspect_fixture.py

check-python: ## Run offline Python tests
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests/unit -v

check: check-config inspect-fixture check-python ## Run all checks available at the current stage

db-init: ## Create ingestion schema and tables in the running warehouse
	docker compose exec -T warehouse sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < sql/init/001_ingestion_schema.sql

db-tables: ## List ingestion tables in the running warehouse
	docker compose exec -T warehouse sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "\dt raw.*"'

check-db: ## Verify forecast keys in PostgreSQL and roll back test rows
	docker compose exec -T warehouse sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < tests/integration/check_forecast_keys.sql

install-warehouse: ## Install locked warehouse dependencies into .venv
	$(VENV_DIR)/bin/python -m pip install -r requirements-warehouse.txt

check-load: ## Check transactional loading against PostgreSQL; roll back test data
	PYTHONPATH=src $(VENV_DIR)/bin/python -m unittest discover -s tests/integration -p 'test_load*.py' -v
