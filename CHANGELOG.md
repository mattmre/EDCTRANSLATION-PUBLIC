# Changelog

All notable changes to this project are documented here. This project follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses semantic versioning once public releases begin.

## [0.1.0] - 2026-05-22

### Added

- Initial public working tree for EDC Translation.
- Contract-first `DocumentBundle v1` to `TranslationBundle v1` translation path.
- FastAPI, CLI, Python client, MCP-style CLI, and MCP HTTP surfaces.
- Deterministic CI provider and passthrough provider for credential-free examples.
- Optional local CT2 adapter scaffolding for OPUS, NLLB, and MADLAD paths.
- Optional local OpenAI-compatible runtime adapter and bounded local model ranking.
- Optional OpenRouter and Gemini live-provider adapters behind explicit smoke gates.
- Batch text-file translation with manifests, logs, and optional bundle sidecars.
- Local admin UI for API-driven operational smoke workflows.
- Local, file-backed, Postgres-backed, and Kafka-aware job/queue deployment paths.
- Custody, evidence, quality, review, model-validation, and release-readiness surfaces.
- Dockerfile, local Compose, staging-like Compose, Helm, GitOps, and Ansible deployment scaffolding.
- Public documentation suite, wiki source pages, presentation microsite, governance files, issue templates, and release workflows.

### Documentation

- Expanded root README, installation, architecture, development, contribution, support, and security docs.
- Added numbered public docs for system blueprint, tech stack, quickstart, information flows, use cases, walkthrough, deployment, configuration, contracts, provider operations, batch workflows, troubleshooting, and release readiness.
- Added GitHub-wiki-ready source pages under `wiki/`.

### Notes

- The repository does not ship model weights.
- Live providers require operator-managed credentials and explicit opt-in.
- Production-like use requires environment-specific auth, store, retention, provider, and infrastructure review.
