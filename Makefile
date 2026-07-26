.PHONY: install setup test lint format typecheck run clean

setup:
	./scripts/setup.sh

install: setup
	pip install -e ".[dev]"


test:
	pytest tests/ -v

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy opencode_proxy/

run:
	uvicorn opencode_proxy.main:app --reload --host 0.0.0.0 --port 8080

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete; \
	rm -rf .pytest_cache .mypy_cache .ruff_cache
