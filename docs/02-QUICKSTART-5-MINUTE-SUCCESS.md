# Quickstart: 5-Minute Success

This path verifies the package, CLI, deterministic provider, REST API, and local documentation assumptions without model downloads or external credentials.

## Prerequisites

| Requirement | Version or note |
|---|---|
| Python | 3.11 or newer |
| Git | Any current version |
| Shell | PowerShell on Windows, Bash-compatible shell on Linux/macOS |
| Optional | Docker Desktop or Docker Engine for Compose smoke |

## 1. Create The Environment

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Linux/macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

> **Tip**
> Use `.[all]` only when you want CT2, Postgres, and Kafka optional dependencies installed. The quickstart does not need them.

## 2. Confirm Provider Discovery

```bash
edc-translation list-engines
```

Expected baseline:

- `deterministic_ci` appears and is configured.
- `passthrough` appears and is configured.
- Optional CT2 and live providers appear with metadata, but may report configuration requirements.

For routing diagnostics:

```bash
edc-translation list-engines --include-routing-diagnostics --source en --target fr
```

## 3. Translate Raw Text

```bash
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
```

The command returns JSON with a completed local job and provider metadata. The deterministic provider produces repeatable output for integration tests and documentation examples.

## 4. Translate A Contract Bundle

```bash
edc-translation translate tests/fixtures/edc_contracts/document-bundle-v1.valid.json --target fr --provider deterministic_ci
```

Use this command when you need to validate the full document-bundle contract rather than a raw-text convenience path.

## 5. Run The API

```bash
uvicorn edc_translation.api:app --host 127.0.0.1 --port 8080
```

Open these local URLs:

| URL | Purpose |
|---|---|
| `http://127.0.0.1:8080/healthz` | Liveness. |
| `http://127.0.0.1:8080/readyz` | Readiness. |
| `http://127.0.0.1:8080/docs` | FastAPI interactive docs. |
| `http://127.0.0.1:8080/admin` | Static local admin page. |

Submit raw text with curl:

```bash
curl -s -X POST http://127.0.0.1:8080/api/v1/translation/jobs/text \
  -H "content-type: application/json" \
  -d "{\"text\":\"Hello world.\",\"source_language\":\"en\",\"target_language\":\"fr\",\"provider_id\":\"deterministic_ci\"}"
```

## 6. Run The Local Compose Smoke

```bash
docker compose -f docker-compose.local.yml up --build
```

| Service | URL or port |
|---|---|
| API | `http://127.0.0.1:18080` |
| MCP HTTP | `http://127.0.0.1:18081` |
| Mock OpenAI-compatible runtime | `http://127.0.0.1:18082` |
| Redpanda Kafka | `127.0.0.1:19092` |

## 7. Run Tests

```bash
python -m ruff check edc_translation tests
PGCONNECT_TIMEOUT=2 python -m pytest -q
```

`PGCONNECT_TIMEOUT=2` keeps optional Postgres integration probes from hanging on machines without a local database.

## First Failure Checks

| Symptom | Check |
|---|---|
| `edc-translation` command not found | Confirm the virtual environment is activated and `python -m pip install -e ".[dev]"` succeeded. |
| API starts but `/docs` is unavailable | Confirm Uvicorn is serving `edc_translation.api:app` and no other service owns the port. |
| Auto-route returns no provider | Use `deterministic_ci` explicitly or configure a local model path/runtime. |
| Live smoke fails | Set credentials and `EDC_TRANSLATION_LIVE_SMOKE=1`; otherwise live calls are intentionally blocked. |
| Docker Compose port conflict | Change host port mappings or stop the process already using the local port. |
