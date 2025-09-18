## DevOps Provisioning Checklist – Dev Environment (MCC AI Underwriting Agent)

Owner: DevOps
Goal: Provision the dev stack via Terraform; enable API hello-world deployment and basic E2E.

### 0) Pre-requisites
- AWS account and target region (dev): us-east-1
- Terraform remote state: S3 bucket + DynamoDB table for locks (KMS-encrypted)
- Bitbucket OIDC -> AWS role for CI deploys (dev)
- KMS CMKs: one per data domain (logs, artifacts, OpenSearch)

### 1) Networking (module: network)
- [ ] VPC, 2-3 public + 2-3 private subnets across ≥2 AZs
- [ ] NAT gateway(s) for private subnets
- [ ] VPC endpoints (S3, Secrets Manager, OpenSearch)
- [ ] Security groups: ALB, ECS tasks (api/agents/scraper), OpenSearch

### 2) Storage & Data
- [ ] S3 buckets: artifacts, logs (versioning, lifecycle: logs 30d, artifacts 180d)
- [ ] KMS encryption on S3 buckets
- [ ] Aurora MySQL access: SG rules from ECS tasks; endpoint and creds (from existing cluster)
- [ ] (Optional later) Aurora Postgres for pgvector – skip for now

### 3) OpenSearch Serverless (module: opensearch_serverless)
- [ ] Create collection for `mcc-underwriter`
- [ ] Security policy (network + encryption), data access role(s)
- [ ] Index templates: `web_chunks`, `catalog_chunks` (vector mapping, dim=1536)

### 4) IAM & Secrets (module: security)
- [ ] Secrets Manager entries: OPENAI_API_KEY, AURORA_MYSQL_URI, COGNITO_CLIENT_SECRETS
- [ ] Rotation policy set to 90 days (where applicable)
- [ ] Task roles for ECS services (least-privilege): read secrets, S3 R/W, OpenSearch access, SQS

### 5) Queues & Scheduling (module: queues)
- [ ] SQS: work queue + DLQ for agents; permissions for ECS tasks
- [ ] EventBridge: nightly benchmark refresh, weekly eval job rules

### 6) Edge & Security (module: edge)
- [ ] ALB + target groups for API service
- [ ] WAF attached to ALB; baseline rules (bot control, geo US-only as needed)
- [ ] TLS certs (ACM) for API domain (dev)

### 7) Identity (module: cognito)
- [ ] Cognito User Pool with Google IdP
- [ ] App client(s); groups: Underwriter, RiskAgent, Admin, Auditor
- [ ] Callback URLs for UI (if applicable later)

### 8) Compute (module: ecs_service)
- [ ] ECS cluster (Fargate)
- [ ] Services: `api`, `agents`, `scraper` with task defs, autoscaling policies
- [ ] Logs to CloudWatch; OTEL sidecar optional

### 9) Observability
- [ ] CloudWatch dashboards: latency P95/P99, error rate, queue depth, CPU/mem
- [ ] Alarms: API 5xx, ECS task failures, SQS age/depth, OpenSearch health
- [ ] Log retention (30–90d per PRD)

### 10) CI/CD (Bitbucket Pipelines)
- [ ] Configure OIDC in AWS and Bitbucket repo
- [ ] Set repo variables (non-secret) and secure variables (deploy role ARN, region)
- [ ] Enable pipelines stages: lint, test, build, infra:plan/apply (manual), deploy

### 11) Policies & Egress
- [ ] Outbound egress allowlist for scraper (maintained via Terraform variable)
- [ ] robots.txt respect default; feature flag for admin override (off by default)

### 12) Validations (Exit Criteria)
- [ ] `terraform plan` and `apply` succeed in dev
- [ ] API hello-world endpoint responding via ALB with Cognito protection
- [ ] OpenSearch index write/read test passes (vector insert + kNN query)
- [ ] S3 artifact write/read; Secrets fetch from ECS
- [ ] SQS produce/consume by `agents` service

Notes
- Use environment-specific prefixes/suffixes in resource names
- All encryption at rest via KMS; TLS enforced everywhere
- Record ARNs/URLs in Terraform outputs
