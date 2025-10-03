## PRD Addendum: MCP (Merchant Classification Proposal) Object

### Goal
Provide a single, clear root object that contains a ranked proposal of MCC options with supporting rationale and benchmark context.

### Response Shape (new root object)
```
"mcp_proposal": {
  "ranked": [
    {
      "mcc": "4511",
      "description": "Airlines, Air Carriers",
      "rationale": "Direct first‑party airline ticketing (book/manage/CoC evidence)...",
      "confidence": 95,
      "benchmark": {
        "cohort_ref": "portfolio:mcc:4511",
        "cohort_source": "mcc_portfolio",
        "average_ic_rate": 0.01875,
        "average_decline_rate_pct": 1.9,
        "example_merchant": "United Airlines"  // optional when available and allowed
      }
    },
    {
      "mcc": "4722",
      "description": "Travel Agencies and Tour Operators",
      "rationale": "OTA/multi‑airline language present...",
      "confidence": 60,
      "benchmark": {
        "cohort_ref": "portfolio:mcc:4722",
        "cohort_source": "mcc_portfolio",
        "average_ic_rate": 0.01710,
        "average_decline_rate_pct": 2.7
      }
    }
  ]
}
```

### Notes
- Ranked list MUST be ordered highest to lowest by overall score (confidence then optimization).
- `example_merchant` is optional; include only when policy allows; otherwise omit.
- Existing fields (final recommendation, provenance, website_summary, etc.) remain unchanged; this adds a canonical container for ranked options.


