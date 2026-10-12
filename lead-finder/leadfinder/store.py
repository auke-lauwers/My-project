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
          "company", "location", "domain", "email", "email_status", "email_score",
          "search_title", "search_location", "query", "provider", "status",
          "first_seen", "last_seen"]

# Added after the first release; created on existing databases by _migrate()
EMAIL_COLUMNS = {"domain": "TEXT", "domain_source": "TEXT", "email": "TEXT",
                 "email_status": "TEXT", "email_score": "INTEGER", "email_pattern": "TEXT",
                 "email_checked": "TEXT"}

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
CREATE TABLE IF NOT EXISTS domain_patterns (
    domain TEXT PRIMARY KEY, pattern TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 1,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_domains (
    company_key TEXT PRIMARY KEY, domain TEXT, source TEXT, updated TEXT NOT NULL
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
        self._migrate()

    def _migrate(self):
        have = {r[1] for r in self.db.execute("PRAGMA table_info(leads)")}
        for col, kind in EMAIL_COLUMNS.items():
            if col not in have:
                self.db.execute(f"ALTER TABLE leads ADD COLUMN {col} {kind}")
        self.db.commit()

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

    def leads(self, status: str | None = None, contains: str | None = None,
              email_status: str | None = None, missing_email: bool = False):
        sql, args = "SELECT * FROM leads WHERE 1=1", []
        if email_status:
            sql += " AND email_status=?"
            args.append(email_status)
        if missing_email:
            sql += " AND email_status IS NULL"
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

    def lead(self, slug: str):
        return self.db.execute("SELECT * FROM leads WHERE slug=?", (slug.lower(),)).fetchone()

    def set_email(self, slug: str, found: dict, domain: str | None = None, domain_source: str = ""):
        self.db.execute("""
            UPDATE leads SET domain=COALESCE(?, domain), domain_source=COALESCE(NULLIF(?,''), domain_source),
                email=?, email_status=?, email_score=?, email_pattern=?, email_checked=?
            WHERE slug=?""",
            (domain, domain_source, found.get("email"), found.get("status"), found.get("score"),
             found.get("pattern"), _now(), slug))
        self.db.commit()

    # Learned per-domain email patterns ("{first}.{last}") from confirmed finds
    def patterns(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT domain, pattern FROM domain_patterns").fetchall())

    def learn_pattern(self, domain: str, pattern: str):
        self.db.execute("""
            INSERT INTO domain_patterns (domain, pattern, updated) VALUES (?,?,?)
            ON CONFLICT(domain) DO UPDATE SET
                confirmed = CASE WHEN pattern=excluded.pattern THEN confirmed+1 ELSE 1 END,
                pattern = excluded.pattern, updated = excluded.updated""",
            (domain, pattern, _now()))
        self.db.commit()

    # company name -> website domain, so each company is looked up once
    def company_domain(self, company: str):
        row = self.db.execute("SELECT domain, source FROM company_domains WHERE company_key=?",
                              (company.strip().lower(),)).fetchone()
        return (row["domain"], row["source"]) if row else None

    def remember_company_domain(self, company: str, domain: str | None, source: str):
        self.db.execute("INSERT OR REPLACE INTO company_domains VALUES (?,?,?,?)",
                        (company.strip().lower(), domain, source, _now()))
        self.db.commit()

    def stats(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchone()[0]
        return {
            "leads": q("SELECT COUNT(*) FROM leads"),
            "by_status": dict(self.db.execute(
                "SELECT status, COUNT(*) FROM leads GROUP BY status").fetchall()),
            "queries_run": q("SELECT COUNT(*) FROM runs"),
            "suppressed": q("SELECT COUNT(*) FROM suppressed"),
            "emails": dict(self.db.execute(
                "SELECT email_status, COUNT(*) FROM leads WHERE email_status IS NOT NULL "
                "GROUP BY email_status").fetchall()),
            "patterns_learned": q("SELECT COUNT(*) FROM domain_patterns"),
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
