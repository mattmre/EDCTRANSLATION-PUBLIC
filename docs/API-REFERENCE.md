# API Reference

The FastAPI app exposes OpenAPI at `/openapi.json` and interactive docs at `/docs` when running locally.

```bash
uvicorn edc_translation.api:app --host 127.0.0.1 --port 8080
```

## Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Basic service health. |
| GET | `/healthz` | Kubernetes liveness. |
| GET | `/readyz` | Kubernetes readiness. |

## Provider And Language Discovery

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/translation/engines` | List provider metadata; optional routing diagnostics. |
| GET | `/api/v1/translation/languages` | Return language catalog and provider capability matrices. |
| GET | `/api/v1/translation/routing/diagnostics` | Explain auto-route candidate selection. |
| GET | `/api/v1/translation/readiness/auto-route` | Return ready or fail with auto-route diagnostics. |

## Translation

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/translation/bundles` | Translate a `DocumentBundle v1` synchronously. |
| POST | `/api/v1/translation/jobs` | Submit a `DocumentBundle v1` asynchronous job. |
| POST | `/api/v1/translation/jobs/text` | Submit raw text as a normalized translation job. |
| GET | `/api/v1/translation/jobs` | List translation jobs. |
| GET | `/api/v1/translation/jobs/{job_id}` | Read job status. |
| GET | `/api/v1/translation/jobs/{job_id}/bundle` | Read completed `TranslationBundle v1`. |
| GET | `/api/v1/translation/jobs/{job_id}/evidence` | Read evidence metadata for a job. |
| POST | `/api/v1/translation/score-pair` | Score a source/translation pair. |
| POST | `/api/v1/translation/custody/validate` | Validate custody fields on a translation bundle. |

## Batch Text Files

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/translation/files/batch` | Submit a folder/file text translation job. |
| GET | `/api/v1/translation/files/batch` | List batch jobs. |
| GET | `/api/v1/translation/files/batch/{job_id}` | Read batch job status. |
| GET | `/api/v1/translation/files/batch/{job_id}/logs` | Read structured logs. |
| GET | `/api/v1/translation/files/batch/{job_id}/logs/text` | Read plain-text logs. |
| POST | `/api/v1/translation/files/batch/{job_id}/logs/save` | Save logs to a selected path. |
| GET | `/api/v1/translation/files/batch/{job_id}/outputs` | List output files and sidecars. |

## Governance, Models, And Reviews

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/translation/tenant-policy/{tenant_id}` | Read tenant policy. |
| PUT | `/api/v1/translation/tenant-policy/{tenant_id}` | Update tenant policy fields. |
| GET | `/api/v1/translation/glossaries` | List glossaries. |
| POST | `/api/v1/translation/glossaries` | Upsert a glossary. |
| GET | `/api/v1/translation/glossaries/{glossary_id}` | Read one glossary. |
| DELETE | `/api/v1/translation/glossaries/{glossary_id}` | Delete one glossary. |
| GET | `/api/v1/translation/instruction-sets` | List instruction sets. |
| POST | `/api/v1/translation/models/validate` | Validate a local model bundle. |
| GET | `/api/v1/translation/models` | List model validation status. |
| POST | `/api/v1/translation/live-smoke` | Run a tiny opt-in live provider smoke check. |
| GET | `/api/v1/translation/local-model-ranking` | Rank local OpenAI-compatible models with bounded probes. |
| GET | `/api/v1/translation/env-discovery` | List top-level env files and relevant variable names without values. |
| GET | `/api/v1/translation/readiness/evidence-status` | Return release-readiness evidence lane status. |
| GET | `/api/v1/translation/reviews` | List review decisions. |
| POST | `/api/v1/translation/jobs/{job_id}/reviews` | Record a review or certification decision. |
| GET | `/api/v1/translation/admin` | Serve static admin HTML. |
| GET | `/api/v1/translation/openapi-summary` | Return a compact endpoint list. |

## Example: Raw Text Job

```bash
curl -s -X POST http://127.0.0.1:8080/api/v1/translation/jobs/text \
  -H "content-type: application/json" \
  -d "{\"text\":\"Hello world.\",\"source_language\":\"en\",\"target_language\":\"fr\",\"provider_id\":\"deterministic_ci\"}"
```

## Example: Auto-Route Diagnostics

```bash
curl -s "http://127.0.0.1:8080/api/v1/translation/routing/diagnostics?source_language=en&target_language=fr"
```

## CLI Commands

| Command | Purpose |
|---|---|
| `edc-translation list-engines` | List provider engines. |
| `edc-translation smoke-auto-route` | Fail if auto-route cannot select an engine. |
| `edc-translation translate` | Translate a `DocumentBundle v1` JSON file. |
| `edc-translation submit-bundle` | Submit a document bundle job. |
| `edc-translation job-status` | Get local job status. |
| `edc-translation get-bundle` | Get a completed translation bundle. |
| `edc-translation submit-text` | Submit raw text. |
| `edc-translation score-pair` | Score source and translated text. |
| `edc-translation verify-model-bundle` | Validate a local model bundle. |
| `edc-translation evidence-bundle` | Read evidence metadata for a job. |
| `edc-translation validate-custody` | Validate custody fields in a bundle. |
| `edc-translation tenant-policy` | Read or update tenant policy. |
| `edc-translation glossaries` | List or upsert glossaries. |
| `edc-translation instruction-sets` | List instruction sets. |
| `edc-translation model-status` | List validated model status. |
| `edc-translation review-job` | Record a review decision. |
| `edc-translation live-smoke` | Run an opt-in tiny live smoke. |
| `edc-translation rank-local-models` | Rank local OpenAI-compatible models. |
| `edc-translation runtime-readiness` | Probe local runtime readiness. |
| `edc-translation discover-env` | List env variable names without values. |
| `edc-translation readiness-check` | Check release evidence prerequisites. |
| `edc-translation readiness-run` | Run lane-separated readiness rubric. |

## MCP-Style Tools

Run:

```bash
edc-translation-mcp --list-tools
edc-translation-mcp-http --host 127.0.0.1 --port 8081
```

Tools include:

- `translation_list_engines`
- `translation_submit_bundle`
- `translation_get_job_status`
- `translation_get_bundle`
- `translation_submit_text`
- `translation_score_pair`
- `translation_validate_model_bundle`
- `translation_get_evidence_bundle`
- `translation_validate_custody`
- `translation_live_smoke`
- `translation_rank_local_models`
- `translation_discover_env`
- `translation_release_readiness_status`

## Route Scopes

| Scope | Typical routes |
|---|---|
| `translation:submit` | Submit bundles, text, batch jobs, glossaries. |
| `translation:read` | Read jobs, bundles, batch outputs, reviews. |
| `evidence:read` | Evidence bundles and custody validation. |
| `models:read` | Engines, languages, readiness, local ranking, live smoke. |
| `models:write` | Model bundle validation. |
| `tenant:policy:read` | Read tenant policy. |
| `tenant:policy:write` | Update tenant policy. |
| `reviews:write` | Record review decisions. |
| `audit:read` | Env discovery, release-readiness status, admin page. |
