.PHONY: install run lint format typecheck test integration-test migration migrate docker-up docker-down

install:
	python -m pip install -e ".[dev]"

run:
	python -m app.main

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy .

test:
	pytest

integration-test:
	pytest -m integration

migration:
	alembic revision --autogenerate -m "$(m)"

migrate:
	alembic upgrade head

docker-up:
	docker compose up --build

docker-down:
	docker compose down
