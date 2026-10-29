"""Drive a real Chromium, signed in as you, through each account's posts page.

The page is scrolled like a person would, the rendered HTML is parsed for
text, and LinkedIn's own Voyager API responses (which the page fetches while
scrolling) are captured for exact engagement counts.
"""

import json
import os
import random
import re
import time

from .parse import counts_from_voyager, merge_counts, parse_feed_html

PROFILE_DIR = ".browser-profile"


def normalize_account(value: str) -> tuple:
    """'https://www.linkedin.com/in/foo/' or 'in/foo' -> ('in/foo', posts URL)."""
    value = value.split("#")[0].strip()
    m = re.search(r"(in|company|school)/([^/?#\s]+)", value)
    if not m:
        value = value.strip("/@ ")
        if not value:
            raise ValueError("empty account")
        kind, slug = "in", value
    else:
        kind, slug = m.group(1), m.group(2)
    account = f"{kind}/{slug}"
    if kind == "in":
        url = f"https://www.linkedin.com/in/{slug}/recent-activity/all/"
    else:
        url = f"https://www.linkedin.com/{kind}/{slug}/posts/?feedView=all&sortBy=recent"
    return account, url


def _sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Playwright is not installed. Run:\n"
            "  pip install -r requirements.txt\n"
            "  python -m playwright install chromium"
        )
    return sync_playwright


def open_context(p, headless: bool, li_at: str = ""):
    ctx = p.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=headless,
        locale="en-US",
        viewport={"width": 1280, "height": 900},
        # Optional: use an existing Chrome/Chromium instead of Playwright's download.
        executable_path=os.environ.get("CHROMIUM_PATH") or None,
    )
    if li_at:
        ctx.add_cookies([{
            "name": "li_at", "value": li_at, "domain": ".linkedin.com",
            "path": "/", "httpOnly": True, "secure": True, "sameSite": "None",
        }])
    return ctx


def login():
    """Open a visible browser so you can sign in; the session is kept on disk."""
    with _sync_playwright()() as p:
        ctx = open_context(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/login")
        print("Sign in in the browser window. Waiting until your feed loads (5 min max)...")
        try:
            page.wait_for_url(re.compile(r"linkedin\.com/(feed|in/)"), timeout=300_000)
            print(f"Signed in. Session saved in {PROFILE_DIR}/")
        finally:
            ctx.close()


def _signed_out(page) -> bool:
    return bool(re.search(r"/(login|authwall|checkpoint|uas/)", page.url))


class Scraper:
    def __init__(self, headless=True, li_at="", scrolls=8, delay=(8, 20)):
        self.headless, self.li_at, self.scrolls, self.delay = headless, li_at, scrolls, delay

    def __enter__(self):
        self._pw = _sync_playwright()().start()
        self.ctx = open_context(self._pw, self.headless, self.li_at)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self._counts = {}
        self.page.on("response", self._on_response)
        return self

    def __exit__(self, *exc):
        self.ctx.close()
        self._pw.stop()

    def _on_response(self, response):
        if "/voyager/api/" not in response.url:
            return
        try:
            self._counts.update(counts_from_voyager(json.loads(response.text())))
        except Exception:
            pass  # not JSON, or the body is gone; HTML counts are the fallback

    def pause(self):
        time.sleep(random.uniform(*self.delay))

    def scrape(self, account_value: str, max_posts=30) -> list:
        account, url = normalize_account(account_value)
        self._counts = {}
        self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if _signed_out(self.page):
            raise SystemExit(
                "LinkedIn wants you to sign in. Run `python -m postscraper login` "
                "(or set LI_AT in .env) and try again."
            )
        try:
            self.page.wait_for_selector("[data-urn*='activity'], [data-id*='activity']", timeout=20_000)
        except Exception:
            return []  # no posts, wrong handle, or the layout changed

        posts = []
        for _ in range(self.scrolls):
            self._expand_see_more()
            posts = parse_feed_html(self.page.content(), account)
            if len(posts) >= max_posts:
                break
            self.page.mouse.wheel(0, random.randint(2500, 4000))
            time.sleep(random.uniform(1.5, 3.5))

        self._expand_see_more()
        posts = parse_feed_html(self.page.content(), account)
        return merge_counts(posts, self._counts)[:max_posts]

    def _expand_see_more(self):
        """Click 'see more' so the full post text is in the DOM."""
        try:
            self.page.evaluate(
                """() => document.querySelectorAll(
                    'button.feed-shared-inline-show-more-text__see-more-less-toggle[aria-expanded="false"]'
                ).forEach(b => b.click())"""
            )
        except Exception:
            pass
