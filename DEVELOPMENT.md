# Development

This repo should remain usable from a clean clone. Keep behavior changes paired with tests and public documentation updates.

## Repository Layout

| Path | Purpose |
|---|---|
| `edc_translation/` | Runtime package, API, CLI, engines, stores, providers, auth, review, release readiness, and admin UI. |
| `schemas/` | Public JSON schemas for document and translation contracts. |
| `tests/` | Unit, API, CLI, provider, packaging, product-surface, and optional integration tests. |
| `examples/` | Public sample inputs and deterministic demo fixtures. |
| `helm/` | Kubernetes chart and staged values. |
| `gitops/` | Argo CD application and operator scaffolding. |
| `ansible/` | Parameterized deployment automation. |
| `docs/` | Public documentation suite. |
| `wiki/` | GitHub-wiki-ready source pages maintained in-tree. |
| `presentation/` | Static GitHub Pages microsite and slide deck. |

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Development Commands

```bash
python -m ruff check edc_translation tests
PGCONNECT_TIMEOUT=2 python -m pytest -q
python -m build
helm lint helm/edc-translation
helm template edc-translation helm/edc-translation
docker compose -f docker-compose.local.yml config --quiet
EDC_TRANSLATION_POSTGRES_PASSWORD=local-dev-password EDC_JWT_SECRET=local-dev-jwt-secret docker compose -f docker-compose.prod.yml config --quiet
```

`PGCONNECT_TIMEOUT=2` keeps optional Postgres integration probes from hanging on machines without a local database.
The production-like Compose config requires `EDC_TRANSLATION_POSTGRES_PASSWORD` and `EDC_JWT_SECRET`; use local placeholders only for config validation.

## Change Guidance

| Change type | Expected updates |
|---|---|
| API endpoint | Tests, [API Reference](docs/API-REFERENCE.md), admin UI if applicable. |
| CLI command | CLI tests and docs command tables. |
| Schema change | Root schema, packaged schema, fixtures, [Contracts Reference](docs/07-CONTRACTS-REFERENCE.md). |
| Provider behavior | Provider tests, [Provider Operations](docs/08-PROVIDER-OPERATIONS.md), readiness behavior if relevant. |
| Deployment values | Helm/Compose tests, [Deployment](docs/05-DEPLOYMENT.md), configuration docs. |
| Public docs | Link check, private-term scan, and docs index update. |

## Release Hygiene

- Keep public docs free of private paths, local workstation details, customer data, and internal process notes.
- Keep generated data under ignored folders such as `out/`, `.local-stack/`, build directories, or temp directories.
- Use the deterministic provider for CI and public examples.
- Gate live provider work behind `EDC_TRANSLATION_LIVE_SMOKE=1`.
- Do not include AI/LLM `Co-Authored-By:` footers in commits.
- Do not commit secrets, real `.env` files, local model paths, generated evidence, or private runtime artifacts.

## Documentation Standard

Use active voice and concrete commands. Prefer tables for configuration, routes, providers, and deployment choices. Add Mermaid diagrams for architecture or flow changes. Avoid catch-all abbreviations when listing supported behavior.
