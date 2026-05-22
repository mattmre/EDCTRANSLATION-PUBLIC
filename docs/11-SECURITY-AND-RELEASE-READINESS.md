# Security And Release Readiness

This document covers public-release hygiene, runtime security posture, and the readiness checks that should pass before a public announcement or production-like deployment claim.

## Public Hygiene

- Do not commit secrets, `.env` files, private model paths, customer documents, generated evidence, or local runtime artifacts.
- Do not include AI/LLM `Co-Authored-By:` footers in commit messages.
- Keep public docs free of private repo names, private workstation paths, internal hostnames, and customer names.
- Use deterministic examples unless a section explicitly describes optional provider configuration.
- Keep generated outputs out of source control unless they are intentional fixtures.

## Runtime Security Posture

| Area | Required posture |
|---|---|
| Auth | Disabled auth only for isolated local development. |
| Staging/prod | Non-disabled auth plus tenant and scope binding. |
| Tokens | Store hashes, not plaintext tokens. |
| JWT | Use deployment-managed secrets. |
| Batch filesystem | Restrict source and output roots outside the application. |
| Live providers | Require explicit credentials and `EDC_TRANSLATION_LIVE_SMOKE=1`. |
| Logs | Do not log secrets or full sensitive payloads. |

## Release Readiness Commands

```bash
edc-translation readiness-check
edc-translation readiness-run
```

The readiness rubric is lane-separated and intentionally avoids auto-claiming perfect readiness without evidence artifacts.

## Evidence Lanes

| Lane | Evidence examples |
|---|---|
| Product E2E | Deterministic CLI/API tests, contract fixtures, local smoke output. |
| Local evidence | Custody validation, evidence bundle retrieval, review decision flow. |
| Deployment | Compose config, Helm lint/template, Ansible dry run. |
| Auth provider | Disabled-auth rejection in non-local mode, token/JWT scope checks, audit store configuration. |
| Live provider | Bounded live smoke artifact for each enabled live provider. |

## Public Release Checklist

- README renders with hero, badges, quickstart, system diagram, and links.
- Numbered docs suite is complete.
- Presentation site renders desktop and mobile without console errors.
- Wiki source pages are present under `wiki/`.
- Private-term sweep is clean.
- Secret-pattern scan is clean or findings are confirmed examples/tests.
- `python -m ruff check edc_translation tests` passes.
- `PGCONNECT_TIMEOUT=2 python -m pytest -q` passes or skips are understood.
- `docker compose -f docker-compose.local.yml config --quiet` passes.
- `EDC_TRANSLATION_POSTGRES_PASSWORD=local-dev-password EDC_JWT_SECRET=local-dev-jwt-secret docker compose -f docker-compose.prod.yml config --quiet` passes.
- `helm lint helm/edc-translation` passes.
- `helm template edc-translation helm/edc-translation` passes.

## Security Reporting

Use [SECURITY.md](../SECURITY.md) for vulnerability reporting. Do not include real documents, secrets, API keys, private model artifacts, or private infrastructure details in public issues.
