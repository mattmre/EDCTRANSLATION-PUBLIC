# Deployment Runbook

## Local Python

```bash
python -m pip install -e ".[dev]"
uvicorn edc_translation.api:app --host 127.0.0.1 --port 8080
```

## Local Compose

```bash
docker compose -f docker-compose.local.yml up --build
```

## Staging-Like Compose

```bash
export EDC_TRANSLATION_POSTGRES_PASSWORD=local-dev-password
export EDC_JWT_SECRET=local-dev-jwt-secret
docker compose -f docker-compose.prod.yml up --build
```

Use this path to validate auth and durable-store behavior on one machine.

## Helm

```bash
helm lint helm/edc-translation
helm template edc-translation helm/edc-translation
helm template edc-translation helm/edc-translation -f helm/edc-translation/values-staging.yaml
```

## Ansible Dry Run

```bash
ansible-playbook --version
ansible-playbook -i ansible/inventory/example.ini ansible/playbooks/deploy.yml --check --diff
```

## Promotion Gates

- Local deterministic smoke passes.
- Compose config validates.
- Helm lint/template passes.
- Non-local auth is not disabled.
- Store and queue backends are intentionally selected.
- Provider paths are reviewed.
- Release-readiness evidence is available.
