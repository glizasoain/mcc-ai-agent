import os
import json
from typing import Optional, Dict, Any
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


