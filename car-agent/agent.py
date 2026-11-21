#!/usr/bin/env python3
"""Car search agent: scans Yad2 used-car listings, filters and ranks them,
and sends an alert (Telegram and/or email) with links to new matches.

Run:  python car-agent/agent.py            (normal run)
      python car-agent/agent.py --dry-run  (print results, send nothing, don't save state)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import sys
import time
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
SEEN_PATH = HERE / "seen.json"
ITEM_URL = "https://www.yad2.co.il/vehicles/item/{token}"
CURRENT_YEAR = time.localtime().tm_year

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}

NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
BLOCK_MARKERS = ("captcha", "shieldsquare", "radware", "are you a human", "perfdrive")
PROMOTED_BUCKETS = ("platinum", "solo", "boost", "promoted", "highlight", "vip", "premium")
DEALER_BUCKETS = ("commercial", "agency", "dealer")


class BlockedError(RuntimeError):
    pass


# --------------------------------------------------------------------------- fetching
def fetch_html(url: str, session: requests.Session) -> str:
    """Fetch a page with requests; fall back to headless Chromium if blocked."""
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
        html = r.text
        if r.status_code == 200 and NEXT_DATA_RE.search(html):
            return html
    except requests.RequestException as e:
        print(f"  requests failed: {e}")
    return fetch_html_browser(url)


_browser = None


def fetch_html_browser(url: str) -> str:
    global _browser
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise BlockedError("Page blocked and Playwright is not installed")
    if _browser is None:
        import atexit
        pw = sync_playwright().start()
        _browser = pw.chromium.launch(headless=True)
        atexit.register(lambda: (_browser.close(), pw.stop()))
    page = _browser.new_page(user_agent=HEADERS["User-Agent"], locale="he-IL")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        html = page.content()
    finally:
        page.close()
    if not NEXT_DATA_RE.search(html):
        low = html.lower()
        if any(m in low for m in BLOCK_MARKERS):
            raise BlockedError(f"Yad2 bot-protection page for {url}")
        raise BlockedError(f"No __NEXT_DATA__ in page {url} ({len(html)} bytes)")
    return html


def next_data(html: str) -> dict:
    m = NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("no __NEXT_DATA__")
    return json.loads(m.group(1))


def with_page(url: str, page: int) -> str:
    p = urlparse(url)
    q = dict(parse_qsl(p.query))
    q["page"] = str(page)
    return urlunparse(p._replace(query=urlencode(q)))


# --------------------------------------------------------------------------- parsing
def flatten_text(obj) -> str:
    """All string values in a nested JSON object, joined (for keyword search)."""
    out: list[str] = []

    def walk(o):
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return " ".join(out)


def find_listings(data) -> list[tuple[dict, str]]:
    """Walk the page JSON and return (item, bucket_name) for every car listing.

    A listing is any dict with a string 'token' plus a price/km/year-ish field.
    bucket_name is the key of the list it sat in (e.g. 'private', 'commercial',
    'platinum') — used to spot dealer / promoted ads.
    """
    found: dict[str, tuple[dict, str]] = {}

    def is_listing(d: dict) -> bool:
        return isinstance(d.get("token"), str) and any(
            k in d for k in ("price", "km", "vehicleDates", "year", "manufacturer")
        )

    def walk(o, bucket: str):
        if isinstance(o, dict):
            if is_listing(o):
                found.setdefault(o["token"], (o, bucket))
                return
            for k, v in o.items():
                walk(v, k if isinstance(v, list) else bucket)
        elif isinstance(o, list):
            for v in o:
                walk(v, bucket)

    walk(data, "")
    return list(found.values())


def _text(v) -> str:
    if isinstance(v, dict):
        return str(v.get("text") or v.get("textEng") or v.get("name") or "")
    return "" if v is None else str(v)


def _int(v):
    if isinstance(v, dict):
        v = v.get("id", v.get("value", v.get("text")))
    if v is None:
        return None
    m = re.sub(r"[^\d]", "", str(v))
    return int(m) if m else None


def normalize(item: dict, bucket: str) -> dict:
    dates = item.get("vehicleDates") or {}
    year = _int(dates.get("yearOfProduction")) or _int(item.get("year"))
    car = {
        "token": item["token"],
        "url": ITEM_URL.format(token=item["token"]),
        "price": _int(item.get("price")),
        "year": year,
        "km": _int(item.get("km")),
        "hand": _int(item.get("hand")),
        "manufacturer": _text(item.get("manufacturer")),
        "model": _text(item.get("model")),
        "sub_model": _text(item.get("subModel")),
        "gear": _text(item.get("gearBox")),
        "ad_type": str(item.get("adType") or "").lower(),
        "bucket": bucket.lower(),
        "city": _text((item.get("address") or {}).get("city")),
        "text": flatten_text(item),
    }
    car["title"] = " ".join(
        x for x in (car["manufacturer"], car["model"], car["sub_model"]) if x
    ) or "רכב"
    return car


# --------------------------------------------------------------------------- filtering
def reject_reason(car: dict, cfg: dict) -> str | None:
    p = car["price"]
    if not p or p < cfg["price_min"] or p > cfg["price_max"]:
        return "price"
    if car["year"] and car["year"] < cfg["year_min"]:
        return "year"
    if car["km"] and car["km"] > cfg["km_max"]:
        return "km"
    if car["hand"] and car["hand"] > cfg["hand_max"]:
        return "hand"
    gear_text = (car["gear"] or car["text"])
    if cfg["automatic_only"]:
        if car["gear"]:
            if "אוטומט" not in car["gear"] and "רובוט" not in car["gear"]:
                return "gear"
        elif "ידני" in gear_text:
            return "gear"
    if cfg["private_seller_only"]:
        if car["ad_type"] in ("commercial", "agency", "dealer") or any(
            b in car["bucket"] for b in DEALER_BUCKETS
        ):
            return "dealer"
    if cfg["exclude_promoted_ads"] and any(b in car["bucket"] for b in PROMOTED_BUCKETS):
        return "promoted"
    for kw in cfg["exclude_ownership_keywords"]:
        if kw in car["text"]:
            return f"ownership:{kw}"
    return None


def has_service_history(car: dict, cfg: dict) -> bool:
    return any(kw in car["text"] for kw in cfg["service_history_keywords"])


def is_preferred_model(car: dict, cfg: dict) -> bool:
    t = f'{car["title"]} {car["text"][:300]}'.lower()
    return any(m.lower() in t for m in cfg["preferred_models"])


def score(car: dict, cfg: dict) -> float:
    """Higher is better. Roughly 0-100."""
    s = 0.0
    # price: cheaper is better; full 30 pts at/below price_ideal
    p = car["price"]
    if p <= cfg["price_ideal"]:
        s += 30
    else:
        s += 30 * (cfg["price_max"] - p) / max(1, cfg["price_max"] - cfg["price_ideal"])
    # year: newer is better (25 pts)
    if car["year"]:
        s += 25 * min(1, max(0, (car["year"] - cfg["year_min"]) / 8))
    # km: lower is better (25 pts)
    if car["km"]:
        s += 25 * max(0, 1 - car["km"] / cfg["km_max"])
    else:
        s += 8
    # hand: fewer previous owners
    if car["hand"]:
        s += max(0, 5 - car["hand"]) * 1.5
    if car.get("service_history"):
        s += 10
    if car.get("preferred_model"):
        s += 8
    return round(s, 1)


# --------------------------------------------------------------------------- alerts
def fmt_num(n) -> str:
    return f"{n:,}" if isinstance(n, int) else "?"


def format_alert(cars: list[dict]) -> str:
    lines = [f"🚗 נמצאו {len(cars)} רכבים חדשים שמתאימים לך:\n"]
    for i, c in enumerate(cars, 1):
        tags = []
        if c.get("service_history"):
            tags.append("✅ מוזכרים טיפולים")
        if c.get("preferred_model"):
            tags.append("👨‍👩‍👧 משפחתי/בינוני")
        lines.append(
            f"{i}. {c['title']}\n"
            f"   💰 {fmt_num(c['price'])} ₪ | 📅 {c['year'] or '?'} | "
            f"🛣️ {fmt_num(c['km'])} ק\"מ | יד {c['hand'] or '?'}\n"
            + (f"   {' · '.join(tags)}\n" if tags else "")
            + f"   ⭐ ציון {c['score']}\n"
            f"   🔗 {c['url']}\n"
        )
    lines.append("⚠️ לפני קנייה: בדיקת מוסך + בדיקת היסטוריה לפי מספר רישוי.")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"},
        timeout=30,
    )
    print(f"Telegram: {r.status_code}")
    return r.ok


def send_email(text: str) -> bool:
    user, pwd = os.getenv("GMAIL_USER"), os.getenv("GMAIL_APP_PASSWORD")
    to = os.getenv("ALERT_EMAIL_TO") or user
    if not (user and pwd):
        return False
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = "🚗 סוכן רכב: נמצאו רכבים חדשים"
    msg["From"], msg["To"] = user, to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
    print("Email sent")
    return True


def notify(text: str) -> None:
    sent = False
    for fn in (send_telegram, send_email):
        try:
            sent = fn(text) or sent
        except Exception as e:  # keep going with the other channel
            print(f"{fn.__name__} failed: {e}")
    if not sent:
        print("No notification channel configured (set Telegram or Gmail secrets).")


# --------------------------------------------------------------------------- main
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def collect(cfg: dict, session: requests.Session) -> list[dict]:
    cars: dict[str, dict] = {}
    for base in cfg["search_urls"]:
        for page in range(1, cfg["max_pages"] + 1):
            url = with_page(base, page)
            print(f"Fetching {url}")
            items = find_listings(next_data(fetch_html(url, session)))
            print(f"  {len(items)} listings")
            if not items:
                break
            for it, bucket in items:
                c = normalize(it, bucket)
                cars.setdefault(c["token"], c)
            time.sleep(2)
    return list(cars.values())


def enrich(car: dict, session: requests.Session) -> None:
    """Fetch the ad page to read its full description (service history etc.)."""
    try:
        data = next_data(fetch_html(car["url"], session))
        car["text"] += " " + flatten_text(data.get("props", data))
    except Exception as e:
        print(f"  details failed for {car['token']}: {e}")


def run(dry_run: bool) -> int:
    cfg = load_json(CONFIG_PATH, None)
    seen: dict = load_json(SEEN_PATH, {})
    session = requests.Session()

    try:
        cars = collect(cfg, session)
    except BlockedError as e:
        print(f"BLOCKED: {e}")
        return 2
    print(f"Total unique listings: {len(cars)}")

    rejects: dict[str, int] = {}
    passed = []
    for c in cars:
        why = reject_reason(c, cfg)
        if why:
            rejects[why.split(":")[0]] = rejects.get(why.split(":")[0], 0) + 1
        else:
            passed.append(c)
    print(f"Passed filters: {len(passed)}  rejected: {rejects}")

    new = [c for c in passed if c["token"] not in seen]
    # rough pre-rank, then read the full ad for the best ones
    for c in new:
        c["preferred_model"] = is_preferred_model(c, cfg)
        c["score"] = score(c, cfg)
    new.sort(key=lambda c: c["score"], reverse=True)
    for c in new[: cfg["fetch_item_details_top_n"]]:
        enrich(c, session)
        time.sleep(1.5)
    final, late_rejects = [], []
    for c in new:
        if reject_reason(c, cfg):  # description may reveal leasing / manual etc.
            late_rejects.append(c)
            continue
        c["service_history"] = has_service_history(c, cfg)
        c["preferred_model"] = is_preferred_model(c, cfg)
        c["score"] = score(c, cfg)
        final.append(c)
    final.sort(key=lambda c: c["score"], reverse=True)
    top = final[: cfg["alert_top_n"]]

    if top:
        text = format_alert(top)
        print(text)
        if not dry_run:
            notify(text)
    else:
        print("No new matching cars this run.")

    if not dry_run:
        now = time.strftime("%Y-%m-%d")
        for c in top + late_rejects:  # alerted (or ruled out) -> don't show again
            seen[c["token"]] = now
        SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    sys.exit(run(ap.parse_args().dry_run))
