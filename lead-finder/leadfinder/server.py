"""Web dashboard: email finder, domain search, verifier, bulk CSV and saved leads.

    python3 -m leadfinder serve            # http://127.0.0.1:8080

Standard library only. Set LEADFINDER_PASSWORD to require a login when it
runs on a server.
"""

import base64
import hmac
import json
import os
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import providers
from .mail import enrich, finder, verify, website
from .mail.names import split_full_name
from .store import FIELDS, Store

STATIC = Path(__file__).parent / "static"
MAX_BODY = 20_000_000
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def optional_provider():
    """The configured search provider, or None when no API key is set (domain lookup then guesses)."""
    name = os.environ.get("LEADFINDER_PROVIDER", "serper")
    keys = {"serper": ["SERPER_API_KEY"], "serpapi": ["SERPAPI_API_KEY"],
            "brave": ["BRAVE_API_KEY"], "google": ["GOOGLE_API_KEY", "GOOGLE_CSE_ID"]}
    if name not in keys or not all(os.environ.get(v) for v in keys[name]):
        return None
    return providers.get_provider(name)


def _start_job(kind: str, fn) -> str:
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "kind": kind, "done": 0, "total": 0, "finished": False,
           "error": None, "counts": {}, "output": None, "recent": []}
    with JOBS_LOCK:
        JOBS[job_id] = job

    def progress(done, total, record, found):
        with JOBS_LOCK:
            job["done"], job["total"] = done, total
            job["recent"] = ([{"name": f"{record.get('first_name', '')} {record.get('last_name', '')}".strip(),
                               "email": found.get("email"), "status": found["status"]}]
                             + job["recent"])[:15]

    def run():
        try:
            fn(job, progress)
        except Exception as e:  # surfaced to the UI
            job["error"] = str(e)
            traceback.print_exc()
        finally:
            job["finished"] = True

    threading.Thread(target=run, daemon=True).start()
    return job_id


class Handler(BaseHTTPRequestHandler):
    db_path = "leads.db"
    country = ""
    server_version = "lead-finder"

    # ---- plumbing -------------------------------------------------------
    def log_message(self, fmt, *args):
        if os.environ.get("LEADFINDER_DEBUG"):
            super().log_message(fmt, *args)

    def _authorized(self) -> bool:
        password = os.environ.get("LEADFINDER_PASSWORD")
        if not password:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(header[6:]).decode().partition(":")
                if hmac.compare_digest(given, password):
                    return True
            except ValueError:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="lead-finder"')
        self.end_headers()
        return False

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200):
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json")

    def _body(self) -> dict:
        # JSON only: browsers can't send it cross-site without a preflight, which blocks CSRF
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("send JSON")
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            raise ValueError("upload too large (20 MB max)")
        return json.loads(self.rfile.read(length) or b"{}")

    # ---- routes ---------------------------------------------------------
    def do_GET(self):
        if not self._authorized():
            return
        url = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/stats":
                with_store = Store(self.db_path)
                try:
                    stats = with_store.stats()
                finally:
                    with_store.close()
                stats["search_api"] = bool(optional_provider())
                return self._json(stats)
            if url.path == "/api/leads":
                store = Store(self.db_path)
                try:
                    rows = store.leads(q.get("status"), q.get("q"), q.get("email_status"))
                    data = [{k: r[k] for k in FIELDS} for r in rows[-int(q.get("limit", 500)):]]
                finally:
                    store.close()
                return self._json({"leads": data[::-1], "total": len(rows)})
            if url.path == "/api/export.csv":
                store = Store(self.db_path)
                tmp = Path(self.db_path).with_suffix(".export.csv")
                try:
                    store.export(str(tmp), store.leads(q.get("status"), q.get("q"), q.get("email_status")))
                finally:
                    store.close()
                body = tmp.read_bytes()
                tmp.unlink(missing_ok=True)
                return self._send(200, body, "text/csv; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="leads.csv"'})
            if url.path.startswith("/api/jobs/"):
                parts = url.path.split("/")
                with JOBS_LOCK:
                    job = JOBS.get(parts[3])
                    snapshot = dict(job) if job else None
                if not snapshot:
                    return self._json({"error": "no such job"}, 404)
                if len(parts) > 4 and parts[4] == "download":
                    return self._send(200, (snapshot["output"] or "").encode("utf-8-sig"),
                                      "text/csv; charset=utf-8",
                                      {"Content-Disposition": 'attachment; filename="emails.csv"'})
                snapshot["has_output"] = bool(snapshot.pop("output"))
                return self._json(snapshot)
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        try:
            body = self._body()
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        try:
            handler = {
                "/api/find": self.api_find,
                "/api/verify": self.api_verify,
                "/api/domain": self.api_domain,
                "/api/bulk": self.api_bulk,
                "/api/enrich": self.api_enrich,
            }.get(path)
            if not handler:
                return self._json({"error": "not found"}, 404)
            return handler(body)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def api_find(self, body):
        first, last = body.get("first_name", "").strip(), body.get("last_name", "").strip()
        if not first and body.get("full_name"):
            first, last = split_full_name(body["full_name"])
        domain, source = website.normalize_domain(body.get("domain", "")), "given"
        store = Store(self.db_path)
        try:
            company = body.get("company", "").strip()
            if not domain and company:
                cached = store.company_domain(company)
                domain, source = cached or finder.company_domain(
                    company, country=body.get("country", self.country), provider=optional_provider())
                if not cached:
                    store.remember_company_domain(company, domain, source)
            if not first or not domain:
                raise ValueError("Need a name and a domain (or a company we can find the domain for)")
            found = finder.find_email(first, last, domain, known_pattern=store.patterns().get(domain))
            if found["status"] == verify.VALID and found["pattern"]:
                store.learn_pattern(domain, found["pattern"])
        finally:
            store.close()
        found["domain_source"] = source
        return self._json(found)

    def api_verify(self, body):
        emails = body.get("emails") or [body.get("email", "")]
        emails = [e.strip() for e in emails if e and e.strip()][:200]
        if not emails:
            raise ValueError("Give an email address")
        return self._json({"results": [verify.verify(e) for e in emails]})

    def api_domain(self, body):
        domain = website.normalize_domain(body.get("domain", ""))
        if not domain:
            raise ValueError("Give a domain, e.g. acme.com")
        data = website.search_domain(domain)
        store = Store(self.db_path)
        try:
            data["known_pattern"] = store.patterns().get(domain)
        finally:
            store.close()
        return self._json(data)

    def api_bulk(self, body):
        text = body.get("csv", "")
        if not text.strip():
            raise ValueError("Upload a CSV")
        enrich.records_from_csv(text)  # fail fast on unreadable files
        country, db = body.get("country", self.country), self.db_path

        def run(job, progress):
            store = Store(db)
            try:
                job["output"], job["counts"] = enrich.enrich_csv(
                    text, store, optional_provider(), country, progress=progress)
            finally:
                store.close()
        return self._json({"job": _start_job("bulk", run)})

    def api_enrich(self, body):
        country, db, redo = body.get("country", self.country), self.db_path, bool(body.get("redo"))

        def run(job, progress):
            store = Store(db)
            try:
                job["counts"] = enrich.enrich_store(store, optional_provider(), country,
                                                    redo=redo, progress=progress)
            finally:
                store.close()
        return self._json({"job": _start_job("enrich", run)})


def serve(db_path: str, host: str = "127.0.0.1", port: int = 8080, country: str = ""):
    if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("LEADFINDER_PASSWORD"):
        raise SystemExit("Set LEADFINDER_PASSWORD before listening on a public address.")
    Handler.db_path, Handler.country = db_path, country
    Store(db_path).close()  # create/migrate before the first request
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"lead-finder dashboard on http://{host}:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
