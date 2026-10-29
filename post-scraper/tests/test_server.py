import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from postscraper import server, store
from tests.test_postscraper import _post


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        posts = {}
        store.upsert(posts, [_post("1", "in/a", 500, 10), _post("2", "in/a", 50),
                             _post("3", "in/b", 900, text="Hiring is hard"), _post("4", "in/b", 90)])
        store.save("data/posts.jsonl", posts)
        with open("accounts.txt", "w") as f:
            f.write("in/a\nin/b  # B\n")
        server.Handler.db_path = "data/posts.jsonl"
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        os.environ.pop("LI_AT", None)
        os.environ.pop("POSTSCRAPER_PASSWORD", None)
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.headers, r.read().decode()

    def post(self, path, body, ctype="application/json"):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": ctype}, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_index_and_status(self):
        status, _, html = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("PostScraper", html.replace("<span>", "").replace("</span>", ""))
        status = json.loads(self.get("/api/status")[2])
        self.assertEqual((status["posts"], status["accounts"], status["scraped_accounts"]), (4, 2, 2))
        self.assertFalse(status["session"]["cookie_set"])

    def test_posts_filters(self):
        rows = json.loads(self.get("/api/posts")[2])["rows"]
        self.assertEqual([r["post_id"] for r in rows], ["3", "1", "4", "2"])
        rows = json.loads(self.get("/api/posts?per_account=1")[2])["rows"]
        self.assertEqual([r["post_id"] for r in rows], ["3", "1"])
        rows = json.loads(self.get("/api/posts?account=in/a")[2])["rows"]
        self.assertEqual({r["account"] for r in rows}, {"in/a"})
        rows = json.loads(self.get("/api/posts?q=hiring")[2])["rows"]
        self.assertEqual([r["post_id"] for r in rows], ["3"])
        self.assertEqual(rows[0]["vs_median"], round(900 / 495, 2))  # median over all of in/b
        rows = json.loads(self.get("/api/posts?q=hello&limit=1")[2])["rows"]
        self.assertEqual([r["post_id"] for r in rows], ["1"])

    def test_export(self):
        status, headers, body = self.get("/api/export?format=csv&per_account=1")
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(len(body.strip().splitlines()), 3)
        self.assertTrue(json.loads(self.get("/api/export?format=json")[2]))
        with self.assertRaises(urllib.error.HTTPError):
            self.get("/api/export?format=exe")

    def test_accounts_roundtrip_and_validation(self):
        self.assertEqual(self.post("/api/accounts", {"text": "in/x\ncompany/y # Y\n"}), (200, {"ok": True, "count": 2}))
        self.assertIn("in/x", json.loads(self.get("/api/accounts")[2])["text"])
        status, body = self.post("/api/accounts", {"text": "https://www.linkedin.com/in/ok/\n   #\n"})
        self.assertEqual(status, 200)

    def test_settings_are_clamped(self):
        status, body = self.post("/api/settings", {"min_delay": 0, "max_delay": 1, "max_posts": 9999, "schedule_hours": 24})
        s = body["settings"]
        self.assertEqual((s["min_delay"], s["max_delay"], s["max_posts"], s["schedule_hours"]), (3, 3, 200, 24))
        self.assertIsNotNone(json.loads(self.get("/api/status")[2])["next_run_at"])

    def test_cookie_saved_to_env(self):
        self.assertEqual(self.post("/api/cookie", {"li_at": "short"})[0], 400)
        good = "AQEDA" + "x" * 60
        self.assertEqual(self.post("/api/cookie", {"li_at": good})[0], 200)
        with open(".env") as f:
            self.assertIn(f"LI_AT={good}", f.read())
        self.assertEqual(oct(os.stat(".env").st_mode & 0o777), "0o600")
        self.assertTrue(json.loads(self.get("/api/status")[2])["session"]["cookie_set"])

    def test_post_requires_json(self):
        self.assertEqual(self.post("/api/stop", {}, ctype="text/plain")[0], 400)

    def test_password(self):
        os.environ["POSTSCRAPER_PASSWORD"] = "s3cret"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/status")
        self.assertEqual(cm.exception.code, 401)


if __name__ == "__main__":
    unittest.main()


class TopicServerTests(ServerTests):
    def test_topics_creators_follow_and_filters(self):
        posts = store.load("data/posts.jsonl")
        store.upsert(posts, [
            dict(_post("9", "in/jane", 3000), sources=["search:cold email"], media="document"),
            dict(_post("8", "in/kim", 40), sources=["search:cold email"]),
        ])
        store.save("data/posts.jsonl", posts)

        self.assertEqual(self.post("/api/topics", {"text": "cold   email\n\nsales\n"}), (200, {"ok": True, "count": 2}))
        self.assertEqual(json.loads(self.get("/api/topics")[2])["text"], "cold email\n\nsales\n")

        creators = json.loads(self.get("/api/creators")[2])
        self.assertEqual([c["account"] for c in creators["rows"]], ["in/jane", "in/kim"])
        self.assertEqual(creators["topics"], ["cold email"])

        self.assertEqual(self.post("/api/follow", {"account": "in/jane"}), (200, {"ok": True, "added": True}))
        self.assertEqual(self.post("/api/follow", {"account": "https://www.linkedin.com/in/jane/"})[1]["added"], False)
        self.assertIn("in/jane", json.loads(self.get("/api/accounts")[2])["text"])
        self.assertTrue(json.loads(self.get("/api/creators")[2])["rows"][0]["followed"])

        data = json.loads(self.get("/api/posts?source=topics")[2])
        self.assertEqual({r["post_id"] for r in data["rows"]}, {"9", "8"})
        self.assertIn("in/jane", data["followed"])
        self.assertEqual(data["topics"], ["cold email"])
        self.assertEqual({r["post_id"] for r in json.loads(self.get("/api/posts?source=accounts")[2])["rows"]},
                         {"1", "2", "3", "4"})
        self.assertEqual([r["post_id"] for r in json.loads(self.get("/api/posts?media=document")[2])["rows"]], ["9"])
        self.assertEqual({r["post_id"] for r in json.loads(self.get("/api/posts?min_reactions=600")[2])["rows"]},
                         {"9", "3"})

    def test_run_needs_something_to_do(self):
        os.remove("accounts.txt")
        status, body = self.post("/api/run", {"what": "topics"})
        self.assertEqual((status, body["ok"]), (409, False))
        self.assertIn("topics", body["message"])
        self.assertEqual(self.post("/api/run", {"what": "nope"})[0], 400)
