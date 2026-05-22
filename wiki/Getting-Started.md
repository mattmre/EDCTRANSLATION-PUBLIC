# Getting Started

This page gets a new user from clean clone to a working deterministic translation.

## Install

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

## First Translation

```bash
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
```

This uses the deterministic provider so no credentials, model downloads, or external services are needed.

## Start The API

```bash
uvicorn edc_translation.api:app --host 127.0.0.1 --port 8080
```

Open:

- `http://127.0.0.1:8080/healthz`
- `http://127.0.0.1:8080/readyz`
- `http://127.0.0.1:8080/docs`
- `http://127.0.0.1:8080/admin`

## Docker Smoke

```bash
docker compose -f docker-compose.local.yml up --build
```

Local services:

| Service | URL |
|---|---|
| API | `http://127.0.0.1:18080` |
| MCP HTTP | `http://127.0.0.1:18081` |
| Mock LLM | `http://127.0.0.1:18082` |

## Next Pages

- [Architecture Overview](Architecture-Overview.md)
- [API and CLI](API-and-CLI.md)
- [Configuration](Configuration.md)
