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


if __name__ == "__main__":
    unittest.main()
