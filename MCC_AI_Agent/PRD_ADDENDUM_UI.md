## PRD Addendum: Underwriter UI (Decision + Chat), styled like trycast.com

### Objectives
- Present a clear MCC decision package (final MCC, ranked alternatives, rationale, benchmarks, deltas).
- Provide a chat workbench to ask questions about the merchant and the evidence (post‑research Q&A), with strict citations.
- Use a clean, modern aesthetic inspired by trycast.com: dark theme by default, high-contrast typography, subtle shadows, rounded cards, accent color for actions.

### Layout
- Two-pane responsive layout
  - Left: Decision Panel (sticky on desktop; collapsible on mobile)
  - Right: Research Chat (full-height, streaming)

### Intake & Submission (Top of Decision Panel)
- Intake Card (collapsible when a run is active)
  - Fields (mapped to API `/api/v1/mcc/recommend`):
    - legal_name (text)
    - dba_name (text)
    - websites (tagged URL list; validates http/https)
    - merchant_description (multiline; optional)
    - profile:
      - industry (select/autocomplete)
      - vertical (select/autocomplete)
      - country (ISO select)
      - avg_ticket (number)
      - volume_band (select: small/mid/large)
    - force (checkbox)
    - Idempotency-Key (auto-generated; reveal/copy)
  - Actions:
    - “Analyze Merchant” (POST recommend)
    - “Reset Form”
  - Validation:
    - At least one of legal_name|dba_name|websites required
    - URLs normalized to https://
  - States:
    - Submitting (spinner)
    - Error (inline message + retry)
    - Success (scroll to Decision Panel with anchor)

### Decision Panel (Left)
- Header
  - Merchant name, legal/DBA, website
  - Badge: status (completed | needs review)
- Final Recommendation Card
  - MCC code + title
  - Confidence, short rationale (1–2 lines), “View full rationale” expands
  - Quick links: “View sources,” “Compare alternatives,” “Simulate impact”
- Ranked Alternatives (mcc_proposal.ranked)
  - For each entry: mcc, description, confidence
  - Optimization: average_ic_rate, average_decline_rate_pct, and deltas vs current_mcc
  - Benchmark cohort: cohort_ref/source; optional example_merchant_name/url when allowed
  - “Compare vs selected” button (opens side-by-side diff modal)
- Business Description
  - core_revenue_stream, channels, MoR, flows, monetization, target_customers, regulated_flags
  - Collapsible evidence list (URLs/quotes)
- Actions
  - Approve MCC → confirmation modal → audit trail
  - Request Review → comment box, assign reviewer

### Research Chat (Right)
- System prompt scoped to the selected run only; retrieval over:
  - web_intel evidence snippets and crawled pages (stored artifacts)
  - business_description
  - brand inference and provenance
  - mcc_proposal (ranked list, metrics/deltas)
- Guardrails
  - Answer strictly from data; cite sources (URL + snippet)
  - If insufficient data, say so and suggest specific follow-ups
- Preset prompts (chips)
  - “Why not the runner-up?”
  - “Show evidence for merchant_of_record”
  - “Compare MCC 5732 vs 5999 on this merchant”
  - “List pages mentioning subscriptions/pricing”
- Streaming responses; copy code/JSON buttons where relevant

### Branding & Style (trycast-inspired)
- Dark mode default; light mode toggle in header
- Typography: Neutral sans for UI; mono for code/JSON blocks
- Cards: rounded corners, 1px border, soft shadow, subtle glass on hover
- Accent color: single brand hue for primary actions and focus rings
- Icons: thin outline style; clear affordances

### States & Errors
- Loading skeletons for decision cards and chat messages
- Empty state messaging when data missing (benchmarks, brand inference)
- Error toasts with retry for chat and data fetches
- Needs Review banner when confidence < threshold or contradictions detected

### Accessibility & Perf
- Keyboard navigation, ARIA landmarks/labels, color contrast ≥ WCAG AA
- Lazy-load long evidence lists; virtualize large tables
- Streaming chat to keep TTI low; client cache for run data

### API/Integration
- Existing endpoints: /api/v1/mcc/recommend, /api/v1/get_run, /api/v1/list_runs
- New (future): /api/v1/chat (retrieval Q&A over stored artifacts/provenance for selected run)
- Feature flags (admin): enable_chat, show_benchmarks_examples, dark_default

### Telemetry
- UI events: compare_clicked, approve_clicked, chat_question_submitted, evidence_opened
- Latency metrics for first decision render and chat response TTFB/TTFR


