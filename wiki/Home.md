# EDC Translation Wiki

Welcome to the EDC Translation wiki source. These pages are maintained in-tree so they can be reviewed, tested, and copied into GitHub Wiki if the repository owner enables the Wiki feature.

## What EDC Translation Does

EDC Translation provides a contract-first translation layer for structured document workflows. It accepts raw text or `DocumentBundle v1` input and emits `TranslationBundle v1` output with span linkage, provider metadata, quality fields, custody references, and review hooks.

## Fast Paths

| Need | Page |
|---|---|
| Run the project locally | [Getting Started](Getting-Started.md) |
| Understand the system | [Architecture Overview](Architecture-Overview.md) |
| Use REST, CLI, or MCP tools | [API and CLI](API-and-CLI.md) |
| Configure providers and stores | [Configuration](Configuration.md) |
| Operate model/provider paths | [Provider Operations](Provider-Operations.md) |
| Translate folders of text files | [Batch Text Translation](Batch-Text-Translation.md) |
| Deploy beyond local smoke | [Deployment Runbook](Deployment-Runbook.md) |
| Check public-release hygiene | [Security and Release Readiness](Security-and-Release-Readiness.md) |
| Fix common failures | [Troubleshooting](Troubleshooting.md) |
| Answer high-level questions | [FAQ](FAQ.md) |

## Core Principles

- Contracts first: validate input and output payloads.
- Deterministic by default: public examples run without credentials.
- Provider decisions visible: output includes provider identity and metadata.
- Optional live calls: cloud providers require explicit opt-in.
- Deployment-aware: local, Compose, Helm, GitOps, and Ansible paths are documented.

## Primary Docs

The canonical long-form docs live in [`docs/`](../docs/README.md). The wiki is a navigable companion, not a replacement for the numbered documentation suite.
