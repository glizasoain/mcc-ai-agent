## PRD Addendum: Generalized MCC Disambiguation Framework

### Goal
Provide a domain-agnostic decision system that combines deterministic signals, RAG, and LLM reasoning to select the correct MCC with evidence, while handling ambiguous merchant categories reliably.

### Components
- Signals extractor: computes weighted cues from web intel (pages, titles, evidence) across families (airline↔agency, marketplace↔retail, SaaS↔services, telecom, healthcare, adult/gambling, charity, utilities). Outputs per-family scores and fired cues with URLs.
- Brand overrides: DB table of brand/domain patterns → MCC (e.g., first-party airlines). Applied deterministically when matched.
- RAG shortlisting: retrieve 5–10 MCC candidates from the catalog embeddings using a query built from web intel + signals; merge with family-driven candidates and overrides.
- LLM selection: constrained to candidate set; must justify and explain “why not” the runner-up, citing URLs.
- Governance: post-validate code ∈ catalog; export provenance (fired_signals, family_scores, candidate_set, retrieval_query, overrides_used).

### Signals (examples)
- Airline cues: book/check-in/manage/flight-status/baggage/contract-of-carriage/routes.
- Agency cues: multi-airline search/compare, OTA phrasing, IATA agency text, hotel/car/cruise primary.
- Marketplace vs retail: multi-seller wording, seller onboarding, category breadth vs single-brand product pages.
- SaaS vs services: pricing tiers, docs/API, subscription billing vs consulting verbiage.
- Merchant-of-record: refund issuer, terms style, brand on checkout, schema.org JSON-LD types.

### Decision
1) If brand override hits and signals confirm first-party, return override MCC (high confidence).
2) Else compute family scores and build candidate set (families + RAG + heuristics). Enforce candidate-only selection.
3) Confidence from score margin and evidence density; ambiguous → needs_review=true.

### Data
- Table: brand_mcc_overrides(domain_pattern, brand_key, mcc_code, notes, updated_at)
- Table: mcc_embeddings (already defined in RAG addendum)


