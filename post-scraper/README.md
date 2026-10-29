# post-scraper

Collects recent posts from a list of big LinkedIn accounts and ranks the
best performers by engagement. Exports CSV, JSON or a readable Markdown
swipe file.

It drives a real Chromium signed in to **your own LinkedIn account**,
scrolls each account's posts page and reads:

- **text, author and media type** from the rendered page
- **exact reaction, comment and repost counts** from LinkedIn's own API
  responses, which the page loads as it scrolls. The page itself shows
  rounded numbers like "12K", so these are used only as a fallback.
- **post date** decoded from the post ID (LinkedIn IDs contain a timestamp)

## Setup

```bash
cd post-scraper
pip install -r requirements.txt
python -m playwright install chromium
python -m postscraper login     # sign in once; the session stays in .browser-profile/
```

You can skip `login` and paste your `li_at` cookie into `.env` instead (see
`.env.example`). To use a Chrome you already have, set `CHROMIUM_PATH`.

## Use

```bash
python -m postscraper run                       # scrape accounts.txt, rank, write out/top.csv + out/top.md
```

Or in steps:

```bash
python -m postscraper scrape --max-posts 40     # adds to data/posts.jsonl
python -m postscraper scrape --account https://www.linkedin.com/in/someone/
python -m postscraper top --days 90 --limit 50 --out out/top.md --out out/top.csv
python -m postscraper top --sort vs_median --per-account 3   # breakout posts
```

`accounts.txt` comes with some of LinkedIn's largest accounts (Gates, Obama,
Branson, Nadella, Sinek, Adam Grant, Gary Vee, Justin Welsh, Sahil Bloom,
Google, Microsoft…). Add your own as profile URLs, `in/<handle>` or
`company/<slug>`. Pick creators in your niche for posts you can learn from.

Scraping again updates the counts of posts you already have, so you can
re-run weekly and `top` always ranks on the latest numbers.

### How "best performing" is measured

| Column | Meaning |
|---|---|
| `score` | reactions + 2 × comments + 3 × reposts. Comments and reposts take more effort from the reader and spread the post further. |
| `vs_median` | the post's score ÷ that account's median score. `8.5` means 8.5× their normal post. |

`--sort score` (default) ranks by raw reach, which the biggest names will
dominate. `--sort vs_median` ranks posts that beat their author's own
normal, which is usually more useful for spotting hooks and formats that
work. Reposts of other people's posts are excluded unless you pass
`--include-reposts`.

## Be careful with your account

Automated access is against LinkedIn's User Agreement, and LinkedIn does
restrict accounts it flags. The defaults are kept slow on purpose: 8–20 s
between accounts, about 30 posts each, human-like scrolling, one browser.

- Keep runs small, around 20–50 accounts a day. Don't raise the delays'
  floor.
- Use `--show-browser` the first few times so you can see what happens.
- If LinkedIn shows a security check, stop and complete it by hand.
- Consider using a secondary account rather than your main one.
- This only reads public posts. Don't use it to collect personal data about
  people. The export holds post text and public engagement counts only.

## When it breaks

LinkedIn changes its markup often. All selectors live in
`postscraper/parse.py`. If an account logs "no posts found" but has posts,
run with `--show-browser` and check whether the posts still carry a
`data-urn="urn:li:activity:…"` attribute, then adjust `parse_feed_html`.

## Tests

```bash
python -m unittest
```

```
accounts.txt              # accounts to scrape
postscraper/browser.py    # Playwright: login, scrolling, API response capture
postscraper/parse.py      # HTML + API JSON -> Post records
postscraper/rank.py       # scoring and ranking
postscraper/store.py      # data/posts.jsonl, CSV/JSON/Markdown export
postscraper/cli.py        # commands
```
