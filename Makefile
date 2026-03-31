.PHONY: help build install uninstall test pub clean lint

# Configuration
PYTHON = python3
PIP = $(PYTHON) -m pip
BUILD = $(PYTHON) -m build
TWINE = $(PYTHON) -m twine
PYTEST = $(PYTHON) -m pytest

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: clean ## Build the package (sdist and wheel)
	$(PIP) install --upgrade build
	$(BUILD)

install: ## Install the package locally
	$(PIP) install .

install-e: ## Install the package in editable mode for development
	$(PIP) install -e .

uninstall: ## Uninstall the package
	$(PIP) uninstall -y pgslim

test: ## Run unit tests
	$(PIP) install pytest
	$(PYTEST) tests

lint: ## Check code for style and errors
	$(PIP) install flake8
	$(PYTHON) -m flake8 pgslim

pub: build ## Build and upload the package to PyPI
	$(PIP) install --upgrade twine
	$(TWINE) upload dist/*

clean: ## Remove build artifacts and temporary files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
