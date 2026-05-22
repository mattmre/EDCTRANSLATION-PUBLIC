from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_exposes_api():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "uvicorn" in text
    assert "edc_translation.api:app" in text
    assert "COPY schemas ./schemas" in text
    assert "mkdir -p /data/jobs" in text
    assert "chown -R appuser:appuser /app /data" in text


def test_contract_schema_loader_supports_installed_container_workdir():
    contracts = (ROOT / "edc_translation" / "contracts.py").read_text(
        encoding="utf-8"
    )

    assert "PACKAGE_SCHEMA_DIR" in contracts
    assert 'Path(__file__).resolve().parent / "schemas"' in contracts
    assert 'Path.cwd() / "schemas"' in contracts


def test_package_exposes_worker_entrypoint():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'edc-translation-worker = "edc_translation.worker:main"' in text
    assert 'edc-translation-mcp = "edc_translation.mcp:main"' in text
    assert 'edc-translation-mcp-http = "edc_translation.mcp_http:main"' in text


def test_helm_chart_skeleton_present():
    chart = ROOT / "helm" / "edc-translation"
    assert (chart / "Chart.yaml").is_file()
    assert (chart / "values.yaml").is_file()
    assert (chart / "templates" / "deployment.yaml").is_file()
    assert (chart / "templates" / "service.yaml").is_file()


def test_helm_chart_supports_stable_fullname_override():
    values = (ROOT / "helm" / "edc-translation" / "values.yaml").read_text(
        encoding="utf-8"
    )
    helpers = (
        ROOT / "helm" / "edc-translation" / "templates" / "_helpers.tpl"
    ).read_text(encoding="utf-8")

    assert "fullnameOverride" in values
    assert ".Values.fullnameOverride" in helpers


def test_helm_chart_exposes_optional_ct2_engine_config():
    chart = ROOT / "helm" / "edc-translation"
    values = (chart / "values.yaml").read_text(encoding="utf-8")
    deployment = (chart / "templates" / "deployment.yaml").read_text(
        encoding="utf-8"
    )

    assert "localCt2OpusModelDir" in values
    assert "localCt2NllbModelDir" in values
    assert "localCt2MadladModelDir" in values
    assert "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR" in deployment
    assert "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR" in deployment
    assert "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR" in deployment
    assert "EDC_TRANSLATION_CT2_DEVICE" in deployment


def test_helm_chart_exposes_optional_auto_route_smoke_gate():
    chart = ROOT / "helm" / "edc-translation"
    values = (chart / "values.yaml").read_text(encoding="utf-8")
    deployment = (chart / "templates" / "deployment.yaml").read_text(
        encoding="utf-8"
    )

    assert "autoRoute" in values
    assert "enabled: false" in values
    assert "allowNcLicensed: false" in values
    assert ".Values.translation.smoke.autoRoute.enabled" in deployment
    assert "initContainers:" in deployment
    assert "auto-route-smoke" in deployment
    assert "smoke-auto-route" in deployment
    assert ".Values.translation.smoke.autoRoute.source" in deployment
    assert ".Values.translation.smoke.autoRoute.target" in deployment
    assert ".Values.translation.smoke.autoRoute.allowNcLicensed" in deployment
    assert "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR" in deployment


def test_helm_chart_exposes_optional_local_job_store():
    chart = ROOT / "helm" / "edc-translation"
    values = (chart / "values.yaml").read_text(encoding="utf-8")
    deployment = (chart / "templates" / "deployment.yaml").read_text(
        encoding="utf-8"
    )

    assert "localStoreDir" in values
    assert "EDC_TRANSLATION_JOB_STORE_DIR" in deployment
    assert "translation-job-store" in deployment
    assert "emptyDir: {}" in deployment


def test_helm_chart_exposes_split_worker_mcp_and_gpu_profiles():
    chart = ROOT / "helm" / "edc-translation"
    values = (chart / "values.yaml").read_text(encoding="utf-8")
    worker = (chart / "templates" / "worker-deployment.yaml").read_text(
        encoding="utf-8"
    )
    mcp = (chart / "templates" / "mcp-deployment.yaml").read_text(encoding="utf-8")
    mcp_service = (chart / "templates" / "mcp-service.yaml").read_text(
        encoding="utf-8"
    )

    assert "worker:" in values
    assert "mcp:" in values
    assert "modelCache:" in values
    assert "gpuProfile:" in values
    assert "gpu-1x16" in values
    assert "gpu-1x24" in values
    assert ".Values.worker.enabled" in worker
    assert "edc-translation-worker" in values
    assert "EDC_TRANSLATION_MAX_LOADED_MODELS" in worker
    assert ".Values.mcp.enabled" in mcp
    assert "edc-translation-mcp-http" in values
    assert ".Values.mcp.enabled" in mcp_service


def test_helm_chart_exposes_mandatory_platform_surfaces():
    chart = ROOT / "helm" / "edc-translation"
    values = (chart / "values.yaml").read_text(encoding="utf-8")
    prod_values = (chart / "values-production.yaml").read_text(encoding="utf-8")
    staging_values = (chart / "values-staging.yaml").read_text(encoding="utf-8")
    deployment = (chart / "templates" / "deployment.yaml").read_text(
        encoding="utf-8"
    )
    worker = (chart / "templates" / "worker-deployment.yaml").read_text(
        encoding="utf-8"
    )
    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (chart / "templates").glob("*.yaml")
    )

    assert "platform:" in values
    assert "production: false" in values
    assert (chart / "values-production.yaml").is_file()
    assert (chart / "values-staging.yaml").is_file()
    assert "production: true" in prod_values
    assert "environment: approved_staging" in staging_values
    assert "ServiceAccount" in templates
    assert "automountServiceAccountToken" in templates
    assert "RoleBinding" in templates
    assert "NetworkPolicy" in templates
    assert "egressAllowAll: false" in values
    assert "kind: Ingress" in templates
    assert "kind: ScaledObject" in templates
    assert "kind: Cluster" in templates
    assert "kind: Kafka" in templates
    assert "kind: KafkaTopic" in templates
    assert "production profile requires" in templates
    assert '"component" "api"' in deployment
    assert "path: /healthz" in deployment
    assert "path: /readyz" in deployment
    assert "nvidia.com/gpu: 1" in values
    assert "nvidia.com/gpu: 1" in prod_values
    assert "cnpg.io/cluster" in prod_values
    assert "strimzi.io/cluster" in prod_values
    assert "minInSyncReplicas" in values
    assert ".Values.gpuProfile.selected).resources" in worker


def test_helm_default_and_production_profiles_render():
    if shutil.which("helm") is None:
        pytest.skip("helm is not installed")

    chart = ROOT / "helm" / "edc-translation"
    default_render = subprocess.run(
        ["helm", "template", "edc-translation", str(chart)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    blocked_prod = subprocess.run(
        [
            "helm",
            "template",
            "edc-translation",
            str(chart),
            "-f",
            str(chart / "values-production.yaml"),
            "--set",
            "auth.existingSecret=",
        ],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    prod_render = subprocess.run(
        [
            "helm",
            "template",
            "edc-translation",
            str(chart),
            "-f",
            str(chart / "values-production.yaml"),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout

    assert "kind: Deployment" in default_render
    assert "kind: ScaledObject" not in default_render
    assert "kind: Cluster" not in default_render
    assert "kind: Kafka" not in default_render
    assert blocked_prod.returncode != 0
    assert "production profile requires auth.existingSecret" in blocked_prod.stderr
    assert "kind: ScaledObject" in prod_render
    assert "kind: Cluster" in prod_render
    assert "kind: Kafka" in prod_render
    assert "name: EDC_AUTH_MODE" in prod_render
    assert 'value: "jwt_ldap"' in prod_render
    assert 'name: "edc-translation-auth"' in prod_render
    assert "kind: NetworkPolicy" in prod_render
    assert "podSelector: {}" not in prod_render
    assert "\n  egress:\n    - {}\n" not in prod_render
    assert "kind: Ingress" in prod_render
    assert "nvidia.com/gpu: 1" in prod_render


def test_helm_staging_profile_renders_approved_staging_surfaces():
    if shutil.which("helm") is None:
        pytest.skip("helm is not installed")

    chart = ROOT / "helm" / "edc-translation"
    staging_render = subprocess.run(
        [
            "helm",
            "template",
            "edc-translation",
            str(chart),
            "-f",
            str(chart / "values-staging.yaml"),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout

    assert "kind: ScaledObject" in staging_render
    assert "kind: Cluster" in staging_render
    assert "kind: Kafka" in staging_render
    assert "kind: Ingress" not in staging_render
    assert "edc-translation-postgres-daily" not in staging_render
    assert 'value: "jwt_ldap"' in staging_render
    assert "cnpg.io/cluster: edc-translation-postgres" in staging_render
    assert "strimzi.io/cluster: edc-translation-kafka" in staging_render
    assert "min.insync.replicas: 1" in staging_render
    assert "transaction.state.log.min.isr: 1" in staging_render
    assert "nvidia.com/gpu: 1" not in staging_render


def test_gitops_paths_are_kustomize_buildable():
    if shutil.which("kubectl") is None:
        pytest.skip("kubectl is not installed")

    paths = [
        ROOT / "gitops" / "argocd",
        ROOT / "gitops" / "argocd" / "applications",
        ROOT / "gitops" / "operators",
    ]
    renders = [
        subprocess.run(
            ["kubectl", "kustomize", str(path)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        for path in paths
    ]

    assert "kind: AppProject" in renders[0]
    assert "edc-translation-platform" in renders[0]
    assert "edc-translation-staging" in renders[1]
    assert "values-staging.yaml" in renders[1]
    assert "name: cnpg-system" in renders[2]
    assert "name: monitoring" in renders[2]


def test_ansible_deployment_scaffold_is_parameterized():
    ansible_dir = ROOT / "ansible"
    defaults = (ansible_dir / "group_vars" / "all.yml").read_text(
        encoding="utf-8"
    )
    tasks = (
        ansible_dir / "roles" / "edc_translation" / "tasks" / "main.yml"
    ).read_text(encoding="utf-8")
    helm_values_template = (
        ansible_dir
        / "roles"
        / "edc_translation"
        / "templates"
        / "helm-values.yaml.j2"
    ).read_text(encoding="utf-8")

    assert (ansible_dir / "inventory" / "example.ini").is_file()
    assert (ansible_dir / "playbooks" / "deploy.yml").is_file()
    assert "edc_namespace" in defaults
    assert "edc_queue:" in defaults
    assert "edc_model_cache:" in defaults
    assert "edc_worker:" in defaults
    assert "edc_mcp:" in defaults
    assert "edc_auth:" in defaults
    assert "edc_gpu:" in defaults
    assert "edc_strimzi:" in defaults
    assert "edc_postgres:" in defaults
    assert "kubernetes.core.helm" in tasks
    assert "from_yaml" in tasks
    assert "helm-values.yaml.j2" in tasks
    assert "KafkaTopic" in tasks
    assert "PersistentVolumeClaim" in tasks
    assert "worker:" in helm_values_template
    assert "queueBackend" in helm_values_template
    assert "runtimeAdapterVerified" in helm_values_template
    assert "mcp:" in helm_values_template
    assert "runtimeHttpServerVerified" in helm_values_template
    assert "auth:" in helm_values_template
    assert "modelCache:" in helm_values_template
    assert "existingClaim" in helm_values_template
    assert "gpuProfile:" in helm_values_template
    assert "ct2Device" in helm_values_template
    assert "maxLoadedModels" in helm_values_template
    assert "nodeSelector" in helm_values_template
    assert "tolerations" in helm_values_template
    assert "minInSyncReplicas" in helm_values_template
    assert "zookeeper:" in helm_values_template
    assert 'enabled: "{{' not in helm_values_template
    assert "planned but disabled" not in tasks
    assert "local-cpu" in defaults
    assert "gpu-1x16" in defaults
    assert "gpu-1x24" in defaults
    assert "max_loaded_models" in defaults
    assert "service_port: 8081" in defaults
    assert "min_insync_replicas" in defaults
    assert "zookeeper_replicas" in defaults


def test_ansible_scaffold_does_not_embed_cluster_specific_material():
    ansible_dir = ROOT / "ansible"
    forbidden = [
        "kubeconfig",
        "ldap://",
        "ldaps://",
        "password:",
        "private-registry",
        "redacted",
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in ansible_dir.rglob("*")
        if path.is_file()
    )

    for token in forbidden:
        assert token not in combined


def test_ansible_readme_documents_dry_run_runtime_requirement_and_examples():
    readme = (ROOT / "ansible" / "README.md").read_text(encoding="utf-8")

    assert "ansible-playbook --version" in readme
    assert "ansible-playbook` on `PATH` is required" in readme
    assert (
        "ansible-playbook -i ansible/inventory/example.ini "
        "ansible/playbooks/deploy.yml --check --diff"
    ) in readme
    assert (
        '--extra-vars "edc_worker={enabled: true, replicas: 1, '
        'queue_backend: local} edc_mcp={enabled: true, replicas: 1}"'
    ) in readme
    assert (
        '--extra-vars "edc_model_cache={enabled: true, pvc_name: '
        'edc-translation-model-cache} edc_gpu={profile: gpu-1x16}"'
    ) in readme


def test_public_deployment_docs_cover_ansible_dry_run_examples():
    deployment = (ROOT / "docs" / "05-DEPLOYMENT.md").read_text(encoding="utf-8")

    assert "ansible-playbook --version" in deployment
    assert (
        "ansible-playbook -i ansible/inventory/example.ini "
        "ansible/playbooks/deploy.yml --check --diff"
    ) in deployment
    assert "edc_worker" in deployment
    assert "edc_model_cache" in deployment


def test_admin_html_is_static_and_named():
    html = (ROOT / "edc_translation" / "static" / "admin.html").read_text(
        encoding="utf-8"
    )
    assert "<html" in html
    assert "EDC_TRANSLATION" in html
    assert "Submit Text" in html
    assert "Instruction Set" in html
    assert "Review / Certify" in html
    assert "/api/v1/translation/jobs/text" in html


def test_admin_static_asset_is_in_package_data():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.setuptools.package-data]" in pyproject
    assert 'edc_translation = ["static/*.html", "schemas/*.json"]' in pyproject
