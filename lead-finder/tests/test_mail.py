"""Email finder/verifier tests against a real (local, fake) SMTP server."""

import json
import os
import socketserver
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

from leadfinder.mail import enrich, finder, names, smtp, verify, website
from leadfinder.store import Store


class FakeSMTP(socketserver.ThreadingTCPServer):
    """Answers RCPT like a real server: 250 for known mailboxes, 550 otherwise."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, mailboxes=(), catch_all=False, greylist=False):
        self.mailboxes = {m.lower() for m in mailboxes}
        self.catch_all = catch_all
        self.greylist = greylist
        self.rcpts = []
        super().__init__(("127.0.0.1", 0), FakeSMTPHandler)

    @property
    def port(self):
        return self.server_address[1]


class FakeSMTPHandler(socketserver.StreamRequestHandler):
    def reply(self, line):
        self.wfile.write((line + "\r\n").encode())

    def handle(self):
        srv = self.server
        self.reply("220 fake ESMTP")
        for raw in self.rfile:
            line = raw.decode().strip()
            cmd = line[:4].upper()
            if cmd in ("EHLO", "HELO"):
                self.reply("250-fake hello\r\n250 SIZE 1000000")
            elif cmd == "MAIL":
                self.reply("250 2.1.0 OK")
            elif cmd == "RCPT":
                addr = line.split(":", 1)[1].strip().strip("<>").lower()
                srv.rcpts.append(addr)
                if srv.greylist:
                    self.reply("450 4.2.0 Greylisted, try again later")
                elif srv.catch_all or addr in srv.mailboxes:
                    self.reply("250 2.1.5 OK")
                else:
                    self.reply("550 5.1.1 The email account that you tried to reach does not exist")
            elif cmd == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("250 OK")


def start(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def checker_for(server):
    return smtp.SMTPChecker(helo="test.local", mail_from="verify@test.local", port=server.port, timeout=5)


LOCAL_MX = lambda domain: ("127.0.0.1",) if not domain.endswith(".invalid") else ()


class NameTests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(names.ascii_slug("Jérôme Ørsted-Smit"), "jeromeorstedsmit")

    def test_dutch_particles(self):
        locals_ = [c[0] for c in names.candidates("Jan", "de Vries")]
        self.assertEqual(locals_[0], "jan.devries")
        self.assertIn("jan.vries", locals_)
        self.assertIn("jdevries", locals_)

    def test_preferred_pattern_first(self):
        self.assertEqual(names.candidates("Jane", "Doe", "{f}{last}")[0], ("jdoe", "{f}{last}"))

    def test_first_name_only(self):
        self.assertEqual(names.candidates("Jane", ""), [("jane", "{first}")])

    def test_infer(self):
        self.assertEqual(names.infer_pattern("j.doe@acme.com", "Jane", "Doe"), "{f}.{last}")
        self.assertIsNone(names.infer_pattern("sales@acme.com", "Jane", "Doe"))


class ClassifyTests(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(smtp.classify(250, "ok"), smtp.ACCEPTED)
        self.assertEqual(smtp.classify(550, "5.1.1 user unknown"), smtp.REJECTED)
        self.assertEqual(smtp.classify(450, "greylisted"), smtp.UNKNOWN)
        # A block on our IP is not an answer about the mailbox
        self.assertEqual(smtp.classify(554, "Service unavailable; client host blocked using Spamhaus"),
                         smtp.UNKNOWN)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.srv = start(FakeSMTP(["jane.doe@acme.test", "info@acme.test"]))
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def v(self, email):
        return verify.verify(email, checker_for(self.srv), LOCAL_MX)

    def test_valid(self):
        r = self.v("Jane.Doe@acme.test")
        self.assertEqual((r["status"], r["score"]), (verify.VALID, 95))

    def test_role_scores_lower(self):
        r = self.v("info@acme.test")
        self.assertEqual(r["status"], verify.VALID)
        self.assertTrue(r["role"])
        self.assertLess(r["score"], 95)

    def test_invalid_mailbox(self):
        self.assertEqual(self.v("nobody@acme.test")["status"], verify.INVALID)

    def test_syntax_and_disposable_and_no_mx(self):
        self.assertEqual(self.v("not-an-email")["status"], verify.INVALID)
        self.assertEqual(self.v("x@mailinator.com")["reason"], "disposable address")
        self.assertEqual(self.v("x@nothing.invalid")["reason"], "domain has no mail server")

    def test_catch_all(self):
        self.srv.catch_all = True
        self.assertEqual(self.v("anything@acme.test")["status"], verify.CATCH_ALL)

    def test_unreachable(self):
        closed = smtp.SMTPChecker(helo="t", mail_from="v@t", port=1, timeout=2)
        r = verify.verify("jane.doe@acme.test", closed, LOCAL_MX)
        self.assertEqual(r["status"], verify.UNKNOWN)


class FinderTests(unittest.TestCase):
    def setUp(self):
        self.srv = start(FakeSMTP(["jdevries@acme.test"]))
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def find(self, first, last, domain="acme.test", pattern=None):
        return finder.find_email(first, last, domain, checker_for(self.srv), pattern, LOCAL_MX)

    def test_finds_by_trying_patterns(self):
        r = self.find("Jan", "de Vries")
        self.assertEqual((r["email"], r["status"], r["pattern"]), ("jdevries@acme.test", "valid", "{f}{last}"))
        self.assertGreater(r["tested"], 1)
        self.assertEqual(self.srv.rcpts[-1], "jdevries@acme.test")  # stopped at the hit

    def test_known_pattern_goes_first(self):
        r = self.find("Jan", "de Vries", pattern="{f}{last}")
        self.assertEqual(r["tested"], 1)

    def test_not_found(self):
        r = self.find("Piet", "Jansen")
        self.assertEqual((r["email"], r["status"]), (None, "invalid"))

    def test_catch_all_guess(self):
        self.srv.catch_all = True
        r = self.find("Piet", "Jansen")
        self.assertEqual((r["email"], r["status"]), ("piet.jansen@acme.test", "catch_all"))

    def test_greylisted_is_unknown(self):
        self.srv.greylist = True
        r = self.find("Piet", "Jansen")
        self.assertEqual(r["status"], "unknown")
        self.assertEqual(r["email"], "piet.jansen@acme.test")

    def test_no_mx(self):
        self.assertEqual(self.find("Jan", "Smit", "acme.invalid")["reason"], "domain has no mail server")

    def test_domain_guess(self):
        mx = lambda d: ("mx",) if d == "acmewidgets.nl" else ()
        self.assertEqual(finder.domain_from_guess("Acme Widgets B.V.", "nl", mx), "acmewidgets.nl")
        self.assertIsNone(finder.domain_from_guess("Acme Widgets B.V.", "nl", lambda d: ()))

    def test_domain_from_search_skips_directories(self):
        class P:
            def search_page(self, q, page, country=""):
                return [{"url": "https://www.linkedin.com/company/acme", "title": "Acme"},
                        {"url": "https://www.acme-widgets.com/about", "title": "Acme Widgets | Home"}]
        self.assertEqual(finder.domain_from_search("Acme Widgets BV", provider=P()), "acme-widgets.com")


class WebsiteTests(unittest.TestCase):
    def test_extract(self):
        page = """<a href="mailto:jane.doe@acme.com">Mail</a> sales [at] acme.com
                  logo@2x.png bob@other.com Eve@Sub.Acme.com &#106;oe@acme.com"""
        self.assertEqual(website.extract_emails(page, "acme.com"),
                         {"jane.doe@acme.com", "sales@acme.com", "eve@sub.acme.com", "joe@acme.com"})

    def test_normalize(self):
        self.assertEqual(website.normalize_domain("https://www.Acme.com/x"), "acme.com")
        self.assertEqual(website.normalize_domain("jane@acme.com"), "acme.com")

    def test_search_domain_follows_team_links(self):
        pages = {
            "https://acme.test/": '<a href="/over-ons/team">Team</a> info@acme.test',
            "https://acme.test/over-ons/team": "jan.smit@acme.test, p.jansen@acme.test, k.berg@acme.test",
        }
        r = website.search_domain("acme.test", fetcher=lambda u: (u, pages.get(u, "")))
        self.assertEqual([e["email"] for e in r["emails"]],
                         ["info@acme.test", "jan.smit@acme.test", "k.berg@acme.test", "p.jansen@acme.test"])
        self.assertEqual(r["emails"][0]["type"], "role")
        self.assertEqual(r["pattern"], "{f}.{last}")


class EnrichTests(unittest.TestCase):
    def setUp(self):
        self.srv = start(FakeSMTP(["jane.doe@acme.test", "piet.jansen@acme.test", "kees@globex.test"]))
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.db = os.path.join(tempfile.mkdtemp(), "leads.db")

    def test_csv(self):
        text = ("Full Name,Website,Company\n"
                "Jane Doe,https://acme.test,Acme\n"
                "Kees Bakker,,Globex\n"
                "Nobody Here,,\n")
        mx = lambda d: ("127.0.0.1",) if d in ("acme.test", "globex.com") else ()
        store = Store(self.db)
        with mock.patch.object(finder, "TLDS_BY_COUNTRY", {"": [".com"]}):
            out, counts = enrich.enrich_csv(text, store, checker=checker_for(self.srv), mx_lookup=mx)
        rows = out.strip().splitlines()
        self.assertEqual(rows[0], "Full Name,Website,Company,email,email_status,email_score,email_pattern,domain,email_note")
        self.assertIn("jane.doe@acme.test,valid", rows[1])
        self.assertIn("globex.com", rows[2])  # domain guessed from company name
        self.assertIn("no_domain", rows[3])
        self.assertEqual(store.company_domain("Globex"), ("globex.com", "guess"))
        store.close()

    def test_csv_needs_columns(self):
        with self.assertRaises(ValueError):
            enrich.enrich_csv("email\nx@y.com\n")

    def test_store_learns_pattern(self):
        store = Store(self.db)
        for slug, first, last in [("jd", "Jane", "Doe"), ("pj", "Piet", "Jansen")]:
            store.upsert({"slug": slug, "linkedin_url": f"https://www.linkedin.com/in/{slug}",
                          "full_name": f"{first} {last}", "first_name": first, "last_name": last,
                          "headline": "", "company": "Acme", "location": "", "snippet": ""}, {})
        store.remember_company_domain("Acme", "acme.test", "search")
        counts = enrich.enrich_store(store, checker=checker_for(self.srv), mx_lookup=LOCAL_MX)
        self.assertEqual(counts, {"valid": 2})
        self.assertEqual(store.lead("pj")["email"], "piet.jansen@acme.test")
        self.assertEqual(store.patterns(), {"acme.test": "{first}.{last}"})
        # Nothing left to do on a second run
        self.assertEqual(enrich.enrich_store(store, checker=checker_for(self.srv), mx_lookup=LOCAL_MX), {})
        store.close()


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        from leadfinder import server
        cls.smtp = start(FakeSMTP(["jane.doe@acme.test"]))
        cls.env = mock.patch.dict(os.environ, {"SMTP_PORT": str(cls.smtp.port), "SMTP_HELO": "t.local",
                                               "LEADFINDER_PROVIDER": "none"})
        cls.env.start()
        cls.mx = mock.patch("leadfinder.mail.dns.mx_hosts", LOCAL_MX)
        cls.mx.start()
        server.Handler.db_path = os.path.join(tempfile.mkdtemp(), "leads.db")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.smtp.shutdown()
        cls.smtp.server_close()
        cls.mx.stop()
        cls.env.stop()

    def call(self, path, body=None, ctype="application/json"):
        data = None if body is None else (json.dumps(body).encode() if ctype == "application/json" else body)
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if "json" in r.headers["Content-Type"] else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_dashboard_and_stats(self):
        status, body = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Email finder", body)
        self.assertEqual(self.call("/api/stats")[1]["search_api"], False)

    def test_find_and_verify(self):
        status, r = self.call("/api/find", {"full_name": "Jane Doe", "domain": "acme.test"})
        self.assertEqual((status, r["email"], r["status"]), (200, "jane.doe@acme.test", "valid"))
        status, r = self.call("/api/verify", {"emails": ["jane.doe@acme.test", "x@acme.test"]})
        self.assertEqual([x["status"] for x in r["results"]], ["valid", "invalid"])

    def test_rejects_form_posts(self):
        # Cross-site forms can't send JSON; refusing anything else blocks CSRF
        status, _ = self.call("/api/find", b"full_name=x&domain=y", "application/x-www-form-urlencoded")
        self.assertEqual(status, 400)

    def test_bulk_job(self):
        status, r = self.call("/api/bulk", {"csv": "first_name,last_name,domain\nJane,Doe,acme.test\n"})
        self.assertEqual(status, 200)
        for _ in range(50):
            job = self.call(f"/api/jobs/{r['job']}")[1]
            if job["finished"]:
                break
            time.sleep(0.1)
        self.assertIsNone(job["error"])
        self.assertEqual(job["counts"], {"valid": 1})
        status, csv_bytes = self.call(f"/api/jobs/{r['job']}/download")
        self.assertIn("jane.doe@acme.test", csv_bytes.decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
