"""Shared scoring + filtering logic for ARTART monitor."""

from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import statistics

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REFERENCES_DIR = REPO_ROOT / "references"


def load_posts(account: str) -> list[dict]:
    path = REFERENCES_DIR / account / "posts.jsonl"
    if not path.exists():
        return []
    posts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            posts.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    posts.sort(key=lambda p: p.get("timestamp") or "", reverse=True)
    return posts


def has_valid_likes(post: dict) -> bool:
    return (post.get("likes") or 0) >= 0


def engagement(post: dict) -> int:
    return (post.get("likes") or 0) + 3 * (post.get("comments") or 0)


def days_old(post: dict, now: dt.datetime) -> float:
    ts = post.get("timestamp")
    if not ts:
        return 999.0
    try:
        posted = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return 999.0
    return (now - posted).total_seconds() / 86400


def hours_old(post: dict, now: dt.datetime) -> float:
    return days_old(post, now) * 24


def score_posts(posts: list[dict], baseline_window: int = 30) -> list[dict]:
    """Annotate every post with _score, _engagement, _age_days, _age_hours,
    _hidden_likes, _warming. Score = engagement / median(mature engagements).
    """
    now = dt.datetime.now(dt.timezone.utc)
    mature = [
        p for p in posts if days_old(p, now) >= 1.5 and has_valid_likes(p)
    ][:baseline_window]
    baseline = (
        statistics.median(engagement(p) for p in mature) if mature else 1
    )
    if baseline == 0:
        baseline = 1
    for p in posts:
        eng = engagement(p)
        p["_engagement"] = eng
        p["_score"] = round(eng / baseline, 2)
        p["_age_days"] = round(days_old(p, now), 1)
        p["_age_hours"] = round(hours_old(p, now), 1)
        p["_hidden_likes"] = not has_valid_likes(p)
        p["_warming"] = days_old(p, now) < 1.5
    return posts


def tag_emoji(score: float, warming: bool = False) -> str:
    if warming:
        return "⏳"
    if score >= 2.0:
        return "🔥"
    if score >= 1.5:
        return "✨"
    if score >= 0.7:
        return "😐"
    if score >= 0.5:
        return "📉"
    return "💀"


def caption_preview(caption: str, n: int = 80) -> str:
    text = (caption or "").replace("\n", " ").strip()
    return text[:n] + ("…" if len(text) > n else "")


def filter_window(posts: list[dict], mode: str) -> list[dict]:
    """Filter posts to the time window for a given report mode.

    daily   = posts aged 18-42h (yesterday's, ~24h mark)
    weekly  = posts aged 0-168h (last 7 days, all)
    monthly = posts aged 0-720h (last 30 days, all)
    """
    valid = [p for p in posts if not p.get("_hidden_likes")]
    if mode == "daily":
        return [p for p in valid if 18 <= (p.get("_age_hours") or 999) <= 42]
    if mode == "weekly":
        return [p for p in valid if (p.get("_age_hours") or 999) <= 168]
    if mode == "monthly":
        return [p for p in valid if (p.get("_age_hours") or 999) <= 720]
    raise ValueError(f"unknown mode: {mode}")


def hashtag_performance(
    posts: list[dict], min_uses: int = 2
) -> list[tuple[str, float, int]]:
    """Average score per hashtag across the given post list. Returns
    [(tag, avg_score, count)] sorted by avg_score desc.
    """
    bucket: dict[str, list[float]] = collections.defaultdict(list)
    for p in posts:
        for tag in p.get("hashtags") or []:
            bucket[tag].append(p.get("_score") or 0)
    rows = [
        (tag, round(sum(scores) / len(scores), 2), len(scores))
        for tag, scores in bucket.items()
        if len(scores) >= min_uses
    ]
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def daily_buckets(posts: list[dict]) -> list[tuple[str, float, int]]:
    """Avg score per calendar day (UTC). Returns [(date, avg, count)] oldest first."""
    bucket: dict[str, list[float]] = collections.defaultdict(list)
    for p in posts:
        ts = p.get("timestamp")
        if not ts:
            continue
        try:
            day = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            continue
        bucket[day].append(p.get("_score") or 0)
    return sorted(
        [
            (day, round(sum(s) / len(s), 2), len(s))
            for day, s in bucket.items()
        ],
        key=lambda r: r[0],
    )


def weekly_buckets(posts: list[dict]) -> list[tuple[str, float, int]]:
    """Avg score per ISO week (YYYY-Www). Returns [(week, avg, count)]."""
    bucket: dict[str, list[float]] = collections.defaultdict(list)
    for p in posts:
        ts = p.get("timestamp")
        if not ts:
            continue
        try:
            d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            iy, iw, _ = d.isocalendar()
            key = f"{iy}-W{iw:02d}"
        except ValueError:
            continue
        bucket[key].append(p.get("_score") or 0)
    return sorted(
        [(k, round(sum(s) / len(s), 2), len(s)) for k, s in bucket.items()],
        key=lambda r: r[0],
    )
