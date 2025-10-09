## PRD Addendum: Compliance Analyst Agent

### Purpose
Add a dedicated Compliance Analyst to identify website compliance risks and surface actionable findings to the underwriter and the decision agents.

### Inputs
- website_summary (concise summary of site content)
- web_intel (structured intel: core_offering, revenue, target_customers, evidence URLs/snippets)
- business_description (normalized business model)
- key URLs when available (terms/privacy/subscriptions/returns/pricing/contact)

### Checks
- Continuity/subscription disclosures (auto‑renew, cancellation clarity)
- Free‑trial/negative option compliance
- Pricing/fees transparency, surcharging indicators
- Claims in regulated domains (health, financial) and risky keywords
- Age‑restricted content; KYC/AML hints for financial services
- PCI/checkout security cues, presence of HTTPS and trust signals
- Required consumer pages present: Terms, Privacy, Returns/Refunds, Contact

### Output (JSON)
```
{
  "overall_risk_score": 0-100,
  "risk_flags": ["subscription", "claims_health", "missing_privacy"],
  "findings": [
    {"issue": "Missing or unclear cancellation policy", "severity": "high", "evidence_url": "https://...", "snippet": "..."},
    {"issue": "No returns policy found", "severity": "medium"}
  ]
}
```

### Integration
- Orchestrator: run after Web Intelligence; include `compliance_report` in API response.
- Decision agents: may down‑rank MCCs incompatible with high‑risk flags.
- Chat: include compliance findings as RAG snippets for compliance queries.
- UI: show a Compliance card with sortable findings by severity.

### Non‑goals
- No legal advice; provide findings and evidence, not definitive judgments.


