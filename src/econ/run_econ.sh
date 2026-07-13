#!/bin/bash
# 경제 소재공유방 데일리 발송 (로컬 실행)
# 1) Apify 로 IG 4계정 스크랩(순수 stdlib) → outputs/econ/ig_posts.json
# 2) headless claude 가 인베스팅/토스/교훈성 리서치 + dedup + 포맷 + 웹후크 발송
set -euo pipefail

# launchd 는 최소 PATH·HOME 만 줌 → 경로 명시.
# ⚠️ 계정명 하드코딩 금지 — 이 맥북은 /Users/munsok, 집맥은 /Users/dev_munsok 이다.
: "${HOME:=$(eval echo ~"$(id -un)")}"
export HOME
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJ="$HOME/code/artart-cardnews-automation"
cd "$PROJ"

# 슬롯: daily(매일 오후3시 시의성) / lesson(금요일 오후3시 교훈성 7개). 기본 daily.
export ECON_SLOT="${1:-daily}"

# .env 에서 APIFY_TOKEN / SLACK_ECON_WEBHOOK_URL 읽어 자식 프로세스 env 로 전달
set -a
# shellcheck disable=SC1091
source "$PROJ/.env"
set +a

LOG_DIR="$PROJ/outputs/econ"
mkdir -p "$LOG_DIR"
STAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "===== $STAMP : econ 실행 시작 (slot=$ECON_SLOT) =====" >> "$LOG_DIR/run.log"

# 슬롯별 프롬프트 선택. lesson(교훈성)은 IG 스크랩 불필요.
if [ "$ECON_SLOT" = "lesson" ]; then
  PROMPT_FILE="$PROJ/src/econ/econ_lesson_prompt.md"
else
  PROMPT_FILE="$PROJ/src/econ/econ_prompt.md"
  # 1) IG 스크랩 (실패해도 기존 ig_posts.json 보존, claude 가 있는 것만 발송)
  python3 "$PROJ/src/econ/scrape_ig.py" >> "$LOG_DIR/run.log" 2>&1 || \
    echo "[warn] scrape_ig 실패 — 기존 ig_posts.json 으로 진행(없으면 IG 생략)" >> "$LOG_DIR/run.log"
fi

# 2) headless claude. --dangerously-skip-permissions: launchd 는 권한 프롬프트에 답 불가.
# 다른 API 키가 구독 토큰을 가로채지 않게 제거 (Max 구독 헤드리스는 CLAUDE_CODE_OAUTH_TOKEN 사용)
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
claude -p "$(cat "$PROMPT_FILE")" \
  --dangerously-skip-permissions \
  >> "$LOG_DIR/run.log" 2>&1

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') : econ 실행 종료 (exit=$?) =====" >> "$LOG_DIR/run.log"
