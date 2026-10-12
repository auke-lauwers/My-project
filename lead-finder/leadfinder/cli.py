"""lead-finder command line.

    python -m leadfinder search --title "Head of Marketing" --title CMO \
        --location Amsterdam --location Rotterdam --limit 100
    python -m leadfinder enrich                      # find emails for saved leads
    python -m leadfinder find-email "Jane Doe" acme.com
    python -m leadfinder serve                       # web dashboard
    python -m leadfinder export leads.csv
"""

import argparse
import os
import sys

from . import providers
from .parse import parse_result, profile_slug
from .query import expand_queries
from .store import Store


def load_dotenv(path: str = ".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _read_list(values, file):
    items = list(values or [])
    if file:
        with open(file, encoding="utf-8") as f:
            items += [l.strip() for l in f if l.strip() and not l.startswith("#")]
    return items


def cmd_search(args, store: Store) -> int:
    titles = _read_list(args.title, args.titles_file)
    locations = _read_list(args.location, args.locations_file)
    if not titles and not locations and not args.keyword:
        print("Give at least one --title, --location or --keyword.", file=sys.stderr)
        return 2
    provider = providers.get_provider(args.provider)
    queries = list(expand_queries(titles, locations, args.keyword or [], args.exclude or []))
    print(f"{len(queries)} queries via {provider.name}, up to {args.limit} results each\n")

    total_new = 0
    for i, q in enumerate(queries, 1):
        if not args.rerun and store.ran_before(q["query"], provider.name):
            print(f"[{i}/{len(queries)}] skip (already run): {q['query']}")
            continue
        if args.dry_run:
            print(f"[{i}/{len(queries)}] {q['query']}")
            continue
        counts = {"new": 0, "updated": 0, "suppressed": 0, "skipped": 0}
        seen = 0
        try:
            for result in providers.search(provider, q["query"], args.limit, args.country, args.delay):
                seen += 1
                lead = parse_result(result)
                if not lead:
                    counts["skipped"] += 1
                    continue
                counts[store.upsert(lead, {**q, "provider": provider.name})] += 1
        except providers.ProviderError as e:
            print(f"[{i}/{len(queries)}] error: {e}", file=sys.stderr)
            if "Set " in str(e) or "HTTP 401" in str(e) or "HTTP 403" in str(e):
                return 1
            continue
        store.log_run(q["query"], provider.name, seen, counts["new"])
        total_new += counts["new"]
        print(f"[{i}/{len(queries)}] {counts['new']:>3} new, {counts['updated']:>3} seen before"
              f"  ← {q['query']}")
    if not args.dry_run:
        print(f"\nDone: {total_new} new leads. Total in database: {store.stats()['leads']}")
    return 0


def cmd_export(args, store: Store) -> int:
    n = store.export(args.path, store.leads(args.status, args.contains))
    print(f"Wrote {n} leads to {args.path}")
    return 0


def cmd_list(args, store: Store) -> int:
    rows = store.leads(args.status, args.contains)
    for r in rows[: args.limit]:
        bits = [r["full_name"] or r["slug"], r["headline"], r["company"], r["location"]]
        print(" | ".join(b for b in bits if b), f"\n    {r['linkedin_url']}  [{r['status']}]")
    print(f"\n{len(rows)} leads" + (f" (showing {args.limit})" if len(rows) > args.limit else ""))
    return 0


def _slug_arg(value: str) -> str:
    return profile_slug(value) or value.strip("/").lower()


def cmd_status(args, store: Store) -> int:
    ok = store.set_status(_slug_arg(args.profile), args.status)
    print("Updated." if ok else "No lead with that profile.")
    return 0 if ok else 1


def cmd_forget(args, store: Store) -> int:
    existed = store.forget(_slug_arg(args.profile))
    print(("Deleted and " if existed else "Not in database; ") + "blocked from future searches.")
    return 0


def _optional_provider(name: str):
    from .server import optional_provider
    os.environ.setdefault("LEADFINDER_PROVIDER", name)
    return optional_provider()


def _print_progress(done, total, record, found):
    name = f"{record.get('first_name', '')} {record.get('last_name', '')}".strip()
    print(f"[{done}/{total}] {name:<28} {found.get('email') or '-':<40} {found['status']}")


def cmd_find_email(args, store: Store) -> int:
    from .mail import finder
    from .mail.names import split_full_name
    from .mail.website import normalize_domain
    first, last = split_full_name(args.name)
    domain = normalize_domain(args.domain) if "." in args.domain else None
    if not domain:
        cached = store.company_domain(args.domain)
        domain, source = cached or finder.company_domain(
            args.domain, country=args.country, provider=_optional_provider(args.provider))
        if not cached:
            store.remember_company_domain(args.domain, domain, source)
        if not domain:
            print(f"Couldn't find a website for {args.domain!r}; pass the domain instead.")
            return 1
        print(f"Company domain: {domain} ({source})")
    found = finder.find_email(first, last, domain, known_pattern=store.patterns().get(domain))
    if found["status"] == "valid" and found["pattern"]:
        store.learn_pattern(domain, found["pattern"])
    print(f"{found['email'] or 'not found'}  [{found['status']}, {found['score']}%]  {found['reason']}")
    return 0 if found["email"] else 1


def cmd_verify(args, store: Store) -> int:
    from .mail.verify import verify
    emails = list(args.emails)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            emails += [l.strip().split(",")[0] for l in f if "@" in l]
    for e in emails:
        r = verify(e)
        flags = [k for k in ("role", "free") if r.get(k)]
        print(f"{r['email']:<45} {r['status']:<10} {r['score']:>3}  {r['reason']}"
              + (f" ({', '.join(flags)})" if flags else ""))
    return 0


def cmd_domain(args, store: Store) -> int:
    from .mail.website import search_domain
    r = search_domain(args.domain, max_pages=args.pages)
    for m in r["emails"]:
        print(f"{m['email']:<45} {m['type']:<9} {m['sources'][0]}")
    pattern = store.patterns().get(r["domain"]) or r["pattern"]
    print(f"\n{len(r['emails'])} addresses from {r['pages_checked']} pages"
          + (f"; pattern {pattern}@{r['domain']}" if pattern else ""))
    return 0


def cmd_enrich(args, store: Store) -> int:
    from .mail.enrich import enrich_store
    counts = enrich_store(store, _optional_provider(args.provider), args.country,
                          redo=args.redo, workers=args.workers, progress=_print_progress)
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) if counts
          else "Every lead already has an email result (use --redo to check again).")
    return 0


def cmd_bulk(args, store: Store) -> int:
    from .mail.enrich import enrich_csv
    with open(args.input, encoding="utf-8-sig") as f:
        text = f.read()
    try:
        out, counts = enrich_csv(text, store, _optional_provider(args.provider), args.country,
                                 workers=args.workers, progress=_print_progress)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        f.write(out)
    print(f"\nWrote {args.output}: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 0


def cmd_serve(args, store: Store) -> int:
    from .server import serve
    store.close()
    serve(args.db, args.host, args.port, args.country)
    return 0


def cmd_stats(args, store: Store) -> int:
    s = store.stats()
    print(f"Leads: {s['leads']}")
    for status, n in sorted(s["by_status"].items()):
        print(f"  {status}: {n}")
    print(f"Queries run: {s['queries_run']}\nSuppressed: {s['suppressed']}")
    if s["emails"]:
        print("Emails: " + ", ".join(f"{k} {v}" for k, v in sorted(s["emails"].items())))
    print(f"Company email patterns learned: {s['patterns_learned']}")
    return 0


def main(argv=None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(prog="leadfinder",
                                description="Find public LinkedIn profiles via search-engine APIs.")
    p.add_argument("--db", default=os.environ.get("LEADFINDER_DB", "leads.db"))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="run searches and save leads")
    s.add_argument("--title", action="append", help="job title, repeatable")
    s.add_argument("--titles-file", help="file with one job title per line")
    s.add_argument("--location", action="append", help="city/region/country, repeatable")
    s.add_argument("--locations-file", help="file with one location per line")
    s.add_argument("--keyword", action="append", help="extra term every result must mention, repeatable")
    s.add_argument("--exclude", action="append", help="term to exclude, e.g. recruiter, repeatable")
    s.add_argument("--provider", default=os.environ.get("LEADFINDER_PROVIDER", "serper"),
                   choices=sorted(providers.PROVIDERS))
    s.add_argument("--country", default="", help="two-letter country code for local results, e.g. nl")
    s.add_argument("--limit", type=int, default=100, help="max results per query (default 100)")
    s.add_argument("--delay", type=float, default=1.0, help="seconds between API calls")
    s.add_argument("--rerun", action="store_true", help="run queries even if they ran before")
    s.add_argument("--dry-run", action="store_true", help="print the queries without running them")
    s.set_defaults(fn=cmd_search)

    e = sub.add_parser("export", help="write leads to .csv or .json")
    e.add_argument("path")
    e.add_argument("--status")
    e.add_argument("--contains", help="only leads whose name/headline/company/location contains this")
    e.set_defaults(fn=cmd_export)

    l = sub.add_parser("list", help="show leads")
    l.add_argument("--status")
    l.add_argument("--contains")
    l.add_argument("--limit", type=int, default=50)
    l.set_defaults(fn=cmd_list)

    st = sub.add_parser("status", help="set a lead's status (new, contacted, replied, ...)")
    st.add_argument("profile", help="LinkedIn URL or profile slug")
    st.add_argument("status")
    st.set_defaults(fn=cmd_status)

    f = sub.add_parser("forget", help="delete a person and block them from future searches")
    f.add_argument("profile", help="LinkedIn URL or profile slug")
    f.set_defaults(fn=cmd_forget)

    sub.add_parser("stats", help="database summary").set_defaults(fn=cmd_stats)

    default_provider = os.environ.get("LEADFINDER_PROVIDER", "serper")

    fe = sub.add_parser("find-email", help='find one person\'s email: find-email "Jane Doe" acme.com')
    fe.add_argument("name", help="full name")
    fe.add_argument("domain", help="company domain, or company name to look it up")
    fe.add_argument("--country", default="", help="helps guess the domain from a company name")
    fe.add_argument("--provider", default=default_provider, choices=sorted(providers.PROVIDERS))
    fe.set_defaults(fn=cmd_find_email)

    v = sub.add_parser("verify", help="check whether email addresses exist")
    v.add_argument("emails", nargs="*")
    v.add_argument("--file", help="file with one address per line (first CSV column)")
    v.set_defaults(fn=cmd_verify)

    d = sub.add_parser("domain", help="list addresses published on a company's website")
    d.add_argument("domain")
    d.add_argument("--pages", type=int, default=12, help="max pages to visit")
    d.set_defaults(fn=cmd_domain)

    en = sub.add_parser("enrich", help="find emails for saved leads")
    en.add_argument("--country", default="")
    en.add_argument("--provider", default=default_provider, choices=sorted(providers.PROVIDERS))
    en.add_argument("--redo", action="store_true", help="also re-check leads that already have a result")
    en.add_argument("--workers", type=int, default=4, help="companies checked in parallel")
    en.set_defaults(fn=cmd_enrich)

    b = sub.add_parser("bulk", help="add emails to a CSV of names + domains/companies")
    b.add_argument("input")
    b.add_argument("output")
    b.add_argument("--country", default="")
    b.add_argument("--provider", default=default_provider, choices=sorted(providers.PROVIDERS))
    b.add_argument("--workers", type=int, default=4)
    b.set_defaults(fn=cmd_bulk)

    sv = sub.add_parser("serve", help="open the web dashboard")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8080)
    sv.add_argument("--country", default="")
    sv.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    store = Store(args.db)
    try:
        return args.fn(args, store)
    except providers.ProviderError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
