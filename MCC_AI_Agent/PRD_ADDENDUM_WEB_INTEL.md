## PRD Addendum: Web Intelligence Analyst Agent

### Purpose
Deeply analyze merchant websites to extract structured, MCC-relevant facts and evidence for classification. This agent precedes the Classifier and Reviewer and produces a concise, structured summary that feeds into the classification prompt.

### Inputs
- merchant_id
- websites (list; primary URL selected)
- merchant_description (underwriter free text)
- business_registration_name (from DB when available)
- profile context (industry, vertical, country, avg_ticket, volume_band)

### Web Intelligence Process
- Focused same-domain crawl (default depth 3, max 50 pages, 8s budget)
- Prioritize paths: /solutions, /products, /features, /pricing, /docs, /about, /company, /partners
- Filter static/media; denoise text; dedupe
- Respect env-configured limits; robots.txt respect to be added in Phase 6 hardening

### Output (STRICT JSON)
```
{
  "core_offering": string,
  "primary_revenue_stream": string,
  "target_customers": string,
  "sales_model": string,               // e.g., direct SaaS, reseller, marketplace, ISO/agent
  "transaction_flow": string,          // card-present vs card-not-present, gateway, aggregator/acquirer hints
  "pricing_model": string,             // subscription, usage, MDR, blended, interchange++
  "regulated_keywords": string,        // PCI, HIPAA, KYC, high-risk, surcharging, BNPL, crypto, adult
  "compliance_indicators": string,     // PCI DSS, 3DS, tokenization, chargeback tools, risk
  "verticals": string,                 // industries served
  "integrations": string,              // PSPs, acquirers, ISVs referenced
  "excluded_lines": string,            // explicit non-offerings
  // Domain-specific disambiguation cues
  "is_first_party_airline": boolean,   // true if booking/manage/contract-of-carriage present and brand matches airline
  "is_travel_agency": boolean,         // true if OTA language, multi-airline booking, IATA agency wording
  "key_pages": [{ "url": string, "title": string }],
  "evidence": [{ "quote": string, "url": string }]
}
```

### Orchestration
1. Web Intelligence Analyst produces the structured JSON and a brief website_summary
2. Classifier consumes profile + merchant_description + website_summary + structured evidence and proposes MCC JSON
3. Reviewer validates schema and coherence; returns corrected JSON

### Policies
- No fabricated data; cite evidence URLs
- Lower confidence if primary revenue unclear
- Always choose MCC for core revenue-generating activity

### Telemetry
- Capture agents_involved, prompt_hash, llm_model


