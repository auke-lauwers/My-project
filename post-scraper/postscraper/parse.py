"""Turn LinkedIn feed HTML and Voyager API JSON into Post records.

Nothing here touches the network, so it is all unit-testable from fixtures.
LinkedIn changes its markup often; the selectors are deliberately loose and
every field falls back to something sensible instead of raising.
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from urllib.parse import quote, unquote, urlencode

from bs4 import BeautifulSoup

ACTIVITY_RE = re.compile(r"urn:li:(?:activity|ugcPost|share):(\d{15,22})")
COUNT_RE = re.compile(r"(\d[\d,.]*)\s*([KkMm])?")


@dataclass
class Post:
    post_id: str
    account: str
    author: str = ""
    text: str = ""
    url: str = ""
    posted_at: str = ""  # ISO 8601, UTC
    reactions: int = 0
    comments: int = 0
    reposts: int = 0
    media: str = ""  # image, video, document, article, poll or empty
    is_repost: bool = False
    author_url: str = ""
    headline: str = ""  # the author's tagline, e.g. "Founder @ Acme | Cold email"
    sources: list = field(default_factory=list)  # "account" and/or "search:<topic>"
    scraped_at: str = field(default_factory=lambda: now_iso())

    def to_dict(self) -> dict:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_count(text) -> int:
    """'1,234' -> 1234, '12K' -> 12000, '1.2M reactions' -> 1200000, '' -> 0."""
    if text is None:
        return 0
    if isinstance(text, (int, float)):
        return int(text)
    m = COUNT_RE.search(text)
    if not m:
        return 0
    number, suffix = m.group(1), (m.group(2) or "").lower()
    if suffix:
        return int(round(float(number.replace(",", "")) * {"k": 1_000, "m": 1_000_000}[suffix]))
    return int(re.sub(r"[,.]", "", number))


def activity_id(text: str) -> str:
    m = ACTIVITY_RE.search(text or "")
    return m.group(1) if m else ""


def posted_at_from_id(post_id: str) -> str:
    """LinkedIn post IDs are snowflakes: the first 41 bits are epoch milliseconds."""
    try:
        ms = int(post_id) >> 22
    except (TypeError, ValueError):
        return ""
    if not 1_000_000_000_000 < ms < 4_000_000_000_000:  # 2001..2096: sanity check
        return ""
    return datetime.fromtimestamp(ms / 1000, timezone.utc).replace(microsecond=0).isoformat()


def search_url(query: str, date_posted: str = "past-month", sort: str = "relevance") -> str:
    """LinkedIn's post search. date_posted: past-24h, past-week, past-month or '' for any time."""
    params = {"keywords": query, "origin": "FACETED_SEARCH", "sortBy": f'"{sort}"'}
    if date_posted:
        params["datePosted"] = f'"{date_posted}"'
    return "https://www.linkedin.com/search/results/content/?" + urlencode(params, quote_via=quote)


def account_from_url(href: str) -> str:
    """'https://www.linkedin.com/in/jane-doe?miniProfileUrn=...' -> 'in/jane-doe'."""
    m = re.search(r"linkedin\.com/(in|company|school)/([^/?#\s]+)", href or "")
    if not m:
        m = re.match(r"/(in|company|school)/([^/?#\s]+)", href or "")
    return f"{m.group(1)}/{unquote(m.group(2))}" if m else ""


def post_url(post_id: str) -> str:
    return f"https://www.linkedin.com/feed/update/urn:li:activity:{post_id}/"


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _multiline_text(node) -> str:
    """Post text with its line breaks kept; LinkedIn renders them as <br>."""
    if not node:
        return ""
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text("")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _first(container, selectors):
    for sel in selectors:
        node = container.select_one(sel)
        if node:
            return node
    return None


def _aria_count(container, word: str) -> int:
    """Counts like '57 comments' live in button aria-labels or visible text."""
    pattern = re.compile(rf"(\d[\d,.]*\s*[KkMm]?)\s+{word}", re.I)
    for node in container.select("button, a, span, li"):
        for value in (node.get("aria-label", ""), _text(node)):
            m = pattern.search(value)
            if m:
                return parse_count(m.group(1))
    return 0


def _media_type(container) -> str:
    checks = [
        ("video", "video, .update-components-linkedin-video"),
        ("document", ".update-components-document, .document-s-container"),
        ("poll", ".update-components-poll"),
        ("article", ".update-components-article"),
        ("image", ".update-components-image, .update-components-carousel"),
    ]
    for name, sel in checks:
        if container.select_one(sel):
            return name
    return ""


def parse_feed_html(html: str, account: str = "", source: str = "account") -> list:
    """Parse the posts on a recent-activity, company posts or search results page.

    With no account (search results), each post is credited to its author's
    profile, taken from the author link.
    """
    soup = BeautifulSoup(html, "html.parser")
    posts, seen = [], set()
    for container in soup.select("[data-urn], [data-id]"):
        urn = container.get("data-urn") or container.get("data-id") or ""
        pid = activity_id(urn)
        if not pid or pid in seen:
            continue
        # Skip outer wrappers that contain another post container.
        if container.select_one("[data-urn*='activity'], [data-id*='activity']"):
            continue
        seen.add(pid)

        header = _text(_first(container, [".update-components-header__text-view", ".update-components-header"]))
        # "X reposted this", "X commented on this", "X likes this": not their own post.
        is_repost = bool(re.search(r"\b(reposted|commented|likes|loves|celebrates|supports|finds)\b", header, re.I))
        author = _text(_first(container, [
            ".update-components-actor__title span[aria-hidden='true']",
            ".update-components-actor__name span[aria-hidden='true']",
            ".update-components-actor__title",
            ".update-components-actor__name",
        ]))
        actor = _first(container, [".update-components-actor", ".feed-shared-actor"]) or container
        author_url = ""
        for link in actor.select("a[href]"):
            if account_from_url(link["href"]):
                author_url = "https://www.linkedin.com/" + account_from_url(link["href"]) + "/"
                break
        headline = _text(_first(actor, [
            ".update-components-actor__description span[aria-hidden='true']",
            ".update-components-actor__description",
        ]))
        post_account = account or account_from_url(author_url)
        if not post_account:
            continue  # a search result we can't attribute to anyone
        body = _first(container, [
            ".update-components-update-v2__commentary",
            ".feed-shared-update-v2__description",
            ".update-components-text",
            ".feed-shared-inline-show-more-text",
        ])
        text = _multiline_text(body).removesuffix("…more").removesuffix("... more").strip()

        reactions_node = _first(container, [
            ".social-details-social-counts__reactions-count",
            ".social-details-social-counts__social-proof-fallback-number",
        ])
        reactions = parse_count(_text(reactions_node)) if reactions_node else _aria_count(container, "reactions?")

        posts.append(Post(
            post_id=pid,
            account=post_account,
            author=author.split(" • ")[0],
            text=text,
            url=post_url(pid),
            posted_at=posted_at_from_id(pid),
            reactions=reactions,
            comments=_aria_count(container, "comments?"),
            reposts=_aria_count(container, "reposts?"),
            media=_media_type(container),
            is_repost=is_repost,
            author_url=author_url,
            headline=headline,
            sources=[source],
        ))
    return posts


def counts_from_voyager(payload) -> dict:
    """Walk any Voyager JSON response and pull out per-post engagement counts.

    LinkedIn's own API responses carry exact numbers (the HTML shows "12K"),
    in objects shaped like {"entityUrn": "...urn:li:activity:123...",
    "numLikes": 10, "numComments": 2, "numShares": 1}.
    """
    found = {}

    def walk(node):
        if isinstance(node, dict):
            if "numLikes" in node or "numComments" in node:
                pid = ""
                for key in ("entityUrn", "urn", "threadUrn", "*socialDetail"):
                    pid = activity_id(str(node.get(key, "")))
                    if pid:
                        break
                if pid:
                    found[pid] = {
                        "reactions": int(node.get("numLikes") or 0),  # sums every reaction type
                        "comments": int(node.get("numComments") or 0),
                        "reposts": int(node.get("numShares") or 0),
                    }
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def merge_counts(posts: list, counts: dict) -> list:
    """Prefer exact API counts over the rounded numbers in the HTML."""
    for p in posts:
        c = counts.get(p.post_id)
        if c:
            p.reactions = c["reactions"] or p.reactions
            p.comments = c["comments"] or p.comments
            p.reposts = c["reposts"] or p.reposts
    return posts
