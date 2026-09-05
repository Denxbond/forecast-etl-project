.DEFAULT_GOAL := help

PYTHON ?= python3
VENV_DIR ?= .venv

.PHONY: help bootstrap check check-config inspect-fixture check-python

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
