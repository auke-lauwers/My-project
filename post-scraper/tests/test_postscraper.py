import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from postscraper import rank, store
from postscraper.browser import normalize_account
from postscraper.cli import read_accounts
from postscraper.parse import (
    counts_from_voyager, merge_counts, parse_count, parse_feed_html, posted_at_from_id,
)

# 7255000000000000000 >> 22 = 1729727474380 ms -> 2024-10-23
OWN_ID = "7255000000000000000"
REPOST_ID = "7255000000000000001"

FEED_HTML = f"""
<div class="scaffold-finite-scroll__content">
  <div data-urn="urn:li:activity:{OWN_ID}" class="feed-shared-update-v2">
    <div class="update-components-actor">
      <span class="update-components-actor__title">
        <span aria-hidden="true">Bill Gates</span><span class="visually-hidden">View profile</span>
      </span>
    </div>
    <div class="update-components-text">
      <span dir="ltr">Malaria deaths are down by half.<br><br>
        Here is   what changed.</span>
    </div>
    <div class="update-components-image"><img src="x.jpg"></div>
    <ul class="social-details-social-counts">
      <li><span class="social-details-social-counts__reactions-count">12,345</span></li>
      <li><button aria-label="678 comments on Bill Gates’s post">678 comments</button></li>
      <li><button aria-label="1.2K reposts of Bill Gates’s post">1.2K reposts</button></li>
    </ul>
  </div>
  <div data-urn="urn:li:activity:{REPOST_ID}" class="feed-shared-update-v2">
    <div class="update-components-header">
      <span class="update-components-header__text-view">Bill Gates reposted this</span>
    </div>
    <span class="update-components-actor__title"><span aria-hidden="true">Someone Else</span></span>
    <div class="update-components-text">Not Bill's own post.</div>
    <span class="social-details-social-counts__reactions-count">50</span>
  </div>
</div>
"""


class ParseTests(unittest.TestCase):
    def test_parse_count(self):
        self.assertEqual(parse_count("12,345"), 12345)
        self.assertEqual(parse_count("12K"), 12000)
        self.assertEqual(parse_count("1.2M reactions"), 1_200_000)
        self.assertEqual(parse_count("3 comments"), 3)
        self.assertEqual(parse_count(""), 0)
        self.assertEqual(parse_count(None), 0)
        self.assertEqual(parse_count(42), 42)

    def test_posted_at_from_id(self):
        self.assertTrue(posted_at_from_id(OWN_ID).startswith("2024-10-23"))
        self.assertEqual(posted_at_from_id("123"), "")
        self.assertEqual(posted_at_from_id("nope"), "")

    def test_parse_feed_html(self):
        posts = parse_feed_html(FEED_HTML, "in/williamhgates")
        self.assertEqual([p.post_id for p in posts], [OWN_ID, REPOST_ID])
        own, repost = posts
        self.assertEqual(own.author, "Bill Gates")
        self.assertEqual(own.text, "Malaria deaths are down by half.\n\nHere is what changed.")
        self.assertEqual((own.reactions, own.comments, own.reposts), (12345, 678, 1200))
        self.assertEqual(own.media, "image")
        self.assertFalse(own.is_repost)
        self.assertTrue(own.url.endswith(f"urn:li:activity:{OWN_ID}/"))
        self.assertTrue(repost.is_repost)
        self.assertEqual(repost.reactions, 50)

    def test_voyager_counts_override_rounded_html(self):
        payload = {"included": [
            {"entityUrn": f"urn:li:fsd_socialActivityCounts:urn:li:activity:{OWN_ID}",
             "numLikes": 12377, "numComments": 681, "numShares": 1234},
            {"entityUrn": "urn:li:fsd_profile:abc", "firstName": "Bill"},
        ]}
        counts = counts_from_voyager(payload)
        self.assertEqual(counts, {OWN_ID: {"reactions": 12377, "comments": 681, "reposts": 1234}})
        own = merge_counts(parse_feed_html(FEED_HTML, "in/williamhgates"), counts)[0]
        self.assertEqual((own.reactions, own.comments, own.reposts), (12377, 681, 1234))


class AccountTests(unittest.TestCase):
    def test_normalize_account(self):
        self.assertEqual(
            normalize_account("https://www.linkedin.com/in/williamhgates/?trk=x"),
            ("in/williamhgates", "https://www.linkedin.com/in/williamhgates/recent-activity/all/"),
        )
        account, url = normalize_account("company/google")
        self.assertEqual(account, "company/google")
        self.assertIn("/company/google/posts/", url)
        self.assertEqual(normalize_account("@satyanadella")[0], "in/satyanadella")
        with self.assertRaises(ValueError):
            normalize_account("  # only a comment")

    def test_read_accounts_strips_comments_and_dupes(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# header\nin/a   # Person A\n\ncompany/b\nin/a\n")
        try:
            self.assertEqual(read_accounts(["in/c"], f.name), ["in/c", "in/a", "company/b"])
        finally:
            os.unlink(f.name)


def _post(pid, account, reactions, comments=0, reposts=0, days_ago=1, is_repost=False, text="hello"):
    posted = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {"post_id": pid, "account": account, "author": account, "text": text,
            "url": f"u/{pid}", "posted_at": posted.isoformat(), "reactions": reactions,
            "comments": comments, "reposts": reposts, "media": "", "is_repost": is_repost}


class RankTests(unittest.TestCase):
    def setUp(self):
        self.posts = [
            _post("1", "in/big", 10_000, 100, 10),      # 10230
            _post("2", "in/big", 9_000),                # 9000
            _post("3", "in/big", 11_000, days_ago=400),  # old
            _post("4", "in/small", 100),
            _post("5", "in/small", 2_000, 50),          # 2100, a breakout
            _post("6", "in/small", 120),
            _post("7", "in/big", 99_999, is_repost=True),
        ]

    def test_score_weights(self):
        self.assertEqual(rank.score(self.posts[0]), 10_000 + 200 + 30)

    def test_rank_by_score_skips_reposts(self):
        ids = [r["post_id"] for r in rank.rank(self.posts)]
        self.assertEqual(ids[0], "3")
        self.assertNotIn("7", ids)
        self.assertIn("7", [r["post_id"] for r in rank.rank(self.posts, include_reposts=True)])

    def test_days_filter(self):
        self.assertNotIn("3", [r["post_id"] for r in rank.rank(self.posts, days=30)])

    def test_vs_median_surfaces_breakouts(self):
        best = rank.rank(self.posts, days=30, sort="vs_median")[0]
        self.assertEqual(best["post_id"], "5")
        self.assertEqual(best["vs_median"], round(2100 / 120, 2))

    def test_top_per_account(self):
        rows = rank.top(self.posts, n=10, per_account=1, days=30)
        self.assertEqual([r["post_id"] for r in rows], ["1", "5"])


class StoreTests(unittest.TestCase):
    def test_upsert_save_load_and_export(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "data", "posts.jsonl")
            posts = store.load(db)
            self.assertEqual(store.upsert(posts, [_post("1", "in/a", 5)]), (1, 0))
            self.assertEqual(store.upsert(posts, [_post("1", "in/a", 9, text="")]), (0, 1))
            self.assertEqual(posts["1"]["text"], "hello")  # kept from the first scrape
            store.save(db, posts)
            self.assertEqual(store.load(db)["1"]["reactions"], 9)

            rows = rank.top(store.load(db).values())
            for ext in ("csv", "json", "md"):
                store.export(rows, os.path.join(d, f"top.{ext}"))
            with open(os.path.join(d, "top.json")) as f:
                self.assertEqual(json.load(f)[0]["rank"], 1)
            with open(os.path.join(d, "top.md")) as f:
                self.assertIn("**9** reactions", f.read())


if __name__ == "__main__":
    unittest.main()


SEARCH_HTML = """
<div class="search-results-container">
  <div data-urn="urn:li:activity:7255000000000000010">
    <div class="update-components-actor">
      <a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/jane-doe?miniProfileUrn=abc">
        <span class="update-components-actor__title"><span aria-hidden="true">Jane Doe</span></span>
        <span class="update-components-actor__description"><span aria-hidden="true">Founder @ Acme | Cold email</span></span>
      </a>
    </div>
    <div class="update-components-text">Cold email is not dead.</div>
    <span class="social-details-social-counts__reactions-count">2,100</span>
  </div>
  <div data-urn="urn:li:activity:7255000000000000011">
    <div class="update-components-actor"><a href="/company/acme-inc/">Acme</a></div>
    <div class="update-components-text">We are hiring.</div>
  </div>
  <div data-urn="urn:li:activity:7255000000000000012">
    <div class="update-components-actor"><span>No link at all</span></div>
  </div>
</div>
"""


class SearchTests(unittest.TestCase):
    def test_search_url(self):
        from postscraper.parse import search_url
        url = search_url("cold email", "past-week")
        self.assertIn("keywords=cold%20email", url)
        self.assertIn("datePosted=%22past-week%22", url)
        self.assertNotIn("datePosted", search_url("x", ""))

    def test_account_from_url(self):
        from postscraper.parse import account_from_url
        self.assertEqual(account_from_url("https://www.linkedin.com/in/jane-doe?x=1"), "in/jane-doe")
        self.assertEqual(account_from_url("/company/acme-inc/"), "company/acme-inc")
        self.assertEqual(account_from_url("https://www.linkedin.com/feed/"), "")

    def test_parse_search_results_credits_authors(self):
        posts = parse_feed_html(SEARCH_HTML, source="search:cold email")
        self.assertEqual([p.account for p in posts], ["in/jane-doe", "company/acme-inc"])  # 3rd unattributable
        jane = posts[0]
        self.assertEqual(jane.author, "Jane Doe")
        self.assertEqual(jane.headline, "Founder @ Acme | Cold email")
        self.assertEqual(jane.author_url, "https://www.linkedin.com/in/jane-doe/")
        self.assertEqual(jane.sources, ["search:cold email"])
        self.assertEqual(jane.reactions, 2100)

    def test_upsert_merges_sources(self):
        posts = {}
        store.upsert(posts, [dict(_post("1", "in/a", 5), sources=["account"])])
        store.upsert(posts, [dict(_post("1", "in/a", 7), sources=["search:sales"], headline="")])
        self.assertEqual(posts["1"]["sources"], ["account", "search:sales"])
        self.assertEqual(posts["1"]["reactions"], 7)

    def test_creators(self):
        posts = [
            dict(_post("1", "in/jane", 2000), sources=["search:cold email"], headline="Founder"),
            dict(_post("2", "in/jane", 100), sources=["account"]),
            dict(_post("3", "in/bob", 500), sources=["search:sales"]),
            dict(_post("4", "in/me", 9000), sources=["account"]),  # never found via a topic
        ]
        rows = rank.creators(posts, followed={"in/bob"})
        self.assertEqual([c["account"] for c in rows], ["in/jane", "in/bob"])
        jane, bob = rows
        self.assertEqual((jane["posts"], jane["best_score"], jane["avg_score"]), (2, 2000, 1050))
        self.assertEqual(jane["topics"], ["cold email"])
        self.assertTrue(bob["followed"])
        self.assertEqual([c["account"] for c in rank.creators(posts, topic="sales")], ["in/bob"])
        self.assertEqual(rank.topics(posts), ["cold email", "sales"])
