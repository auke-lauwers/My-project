"""Turn a search result for a LinkedIn profile into a structured lead.

Search engines show LinkedIn profiles with titles like
    "Jane Doe - Head of Marketing - Acme BV | LinkedIn"
    "Jane Doe – Acme BV | LinkedIn"
and snippets that often contain "Location: Amsterdam" or
"Amsterdam, North Holland, Netherlands · Head of Marketing · Acme".
Everything here works from that text alone; no LinkedIn page is fetched.
"""

import re
import urllib.parse

PROFILE_RE = re.compile(r"^https?://([a-z]{2,3}\.)?(www\.)?linkedin\.com/in/([^/?#]+)", re.I)
SEPARATORS = re.compile(r"\s+[-–—|]\s+")
LOCATION_RE = re.compile(r"(?:Location|Locatie|Standort|Lieu)\s*:\s*([^·|\n]+?)(?:\s*·|\s*\||$)", re.I)
TAIL_RE = re.compile(r"\s*[|\-–—]\s*LinkedIn\s*$", re.I)
TRUNCATED = "..."


def profile_slug(url: str) -> str | None:
    """'https://nl.linkedin.com/in/jane-doe-123/?x=1' -> 'jane-doe-123'; None if not a profile."""
    m = PROFILE_RE.match(url.strip())
    if not m:
        return None
    return urllib.parse.unquote(m.group(3)).lower()


def canonical_url(slug: str) -> str:
    return f"https://www.linkedin.com/in/{urllib.parse.quote(slug)}"


def _clean(part: str) -> str:
    return part.strip(" .…").replace("…", "").strip()


def _split_name(full: str) -> tuple[str, str]:
    # Drop credentials and pronouns people put after their name: "Jane Doe, MBA (she/her)"
    full = re.sub(r"\(.*?\)", "", full)
    full = full.split(",")[0].strip()
    words = full.split()
    if not words:
        return "", ""
    if len(words) == 1:
        return words[0], ""
    return words[0], " ".join(words[1:])


def parse_title(title: str) -> dict:
    title = TAIL_RE.sub("", title.strip())
    parts = [_clean(p) for p in SEPARATORS.split(title) if _clean(p)]
    out = {"full_name": "", "headline": "", "company": ""}
    if not parts:
        return out
    out["full_name"] = parts[0]
    if len(parts) == 2:
        # "Name - Company" or "Name - Headline": a long or role-like part is a headline
        second = parts[1]
        if re.search(r"\b(at|bij|@)\b", second, re.I) or len(second.split()) > 4:
            out["headline"] = second
        else:
            out["company"] = second
    elif len(parts) >= 3:
        out["headline"] = parts[1]
        out["company"] = parts[2]
    # "Head of Marketing at Acme" -> split it
    if out["headline"] and not out["company"]:
        m = re.match(r"(.+?)\s+(?:at|bij|@)\s+(.+)", out["headline"], re.I)
        if m:
            out["headline"], out["company"] = m.group(1).strip(), m.group(2).strip()
    return out


def parse_location(snippet: str) -> str:
    m = LOCATION_RE.search(snippet)
    if m:
        return _clean(m.group(1))
    # Snippets often start with "City, Region, Country · ..."
    first = snippet.split("·")[0].strip()
    if "," in first and len(first) < 80 and not re.search(r"\d{3,}|\.\s", first):
        return _clean(first)
    return ""


def parse_result(result: dict) -> dict | None:
    """A search result -> lead dict, or None if it isn't a personal profile."""
    slug = profile_slug(result.get("url", ""))
    if not slug:
        return None
    fields = parse_title(result.get("title", ""))
    first, last = _split_name(fields["full_name"])
    snippet = result.get("snippet", "") or ""
    return {
        "slug": slug,
        "linkedin_url": canonical_url(slug),
        "full_name": fields["full_name"],
        "first_name": first,
        "last_name": last,
        "headline": fields["headline"],
        "company": fields["company"],
        "location": parse_location(snippet),
        "snippet": snippet.strip(),
    }
