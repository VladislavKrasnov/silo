.PHONY: install install-dev run test test-fast lint format docker-build docker-up docker-down

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

run:
	python -m app

test:
	pytest

test-fast:
	pytest -m "not slow"

lint:
	ruff check app tests

format:
	black app tests && ruff check --fix app tests

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down
