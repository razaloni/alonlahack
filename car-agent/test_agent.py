"""Offline tests with a synthetic Yad2-like page.  Run: python -m unittest car-agent/test_agent.py"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent  # noqa: E402

CFG = json.loads((Path(__file__).resolve().parent / "config.json").read_text(encoding="utf-8"))


def item(token, price, year, km, gear="אוטומטי", hand=2, model="קורולה", **kw):
    d = {
        "token": token, "price": price, "km": km,
        "vehicleDates": {"yearOfProduction": year},
        "hand": {"id": hand, "text": f"יד {hand}"},
        "gearBox": {"id": 102, "text": gear},
        "manufacturer": {"text": "טויוטה"}, "model": {"text": model},
        "adType": kw.pop("adType", "private"),
    }
    d.update(kw)
    return d


PAGE = {
    "props": {"pageProps": {"dehydratedState": {"queries": [{"state": {"data": {
        "private": [
            item("good1", 14500, 2014, 120000, description="כל הטיפולים במוסך מורשה"),
            item("good2", 19000, 2012, 180000, model="i30"),
            item("manual", 13000, 2013, 100000, gear="ידני"),
            item("pricey", 25000, 2015, 90000),
            item("old", 12000, 2005, 150000),
            item("lease", 15000, 2014, 110000, description="רכב ליסינג לשעבר"),
        ],
        "commercial": [item("dealer", 15000, 2015, 90000, adType="commercial")],
        "platinum": [item("promo", 15000, 2015, 90000)],
    }}}]}}}
}
HTML = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(PAGE)}</script></html>'


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.cars = [agent.normalize(i, b) for i, b in agent.find_listings(agent.next_data(HTML))]

    def test_finds_all_listings(self):
        self.assertEqual(len(self.cars), 8)

    def test_filters(self):
        reasons = {c["token"]: agent.reject_reason(c, CFG) for c in self.cars}
        self.assertIsNone(reasons["good1"])
        self.assertIsNone(reasons["good2"])
        self.assertEqual(reasons["manual"], "gear")
        self.assertEqual(reasons["pricey"], "price")
        self.assertEqual(reasons["old"], "year")
        self.assertTrue(reasons["lease"].startswith("ownership"))
        self.assertEqual(reasons["dealer"], "dealer")
        self.assertEqual(reasons["promo"], "promoted")

    def test_ranking_prefers_cheaper_newer_with_history(self):
        by = {c["token"]: c for c in self.cars}
        for c in (by["good1"], by["good2"]):
            c["service_history"] = agent.has_service_history(c, CFG)
            c["preferred_model"] = agent.is_preferred_model(c, CFG)
        self.assertTrue(by["good1"]["service_history"])
        self.assertGreater(agent.score(by["good1"], CFG), agent.score(by["good2"], CFG))

    def test_alert_has_link(self):
        c = self.cars[0]
        c["score"] = 50
        self.assertIn("https://www.yad2.co.il/vehicles/item/good1", agent.format_alert([c]))

    def test_with_page(self):
        self.assertEqual(
            agent.with_page("https://x.co/a?price=1-2", 3), "https://x.co/a?price=1-2&page=3"
        )


import sources  # noqa: E402

GENERIC_HTML = """<html><body>
<a href="/nav/cars">רכב יד 2</a>
<a href="/ad/111"><div>טויוטה קורולה 2013</div><span>אוטומט</span> <span>140,000 ק"מ</span> יד 2 <b>₪ 16,500</b></a>
<a href="/ad/222">מאזדה 3 2011 ידני 120,000 ק"מ 13,000 ₪</a>
<a href="/ad/333">יונדאי i30 2012 אוטומטי 150,000 ק"מ 17,000 ₪ מודעה ממומנת</a>
<a href="https://other.site/ad/9">קיה 2014 14,000 ₪</a>
<a href="/about">אודות</a>
</body></html>"""


class GenericSourceTests(unittest.TestCase):
    def cars(self):
        return {c["url"].rsplit("/", 1)[-1]: c
                for c in sources.cards_from_html(GENERIC_HTML, "https://site.co.il/", "בדיקה")}

    def test_parse_text(self):
        f = sources.parse_car_text('קורולה 2013 אוטומט 140,000 ק"מ יד 2 ₪ 16,500')
        self.assertEqual((f["price"], f["year"], f["km"], f["hand"], f["gear"]),
                         (16500, 2013, 140000, 2, "אוטומטי"))

    def test_cards_same_domain_only(self):
        self.assertEqual(set(self.cars()), {"111", "222", "333"})

    def test_generic_filters(self):
        c = self.cars()
        self.assertIsNone(agent.reject_reason(c["111"], CFG))
        self.assertEqual(agent.reject_reason(c["222"], CFG), "gear")
        self.assertIn(agent.reject_reason(c["333"], CFG), ("promoted",) + tuple(
            "ownership:" + k for k in CFG["exclude_ownership_keywords"]))

    def test_section_discovery(self):
        pages = {"https://site.co.il/": "<a href='/used'>רכב יד 2</a>", "https://site.co.il/used": GENERIC_HTML}
        state = {}
        cars, status = sources.scan_source(
            {"name": "בדיקה", "url": "https://site.co.il/", "nav_words": ["רכב יד 2"]}, pages.__getitem__, state)
        self.assertEqual(len(cars), 3)
        self.assertEqual(state["__section:בדיקה"], "https://site.co.il/used")


import discovery  # noqa: E402

DDG_HTML = """
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fcars-board.co.il%2Fused&amp;rut=x">לוח רכבים</a>
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fsmall-site.co.il%2Fad%2F55&amp;rut=y">מודעה</a>
<a rel="nofollow" class="result__a" href="https://www.facebook.com/marketplace">fb</a>
"""
SINGLE_AD = """<html><head><title>למכירה מאזדה 3 2012 אוטומטית 150,000 ק"מ 15,500 ₪</title>
<meta name="description" content="יד 2, כל הטיפולים במוסך"></head><body>...</body></html>"""


class DiscoveryTests(unittest.TestCase):
    def test_parse_ddg(self):
        self.assertEqual(discovery.parse_ddg(DDG_HTML)[:2],
                         ["https://cars-board.co.il/used", "https://small-site.co.il/ad/55"])

    def test_single_ad(self):
        ad = discovery.single_ad(SINGLE_AD, "https://small-site.co.il/ad/55")
        self.assertEqual((ad["price"], ad["year"], ad["gear"]), (15500, 2012, "אוטומטי"))
        self.assertIsNone(agent.reject_reason(ad, CFG))

    def test_discover_remembers_sites_and_drops_dead_ones(self):
        orig = discovery.web_search
        discovery.web_search = lambda q, n: discovery.parse_ddg(DDG_HTML)
        pages = {"https://cars-board.co.il/used": GENERIC_HTML, "https://small-site.co.il/ad/55": SINGLE_AD}
        state = {}
        try:
            cars, status = discovery.discover(CFG, pages.__getitem__, state, set())
        finally:
            discovery.web_search = orig
        self.assertIn("cars-board.co.il", state["__discovered"])
        self.assertNotIn("facebook.com", state["__discovered"])
        self.assertEqual(len(cars), 4)  # 3 cards + 1 single ad
        # site goes dead: dropped after 3 failed runs
        cfg = dict(CFG, discovery=dict(CFG["discovery"], search_queries=[]))
        dead = lambda u: (_ for _ in ()).throw(IOError("down"))
        for _ in range(3):
            discovery.discover(cfg, dead, state, set())
        self.assertNotIn("cars-board.co.il", state["__discovered"])


if __name__ == "__main__":
    unittest.main()
