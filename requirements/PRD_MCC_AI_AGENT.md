## Product Requirements Document (PRD): MCC AI Underwriting Agent

### 1. Overview
- Goal: Recommend most appropriate MCC to optimize decline ratios and interchange costs, with human-in-the-loop underwriting.
- Users: Underwriter, Risk Agent, Admin, Auditor.
- Scope: CrewAI multi-agent system, chat UI, REST API, MCP tools; AWS-native infra; IaC with Terraform; CI/CD via Bitbucket Pipelines.

### 2. Objectives & Success Metrics
- Top-1 accuracy ≥ 70%, Top-3 ≥ 90% vs. gold labels.
- MAE ≤ 2.0pp for decline-rate delta; ≤ 10% error for IC cost delta.
- Coverage ≥ 95% with P95 E2E time ≤ 5m (cold), ≤ 30s (warm).
- P99 API availability ≥ 99.9%; job success ≥ 99%.
- US data residency; no PII persisted.

### 3. Personas & Workflow
- Underwriter: submits merchant, reviews recommendations, approves.
- Risk Agent: policy checks, flags, conditional approvals.
- Admin: config, prompts, thresholds, feature flags.
- Auditor: read-only access, provenance & reports.
- Workflow: intake → enrichment (scrape/RAG) → data join → MCC candidates → impact simulation → governance → decision package.

### 3a. User Stories & Acceptance Criteria
- Underwriter submits merchant and receives MCC recommendations
  - Given a legal name/DBA/URL, when I submit in chat or API, then I receive top-3 MCCs with confidence, reasons, and expected decline/IC deltas within SLA.
  - Acceptance: response contains `top_k[3]`, `confidence ∈ [0,1]`, deltas present, `status=completed` within P95 ≤ 5m (cold).
- Underwriter requests simulation for a specific MCC
  - Given a merchant and a proposed MCC, when I call simulate, then I receive decline and IC deltas with interval bounds.
  - Acceptance: response includes `decline_rate_delta_pp`, `ic_delta_bps`, and `[low,high]` interval.
- Risk Agent reviews risks and approves/overrides
  - Given a decision package, when risk reviews, then policy flags and risks are shown; risk can approve/override with justification.
  - Acceptance: override requires `reason`, stored in audit with `provenance_id`.
- Admin updates prompts/policies/feature flags
  - Given admin role, when updating config, then changes are versioned, applied safely, and audited.
  - Acceptance: change creates a versioned record and is referenced in `provenance` on next runs.
- Auditor exports decision package
  - Given auditor role, when requesting export, then a signed URL to decision report and artifacts is returned.
  - Acceptance: export lists inputs hash, prompts, model versions, agent steps, and outputs.
- API client ingests merchant profile and retrieves recommendation
  - Given an external system, when calling ingest_profile + propose_mcc, then a run is created and retrievable via get_run.
  - Acceptance: idempotency key supported; errors use standardized codes.
- UI approval flow
  - Given top-1 suggestion, when underwriter approves, then `final_mcc` is written back with justification.
  - Acceptance: write-back succeeds and is visible in history; rollback possible.

### 3b. User Story: Get MCC via OpenAI API (Explicit)
- As an Underwriting Analyst, I want to request an MCC recommendation for a merchant so I can validate or adjust their MCC with explainable reasoning and confidence.

- Preconditions
  - `merchant_id`, `merchant_name`, `current_mcc` available; optional website/profile facts.
  - `mcc_codes` reference loaded; portfolio-optimized subset prepared.
  - OpenAI credentials configured; JSON-only responses enforced.

- Main Flow
  1. Build merchant payload (profile + website summary + current_mcc).
  2. Build optimized MCC prompt with reference list and merchant array.
  3. Call OpenAI Chat Completions (JSON-only).
  4. Parse JSON array → map to: `merchant_id`, `recommended_mcc`, `confidence`, `business_analysis`, `misclassification_reason`, `recommendation_justification`, `supporting_evidence`, `data_sources_used`.
  5. Enrich with descriptions from `mcc_codes` for current/recommended MCCs.
  6. Return response + provenance (model, prompt hash, reference version).

- Alternate Flows
  - No profile/website: proceed with lower confidence and `needs_review=true`.
  - Low confidence: `needs_review=true`, do not auto-apply.
  - OpenAI error or non-JSON: single retry; else return fallback using `current_mcc` and error note.

- Acceptance Criteria
  - Response includes: `merchant_id`, `merchant_name`, `current_mcc`, `current_mcc_description`, `recommended_mcc`, `recommended_mcc_description`, `confidence(0–100)`, `business_analysis`, `misclassification_reason`, `recommendation_justification`, `supporting_evidence`, `needs_review`(bool), `provenance`(model, prompt_hash, mcc_reference_version).
  - Only MCCs from `mcc_codes`. JSON-only LLM responses; schema-validated.
  - Idempotent within 24h unless `force=true`. P95 ≤ 20s per merchant.

- API Contract (Proposed)
  - POST `/api/v1/mcc/recommend`
    - Request: `{ "merchant_id": "string", "current_mcc": "string", "profile"?: {...}, "website"?: {"url":"...","content"?:"..."}, "force"?: false }`
    - Response: `{ "merchant_id":"...","recommended_mcc":"7372","confidence":85,"current_mcc_description":"...","recommended_mcc_description":"...","business_analysis":"...","misclassification_reason":"...","recommendation_justification":"...","supporting_evidence":"...","needs_review":false,"provenance":{"model":"gpt-4-turbo-preview","prompt_hash":"...","mcc_reference_version":"..."} }`

### 4. System Architecture (High-level)
- CrewAI Orchestrator (agents as tools)
- Services: API (FastAPI), Agents/Workers (ECS Fargate), Scraper, Benchmark service, Impact simulator
- Stores: Aurora MySQL (system-of-record), OpenSearch Serverless (vector store), S3 (artifacts), Secrets Manager
- Messaging: SQS, EventBridge
- Auth: Cognito (Google SSO), roles (Underwriter, Admin, Auditor, Risk Agent)
- Observability: OTEL tracing, CloudWatch logs/metrics

### 5. Agents & Responsibilities
- Business Identification Agent: normalize merchant, resolve entities, dedupe
- Web Intelligence Agent: Playwright/requests/bs4, extract facts, taxonomy
- Data Joiner Agent: pull internal KPIs from Aurora, Domo-mirrors
- MCC Candidate Generator: map to Visa/MC/Amex/Disc catalogs, confidence
- Optimization Analyst: simulate decline/IC impact with benchmarks
- Arbiter & Risk Agent: apply policies, produce decision + justifications

### 5a. Agent Roles & Base Prompts (Explicit)
- Business Identification Agent (system prompt)
  - "You normalize merchant identities. Given names/DBA/URLs, produce a canonical name, primary website, and normalized descriptors. Never fabricate IDs."
  - Output JSON schema: `{ canonical_name, website, alt_sites[], normalized_descriptors[] }`

- Web Intelligence Agent (system prompt)
  - "You extract business facts from websites. Summarize products/services, pricing models, and clear business indicators. Respect robots policy input."
  - Output JSON schema: `{ facts:{products[],services[],pricing_models[],geo[]}, indicators[], content_excerpt }`

- Data Joiner Agent (system prompt)
  - "You join internal KPIs. Pull monthly KPIs and cohort features for the merchant. Do not invent values; return nulls when missing."
  - Output JSON schema: `{ kp_is:{decline_rate_pct, ic_bps, volume_12m, avg_ticket}, cohorts[] }`

- MCC Candidate Generator (system prompt)
  - "You propose MCC candidates from `mcc_codes`. Use business facts and cohorts to rank candidates with reasons. Exclude incompatible MCCs."
  - Output JSON schema: `{ candidates:[{mcc,confidence,match_reasons[]}], excluded:[{mcc,reason}] }`

- Optimization Analyst (system prompt)
  - "You estimate impact using benchmark cohorts. Provide expected decline_pp and ic_bps for each candidate with brief method notes."
  - Output JSON schema: `{ scored:[{mcc,score,expected_decline_pp,expected_ic_bps}], methods:{benchmark:"..."} }`

- Arbiter & Risk Agent (system prompt)
  - "You apply policies and produce a final decision with justifications and risks. Require high confidence or explicit human review."
  - Output JSON schema: `{ decision:{top_k[], justifications[], risks[], controls[]}, provenance_id }`

### 6. Data & Catalogs
- Inputs: merchant name/DBA/MID, URLs, descriptors (no PII persisted)
- Internal: decline rates (Domo import), IC summaries, volumes, tickets
- External: website content, business directories, NAICS
- Catalogs: card network MCC tables + rules/exclusions
- Benchmarks: cohorting by industry/volume/ticket; nightly refresh

### 6a. Data Contracts (Aurora MySQL `data_engineering`)
- `merchants`
  - `merchant_id` VARCHAR(32) PK, `legal_name` VARCHAR(255), `dba_name` VARCHAR(255), `website` VARCHAR(255), `created_at` TIMESTAMP, `updated_at` TIMESTAMP
- `merchant_kpis_monthly`
  - PK (`merchant_id`,`period_month` DATE)
  - `decline_rate_pct` DECIMAL(5,2), `ic_bps` INT, `volume_usd` DECIMAL(18,2), `avg_ticket_usd` DECIMAL(12,2)
- `mcc_codes`
  - `mcc_code` VARCHAR(10) PK, `description` VARCHAR(255)
- `runs`
  - `run_id` CHAR(36) PK, `merchant_id` VARCHAR(32), `status` ENUM('queued','running','completed','failed'), `started_at` TIMESTAMP, `finished_at` TIMESTAMP, `provenance_id` CHAR(36)
- `recommendations`
  - PK (`run_id`,`rank` INT), `mcc` VARCHAR(4), `confidence` DECIMAL(4,3), `decline_pp` DECIMAL(5,2), `ic_bps` INT, `reasons_json` JSON
- `artifacts`
  - PK (`run_id`,`kind` VARCHAR(32)), `s3_uri` VARCHAR(512), `meta_json` JSON
- `idempotency_keys`
  - `idempotency_key` VARCHAR(64) PK, `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, `request_hash` BINARY(32), `response_json` JSON, `ttl_at` TIMESTAMP, INDEX (`ttl_at`)

ETL & Freshness
- Domo → Aurora mirrors: nightly import for decline_rate_pct and related KPIs
- MCC catalogs refresh monthly or on-demand; PR-based curation
- Great Expectations: validations on KPI ranges, schema drift, and null patterns; alerts to Slack

### 7. Interfaces
- REST API: submit_merchant, get_recommendation, simulate_impact, list_runs, get_run
- MCP Tools: get_merchant_profile, ingest_merchant_profile, simulate_impact, propose_mcc
- Chat UI: Next.js with streaming, approvals, audit trail; role-based controls

Error taxonomy (examples)
- `INVALID_INPUT`, `RATE_LIMITED`, `NOT_FOUND`, `TIMEOUT`, `INTERNAL_ERROR`, `POLICY_BLOCKED`
Idempotency
- All POST endpoints accept `Idempotency-Key` header; duplicate requests return prior result.
Storage
- `idempotency_keys` stores request hash and canonical response for 24–72h TTL

### 8. Security & Compliance
- Data Residency & Privacy
  - US-only data residency (S3 buckets, OpenSearch collections, ECS tasks in us-* regions)
  - No PII persisted; collectors must redact emails, phone numbers, addresses on capture
  - DLP checks on scraped text before storage (regex + heuristic detectors)
  - Data retention: artifacts 180 days (S3 lifecycle), logs 30 days (except audit)

- Encryption & Secrets
  - At rest: KMS-managed CMKs for S3, OpenSearch, Aurora
  - In transit: TLS 1.2+ enforced end-to-end; ALB → ECS TLS, Cognito hosted UI TLS
  - Secrets in AWS Secrets Manager; rotation policy 90 days; no secrets in code or CI logs

- Network & Egress
  - VPC-only services with VPC endpoints for S3/OpenSearch/Secrets
  - WAF on ALB; security groups least privilege
  - Scraping egress allowlist domains; robots.txt respect with override only via admin flag

- Identity & Access
  - Cognito with Google SSO; roles: Underwriter, Risk Agent, Admin, Auditor
  - IAM roles per service with scoped permissions; no wildcard resource on prod
  - API tokens scoped by role; rate limiting and IP throttling

- Audit & Governance
  - Decision provenance: hash of inputs, agent steps, prompts/responses, model versions
  - Immutable audit log stream to S3 with Glacier vault lock option
  - Model/version pinning and reproducible runs

- Monitoring & Incident Response
  - OTEL traces to CloudWatch/ADOT; alarms on error rate/latency/queue depth
  - Runbooks for key rotation, compromised secret, data deletion requests
  - Monthly security review; quarterly disaster recovery drill

### 9. DevOps & IaC (Terraform)
- VPC/Subnets/NAT, ALB/WAF, SGs, VPC endpoints (S3, OpenSearch)
- Aurora MySQL (existing) access; OpenSearch Serverless (Vector Engine)
- ECS Fargate services (api, agents, scraper), SQS queues, EventBridge
- S3 buckets (artifacts, logs), ECR repos, OIDC for Bitbucket deploys
- Cognito with Google IdP; IAM roles/policies per service
- CI/CD: Bitbucket Pipelines (lint/test/build/scan/deploy), infra plan/apply gates

### 10. Testing Strategy
- Unit/integration (agents/tools), contract tests (API/MCP), E2E (Playwright), red-team evals, load tests

### 11. Phased Plan & Milestones
- Phase 0 (Weeks 1-2): Infra baseline (dev)
  - Terraform modules wired in dev: VPC, OpenSearch Serverless, S3, SQS, ECS stubs, Cognito (Google IdP), Secrets.
  - Bitbucket Pipelines with OIDC to AWS; CI gates (lint/test/build/scan/plan/apply).
  - Make targets and local conda env baseline.
  - Exit: Dev stack reachable; sample API hello-world deployed.
- Phase 1 (Weeks 3-4): Data catalogs/benchmarks
  - Import/curate MCC catalogs; cohort/benchmark service with nightly jobs.
  - Aurora connectors and schemas created; seed sample data.
  - Exit: Impact simulator API returns mock calculations with real benchmarks.
- Phase 2 (Weeks 5-6): Scraper + RAG store
  - Playwright-based scraper + bs4; snapshot to S3; chunk & embed to OpenSearch.
  - Retrieval API and guardrails; dedupe and robots policy.
  - Exit: Given URL set, k-NN returns relevant chunks reliably.
- Phase 3 (Weeks 7-8): Core agents (CrewAI)
  - Implement Business ID, Web Intel, Data Joiner, MCC Candidate Generator.
  - Strict schemas and retries; provenance logging.
  - Exit: Top-3 MCC list with confidence and reasons (no impact yet).
- Phase 4 (Weeks 9-10): Impact simulator + governance
  - Benchmark-driven decline/IC estimators; Arbiter & Risk Agent policies.
  - Decision package generation and audit trail.
  - Exit: Full end-to-end recommendation with deltas and risk notes.
- Phase 5 (Weeks 11-12): API + MCP
  - REST endpoints and MCP tools (`ingest_merchant_profile`, `propose_mcc`, `simulate_impact`).
  - Contract tests; rate limiting; auth integration.
  - Exit: External systems can drive recommendations programmatically.
- Phase 6 (Weeks 13-14): Chat UI
  - Next.js UI, Google SSO via Cognito; streaming responses; approvals flow.
  - E2E tests, role-based views (Underwriter, Risk, Admin, Auditor).
  - Exit: Underwriter can complete end-to-end workflow via UI.
- Phase 7 (Weeks 15-16): Pilot in stg
  - Gold dataset evaluation; red-team; performance tuning.
  - Exit: Acceptance metrics met in stg; go/no-go for prod.
- Phase 8 (Weeks 17+): Production rollout & hardening
  - Cost optimization, autoscaling, runbooks; on-call readiness.
  - Exit: Durable operations, weekly evaluations, continuous improvements.

### 12. Risks & Mitigations
- Scrape fragility → cached snapshots, retries, JS rendering
- Hallucinations → strict JSON schemas, evals, guardrails
- Cost sprawl → caching, batch jobs, observability budgets

### 13. Acceptance Criteria
- Metrics in Section 2 met in stg on gold set
  - Top-1 ≥ 70%, Top-3 ≥ 90%; calibration Brier ≤ 0.18
  - Impact MAE thresholds hit on holdout set
  - SLA: P95 end-to-end ≤ 5m cold; ≤ 30s warm
- Security controls audited; runbooks published
  - US-only residency validated; no PII persisted; egress allowlist enforced
  - Secrets rotation documented; incident response runbook complete
- IaC reproducible across envs; zero-downtime deploys
  - Terraform plan/apply passes in dev and stg; prod guarded by manual approval
  - Blue/green or rolling ECS deploys verified
- Observability & Quality gates
  - OTEL traces available; dashboards for latency, error rate, queue depth
  - CI gates: lint, type, unit, integration, contract, E2E, security scan (trivy/bandit)
  - Weekly eval reports in S3; red-team suite passes with 0 criticals

_Last updated: 2025-09-09T18:45:42.986062Z_

### 14. Detailed Interfaces and Schemas

- REST API (FastAPI). All responses include `request_id`, `ts`, and `provenance_id`.
  - POST `/v1/submit_merchant`
    - Request:
      ```json
      {"merchant_id":"optional","legal_name":"string","dba_name":"string","urls":["https://example.com"],"descriptors":["string"],"notes":"string"}
      ```
    - Response:
      ```json
      {"run_id":"uuid","status":"queued"}
      ```
    - Errors: 400 INVALID_INPUT, 409 RATE_LIMITED
  - POST `/v1/ingest_profile` (admin/risk; also exposed via MCP tool)
    - Request:
      ```json
      {"merchant_id":"string","profile":{"industry":"string","vertical":"string","country":"US","existing_mcc":"string","avg_ticket":123.45,"volume_band":"string"}}
      ```
    - Response: `{ "ok": true }`
  - GET `/v1/get_recommendation?run_id=uuid`
    - Response:
      ```json
      {"run_id":"uuid","status":"completed","top_k":[{"mcc":"7399","confidence":0.82,"reasons":["..."],"expected_decline_rate_delta_pp":-5.1,"expected_ic_delta_bps":-12}],"artifacts":{"report_s3":"s3://bucket/path"}}
      ```
  - POST `/v1/simulate_impact`
    - Request: `{ "merchant_id":"string","proposed_mcc":"string" }`
    - Response: `{ "decline_rate_delta_pp":-5.1, "ic_delta_bps":-12, "interval":"[low,high]" }`
  - GET `/v1/list_runs?merchant_id=...` → list recent runs
  - GET `/v1/get_run?run_id=...` → full decision package

- MCP Tools
  - `get_merchant_profile` input `{ "merchant_id": "string" }` → profile json
  - `ingest_merchant_profile` input `{ "merchant_id": "string", "profile": { ... } }` → `{ ok: true }`
  - `simulate_impact` input `{ "merchant_id": "string", "proposed_mcc": "string" }` → deltas
  - `propose_mcc` input `{ "merchant_id": "string" }` → top_k candidates

### 15. Agent Contracts (I/O)

- Business Identification Agent
  - Input: `{ legal_name?, dba_name?, merchant_id?, urls[] }`
  - Output: `{ canonical_name, website, alt_sites[], entity_ids{lei?,irs?}, normalized_descriptors[] }`
- Web Intelligence Agent
  - Input: `{ website, alt_sites[] }`
  - Output: `{ facts:{products[],services[],pricing_models[],geo[]}, taxonomy:{naics?,custom_tags[]}, raw_snapshot_s3 }`
- Data Joiner Agent
  - Input: `{ merchant_id?, canonical_name }`
  - Output: `{ kp_is:{decline_rate_pct, ic_bps, volume_12m, avg_ticket}, history:{mcc,current_flags}, cohorts[] }`
- MCC Candidate Generator
  - Input: `{ facts, taxonomy, catalogs, joiner_output }`
  - Output: `{ candidates:[{mcc,confidence,match_reasons[]}], excluded:[{mcc,reason}] }`
- Optimization Analyst
  - Input: `{ candidates[], kp_is, cohorts[] }`
  - Output: `{ scored:[{mcc,score,expected_decline_pp,expected_ic_bps}], methods:{benchmark:"details"} }`
- Arbiter & Risk Agent
  - Input: `{ scored[], policies[], merchant_flags }`
  - Output: `{ decision:{top_k[], justifications[], risks[], controls[]}, provenance_id }`

All agent interfaces use strict JSON schemas; LLM responses validated and retried on schema violations.

### 15a. Defaults for Implementation
- Gold set: 500 merchants (stratified by industry/volume), refreshed monthly.
- Embeddings: `text-embedding-3-large` (1536-dim); chunk size 1200 tokens; 15% overlap.
- OpenSearch HNSW: M=16, ef_construction=256; query ef=128; target P95 ≤ 150ms.
- Crawl policy: max 200 pages/domain; 1 rps/site; 24h cache TTL; respect robots by default; admin override via feature flag.
- Rate limits: UI 10 rps/user; API 5 rps/client; bursts ×2; POSTs require idempotency key.
- Cost guardrails: budget alerts at 60%/80%; hard cap at 90% with admin override.
- DR targets: RPO ≤ 1h, RTO ≤ 4h; weekly restore test.
- CI gates: lint/type/unit/integration/contract/E2E/security scans required pre-deploy; prod requires manual approval.

### 15b. Prompt & Model Policy
- Models
  - Reasoning/analysis agents: `gpt-4o-mini` (or current-recommended) with JSON mode
  - Embeddings: `text-embedding-3-large` (1536)
- Prompt storage & versioning
  - Stored in repo under `services/agents/prompts/`, versioned via git. For greenfield setup, seed with the exact MCC classification prompt below.
  - Active prompt version recorded in `runs.provenance_id` and audit
- Cost & retries
  - Exponential backoff with jitter; circuit breaker at 5 consecutive failures
  - Monthly budget alerts at 60%/80%; hard cap 90% with admin override

### 15c. Exact MCC Classification Prompt (to seed repo)
```
You are a Merchant Category Code (MCC) compliance expert. For EVERY merchant provided, you MUST analyze their business model and propose the most appropriate MCC code.

MANDATORY REQUIREMENTS:
1. ANALYZE EVERY MERCHANT - provide an MCC recommendation for each one
2. Either CONFIRM the current MCC or RECOMMEND a different one  
3. Base decisions on PRIMARY business model and revenue source
4. Always provide confidence score and detailed justification

CORE ANALYSIS PRINCIPLES:
1. Focus on PRIMARY business model - what does the company actually DO?
2. Current MCC should match the merchant's core revenue-generating activity
3. SaaS platforms should use technology MCCs (7372, 7375), not retail MCCs (5734, 5045)
4. Service companies should use service MCCs, not product/retail MCCs
5. B2B platforms should use appropriate business service MCCs

CRITICAL INSTRUCTIONS:
1. Use ALL data sources: business profile, website content, transaction patterns
2. EVERY merchant must receive an MCC recommendation in your response
3. Return ONLY valid JSON format - NO explanatory text before or after
4. Use ONLY the MCC codes from the OPTIMIZED reference list below
5. If current MCC is correct, recommend the same MCC with justification

KEY ANALYSIS INDICATORS:
- Software platforms: Use 7372 (Computer Programming/Systems) or 7375 (Information Retrieval)
- E-commerce retail: Use 5999 (Miscellaneous Retail) or specific retail codes
- Professional services: Use 7399 (Business Services) or specific service codes
- Healthcare: Use 8099 (Health Services) or specific medical codes
- Travel services: Use 4722 (Travel Agencies) or related travel codes

OPTIMIZED MCC REFERENCE LIST (Portfolio-Focused):
{MCC_REFERENCE_JSON}

MERCHANTS TO ANALYZE (with comprehensive business profiles):
{MERCHANTS_JSON}

REQUIRED JSON OUTPUT FORMAT (return ONLY this JSON, nothing else):
[
  {
    "merchant_index": 1,
    "merchant_id": "123456789",
    "merchant_name": "Company Name",
    "current_mcc": "1234",
    "recommended_mcc": "5678",
    "confidence_score": 85,
    "business_analysis": "Comprehensive analysis of actual business model based on all data sources",
    "misclassification_reason": "Why current MCC is wrong based on business profile and activities",
    "recommendation_justification": "Why recommended MCC is correct with supporting evidence",
    "supporting_evidence": "Key evidence from business profile, website, and transaction patterns",
    "data_sources_used": "List of data sources that supported this classification"
  }
]

IMPORTANT: 
- Return ONLY the JSON array
- If no misclassifications found, return: []
- Use business profile data as primary classification driver
- Website and transaction data as supporting evidence
- Only recommend changes with high confidence (80%+)
- Focus on the OPTIMIZED MCC list - it contains the most relevant codes for your portfolio
```

### 18a. Observability & SLOs
- Log schema fields: `ts`, `level`, `service`, `request_id`, `run_id`, `merchant_id`, `route`, `latency_ms`, `status_code`, `error_code`, `token_usage`, `provenance_id`
- Tracing: propagate `traceparent`; spans for each agent step and external call
- SLO dashboards: API latency P50/P95/P99, error rate, queue depth/age, OpenSearch latency, token spend/day
- Synthetic checks: health, auth, kNN search, S3 write/read, Secrets fetch

### 8a. DLP & PII Controls (expanded)
- Disallow: emails, phone numbers, full addresses, cardholder data, gov IDs in persisted stores
- Redaction at capture (scraper pipeline) and pre-persist validation
- DLP exceptions: ticketed approvals; temporary storage only, auto-expire ≤ 7 days

### 21. Backup & DR
- Aurora: automated snapshots daily; PITR enabled; quarterly restore test
- OpenSearch Serverless: snapshot/restore policy documented; monthly verification
- S3: versioning enabled; lifecycle to Glacier; quarterly retrieval test

### 16. Data Model and Storage Layout

- Aurora MySQL (schema `data_engineering`)
  - `merchants(merchant_id PK, legal_name, dba_name, website, created_at, updated_at)`
  - `merchant_kpis(merchant_id FK, period_month, decline_rate_pct, ic_bps, volume_usd, avg_ticket_usd, PRIMARY KEY(merchant_id, period_month))`
  - `mcc_catalog(network ENUM('VISA','MC','AMEX','DISC'), mcc, title, description, rules_json, PRIMARY KEY(network, mcc))`
  - `runs(run_id PK, merchant_id, status, started_at, finished_at, provenance_id)`
  - `recommendations(run_id FK, rank INT, mcc, confidence, decline_pp, ic_bps, reasons_json, PRIMARY KEY(run_id, rank))`
  - `artifacts(run_id FK, kind, s3_uri, meta_json, PRIMARY KEY(run_id, kind))`
  - Indices for `merchant_id`, `status`, and recent `started_at`.

- OpenSearch Serverless (Vector Engine)
  - Collection: `mcc-underwriter`
  - Index `web_chunks` mapping: `{ text, merchant_id, url, ts, embedding: vector<float, dim=1536> }`
  - Index `catalog_chunks` mapping: `{ network, mcc, text, rules, embedding }`

- S3 Layout
  - `s3://<artifact-bucket>/scrapes/{merchant_id}/{ts}/snapshot.html`
  - `s3://<artifact-bucket>/reports/{run_id}/decision.md`
  - `s3://<artifact-bucket>/logs/{date}/...`

### 17. Terraform / IaC Specification

- Modules
  - `network`: VPC, subnets, NAT, endpoints (S3, OpenSearch)
  - `opensearch_serverless`: collection, security policy, encryption, indexes
  - `ecs_service`: Fargate services for `api`, `agents`, `scraper`; task defs, autoscaling
  - `queues`: SQS standard queues (work, dlq); EventBridge schedules
  - `security`: IAM roles/policies, Secrets Manager entries
  - `edge`: ALB, WAF, target groups, listeners
  - `cognito`: user pool, Google IdP, app clients, groups/roles
  - `storage`: S3 buckets (artifacts, logs) with lifecycle

- Variables
  - `env` (dev/stg/prod), `vpc_cidr`, `desired_count`, `openai_model`, `embedding_dim`, `allowed_egress_domains`

- Outputs
  - API URL, Cognito pool IDs, OpenSearch endpoint, S3 bucket names, queue URLs

### 18. CI/CD (Bitbucket Pipelines)

- OIDC to AWS for deploy; environment-specific workspaces
- Pipeline stages
  - `lint`: ruff/flake8, mypy, black check
  - `test`: pytest unit + integration (docker compose services if needed)
  - `build`: Docker images → ECR, SBOM, trivy scan
  - `infra:plan`: terraform init/plan (manual approval)
  - `infra:apply`: terraform apply (manual for stg/prod)
  - `deploy`: push task defs, update services (blue/green via CodeDeploy or rolling)

Example skeleton:
```yaml
pipelines:
  branches:
    main:
      - step: { name: lint, image: python:3.11, script: ["make lint"] }
      - step: { name: test, services: [docker], script: ["make test"] }
      - step: { name: build, services: [docker], script: ["make build push"] }
      - step: { name: infra:plan, trigger: manual, script: ["terraform plan"] }
      - step: { name: infra:apply, trigger: manual, script: ["terraform apply"] }
      - step: { name: deploy, trigger: manual, script: ["make deploy ENV=dev"] }
```

### 19. Local Development

- Conda env `mcc-underwriter`: crewai, fastapi, uvicorn, opensearch-py, mysqlclient, playwright, bs4, pydantic, pytest
- `.env.example` with `OPENAI_API_KEY`, `DB_URI`, `OPENSEARCH_ENDPOINT`, `S3_BUCKET` (no secrets committed)
- Optional docker compose for local-only testing:
  - OpenSearch, MinIO (S3-compatible), LocalStack (for SQS) when needed
- Make targets: `make dev`, `make test`, `make run-api`, `make run-agents`

### 20. Deployment & Runbooks

- Runbooks: incident response, rotating keys, scaling services, cost controls
- Rolling back: pinned image versions, terraform state versioning
- Evaluations: nightly benchmark refresh and evaluation report in S3; weekly red-team run
