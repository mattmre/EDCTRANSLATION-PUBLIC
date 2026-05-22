## Summary

-

## Validation

- [ ] `python -m ruff check edc_translation tests`
- [ ] `PGCONNECT_TIMEOUT=2 python -m pytest -q`
- [ ] `helm lint helm/edc-translation`
- [ ] `helm template edc-translation helm/edc-translation`

## Checklist

- [ ] Public docs updated when behavior, setup, or configuration changed.
- [ ] No secrets, local paths, private model paths, generated evidence, or `.env` files committed.
- [ ] Commit messages do not include AI/LLM `Co-Authored-By:` footers.
