## Cursor Rules for MCC AI Underwriting Agent

- Use Python 3.11, FastAPI for API, CrewAI for orchestration.
- Enforce Pydantic models with strict types for all agent/tool I/O.
- All LLM calls must use JSON schema validation and retries on schema errors.
- Persist system-of-record data only in Aurora MySQL (`data_engineering`); no PII.
- Use OpenSearch Serverless for embeddings; use 1536-dim OpenAI embeddings.
- Implement role-based auth via Cognito (Google SSO) in API and UI.
- Code style: ruff/black/mypy enforced in CI; 90%+ unit test coverage for core logic.
- Directory layout:
  - `services/api` (FastAPI), `services/agents` (CrewAI), `services/scraper`, `ui/web` (Next.js), `infra/terraform`, `tools/mcp`.
- Provide Make targets: `make dev`, `make test`, `make build`, `make deploy`.
- Never commit secrets. Use AWS Secrets Manager and environment variables.
- Add contract tests for API and MCP; E2E tests for chat UI (Playwright).
- Logging: structured JSON, trace IDs; OTEL traces enabled in all services.
