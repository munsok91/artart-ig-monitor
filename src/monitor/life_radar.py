"""ARTART LIFE adaptive topic radar.

The radar does three things on every run:

1. Re-measures which topic families are working on ``@artart.life``.
2. Finds proven carousel follow-ups from ``@artart.today``.
3. Expands beyond fixed movie accounts by learning source accounts from the
   credits of LIFE's own winners, then ranks their fresh posts.

Only public Instagram metadata is collected through Apify.  The routine never
logs in to Instagram, never renders a post, and never publishes to Instagram.
Its output is a short list in ``#01_라이프_소재공유`` for human review.

Run:
    python3 -m src.monitor.life_radar --no-send
    python3 -m src.monitor.life_radar
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import re
import statistics
import sys
import time
import urllib.error

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
OUTPUT_DIR = REPO_ROOT / "outputs" / "monitor"
PROFILE_PATH = OUTPUT_DIR / "life_radar_profile.json"
STATE_PATH = OUTPUT_DIR / ".sent_life_radar.json"

sys.path.insert(0, str(REPO_ROOT))

from src.monitor.scoring import REFERENCES_DIR, engagement, load_posts  # noqa: E402
from src.monitor.trending_slack import (  # noqa: E402
    clean_title,
    format_likes,
    jaccard,
    post_to_slack,
    post_tokens,
)
from src.scrapers.apify_ig import (  # noqa: E402
    load_env,
    scrape_accounts,
    write_posts_jsonl,
)

TODAY_ACCOUNT = "artart.today"
LIFE_ACCOUNT = "artart.life"

# The old LIFE routine watched only these three movie/anime accounts.  They
# remain useful seeds, but the learned source pool below can replace weak ones.
SEED_SOURCES = (
    "movieday.kr",
    "decision_movie",
    "deepdive.anime",
    "thedodo",
    "weratedogs",
    "montereybayaquarium",
    "sealrescueireland",
    "goodnews_movement",
    "upworthy",
)

CORE_LIMIT = 80
SOURCE_LIMIT = 14
MAX_LEARNED_SOURCES = 7
MAX_SOURCE_ACCOUNTS = 10
DEFAULT_TOP = 3
STATE_RETENTION_DAYS = 45

# Priors come from the 2026-07-13 measurement of 148 LIFE posts.  They are
# deliberately conservative and are blended with fresh account data each run.
CATEGORY_PRIORS = {
    "animal_cute": 1.55,
    "anime_character": 1.32,
    "human_emotion": 1.24,
    "everyday_curiosity": 1.10,
    "series_entertainment": 1.04,
    "art_design": 0.92,
    "film_cinema": 0.76,
    "general_life": 0.88,
}

CATEGORY_LABELS = {
    "animal_cute": "동물·귀여움",
    "anime_character": "애니·캐릭터",
    "human_emotion": "감정·관계",
    "everyday_curiosity": "일상·호기심",
    "series_entertainment": "드라마·예능",
    "art_design": "예술·디자인",
    "film_cinema": "영화·극장",
    "general_life": "라이프 일반",
}

CATEGORY_KEYWORDS = {
    "animal_cute": (
        "동물", "반려", "강아지", "고양이", "판다", "물범", "수달", "펭귄",
        "햄스터", "토끼", "여우", "사슴", "알파카", "쿼카", "라쿤", "캥거루",
        "고래", "돌고래", "해달", "새끼", "댕댕", "냥이", "animal", "puppy",
        "kitten", "panda", "seal", "otter", "pet",
    ),
    "anime_character": (
        "애니", "애니메이션", "캐릭터", "포켓몬", "피카츄", "지브리", "디즈니",
        "픽사", "짱구", "도라에몽", "원피스", "귀멸", "슬램덩크", "웹툰", "만화",
        "anime", "animation", "character", "pokemon", "ghibli", "disney", "pixar",
    ),
    "human_emotion": (
        "사랑", "우정", "가족", "부모", "아버지", "어머니", "엄마", "아빠", "아들",
        "딸", "연인", "부부", "친구", "배려", "다정", "따뜻", "위로", "감동", "눈물",
        "관계", "마음", "행복", "신뢰", "용기", "편지", "약속", "고백", "love",
        "family", "friendship", "kindness",
    ),
    "everyday_curiosity": (
        "일상", "생활", "음식", "요리", "카페", "디저트", "여행", "공간", "집", "방",
        "직장", "학교", "광고", "아이디어", "발명", "실험", "반전", "비밀", "이유",
        "알고 보니", "처음", "기록", "습관", "취향", "수집", "티켓", "굿즈", "daily",
        "life", "food", "travel", "idea", "curious",
    ),
    "series_entertainment": (
        "드라마", "시리즈", "넷플릭스", "예능", "방송", "명대사", "캐릭터", "배우",
        "에피소드", "ott", "netflix", "series", "drama", "tvn", "jtbc", "sbs", "mbc",
        "kbs", "channel a", "채널a",
    ),
    "art_design": (
        "예술", "미술", "작가", "작품", "그림", "회화", "조각", "설치", "전시", "미술관",
        "갤러리", "디자인", "건축", "사진가", "사진작가", "아티스트", "art", "artist",
        "design", "architecture", "museum", "gallery",
    ),
    "film_cinema": (
        "영화", "극장", "개봉", "감독", "관객", "박스오피스", "시사회", "영화관", "gv",
        "무비", "cinema", "movie", "film", "director", "box office",
    ),
}

ANGLE_GUIDES = {
    "animal_cute": "정보보다 귀여운 행동과 관계가 보이는 한 장면으로",
    "anime_character": "공개 소식보다 캐릭터의 반전 설정과 감정선으로",
    "human_emotion": "사건 전체보다 마음이 움직인 작은 행동 하나로",
    "everyday_curiosity": "뉴스 요약보다 ‘나도 궁금한 일상’의 질문으로",
    "series_entertainment": "출연·공개 소식보다 장면, 명대사, 관계성으로",
    "art_design": "작품 설명보다 일상에서 마주친 낯선 장면으로",
    "film_cinema": "개봉 정보보다 기억에 남는 한 장면이나 비하인드로",
    "general_life": "정보 전달보다 사람의 감정과 일상에 닿는 각도로",
}

RISK_KEYWORDS = {
    "reuse_restricted": (
        "무단 전재", "무단전재", "재배포 금지", "ai학습 이용 금지",
        "ai 학습 이용 금지", "all rights reserved",
    ),
    "death": (
        "사망", "별세", "부고", "숨졌", "목숨", "살해", "유해", "장례", "투병",
        "폭행", "성폭력", "범죄", "전쟁", "참사",
    ),
    "politics_finance": (
        "대통령", "국회", "정부", "법안", "정책", "선거", "정당", "주가", "증시",
        "코스피", "코스닥", "비트코인", "금리", "세금", "투자", "실적", "매출",
    ),
    "sports_result": (
        "우승", "준우승", "득점", "결승", "리그", "경기 결과", "이적", "fa 계약",
        "홈런", "승리", "패배",
    ),
}

COMMERCIAL_KEYWORDS = (
    "광고", "협찬", "할인", "구매", "판매", "프로모션", "쿠폰", "공동구매",
    "한정 판매", "사전예약", "링크에서", "프로필 링크",
)

SOURCE_MARKERS = ("📸", "📷", "🎥", "출처", "source", "credit", "영상", "사진")
HANDLE_RE = re.compile(r"@([A-Za-z0-9._]{2,30})")
OWN_OR_BAD_HANDLES = {
    "artart.today", "artart.life", "artart.team", "artart.jp", "artart.en",
    "artart.fr", "editor", "editors",
}

GENERIC_DEDUP_TOKENS = {
    "editor", "artart", "라이프", "아트아트", "오늘", "이번", "공개", "소식",
    "사실", "지금", "정말", "대한", "통해", "위해", "있는", "하는", "에서",
    "합니다", "했습니다", "있습니다", "instagram", "photo", "video",
}

SOURCE_CATEGORY_HINTS = {
    "movieday.kr": "film_cinema",
    "decision_movie": "film_cinema",
    "deepdive.anime": "anime_character",
    "thedodo": "animal_cute",
    "weratedogs": "animal_cute",
    "montereybayaquarium": "animal_cute",
    "sealrescueireland": "animal_cute",
    "goodnews_movement": "human_emotion",
    "upworthy": "human_emotion",
}

EDITORIAL_HANDLE_HINTS = (
    "official", "movie", "anime", "animation", "studio", "drama", "netflix",
    "disney", "pixar", "tvn", "sbs", "mbc", "jtbc", "kbs", "channel",
    "news", "mag", "archive", "rescue", "aquarium", "animal", "pets",
)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def age_hours(post: dict, now: dt.datetime) -> float:
    posted = parse_timestamp(post.get("timestamp"))
    if not posted:
        return 99999.0
    return max(0.0, (now - posted).total_seconds() / 3600)


def valid_engagement(post: dict) -> bool:
    likes = post.get("likes")
    return isinstance(likes, (int, float)) and likes >= 0


def baseline_for(posts: list[dict], now: dt.datetime, min_age_hours: float = 36) -> float:
    mature = [
        p for p in posts
        if valid_engagement(p) and age_hours(p, now) >= min_age_hours
    ]
    mature.sort(key=lambda p: p.get("timestamp") or "", reverse=True)
    values = [engagement(p) for p in mature[:30] if engagement(p) >= 0]
    return float(statistics.median(values)) if values else 1.0


def post_text(post: dict) -> str:
    text = post.get("caption") or ""
    tags = " ".join(str(tag) for tag in (post.get("hashtags") or []))
    return f"{text} {tags}".lower()


def classify_topics(post: dict) -> list[str]:
    text = post_text(post)
    hits: list[tuple[int, float, str]] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        count = sum(1 for keyword in keywords if keyword in text)
        if count:
            hits.append((count, CATEGORY_PRIORS[category], category))
    if not hits:
        return ["general_life"]
    hits.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [category for _, _, category in hits]


def primary_category(post: dict) -> str:
    classified = classify_topics(post)[0]
    owner = str(post.get("owner") or "").lower()
    hint = SOURCE_CATEGORY_HINTS.get(owner)
    if classified == "general_life" and hint:
        return hint
    return classified


def risk_multiplier(post: dict) -> tuple[float, list[str]]:
    text = post_text(post)
    reasons: list[str] = []
    multiplier = 1.0
    for name, keywords in RISK_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            reasons.append(name)
            multiplier *= {
                "reuse_restricted": 0.03,
                "death": 0.42,
                "politics_finance": 0.45,
                "sports_result": 0.72,
            }[name]
    if any(keyword in text for keyword in COMMERCIAL_KEYWORDS):
        reasons.append("commercial")
        multiplier *= 0.68
    return max(0.03, multiplier), reasons


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def learned_factor(prior: float, samples: list[float]) -> tuple[float, float, int]:
    if not samples:
        return prior, 0.0, 0
    median_score = float(statistics.median(samples))
    measured = clamp(median_score, 0.42, 2.30)
    weight = min(0.78, len(samples) / (len(samples) + 5.0))
    factor = prior * (1.0 - weight) + measured * weight
    return round(clamp(factor, 0.45, 2.20), 3), round(median_score, 3), len(samples)


def extract_source_handles(post: dict) -> set[str]:
    caption = post.get("caption") or ""
    credit_handles: set[str] = set()
    for line in caption.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in SOURCE_MARKERS):
            credit_handles.update(handle.lower() for handle in HANDLE_RE.findall(line))

    # Tagged users often carry the original creator even when the caption has
    # no explicit credit line.  Free-form mentions are used only as a fallback.
    tagged = {
        str(handle).lstrip("@").lower()
        for handle in (post.get("taggedUsers") or [])
        if handle
    }
    handles = credit_handles | tagged
    if not handles:
        handles = {
            str(handle).lstrip("@").lower()
            for handle in (post.get("mentions") or [])
            if handle
        }
    return {
        handle for handle in handles
        if handle not in OWN_OR_BAD_HANDLES and not handle.startswith("artart.")
    }


def build_life_profile(life_posts: list[dict], now: dt.datetime | None = None) -> dict:
    now = now or utcnow()
    baseline = baseline_for(life_posts, now)
    carousel_posts = [
        post for post in life_posts
        if post.get("type") in {"Sidecar", "Carousel"}
    ]
    carousel_baseline = baseline_for(carousel_posts, now)
    category_samples: dict[str, list[float]] = {
        category: [] for category in CATEGORY_PRIORS
    }
    format_samples: dict[str, list[float]] = {}
    source_scores: dict[str, list[float]] = {}
    source_categories: dict[str, list[str]] = {}

    usable: list[tuple[dict, float]] = []
    topic_usable: list[tuple[dict, float]] = []
    for post in life_posts:
        age = age_hours(post, now)
        if not valid_engagement(post) or not 36 <= age <= 45 * 24:
            continue
        score = engagement(post) / max(1.0, baseline)
        usable.append((post, score))
        post_type = str(post.get("type") or "Unknown")
        format_samples.setdefault(post_type, []).append(clamp(score, 0.0, 6.0))
        if post_type in {"Sidecar", "Carousel"}:
            topic_score = engagement(post) / max(1.0, carousel_baseline)
            topic_usable.append((post, topic_score))

    # This radar produces carousel briefs, so topic taste is learned from
    # LIFE carousels.  Fall back to all formats only when the sample is tiny.
    learning_rows = topic_usable if len(topic_usable) >= 10 else usable
    for post, score in learning_rows:
        for category in classify_topics(post)[:2]:
            category_samples[category].append(clamp(score, 0.0, 6.0))

    factors: dict[str, float] = {}
    stats: dict[str, dict] = {}
    for category, prior in CATEGORY_PRIORS.items():
        factor, median_score, count = learned_factor(prior, category_samples[category])
        factors[category] = factor
        stats[category] = {
            "label": CATEGORY_LABELS[category],
            "factor": factor,
            "median_score": median_score,
            "samples": count,
        }

    # Credit accounts from strong LIFE posts become tomorrow's source pool.
    for post, score in sorted(usable, key=lambda row: row[1], reverse=True)[:35]:
        if score < 1.0:
            continue
        category = primary_category(post)
        contribution = min(score, 5.0) * factors.get(category, 1.0)
        for handle in extract_source_handles(post):
            source_scores.setdefault(handle, []).append(contribution)
            source_categories.setdefault(handle, []).append(category)

    learned_sources = []
    for handle, values in source_scores.items():
        categories = source_categories.get(handle) or ["general_life"]
        dominant = max(set(categories), key=categories.count)
        learned_sources.append({
            "handle": handle,
            "score": round(sum(values), 3),
            "wins": len(values),
            "category": dominant,
        })
    learned_sources.sort(key=lambda row: (row["score"], row["wins"]), reverse=True)

    format_stats = {}
    for post_type, values in format_samples.items():
        format_stats[post_type] = {
            "median_score": round(float(statistics.median(values)), 3),
            "samples": len(values),
        }

    return {
        "version": 1,
        "learned_at": now.isoformat(),
        "life_baseline": round(baseline, 2),
        "carousel_baseline": round(carousel_baseline, 2),
        "sample_count": len(learning_rows),
        "all_sample_count": len(usable),
        "category_factors": factors,
        "category_stats": stats,
        "format_stats": format_stats,
        "learned_sources": learned_sources[:MAX_LEARNED_SOURCES],
    }


def content_tokens(post: dict) -> set[str]:
    return post_tokens(post) - GENERIC_DEDUP_TOKENS


def token_similarity(a: set[str], b: set[str]) -> float:
    if len(a & b) < 2:
        return 0.0
    return jaccard(a, b)


def duplicates_topic(tokens: set[str], token_sets: list[set[str]], threshold: float = 0.24) -> bool:
    return any(token_similarity(tokens, prior) >= threshold for prior in token_sets)


def category_factor(profile: dict, category: str) -> float:
    return float((profile.get("category_factors") or {}).get(
        category, CATEGORY_PRIORS.get(category, 0.88)
    ))


def freshness_multiplier(age: float, low: float, high: float) -> float:
    if age <= low:
        return 1.0
    span = max(1.0, high - low)
    return clamp(1.0 - 0.30 * ((age - low) / span), 0.70, 1.0)


def editorial_multiplier(post: dict, category: str) -> float:
    """Down-rank thin release promos while keeping visual animal clips eligible."""
    if category not in {"series_entertainment", "film_cinema"}:
        return 1.0
    text = post_text(post)
    caption_len = len(re.sub(r"[#@]\S+", "", post.get("caption") or "").strip())
    multiplier = 1.0
    if caption_len < 90:
        multiplier *= 0.52
    elif caption_len < 170:
        multiplier *= 0.78
    promo_markers = (
        "오직 넷플릭스", "공개 예정", "월 공개", "개봉", "출연", "캐스팅",
        "예고편", "티저", "trailer", "teaser", "premiere", "streaming",
    )
    if any(marker in text for marker in promo_markers):
        multiplier *= 0.72
    return multiplier


def make_candidate(
    post: dict,
    route: str,
    source_baseline: float,
    profile: dict,
    now: dt.datetime,
) -> dict:
    category = primary_category(post)
    base_score = engagement(post) / max(1.0, source_baseline)
    age = age_hours(post, now)
    risk, risk_reasons = risk_multiplier(post)
    life_factor = category_factor(profile, category)
    editorial = editorial_multiplier(post, category)
    if route == "today_followup":
        fresh = freshness_multiplier(age, 36, 10 * 24)
        route_bias = 1.15
    else:
        fresh = freshness_multiplier(age, 0, 96)
        route_bias = 1.0
    radar_score = (
        (clamp(base_score, 0.0, 6.0) ** 0.68)
        * life_factor * risk * fresh * route_bias * editorial
    )
    fit = int(round(clamp(57 + 18 * math.log(max(radar_score, 0.25), 2), 40, 99)))
    result = dict(post)
    result.update({
        "_route": route,
        "_category": category,
        "_category_label": CATEGORY_LABELS[category],
        "_life_factor": round(life_factor, 3),
        "_source_score": round(base_score, 3),
        "_radar_score": round(radar_score, 4),
        "_fit": fit,
        "_age_hours": round(age, 1),
        "_risk_reasons": risk_reasons,
        "_editorial_multiplier": round(editorial, 3),
        "_tokens": content_tokens(post),
        "_angle": ANGLE_GUIDES[category],
    })
    return result


def recent_life_token_sets(life_posts: list[dict], now: dt.datetime) -> list[set[str]]:
    return [
        content_tokens(post) for post in life_posts
        if age_hours(post, now) <= 45 * 24 and content_tokens(post)
    ]


def sent_token_sets(state: dict) -> list[set[str]]:
    return [
        set(entry.get("tokens") or [])
        for entry in (state.get("sent") or {}).values()
        if isinstance(entry, dict) and entry.get("tokens")
    ]


def collect_today_candidates(
    posts: list[dict],
    life_posts: list[dict],
    profile: dict,
    state: dict,
    now: dt.datetime | None = None,
) -> list[dict]:
    now = now or utcnow()
    baseline = baseline_for(posts, now)
    blocked = recent_life_token_sets(life_posts, now) + sent_token_sets(state)
    candidates = []
    for post in posts:
        age = age_hours(post, now)
        if post.get("type") not in {"Sidecar", "Carousel"}:
            continue
        if not valid_engagement(post) or not 36 <= age <= 10 * 24:
            continue
        if engagement(post) / max(1.0, baseline) < 1.30:
            continue
        candidate = make_candidate(post, "today_followup", baseline, profile, now)
        if candidate["_radar_score"] < 0.78:
            continue
        if duplicates_topic(candidate["_tokens"], blocked):
            continue
        candidates.append(candidate)
    return sorted(candidates, key=lambda row: row["_radar_score"], reverse=True)


def collect_external_candidates(
    posts_by_owner: dict[str, list[dict]],
    life_posts: list[dict],
    profile: dict,
    state: dict,
    now: dt.datetime | None = None,
) -> list[dict]:
    now = now or utcnow()
    blocked = recent_life_token_sets(life_posts, now) + sent_token_sets(state)
    candidates = []
    for owner, posts in posts_by_owner.items():
        baseline = baseline_for(posts, now, min_age_hours=18)
        for post in posts:
            age = age_hours(post, now)
            if not valid_engagement(post) or not 0 <= age <= 96:
                continue
            source_score = engagement(post) / max(1.0, baseline)
            if source_score < 1.12:
                continue
            candidate = make_candidate(post, "external_discovery", baseline, profile, now)
            # A source Reel is allowed because the editor will convert the topic
            # into a carousel, but a ready-made source carousel gets a small lift.
            if post.get("type") in {"Sidecar", "Carousel"}:
                candidate["_radar_score"] = round(candidate["_radar_score"] * 1.06, 4)
            if candidate["_radar_score"] < 0.72:
                continue
            if duplicates_topic(candidate["_tokens"], blocked):
                continue
            candidates.append(candidate)
    return sorted(candidates, key=lambda row: row["_radar_score"], reverse=True)


def select_balanced(today: list[dict], external: list[dict], top_n: int) -> list[dict]:
    """Keep both routes represented and stop one topic family flooding the list."""
    selected: list[dict] = []
    category_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    category_limit = 1 if top_n <= 3 else 2

    def add(candidate: dict) -> bool:
        if any(
            token_similarity(candidate["_tokens"], prior["_tokens"]) >= 0.24
            for prior in selected
        ):
            return False
        category = candidate["_category"]
        if category_counts.get(category, 0) >= category_limit:
            return False
        owner = str(candidate.get("owner") or "")
        if owner and owner_counts.get(owner, 0) >= 1:
            return False
        selected.append(candidate)
        category_counts[category] = category_counts.get(category, 0) + 1
        if owner:
            owner_counts[owner] = owner_counts.get(owner, 0) + 1
        return True

    # One proven Today follow-up and one genuinely new source whenever possible.
    if today:
        add(today[0])
    if external and len(selected) < top_n:
        add(external[0])

    pool = sorted(today[1:] + external[1:], key=lambda row: row["_radar_score"], reverse=True)
    for candidate in pool:
        if len(selected) >= top_n:
            break
        add(candidate)
    # If a forced first choice collided, fill from the complete pool.
    for candidate in sorted(today + external, key=lambda row: row["_radar_score"], reverse=True):
        if len(selected) >= top_n:
            break
        if candidate not in selected:
            add(candidate)
    selected.sort(key=lambda row: row["_radar_score"], reverse=True)
    return selected


def load_state(path: pathlib.Path = STATE_PATH) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "sent": {}}
    if not isinstance(raw, dict):
        return {"version": 1, "sent": {}}
    raw.setdefault("version", 1)
    raw.setdefault("sent", {})
    return raw


def atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def prune_state(state: dict, now: dt.datetime | None = None) -> dict:
    now = now or utcnow()
    fresh = {}
    for key, entry in (state.get("sent") or {}).items():
        if not isinstance(entry, dict):
            continue
        sent_at = parse_timestamp(entry.get("sent_at"))
        if sent_at and (now - sent_at).days <= STATE_RETENTION_DAYS:
            fresh[key] = entry
    return {"version": 1, "updated_at": now.isoformat(), "sent": fresh}


def refresh_feedback(state: dict, life_posts: list[dict], profile: dict, now: dt.datetime) -> int:
    """Mark radar suggestions that later appeared on LIFE.

    The profile already learns from every published LIFE post.  This marker is
    an audit trail showing whether radar suggestions actually became content.
    """
    matched = 0
    baseline = max(1.0, float(profile.get("life_baseline") or 1.0))
    for entry in (state.get("sent") or {}).values():
        if not isinstance(entry, dict) or entry.get("published_shortcode"):
            continue
        sent_at = parse_timestamp(entry.get("sent_at"))
        tokens = set(entry.get("tokens") or [])
        if not sent_at or not tokens:
            continue
        for post in life_posts:
            posted_at = parse_timestamp(post.get("timestamp"))
            if not posted_at or posted_at <= sent_at:
                continue
            if token_similarity(tokens, content_tokens(post)) < 0.30:
                continue
            entry["published_shortcode"] = post.get("shortCode")
            entry["published_url"] = post.get("url")
            entry["published_score"] = round(engagement(post) / baseline, 3)
            entry["matched_at"] = now.isoformat()
            matched += 1
            break
    return matched


def source_handles(profile: dict) -> list[str]:
    handles = list(SEED_SOURCES)
    for row in profile.get("learned_sources") or []:
        handle = str(row.get("handle") or "").lstrip("@").lower()
        category = str(row.get("category") or "general_life")
        wins = int(row.get("wins") or 0)
        editorial_handle = any(hint in handle for hint in EDITORIAL_HANDLE_HINTS)
        discovery_friendly = category in {
            "animal_cute", "anime_character", "human_emotion", "everyday_curiosity"
        }
        trusted = wins >= 2 or editorial_handle or discovery_friendly
        if trusted and handle and handle not in handles and handle not in OWN_OR_BAD_HANDLES:
            handles.append(handle)
        if len(handles) >= MAX_SOURCE_ACCOUNTS:
            break
    return handles


def learning_summary(profile: dict, limit: int = 3) -> str:
    rows = list((profile.get("category_stats") or {}).values())
    measured = [row for row in rows if int(row.get("samples") or 0) >= 2]
    ranked = measured or rows
    ranked.sort(key=lambda row: float(row.get("factor") or 0), reverse=True)
    return " · ".join(
        f"{row['label']} {float(row['factor']):.1f}배"
        for row in ranked[:limit]
    )


def format_candidate_message(rank: int, candidate: dict) -> dict:
    rank_marks = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    mark = rank_marks[rank - 1] if rank <= len(rank_marks) else f"{rank}."
    route = "투데이 후속" if candidate["_route"] == "today_followup" else "새 소재"
    title = clean_title(candidate.get("caption") or "", max_len=60) or "제목 확인 필요"
    owner = candidate.get("owner") or "unknown"
    measured = float(candidate["_source_score"])
    measured_label = "6.0배+" if measured > 6.0 else f"{measured:.1f}배"
    source_label = (
        f"투데이 평소의 {measured_label}"
        if candidate["_route"] == "today_followup"
        else f"@{owner} 평소의 {measured_label}"
    )
    likes = format_likes(int(candidate.get("likes") or 0))
    comments = int(candidate.get("comments") or 0)
    meta = f"추천 {candidate['_fit']} · {source_label} · {candidate['_category_label']} · ♥{likes}"
    if comments:
        meta += f" 💬{format_likes(comments)}"
    text = "\n".join([
        f"{mark} *[{route}] {title}*",
        meta,
        f"라이프 각도: {candidate['_angle']}",
        "권장: 4~6장 · 커버 훅 15자 이내 · 원문 장표 순서 재사용 금지",
        candidate.get("url") or "",
    ])
    return {"text": text, "unfurl_links": True, "unfurl_media": True}


def serializable_candidate(candidate: dict) -> dict:
    result = dict(candidate)
    result["_tokens"] = sorted(candidate.get("_tokens") or [])
    return result


def persist_scrape(by_owner: dict[str, list[dict]]) -> None:
    for owner, posts in by_owner.items():
        account_dir = REFERENCES_DIR / owner
        write_posts_jsonl(posts, account_dir)
        print(f"[scrape] @{owner}: {len(posts)}개 갱신")


def scrape_core(token: str, limit: int) -> None:
    print(f"[scrape] LIFE 학습 + TODAY 후속 후보 · 계정당 {limit}개")
    by_owner = scrape_accounts(
        token, [LIFE_ACCOUNT, TODAY_ACCOUNT], limit, download_images=False
    )
    persist_scrape(by_owner)


def scrape_sources(token: str, handles: list[str], limit: int) -> dict[str, list[dict]]:
    print(f"[scrape] 새 소재 출처 {len(handles)}개 · 계정당 {limit}개")
    by_owner = scrape_accounts(token, handles, limit, download_images=False)
    persist_scrape(by_owner)
    return {handle: load_posts(handle) for handle in handles}


def main() -> int:
    parser = argparse.ArgumentParser(description="ARTART LIFE 자동 소재 레이더")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--no-send", action="store_true", help="Slack 발송 없이 결과만 확인")
    parser.add_argument("--no-rescrape", action="store_true", help="Apify 호출 없이 저장 데이터 사용")
    parser.add_argument("--reset-dedup", action="store_true", help="이전 발송 중복 기록 무시")
    parser.add_argument("--core-limit", type=int, default=CORE_LIMIT)
    parser.add_argument("--source-limit", type=int, default=SOURCE_LIMIT)
    args = parser.parse_args()

    now = utcnow()
    env = {**load_env(ENV_PATH), **os.environ}
    token = env.get("APIFY_TOKEN")
    if not args.no_rescrape and not token:
        print("ERROR: APIFY_TOKEN 없음", file=sys.stderr)
        return 2

    if not args.no_rescrape:
        try:
            scrape_core(token, args.core_limit)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 핵심 계정 새 수집 실패, 저장 데이터로 계속: {exc}", file=sys.stderr)

    life_posts = load_posts(LIFE_ACCOUNT)
    today_posts = load_posts(TODAY_ACCOUNT)
    if not life_posts or not today_posts:
        print("ERROR: LIFE/TODAY 학습 데이터가 부족합니다.", file=sys.stderr)
        return 3

    profile = build_life_profile(life_posts, now)
    atomic_json(PROFILE_PATH, profile)
    handles = source_handles(profile)

    if not args.no_rescrape:
        try:
            posts_by_owner = scrape_sources(token, handles, args.source_limit)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 새 출처 수집 실패, 저장 데이터로 계속: {exc}", file=sys.stderr)
            posts_by_owner = {handle: load_posts(handle) for handle in handles}
    else:
        posts_by_owner = {handle: load_posts(handle) for handle in handles}

    state = {"version": 1, "sent": {}} if args.reset_dedup else load_state()
    state = prune_state(state, now)
    new_matches = refresh_feedback(state, life_posts, profile, now)

    today_candidates = collect_today_candidates(today_posts, life_posts, profile, state, now)
    external_candidates = collect_external_candidates(posts_by_owner, life_posts, profile, state, now)
    selected = select_balanced(today_candidates, external_candidates, max(1, args.top))

    print("\n=== ARTART LIFE 자동 소재 레이더 ===")
    print(f"[학습] {profile['sample_count']}개 · 기준 {profile['life_baseline']:.0f} · {learning_summary(profile)}")
    print(f"[출처] {', '.join('@' + handle for handle in handles)}")
    print(f"[후보] 투데이 후속 {len(today_candidates)} · 외부 새 소재 {len(external_candidates)} · 최종 {len(selected)}")
    for index, candidate in enumerate(selected, 1):
        route = "투데이 후속" if candidate["_route"] == "today_followup" else "새 소재"
        print(
            f"  {index}. [{route}/{candidate['_category_label']}] "
            f"추천 {candidate['_fit']} · {candidate['_source_score']:.2f}x · "
            f"{candidate.get('url')}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "run_at": now.isoformat(),
        "learning": profile,
        "source_handles": handles,
        "feedback_matches_added": new_matches,
        "counts": {
            "today_followup": len(today_candidates),
            "external_discovery": len(external_candidates),
            "selected": len(selected),
        },
        "selected": [serializable_candidate(candidate) for candidate in selected],
    }
    log_path = OUTPUT_DIR / f"{now.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()}_life_radar.json"
    atomic_json(log_path, report)

    if args.no_send:
        atomic_json(STATE_PATH, state)
        print("[send] --no-send: Slack 발송 생략")
        return 0
    if not selected:
        atomic_json(STATE_PATH, state)
        print("[send] 강한 새 후보 없음 — 억지로 채우지 않고 발송 생략")
        return 0

    webhook = env.get("SLACK_LIFE_WEBHOOK_URL")
    if not webhook:
        print("ERROR: SLACK_LIFE_WEBHOOK_URL 없음", file=sys.stderr)
        return 4

    kst = dt.timezone(dt.timedelta(hours=9))
    date_label = now.astimezone(kst).strftime("%-m/%-d")
    route_counts = {
        "today": sum(1 for row in selected if row["_route"] == "today_followup"),
        "external": sum(1 for row in selected if row["_route"] == "external_discovery"),
    }
    header = {
        "text": (
            f"🧭 *{date_label} 라이프 자동 소재 레이더 TOP {len(selected)}*\n"
            f"이번 학습: {learning_summary(profile)}\n"
            f"투데이 후속 {route_counts['today']} · 외부 새 소재 {route_counts['external']} "
            f"· 이미 다룬 주제 제외"
        )
    }
    try:
        post_to_slack(webhook, header)
        for index, candidate in enumerate(selected, 1):
            post_to_slack(webhook, format_candidate_message(index, candidate))
            code = candidate.get("shortCode") or candidate.get("id") or candidate.get("url")
            state["sent"][str(code)] = {
                "sent_at": now.isoformat(),
                "route": candidate["_route"],
                "source": candidate.get("owner"),
                "source_url": candidate.get("url"),
                "category": candidate["_category"],
                "tokens": sorted(candidate["_tokens"]),
                "title": clean_title(candidate.get("caption") or "", max_len=80),
            }
            time.sleep(1.0)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as exc:
        print(f"ERROR: Slack 발송 실패: {exc}", file=sys.stderr)
        return 5

    atomic_json(STATE_PATH, prune_state(state, now))
    print(f"[send] #01_라이프_소재공유 발송 완료 · {len(selected)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
