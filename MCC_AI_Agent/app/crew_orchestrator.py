from typing import Optional, Dict, Any, List
import os

import time
import json
import re
import hashlib
from crewai import Agent, Task, Crew
from urllib.parse import urlparse
from app.db import (
    get_mcc_description,
    get_brand_override,
    list_all_mcc_codes,
    get_portfolio_row,
    get_ic_optimization_metrics,
    get_merchant_kpis_aggregates,
    compute_bands,
    get_ic_optimization_metrics_band,
)
from app.rag import ensure_mcc_embeddings_built, retrieve_mcc_candidates
from app.signals import compute_signals, infer_brand
from app.db import load_brand_registry


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



def run_mcc_recommendation(merchant_id: str, website_url: Optional[str], profile: Optional[Dict[str, Any]] = None, merchant_description: Optional[str] = None, website_urls: Optional[List[str]] = None, business_registration_name: Optional[str] = None, web_pages: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
	# Deterministic brand-specific MCC overrides (example list; extend as needed)
	BRAND_MCC_OVERRIDES: Dict[str, str] = {
		"united": "3000",
		# "delta": "3001",
		# "american": "3002",
	}
	# Web Intelligence Analyst: produce structured evidence JSON
	intel_analyst = Agent(
		role="Web Intelligence Analyst",
		goal=(
			"Extract MCC-relevant facts from provided website context and underwriter inputs, "
			"returning STRICT JSON with fields: core_offering, primary_revenue_stream, target_customers, "
			"sales_model, transaction_flow, pricing_model, regulated_keywords, compliance_indicators, "
			"verticals, integrations, excluded_lines, key_pages, evidence."
		),
		backstory=(
			"You analyze merchant websites to identify their core revenue-generating activity. "
			"You never fabricate. Cite short quotes with URLs when possible."
		),
		allow_delegation=False,
		verbose=False,
	)

	business_model_analyst = Agent(
		role="Business Model Analyst",
		goal=(
			"Summarize the merchant's business model into normalized fields for MCC decision-making."
		),
		backstory=(
			"You read web intelligence, brand inference, and basic KPIs to identify core revenue, channels, MoR, flows, and monetization."
		),
		allow_delegation=False,
		verbose=False,
	)

	# Candidate Selector agent
	selector = Agent(
		role="Candidate Selector",
		goal=(
			"Given web intelligence, signals, and a pool of candidate MCC codes with descriptions, "
			"return a ranked shortlist (5-10) with scores (0-100), per-candidate reasoning, and citations."
		),
		backstory=(
			"You specialize in narrowing down MCC options. You DO NOT invent new codes. "
			"You only score and explain candidates provided to you."
		),
		allow_delegation=False,
		verbose=False,
	)

	# Decision agent
	decision = Agent(
		role="MCC Decision Analyst",
		goal=(
			"Choose exactly one MCC from a provided shortlist. Output strict JSON with merchant_name, "
			"recommended_mcc (4 digits), confidence (0-100), justification."
		),
		backstory=(
			"You decide the final MCC from a shortlist. You MUST pick from the shortlist only. "
			"You must justify why the chosen MCC fits and why the runner-up does not, citing URLs."
		),
		allow_delegation=False,
		verbose=False,
	)

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

	# Prepare concise web pages context for the intel agent
	pages_ctx: List[Dict[str, str]] = []
	if web_pages:
		for p in web_pages[:8]:
			pages_ctx.append({
				"url": str(p.get("url") or ""),
				"title": str(p.get("title") or ""),
				"text": str(p.get("text") or "")[:1200],
			})

	intel_prompt = (
		"Analyze the following merchant context and website content to extract MCC-relevant facts.\n"
		"Return STRICT JSON ONLY with keys: core_offering, primary_revenue_stream, target_customers, "
		"sales_model, transaction_flow, pricing_model, regulated_keywords, compliance_indicators, verticals, "
		"integrations, excluded_lines, is_first_party_airline, is_travel_agency, key_pages (array of {url,title}), "
		"evidence (array of {quote,url}).\n\n"
		"Context:\n"
		f"merchant_id: {merchant_id}\n"
		f"websites: {', '.join(all_sites)}\n"
		f"merchant_description: {merchant_description or ''}\n"
		f"business_registration_name: {business_registration_name or ''}\n"
		f"legal_name: {business_registration_name or ''}\n"
		f"industry: {prof.get('industry')}\n"
		f"vertical: {prof.get('vertical')}\n"
		f"country: {prof.get('country')}\n"
		f"website_summary: {prof.get('website_summary')}\n"
		f"pages: {json.dumps(pages_ctx)}\n"
		"Respond ONLY with the JSON object."
	)

	prompt = (
		"You are a Merchant Category Code (MCC) compliance expert.\n"
		"MCCs are 4-digit codes used by card networks to categorize a merchant's PRIMARY business activity for authorization, "
		"interchange, risk, and reporting. Always choose the MCC that reflects the merchant's core revenue-generating activity (not ancillary services).\n\n"
		"Instructions:\n"
		"- Return STRICT JSON only with keys: merchant_name, recommended_mcc (4 digits), confidence (0-100), justification.\n"
		"- Use the context below (industry, vertical, country, business registration, websites, current_mcc, ticket/volume).\n"
		"- If uncertain, lower confidence and state which evidence is missing.\n\n"
		"Heuristics: SaaS/Software → 7372/7375; E-commerce retail → 5999/5732; Professional services → 7392/7399; "
		"Healthcare → 8011/8021/8099; Travel agency → 4722; Airline (first-party) → 4511; Utilities → 4900.\n\n"
		"Context:\n"
		f"merchant_id: {merchant_id}\n"
		f"website: {website_url or ''}\n"
		f"websites: {', '.join(all_sites)}\n"
		f"merchant_description: {merchant_description or ''}\n"
		f"website_summary: {prof.get('website_summary')}\n"
		f"business_registration_name: {business_registration_name or ''}\n"
		f"current_mcc: {prof.get('current_mcc')}\n"
		f"industry: {prof.get('industry')}\n"
		f"vertical: {prof.get('vertical')}\n"
		f"country: {prof.get('country')}\n"
		f"avg_ticket: {prof.get('avg_ticket')}\n"
		f"volume_band: {prof.get('volume_band')}\n"
		f"web_intel: will be provided separately as JSON\n"
		"Respond ONLY in JSON with keys: merchant_name, recommended_mcc, confidence, justification."
	)
	prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

	# Step 0: Web Intelligence task
	intel_task = Task(
		description=intel_prompt,
		expected_output=(
			"Strict JSON with keys: core_offering, primary_revenue_stream, target_customers, sales_model, "
			"transaction_flow, pricing_model, regulated_keywords, compliance_indicators, verticals, integrations, "
			"excluded_lines, key_pages, evidence."
		),
		agent=intel_analyst,
	)

	# Step 0.5: Business Model summary task
	# Ensure intel_json_for_debug has a default before first use
	intel_json_for_debug = "{}"
	model_summary_prompt = (
		"You are the Business Model Analyst. Produce a normalized JSON summary.\n"
		"Return STRICT JSON with keys: core_revenue_stream, primary_offering, channels(array), merchant_of_record, transaction_flows(array), "
		"monetization(array), target_customers(array), regulated_flags(array), brand_match(obj), key_evidence(array).\n\n"
		f"legal_name: {business_registration_name or ''}\n"
		f"web_intel: {(intel_json_for_debug or '{}')}\n"
		"Respond ONLY with the JSON object."
	)
	model_task = Task(
		description=model_summary_prompt,
		expected_output=(
			"Strict JSON with keys: core_revenue_stream, primary_offering, channels, merchant_of_record, transaction_flows, monetization, target_customers, regulated_flags, brand_match, key_evidence."
		),
		agent=business_model_analyst,
	)

	classify_task = Task(
		description=prompt,
		expected_output=(
			"Strict JSON with keys: merchant_name (string), recommended_mcc (4-digit string), "
			"confidence (0-100 integer), justification (string)."
		),
		agent=classifier,
	)

	# We'll run the intelligence task first to capture its JSON, then run classification using it

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
			# Step 0: Run Web Intelligence first and capture JSON
			intel_crew = Crew(agents=[intel_analyst], tasks=[intel_task])
			res_intel = intel_crew.kickoff()
			intel_text: str = getattr(res_intel, "raw", None) or getattr(res_intel, "output", None) or str(res_intel)
			intel_json_for_debug = None
			try:
				start_i = intel_text.find("{")
				end_i = intel_text.rfind("}")
				intel_json_for_debug = intel_text[start_i:end_i + 1] if start_i != -1 and end_i != -1 else "{}"
			except Exception:
				intel_json_for_debug = "{}"

			# Business model summary
			model_crew = Crew(agents=[business_model_analyst], tasks=[model_task])
			res_model = model_crew.kickoff()
			model_text: str = getattr(res_model, "raw", None) or getattr(res_model, "output", None) or str(res_model)
			model_json: dict | None = None
			try:
				start_m = model_text.find("{"); end_m = model_text.rfind("}")
				model_json = json.loads(model_text[start_m:end_m+1]) if start_m != -1 and end_m != -1 else None
			except Exception:
				model_json = None

			# Deterministic airline vs agency disambiguator from intel JSON
			rule_hint = ""
			candidate_codes: List[str] = []
			try:
				intel_obj = json.loads(intel_json_for_debug or "{}")
				is_airline = bool(intel_obj.get("is_first_party_airline"))
				is_agency = bool(intel_obj.get("is_travel_agency"))
				# If business model summary exists, prefer its MoR/channel cues
				try:
					if model_json:
						mor = (model_json.get("merchant_of_record") or "").lower()
						channels = [str(c).lower() for c in (model_json.get("channels") or [])]
						if mor == "first_party":
							is_airline = is_airline or ("airline" in (model_json.get("primary_offering") or "").lower())
						if "marketplace" in channels:
							is_agency = True
				except Exception:
					pass
				key_pages = intel_obj.get("key_pages") or []
				evidence = intel_obj.get("evidence") or []
				text_blobs = " ".join([str((e or {}).get("quote") or "") for e in evidence])
				urls = " ".join([str((kp or {}).get("url") or "") for kp in key_pages])
				airline_cues = 0
				agency_cues = 0
				for token in ["/book", "/check-in", "/checkin", "/manage", "/manage-booking", "/flight-status", "/baggage", "contract-of-carriage"]:
					if token in urls.lower():
						airline_cues += 1
				for token in ["over ", " airlines", "multi-airline", "ota", "travel agency", "compare airlines", "iata"]:
					if token in text_blobs.lower():
						agency_cues += 1
				if is_airline:
					airline_cues += 2
				if is_agency:
					agency_cues += 2
				# Brand override (e.g., united.com -> 3000)
				brand_key = None
				try:
					if website_url:
						pu = urlparse(website_url)
						host = pu.netloc.lower()
						labels = [lbl for lbl in host.split(".") if lbl and lbl != "www"]
						if labels:
							brand_key = labels[0]
				except Exception:
					brand_key = None
				brand_code = get_brand_override(brand_key, host)
				# Build candidate list
				cset = []
				if brand_code:
					cset.append(brand_code)
				# Airline/agency candidates
				if airline_cues >= agency_cues:
					if "4511" not in cset:
						cset.append("4511")
					if "4722" not in cset:
						cset.append("4722")
				else:
					if "4722" not in cset:
						cset.append("4722")
					if "4511" not in cset:
						cset.append("4511")
				# Compute general signals and include in provenance later
				signals = compute_signals(intel_obj)
				# Infer brand from registry
				brand_reg = load_brand_registry()
				brand_infer = infer_brand(intel_obj, brand_reg, host)
				brand_key_infer = brand_infer.get("brand_key")
				brand_mcc_infer = brand_infer.get("brand_mcc")
				brand_match_score = int(brand_infer.get("match_score") or 0)
				# RAG retrieval: build a query from intel fields
				try:
					q_parts = []
					for key in ("core_offering", "primary_revenue_stream", "sales_model", "transaction_flow", "verticals"):
						val = intel_obj.get(key)
						if isinstance(val, list):
							q_parts.extend([str(v) for v in val])
						elif val:
							q_parts.append(str(val))
					retrieval_query = "; ".join(q_parts) or (merchant_description or "")
					ensure_mcc_embeddings_built()
					rag_hits = retrieve_mcc_candidates(retrieval_query, top_k=7)
					for code, _ in rag_hits:
						if code not in cset:
							cset.append(code)
				except Exception:
					pass
				# If brand registry inference confident and first-party airline, boost it as a top candidate (no short-circuit)
				if brand_mcc_infer and is_airline and brand_match_score >= 85:
					if brand_code not in cset:
						cset.insert(0, brand_mcc_infer)
					# Add a rule hint but let the decision agent choose among candidates
					rule_hint += (f"\nBrand candidate suggested: {brand_mcc_infer} for inferred brand '{brand_key_infer}' (score={brand_match_score}). When is_first_party_airline=true, prefer the brand-specific MCC over generic airline unless evidence shows otherwise.")

				candidate_codes = cset
				# Attach signals in debug output
				parsed_signals_json = json.dumps(signals)
				candidate = None
				why_not = None
				if airline_cues >= 2 and agency_cues == 0:
					candidate = "4511"
					why_not = "4722"
				elif agency_cues >= 2 and airline_cues == 0:
					candidate = "4722"
					why_not = "4511"
				elif airline_cues > agency_cues:
					candidate = "4511"
					why_not = "4722"
				elif agency_cues > airline_cues:
					candidate = "4722"
					why_not = "4511"
				if candidate:
					rule_hint = (
						f"Preliminary MCC by deterministic signals: {candidate}. "
						f"Airline_cues={airline_cues}, agency_cues={agency_cues}. "
						f"If you disagree, cite evidence and explain why not {candidate}. Also explain why not {why_not}."
					)
			except Exception:
				pass

			# Step 1: Candidate selection (ranked shortlist)
			candidates_blob = "\n".join([f"- {code}: {get_mcc_description(code) or ''}" for code in (candidate_codes or [])]) if candidate_codes else ""
			# If candidate set is too small (<3) or caller opts for full catalog mode via env, expand to full catalog for selector
			full_catalog = (len(candidate_codes or []) < 3) or (os.getenv("MCC_FULL_CATALOG_MODE", "false").lower() in ("1","true","yes"))
			if full_catalog:
				all_codes = list_all_mcc_codes()
				candidate_codes = [c for c, _ in all_codes]
				candidates_blob = "\n".join([f"- {c}: {d}" for c, d in all_codes])

			bypass_selector = (os.getenv("MCC_BYPASS_SELECTOR", "false").lower() in ("1","true","yes"))
			shortlist: List[str] = []
			if bypass_selector:
				shortlist = candidate_codes or []
			else:
				selector_prompt = (
					"You are the Candidate Selector. Score and shortlist MCC candidates.\n"
					"Rules: Only use the provided candidate codes. Return STRICT JSON with keys: candidates (array of {code, score, why, evidence}), top_two (array of two codes).\n\n"
					"Context:\n"
					f"Web Intelligence JSON: {(intel_json_for_debug or '{}')}\n"
					f"Signals: {json.dumps(signals)}\n"
					f"Rule hints: {rule_hint}\n"
					f"Merchant domain brand_key: {brand_key or ''}; brand_candidate: {brand_code or ''}\n"
					f"Candidates (code: description):\n{candidates_blob}\n"
				)
				selector_task = Task(
					description=selector_prompt,
					expected_output=(
						"Strict JSON with keys: candidates (array of {code, score, why, evidence}), top_two (array of two codes)."
					),
					agent=selector,
				)
				selector_crew = Crew(agents=[selector], tasks=[selector_task])
				res_sel = selector_crew.kickoff()
				text_sel: str = getattr(res_sel, "raw", None) or getattr(res_sel, "output", None) or str(res_sel)
				# Parse selector output
				try:
					sel_obj = json.loads(text_sel[text_sel.find("{"):text_sel.rfind("}")+1])
					cand_list = sel_obj.get("candidates") or []
					# sort by score desc, keep top 10, and stay within candidate_codes
					cand_list_sorted = sorted(
						[c for c in cand_list if str(c.get("code") or "") in (candidate_codes or [])],
						key=lambda c: int(c.get("score") or 0), reverse=True)
					shortlist = [str(c.get("code")) for c in cand_list_sorted[:10]]
				except Exception:
					# fallback to original candidate_codes if parsing fails
					shortlist = candidate_codes or []

			# Step 2: Decision agent chooses exactly one from shortlist
			decision_prompt = (
				"You are the MCC Decision Analyst. Choose exactly one MCC from the shortlist.\n"
				"Return STRICT JSON: { merchant_name, recommended_mcc (4-digit), confidence (0-100), justification }.\n"
				"Constraints: You MUST choose from the shortlist ONLY. If the shortlist contains a brand-specific MCC matching the merchant's brand/domain and is_first_party_airline=true, prefer the brand-specific MCC over generic airline (e.g., 3000 United Airlines over 4511), unless specific evidence shows it is not the brand. Justify why chosen and why not the runner-up, citing URLs.\n\n"
				f"Shortlist: {shortlist}\n"
				f"Web Intelligence JSON: {(intel_json_for_debug or '{}')}\n"
				f"Signals: {json.dumps(signals)}\n"
				f"Rule hints: {rule_hint}\n"
				f"Merchant domain brand_key: {brand_key or ''}; brand_candidate: {brand_code or ''}\n"
				f"Candidates (code: description):\n{candidates_blob}\n"
			)
			decision_task = Task(
				description=decision_prompt,
				expected_output=(
					"Strict JSON with keys: merchant_name (string), recommended_mcc (4-digit string), confidence (0-100 integer), justification (string)."
				),
				agent=decision,
			)
			decision_crew = Crew(agents=[decision], tasks=[decision_task])
			res_dec = decision_crew.kickoff()
			text_dec: str = getattr(res_dec, "raw", None) or getattr(res_dec, "output", None) or str(res_dec)
			parsed = normalize_and_validate(text_dec)
			# Build top_k from shortlist with simple scores (if selector bypassed, approximate)
			top_k = []
			try:
				for code in shortlist[:3]:
					item = {"mcc": code, "confidence": 60}
					if code == parsed.get("recommended_mcc"):
						item["confidence"] = parsed.get("confidence") or 85
					top_k.append(item)
			except Exception:
				pass
			# Enforce shortlist membership if provided
			if shortlist and parsed.get("recommended_mcc") not in shortlist:
				raise RuntimeError("Decision selected MCC outside shortlist")
			# Post-rule guardrail: if first-party airline and high-confidence brand match exists, prefer brand MCC
			try:
				if is_airline and brand_mcc_infer and brand_match_score >= 85:
					parsed["recommended_mcc"] = brand_mcc_infer
					parsed["justification"] = (parsed.get("justification") or "") + f"\n[Preferred brand-specific MCC: {brand_mcc_infer} (brand_match_score={brand_match_score})]"
			except Exception:
				pass

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

			combined_hash = hashlib.sha256((intel_prompt + "\n---\n" + prompt + "\n---\n" + review_prompt).encode("utf-8")).hexdigest()
			_cb_record_success()
			parsed["model"] = "crewai"
			parsed["prompt_hash"] = combined_hash
			parsed["_debug_prompt"] = prompt
			parsed["_agents"] = ["Web Intelligence Analyst", "Business Model Analyst"] + ([] if bypass_selector else ["Candidate Selector"]) + ["MCC Decision Analyst", "MCC Review Analyst"]
			try:
				if 'parsed_signals_json' in locals():
					parsed["_signals"] = json.loads(parsed_signals_json)
			except Exception:
				pass
			if intel_json_for_debug:
				try:
					parsed["_web_intel_json"] = json.loads(intel_json_for_debug)
				except Exception:
					parsed["_web_intel_json"] = None
			# Enrich top_k with IC/decline benchmarks when available (portfolio and ic_optimization)
			try:
				for item in (top_k or []):
					mcc_code = item.get("mcc")
					row = get_portfolio_row(mcc_code)
					if row:
						item["weighted_avg_ic_rate"] = row.get("weighted_avg_ic_rate")
						item["decline_rate_pct"] = row.get("decline_rate_pct")
						item["cohort_ref"] = f"portfolio:mcc:{mcc_code}"
						item["cohort_source"] = "mcc_portfolio"
					else:
						opt = get_ic_optimization_metrics(mcc_code)
						if opt:
							item["weighted_avg_ic_rate"] = opt.get("avg_ic_rate")
							item["decline_rate_pct"] = opt.get("decline_rate_pct")
							item["cohort_ref"] = f"ic_opt:mcc:{mcc_code}"
							item["cohort_source"] = "ic_optimization"
			except Exception:
				pass

			# Ensure final choice is included in shortlist/top_k (rank 1)
			try:
				final_code = str(parsed.get("recommended_mcc") or "")
				if final_code and final_code not in (shortlist or []):
					shortlist = [final_code] + (shortlist or [])
				if final_code and (top_k is not None):
					present = any(str(i.get("mcc")) == final_code for i in top_k)
					if not present:
						top_k = [{"mcc": final_code, "confidence": parsed.get("confidence") or 85}] + top_k
			except Exception:
				pass

			# Compute deltas vs current_mcc using portfolio, and enrich with ic_optimization metrics (optionally banded by merchant KPIs)
			try:
				current_mcc_val = prof.get("current_mcc") if isinstance(prof, dict) else None
				# baseline from portfolio
				base = get_portfolio_row(str(current_mcc_val)) if current_mcc_val else None
				base_ic = (base or {}).get("weighted_avg_ic_rate")
				base_decl = (base or {}).get("decline_rate_pct")
				# merchant KPI bands
				merchant_kpis = get_merchant_kpis_aggregates(merchant_id)
				bands = compute_bands((merchant_kpis or {}).get("avg_volume_usd"), (merchant_kpis or {}).get("avg_ticket_usd")) if merchant_kpis else {"volume_band": None, "ticket_band": None}
				for item in (top_k or []):
					# portfolio metrics already present in item
					cand_ic = item.get("weighted_avg_ic_rate")
					cand_decl = item.get("decline_rate_pct")
					# add ic_optimization observed metrics (global)
					try:
						obs = get_ic_optimization_metrics(item.get("mcc"))
						if obs:
							item["obs_avg_ic_rate"] = obs.get("avg_ic_rate")
							item["obs_decline_rate_pct"] = obs.get("decline_rate_pct")
					except Exception:
						pass
					# banded metrics when bands available
					try:
						if bands.get("volume_band") or bands.get("ticket_band"):
							bobs = get_ic_optimization_metrics_band(item.get("mcc"), bands.get("volume_band"), bands.get("ticket_band"))
							if bobs:
								item["band_avg_ic_rate"] = bobs.get("avg_ic_rate")
								item["band_decline_rate_pct"] = bobs.get("decline_rate_pct")
					except Exception:
						pass
					# compute deltas vs base
					if base_ic is not None and cand_ic is not None:
						item["ic_bps_delta"] = (float(cand_ic) - float(base_ic)) * 10000.0
					if base_decl is not None and cand_decl is not None:
						item["decline_pp_delta"] = float(cand_decl) - float(base_decl)
			except Exception:
				pass

			# Build MCP proposal ranked list
			mcp_ranked = []
			try:
				for item in (top_k or []):
					m = {
						"mcc": item.get("mcc"),
						"description": get_mcc_description(item.get("mcc") or ""),
						"rationale": "Preferred due to evidence and signals; see justification.",
						"confidence": int(item.get("confidence") or 0),
						"benchmark": {
							"cohort_ref": item.get("cohort_ref"),
							"cohort_source": item.get("cohort_source"),
							"average_ic_rate": item.get("weighted_avg_ic_rate"),
							"average_decline_rate_pct": item.get("decline_rate_pct"),
							"example_merchant_name": None,
							"example_merchant_url": None,
						},
					}
					# if portfolio row included examples, add them
					try:
						row = get_portfolio_row(item.get("mcc"))
						if row:
							m["benchmark"]["example_merchant_name"] = row.get("example_merchant_name")
							m["benchmark"]["example_merchant_url"] = row.get("example_merchant_url")
					except Exception:
						pass
					# attach optimization deltas when present
					if "ic_bps_delta" in item:
						m["ic_bps_delta"] = item["ic_bps_delta"]
					if "decline_pp_delta" in item:
						m["decline_pp_delta"] = item["decline_pp_delta"]
					mcp_ranked.append(m)
				# sort by confidence desc, then by lower IC delta and lower decline delta
				mcp_ranked.sort(key=lambda x: (
					-(int(x.get("confidence") or 0)),
					abs(float(x.get("ic_bps_delta", 0.0))),
					abs(float(x.get("decline_pp_delta", 0.0))),
				))
				# refine rationale for chosen MCC to reflect decision justification
				for m in mcp_ranked:
					if str(m.get("mcc")) == str(parsed.get("recommended_mcc")):
						m["rationale"] = parsed.get("justification") or m.get("rationale")
			except Exception:
				pass

			# no longer expose top_k; mcc_proposal carries ranked entries
			# Add benchmark source tag
			try:
				parsed["_benchmark_source"] = {"source": "mcc_portfolio"}
			except Exception:
				pass
			# Add brand inference to provenance
			try:
				parsed["_brand"] = {
					"brand_key": brand_key_infer,
					"brand_mcc": brand_mcc_infer,
					"brand_match_score": brand_match_score,
				}
			except Exception:
				pass
			# Try to surface underlying LLM model if available on agents (best-effort)
			try:
				llm_model = getattr(getattr(classifier, "llm", None), "model_name", None) or getattr(getattr(reviewer, "llm", None), "model_name", None)
				if not llm_model:
					llm_model = os.getenv("OPENAI_MODEL")
				if llm_model:
					parsed["llm_model"] = llm_model
			except Exception:
				pass
			# expose MCP proposal
			try:
				parsed["_mcp_proposal"] = {"ranked": mcp_ranked}
			except Exception:
				pass
			# expose business model summary
			try:
				parsed["_business_model"] = model_json
			except Exception:
				pass
			return parsed
		except Exception as e:
			last_err = e
			time.sleep(0.6 * (2 ** attempt))

	_cb_record_failure()
	raise RuntimeError(f"CrewAI orchestration failed: {last_err}")


