"""SQLite storage: one row per profile, de-duplicated across runs.

Also keeps a suppression list so people who ask to be removed never come back
in a later search (GDPR Art. 17/21).
"""

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

FIELDS = ["linkedin_url", "full_name", "first_name", "last_name", "headline",
          "company", "location", "search_title", "search_location", "query",
          "provider", "status", "first_seen", "last_seen"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    slug TEXT PRIMARY KEY,
    linkedin_url TEXT NOT NULL,
    full_name TEXT, first_name TEXT, last_name TEXT,
    headline TEXT, company TEXT, location TEXT, snippet TEXT,
    search_title TEXT, search_location TEXT, query TEXT, provider TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppressed (
    slug_hash TEXT PRIMARY KEY,
    added TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    query TEXT NOT NULL, provider TEXT NOT NULL, ran_at TEXT NOT NULL,
    results INTEGER NOT NULL, new_leads INTEGER NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(slug: str) -> str:
    # Only a hash is kept for removed people, so the list holds no personal data itself
    return hashlib.sha256(slug.lower().encode()).hexdigest()


class Store:
    def __init__(self, path: str = "leads.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def is_suppressed(self, slug: str) -> bool:
        return self.db.execute("SELECT 1 FROM suppressed WHERE slug_hash=?",
                               (_hash(slug),)).fetchone() is not None

    def ran_before(self, query: str, provider: str) -> bool:
        return self.db.execute("SELECT 1 FROM runs WHERE query=? AND provider=?",
                               (query, provider)).fetchone() is not None

    def log_run(self, query: str, provider: str, results: int, new_leads: int):
        self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?)",
                        (query, provider, _now(), results, new_leads))
        self.db.commit()

    def upsert(self, lead: dict, context: dict) -> str:
        """Insert or refresh a lead. Returns 'new', 'updated' or 'suppressed'."""
        if self.is_suppressed(lead["slug"]):
            return "suppressed"
        now = _now()
        existing = self.db.execute("SELECT 1 FROM leads WHERE slug=?", (lead["slug"],)).fetchone()
        if existing:
            # Keep the original search context; only fill in fields that were empty
            self.db.execute("""
                UPDATE leads SET
                    full_name = COALESCE(NULLIF(full_name,''), ?),
                    first_name = COALESCE(NULLIF(first_name,''), ?),
                    last_name = COALESCE(NULLIF(last_name,''), ?),
                    headline = COALESCE(NULLIF(headline,''), ?),
                    company = COALESCE(NULLIF(company,''), ?),
                    location = COALESCE(NULLIF(location,''), ?),
                    last_seen = ?
                WHERE slug = ?""",
                (lead["full_name"], lead["first_name"], lead["last_name"], lead["headline"],
                 lead["company"], lead["location"], now, lead["slug"]))
            self.db.commit()
            return "updated"
        self.db.execute("""
            INSERT INTO leads (slug, linkedin_url, full_name, first_name, last_name,
                headline, company, location, snippet, search_title, search_location,
                query, provider, first_seen, last_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (lead["slug"], lead["linkedin_url"], lead["full_name"], lead["first_name"],
             lead["last_name"], lead["headline"], lead["company"], lead["location"],
             lead["snippet"], context.get("title", ""), context.get("location", ""),
             context.get("query", ""), context.get("provider", ""), now, now))
        self.db.commit()
        return "new"

    def leads(self, status: str | None = None, contains: str | None = None):
        sql, args = "SELECT * FROM leads WHERE 1=1", []
        if status:
            sql += " AND status=?"
            args.append(status)
        if contains:
            sql += " AND (headline LIKE ? OR company LIKE ? OR location LIKE ? OR full_name LIKE ?)"
            args += [f"%{contains}%"] * 4
        return self.db.execute(sql + " ORDER BY first_seen", args).fetchall()

    def set_status(self, slug: str, status: str) -> bool:
        cur = self.db.execute("UPDATE leads SET status=? WHERE slug=?", (status, slug.lower()))
        self.db.commit()
        return cur.rowcount > 0

    def forget(self, slug: str) -> bool:
        """Delete everything about a person and block them from future searches."""
        slug = slug.lower()
        cur = self.db.execute("DELETE FROM leads WHERE slug=?", (slug,))
        self.db.execute("INSERT OR IGNORE INTO suppressed VALUES (?,?)", (_hash(slug), _now()))
        self.db.commit()
        return cur.rowcount > 0

    def stats(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchone()[0]
        return {
            "leads": q("SELECT COUNT(*) FROM leads"),
            "by_status": dict(self.db.execute(
                "SELECT status, COUNT(*) FROM leads GROUP BY status").fetchall()),
            "queries_run": q("SELECT COUNT(*) FROM runs"),
            "suppressed": q("SELECT COUNT(*) FROM suppressed"),
        }

    def export(self, path: str, rows) -> int:
        rows = list(rows)
        if path.endswith(".json"):
            with open(path, "w", encoding="utf-8") as f:
                json.dump([{k: r[k] for k in FIELDS} for r in rows], f, indent=2, ensure_ascii=False)
        else:
            # utf-8-sig so Excel shows accented names correctly
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(FIELDS)
                for r in rows:
                    w.writerow([r[k] for k in FIELDS])
        return len(rows)
