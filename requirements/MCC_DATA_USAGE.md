## MCC Data Usage (Agent Context)

Purpose: Document how existing MCC datasets are used by the MCC AI Underwriting Agent.

### Datasets
- mcc_codes: authoritative MCC codes and descriptions from `ic_optimization.mcc_codes`.
- mcc_ranking_portfolio: portfolio-level MCC performance (IC rates, volatility, volumes, ranks).
- merchant_kpis_monthly: per-merchant KPIs used for benchmarking and impact simulation.
- gold_set: adjudicated MCC labels for evaluation/calibration.

### How the agent uses them
- Candidate generation: `mcc_codes` provides the valid MCC universe; rule-based exclusions can be layered later if needed.
- Scoring & impact: `mcc_ranking_portfolio` provides baseline IC characteristics by MCC for expected IC delta; benchmark cohorts are formed using `merchant_kpis_monthly` (industry/volume/ticket).
- Evaluation: gold set is the ground truth for Top-1/Top-3 accuracy and calibration metrics.
- Governance: decisions record the snapshot/version used (provenance).

### Refresh & provenance
- Codes: exported from existing MySQL (`ic_optimization.mcc_codes`) via `scripts/export_mysql_mcc_data.py` and loaded via `scripts/seed_from_csv.py`.
- Rankings: exported from existing MySQL (`ic_optimization.mcc_ranking`) via `scripts/export_mysql_mcc_data.py` and loaded via `scripts/seed_from_csv.py`.
- KPIs: seeded locally via samples; in cloud, loaded from Aurora mirrors nightly.

### Local/CI usage
- Use `make export` (with SRC_ env vars) to snapshot current rankings/codes into `data/catalogs/`.
- Run `make seedcsv` (with TGT_ env vars) to load into the agent schema.
- For CI, avoid real data; rely on samples and headers only.
