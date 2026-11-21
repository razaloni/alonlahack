"""Generic scanner for car-ad sites other than Yad2.

It does not need to know a site's internal structure. On a results page it
looks for links whose text looks like a car ad (a price in ₪ and a model
year), and it reads price / year / km / hand / gearbox from that text.
If the start page has no ads, it follows links whose text contains
words like "רכב יד 2" to find the used-car section.
"""
from __future__ import annotations

import hashlib
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

CURRENT_YEAR = time.localtime().tm_year

PRICE_RE = re.compile(r"(?:₪\s*([\d][\d,\.]{2,8}))|(?:([\d][\d,\.]{2,8})\s*(?:₪|ש\"ח|ש״ח|שקל))")
YEAR_RE = re.compile(r"(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)")
KM_RE = re.compile(r"([\d][\d,\.]{1,8})\s*(?:ק\"מ|ק״מ|קמ\b|קילומטר|km)", re.I)
KM_LABEL_RE = re.compile(r"(?:קילומטראז'?|ק\"מ|ק״מ)\s*[:\-]?\s*([\d][\d,\.]{1,8})")
HAND_RE = re.compile(r"יד\s*[:\-]?\s*(\d{1,2})(?!\d)")

PROMOTED_WORDS = ("מודעה ממומנת", "ממומן", "מקודם", "מודעה מקודמת", "פרסומת", "sponsored")
DEALER_WORDS = ("סוחר", "מגרש רכב", "מגרש", "יבואן", "סוכנות רכב", "trade-in", "טרייד אין")


def _num(s: str) -> int | None:
    d = re.sub(r"[^\d]", "", s or "")
    return int(d) if d else None


def parse_car_text(text: str) -> dict:
    """Pull price/year/km/hand/gear out of free Hebrew ad text."""
    price = None
    for m in PRICE_RE.finditer(text):
        n = _num(m.group(1) or m.group(2))
        if n and 1000 <= n <= 1_000_000:
            price = n
            break
    years = [int(y) for y in YEAR_RE.findall(text) if 1985 <= int(y) <= CURRENT_YEAR + 1]
    km = None
    for rx in (KM_RE, KM_LABEL_RE):
        m = rx.search(text)
        if m:
            km = _num(m.group(1))
            break
    hand = None
    m = HAND_RE.search(text)
    if m and 0 < int(m.group(1)) < 15:
        hand = int(m.group(1))
    if "אוטומט" in text or "רובוטי" in text:
        gear = "אוטומטי"
    elif "ידני" in text:
        gear = "ידני"
    else:
        gear = ""
    return {"price": price, "year": years[0] if years else None, "km": km, "hand": hand, "gear": gear}


class _LinkParser(HTMLParser):
    """Collect (href, visible text inside the <a>) pairs."""

    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._stack: list[list] = []  # [href, [text parts]]
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "a":
            self._stack.append([dict(attrs).get("href") or "", []])

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "a" and self._stack:
            href, parts = self._stack.pop()
            text = " ".join(" ".join(parts).split())
            self.links.append((href, text))
            if self._stack:  # nested <a>: give text to the parent too
                self._stack[-1][1].append(text)

    def handle_data(self, data):
        if not self._skip and self._stack:
            self._stack[-1][1].append(data)


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    p = _LinkParser()
    p.feed(html)
    out = []
    for href, text in p.links:
        if href and not href.startswith(("javascript:", "mailto:", "tel:", "#")):
            out.append((urljoin(base_url, href), text))
    return out


def looks_like_ad(text: str) -> bool:
    f = parse_car_text(text)
    return bool(f["price"] and f["year"] and len(text) < 1500)


def cards_from_html(html: str, base_url: str, source_name: str) -> list[dict]:
    domain = urlparse(base_url).netloc
    cars: dict[str, dict] = {}
    for url, text in extract_links(html, base_url):
        if urlparse(url).netloc != domain or not looks_like_ad(text):
            continue
        f = parse_car_text(text)
        low = text.lower()
        token = source_name + ":" + hashlib.sha1(url.split("?")[0].encode()).hexdigest()[:16]
        cars.setdefault(token, {
            "token": token,
            "url": url,
            "source": source_name,
            **f,
            "manufacturer": "", "model": "", "sub_model": "",
            "title": text[:70],
            "ad_type": "commercial" if any(w in text for w in DEALER_WORDS) else "",
            "bucket": "promoted" if any(w in low for w in PROMOTED_WORDS) else "",
            "city": "",
            "text": text,
        })
    return list(cars.values())


def section_links(html: str, base_url: str, nav_words: list[str]) -> list[str]:
    domain = urlparse(base_url).netloc
    seen, out = set(), []
    for url, text in extract_links(html, base_url):
        if urlparse(url).netloc == domain and any(w in text for w in nav_words) and url not in seen:
            seen.add(url)
            out.append(url)
    return out[:4]


def scan_source(src: dict, fetch, state: dict) -> tuple[list[dict], str]:
    """Scan one generic source. Returns (cars, status message).

    fetch(url) -> html.  state remembers a discovered section URL per source.
    """
    name = src["name"]
    start = state.get(f"__section:{name}") or src["url"]
    try:
        html = fetch(start)
    except Exception as e:
        return [], f"נכשל ({type(e).__name__})"
    cars = cards_from_html(html, start, name)
    if not cars:
        for link in section_links(html, start, src.get("nav_words", [])):
            try:
                sub = fetch(link)
            except Exception:
                continue
            cars = cards_from_html(sub, link, name)
            if cars:
                state[f"__section:{name}"] = link
                break
    if not cars:
        return [], "לא נמצאו מודעות (ייתכן שהאתר חוסם או שמבנה הדף לא זוהה)"
    return cars, f"{len(cars)} מודעות"
