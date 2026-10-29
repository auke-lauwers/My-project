"""post-scraper command line.

    python -m postscraper login
    python -m postscraper scrape --accounts accounts.txt --max-posts 30
    python -m postscraper top --days 90 --limit 50 --out out/top.md
    python -m postscraper run            # scrape, then top
    python -m postscraper serve          # web dashboard on http://127.0.0.1:8080
"""

import argparse
import os
import random
import sys

from . import rank, store

DEFAULT_DB = "data/posts.jsonl"


def load_dotenv(path: str = ".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_accounts(values, file) -> list:
    items = list(values or [])
    if file:
        with open(file, encoding="utf-8") as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line:
                    items.append(line)
    return list(dict.fromkeys(items))


def cmd_login(args) -> int:
    from .browser import login
    login()
    return 0


def cmd_scrape(args) -> int:
    from .browser import SignedOut
    from .runner import run_scrape

    file = args.accounts or (None if args.account else "accounts.txt")
    accounts = read_accounts(args.account, file)
    if not accounts:
        print("Give accounts with --account or --accounts FILE.", file=sys.stderr)
        return 2
    if args.shuffle:
        random.shuffle(accounts)

    try:
        run_scrape(
            accounts, args.db,
            max_posts=args.max_posts,
            scrolls=args.scrolls,
            delay=(args.min_delay, args.max_delay),
            headless=not args.show_browser,
            li_at=os.environ.get("LI_AT", ""),
        )
    except SignedOut as e:
        print(f"\n{e}\nRun `python -m postscraper login` or set LI_AT in .env.", file=sys.stderr)
        return 1
    return 0


def cmd_top(args) -> int:
    posts = list(store.load(args.db).values())
    if not posts:
        print(f"No posts in {args.db} yet. Run `python -m postscraper scrape` first.", file=sys.stderr)
        return 1
    rows = rank.top(
        posts,
        n=args.limit,
        per_account=args.per_account,
        days=args.days,
        include_reposts=args.include_reposts,
        min_text=args.min_text,
        sort=args.sort,
    )
    for i, r in enumerate(rows[: args.print], 1):
        snippet = (r.get("text") or "").replace("\n", " ")[:90]
        print(
            f"{i:>3}. {r['score']:>9,} pts  {r['vs_median']:>5}x  "
            f"{(r.get('author') or r['account'])[:22]:<22}  {snippet}"
        )
    for path in args.out or []:
        store.export(rows, path)
        print(f"Wrote {len(rows)} posts to {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="postscraper", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB, help=f"posts file (default {DEFAULT_DB})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="sign in to LinkedIn once in a visible browser")

    def scrape_args(p):
        p.add_argument("--account", action="append", help="profile/company URL, in/<handle> or company/<slug>")
        p.add_argument("--accounts", help="file with one account per line (default accounts.txt)")
        p.add_argument("--max-posts", type=int, default=30, help="posts per account (default 30)")
        p.add_argument("--scrolls", type=int, default=10, help="max page scrolls per account")
        p.add_argument("--min-delay", type=float, default=8, help="min seconds between accounts")
        p.add_argument("--max-delay", type=float, default=20, help="max seconds between accounts")
        p.add_argument("--shuffle", action="store_true", help="visit accounts in random order")
        p.add_argument("--show-browser", action="store_true", help="run with a visible window")

    def top_args(p):
        p.add_argument("--days", type=int, help="only posts from the last N days")
        p.add_argument("--limit", type=int, default=50, help="how many posts to keep (default 50)")
        p.add_argument("--per-account", type=int, help="at most N posts per account")
        p.add_argument("--sort", choices=["score", "vs_median"], default="score",
                       help="score = most engagement; vs_median = biggest outliers vs the account's norm")
        p.add_argument("--min-text", type=int, default=0, help="skip posts with less text than N chars")
        p.add_argument("--include-reposts", action="store_true", help="keep reposts of other people's posts")
        p.add_argument("--print", type=int, default=20, help="rows to print (default 20)")
        p.add_argument("--out", action="append", help="export to .csv, .json or .md (repeatable)")

    scrape_args(sub.add_parser("scrape", help="collect posts from accounts"))
    top_args(sub.add_parser("top", help="rank stored posts and export the best"))
    serve = sub.add_parser("serve", help="web dashboard to run and browse everything")
    serve.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to allow other machines (set POSTSCRAPER_PASSWORD)")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))

    run = sub.add_parser("run", help="scrape, then top")
    scrape_args(run)
    top_args(run)
    return ap


def main(argv=None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    if args.cmd == "login":
        return cmd_login(args)
    if args.cmd == "scrape":
        return cmd_scrape(args)
    if args.cmd == "top":
        return cmd_top(args)
    if args.cmd == "serve":
        from .server import serve
        serve(args.host, args.port, args.db)
        return 0
    code = cmd_scrape(args)
    if code:
        return code
    if not args.out:
        args.out = ["out/top.csv", "out/top.md"]
    return cmd_top(args)
