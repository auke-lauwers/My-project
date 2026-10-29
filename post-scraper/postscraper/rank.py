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
    picked, taken = [], {}
    for r in rank(posts, **kwargs):
        if per_account and taken.get(r["account"], 0) >= per_account:
            continue
        taken[r["account"]] = taken.get(r["account"], 0) + 1
        picked.append(r)
        if len(picked) >= n:
            break
    return picked
