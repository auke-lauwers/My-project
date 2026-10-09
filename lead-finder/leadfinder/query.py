"""Build search-engine queries that target public LinkedIn profile pages."""

from itertools import product


def _quote(term: str) -> str:
    term = term.strip().replace('"', "")
    return f'"{term}"' if term else ""


def build_query(title: str = "", location: str = "", keywords=(), exclude=(),
                site: str = "linkedin.com/in") -> str:
    """One query, e.g. site:linkedin.com/in "Head of Marketing" "Amsterdam" -recruiter."""
    parts = [f"site:{site}"]
    parts += [q for q in (_quote(title), _quote(location)) if q]
    parts += [q for q in (_quote(k) for k in keywords) if q]
    parts += [f"-{_quote(x)}" for x in exclude if x.strip()]
    return " ".join(parts)


def expand_queries(titles=(), locations=(), keywords=(), exclude=(),
                   site: str = "linkedin.com/in"):
    """Every title x location combination as its own query.

    Search APIs cap results per query (about 100), so many narrow queries
    find far more people than one broad one.
    """
    titles = [t for t in titles if t.strip()] or [""]
    locations = [l for l in locations if l.strip()] or [""]
    for title, location in product(titles, locations):
        yield {
            "title": title,
            "location": location,
            "query": build_query(title, location, keywords, exclude, site),
        }
