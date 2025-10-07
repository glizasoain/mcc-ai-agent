## PRD Addendum: Business Model Analyst Agent

### Purpose
Produce a normalized, decision-ready business model summary from legal/DBA names, web intelligence, brand inference, and basic KPIs to reduce ambiguity before MCC selection.

### Inputs
- legal_name, dba_name
- websites (primary + alt)
- web_intel JSON (facts/evidence)
- brand inference (brand_key, brand_mcc, match_score)
- profile (industry, vertical, country, avg_ticket, volume_band)
- basic KPIs when available (decline_rate_pct, effective_ic_rate)

### Output (STRICT JSON)
```
{
  "core_revenue_stream": string,
  "primary_offering": string,
  "channels": ["D2C"|"B2B"|"marketplace"],
  "merchant_of_record": "first_party"|"agency"|"mixed"|"unknown",
  "transaction_flows": ["CP","CNP"],
  "monetization": ["retail","subscription","usage","MDR","interchange++","services"],
  "target_customers": [string],
  "regulated_flags": [string],
  "brand_match": { "brand_key": string|null, "brand_mcc": string|null, "match_score": 0-100 },
  "key_evidence": [{ "quote": string, "url": string }]
}
```

### Orchestration
Web Intelligence → Business Model Analyst → Candidate Selector → Decision → Review.


