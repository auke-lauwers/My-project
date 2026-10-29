"""Score posts and pick the best performers.

Two views of "best":
  score      absolute engagement: reactions + 2 x comments + 3 x reposts.
             Comments and reposts cost the reader more effort and push the
             post further, so they weigh more than a one-tap reaction.
  vs_median  the post's score divided by its account's median score: how far
             it beat that account's normal. Surfaces breakout posts from
             smaller accounts that the absolute ranking would bury under the
             Bill Gateses of the list.
"""

from datetime import datetime, timedelta, timezone
from statistics import median

WEIGHTS = {"reactions": 1, "comments": 2, "reposts": 3}


def score(post: dict, weights: dict = WEIGHTS) -> int:
    return sum(int(post.get(k) or 0) * w for k, w in weights.items())


def within_days(post: dict, days) -> bool:
    if not days:
        return True
    if not post.get("posted_at"):
        return False
    posted = datetime.fromisoformat(post["posted_at"])
    return posted >= datetime.now(timezone.utc) - timedelta(days=days)


def rank(posts, days=None, include_reposts=False, min_text=0, sort="score", weights=WEIGHTS) -> list:
    """Return scored copies of posts, best first."""
    rows = [
        dict(p) for p in posts
        if (include_reposts or not p.get("is_repost"))
        and within_days(p, days)
        and len(p.get("text") or "") >= min_text
    ]
    for r in rows:
        r["score"] = score(r, weights)

    by_account = {}
    for r in rows:
        by_account.setdefault(r["account"], []).append(r["score"])
    medians = {a: median(s) for a, s in by_account.items()}
    for r in rows:
        m = medians[r["account"]]
        r["vs_median"] = round(r["score"] / m, 2) if m else 0.0

    key = (lambda r: (r["vs_median"], r["score"])) if sort == "vs_median" else (lambda r: (r["score"], r["vs_median"]))
    return sorted(rows, key=key, reverse=True)


def top(posts, n=50, per_account=None, **kwargs) -> list:
    """Top n overall, keeping at most per_account posts from any one account."""
    return pick(rank(posts, **kwargs), n, per_account)


def pick(rows, n=50, per_account=None) -> list:
    """First n of already-ranked rows, at most per_account from any one account."""
    picked, taken = [], {}
    for r in rows:
        if per_account and taken.get(r["account"], 0) >= per_account:
            continue
        taken[r["account"]] = taken.get(r["account"], 0) + 1
        picked.append(r)
        if len(picked) >= n:
            break
    return picked


def sources_of(post: dict) -> list:
    return post.get("sources") or ["account"]  # posts saved before topic search existed


def has_source(post: dict, source: str) -> bool:
    """source: 'accounts', 'topics', or one exact source like 'search:cold email'."""
    sources = sources_of(post)
    if source == "accounts":
        return "account" in sources
    if source == "topics":
        return any(s.startswith("search:") for s in sources)
    return source in sources


def topics(posts) -> list:
    return sorted({s[len("search:"):] for p in posts for s in sources_of(p) if s.startswith("search:")},
                  key=str.lower)


def creators(posts, days=None, topic=None, followed=()) -> list:
    """Authors found through topic searches, best first.

    Each creator's numbers cover all of their stored posts in the window;
    'followed' marks the ones already in the account list.
    """
    rows = rank(posts, days=days)
    found = {r["account"] for r in rows if has_source(r, f"search:{topic}" if topic else "topics")}
    followed = set(followed)
    out = {}
    for r in rows:
        if r["account"] not in found:
            continue
        c = out.setdefault(r["account"], {
            "account": r["account"], "author": r.get("author") or r["account"],
            "headline": r.get("headline", ""), "author_url": r.get("author_url", ""),
            "posts": 0, "total_score": 0, "best_score": 0, "best_text": "", "best_url": "",
            "topics": set(), "followed": r["account"] in followed,
        })
        c["posts"] += 1
        c["total_score"] += r["score"]
        c["headline"] = c["headline"] or r.get("headline", "")
        c["topics"].update(s[len("search:"):] for s in sources_of(r) if s.startswith("search:"))
        if r["score"] > c["best_score"]:
            c["best_score"], c["best_text"], c["best_url"] = r["score"], r.get("text", ""), r["url"]
    result = []
    for c in out.values():
        c["avg_score"] = round(c.pop("total_score") / c["posts"])
        c["topics"] = sorted(c["topics"], key=str.lower)
        result.append(c)
    return sorted(result, key=lambda c: (c["best_score"], c["avg_score"]), reverse=True)
