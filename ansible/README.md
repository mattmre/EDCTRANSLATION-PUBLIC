# EDC_TRANSLATION Deployment Automation

This directory is parameterized production deployment automation. It is intended
to apply the Kubernetes deployment shape without embedding
cluster names, hostnames, cluster credential files, private registries, or
secrets.

## Layout

- `inventory/example.ini` - localhost control-plane inventory for rendering or applying.
- `group_vars/all.yml` - non-secret defaults and production toggles.
- `playbooks/deploy.yml` - entry point for namespace, cache, queue, Helm release, and optional integrations.
- `roles/edc_translation/tasks/main.yml` - Kubernetes and Helm tasks guarded by feature flags.

## Deployment Shape

The automation covers these production concerns:

- namespace creation or reuse through `edc_namespace`
- queue configuration via in-memory defaults or optional Kafka/Strimzi settings
- model cache PVC creation for pre-warmed CT2 model directories
- API Helm release deployment using the existing `helm/edc-translation` chart
- worker and MCP component settings for follow-on charts or templates
- GPU profile selection through explicit, disabled-by-default profiles
- Strimzi Kafka topic and Postgres connection references when enabled

No task creates or stores real credentials. Secret-bearing values are represented
only as existing Kubernetes Secret names and keys that must be created by an
external secret-management workflow.

## Dry Run

An Ansible runtime with `ansible-playbook` on `PATH` is required before any
dry-run or apply command can execute. Verify the local control machine first:

```powershell
ansible-playbook --version
```

Render the default task plan without applying changes:

```powershell
ansible-playbook -i ansible/inventory/example.ini ansible/playbooks/deploy.yml --check --diff
```

Render the split API, worker, and MCP component plan without applying changes:

```powershell
ansible-playbook -i ansible/inventory/example.ini ansible/playbooks/deploy.yml --check --diff --extra-vars "edc_worker={enabled: true, replicas: 1, queue_backend: local} edc_mcp={enabled: true, replicas: 1}"
```

Render the split-component plan with an existing model-cache PVC and a single
GPU profile:

```powershell
ansible-playbook -i ansible/inventory/example.ini ansible/playbooks/deploy.yml --check --diff --extra-vars "edc_model_cache={enabled: true, pvc_name: edc-translation-model-cache} edc_gpu={profile: gpu-1x16}"
```

## Apply

Set environment-specific values in an inventory or extra-vars file outside this
repository, then run:

```powershell
ansible-playbook -i <inventory> ansible/playbooks/deploy.yml
```

Keep environment files with real cluster identifiers or secret references out of
version control.
