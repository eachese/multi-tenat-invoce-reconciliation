# Convenience commands for Flow RMS invoice API

.PHONY: install lint format test run dev

install:
	poetry install

lint:
	poetry run ruff check app
	poetry run mypy app

format:
	poetry run black app
	poetry run isort app

format-check:
	poetry run black --check app
	poetry run isort --check-only app

test:
	poetry run pytest --cov=app --cov-report=term-missing

run:
	poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:
	poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
