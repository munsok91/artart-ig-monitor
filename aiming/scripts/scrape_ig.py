"""경제 소재공유 — 인스타 4개 계정 스크랩 (순수 stdlib).

snew_magazine / 1club.kr / dy1.mag / ekke.now 의 최근 게시물을
Apify instagram-post-scraper 로 가져와 계정별 engagement 정렬 후
outputs/econ/ig_posts.json 으로 저장한다. (이미지 다운로드 없음, ~1분)

좋아요 숨김 계정(likesCount=-1)은 댓글수 가중으로 정렬한다.

Run:
    python3 src/econ/scrape_ig.py
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
OUT_PATH = REPO_ROOT / "outputs" / "econ" / "ig_posts.json"

ACCOUNTS = ["ekke.now", "soonsal.brief", "moneygraphyworld"]
# 7일 누적 중복차단을 켠 뒤로는 후보 풀이 얕으면 며칠 만에 바닥난다.
# (계정당 하루 최대 2건 소진 × 7일 = 14건이 이론상 최대 소모량)
RESULTS_LIMIT = 30
KEEP_PER_ACCOUNT = 14
ACTOR = "apify~instagram-post-scraper"
MAX_RETRIES = 3       # DNS/타임아웃 등 일시 실패 시 재시도 횟수
RETRY_WAIT = 20       # 재시도 간 대기(초)
REQ_TIMEOUT = 300     # run-sync 한 번당 최대 대기(초)


def load_env(path: pathlib.Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def score(p: dict) -> float:
    likes = p.get("likesCount") or 0
    comments = p.get("commentsCount") or 0
    # 좋아요 숨김(-1)이면 댓글 중심, 아니면 likes + 3*comments
    if likes < 0:
        return comments * 10.0
    return likes + comments * 3.0


def fetch_items(token: str) -> list:
    """Apify run-sync 호출. DNS/타임아웃 등 일시 실패는 재시도, 0건이면 실패 취급."""
    url = (
        f"https://api.apify.com/v2/acts/{ACTOR}"
        f"/run-sync-get-dataset-items?token={token}"
    )
    payload = {"username": ACCOUNTS, "resultsLimit": RESULTS_LIMIT}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            items = json.loads(
                urllib.request.urlopen(req, timeout=REQ_TIMEOUT).read()
            )
            if items:
                return items
            last_err = "0건 반환"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = repr(e)
        print(f"[scrape] 시도 {attempt}/{MAX_RETRIES} 실패: {last_err}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_WAIT)
    raise SystemExit(f"IG 스크랩 {MAX_RETRIES}회 모두 실패 ({last_err}) — 기존 파일 보존")


def main() -> None:
    env = load_env(ENV_PATH)
    token = os.environ.get("APIFY_TOKEN") or env.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN 없음 (.env 확인)")

    items = fetch_items(token)

    by_account: dict[str, list] = {a: [] for a in ACCOUNTS}
    for p in items:
        u = p.get("ownerUsername") or p.get("username") or ""
        if u in by_account:
            by_account[u].append(
                {
                    "username": u,
                    "url": p.get("url"),
                    "type": p.get("type"),
                    "timestamp": (p.get("timestamp") or "")[:10],
                    "likesCount": p.get("likesCount"),
                    "commentsCount": p.get("commentsCount"),
                    "caption": (p.get("caption") or "").strip(),
                    "_score": score(p),
                }
            )

    for u in by_account:
        by_account[u].sort(key=lambda x: x["_score"], reverse=True)
        by_account[u] = by_account[u][:KEEP_PER_ACCOUNT]

    total = sum(len(v) for v in by_account.values())
    if total == 0:
        # 응답은 왔으나 4계정과 매칭 0건 → 기존 파일 보존(빈 배열로 덮어쓰지 않음)
        raise SystemExit("매칭된 게시물 0건 — 기존 ig_posts.json 보존")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(by_account, ensure_ascii=False, indent=2))
    print(f"saved {total} candidate posts -> {OUT_PATH}")


if __name__ == "__main__":
    main()
