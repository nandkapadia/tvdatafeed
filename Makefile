.PHONY: help install install-dev test test-cov test-quick lint format clean build upload-test upload docs

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install package dependencies
	pip install -r requirements.txt

install-dev:  ## Install package with development dependencies
	pip install -r requirements.txt -r requirements-dev.txt
	pip install -e .

test:  ## Run all tests with coverage
	pytest -v --cov=tvDatafeed --cov-report=html --cov-report=term-missing

test-cov:  ## Run tests and open coverage report
	pytest -v --cov=tvDatafeed --cov-report=html
	@echo "Opening coverage report..."
	@python -m webbrowser htmlcov/index.html || open htmlcov/index.html || xdg-open htmlcov/index.html

test-quick:  ## Run tests without coverage (faster)
	pytest -v

test-file:  ## Run specific test file (use FILE=tests/test_main.py)
	pytest -v $(FILE)

test-debug:  ## Run tests with debug output
	pytest -vv -s

lint:  ## Run all linters
	@echo "Running black..."
	black --check tvDatafeed tests
	@echo "Running flake8..."
	flake8 tvDatafeed tests --max-line-length=100 --extend-ignore=E203,W503
	@echo "Running isort..."
	isort --check-only --profile black tvDatafeed tests
	@echo "Running mypy..."
	mypy tvDatafeed --ignore-missing-imports || true

format:  ## Format code with black and isort
	@echo "Formatting with black..."
	black tvDatafeed tests
	@echo "Sorting imports with isort..."
	isort --profile black tvDatafeed tests
	@echo "Done!"

clean:  ## Clean build artifacts and cache files
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Cleaned build artifacts"

build:  ## Build package for distribution
	python -m build
	@echo "Build complete! Artifacts in dist/"

upload-test:  ## Upload to TestPyPI
	@echo "Uploading to TestPyPI..."
	twine upload --repository testpypi dist/*

upload:  ## Upload to PyPI (production)
	@echo "⚠️  Uploading to PyPI (production)..."
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		twine upload dist/*; \
	fi

docs:  ## Generate documentation (if sphinx is installed)
	@if command -v sphinx-build >/dev/null 2>&1; then \
		echo "Building documentation..."; \
		cd docs && make html; \
	else \
		echo "Sphinx not installed. Install with: pip install sphinx sphinx-rtd-theme"; \
	fi

check:  ## Run tests and linters
	@$(MAKE) test
	@$(MAKE) lint

ci:  ## Run CI checks locally
	@echo "Running CI checks..."
	@$(MAKE) lint
	@$(MAKE) test
	@echo "All CI checks passed!"
