"""External account trending → Slack.

매일 09:30 / 12:00 / 18:00 KST 3회, 각 회마다 TOP 3 게시물을 슬랙으로 발송.
각 게시물은 별개 메시지로 보내서 슬랙이 IG 링크 unfurl 깔끔하게 띄우게 함.

랭킹 = base_score(engagement/baseline) × account_weight × cultural_bonus
- account_weight: 문화예술 무게 (eyesmag 1.2, millionhiphop 1.1, ...)
- cultural_bonus: 캡션/해시태그에 전시/공연/예술 키워드 있으면 가산
- 이전 슬롯에서 보낸 건은 dedup (.sent_slack_state.json)

Run:
    python3 src/monitor/trending_slack.py --slot now    # 즉시 발송 (24h 윈도우)
    python3 src/monitor/trending_slack.py --slot morning   # 9:30 (12-36h)
    python3 src/monitor/trending_slack.py --slot noon      # 12:00 (0-15h)
    python3 src/monitor/trending_slack.py --slot evening   # 18:00 (0-9h)
    python3 src/monitor/trending_slack.py --backfill 60 --no-send   # baseline 쌓기
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
OUTPUT_DIR = REPO_ROOT / "outputs" / "monitor"
STATE_PATH = OUTPUT_DIR / ".sent_slack_state.json"

sys.path.insert(0, str(REPO_ROOT))

from src.monitor.scoring import (  # noqa: E402
    REFERENCES_DIR,
    caption_preview,
    hours_old,
    load_posts,
    score_posts,
    tag_emoji,
)
from src.scrapers.apify_ig import (  # noqa: E402
    load_env,
    scrape_accounts,
    write_posts_jsonl,
)

# (handle, 한글라벨, 문화예술 가중치)
ACCOUNTS = [
    ("eyesmag",           "아이즈매거진",   1.20),  # 문화/예술/패션 — 핵심
    ("calue.inspir",      "캘유",           1.15),  # 가치/인사이트 매거진 — 인문/문화
    ("millionhiphop",     "밀리언힙합",     1.10),  # 음악
    ("_tripgoing",        "트립고잉",       1.00),  # 여행
    ("dailyfashion_news", "데일리패션뉴스", 0.95),  # 패션 뉴스
]

# 스토리카 소재공유방 — 큐레이션/인사이트 매거진 세트 (2026-06-18 문석 요청)
STORICA_ACCOUNTS = [
    ("dy1.mag",       "데이원 매거진",   1.10),
    ("varo_magazine", "바로 매거진",     1.05),
    ("cloud__pages",  "클라우드 페이지", 1.05),
    ("curation_club", "큐레이션 클럽",   1.00),
]

# --profile 로 선택하는 발송 프로필 (계정 세트 + 채널 웹훅 + 헤더 + state 파일 분리)
PROFILES = {
    "today": {
        "accounts":        ACCOUNTS,
        "webhook_env":     "SLACK_WEBHOOK_URL",       # #01_투데이_소재공유방
        "header_emoji":    "📰",
        "header_title":    "시의성",
        "state_suffix":    "",                         # 기존 .sent_slack_state.json 유지
        "per_account_top": None,                       # 전체 통합 TOP N (기존 방식)
    },
    "storica": {
        "accounts":        STORICA_ACCOUNTS,
        "webhook_env":     "SLACK_STORICA_WEBHOOK_URL",  # 스토리카 소재공유방
        "header_emoji":    "📚",
        "header_title":    "스토리카 시의성",
        "state_suffix":    "_storica",
        "per_account_top": 2,                          # 계정별 TOP 2 + 중복 제거, 계정순 정렬
    },
}

# ARTART 톤 핵심 키워드 — 1개 적중당 +15%, 최대 1.6x
# "쉽고 힙한 문화/예술" — 작가/공간/전시/디자인/건축/독립영화·음악 위주
POSITIVE_KEYWORDS = [
    # 핵심 미술/예술
    "전시", "갤러리", "박물관", "뮤지엄", "비엔날레", "아트페어",
    "작품", "작가", "큐레이터", "큐레이션", "도슨트",
    "회화", "조각", "조형", "설치미술", "미디어아트", "디지털아트",
    # 디자인/창작 (패션 제외)
    "디자인", "디자이너", "일러스트", "그래픽", "타이포",
    "건축", "건축가", "공간디자인", "인테리어", "프로덕트디자인",
    "사진작가", "사진집", "포토그래퍼", "포토북",
    # 문학/출판
    "독립서점", "에세이", "문학", "시집", "출판", "북페어", "도서",
    "책", "독서", "신간", "추천도서", "필독서", "베스트셀러",
    # 인문학/인사이트 (사용자 강력 선호 톤)
    "인사이트", "insight", "인문", "인문학", "철학", "사유", "사색",
    "성찰", "단상", "에세이", "칼럼", "글", "쓰기",
    "통찰", "관점", "시선", "이야기", "내러티브",
    # 사회/현상/데이터 (시의성 + 인사이트)
    "청년", "세대", "mz", "젠지", "z세대", "밀레니얼",
    "사회", "사회적", "시대", "시대정신", "현상",
    "데이터", "통계", "조사", "설문", "리포트", "보고서",
    "트렌드 분석", "트렌드리포트", "트렌드 리포트",
    "노동", "일자리", "직업", "커리어", "직장인",
    "주거", "주택", "1인 가구",
    "정책", "복지", "교육",
    "환경", "기후", "지구", "탄소", "비건", "지속가능",
    "역사", "인류", "고고학",
    # 공간/문화 (장소·팝업·런칭 — 아트아트가 좋아함)
    "팝업", "팝업스토어", "팝업전시", "팝업공간",
    "공방", "스튜디오", "레지던시", "아카이브", "쇼룸",
    "독립공간", "복합문화공간",
    "신규 오픈", "신규오픈", "오픈", "opening", "그랜드 오픈",
    "런칭 이벤트", "launch event", "런칭쇼", "프리뷰",
    "콘셉트 스토어", "컨셉 스토어", "concept store", "플래그십",
    # 웰니스/라이프스타일 공간 (소재공유방 패턴)
    "웰니스", "wellness", "사우나", "콜드플런지", "리커버리",
    "필라테스", "요가", "명상", "리트릿",
    "라이프스타일 공간", "라이프스타일",
    # 핫플 동네
    "압구정", "성수", "한남", "청담", "이태원", "연남", "용산", "도산",
    "익선동", "을지로", "북촌", "삼청동", "서촌", "효창",
    # 영화/공연 (대중상업 X, 아트하우스 O)
    "영화제", "독립영화", "다큐멘터리", "단편영화", "아트하우스",
    "연극", "뮤지컬", "퍼포먼스", "현대무용",
    # 음악 (장르 위주, 아이돌 X)
    "재즈", "클래식", "인디", "포크", "앰비언트", "lp",
    "라이브하우스", "공연장",
    # 여행/문화공간
    "여행지", "동네", "골목", "지역", "로컬",
    # 영어 (substring 매칭이라 "art" 단독은 "아트에는" 같은 무관 매칭 일으킴 → 제외)
    "exhibition", "exhibit", "gallery", "museum", "artist", "curator",
    "designer", "architecture", "biennale", "artwork",
    "indie film", "documentary", "editorial",
    "vintage", "handcraft",
]

# 하드 제외 — 1개라도 매칭되면 후보 자체에서 컷 (아이돌/배우/격투기)
HARD_EXCLUDE_KEYWORDS = [
    # === K-pop 그룹/아이돌 ===
    "에이티즈", "ateez", "르세라핌", "lesserafim", "세븐틴", "seventeen",
    "트와이스", "twice", "뉴진스", "newjeans", "에스파", "aespa",
    "아이브", "ive", "블랙핑크", "blackpink", "방탄소년단", "bts",
    "엑소", "exo", "빅뱅", "bigbang", "스트레이키즈", "straykids",
    "있지", "itzy", "프로듀스", "produce101", "보이즈플래닛", "걸스플래닛",
    "샤이니", "shinee", "투바투", "txt", "엔하이픈", "enhypen",
    "데이식스", "day6", "투모로우바이투게더", "더보이즈", "theboyz",
    "(여자)아이들", "스키즈", "키스오브라이프", "젯츠", "라이즈", "riize",
    "베이비몬스터", "babymonster", "키스오브라이프", "코르티스", "cortis",
    "보넥도", "nct", "엔시티", "재즈프", "투어스", "tws", "제로베이스원",
    "zerobaseone", "zb1", "아이엠이즈", "엔믹스", "nmixx", "le sserafim",
    "헌트릭스", "huntr/x",
    # K-pop 멤버 이름 (캡션 상위 등장)
    "민기", "원영", "장원영", "카즈하", "태양", "지수", "제니", "리사", "로제",
    "정국", "지민", "뷔", "지드래곤", "권지용",
    # K-pop 관련 공통어 (컴백/앨범/MV)
    "정규앨범", "정규2집", "정규3집", "타이틀곡", "뮤직비디오", "mv공개",
    "컴백", "comeback", "케이팝", "k-pop", "kpop", "아이돌", "idol",
    "솔로데뷔", "솔로앨범", "팬미팅", "팬싸인회", "콘서트투어", "월드투어",
    # === 배우/셀럽 화보·인터뷰 콘텐츠 ===
    "배우", "actor", "actress",
    "화보", "필모", "필모그래피", "프로필 컷",
    "촬영장 비하인드", "촬영 현장", "촬영장에서", "촬영 비하인드",
    "솔로 프로젝트", "솔로프로젝트",
    # === 예능/방송/연예인 콘텐츠 (TV쇼·토크쇼·예능 출연 소식) ===
    "예능", "variety show",
    "예고편", "토크쇼", "talk show",
    "출연하는", "출연한", "출연했던", "출연 확정", "캐스팅",
    "출연합니다", "출연한다", "출연했다", "출연했어요", "출연 예정",
    "주연", "주연을 맡", "특별 출연",
    # === 콘서트 티켓팅·투어 (가수 솔로 포함) ===
    "콘서트 티켓", "티켓팅", "티켓 오픈", "티켓오픈", "예매 오픈", "선예매",
    "흠뻑쇼", "summer swag", "여름 콘서트", "단독 콘서트",
    "내한 공연", "내한공연", "내한 콘서트",
    # === 피겨/스포츠 IP 쇼 ===
    "아이스쇼", "아이스 쇼", "ice show",
    "차준환", "김연아", "손흥민", "이강인", "황희찬", "박지성",
    "첫 방송", "방송 활동", "방송 활동을 중단", "방송 중단", "방송되니",
    "투병", "갑상선암", "유방암", "병 투병",
    "코미디언", "개그우먼", "개그맨",
    "유재석", "강호동", "신동엽", "김구라", "전현무", "이수근", "박나래",
    "이광수", "김우빈", "도경수", "지예은", "송강호", "박서준", "이병헌",
    "콩콩팜팜", "콩콩", "런닝맨", "무한도전", "나 혼자 산다", "나혼자산다",
    "1박 2일", "놀면 뭐하니", "놀면뭐하니", "유 퀴즈", "유퀴즈",
    "동물농장", "솔로지옥", "환승연애",
    "tvn 예능", "jtbc 예능", "mbc 예능", "kbs 예능", "sbs 예능",
    "넷플릭스 예능", "넷플릭스 시리즈", "디즈니플러스 시리즈",
    # 래퍼/뮤지션 개인 굿즈·SNS 홍보
    "스윙스", "사이먼도미닉", "다이나믹듀오", "지코", "비와이",
    "인생네컷 프레임", "프레임 출시",
    # 가수 솔로 (한국 대중가수)
    "싸이", "psy", "아이유", "iu", "임영웅", "장윤정", "박재범", "박효신",
    "성시경", "윤종신", "장기하", "혁오", "잔나비",
    # 유튜버/인플루언서 (개인 채널 홍보 콘텐츠)
    "유튜버", "유튜브 채널", "구독자", "인플루언서",
    "브이로그", "vlog", "먹방", "겟레디위드미",
    # === 격투기/스포츠 ===
    "ufc", "복싱", "맥그리거", "권투", "격투기", "kickboxing", "mma",
    "wwe", "프로레슬링",
    # === 패션 (산업·트렌드·스타일링 콘텐츠) ===
    "패션", "fashion", "패션위크", "fashion week", "fashionweek",
    "패션쇼", "fashion show", "런웨이", "runway",
    "룩북", "lookbook", "lookbooks",
    "코디", "스타일링", "ootd", "outfit", "outfits",
    "신상 컬렉션", "신상컬렉션", "캡슐 컬렉션", "캡슐컬렉션",
    "프리폴", "리조트 컬렉션",
    "스트릿 패션", "스트릿패션", "street fashion",
    "잇템", "꿀템",
    # === 명품/럭셔리 단독 콘텐츠 ===
    "프라다", "구찌", "샤넬", "루이비통", "에르메스", "디올",
    "발렌시아가", "생로랑", "셀린느", "보테가", "버버리",
    "페라가모", "베르사체", "발렌티노", "지방시", "프리츠",
    "크롬하츠", "메종마르지엘라",
    # === 광고/브랜드 협업 ===
    "제작지원", "광고", "협찬",
    "한정판", "한정 판매", "한정판매", "리미티드 에디션", "limited edition",
    "올리브영 단독", "29cm 단독", "무신사 단독", "쿠팡 단독",
    "단독 판매", "단독판매", "단독 발매", "선주문",
    "프로모션", "이벤트 응모", "리뷰 이벤트", "당첨자 발표",
    # === 식음료 신제품 출시 (광고성) ===
    "성심당", "신제품 출시", "신상 출시", "신메뉴 출시", "신메뉴",
    "출시합니다", "출시되었", "출시된", "출시 예정", "공식 출시",
    "시즌 한정", "여름 시즌", "겨울 시즌", "시즌한정",
    "케이크 출시", "베이커리 신상", "디저트 신상",
    "런칭합니다", "선보입니다", "공개합니다", "공개했습니다", "공개되었",
    "공개된", "공개된다",
    # === 브랜드 협업/콜라보 컬렉션 ===
    "협업 컬렉션", "협업 라인", "콜라보 컬렉션", "콜라보",
    "콜라보레이션", "collaboration", "콜렉션 공개", "컬렉션 공개",
    "협업을 공개", "협업을 진행",
    # === 음반 발매·신곡 (래퍼/뮤지션 본인 홍보) ===
    "발매됩니다", "발매되었", "발매된", "발매 예정", "앨범 발매",
    "신보 발매", "신곡 발매", "신보를", "정규 발매",
    "커버 아트", "타이틀곡 공개", "선공개", "선공개곡",
]

# 소프트 페널티 — 1개 적중당 30% 컷 (애매한 케이스)
NEGATIVE_KEYWORDS = [
    "셀카", "일상룩", "데일리룩", "출근룩", "데이트룩",
    "공항패션", "공항룩", "신곡", "신보", "신보발매",
    "팬덤", "팬싸",
]

DEFAULT_TOP = 3
DEFAULT_LIMIT = 30
PER_ACCOUNT_POOL = 3   # 계정당 최고 N개 후보 추림
JACCARD_THRESHOLD = 0.30  # 토큰 겹침 이상이면 중복 소재로 간주
EXCLUDED_TYPES = {"Video"}  # 릴스/동영상 제외

# 슬롯별 윈도우 (hours_old 기준)
SLOT_WINDOWS = {
    "morning": (12, 36),   # 어제 새벽~오늘 새벽
    "noon":    (0, 15),    # 어제저녁~지금
    "evening": (0, 9),     # 오늘 오전~지금
    "now":     (0, 36),    # 즉시 테스트용
}


def post_tokens(post: dict) -> set[str]:
    """캡션·해시태그에서 한글 2자+ / 영문 3자+ 토큰 추출 (소재 비교용)."""
    text = (post.get("caption") or "").lower()
    tokens = set(re.findall(r"[가-힣]{2,}|[a-z]{3,}", text))
    for tag in post.get("hashtags") or []:
        tokens.add(str(tag).lower())
    # 공통 불용어 제거
    stop = {"the", "and", "for", "you", "this", "that", "with", "from",
            "have", "are", "was", "은", "는", "이", "가", "을", "를",
            "에서", "에게", "와", "과", "의", "도", "만", "에", "하다"}
    return tokens - stop


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_excluded_type(post: dict) -> bool:
    return (post.get("type") or "") in EXCLUDED_TYPES


def is_hard_excluded(post: dict) -> tuple[bool, str]:
    """하드 제외 키워드 1개라도 매칭되면 컷."""
    text = (post.get("caption") or "")
    for tag in post.get("hashtags") or []:
        text += " " + str(tag)
    text = text.lower()
    for kw in HARD_EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return True, kw
    return False, ""


def topic_multiplier(post: dict) -> tuple[float, int, int]:
    """ARTART 톤 매칭 multiplier + (pos_hits, neg_hits) 디버그용 반환.

    pos: +25% per hit (최대 2.5x) — 인문학·인사이트 콘텐츠를 트래픽만 높은 글보다 위로
    neg: -30% per hit (최소 0.2x)
    """
    text = (post.get("caption") or "")
    for tag in post.get("hashtags") or []:
        text += " " + str(tag)
    text = text.lower()
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw.lower() in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in text)
    mult = (1.0 + 0.25 * pos) * (0.70 ** neg)
    return max(0.20, min(2.50, mult)), pos, neg


def cultural_bonus(post: dict) -> float:
    """Legacy alias (display only). 실제 점수는 topic_multiplier."""
    m, _, _ = topic_multiplier(post)
    return m


def adjusted_score(post: dict, account_weight: float) -> float:
    base = post.get("_score") or 0
    m, pos, neg = topic_multiplier(post)
    post["_topic_mult"] = m
    post["_pos_hits"] = pos
    post["_neg_hits"] = neg
    return round(base * account_weight * m, 3)


SENT_RETENTION_HOURS = 7 * 24  # 7일 보관 (토픽 중복 체크 윈도우)


def load_sent_state(path=None) -> dict[str, dict]:
    """{shortCode: {sent_at, tokens, caption_preview}} 형태로 로드.
    구버전 (값이 string인 timestamp)도 자동 마이그레이션.
    """
    path = path or STATE_PATH
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    result: dict[str, dict] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            result[k] = v
        elif isinstance(v, str):
            # 구버전 마이그레이션
            result[k] = {"sent_at": v, "tokens": [], "caption_preview": ""}
    return result


def save_sent_state(state: dict[str, dict], path=None) -> None:
    path = path or STATE_PATH
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    fresh = {}
    for code, entry in state.items():
        if not isinstance(entry, dict):
            continue
        try:
            t = dt.datetime.fromisoformat(entry["sent_at"])
            if (now - t).total_seconds() < SENT_RETENTION_HOURS * 3600:
                fresh[code] = entry
        except (ValueError, KeyError, TypeError):
            continue
    path.write_text(
        json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def collect_trending(
    accounts: list[tuple[str, str, float]],
    window: tuple[float, float],
    top_n: int,
    sent_state: dict[str, dict],
    per_account_top: int | None = None,
) -> list[dict]:
    """계정별 후보 → 토픽 dedup → 최종 선별.

    per_account_top=None  : 전체 통합 점수순 TOP {top_n} (기본).
    per_account_top=N     : 계정별 TOP N만 뽑고 중복 기사 제거 후 계정순 정렬.

    Greedy dedup: 점수 높은 순서로 선택, 이미 선택된 것과 토큰 Jaccard 유사도가
    임계치 이상이면 같은 소재(중복 기사)로 보고 스킵.
    릴스(type='Video')는 전 단계에서 제외.
    """
    low, high = window
    sent_codes = set(sent_state.keys())
    sent_token_sets = [
        set(entry.get("tokens") or []) for entry in sent_state.values()
    ]
    sent_token_sets = [tk for tk in sent_token_sets if tk]

    pool: list[dict] = []
    total_topic_dupes = 0
    for handle, label, weight in accounts:
        posts = load_posts(handle)
        if not posts:
            print(f"  [{handle}] posts.jsonl 비어있음 — 스킵")
            continue
        score_posts(posts, baseline_window=30)

        account_candidates = []
        excluded_reels = 0
        excluded_hard = 0
        excluded_topic_dupe = 0
        for p in posts:
            if p.get("_hidden_likes"):
                continue
            if is_excluded_type(p):
                excluded_reels += 1
                continue
            age_h = p.get("_age_hours") or 999
            if not (low <= age_h <= high):
                continue
            if (p.get("shortCode") or "") in sent_codes:
                continue
            hard, hit_kw = is_hard_excluded(p)
            if hard:
                excluded_hard += 1
                continue
            # 슬랙에 이미 보낸 콘텐츠와 토픽 중복 체크
            tokens = post_tokens(p)
            topic_dupe = False
            for sent_tk in sent_token_sets:
                if jaccard(tokens, sent_tk) >= JACCARD_THRESHOLD:
                    topic_dupe = True
                    break
            if topic_dupe:
                excluded_topic_dupe += 1
                total_topic_dupes += 1
                continue
            p["_label"] = label
            p["_account_weight"] = weight
            p["_adj_score"] = adjusted_score(p, weight)
            p["_cultural_bonus"] = p.get("_topic_mult") or 1.0
            p["_tokens"] = tokens
            account_candidates.append(p)

        account_candidates.sort(key=lambda x: x.get("_adj_score") or 0, reverse=True)
        slice_n = per_account_top or PER_ACCOUNT_POOL
        top_per_account = account_candidates[:slice_n]
        pool.extend(top_per_account)
        print(
            f"  [{handle}] 후보 {len(top_per_account)}개 채택 "
            f"(통과 {len(account_candidates)}, 릴스 {excluded_reels}, "
            f"하드제외 {excluded_hard}, 슬랙중복 {excluded_topic_dupe}, "
            f"전체 {len(posts)}, weight {weight}x)"
        )

    # 토픽 dedup (greedy by score)
    pool.sort(key=lambda p: p.get("_adj_score") or 0, reverse=True)
    selected: list[dict] = []
    for p in pool:
        tk = post_tokens(p)
        dup = False
        for s in selected:
            sim = jaccard(tk, s.get("_tokens") or set())
            if sim >= JACCARD_THRESHOLD:
                dup = True
                print(
                    f"  [dedup] '{(p.get('caption') or '')[:30]}...' "
                    f"≈ '{(s.get('caption') or '')[:30]}...' (sim={sim:.2f}) → 스킵"
                )
                break
        if dup:
            continue
        p["_tokens"] = tk
        selected.append(p)
        if per_account_top is None and len(selected) >= top_n:
            break

    if per_account_top is not None:
        # 계정 등록 순서대로, 각 계정 내부는 점수 내림차순 정렬
        order = {h: i for i, (h, _, _) in enumerate(accounts)}
        selected.sort(
            key=lambda p: (order.get(p.get("owner"), 999),
                           -(p.get("_adj_score") or 0))
        )
    return selected


RANK_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def clean_title(caption: str, max_len: int = 55) -> str:
    """캡션에서 깔끔한 한 줄 제목 추출. 첫 문장만, URL/연속이모지 정리."""
    if not caption:
        return ""
    # 첫 줄
    text = caption.split("\n")[0]
    # 문장 종결로 자르기
    m = re.search(r"[.!?。…]", text)
    if m:
        text = text[: m.start()]
    # URL 제거
    text = re.sub(r"https?://\S+", "", text)
    # (@xxx) 괄호 전체 제거 — '싸이(@42psy42)' → '싸이'
    text = re.sub(r"\s*\(\s*@\S+?\s*\)", "", text)
    # 남은 @멘션, #해시태그 제거
    text = re.sub(r"[@#]\S+", "", text)
    # 같은 이모지 연속 → 1개로
    text = re.sub(r"(\W)\1{2,}", r"\1", text)
    # 공백 정리
    text = re.sub(r"\s+", " ", text).strip()
    # 양끝 점/쉼표/물결 제거
    text = text.strip(" .,~-—_·")
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def format_likes(n: int) -> str:
    if n >= 10000:
        return f"{n / 10000:.1f}만"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def format_post_message(rank: int, total: int, p: dict) -> dict:
    rank_emoji = RANK_EMOJI[rank - 1] if rank <= len(RANK_EMOJI) else f"{rank}."
    label = p.get("_label") or p.get("owner")
    title = clean_title(p.get("caption") or "")
    likes = p.get("likes") or 0
    comments = p.get("comments") or 0
    url = p.get("url") or ""

    lines = [f"{rank_emoji} *{title}*" if title else f"{rank_emoji}"]
    meta_bits = [f"@{p.get('owner')}"]
    if label and label != p.get("owner"):
        meta_bits.append(label)
    meta_bits.append(f"♥{format_likes(likes)}")
    if comments:
        meta_bits.append(f"💬{format_likes(comments)}")
    lines.append(" · ".join(meta_bits))
    lines.append(url)
    return {"text": "\n".join(lines)}


def post_to_slack(webhook_url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Slack HTTP {resp.status}: {resp.read()!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="외부 IG 시의성 TOP → Slack")
    parser.add_argument(
        "--profile", choices=list(PROFILES.keys()), default="today",
        help="발송 프로필 (today=투데이 소재공유방 / storica=스토리카 소재공유방)",
    )
    parser.add_argument(
        "--slot", choices=list(SLOT_WINDOWS.keys()), default="now",
        help="시간대 (morning=9:30 / noon=12:00 / evening=18:00 / now=테스트)",
    )
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--no-send", action="store_true")
    parser.add_argument("--no-rescrape", action="store_true")
    parser.add_argument("--no-dedup", action="store_true", help="이전 발송 무시")
    parser.add_argument(
        "--with-images", action="store_true",
        help="이미지도 다운로드 (느림 — 카드뉴스 소재용. 기본은 스킵)",
    )
    parser.add_argument(
        "--backfill", type=int, default=None,
        help="첫 실행용: 계정별 N개 긁어 baseline 쌓기",
    )
    args = parser.parse_args()

    slot_label_map = {
        "morning": "🌅 아침 9:30",
        "noon":    "☀️ 점심 12:00",
        "evening": "🌆 저녁 18:00",
        "now":     "🧪 즉시 테스트",
    }
    slot_label = slot_label_map[args.slot]
    window = SLOT_WINDOWS[args.slot]

    prof = PROFILES[args.profile]
    accounts = prof["accounts"]
    state_path = OUTPUT_DIR / f".sent_slack_state{prof['state_suffix']}.json"
    print(f"[profile] {args.profile} — {len(accounts)}개 계정 → {prof['webhook_env']}")

    env = load_env(ENV_PATH)
    env_os = {**os.environ}

    if not args.no_rescrape:
        token = env.get("APIFY_TOKEN") or env_os.get("APIFY_TOKEN")
        if not token:
            print("ERROR: APIFY_TOKEN 없음 (.env)", file=sys.stderr)
            return 2
        limit = args.backfill or DEFAULT_LIMIT
        handles = [h for h, _, _ in accounts]
        img_mode = "이미지 포함" if args.with_images else "메타데이터만 (빠름)"
        print(f"[scrape] Apify {len(handles)}개 계정 × {limit}개 ({img_mode})...")
        try:
            by_owner = scrape_accounts(
                token, handles, limit, download_images=args.with_images
            )
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: Apify 호출 실패: {e}", file=sys.stderr)
            return 3
        for owner, posts in by_owner.items():
            account_dir = REFERENCES_DIR / owner
            write_posts_jsonl(posts, account_dir)
            print(f"[scrape] {owner}: {len(posts)}개 갱신")

    state = {} if args.no_dedup else load_sent_state(state_path)
    top_posts = collect_trending(
        accounts, window, args.top, state,
        per_account_top=prof.get("per_account_top"),
    )

    print(f"\n=== {slot_label} TOP {len(top_posts)} (윈도우 {window[0]}-{window[1]}h) ===")
    for i, p in enumerate(top_posts, 1):
        print(
            f"  {i}. [{p['owner']}] adj={p['_adj_score']:.2f} "
            f"(base {p['_score']:.2f} × w{p['_account_weight']} × 🎨{p['_cultural_bonus']:.2f}) "
            f"[+{p.get('_pos_hits',0)}/-{p.get('_neg_hits',0)}] "
            f"♥{p.get('likes',0)} {p.get('url')}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / f"{dt.date.today().isoformat()}_{args.slot}_trending.json"
    log_path.write_text(
        json.dumps(top_posts, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    if args.no_send:
        print("\n[send] --no-send: 발송 생략")
        return 0
    if not top_posts:
        print("\n[send] 후보 없음 — 발송 생략")
        return 0

    wh_env = prof["webhook_env"]
    webhook = env.get(wh_env) or env_os.get(wh_env)
    if not webhook:
        print(f"ERROR: {wh_env} 없음 (.env / 환경변수)", file=sys.stderr)
        return 4

    # 헤더 메시지 1개 + 각 포스트 별개 메시지
    today_str = dt.date.today().strftime("%-m/%-d")
    header = {
        "text": f"{prof['header_emoji']} *{today_str} {slot_label} · "
                f"{prof['header_title']} TOP {len(top_posts)}*",
    }
    try:
        post_to_slack(webhook, header)
        for i, p in enumerate(top_posts, 1):
            payload = format_post_message(i, len(top_posts), p)
            post_to_slack(webhook, payload)
            code = p.get("shortCode") or ""
            if code:
                state[code] = {
                    "sent_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "tokens": sorted(p.get("_tokens") or set()),
                    "caption_preview": (p.get("caption") or "")[:120],
                }
            time.sleep(1.0)  # Slack rate limit (1 msg/sec/webhook)
        print(f"\n[send] Slack 발송 완료 (헤더 + {len(top_posts)}개)")
        save_sent_state(state, state_path)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
        print(f"ERROR: Slack 발송 실패: {e}", file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
