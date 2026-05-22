# Security And Release Readiness

## Security Posture

- Disabled auth is local-only.
- Staging and production-like deployments require non-disabled auth.
- Tokens should be stored as hashes.
- Live providers require explicit credentials and smoke opt-in.
- Batch filesystem access requires deployment-level path policy.

## Public Hygiene

- Do not commit secrets, `.env` files, private model paths, generated evidence, customer data, or local runtime artifacts.
- Do not include AI/LLM co-author footers in commits.
- Keep public docs free of private paths and private entity names.
- Use deterministic examples by default.

## Readiness Commands

```bash
edc-translation readiness-check
edc-translation readiness-run
```

## Release Checklist

- Docs and wiki pages are complete.
- Presentation site renders.
- Private-term sweep is clean.
- Secret-pattern scan is clean or findings are confirmed fixtures/examples.
- Tests pass.
- Compose and Helm render checks pass.
- Live-provider claims have live-smoke evidence.

See [Security And Release Readiness](../docs/11-SECURITY-AND-RELEASE-READINESS.md) for the full public-release checklist.
