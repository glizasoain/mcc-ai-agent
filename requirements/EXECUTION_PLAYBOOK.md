## MCC AI Underwriting Agent – Execution Playbook (Chronological)

This playbook prioritizes a local, containerized demo first, then AWS dev → stg → prod rollout. Follow in order unless noted otherwise.

### 0) Prep (Local Machine)
- Ensure Docker Desktop and Conda are installed
- Pull repository and checkout `main`
- Create Conda env
```bash
conda create -y -n mcc-underwriter python=3.11
conda activate mcc-underwriter
pip install -r requirements.txt
```

### 1) Local Services (for demo)
Goal: Run everything locally to demo from your laptop.

- Bring up local infra (OpenSearch, S3-compatible, queues) via Docker
  - If you have VPN access to Aurora dev, you can skip local MySQL and point to Aurora; otherwise, use a local MySQL container.
- Suggested services:
  - OpenSearch (vector store)
  - MinIO (S3-compatible) for artifacts
  - LocalStack (optional) for SQS emulation
  - MySQL container (optional) if not using Aurora dev

Example (adjust to your tooling):
```bash
# Example: run OpenSearch locally (single node)
docker run -d --name os \
  -p 9200:9200 -e discovery.type=single-node \
  -e OPENSEARCH_SECURITY_DISABLED=true \
  opensearchproject/opensearch:latest

# Example: run MinIO locally
docker run -d --name minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minio -e MINIO_ROOT_PASSWORD=minio123 \
  quay.io/minio/minio server /data --console-address :9001

# (Optional) Local MySQL (if not using Aurora dev)
docker run -d --name mysql -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=data_engineering mysql:8
```

- Configure `.env.local` (do not commit)
```bash
OPENAI_API_KEY=sk-...
DB_URI=mysql+pymysql://root:root@127.0.0.1:3306/data_engineering  # or Aurora dev URI
OPENSEARCH_ENDPOINT=http://127.0.0.1:9200
S3_ENDPOINT=http://127.0.0.1:9000
S3_BUCKET=mcc-artifacts
```

### 2) Initialize Data (Local)
- Create S3 bucket in MinIO console (http://localhost:9001)
- Seed schemas in MySQL (local or Aurora dev) per PRD Section 6a
  - `merchants`, `merchant_kpis_monthly`, `mcc_catalog`, `runs`, `recommendations`, `artifacts`, `idempotency_keys`
- Seed sample data
  - Import MCC catalogs (Visa/MC/Amex/Disc) into `mcc_catalog`
  - Insert a small gold set (≈ 20–50 merchants) and KPIs into `merchants`/`merchant_kpis_monthly`

### 3) Run Services Locally
- API (FastAPI)
```bash
make run-api   # or: uvicorn services.api.main:app --reload --port 8080
```
- Agents/Workers (CrewAI)
```bash
make run-agents  # background workers consuming queue or local task runner
```
- Scraper (Playwright/requests/bs4)
```bash
python services/scraper/run.py --merchant-id <MID>
```

### 4) Local Demo Flow
1. Submit merchant (chat UI or REST)
2. Verify scrape artifacts in MinIO; embeddings indexed in OpenSearch
3. Retrieve recommendation; review top-3 MCC with confidence and deltas
4. Run `simulate_impact` for a candidate MCC
5. Approve in UI; verify write-back to `recommendations` and audit artifacts

Example REST calls:
```bash
curl -X POST http://localhost:8080/v1/submit_merchant -H 'Content-Type: application/json' \
  -d '{"legal_name":"Travorium","urls":["https://example.com"]}'

curl http://localhost:8080/v1/get_recommendation?run_id=<uuid>
```

### 5) Hardening for Local Demo
- Add 10–20 diversified merchants to show breadth
- Pre-warm caches and embeddings to reduce cold-start latency
- Validate idempotency and error responses (e.g., rate limiting, invalid input)
- Capture a short script to run the demo end-to-end

---

### 6) Dev Environment (AWS) – Ask DevOps
Use `DEVOPS_PROVISIONING_CHECKLIST.md` and Terraform stubs.
- Request: provision dev stack for “MCC AI Underwriting”
  - VPC, OpenSearch Serverless, S3 buckets, SQS, Cognito, ECS Fargate (api/agents/scraper), ALB/WAF, Secrets Manager
  - Wire to existing Aurora MySQL (security groups/secrets)
- CI/CD: enable Bitbucket OIDC role and pipelines (lint/test/build/infra/deploy)
- Validate exits in the checklist (API reachable, kNN works, S3 read/write, SQS consume)

### 7) Deploy to Dev (AWS)
- Build and push images to ECR (via pipelines)
- Apply Terraform in `environments/dev`
- Deploy services (api/agents/scraper) with environment variables from Secrets Manager
- Smoke tests: health, submit/get_recommendation, simulate_impact, audit artifacts

### 8) Staging (AWS)
- Promote artifacts; apply infra changes in `stg`
- Import larger gold set; run evaluations against acceptance metrics
- Red-team prompts; performance/load tests; tune autoscaling

### 9) Production (AWS)
- Manual approval; blue/green or rolling deploy
- Enable alarms/dashboards and on-call
- Weekly eval reports and monthly security review

### Decision Tree: Local vs Cloud First
- If you need an immediate demo: run local-first (Sections 1–5)
- If you need team access and repeatability: provision dev (Sections 6–7)
- Hybrid: connect local services to Aurora dev if available (best UX)

### Handy Commands
```bash
make dev        # install dev deps, pre-commit hooks
make test       # run unit/integration
make build      # build docker images
make deploy     # deploy to current env (requires CI creds)
```

### Notes
- Keep `.env.local` for local dev only; secrets must live in AWS Secrets Manager in cloud
- For scraping, respect robots.txt by default; override only via admin flag in dev/stg with approval
- Prefer `Idempotency-Key` header on POSTs during demos to show retry safety


