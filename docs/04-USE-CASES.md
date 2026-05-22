# Use Cases

EDC Translation is best for teams that already have text or document-span output and need a governed translation layer around it. It is not an OCR engine and it is not a managed translation marketplace.

## 1. Contract Smoke Testing

| Field | Details |
|---|---|
| User | Developer integrating a document-processing pipeline. |
| Problem | The upstream system needs proof that its `DocumentBundle v1` output can be translated and consumed downstream. |
| Workflow | Run the deterministic provider against a fixture and validate the returned `TranslationBundle v1`. |
| Command | `edc-translation translate tests/fixtures/edc_contracts/document-bundle-v1.valid.json --target fr --provider deterministic_ci` |
| Success | Output validates, span IDs are preserved, provider metadata is present, and no external services are used. |

## 2. Local API Integration

| Field | Details |
|---|---|
| User | Application developer. |
| Problem | A product needs a local translation API during feature development. |
| Workflow | Start Uvicorn, submit raw text or bundles, retrieve job state and bundles. |
| Best provider | `deterministic_ci` for tests; `local_openai_compat` or CT2 adapters after model review. |
| Success | The app can handle job IDs, completed bundles, failures, and provider metadata. |

## 3. Multilingual Review Pipeline

| Field | Details |
|---|---|
| User | Review workflow owner. |
| Problem | Reviewers need translated text while preserving source span identity and custody references. |
| Workflow | Submit structured bundles, retrieve translated spans, record review decisions, export evidence metadata. |
| Success | Every translated span maps back to a source span, page, bounding box, source language, target language, provider, and quality score. |

## 4. Local Model Evaluation

| Field | Details |
|---|---|
| User | Model owner or ML platform engineer. |
| Problem | Candidate local runtimes need a small, controlled probe before being wired into workflows. |
| Workflow | Configure local runtime variables, run `runtime-readiness`, run tiny live smoke, then compare local model ranking. |
| Success | The runtime reports `/v1/models`, selected models answer bounded prompts, and failures do not expose secrets. |

## 5. Folder-Based Text Translation

| Field | Details |
|---|---|
| User | Operator, analyst, or support engineer. |
| Problem | A directory of text files needs translated output while preserving relative structure. |
| Workflow | Submit a batch file job with source path, output directory, encoding settings, and sidecar bundle options. |
| Success | Translated files, optional JSON sidecars, logs, and manifest are written to the output directory. |

## 6. Agent Or Automation Tooling

| Field | Details |
|---|---|
| User | Automation engineer or agent developer. |
| Problem | A tool runner needs a bounded translation interface with discoverable schemas. |
| Workflow | Use `edc-translation-mcp --list-tools` or run the MCP HTTP wrapper locally. |
| Success | Tool calls return JSON objects, scope checks apply, and the same service layer handles API/CLI/MCP behavior. |

## 7. Platform Deployment Evaluation

| Field | Details |
|---|---|
| User | Platform team. |
| Problem | The team needs to evaluate whether the service can run in their cluster shape. |
| Workflow | Render Helm, run Compose config validation, dry-run Ansible, and inspect values for auth, stores, workers, ingress, and network policy. |
| Success | Manifests render, auth is configured for non-local environments, durable stores are selected, and rollout dependencies are explicit. |

## Non-Goals

| Not a fit | Why |
|---|---|
| Image-only OCR extraction | The project consumes text/spans; it does not extract text from images. |
| Blind live-provider proxying | Live providers are opt-in and require credential, retention, and quality review. |
| Automatic legal certification | The service records metadata and review decisions; it does not provide legal advice. |
| Public model hosting | Model weights and runtime selection are operator-managed. |

## Acceptance Criteria For Any Use Case

- Input and output contracts are versioned.
- Provider identity and retention class are visible in output.
- Failure responses are bounded and actionable.
- Local examples are reproducible without credentials.
- Sensitive provider paths require explicit configuration.
