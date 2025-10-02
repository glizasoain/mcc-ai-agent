## PRD Addendum: Business Legal Name and DBA Usage

### Requirement
- Collect merchant legal name and DBA (Doing Business As) name as part of API inputs.
- Persist both fields in the merchant registry.
- Use legal/DBA names in brand inference and MCC disambiguation.

### API
- RecommendRequest: add optional fields `legal_name`, `dba_name`.
- SubmitMerchantRequest: add optional fields `legal_name`, `dba_name`.

### Processing
- Include `legal_name` and `dba_name` in:
  - Web Intelligence context presented to agents
  - Brand inference (as high-signal name hints)
- Prefer brand-specific MCC only when first-party cues are present and brand match score (computed using legal/DBA/domain/evidence) exceeds threshold.

### Persistence
- Store `legal_name` and `dba_name` in `merchants` table.


