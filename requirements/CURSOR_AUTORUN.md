## Cursor Auto-Run Entrypoint (No-Intervention Execution)

Cursor – execute these steps autonomously. Do not wait for confirmations unless a secret is missing.

1) Read specs
- Read: PRD_MCC_AI_AGENT.md, CURSOR_RULES.md, CURSOR_ORCHESTRATION.md, EXECUTION_PLAYBOOK.md
- Treat PRD as source of truth for APIs, agents, data contracts, security, and tests.

2) Implement services (create code if missing)
- services/api (FastAPI): implement endpoints in PRD Section 14, with idempotency and error taxonomy.
- services/agents (CrewAI): implement agents per Section 15 + 15a; strict JSON schemas.
- services/scraper: Playwright/requests/bs4 pipeline; S3 artifact write, chunk & embed to OpenSearch.
- tools/mcp: expose MCP tools listed in PRD Section 14.

3) Local runtime setup
- Use docker-compose.yml to start OpenSearch + MinIO (+ MySQL if not using Aurora dev): `docker compose up -d`
- Ensure Conda env: `conda activate mcc-underwriter && make dev`

4) Seed data
- Implement and run `scripts/db_seed.py` to create schemas in MySQL and seed:
  - merchants, merchant_kpis_monthly, mcc_catalog, runs, recommendations, artifacts, idempotency_keys
  - import MCC catalogs and a small gold set

5) Run services
- API: `make run-api`
- Agents: `make run-agents`
- Scraper: run against sample merchant(s); index embeddings in OpenSearch

6) End-to-end demo
- Implement and run `scripts/run_demo.py`:
  - submit_merchant → get_recommendation → simulate_impact → approve
  - write a report to `MCC_AI_Agent/demo_reports/<timestamp>.md`

7) Tests & quality gates
- Add unit/integration/contract tests to meet PRD gates; run `make test`
- Log structured JSON; ensure OTEL stubs in place locally

8) Commit artifacts
- Commit all new code; update docs if interfaces differ (they should not)

9) Optional: CI + IaC
- Ensure `bitbucket-pipelines.yml` runs lint/test/build
- Prepare Terraform `dev` plan (no apply) and report readiness

ENV hints
- Use `.env.local` (not committed) for local values: OPENAI_API_KEY, DB_URI, OPENSEARCH_ENDPOINT, S3_ENDPOINT, S3_BUCKET
- In cloud, use AWS Secrets Manager per PRD

Exit conditions
- `make demo` runs successfully end-to-end
- Demo report generated with top-3 MCC, confidence, deltas, and artifacts
