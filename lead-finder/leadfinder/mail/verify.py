"""Email verification: syntax, disposable/role/free checks, MX, SMTP mailbox check, catch-all."""

import re

from . import dns, smtp

VALID = "valid"            # mailbox confirmed by the server
INVALID = "invalid"        # bad syntax, no mail server, or mailbox rejected
CATCH_ALL = "catch_all"    # server accepts any address, so this one can't be confirmed
UNKNOWN = "unknown"        # server unreachable, greylisted or blocked us

EMAIL_RE = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
                      r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$", re.I)

ROLE = {"info", "contact", "hello", "hi", "sales", "support", "help", "admin", "office",
        "mail", "team", "marketing", "jobs", "careers", "hr", "billing", "finance",
        "accounts", "noreply", "no-reply", "postmaster", "webmaster", "abuse", "press",
        "media", "service", "receptie", "reception", "kantoor", "administratie", "vacatures"}

FREE = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
        "yahoo.com", "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com",
        "gmx.com", "gmx.de", "gmx.net", "web.de", "hotmail.nl", "live.nl", "ziggo.nl",
        "kpnmail.nl", "planet.nl", "home.nl", "xs4all.nl", "zonnet.nl", "yahoo.co.uk",
        "outlook.de", "t-online.de", "orange.fr", "free.fr", "laposte.net", "mail.com",
        "yandex.com", "zoho.com"}

DISPOSABLE = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
              "temp-mail.org", "yopmail.com", "trashmail.com", "sharklasers.com",
              "getnada.com", "dispostable.com", "maildrop.cc", "throwawaymail.com",
              "fakeinbox.com", "mintemail.com", "emailondeck.com", "mohmal.com", "tempail.com",
              "spamgourmet.com", "mailnesia.com", "mytemp.email", "burnermail.io"}


def result(email, status, score, reason, **extra):
    return {"email": email, "status": status, "score": score, "reason": reason, **extra}


def verify(email: str, checker: smtp.SMTPChecker | None = None, mx_lookup=None) -> dict:
    email = email.strip().lower()
    if not EMAIL_RE.match(email) or ".." in email or email.startswith("."):
        return result(email, INVALID, 0, "bad syntax")
    local, domain = email.rsplit("@", 1)
    flags = {"role": local in ROLE, "free": domain in FREE, "disposable": domain in DISPOSABLE}
    if flags["disposable"]:
        return result(email, INVALID, 0, "disposable address", **flags)
    try:
        hosts = (mx_lookup or dns.mx_hosts)(domain)
    except dns.DNSError as e:
        return result(email, UNKNOWN, 30, str(e), **flags)
    if not hosts:
        return result(email, INVALID, 0, "domain has no mail server", **flags)

    checker = checker or smtp.SMTPChecker()
    probe = f"{smtp.random_local()}@{domain}"
    answers = checker.check_all(hosts, [email, probe])
    state, code, msg = answers[email]
    probe_state = answers[probe][0]
    flags["mx"] = hosts[0]

    if state == smtp.REJECTED:
        return result(email, INVALID, 5, f"mailbox rejected: {code} {msg}".strip(), **flags)
    if state == smtp.ACCEPTED and probe_state == smtp.REJECTED:
        return result(email, VALID, 80 if flags["role"] else 95, "mailbox exists", **flags)
    if state == smtp.ACCEPTED:
        return result(email, CATCH_ALL, 50, "server accepts every address", **flags)
    return result(email, UNKNOWN, 30, f"could not check: {code} {msg}".strip(), **flags)
