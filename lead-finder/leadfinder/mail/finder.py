"""Email finder: first name + last name + company domain -> the most likely working address.

1. Build candidate addresses from common patterns (the domain's known pattern first).
2. Ask the company's mail server which candidate exists (SMTP RCPT, nothing is sent).
3. If the server accepts everything (catch-all), fall back to the best-known pattern
   and mark the result as risky.
"""

import re

from . import dns, smtp
from .names import candidates, ascii_slug
from .verify import CATCH_ALL, INVALID, UNKNOWN, VALID
from .website import normalize_domain

NOT_COMPANY_SITES = {"linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
                     "youtube.com", "wikipedia.org", "crunchbase.com", "glassdoor.com",
                     "glassdoor.nl", "indeed.com", "indeed.nl", "kvk.nl", "bloomberg.com",
                     "zoominfo.com", "rocketreach.co", "apollo.io", "dnb.com", "opencorporates.com",
                     "werkzoeken.nl", "nationalevacaturebank.nl", "github.com", "medium.com",
                     "trustpilot.com", "yelp.com", "google.com", "apple.com", "tiktok.com",
                     "companyinfo.nl", "drimble.nl", "northdata.com", "pitchbook.com"}
LEGAL_SUFFIX = re.compile(r"\b(b\.?v\.?|n\.?v\.?|v\.?o\.?f\.?|gmbh|ag|ltd|limited|inc|llc|plc|"
                          r"s\.?a\.?|sarl|bvba|holding|holdings|group|groep|nederland|"
                          r"netherlands|international|co)\b\.?", re.I)
TLDS_BY_COUNTRY = {"nl": [".nl", ".com", ".io", ".eu"], "be": [".be", ".com", ".eu", ".nl"],
                   "de": [".de", ".com", ".io", ".eu"], "uk": [".co.uk", ".com", ".io"],
                   "gb": [".co.uk", ".com", ".io"], "fr": [".fr", ".com", ".io", ".eu"]}


def find_email(first: str, last: str, domain: str, checker: smtp.SMTPChecker | None = None,
               known_pattern: str | None = None, mx_lookup=None,
               max_candidates: int = 10) -> dict:
    domain = normalize_domain(domain)
    out = {"first_name": first, "last_name": last, "domain": domain, "email": None,
           "status": INVALID, "score": 0, "pattern": None, "reason": "", "tested": 0}
    cands = candidates(first, last, known_pattern)[:max_candidates]
    if not cands or not domain:
        out["reason"] = "need a first name and a domain"
        return out
    try:
        hosts = (mx_lookup or dns.mx_hosts)(domain)
    except dns.DNSError as e:
        out.update(status=UNKNOWN, reason=str(e))
        return out
    if not hosts:
        out["reason"] = "domain has no mail server"
        return out

    checker = checker or smtp.SMTPChecker()
    probe = f"{smtp.random_local()}@{domain}"
    addresses = [probe] + [f"{local}@{domain}" for local, _ in cands]
    answers = checker.check(hosts, addresses)
    out["tested"] = len(answers) - 1
    best_local, best_pattern = cands[0]
    best = f"{best_local}@{domain}"

    if answers[probe][0] == smtp.ACCEPTED:
        # Catch-all: every address "exists". Best guess is the known pattern, else the most common one.
        out.update(email=best, status=CATCH_ALL, pattern=best_pattern,
                   score=70 if known_pattern else 45,
                   reason="server accepts every address; pattern-based guess")
        return out
    for (local, pattern), address in zip(cands, addresses[1:]):
        state = answers.get(address, (None,))[0]
        if state == smtp.ACCEPTED:
            out.update(email=address, status=VALID, pattern=pattern, score=95,
                       reason="mailbox confirmed by mail server")
            return out
    states = {a[0] for a in answers.values()}
    if states == {smtp.REJECTED}:
        out["reason"] = f"none of {out['tested']} likely addresses exist"
        return out
    # Couldn't get a clear answer (port 25 blocked, greylisting, blocklisted IP)
    first_error = next((a for a in answers.values() if a[0] == smtp.UNKNOWN), (None, 0, ""))
    out.update(email=best, status=UNKNOWN, pattern=best_pattern, score=35 if known_pattern else 20,
               reason=f"could not verify ({first_error[2] or 'no answer'}); pattern-based guess")
    return out


def _company_core(company: str) -> str:
    return ascii_slug(LEGAL_SUFFIX.sub(" ", company))


def domain_from_search(company: str, location: str = "", provider=None) -> str | None:
    """Ask a search API for the company's website; the first plausible non-directory result wins."""
    if provider is None:
        return None
    from .. import providers
    core = _company_core(company)
    query = f'"{company}" {location}'.strip()
    try:
        results = provider.search_page(query, 0)
    except providers.ProviderError:
        return None
    for r in results:
        domain = normalize_domain(r.get("url", ""))
        root = ".".join(domain.split(".")[-2:])
        if not domain or root in NOT_COMPANY_SITES or domain in NOT_COMPANY_SITES:
            continue
        name = ascii_slug(domain.split(".")[-2] if domain.count(".") else domain)
        title = ascii_slug(r.get("title", ""))
        if core and (core[:5] in name or name in core or core[:6] in title):
            return domain
    return None


def domain_from_guess(company: str, country: str = "", mx_lookup=None) -> str | None:
    """'Acme B.V.' -> first of acme.nl, acme.com, ... that has a mail server."""
    core = _company_core(company)
    if len(core) < 2:
        return None
    words = [ascii_slug(w) for w in LEGAL_SUFFIX.sub(" ", company).split() if ascii_slug(w)]
    stems = [core] + ([words[0]] if len(words) > 1 and len(words[0]) > 3 else [])
    tlds = TLDS_BY_COUNTRY.get(country.lower(), [".com", ".io", ".co", ".net"])
    for stem in stems:
        for tld in tlds:
            try:
                if (mx_lookup or dns.mx_hosts)(stem + tld):
                    return stem + tld
            except dns.DNSError:
                continue
    return None


def company_domain(company: str, location: str = "", country: str = "", provider=None,
                   mx_lookup=None) -> tuple[str | None, str]:
    """(domain, how it was found)."""
    if not company:
        return None, ""
    domain = domain_from_search(company, location, provider)
    if domain:
        return domain, "search"
    domain = domain_from_guess(company, country, mx_lookup)
    return (domain, "guess") if domain else (None, "")
