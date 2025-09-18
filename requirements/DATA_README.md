## Data Package for MCC AI Underwriting Agent (Non-PII)

Purpose: Ship minimal, non-sensitive datasets with the repo so Cursor can run locally and in CI.

Contents:
- data/catalogs/: MCC catalogs per network (headers + examples). Replace with curated exports in dev/stg/prod.
- data/samples/: Small synthetic samples for merchants, KPIs, and gold set.
- data/manifests/: Data manifest describing sources, refresh cadence, and ownership.
- data/migrations/: SQL to create required Aurora MySQL tables.

Non-PII policy:
- Do not commit PII. Only synthetic or anonymized IDs and URLs.
- Real datasets should live in S3 or Aurora; seed via scripts.

Replace flow (dev/stg):
- Export curated MCC catalogs (CSV) to this folder in dev only, or point seeding to S3 location.
- Keep the schema migration file under version control.
