"""One scrape run over a list of accounts, shared by the CLI and the dashboard."""

from . import rank, store
from .browser import Scraper, SignedOut


def run_scrape(accounts, db, *, max_posts=30, scrolls=10, delay=(8, 20), headless=True,
               li_at="", log=print, progress=None, stop=None) -> dict:
    """Scrape each account into db. Raises browser.SignedOut if the session is gone.

    log(str) gets one line per account; progress(done, total) is called after
    each; setting the stop event ends the run after the current account.
    """
    posts = store.load(db)
    summary = {"accounts": 0, "added": 0, "updated": 0, "errors": 0, "stopped": False}
    total = len(accounts)
    log(f"Scraping {total} accounts, up to {max_posts} posts each")
    with Scraper(headless=headless, li_at=li_at, scrolls=scrolls, delay=delay) as scraper:
        for i, account in enumerate(accounts, 1):
            if stop is not None and stop.is_set():
                summary["stopped"] = True
                log("Stopped.")
                break
            prefix = f"[{i}/{total}] {account}:"
            try:
                found = scraper.scrape(account, max_posts)
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
                store.save(db, posts)  # after every account, so a crash loses nothing
                summary["added"] += added
                summary["updated"] += updated
                best = max(rank.score(p.to_dict()) for p in found)
                log(f"{prefix} {len(found)} posts ({added} new, {updated} updated), best {best:,} pts")
            elif found is not None:
                log(f"{prefix} no posts found")
            summary["accounts"] = i
            if progress:
                progress(i, total)
            if i < total and not (stop is not None and stop.is_set()):
                scraper.pause(stop)
    log(f"{len(posts)} posts stored in {db}")
    return summary
