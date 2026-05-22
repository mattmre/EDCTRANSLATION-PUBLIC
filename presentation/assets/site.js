const navItems = [
  ["index.html", "Overview", "home"],
  ["executive-summary.html", "Executive", "executive"],
  ["technical-brief.html", "Technical", "technical"],
  ["use-cases.html", "Use Cases", "usecases"],
  ["architecture.html", "Architecture", "architecture"],
  ["white-paper.html", "White Paper", "whitepaper"],
  ["slides.html", "Slides", "slides"],
];

function header(activePage) {
  const links = navItems
    .map(([href, label, key]) => {
      const isActive = key === activePage;
      return `<a href="${href}" class="${isActive ? "active" : ""}"${isActive ? ' aria-current="page"' : ""}>${label}</a>`;
    })
    .join("");
  return `
    <header class="header">
      <div class="container header-inner">
        <a class="logo" href="index.html">EDC<span>Translation</span></a>
        <nav class="nav" aria-label="Presentation navigation">${links}</nav>
      </div>
    </header>
  `;
}

function footer() {
  return `
    <footer class="footer">
      <div class="container">
        <div class="footer-links">
          <a href="../README.md">README</a>
          <a href="../docs/README.md">Docs Index</a>
          <a href="../docs/API-REFERENCE.md">API Reference</a>
          <a href="../docs/DEPLOYMENT-DECISION-GUIDE.md">Deployment Guide</a>
          <a href="../CHANGELOG.md">Changelog</a>
        </div>
        <p>EDC Translation is a contract-first translation control plane for structured document workflows.</p>
      </div>
    </footer>
  `;
}

function badges(items) {
  return `<div class="badge-row">${items.map((item) => `<span class="badge">${item}</span>`).join("")}</div>`;
}

function ctas(items) {
  return `<div class="btn-row">${items.map(([href, label, kind]) => `<a class="btn ${kind || "btn-secondary"}" href="${href}">${label}</a>`).join("")}</div>`;
}

function card(icon, title, body) {
  return `<article class="card"><span class="card-icon">${icon}</span><h3>${title}</h3><p>${body}</p></article>`;
}

function kpi(value, label) {
  return `<div class="kpi"><div class="kpi-value">${value}</div><div class="kpi-label">${label}</div></div>`;
}

function table(headers, rows) {
  return `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("")}</tbody></table></div>`;
}

function diagram(title, source) {
  return `<figure class="diagram" aria-label="${title} diagram"><figcaption>${title}</figcaption><p class="sr-only">Diagram: ${title}. The surrounding section describes the same architecture and workflow in text.</p><div class="mermaid">${source.trim()}</div></figure>`;
}

function codeBlock(label, source) {
  return `<span class="code-label">${label}</span><pre><code>${source.trim()}</code></pre>`;
}

const diagrams = {
  pipeline: `
flowchart LR
  A["DocumentBundle v1 or raw text"] --> B["Schema validation"]
  B --> C["Text and span normalization"]
  C --> D["Tenant and provider policy"]
  D --> E["Provider routing"]
  E --> F1["Deterministic CI"]
  E --> F2["Passthrough"]
  E --> F3["Local CT2"]
  E --> F4["Local OpenAI-compatible"]
  E --> F5["Optional cloud adapter"]
  F1 --> G["TranslationBundle v1"]
  F2 --> G
  F3 --> G
  F4 --> G
  F5 --> G
  G --> H["Review, search, export, evidence"]
  `,
  control: `
flowchart TB
  Client["REST, CLI, Python, MCP, Admin UI"] --> Auth["Auth, tenant binding, scopes"]
  Auth --> Service["Translation service layer"]
  Service --> Contracts["JSON Schema contracts"]
  Service --> Policy["Tenant policy, glossaries, instruction sets"]
  Service --> Router["Routing diagnostics and auto-route"]
  Router --> Engines["Translation engines"]
  Service --> Jobs["Job repository and queue"]
  Service --> Evidence["Custody, quality, review metadata"]
  Jobs --> Store["Memory, file, Postgres"]
  Jobs --> Queue["Local, Postgres, Kafka"]
  `,
  deployment: `
flowchart TB
  subgraph Local["Local workstation"]
    CLI["CLI and Python client"]
    API0["FastAPI dev server"]
    Mock["Mock OpenAI-compatible runtime"]
  end
  subgraph Compose["Docker Compose"]
    API["API service"]
    MCP["MCP HTTP service"]
    Worker["Worker"]
    PG["Postgres"]
    Kafka["Redpanda Kafka"]
  end
  subgraph Cluster["Kubernetes"]
    Ingress["Ingress"]
    ApiPods["API pods"]
    WorkerPods["Worker pods"]
    McpPods["MCP pods"]
    CNPG["CNPG Postgres"]
    Strimzi["Strimzi Kafka"]
    KEDA["KEDA scaling"]
    GitOps["Argo CD GitOps"]
  end
  CLI --> API0 --> API
  API --> PG
  API --> Kafka
  API --> Worker
  Ingress --> ApiPods
  ApiPods --> CNPG
  ApiPods --> Strimzi
  WorkerPods --> CNPG
  WorkerPods --> Strimzi
  KEDA --> WorkerPods
  GitOps --> ApiPods
  GitOps --> WorkerPods
  GitOps --> McpPods
  `,
  sequence: `
sequenceDiagram
  participant Caller
  participant API
  participant Service
  participant Engine
  participant Store
  Caller->>API: POST /api/v1/translation/jobs/text
  API->>Service: Normalize raw text
  Service->>Engine: Translate spans
  Engine-->>Service: Translated spans and provider metadata
  Service->>Store: Save job status and bundle
  Store-->>API: Job record
  API-->>Caller: 202 Accepted with job id
  `,
  trust: `
flowchart LR
  Caller["Caller or automation"] --> Auth["Auth and tenant boundary"]
  Auth --> Service["Contract-first service"]
  Service --> Data["Durable data boundary"]
  Service --> Router["Provider policy boundary"]
  Router --> Local["Local model/runtime"]
  Router --> Cloud["Optional external provider"]
  Service --> Review["Review and evidence metadata"]
  Data --> Audit["Token, audit, job, result, model state"]
  `,
};

const pages = {
  home: `
    <main>
      <section class="page-hero">
        <div class="container">
          ${badges(["v0.1.0", "MIT", "Python 3.11+", "FastAPI", "DocumentBundle v1", "TranslationBundle v1"])}
          <h1>Contract-first translation for document pipelines.</h1>
          <p class="lead">EDC Translation turns multilingual document translation into a governed control plane. It validates structured inputs, applies provider policy, routes to approved engines, and emits review-ready <code>TranslationBundle v1</code> output for downstream search, review, and export systems.</p>
          ${ctas([
            ["#quickstart", "Quick Start", "btn-primary"],
            ["technical-brief.html", "Technical Brief"],
            ["architecture.html", "Architecture"],
            ["white-paper.html", "White Paper"],
          ])}
          <img class="hero-visual" src="../.github/social-preview.png" alt="EDC Translation public preview">
        </div>
      </section>

      <section class="section" id="why">
        <div class="container">
          <div class="section-kicker">Why it exists</div>
          <h2>Translation as infrastructure, not a loose provider call.</h2>
          <p class="lead">Most translation integrations stop at text-in and text-out. Document workflows need more: source span identity, provider metadata, tenant policy, local smoke paths, review state, and deployable service surfaces.</p>
          <div class="grid grid-3">
            ${card("[CONTRACT]", "Contract-first I/O", "Consumes <code>DocumentBundle v1</code> and emits <code>TranslationBundle v1</code> so integrations can validate both sides of the boundary.")}
            ${card("[ROUTE]", "Provider-governed routing", "Routes through deterministic, passthrough, CT2, local OpenAI-compatible, and optional cloud adapters with explicit policy checks.")}
            ${card("[LOCAL]", "Local-first operation", "Deterministic and mock local paths let teams test without API keys, cloud calls, or model downloads.")}
            ${card("[REVIEW]", "Review-ready metadata", "Preserves job, provider, quality, custody, certification, and evidence metadata for downstream operators.")}
            ${card("[BATCH]", "Batch and service modes", "Supports raw text, document bundles, recursive text-folder translation, REST, CLI, Python, and MCP-style tools.")}
            ${card("[DEPLOY]", "Platform deployment path", "Ships Docker, Compose, Helm, GitOps, and Ansible surfaces for staged adoption.")}
          </div>
        </div>
      </section>

      <section class="section">
        <div class="container">
          <div class="section-kicker">By the numbers</div>
          <h2>Concrete public surfaces.</h2>
          <div class="kpi-grid">
            ${kpi("2", "Primary JSON contracts")}
            ${kpi("4", "Access surfaces: REST, CLI, Python, MCP")}
            ${kpi("9", "Registered engine IDs")}
            ${kpi("13", "MCP-style tools")}
            ${kpi("339", "Language catalog entries")}
            ${kpi("200", "NLLB capability count")}
            ${kpi("419", "MADLAD-family capability count")}
            ${kpi("0", "Cloud calls required by default")}
          </div>
        </div>
      </section>

      <section class="section" id="architecture">
        <div class="container">
          <div class="section-kicker">Information flow</div>
          <h2>One narrow path from input to reviewed output.</h2>
          <p class="lead">The service keeps the translation decision visible. Validation, normalization, policy, routing, provider execution, bundle assembly, and review metadata are separate steps.</p>
          ${diagram("Translation pipeline", diagrams.pipeline)}
          <div class="pipeline">
            <div class="pipeline-stage"><div class="stage-num">01</div><div class="stage-name">Input</div><div class="stage-note">Text or bundle</div></div>
            <div class="pipeline-stage"><div class="stage-num">02</div><div class="stage-name">Validate</div><div class="stage-note">Schema checks</div></div>
            <div class="pipeline-stage"><div class="stage-num">03</div><div class="stage-name">Policy</div><div class="stage-note">Tenant controls</div></div>
            <div class="pipeline-stage"><div class="stage-num">04</div><div class="stage-name">Route</div><div class="stage-note">Provider choice</div></div>
            <div class="pipeline-stage"><div class="stage-num">05</div><div class="stage-name">Translate</div><div class="stage-note">Engine execution</div></div>
            <div class="pipeline-stage"><div class="stage-num">06</div><div class="stage-name">Bundle</div><div class="stage-note">Review output</div></div>
          </div>
        </div>
      </section>

      <section class="section" id="suite">
        <div class="container">
          <div class="section-kicker">Presentation suite</div>
          <h2>Briefings for every evaluator.</h2>
          <div class="grid grid-3">
            ${card("[EXEC]", "Executive summary", "Decision-maker overview of the product boundary, risk controls, use cases, and deployment posture.")}
            ${card("[TECH]", "Technical brief", "Detailed service architecture, schema contracts, provider strategy, API surface, queues, storage, and auth.")}
            ${card("[USE]", "Use cases", "Seven practical scenarios with personas, workflows, acceptance criteria, best-fit cases, and non-fit cases.")}
            ${card("[ARCH]", "Architecture", "Mermaid-heavy walkthrough of data flow, control plane, deployment topology, trust boundaries, and storage modes.")}
            ${card("[PAPER]", "White paper", "Structured technical narrative covering motivation, contracts, provider governance, security, deployment, and limits.")}
            ${card("[DECK]", "Slides", "A 15-slide stakeholder deck with keyboard navigation, diagrams, and compact speaker-ready bullets.")}
          </div>
        </div>
      </section>

      <section class="section" id="quickstart">
        <div class="container">
          <div class="section-kicker">5-minute success path</div>
          <h2>Run a deterministic translation without external services.</h2>
          ${codeBlock("PowerShell", `py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
uvicorn edc_translation.api:app --host 127.0.0.1 --port 8080`)}
          <div class="grid grid-3">
            ${card("[PY]", "Python and CLI", "Fastest feedback loop for contract tests, local examples, and API exploration.")}
            ${card("[DOCKER]", "Compose smoke stack", "Runs API, MCP HTTP, mock OpenAI-compatible runtime, Postgres, and Redpanda on localhost-bound ports.")}
            ${card("[K8S]", "Helm and GitOps", "Renders API, worker, MCP, durable stores, ingress, network policy, and scaling components for cluster evaluation.")}
          </div>
        </div>
      </section>
    </main>
  `,

  executive: `
    <main>
      <section class="page-hero">
        <div class="container">
          ${badges(["Executive Summary", "Contract-first", "Local + Kubernetes", "5 minute read"])}
          <h1>Translation that keeps its contract.</h1>
          <p class="lead">EDC Translation is not trying to be the translation model. It is the governed translation control plane around models and providers: validate the input, enforce policy, preserve metadata, and return a bundle downstream systems can trust.</p>
          ${ctas([
            ["technical-brief.html", "Technical Brief", "btn-primary"],
            ["use-cases.html", "Use Cases"],
            ["../docs/00-SYSTEM-BLUEPRINT.md", "System Blueprint"],
          ])}
        </div>
      </section>

      <section class="section">
        <div class="container">
          <h2>The executive case.</h2>
          <p class="quote">Provider APIs return translated strings. EDC Translation returns a governed artifact: validated contracts, provider metadata, policy decisions, job state, quality signals, and review hooks.</p>
          <div class="grid grid-4">
            ${card("[01]", "Contract-first translation", "The source and target envelopes are versioned JSON contracts, not incidental application payloads.")}
            ${card("[02]", "Policy-aware provider routing", "Provider choice is explicit, explainable, and bound to tenant, license, and deployment controls.")}
            ${card("[03]", "Local-first assurance", "The deterministic provider and local runtimes support repeatable testing before any optional cloud path is enabled.")}
            ${card("[04]", "Deployment path, not demo code", "The repo includes REST, CLI, Python, MCP, batch, Docker, Helm, GitOps, and Ansible surfaces.")}
          </div>
        </div>
      </section>

      <section class="section">
        <div class="container">
          <h2>What changes for the organization?</h2>
          ${table(["Question", "Loose provider call", "EDC Translation"], [
            ["Can downstream tools validate output?", "Usually no; output shape is provider-specific.", "Yes; output is <code>TranslationBundle v1</code>."],
            ["Can CI run without credentials?", "Usually no or requires mocks.", "Yes; <code>deterministic_ci</code> is built in."],
            ["Can provider selection be audited?", "Often hidden in app code.", "Yes; routing and provider metadata are surfaced."],
            ["Can local-only operation be evaluated?", "Depends on the provider.", "Yes; passthrough, deterministic, CT2, and local OpenAI-compatible paths exist."],
            ["Can agents/tools integrate without bypassing policy?", "Rarely first-class.", "Yes; MCP-style tools call the same service layer."],
            ["Can a platform team deploy it?", "Usually custom work.", "Yes; Compose, Helm, GitOps, and Ansible are included."],
          ])}
        </div>
      </section>

      <section class="section">
        <div class="container">
          <h2>Where it fits.</h2>
          <div class="grid grid-3">
            ${card("[DISCOVERY]", "eDiscovery translation", "Translate extracted document spans while preserving page, span, hash, provider, and review context.")}
            ${card("[REVIEW]", "Review platform integration", "Expose predictable REST, CLI, Python, and MCP-style surfaces to review tools and automation.")}
            ${card("[LOCAL]", "Local model evaluation", "Compare deterministic, passthrough, CT2, and local OpenAI-compatible providers before cloud adoption.")}
            ${card("[BATCH]", "Batch text operations", "Process folders of text files with encoding controls, mirrored output paths, logs, manifests, and sidecars.")}
            ${card("[MODEL]", "Model governance", "Validate local model bundles, capture provider metadata, and fail closed when routes are unavailable.")}
            ${card("[PLATFORM]", "Staged deployment", "Move from virtualenv to Compose to Helm-rendered Kubernetes with clear readiness gates.")}
          </div>
        </div>
      </section>

      <section class="section">
        <div class="container split">
          <div>
            <h2>Executive assurance controls.</h2>
            <ul>
              <li>Cloud providers are optional and require explicit configuration.</li>
              <li>Non-commercial license paths are blocked unless policy explicitly allows them.</li>
              <li>Auto-route failures return stable diagnostics instead of silent fallback.</li>
              <li>Live smoke checks require explicit live-provider opt in.</li>
              <li>The deterministic provider gives every integration a repeatable baseline.</li>
              <li>OCR extraction remains outside this project boundary; translation starts from text or structured bundles.</li>
            </ul>
          </div>
          <div class="panel">
            <h3>Recommended evaluation path</h3>
            <ol>
              <li>Run the deterministic quickstart.</li>
              <li>Submit the public fixture bundle.</li>
              <li>Inspect provider metadata and quality output.</li>
              <li>Render Helm values for the target topology.</li>
              <li>Add approved local models or live-provider credentials only after policy review.</li>
            </ol>
          </div>
        </div>
      </section>
    </main>
  `,

  technical: `
    <main>
      <section class="page-hero">
        <div class="container">
          ${badges(["Technical Brief", "v0.1.0", "Python 3.11+", "FastAPI", "13 MCP tools"])}
          <h1>Technical brief.</h1>
          <p class="lead">For engineers, SREs, and integrators. This is the service boundary, runtime stack, provider strategy, data model, deployment topology, and the operational controls that keep translation predictable.</p>
          <nav class="toc">
            <a href="#boundary">Boundary</a>
            <a href="#contracts">Contracts</a>
            <a href="#providers">Providers</a>
            <a href="#api">API and CLI</a>
            <a href="#jobs">Jobs and storage</a>
            <a href="#deployment">Deployment</a>
          </nav>
        </div>
      </section>

      <section class="section" id="boundary">
        <div class="container">
          <h2>1. System boundary.</h2>
          <p class="lead">EDC Translation is deliberately narrow: it translates text-bearing bundles and raw text. It does not perform OCR, manage human translation vendors, host production infrastructure, or ship model weights.</p>
          ${table(["In scope", "Out of scope"], [
            ["<code>DocumentBundle v1</code> ingestion", "OCR extraction and page rendering"],
            ["<code>TranslationBundle v1</code> output", "Human translation workflow management"],
            ["REST, CLI, Python, MCP-style access", "Managed hosted translation SaaS"],
            ["Deterministic and configurable provider engines", "Bundled model weights"],
            ["Local, Docker, Kubernetes, GitOps, Ansible deployment surfaces", "Provider contract negotiation"],
          ])}
          ${diagram("Control plane", diagrams.control)}
        </div>
      </section>

      <section class="section" id="contracts">
        <div class="container">
          <h2>2. Primary contracts.</h2>
          <div class="grid grid-2">
            ${card("[INPUT]", "DocumentBundle v1", "The source envelope for documents and spans. It carries document identity, source text spans, page references, hashes, language metadata, OCR engine metadata, custody references, and artifact manifest entries.")}
            ${card("[OUTPUT]", "TranslationBundle v1", "The translated envelope. It carries translated spans, provider metadata, model provenance, quality scores, certification state, source hashes, custody references, and artifact manifest entries.")}
          </div>
          ${table(["Contract file", "Purpose"], [
            ["<code>schemas/document-bundle-v1.schema.json</code>", "Validates structured document input and source span geometry."],
            ["<code>schemas/translation-bundle-v1.schema.json</code>", "Validates translated output, provider metadata, provenance, quality, and review state."],
            ["<code>edc_translation/contracts.py</code>", "Loads packaged schemas and validates payloads using JSON Schema Draft 7."],
          ])}
        </div>
      </section>

      <section class="section" id="providers">
        <div class="container">
          <h2>3. Translation engine strategy.</h2>
          ${table(["Engine family", "Role", "Notes"], [
            ["<code>deterministic_ci</code>", "Tests and examples", "Repeatable output with no network, credentials, or model downloads."],
            ["<code>passthrough</code>", "Same-language preservation", "Useful for routing and no-op cases."],
            ["CT2 OPUS/NLLB/MADLAD", "Optional local NMT", "Requires approved local model directories and tokenizer assets."],
            ["Local OpenAI-compatible", "Optional local runtime", "Uses <code>/v1/models</code> and <code>/v1/chat/completions</code> compatible servers."],
            ["OpenRouter/Gemini", "Optional live providers", "Requires credentials and explicit live-smoke opt in."],
          ])}
          <div class="grid grid-3">
            ${card("[LICENSE]", "License-aware routing", "Non-commercial providers are blocked by default unless the caller explicitly allows them.")}
            ${card("[READY]", "Readiness diagnostics", "Auto-route readiness reports why a route can or cannot serve a language pair.")}
            ${card("[SMOKE]", "Live smoke gates", "Tiny provider smoke checks run only when live-provider configuration is explicitly enabled.")}
          </div>
        </div>
      </section>

      <section class="section" id="api">
        <div class="container">
          <h2>4. API, CLI, and MCP surfaces.</h2>
          ${table(["Surface", "Examples"], [
            ["Health", "<code>/health</code>, <code>/healthz</code>, <code>/readyz</code>"],
            ["Translation", "<code>POST /api/v1/translation/jobs/text</code>, <code>POST /api/v1/translation/jobs/bundle</code>, <code>GET /jobs/{job_id}/bundle</code>"],
            ["Provider operations", "<code>/engines</code>, <code>/languages</code>, <code>/routing/diagnostics</code>, <code>/models/validate</code>, <code>/live-smoke</code>"],
            ["Governance", "<code>/tenant-policy/{tenant_id}</code>, <code>/glossaries</code>, <code>/instruction-sets</code>, <code>/reviews</code>"],
            ["MCP-style tools", "<code>translation_submit_text</code>, <code>translation_get_bundle</code>, <code>translation_validate_model_bundle</code>, <code>translation_release_readiness_status</code>"],
          ])}
          ${codeBlock("CLI examples", `edc-translation list-engines
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci
edc-translation translate tests/fixtures/edc_contracts/document-bundle-v1.valid.json --target fr --provider deterministic_ci
edc-translation score-pair --source source.txt --target translated.txt
edc-translation verify-model-bundle ./models/opus-en-fr`)}
        </div>
      </section>

      <section class="section" id="jobs">
        <div class="container">
          <h2>5. Jobs, queues, and storage.</h2>
          <div class="grid grid-3">
            ${card("[LOCAL]", "Local/in-memory", "Fastest mode for development, tests, and deterministic examples.")}
            ${card("[FILE]", "File-backed job state", "Local durable job files through configured store directories.")}
            ${card("[POSTGRES]", "Postgres-backed stores", "Durable jobs, queue state, token/audit store, model registry, results, and evidence bundles.")}
            ${card("[KAFKA]", "Kafka fanout", "Optional high-throughput worker fanout with job, segment, result, event, and dead-letter topics.")}
            ${card("[WORKER]", "Worker process", "Runs local, Postgres, or Kafka queue backends with health port and model-profile options.")}
            ${card("[REVIEW]", "Review and evidence", "Tracks submitted content, provider choice, output bundle, review decisions, and local evidence metadata.")}
          </div>
          ${diagram("Synchronous text submission", diagrams.sequence)}
        </div>
      </section>

      <section class="section" id="deployment">
        <div class="container">
          <h2>6. Deployment topology.</h2>
          ${diagram("Local to cluster topology", diagrams.deployment)}
          <div class="grid grid-3">
            ${card("[DEV]", "Python editable install", "Fast local API, CLI, tests, and deterministic provider work.")}
            ${card("[COMPOSE]", "Docker Compose", "Local smoke stack and staging-like durable validation with auth enforcement.")}
            ${card("[HELM]", "Helm and Kubernetes", "API, worker, MCP, CNPG, Strimzi, KEDA, ingress, network policy, and model cache options.")}
            ${card("[GITOPS]", "Argo CD", "Application scaffolding for platform teams to wire into GitOps promotion.")}
            ${card("[ANSIBLE]", "Ansible", "Parameterized deployment automation for Helm and runtime overrides.")}
            ${card("[AUTH]", "Deployment-aware auth", "Disabled auth is local-only; staging and production-like deployments require explicit auth configuration.")}
          </div>
        </div>
      </section>
    </main>
  `,

  usecases: `
    <main>
      <section class="page-hero">
        <div class="container">
          ${badges(["7 scenarios", "Personas", "Workflows", "Acceptance criteria", "Non-fit cases"])}
          <h1>Where EDC Translation fits.</h1>
          <p class="lead">Best-fit scenarios for governed document translation: stable contracts, provider routing, local-first execution, quality metadata, and operational controls across API, CLI, MCP, batch, and Kubernetes surfaces.</p>
        </div>
      </section>

      <section class="section">
        <div class="container">
          ${[
            ["Scenario 01", "Developer contract smoke testing", "A developer needs to prove an upstream extraction system can emit valid <code>DocumentBundle v1</code> and downstream systems can consume <code>TranslationBundle v1</code> without standing up external providers.", "Run deterministic translation through CLI or API, validate output against schema, assert span/page/hash preservation, and use the result as a downstream fixture.", "CI contract tests, local development, and regression fixtures.", "Human-quality translation evaluation; deterministic output is for contract stability."],
            ["Scenario 02", "Local API integration", "A product team wants translation behind a stable service facade without coupling directly to a provider API.", "Run FastAPI locally, submit raw text or bundles, poll job status, inspect engine metadata, and promote the same path to approved provider routes.", "Review platforms, case systems, records applications, and automation services.", "One-off scripts where no contract, routing, provenance, or job lifecycle is needed."],
            ["Scenario 03", "Operator batch text translation", "An operator needs to translate folders of text files while preserving relative paths, encodings, logs, manifests, and optional JSON sidecars.", "Select source/output folders, target language, provider, encodings, and file extensions; run through admin UI or REST; review mirrored output and logs.", "Controlled local folder translation, migration batches, plain-text exports, and review sets.", "Visual document reconstruction or desktop publishing workflows."],
            ["Scenario 04", "Model owner provider evaluation", "A model owner needs to compare deterministic, local CT2, local OpenAI-compatible, OpenRouter, Gemini, or future provider paths under one governance surface.", "Configure candidates, run licensed smoke checks, capture provider metadata, validate model bundles, and promote only approved routes.", "Provider comparison, local model approval, quality studies, and deployment readiness evidence.", "Ad hoc benchmarking that ignores dataset license, model license, residency, or retention policy."],
            ["Scenario 05", "Governed document translation", "A regulated team needs translated text traceable to source spans, pages, bounding boxes, hashes, provider identity, and review metadata.", "Receive <code>DocumentBundle v1</code>, translate spans through approved routes, preserve source alignment, and emit <code>TranslationBundle v1</code> for review and export.", "eDiscovery translation, public records, multilingual review, and compliance archives.", "Consumer chat translation where losing source alignment is acceptable."],
            ["Scenario 06", "Kubernetes platform packaging", "A platform team needs API, worker, MCP, queue, storage, model runtime, and GitOps concerns separated cleanly.", "Render Helm values, configure API/worker/MCP/Postgres/Kafka/auth/model endpoints, run readiness gates, and wire Argo CD or Ansible.", "Organization-operated translation services, local GPU model serving, staging promotion, and regulated environments.", "Fully managed SaaS translation where the organization does not want to operate service infrastructure."],
            ["Scenario 07", "MCP and agent workflow integration", "An agent or toolchain needs translation as a typed capability without bypassing policy, job state, or output contracts.", "List engines, submit text or bundles, poll status, retrieve bundles, inspect evidence, and keep agent behavior constrained by provider policy.", "Review assistants, records automation, knowledge-management tools, and governed agent workflows.", "Autonomous publication of translated content without review or quality gates."],
          ].map(([tag, title, problem, workflow, best, notFit]) => `
            <article class="scenario">
              <div class="scenario-meta">${tag}</div>
              <h2>${title}</h2>
              <div class="grid grid-2">
                <div>
                  <h3>The problem</h3>
                  <p>${problem}</p>
                  <h3>Workflow</h3>
                  <p>${workflow}</p>
                </div>
                <div>
                  <h3>Best fit</h3>
                  <p>${best}</p>
                  <h3>Not a fit</h3>
                  <p>${notFit}</p>
                </div>
              </div>
            </article>`).join("")}
        </div>
      </section>

      <section class="section">
        <div class="container split">
          <div>
            <h2>General acceptance criteria.</h2>
            <ul>
              <li>Inputs and outputs validate against published JSON schemas.</li>
              <li>Every translated span remains traceable to a source span and page where the input provides that structure.</li>
              <li>Provider and model metadata are represented explicitly.</li>
              <li>Cloud providers remain optional and gated behind configuration and policy.</li>
              <li>Unavailable routes fail closed with diagnostics that callers can test.</li>
              <li>Review and certification state are represented explicitly rather than implied.</li>
            </ul>
          </div>
          <div class="panel">
            <h3>Strongest fit</h3>
            <p>Use EDC Translation when translation must remain tied to contracts, source structure, provider choice, deployment posture, and review metadata.</p>
            <h3>Weakest fit</h3>
            <p>Do not use it when the only requirement is casual sentence translation with no provenance, review, or operational constraints.</p>
          </div>
        </div>
      </section>
    </main>
  `,

  architecture: `
    <main>
      <section class="page-hero">
        <div class="container">
          ${badges(["Architecture", "Mermaid diagrams", "Control plane", "Deployment", "Trust boundaries"])}
          <h1>Architecture walkthrough.</h1>
          <p class="lead">Component-by-component tour of EDC Translation: entry surfaces, schema validation, policy, provider routing, engines, jobs, stores, queues, review metadata, and deployment boundaries.</p>
          <nav class="toc">
            <a href="#data-flow">Data flow</a>
            <a href="#control-plane">Control plane</a>
            <a href="#deployment">Deployment</a>
            <a href="#trust">Trust boundaries</a>
            <a href="#storage">Storage modes</a>
            <a href="#failure">Failure modes</a>
          </nav>
        </div>
      </section>

      <section class="section" id="data-flow">
        <div class="container">
          <h2>1. Translation data flow.</h2>
          <p class="lead">All entry surfaces converge on the same service layer. That is the point: API users, CLI users, Python callers, MCP tools, and the admin UI all get the same contract validation and provider policy.</p>
          ${diagram("End-to-end data flow", diagrams.pipeline)}
          ${table(["Step", "Responsibility", "Output"], [
            ["Input", "Accept raw text or a <code>DocumentBundle v1</code> payload.", "Normalized source envelope."],
            ["Validation", "Validate JSON contracts and request shape.", "Typed errors or accepted work item."],
            ["Policy", "Bind tenant, license, provider, glossary, and instruction constraints.", "Allowed route set."],
            ["Routing", "Select explicit provider or diagnose auto-route readiness.", "Provider execution plan."],
            ["Engine", "Translate spans through deterministic, local, or optional live provider.", "Translated spans plus provider metadata."],
            ["Bundle", "Assemble and validate <code>TranslationBundle v1</code>.", "Review-ready output artifact."],
          ])}
        </div>
      </section>

      <section class="section" id="control-plane">
        <div class="container">
          <h2>2. Control plane.</h2>
          <p>The non-translation controls are first-class: language catalog, engine list, routing diagnostics, tenant policy, glossaries, instruction sets, model validation, local model ranking, live smoke checks, review decisions, token store, audit store, and release-readiness checks.</p>
          ${diagram("Control plane map", diagrams.control)}
        </div>
      </section>

      <section class="section" id="deployment">
        <div class="container">
          <h2>3. Deployment topology.</h2>
          <p>Local and platform deployments share the same image and service modules. The deployment surface decides persistence, queue, auth, model runtime, ingress, and scaling behavior.</p>
          ${diagram("Deployment topology", diagrams.deployment)}
          <div class="grid grid-3">
            ${card("[LOCAL]", "Developer workstation", "Virtualenv, deterministic provider, FastAPI, CLI, and static admin page.")}
            ${card("[COMPOSE]", "Compose stack", "API, MCP HTTP, mock OpenAI-compatible runtime, Postgres, and Redpanda for local smoke.")}
            ${card("[CLUSTER]", "Kubernetes", "Helm-rendered API, worker, MCP, CNPG, Strimzi, KEDA, ingress, network policy, and GitOps.")}
          </div>
        </div>
      </section>

      <section class="section" id="trust">
        <div class="container">
          <h2>4. Trust boundaries.</h2>
          <p>Provider calls are not inside the core trust boundary by default. External providers are optional, policy-gated, and explicitly configured. Disabled authentication is local-only.</p>
          ${diagram("Trust boundary map", diagrams.trust)}
          ${table(["Boundary", "Control"], [
            ["Caller boundary", "Bearer token or local disabled-auth path, depending on deployment mode."],
            ["Tenant boundary", "Principal binding and tenant-scoped policy checks."],
            ["Provider boundary", "Local and cloud providers selected only after routing policy."],
            ["Data boundary", "Postgres-backed jobs, results, tokens, audit events, and model registry when durable mode is enabled."],
            ["Review boundary", "Certification and review decisions are explicit metadata, not implied quality guarantees."],
          ])}
        </div>
      </section>

      <section class="section" id="storage">
        <div class="container">
          <h2>5. Storage and queue modes.</h2>
          <div class="grid grid-4">
            ${card("[MEM]", "In-memory", "Fast local development and tests.")}
            ${card("[FILE]", "File-backed", "Local durable-ish job state in configured directories.")}
            ${card("[PG]", "Postgres", "Durable jobs, queue, results, audit, tokens, and model registry.")}
            ${card("[KAFKA]", "Kafka", "Worker fanout and dead-letter queue patterns.")}
          </div>
        </div>
      </section>

      <section class="section" id="failure">
        <div class="container">
          <h2>6. Failure modes and diagnostics.</h2>
          <div class="timeline">
            <div class="timeline-item"><strong>Schema failure</strong><p>Invalid bundles are rejected before routing or provider execution.</p></div>
            <div class="timeline-item"><strong>Auto-route unavailable</strong><p>Auto routing fails closed with diagnostics rather than silently falling back to an unapproved route.</p></div>
            <div class="timeline-item"><strong>Provider not configured</strong><p>Optional CT2, local OpenAI-compatible, OpenRouter, and Gemini paths report missing configuration explicitly.</p></div>
            <div class="timeline-item"><strong>Auth mismatch</strong><p>Production-like deployment modes reject disabled auth and require explicit credentials/scopes.</p></div>
            <div class="timeline-item"><strong>Worker retry</strong><p>Durable queues support claim, retry, nack, and dead-letter handling depending on backend.</p></div>
          </div>
        </div>
      </section>
    </main>
  `,

  whitepaper: `
    <main>
      <section class="page-hero">
        <div class="container">
          ${badges(["White Paper", "Contract-driven", "Provider-governed", "No OCR extraction", "No hosted SaaS"])}
          <h1>Contract-driven translation for structured document workflows.</h1>
          <p class="lead">This white paper explains why document translation needs a control plane: stable contracts, provider routing, local-first testability, deployment-aware auth, quality metadata, and reviewable output.</p>
        </div>
      </section>

      <section class="section">
        <div class="container">
          <nav class="toc">
            <a href="#abstract">Abstract</a>
            <a href="#motivation">Motivation</a>
            <a href="#principles">Principles</a>
            <a href="#architecture">Architecture</a>
            <a href="#contracts">Contracts</a>
            <a href="#security">Security</a>
            <a href="#limits">Limits</a>
            <a href="#references">References</a>
          </nav>
        </div>
      </section>

      <section class="section" id="abstract">
        <div class="container">
          <h2>1. Abstract.</h2>
          <p>EDC Translation is a translation service for structured document-processing pipelines. It accepts raw text or <code>DocumentBundle v1</code>, emits <code>TranslationBundle v1</code>, routes work through configurable translation providers, and exposes REST, CLI, Python, and MCP-style access. It is designed for downstream review, custody, automation, and integration workflows.</p>
          <p>It is not an OCR engine, not a human translation management system, not a hosted translation SaaS, and not a repository of model weights. Its value is the contract and control layer around translation execution.</p>
        </div>
      </section>

      <section class="section" id="motivation">
        <div class="container">
          <h2>2. Motivation.</h2>
          <div class="grid grid-2">
            ${card("[STRUCTURE]", "Translation is a workflow problem", "Document pipelines need span identity, source language, target language, provider metadata, job status, quality state, and review context.")}
            ${card("[CONTRACT]", "Contracts reduce integration risk", "JSON schemas make requests and outputs independently verifiable by clients, tests, and automation.")}
            ${card("[VARIANCE]", "Providers are not interchangeable", "Engines differ by license, deployment model, latency, determinism, language coverage, and retention posture.")}
            ${card("[TRACE]", "Review teams need traceability", "Operators need to answer what input was submitted, which provider handled it, what output was emitted, and what review decision was applied.")}
          </div>
        </div>
      </section>

      <section class="section" id="principles">
        <div class="container">
          <h2>3. Design principles.</h2>
          <div class="timeline">
            <div class="timeline-item"><strong>Contract-first translation</strong><p>The main unit of work is a document bundle or raw text normalized into bundle-compatible structure. The main output is a translation bundle.</p></div>
            <div class="timeline-item"><strong>Explicit provider routing</strong><p>Provider choice is resolved through tenant and provider policy instead of being hidden inside application code.</p></div>
            <div class="timeline-item"><strong>Local-first deployment</strong><p>Deterministic tests, mock local runtime, local CT2 adapters, Docker, Helm, GitOps, and Ansible support evaluation before live providers.</p></div>
            <div class="timeline-item"><strong>Deterministic testability</strong><p>The built-in deterministic provider enables repeatable tests, examples, and smoke checks.</p></div>
            <div class="timeline-item"><strong>Separation from OCR</strong><p>The service receives text or structured bundles from upstream extraction systems and does not perform page image OCR.</p></div>
          </div>
        </div>
      </section>

      <section class="section" id="architecture">
        <div class="container">
          <h2>4. System architecture.</h2>
          ${diagram("Architecture overview", diagrams.pipeline)}
          ${table(["Layer", "Responsibility"], [
            ["API layer", "FastAPI app, OpenAPI, health, jobs, bundles, admin UI, and provider operations."],
            ["Service layer", "Validation, normalization, routing, glossary/instruction policy, job state, review metadata."],
            ["Provider layer", "Deterministic, passthrough, CT2, local OpenAI-compatible, and optional cloud engines."],
            ["Store layer", "In-memory, file-backed, and Postgres-backed repositories."],
            ["Queue layer", "Local, Postgres, and Kafka worker fanout modes."],
            ["Deployment layer", "Docker, Compose, Helm, GitOps, Ansible, worker, MCP, ingress, scaling, and network policy."],
          ])}
        </div>
      </section>

      <section class="section" id="contracts">
        <div class="container">
          <h2>5. Data contracts and provider strategy.</h2>
          <p><code>DocumentBundle v1</code> provides the source document and source spans. <code>TranslationBundle v1</code> provides translated spans, provider metadata, provenance, quality scores, certification state, custody references, and artifact metadata.</p>
          ${table(["Provider path", "Purpose", "Evaluation concern"], [
            ["Deterministic CI", "Repeatable tests and examples.", "Contract stability, not linguistic quality."],
            ["Passthrough", "Same-language preservation.", "Correct no-op routing."],
            ["CT2 local models", "Local NMT with approved model directories.", "License, tokenizer assets, provenance, and quality."],
            ["Local OpenAI-compatible", "Private local model runtime.", "Runtime readiness, model identity, and endpoint reachability."],
            ["OpenRouter/Gemini", "Optional live provider paths.", "Credentials, live-smoke opt in, retention, residency, and policy."],
          ])}
        </div>
      </section>

      <section class="section" id="security">
        <div class="container">
          <h2>6. Security, tenant controls, and deployment models.</h2>
          <p>Local development can run with disabled auth. Staging and production-like environments require explicit auth configuration. Static bearer tokens, JWT secret configuration, tenant binding, scope binding, token stores, audit stores, and Postgres-backed persistence are all treated as deployment concerns.</p>
          ${diagram("Trust model", diagrams.trust)}
          <div class="grid grid-3">
            ${card("[COMPOSE]", "Docker Compose", "Local smoke and staging-like validation stacks.")}
            ${card("[HELM]", "Kubernetes", "API, worker, MCP, CNPG, Strimzi, KEDA, ingress, network policy.")}
            ${card("[GITOPS]", "Operations", "Argo CD scaffolding and Ansible deployment automation.")}
          </div>
        </div>
      </section>

      <section class="section" id="limits">
        <div class="container">
          <h2>7. What it is not.</h2>
          <ul>
            <li>Not an OCR engine.</li>
            <li>Not a human translation management platform.</li>
            <li>Not a hosted translation SaaS.</li>
            <li>Not a repository of model weights.</li>
            <li>Not a guarantee that every provider is suitable for every language, license, or deployment environment.</li>
            <li>Not a substitute for human review where certification or regulated use requires it.</li>
          </ul>
        </div>
      </section>

      <section class="section" id="references">
        <div class="container">
          <h2>8. Public references.</h2>
          ${table(["Reference", "Purpose"], [
            ["<a href='../docs/00-SYSTEM-BLUEPRINT.md'>System Blueprint</a>", "Boundary, architecture, and primary contracts."],
            ["<a href='../docs/01-TECH-STACK-DNA.md'>Tech Stack DNA</a>", "Runtime, engines, storage, queue, and deployment surfaces."],
            ["<a href='../docs/03-INFORMATION-FLOWS.md'>Information Flows</a>", "Synchronous, bundle, worker, and review flows."],
            ["<a href='../docs/API-REFERENCE.md'>API Reference</a>", "Health, translation, model, provider, CLI, and MCP surfaces."],
            ["<a href='../docs/05-DEPLOYMENT.md'>Deployment</a>", "Compose, Helm, GitOps, and Ansible deployment commands."],
            ["<a href='../schemas/document-bundle-v1.schema.json'>DocumentBundle schema</a>", "Input contract."],
            ["<a href='../schemas/translation-bundle-v1.schema.json'>TranslationBundle schema</a>", "Output contract."],
          ])}
        </div>
      </section>
    </main>
  `,

  slides: `
    <main class="deck">
      ${[
        ["EDC Translation", "Contract-first translation for document-processing pipelines.", ["MIT", "Python 3.11+", "FastAPI", "DocumentBundle v1", "TranslationBundle v1"]],
        ["The problem", "Provider calls alone do not create reviewable translation systems.", ["Raw text APIs lose document context.", "Provider choices can violate license, residency, or deployment requirements.", "Review systems need traceable output, not just translated strings."]],
        ["The approach", "A governed translation control plane around models and providers.", ["Contract-first input and output.", "Deterministic test provider for repeatable CI.", "Policy-aware provider routing.", "Local-first deployment with optional live providers."]],
        ["System boundary", "In scope: bundle translation, raw text jobs, REST, CLI, Python, MCP, admin UI, deployment scaffolding. Out of scope: OCR extraction, human vendor management, hosted SaaS, model weights.", []],
        ["Pipeline overview", "Input, validate, normalize, policy, route, translate, bundle, review.", "DIAGRAM:pipeline"],
        ["Primary contracts", "DocumentBundle v1 preserves source structure. TranslationBundle v1 preserves translated spans, provider metadata, quality, certification, and review hooks.", []],
        ["Runtime surfaces", "REST API, CLI, Python client, MCP-style HTTP wrapper, static admin UI, and worker daemon all converge on the same service layer.", []],
        ["Provider strategy", "Deterministic CI, passthrough, CT2 local models, local OpenAI-compatible runtimes, and optional OpenRouter/Gemini paths.", []],
        ["Policy-aware routing", "Auto-route is opt-in and fails closed. Non-commercial license paths are blocked unless explicitly allowed. Live providers require credentials and smoke opt in.", []],
        ["Information flow", "The synchronous text path returns a job id and stores the emitted bundle for retrieval.", "DIAGRAM:sequence"],
        ["API surface", "Health, jobs, bundles, languages, routing diagnostics, model validation, live smoke, local model ranking, tenant policy, glossaries, instruction sets, reviews, admin.", []],
        ["Deployment topologies", "Python install, Docker Compose smoke, staging-like Compose validation, Helm, GitOps, and Ansible.", "DIAGRAM:deployment"],
        ["Operations and evidence", "Local, file-backed, and Postgres-backed job state; optional Kafka fanout; custody, review, quality, and evidence metadata.", []],
        ["Best-fit cases", "eDiscovery translation, multilingual review, local model evaluation, batch text translation, MCP/agent workflows, and platform deployment.", []],
        ["Get started", "Run a deterministic smoke test with no external provider.", "CODE"],
      ].map((slide, idx) => {
        const [title, lead, detail] = slide;
        let body = "";
        if (Array.isArray(detail) && detail.length) {
          body = `<ul class="big-list">${detail.map((item) => `<li>${item}</li>`).join("")}</ul>`;
        } else if (detail === "DIAGRAM:pipeline") {
          body = diagram("Pipeline", diagrams.pipeline);
        } else if (detail === "DIAGRAM:sequence") {
          body = diagram("Sequence", diagrams.sequence);
        } else if (detail === "DIAGRAM:deployment") {
          body = diagram("Deployment", diagrams.deployment);
        } else if (detail === "CODE") {
          body = codeBlock("PowerShell", `py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
edc-translation submit-text "Hello world." --source en --target fr --provider deterministic_ci`);
        }
        return `<section class="slide"><span class="slide-num">${String(idx + 1).padStart(2, "0")} / 15</span><div class="slide-content ${idx === 0 ? "center" : ""}"><h${idx === 0 ? "1" : "2"}>${title}</h${idx === 0 ? "1" : "2"}><p class="lead ${idx === 0 ? "text-center" : ""}">${lead}</p>${body}</div></section>`;
      }).join("")}
      <div class="slide-controls" aria-label="Slide controls">
        <button class="btn btn-secondary" type="button" data-slide-prev>Prev</button>
        <button class="btn btn-primary" type="button" data-slide-next>Next</button>
      </div>
    </main>
  `,
};

function renderPage() {
  const page = document.body.dataset.page || "home";
  const content = pages[page] || pages.home;
  document.body.innerHTML = header(page) + content + footer();
  renderMermaid();
  initSlides();
}

function renderMermaid() {
  if (!window.mermaid) return;
  window.mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    securityLevel: "strict",
    themeVariables: {
      background: "#182236",
      primaryColor: "#182236",
      primaryBorderColor: "#4f8cff",
      primaryTextColor: "#edf4ff",
      lineColor: "#a7b3c7",
      secondaryColor: "#111827",
      tertiaryColor: "#202b42",
    },
  });
  window.mermaid.run({ querySelector: ".mermaid" });
}

function initSlides() {
  const slides = Array.from(document.querySelectorAll(".slide"));
  if (!slides.length) return;
  let index = 0;
  const go = (nextIndex) => {
    index = Math.max(0, Math.min(slides.length - 1, nextIndex));
    slides[index].scrollIntoView({ behavior: "smooth", block: "start" });
  };
  document.querySelector("[data-slide-next]")?.addEventListener("click", () => go(index + 1));
  document.querySelector("[data-slide-prev]")?.addEventListener("click", () => go(index - 1));
  document.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight" || event.key === "PageDown") go(index + 1);
    if (event.key === "ArrowLeft" || event.key === "PageUp") go(index - 1);
  });
}

document.addEventListener("DOMContentLoaded", renderPage);
