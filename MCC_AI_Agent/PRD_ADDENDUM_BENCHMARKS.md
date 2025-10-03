## PRD Addendum: Benchmarks in Provenance

### Requirement
- For every recommendation, include benchmark cohort references in provenance so reviewers understand which benchmarks informed decline/IC estimates.
- Do not list specific benchmark merchants; include cohort identifiers and data source references only.

### Response Additions
- `top_k[]` entries may include:
  - `weighted_avg_ic_rate` (from portfolio)
  - `decline_rate_pct` (from portfolio)
  - `cohort_ref`: short identifier of the benchmark cohort (e.g., `portfolio:mcc:{code}`)
  - `cohort_source`: data source tag (e.g., `mcc_portfolio`)

- Provenance additions:
  - `_benchmark_source`: `{ source: "mcc_portfolio", version?: string }`

### Notes
- As richer cohorts (industry/volume/avg_ticket) arrive, `cohort_ref` should encode these facets (e.g., `portfolio:mcc:{code}:vol:{band}:ticket:{bucket}`).


