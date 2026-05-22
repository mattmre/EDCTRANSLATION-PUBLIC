# Troubleshooting

## Fast Check

```bash
edc-translation list-engines
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
PGCONNECT_TIMEOUT=2 python -m pytest -q
```

## Common Issues

| Symptom | Fix |
|---|---|
| CLI not found | Activate the virtual environment and reinstall editable package. |
| Auto-route unavailable | Use `deterministic_ci` or configure a local provider. |
| Live smoke blocked | Set credentials and `EDC_TRANSLATION_LIVE_SMOKE=1`. |
| Job not found | Confirm store backend and process lifetime. |
| Bundle conflict | Wait for job completion or inspect job failure. |
| Docker port conflict | Change host ports or stop the conflicting process. |
| Helm render fails | Review values indentation and required secret references. |

## When Asking For Help

Include OS, Python version, install method, command, provider ID, backend selection, Docker/Helm involvement, and sanitized error output.
