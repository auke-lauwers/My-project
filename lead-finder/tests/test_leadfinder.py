import csv
import os
import tempfile
import unittest
from unittest import mock

from leadfinder import cli, providers
from leadfinder.parse import parse_location, parse_result, parse_title, profile_slug
from leadfinder.query import build_query, expand_queries
from leadfinder.store import Store


class QueryTests(unittest.TestCase):
    def test_build_query(self):
        q = build_query("Head of Marketing", "Amsterdam", ["SaaS"], ["recruiter"])
        self.assertEqual(q, 'site:linkedin.com/in "Head of Marketing" "Amsterdam" "SaaS" -"recruiter"')

    def test_expand_is_cartesian(self):
        qs = list(expand_queries(["CMO", "CEO"], ["Utrecht", "Leiden"]))
        self.assertEqual(len(qs), 4)
        self.assertEqual(qs[0]["title"], "CMO")
        self.assertEqual(qs[1]["location"], "Leiden")

    def test_expand_without_locations(self):
        qs = list(expand_queries(["CMO"], []))
        self.assertEqual(qs[0]["query"], 'site:linkedin.com/in "CMO"')


class ParseTests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(profile_slug("https://nl.linkedin.com/in/Jane-Doe-123/?trk=x"), "jane-doe-123")
        self.assertEqual(profile_slug("https://www.linkedin.com/in/j%C3%A9r%C3%B4me"), "jérôme")
        self.assertIsNone(profile_slug("https://www.linkedin.com/company/acme"))
        self.assertIsNone(profile_slug("https://www.linkedin.com/pulse/some-post"))

    def test_title_three_parts(self):
        t = parse_title("Jane Doe - Head of Marketing - Acme BV | LinkedIn")
        self.assertEqual(t, {"full_name": "Jane Doe", "headline": "Head of Marketing", "company": "Acme BV"})

    def test_title_company_only(self):
        t = parse_title("Jan de Vries – Bol.com | LinkedIn")
        self.assertEqual((t["full_name"], t["company"], t["headline"]), ("Jan de Vries", "Bol.com", ""))

    def test_title_headline_with_at(self):
        t = parse_title("Sam Lee - Growth Lead at Mollie | LinkedIn")
        self.assertEqual((t["headline"], t["company"]), ("Growth Lead", "Mollie"))

    def test_title_truncated(self):
        t = parse_title("Anna Smit - Chief Marketing Officer - Very Long Compa... | LinkedIn")
        self.assertEqual(t["company"], "Very Long Compa")

    def test_location(self):
        self.assertEqual(parse_location("Head of Marketing · Location: Amsterdam · 500+ connections"), "Amsterdam")
        self.assertEqual(parse_location("Rotterdam, South Holland, Netherlands · CMO · Acme"),
                         "Rotterdam, South Holland, Netherlands")
        self.assertEqual(parse_location("Experienced marketer. I love growth, data and SaaS."), "")

    def test_result_name_split(self):
        lead = parse_result({"url": "https://www.linkedin.com/in/jd",
                             "title": "Jane van der Berg, MBA (she/her) - CMO - Acme | LinkedIn",
                             "snippet": "Location: Utrecht"})
        self.assertEqual((lead["first_name"], lead["last_name"]), ("Jane", "van der Berg"))
        self.assertEqual(lead["location"], "Utrecht")
        self.assertEqual(lead["linkedin_url"], "https://www.linkedin.com/in/jd")

    def test_non_profile_skipped(self):
        self.assertIsNone(parse_result({"url": "https://www.linkedin.com/jobs/view/1", "title": "x"}))


class FakeProvider(providers.Provider):
    name = "fake"
    page_size = 2
    max_results = 100

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def search_page(self, query, page, country=""):
        self.calls.append((query, page))
        return self.pages[page] if page < len(self.pages) else []


class SearchPagingTests(unittest.TestCase):
    def test_stops_at_short_page(self):
        p = FakeProvider([[{"url": "a"}, {"url": "b"}], [{"url": "c"}]])
        self.assertEqual(len(list(providers.search(p, "q", 100, delay=0))), 3)
        self.assertEqual(len(p.calls), 2)

    def test_respects_limit(self):
        p = FakeProvider([[{"url": "a"}, {"url": "b"}]] * 10)
        self.assertEqual(len(list(providers.search(p, "q", 3, delay=0))), 3)


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "leads.db")
        self.fake = FakeProvider([[
            {"url": "https://nl.linkedin.com/in/jane-doe", "title": "Jane Doe - CMO - Acme | LinkedIn",
             "snippet": "Location: Amsterdam · 500+ connections"},
            {"url": "https://www.linkedin.com/company/acme", "title": "Acme | LinkedIn", "snippet": ""},
        ], [
            {"url": "https://www.linkedin.com/in/jane-doe/", "title": "Jane Doe - CMO - Acme | LinkedIn",
             "snippet": ""},
        ]])
        patcher = mock.patch.object(providers, "get_provider", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *argv):
        return cli.main(["--db", self.db, *argv])

    def test_search_dedupe_export_forget(self):
        self.assertEqual(self.run_cli("search", "--title", "CMO", "--location", "Amsterdam", "--delay", "0"), 0)
        store = Store(self.db)
        rows = store.leads()
        self.assertEqual(len(rows), 1)  # company page skipped, duplicate merged
        self.assertEqual(rows[0]["location"], "Amsterdam")
        self.assertEqual(rows[0]["search_title"], "CMO")
        store.close()

        # Same query is skipped next time
        calls = len(self.fake.calls)
        self.run_cli("search", "--title", "CMO", "--location", "Amsterdam", "--delay", "0")
        self.assertEqual(len(self.fake.calls), calls)

        out = os.path.join(self.tmp, "out.csv")
        self.run_cli("export", out)
        with open(out, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["full_name"], "Jane Doe")
        self.assertEqual(rows[0]["company"], "Acme")

        self.run_cli("forget", "https://www.linkedin.com/in/jane-doe")
        self.run_cli("search", "--title", "CMO", "--location", "Amsterdam", "--delay", "0", "--rerun")
        store = Store(self.db)
        self.assertEqual(len(store.leads()), 0)  # suppressed person stays out
        store.close()


if __name__ == "__main__":
    unittest.main()
