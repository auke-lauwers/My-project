# lead-finder

Finds public LinkedIn profiles through search engines and saves them as
leads: name, headline, company, location and profile URL. Duplicates are
merged and everything can be exported to CSV/JSON for your CRM or sending tool.

It runs Google-style queries such as

```
site:linkedin.com/in "Head of Marketing" "Amsterdam" -"recruiter"
```

through a **search API** and reads the result titles and snippets. It never
logs in to LinkedIn or loads LinkedIn pages, so your LinkedIn account is never at risk.
It also doesn't scrape Google's result pages directly, because Google answers that with
CAPTCHAs and IP blocks after a few dozen requests. A search API is the reliable
way to do thousands of queries.

No dependencies: Python 3.10+ only.

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

## What you get, and what you don't

- **You get:** name, first/last name, headline, company, location (when the snippet
  shows it), LinkedIn URL, plus the query that found them and when.
- **You don't get emails or phone numbers.** Search results don't contain them.
  To get emails, run the exported CSV through an email finder that verifies addresses
  (Hunter, Apollo, Prospeo, Findymail and others take name + company).
- Headline, company and location are parsed from search snippets. They can be
  cut off or out of date, so check them before personalising anything.

## GDPR (you're in the EU, so this applies)

The names and profile URLs you collect are personal data. Cold outreach to business contacts is
usually justified on *legitimate interest*, but that comes with obligations:

- Record your legitimate-interest assessment, and only collect people who match your offer.
- Tell each person where you got their data, and that they can object, no later than
  your first message to them (Art. 14). One line in the first email is enough.
- Honour opt-outs immediately: `forget` handles that.
- Don't keep leads forever. Delete the ones you never contacted after a set period.
- For cold email, also check the email-marketing rules of the country you're sending to
  (the Netherlands' Telecommunicatiewet, for example).

This tool collects only what search engines already show publicly, and records where each lead came from.
That helps with the points above, but it doesn't replace them.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
