# Bitbucket Pipelines Variables (dev)

Repository variables (non-secret):
- AWS_REGION=us-east-1
- ENV=dev

Secure variables (Repository or Deployment variables):
- AWS_ROLE_ARN=<oidc-deploy-role-arn>
- OPENAI_API_KEY (for dev only if needed in CI)

Notes:
- Prefer Secrets Manager for runtime secrets; CI only holds minimal deploy creds.
