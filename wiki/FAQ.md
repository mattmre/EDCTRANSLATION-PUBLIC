# FAQ

## Is this an OCR engine?

No. EDC Translation consumes text or document-span bundles. It does not extract text from images.

## Does the repo ship model weights?

No. Model weights and local runtimes are operator-managed.

## What provider should I use first?

Use `deterministic_ci` for initial tests and public examples.

## Can I use cloud providers?

Yes, but only after configuring credentials, enabling live smoke, and reviewing provider terms, retention, residency, logging, cost, and quality.

## What is `DocumentBundle v1`?

It is the input JSON contract carrying document identity, pages, source spans, language metadata, custody fields, and artifact references.

## What is `TranslationBundle v1`?

It is the output JSON contract carrying translated spans, provider metadata, model provenance, quality fields, custody fields, and review/evidence references.

## Why does auto-route fail?

Auto-route fails closed when it cannot select a configured, policy-allowed provider. Run routing diagnostics or choose an explicit provider.

## Can this run in Kubernetes?

Yes. Use Helm for rendering and deployment, GitOps scaffolding for Argo CD, and Ansible for inventory-driven automation.

## Where is the full documentation?

Start with [docs/README.md](../docs/README.md).
