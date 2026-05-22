# Deployment Decision Guide

Use this guide to choose the smallest deployment path that answers the question in front of you.

## Decision Matrix

| Goal | Recommended path | Why | Promotion trigger |
|---|---|---|---|
| Try the CLI and contracts | Python editable install | Fast, no containers, no credentials. | You need HTTP, MCP, or container parity. |
| Demo API and admin page | Python + Uvicorn | Direct API feedback with local reload. | You need multiple services. |
| Exercise API, MCP, mock LLM, and Kafka locally | `docker-compose.local.yml` | One command with no external credentials. | You need auth/durable-store behavior. |
| Validate durable stores on one machine | `docker-compose.prod.yml` | Exercises Postgres-backed paths and auth enforcement. | You need Kubernetes manifests. |
| Render cluster manifests | Helm default/staging values | Confirms chart shape before cluster access. | You need GitOps promotion. |
| Operate in Kubernetes | Helm plus GitOps | Repeatable rollout, scaling, secrets, ingress, platform integration. | You need inventory-driven automation. |
| Parameterize cluster deployment | Ansible | Useful when teams drive Helm from inventory. | You need organization-specific playbooks. |

## Provider Decision Matrix

| Goal | Provider path |
|---|---|
| Reproducible tests and examples | `deterministic_ci` |
| Same-language plumbing | `passthrough` |
| Air-gapped local NMT | CT2 provider after model/license validation |
| Local LLM runtime evaluation | `local_openai_compat` with bounded probes |
| Cloud-provider experiment | OpenRouter or Gemini only after explicit live-smoke opt-in |

## Store Decision Matrix

| Requirement | Store/queue choice |
|---|---|
| Fast local tests | Local in-memory/default stores |
| Repeatable local evidence | File-backed or JSON local stores |
| Durable API jobs | Postgres job backend |
| Durable token/audit records | Postgres auth store |
| Distributed worker fanout | Kafka queue backend |

## Maturity Notes

- Use deterministic provider paths for CI and public examples.
- Treat live providers and local model runtimes as explicitly configured operator surfaces.
- Do not expose batch filesystem APIs to untrusted users without a path policy.
- Do not run staging or production with disabled authentication.
- Do not promote `auto` routing until diagnostics show the expected provider.
- Do not claim production readiness without release-readiness evidence artifacts.

## Promotion Checklist

| Promotion | Required evidence |
|---|---|
| Local to Compose | CLI smoke, API health, deterministic text job. |
| Compose local to staging-like Compose | Auth mode selected, durable Postgres configured, tests pass. |
| Compose to Helm render | Helm lint and template pass, values reviewed. |
| Helm render to cluster | Secret references, ingress, network policy, store backends, and resource requests reviewed. |
| Cluster smoke to release | Readiness lanes, live-provider smoke if enabled, public docs, and private-term scan complete. |
