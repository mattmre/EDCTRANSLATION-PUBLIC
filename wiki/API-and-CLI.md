# API And CLI

## CLI

Common commands:

```bash
edc-translation list-engines
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
edc-translation translate tests/fixtures/edc_contracts/document-bundle-v1.valid.json --target fr --provider deterministic_ci
edc-translation score-pair --source source.txt --target translated.txt
edc-translation verify-model-bundle ./models/opus-en-fr
edc-translation readiness-check
```

Run help:

```bash
edc-translation --help
edc-translation submit-text --help
```

## REST

Start:

```bash
uvicorn edc_translation.api:app --host 127.0.0.1 --port 8080
```

Primary routes:

| Route | Purpose |
|---|---|
| `/api/v1/translation/engines` | Provider metadata. |
| `/api/v1/translation/languages` | Language catalog. |
| `/api/v1/translation/jobs/text` | Raw text job submission. |
| `/api/v1/translation/bundles` | Synchronous bundle translation. |
| `/api/v1/translation/files/batch` | Batch text job submission. |
| `/api/v1/translation/jobs/{job_id}/bundle` | Completed bundle retrieval. |
| `/api/v1/translation/jobs/{job_id}/evidence` | Evidence metadata. |

## MCP

```bash
edc-translation-mcp --list-tools
edc-translation-mcp-http --host 127.0.0.1 --port 8081
```

MCP-style tools include translation submission, job lookup, bundle retrieval, provider listing, quality scoring, custody validation, model validation, live smoke, local model ranking, env discovery, and release-readiness status.

See [API Reference](../docs/API-REFERENCE.md) for the full route and tool map.
