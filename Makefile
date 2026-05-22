.PHONY: install install-dev test lint build docker helm compose-config

install:
	python -m pip install --upgrade pip
	python -m pip install -e .

install-dev:
	python -m pip install --upgrade pip
	python -m pip install -e ".[dev]"

test:
	PGCONNECT_TIMEOUT=2 python -m pytest -q

lint:
	python -m ruff check edc_translation tests

build:
	python -m build

docker:
	docker build -t edc-translation:local .

helm:
	helm lint helm/edc-translation
	helm template edc-translation helm/edc-translation

compose-config:
	docker compose -f docker-compose.local.yml config --quiet
	docker compose -f docker-compose.prod.yml config --quiet
