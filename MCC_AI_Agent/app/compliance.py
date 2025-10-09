from typing import Dict, Any, List


def analyze_compliance(website_summary: str | None, web_intel: Dict[str, Any] | None, key_pages: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
	"""Heuristic compliance analyzer (LLM-free) using available intel.

	Returns overall_risk_score 0-100, risk_flags, and structured findings.
	"""
	findings: List[Dict[str, Any]] = []
	risk_flags: List[str] = []

	ws = (website_summary or "").lower()
	intel = web_intel or {}
	pages = key_pages or intel.get("key_pages") or []
	page_urls = "\n".join([str(p.get("url", "")).lower() for p in pages])

	def add(issue: str, severity: str, url: str | None = None, snippet: str | None = None, flag: str | None = None):
		findings.append({"issue": issue, "severity": severity, "evidence_url": url, "snippet": snippet})
		if flag:
			risk_flags.append(flag)

	# Required pages
	if "privacy" not in page_urls:
		add("Privacy policy not found", "medium", flag="missing_privacy")
	if "terms" not in page_urls and "conditions" not in page_urls:
		add("Terms/Conditions page not found", "medium", flag="missing_terms")
	if "return" not in page_urls and "refund" not in page_urls:
		add("Returns/Refunds policy not found", "low", flag="missing_returns")

	# Continuity/subscription cues
	if any(k in ws for k in ["subscribe", "subscription", "auto-renew", "auto renew"]):
		add("Subscription/continuity present; verify cancellation clarity", "high", flag="subscription")

	# Claims cues in health/finance
	regulated = ["cure", "treat", "diagnose", "returns guaranteed", "risk-free"]
	if any(k in (ws or "") for k in regulated):
		add("Potential regulated/marketing claims detected", "high", flag="claims_risk")

	# Basic HTTPS/checkout cue (best-effort via key pages)
	if not any("checkout" in (p.get("url", "").lower()) for p in pages):
		add("Checkout page not observed (best-effort)", "low")

	# Compute very rough risk score
	weights = {"high": 30, "medium": 15, "low": 5}
	score = sum(weights.get(f.get("severity"), 0) for f in findings)
	score = max(0, min(100, score))

	return {"overall_risk_score": score, "risk_flags": sorted(list(set(risk_flags))), "findings": findings}


