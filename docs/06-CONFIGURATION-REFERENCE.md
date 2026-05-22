# Configuration Reference

Configuration is environment-variable driven. Public examples use safe local defaults and avoid real secrets.

## Core Runtime

| Variable | Default | Purpose |
|---|---|---|
| `EDC_DEPLOYMENT_ENV` | `local` | Deployment class. Non-local environments should reject disabled auth. |
| `EDC_AUTH_MODE` | `disabled` | Auth mode. Use disabled only for isolated local development. |
| `EDC_TRANSLATION_JOB_BACKEND` | `local` | Job store backend: `local` or `postgres`. |
| `EDC_TRANSLATION_QUEUE_BACKEND` | `local` | Queue backend: `local`, `postgres`, or `kafka`. |
| `EDC_TRANSLATION_MODEL_REGISTRY_BACKEND` | local default | Model registry backend. Use Postgres for durable deployments. |
| `EDC_TRANSLATION_AUTH_STORE_BACKEND` | `json` | Auth token/audit store backend: `json` or `postgres`. |
| `EDC_TOKEN_AUDIT_STORE_PATH` | unset | JSON token/audit path for local durable auth tests. |

## Postgres

| Variable | Purpose |
|---|---|
| `EDC_TRANSLATION_POSTGRES_DSN` | Postgres connection string for durable stores. |
| `PGCONNECT_TIMEOUT` | Shortens optional integration probes during tests. |

Use Postgres when you need durable job state, queue state, token/audit records, model registry records, or production-like readiness evidence.

## Kafka

| Variable | Purpose |
|---|---|
| `EDC_TRANSLATION_KAFKA_BOOTSTRAP_SERVERS` | Kafka or Redpanda bootstrap servers. |
| `EDC_TRANSLATION_KAFKA_TOPIC` | Work item topic. |
| `EDC_TRANSLATION_KAFKA_CONSUMER_GROUP` | Worker consumer group. |

Kafka is optional. Use it when you need distributed worker fanout rather than a single local or Postgres-backed queue.

## CT2 Providers

| Variable | Purpose |
|---|---|
| `EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR` | Local OPUS CT2 model directory. |
| `EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR` | Local NLLB CT2 model directory. |
| `EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR` | Local MADLAD CT2 model directory. |
| `EDC_TRANSLATION_CT2_DEVICE` | `cpu` or `cuda`. |
| `EDC_TRANSLATION_CT2_COMPUTE_TYPE` | Optional CT2 compute type. |

Model directories should contain the runtime assets required by the selected CT2 adapter, including tokenizer assets where applicable.

## Local OpenAI-Compatible Runtime

| Variable | Purpose |
|---|---|
| `EDC_TRANSLATION_LOCAL_LLM_BASE_URL` | Base URL for a local OpenAI-compatible runtime. |
| `EDC_TRANSLATION_LOCAL_LLM_MODEL_IDS` | Comma-separated model IDs to probe or prefer. |
| `EDC_TRANSLATION_LOCAL_LLM_TIMEOUT_SECONDS` | Optional request timeout. |

The runtime should support:

- `GET /v1/models`
- `POST /v1/chat/completions`

## Optional Cloud Providers

| Variable | Purpose |
|---|---|
| `EDC_TRANSLATION_LIVE_SMOKE` | Set to `1` to allow tiny live-provider smoke checks. |
| `OPENROUTER_API_KEY` | OpenRouter credential. |
| `EDC_TRANSLATION_OPENROUTER_MODEL_ID` | Optional OpenRouter model ID. |
| `GOOGLE_API_KEY` | Gemini credential. |
| `GEMINI_API_KEY` | Alternate Gemini credential variable. |
| `EDC_TRANSLATION_GOOGLE_MODEL_ID` | Optional Gemini model ID. |

> **Warning**
> Credentials alone should not enable production use. Review provider terms, retention, residency, logging, cost, and quality before live traffic.

## Static Token And JWT Auth

| Variable | Purpose |
|---|---|
| `EDC_STATIC_API_TOKEN_HASH` | PBKDF2 hash for static bearer-token auth. |
| `EDC_STATIC_API_TOKEN_TENANT` | Tenant bound to the static token. |
| `EDC_STATIC_API_TOKEN_SCOPES` | Comma-separated scopes bound to the static token. |
| `EDC_STATIC_API_TOKEN_SUBJECT` | Subject label for audit metadata. |
| `EDC_JWT_SECRET` | HS256 signing secret for JWT paths. |

Never commit plaintext tokens or generated `.env` files.

## LDAP Variables

| Variable | Purpose |
|---|---|
| `EDC_LDAP_URL` | LDAP endpoint. |
| `EDC_LDAP_BIND_DN` | LDAP bind DN. |
| `EDC_LDAP_BIND_PASSWORD` | LDAP bind password. |

LDAP settings are deployment concerns. Public examples intentionally avoid real directory endpoints.

## Batch Text

Batch jobs receive most runtime settings in the API request:

| Request field | Default | Purpose |
|---|---|---|
| `source_path` | required | Input file or directory path. |
| `output_dir` | required | Output directory path. |
| `source_language` | `auto` | Source language tag or auto detection. |
| `target_language` | required | Target language tag. |
| `provider_id` | `deterministic_ci` | Provider for per-file translations. |
| `input_encoding` | `auto` | Input encoding policy. |
| `output_encoding` | `utf-8` | Output encoding. |
| `recursive` | `true` | Recurse directories. |
| `file_extensions` | `[".txt"]` | File extensions to process. |
| `write_translation_bundles` | `true` | Write sidecar bundles. |
| `write_manifest` | `true` | Write batch manifest. |
| `continue_on_error` | `true` | Continue after per-file failures. |

## Minimum Local `.env` Example

```dotenv
EDC_DEPLOYMENT_ENV=local
EDC_AUTH_MODE=disabled
EDC_TRANSLATION_JOB_BACKEND=local
EDC_TRANSLATION_QUEUE_BACKEND=local
```

## Production-Like Checklist

- Set `EDC_DEPLOYMENT_ENV` to a non-local value.
- Use non-disabled auth.
- Use durable job, queue, token/audit, and model registry stores where needed.
- Provide secrets through secret manager or orchestrator primitives.
- Keep live-provider credentials out of images and source control.
- Confirm release-readiness evidence before public claims.
