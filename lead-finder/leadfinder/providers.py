"""Search API clients. Each returns pages of {"url", "title", "snippet"} dicts.

Search engines block automated scraping of their result pages (CAPTCHAs,
IP bans), so this only talks to their paid or free-tier APIs.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "lead-finder/0.1"


class ProviderError(RuntimeError):
    pass


def _request(url: str, params: dict | None = None, payload: dict | None = None,
             headers: dict | None = None, retries: int = 3) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            body = e.read().decode(errors="replace")[:300]
            raise ProviderError(f"HTTP {e.code} from {req.host}: {body}") from e
        except urllib.error.URLError as e:
            if attempt == retries - 1:
                raise ProviderError(f"Could not reach {req.host}: {e.reason}") from e
            time.sleep(2 ** (attempt + 1))
    raise ProviderError(f"Gave up on {req.host} after {retries} attempts (rate limited?)")


def _need(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        raise ProviderError(f"Set {var} in your environment or .env file")
    return value


class Provider:
    name = ""
    page_size = 10
    max_results = 100

    def search_page(self, query: str, page: int, country: str = "") -> list[dict]:
        raise NotImplementedError


class Serper(Provider):
    """serper.dev: Google results, 2,500 free queries, then cheap. Recommended."""
    name = "serper"
    max_results = 100

    def search_page(self, query, page, country=""):
        payload = {"q": query, "num": self.page_size, "page": page + 1}
        if country:
            payload["gl"] = country.lower()
        data = _request("https://google.serper.dev/search", payload=payload,
                        headers={"X-API-KEY": _need("SERPER_API_KEY")})
        return [{"url": r.get("link", ""), "title": r.get("title", ""),
                 "snippet": r.get("snippet", "")} for r in data.get("organic", [])]


class SerpApi(Provider):
    """serpapi.com: Google results."""
    name = "serpapi"
    max_results = 100

    def search_page(self, query, page, country=""):
        params = {"engine": "google", "q": query, "num": self.page_size,
                  "start": page * self.page_size, "api_key": _need("SERPAPI_API_KEY")}
        if country:
            params["gl"] = country.lower()
        data = _request("https://serpapi.com/search.json", params)
        if "error" in data and "hasn't returned any results" not in data["error"]:
            raise ProviderError(f"SerpApi: {data['error']}")
        return [{"url": r.get("link", ""), "title": r.get("title", ""),
                 "snippet": r.get("snippet", "")} for r in data.get("organic_results", [])]


class Brave(Provider):
    """Brave Search API: its own index, so it finds people Google misses."""
    name = "brave"
    page_size = 20
    max_results = 200  # offset is capped at 9 pages

    def search_page(self, query, page, country=""):
        params = {"q": query, "count": self.page_size, "offset": page}
        if country:
            params["country"] = country.upper()
        data = _request("https://api.search.brave.com/res/v1/web/search", params,
                        headers={"X-Subscription-Token": _need("BRAVE_API_KEY"),
                                 "Accept": "application/json"})
        return [{"url": r.get("url", ""), "title": r.get("title", ""),
                 "snippet": r.get("description", "")}
                for r in data.get("web", {}).get("results", [])]


class GoogleCSE(Provider):
    """Google Programmable Search JSON API (100 free queries a day)."""
    name = "google"
    max_results = 100

    def search_page(self, query, page, country=""):
        params = {"key": _need("GOOGLE_API_KEY"), "cx": _need("GOOGLE_CSE_ID"),
                  "q": query, "num": self.page_size, "start": page * self.page_size + 1}
        if country:
            params["gl"] = country.lower()
        data = _request("https://www.googleapis.com/customsearch/v1", params)
        return [{"url": r.get("link", ""), "title": r.get("title", ""),
                 "snippet": r.get("snippet", "")} for r in data.get("items", [])]


PROVIDERS = {p.name: p for p in (Serper, SerpApi, Brave, GoogleCSE)}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise ProviderError(f"Unknown provider {name!r}; pick one of {', '.join(PROVIDERS)}")


def search(provider: Provider, query: str, limit: int = 100, country: str = "",
           delay: float = 1.0):
    """Yield results page by page until `limit`, the provider cap, or no more results."""
    limit = min(limit, provider.max_results)
    seen = 0
    page = 0
    while seen < limit:
        results = provider.search_page(query, page, country)
        if not results:
            return
        for r in results[: limit - seen]:
            yield r
        seen += len(results)
        if len(results) < provider.page_size:
            return
        page += 1
        time.sleep(delay)
