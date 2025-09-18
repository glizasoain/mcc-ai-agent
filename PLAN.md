# MCC AI Underwriting Agent – Implementation Checklist

## Phase 0 — Bootstrap
- [ ] Create `MCC_AI_Agent/` app root (code only; do not modify `requirements/`)
- [ ] Add `.env.example` (OPENAI_API_KEY, OPENAI_MODEL, DB_URI, OPENSEARCH_ENDPOINT, S3_BUCKET)
- [ ] Add `requirements.txt`, `Makefile`, pre-commit hooks, Ruff/Mypy/Pytest configs
- [ ] FastAPI skeleton (health) and folder layout
- [ ] Versioned prompts folder: `services/agents/prompts/` with PRD 15c prompt as v1

## Phase 1 — Data catalogs & contracts
- [ ] Data loaders for MCC catalogs from `requirements/data/catalogs/`
- [ ] SQL migrations for PRD 6a tables (dev/local only)
- [ ] Great Expectations stubs (schema/quality) for future activation

## Phase 2 — API contracts
- [ ] Implement `POST /api/v1/mcc/recommend` (PRD 3b/71) with idempotency
- [ ] Stubs for `/v1/submit_merchant`, `/v1/get_recommendation`, `/v1/simulate_impact`, `/v1/list_runs`, `/v1/get_run`, `/v1/ingest_profile`
- [ ] Error taxonomy responses and validation
- [ ] Contract tests and smoke script

## Phase 3 — CrewAI orchestration (to follow)
- [ ] Agents & prompts per PRD 5/5a
- [ ] Strict JSON validation, retries, provenance

## Phase 4 — LLM integration (to follow)
- [ ] JSON-mode + fallback; schema enforcement; backoff/circuit breaker

## Phase 5 — Impact simulator (to follow)
- [ ] Benchmark cohorts and simulator endpoints

## Phase 6 — Web intelligence & RAG (to follow)
- [ ] Scraper, chunk/embed, retrieval API, artifacts

## Phase 7 — Governance & decision package (to follow)
- [ ] Arbiter policies, risks/controls, final package

## Phase 8 — Observability & quality (to follow)
- [ ] OTEL traces, logs, dashboards, synthetic checks

## Phase 9 — DevOps/IaC scaffolding (to follow)
- [ ] Terraform modules layout and pipelines stubs

## Phase 10 — UI and MCP (to follow)
- [ ] MCP tools, UI skeleton later
