"""Posts live in one JSON Lines file, de-duplicated by post_id.

Re-scraping an account updates the counts of posts already stored, so the
file always holds the latest engagement numbers.
"""

import csv
import io
import json
import os

CSV_FIELDS = [
    "rank", "score", "vs_median", "account", "author", "posted_at", "reactions",
    "comments", "reposts", "media", "url", "text",
]


def load(path: str) -> dict:
    posts = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    p = json.loads(line)
                    posts[p["post_id"]] = p
    return posts


def save(path: str, posts: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for p in posts.values():
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def upsert(posts: dict, new) -> tuple:
    added = updated = 0
    for p in new:
        d = p.to_dict() if hasattr(p, "to_dict") else dict(p)
        if d["post_id"] in posts:
            updated += 1
            old = posts[d["post_id"]]
            # Keep text/author from an earlier scrape if this one missed them.
            for key in ("text", "author", "media"):
                d[key] = d[key] or old.get(key, "")
        else:
            added += 1
        posts[d["post_id"]] = d
    return added, updated


def render(rows, fmt: str) -> str:
    """Ranked rows as csv, json or md text."""
    ranked = [{"rank": i, **r} for i, r in enumerate(rows, 1)]
    if fmt == "json":
        return json.dumps(ranked, ensure_ascii=False, indent=2)
    if fmt == "md":
        return markdown(ranked)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    w.writerows(ranked)
    return buf.getvalue()


def export(rows, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fmt = os.path.splitext(path)[1].lower().lstrip(".")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(render(rows, fmt if fmt in ("json", "md") else "csv"))


def markdown(rows) -> str:
    out = ["# Top LinkedIn posts", ""]
    for r in rows:
        date = (r.get("posted_at") or "")[:10]
        out.append(f"## {r['rank']}. {r.get('author') or r['account']} — {date}")
        out.append(
            f"**{r['reactions']:,}** reactions · **{r['comments']:,}** comments · "
            f"**{r['reposts']:,}** reposts · score {r['score']:,} · "
            f"{r['vs_median']}x their median{' · ' + r['media'] if r.get('media') else ''}"
        )
        out.append("")
        out.extend("> " + line for line in (r.get("text") or "(no text)").splitlines())
        out.append("")
        out.append(f"[Open post]({r['url']})")
        out.append("")
    return "\n".join(out)
