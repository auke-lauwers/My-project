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
python -m postscraper serve     # dashboard at http://127.0.0.1:8080
```

Sign in from the dashboard's **LinkedIn session** tab, or on the command line
with `python -m postscraper login`. The session is kept in `.browser-profile/`.

Or paste your `li_at` cookie on that tab, or into `.env` (see
`.env.example`). To use a Chrome you already have, set `CHROMIUM_PATH`.

## Dashboard

```bash
python -m postscraper serve     # then open http://127.0.0.1:8080
```

Everything runs from the browser:

- **Top posts**: the ranked posts as cards, with filters for search, account,
  time range, ranking (most engagement or biggest breakouts) and posts per
  account. Copy a post's text, open it on LinkedIn, or export the current
  view as CSV, Markdown or JSON.
- **Run**: start or stop a scrape and follow the live log. Settings for
  posts per account and wait times, and an optional automatic run every
  day, 3 days or week (it runs while the dashboard is running).
- **Accounts**: edit the account list.
- **LinkedIn session**: open the sign-in window, or paste your `li_at`
  cookie. Shows when the session has expired.

### Put it online (Railway)

This gives you a private link that works from any browser, with nothing to
install. Railway builds it from this repo's `Dockerfile`. It needs a paid
plan, since the app must stay running for its schedule and keep a volume (see
railway.com/pricing). Menu names below may have shifted since this was written.
If a step doesn't match, Railway's docs on monorepos (root directory) and
volumes cover it.

1. Sign up at railway.com with your GitHub account.
2. **New Project → Deploy from GitHub repo**, pick this repository.
3. Open the new service's **Settings**:
   - **Source → Root Directory**: `post-scraper`
   - **Source → Branch**: the branch this code is on
     (`claude/vibrant-albattani-dp7y2v` until it's merged into `main`)
   - **Networking → Generate Domain** to get your link
4. **Variables**: add `POSTSCRAPER_PASSWORD` with a long password of your
   own. The app won't start without it: the dashboard holds your LinkedIn
   session.
5. Add a **volume** to the service (right-click the service on the project
   canvas, or the command palette) with mount path `/data`. This keeps your posts, accounts, settings and cookie across
   redeploys; without it they are wiped every time.
6. Open your link. The browser asks for a username and password: any
   username, and the password from step 4.
7. On the **LinkedIn session** tab, paste your `li_at` cookie (a server has
   no screen for the sign-in window).

Railway redeploys by itself when you push to the branch.

**About your LinkedIn account:** run from a server, the scraper uses your
cookie from a data-center IP address, often in another country. LinkedIn is
quicker to flag that than activity from your home connection, and may sign
you out (paste a fresh cookie) or restrict the account. Use a secondary
account for this, keep runs small, and if you get a security check, stop.

### Any other server

```bash
docker build -t post-scraper .
```

```bash
docker run -d -p 8080:8080 -v post-scraper-data:/data -e POSTSCRAPER_PASSWORD=change-me --name post-scraper post-scraper
```

Put it behind HTTPS (e.g. Caddy or a Cloudflare Tunnel) if it's reachable
from the internet: the password is sent with every request.

## Command line

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
postscraper/server.py     # dashboard API, background runs, schedule
postscraper/static/       # dashboard page
postscraper/runner.py     # one scrape run, shared by CLI and dashboard
postscraper/browser.py    # Playwright: login, scrolling, API response capture
postscraper/parse.py      # HTML + API JSON -> Post records
postscraper/rank.py       # scoring and ranking
postscraper/store.py      # data/posts.jsonl, CSV/JSON/Markdown export
postscraper/cli.py        # commands
```
