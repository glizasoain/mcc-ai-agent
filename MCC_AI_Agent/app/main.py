from fastapi import FastAPI, Header, HTTPException
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

from app.schemas import (
	RecommendRequest, RecommendResponse, Provenance,
	SubmitMerchantRequest, SubmitMerchantResponse,
	GetRecommendationRequest, GetRecommendationResponse,
	SimulateImpactRequest, SimulateImpactResponse,
	ListRunsResponse, GetRunResponse,
	IngestProfileRequest, IngestProfileResponse,
)
from app.db import (
	init_database, get_mcc_description,
	create_run, complete_run, insert_recommendation,
	get_idempotent_response, save_idempotent_response,
	upsert_merchant, list_runs_db, get_run_db, get_latest_recommendation_for_merchant, insert_artifact, get_merchant,
)
from app.llm import call_llm_for_mcc
from app.crew_orchestrator import run_mcc_recommendation
from app.impact import simulate_impact as simulate_impact_calc
from app.impact import fetch_and_summarize
from app.web import crawl_and_summarize

# Load .env if present
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

app = FastAPI(title="MCC AI Agent", version="0.1.0")

# Initialize DB at startup
@app.on_event("startup")
def _startup():
	init_database()

# Simple in-memory idempotency cache for Phase 2
_IDEMP: dict[str, dict] = {}


@app.get("/health")
def health():
	return {"ok": True}


@app.post("/api/v1/mcc/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
	# Check DB idempotency first
	if idempotency_key:
		cached = get_idempotent_response(idempotency_key)
		if cached:
			return cached

	# Simple domain-based heuristic for Phase 2 demo; LLM comes in later phases
	merchant_name = req.merchant_id
	rec_mcc = req.current_mcc or ""
	confidence = 50
	business_analysis = "Pending analysis"
	rec_justification = ""
	supporting = ""
	needs_review = True

	def to_url(val: Optional[object]) -> Optional[str]:
		if not val:
			return None
		s = str(val).strip()
		if not s.startswith("http://") and not s.startswith("https://"):
			s = "https://" + s
		return s

	website_url = ""
	all_websites = []
	if req.websites:
		for w in req.websites:
			u = to_url(w)
			if u:
				all_websites.append(u)
	website_url = (all_websites[0] if all_websites else "")

	# Phase 6: if no websites provided, try a simple guess using merchant_id/DB record
	if not all_websites:
		mer = get_merchant(req.merchant_id)
		candidates = []
		name = (mer.get("legal_name") if mer else None) or req.merchant_id
		domain_key = name.lower().strip().replace(" ", "")
		for tld in (".com", ".net", ".io", ".co"):
			candidates.append(f"https://{domain_key}{tld}")
		# Persist guesses as artifacts
		for url in candidates:
			try:
				insert_artifact(req.merchant_id, kind="website_guess", content=url, metadata={"source": "phase6-guess"})
			except Exception:
				pass
		all_websites.extend(candidates)
		website_url = all_websites[0] if all_websites else website_url
	domain = website_url.lower()
	model_name = None

	# Phase 3: Use CrewAI orchestration only (no heuristics/fallback)
	# Build a simple profile dict from request
	prof = {}
	if req.profile:
		prof = {
			"industry": req.profile.industry,
			"vertical": req.profile.vertical,
			"country": req.profile.country,
			"avg_ticket": req.profile.avg_ticket,
			"volume_band": req.profile.volume_band,
		}
	try:
		# Prefer list if provided; also pass primary website
		primary = all_websites[0] if all_websites else website_url
		# Include business registration name from DB if present
		mer_info = (get_merchant(req.merchant_id) or {})
		biz_name = req.legal_name or mer_info.get("legal_name")
		# Fetch website summary: try focused crawl first, then single-page fallback
		website_summary = ""
		if primary:
			try:
				overall, pages = crawl_and_summarize(primary, depth=3, max_pages=50, total_budget_seconds=8.0)
				website_summary = overall or ""
				if not website_summary:
					ws = fetch_and_summarize(primary)
					website_summary = ws.get("summary") or ""
			except Exception:
				website_summary = ""
		# Add website_summary into profile context for prompt
		prof_with_summary = dict(prof)
		prof_with_summary["website_summary"] = website_summary
		if req.current_mcc:
			prof_with_summary["current_mcc"] = req.current_mcc
		# Prepare web pages payload for Web Intelligence agent (if available)
		pages_payload = []
		try:
			pages_payload = ([{"url": getattr(p, "url", ""), "title": getattr(p, "title", ""), "text": getattr(p, "text", "")} for p in (pages or [])])
		except Exception:
			pages_payload = []
		crew = run_mcc_recommendation(req.merchant_id, primary, prof_with_summary, req.merchant_description, all_websites, biz_name, pages_payload)
		merchant_name = crew.get("merchant_name") or merchant_name
		rec_mcc = crew.get("recommended_mcc") or rec_mcc
		confidence = int(crew.get("confidence") or confidence)
		rec_justification = crew.get("justification") or rec_justification
		supporting = website_url
		needs_review = confidence < 80
		model_name = crew.get("model") or "crewai"
		prompt_hash_val = crew.get("prompt_hash")
		llm_model_name = crew.get("llm_model")
		web_intel_obj = crew.get("_web_intel_json")
		# If deterministic path was taken and website_summary is empty, synthesize from web_intel if present
		if (not website_summary) and web_intel_obj:
			try:
				parts = []
				co = (web_intel_obj.get("core_offering") or "").strip()
				sm = (web_intel_obj.get("sales_model") or "").strip()
				tc = (web_intel_obj.get("target_customers") or "").strip()
				if co:
					parts.append(co)
				if sm:
					parts.append(sm)
				if tc:
					parts.append(f"for {tc}")
				candidate = "; ".join(parts).strip()
				if candidate:
					website_summary = candidate[:400]
			except Exception:
				pass
		# If website_summary is empty or looks like a gate, synthesize a concise summary from web_intel or page titles
		if not website_summary or "continue shopping" in (website_summary or "").lower():
			try:
				if web_intel_obj:
					parts = []
					co = (web_intel_obj.get("core_offering") or "").strip()
					sm = (web_intel_obj.get("sales_model") or "").strip()
					tc = (web_intel_obj.get("target_customers") or "").strip()
					if co:
						parts.append(co)
					if sm:
						parts.append(sm)
					if tc:
						parts.append(f"for {tc}")
					candidate = "; ".join(parts).strip()
					if candidate:
						website_summary = candidate[:400]
			except Exception:
				pass
			if (not website_summary) and pages:
				try:
					website_summary = " | ".join([(getattr(p, "title", None) or getattr(p, "url", "")) for p in (pages[:3])])[:400]
				except Exception:
					pass
		# reflect any updated summary in profile used for response
		prof_with_summary["website_summary"] = website_summary or prof_with_summary.get("website_summary") or ""
	except Exception as e:
		raise HTTPException(status_code=503, detail={"error": "CREW_UNAVAILABLE", "message": str(e)})


	current_desc = get_mcc_description(req.current_mcc) if req.current_mcc else ""
	rec_desc = get_mcc_description(rec_mcc) if rec_mcc else ""

	resp = RecommendResponse(
		merchant_id=req.merchant_id,
		merchant_name=merchant_name,
		current_mcc=req.current_mcc or "",
		current_mcc_description=current_desc,
		recommended_mcc=rec_mcc,
		recommended_mcc_description=rec_desc,
		confidence=confidence,
		business_analysis=business_analysis,
		misclassification_reason="",
		recommendation_justification=rec_justification,
		supporting_evidence=supporting,
		needs_review=needs_review,
		website_summary=prof_with_summary.get("website_summary") or "",
		debug_prompt=crew.get("_debug_prompt"),
		agents_involved=crew.get("_agents") or [],
		web_intel=web_intel_obj,
		provenance=Provenance(model=locals().get("model_name"), prompt_hash=locals().get("prompt_hash_val"), mcc_reference_version="catalog:mcc_codes_full.csv", llm_model=locals().get("llm_model_name")),
	)
	data = resp.model_dump()

	# Persist run + top recommendation
	try:
		run_id = create_run(req.merchant_id)
		insert_recommendation(
			run_id=run_id,
			rank=1,
			mcc=data.get("recommended_mcc"),
			confidence_pct=int(data.get("confidence") or 0),
			reasons={
				"justification": data.get("recommendation_justification"),
				"supporting": data.get("supporting_evidence"),
			},
		)
		complete_run(run_id, status="completed")
	except Exception:
		# Do not fail the request on persistence issues in Phase 2
		pass

	# Save idempotent response in DB
	if idempotency_key:
		try:
			save_idempotent_response(idempotency_key, req.model_dump(), data)
		except Exception:
			pass

	return resp


# --- Additional Phase 2 stub endpoints ---

@app.post("/api/v1/submit_merchant", response_model=SubmitMerchantResponse)
def submit_merchant(req: SubmitMerchantRequest):
	try:
		first_site = None
		if req.websites:
			first_site = req.websites[0]
		upsert_merchant(req.merchant_id, req.legal_name or req.merchant_name, first_site, req.dba_name)
		return {"submitted": True, "merchant_id": req.merchant_id}
	except Exception:
		return {"submitted": False, "merchant_id": req.merchant_id}


@app.post("/api/v1/get_recommendation", response_model=GetRecommendationResponse)
def get_recommendation(req: GetRecommendationRequest):
	latest = get_latest_recommendation_for_merchant(req.merchant_id)
	if not latest:
		return {"merchant_id": req.merchant_id, "recommendation": None}
	# Map DB record back to API shape (partial)
	return {
		"merchant_id": req.merchant_id,
		"recommendation": {
			"merchant_id": req.merchant_id,
			"merchant_name": req.merchant_id,
			"current_mcc": "",
			"current_mcc_description": "",
			"recommended_mcc": latest.get("mcc") or "",
			"recommended_mcc_description": get_mcc_description(latest.get("mcc") or ""),
			"confidence": int(latest.get("confidence") or 0),
			"business_analysis": "",
			"misclassification_reason": "",
			"recommendation_justification": (latest.get("reasons") or {}).get("justification", ""),
			"supporting_evidence": (latest.get("reasons") or {}).get("supporting", ""),
			"needs_review": (int(latest.get("confidence") or 0) < 80),
			"provenance": {"model": None, "prompt_hash": None, "mcc_reference_version": "catalog:mcc_codes_full.csv"},
		},
	}


@app.post("/api/v1/simulate_impact", response_model=SimulateImpactResponse)
def simulate_impact(req: SimulateImpactRequest):
	data = simulate_impact_calc(req.mcc_from, req.mcc_to, req.cohort_size or 1000)
	return {"cohort_size": int(data.get("cohort_size") or 0), "summary": data.get("summary") or "no_data"}


@app.get("/api/v1/list_runs", response_model=ListRunsResponse)
def list_runs():
	return {"runs": list_runs_db(limit=50)}


@app.get("/api/v1/get_run/{run_id}", response_model=GetRunResponse)
def get_run(run_id: str):
	data = get_run_db(run_id)
	return {"run": data or {"id": run_id, "status": "not_found"}}


@app.post("/api/v1/ingest_profile", response_model=IngestProfileResponse)
def ingest_profile(req: IngestProfileRequest):
	# Phase 6 placeholder for web artifacts ingestion; accept and store raw content if provided later
	return {"merchant_id": req.merchant_id, "ingested": True}