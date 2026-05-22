# Provider Operations

Providers are explicit operational choices. Do not treat them as interchangeable strings.

## List Providers

```bash
edc-translation list-engines --include-routing-diagnostics --source en --target fr
```

## Recommended Defaults

| Situation | Provider |
|---|---|
| CI and public examples | `deterministic_ci` |
| Same-language plumbing | `passthrough` |
| Local reviewed NMT | `local_ct2_opus`, `local_ct2_nllb`, or `local_ct2_madlad` |
| Local LLM runtime | `local_openai_compat` |
| Controlled cloud experiment | `openrouter_llm` or `google_gemini` |

## Auto Route

```bash
edc-translation smoke-auto-route --source en --target fr
```

Auto-route fails closed when no reviewed provider is selected.

## Live Smoke

```bash
edc-translation live-smoke --provider local_openai_compat --source en --target fr --max-tokens 64
```

Live smoke is blocked unless explicitly enabled for live provider paths.

## Readiness Checklist

- Provider license reviewed.
- Retention class acceptable.
- Runtime reachable.
- Output includes provider metadata.
- Failure payloads do not expose secrets.
- Live provider calls are opt-in and bounded.
