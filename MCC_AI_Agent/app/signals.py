from __future__ import annotations

from typing import Dict, Any, List


def compute_signals(intel: Dict[str, Any]) -> Dict[str, Any]:
    """Compute domain-agnostic signals and family scores from web intelligence JSON.

    Returns a dict with:
    - family_scores: {family: score}
    - fired_signals: [{family, signal, url}]
    """
    family_scores: Dict[str, int] = {
        "airline": 0,
        "agency": 0,
        "marketplace": 0,
        "retail": 0,
        "saas": 0,
        "services": 0,
    }
    fired: List[Dict[str, str]] = []

    key_pages = intel.get("key_pages") or []
    urls = " ".join([str((kp or {}).get("url") or "").lower() for kp in key_pages])
    evidence = intel.get("evidence") or []
    quotes = " ".join([str((e or {}).get("quote") or "").lower() for e in evidence])

    def hit(family: str, signal: str, url: str | None = None):
        family_scores[family] = family_scores.get(family, 0) + 1
        fired.append({"family": family, "signal": signal, "url": (url or "")})

    # Airline vs Agency
    for token in ["/book", "/check-in", "/checkin", "/manage", "/manage-booking", "/flight-status", "/baggage", "contract-of-carriage"]:
        if token in urls:
            hit("airline", f"path:{token}")
    if intel.get("is_first_party_airline"):
        hit("airline", "flag:is_first_party_airline")
        # stronger weight
        hit("airline", "flag:is_first_party_airline")
    for token in ["multi-airline", "compare airlines", "ota", "travel agency", "over "]:
        if token in quotes:
            hit("agency", f"text:{token}")

    # Marketplace vs Retail
    for token in ["marketplace", "sellers", "sell on", "vendor portal", "seller center"]:
        if token in quotes:
            hit("marketplace", f"text:{token}")
    for token in ["add to cart", "buy now", "returns", "shipping"]:
        if token in quotes:
            hit("retail", f"text:{token}")

    # SaaS vs Services
    for token in ["pricing", "plan", "per month", "api", "docs", "developer"]:
        if token in quotes:
            hit("saas", f"text:{token}")
    for token in ["consulting", "professional services", "custom implementation"]:
        if token in quotes:
            hit("services", f"text:{token}")

    return {"family_scores": family_scores, "fired_signals": fired}


def infer_brand(intel: Dict[str, Any], registry: List[Dict[str, Any]], host: str | None) -> Dict[str, Any]:
    """Infer brand from web intel and registry using fuzzy signals.

    Returns: { brand_key, brand_mcc, match_score, evidence }
    """
    import difflib
    host = (host or "").lower()
    names = []
    try:
        names.extend([str((kp or {}).get("title") or "") for kp in (intel.get("key_pages") or [])])
    except Exception:
        pass
    quotes = " ".join([str((e or {}).get("quote") or "") for e in (intel.get("evidence") or [])])
    candidates = []
    for row in registry:
        key = row.get("brand_key")
        mcc = row.get("brand_mcc")
        r_names = (row.get("official_names") or []) + (row.get("aliases") or [])
        r_domains = row.get("official_domains") or []
        score = 0
        # Domain match boosts
        for d in r_domains:
            d = (d or "").lower()
            if host == d or (host.endswith("." + d) if d else False):
                score += 50
        # Name fuzzy match
        try:
            for n in names:
                ratio = max([difflib.SequenceMatcher(None, n.lower(), rn.lower()).ratio() for rn in r_names] or [0])
                if ratio > 0.8:
                    score += int(ratio * 40)
        except Exception:
            pass
        # Quote keyword hints
        for rn in r_names:
            if rn and rn.lower() in quotes.lower():
                score += 10
        if score > 0:
            candidates.append({"brand_key": key, "brand_mcc": mcc, "score": min(score, 100)})
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0] if candidates else None
    return {
        "brand_key": (best or {}).get("brand_key"),
        "brand_mcc": (best or {}).get("brand_mcc"),
        "match_score": (best or {}).get("score") or 0,
        "evidence": {
            "host": host,
            "names_considered": names[:5],
        },
    }


