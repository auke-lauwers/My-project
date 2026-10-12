"""Find emails for many people at once: saved leads or a CSV.

Network work runs in a thread pool, one worker per company domain, so each
mail server sees one polite connection at a time and a pattern confirmed for
the first person at a company is tried first for the next.
The database is only touched from the calling thread.
"""

import csv
import io
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import smtp
from .finder import company_domain, find_email
from .names import split_full_name
from .verify import VALID
from .website import normalize_domain

# Header names we recognise in uploaded CSVs (lower-case, spaces/underscores ignored)
COLUMN_ALIASES = {
    "first_name": ["firstname", "first", "givenname", "voornaam"],
    "last_name": ["lastname", "last", "surname", "familyname", "achternaam"],
    "full_name": ["fullname", "name", "naam", "contact", "contactname"],
    "company": ["company", "companyname", "organization", "organisation", "account",
                "bedrijf", "bedrijfsnaam", "employer"],
    "domain": ["domain", "website", "companydomain", "url", "companywebsite", "web", "site"],
    "location": ["location", "city", "plaats", "stad"],
}


def _key(header: str) -> str:
    return "".join(c for c in header.lower() if c.isalnum())


def map_columns(headers) -> dict[str, str]:
    """{our_field: their_header} for the headers we understand."""
    found = {}
    for field, aliases in COLUMN_ALIASES.items():
        for h in headers:
            k = _key(h)
            if k == _key(field) or k in aliases:
                found.setdefault(field, h)
    return found


def records_from_csv(text: str) -> tuple[list[dict], list[str], dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = reader.fieldnames or []
    cols = map_columns(headers)
    records = []
    for i, row in enumerate(reader):
        r = {field: (row.get(h) or "").strip() for field, h in cols.items()}
        if not r.get("first_name") and r.get("full_name"):
            r["first_name"], r["last_name"] = split_full_name(r["full_name"])
        records.append({"id": i, "row": row, **r})
    return records, headers, cols


def resolve_domains(records, store, provider=None, country="", mx_lookup=None, workers=8):
    """Fill record['domain'] from the company name where it's missing (cached per company)."""
    todo = defaultdict(list)
    for r in records:
        if r.get("domain"):
            r["domain"] = normalize_domain(r["domain"])
            r.setdefault("domain_source", "given")
            continue
        company = (r.get("company") or "").strip()
        if not company:
            continue
        cached = store.company_domain(company) if store else None
        if cached:
            r["domain"], r["domain_source"] = cached
        else:
            todo[company].append(r)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(company_domain, c, rs[0].get("location", ""), country, provider,
                               mx_lookup): c for c, rs in todo.items()}
        for fut in as_completed(futures):
            company = futures[fut]
            try:
                domain, source = fut.result()
            except Exception:  # one bad lookup shouldn't stop the batch
                domain, source = None, ""
            if store:
                store.remember_company_domain(company, domain, source)
            for r in todo[company]:
                r["domain"], r["domain_source"] = domain, source


def find_emails(records, store=None, checker=None, mx_lookup=None, workers=4,
                progress=None):
    """Run the finder for every record that has a name and domain. Yields (record, result)."""
    checker = checker or smtp.SMTPChecker()
    known = store.patterns() if store else {}
    by_domain = defaultdict(list)
    for r in records:
        if r.get("first_name") and r.get("domain"):
            by_domain[r["domain"]].append(r)

    def work(domain, people):
        pattern = known.get(domain)
        out = []
        for r in people:
            found = find_email(r["first_name"], r.get("last_name", ""), domain, checker,
                               pattern, mx_lookup)
            if found["status"] == VALID:
                pattern = found["pattern"]
            out.append((r, found))
        return out

    done = 0
    total = sum(len(v) for v in by_domain.values())
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(work, d, p) for d, p in by_domain.items()]):
            for r, found in fut.result():
                if store and found["status"] == VALID and found["pattern"]:
                    store.learn_pattern(found["domain"], found["pattern"])
                done += 1
                if progress:
                    progress(done, total, r, found)
                yield r, found


def enrich_store(store, provider=None, country="", checker=None, mx_lookup=None,
                 redo=False, workers=4, progress=None) -> dict:
    """Find emails for saved leads. Returns counts by status."""
    rows = store.leads(missing_email=not redo)
    records = [{"id": r["slug"], "first_name": r["first_name"] or "", "last_name": r["last_name"] or "",
                "company": r["company"] or "", "location": r["location"] or "",
                "domain": r["domain"] or ""} for r in rows]
    resolve_domains(records, store, provider, country, mx_lookup)
    counts = defaultdict(int)
    for r in records:
        if not r.get("domain"):
            store.set_email(r["id"], {"status": "no_domain"})
            counts["no_domain"] += 1
    for r, found in find_emails(records, store, checker, mx_lookup, workers, progress):
        store.set_email(r["id"], found, r["domain"], r.get("domain_source", ""))
        counts[found["status"]] += 1
    return dict(counts)


OUTPUT_COLUMNS = ["email", "email_status", "email_score", "email_pattern", "domain", "email_note"]


def enrich_csv(text: str, store=None, provider=None, country="", checker=None,
               mx_lookup=None, workers=4, progress=None) -> tuple[str, dict]:
    """CSV text in, CSV text out with email columns appended. Returns (csv_text, counts)."""
    records, headers, cols = records_from_csv(text)
    if "first_name" not in cols and "full_name" not in cols:
        raise ValueError("CSV needs a first_name (or full name) column")
    if "domain" not in cols and "company" not in cols:
        raise ValueError("CSV needs a domain/website or company column")
    resolve_domains(records, store, provider, country, mx_lookup)
    results = {r["id"]: found for r, found in
               find_emails(records, store, checker, mx_lookup, workers, progress)}
    counts = defaultdict(int)
    out = io.StringIO()
    extra = [c for c in OUTPUT_COLUMNS if c not in headers]
    w = csv.DictWriter(out, fieldnames=list(headers) + extra, extrasaction="ignore")
    w.writeheader()
    for r in records:
        found = results.get(r["id"])
        if found:
            note = found["reason"]
        elif not r.get("domain"):
            note = "company domain not found"
        else:
            note = "no first name"
        status = found["status"] if found else ("no_domain" if not r.get("domain") else "skipped")
        counts[status] += 1
        w.writerow({**r["row"], "email": (found or {}).get("email") or "", "email_status": status,
                    "email_score": (found or {}).get("score", ""),
                    "email_pattern": (found or {}).get("pattern") or "",
                    "domain": r.get("domain") or "", "email_note": note})
    return out.getvalue(), dict(counts)
