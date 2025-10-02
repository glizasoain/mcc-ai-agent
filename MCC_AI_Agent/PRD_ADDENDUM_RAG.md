## PRD Addendum: MCC Catalog RAG (Retrieval-Augmented Generation)

### Purpose
Improve MCC selection accuracy and determinism by retrieving a small, relevant subset of MCC candidates from a vectorized catalog and constraining the LLM to choose from those candidates only, while preserving deterministic overrides for brand-specific codes.

### Indexing
- Corpus: Each MCC catalog row as a single document: code, canonical description, aliases/synonyms, example merchant types.
- Embeddings: OpenAI `text-embedding-3-large` (1536-d). Store vectors per MCC in a local table `mcc_embeddings` (dev) and later in OpenSearch Serverless (prod).
- Refresh: Rebuild on startup if empty or catalog version changes.

### Query Construction
- Build a dense query from Web Intelligence fields: `core_offering`, `primary_revenue_stream`, `sales_model`, `transaction_flow`, `verticals`, plus `merchant_description` and brand name if present.
- Hybrid scoring (initially dense-only; BM25 optional later). Retrieve top-k (5–10) MCCs by cosine similarity.
- Option B (full-catalog mode): run the Selector against the entire catalog (code+description) to produce a global score distribution, then keep top-k for the Decision step. Use sparingly due to token/cost.

### Deterministic Overrides
- Brand-specific MCC map (e.g., airlines: `united` → `3000`). If matched, inject into candidate list at rank 1.
- Airline vs agency rule: prefer 4511 when first-party airline cues present; prefer 4722 for OTAs.

### LLM Usage
- Provide only the retrieved/overridden candidates to the classifier with their descriptions; instruct “choose from these only.”
- Require justification and “why not the runner-up,” citing web evidence.
- Post-validate: reject any MCC not in candidates; fall back to rules or needs_review=true.

### Telemetry/Provenance
- Log `retrieval_query`, `candidate_codes`, `embedding_model`, and catalog version.

### Local Dev Scope
- Implement using `mcc_embeddings` MySQL table for vectors. Defer OpenSearch integration to cloud phase.


