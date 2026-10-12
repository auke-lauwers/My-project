"""MX lookups. Uses dnspython when installed, otherwise DNS-over-HTTPS (no dependencies)."""

import json
import urllib.parse
import urllib.request
from functools import lru_cache

DOH_SERVERS = ["https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"]


class DNSError(RuntimeError):
    pass


def _doh(name: str, rtype: str) -> list[str] | None:
    """Record data strings, [] if none, None if the domain doesn't exist."""
    last_error = None
    for server in DOH_SERVERS:
        url = f"{server}?{urllib.parse.urlencode({'name': name, 'type': rtype})}"
        req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
        except OSError as e:
            last_error = e
            continue
        if data.get("Status") == 3:
            return None
        want = {"MX": 15, "A": 1, "AAAA": 28}[rtype]
        return [a["data"] for a in data.get("Answer", []) if a.get("type") == want]
    raise DNSError(f"DNS lookup failed for {name}: {last_error}")


def _dnspython(name: str, rtype: str) -> list[str] | None:
    import dns.resolver  # type: ignore
    try:
        return [r.to_text() for r in dns.resolver.resolve(name, rtype, lifetime=10)]
    except dns.resolver.NXDOMAIN:
        return None
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return []
    except dns.exception.DNSException as e:
        raise DNSError(f"DNS lookup failed for {name}: {e}") from e


def _query(name: str, rtype: str) -> list[str] | None:
    try:
        import dns.resolver  # noqa: F401
    except ImportError:
        return _doh(name, rtype)
    return _dnspython(name, rtype)


@lru_cache(maxsize=4096)
def mx_hosts(domain: str) -> tuple[str, ...]:
    """Mail servers for a domain, best first. () if the domain can't receive mail."""
    records = _query(domain, "MX")
    if records is None:
        return ()
    hosts = []
    for r in records:
        parts = r.split()
        if len(parts) == 2:
            hosts.append((int(parts[0]), parts[1].rstrip(".").lower()))
    hosts = [h for _, h in sorted(hosts) if h]  # "0 ." is a null MX: no mail accepted
    if hosts:
        return tuple(hosts)
    if records == [] and _query(domain, "A"):
        return (domain,)  # no MX: mail goes to the A record (RFC 5321 5.1)
    return ()
