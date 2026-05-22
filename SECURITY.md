# Security Policy

## Supported Versions

The public repository is pre-1.0. Security fixes target the latest `main` branch until versioned public releases are cut.

## Reporting A Vulnerability

Use GitHub Security Advisories for private vulnerability reports:

https://github.com/mattmre/EDCTRANSLATION-PUBLIC/security/advisories/new

Please include:

- Affected version or commit.
- Reproduction steps.
- Impacted surface, such as REST API, CLI, Docker image, Helm chart, MCP wrapper, batch text workflow, provider adapter, or dependency.
- Whether the issue requires credentials, live providers, model files, filesystem access, Postgres, Kafka, or Kubernetes access.

Do not include real customer documents, secrets, API keys, private model artifacts, private hostnames, or private infrastructure details in a public issue.

## Security Notes

- Local development defaults to disabled authentication for fast isolated testing.
- Staging and production deployments must set a non-local `EDC_DEPLOYMENT_ENV` and a non-disabled `EDC_AUTH_MODE`.
- Static bearer-token auth stores hashes, not plaintext tokens.
- Live providers are opt-in and should not be used for sensitive data without retention, residency, logging, and terms review.
- Batch file translation reads and writes operator-supplied paths. Do not expose that surface to untrusted users without a deployment-level filesystem policy.

See [Security And Release Readiness](docs/11-SECURITY-AND-RELEASE-READINESS.md) for the broader public-release checklist.
