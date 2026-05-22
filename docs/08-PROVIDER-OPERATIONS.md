# Provider Operations

Provider configuration is the main operational decision in EDC Translation. The default path is deterministic and local; every live or model-backed path should be explicitly reviewed.

## Provider Inventory

Run:

```bash
edc-translation list-engines --include-routing-diagnostics --source en --target fr
```

The output includes provider ID, family, local/cloud flags, license, retention class, quality class, latency class, deployment environments, runtime, runtime version, model provenance, and configuration status.

## Provider Families

| Family | Provider IDs | Notes |
|---|---|---|
| `passthrough` | `passthrough`, `stub`, `deterministic_ci` | Built in; best for tests and plumbing. |
| `ct2_nmt` | `local_ct2_opus`, `local_ct2_nllb`, `local_ct2_madlad` | Optional CT2/SentencePiece model directories. |
| `llm_local` | `local_openai_compat` | Local `/v1` runtime. |
| `llm_cloud` | `openrouter_llm`, `google_gemini` | Optional external provider calls. |

## Auto-Route Policy

`provider_id=auto` is opt-in. It can select passthrough for same-language requests or a configured local provider. It fails closed when no acceptable provider is configured.

```bash
edc-translation smoke-auto-route --source en --target fr
```

Use `--allow-nc-licensed` only after license review.

## Local OpenAI-Compatible Runtime

Set:

```dotenv
EDC_TRANSLATION_LOCAL_LLM_BASE_URL=http://127.0.0.1:1234
EDC_TRANSLATION_LOCAL_LLM_MODEL_IDS=model-a,model-b
```

Probe:

```bash
edc-translation runtime-readiness --provider local_openai_compat
edc-translation rank-local-models --source en --target fr --max-models 4
```

The runtime should support `GET /v1/models` and `POST /v1/chat/completions`.

## CT2 Model Bundles

Set the appropriate model directory:

```dotenv
EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR=/models/opus-en-fr
EDC_TRANSLATION_CT2_DEVICE=cpu
```

Validate:

```bash
edc-translation verify-model-bundle ./models/opus-en-fr --model-id opus-en-fr
```

Model validation should check required runtime files, tokenizer assets, provenance metadata, and operator approval requirements.

## Live Provider Smoke

Live smoke is intentionally gated:

```dotenv
EDC_TRANSLATION_LIVE_SMOKE=1
OPENROUTER_API_KEY=...
```

Then:

```bash
edc-translation live-smoke --provider openrouter_llm --source en --target fr --text "Translate this sentence." --max-tokens 64
```

Do not use live providers for sensitive data until terms, retention, residency, logging, and cost controls are reviewed.

## Provider Readiness Checklist

- Provider ID is explicit or auto-route diagnostics select the expected provider.
- License is compatible with the intended use.
- Retention class is acceptable for the data category.
- Runtime credentials are not committed.
- Live smoke is bounded and opt-in.
- Model provenance is documented.
- Output bundles include provider metadata.
- Failure payloads do not expose secrets.
