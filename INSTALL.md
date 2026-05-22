# Install

EDC Translation supports Python editable installs, optional runtime extras, Docker Compose smoke stacks, and local container builds.

## Requirements

| Requirement | Minimum |
|---|---|
| Python | 3.11 |
| pip | Current enough to install PEP 621 projects |
| Docker | Optional, for Compose and image smoke |
| Helm | Optional, for Kubernetes chart validation |
| Ansible | Optional, for inventory-driven deployment dry runs |

## Python Editable Install

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
edc-translation list-engines
```

Linux/macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
edc-translation list-engines
```

## Optional Extras

| Extra | Purpose |
|---|---|
| `.[ct2]` | CTranslate2 and SentencePiece model adapters. |
| `.[postgres]` | Durable Postgres job, queue, token/audit, and model stores. |
| `.[kafka]` | Kafka queue integration. |
| `.[all]` | CT2, Postgres, and Kafka extras. |
| `.[dev]` | Test, lint, HTTP test client, and build tooling. |

Example:

```bash
python -m pip install -e ".[all,dev]"
```

## First Smoke

```bash
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
```

Then start the API:

```bash
uvicorn edc_translation.api:app --host 127.0.0.1 --port 8080
```

## Docker Compose

```bash
docker compose -f docker-compose.local.yml up --build
```

Local ports:

| Service | URL |
|---|---|
| API | `http://127.0.0.1:18080` |
| MCP HTTP | `http://127.0.0.1:18081` |
| Mock LLM | `http://127.0.0.1:18082` |
| Redpanda Kafka | `127.0.0.1:19092` |

Staging-like durable validation:

```bash
export EDC_TRANSLATION_POSTGRES_PASSWORD=local-dev-password
export EDC_JWT_SECRET=local-dev-jwt-secret
docker compose -f docker-compose.prod.yml up --build
```

In PowerShell, set `$env:EDC_TRANSLATION_POSTGRES_PASSWORD="local-dev-password"` and `$env:EDC_JWT_SECRET="local-dev-jwt-secret"` before running the same Compose command.

## Container Image

```bash
docker build -t edc-translation:local .
docker run --rm -p 127.0.0.1:8080:8080 edc-translation:local
```

The image installs Postgres and Kafka extras so worker and durable-store paths are available from the same artifact.

## Verify The Install

```bash
python -m ruff check edc_translation tests
PGCONNECT_TIMEOUT=2 python -m pytest -q
```

## Next Steps

- Read [Quickstart](docs/02-QUICKSTART-5-MINUTE-SUCCESS.md) for a guided local path.
- Read [Configuration Reference](docs/06-CONFIGURATION-REFERENCE.md) before enabling providers.
- Read [Deployment](docs/05-DEPLOYMENT.md) before moving beyond local smoke.
