# v0.1.0 - Initial Public Release

This release publishes the first public working tree for EDC Translation: a contract-first translation control plane for structured document workflows.

## Highlights

- `DocumentBundle v1` input and `TranslationBundle v1` output contracts.
- Deterministic local provider for repeatable smoke tests and examples.
- FastAPI, CLI, Python client, MCP-style CLI, and MCP HTTP surfaces.
- Provider metadata, auto-route diagnostics, tenant policy, glossaries, instruction sets, review decisions, and evidence surfaces.
- Batch text-file translation with manifests, logs, and optional sidecar bundles.
- Docker Compose local stack with API, MCP HTTP, mock LLM, Postgres, and Redpanda.
- Helm, GitOps, and Ansible deployment scaffolding.
- Full public documentation suite, wiki source pages, and presentation microsite.

## Install

```bash
python -m pip install -e ".[dev]"
edc-translation list-engines
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
```

## Not Included

- Model weights.
- Managed hosting.
- Production legal, residency, or provider approval.
- Cloud-provider credentials.
- OCR image extraction.

## Validation

```bash
python -m ruff check edc_translation tests
PGCONNECT_TIMEOUT=2 python -m pytest -q
docker compose -f docker-compose.local.yml config --quiet
docker compose -f docker-compose.prod.yml config --quiet
helm lint helm/edc-translation
helm template edc-translation helm/edc-translation
```

## Documentation

- [README](README.md)
- [Install](INSTALL.md)
- [Architecture](ARCHITECTURE.md)
- [Docs Index](docs/README.md)
- [API Reference](docs/API-REFERENCE.md)
- [Contracts Reference](docs/07-CONTRACTS-REFERENCE.md)
- [Provider Operations](docs/08-PROVIDER-OPERATIONS.md)
- [Wiki Source](wiki/Home.md)
- [Presentation](presentation/index.html)
