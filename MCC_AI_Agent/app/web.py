from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import List, Set, Dict
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup


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
)


def _prioritize(urls: List[str]) -> List[str]:
    return sorted(urls, key=lambda u: (0 if any(h in u.lower() for h in KEY_URL_HINTS) else 1, len(u)))


def _extract_links(base_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        abs_url = urljoin(base_url, href)
        links.append(abs_url)
    return links


def _clean_text(html: str) -> (str, str):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    title = (soup.title.string if soup.title and soup.title.string else "").strip()
    text = " ".join((soup.get_text(separator=" ") or "").split())
    return title, text


def crawl_and_summarize(
    start_url: str,
    depth: int = 2,
    max_pages: int = 25,
    per_request_timeout: float = 4.0,
    total_budget_seconds: float = 6.0,
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

    with httpx.Client(timeout=per_request_timeout, follow_redirects=True) as client:
        while q and len(pages) < max_pages and time.time() < t_end:
            url, d = q.popleft()
            if url in visited:
                continue
            visited.add(url)

            # Same-domain only
            pu = urlparse(url)
            if pu.netloc != parsed.netloc:
                continue

            try:
                r = client.get(url)
            except Exception:
                continue
            if r.status_code < 200 or r.status_code >= 300 or not r.text:
                continue

            title, text = _clean_text(r.text)
            if text:
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
        key=lambda p: (0 if any(h in p.url.lower() for h in KEY_URL_HINTS) else 1, len(p.url)),
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


