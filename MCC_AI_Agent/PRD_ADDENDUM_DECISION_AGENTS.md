## PRD Addendum: Two-Agent Decision Flow (Selector + Decision)

### Objective
Increase accuracy and generality by separating candidate generation from final selection:
- Candidate Selector: synthesizes a small shortlist with scores and evidence.
- Decision Agent: chooses exactly one MCC from the shortlist with a “why not runner-up” explanation.

### Inputs
- Web Intelligence JSON (structured facts + citations)
- Signals (family scores, fired cues)
- RAG candidates (top-k MCCs with descriptions)
- Optional brand hints (treated as candidates, not enforced)

### Candidate Selector (LLM)
- Task: Given intel, signals, and candidate pool (codes + descriptions), return JSON:
```
{
  "candidates": [
    { "code": "4511", "score": 92, "why": "direct airline booking...", "evidence": [ {"quote": "...", "url": "..."} ] },
    { "code": "4722", "score": 41, "why": "OTA language present..." }
  ],
  "top_two": ["4511", "4722"]
}
```
- Notes: score 0–100; cite URLs where possible; no codes outside the provided pool.

### Decision Agent (LLM)
- Task: Choose exactly one MCC from selector’s candidates. Return strict JSON:
```
{ "merchant_name": str, "recommended_mcc": "dddd", "confidence": 0–100, "justification": str }
```
- Constraints: must pick from provided candidates; justify “why chosen” and “why not the runner-up,” citing URLs. Lower confidence if evidence sparse.

### Governance
- Post-validate: MCC must be 4 digits and in the candidate set.
- Provenance: store selector shortlist, scores, and fired signals.


