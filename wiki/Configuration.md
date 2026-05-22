# Configuration

Configuration is environment-variable driven. Defaults are optimized for local deterministic smoke.

## Minimal Local Configuration

```dotenv
EDC_DEPLOYMENT_ENV=local
EDC_AUTH_MODE=disabled
EDC_TRANSLATION_JOB_BACKEND=local
EDC_TRANSLATION_QUEUE_BACKEND=local
```

## Stores

| Variable | Purpose |
|---|---|
| `EDC_TRANSLATION_JOB_BACKEND` | `local` or `postgres`. |
| `EDC_TRANSLATION_QUEUE_BACKEND` | `local`, `postgres`, or `kafka`. |
| `EDC_TRANSLATION_POSTGRES_DSN` | Postgres connection string. |
| `EDC_TRANSLATION_AUTH_STORE_BACKEND` | `json` or `postgres`. |

## Providers

| Variable | Purpose |
|---|---|
| `EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR` | OPUS CT2 model directory. |
| `EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR` | NLLB CT2 model directory. |
| `EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR` | MADLAD CT2 model directory. |
| `EDC_TRANSLATION_LOCAL_LLM_BASE_URL` | Local OpenAI-compatible runtime URL. |
| `EDC_TRANSLATION_LOCAL_LLM_MODEL_IDS` | Preferred local model IDs. |
| `EDC_TRANSLATION_LIVE_SMOKE` | Enables bounded live-provider smoke checks when set to `1`. |

## Auth

Use disabled auth only in isolated local development. Staging and production-like environments should configure static token, JWT, or enterprise auth paths and bind scopes intentionally.

See [Configuration Reference](../docs/06-CONFIGURATION-REFERENCE.md) for the full table.
