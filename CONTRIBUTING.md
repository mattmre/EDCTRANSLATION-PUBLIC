# Contributing

Thanks for helping improve EDC Translation. This repository is intended to stay usable from a clean clone, so public contributions should include tests or documentation updates for behavior changes.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Validation

```bash
python -m ruff check edc_translation tests
PGCONNECT_TIMEOUT=2 python -m pytest -q
helm lint helm/edc-translation
helm template edc-translation helm/edc-translation
```

Run focused tests when changing one surface, then run the full suite before opening a PR.

## Pull Request Rules

- Keep changes scoped to one feature, fix, or documentation topic.
- Add or update tests for behavior changes.
- Update public docs when setup, API behavior, deployment, config, contracts, or provider behavior changes.
- Do not commit secrets, `.env` files, local paths, private model paths, generated evidence, or local runtime artifacts.
- Do not include AI/LLM `Co-Authored-By:` footers in commit messages.
- Keep public examples deterministic unless the PR is specifically about optional provider configuration.

## Documentation Rules

- Update [docs/README.md](docs/README.md) when adding a new canonical doc.
- Update [wiki/Home.md](wiki/Home.md) and [_Sidebar](wiki/_Sidebar.md) when wiki-facing guidance changes.
- Use Mermaid diagrams for architecture and workflow changes.
- Prefer tables for endpoints, config, providers, and deployment choices.

## Issue Triage

Use bug reports for reproducible failures, feature requests for product changes, and Discussions for design questions or setup help.
