# lead-finder

A self-hosted prospecting tool in the style of Skrapp.io:

| | |
|---|---|
| **Lead search** | Finds public LinkedIn profiles through search engines: name, headline, company, location |
| **Email finder** | Name + company domain (or company name) → the address that actually exists |
| **Email verifier** | Syntax, disposable, mail server, mailbox check, catch-all detection |
| **Domain search** | Every address a company publishes on its own website + its email pattern |
| **Bulk** | Upload a CSV of names + companies, get it back with emails |
| **Dashboard** | All of the above in the browser: `python3 -m leadfinder serve` |

Everything is stored in one local SQLite file, so there are no per-credit fees
apart from the search API. No dependencies: Python 3.10+ only.

It runs Google-style queries such as

```
site:linkedin.com/in "Head of Marketing" "Amsterdam" -"recruiter"
```

through a **search API** and reads the result titles and snippets. It never
logs in to LinkedIn or loads LinkedIn pages, so your LinkedIn account is never at risk.
It also doesn't scrape Google's result pages directly, because Google answers that with
CAPTCHAs and IP blocks after a few dozen requests. A search API is the reliable
way to do thousands of queries.

## Setup

1. Get an API key. **[serper.dev](https://serper.dev)** is the easiest: it gives
   Google results, the first 2,500 searches are free, and after that it's cheap.
   SerpApi, Brave Search and Google Programmable Search also work.
2. `cp .env.example .env` and paste the key in.

## Use

```bash
cd lead-finder

# See which queries it will run (costs nothing)
python3 -m leadfinder search --titles-file examples/titles.txt \
    --locations-file examples/locations.txt --exclude recruiter --dry-run

# Run them: 5 titles x 5 cities = 25 queries, up to 100 results each
python3 -m leadfinder search --titles-file examples/titles.txt \
    --locations-file examples/locations.txt --exclude recruiter --country nl

python3 -m leadfinder stats
python3 -m leadfinder list --contains SaaS
python3 -m leadfinder export leads.csv
python3 -m leadfinder export saas.csv --contains SaaS --status new
```

Other options for `search`:

| Flag | What it does |
|---|---|
| `--title`, `--location` | Repeatable; every title is combined with every location |
| `--keyword` | A term every result must mention (e.g. `--keyword SaaS`) |
| `--exclude` | Leave out results that mention this term (e.g. `recruiter`, `student`) |
| `--provider` | `serper` (default), `serpapi`, `brave`, `google` |
| `--country` | Local results for this two-letter country code, e.g. `nl` |
| `--limit` | Max results per query (default 100, the most search APIs give) |
| `--rerun` | Run queries again; normally a query that already ran is skipped so you don't pay twice |

### Getting more leads

Each query tops out at about 100 results. The way to get thousands is **many
narrow queries**: more title variants (`CMO`, `Chief Marketing Officer`,
`Marketing Director`, `Head of Marketing`), more cities, and keywords for the
industry. Running the same list through a second provider (`--provider brave`)
also helps, because Brave has its own index and finds different people.

### Tracking

```bash
python3 -m leadfinder status https://www.linkedin.com/in/jane-doe contacted
python3 -m leadfinder forget https://www.linkedin.com/in/jane-doe
```

`forget` deletes the person and blocks them from coming back in later
searches. Only a hash of their profile slug is kept, so the block list holds no personal data.

## Finding emails

```bash
python3 -m leadfinder find-email "Jane de Vries" acme.com   # or a company name: "Acme BV"
python3 -m leadfinder verify jane.devries@acme.com info@acme.com
python3 -m leadfinder domain acme.com                        # addresses on their website
python3 -m leadfinder enrich --country nl                    # every saved lead without an email
python3 -m leadfinder bulk prospects.csv prospects-with-emails.csv
python3 -m leadfinder serve                                  # dashboard on http://127.0.0.1:8080
```

### How the finder works

1. **Company → domain.** With a search API key it searches for the company's website,
   skipping LinkedIn, KvK, Glassdoor and other directories. Without a key it tries
   `company.nl`, `company.com` and so on (`--country` picks the order), keeping the first one
   that receives mail. Each company is looked up once and then cached.
2. **Candidates.** `jane.devries`, `jane`, `jdevries`, `janedevries`, `j.devries` and others,
   14 patterns in all. Accents are stripped and Dutch/German surname particles are
   handled, so `jane.vries` is tried as well.
3. **Mailbox check.** It connects to the company's mail server and asks, address by
   address, whether it would accept mail (`RCPT TO`). **No email is ever sent.** It
   first tries a random address: if the server accepts that too, it accepts everything (catch-all).
4. **Learning.** Once an address is confirmed at a company, that pattern is tried first for
   everyone else there. On a list with many people per company, most lookups then need only one check.

| Status | Meaning | Send? |
|---|---|---|
| `valid` | The mail server confirmed the mailbox | Yes |
| `catch_all` | The server accepts any address; this is the most likely pattern | Carefully, in small batches |
| `unknown` | No clear answer (port 25 blocked, greylisting, our IP blocked) | Run it again later or from another server |
| `invalid` | Mailbox rejected, or none of the patterns exist | No |

### Port 25: where to run it

The mailbox check needs **outbound port 25**, which almost every home ISP and most
clouds block (AWS, Google Cloud and Azure by default; DigitalOcean too). On a
laptop, every result will come back `unknown`. Run it on a small VPS that allows port 25,
such as Hetzner (ask support to unblock it after your first invoice) or OVH. Check the provider's current policy, or use a
dedicated server. Then:

- Point a domain you **don't** send campaigns from at the server (e.g. `verify.yourbrand-mail.com`),
  set a PTR (reverse DNS) record to it, and set `SMTP_HELO` / `SMTP_FROM` in `.env`.
  Mail servers trust a properly named server more.
- Don't verify from your sending domain's IP. Verifying from a new IP at high volume
  can get that IP listed on Spamhaus, and Microsoft 365 and some others start answering
  `unknown` when they see too many checks.
- Keep `--workers` low (the default is 4). Each company's mail server only gets one
  connection at a time.

To use the dashboard on the server, set `LEADFINDER_PASSWORD` and run
`python3 -m leadfinder serve --host 0.0.0.0`, ideally behind HTTPS (Caddy or nginx).

### Bulk CSV format

Headers are matched loosely: `First Name`/`voornaam`, `Last Name`/`achternaam`, or a single
`Name`/`Full Name` column, plus `Domain`/`Website` or `Company`/`Bedrijf`. The output is your
file with `email`, `email_status`, `email_score`, `email_pattern`, `domain` and `email_note` added.

## What you get, and what you don't

- **From lead search:** name, headline, company, location (when the snippet
  shows it), LinkedIn URL, plus the query that found them and when.
- **From the email finder:** a work email with a status and confidence score. There are
  no phone numbers.
- Headline, company and location are parsed from search snippets. They can be
  cut off or out of date, so check them before personalising anything.
- Compared with Skrapp, there is no Chrome extension that reads LinkedIn pages. That
  would break LinkedIn's terms and put your account at risk.

## GDPR (you're in the EU, so this applies)

The names and profile URLs you collect are personal data. Cold outreach to business contacts is
usually justified on *legitimate interest*, but that comes with obligations:

- Record your legitimate-interest assessment, and only collect people who match your offer.
- Tell each person where you got their data, and that they can object, no later than
  your first message to them (Art. 14). One line in the first email is enough.
- Honour opt-outs immediately: `forget` handles that.
- Domain search only collects addresses a company published itself, and respects robots.txt.
- Don't keep leads forever. Delete the ones you never contacted after a set period.
- For cold email, also check the email-marketing rules of the country you're sending to
  (the Netherlands' Telecommunicatiewet, for example).

This tool collects only what search engines already show publicly, and records where each lead came from.
That helps with the points above, but it doesn't replace them.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
