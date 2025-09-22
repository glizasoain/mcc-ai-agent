from typing import Optional, Dict, Any, List
import os

import time
import json
import re
import hashlib
from crewai import Agent, Task, Crew


# Simple circuit breaker
_CB_FAILURES = 0
_CB_OPEN_UNTIL_EPOCH_MS = 0
_CB_THRESHOLD = 3
_CB_COOLDOWN_MS = 30_000


def _cb_now_ms() -> int:
	return int(time.time() * 1000)


def _cb_allowed() -> bool:
	global _CB_OPEN_UNTIL_EPOCH_MS
	return _cb_now_ms() >= _CB_OPEN_UNTIL_EPOCH_MS


def _cb_record_failure():
	global _CB_FAILURES, _CB_OPEN_UNTIL_EPOCH_MS
	_CB_FAILURES += 1
	if _CB_FAILURES >= _CB_THRESHOLD:
		_CB_OPEN_UNTIL_EPOCH_MS = _cb_now_ms() + _CB_COOLDOWN_MS
		_CB_FAILURES = 0


def _cb_record_success():
	global _CB_FAILURES
	_CB_FAILURES = 0



def run_mcc_recommendation(merchant_id: str, website_url: Optional[str], profile: Optional[Dict[str, Any]] = None, merchant_description: Optional[str] = None, website_urls: Optional[List[str]] = None, business_registration_name: Optional[str] = None) -> Dict[str, Any]:
	classifier = Agent(
		role="MCC Classification Analyst",
		goal="Classify the correct Merchant Category Code (MCC) for the given merchant.",
		backstory=(
			"You are an expert analyst in card networks' MCC taxonomy. "
			"You ALWAYS return strict JSON with fields: merchant_name, recommended_mcc, confidence, justification. "
			"Confidence must be a number 0-100. recommended_mcc must be a 4-digit code."
		),
		allow_delegation=False,
		verbose=False,
	)

	reviewer = Agent(
		role="MCC Review Analyst",
		goal="Review and correct MCC classification JSON for accuracy and schema compliance.",
		backstory=(
			"You double-check recommended_mcc (4 digits), ensure confidence is 0-100 integer, and justification coherent. "
			"Return STRICT JSON with the same keys only."
		),
		allow_delegation=False,
		verbose=False,
	)

	prof = profile or {}
	all_sites = website_urls or []
	prompt = (
		"You are a Merchant Category Code (MCC) compliance expert.\n"
		"MCCs are 4-digit codes used by card networks to categorize a merchant's PRIMARY business activity for authorization, "
		"interchange, risk, and reporting. Always choose the MCC that reflects the merchant's core revenue-generating activity (not ancillary services).\n\n"
		"Instructions:\n"
		"- Return STRICT JSON only with keys: merchant_name, recommended_mcc (4 digits), confidence (0-100), justification.\n"
		"- Use the context below (industry, vertical, country, business registration, websites, existing_mcc, ticket/volume).\n"
		"- If uncertain, lower confidence and state which evidence is missing.\n\n"
		"Heuristics: SaaS/Software → 7372/7375; E-commerce retail → 5999/5732; Professional services → 7392/7399; "
		"Healthcare → 8011/8021/8099; Travel → 4722; Utilities → 4900.\n\n"
		"Context:\n"
		f"merchant_id: {merchant_id}\n"
		f"website: {website_url or ''}\n"
		f"websites: {', '.join(all_sites)}\n"
		f"merchant_description: {merchant_description or ''}\n"
		f"website_summary: {prof.get('website_summary')}\n"
		f"business_registration_name: {business_registration_name or ''}\n"
		f"industry: {prof.get('industry')}\n"
		f"vertical: {prof.get('vertical')}\n"
		f"country: {prof.get('country')}\n"
		f"existing_mcc: {prof.get('existing_mcc')}\n"
		f"avg_ticket: {prof.get('avg_ticket')}\n"
		f"volume_band: {prof.get('volume_band')}\n"
		"Respond ONLY in JSON with keys: merchant_name, recommended_mcc, confidence, justification."
	)
	prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

	classify_task = Task(
		description=prompt,
		expected_output=(
			"Strict JSON with keys: merchant_name (string), recommended_mcc (4-digit string), "
			"confidence (0-100 integer), justification (string)."
		),
		agent=classifier,
	)

	classify_crew = Crew(agents=[classifier], tasks=[classify_task])

	def normalize_and_validate(text: str) -> Dict[str, Any]:
		def parse_conf(val) -> int:
			if isinstance(val, (int, float)):
				c = int(val)
				return max(0, min(100, c))
			if isinstance(val, str):
				lowered = val.strip().lower()
				if lowered in {"high", "strong", "very high"}: return 85
				if lowered in {"medium", "moderate"}: return 60
				if lowered in {"low", "weak", "very low"}: return 30
				m = re.search(r"\d+", lowered)
				if m:
					n = int(m.group())
					return max(0, min(100, n))
			return 0

		def sanitize_mcc(val) -> str:
			s = str(val or "")
			m = re.search(r"\b(\d{4})\b", s)
			return m.group(1) if m else ""

		data: Dict[str, Any]
		try:
			data = json.loads(text)
		except Exception:
			start = text.find("{")
			end = text.rfind("}")
			if start != -1 and end != -1 and end > start:
				data = json.loads(text[start:end + 1])
			else:
				raise RuntimeError("CrewAI returned a non-JSON response")

		merchant_name = str(data.get("merchant_name") or merchant_id)
		recommended_mcc = sanitize_mcc(data.get("recommended_mcc"))
		confidence = parse_conf(data.get("confidence"))
		justification = str(data.get("justification") or "")

		# Strict validation
		if recommended_mcc and not re.fullmatch(r"\d{4}", recommended_mcc):
			raise RuntimeError("Invalid recommended_mcc format")
		if not (0 <= confidence <= 100):
			raise RuntimeError("Invalid confidence range")
		return {
			"merchant_name": merchant_name,
			"recommended_mcc": recommended_mcc,
			"confidence": confidence,
			"justification": justification,
		}

	if not _cb_allowed():
		raise RuntimeError("CrewAI circuit open")

	last_err: Optional[Exception] = None
	for attempt in range(3):
		try:
			# Step 1: Classification
			result_cls = classify_crew.kickoff()
			text_cls: str = getattr(result_cls, "raw", None) or getattr(result_cls, "output", None) or str(result_cls)
			parsed = normalize_and_validate(text_cls)

			# Step 2: Review & correction
			review_prompt = (
				"Review and correct the following MCC classification JSON. "
				"Ensure recommended_mcc is a 4-digit string, confidence is 0-100 integer, and justification aligns with inputs.\n"
				f"merchant_id: {merchant_id}\n"
				f"website: {website_url or ''}\n"
				f"websites: {', '.join(all_sites)}\n"
				f"merchant_description: {merchant_description or ''}\n"
				f"industry: {prof.get('industry')}\n"
				f"vertical: {prof.get('vertical')}\n"
				f"country: {prof.get('country')}\n"
				f"existing_mcc: {prof.get('existing_mcc')}\n"
				f"avg_ticket: {prof.get('avg_ticket')}\n"
				f"volume_band: {prof.get('volume_band')}\n"
				f"draft_json: {json.dumps(parsed)}\n"
				"Return STRICT JSON with keys: merchant_name, recommended_mcc, confidence, justification."
			)
			review_task = Task(
				description=review_prompt,
				expected_output=(
					"Strict JSON with keys: merchant_name (string), recommended_mcc (4-digit string), "
					"confidence (0-100 integer), justification (string)."
				),
				agent=reviewer,
			)
			review_crew = Crew(agents=[reviewer], tasks=[review_task])
			result_rev = review_crew.kickoff()
			text_rev: str = getattr(result_rev, "raw", None) or getattr(result_rev, "output", None) or str(result_rev)

			try:
				reviewed = normalize_and_validate(text_rev)
				parsed = reviewed
			except Exception:
				# keep original parsed if reviewer output invalid
				pass

			combined_hash = hashlib.sha256((prompt + "\n---\n" + review_prompt).encode("utf-8")).hexdigest()
			_cb_record_success()
			parsed["model"] = "crewai"
			parsed["prompt_hash"] = combined_hash
			parsed["_debug_prompt"] = prompt
			parsed["_agents"] = ["MCC Classification Analyst", "MCC Review Analyst"]
			# Try to surface underlying LLM model if available on agents (best-effort)
			try:
				llm_model = getattr(getattr(classifier, "llm", None), "model_name", None) or getattr(getattr(reviewer, "llm", None), "model_name", None)
				if not llm_model:
					llm_model = os.getenv("OPENAI_MODEL")
				if llm_model:
					parsed["llm_model"] = llm_model
			except Exception:
				pass
			return parsed
		except Exception as e:
			last_err = e
			time.sleep(0.6 * (2 ** attempt))

	_cb_record_failure()
	raise RuntimeError(f"CrewAI orchestration failed: {last_err}")


