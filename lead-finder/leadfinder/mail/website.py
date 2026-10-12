"""Domain search: collect the email addresses a company publishes on its own website.

Visits the homepage, the usual contact/about/team/imprint pages and internal
links that look like them (at most `max_pages`), and respects robots.txt.
"""

import html
import re
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

from .names import guess_shape
from .verify import ROLE

USER_AGENT = "Mozilla/5.0 (compatible; lead-finder/0.1; domain search)"
MAX_BYTES = 2_000_000
COMMON_PATHS = ["", "contact", "contact-us", "contact.html", "about", "about-us", "team",
                "our-team", "people", "impressum", "imprint", "over-ons", "over", "ons-team",
                "medewerkers", "kontakt", "legal", "privacy"]
LINK_HINTS = re.compile(r"contact|about|team|people|staff|impressum|imprint|over-ons|"
                        r"medewerkers|kontakt|leadership|management|wie-zijn", re.I)
EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,24}", re.I)
OBFUSCATED = [(re.compile(r"\s*[\[\(\{]\s*at\s*[\]\)\}]\s*", re.I), "@"),
              (re.compile(r"\s*[\[\(\{]\s*dot\s*[\]\)\}]\s*", re.I), ".")]
HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)""", re.I)
ASSET = re.compile(r"\.(png|jpe?g|gif|svg|webp|css|js)$", re.I)


def normalize_domain(value: str) -> str:
    """'https://www.Acme.com/about' -> 'acme.com'."""
    value = value.strip().lower()
    if "@" in value:
        value = value.rsplit("@", 1)[1]
    if "//" not in value:
        value = "//" + value
    host = urllib.parse.urlsplit(value).hostname or ""
    return host[4:] if host.startswith("www.") else host


def fetch(url: str, timeout: float = 15.0) -> tuple[str, str]:
    """(final_url, html) or ('', '') if it isn't an HTML page we can read."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if "html" not in resp.headers.get("Content-Type", "html"):
                return "", ""
            raw = resp.read(MAX_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.geturl(), raw.decode(charset, errors="replace")
    except (OSError, ValueError):
        return "", ""


def extract_emails(page: str, domain: str) -> set[str]:
    text = html.unescape(urllib.parse.unquote(page))
    for pattern, repl in OBFUSCATED:
        text = pattern.sub(repl, text)
    found = set()
    for m in EMAIL_RE.findall(text):
        email = m.lower().strip(".")
        host = email.rsplit("@", 1)[1]
        if ASSET.search(email) or not (host == domain or host.endswith("." + domain)):
            continue
        found.add(email)
    return found


def internal_links(page: str, base: str, domain: str) -> list[str]:
    links = []
    for href in HREF_RE.findall(page):
        url = urllib.parse.urljoin(base, html.unescape(href))
        host = normalize_domain(url)
        if (host == domain or host.endswith("." + domain)) and LINK_HINTS.search(url) \
                and not ASSET.search(url) and url.startswith("http"):
            links.append(url.split("#")[0])
    return links


def search_domain(domain: str, max_pages: int = 12, fetcher=fetch) -> dict:
    domain = normalize_domain(domain)
    root = f"https://{domain}/"
    robots = urllib.robotparser.RobotFileParser(root + "robots.txt")
    try:
        robots.read()
    except (OSError, ValueError):
        robots.allow_all = True

    queue = [urllib.parse.urljoin(root, p) for p in COMMON_PATHS]
    visited, emails = set(), {}
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited or not robots.can_fetch(USER_AGENT, url):
            continue
        visited.add(url)
        final, page = fetcher(url)
        if not page:
            continue
        for email in extract_emails(page, domain):
            emails.setdefault(email, []).append(final)
        # Links the site itself points to beat our guessed paths, so they go first
        found = [l for l in dict.fromkeys(internal_links(page, final, domain)) if l not in visited]
        queue = found + [u for u in queue if u not in found]

    rows = []
    for email, sources in sorted(emails.items()):
        local = email.split("@")[0]
        rows.append({"email": email, "type": "role" if local in ROLE else "personal",
                     "sources": sorted(set(sources))})
    shapes = [s for s in (guess_shape(r["email"].split("@")[0]) for r in rows
                          if r["type"] == "personal") if s]
    pattern = max(set(shapes), key=shapes.count) if shapes else None
    return {"domain": domain, "emails": rows, "pattern": pattern, "pages_checked": len(visited)}
