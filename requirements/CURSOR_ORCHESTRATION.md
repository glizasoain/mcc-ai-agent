## Cursor Orchestration Guide (Local & CI)

Goal: Enable Cursor to run the entire project from requirements to demo.

### Steps Cursor should take (local):
1. Ensure Conda env `mcc-underwriter` (python 3.11); install `requirements.txt`.
2. Start local services via `docker-compose` (OpenSearch, MinIO, optional MySQL).
3. Seed Aurora/MySQL schemas (or local MySQL) using `scripts/db_seed.py` (Cursor to generate if missing) per PRD Section 6a.
4. Import MCC catalogs and sample KPIs (Cursor to run seed scripts).
5. Launch API (FastAPI) and Agents (CrewAI) using `make run-api` and `make run-agents`.
6. Run scraper for a sample merchant and index embeddings.
7. Execute demo flow: submit_merchant → get_recommendation → simulate_impact → approve.
8. Generate a short markdown demo report to `MCC_AI_Agent/demo_reports/`.

### Steps Cursor should take (CI):
- Use Bitbucket Pipelines to lint/test/build, run minimal integration with docker-compose, and produce artifacts.
- For deploy steps, call terraform plan/apply (manual gates), then push ECS updates.
