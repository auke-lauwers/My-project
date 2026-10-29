"""One scrape run over accounts and topic searches, shared by the CLI and the dashboard."""

from . import rank, store
from .browser import Scraper, SignedOut


def run_scrape(accounts, db, *, topics=(), max_posts=30, topic_posts=50, date_posted="past-month",
               scrolls=10, delay=(8, 20), headless=True, li_at="", log=print, progress=None,
               stop=None) -> dict:
    """Scrape each account, then search each topic, into db.

    Raises browser.SignedOut if the session is gone. log(str) gets one line
    per account or topic; progress(done, total) is called after each; setting
    the stop event ends the run after the current one.
    """
    posts = store.load(db)
    summary = {"accounts": 0, "topics": 0, "added": 0, "updated": 0, "errors": 0, "stopped": False}
    jobs = [("account", a) for a in accounts] + [("topic", t) for t in topics]
    total = len(jobs)
    parts = []
    if accounts:
        parts.append(f"{len(accounts)} accounts (up to {max_posts} posts each)")
    if topics:
        parts.append(f"{len(topics)} topics (up to {topic_posts} posts each)")
    log("Scraping " + " and ".join(parts))
    with Scraper(headless=headless, li_at=li_at, scrolls=scrolls, delay=delay) as scraper:
        for i, (kind, target) in enumerate(jobs, 1):
            if stop is not None and stop.is_set():
                summary["stopped"] = True
                log("Stopped.")
                break
            prefix = f"[{i}/{total}] {target}:" if kind == "account" else f'[{i}/{total}] topic "{target}":'
            try:
                if kind == "account":
                    found = scraper.scrape(target, max_posts)
                else:
                    # Topic searches scroll further: they're where new creators come from.
                    scraper.scrolls = max(scrolls, 15)
                    found = scraper.search(target, topic_posts, date_posted)
                    scraper.scrolls = scrolls
            except ValueError as e:
                log(f"{prefix} skipped ({e})")
                found = None
            except SignedOut:
                raise
            except Exception as e:  # one bad page should not end the run
                log(f"{prefix} error: {e}")
                summary["errors"] += 1
                found = None
            if found:
                added, updated = store.upsert(posts, found)
                store.save(db, posts)  # after every target, so a crash loses nothing
                summary["added"] += added
                summary["updated"] += updated
                best = max(rank.score(p.to_dict()) for p in found)
                extra = ""
                if kind == "topic":
                    extra = f", {len({p.account for p in found})} creators"
                log(f"{prefix} {len(found)} posts ({added} new, {updated} updated{extra}), best {best:,} pts")
            elif found is not None:
                log(f"{prefix} no posts found")
            summary["accounts" if kind == "account" else "topics"] += 1
            if progress:
                progress(i, total)
            if i < total and not (stop is not None and stop.is_set()):
                scraper.pause(stop)
    log(f"{len(posts)} posts stored in {db}")
    return summary
