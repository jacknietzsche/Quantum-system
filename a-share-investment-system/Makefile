.PHONY: help install test lint format serve dev build clean docker

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements.txt 2>/dev/null || pip install -e ".[dev]" 2>/dev/null || true

test:  ## Run unit tests
	python -m pytest tests/unit/ --no-cov --timeout=15 -v

test-all:  ## Run all tests
	python -m pytest tests/ --no-cov --timeout=30 -v

lint:  ## Run linter
	ruff check .

format:  ## Format code
	ruff format .

format-check:  ## Check formatting
	ruff format --check .

serve:  ## Start production server
	python main.py serve

dev:  ## Start development server
	python launch.py --dev

build:  ## Build frontend
	cd frontend && npm run build:quick

clean:  ## Clean build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache

docker:  ## Build and run Docker container
	docker-compose up --build -d

docker-stop:  ## Stop Docker container
	docker-compose down
