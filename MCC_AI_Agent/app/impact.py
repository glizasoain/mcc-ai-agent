import csv
from pathlib import Path
from typing import Optional, Dict
import httpx
from bs4 import BeautifulSoup


_PORTFOLIO_CACHE: Dict[str, dict] = {}
_KPIS_AVG_VOLUME_USD: Optional[float] = None


def _load_portfolio_once() -> None:
	global _PORTFOLIO_CACHE
	if _PORTFOLIO_CACHE:
		return
	root = Path(__file__).resolve().parents[2] / "requirements" / "data" / "catalogs" / "mcc_ranking_portfolio.csv"
	if not root.exists():
		_PORTFOLIO_CACHE = {}
		return
	with root.open("r", encoding="utf-8") as f:
		reader = csv.DictReader(f)
		for row in reader:
			code = (row.get("mcc_code") or "").strip()
			if not code:
				continue
			try:
				weighted = float(row.get("weighted_avg_ic_rate") or 0.0)
			except Exception:
				weighted = 0.0
			_PORTFOLIO_CACHE[code] = {
				"mcc_code": code,
				"description": (row.get("mcc_description") or "").strip(),
				"weighted_avg_ic_rate": weighted,
			}


def _load_avg_kpis_volume_once() -> None:
	global _KPIS_AVG_VOLUME_USD
	if _KPIS_AVG_VOLUME_USD is not None:
		return
	root = Path(__file__).resolve().parents[2] / "requirements" / "data" / "samples" / "merchant_kpis_monthly.sample.csv"
	if not root.exists():
		_KPIS_AVG_VOLUME_USD = 0.0
		return
	count = 0
	total = 0.0
	with root.open("r", encoding="utf-8") as f:
		reader = csv.DictReader(f)
		for row in reader:
			try:
				v = float(row.get("volume_usd") or 0.0)
			except Exception:
				v = 0.0
			total += v
			count += 1
	_KPIS_AVG_VOLUME_USD = (total / count) if count else 0.0


def simulate_impact(mcc_from: str, mcc_to: str, cohort_size: int = 1000) -> dict:
	"""Compute impact using portfolio CSV and average KPIs sample.

	Returns a dict containing numeric fields and a short human-readable summary.
	If data is missing for given MCCs, marks not_found accordingly and does not fabricate values.
	"""
	_load_portfolio_once()
	_load_avg_kpis_volume_once()

	from_row = _PORTFOLIO_CACHE.get(mcc_from)
	to_row = _PORTFOLIO_CACHE.get(mcc_to)

	result = {
		"mcc_from": mcc_from,
		"mcc_to": mcc_to,
		"cohort_size": cohort_size,
		"from_weighted_ic_rate": None,
		"to_weighted_ic_rate": None,
		"ic_bps_delta": None,
		"estimated_total_volume_usd": None,
		"estimated_ic_delta_usd": None,
		"not_found": [],
	}

	if not from_row:
		result["not_found"].append(mcc_from)
	else:
		result["from_weighted_ic_rate"] = from_row.get("weighted_avg_ic_rate")

	if not to_row:
		result["not_found"].append(mcc_to)
	else:
		result["to_weighted_ic_rate"] = to_row.get("weighted_avg_ic_rate")

	if result["from_weighted_ic_rate"] is not None and result["to_weighted_ic_rate"] is not None:
		ic_delta = (result["to_weighted_ic_rate"] - result["from_weighted_ic_rate"]) * 10_000.0
		result["ic_bps_delta"] = ic_delta
		# Use observed average monthly volume per merchant from KPIs; scale by cohort size
		avg_volume = _KPIS_AVG_VOLUME_USD or 0.0
		total_vol = avg_volume * float(max(0, cohort_size))
		result["estimated_total_volume_usd"] = total_vol
		result["estimated_ic_delta_usd"] = (total_vol * ((result["to_weighted_ic_rate"] or 0.0) - (result["from_weighted_ic_rate"] or 0.0)))

	summary_bits = []
	if result["ic_bps_delta"] is not None:
		summary_bits.append(f"delta_ic_bps={result['ic_bps_delta']:.1f}")
	if result["estimated_ic_delta_usd"] is not None:
		summary_bits.append(f"delta_ic_usd={result['estimated_ic_delta_usd']:.2f}")
	if result["not_found"]:
		summary_bits.append(f"missing={','.join(result['not_found'])}")
	result["summary"] = ", ".join(summary_bits) if summary_bits else "no_data"

	return result


def fetch_and_summarize(url: str, timeout: float = 5.0) -> Dict[str, str]:
	"""Fetch a single URL and return {'content': text, 'summary': summary}.

	No fabrication: if fetch fails, fields are empty strings.
	"""
	text = ""
	summary = ""
	try:
		with httpx.Client(timeout=timeout, follow_redirects=True) as client:
			r = client.get(url)
			if r.status_code >= 200 and r.status_code < 300:
				soup = BeautifulSoup(r.text, "lxml")
				# Drop script/style
				for tag in soup(["script", "style", "noscript"]):
					tag.extract()
				text = " ".join((soup.get_text(separator=" ") or "").split())
				# Simple heuristic summary: first 400 chars
				summary = text[:400]
	except Exception:
		pass
	return {"content": text, "summary": summary}


