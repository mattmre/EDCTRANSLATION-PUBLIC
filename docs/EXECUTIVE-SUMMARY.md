# Executive Summary

EDC Translation provides a governed translation layer for structured document-processing systems. It turns raw text or `DocumentBundle v1` input into `TranslationBundle v1` output while preserving source-span identity, provider metadata, quality fields, custody references, and review hooks.

## Why It Exists

Most translation integrations are direct provider calls. That is not enough for review-heavy document workflows. Teams need reproducible setup, explicit contracts, visible provider decisions, evidence metadata, and deployment paths that can run locally or in controlled infrastructure.

## What It Delivers

| Capability | Value |
|---|---|
| Contract-first bundles | Downstream systems can validate inputs and outputs. |
| Deterministic provider | CI and public examples run without credentials. |
| Provider routing | Local, CT2, local OpenAI-compatible, and optional cloud paths are visible and configurable. |
| Evidence metadata | Jobs can expose custody, quality, review, and provider information. |
| Deployment scaffolding | Python, Docker Compose, Helm, GitOps, and Ansible paths are available. |
| MCP-style tooling | Agent and automation integrations can use a bounded tool surface. |

## Best Fit

- eDiscovery and review pipelines that already have extracted text.
- Multilingual review workflows that need span-level traceability.
- Local model evaluation and runtime smoke testing.
- Batch translation of plain-text folders under operator control.
- Platform teams evaluating Kubernetes deployment shape.

## Not A Fit

- OCR extraction from images.
- Hosted SaaS translation.
- Automatic legal certification.
- Shipping or redistributing model weights.
- Unrestricted public filesystem translation endpoints.

## Readiness Position

The repo is suitable for public evaluation, deterministic local smoke, integration design, and deployment review. Production-like use requires operator-specific auth, store, provider, retention, model, and infrastructure review.
