#!/bin/bash
# 에이밍 데일리 카드뉴스 — 무인 제작·발행 러너 (launchd 진입점)
# 1) 경제 IG 소재 갱신 (artart 리포 scrape_ig.py 재사용)
# 2) headless claude 가 소재 선정 → 제작 → 렌더 → 검수 → 인스타 발행
set -euo pipefail

# launchd 는 최소 환경만 준다 — HOME 이 비어 있을 때만 계정에서 유추 (계정명 하드코딩 금지)
: "${HOME:=$(eval echo ~$(id -un))}"
export HOME
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

KIT="$HOME/code/aiming-cardnews-kit"
ARTART="$HOME/code/artart-cardnews-automation"
cd "$KIT"

# APIFY_TOKEN 등은 artart 리포 .env 공용
set -a
# shellcheck disable=SC1091
source "$ARTART/.env"
set +a

LOG_DIR="$KIT/logs"
mkdir -p "$LOG_DIR"
echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') : aiming daily 시작 =====" >> "$LOG_DIR/auto.log"

# 1) IG 소재 갱신 (실패해도 기존 파일로 진행)
python3 "$ARTART/src/econ/scrape_ig.py" >> "$LOG_DIR/auto.log" 2>&1 || \
  echo "[warn] scrape_ig 실패 — 기존 ig_posts.json 으로 진행" >> "$LOG_DIR/auto.log"

# 2) headless claude (launchd 는 권한 프롬프트에 답 불가)
claude -p "$(cat "$KIT/auto/aiming_daily_prompt.md")" \
  --dangerously-skip-permissions \
  >> "$LOG_DIR/auto.log" 2>&1

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') : aiming daily 종료 (exit=$?) =====" >> "$LOG_DIR/auto.log"
