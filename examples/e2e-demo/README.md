# E2E Demo Translation Data

This folder contains public-safe smoke data for deterministic end-to-end testing. The checked-in fixture is intentionally small and project-authored so local tests do not need network access, API keys, paid provider calls, or external corpus downloads.

## Included Fixture

| File | Purpose |
|---|---|
| `edc-translation-cc0-smoke.json` | Tiny public smoke fixture used for deterministic examples and contract checks. |

## Optional External Datasets

The fixture file records two broader public dataset references for manual or CI-gated model-quality evaluation:

| Dataset | License note | Use |
|---|---|---|
| FLORES-200 on Hugging Face | CC-BY-SA-4.0 | Multilingual translation benchmark evaluation. |
| Tatoeba text downloads | CC-BY 2.0 FR | Multilingual sentence and translation collection requiring attribution. |

Handle attribution and share-alike obligations in the generated evidence artifact when using external datasets. Do not vendor large external corpora into this repository.

## Recommended Smoke

```bash
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
```

For full contract validation, use fixtures under `tests/fixtures/edc_contracts/`.
