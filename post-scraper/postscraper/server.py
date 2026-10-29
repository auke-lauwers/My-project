"""Web dashboard: accounts, LinkedIn session, scrape runs with a live log,
a schedule, and the ranked top posts with export.

    python -m postscraper serve                 # http://127.0.0.1:8080
    POSTSCRAPER_PASSWORD=... python -m postscraper serve --host 0.0.0.0

Standard library only (plus what the scraper itself needs). Set
POSTSCRAPER_PASSWORD to require a login when it runs on a server.
"""

import base64
import hmac
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import rank, store
from .browser import SIGNED_IN_MARKER, normalize_account
from .cli import read_accounts

STATIC = Path(__file__).parent / "static"
MAX_BODY = 1_000_000
ACCOUNTS_FILE = "accounts.txt"
TOPICS_FILE = "topics.txt"
SETTINGS_FILE = "data/settings.json"
DATE_RANGES = ("past-24h", "past-week", "past-month", "")
DEFAULT_SETTINGS = {
    "max_posts": 30, "scrolls": 10, "min_delay": 8, "max_delay": 20,
    "topic_posts": 50, "date_posted": "past-month",
    "show_browser": False, "schedule_hours": 0, "last_run_at": None,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---- settings, accounts and session ---------------------------------------

def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            settings.update(json.load(f))
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings: dict):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def clean_settings(body: dict) -> dict:
    s = load_settings()
    ints = {"max_posts": (1, 200), "topic_posts": (1, 200), "scrolls": (1, 50),
            "schedule_hours": (0, 24 * 30)}
    floats = {"min_delay": (3, 600), "max_delay": (3, 600)}
    for key, (lo, hi) in {**ints, **floats}.items():
        if key in body and body[key] not in ("", None):
            value = float(body[key])
            s[key] = max(lo, min(hi, int(value) if key in ints else value))
    if body.get("date_posted") in DATE_RANGES:
        s["date_posted"] = body["date_posted"]
    if "show_browser" in body:
        s["show_browser"] = bool(body["show_browser"])
    s["max_delay"] = max(s["max_delay"], s["min_delay"])
    return s


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def read_list(path: str) -> list:
    return read_accounts([], path) if os.path.exists(path) else []


def followed_accounts() -> set:
    out = set()
    for line in read_list(ACCOUNTS_FILE):
        try:
            out.add(normalize_account(line)[0])
        except ValueError:
            pass
    return out


def follow(account: str) -> bool:
    """Add an account to accounts.txt; False if it was already there."""
    account = normalize_account(account)[0]
    if account in followed_accounts():
        return False
    text = read_text(ACCOUNTS_FILE)
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(("" if not text or text.endswith("\n") else "\n") + account + "  # found via topic search\n")
    return True


def write_env_value(key: str, value: str, path: str = ".env"):
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)
    os.environ[key] = value


def can_open_browser() -> bool:
    """A visible sign-in window needs a desktop; a bare Linux server has none."""
    return not sys.platform.startswith("linux") or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


# ---- the one background job: a scrape run or a sign-in window --------------

class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.state = {"kind": None, "running": False, "done": 0, "total": 0,
                      "log": [], "started_at": None, "finished_at": None,
                      "error": None, "summary": None, "trigger": None}
        self.session = {"status": "unknown", "message": ""}

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def log(self, line: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.state["log"] = (self.state["log"] + [f"{stamp}  {line}"])[-400:]

    def start(self, kind: str, fn, trigger="manual") -> bool:
        with self.lock:
            if self.state["running"]:
                return False
            self.stop.clear()
            self.state.update(kind=kind, running=True, done=0, total=0, log=[],
                              started_at=now_iso(), finished_at=None, error=None,
                              summary=None, trigger=trigger)

        def run():
            try:
                fn()
            except Exception as e:  # surfaced to the UI
                traceback.print_exc()
                with self.lock:
                    self.state["error"] = str(e)
                self.log(f"Error: {e}")
            finally:
                with self.lock:
                    self.state["running"] = False
                    self.state["finished_at"] = now_iso()

        threading.Thread(target=run, daemon=True).start()
        return True


JOB = Job()


def start_scrape(db: str, what="all", trigger="manual") -> tuple:
    """what: 'all', 'accounts' or 'topics'."""
    from .browser import SignedOut
    from .runner import run_scrape

    accounts = read_list(ACCOUNTS_FILE) if what in ("all", "accounts") else []
    topics = read_list(TOPICS_FILE) if what in ("all", "topics") else []
    if not accounts and not topics:
        return False, {"accounts": "Add some accounts first.", "topics": "Add some topics first."}.get(
            what, "Add some accounts or topics first.")
    settings = load_settings()

    def progress(done, total):
        with JOB.lock:
            JOB.state["done"], JOB.state["total"] = done, total

    def work():
        with JOB.lock:
            JOB.state["total"] = len(accounts) + len(topics)
        # Stamp the start, not the end, so a failing run isn't retried every minute.
        s = load_settings()
        s["last_run_at"] = now_iso()
        save_settings(s)
        try:
            summary = run_scrape(
                accounts, db, topics=topics,
                max_posts=settings["max_posts"], topic_posts=settings["topic_posts"],
                date_posted=settings["date_posted"], scrolls=settings["scrolls"],
                delay=(settings["min_delay"], settings["max_delay"]),
                headless=not (settings["show_browser"] and can_open_browser()),
                li_at=os.environ.get("LI_AT", ""),
                log=JOB.log, progress=progress, stop=JOB.stop,
            )
        except SignedOut as e:
            JOB.session.update(status="signed_out", message=str(e))
            raise
        JOB.session.update(status="ok", message="")
        with JOB.lock:
            JOB.state["summary"] = summary

    if not JOB.start("scrape", work, trigger):
        return False, "A job is already running."
    parts = [f"{len(accounts)} accounts" if accounts else "", f"{len(topics)} topics" if topics else ""]
    return True, "Started: " + " and ".join(p for p in parts if p) + "."


def start_login() -> tuple:
    if not can_open_browser():
        return False, "No screen on this machine to open a browser. Paste your li_at cookie instead."

    def work():
        from .browser import login
        JOB.log("Opening a browser window. Sign in there; this finishes once your feed loads.")
        login()
        JOB.session.update(status="ok", message="")
        JOB.log("Signed in. Session saved.")

    if not JOB.start("login", work):
        return False, "A job is already running."
    return True, "Browser opened."


def scheduler(db: str):
    """Start a run when the schedule says one is due. Checks once a minute."""
    while True:
        time.sleep(60)
        try:
            s = load_settings()
            hours = s.get("schedule_hours") or 0
            if not hours or JOB.snapshot()["running"]:
                continue
            last = s.get("last_run_at")
            due = not last or (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() >= hours * 3600
            if due:
                start_scrape(db, trigger="schedule")
        except Exception:
            traceback.print_exc()


def next_run_at(settings: dict):
    hours = settings.get("schedule_hours") or 0
    if not hours:
        return None
    last = settings.get("last_run_at")
    if not last:
        return now_iso()
    ts = datetime.fromisoformat(last).timestamp() + hours * 3600
    return datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat()


# ---- HTTP -------------------------------------------------------------------

def _q(query: dict, key: str, default=None):
    value = query.get(key, [""])[0].strip()
    return value if value else default


def query_rows(db: str, query: dict) -> tuple:
    posts = list(store.load(db).values())
    meta = {"accounts": sorted({p["account"] for p in posts}), "topics": rank.topics(posts)}
    days = _q(query, "days")
    per_account = _q(query, "per_account")
    account = _q(query, "account")
    if account:
        posts = [p for p in posts if p["account"] == account]
    rows = rank.rank(
        posts,
        days=int(days) if days else None,
        include_reposts=_q(query, "include_reposts") == "1",
        min_text=int(_q(query, "min_text", "0")),
        sort=_q(query, "sort", "score"),
    ) if posts else []
    # Search after ranking, so x-median still compares against the whole account,
    # and before the limits, so matches outside the top N still show.
    q = (_q(query, "q") or "").lower()
    if q:
        rows = [r for r in rows if q in (r.get("text") or "").lower() or q in (r.get("author") or "").lower()]
    source = _q(query, "source")
    if source:
        rows = [r for r in rows if rank.has_source(r, source)]
    media = _q(query, "media")
    if media:
        rows = [r for r in rows if (r.get("media") or "text") == media]
    min_reactions = int(_q(query, "min_reactions", "0"))
    if min_reactions:
        rows = [r for r in rows if r["reactions"] >= min_reactions]
    rows = rank.pick(rows, int(_q(query, "limit", "100")), int(per_account) if per_account else None)
    return rows, meta


class Handler(BaseHTTPRequestHandler):
    db_path = "data/posts.jsonl"
    server_version = "post-scraper"

    def log_message(self, fmt, *args):
        if os.environ.get("POSTSCRAPER_DEBUG"):
            super().log_message(fmt, *args)

    def _authorized(self) -> bool:
        password = os.environ.get("POSTSCRAPER_PASSWORD")
        if not password:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(header[6:]).decode().partition(":")
                if hmac.compare_digest(given.encode(), password.encode()):
                    return True
            except ValueError:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="post-scraper"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _send(self, status: int, body: bytes, ctype: str, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
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
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if not self._authorized():
            return
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/status":
                self._json(self.status())
            elif url.path == "/api/job":
                self._json(JOB.snapshot())
            elif url.path == "/api/accounts":
                self._json({"text": read_text(ACCOUNTS_FILE)})
            elif url.path == "/api/posts":
                rows, meta = query_rows(self.db_path, query)
                self._json({"rows": rows, "followed": sorted(followed_accounts()), **meta})
            elif url.path == "/api/topics":
                self._json({"text": read_text(TOPICS_FILE)})
            elif url.path == "/api/creators":
                days = _q(query, "days")
                posts = list(store.load(self.db_path).values())
                self._json({"rows": rank.creators(posts, days=int(days) if days else None,
                                                  topic=_q(query, "topic"), followed=followed_accounts()),
                            "topics": rank.topics(posts)})
            elif url.path == "/api/export":
                fmt = _q(query, "format", "csv")
                if fmt not in ("csv", "json", "md"):
                    raise ValueError("format must be csv, json or md")
                rows, _ = query_rows(self.db_path, query)
                ctype = {"csv": "text/csv", "json": "application/json", "md": "text/markdown"}[fmt]
                name = f"top-linkedin-posts-{datetime.now():%Y-%m-%d}.{fmt}"
                self._send(200, store.render(rows, fmt).encode(), f"{ctype}; charset=utf-8",
                           {"Content-Disposition": f'attachment; filename="{name}"'})
            else:
                self._json({"error": "not found"}, 404)
        except ValueError as e:
            self._json({"error": str(e)}, 400)

    def do_POST(self):
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        try:
            body = self._body()
            if path == "/api/accounts":
                text = str(body.get("text", ""))
                bad = []
                for line in text.splitlines():
                    line = line.split("#")[0].strip()
                    if line:
                        try:
                            normalize_account(line)
                        except ValueError:
                            bad.append(line)
                if bad:
                    raise ValueError(f"Not an account: {', '.join(bad[:5])}")
                with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                    f.write(text.rstrip() + "\n")
                self._json({"ok": True, "count": len(read_accounts([], ACCOUNTS_FILE))})
            elif path == "/api/topics":
                lines = [" ".join(l.split()) for l in str(body.get("text", "")).splitlines()]
                with open(TOPICS_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines).strip() + "\n")
                self._json({"ok": True, "count": len(read_list(TOPICS_FILE))})
            elif path == "/api/follow":
                added = follow(str(body.get("account", "")))
                self._json({"ok": True, "added": added})
            elif path == "/api/settings":
                s = clean_settings(body)
                save_settings(s)
                self._json({"ok": True, "settings": s})
            elif path == "/api/cookie":
                value = str(body.get("li_at", "")).strip().strip('"')
                if value and (len(value) < 40 or any(c.isspace() or c in ";=" for c in value)):
                    raise ValueError("That doesn't look like an li_at cookie value.")
                write_env_value("LI_AT", value)
                JOB.session.update(status="unknown", message="")
                self._json({"ok": True})
            elif path == "/api/login":
                ok, message = start_login()
                self._json({"ok": ok, "message": message}, 200 if ok else 409)
            elif path == "/api/run":
                what = body.get("what", "all")
                if what not in ("all", "accounts", "topics"):
                    raise ValueError("what must be all, accounts or topics")
                ok, message = start_scrape(self.db_path, what=what)
                self._json({"ok": ok, "message": message}, 200 if ok else 409)
            elif path == "/api/stop":
                JOB.stop.set()
                JOB.log("Stopping after the current account...")
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)
        except (ValueError, json.JSONDecodeError) as e:
            self._json({"error": str(e)}, 400)

    def status(self) -> dict:
        settings = load_settings()
        posts = store.load(self.db_path)
        return {
            "posts": len(posts),
            "accounts": len(read_list(ACCOUNTS_FILE)),
            "topics": len(read_list(TOPICS_FILE)),
            "scraped_accounts": len(followed_accounts() & {p["account"] for p in posts.values()}),
            "session": {
                "cookie_set": bool(os.environ.get("LI_AT")),
                "profile_saved": os.path.exists(SIGNED_IN_MARKER),
                "can_open_browser": can_open_browser(),
                **JOB.session,
            },
            "settings": settings,
            "next_run_at": next_run_at(settings),
            "job": {k: v for k, v in JOB.snapshot().items() if k != "log"},
        }


def serve(host: str = "127.0.0.1", port: int = 8080, db: str = "data/posts.jsonl"):
    Handler.db_path = db
    if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("POSTSCRAPER_PASSWORD"):
        # Online, the dashboard holds your LinkedIn session: never serve it without a password.
        raise SystemExit("Refusing to listen on a public address without POSTSCRAPER_PASSWORD set.")
    threading.Thread(target=scheduler, args=(db,), daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    where = f"port {port}" if host == "0.0.0.0" else f"http://{host}:{port}"
    print(f"post-scraper dashboard on {where}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
