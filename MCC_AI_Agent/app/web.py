from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import List, Set, Dict
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup
import re


@dataclass
class CrawledPage:
    url: str
    title: str
    text: str


KEY_URL_HINTS = (
    "/about",
    "/company",
    "/solutions",
    "/products",
    "/platform",
    "/pricing",
    "/docs",
    "/documentation",
    "/partners",
    "/press",
    "/news",
    "/case-studies",
    "/customers",
    "/blog",
    "/investors",
    "/careers",
    "/business",
    "/services",
    "/devices",
    # Airline-specific informative paths
    "/book",
    "/check-in",
    "/checkin",
    "/manage",
    "/manage-booking",
    "/flight-status",
    "/status",
    "/baggage",
    "/contract-of-carriage",
    "/terms-of-carriage",
    "/routes",
    "/destinations",
)


def _prioritize(urls: List[str]) -> List[str]:
    return sorted(
        urls,
        key=lambda u: (
            0 if any(h in u.lower() for h in KEY_URL_HINTS) else 1,
            0 if len(u) <= 120 else 1,
            len(u),
        ),
    )


_STATIC_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js", ".ico", ".webp", ".woff", ".ttf", ".eot", ".pdf")
_DISALLOWED_SUBSTR = (
    "/ap/signin",
    "/signin",
    "/login",
    "/cookie",
    "/cookies",
    "/privacy",
    "/terms",
    "/captcha",
    "/validateCaptcha",
    "/robots.txt",
)

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


def _extract_links(base_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        abs_url = urljoin(base_url, href)
        lp = urlparse(abs_url)
        # Filter obvious static/media links
        if any(lp.path.lower().endswith(ext) for ext in _STATIC_EXT):
            continue
        # Filter wordpress uploads directory
        if "/wp-content/uploads/" in lp.path.lower():
            continue
        # Filter disallowed/gate paths
        lowp = lp.path.lower()
        if any(substr in lowp for substr in _DISALLOWED_SUBSTR):
            continue
        links.append(abs_url)
    return links


def _denoise_text(text: str) -> str:
    # Drop lines that are just URLs or ISO timestamps
    lines = text.split()
    cleaned_tokens: List[str] = []
    url_re = re.compile(r"^https?://[\w\-./%]+$")
    iso_re = re.compile(r"^20\d{2}-\d{2}-\d{2}T\d{2}:")
    for tok in lines:
        if url_re.match(tok) or iso_re.match(tok):
            continue
        cleaned_tokens.append(tok)
    return " ".join(cleaned_tokens)


def _clean_text(html: str) -> (str, str):
    soup = BeautifulSoup(html, "lxml")
    # Drop boilerplate containers
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    # Remove common nav/footer/consent elements by id/class heuristics
    noisy_keywords = ("cookie", "consent", "banner", "footer", "header", "subscribe", "newsletter", "promo", "signup")
    try:
        for el in soup.find_all(True):
            cls = " ".join((el.get("class") or []))
            el_id = el.get("id") or ""
            role = el.get("role") or ""
            hay = f"{cls} {el_id} {role}".lower()
            if any(k in hay for k in noisy_keywords):
                el.decompose()
    except Exception:
        pass
    title = (soup.title.string if soup.title and soup.title.string else "").strip()
    text_raw = soup.get_text(separator=" ") or ""
    text = " ".join(text_raw.split())
    text = _denoise_text(text)
    return title, text


def _is_gate_or_thin_page(text: str) -> bool:
    if not text or len(text) < 200:
        return True
    gate_phrases = (
        "continue shopping",
        "conditions of use",
        "privacy policy",
        "sign in",
        "captcha",
        "are you a robot",
        "enable cookies",
    )
    low = text.lower()
    return any(p in low for p in gate_phrases)


def _same_site(base_netloc: str, other_netloc: str, allow_subdomains: bool = True) -> bool:
    if base_netloc == other_netloc:
        return True
    if not allow_subdomains:
        return False
    # crude eTLD+1 match: last two labels must match
    base_parts = base_netloc.split(".")
    other_parts = other_netloc.split(".")
    if len(base_parts) >= 2 and len(other_parts) >= 2:
        return ".".join(other_parts[-2:]) == ".".join(base_parts[-2:])
    return False


def _fetch_sitemap_urls(start_url: str, timeout: float) -> List[str]:
    urls: List[str] = []
    base = urlparse(start_url)
    roots = [f"{base.scheme}://{base.netloc}/sitemap.xml", f"{base.scheme}://{base.netloc}/sitemap_index.xml"]
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for sm in roots:
            try:
                r = client.get(sm)
            except Exception:
                continue
            if r.status_code < 200 or r.status_code >= 300 or not r.text:
                continue
            # naive XML parse via bs4
            try:
                soup = BeautifulSoup(r.text, "xml")
                for loc in soup.find_all("loc"):
                    u = (loc.get_text() or "").strip()
                    if not u:
                        continue
                    pu = urlparse(u)
                    if pu.netloc == base.netloc and pu.scheme in ("http", "https"):
                        urls.append(u)
            except Exception:
                continue
    return urls[:200]


def crawl_and_summarize(
    start_url: str,
    depth: int = 3,
    max_pages: int = 50,
    per_request_timeout: float = 4.0,
    total_budget_seconds: float = 8.0,
    use_sitemap: bool = True,
    allow_subdomains: bool = True,
) -> (str, List[CrawledPage]):
    """Same-domain focused crawl with a small page/time budget.

    Returns (overall_summary, pages).
    overall_summary is a naive synthesis of first N characters across prioritized pages.
    """
    try:
        parsed = urlparse(start_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return "", []
    except Exception:
        return "", []

    t_end = time.time() + max(0.5, total_budget_seconds)
    visited: Set[str] = set()
    q = deque([(start_url, 0)])
    pages: List[CrawledPage] = []

    # Seed with sitemap URLs if enabled
    if use_sitemap:
        try:
            for u in _fetch_sitemap_urls(start_url, per_request_timeout):
                q.append((u, 1))
        except Exception:
            pass

    with httpx.Client(timeout=per_request_timeout, follow_redirects=True, headers=_BROWSER_HEADERS) as client:
        while q and len(pages) < max_pages and time.time() < t_end:
            url, d = q.popleft()
            if url in visited:
                continue
            visited.add(url)

            # Same-site only (optionally allow subdomains)
            pu = urlparse(url)
            if not _same_site(parsed.netloc, pu.netloc, allow_subdomains=allow_subdomains):
                continue

            try:
                r = client.get(url)
            except Exception:
                continue
            if r.status_code < 200 or r.status_code >= 300 or not r.text:
                continue
            # Skip non-HTML content (xml/images)
            ct = (r.headers.get("content-type") or "").lower()
            if ("xml" in ct and "html" not in ct) or "image/" in ct or "application/rss" in ct or "application/json" in ct:
                continue

            title, text = _clean_text(r.text)
            if text and not _is_gate_or_thin_page(text):
                pages.append(CrawledPage(url=url, title=title, text=text))

            if d < depth and time.time() < t_end:
                links = [lnk for lnk in _extract_links(url, r.text) if urlparse(lnk).scheme in ("http", "https")]
                # Only keep same-domain
                links = [lnk for lnk in links if urlparse(lnk).netloc == parsed.netloc]
                links = _prioritize(links)
                for lnk in links:
                    if lnk not in visited:
                        q.append((lnk, d + 1))

    # Build a lightweight overall summary. Prefer pages with URL hints first.
    prioritized = sorted(
        pages,
        key=lambda p: (
            0 if any(h in p.url.lower() for h in KEY_URL_HINTS) else 1,
            -len(p.text),
            len(p.url),
        ),
    )
    chunks: List[str] = []
    budget_chars = 1200
    for p in prioritized:
        if len(" ".join(chunks)) >= budget_chars:
            break
        snippet = (p.title + " - " if p.title else "") + p.text[:400]
        chunks.append(snippet)
    overall = " \n".join(chunks)[:budget_chars]
    return overall, pages


