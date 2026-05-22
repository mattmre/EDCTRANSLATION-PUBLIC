# Tech Stack DNA

EDC Translation is a Python-first service with a deliberately small core dependency set and optional extras for model runtimes, durable stores, and queues.

## Runtime Stack

| Layer | Technology | Role |
|---|---|---|
| Language | Python 3.11+ | API, service layer, CLI, workers, stores, provider adapters, tests. |
| API framework | FastAPI | REST surface, OpenAPI schema, request validation, static admin page route. |
| Request models | Pydantic v2 | API request bodies and field-level validation. |
| JSON contracts | `jsonschema` | Public `DocumentBundle v1` and `TranslationBundle v1` validation. |
| ASGI server | Uvicorn | Local and containerized API serving. |
| CLI | `argparse` | No heavy CLI framework; predictable public command syntax. |
| Tests | pytest, httpx | Unit, API, CLI, packaging, product-surface, and optional integration tests. |
| Lint | Ruff | Fast static checks for Python code. |
| Packaging | setuptools, PEP 621 | Editable installs and wheel/sdist builds. |

## Optional Extras

| Extra | Installs | Enables |
|---|---|---|
| `.[dev]` | `build`, `httpx`, `pytest`, `ruff` | Local development, test, lint, package build. |
| `.[ct2]` | `ctranslate2`, `sentencepiece` | Local CT2 OPUS/NLLB/MADLAD adapters. |
| `.[postgres]` | `psycopg[binary]` | Postgres-backed jobs, queues, token/audit, and model registry. |
| `.[kafka]` | `aiokafka` | Kafka queue integration. |
| `.[all]` | CT2, Postgres, Kafka extras | Full optional local runtime surface. |

## Provider Stack

| Provider family | IDs | Runtime | Configuration |
|---|---|---|---|
| Deterministic | `deterministic_ci` | Built-in Python | None. Best for docs, tests, and CI. |
| Passthrough | `passthrough`, `stub` | Built-in Python | None. Useful for same-language or plumbing checks. |
| CT2 NMT | `local_ct2_opus`, `local_ct2_nllb`, `local_ct2_madlad` | CTranslate2 + SentencePiece | Model directory variables and tokenizer assets. |
| Local LLM | `local_openai_compat` | OpenAI-compatible local runtime | `EDC_TRANSLATION_LOCAL_LLM_BASE_URL` and model IDs. |
| Cloud LLM | `openrouter_llm`, `google_gemini` | Provider HTTP APIs | Credentials plus `EDC_TRANSLATION_LIVE_SMOKE=1` for smoke checks. |

## Store And Queue Stack

| Surface | Local option | Durable option | Notes |
|---|---|---|---|
| Job state | In-memory/local store | Postgres | Controls job submission, status, and completed bundles. |
| Queue | Local queue | Postgres or Kafka | Worker can consume local/store-backed or Kafka work. |
| Model registry | In-memory/local | Postgres | Tracks validated model bundle status. |
| Token/audit | JSON local store | Postgres | Used by auth paths and readiness evidence. |
| Batch output | Filesystem | Operator-managed volume | Requires path policy in shared deployments. |

## Deployment Stack

| Surface | Files | Purpose |
|---|---|---|
| Container image | `Dockerfile` | Single image for API, worker, MCP HTTP, and mock OpenAI-compatible runtime. |
| Local Compose | `docker-compose.local.yml` | Developer smoke with API, MCP HTTP, mock LLM, Redpanda, and no external credentials. |
| Staging-like Compose | `docker-compose.prod.yml` | Durable-store and auth-enforcement validation on one machine. |
| Helm | `helm/edc-translation/` | Kubernetes API, worker, MCP, Postgres/operator, Kafka/operator, KEDA, ingress, network policy, model cache, GPU profiles. |
| GitOps | `gitops/argocd/` | Argo CD application and operator scaffolding. |
| Ansible | `ansible/` | Inventory-driven Helm deployment automation and dry-run examples. |

## Source Layout

| Path | Content |
|---|---|
| `edc_translation/api.py` | REST API, admin route, OpenAPI summary. |
| `edc_translation/cli.py` | Public CLI command parser and command dispatch. |
| `edc_translation/service.py` | Core translation orchestration and shared service functions. |
| `edc_translation/routing.py` | Explicit and auto provider resolution. |
| `edc_translation/llm_live.py` | Optional local/cloud LLM probes and live smoke. |
| `edc_translation/postgres_backend.py` | Postgres schema and store adapters. |
| `edc_translation/kafka_backend.py` | Kafka queue adapter. |
| `edc_translation/text_batch.py` | Recursive text-file translation jobs and output handling. |
| `schemas/` | Public JSON Schema files shipped at repo root. |
| `edc_translation/schemas/` | Packaged copy of public schemas. |
| `tests/` | Contract, CLI, API, service, provider, packaging, and deployment-surface tests. |

## Design Bias

- Keep the default path deterministic and credential-free.
- Keep optional model/runtime integrations explicit.
- Keep provider metadata attached to every output bundle.
- Keep public examples reproducible on a clean clone.
- Keep production-like behavior behind configuration that can be audited.
