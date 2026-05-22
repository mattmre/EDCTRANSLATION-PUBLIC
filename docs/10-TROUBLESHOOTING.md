# Troubleshooting

Use this guide when local setup, routing, providers, auth, Docker, Helm, or optional stores fail.

## Quick Diagnostics

```bash
python --version
python -m pip show edc-translation
edc-translation list-engines
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
python -m ruff check edc_translation tests
PGCONNECT_TIMEOUT=2 python -m pytest -q
```

## Install Problems

| Symptom | Fix |
|---|---|
| `edc-translation` not found | Activate the virtual environment and reinstall with `python -m pip install -e ".[dev]"`. |
| Python version error | Use Python 3.11 or newer. |
| Optional CT2 import error | Install `.[ct2]` or `.[all]`. |
| Postgres dependency missing | Install `.[postgres]` or `.[all]`. |
| Kafka dependency missing | Install `.[kafka]` or `.[all]`. |

## API Problems

| Symptom | Fix |
|---|---|
| Port already in use | Use a different Uvicorn port or stop the process using `8080`. |
| `/docs` missing | Confirm you launched `edc_translation.api:app`. |
| Job returns `404` | Check the job ID and store backend. Local in-memory state does not survive process restarts. |
| Bundle returns `409` | The job has not completed or failed before bundle creation. |

## Routing Problems

| Symptom | Fix |
|---|---|
| Auto-route unavailable | Use `deterministic_ci` explicitly or configure a local provider. |
| Non-commercial provider skipped | Pass `--allow-nc-licensed` only after license review. |
| Unexpected provider selected | Run `list-engines --include-routing-diagnostics` and inspect candidates. |

## Live Provider Problems

| Symptom | Fix |
|---|---|
| Live smoke blocked | Set `EDC_TRANSLATION_LIVE_SMOKE=1`. |
| Credential missing | Set provider credential variables outside source control. |
| Runtime unreachable | Check base URL, host binding, firewall, and `/v1/models`. |
| Non-JSON provider response | Confirm the runtime implements OpenAI-compatible response shapes. |

## Auth Problems

| Symptom | Fix |
|---|---|
| Disabled auth rejected | Set `EDC_DEPLOYMENT_ENV=local` for local-only smoke, or configure auth for staging/prod. |
| Missing scope | Bind the token/JWT to the route scope listed in [API Reference](API-REFERENCE.md). |
| Cross-tenant rejection | Use the token's tenant or update tenant binding intentionally. |

## Docker And Compose Problems

| Symptom | Fix |
|---|---|
| Build cannot copy schemas | Build from repo root. |
| Port conflict | Edit Compose host ports or stop the conflicting process. |
| Mock runtime unhealthy | Check `docker compose logs mock-llm`. |
| API cannot reach runtime | Confirm service URL and Compose network hostnames. |

## Helm Problems

| Symptom | Fix |
|---|---|
| `helm lint` fails | Validate values indentation and required fields. |
| Rendered auth secret missing | Set auth secret references in values. |
| Model cache PVC not mounted | Check `modelCache` values and storage class availability. |
| GPU scheduling fails | Check node labels, tolerations, and requested GPU profile. |

## Postgres And Kafka Problems

| Symptom | Fix |
|---|---|
| Postgres connection hangs in tests | Use `PGCONNECT_TIMEOUT=2`. |
| Durable jobs disappear | Confirm `EDC_TRANSLATION_JOB_BACKEND=postgres` and DSN are set for all processes. |
| Worker sees no jobs | Confirm queue backend and worker configuration match API configuration. |
| Kafka consumer does not process | Check bootstrap servers, topic, consumer group, and network reachability. |

## When Filing An Issue

Include:

- OS and Python version.
- Install method.
- Exact command.
- Provider ID.
- Store/queue backend.
- Whether Docker, Helm, or Ansible is involved.
- Sanitized error output.
