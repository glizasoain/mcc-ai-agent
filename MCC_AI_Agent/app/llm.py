import os
import json
from typing import Optional, Dict, Any
import time
import re

try:
	from openai import OpenAI as OpenAIClient  # SDK >=1.0
	_HAS_NEW_OPENAI_SDK = True
except Exception:
	_HAS_NEW_OPENAI_SDK = False
	import openai as OpenAILegacy  # SDK 0.x
from dotenv import load_dotenv
from pathlib import Path
import logging

# Ensure we load latest env vars (supports hot key changes without full restart)
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)


def _build_prompt(merchant_id: str, website_url: Optional[str], profile: Optional[Dict[str, Any]] = None) -> str:
	base_path = os.path.join(os.path.dirname(__file__), "prompts", "mcc_classification_v1.txt")
	try:
		with open(base_path, "r", encoding="utf-8") as f:
			prompt = f.read()
	except FileNotFoundError:
		prompt = (
			"You are an expert in Merchant Category Codes. Given a website, respond strictly "
			"with JSON: {\"merchant_name\",\"recommended_mcc\",\"confidence\",\"justification\"}."
		)
	ctx = {
		"merchant_id": merchant_id,
		"website": website_url or "",
		"profile": {
			"industry": (profile or {}).get("industry"),
			"vertical": (profile or {}).get("vertical"),
			"country": (profile or {}).get("country"),
			"existing_mcc": (profile or {}).get("existing_mcc"),
			"avg_ticket": (profile or {}).get("avg_ticket"),
			"volume_band": (profile or {}).get("volume_band"),
		},
	}
	return f"{prompt}\n\nContext:\n{json.dumps(ctx)}\n\nRespond in JSON only."


def call_llm_for_mcc(merchant_id: str, website_url: Optional[str], profile: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
	# Reload env every call to pick up changes without restart
	load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
	api_key = os.getenv("OPENAI_API_KEY")
	model = os.getenv("OPENAI_MODEL", "gpt-4o-turbo")
	if not api_key:
		return None
	# Initialize client depending on SDK flavor
	client = OpenAIClient(api_key=api_key) if _HAS_NEW_OPENAI_SDK else None
	prompt = _build_prompt(merchant_id, website_url, profile)

	def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
		def parse_conf(val) -> int:
			if isinstance(val, (int, float)):
				c = int(val)
				return max(0, min(100, c))
			if isinstance(val, str):
				lowered = val.strip().lower()
				if lowered in {"high", "strong", "very high"}:
					return 85
				if lowered in {"medium", "moderate"}:
					return 60
				if lowered in {"low", "weak", "very low"}:
					return 30
				m = re.search(r"\d+", lowered)
				if m:
					n = int(m.group())
					if 0 <= n <= 100:
						return n
					if 0 <= n <= 1:
						return int(n * 100)
			return 0

		def sanitize_mcc(val) -> str:
			s = str(val or "")
			m = re.search(r"\b(\d{4})\b", s)
			return m.group(1) if m else ""

		return {
			"merchant_name": raw.get("merchant_name"),
			"recommended_mcc": sanitize_mcc(raw.get("recommended_mcc")),
			"confidence": parse_conf(raw.get("confidence")),
			"justification": raw.get("justification") or "",
			"model": model,
		}

	# Try JSON-mode first
	try:
		if _HAS_NEW_OPENAI_SDK:
			resp = client.chat.completions.create(
				model=model,
				messages=[
					{"role": "system", "content": "You are a careful classifier that always replies with strict JSON."},
					{"role": "user", "content": prompt},
				],
				response_format={"type": "json_object"},
				temperature=0,
			)
			text = resp.choices[0].message.content or "{}"
			return normalize(json.loads(text))
		else:
			OpenAILegacy.api_key = api_key
			r = OpenAILegacy.ChatCompletion.create(
				model=model,
				messages=[
					{"role": "system", "content": "You are a careful classifier that always replies with strict JSON."},
					{"role": "user", "content": prompt},
				],
				temperature=0,
			)
			text = r["choices"][0]["message"]["content"] or "{}"
			return normalize(json.loads(text))
	except Exception:
		logging.exception("LLM JSON-mode call failed")

	# Fallback: non-JSON with lenient parsing
	try:
		if _HAS_NEW_OPENAI_SDK:
			resp = client.chat.completions.create(
				model=model,
				messages=[
					{"role": "system", "content": "You are a careful classifier that replies with JSON."},
					{"role": "user", "content": prompt},
				],
				temperature=0,
			)
			text = resp.choices[0].message.content or ""
		else:
			r = OpenAILegacy.ChatCompletion.create(
				model=model,
				messages=[
					{"role": "system", "content": "You are a careful classifier that replies with JSON."},
					{"role": "user", "content": prompt},
				],
				temperature=0,
			)
			text = r["choices"][0]["message"]["content"] or ""
		start = text.find("{")
		end = text.rfind("}")
		if start != -1 and end != -1 and end > start:
			data = json.loads(text[start:end + 1])
			return normalize(data)
	except Exception:
		logging.exception("LLM non-JSON fallback failed")

	return None


def _summarize_context_for_chat(ctx: Dict[str, Any]) -> str:
	parts = []
	intel = ctx.get("web_intel") or {}
	biz = ctx.get("business_description") or {}
	ws = ctx.get("website_summary") or ""
	mcp = ctx.get("mcc_proposal") or {}
	if intel:
		co = (intel.get("core_offering") or "").strip()
		prs = (intel.get("primary_revenue_stream") or "").strip()
		tc = (intel.get("target_customers") or "").strip()
		if co:
			parts.append(f"core_offering: {co}")
		if prs:
			parts.append(f"revenue: {prs}")
		if tc:
			parts.append(f"customers: {tc}")
	if ws and not parts:
		parts.append(f"website_summary: {ws[:300]}")
	ranked = (mcp.get("ranked") or [])
	if ranked:
		lead = ranked[0]
		parts.append(f"top_mcc: {lead.get('mcc')} — {lead.get('description')}")
		if lead.get("rationale"):
			parts.append(f"top_rationale: {lead.get('rationale')}")
	return " \n".join([p for p in parts if p])


_EMBED_CACHE: Dict[str, list[float]] = {}
_EMBED_CACHE_MAX = 512


def _cache_embed_get(key: str) -> Optional[list[float]]:
    return _EMBED_CACHE.get(key)


def _cache_embed_put(key: str, vec: list[float]) -> None:
    if key in _EMBED_CACHE:
        _EMBED_CACHE[key] = vec
        return
    if len(_EMBED_CACHE) >= _EMBED_CACHE_MAX:
        # drop an arbitrary oldest key (not strict LRU to keep it simple)
        try:
            _EMBED_CACHE.pop(next(iter(_EMBED_CACHE)))
        except Exception:
            _EMBED_CACHE.clear()
    _EMBED_CACHE[key] = vec


def call_llm_chat(context: Dict[str, Any], messages: list[dict]) -> Optional[str]:
	# Reload env to pick up latest model/key
	load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
	api_key = os.getenv("OPENAI_API_KEY")
	model = os.getenv("OPENAI_MODEL", "gpt-4o")
	if not api_key:
		return None
	client = OpenAIClient(api_key=api_key) if _HAS_NEW_OPENAI_SDK else None

	# Build a small retrieval corpus from existing context (website_summary, web_intel, business_description, compliance, mcc_proposal, justification)
	ctx = context or {}
	corpus: list[dict] = []
	ws = (ctx.get("website_summary") or "").strip()
	if ws:
		corpus.append({"title": "website_summary", "text": ws})
	intel = ctx.get("web_intel") or {}
	if isinstance(intel, dict) and intel:
		parts = []
		for k in ["core_offering", "primary_revenue_stream", "sales_model", "transaction_flow", "pricing_model", "target_customers"]:
			v = (intel.get(k) or "").strip()
			if v:
				parts.append(f"{k}: {v}")
		for ev in (intel.get("evidence") or [])[:5]:
			q = (ev.get("quote") or ev.get("url") or "").strip()
			if q:
				parts.append(f"evidence: {q}")
		if parts:
			corpus.append({"title": "web_intel", "text": " \n".join(parts)})
	biz = ctx.get("business_description")
	if isinstance(biz, dict) and biz:
		try:
			corpus.append({"title": "business_description", "text": json.dumps(biz, ensure_ascii=False)})
		except Exception:
			pass
	# Compliance findings
	comp = ctx.get("compliance_report") or {}
	for f in (comp.get("findings") or [])[:6]:
		try:
			txt = f"issue: {f.get('issue')} severity: {f.get('severity')} evidence: {(f.get('snippet') or f.get('evidence_url') or '')}"
			corpus.append({"title": "compliance", "text": txt})
		except Exception:
			pass

	mcp = ctx.get("mcc_proposal") or {}
	for i, r in enumerate((mcp.get("ranked") or [])[:5]):
		try:
			text_bits = [
				f"mcc: {r.get('mcc')}",
				f"desc: {r.get('description')}",
				f"rationale: {(r.get('rationale') or '').strip()}",
			]
			bm = r.get("benchmark") or {}
			if bm:
				text_bits.append(f"ic_avg: {bm.get('average_ic_rate')} decline_avg: {bm.get('average_decline_rate_pct')}")
				if bm.get("example_merchant_name"):
					text_bits.append(f"example: {bm.get('example_merchant_name')} {bm.get('example_merchant_url') or ''}")
			corpus.append({"title": f"ranked_{i}", "text": " ".join([b for b in text_bits if b])})
		except Exception:
			pass
	just = (ctx.get("justification") or "").strip()
	if just:
		corpus.append({"title": "justification", "text": just})

	# Lightweight RAG: embed question and corpus, select top snippets
	def _embed_texts(texts: list[str]) -> list[list[float]]:
		out: list[list[float]] = []
		if _HAS_NEW_OPENAI_SDK:
			for t in texts:
				cached = _cache_embed_get(t)
				if cached is not None:
					out.append(cached)
					continue
				resp = client.embeddings.create(model="text-embedding-3-small", input=[t])
				vec = resp.data[0].embedding
				_cache_embed_put(t, vec)
				out.append(vec)
			return out
		else:
			OpenAILegacy.api_key = api_key
			for t in texts:
				cached = _cache_embed_get(t)
				if cached is not None:
					out.append(cached)
					continue
				r = OpenAILegacy.Embedding.create(model="text-embedding-3-small", input=[t])
				vec = r["data"][0]["embedding"]
				_cache_embed_put(t, vec)
				out.append(vec)
			return out

	question = (messages[-1].get("content") if messages else "") or ""
	start_ts = time.time()
	def _deadline_exceeded() -> bool:
		# overall chat budget ~6s
		return (time.time() - start_ts) > 6.0

	try:
		qvec = _embed_texts([question])[0]
		doc_vecs = _embed_texts([c["text"] for c in corpus]) if corpus else []
		def _cos(a, b):
			import math
			dot = sum(x*y for x, y in zip(a, b))
			n1 = math.sqrt(sum(x*x for x in a)) or 1.0
			n2 = math.sqrt(sum(y*y for y in b)) or 1.0
			return dot / (n1 * n2)
		scored = [(i, _cos(qvec, v)) for i, v in enumerate(doc_vecs)]
		scored.sort(key=lambda t: t[1], reverse=True)
		top_idx = [i for i, _ in scored[:5]]
		snips = [corpus[i] for i in top_idx] if corpus else []
	except Exception:
		# If embeddings fail, fall back to summarized context
		snips = [{"title": "summary", "text": _summarize_context_for_chat(ctx)}]

	sys = (
		"You are an underwriting research assistant.\n"
		"Answer concisely using ONLY the provided snippets. If insufficient, reply 'insufficient evidence'.\n"
		"If asked 'why', explain the rationale for the top MCC and compare with runner-up if present.\n"
		"Avoid fabrication."
	)
	chat_msgs = [{"role": "system", "content": sys}]
	if snips:
		joined = "\n\n".join([f"[{s['title']}]\n{s['text']}" for s in snips])
		chat_msgs.append({"role": "assistant", "content": f"SNIPPETS:\n{joined}"})
	# append limited history
	for m in messages[-8:]:
		chat_msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})
	try:
		if _deadline_exceeded():
			return "insufficient evidence"
		if _HAS_NEW_OPENAI_SDK:
			resp = client.chat.completions.create(model=model, messages=chat_msgs)
			return (resp.choices[0].message.content or "").strip()
		else:
			OpenAILegacy.api_key = api_key
			r = OpenAILegacy.ChatCompletion.create(model=model, messages=chat_msgs)
			return (r["choices"][0]["message"]["content"] or "").strip()
	except Exception:
		logging.exception("LLM chat call failed")
		return None


