"""Find car-ad sites anywhere on the web, via a search engine.

Each run:
1. Runs a few web searches (rotating through config "search_queries").
2. Opens every result. A page with several car ads -> its site is remembered
   as a "discovered source" and rescanned on every future run.
   A page that is a single car ad -> that ad is a candidate.
3. Rescans the discovered sources (sites that fail 3 runs in a row are dropped).

Search engine: DuckDuckGo's HTML page (no key needed). If BRAVE_API_KEY is set,
Brave Search API is used instead (more reliable).
"""
from __future__ import annotations

import hashlib
import os
import re
from html import unescape
from urllib.parse import parse_qs, quote_plus, urlparse

import requests

import sources

DDG_URL = "https://html.duckduckgo.com/html/?q={q}&kl=il-he"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"}
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
META_DESC_RE = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:og:)?description["\'][^>]+content=["\']([^"\']*)', re.I)


def domain_of(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def parse_ddg(html: str) -> list[str]:
    """Result URLs from DuckDuckGo's HTML results page."""
    urls = []
    for href in re.findall(r'class="result__a"[^>]*href="([^"]+)"', html) + \
            re.findall(r'href="([^"]+)"[^>]*class="result__a"', html):
        href = unescape(href)
        if "uddg=" in href:
            href = parse_qs(urlparse(href).query).get("uddg", [""])[0]
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("http") and "duckduckgo.com" not in href and href not in urls:
            urls.append(href)
    return urls


def web_search(query: str, max_results: int) -> list[str]:
    key = os.getenv("BRAVE_API_KEY")
    if key:
        r = requests.get(BRAVE_URL, params={"q": query, "country": "il", "count": max_results},
                         headers={"X-Subscription-Token": key, "Accept": "application/json"},
                         timeout=30)
        r.raise_for_status()
        return [x["url"] for x in r.json().get("web", {}).get("results", [])][:max_results]
    r = requests.get(DDG_URL.format(q=quote_plus(query)), headers=UA, timeout=30)
    r.raise_for_status()
    return parse_ddg(r.text)[:max_results]


def single_ad(html: str, url: str) -> dict | None:
    """If the page is one car ad, describe it from <title> + meta description."""
    m = TITLE_RE.search(html)
    d = META_DESC_RE.search(html)
    text = " ".join(unescape(x.group(1)).strip() for x in (m, d) if x)
    if not text or not sources.looks_like_ad(text):
        return None
    f = sources.parse_car_text(text)
    low = text.lower()
    name = domain_of(url)
    return {
        "token": name + ":" + hashlib.sha1(url.split("?")[0].encode()).hexdigest()[:16],
        "url": url, "source": name, **f,
        "manufacturer": "", "model": "", "sub_model": "", "title": text[:70],
        "ad_type": "commercial" if any(w in text for w in sources.DEALER_WORDS) else "",
        "bucket": "promoted" if any(w in low for w in sources.PROMOTED_WORDS) else "",
        "city": "", "text": text,
    }


def discover(cfg: dict, fetch, state: dict, known_domains: set[str]) -> tuple[list[dict], dict]:
    """Web search + rescan of remembered sites. Returns (cars, status)."""
    dcfg = cfg.get("discovery", {})
    if not dcfg.get("enabled", True):
        return [], {}
    blocked = set(dcfg.get("blocked_domains", []))
    found: dict = state.setdefault("__discovered", {})
    cars: list[dict] = []
    status: dict[str, str] = {}

    # 1) web search, rotating through queries so each run asks different things
    queries = dcfg.get("search_queries", [])
    n = dcfg.get("queries_per_run", 3)
    start = state.get("__query_idx", 0) % max(1, len(queries))
    todo = (queries[start:] + queries[:start])[:n]
    state["__query_idx"] = start + n
    result_urls: list[str] = []
    for q in todo:
        try:
            urls = web_search(q, dcfg.get("results_per_query", 10))
            print(f"  search '{q}': {len(urls)} results")
            result_urls += [u for u in urls if u not in result_urls]
        except Exception as e:
            print(f"  search '{q}' failed: {e}")
            status["חיפוש ברשת"] = f"נכשל ({type(e).__name__})"
    new_sites = 0
    for url in result_urls:
        dom = domain_of(url)
        if any(dom == b or dom.endswith("." + b) for b in blocked) or dom in known_domains:
            continue
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  {url}: {type(e).__name__}")
            continue
        page_cars = sources.cards_from_html(html, url, dom)
        if len(page_cars) >= 3:  # a listings page -> remember the site
            if dom not in found:
                new_sites += 1
                print(f"  ➕ new site: {dom} ({url})")
            found[dom] = {"url": url, "fails": 0}
            cars += page_cars
        else:
            ad = single_ad(html, url)
            if ad:
                cars.append(ad)
    if result_urls:
        status["חיפוש ברשת"] = f"{len(result_urls)} תוצאות, {new_sites} אתרים חדשים"

    # 2) rescan remembered sites
    limit = dcfg.get("max_discovered_sites_per_run", 15)
    for dom, info in list(found.items())[:limit]:
        if dom in known_domains or any(c["source"] == dom for c in cars):
            continue
        site_cars, msg = sources.scan_source({"name": dom, "url": info["url"]}, fetch, state)
        if site_cars:
            info["fails"] = 0
            cars += site_cars
        else:
            info["fails"] = info.get("fails", 0) + 1
            if info["fails"] >= 3:
                print(f"  ➖ dropping {dom} (failed 3 runs)")
                del found[dom]
    if found:
        status["אתרים שנמצאו ברשת"] = f"{len(found)}: " + ", ".join(list(found)[:12])
    return cars, status
